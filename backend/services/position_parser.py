"""
Position parsing — Extract portfolio positions from CSV, Excel, PDF, and image uploads.

Extracted from server.py for modularization.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Literal

import pandas as pd
from fastapi import HTTPException, UploadFile

from services.utils import normalize_header as _normalize_header, to_float as _to_float

# Optional heavy dependencies
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from pdf2image import convert_from_bytes
except ImportError:
    convert_from_bytes = None

# ── Header aliases for position columns ──
SYMBOL_HEADERS = {
    "symbol", "tradingsymbol", "stock", "name", "security", "instrument",
}
AVG_HEADERS = {
    "avg_price", "average_price", "avgprice", "buy_price", "avgcost",
    "buyprice", "average", "buy avg price", "avg cost", "avg. price",
    "purchase price", "avg acquisition",
}
QTY_HEADERS = {
    "qty", "quantity", "qnty", "shares", "units", "net qty",
    "holding", "holding qty",
}


def _is_tesseract_ready() -> bool:
    if pytesseract is None:
        return False
    try:
        _ = pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _find_column(headers: list[str], aliases: set[str]) -> int | None:
    normalized = [_normalize_header(item) for item in headers]
    alias_normalized = {_normalize_header(alias) for alias in aliases}
    for idx, item in enumerate(normalized):
        if item in alias_normalized:
            return idx
    return None


def normalize_positions_from_rows(rows: list[list[object]], headers: list[str]) -> list[dict]:
    if not headers:
        return []
    symbol_idx = _find_column(headers, SYMBOL_HEADERS)
    avg_idx = _find_column(headers, AVG_HEADERS)
    qty_idx = _find_column(headers, QTY_HEADERS)
    positions: list[dict] = []
    for row in rows:
        symbol = ""
        avg_price = None
        quantity = None

        if symbol_idx is not None and avg_idx is not None and qty_idx is not None:
            if max(symbol_idx, avg_idx, qty_idx) >= len(row):
                continue
            symbol = str(row[symbol_idx]).strip().upper()
            avg_price = _to_float(row[avg_idx])
            quantity = _to_float(row[qty_idx])
        else:
            non_empty_cells = [cell for cell in row if str(cell).strip()]
            if len(non_empty_cells) < 3:
                continue
            numeric_cells = [_to_float(cell) for cell in non_empty_cells]
            numeric_indexes = [idx for idx, value in enumerate(numeric_cells) if value is not None]
            if len(numeric_indexes) < 2:
                continue
            symbol_candidates = [
                str(non_empty_cells[idx]).strip().upper()
                for idx, value in enumerate(numeric_cells)
                if value is None
            ]
            if not symbol_candidates:
                continue
            symbol = symbol_candidates[0]
            avg_price = numeric_cells[numeric_indexes[0]]
            quantity = numeric_cells[numeric_indexes[1]]

        if not symbol or avg_price is None or quantity is None or quantity <= 0:
            continue
        cleaned_symbol = re.sub(r"\s+", " ", str(symbol).strip().upper())
        if len(re.sub(r"[^A-Z0-9]", "", cleaned_symbol)) < 2:
            continue
        positions.append({
            "symbol": cleaned_symbol,
            "avg_price": round(avg_price, 4),
            "quantity": round(quantity, 4),
        })
    return positions


def _detect_qty_avg_orientation(lines: list[str]) -> Literal["QTY_FIRST", "AVG_FIRST"] | None:
    for line in lines[:8]:
        normalized = _normalize_header(line)
        if not normalized:
            continue
        tokens = normalized.split()
        qty_index = next((idx for idx, token in enumerate(tokens) if token in {"qty", "quantity", "holding", "units", "shares"}), None)
        avg_index = next((idx for idx, token in enumerate(tokens) if token in {"avg", "average", "cost", "buy", "price", "acquisition"}), None)
        if qty_index is None or avg_index is None:
            continue
        return "QTY_FIRST" if qty_index < avg_index else "AVG_FIRST"
    return None


def _pick_avg_and_qty(
    first_num: float,
    second_num: float,
    orientation: Literal["QTY_FIRST", "AVG_FIRST"] | None,
) -> tuple[float, float]:
    if orientation == "QTY_FIRST":
        return second_num, first_num
    if orientation == "AVG_FIRST":
        return first_num, second_num

    first_is_int = abs(first_num - round(first_num)) < 1e-9
    second_is_int = abs(second_num - round(second_num)) < 1e-9

    if first_is_int and not second_is_int:
        return second_num, first_num
    if second_is_int and not first_is_int:
        return first_num, second_num

    if first_num > 10000 and second_num <= 10000:
        return second_num, first_num
    if second_num > 10000 and first_num <= 10000:
        return first_num, second_num

    if first_num <= 10 and second_num >= 20:
        return second_num, first_num
    if second_num <= 10 and first_num >= 20:
        return first_num, second_num

    return first_num, second_num


def extract_positions_from_text_lines(text: str) -> list[dict]:
    positions: list[dict] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    orientation = _detect_qty_avg_orientation(lines)
    pattern = re.compile(r"^([A-Za-z][A-Za-z0-9&.\- ]+?)\s+([0-9][0-9,\.]*?)\s+([0-9][0-9,\.]*)(?:\s|$)")
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        symbol, first_txt, second_txt = match.groups()
        first_num = _to_float(first_txt)
        second_num = _to_float(second_txt)
        if first_num is None or second_num is None:
            continue
        avg_price, quantity = _pick_avg_and_qty(first_num, second_num, orientation)
        if avg_price is None or quantity is None or quantity <= 0:
            continue
        cleaned = re.sub(r"\s+", " ", symbol.upper()).strip()
        if len(cleaned) < 2:
            continue
        positions.append({"symbol": cleaned, "avg_price": avg_price, "quantity": quantity})

    unique: dict[str, dict] = {}
    for item in positions:
        unique[item["symbol"]] = item
    return list(unique.values())


def parse_positions_from_csv_text(content: str) -> list[dict]:
    sample = content[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = [row for row in reader if row and any(str(cell).strip() for cell in row)]
    if not rows:
        return []

    header_idx = 0
    for idx, row in enumerate(rows[:5]):
        normalized = {_normalize_header(str(item)) for item in row}
        if normalized.intersection({_normalize_header(x) for x in SYMBOL_HEADERS}) and normalized.intersection({_normalize_header(x) for x in AVG_HEADERS}):
            header_idx = idx
            break

    headers = [str(value).strip() for value in rows[header_idx]]
    normalized_positions = normalize_positions_from_rows(rows[header_idx + 1:], headers)
    if normalized_positions:
        return normalized_positions

    try:
        frame = pd.read_csv(io.StringIO(content))
        frame = frame.dropna(how="all")
        if not frame.empty:
            headers = [str(col).strip() for col in frame.columns]
            rows = frame.fillna("").values.tolist()
            normalized_positions = normalize_positions_from_rows(rows, headers)
            if normalized_positions:
                return normalized_positions
    except Exception:
        pass

    return extract_positions_from_text_lines(content)


def parse_positions_from_excel_bytes(content: bytes) -> list[dict]:
    frame = pd.read_excel(io.BytesIO(content), sheet_name=0)
    frame = frame.dropna(how="all")
    if frame.empty:
        return []
    headers = [str(col).strip() for col in frame.columns]
    rows = frame.fillna("").values.tolist()
    return normalize_positions_from_rows(rows, headers)


def _pil_image_to_bytes(image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def parse_positions_from_pdf_bytes(content: bytes) -> list[dict]:
    extracted_rows: list[dict] = []

    if PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            extracted_rows = extract_positions_from_text_lines(text)
        except Exception:
            extracted_rows = []

    if extracted_rows:
        return extracted_rows

    if convert_from_bytes is None or Image is None or not _is_tesseract_ready():
        return []

    try:
        page_images = convert_from_bytes(content, dpi=220, first_page=1, last_page=3)
    except Exception:
        return []

    merged_rows: list[dict] = []
    for image in page_images:
        try:
            parsed = parse_positions_from_image_bytes(_pil_image_to_bytes(image))
        except Exception:
            parsed = []
        if parsed:
            merged_rows.extend(parsed)

    unique: dict[str, dict] = {}
    for row in merged_rows:
        unique[row["symbol"]] = row
    return list(unique.values())


def parse_positions_from_image_bytes(content: bytes) -> list[dict]:
    if Image is None or not _is_tesseract_ready():
        return []

    image = Image.open(io.BytesIO(content)).convert("L")
    enhanced = image.point(lambda px: 0 if px < 160 else 255, mode="1")
    candidates = [
        pytesseract.image_to_string(image, config="--psm 6"),
        pytesseract.image_to_string(image, config="--psm 11"),
        pytesseract.image_to_string(enhanced, config="--psm 6"),
        pytesseract.image_to_string(enhanced, config="--psm 11"),
        pytesseract.image_to_data(enhanced, output_type=pytesseract.Output.STRING),
    ]

    for text in candidates:
        rows = extract_positions_from_text_lines(text)
        if rows:
            return rows

    return []


async def parse_positions_from_upload(file: UploadFile) -> list[dict]:
    filename = file.filename or ""
    extension = filename.split(".")[-1].lower() if "." in filename else ""
    payload = await file.read()

    if extension in {"txt", "csv"}:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                text = payload.decode(encoding)
                return parse_positions_from_csv_text(text)
            except Exception:
                continue
        text = payload.decode("utf-8", errors="ignore")
        return parse_positions_from_csv_text(text)

    if extension in {"xlsx", "xls"}:
        return parse_positions_from_excel_bytes(payload)

    if extension == "pdf":
        return parse_positions_from_pdf_bytes(payload)

    if extension in {"jpg", "jpeg", "bmp", "png", "webp"}:
        return parse_positions_from_image_bytes(payload)

    raise HTTPException(status_code=400, detail="Unsupported file format")
