import asyncio
import csv
import difflib
import hashlib
import io
import logging
import os
import re
import socket
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Literal
from urllib.parse import urlparse

import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from starlette.middleware.cors import CORSMiddleware

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

try:
    from pdf2image import convert_from_bytes
except Exception:  # pragma: no cover
    convert_from_bytes = None

from data.fno_contracts import FNO_CONTRACTS, get_fno_contract
from data.symbols import MULTIBAGGER_UNIVERSE
from services.market_data import get_stock_core, market_data_client

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI()
api_router = APIRouter(prefix="/api")

OWNER_BOOTSTRAP_USERNAME = os.environ.get("OWNER_BOOTSTRAP_USERNAME", "@shish123")
LEGACY_OWNER_ALIAS = os.environ.get("LEGACY_OWNER_ALIAS", "owner123")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9@._-]{6,}$")
SCRIPT_PATTERN = re.compile(r"^([A-Z]+)(\d{1,2})([A-Z]{3})(\d+)(CE|PE)$")
SESSION_STORE: Dict[str, dict] = {}
IST = timezone(timedelta(hours=5, minutes=30))

MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

LOT_SIZE_MAP = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "RELIANCE": 250,
    "BDL": 1350,
    "SBIN": 750,
    "TCS": 175,
}

STOCK_FNO_UNIVERSE = [
    "RELIANCE",
    "TCS",
    "SBIN",
    "HDFCBANK",
    "ICICIBANK",
    "INFY",
    "LT",
    "ITC",
    "AXISBANK",
    "KOTAKBANK",
    "HDFCLIFE",
    "SBILIFE",
    "ULTRACEMCO",
    "BAJFINANCE",
]

SCRIPT_MASTER_LAST_SYNC_DATE: str | None = None
NSE_SCRIPT_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
ANGEL_SCRIPT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
KITE_SCRIPT_MASTER_URL = "https://api.kite.trade/instruments"
DHAN_SCRIPT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
KITE_OPTION_MASTER_LAST_SYNC_DATE: str | None = None

KITE_API_KEY = os.environ.get("KITE_API_KEY")
KITE_API_SECRET = os.environ.get("KITE_API_SECRET")
KITE_REDIRECT_URL = os.environ.get("KITE_REDIRECT_URL")
KITE_READ_ONLY_MODE = True
KITE_ALLOWED_DATA_ENDPOINTS = [
    "/quote/ltp",
    "/instruments",
    "/instruments/historical",
]

API_CONTROL_CACHE: dict[str, object] = {
    "kite_data_enabled": True,
    "moneycontrol_data_enabled": True,
    "strict_live_only": True,
}
API_CONTROL_CACHE_TS: datetime | None = None

SYMBOL_HEADERS = {
    "symbol",
    "tradingsymbol",
    "stock",
    "name",
    "security",
    "instrument",
}
AVG_HEADERS = {
    "avg_price",
    "average_price",
    "avgprice",
    "buy_price",
    "avgcost",
    "buyprice",
    "average",
    "buy avg price",
    "avg cost",
    "avg. price",
    "purchase price",
    "avg acquisition",
}
QTY_HEADERS = {
    "qty",
    "quantity",
    "qnty",
    "shares",
    "units",
    "net qty",
    "holding",
    "holding qty",
}

NIFTY_WEIGHT_PROXY = [
    ("HDFCBANK", 13.0),
    ("RELIANCE", 9.6),
    ("ICICIBANK", 8.4),
    ("INFY", 6.0),
    ("TCS", 4.4),
    ("BHARTIARTL", 4.1),
    ("ITC", 3.8),
    ("LT", 3.5),
    ("AXISBANK", 3.1),
    ("KOTAKBANK", 2.8),
]

BANKNIFTY_WEIGHT_PROXY = [
    ("HDFCBANK", 29.0),
    ("ICICIBANK", 23.0),
    ("KOTAKBANK", 13.0),
    ("AXISBANK", 11.0),
    ("SBIN", 10.0),
    ("INDUSINDBK", 4.0),
    ("BANDHANBNK", 2.0),
    ("FEDERALBNK", 2.0),
    ("AUBANK", 2.0),
    ("PNB", 1.5),
    ("CANBK", 1.5),
    ("BANKBARODA", 1.0),
]


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class AccessRequest(BaseModel):
    username: str | None = None
    password: str | None = None


class AccessResponse(BaseModel):
    token: str
    role: Literal["owner", "sub_admin", "user"]
    credits: float
    user_key: str
    username: str
    admin_exempt: bool


class MeResponse(BaseModel):
    role: Literal["owner", "sub_admin", "user"]
    credits: float
    user_key: str
    username: str
    admin_exempt: bool


class AdminUserView(BaseModel):
    user_key: str
    username: str
    role: Literal["owner", "sub_admin", "user"]
    credits: float
    created_at: str
    created_by: str
    quota_limit: int
    quota_used: int
    credential_label: str


class AdminCreateUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    role: Literal["sub_admin", "user"] = "user"
    initial_credits: float = 0
    quota_limit: int = 10


class AdminSetCreditsRequest(BaseModel):
    credits: float


class AdminSetQuotaRequest(BaseModel):
    quota_limit: int


class AdminUserProfileUpdateRequest(BaseModel):
    username: str | None = None
    role: Literal["owner", "sub_admin", "user"] | None = None


class DomainMappingCreateRequest(BaseModel):
    domain: str
    target_record: str
    record_type: Literal["A"] = "A"


class DomainMappingStatusUpdateRequest(BaseModel):
    status: Literal["PENDING", "ACTIVE", "FAILED"]


class ApiControlUpdateRequest(BaseModel):
    kite_data_enabled: bool | None = None
    moneycontrol_data_enabled: bool | None = None
    strict_live_only: bool | None = None


class StockCoreNormalized(BaseModel):
    symbol: str
    company_name: str
    ltp: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    volume: int = 0
    market_cap: float | None = None
    pe_ratio: float | None = None
    book_value: float | None = None
    eps: float | None = None
    sector: str = "Unknown"


class MultibaggerCandidate(BaseModel):
    symbol: str
    company_name: str
    sector: str
    ltp: float | None = None
    market_cap_cr: float | None = None
    pe_ratio: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    upside_to_52w_high_pct: float | None = None
    pb_ratio_est: float | None = None
    peg_ratio_est: float | None = None
    tier_pass_count: int
    is_potential_multibagger: bool
    multibagger_score: int
    current_rsi_level: float | None = None
    gtt_buy_price: float | None = None
    targeted_upside_price: dict
    targeted_upside_profit_pct: dict
    thesis: str
    analysis_refreshed_at: str


class FNOContract(BaseModel):
    script: str
    underlying: str
    expiry: str
    expiry_time_ist: str = "15:30"
    strike: float
    option_type: Literal["CE", "PE"]
    exchange: str
    lot_size: int


class FNOSignalResponse(BaseModel):
    script: str
    underlying: str
    expiry: str
    strike: float
    option_type: Literal["CE", "PE"]
    exchange: str
    lot_size: int
    underlying_ltp: float
    option_ltp: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    strategy: str
    entry_price: float
    stop_loss: float
    target1: float
    target2: float
    risk_reward_target1: float
    risk_reward_target2: float
    trigger_factors: List[str]
    confluence_score: int
    signal_quality: Literal["HIGH", "MEDIUM", "LOW"]
    is_potential_trade: bool
    minutes_to_expiry: int
    expiry_risk: Literal["LOW", "MEDIUM", "HIGH"]
    data_source: Literal["LIVE_OPTION_CHAIN", "MODELED_FROM_SPOT"]
    analysis_refreshed_at: str


class NonDirectionalStrategy(BaseModel):
    strike: float
    strategy: str
    ce_script: str
    pe_script: str
    combined_entry: float
    rationale: str
    confidence_score: int


class IndexAnalysisReport(BaseModel):
    report_type: Literal["with_consolidated", "without_consolidated"]
    breadth_score: float
    momentum_score: float
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    top_contributors: List[str]
    summary: str


class IndexProjectionPane(BaseModel):
    index_name: Literal["NIFTY", "BANKNIFTY"]
    spot: float
    strike_range_min: float
    strike_range_max: float
    assured_signals: List[FNOSignalResponse]
    watchlist_signals: List[FNOSignalResponse]
    non_directional_strategies: List[NonDirectionalStrategy]
    rejection_note: str | None = None
    with_consolidated_report: IndexAnalysisReport
    without_consolidated_report: IndexAnalysisReport


class MultibaggerGenerateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    analysis_refreshed_at: str
    candidates: List[MultibaggerCandidate]
    potential_count: int


class FNOGenerateRequest(BaseModel):
    custom_script: str | None = None


class FNOGenerateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    analysis_refreshed_at: str
    signals: List[FNOSignalResponse]
    potential_signals: List[FNOSignalResponse]
    top_trades: List[FNOSignalResponse]
    custom_signal: FNOSignalResponse | None = None
    nifty_projection: IndexProjectionPane
    banknifty_projection: IndexProjectionPane
    stock_signals: List[FNOSignalResponse]


class PortfolioPositionInput(BaseModel):
    symbol: str
    avg_price: float
    quantity: float


class PortfolioAnalyzeRequest(BaseModel):
    positions: List[PortfolioPositionInput]


class PortfolioHorizonRange(BaseModel):
    upside_pct: float
    downside_pct: float
    flag: Literal["GREEN", "RED"]


class PortfolioExpectedSignal(BaseModel):
    max_expected_price: float
    amount_signal: str
    percent_signal: str
    direction: Literal["PROFIT", "LOSS"]


class PortfolioStockAnalysis(BaseModel):
    symbol: str
    company_name: str
    sector: str
    ltp: float
    market_cap: float | None = None
    pe_ratio: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    eps: float | None = None
    avg_price: float
    quantity: float
    allocation_pct: float
    pnl_pct: float
    value_flag: Literal["Attractive", "Fair", "Expensive"]
    price_zone: Literal["Near 52W low", "Mid range", "Near 52W high"]
    momentum_proxy: Literal["Positive trend", "Flat", "Negative trend"]
    quality_proxy: Literal["Stable quality", "Speculative", "Moderate"]
    expected_ranges: dict[str, PortfolioHorizonRange]
    expected_signals: dict[str, PortfolioExpectedSignal]
    recommendation: str
    comments: str


class PortfolioAnalyzeResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    parsed_positions_count: int
    stocks: List[PortfolioStockAnalysis]


class CustomPositionCreateRequest(BaseModel):
    script: str
    buy_price: float


class CustomPositionSellRequest(BaseModel):
    sold_price: float
    confirm: bool = True


class CustomPositionResponse(BaseModel):
    id: str
    script: str
    underlying: str
    expiry_date: str
    expiry_time_ist: str
    lot_size: int
    quantity_lots: int = 1
    units: int = 1
    buy_price: float
    created_at: str
    last_update: str
    status: Literal["OPEN", "CLOSED", "EXPIRED", "SOLD"]
    alert: str | None = None
    latest_option_ltp: float | None = None
    target1: float | None = None
    target2: float | None = None
    buy_to_ltp_diff: float | None = None
    ltp_to_t1_diff: float | None = None
    ltp_to_t2_diff: float | None = None
    target1_achieved: bool = False
    target2_achieved: bool = False
    can_sell: bool = False
    sold_price: float | None = None
    realized_pnl: float | None = None
    projected_exit_price: float | None = None
    best_exit_price: float | None = None
    recovery_potential: float | None = None
    minutes_to_expiry: int
    revised_exit_plan: str


class CustomPositionCreateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    position: CustomPositionResponse


class ScriptSearchResult(BaseModel):
    query: str
    suggestions: List[str]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _estimate_option_ltp(underlying_ltp: float, strike: float, option_type: str) -> float:
    intrinsic = (
        max(underlying_ltp - strike, 0)
        if option_type == "CE"
        else max(strike - underlying_ltp, 0)
    )
    time_value = max(underlying_ltp * 0.002, 5)
    return round(intrinsic + time_value, 2)


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "")
    if raw in {"", "-", "--", "na", "n/a", "none", "null"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


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


def _normalize_positions_from_rows(rows: list[list[object]], headers: list[str]) -> list[dict]:
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
        positions.append(
            {
                "symbol": cleaned_symbol,
                "avg_price": round(avg_price, 4),
                "quantity": round(quantity, 4),
            }
        )
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


def _extract_positions_from_text_lines(text: str) -> list[dict]:
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

    # remove duplicates by symbol keeping latest line
    unique: dict[str, dict] = {}
    for item in positions:
        unique[item["symbol"]] = item
    return list(unique.values())


def _parse_positions_from_csv_text(content: str) -> list[dict]:
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

    # detect header row flexibly
    header_idx = 0
    for idx, row in enumerate(rows[:5]):
        normalized = {_normalize_header(str(item)) for item in row}
        if normalized.intersection({_normalize_header(x) for x in SYMBOL_HEADERS}) and normalized.intersection({_normalize_header(x) for x in AVG_HEADERS}):
            header_idx = idx
            break

    headers = [str(value).strip() for value in rows[header_idx]]
    normalized_positions = _normalize_positions_from_rows(rows[header_idx + 1 :], headers)
    if normalized_positions:
        return normalized_positions

    try:
        frame = pd.read_csv(io.StringIO(content))
        frame = frame.dropna(how="all")
        if not frame.empty:
            headers = [str(col).strip() for col in frame.columns]
            rows = frame.fillna("").values.tolist()
            normalized_positions = _normalize_positions_from_rows(rows, headers)
            if normalized_positions:
                return normalized_positions
    except Exception:
        pass

    return _extract_positions_from_text_lines(content)


def _parse_positions_from_excel_bytes(content: bytes) -> list[dict]:
    frame = pd.read_excel(io.BytesIO(content), sheet_name=0)
    frame = frame.dropna(how="all")
    if frame.empty:
        return []
    headers = [str(col).strip() for col in frame.columns]
    rows = frame.fillna("").values.tolist()
    return _normalize_positions_from_rows(rows, headers)


def _parse_positions_from_pdf_bytes(content: bytes) -> list[dict]:
    extracted_rows: list[dict] = []

    if PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            extracted_rows = _extract_positions_from_text_lines(text)
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
            parsed = _parse_positions_from_image_bytes(_pil_image_to_bytes(image))
        except Exception:
            parsed = []
        if parsed:
            merged_rows.extend(parsed)

    unique: dict[str, dict] = {}
    for row in merged_rows:
        unique[row["symbol"]] = row
    return list(unique.values())


def _pil_image_to_bytes(image: "Image.Image") -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _parse_positions_from_image_bytes(content: bytes) -> list[dict]:
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
        rows = _extract_positions_from_text_lines(text)
        if rows:
            return rows

    return []


async def _parse_positions_from_upload(file: UploadFile) -> list[dict]:
    filename = file.filename or ""
    extension = filename.split(".")[-1].lower() if "." in filename else ""
    payload = await file.read()

    if extension in {"txt", "csv"}:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                text = payload.decode(encoding)
                return _parse_positions_from_csv_text(text)
            except Exception:
                continue
        text = payload.decode("utf-8", errors="ignore")
        return _parse_positions_from_csv_text(text)

    if extension in {"xlsx", "xls"}:
        return _parse_positions_from_excel_bytes(payload)

    if extension == "pdf":
        return _parse_positions_from_pdf_bytes(payload)

    if extension in {"jpg", "jpeg", "bmp", "png", "webp"}:
        return _parse_positions_from_image_bytes(payload)

    raise HTTPException(status_code=400, detail="Unsupported file format")


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()


async def _get_api_controls(force_refresh: bool = False) -> dict[str, bool]:
    global API_CONTROL_CACHE_TS
    now = datetime.now(IST)
    if (
        (not force_refresh)
        and API_CONTROL_CACHE_TS is not None
        and (now - API_CONTROL_CACHE_TS).total_seconds() < 45
    ):
        return {
            "kite_data_enabled": bool(API_CONTROL_CACHE.get("kite_data_enabled", True)),
            "moneycontrol_data_enabled": bool(API_CONTROL_CACHE.get("moneycontrol_data_enabled", True)),
            "strict_live_only": bool(API_CONTROL_CACHE.get("strict_live_only", True)),
        }

    row = await db.system_meta.find_one({"key": "api_controls"}, {"_id": 0})
    if row:
        API_CONTROL_CACHE["kite_data_enabled"] = bool(row.get("kite_data_enabled", True))
        API_CONTROL_CACHE["moneycontrol_data_enabled"] = bool(row.get("moneycontrol_data_enabled", True))
        API_CONTROL_CACHE["strict_live_only"] = bool(row.get("strict_live_only", True))
    API_CONTROL_CACHE_TS = now
    return {
        "kite_data_enabled": bool(API_CONTROL_CACHE.get("kite_data_enabled", True)),
        "moneycontrol_data_enabled": bool(API_CONTROL_CACHE.get("moneycontrol_data_enabled", True)),
        "strict_live_only": bool(API_CONTROL_CACHE.get("strict_live_only", True)),
    }


async def _sync_kite_option_master_daily(force: bool = False) -> None:
    global KITE_OPTION_MASTER_LAST_SYNC_DATE
    today = _today_ist()
    if not force and KITE_OPTION_MASTER_LAST_SYNC_DATE == today:
        return

    meta = await db.system_meta.find_one({"key": "kite_option_master_sync"}, {"_id": 0})
    if (not force) and meta and meta.get("date") == today and int(meta.get("updated_count", 0) or 0) > 0:
        KITE_OPTION_MASTER_LAST_SYNC_DATE = today
        return

    if not KITE_API_KEY:
        return

    def _load_rows() -> list[dict]:
        try:
            response = requests.get(KITE_SCRIPT_MASTER_URL, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                return []

            reader = csv.DictReader(io.StringIO(response.text))
            allowed = {"NIFTY", "BANKNIFTY", *STOCK_FNO_UNIVERSE}
            rows: list[dict] = []
            for row in reader:
                exchange = str(row.get("exchange", "")).upper().strip()
                instrument_type = str(row.get("instrument_type", "")).upper().strip()
                if exchange != "NFO" or instrument_type not in {"CE", "PE"}:
                    continue

                expiry = str(row.get("expiry", "")).strip()
                strike = _to_float(row.get("strike"))
                tradingsymbol = str(row.get("tradingsymbol", "")).strip().upper()
                if not expiry or strike is None or not tradingsymbol:
                    continue

                raw_name = str(row.get("name", "")).strip().upper()
                underlying = _normalize_symbol_key(raw_name) if raw_name else ""
                if not underlying:
                    underlying = next((symbol for symbol in allowed if tradingsymbol.startswith(symbol)), "")
                if underlying not in allowed:
                    continue

                rows.append(
                    {
                        "underlying": underlying,
                        "expiry": expiry,
                        "strike": float(strike),
                        "option_type": instrument_type,
                        "tradingsymbol": tradingsymbol,
                        "instrument": f"NFO:{tradingsymbol}",
                        "lot_size": int(_to_float(row.get("lot_size")) or LOT_SIZE_MAP.get(underlying, 1)),
                        "updated_at": _utc_now_iso(),
                    }
                )
            return rows
        except Exception as exc:
            logger.warning("Kite option master refresh failed: %s", exc)
            return []

    rows = await asyncio.to_thread(_load_rows)
    if not rows:
        return

    await db.kite_option_master.delete_many({})
    for start in range(0, len(rows), 5000):
        await db.kite_option_master.insert_many(rows[start : start + 5000], ordered=False)

    await db.system_meta.update_one(
        {"key": "kite_option_master_sync"},
        {
            "$set": {
                "key": "kite_option_master_sync",
                "date": today,
                "updated_count": len(rows),
                "updated_at": _utc_now_iso(),
            }
        },
        upsert=True,
    )
    KITE_OPTION_MASTER_LAST_SYNC_DATE = today


async def _get_kite_access_token() -> str | None:
    if not KITE_API_KEY:
        return None
    session = await db.system_meta.find_one({"key": "kite_session"}, {"_id": 0})
    if not session:
        return None
    if session.get("date") != _today_ist():
        return None
    token = str(session.get("access_token", "")).strip()
    return token or None


async def _resolve_kite_instrument_for_contract(contract: FNOContract) -> str | None:
    rows = await db.kite_option_master.find(
        {
            "underlying": contract.underlying,
            "expiry": contract.expiry,
            "option_type": contract.option_type,
        },
        {"_id": 0, "instrument": 1, "strike": 1},
    ).to_list(500)
    if not rows:
        return None

    target_strike = float(contract.strike)
    rows.sort(key=lambda item: abs(float(item.get("strike", 0.0)) - target_strike))
    best = rows[0]
    if abs(float(best.get("strike", 0.0)) - target_strike) > 0.01:
        return None
    instrument = str(best.get("instrument", "")).strip()
    return instrument or None


async def _fetch_option_ltp_from_kite(contract: FNOContract) -> float | None:
    access_token = await _get_kite_access_token()
    if not access_token or not KITE_API_KEY:
        return None

    await _sync_kite_option_master_daily()
    instrument = await _resolve_kite_instrument_for_contract(contract)
    if not instrument:
        return None

    def _fetch_ltp() -> float | None:
        try:
            response = requests.get(
                "https://api.kite.trade/quote/ltp",
                params={"i": instrument},
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {KITE_API_KEY}:{access_token}",
                },
                timeout=12,
            )
            if response.status_code != 200:
                return None
            payload = response.json()
            data = payload.get("data", {})
            row = data.get(instrument, {})
            last_price = _to_float(row.get("last_price"))
            if last_price is None or last_price <= 0:
                return None
            return float(last_price)
        except Exception:
            return None

    return await asyncio.to_thread(_fetch_ltp)


async def _fetch_option_ltps_from_kite(contracts: list[FNOContract]) -> dict[str, float]:
    access_token = await _get_kite_access_token()
    if not access_token or not KITE_API_KEY or not contracts:
        return {}

    await _sync_kite_option_master_daily()

    script_to_instrument: dict[str, str] = {}
    grouped: dict[tuple[str, str, str], list[FNOContract]] = defaultdict(list)
    for contract in contracts:
        grouped[(contract.underlying, contract.expiry, contract.option_type)].append(contract)

    for (underlying, expiry, option_type), group_contracts in grouped.items():
        rows = await db.kite_option_master.find(
            {
                "underlying": underlying,
                "expiry": expiry,
                "option_type": option_type,
            },
            {"_id": 0, "instrument": 1, "strike": 1},
        ).to_list(2000)
        if not rows:
            continue

        by_strike = {round(float(row.get("strike", 0.0)), 2): str(row.get("instrument", "")).strip() for row in rows}
        for contract in group_contracts:
            instrument = by_strike.get(round(float(contract.strike), 2))
            if instrument:
                script_to_instrument[contract.script] = instrument

    if not script_to_instrument:
        return {}

    unique_instruments = list(dict.fromkeys(script_to_instrument.values()))
    instrument_ltp: dict[str, float] = {}

    def _fetch_batch(batch: list[str]) -> dict[str, float]:
        params = [("i", item) for item in batch]
        try:
            response = requests.get(
                "https://api.kite.trade/quote/ltp",
                params=params,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {KITE_API_KEY}:{access_token}",
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            data = payload.get("data", {})
            rows: dict[str, float] = {}
            for instrument, row in data.items():
                price = _to_float((row or {}).get("last_price"))
                if price is not None and price > 0:
                    rows[instrument] = float(price)
            return rows
        except Exception:
            return {}

    for idx in range(0, len(unique_instruments), 200):
        batch = unique_instruments[idx : idx + 200]
        rows = await asyncio.to_thread(_fetch_batch, batch)
        instrument_ltp.update(rows)

    response: dict[str, float] = {}
    for script, instrument in script_to_instrument.items():
        value = instrument_ltp.get(instrument)
        if value is not None and value > 0:
            response[script] = float(value)
    return response


async def _fetch_live_option_ltp(contract: FNOContract) -> float:
    controls = await _get_api_controls()

    if controls.get("kite_data_enabled", True):
        kite_ltp = await _fetch_option_ltp_from_kite(contract)
        if kite_ltp is not None and kite_ltp > 0:
            return float(kite_ltp)

    if controls.get("moneycontrol_data_enabled", True):
        try:
            return float(
                await asyncio.to_thread(
                    market_data_client.fetch_option_ltp_for_contract,
                    contract.model_dump(),
                )
            )
        except Exception:
            pass

    if not controls.get("strict_live_only", True):
        core = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
        if core.ltp is not None:
            modeled = _estimate_option_ltp(core.ltp, contract.strike, contract.option_type)
            if modeled > 0:
                return float(modeled)

    raise HTTPException(status_code=502, detail=f"Live option LTP unavailable for {contract.script}")


def _portfolio_horizon_ranges(
    value_flag: str,
    price_zone: str,
    pnl_pct: float,
) -> dict[str, PortfolioHorizonRange]:
    if value_flag == "Attractive" and price_zone == "Near 52W low":
        base_up, base_down = 20.0, 8.0
    elif value_flag == "Expensive" and price_zone == "Near 52W high":
        base_up, base_down = 8.0, 20.0
    elif value_flag == "Expensive":
        base_up, base_down = 10.0, 16.0
    elif value_flag == "Attractive":
        base_up, base_down = 16.0, 10.0
    else:
        base_up, base_down = 12.0, 12.0

    overbought_penalty = 3 if pnl_pct > 20 else 0
    oversold_bonus = 3 if pnl_pct < -10 else 0

    horizons = {
        "1W": 0.25,
        "1M": 0.45,
        "3M": 0.8,
        "6M": 1.0,
        "9M": 1.2,
        "1Y": 1.35,
    }
    response: dict[str, PortfolioHorizonRange] = {}
    for horizon, multiplier in horizons.items():
        upside = max(1.0, (base_up + oversold_bonus - overbought_penalty) * multiplier)
        downside = max(1.0, (base_down + overbought_penalty - oversold_bonus) * multiplier)
        flag: Literal["GREEN", "RED"] = "GREEN" if upside >= downside * 1.15 else "RED"
        response[horizon] = PortfolioHorizonRange(
            upside_pct=round(upside, 2),
            downside_pct=round(-downside, 2),
            flag=flag,
        )
    return response


async def _analyze_portfolio_positions(positions: list[dict]) -> PortfolioAnalyzeResponse:
    normalized_positions = []
    for row in positions:
        raw_symbol = str(row.get("symbol", "")).strip()
        symbol = await _resolve_symbol_input(raw_symbol)
        avg_price = _to_float(row.get("avg_price"))
        quantity = _to_float(row.get("quantity"))
        if not symbol or avg_price is None or quantity is None or quantity <= 0:
            continue
        normalized_positions.append(
            {
                "symbol": symbol,
                "avg_price": float(avg_price),
                "quantity": float(quantity),
            }
        )

    if not normalized_positions:
        raise HTTPException(status_code=400, detail="No valid portfolio positions found")

    cores = await asyncio.gather(*[get_stock_core(item["symbol"]) for item in normalized_positions])
    stock_rows: list[dict] = []
    total_current_value = 0.0
    for idx, core in enumerate(cores):
        stock = StockCoreNormalized(**core)
        if stock.ltp is None:
            continue
        pos = normalized_positions[idx]
        cost = pos["avg_price"] * pos["quantity"]
        current_value = stock.ltp * pos["quantity"]
        pnl_pct = ((stock.ltp - pos["avg_price"]) / pos["avg_price"]) * 100 if pos["avg_price"] > 0 else 0.0

        total_current_value += current_value
        stock_rows.append(
            {
                "core": stock,
                "avg_price": pos["avg_price"],
                "quantity": pos["quantity"],
                "cost": cost,
                "current_value": current_value,
                "pnl_pct": pnl_pct,
            }
        )

    if not stock_rows:
        raise HTTPException(status_code=400, detail="No live data available for provided symbols")

    analyses: list[PortfolioStockAnalysis] = []
    for row in stock_rows:
        stock = row["core"]
        pe = stock.pe_ratio
        if pe is None:
            value_flag: Literal["Attractive", "Fair", "Expensive"] = "Fair"
        elif pe <= 18:
            value_flag = "Attractive"
        elif pe <= 35:
            value_flag = "Fair"
        else:
            value_flag = "Expensive"

        position = _position_in_range(stock.ltp, stock.year_low, stock.year_high)
        if position is None:
            price_zone: Literal["Near 52W low", "Mid range", "Near 52W high"] = "Mid range"
        elif position <= 0.25:
            price_zone = "Near 52W low"
        elif position >= 0.75:
            price_zone = "Near 52W high"
        else:
            price_zone = "Mid range"

        day_change = 0.0
        if stock.prev_close is not None and stock.prev_close > 0:
            day_change = ((stock.ltp - stock.prev_close) / stock.prev_close) * 100
        if day_change > 0.5:
            momentum_proxy: Literal["Positive trend", "Flat", "Negative trend"] = "Positive trend"
        elif day_change < -0.5:
            momentum_proxy = "Negative trend"
        else:
            momentum_proxy = "Flat"

        if (stock.eps or 0) > 0 and (pe or 0) <= 30:
            quality_proxy: Literal["Stable quality", "Speculative", "Moderate"] = "Stable quality"
        elif (stock.eps or 0) <= 0 or (pe or 0) > 45:
            quality_proxy = "Speculative"
        else:
            quality_proxy = "Moderate"

        expected_ranges = _portfolio_horizon_ranges(value_flag, price_zone, row["pnl_pct"])
        expected_signals: dict[str, PortfolioExpectedSignal] = {}
        for horizon, hr in expected_ranges.items():
            max_expected_price = round(stock.ltp * (1 + (hr.upside_pct / 100)), 2)
            delta_amount = max_expected_price - row["avg_price"]
            delta_pct = (delta_amount / row["avg_price"]) * 100 if row["avg_price"] > 0 else 0.0
            amount_signal = f"{delta_amount:+.2f}"
            percent_signal = f"{delta_pct:+.2f}%"
            expected_signals[horizon] = PortfolioExpectedSignal(
                max_expected_price=max_expected_price,
                amount_signal=amount_signal,
                percent_signal=percent_signal,
                direction="PROFIT" if delta_amount >= 0 else "LOSS",
            )

        if value_flag == "Attractive" and price_zone != "Near 52W high":
            recommendation = "Accumulate on dips"
            comments = "Reasonably valued with favorable upside profile across medium horizons."
        elif value_flag == "Expensive" and price_zone == "Near 52W high":
            recommendation = "Consider partial profit booking"
            comments = "Valuation is stretched near highs; downside risk dominates in near terms."
        elif quality_proxy == "Speculative":
            recommendation = "High risk – consider reducing exposure"
            comments = "Signal quality is speculative due to weak earnings/valuation balance."
        else:
            recommendation = "Strong Hold"
            comments = "Balanced profile; hold and monitor trend confirmations on declines."

        allocation_pct = (row["current_value"] / total_current_value) * 100 if total_current_value > 0 else 0.0
        analyses.append(
            PortfolioStockAnalysis(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector,
                ltp=round(stock.ltp, 2),
                market_cap=stock.market_cap,
                pe_ratio=stock.pe_ratio,
                year_high=stock.year_high,
                year_low=stock.year_low,
                eps=stock.eps,
                avg_price=round(row["avg_price"], 2),
                quantity=round(row["quantity"], 2),
                allocation_pct=round(allocation_pct, 2),
                pnl_pct=round(row["pnl_pct"], 2),
                value_flag=value_flag,
                price_zone=price_zone,
                momentum_proxy=momentum_proxy,
                quality_proxy=quality_proxy,
                expected_ranges=expected_ranges,
                expected_signals=expected_signals,
                recommendation=recommendation,
                comments=comments,
            )
        )

    analyses.sort(key=lambda row: row.allocation_pct, reverse=True)
    return PortfolioAnalyzeResponse(
        cost_charged=0.0,
        credits_remaining=0.0,
        parsed_positions_count=len(analyses),
        stocks=analyses,
    )


def _position_in_range(ltp: float | None, year_low: float | None, year_high: float | None) -> float | None:
    if ltp is None or year_low is None or year_high is None or year_high <= year_low:
        return None
    return clamp((ltp - year_low) / (year_high - year_low), 0.0, 1.0)


def get_minutes_to_expiry(contract: FNOContract | dict) -> int:
    expiry_date_str = contract["expiry"] if isinstance(contract, dict) else contract.expiry
    expiry_time_str = (
        contract.get("expiry_time_ist", "15:30")
        if isinstance(contract, dict)
        else contract.expiry_time_ist
    )
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    hh, mm = map(int, expiry_time_str.split(":"))
    expiry_dt = datetime.combine(expiry_date, time(hh, mm, tzinfo=IST))
    now = datetime.now(IST)
    return int((expiry_dt - now).total_seconds() / 60)


def _expiry_risk_bucket(minutes_to_expiry: int) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if minutes_to_expiry < 180:
        return "HIGH"
    if minutes_to_expiry < 1440:
        return "MEDIUM"
    return "LOW"


def _validate_expiry_guard(minutes_to_expiry: int) -> None:
    if minutes_to_expiry <= 0:
        raise HTTPException(status_code=400, detail="Contract expired. No projections available.")
    if minutes_to_expiry <= 15:
        raise HTTPException(status_code=400, detail="Too close to expiry for safe projections.")


def _validate_username(username: str) -> str:
    value = username.strip()
    if not USERNAME_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="Username must be at least 6 chars and can use letters, numbers, @ . _ -",
        )
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise HTTPException(status_code=400, detail="Username must include at least one letter and one number")
    return value


def _validate_domain(domain: str) -> str:
    value = domain.strip().lower()
    if not re.fullmatch(r"^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$", value):
        raise HTTPException(status_code=400, detail="Invalid domain format")
    return value


def _split_domain_root_and_host(fqdn: str) -> tuple[str, str]:
    parts = fqdn.split(".")
    if len(parts) <= 2:
        return fqdn, "@"
    root_domain = ".".join(parts[-2:])
    host_label = ".".join(parts[:-2])
    return root_domain, host_label or "@"


def _normalize_target_record(target_record: str) -> str:
    value = target_record.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Target record is required")
    if "://" in value:
        parsed = urlparse(value)
        if parsed.hostname:
            return parsed.hostname.lower()
    return value.lower()


def _resolve_ipv4(value: str) -> str | None:
    if re.fullmatch(r"^\d{1,3}(\.\d{1,3}){3}$", value):
        return value
    try:
        return socket.gethostbyname(value)
    except Exception:
        return None


def _normalize_symbol_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


async def _sync_script_master_daily(force: bool = False) -> None:
    global SCRIPT_MASTER_LAST_SYNC_DATE
    today = datetime.now(IST).date().isoformat()
    if not force and SCRIPT_MASTER_LAST_SYNC_DATE == today:
        return

    meta = await db.system_meta.find_one({"key": "script_master_sync"}, {"_id": 0})
    if (not force) and meta and meta.get("date") == today and int(meta.get("updated_count", 0) or 0) >= 500:
        SCRIPT_MASTER_LAST_SYNC_DATE = today
        return

    seed_symbols = {
        *MULTIBAGGER_UNIVERSE,
        *STOCK_FNO_UNIVERSE,
        *[row["underlying"] for row in FNO_CONTRACTS],
        "NIFTY",
        "BANKNIFTY",
    }

    def _clean_source_symbol(value: str) -> str:
        raw = str(value or "").upper().strip()
        raw = raw.replace("-EQ", "")
        raw = raw.replace(" EQ", "")
        raw = raw.replace(".EQ", "")
        return _normalize_symbol_key(raw)

    def _fetch_nse_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(
                NSE_SCRIPT_MASTER_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            if response.status_code != 200:
                return []
            reader = csv.DictReader(io.StringIO(response.text))
            rows: list[tuple[str, str]] = []
            for row in reader:
                symbol = _normalize_symbol_key(str(row.get("SYMBOL", "")).strip())
                name = str(row.get("NAME OF COMPANY", "")).strip()
                if symbol:
                    rows.append((symbol, name or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch NSE script master: %s", exc)
            return []

    def _fetch_angel_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(ANGEL_SCRIPT_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if response.status_code != 200:
                return []
            payload = response.json()
            rows: list[tuple[str, str]] = []
            for item in payload if isinstance(payload, list) else []:
                exch = str(item.get("exch_seg", "")).upper().strip()
                instrument_type = str(item.get("instrumenttype", "")).upper().strip()
                if exch not in {"NSE", "BSE"}:
                    continue
                if instrument_type and instrument_type not in {"EQ", "AMXIDX", "INDEX"}:
                    continue
                raw_symbol = str(item.get("symbol") or item.get("name") or "").strip()
                raw_name = str(item.get("name") or item.get("symbol") or "").strip()
                symbol = _clean_source_symbol(raw_symbol)
                if not symbol:
                    symbol = _clean_source_symbol(raw_name)
                if symbol.endswith(("FUT", "CE", "PE")):
                    continue
                if symbol:
                    rows.append((symbol, raw_name or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch Angel script master: %s", exc)
            return []

    def _fetch_kite_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(KITE_SCRIPT_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if response.status_code != 200:
                return []
            reader = csv.DictReader(io.StringIO(response.text))
            rows: list[tuple[str, str]] = []
            for item in reader:
                exchange = str(item.get("exchange", "")).upper().strip()
                segment = str(item.get("segment", "")).upper().strip()
                instrument_type = str(item.get("instrument_type", "")).upper().strip()
                if exchange not in {"NSE", "BSE"}:
                    continue
                if segment not in {"NSE", "BSE"}:
                    continue
                if instrument_type not in {"EQ", ""}:
                    continue
                raw_symbol = str(item.get("tradingsymbol", "")).strip()
                raw_name = str(item.get("name", "")).strip()
                symbol = _normalize_symbol_key(raw_symbol)
                if symbol:
                    rows.append((symbol, raw_name or raw_symbol or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch Kite script master: %s", exc)
            return []

    def _fetch_dhan_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(DHAN_SCRIPT_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if response.status_code != 200:
                return []
            reader = csv.DictReader(io.StringIO(response.text))
            rows: list[tuple[str, str]] = []
            for item in reader:
                exchange = str(item.get("SEM_EXM_EXCH_ID", "")).upper().strip()
                instrument_name = str(item.get("SEM_INSTRUMENT_NAME", "")).upper().strip()
                symbol_name = str(item.get("SM_SYMBOL_NAME", "")).strip()
                trading_symbol = str(item.get("SEM_TRADING_SYMBOL", "")).strip()
                custom_symbol = str(item.get("SEM_CUSTOM_SYMBOL", "")).strip()
                if exchange not in {"NSE", "BSE"}:
                    continue
                if instrument_name not in {"EQUITY", "INDEX"}:
                    continue
                raw_symbol = trading_symbol or symbol_name or custom_symbol
                raw_name = custom_symbol or symbol_name or trading_symbol
                symbol = _clean_source_symbol(raw_symbol)
                if symbol.endswith(("FUT", "CE", "PE")):
                    continue
                if symbol:
                    rows.append((symbol, raw_name or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch Dhan script master: %s", exc)
            return []

    nse_rows, angel_rows, kite_rows, dhan_rows = await asyncio.gather(
        asyncio.to_thread(_fetch_nse_rows),
        asyncio.to_thread(_fetch_angel_rows),
        asyncio.to_thread(_fetch_kite_rows),
        asyncio.to_thread(_fetch_dhan_rows),
    )

    nse_equity_symbols = {symbol for symbol, _ in nse_rows}
    allow_symbols = {_normalize_symbol_key(symbol) for symbol in seed_symbols}
    allow_symbols.update({"NIFTY", "BANKNIFTY"})

    source_rows = []
    for symbol, name in [*nse_rows, *angel_rows, *kite_rows, *dhan_rows]:
        canonical = _normalize_symbol_key(symbol)
        if not canonical:
            continue
        if canonical in allow_symbols or canonical in nse_equity_symbols:
            source_rows.append((canonical, name))
    script_records: dict[str, dict] = {}

    for symbol in seed_symbols:
        canonical = _normalize_symbol_key(symbol)
        if not canonical:
            continue
        script_records.setdefault(
            canonical,
            {
                "display_name": symbol,
                "aliases": {symbol, canonical},
            },
        )

    for symbol, name in source_rows:
        row = script_records.setdefault(
            symbol,
            {
                "display_name": name,
                "aliases": {symbol},
            },
        )
        row["display_name"] = row.get("display_name") or name
        row["aliases"].update({symbol, name, name.replace("LIMITED", "LTD")})

    for symbol in sorted(seed_symbols):
        canonical = _normalize_symbol_key(symbol)
        if not canonical:
            continue
        try:
            meta_symbol = await asyncio.to_thread(market_data_client.resolve_symbol_meta, canonical)
        except Exception:
            meta_symbol = None
        if not meta_symbol:
            continue

        row = script_records.setdefault(
            canonical,
            {
                "display_name": symbol,
                "aliases": {symbol, canonical},
            },
        )
        row["display_name"] = meta_symbol.get("name") or row.get("display_name") or symbol
        row["aliases"].update(
            {
                meta_symbol.get("name", ""),
                meta_symbol.get("id", ""),
                meta_symbol.get("did", ""),
                canonical,
            }
        )

    now_iso = _utc_now_iso()
    docs: list[dict] = []
    for canonical, data in sorted(script_records.items()):
        aliases = sorted({str(alias).strip() for alias in data["aliases"] if str(alias).strip()})
        normalized_aliases = sorted(
            {
                _normalize_symbol_key(alias)
                for alias in aliases
                if _normalize_symbol_key(alias)
            }
        )
        docs.append(
            {
                "canonical_symbol": canonical,
                "display_name": data.get("display_name") or canonical,
                "aliases": aliases,
                "normalized_aliases": normalized_aliases,
                "updated_at": now_iso,
            }
        )

    if len(docs) < 500:
        logger.warning("Script master refresh skipped: insufficient compiled rows (%s)", len(docs))
        return

    staging = db.script_master_staging
    await staging.drop()
    for start in range(0, len(docs), 5000):
        await staging.insert_many(docs[start : start + 5000], ordered=False)

    db_name = os.environ["DB_NAME"]
    try:
        await client.admin.command(
            "renameCollection",
            f"{db_name}.script_master_staging",
            to=f"{db_name}.script_master",
            dropTarget=True,
        )
    except Exception:
        await db.script_master.delete_many({})
        cursor = staging.find({}, {"_id": 0})
        batch: list[dict] = []
        async for row in cursor:
            batch.append(row)
            if len(batch) >= 5000:
                await db.script_master.insert_many(batch, ordered=False)
                batch = []
        if batch:
            await db.script_master.insert_many(batch, ordered=False)
        await staging.drop()

    await db.system_meta.update_one(
        {"key": "script_master_sync"},
        {
            "$set": {
                "key": "script_master_sync",
                "date": today,
                "updated_count": len(docs),
                "updated_at": _utc_now_iso(),
            }
        },
        upsert=True,
    )
    SCRIPT_MASTER_LAST_SYNC_DATE = today


async def _resolve_symbol_input(value: str) -> str:
    await _sync_script_master_daily()
    raw_query = str(value or "").strip()
    cleaned = _normalize_symbol_key(raw_query)
    if not cleaned:
        return cleaned

    normalized_variants = {cleaned}
    if cleaned.endswith("LTD"):
        normalized_variants.add(f"{cleaned[:-3]}LIMITED")
    if cleaned.endswith("LIMITED"):
        normalized_variants.add(f"{cleaned[:-7]}LTD")
    query_tokens = [
        _normalize_symbol_key(token)
        for token in re.split(r"\s+|[,&./()-]", raw_query)
        if _normalize_symbol_key(token) and len(_normalize_symbol_key(token)) >= 3
    ]

    row = await db.script_master.find_one(
        {
            "$or": [
                {"canonical_symbol": {"$in": list(normalized_variants)}},
                {"normalized_aliases": {"$in": list(normalized_variants)}},
            ]
        },
        {"_id": 0, "canonical_symbol": 1},
    )
    if row and row.get("canonical_symbol"):
        return row["canonical_symbol"]

    regex_candidates = await db.script_master.find(
        {
            "$or": [
                {
                    "normalized_aliases": {
                        "$regex": "|".join(
                            re.escape(item)
                            for item in [*normalized_variants, *query_tokens]
                        )
                    }
                },
                {"display_name": {"$regex": re.escape(raw_query), "$options": "i"}},
            ]
        },
        {"_id": 0, "canonical_symbol": 1, "display_name": 1, "normalized_aliases": 1},
    ).to_list(5000)
    if regex_candidates:
        def _candidate_sort_key(item: dict) -> tuple[int, int]:
            normalized_aliases = item.get("normalized_aliases", [])
            exact = 1 if any(candidate in normalized_aliases for candidate in normalized_variants) else 0
            starts_with = 1 if any(
                (str(alias).startswith(candidate) or candidate.startswith(str(alias)))
                for alias in normalized_aliases
                for candidate in normalized_variants
            ) else 0
            token_hits = sum(
                1 for token in query_tokens if any(token in str(alias) for alias in normalized_aliases)
            )
            score = (exact * 100) + (starts_with * 50)
            display = _normalize_symbol_key(str(item.get("display_name", "")))
            similarity = int(difflib.SequenceMatcher(None, cleaned, display).ratio() * 100)
            return (score, token_hits, similarity)

        best = sorted(regex_candidates, key=_candidate_sort_key, reverse=True)[0]
        candidate = best.get("canonical_symbol")
        if candidate:
            return candidate

    try:
        meta = await asyncio.to_thread(market_data_client.resolve_symbol_meta, raw_query.upper())
    except Exception:
        meta = None
    if meta:
        discovered = _normalize_symbol_key(meta.get("did") or meta.get("id") or cleaned)
        if discovered:
            aliases = {
                raw_query,
                cleaned,
                meta.get("name", ""),
                meta.get("id", ""),
                meta.get("did", ""),
            }
            aliases = {str(alias).strip() for alias in aliases if str(alias).strip()}
            normalized_aliases = sorted(
                {
                    _normalize_symbol_key(alias)
                    for alias in aliases
                    if _normalize_symbol_key(alias)
                }
            )
            await db.script_master.update_one(
                {"canonical_symbol": discovered},
                {
                    "$set": {
                        "canonical_symbol": discovered,
                        "display_name": meta.get("name") or discovered,
                        "aliases": sorted(aliases),
                        "normalized_aliases": normalized_aliases,
                        "updated_at": _utc_now_iso(),
                    }
                },
                upsert=True,
            )
            return discovered

    return cleaned


async def _ensure_owner_exists() -> dict:
    owner_doc = await db.app_users.find_one_and_update(
        {"username": OWNER_BOOTSTRAP_USERNAME},
        {
            "$setOnInsert": {
                "user_key": str(uuid.uuid4()),
                "username": OWNER_BOOTSTRAP_USERNAME,
                "role": "owner",
                "credits": 0,
                "created_at": _utc_now_iso(),
                "created_by": "SYSTEM",
                "quota_limit": 10_000,
                "quota_used": 0,
            }
        },
        upsert=True,
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return owner_doc


async def _get_user_by_key(user_key: str) -> dict | None:
    return await db.app_users.find_one({"user_key": user_key}, {"_id": 0})


async def _get_user_by_username(username: str) -> dict | None:
    return await db.app_users.find_one({"username": username}, {"_id": 0})


async def _get_user_by_ref(user_ref: str) -> dict | None:
    candidate = await db.app_users.find_one({"user_key": user_ref}, {"_id": 0})
    if candidate:
        return candidate
    return await db.app_users.find_one({"username": user_ref}, {"_id": 0})


def _is_owner(user: dict) -> bool:
    return user.get("role") == "owner"


def _is_admin(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


def _is_credit_exempt(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


async def _consume_credits(user: dict, cost: float) -> tuple[dict, float]:
    if _is_credit_exempt(user):
        latest = await _get_user_by_key(user["user_key"])
        return latest or user, 0.0

    updated = await db.app_users.find_one_and_update(
        {"user_key": user["user_key"], "credits": {"$gte": cost}},
        {"$inc": {"credits": -cost}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        latest = await _get_user_by_key(user["user_key"])
        current = float(latest.get("credits", 0)) if latest else 0.0
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Required {round(cost,2)}, available {round(current,2)}",
        )
    return updated, float(cost)


def _map_user_view(user: dict) -> AdminUserView:
    role_raw = str(user.get("role", "user"))
    if role_raw == "admin":
        role_raw = "owner"
    role: Literal["owner", "sub_admin", "user"] = role_raw if role_raw in {"owner", "sub_admin", "user"} else "user"
    username = user.get("username") or f"legacy-{str(user.get('user_key', 'user'))[:6]}"

    return AdminUserView(
        user_key=user.get("user_key", str(uuid.uuid4())),
        username=username,
        role=role,
        credits=round(float(user.get("credits", 0)), 2),
        created_at=user.get("created_at", ""),
        created_by=user.get("created_by", "SYSTEM"),
        quota_limit=int(user.get("quota_limit", 0)),
        quota_used=int(user.get("quota_used", 0)),
        credential_label=f"{username} as {role}",
    )


async def get_current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "", 1).strip()
    session = SESSION_STORE.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = await _get_user_by_key(session["user_key"])
    if not user:
        SESSION_STORE.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")
    return user


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


async def get_owner_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_owner(current_user):
        raise HTTPException(status_code=403, detail="Owner only")
    return current_user


def compute_multibagger_analysis(stock: StockCoreNormalized) -> dict:
    ltp = stock.ltp
    market_cap = stock.market_cap
    pe = stock.pe_ratio
    book_value = stock.book_value
    eps = stock.eps
    year_high = stock.year_high
    year_low = stock.year_low

    pb_ratio_est = _safe_ratio(ltp, book_value)
    upside_to_52w_high_pct = (
        ((year_high - ltp) / ltp) * 100
        if year_high is not None and ltp is not None and ltp > 0
        else None
    )
    growth_proxy_pct = (
        ((year_high - year_low) / year_low) * 100
        if year_high is not None and year_low is not None and year_low > 0 and year_high > year_low
        else None
    )
    peg_ratio_est = _safe_ratio(pe, growth_proxy_pct) if growth_proxy_pct is not None else None
    day_change_pct = (
        ((ltp - stock.prev_close) / stock.prev_close) * 100
        if ltp is not None and stock.prev_close is not None and stock.prev_close > 0
        else 0.0
    )
    position = _position_in_range(ltp, year_low, year_high)

    tier_scores = {f"tier_{idx}": 0.0 for idx in range(1, 9)}

    # Tier 1: Business quality (ROE/ROCE/margin/revenue CAGR proxy)
    if market_cap is not None and market_cap >= 2_000:
        tier_scores["tier_1"] += 7
    if eps is not None and eps > 0:
        tier_scores["tier_1"] += 6
    if pe is not None and 8 <= pe <= 35:
        tier_scores["tier_1"] += 5

    # Tier 2: Financial health (leverage/liquidity proxy)
    if pb_ratio_est is not None and pb_ratio_est <= 5:
        tier_scores["tier_2"] += 5
    if market_cap is not None and market_cap >= 1_000:
        tier_scores["tier_2"] += 4
    if stock.volume >= 120_000:
        tier_scores["tier_2"] += 3

    # Tier 3: Growth trajectory proxy
    if growth_proxy_pct is not None:
        tier_scores["tier_3"] += clamp(growth_proxy_pct / 10, 0, 7)
    if ltp is not None and stock.open is not None and ltp > stock.open:
        tier_scores["tier_3"] += 3
    if day_change_pct > 0:
        tier_scores["tier_3"] += 2

    # Tier 4: Forensic quality proxy (Beneish/Piotroski/CFO proxy)
    if eps is not None and eps > 0:
        tier_scores["tier_4"] += 5
    if pe is not None and 6 <= pe <= 45:
        tier_scores["tier_4"] += 4
    if stock.sector != "Unknown":
        tier_scores["tier_4"] += 3

    # Tier 5: Valuation
    if peg_ratio_est is not None and peg_ratio_est <= 1.8:
        tier_scores["tier_5"] += 6
    if pe is not None and 10 <= pe <= 32:
        tier_scores["tier_5"] += 4
    if pb_ratio_est is not None and pb_ratio_est <= 3.5:
        tier_scores["tier_5"] += 2

    # Tier 6: Technical setup (Supertrend/50DMA/RSI proxy)
    if position is not None and 0.30 <= position <= 0.75:
        tier_scores["tier_6"] += 6
    if ltp is not None and stock.prev_close is not None and ltp > stock.prev_close:
        tier_scores["tier_6"] += 4
    if stock.volume >= 150_000:
        tier_scores["tier_6"] += 4

    # Tier 7: Institutional interest proxy
    if market_cap is not None and market_cap >= 12_000:
        tier_scores["tier_7"] += 6
    if stock.volume >= 250_000:
        tier_scores["tier_7"] += 4

    # Tier 8: Risk flags (deductions)
    risk_deduction = 0
    if pe is not None and pe > 60:
        risk_deduction += 4
    if eps is not None and eps <= 0:
        risk_deduction += 3
    if position is not None and position > 0.92:
        risk_deduction += 2
    if ltp is not None and ltp < 10:
        risk_deduction += 3
    tier_scores["tier_8"] = -float(risk_deduction)

    # Fixed weighted score composition
    raw_score = (
        tier_scores["tier_1"]
        + tier_scores["tier_2"]
        + tier_scores["tier_3"]
        + tier_scores["tier_4"]
        + tier_scores["tier_5"]
        + tier_scores["tier_6"]
        + tier_scores["tier_7"]
        + tier_scores["tier_8"]
    )
    final_score = int(clamp(round(raw_score), 0, 100))

    tier_thresholds = {
        "tier_1": 10,
        "tier_2": 7,
        "tier_3": 7,
        "tier_4": 7,
        "tier_5": 6,
        "tier_6": 7,
        "tier_7": 5,
    }
    tier_pass_count = sum(1 for key, threshold in tier_thresholds.items() if tier_scores.get(key, 0) >= threshold)

    mandatory_filters = (
        ltp is not None
        and ltp > 10
        and market_cap is not None
        and market_cap >= 500
        and eps is not None
        and eps > 0
    )
    is_potential_multibagger = bool(mandatory_filters and final_score >= 70 and tier_pass_count >= 5)

    current_rsi_level = round(30 + (position if position is not None else 0.5) * 40, 2) if ltp is not None else None
    gtt_buy_price = None
    if ltp is not None:
        base_buy = ltp * 0.965
        if year_low is not None and year_low > 0:
            base_buy = max(base_buy, year_low * 1.03)
        gtt_buy_price = round(base_buy, 2)

    duration_base = {
        "1W": 0.012,
        "1M": 0.045,
        "3M": 0.11,
        "6M": 0.19,
        "9M": 0.27,
        "1Y": 0.34,
    }
    momentum_adj = (final_score - 55) / 280
    targeted_upside_price = {}
    targeted_upside_profit_pct = {}
    for key, base in duration_base.items():
        if ltp is None:
            targeted_upside_price[key] = None
            targeted_upside_profit_pct[key] = None
            continue

        growth = base + momentum_adj
        if upside_to_52w_high_pct is not None and upside_to_52w_high_pct > 0:
            growth = min(growth, (upside_to_52w_high_pct / 100) * 1.25)
        growth = max(growth, 0.005)
        target_price = round(ltp * (1 + growth), 2)
        roi_pct = round(((target_price - ltp) / ltp) * 100, 2)

        targeted_upside_price[key] = target_price
        targeted_upside_profit_pct[key] = roi_pct

    thesis_parts = []
    if final_score >= 80:
        thesis_parts.append("Strong 8-tier score with favorable valuation/technical mix")
    elif final_score >= 70:
        thesis_parts.append("Balanced quality-growth setup with acceptable risk")
    else:
        thesis_parts.append("Needs further confirmation on quality/valuation factors")
    if upside_to_52w_high_pct is not None:
        thesis_parts.append(f"Potential upside to 52W high: {round(upside_to_52w_high_pct, 1)}%")
    if peg_ratio_est is not None:
        thesis_parts.append(f"PEG proxy: {round(peg_ratio_est, 2)}")
    thesis = " | ".join(thesis_parts)

    return {
        "multibagger_score": final_score,
        "upside_to_52w_high_pct": round(upside_to_52w_high_pct, 2) if upside_to_52w_high_pct is not None else None,
        "pb_ratio_est": round(pb_ratio_est, 2) if pb_ratio_est is not None else None,
        "peg_ratio_est": round(peg_ratio_est, 2) if peg_ratio_est is not None else None,
        "tier_pass_count": tier_pass_count,
        "is_potential_multibagger": is_potential_multibagger,
        "current_rsi_level": current_rsi_level,
        "gtt_buy_price": gtt_buy_price,
        "targeted_upside_price": targeted_upside_price,
        "targeted_upside_profit_pct": targeted_upside_profit_pct,
        "thesis": thesis,
    }


def _get_signal_quality(confluence_score: int) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if confluence_score >= 78:
        return "HIGH"
    if confluence_score >= 65:
        return "MEDIUM"
    return "LOW"


def build_fno_signal(
    contract: FNOContract,
    stock_core: StockCoreNormalized,
    option_ltp: float,
    refreshed_at: str,
    minutes_to_expiry: int,
) -> FNOSignalResponse:
    underlying_ltp = stock_core.ltp
    if underlying_ltp is None:
        raise HTTPException(status_code=502, detail="Underlying LTP unavailable")

    pos = _position_in_range(underlying_ltp, stock_core.year_low, stock_core.year_high)
    day_change_pct = (
        ((underlying_ltp - stock_core.prev_close) / stock_core.prev_close) * 100
        if stock_core.prev_close is not None and stock_core.prev_close > 0
        else 0.0
    )
    intraday_change_pct = (
        ((underlying_ltp - stock_core.open) / stock_core.open) * 100
        if stock_core.open is not None and stock_core.open > 0
        else 0.0
    )

    trigger_factors: list[str] = []
    if day_change_pct >= 0.35:
        trigger_factors.append(f"DayChange={day_change_pct:.2f}%")
    elif day_change_pct <= -0.35:
        trigger_factors.append(f"DayChange={day_change_pct:.2f}%")

    if intraday_change_pct >= 0.20:
        trigger_factors.append(f"IntraDay={intraday_change_pct:.2f}%")
    elif intraday_change_pct <= -0.20:
        trigger_factors.append(f"IntraDay={intraday_change_pct:.2f}%")

    bias_score = (0.65 * day_change_pct) + (0.35 * intraday_change_pct)
    if pos is not None:
        bias_score += (pos - 0.5) * 1.2
    trigger_factors.append(f"BiasScore={bias_score:.2f}")

    if bias_score >= 0.05:
        underlying_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif bias_score <= -0.05:
        underlying_bias = "BEARISH"
    else:
        underlying_bias = "NEUTRAL"

    if contract.option_type == "CE" and underlying_bias == "BULLISH":
        direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif contract.option_type == "PE" and underlying_bias == "BEARISH":
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    entry_price = round(option_ltp, 2)
    stop_loss = round(entry_price * 0.75, 2)
    target1 = round(entry_price * 1.12, 2)
    target2 = round(entry_price * 1.5, 2)

    if minutes_to_expiry < 60 and entry_price > 0:
        required_gain = (target1 - entry_price) / entry_price
        if required_gain > 0.12:
            raise HTTPException(
                status_code=400,
                detail="Insufficient time to expiry for this upside. No projections shown.",
            )

    risk = max(entry_price - stop_loss, 0.01)
    risk_reward_target1 = round((target1 - entry_price) / risk, 2)
    risk_reward_target2 = round((target2 - entry_price) / risk, 2)

    confluence = 52 + abs(bias_score) * 22
    confluence += 12 if direction != "NEUTRAL" else -18
    if risk_reward_target2 >= 2:
        confluence += 8
    if option_ltp < 1:
        confluence -= 8
    if minutes_to_expiry < 60:
        confluence -= 30
        trigger_factors.append("ExpiryWindow=<60m")
    elif minutes_to_expiry < 180:
        confluence -= 15
        trigger_factors.append("ExpiryWindow=<180m")

    confluence_score = int(clamp(round(confluence), 0, 100))
    signal_quality = _get_signal_quality(confluence_score)

    if direction != "NEUTRAL" and 60 <= confluence_score < 80:
        target1 = round(max(entry_price * 1.05, min(target1, entry_price * 1.1)), 2)
        target2 = round(max(entry_price * 1.12, min(target2, entry_price * 1.22)), 2)
        risk_reward_target1 = round((target1 - entry_price) / risk, 2)
        risk_reward_target2 = round((target2 - entry_price) / risk, 2)

    is_potential_trade = direction != "NEUTRAL" and confluence_score >= 72 and risk_reward_target2 >= 1.6
    if is_potential_trade:
        trigger_factors.append("PotentialTrade=YES")

    return FNOSignalResponse(
        script=contract.script,
        underlying=contract.underlying,
        expiry=contract.expiry,
        strike=contract.strike,
        option_type=contract.option_type,
        exchange=contract.exchange,
        lot_size=contract.lot_size,
        underlying_ltp=round(underlying_ltp, 2),
        option_ltp=round(option_ltp, 2),
        direction=direction,
        strategy=(
            "Assured Directional Projection"
            if is_potential_trade
            else "Directional Projection (Low Confidence)"
        ),
        entry_price=entry_price,
        stop_loss=stop_loss,
        target1=target1,
        target2=target2,
        risk_reward_target1=risk_reward_target1,
        risk_reward_target2=risk_reward_target2,
        trigger_factors=trigger_factors,
        confluence_score=confluence_score,
        signal_quality=signal_quality,
        is_potential_trade=is_potential_trade,
        minutes_to_expiry=minutes_to_expiry,
        expiry_risk=_expiry_risk_bucket(minutes_to_expiry),
        data_source="LIVE_OPTION_CHAIN",
        analysis_refreshed_at=refreshed_at,
    )


async def _get_nearest_expiry(underlying: str, prefer_monthly: bool = False) -> str:
    instrument_id = ""
    if underlying == "NIFTY":
        instrument_id = "9"
    elif underlying == "BANKNIFTY":
        instrument_id = "23"
    else:
        meta = await asyncio.to_thread(market_data_client.resolve_symbol_meta, underlying)
        if meta:
            instrument_id = str(meta.get("id", ""))

    if not instrument_id:
        return "2026-03-10"

    expiries = await asyncio.to_thread(market_data_client.get_option_expiries, instrument_id)
    if not expiries:
        return "2026-03-10"

    now_ist = datetime.now(IST)
    future_expiries = []
    for expiry in expiries:
        expiry_dt = datetime.combine(expiry.date(), time(15, 30, tzinfo=IST))
        if expiry_dt > now_ist:
            future_expiries.append(expiry)

    if not future_expiries:
        return expiries[-1].strftime("%Y-%m-%d")

    if prefer_monthly and underlying not in {"NIFTY", "BANKNIFTY"}:
        monthly_candidates: list[datetime] = []
        bucket: dict[tuple[int, int], list[datetime]] = defaultdict(list)
        for expiry in future_expiries:
            bucket[(expiry.year, expiry.month)].append(expiry)

        for _, values in bucket.items():
            monthly_candidates.append(max(values))

        monthly_candidates.sort()
        if monthly_candidates:
            return monthly_candidates[0].strftime("%Y-%m-%d")

    for expiry in future_expiries:
        return expiry.strftime("%Y-%m-%d")

    return expiries[-1].strftime("%Y-%m-%d")


def _format_script(underlying: str, expiry: str, strike: float, option_type: str) -> str:
    date_obj = datetime.strptime(expiry, "%Y-%m-%d")
    return f"{underlying}{date_obj.strftime('%d%b').upper()}{int(strike)}{option_type}"


async def _build_contract(
    underlying: str,
    strike: float,
    option_type: Literal["CE", "PE"],
    prefer_monthly: bool = False,
) -> FNOContract:
    expiry = await _get_nearest_expiry(underlying, prefer_monthly=prefer_monthly)
    script = _format_script(underlying, expiry, strike, option_type)
    lot_size = LOT_SIZE_MAP.get(underlying, 1)
    return FNOContract(
        script=script,
        underlying=underlying,
        expiry=expiry,
        expiry_time_ist="15:30",
        strike=float(strike),
        option_type=option_type,
        exchange="NFO",
        lot_size=lot_size,
    )


async def _resolve_contract_from_input(raw_script: str) -> FNOContract:
    script = raw_script.strip().upper()
    contract_dict = get_fno_contract(script)
    if contract_dict:
        return FNOContract(**contract_dict)

    parsed = SCRIPT_PATTERN.fullmatch(script)
    if parsed:
        underlying, day_txt, mon_txt, strike_txt, option_type = parsed.groups()
        month = MONTH_MAP.get(mon_txt)
        if not month:
            raise HTTPException(status_code=404, detail="Script not supported")

        day = int(day_txt)
        now_ist = datetime.now(IST)
        year = now_ist.year
        try:
            candidate = datetime(year, month, day, 15, 30, tzinfo=IST)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Script not supported") from exc
        if candidate <= now_ist:
            candidate = datetime(year + 1, month, day, 15, 30, tzinfo=IST)

        return FNOContract(
            script=script,
            underlying=underlying,
            expiry=candidate.strftime("%Y-%m-%d"),
            expiry_time_ist="15:30",
            strike=float(strike_txt),
            option_type=option_type,
            exchange="NFO",
            lot_size=LOT_SIZE_MAP.get(underlying, 1),
        )

    resolved_symbol = await _resolve_symbol_input(script)
    if resolved_symbol:
        stock = StockCoreNormalized(**(await get_stock_core(resolved_symbol)))
        if stock.ltp is None:
            raise HTTPException(status_code=404, detail="Script not supported")
        step = 50 if resolved_symbol == "NIFTY" else (100 if resolved_symbol == "BANKNIFTY" else (20 if stock.ltp > 300 else 10))
        strike = round(stock.ltp / step) * step
        return await _build_contract(resolved_symbol, strike, "CE")

    raise HTTPException(status_code=404, detail="Script not supported")


async def _build_signal_for_contract(contract: FNOContract, refreshed_at: str) -> FNOSignalResponse:
    minutes_to_expiry = get_minutes_to_expiry(contract)
    _validate_expiry_guard(minutes_to_expiry)
    stock_data = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
    option_ltp = await _fetch_live_option_ltp(contract)
    return build_fno_signal(
        contract,
        stock_data,
        option_ltp,
        refreshed_at,
        minutes_to_expiry,
    )


async def _safe_signal(contract: FNOContract, refreshed_at: str, sem: asyncio.Semaphore) -> FNOSignalResponse | None:
    async with sem:
        try:
            return await _build_signal_for_contract(contract, refreshed_at)
        except Exception:
            return None


async def _build_report(index_name: Literal["NIFTY", "BANKNIFTY"], weighted: bool) -> IndexAnalysisReport:
    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY
    symbols = [symbol for symbol, _ in weight_source]
    rows = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_rows = [StockCoreNormalized(**row) for row in rows]
    return _compute_report_from_rows(index_name, weight_source, normalized_rows, weighted)


def _compute_report_from_rows(
    index_name: Literal["NIFTY", "BANKNIFTY"],
    weight_source: list[tuple[str, float]],
    rows: list[StockCoreNormalized],
    weighted: bool,
) -> IndexAnalysisReport:

    contributions: list[tuple[str, float]] = []
    bullish_count = 0
    total_weight = 0.0
    total_momentum = 0.0
    for idx, stock in enumerate(rows):
        day_change = 0.0
        if stock.ltp is not None and stock.prev_close is not None and stock.prev_close > 0:
            day_change = ((stock.ltp - stock.prev_close) / stock.prev_close) * 100

        if day_change > 0:
            bullish_count += 1

        weight = weight_source[idx][1] if weighted else 1.0
        total_weight += weight
        total_momentum += day_change * weight
        contributions.append((stock.symbol, day_change * weight))

    breadth_score = round((bullish_count / max(len(rows), 1)) * 100, 2)
    weighted_change = total_momentum / max(total_weight, 1)
    momentum_score = round(clamp(50 + (weighted_change * 8), 0, 100), 2)

    if momentum_score >= 58:
        bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif momentum_score <= 42:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    top_contributors = [f"{sym}:{round(val, 2)}" for sym, val in sorted(contributions, key=lambda x: abs(x[1]), reverse=True)[:3]]
    mode_text = "weighted constituent" if weighted else "equal constituent"

    return IndexAnalysisReport(
        report_type="with_consolidated" if weighted else "without_consolidated",
        breadth_score=breadth_score,
        momentum_score=momentum_score,
        bias=bias,
        top_contributors=top_contributors,
        summary=(
            f"{index_name} {mode_text} analysis: breadth {breadth_score} and momentum {momentum_score} suggests {bias.lower()} bias."
        ),
    )


async def _build_index_projection(index_name: Literal["NIFTY", "BANKNIFTY"], refreshed_at: str) -> IndexProjectionPane:
    stock = StockCoreNormalized(**(await get_stock_core(index_name)))
    if stock.ltp is None:
        raise HTTPException(status_code=502, detail=f"{index_name} spot unavailable")

    step = 50 if index_name == "NIFTY" else 100
    atm = round(stock.ltp / step) * step
    strike_range_min = atm - 500
    strike_range_max = atm + 500
    expiry = await _get_nearest_expiry(index_name)

    strikes = list(range(int(strike_range_min), int(strike_range_max) + step, step))
    contracts: list[FNOContract] = []
    for strike in strikes:
        for option_type in ["CE", "PE"]:
            contract = FNOContract(
                script=_format_script(index_name, expiry, strike, option_type),
                underlying=index_name,
                expiry=expiry,
                expiry_time_ist="15:30",
                strike=float(strike),
                option_type=option_type,
                exchange="NFO",
                lot_size=LOT_SIZE_MAP.get(index_name, 1),
            )
            if get_minutes_to_expiry(contract) > 15:
                contracts.append(contract)

    if not contracts:
        raise HTTPException(status_code=502, detail=f"No active contracts available for {index_name}")

    kite_map = await _fetch_option_ltps_from_kite(contracts)
    rows: list[FNOSignalResponse] = []
    for contract in contracts:
        minutes_to_expiry = get_minutes_to_expiry(contract)
        try:
            option_ltp = kite_map.get(contract.script)
            if option_ltp is None:
                option_ltp = await _fetch_live_option_ltp(contract)
            signal = build_fno_signal(
                contract,
                stock,
                option_ltp,
                refreshed_at,
                minutes_to_expiry,
            )
            rows.append(signal)
        except HTTPException:
            continue
        except Exception:
            continue

    if not rows:
        raise HTTPException(status_code=502, detail=f"No live option-chain strikes available for {index_name}")

    directional_candidates = [
        item
        for item in rows
        if item.direction != "NEUTRAL" and item.confluence_score >= 70 and item.risk_reward_target2 >= 1.5
    ]
    by_strike: dict[float, list[FNOSignalResponse]] = defaultdict(list)
    for row in directional_candidates:
        by_strike[row.strike].append(row)

    paired_scripts = set()
    non_directional: list[NonDirectionalStrategy] = []
    for strike, entries in by_strike.items():
        ce = next((item for item in entries if item.option_type == "CE"), None)
        pe = next((item for item in entries if item.option_type == "PE"), None)
        if ce and pe:
            paired_scripts.add(ce.script)
            paired_scripts.add(pe.script)
            non_directional.append(
                NonDirectionalStrategy(
                    strike=strike,
                    strategy="Long Straddle (Non-Directional Strategy)",
                    ce_script=ce.script,
                    pe_script=pe.script,
                    combined_entry=round(ce.entry_price + pe.entry_price, 2),
                    rationale=(
                        "Both CE and PE at same strike passed profitability checks. "
                        "Classified as volatility strategy, not assured directional signal."
                    ),
                    confidence_score=int(round((ce.confluence_score + pe.confluence_score) / 2)),
                )
            )

    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY
    report_rows = await asyncio.gather(*[get_stock_core(symbol) for symbol, _ in weight_source])
    normalized_report_rows = [StockCoreNormalized(**row) for row in report_rows]
    with_report = _compute_report_from_rows(index_name, weight_source, normalized_report_rows, weighted=True)
    without_report = _compute_report_from_rows(index_name, weight_source, normalized_report_rows, weighted=False)

    expected_direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = with_report.bias

    assured_signals = [
        item
        for item in rows
        if item.script not in paired_scripts
        and strike_range_min <= item.strike <= strike_range_max
        and item.direction != "NEUTRAL"
        and expected_direction != "NEUTRAL"
        and item.direction == expected_direction
        and item.confluence_score >= 80
        and item.risk_reward_target2 >= 1.8
        and item.risk_reward_target1 >= 1.1
        and item.expiry_risk != "HIGH"
        and (item.target1 - item.entry_price) / max(item.entry_price, 0.01) <= 0.12
    ]
    assured_signals.sort(key=lambda row: row.confluence_score, reverse=True)

    assured_scripts = {item.script for item in assured_signals}
    watchlist_signals = [
        item
        for item in rows
        if item.direction != "NEUTRAL"
        and item.signal_quality == "MEDIUM"
        and item.script not in paired_scripts
        and item.script not in assured_scripts
        and strike_range_min <= item.strike <= strike_range_max
        and expected_direction != "NEUTRAL"
        and item.direction == expected_direction
        and 70 <= item.confluence_score < 80
        and item.risk_reward_target1 >= 1.05
        and item.risk_reward_target2 >= 1.45
        and item.expiry_risk != "HIGH"
        and item.minutes_to_expiry > 120
        and (item.target1 - item.entry_price) / max(item.entry_price, 0.01) <= 0.1
    ]
    watchlist_signals.sort(key=lambda row: row.confluence_score, reverse=True)

    directional_count = len([item for item in rows if item.direction != "NEUTRAL"])
    high_conf_count = len([item for item in rows if item.confluence_score >= 80])
    medium_conf_count = len([item for item in rows if 70 <= item.confluence_score < 80])
    bias_aligned_count = (
        len([item for item in rows if item.direction == expected_direction])
        if expected_direction != "NEUTRAL"
        else 0
    )
    rejection_note = None
    if not assured_signals and not watchlist_signals:
        if expected_direction == "NEUTRAL":
            rejection_note = (
                f"No trade: weighted {index_name} bias is NEUTRAL. "
                f"Directional contracts: {directional_count}/{len(rows)}."
            )
        else:
            rejection_note = (
                f"No trade: bias-aligned contracts {bias_aligned_count}/{len(rows)} did not pass strict gates. "
                f"High-confluence={high_conf_count}, Medium-confluence={medium_conf_count}."
            )

    return IndexProjectionPane(
        index_name=index_name,
        spot=round(stock.ltp, 2),
        strike_range_min=float(strike_range_min),
        strike_range_max=float(strike_range_max),
        assured_signals=assured_signals,
        watchlist_signals=watchlist_signals[:8],
        non_directional_strategies=non_directional,
        rejection_note=rejection_note,
        with_consolidated_report=with_report,
        without_consolidated_report=without_report,
    )


def _infer_stock_option_type(core: StockCoreNormalized) -> Literal["CE", "PE"] | None:
    if core.ltp is None:
        return None

    pos = _position_in_range(core.ltp, core.year_low, core.year_high)
    day_change_pct = (
        ((core.ltp - core.prev_close) / core.prev_close) * 100
        if core.prev_close is not None and core.prev_close > 0
        else 0.0
    )
    intraday_change_pct = (
        ((core.ltp - core.open) / core.open) * 100
        if core.open is not None and core.open > 0
        else 0.0
    )

    bias_score = (0.65 * day_change_pct) + (0.35 * intraday_change_pct)
    if pos is not None:
        bias_score += (pos - 0.5) * 1.2

    if bias_score >= 0.15:
        return "CE"
    if bias_score <= -0.15:
        return "PE"
    return None


async def _build_stock_fno_signals(refreshed_at: str) -> list[FNOSignalResponse]:
    symbols = STOCK_FNO_UNIVERSE
    cores = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_cores = [StockCoreNormalized(**row) for row in cores]
    semaphore = asyncio.Semaphore(4)

    async def _build_for_symbol(symbol: str, core: StockCoreNormalized) -> FNOSignalResponse | None:
        if core.ltp is None:
            return None

        step = 20 if core.ltp > 400 else 10
        strike = round(core.ltp / step) * step

        async with semaphore:
            expiry = await _get_nearest_expiry(symbol, prefer_monthly=True)
            symbol_rows: list[FNOSignalResponse] = []
            for option_type in ["CE", "PE"]:
                contract = FNOContract(
                    script=_format_script(symbol, expiry, strike, option_type),
                    underlying=symbol,
                    expiry=expiry,
                    expiry_time_ist="15:30",
                    strike=float(strike),
                    option_type=option_type,
                    exchange="NFO",
                    lot_size=LOT_SIZE_MAP.get(symbol, 1),
                )
                minutes_to_expiry = get_minutes_to_expiry(contract)
                if minutes_to_expiry <= 15:
                    continue

                try:
                    option_ltp = await _fetch_live_option_ltp(contract)
                except Exception:
                    continue

                if option_ltp is None or option_ltp <= 0:
                    continue

                try:
                    signal = build_fno_signal(contract, core, float(option_ltp), refreshed_at, minutes_to_expiry)
                except HTTPException:
                    continue

                if signal.direction != "NEUTRAL":
                    symbol_rows.append(signal)

            if not symbol_rows:
                return None

            potential = [
                row for row in symbol_rows if row.is_potential_trade and row.confluence_score >= 72
            ]
            if potential:
                potential.sort(key=lambda row: row.confluence_score, reverse=True)
                return potential[0]

            symbol_rows.sort(key=lambda row: (row.confluence_score, row.risk_reward_target2), reverse=True)
            return symbol_rows[0]

    built = await asyncio.gather(*[_build_for_symbol(symbol, normalized_cores[idx]) for idx, symbol in enumerate(symbols)])
    results = [item for item in built if item is not None]
    results.sort(key=lambda row: row.confluence_score, reverse=True)
    return results[:14]


async def _get_multibagger_universe() -> list[str]:
    await _sync_script_master_daily()
    base = [_normalize_symbol_key(symbol) for symbol in MULTIBAGGER_UNIVERSE]
    base = [symbol for symbol in base if symbol and symbol not in {"NIFTY", "BANKNIFTY"}]

    rows = await db.script_master.find({}, {"_id": 0, "canonical_symbol": 1}).to_list(5000)
    dynamic_symbols: list[str] = []
    for row in rows:
        symbol = _normalize_symbol_key(str(row.get("canonical_symbol", "")))
        if not symbol or symbol in {"NIFTY", "BANKNIFTY"}:
            continue
        if len(symbol) < 2 or len(symbol) > 15:
            continue
        dynamic_symbols.append(symbol)

    merged = list(dict.fromkeys([*base, *dynamic_symbols]))
    # Runtime guard for FastAPI response performance while still covering a broad NSE universe slice
    return merged[:300]


async def _build_multibagger_candidates(refreshed_at: str) -> list[MultibaggerCandidate]:
    universe = await _get_multibagger_universe()

    semaphore = asyncio.Semaphore(18)

    async def _fetch_one(symbol: str) -> dict | None:
        async with semaphore:
            try:
                core = await get_stock_core(symbol)
                if core.get("ltp") is None:
                    return None
                return core
            except Exception:
                return None

    fetched = await asyncio.gather(*[_fetch_one(symbol) for symbol in universe])
    results = [row for row in fetched if row is not None]
    candidates: list[MultibaggerCandidate] = []
    for row in results:
        stock = StockCoreNormalized(**row)
        if stock.ltp is None:
            continue

        analysis = compute_multibagger_analysis(stock)
        candidates.append(
            MultibaggerCandidate(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector,
                ltp=stock.ltp,
                market_cap_cr=stock.market_cap,
                pe_ratio=stock.pe_ratio,
                year_high=stock.year_high,
                year_low=stock.year_low,
                upside_to_52w_high_pct=analysis["upside_to_52w_high_pct"],
                pb_ratio_est=analysis["pb_ratio_est"],
                peg_ratio_est=analysis["peg_ratio_est"],
                tier_pass_count=analysis["tier_pass_count"],
                is_potential_multibagger=analysis["is_potential_multibagger"],
                multibagger_score=analysis["multibagger_score"],
                current_rsi_level=analysis["current_rsi_level"],
                gtt_buy_price=analysis["gtt_buy_price"],
                targeted_upside_price=analysis["targeted_upside_price"],
                targeted_upside_profit_pct=analysis["targeted_upside_profit_pct"],
                thesis=analysis["thesis"],
                analysis_refreshed_at=refreshed_at,
            )
        )

    candidates.sort(
        key=lambda row: (row.is_potential_multibagger, row.multibagger_score),
        reverse=True,
    )
    return candidates[:80]


def _position_to_response(position: dict) -> CustomPositionResponse:
    lot_size = int(position.get("lot_size", 1))
    quantity_lots = max(1, int(position.get("quantity_lots", 1)))
    units = max(1, lot_size * quantity_lots)
    buy_price = float(position["buy_price"])
    latest_option_ltp = _to_float(position.get("latest_option_ltp"))
    target1 = _to_float(position.get("target1"))
    target2 = _to_float(position.get("target2"))

    target1_achieved = bool(latest_option_ltp is not None and target1 is not None and latest_option_ltp >= target1)
    target2_achieved = bool(latest_option_ltp is not None and target2 is not None and latest_option_ltp >= target2)

    buy_to_ltp_diff = round(float(latest_option_ltp) - buy_price, 2) if latest_option_ltp is not None else None
    ltp_to_t1_diff = round(max(float(target1) - float(latest_option_ltp), 0.0), 2) if (target1 is not None and latest_option_ltp is not None) else None
    ltp_to_t2_diff = round(max(float(target2) - float(latest_option_ltp), 0.0), 2) if (target2 is not None and latest_option_ltp is not None) else None

    sold_price = _to_float(position.get("sold_price"))
    realized_pnl = _to_float(position.get("realized_pnl"))
    if realized_pnl is None and sold_price is not None:
        realized_pnl = round((sold_price - buy_price) * units, 2)

    can_sell = position.get("status") == "OPEN" and (target1_achieved or target2_achieved)

    return CustomPositionResponse(
        id=position["id"],
        script=position["script"],
        underlying=position["underlying"],
        expiry_date=position["expiry_date"],
        expiry_time_ist=position.get("expiry_time_ist", "15:30"),
        lot_size=lot_size,
        quantity_lots=quantity_lots,
        units=units,
        buy_price=buy_price,
        created_at=position["created_at"],
        last_update=position["last_update"],
        status=position["status"],
        alert=position.get("alert"),
        latest_option_ltp=latest_option_ltp,
        target1=target1,
        target2=target2,
        buy_to_ltp_diff=buy_to_ltp_diff,
        ltp_to_t1_diff=ltp_to_t1_diff,
        ltp_to_t2_diff=ltp_to_t2_diff,
        target1_achieved=target1_achieved,
        target2_achieved=target2_achieved,
        can_sell=can_sell,
        sold_price=sold_price,
        realized_pnl=realized_pnl,
        projected_exit_price=position.get("projected_exit_price"),
        best_exit_price=position.get("best_exit_price"),
        recovery_potential=position.get("recovery_potential"),
        minutes_to_expiry=int(position.get("minutes_to_expiry", 0)),
        revised_exit_plan=position.get("revised_exit_plan", ""),
    )


async def _refresh_open_position(position: dict) -> dict:
    contract_dict = {
        "script": position["script"],
        "underlying": position["underlying"],
        "expiry": position["expiry_date"],
        "expiry_time_ist": position.get("expiry_time_ist", "15:30"),
        "strike": position["strike"],
        "option_type": position["option_type"],
        "exchange": "NFO",
        "lot_size": position.get("lot_size", 1),
    }
    contract = FNOContract(**contract_dict)
    minutes_to_expiry = get_minutes_to_expiry(contract)

    if minutes_to_expiry <= 0:
        updated = await db.custom_positions.find_one_and_update(
            {"id": position["id"]},
            {
                "$set": {
                    "status": "EXPIRED",
                    "alert": "EXPIRED",
                    "minutes_to_expiry": minutes_to_expiry,
                    "last_update": _utc_now_iso(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return updated

    try:
        latest_option_ltp = await _fetch_live_option_ltp(contract)
    except Exception:
        updated = await db.custom_positions.find_one_and_update(
            {"id": position["id"]},
            {
                "$set": {
                    "alert": "LIVE_LTP_UNAVAILABLE",
                    "minutes_to_expiry": minutes_to_expiry,
                    "last_update": _utc_now_iso(),
                    "revised_exit_plan": "Live option feed unavailable; showing last confirmed option LTP.",
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return updated
    buy_price = float(position["buy_price"])
    pnl_pct = ((latest_option_ltp - buy_price) / buy_price) if buy_price > 0 else 0.0
    revised_target1 = round(float(position.get("target1") or (buy_price * 1.12)), 2)
    revised_target2 = round(float(position.get("target2") or (buy_price * 1.5)), 2)
    projected_exit_price = None
    raw_recovery_potential = ((revised_target1 - latest_option_ltp) / max(latest_option_ltp, 0.01)) if latest_option_ltp > 0 else 0.0
    if minutes_to_expiry <= 120:
        max_recoverable_pct = 0.08
    elif minutes_to_expiry <= 360:
        max_recoverable_pct = 0.10
    else:
        max_recoverable_pct = 0.14
    recovery_potential = max(0.0, min(raw_recovery_potential, max_recoverable_pct))
    best_exit_price = None

    alert = None
    revised_exit_plan = "Hold with trailing stop once target1 hits"
    if pnl_pct <= -0.35 and recovery_potential <= 0.14:
        alert = "EXIT_NOW_HIGH_LOSS"
        projected_exit_price = round(max(latest_option_ltp * 1.03, latest_option_ltp + 1.0), 2)
        best_exit_price = projected_exit_price
        revised_exit_plan = (
            f"URGENT EXIT: Loss >35% and recovery potential is weak ({recovery_potential * 100:.1f}%). Exit near ₹{projected_exit_price}."
        )
    elif minutes_to_expiry <= 15:
        alert = "EXIT_URGENT_TIME"
        revised_exit_plan = "URGENT EXIT: Less than 15 minutes to expiry"
    elif pnl_pct <= -0.12:
        alert = "EXIT_URGENT_LOSS"
        revised_exit_plan = "URGENT EXIT: Loss exceeded 12% from buy"
    elif minutes_to_expiry < 60 and ((position["target1"] - latest_option_ltp) / max(latest_option_ltp, 0.01)) > 0.12:
        alert = "RISKY_PREMIUM"
        revised_exit_plan = "High premium-risk near expiry; consider reducing exposure"

    updated = await db.custom_positions.find_one_and_update(
        {"id": position["id"]},
        {
            "$set": {
                "latest_option_ltp": round(float(latest_option_ltp), 2),
                "target1": revised_target1,
                "target2": revised_target2,
                "minutes_to_expiry": minutes_to_expiry,
                "alert": alert,
                "projected_exit_price": projected_exit_price,
                "best_exit_price": best_exit_price,
                "recovery_potential": round(recovery_potential, 4),
                "last_update": _utc_now_iso(),
                "revised_exit_plan": revised_exit_plan,
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return updated


@api_router.get("/")
async def root():
    return {"message": "AI Stock Research API"}


@api_router.post("/auth/access", response_model=AccessResponse)
async def auth_access(payload: AccessRequest):
    await _ensure_owner_exists()
    credential = (payload.username or payload.password or "").strip()
    if not credential:
        raise HTTPException(status_code=400, detail="Username is required")

    if credential == LEGACY_OWNER_ALIAS:
        credential = OWNER_BOOTSTRAP_USERNAME
    credential = _validate_username(credential)

    user = await _get_user_by_username(credential)
    if not user and credential == OWNER_BOOTSTRAP_USERNAME:
        user = await _ensure_owner_exists()
    if not user:
        raise HTTPException(status_code=404, detail="Username not found. Please contact admin.")

    token = str(uuid.uuid4())
    SESSION_STORE[token] = {
        "user_key": user["user_key"],
        "created_at": _utc_now_iso(),
    }
    return AccessResponse(
        token=token,
        role=user["role"],
        credits=round(float(user.get("credits", 0)), 2),
        user_key=user["user_key"],
        username=user["username"],
        admin_exempt=_is_credit_exempt(user),
    )


@api_router.post("/auth/logout")
async def auth_logout(
    current_user: dict = Depends(get_current_user),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _ = current_user
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        SESSION_STORE.pop(token, None)
    return {"ok": True}


@api_router.get("/auth/me", response_model=MeResponse)
async def auth_me(current_user: dict = Depends(get_current_user)):
    return MeResponse(
        role=current_user["role"],
        credits=round(float(current_user.get("credits", 0)), 2),
        user_key=current_user["user_key"],
        username=current_user["username"],
        admin_exempt=_is_credit_exempt(current_user),
    )


@api_router.get("/script-master/lookup")
async def script_master_lookup(q: str = Query(default="")):
    query = q.strip()
    if not query:
        return {"query": query, "matches": []}

    await _sync_script_master_daily()
    resolved = await _resolve_symbol_input(query)
    row = await db.script_master.find_one(
        {"canonical_symbol": resolved},
        {"_id": 0, "canonical_symbol": 1, "display_name": 1, "aliases": 1},
    )
    if not row:
        return {"query": query, "matches": []}
    return {
        "query": query,
        "matches": [
            {
                "symbol": row.get("canonical_symbol"),
                "display_name": row.get("display_name"),
                "aliases": row.get("aliases", []),
            }
        ],
    }


@api_router.post("/script-master/refresh")
async def script_master_refresh(owner_user: dict = Depends(get_owner_user)):
    _ = owner_user
    global SCRIPT_MASTER_LAST_SYNC_DATE
    SCRIPT_MASTER_LAST_SYNC_DATE = None
    await _sync_script_master_daily(force=True)
    return {"refreshed": True, "date": datetime.now(IST).date().isoformat()}


@api_router.get("/admin/users", response_model=List[AdminUserView])
async def admin_list_users(admin_user: dict = Depends(get_admin_user)):
    if _is_owner(admin_user):
        rows = await db.app_users.find({}, {"_id": 0}).to_list(5000)
    else:
        rows = await db.app_users.find(
            {
                "$or": [
                    {"username": admin_user["username"]},
                    {"created_by": admin_user["username"]},
                    {"role": "owner"},
                ]
            },
            {"_id": 0},
        ).to_list(5000)
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    unique_rows = []
    seen_usernames = set()
    for row in rows:
        username = row.get("username")
        if not username:
            continue
        if username in seen_usernames:
            continue
        seen_usernames.add(username)
        unique_rows.append(row)
    return [_map_user_view(row) for row in unique_rows]


@api_router.post("/admin/users", response_model=AdminUserView)
async def admin_create_user(payload: AdminCreateUserRequest, admin_user: dict = Depends(get_admin_user)):
    username = (payload.username or payload.password or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    username = _validate_username(username)

    if await _get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")

    role = payload.role
    if admin_user["role"] == "sub_admin":
        if role != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can create only Basic Users")
        if int(admin_user.get("quota_used", 0)) >= int(admin_user.get("quota_limit", 0)):
            raise HTTPException(status_code=403, detail="Sub-Admin user creation quota exhausted")

    doc = {
        "user_key": str(uuid.uuid4()),
        "username": username,
        "role": role,
        "credits": max(0.0, float(payload.initial_credits)),
        "created_at": _utc_now_iso(),
        "created_by": admin_user["username"],
        "quota_limit": max(1, int(payload.quota_limit)) if role == "sub_admin" else 0,
        "quota_used": 0,
    }
    await db.app_users.insert_one(doc)

    if admin_user["role"] == "sub_admin":
        await db.app_users.update_one(
            {"user_key": admin_user["user_key"]},
            {"$inc": {"quota_used": 1}},
        )

    return _map_user_view(doc)


@api_router.patch("/admin/users/{user_ref}/credits", response_model=AdminUserView)
async def admin_set_credits(
    user_ref: str,
    payload: AdminSetCreditsRequest,
    admin_user: dict = Depends(get_admin_user),
):
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner" and not _is_owner(admin_user):
        raise HTTPException(status_code=403, detail="Only Owner can modify Owner")

    if admin_user["role"] == "sub_admin":
        if target.get("created_by") != admin_user["username"] or target["role"] != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can modify only own basic users")

    updated = await db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"credits": max(0.0, float(payload.credits))}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return _map_user_view(updated)


@api_router.patch("/admin/users/{user_ref}/quota", response_model=AdminUserView)
async def admin_set_quota(
    user_ref: str,
    payload: AdminSetQuotaRequest,
    owner_user: dict = Depends(get_owner_user),
):
    _ = owner_user
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] != "sub_admin":
        raise HTTPException(status_code=400, detail="Quota applies only to Sub-Admin")

    updated = await db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"quota_limit": max(1, int(payload.quota_limit))}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return _map_user_view(updated)


@api_router.delete("/admin/users/{user_ref}")
async def admin_delete_user(user_ref: str, admin_user: dict = Depends(get_admin_user)):
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot be deleted")

    if admin_user["role"] == "sub_admin":
        if target.get("created_by") != admin_user["username"] or target["role"] != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can delete only own basic users")

    await db.app_users.delete_one({"user_key": target["user_key"]})
    for token, session in list(SESSION_STORE.items()):
        if session.get("user_key") == target["user_key"]:
            SESSION_STORE.pop(token, None)
    return {"deleted": True}


@api_router.patch("/admin/users/{user_ref}/profile", response_model=AdminUserView)
async def admin_update_user_profile(
    user_ref: str,
    payload: AdminUserProfileUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    _ = owner_user
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    updates: dict[str, object] = {}
    new_username: str | None = None
    if payload.username is not None:
        new_username = _validate_username(payload.username)
        if new_username != target.get("username"):
            existing = await _get_user_by_username(new_username)
            if existing and existing.get("user_key") != target.get("user_key"):
                raise HTTPException(status_code=400, detail="Username already exists")
        updates["username"] = new_username

    if payload.role is not None:
        updates["role"] = payload.role

    if not updates:
        raise HTTPException(status_code=400, detail="No profile changes provided")

    old_username = target.get("username")
    updated = await db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": updates},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    if new_username and old_username and old_username != new_username:
        await db.app_users.update_many(
            {"created_by": old_username},
            {"$set": {"created_by": new_username}},
        )

    return _map_user_view(updated)


@api_router.patch("/admin/self/username", response_model=AdminUserView)
async def admin_update_own_username(
    payload: AdminUserProfileUpdateRequest,
    admin_user: dict = Depends(get_admin_user),
):
    if not payload.username:
        raise HTTPException(status_code=400, detail="Username is required")

    new_username = _validate_username(payload.username)
    if new_username != admin_user.get("username"):
        existing = await _get_user_by_username(new_username)
        if existing and existing.get("user_key") != admin_user.get("user_key"):
            raise HTTPException(status_code=400, detail="Username already exists")

    old_username = admin_user.get("username")
    updated = await db.app_users.find_one_and_update(
        {"user_key": admin_user["user_key"]},
        {"$set": {"username": new_username}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    if old_username and old_username != new_username:
        await db.app_users.update_many(
            {"created_by": old_username},
            {"$set": {"created_by": new_username}},
        )
    return _map_user_view(updated)


@api_router.get("/admin/config")
async def admin_get_config(owner_user: dict = Depends(get_owner_user)):
    _ = owner_user
    api_controls = await _get_api_controls(force_refresh=True)
    domains = await db.domain_mappings.find({}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    kite_status = await db.system_meta.find_one({"key": "kite_session"}, {"_id": 0, "access_token": 0})
    hosting_domain = ""
    hosting_ip = None
    if KITE_REDIRECT_URL:
        parsed = urlparse(KITE_REDIRECT_URL)
        hosting_domain = parsed.hostname or ""
        if hosting_domain:
            hosting_ip = _resolve_ipv4(hosting_domain)

    return {
        "api_controls": api_controls,
        "domain_mappings": domains,
        "kite": {
            "connected": bool(kite_status and kite_status.get("date") == _today_ist()),
            "user_id": (kite_status or {}).get("user_id"),
            "updated_at": (kite_status or {}).get("updated_at"),
            "redirect_url": KITE_REDIRECT_URL,
            "postback_url": os.environ.get("KITE_POSTBACK_URL"),
        },
        "hosting_dns_reference": {
            "hosting_domain": hosting_domain,
            "resolved_ipv4": hosting_ip,
            "recommended_record_type": "A",
            "example_apex_host": "@",
            "example_subdomain_host": "trade",
        },
        "dns_note": "A-record mapping requires DNS ownership changes at your domain registrar; app can store and verify mapping status only.",
        "dns_instructions": [
            "Do NOT change registrar nameservers.",
            "Open your current DNS Control Zone for the domain.",
            "Add/Update an A record for host '@' (apex) or your subdomain label (for example 'trade').",
            "Set the value to the hosting IPv4 shown in hosting_dns_reference.resolved_ipv4 (or target value configured below).",
            "Use TTL 300 seconds and remove conflicting A records for the same host.",
            "Verify propagation using nslookup/dig after 1-10 minutes.",
        ],
    }


@api_router.patch("/admin/api-controls")
async def admin_update_api_controls(
    payload: ApiControlUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    _ = owner_user
    current = await _get_api_controls(force_refresh=True)
    updated = {
        "kite_data_enabled": current.get("kite_data_enabled", True),
        "moneycontrol_data_enabled": current.get("moneycontrol_data_enabled", True),
        "strict_live_only": current.get("strict_live_only", True),
    }
    if payload.kite_data_enabled is not None:
        updated["kite_data_enabled"] = bool(payload.kite_data_enabled)
    if payload.moneycontrol_data_enabled is not None:
        updated["moneycontrol_data_enabled"] = bool(payload.moneycontrol_data_enabled)
    if payload.strict_live_only is not None:
        updated["strict_live_only"] = bool(payload.strict_live_only)

    await db.system_meta.update_one(
        {"key": "api_controls"},
        {
            "$set": {
                "key": "api_controls",
                **updated,
                "updated_at": _utc_now_iso(),
                "updated_by": owner_user.get("username"),
            }
        },
        upsert=True,
    )
    await _get_api_controls(force_refresh=True)
    return {"updated": True, "api_controls": updated}


@api_router.post("/admin/domain-mappings")
async def admin_create_domain_mapping(
    payload: DomainMappingCreateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    domain = _validate_domain(payload.domain)
    target_record = _normalize_target_record(payload.target_record)
    root_domain, host_label = _split_domain_root_and_host(domain)
    resolved_target_ip = _resolve_ipv4(target_record)

    await db.domain_mappings.update_one(
        {"domain": domain},
        {
            "$set": {
                "domain": domain,
                "root_domain": root_domain,
                "host_label": host_label,
                "record_type": payload.record_type,
                "target_record": target_record,
                "resolved_target_ip": resolved_target_ip,
                "status": "PENDING",
                "updated_by": owner_user.get("username"),
                "updated_at": _utc_now_iso(),
                "instructions": [
                    "Keep registrar nameservers unchanged.",
                    f"DNS host to add: {host_label}",
                    f"Record type: {payload.record_type}",
                    f"Record value: {resolved_target_ip or target_record}",
                    "TTL recommendation: 300 seconds",
                ],
            }
        },
        upsert=True,
    )
    row = await db.domain_mappings.find_one({"domain": domain}, {"_id": 0})
    return row


@api_router.patch("/admin/domain-mappings/{domain}")
async def admin_update_domain_mapping(
    domain: str,
    payload: DomainMappingStatusUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    key = _validate_domain(domain)
    updated = await db.domain_mappings.find_one_and_update(
        {"domain": key},
        {
            "$set": {
                "status": payload.status,
                "updated_by": owner_user.get("username"),
                "updated_at": _utc_now_iso(),
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Domain mapping not found")
    return updated


@api_router.get("/admin/dns-instructions")
async def admin_dns_instructions(
    domain: str = Query(...),
    target_record: str | None = Query(default=None),
    owner_user: dict = Depends(get_owner_user),
):
    _ = owner_user
    fqdn = _validate_domain(domain)
    root_domain, host_label = _split_domain_root_and_host(fqdn)
    selected_target = _normalize_target_record(target_record) if target_record else ""

    if not selected_target:
        row = await db.domain_mappings.find_one({"domain": fqdn}, {"_id": 0, "target_record": 1, "resolved_target_ip": 1})
        selected_target = (row or {}).get("resolved_target_ip") or (row or {}).get("target_record") or ""

    resolved = _resolve_ipv4(selected_target) if selected_target else None
    value = resolved or selected_target

    return {
        "fqdn": fqdn,
        "root_domain": root_domain,
        "host_label": host_label,
        "record_type": "A",
        "record_value": value,
        "steps": [
            "Do not change current nameservers at registrar.",
            "Open DNS Zone of your current DNS provider.",
            f"Create/Update A record: Host={host_label}, Value={value}, TTL=300.",
            "Delete any conflicting A record for the same host label.",
            "Wait for propagation and verify via nslookup or dig.",
        ],
    }


@api_router.post("/multibagger/generate", response_model=MultibaggerGenerateResponse)
async def generate_multibaggers(current_user: dict = Depends(get_current_user)):
    updated_user, charged = await _consume_credits(current_user, 2.0)
    refreshed_at = _utc_now_iso()
    candidates = await _build_multibagger_candidates(refreshed_at)
    potential_count = len([row for row in candidates if row.is_potential_multibagger])
    return MultibaggerGenerateResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        analysis_refreshed_at=refreshed_at,
        candidates=candidates,
        potential_count=potential_count,
    )


@api_router.post("/fno/generate", response_model=FNOGenerateResponse)
async def generate_fno_signals(payload: FNOGenerateRequest, current_user: dict = Depends(get_current_user)):
    updated_user, charged = await _consume_credits(current_user, 2)
    refreshed_at = _utc_now_iso()

    try:
        nifty_projection = await asyncio.wait_for(_build_index_projection("NIFTY", refreshed_at), timeout=25)
    except Exception:
        nifty_projection = IndexProjectionPane(
            index_name="NIFTY",
            spot=0,
            strike_range_min=0,
            strike_range_max=0,
            assured_signals=[],
            watchlist_signals=[],
            non_directional_strategies=[],
            rejection_note="NIFTY projection temporarily unavailable",
            with_consolidated_report=IndexAnalysisReport(
                report_type="with_consolidated",
                breadth_score=0,
                momentum_score=0,
                bias="NEUTRAL",
                top_contributors=[],
                summary="NIFTY projection temporarily unavailable",
            ),
            without_consolidated_report=IndexAnalysisReport(
                report_type="without_consolidated",
                breadth_score=0,
                momentum_score=0,
                bias="NEUTRAL",
                top_contributors=[],
                summary="NIFTY projection temporarily unavailable",
            ),
        )

    try:
        banknifty_projection = await asyncio.wait_for(_build_index_projection("BANKNIFTY", refreshed_at), timeout=25)
    except Exception:
        banknifty_projection = IndexProjectionPane(
            index_name="BANKNIFTY",
            spot=0,
            strike_range_min=0,
            strike_range_max=0,
            assured_signals=[],
            watchlist_signals=[],
            non_directional_strategies=[],
            rejection_note="BANKNIFTY projection temporarily unavailable",
            with_consolidated_report=IndexAnalysisReport(
                report_type="with_consolidated",
                breadth_score=0,
                momentum_score=0,
                bias="NEUTRAL",
                top_contributors=[],
                summary="BANKNIFTY projection temporarily unavailable",
            ),
            without_consolidated_report=IndexAnalysisReport(
                report_type="without_consolidated",
                breadth_score=0,
                momentum_score=0,
                bias="NEUTRAL",
                top_contributors=[],
                summary="BANKNIFTY projection temporarily unavailable",
            ),
        )

    try:
        stock_signals = await asyncio.wait_for(_build_stock_fno_signals(refreshed_at), timeout=20)
    except Exception:
        stock_signals = []

    potential_signals = [
        *nifty_projection.assured_signals,
        *banknifty_projection.assured_signals,
    ]
    signals = sorted(potential_signals, key=lambda row: row.confluence_score, reverse=True)

    custom_signal = None
    if payload.custom_script:
        contract = await _resolve_contract_from_input(payload.custom_script)
        try:
            custom_signal = await _build_signal_for_contract(contract, refreshed_at)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    top_pool = [*signals, *stock_signals]
    if custom_signal:
        top_pool.append(custom_signal)
    top_trades = sorted(top_pool, key=lambda row: (row.is_potential_trade, row.confluence_score), reverse=True)[:4]

    return FNOGenerateResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        analysis_refreshed_at=refreshed_at,
        signals=signals,
        potential_signals=[row for row in signals if row.is_potential_trade],
        top_trades=top_trades,
        custom_signal=custom_signal,
        nifty_projection=nifty_projection,
        banknifty_projection=banknifty_projection,
        stock_signals=stock_signals,
    )


@api_router.post("/fno/custom-position", response_model=CustomPositionCreateResponse)
async def create_custom_position(
    payload: CustomPositionCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if payload.buy_price <= 0:
        raise HTTPException(status_code=400, detail="Buy price must be greater than 0")

    contract = await _resolve_contract_from_input(payload.script)
    minutes_to_expiry = get_minutes_to_expiry(contract)
    _validate_expiry_guard(minutes_to_expiry)

    updated_user, charged = await _consume_credits(current_user, 1.0)
    try:
        latest_option_ltp = await _fetch_live_option_ltp(contract)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch live option LTP") from exc

    position_id = str(uuid.uuid4())
    now_iso = _utc_now_iso()
    doc = {
        "id": position_id,
        "user_key": current_user["user_key"],
        "script": contract.script,
        "underlying": contract.underlying,
        "expiry_date": contract.expiry,
        "expiry_time_ist": contract.expiry_time_ist,
        "strike": contract.strike,
        "option_type": contract.option_type,
        "lot_size": contract.lot_size,
        "quantity_lots": 1,
        "buy_price": round(float(payload.buy_price), 2),
        "created_at": now_iso,
        "last_update": now_iso,
        "status": "OPEN",
        "alert": None,
        "latest_option_ltp": round(float(latest_option_ltp), 2),
        "target1": round(float(payload.buy_price) * 1.12, 2),
        "target2": round(float(payload.buy_price) * 1.5, 2),
        "projected_exit_price": None,
        "best_exit_price": None,
        "recovery_potential": None,
        "sold_price": None,
        "realized_pnl": None,
        "minutes_to_expiry": minutes_to_expiry,
        "revised_exit_plan": "Hold with trailing stop once target1 hits",
    }

    await db.custom_positions.insert_one(doc)
    return CustomPositionCreateResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        position=_position_to_response(doc),
    )


@api_router.get("/fno/custom-positions", response_model=List[CustomPositionResponse])
async def list_custom_positions(current_user: dict = Depends(get_current_user)):
    rows = await db.custom_positions.find(
        {"user_key": current_user["user_key"], "status": {"$in": ["OPEN", "SOLD"]}},
        {"_id": 0},
    ).to_list(200)

    refreshed: list[CustomPositionResponse] = []
    for row in rows:
        if row.get("status") == "SOLD":
            refreshed.append(_position_to_response(row))
            continue
        try:
            updated = await _refresh_open_position(row)
            if updated and updated.get("status") == "OPEN":
                refreshed.append(_position_to_response(updated))
        except Exception as exc:
            logger.warning("Failed to refresh custom position %s: %s", row.get("id"), exc)
            fallback = {
                **row,
                "alert": row.get("alert") or "REFRESH_ERROR",
                "revised_exit_plan": row.get("revised_exit_plan") or "Temporary refresh issue; retry in a moment",
            }
            refreshed.append(_position_to_response(fallback))
            continue

    refreshed.sort(key=lambda item: item.created_at, reverse=True)
    return refreshed


@api_router.post("/fno/custom-position/{position_id}/sell", response_model=CustomPositionResponse)
async def sell_custom_position(
    position_id: str,
    payload: CustomPositionSellRequest,
    current_user: dict = Depends(get_current_user),
):
    if payload.sold_price <= 0:
        raise HTTPException(status_code=400, detail="Sold price must be greater than 0")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Please confirm sale before submitting")

    row = await db.custom_positions.find_one(
        {"id": position_id, "user_key": current_user["user_key"], "status": "OPEN"},
        {"_id": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Open custom position not found")

    response_view = _position_to_response(row)
    if not (response_view.target1_achieved or response_view.target2_achieved):
        raise HTTPException(status_code=400, detail="Sell allowed only after T1 or T2 is achieved")

    units = max(1, int(row.get("lot_size", 1)) * int(row.get("quantity_lots", 1) or 1))
    realized_pnl = round((float(payload.sold_price) - float(row["buy_price"])) * units, 2)

    updated = await db.custom_positions.find_one_and_update(
        {"id": position_id, "user_key": current_user["user_key"], "status": "OPEN"},
        {
            "$set": {
                "status": "SOLD",
                "alert": "SOLD",
                "sold_price": round(float(payload.sold_price), 2),
                "realized_pnl": realized_pnl,
                "last_update": _utc_now_iso(),
                "revised_exit_plan": "Position sold by user.",
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Open custom position not found")
    return _position_to_response(updated)


@api_router.post("/fno/custom-position/{position_id}/close")
async def close_custom_position(position_id: str, current_user: dict = Depends(get_current_user)):
    updated = await db.custom_positions.find_one_and_update(
        {
            "id": position_id,
            "user_key": current_user["user_key"],
            "status": "OPEN",
        },
        {
            "$set": {
                "status": "CLOSED",
                "last_update": _utc_now_iso(),
                "alert": "CLOSED_BY_USER",
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Custom position not found")
    return {"closed": True, "id": position_id}


@api_router.post("/portfolio/analyze", response_model=PortfolioAnalyzeResponse)
async def analyze_portfolio_manual(
    payload: PortfolioAnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    normalized = [item.model_dump() for item in payload.positions]
    analysis = await _analyze_portfolio_positions(normalized)
    cost = round(0.2 * analysis.parsed_positions_count, 2)
    updated_user, charged = await _consume_credits(current_user, cost)
    return PortfolioAnalyzeResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        parsed_positions_count=analysis.parsed_positions_count,
        stocks=analysis.stocks,
    )


@api_router.post("/portfolio/analyze-upload", response_model=PortfolioAnalyzeResponse)
async def analyze_portfolio_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    extension = (file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else ""
    allowed = {"txt", "csv", "xls", "xlsx", "pdf", "jpg", "jpeg", "bmp", "png", "webp"}
    if extension not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    positions = await _parse_positions_from_upload(file)
    if not positions:
        ocr_hint = "enabled" if _is_tesseract_ready() else "not available"
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid rows could be parsed from uploaded file. "
                "Use columns like Symbol/Name, Avg Price, Quantity. "
                f"OCR engine status: {ocr_hint}."
            ),
        )
    analysis = await _analyze_portfolio_positions(positions)
    cost = round(0.2 * analysis.parsed_positions_count, 2)
    updated_user, charged = await _consume_credits(current_user, cost)
    return PortfolioAnalyzeResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        parsed_positions_count=analysis.parsed_positions_count,
        stocks=analysis.stocks,
    )


@api_router.get("/fno/scripts/search", response_model=ScriptSearchResult)
async def search_scripts(q: str = Query(default="")):
    query = q.strip().upper()
    suggestions = []
    for row in FNO_CONTRACTS:
        script = row["script"]
        if not query or query in script:
            suggestions.append(script)
    suggestions = sorted(set(suggestions))[:30]
    return ScriptSearchResult(query=query, suggestions=suggestions)


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()
    _ = await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check.get("timestamp"), str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])
    return status_checks


# Backward compatibility endpoints
@api_router.get("/multibagger/candidates", response_model=List[MultibaggerCandidate])
async def get_multibagger_candidates(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    return await _build_multibagger_candidates(_utc_now_iso())


@api_router.get("/fno/contracts", response_model=List[FNOContract])
async def get_fno_contracts():
    return [FNOContract(**row) for row in FNO_CONTRACTS]


@api_router.get("/fno/signal/{script}", response_model=FNOSignalResponse)
async def get_single_fno_signal(script: str, refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    contract = await _resolve_contract_from_input(script)
    try:
        return await _build_signal_for_contract(contract, _utc_now_iso())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@api_router.get("/fno/signals/index", response_model=List[FNOSignalResponse])
async def get_index_fno_signals(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    refreshed_at = _utc_now_iso()
    nifty_projection, bank_projection = await asyncio.gather(
        _build_index_projection("NIFTY", refreshed_at),
        _build_index_projection("BANKNIFTY", refreshed_at),
    )
    return sorted(
        [*nifty_projection.assured_signals, *bank_projection.assured_signals],
        key=lambda row: row.confluence_score,
        reverse=True,
    )


@api_router.get("/fno/signals/potential", response_model=List[FNOSignalResponse])
async def get_potential_index_signals(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    rows = await get_index_fno_signals(refresh_nonce=None)
    if rows:
        return rows[:6]
    return rows


@api_router.get("/kite/auth-url")
async def get_kite_auth_url(current_user: dict = Depends(get_owner_user)):
    _ = current_user
    if not KITE_API_KEY or not KITE_API_SECRET or not KITE_REDIRECT_URL:
        raise HTTPException(status_code=400, detail="Kite credentials not configured")
    return {
        "auth_url": f"https://kite.zerodha.com/connect/login?v=3&api_key={KITE_API_KEY}",
        "redirect_url": KITE_REDIRECT_URL,
    }


@api_router.get("/kite/callback")
async def kite_callback(request_token: str = Query(...), status: str | None = Query(default=None)):
    _ = status
    if not KITE_API_KEY or not KITE_API_SECRET:
        raise HTTPException(status_code=400, detail="Kite credentials not configured")

    checksum = hashlib.sha256(f"{KITE_API_KEY}{request_token}{KITE_API_SECRET}".encode()).hexdigest()

    def _create_session() -> dict:
        response = requests.post(
            "https://api.kite.trade/session/token",
            data={
                "api_key": KITE_API_KEY,
                "request_token": request_token,
                "checksum": checksum,
            },
            headers={"X-Kite-Version": "3"},
            timeout=15,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Kite session exchange failed")
        payload = response.json()
        if payload.get("status") != "success":
            raise HTTPException(status_code=502, detail="Kite session exchange failed")
        return payload.get("data", {})

    session_data = await asyncio.to_thread(_create_session)
    access_token = str(session_data.get("access_token", "")).strip()
    if not access_token:
        raise HTTPException(status_code=502, detail="Kite access token missing")

    today = _today_ist()
    await db.system_meta.update_one(
        {"key": "kite_session"},
        {
            "$set": {
                "key": "kite_session",
                "date": today,
                "api_key": KITE_API_KEY,
                "access_token": access_token,
                "public_token": session_data.get("public_token"),
                "user_id": session_data.get("user_id"),
                "user_name": session_data.get("user_name"),
                "updated_at": _utc_now_iso(),
            }
        },
        upsert=True,
    )

    await _sync_kite_option_master_daily(force=True)
    return {
        "connected": True,
        "user_id": session_data.get("user_id"),
        "updated_at": _utc_now_iso(),
    }


@api_router.get("/kite/status")
async def kite_status(current_user: dict = Depends(get_owner_user)):
    _ = current_user
    row = await db.system_meta.find_one({"key": "kite_session"}, {"_id": 0, "access_token": 0})
    if not row:
        return {"connected": False}
    return {
        "connected": bool(row.get("date") == _today_ist()),
        "date": row.get("date"),
        "user_id": row.get("user_id"),
        "updated_at": row.get("updated_at"),
    }


@api_router.post("/kite/refresh-option-master")
async def kite_refresh_option_master(current_user: dict = Depends(get_owner_user)):
    _ = current_user
    await _sync_kite_option_master_daily(force=True)
    meta = await db.system_meta.find_one({"key": "kite_option_master_sync"}, {"_id": 0})
    return {"refreshed": True, "meta": meta or {}}


@api_router.post("/kite/postback")
async def kite_postback(payload: dict):
    _ = payload
    return {"received": True}


@api_router.get("/kite/policy")
async def kite_policy(current_user: dict = Depends(get_owner_user)):
    _ = current_user
    return {
        "read_only_mode": KITE_READ_ONLY_MODE,
        "trading_enabled": False,
        "allowed_data_endpoints": KITE_ALLOWED_DATA_ENDPOINTS,
        "blocked_categories": ["orders", "gtt", "positions-write", "basket-orders"],
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_tasks():
    await _ensure_owner_exists()
    await _sync_script_master_daily()
    await _sync_kite_option_master_daily()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
