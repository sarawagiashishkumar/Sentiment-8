import asyncio
import csv
import difflib
import io
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Literal

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
    "SBIN",
    "TCS",
]

SCRIPT_MASTER_LAST_SYNC_DATE: str | None = None
NSE_SCRIPT_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
ANGEL_SCRIPT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
KITE_SCRIPT_MASTER_URL = "https://api.kite.trade/instruments"
DHAN_SCRIPT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

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
    non_directional_strategies: List[NonDirectionalStrategy]
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


class CustomPositionResponse(BaseModel):
    id: str
    script: str
    underlying: str
    expiry_date: str
    expiry_time_ist: str
    lot_size: int
    buy_price: float
    created_at: str
    last_update: str
    status: Literal["OPEN", "CLOSED", "EXPIRED"]
    alert: str | None = None
    latest_option_ltp: float | None = None
    target1: float | None = None
    target2: float | None = None
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
        positions.append(
            {
                "symbol": re.sub(r"[^A-Z0-9]", "", symbol),
                "avg_price": round(avg_price, 4),
                "quantity": round(quantity, 4),
            }
        )
    return positions


def _extract_positions_from_text_lines(text: str) -> list[dict]:
    positions: list[dict] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pattern = re.compile(r"([A-Za-z0-9&.-]{2,})\s+([0-9,.]+)\s+([0-9,.]+)")
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        symbol, avg_txt, qty_txt = match.groups()
        avg_price = _to_float(avg_txt)
        quantity = _to_float(qty_txt)
        if avg_price is None or quantity is None or quantity <= 0:
            continue
        cleaned = re.sub(r"[^A-Z0-9]", "", symbol.upper())
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
        pytesseract.image_to_string(enhanced, config="--psm 6"),
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

    source_rows = [*nse_rows, *angel_rows, *kite_rows, *dhan_rows]
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
                        "$regex": "|".join(re.escape(item) for item in normalized_variants)
                    }
                },
                {"display_name": {"$regex": re.escape(raw_query), "$options": "i"}},
            ]
        },
        {"_id": 0, "canonical_symbol": 1, "display_name": 1, "normalized_aliases": 1},
    ).to_list(250)
    if regex_candidates:
        def _candidate_sort_key(item: dict) -> tuple[int, int]:
            normalized_aliases = item.get("normalized_aliases", [])
            exact = 1 if any(candidate in normalized_aliases for candidate in normalized_variants) else 0
            starts_with = 1 if any(
                str(alias).startswith(candidate)
                for alias in normalized_aliases
                for candidate in normalized_variants
            ) else 0
            score = (exact * 100) + (starts_with * 50)
            display = _normalize_symbol_key(str(item.get("display_name", "")))
            similarity = int(difflib.SequenceMatcher(None, cleaned, display).ratio() * 100)
            return (score, similarity)

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

    tier_1_market_cap = market_cap is not None and 500 < market_cap < 1_000_000
    tier_1_price_zone = (
        ltp is not None
        and year_low is not None
        and year_high is not None
        and ltp <= 1.15 * year_low
        and year_high >= 1.70 * ltp
        and ltp >= 10
        and pb_ratio_est is not None
        and pb_ratio_est < 5
        and peg_ratio_est is not None
        and peg_ratio_est < 1.5
    )

    tier_2_revenue_profit_proxy = (
        eps is not None
        and eps > 0
        and pe is not None
        and pe < 45
        and upside_to_52w_high_pct is not None
        and upside_to_52w_high_pct >= 12
    )
    tier_3_profitability_proxy = (
        pe is not None and 5 <= pe <= 40 and pb_ratio_est is not None and pb_ratio_est < 4.5
    )
    tier_4_balance_sheet_proxy = market_cap is not None and market_cap > 1_000 and stock.volume > 100_000
    tier_5_governance_proxy = stock.sector != "Unknown" and market_cap is not None and market_cap > 2_000
    tier_6_forensic_proxy = eps is not None and eps > 0 and pe is not None and 6 <= pe <= 45
    tier_7_cwip_capex_proxy = (
        year_high is not None and year_low is not None and year_low > 0 and year_high >= 1.20 * year_low
    )

    tier_flags = [
        tier_1_market_cap,
        tier_1_price_zone,
        tier_2_revenue_profit_proxy,
        tier_3_profitability_proxy,
        tier_4_balance_sheet_proxy,
        tier_5_governance_proxy,
        tier_6_forensic_proxy,
        tier_7_cwip_capex_proxy,
    ]
    tier_pass_count = sum(1 for state in tier_flags if state)

    mandatory_pass = tier_1_market_cap and tier_1_price_zone
    score = 9 * tier_pass_count + (15 if mandatory_pass else -6)
    if upside_to_52w_high_pct is not None:
        score += clamp(upside_to_52w_high_pct / 8, 0, 12)
    if peg_ratio_est is not None:
        score += 8 if peg_ratio_est < 1.5 else (4 if peg_ratio_est < 2.5 else 0)
    if pb_ratio_est is not None:
        score += 6 if pb_ratio_est < 3 else (3 if pb_ratio_est < 5 else 0)
    if pe is not None and pe > 55:
        score -= 10
    elif pe is not None and pe < 10:
        score -= 4

    final_score = int(clamp(round(score), 0, 100))
    is_potential_multibagger = (mandatory_pass and tier_pass_count >= 5) or (
        tier_pass_count >= 6 and final_score >= 68
    )

    position = _position_in_range(ltp, year_low, year_high)
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
    momentum_adj = (final_score - 55) / 300
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

    if bias_score >= 0.15:
        underlying_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif bias_score <= -0.15:
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
    is_potential_trade = direction != "NEUTRAL" and confluence_score >= 72 and risk_reward_target2 >= 2
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
    data_source: Literal["LIVE_OPTION_CHAIN", "MODELED_FROM_SPOT"] = "LIVE_OPTION_CHAIN"
    try:
        option_ltp = await asyncio.to_thread(
            market_data_client.fetch_option_ltp_for_contract,
            contract.model_dump(),
        )
    except Exception:
        if stock_data.ltp is None:
            raise
        if contract.underlying == "NIFTY":
            step = 50
        elif contract.underlying == "BANKNIFTY":
            step = 100
        else:
            step = 20 if stock_data.ltp > 300 else 10

        fallback_contract = contract.model_copy(
            update={"strike": float(round(stock_data.ltp / step) * step)}
        )
        try:
            option_ltp = await asyncio.to_thread(
                market_data_client.fetch_option_ltp_for_contract,
                fallback_contract.model_dump(),
            )
        except Exception:
            option_ltp = _estimate_option_ltp(stock_data.ltp, contract.strike, contract.option_type)
            data_source = "MODELED_FROM_SPOT"
    signal = build_fno_signal(
        contract,
        stock_data,
        option_ltp,
        refreshed_at,
        minutes_to_expiry,
    )
    if data_source == "MODELED_FROM_SPOT":
        signal = signal.model_copy(
            update={
                "data_source": "MODELED_FROM_SPOT",
                "trigger_factors": [*signal.trigger_factors, "OptionLTP=MODELED"],
            }
        )
    return signal


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
    rows: list[FNOSignalResponse] = []
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
            minutes_to_expiry = get_minutes_to_expiry(contract)
            if minutes_to_expiry <= 15:
                continue
            option_ltp = _estimate_option_ltp(stock.ltp, float(strike), option_type)
            try:
                signal = build_fno_signal(
                    contract,
                    stock,
                    option_ltp,
                    refreshed_at,
                    minutes_to_expiry,
                )
                signal = signal.model_copy(
                    update={
                        "data_source": "MODELED_FROM_SPOT",
                        "trigger_factors": [*signal.trigger_factors, "OptionLTP=MODELED"],
                    }
                )
                rows.append(signal)
            except HTTPException:
                continue

    potential = [item for item in rows if item.is_potential_trade]
    by_strike: dict[float, list[FNOSignalResponse]] = defaultdict(list)
    for row in potential:
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

    assured_signals = [
        item
        for item in potential
        if item.script not in paired_scripts and strike_range_min <= item.strike <= strike_range_max
    ]
    assured_signals.sort(key=lambda row: row.confluence_score, reverse=True)

    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY
    report_rows = await asyncio.gather(*[get_stock_core(symbol) for symbol, _ in weight_source])
    normalized_report_rows = [StockCoreNormalized(**row) for row in report_rows]
    with_report = _compute_report_from_rows(index_name, weight_source, normalized_report_rows, weighted=True)
    without_report = _compute_report_from_rows(index_name, weight_source, normalized_report_rows, weighted=False)

    return IndexProjectionPane(
        index_name=index_name,
        spot=round(stock.ltp, 2),
        strike_range_min=float(strike_range_min),
        strike_range_max=float(strike_range_max),
        assured_signals=assured_signals,
        non_directional_strategies=non_directional,
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
                    option_ltp = await asyncio.to_thread(
                        market_data_client.fetch_option_ltp_for_contract,
                        contract.model_dump(),
                    )
                except Exception:
                    option_ltp = _estimate_option_ltp(core.ltp, float(strike), option_type)

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
    return results


async def _build_multibagger_candidates(refreshed_at: str) -> list[MultibaggerCandidate]:
    results = await asyncio.gather(*[get_stock_core(symbol) for symbol in MULTIBAGGER_UNIVERSE])
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
                analysis_refreshed_at=refreshed_at,
            )
        )

    candidates.sort(
        key=lambda row: (row.is_potential_multibagger, row.multibagger_score),
        reverse=True,
    )
    return candidates[:30]


def _position_to_response(position: dict) -> CustomPositionResponse:
    return CustomPositionResponse(
        id=position["id"],
        script=position["script"],
        underlying=position["underlying"],
        expiry_date=position["expiry_date"],
        expiry_time_ist=position.get("expiry_time_ist", "15:30"),
        lot_size=int(position.get("lot_size", 1)),
        buy_price=float(position["buy_price"]),
        created_at=position["created_at"],
        last_update=position["last_update"],
        status=position["status"],
        alert=position.get("alert"),
        latest_option_ltp=position.get("latest_option_ltp"),
        target1=position.get("target1"),
        target2=position.get("target2"),
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
        latest_option_ltp = await asyncio.to_thread(
            market_data_client.fetch_option_ltp_for_contract,
            contract.model_dump(),
        )
    except Exception:
        spot_row = StockCoreNormalized(**(await get_stock_core(position["underlying"])))
        if spot_row.ltp is not None:
            latest_option_ltp = _estimate_option_ltp(
                spot_row.ltp,
                float(position["strike"]),
                str(position["option_type"]),
            )
        else:
            latest_option_ltp = float(position.get("latest_option_ltp") or position["buy_price"])
    buy_price = float(position["buy_price"])
    pnl_pct = ((latest_option_ltp - buy_price) / buy_price) if buy_price > 0 else 0.0
    revised_target1 = round(max(buy_price * 1.12, latest_option_ltp * 1.05), 2)
    revised_target2 = round(max(buy_price * 1.5, latest_option_ltp * 1.2), 2)
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
            non_directional_strategies=[],
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
            non_directional_strategies=[],
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
        latest_option_ltp = await asyncio.to_thread(
            market_data_client.fetch_option_ltp_for_contract,
            contract.model_dump(),
        )
    except Exception:
        core = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
        if core.ltp is None:
            raise HTTPException(status_code=502, detail="Unable to fetch live option LTP")
        latest_option_ltp = _estimate_option_ltp(core.ltp, contract.strike, contract.option_type)

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
        {"user_key": current_user["user_key"], "status": "OPEN"},
        {"_id": 0},
    ).to_list(200)

    refreshed: list[CustomPositionResponse] = []
    for row in rows:
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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
