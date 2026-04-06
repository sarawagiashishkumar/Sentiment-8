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
from services.research_engine import (
    check_stock_eligibility,
    check_urgent_exit,
    classify_market_regime,
    compute_atr_based_fno_targets,
    compute_full_technical_snapshot,
    compute_historical_volatility,
    compute_portfolio_risk_metrics,
    compute_portfolio_verdict,
    compute_realistic_price_bands,
    compute_technical_confluence_bonus,
    compute_altman_z_score,
    compute_earnings_quality,
    compute_forensic_red_flags,
    compute_roic_vs_wacc,
    compute_growth_quality,
    compute_forensic_audit,
    classify_market_regime_enhanced,
    compute_macro_context,
    get_sector_macro_beneficiaries,
    SECTOR_MACRO_IMPACT_MAP,
    compute_portfolio_correlation_matrix,
    compute_portfolio_stress_tests,
    compute_diversification_audit,
    compute_upcoming_catalysts,
    merge_duplicate_holdings,
    compute_master_stock_snapshot,
    STRATEGY_LIBRARY,
    get_eligible_strategies,
    select_strategy_for_signal,
    check_strategy_eligible,
    transition_signal_state,
    compute_index_constituent_bias,
    NIFTY50_WEIGHTS,
    BANKNIFTY_WEIGHTS,
)
from services.data_verifier import (
    fetch_verified_price,
    fetch_verified_snapshot,
    compute_vix_theta_decay,
    compute_dynamic_target_revision,
    get_minutes_to_session_close,
    is_market_open,
    get_market_session_status,
)
from services.sector_momentum import compute_sector_momentum_dashboard

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

# NSE holidays are now managed by services/holiday_manager.py (MongoDB-backed).
# This module-level set is populated at startup by init_holiday_manager().
from services.holiday_manager import get_nse_holidays, init_holiday_manager, shutdown_holiday_manager

NSE_HOLIDAYS: set[str] = set()  # Populated at startup

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
    # Index
    "NIFTY": 75,
    "BANKNIFTY": 30,
    "FINNIFTY": 65,
    "MIDCPNIFTY": 120,
    "SENSEX": 20,
    # Large Cap / Blue Chip
    "RELIANCE": 250,
    "TCS": 175,
    "SBIN": 750,
    "BDL": 1350,
    "HDFCBANK": 550,
    "ICICIBANK": 700,
    "INFY": 300,
    "LT": 50,
    "ITC": 2400,
    "AXISBANK": 1200,
    "KOTAKBANK": 800,
    "HDFCLIFE": 1000,
    "SBILIFE": 750,
    "ULTRACEMCO": 100,
    "BAJFINANCE": 250,
    "WIPRO": 1500,
    "HINDUNILVR": 300,
    "BHARTIARTL": 950,
    "ADANIPORTS": 1250,
    "TATAMOTORS": 1425,
    "ONGC": 3850,
    "COALINDIA": 4200,
    "NTPC": 6000,
    "POWERGRID": 4600,
    "TATASTEEL": 5500,
    "JSWSTEEL": 2500,
    "HINDALCO": 2150,
    "VEDL": 3250,
    "GRASIM": 375,
    "ASIANPAINT": 300,
    "BAJAJFINSV": 125,
    "SUNPHARMA": 350,
    "CIPLA": 650,
    "DRREDDY": 125,
    "DIVISLAB": 200,
    "HCLTECH": 350,
    "TECHM": 600,
    "NESTLEIND": 40,
    "TITAN": 375,
    "MARUTI": 50,
    "M&M": 700,
    "TATACONSUM": 1375,
    "APOLLOHOSP": 125,
    "HEROMOTOCO": 300,
    "EICHERMOT": 175,
    "BPCL": 4375,
    "IOCL": 5750,
    "HPCL": 5400,
    "INDUSINDBK": 500,
    "SHRIRAMFIN": 200,
    "DMART": 75,
    "PIDILITIND": 250,
    "SIEMENS": 175,
    "HAVELLS": 500,
    "ABB": 125,
    "BERGEPAINT": 1100,
    "TRENT": 350,
    "NAUKRI": 75,
    "PAGEIND": 15,
    "MPHASIS": 175,
    "PERSISTENT": 125,
    "COFORGE": 75,
    "LTIM": 75,
    "OFSS": 50,
    "BAJAJ-AUTO": 250,
    "SYNGENE": 650,
    "CHOLAFIN": 500,
    "MUTHOOTFIN": 375,
    "PFC": 5000,
    "RECLTD": 4000,
    "IRFC": 6000,
    "HAL": 150,
    "BEL": 5000,
    "BHEL": 7000,
    "SAIL": 10000,
    "NMDC": 7500,
    "GAIL": 6250,
    "IOC": 5750,
    "OIL": 2300,
    "MOTHERSON": 3500,
    "BOSCHLTD": 25,
    "MRF": 10,
    "BALKRISIND": 250,
    "OBEROIRLTY": 500,
    "DLF": 1650,
    "GODREJPROP": 400,
    "PRESTIGE": 1000,
    "SOBHA": 500,
    "BANDHANBNK": 2500,
    "FEDERALBNK": 5000,
    "IDFCFIRSTB": 5000,
    "RBLBANK": 5000,
    "YESBANK": 40000,
    "AUBANK": 500,
    "SBICARD": 800,
    "MANAPPURAM": 3000,
    "CANBK": 2700,
    "UCOBANK": 10000,
    "PNB": 10000,
    "BANKBARODA": 4350,
    "IDBI": 5500,
    "ZOMATO": 4500,
    "PAYTM": 2000,
    "POLICYBZR": 700,
    "NYKAA": 2000,
    "IRCTC": 875,
    "LUXIND": 150,
    "ABFRL": 2000,
    "ADITIMKT": 200,
    "JUBLFOOD": 500,
    "DEVYANI": 4000,
    "DEVIT": 800,
    "WEBELSOLAR": 625,
    "ADANIENT": 400,
    "ADANIPOWER": 2000,
    "ADANIGREEN": 500,
    "ADANITRANS": 300,
    "ADANIWILMAR": 2000,
    "AMBUJACEM": 2000,
    "ACCIND": 300,
    "SHREECEM": 25,
    "RAMCOCEM": 600,
    "TORNTPOWER": 500,
    "TATAPOWER": 3375,
    "CESC": 1300,
    "GIPCL": 2500,
    "TORNTPHARM": 500,
    "AUROPHARMA": 1000,
    "LUPIN": 700,
    "BIOCON": 2200,
    "GLENMARK": 1200,
    "IPCALAB": 500,
    "ALEMBICPHARMA": 600,
    "ATUL": 100,
    "PIIND": 200,
    "UPL": 1300,
    "DEEPAKNTR": 300,
    "CHLAA": 600,
    "CUMMINSIND": 300,
    "THERMAX": 250,
    "VOLTAS": 500,
    "BLUESTARCO": 300,
    "WHIRLPOOL": 225,
    "CROMPTON": 2000,
    "POLYCAB": 200,
    "KEI": 300,
    "DIXON": 75,
    "AAPLLTD": 500,
    "AMBER": 200,
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
STOCK_CORE_CACHE: dict[str, dict] = {}
STOCK_CORE_CACHE_TTL_SECONDS = 20

# India VIX cache (5-minute TTL)
INDIA_VIX_CACHE: dict = {}
INDIA_VIX_CACHE_TTL_SECONDS = 300

# Fundamental data in-memory cache (24h TTL)  
FUNDAMENTAL_CACHE: dict[str, dict] = {}
FUNDAMENTAL_CACHE_TTL_SECONDS = 86400

# Historical OHLCV in-memory cache (6h TTL)
HIST_OHLCV_CACHE: dict[str, dict] = {}
HIST_OHLCV_CACHE_TTL_SECONDS = 21600  # 6 hours

# Sector Momentum in-memory cache (30-min TTL)
SECTOR_MOMENTUM_CACHE: dict = {}
SECTOR_MOMENTUM_CACHE_TTL_SECONDS = 1800  # 30 minutes

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



# ─── Models (extracted to /app/backend/models/__init__.py) ────────────────────
from models import (
    StatusCheck, StatusCheckCreate, AccessRequest, AccessResponse, MeResponse,
    AdminUserView, AdminCreateUserRequest, AdminSetCreditsRequest,
    AdminSetQuotaRequest, AdminUserProfileUpdateRequest,
    DomainMappingCreateRequest, DomainMappingStatusUpdateRequest,
    ApiControlUpdateRequest, StockCoreNormalized,
    MultibaggerCandidate, FNOContract, FNOSignalResponse,
    NonDirectionalStrategy, IndexAnalysisReport, IndexProjectionPane,
    MultibaggerGenerateResponse, FNOGenerateRequest, FNOGenerateResponse,
    PortfolioPositionInput, PortfolioAnalyzeRequest,
    PortfolioHorizonRange, PortfolioExpectedSignal, PortfolioStockAnalysis,
    PortfolioAnalyzeResponse, CustomPositionCreateRequest,
    CustomPositionSellRequest, CustomPositionResponse,
    CustomPositionCreateResponse, ScriptSearchResult,
)

def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _sanitize_float(value) -> float | None:
    """Return None if value is NaN, Infinity or not a valid finite float."""
    import math
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


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


async def _get_stock_core_cached(symbol: str) -> dict:
    key = _normalize_symbol_key(symbol)
    now = datetime.now(timezone.utc).timestamp()
    cached = STOCK_CORE_CACHE.get(key)
    if cached and (now - float(cached.get("ts", 0))) <= STOCK_CORE_CACHE_TTL_SECONDS:
        return cached["data"]

    data = await get_stock_core(symbol)
    STOCK_CORE_CACHE[key] = {"ts": now, "data": data}
    return data


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

                # Store numeric instrument_token for historical data API
                raw_token = row.get("instrument_token", "")
                numeric_token = None
                try:
                    if raw_token:
                        numeric_token = int(float(str(raw_token).strip()))
                except (ValueError, TypeError):
                    numeric_token = None

                rows.append(
                    {
                        "underlying": underlying,
                        "expiry": expiry,
                        "strike": float(strike),
                        "option_type": instrument_type,
                        "tradingsymbol": tradingsymbol,
                        "instrument": f"NFO:{tradingsymbol}",
                        "instrument_token": numeric_token,  # numeric token for historical API
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


async def _resolve_kite_lot_size_for_script(script: str) -> int | None:
    if not script:
        return None
    await _sync_kite_option_master_daily()
    row = await db.kite_option_master.find_one(
        {"tradingsymbol": script.upper()},
        {"_id": 0, "lot_size": 1},
    )
    if not row:
        return None
    lot_size = int(_to_float(row.get("lot_size")) or 0)
    return lot_size if lot_size > 0 else None


async def _resolve_verified_lot_size(underlying: str, script: str | None = None) -> int:
    if script:
        by_script = await _resolve_kite_lot_size_for_script(script)
        if by_script and by_script > 0:
            return int(by_script)

    await _sync_kite_option_master_daily()
    row = await db.kite_option_master.find_one(
        {"underlying": _normalize_symbol_key(underlying)},
        {"_id": 0, "lot_size": 1},
    )
    if row:
        lot_size = int(_to_float(row.get("lot_size")) or 0)
        if lot_size > 0:
            return lot_size

    mapped = int(LOT_SIZE_MAP.get(_normalize_symbol_key(underlying), 1) or 1)
    return mapped if mapped > 0 else 1


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
    """Returns numeric instrument_token for historical API, falls back to NFO:tradingsymbol."""
    rows = await db.kite_option_master.find(
        {
            "underlying": contract.underlying,
            "expiry": contract.expiry,
            "option_type": contract.option_type,
        },
        {"_id": 0, "instrument": 1, "instrument_token": 1, "strike": 1},
    ).to_list(500)
    if not rows:
        return None

    target_strike = float(contract.strike)
    rows.sort(key=lambda item: abs(float(item.get("strike", 0.0)) - target_strike))
    best = rows[0]
    if abs(float(best.get("strike", 0.0)) - target_strike) > 0.01:
        return None
    # Prefer numeric instrument_token for historical API
    numeric_token = best.get("instrument_token")
    if numeric_token and str(numeric_token).isdigit():
        return str(numeric_token)
    # Fallback: NFO:tradingsymbol format
    instrument = str(best.get("instrument", "")).strip()
    return instrument or None


async def _fetch_option_snapshot_from_kite(contract: FNOContract) -> dict | None:
    access_token = await _get_kite_access_token()
    if not access_token or not KITE_API_KEY:
        return None

    await _sync_kite_option_master_daily()
    instrument = await _resolve_kite_instrument_for_contract(contract)
    if not instrument:
        return None

    def _fetch_snapshot() -> dict | None:
        try:
            response = requests.get(
                "https://api.kite.trade/quote",
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
            ohlc = row.get("ohlc") or {}
            day_high = _to_float(ohlc.get("high"))
            day_low = _to_float(ohlc.get("low"))
            return {
                "ltp": float(last_price),
                "day_high": float(day_high) if day_high is not None else None,
                "day_low": float(day_low) if day_low is not None else None,
            }
        except Exception:
            return None

    return await asyncio.to_thread(_fetch_snapshot)


async def _fetch_option_ltp_from_kite(contract: FNOContract) -> float | None:
    snapshot = await _fetch_option_snapshot_from_kite(contract)
    if not snapshot:
        return None
    return _to_float(snapshot.get("ltp"))


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


async def _fetch_option_snapshots_from_kite(contracts: list[FNOContract]) -> dict[str, dict]:
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
    instrument_snapshot: dict[str, dict] = {}

    def _fetch_batch(batch: list[str]) -> dict[str, dict]:
        params = [("i", item) for item in batch]
        try:
            response = requests.get(
                "https://api.kite.trade/quote",
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
            rows: dict[str, dict] = {}
            for instrument, row in data.items():
                ltp = _to_float((row or {}).get("last_price"))
                ohlc = (row or {}).get("ohlc") or {}
                if ltp is None or ltp <= 0:
                    continue
                rows[instrument] = {
                    "ltp": float(ltp),
                    "day_high": _to_float(ohlc.get("high")),
                    "day_low": _to_float(ohlc.get("low")),
                    "oi": _to_float(row.get("oi")),
                    "volume": _to_float(row.get("volume")),
                }
            return rows
        except Exception:
            return {}

    for idx in range(0, len(unique_instruments), 200):
        batch = unique_instruments[idx : idx + 200]
        rows = await asyncio.to_thread(_fetch_batch, batch)
        instrument_snapshot.update(rows)

    response: dict[str, dict] = {}
    for script, instrument in script_to_instrument.items():
        row = instrument_snapshot.get(instrument)
        if row and _to_float(row.get("ltp")):
            response[script] = row
    return response


async def _fetch_live_option_snapshot(contract: FNOContract) -> dict:
    controls = await _get_api_controls()

    if controls.get("kite_data_enabled", True):
        kite_snapshot = await _fetch_option_snapshot_from_kite(contract)
        if kite_snapshot and _to_float(kite_snapshot.get("ltp")):
            return kite_snapshot

    if controls.get("moneycontrol_data_enabled", True):
        try:
            ltp = float(
                await asyncio.to_thread(
                    market_data_client.fetch_option_ltp_for_contract,
                    contract.model_dump(),
                )
            )
            return {"ltp": ltp, "day_high": None, "day_low": None}
        except Exception:
            pass

    if not controls.get("strict_live_only", True):
        core = StockCoreNormalized(**(await _get_stock_core_cached(contract.underlying)))
        if core.ltp is not None:
            modeled = _estimate_option_ltp(core.ltp, contract.strike, contract.option_type)
            if modeled > 0:
                return {"ltp": float(modeled), "day_high": None, "day_low": None}

    raise HTTPException(status_code=502, detail=f"Live option LTP unavailable for {contract.script}")


async def _fetch_live_option_ltp(contract: FNOContract) -> float:
    snapshot = await _fetch_live_option_snapshot(contract)
    return float(snapshot.get("ltp"))


async def _fetch_historical_candles_from_kite(contract: FNOContract, interval: str = "minute", candles: int = 10) -> list[dict] | None:
    """
    Fetch historical OHLCV candles from Kite for micro-trend analysis.
    interval: 'minute', '3minute', '5minute', etc.
    candles: number of candles to fetch (default 10 = last 10 minutes for 1-min)
    """
    access_token = await _get_kite_access_token()
    if not access_token or not KITE_API_KEY:
        return None

    await _sync_kite_option_master_daily()
    instrument = await _resolve_kite_instrument_for_contract(contract)
    if not instrument:
        return None

    def _fetch_candles() -> list[dict] | None:
        try:
            from_date = datetime.now(IST) - timedelta(minutes=candles + 5)
            to_date = datetime.now(IST)
            
            response = requests.get(
                f"https://api.kite.trade/instruments/historical/{instrument}/{interval}",
                params={
                    "from": from_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "to": to_date.strftime("%Y-%m-%d %H:%M:%S"),
                },
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {KITE_API_KEY}:{access_token}",
                },
                timeout=15,
            )
            if response.status_code != 200:
                logger.warning(
                    "Historical candles API %s for instrument=%s: %s",
                    response.status_code, instrument, response.text[:300]
                )
                return None
            
            payload = response.json()
            data = payload.get("data", {})
            candles_data = data.get("candles", [])
            
            if not candles_data:
                return None
            
            parsed = []
            for candle in candles_data[-candles:]:
                if len(candle) >= 6:
                    parsed.append({
                        "timestamp": candle[0],
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": int(candle[5]),
                    })
            return parsed if parsed else None
        except Exception as exc:
            logger.warning("Failed to fetch historical candles: %s", exc)
            return None

    return await asyncio.to_thread(_fetch_candles)


def _analyze_micro_dip_prediction(candles: list[dict], current_ltp: float) -> dict:
    """
    Analyze 1-min candles to predict if a micro-dip is imminent.
    Returns: {
        'dip_expected': bool,
        'predicted_dip_price': float,
        'confidence': float (0-1),
        'reason': str
    }
    """
    if not candles or len(candles) < 5:
        return {
            "dip_expected": False,
            "predicted_dip_price": current_ltp,
            "confidence": 0.0,
            "reason": "Insufficient candle data",
        }

    recent_candles = candles[-5:]
    
    closes = [c["close"] for c in recent_candles]
    volumes = [c["volume"] for c in recent_candles]
    lows = [c["low"] for c in recent_candles]
    
    avg_volume = sum(volumes) / len(volumes)
    latest_volume = volumes[-1]
    recent_low = min(lows[-3:])
    
    price_momentum = (closes[-1] - closes[0]) / max(closes[0], 0.01)
    volume_spike = latest_volume / max(avg_volume, 1)
    
    distance_to_recent_low = ((current_ltp - recent_low) / max(current_ltp, 0.01)) * 100
    
    dip_indicators = []
    confidence_score = 0.0
    
    if price_momentum < -0.01:
        dip_indicators.append("DownwardMomentum")
        confidence_score += 0.25
    
    if volume_spike > 1.5:
        dip_indicators.append("VolumeSpike")
        confidence_score += 0.20
    
    if distance_to_recent_low > 2.0:
        dip_indicators.append("AboveRecentLow")
        confidence_score += 0.15
    
    consecutive_red = sum(1 for i in range(1, len(recent_candles)) if recent_candles[i]["close"] < recent_candles[i]["open"])
    if consecutive_red >= 3:
        dip_indicators.append(f"ConsecutiveRed={consecutive_red}")
        confidence_score += 0.25
    
    last_3_range = max(lows[-3:]) - min(lows[-3:])
    volatility_pct = (last_3_range / max(current_ltp, 0.01)) * 100
    if volatility_pct > 3.0:
        dip_indicators.append(f"HighVolatility={volatility_pct:.1f}%")
        confidence_score += 0.15
    
    dip_expected = confidence_score >= 0.35
    
    if dip_expected:
        dip_depth_pct = min(0.05 + (confidence_score - 0.35) * 0.15, 0.08)
        predicted_dip = current_ltp * (1 - dip_depth_pct)
        
        predicted_dip = max(predicted_dip, recent_low * 0.98)
    else:
        predicted_dip = current_ltp * 0.995
    
    return {
        "dip_expected": dip_expected,
        "predicted_dip_price": round(predicted_dip, 2),
        "confidence": round(min(confidence_score, 1.0), 2),
        "reason": f"Indicators: {', '.join(dip_indicators) if dip_indicators else 'No significant dip signals'}",
    }


def _portfolio_horizon_ranges(
    value_flag: str,
    price_zone: str,
    pnl_pct: float,
    ltp: float | None = None,
    hist_vol: float | None = None,
    sector: str = "Unknown",
    pe_ratio: float | None = None,
) -> dict[str, PortfolioHorizonRange]:
    """
    Compute realistic horizon ranges using historical volatility when available.
    Falls back to valuation-based static ranges if hist_vol is not available.
    """
    # If we have historical volatility, use the research engine for accurate bands
    if hist_vol is not None and ltp is not None and ltp > 0:
        vol_bands = compute_realistic_price_bands(
            ltp=ltp,
            hist_vol=hist_vol,
            sector=sector,
            pe_ratio=pe_ratio,
        )
        response: dict[str, PortfolioHorizonRange] = {}
        for horizon in ["1W", "1M", "3M", "6M", "9M", "1Y"]:
            band = vol_bands.get(horizon, {})
            upside_pct = band.get("upside_pct", 5.0)
            downside_pct = band.get("downside_pct", -5.0)
            flag: Literal["GREEN", "RED"] = band.get("flag", "GREEN")
            response[horizon] = PortfolioHorizonRange(
                upside_pct=round(upside_pct, 2),
                downside_pct=round(downside_pct, 2),
                flag=flag,
            )
        return response

    # Fallback: valuation-based static approach
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
    response2: dict[str, PortfolioHorizonRange] = {}
    for horizon, multiplier in horizons.items():
        upside = max(1.0, (base_up + oversold_bonus - overbought_penalty) * multiplier)
        downside = max(1.0, (base_down + overbought_penalty - oversold_bonus) * multiplier)
        flag2: Literal["GREEN", "RED"] = "GREEN" if upside >= downside * 1.15 else "RED"
        response2[horizon] = PortfolioHorizonRange(
            upside_pct=round(upside, 2),
            downside_pct=round(-downside, 2),
            flag=flag2,
        )
    return response2


async def _analyze_portfolio_positions(positions: list[dict]) -> PortfolioAnalyzeResponse:
    # ── Batch 4: Merge duplicate holdings first ───────────────────────────
    positions = merge_duplicate_holdings(positions)

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

    cores = await asyncio.gather(*[get_stock_core(item["symbol"]) for item in normalized_positions], return_exceptions=True)
    stock_rows: list[dict] = []
    failed_symbols: list[str] = []
    total_current_value = 0.0
    for idx, core in enumerate(cores):
        pos = normalized_positions[idx]
        sym = pos["symbol"]

        # Handle exceptions or None LTP — try symbol variations before giving up
        if isinstance(core, Exception) or (isinstance(core, dict) and StockCoreNormalized(**core).ltp is None):
            # Try EQ variant, uppercase trim
            variants = [
                sym.upper().strip(),
                sym.upper().replace("-EQ", "").replace(".NS", "").strip(),
                f"{sym.upper().strip()}-EQ",
            ]
            resolved_core = None
            for variant in variants:
                if variant == sym:
                    continue
                try:
                    candidate = await get_stock_core(variant)
                    if candidate and StockCoreNormalized(**candidate).ltp is not None:
                        resolved_core = candidate
                        break
                except Exception:
                    continue
            if resolved_core is None:
                logger.warning("Portfolio: No live data for symbol %s — skipping", sym)
                failed_symbols.append(sym)
                continue
            core = resolved_core

        stock = StockCoreNormalized(**core)
        if stock.ltp is None:
            logger.warning("Portfolio: LTP still None for symbol %s after fallback — skipping", sym)
            failed_symbols.append(sym)
            continue
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
        raise HTTPException(
            status_code=400,
            detail=f"No live data available for provided symbols. Failed: {', '.join(failed_symbols) or 'all'}"
        )

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

        expected_ranges = _portfolio_horizon_ranges(
            value_flag,
            price_zone,
            row["pnl_pct"],
            ltp=stock.ltp,
            hist_vol=None,  # Will be updated below if hist data available
            sector=stock.sector or "Unknown",
            pe_ratio=stock.pe_ratio,
        )
        expected_signals: dict[str, PortfolioExpectedSignal] = {}
        for horizon, hr in expected_ranges.items():
            max_expected_price = round(stock.ltp * (1 + (hr.upside_pct / 100)), 2)
            min_expected_price = round(stock.ltp * (1 + (hr.downside_pct / 100)), 2)
            delta_amount = max_expected_price - row["avg_price"]
            delta_pct = (delta_amount / row["avg_price"]) * 100 if row["avg_price"] > 0 else 0.0
            amount_signal = f"{delta_amount:+.2f}"
            percent_signal = f"{delta_pct:+.2f}%"
            expected_signals[horizon] = PortfolioExpectedSignal(
                max_expected_price=max_expected_price,
                min_expected_price=min_expected_price,
                amount_signal=amount_signal,
                percent_signal=percent_signal,
                direction="PROFIT" if delta_amount >= 0 else "LOSS",
            )

        # ── Use research engine verdict ──────────────────────────────────
        allocation_pct = (row["current_value"] / total_current_value) * 100 if total_current_value > 0 else 0.0

        # ── Fetch fundamental cache for richer verdict ────────────────────
        _fund = await _get_fundamental_cached(stock.symbol)
        _piotroski = _fund.get("piotroski_score") if _fund else None
        _beneish = _fund.get("beneish_m_score") if _fund else None
        _hist_vol_val = None
        _rsi_val = None
        _trend_val = None
        _master_snap: dict | None = None

        # ── Fetch hist OHLCV for tech snapshot + master snapshot ──────────
        try:
            _hist_df = await _get_hist_ohlcv(stock.symbol, period="1y")
            if _hist_df is not None and len(_hist_df) >= 20:
                _ts = compute_full_technical_snapshot(stock.symbol, _hist_df, ltp=stock.ltp)
                _hist_vol_val = _ts.get("hist_vol")
                _rsi_val = _ts.get("rsi")
                _trend_val = _ts.get("trend_alignment")
                # Master stock snapshot
                _master_snap = compute_master_stock_snapshot(
                    symbol=stock.symbol,
                    ltp=stock.ltp,
                    hist=_hist_df,
                    sector=stock.sector,
                    market_cap=stock.market_cap,
                    index_memberships=[],  # enriched if available
                )
                # Use volatility-based price bands if hist available
                _hv_bands = compute_realistic_price_bands(
                    ltp=stock.ltp, hist_vol=_hist_vol_val
                )
                if _hv_bands:
                    for hor, band in _hv_bands.items():
                        if hor in expected_signals:
                            expected_signals[hor] = PortfolioExpectedSignal(
                                max_expected_price=band.get("high", expected_signals[hor].max_expected_price),
                                min_expected_price=band.get("low", expected_signals[hor].min_expected_price),
                                amount_signal=expected_signals[hor].amount_signal,
                                percent_signal=expected_signals[hor].percent_signal,
                                direction=expected_signals[hor].direction,
                            )
        except Exception:
            pass

        recommendation, comments = compute_portfolio_verdict(
            pnl_pct=row["pnl_pct"],
            price_zone=price_zone,
            value_flag=value_flag,
            rsi=_rsi_val,
            trend_alignment=_trend_val,
            piotroski=_piotroski,
            beneish=_beneish,
            hist_vol=_hist_vol_val,
            allocation_pct=allocation_pct,
        )

        _altman = _fund.get("altman_z_zone") if _fund else None
        _roic_spread = _fund.get("roic_wacc_spread") if _fund else None
        if _altman == "DISTRESS" and "Exit or avoid" not in " ".join(comments):
            comments.append(f"Altman Z-Score in DISTRESS zone — review solvency risk")
        if _roic_spread is not None and _roic_spread < -3:
            comments.append(f"ROIC < WACC by {abs(_roic_spread):.1f}% — value destructive")

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
                master_snapshot=_master_snap,
                altman_z_zone=_altman,
                roic_wacc_spread=_roic_spread,
                piotroski_score=_piotroski,
                beneish_m_score=_beneish,
            )
        )

    analyses.sort(key=lambda row: row.allocation_pct, reverse=True)

    # ── Portfolio-level risk metrics ──────────────────────────────────────
    holdings_for_risk = [
        {
            "symbol": a.symbol,
            "ltp": a.ltp,
            "current_value": a.ltp * a.quantity if a.ltp and a.quantity else 0,
            "pnl_pct": a.pnl_pct,
            "sector": a.sector or "Unknown",
            "market_cap": a.market_cap,
            "hist_vol": 0.30,
        }
        for a in analyses
    ]
    portfolio_risk = compute_portfolio_risk_metrics(holdings=holdings_for_risk)

    # ── Batch 4: Enhanced portfolio analytics ────────────────────────────────
    # Stress tests
    stress_tests = compute_portfolio_stress_tests(holdings=holdings_for_risk)

    # Diversification audit
    div_audit = compute_diversification_audit(holdings=holdings_for_risk)

    # Correlation matrix (from historical returns — 90 day window)
    returns_dict: dict[str, list[float]] = {}
    for a in analyses[:15]:  # cap at 15 to limit API calls
        try:
            hist_c = await _get_hist_ohlcv(a.symbol, period="3mo")
            if hist_c is not None and len(hist_c) >= 20:
                rets = hist_c["Close"].pct_change().dropna().tolist()
                returns_dict[a.symbol] = rets
        except Exception:
            pass
    corr_matrix = compute_portfolio_correlation_matrix(returns_dict)

    # Upcoming catalysts (next 15 days)
    catalyst_data = compute_upcoming_catalysts(
        symbols=[a.symbol for a in analyses],
        days_window=15,
    )

    # Merge metadata into response
    enhanced_risk = {
        **(portfolio_risk if isinstance(portfolio_risk, dict) else portfolio_risk.dict() if hasattr(portfolio_risk, 'dict') else {}),
        "stress_tests": stress_tests,
        "diversification_audit": div_audit,
        "correlation_matrix": corr_matrix,
        "upcoming_catalysts": catalyst_data,
    }

    return PortfolioAnalyzeResponse(
        cost_charged=0.0,
        credits_remaining=0.0,
        parsed_positions_count=len(analyses),
        stocks=analyses,
        failed_symbols=failed_symbols,
        portfolio_risk_metrics=portfolio_risk,
        enhanced_analytics=enhanced_risk,
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


def get_remaining_trading_days(expiry_date_str: str) -> int:
    """Count NSE trading days from today (IST) to expiry date (inclusive)."""
    from datetime import date as _date
    holidays = get_nse_holidays() or NSE_HOLIDAYS
    today = datetime.now(IST).date()
    try:
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    except ValueError:
        return 0

    if expiry_date < today:
        return 0

    count = 0
    # Check if today is still a valid trading session
    now_ist = datetime.now(IST)
    market_still_open_today = (now_ist.hour < 15) or (now_ist.hour == 15 and now_ist.minute < 30)
    d = today
    if market_still_open_today and d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
        if d <= expiry_date:
            count += 1

    d = today + timedelta(days=1)
    while d <= expiry_date:
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
            count += 1
        d += timedelta(days=1)

    return count


def get_nth_trading_day_from_today(n: int) -> "datetime.date":
    """Return the calendar date that is exactly N trading days from today (IST)."""
    from datetime import date as _date
    holidays = get_nse_holidays() or NSE_HOLIDAYS
    if n <= 0:
        return datetime.now(IST).date()
    today = datetime.now(IST).date()
    d = today
    count = 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
            count += 1
    return d


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


# ─── India VIX ────────────────────────────────────────────────────────────────

async def _get_india_vix() -> float | None:
    """Fetch India VIX via yfinance with 5-minute cache."""
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = INDIA_VIX_CACHE.get("value")
    cached_ts = INDIA_VIX_CACHE.get("ts", 0.0)
    if cached is not None and (now_ts - cached_ts) < INDIA_VIX_CACHE_TTL_SECONDS:
        return float(cached)

    def _fetch_vix() -> float | None:
        try:
            import yfinance as yf
            ticker = yf.Ticker("^NSEINDVIX")
            hist = ticker.history(period="1d")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
            info = ticker.info or {}
            val = info.get("regularMarketPrice") or info.get("previousClose")
            return float(val) if val else None
        except Exception as exc:
            logger.warning("India VIX fetch failed: %s", exc)
            return None

    try:
        vix = await asyncio.wait_for(asyncio.to_thread(_fetch_vix), timeout=8.0)
    except Exception:
        vix = None

    if vix is not None:
        INDIA_VIX_CACHE["value"] = vix
        INDIA_VIX_CACHE["ts"] = now_ts
    return vix


# ─── yfinance Fundamental Data ────────────────────────────────────────────────

def _compute_piotroski_score_from_data(info: dict, fin: object, bs: object, cf: object) -> int:
    """
    Compute simplified Piotroski F-score (0-9) from yfinance data.
    Returns integer score. Higher = better quality.
    """
    import pandas as pd
    score = 0
    try:
        # 1. ROA > 0
        roa = info.get("returnOnAssets")
        if roa is not None and float(roa) > 0:
            score += 1

        # 2. Operating cash flow > 0
        if cf is not None and not cf.empty:
            ocf_row = None
            for lbl in ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash From Operations"]:
                if lbl in cf.index:
                    ocf_row = cf.loc[lbl]
                    break
            if ocf_row is not None and len(ocf_row) > 0:
                if float(ocf_row.iloc[0]) > 0:
                    score += 1

        # 3. ROA change YoY > 0
        if bs is not None and not bs.empty and fin is not None and not fin.empty:
            net_income_row = None
            total_assets_row = None
            for lbl in ["Net Income", "Net Income Applicable To Common Shares", "Net Income From Continuing Ops"]:
                if lbl in fin.index:
                    net_income_row = fin.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    total_assets_row = bs.loc[lbl]
                    break
            if net_income_row is not None and total_assets_row is not None and len(net_income_row) >= 2:
                ta_0 = float(total_assets_row.iloc[0]) if len(total_assets_row) > 0 else 1
                ta_1 = float(total_assets_row.iloc[1]) if len(total_assets_row) > 1 else ta_0
                roa_0 = float(net_income_row.iloc[0]) / max(ta_0, 1)
                roa_1 = float(net_income_row.iloc[1]) / max(ta_1, 1)
                if roa_0 > roa_1:
                    score += 1

        # 4. Cash flow > ROA (accruals)
        if cf is not None and not cf.empty and bs is not None and not bs.empty:
            ocf_row = None
            total_assets_row = None
            net_income_row = None
            for lbl in ["Operating Cash Flow", "Total Cash From Operating Activities"]:
                if lbl in cf.index:
                    ocf_row = cf.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    total_assets_row = bs.loc[lbl]
                    break
            for lbl in ["Net Income", "Net Income Applicable To Common Shares"]:
                if lbl in fin.index:
                    net_income_row = fin.loc[lbl]
                    break
            if ocf_row is not None and total_assets_row is not None and net_income_row is not None:
                ta = float(total_assets_row.iloc[0]) if len(total_assets_row) > 0 else 1
                ocf = float(ocf_row.iloc[0]) if len(ocf_row) > 0 else 0
                ni = float(net_income_row.iloc[0]) if len(net_income_row) > 0 else 0
                if (ocf / max(ta, 1)) > (ni / max(ta, 1)):
                    score += 1

        # 5. Leverage decrease (long-term debt)
        if bs is not None and not bs.empty:
            ltd_row = None
            ta_row = None
            for lbl in ["Long Term Debt", "LongTermDebt", "Long-Term Debt"]:
                if lbl in bs.index:
                    ltd_row = bs.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    ta_row = bs.loc[lbl]
                    break
            if ltd_row is not None and ta_row is not None and len(ltd_row) >= 2:
                lev_0 = float(ltd_row.iloc[0]) / max(float(ta_row.iloc[0]), 1)
                lev_1 = float(ltd_row.iloc[1]) / max(float(ta_row.iloc[1]) if len(ta_row) > 1 else float(ta_row.iloc[0]), 1)
                if lev_0 < lev_1:
                    score += 1

        # 6. Current ratio improvement
        cr = info.get("currentRatio")
        if cr is not None and float(cr) > 1.0:
            score += 1

        # 7. No new shares issued (proxy: shares outstanding not increased)
        shares = info.get("sharesOutstanding")
        float_shares = info.get("floatShares")
        if shares and float_shares and float(float_shares) <= float(shares) * 1.02:
            score += 1

        # 8. Gross margin > 0
        gm = info.get("grossMargins")
        if gm is not None and float(gm) > 0:
            score += 1

        # 9. Asset turnover: proxy via revenue / total assets
        if fin is not None and not fin.empty and bs is not None and not bs.empty:
            rev_row = None
            ta_row = None
            for lbl in ["Total Revenue", "Revenue"]:
                if lbl in fin.index:
                    rev_row = fin.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    ta_row = bs.loc[lbl]
                    break
            if rev_row is not None and ta_row is not None and len(rev_row) >= 2:
                at_0 = float(rev_row.iloc[0]) / max(float(ta_row.iloc[0]), 1)
                at_1 = float(rev_row.iloc[1]) / max(float(ta_row.iloc[1]) if len(ta_row) > 1 else float(ta_row.iloc[0]), 1)
                if at_0 > at_1:
                    score += 1
    except Exception as exc:
        logger.debug("Piotroski score error: %s", exc)
    return score


def _compute_beneish_m_score_from_data(fin: object, bs: object) -> float | None:
    """
    Compute simplified Beneish M-score from yfinance data.
    M-score > -2.22 suggests potential earnings manipulation.
    """
    try:
        if fin is None or bs is None or fin.empty or bs.empty:
            return None
        if len(fin.columns) < 2:
            return None

        def _get(df, labels):
            import math
            for lbl in labels:
                if lbl in df.index:
                    row = df.loc[lbl]
                    v0_raw = float(row.iloc[0]) if len(row) > 0 else 0
                    v1_raw = float(row.iloc[1]) if len(row) > 1 else v0_raw
                    # Sanitize NaN/Inf from pandas
                    v0 = 0.0 if (math.isnan(v0_raw) or math.isinf(v0_raw)) else v0_raw
                    v1 = 0.0 if (math.isnan(v1_raw) or math.isinf(v1_raw)) else v1_raw
                    return v0, v1
            return None, None

        rev_0, rev_1 = _get(fin, ["Total Revenue", "Revenue"])
        cogs_0, cogs_1 = _get(fin, ["Cost Of Revenue", "Cost of Goods Sold", "Cost Of Goods Sold"])
        ni_0, ni_1 = _get(fin, ["Net Income", "Net Income Applicable To Common Shares"])
        sga_0, sga_1 = _get(fin, ["Selling General Administrative", "Selling General And Administration"])
        ta_0, ta_1 = _get(bs, ["Total Assets"])
        ca_0, ca_1 = _get(bs, ["Total Current Assets", "Current Assets"])
        cl_0, cl_1 = _get(bs, ["Total Current Liabilities", "Current Liabilities"])
        ar_0, ar_1 = _get(bs, ["Net Receivables", "Accounts Receivable"])
        ppe_0, ppe_1 = _get(bs, ["Net PPE", "Property Plant Equipment Net", "Property Plant And Equipment Net"])
        dep_0, dep_1 = _get(fin, ["Depreciation", "Depreciation And Amortization"])
        ltd_0, ltd_1 = _get(bs, ["Long Term Debt"])

        if not all([rev_0, rev_1, ta_0, ta_1]):
            return None

        # DSRI: Days Sales Receivable Index
        ar_0 = ar_0 or 0
        ar_1 = ar_1 or 0
        dsri = (ar_0 / max(rev_0, 1)) / max(ar_1 / max(rev_1, 1), 0.001) if rev_1 and ar_1 else 1.0

        # GMI: Gross Margin Index
        gm_0 = (rev_0 - (cogs_0 or 0)) / max(rev_0, 1)
        gm_1 = (rev_1 - (cogs_1 or 0)) / max(rev_1, 1)
        gmi = gm_1 / max(gm_0, 0.001) if gm_0 else 1.0

        # AQI: Asset Quality Index
        ca_0 = ca_0 or ta_0 * 0.3
        ca_1 = ca_1 or ta_1 * 0.3
        ppe_0 = ppe_0 or ta_0 * 0.3
        ppe_1 = ppe_1 or ta_1 * 0.3
        aq_0 = 1 - (ca_0 + ppe_0) / max(ta_0, 1)
        aq_1 = 1 - (ca_1 + ppe_1) / max(ta_1, 1)
        aqi = aq_0 / max(aq_1, 0.001)

        # SGI: Sales Growth Index
        sgi = rev_0 / max(rev_1, 1)

        # DEPI: Depreciation Index
        dep_0 = dep_0 or 0
        dep_1 = dep_1 or 0
        depi_0 = dep_0 / max(dep_0 + ppe_0, 1)
        depi_1 = dep_1 / max(dep_1 + ppe_1, 1)
        depi = depi_1 / max(depi_0, 0.001) if depi_0 else 1.0

        # SGAI: SGA Index
        sga_0 = sga_0 or rev_0 * 0.1
        sga_1 = sga_1 or rev_1 * 0.1
        sgai_0 = sga_0 / max(rev_0, 1)
        sgai_1 = sga_1 / max(rev_1, 1)
        sgai = sgai_0 / max(sgai_1, 0.001)

        # LVGI: Leverage Index
        ltd_0 = ltd_0 or 0
        ltd_1 = ltd_1 or 0
        cl_0 = cl_0 or ta_0 * 0.2
        cl_1 = cl_1 or ta_1 * 0.2
        lev_0 = (ltd_0 + cl_0) / max(ta_0, 1)
        lev_1 = (ltd_1 + cl_1) / max(ta_1, 1)
        lvgi = lev_0 / max(lev_1, 0.001)

        # TATA: Total Accruals to Total Assets (proxy)
        ni_0 = ni_0 or 0
        tata = (ni_0 - (dep_0 or 0)) / max(ta_0, 1)

        m_score = (
            -4.84
            + 0.92 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )
        result = round(float(m_score), 3)
        import math
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception as exc:
        logger.debug("Beneish M-score error: %s", exc)
        return None


def _fetch_yfinance_fundamentals(symbol: str) -> dict:
    """Synchronous yfinance fetch (run in async thread)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info or {}

        roe = info.get("returnOnEquity")
        if roe is not None:
            roe = _sanitize_float(round(float(roe) * 100, 2))

        # ROCE = EBIT / Capital Employed
        roce = None
        fin, bs, cf = None, None, None
        try:
            fin = ticker.financials
            bs = ticker.balance_sheet
            cf = ticker.cashflow
            if fin is not None and bs is not None and not fin.empty and not bs.empty:
                ebit = None
                ta = None
                cl = None
                for lbl in ["Operating Income", "EBIT", "Ebit"]:
                    if lbl in fin.index:
                        ebit = float(fin.loc[lbl].iloc[0])
                        break
                for lbl in ["Total Assets"]:
                    if lbl in bs.index:
                        ta = float(bs.loc[lbl].iloc[0])
                        break
                for lbl in ["Total Current Liabilities", "Current Liabilities"]:
                    if lbl in bs.index:
                        cl = float(bs.loc[lbl].iloc[0])
                        break
                if ebit is not None and ta is not None and cl is not None:
                    cap_emp = ta - cl
                    if cap_emp > 0:
                        roce = round((ebit / cap_emp) * 100, 2)
        except Exception:
            fin, bs, cf = None, None, None

        eps_growth = None
        try:
            trailing_eps = info.get("trailingEps")
            forward_eps = info.get("forwardEps")
            if trailing_eps and forward_eps and float(trailing_eps) > 0:
                eps_growth = round(((float(forward_eps) - float(trailing_eps)) / abs(float(trailing_eps))) * 100, 2)
        except Exception:
            pass

        piotroski = None
        beneish = None
        try:
            if fin is not None and bs is not None and not fin.empty and not bs.empty:
                piotroski = _compute_piotroski_score_from_data(info, fin, bs, cf)
                beneish = _compute_beneish_m_score_from_data(fin, bs)
        except Exception:
            pass

        gross_margin = info.get("grossMargins")
        if gross_margin is not None:
            gross_margin = _sanitize_float(round(float(gross_margin) * 100, 2))

        # ── New: Total Debt / Market Cap ratio ──────────────────────────────
        total_debt_to_market_cap = None
        try:
            total_debt = _to_float(info.get("totalDebt"))
            market_cap_raw = _to_float(info.get("marketCap"))
            if total_debt is not None and market_cap_raw is not None and market_cap_raw > 0:
                total_debt_to_market_cap = _sanitize_float(round(total_debt / market_cap_raw, 4))
        except Exception:
            pass

        # ── New: Net profit positive in last 3 quarters ─────────────────────
        recent_profit_positive = None
        try:
            q_fin = ticker.quarterly_financials
            if q_fin is not None and not q_fin.empty:
                net_income_labels = ["Net Income", "Net Income From Continuing Operations", "NetIncome"]
                for lbl in net_income_labels:
                    if lbl in q_fin.index:
                        recent_3q = q_fin.loc[lbl].iloc[:3].tolist()
                        recent_profit_positive = any(v > 0 for v in recent_3q if v is not None and str(v) != "nan")
                        break
        except Exception:
            recent_profit_positive = None

        # ── New: Revenue CAGR (3-year) ──────────────────────────────────────
        revenue_cagr_3y = None
        try:
            if fin is not None and not fin.empty:
                rev_labels = ["Total Revenue", "Revenue", "Operating Revenue"]
                for lbl in rev_labels:
                    if lbl in fin.index:
                        rev_series = fin.loc[lbl].dropna()
                        if len(rev_series) >= 3:
                            oldest = float(rev_series.iloc[-1])
                            newest = float(rev_series.iloc[0])
                            n = len(rev_series) - 1
                            if oldest > 0 and newest > 0 and n > 0:
                                revenue_cagr_3y = _sanitize_float(round(((newest / oldest) ** (1 / n) - 1) * 100, 2))
                        break
        except Exception:
            pass

        # ── New: FCF Yield ──────────────────────────────────────────────────
        fcf_yield = None
        try:
            free_cashflow = _to_float(info.get("freeCashflow"))
            market_cap_raw2 = _to_float(info.get("marketCap"))
            if free_cashflow is not None and market_cap_raw2 is not None and market_cap_raw2 > 0:
                fcf_yield = _sanitize_float(round((free_cashflow / market_cap_raw2) * 100, 2))
        except Exception:
            pass

        # ── Batch 2: Altman Z-Score ─────────────────────────────────────────
        altman_z_result: dict = {}
        try:
            if bs is not None and not bs.empty and fin is not None and not fin.empty:
                def _b2_get(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None

                ta_z = _b2_get(bs, ["Total Assets"])
                ca_z = _b2_get(bs, ["Total Current Assets", "Current Assets"])
                cl_z = _b2_get(bs, ["Total Current Liabilities", "Current Liabilities"])
                re_z = _b2_get(bs, ["Retained Earnings", "Retained Earnings (Deficit)"])
                tl_z = _b2_get(bs, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
                rev_z = _b2_get(fin, ["Total Revenue", "Revenue"])
                ebit_z = _b2_get(fin, ["Operating Income", "EBIT", "Ebit"])
                mc_z = _to_float(info.get("marketCap"))

                wc_z = (ca_z - cl_z) if (ca_z is not None and cl_z is not None) else None

                if all(v is not None for v in [ta_z, rev_z, ebit_z, mc_z, tl_z]) and ta_z > 0 and tl_z > 0:
                    altman_z_result = compute_altman_z_score(
                        working_capital=wc_z,
                        retained_earnings=re_z,
                        ebit=ebit_z,
                        market_cap=mc_z,
                        total_liabilities=tl_z,
                        revenue=rev_z,
                        total_assets=ta_z,
                    )
        except Exception as exc:
            logger.debug("Altman Z error for %s: %s", symbol, exc)

        # ── Batch 2: Earnings Quality (CFO/NI ratio, Accrual Ratio) ─────────
        earnings_quality_result: dict = {}
        try:
            if cf is not None and not cf.empty and fin is not None and not fin.empty:
                def _cf_get(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None

                ocf_eq = _cf_get(cf, ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash From Operations"])
                ni_eq = _cf_get(fin, ["Net Income", "Net Income Applicable To Common Shares"])
                ta_eq = _b2_get(bs, ["Total Assets"]) if bs is not None and not bs.empty else None

                if ocf_eq is not None and ni_eq is not None:
                    earnings_quality_result = compute_earnings_quality(
                        operating_cash_flow=ocf_eq,
                        net_income=ni_eq,
                        total_assets=ta_eq,
                    )
        except Exception as exc:
            logger.debug("Earnings quality error for %s: %s", symbol, exc)

        # ── Batch 2: ROIC vs WACC ───────────────────────────────────────────
        roic_result: dict = {}
        try:
            if fin is not None and not fin.empty and bs is not None and not bs.empty:
                def _rv_get(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None

                ebit_rv = _rv_get(fin, ["Operating Income", "EBIT", "Ebit"])
                ta_rv = _rv_get(bs, ["Total Assets"])
                cl_rv = _rv_get(bs, ["Total Current Liabilities", "Current Liabilities"])
                td_rv = _to_float(info.get("totalDebt"))
                mc_rv = _to_float(info.get("marketCap"))
                eff_tax = _to_float(info.get("effectiveTaxRate")) or 0.25

                if ebit_rv is not None:
                    ic_rv = (ta_rv - cl_rv) if (ta_rv is not None and cl_rv is not None) else None
                    roic_result = compute_roic_vs_wacc(
                        ebit=ebit_rv,
                        tax_rate=min(max(float(eff_tax), 0.15), 0.40),
                        invested_capital=ic_rv,
                        total_assets=ta_rv,
                        current_liabilities=cl_rv,
                        total_debt=td_rv,
                        market_cap=mc_rv,
                    )
        except Exception as exc:
            logger.debug("ROIC vs WACC error for %s: %s", symbol, exc)

        # ── Batch 2: Growth Quality (EBITDA margin trend) ───────────────────
        growth_quality_result: dict = {}
        try:
            if fin is not None and not fin.empty:
                def _gq_get_series(df, labels, n=4):
                    for lbl in labels:
                        if lbl in df.index:
                            return [float(v) if str(v) != "nan" else None for v in df.loc[lbl].iloc[:n].tolist()]
                    return []

                rev_list = _gq_get_series(fin, ["Total Revenue", "Revenue"])
                ebit_list = _gq_get_series(fin, ["Operating Income", "EBIT", "Ebit"])
                rev_list2 = _gq_get_series(fin, ["Total Revenue", "Revenue"])
                ebitda_margins = []
                if rev_list and ebit_list:
                    for r, e in zip(rev_list, ebit_list):
                        if r and r > 0 and e is not None:
                            ebitda_margins.append(round(e / r * 100, 2))
                        else:
                            ebitda_margins.append(None)

                if rev_list:
                    growth_quality_result = compute_growth_quality(
                        revenues=rev_list,
                        ebitda_margins=ebitda_margins,
                        fcf_yield=fcf_yield,
                    )
        except Exception as exc:
            logger.debug("Growth quality error for %s: %s", symbol, exc)

        return {
            "roe": _sanitize_float(roe),
            "roce": _sanitize_float(roce),
            "piotroski_score": piotroski,
            "beneish_m_score": _sanitize_float(beneish),
            "eps_growth_pct": _sanitize_float(eps_growth),
            "gross_margin": _sanitize_float(gross_margin),
            "debt_to_equity": _sanitize_float(info.get("debtToEquity")),
            "current_ratio": _sanitize_float(info.get("currentRatio")),
            "total_debt_to_market_cap": total_debt_to_market_cap,
            "recent_profit_positive": recent_profit_positive,
            "revenue_cagr_3y": revenue_cagr_3y,
            "fcf_yield": fcf_yield,
            # Batch 2 additions
            "altman_z": altman_z_result if altman_z_result.get("available") else None,
            "altman_z_score": altman_z_result.get("z_score") if altman_z_result.get("available") else None,
            "altman_z_zone": altman_z_result.get("zone") if altman_z_result.get("available") else None,
            "earnings_quality": earnings_quality_result if earnings_quality_result.get("available") else None,
            "cfo_ni_ratio": earnings_quality_result.get("cfo_ni_ratio"),
            "accrual_ratio": earnings_quality_result.get("accrual_ratio"),
            "roic_vs_wacc": roic_result if roic_result.get("available") else None,
            "roic": roic_result.get("roic"),
            "wacc": roic_result.get("wacc"),
            "roic_wacc_spread": roic_result.get("spread"),
            "growth_quality": growth_quality_result if growth_quality_result.get("available") else None,
            "ebitda_margin_latest": growth_quality_result.get("ebitda_margin_latest"),
            "ebitda_margin_trend": growth_quality_result.get("ebitda_margin_trend"),
        }
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return {}


async def _get_fundamental_data(symbol: str) -> dict:
    """Fetch fundamental data via yfinance with MongoDB + in-memory cache (24h TTL)."""
    now_ts = datetime.now(timezone.utc).timestamp()

    # In-memory cache
    if symbol in FUNDAMENTAL_CACHE:
        cached = FUNDAMENTAL_CACHE[symbol]
        if (now_ts - cached.get("_ts", 0)) < FUNDAMENTAL_CACHE_TTL_SECONDS:
            return cached

    # MongoDB cache
    try:
        cached_doc = await db.fundamental_cache.find_one({"symbol": symbol}, {"_id": 0})
        if cached_doc:
            cached_at = cached_doc.get("cached_at_ts", 0)
            if (now_ts - float(cached_at or 0)) < FUNDAMENTAL_CACHE_TTL_SECONDS:
                cached_doc["_ts"] = float(cached_at or now_ts)
                FUNDAMENTAL_CACHE[symbol] = cached_doc
                return cached_doc
    except Exception:
        pass

    # Fetch from yfinance
    try:
        data = await asyncio.wait_for(asyncio.to_thread(_fetch_yfinance_fundamentals, symbol), timeout=15.0)
    except Exception:
        data = {}

    result = {
        "symbol": symbol,
        "roe": data.get("roe"),
        "roce": data.get("roce"),
        "piotroski_score": data.get("piotroski_score"),
        "beneish_m_score": data.get("beneish_m_score"),
        "eps_growth_pct": data.get("eps_growth_pct"),
        "gross_margin": data.get("gross_margin"),
        "debt_to_equity": data.get("debt_to_equity"),
        "current_ratio": data.get("current_ratio"),
        "total_debt_to_market_cap": data.get("total_debt_to_market_cap"),
        "recent_profit_positive": data.get("recent_profit_positive"),
        "revenue_cagr_3y": data.get("revenue_cagr_3y"),
        "fcf_yield": data.get("fcf_yield"),
        # Batch 2
        "altman_z_score": data.get("altman_z_score"),
        "altman_z_zone": data.get("altman_z_zone"),
        "altman_z": data.get("altman_z"),
        "cfo_ni_ratio": data.get("cfo_ni_ratio"),
        "accrual_ratio": data.get("accrual_ratio"),
        "earnings_quality": data.get("earnings_quality"),
        "roic": data.get("roic"),
        "wacc": data.get("wacc"),
        "roic_wacc_spread": data.get("roic_wacc_spread"),
        "roic_vs_wacc": data.get("roic_vs_wacc"),
        "growth_quality": data.get("growth_quality"),
        "ebitda_margin_latest": data.get("ebitda_margin_latest"),
        "ebitda_margin_trend": data.get("ebitda_margin_trend"),
        "cached_at_ts": now_ts,
        "_ts": now_ts,
    }

    try:
        store_doc = {k: v for k, v in result.items() if k != "_ts"}
        await db.fundamental_cache.update_one(
            {"symbol": symbol},
            {"$set": store_doc},
            upsert=True,
        )
    except Exception:
        pass

    FUNDAMENTAL_CACHE[symbol] = result
    return result


def _fetch_yfinance_hist_ohlcv(symbol: str, period: str = "1y") -> dict | None:
    """Fetch historical OHLCV from yfinance and return as serializable dict."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period=period, auto_adjust=True)
        if hist is None or hist.empty:
            return None
        # Return as JSON-serializable records
        records = []
        for ts, row in hist.iterrows():
            records.append({
                "date": str(ts.date()),
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": int(row.get("Volume", 0)),
            })
        return {"symbol": symbol, "records": records, "count": len(records)}
    except Exception as exc:
        logger.warning("yfinance hist OHLCV failed for %s: %s", symbol, exc)
        return None


async def _get_hist_ohlcv(symbol: str, period: str = "1y"):
    """
    Get historical OHLCV as pandas DataFrame with 6h in-memory cache and 12h MongoDB cache.
    Returns pd.DataFrame or None.
    """
    import pandas as pd
    now_ts = datetime.now(timezone.utc).timestamp()
    cache_key = f"{symbol}_{period}"

    # In-memory cache
    if cache_key in HIST_OHLCV_CACHE:
        cached = HIST_OHLCV_CACHE[cache_key]
        if (now_ts - cached.get("_ts", 0)) < HIST_OHLCV_CACHE_TTL_SECONDS:
            records = cached.get("records", [])
            if records:
                df = pd.DataFrame(records)
                df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                   "close": "Close", "volume": "Volume"}, inplace=True)
                return df

    # MongoDB cache (12h)
    try:
        cached_doc = await db.hist_ohlcv_cache.find_one({"symbol": symbol, "period": period}, {"_id": 0})
        if cached_doc and (now_ts - float(cached_doc.get("cached_at_ts", 0))) < 43200:
            records = cached_doc.get("records", [])
            if records:
                HIST_OHLCV_CACHE[cache_key] = {"records": records, "_ts": now_ts}
                df = pd.DataFrame(records)
                df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                   "close": "Close", "volume": "Volume"}, inplace=True)
                return df
    except Exception:
        pass

    # Fetch from yfinance
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_fetch_yfinance_hist_ohlcv, symbol, period), timeout=20.0)
    except Exception:
        raw = None

    if not raw or not raw.get("records"):
        return None

    # Store in caches
    HIST_OHLCV_CACHE[cache_key] = {"records": raw["records"], "_ts": now_ts}
    try:
        await db.hist_ohlcv_cache.update_one(
            {"symbol": symbol, "period": period},
            {"$set": {"symbol": symbol, "period": period, "records": raw["records"],
                      "cached_at_ts": now_ts, "updated_at": _utc_now_iso()}},
            upsert=True,
        )
    except Exception:
        pass

    df = pd.DataFrame(raw["records"])
    df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                       "close": "Close", "volume": "Volume"}, inplace=True)
    return df


def compute_multibagger_analysis(stock: StockCoreNormalized, fundamental: dict | None = None) -> dict:
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

    # Use historical volatility from fundamental data if available
    hist_vol = fundamental.get("hist_vol") if fundamental else None

    # Compute volatility-based realistic price bands
    vol_bands = compute_realistic_price_bands(
        ltp=float(ltp),
        hist_vol=hist_vol,
        sector=getattr(stock, "sector", "Unknown") if hasattr(stock, "sector") else "Unknown",
        pe_ratio=pe,
    ) if ltp is not None else {}

    for key, base in duration_base.items():
        if ltp is None:
            targeted_upside_price[key] = None
            targeted_upside_profit_pct[key] = None
            continue

        # Use volatility-based expected high if available, else fall back to scoring-based
        if vol_bands and key in vol_bands:
            # Expected upside from vol-based band
            exp_upside_pct = vol_bands[key].get("upside_pct", 0) / 100
            growth = max(exp_upside_pct, 0.005)
        else:
            growth = base + momentum_adj
            if upside_to_52w_high_pct is not None and upside_to_52w_high_pct > 0:
                growth = min(growth, (upside_to_52w_high_pct / 100) * 1.25)
            growth = max(growth, 0.005)

        target_price = round(ltp * (1 + growth), 2)
        roi_pct = round(((target_price - ltp) / ltp) * 100, 2)

        targeted_upside_price[key] = target_price
        targeted_upside_profit_pct[key] = roi_pct

    thesis_parts = []

    # Score summary
    if final_score >= 80:
        thesis_parts.append(f"Strong multibagger profile (Score: {final_score}/100, {tier_pass_count}/7 tiers passed)")
    elif final_score >= 70:
        thesis_parts.append(f"Balanced quality-growth setup (Score: {final_score}/100, {tier_pass_count}/7 tiers passed)")
    else:
        thesis_parts.append(f"Developing setup needing confirmation (Score: {final_score}/100, {tier_pass_count}/7 tiers passed)")

    # Valuation
    if pe is not None and ltp is not None:
        if pe < 15:
            thesis_parts.append(f"Attractively valued at P/E {round(pe, 1)}x (undervalued territory)")
        elif pe < 25:
            thesis_parts.append(f"Fairly valued at P/E {round(pe, 1)}x")
        else:
            thesis_parts.append(f"Premium P/E {round(pe, 1)}x — growth premium required")

    if pb_ratio_est is not None:
        if pb_ratio_est < 2.0:
            thesis_parts.append(f"Trades at P/B {round(pb_ratio_est, 2)}x — below book, possible margin-of-safety")
        else:
            thesis_parts.append(f"P/B {round(pb_ratio_est, 2)}x")

    # Upside
    if upside_to_52w_high_pct is not None and upside_to_52w_high_pct > 0:
        thesis_parts.append(f"Potential upside to 52W high: {round(upside_to_52w_high_pct, 1)}%")

    # Fundamental overlays
    if fundamental:
        roe_val = fundamental.get("roe")
        roce_val = fundamental.get("roce")
        piotroski = fundamental.get("piotroski_score")
        beneish = fundamental.get("beneish_m_score")
        eps_g = fundamental.get("eps_growth_pct")
        de = fundamental.get("debt_to_equity")

        if roe_val is not None:
            if roe_val >= 20:
                thesis_parts.append(f"High ROE {roe_val}% — efficient capital use")
            elif roe_val >= 12:
                thesis_parts.append(f"Adequate ROE {roe_val}%")
            else:
                thesis_parts.append(f"Low ROE {roe_val}% — profitability concern")

        if roce_val is not None:
            if roce_val >= 15:
                thesis_parts.append(f"Strong ROCE {roce_val}%")
            else:
                thesis_parts.append(f"ROCE {roce_val}%")

        if piotroski is not None:
            if piotroski >= 7:
                thesis_parts.append(f"Piotroski F-Score {piotroski}/9 — high quality financials")
            elif piotroski >= 5:
                thesis_parts.append(f"Piotroski F-Score {piotroski}/9 — decent quality")
            else:
                thesis_parts.append(f"Piotroski F-Score {piotroski}/9 — review financials carefully")

        if beneish is not None:
            if beneish > -2.22:
                thesis_parts.append(f"Beneish M-Score {beneish} — potential earnings manipulation risk")
            else:
                thesis_parts.append(f"Beneish M-Score {beneish} — clean earnings quality")

        if eps_g is not None:
            thesis_parts.append(f"Expected EPS growth: {eps_g}%")

        if de is not None:
            if de < 0.5:
                thesis_parts.append(f"Low leverage (D/E {round(de, 2)}) — strong balance sheet")
            elif de < 1.5:
                thesis_parts.append(f"Moderate leverage (D/E {round(de, 2)})")
            else:
                thesis_parts.append(f"High leverage (D/E {round(de, 2)}) — watch debt servicing")

        # ── New fundamental fields ───────────────────────────────────────
        revenue_cagr = fundamental.get("revenue_cagr_3y")
        fcf_yield_val = fundamental.get("fcf_yield")
        debt_to_mktcap = fundamental.get("total_debt_to_market_cap")
        recent_profitable = fundamental.get("recent_profit_positive")

        if revenue_cagr is not None:
            if revenue_cagr >= 20:
                thesis_parts.append(f"Strong revenue CAGR {revenue_cagr:.1f}% (3Y)")
            elif revenue_cagr >= 10:
                thesis_parts.append(f"Healthy revenue CAGR {revenue_cagr:.1f}% (3Y)")
            elif revenue_cagr < 0:
                thesis_parts.append(f"Revenue decline {revenue_cagr:.1f}% CAGR — monitor closely")

        if fcf_yield_val is not None:
            if fcf_yield_val > 5:
                thesis_parts.append(f"Strong FCF yield {fcf_yield_val:.1f}% — cash generative business")
            elif fcf_yield_val < 0:
                thesis_parts.append(f"Negative FCF yield {fcf_yield_val:.1f}% — cash burn concern")

        if debt_to_mktcap is not None and debt_to_mktcap >= 0.20:
            thesis_parts.append(f"Debt {debt_to_mktcap*100:.0f}% of market cap — watch leverage")

        if recent_profitable is False:
            thesis_parts.append("No profitable quarter in last 3Q — revenue recovery needed")

        # ── Batch 2: Altman Z, ROIC vs WACC, Earnings Quality ───────────────
        altman_z_s = fundamental.get("altman_z_score")
        altman_z_zone = fundamental.get("altman_z_zone")
        roic_val = fundamental.get("roic")
        wacc_val = fundamental.get("wacc")
        roic_spread = fundamental.get("roic_wacc_spread")
        cfo_ni = fundamental.get("cfo_ni_ratio")
        ebitda_trend = fundamental.get("ebitda_margin_trend")

        if altman_z_zone is not None:
            if altman_z_zone == "SAFE":
                thesis_parts.append(f"Altman Z={altman_z_s:.2f} — financially sound")
            elif altman_z_zone == "GREY":
                thesis_parts.append(f"Altman Z={altman_z_s:.2f} — grey zone; watch leverage")
            else:
                thesis_parts.append(f"Altman Z={altman_z_s:.2f} — DISTRESS zone (red flag)")

        if roic_spread is not None:
            if roic_spread > 3:
                thesis_parts.append(f"ROIC {roic_val:.1f}% > WACC {wacc_val:.1f}% — value creating (+{roic_spread:.1f}%)")
            elif roic_spread < -3:
                thesis_parts.append(f"ROIC {roic_val:.1f}% < WACC {wacc_val:.1f}% — value destroying ({roic_spread:.1f}%)")

        if cfo_ni is not None:
            if cfo_ni < 0.5:
                thesis_parts.append(f"CFO/NI={cfo_ni:.2f} — low earnings quality (accrual-heavy)")
            elif cfo_ni >= 1.0:
                thesis_parts.append(f"CFO/NI={cfo_ni:.2f} — high earnings quality")

        if ebitda_trend == "DETERIORATING":
            thesis_parts.append("EBITDA margin deteriorating — margin compression risk")

        # ── Batch 4: Macro Context for Multibagger ────────────────────────
        try:
            _mb_sector = fundamental.get("sector") if fundamental else None
            _mb_macro = compute_macro_context(
                active_events=[],
                vix=None,   # VIX not available in sync context; regime will use UNKNOWN
                sector=_mb_sector,
            )
            _mb_bias = _mb_macro.get("macro_bias", "NEUTRAL")
            if _mb_bias == "TAILWIND":
                thesis_parts.append(f"Sector '{_mb_sector}' has macro tailwind — favorable environment")
            elif _mb_bias == "HEADWIND":
                thesis_parts.append(f"Sector '{_mb_sector}' facing macro headwind — risk factor")
        except Exception:
            _mb_macro = {}
            _mb_bias = "NEUTRAL"

    # Tier breakdown
    passed_tiers = [k for k, threshold in tier_thresholds.items() if tier_scores.get(k, 0) >= threshold]
    if passed_tiers:
        tier_labels = {
            "tier_1": "Valuation", "tier_2": "Profitability", "tier_3": "Growth",
            "tier_4": "Balance Sheet", "tier_5": "Momentum", "tier_6": "Sector Tailwind", "tier_7": "Technical",
        }
        passed_names = [tier_labels.get(t, t) for t in passed_tiers]
        thesis_parts.append(f"Passing tiers: {', '.join(passed_names)}")

    if peg_ratio_est is not None:
        thesis_parts.append(f"PEG proxy: {round(peg_ratio_est, 2)}")

    thesis = " | ".join(thesis_parts)

    # Extract fundamental fields for direct model return
    roe_ret = fundamental.get("roe") if fundamental else None
    roce_ret = fundamental.get("roce") if fundamental else None
    piotroski_ret = fundamental.get("piotroski_score") if fundamental else None
    beneish_ret = fundamental.get("beneish_m_score") if fundamental else None
    eps_growth_ret = fundamental.get("eps_growth_pct") if fundamental else None
    de_ret = fundamental.get("debt_to_equity") if fundamental else None
    cr_ret = fundamental.get("current_ratio") if fundamental else None
    gm_ret = fundamental.get("gross_margin") if fundamental else None

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
        "roe": roe_ret,
        "roce": roce_ret,
        "piotroski_score": piotroski_ret,
        "beneish_m_score": beneish_ret,
        "eps_growth_pct": eps_growth_ret,
        "debt_to_equity": de_ret,
        "current_ratio": cr_ret,
        "gross_margin": gm_ret,
        "revenue_cagr_3y": fundamental.get("revenue_cagr_3y") if fundamental else None,
        "fcf_yield": fundamental.get("fcf_yield") if fundamental else None,
        "total_debt_to_market_cap": fundamental.get("total_debt_to_market_cap") if fundamental else None,
        "recent_profit_positive": fundamental.get("recent_profit_positive") if fundamental else None,
        # Batch 2 forensic
        "altman_z_score": fundamental.get("altman_z_score") if fundamental else None,
        "altman_z_zone": fundamental.get("altman_z_zone") if fundamental else None,
        "roic": fundamental.get("roic") if fundamental else None,
        "wacc": fundamental.get("wacc") if fundamental else None,
        "roic_wacc_spread": fundamental.get("roic_wacc_spread") if fundamental else None,
        "cfo_ni_ratio": fundamental.get("cfo_ni_ratio") if fundamental else None,
        "ebitda_margin_latest": fundamental.get("ebitda_margin_latest") if fundamental else None,
        "ebitda_margin_trend": fundamental.get("ebitda_margin_trend") if fundamental else None,
        "vol_bands": vol_bands,  # volatility-based realistic price bands for all horizons
    }


def _calculate_confluence_score_master_spec(
    stock_core: StockCoreNormalized,
    direction: str,
    bias_score: float,
    risk_reward_target2: float,
    option_ltp: float,
    minutes_to_expiry: int,
    entry_discount_pct: float,
    option_day_high: float | None,
    option_day_low: float | None,
    india_vix: float | None = None,
    pcr: float | None = None,
    strategy: str | None = None,
    # ── New: Technical bonus inputs from research engine ────────────────
    rsi: float | None = None,
    macd_bullish: bool | None = None,
    macd_above_zero: bool | None = None,
    trend_alignment: str | None = None,
    obv_trend: str | None = None,
    adx: float | None = None,
    bb_pct_b: float | None = None,
    stoch_k: float | None = None,
) -> tuple[int, str]:
    """
    Master Spec Confluence Scoring (0-100):
    - TechnicalAlignmentScore (0-30): Bias, direction, R:R, position
    - VolumeScore (0-20): Volume vs average, volume trend
    - BreadthScore (0-10): 52W position, price action
    - PCRScore (0-10): Real PCR if available, else entry-discount proxy
    - VIXScore (0-10): Real India VIX if available, else option volatility proxy
    - GEXScore (0-10): Option price level, liquidity
    - FundamentalQualityScore (0-10): Screener metrics proxy
    - StrategyBonus (0-5): Extra credit for ORB/VWAP alignment
    """
    technical_score = 0
    volume_score = 0
    breadth_score = 0
    pcr_score = 5
    vix_score = 5
    gex_score = 5
    fundamental_score = 0
    strategy_bonus = 0

    # ── Technical Alignment ──────────────────────────────────────────────────
    if abs(bias_score) > 2.0:
        technical_score += 12
    elif abs(bias_score) > 1.0:
        technical_score += 8
    elif abs(bias_score) > 0.3:
        technical_score += 4

    if direction != "NEUTRAL":
        technical_score += 10

    if risk_reward_target2 >= 2.5:
        technical_score += 8
    elif risk_reward_target2 >= 2.0:
        technical_score += 6
    elif risk_reward_target2 >= 1.5:
        technical_score += 4
    elif risk_reward_target2 >= 1.2:
        technical_score += 2

    technical_score = min(technical_score, 30)

    # ── Volume Score ─────────────────────────────────────────────────────────
    if stock_core.volume is not None and stock_core.volume > 0:
        volume_ratio = 1.0
        if hasattr(stock_core, 'avg_volume') and stock_core.avg_volume and stock_core.avg_volume > 0:
            volume_ratio = stock_core.volume / stock_core.avg_volume
        if volume_ratio >= 3.0:
            volume_score = 20
        elif volume_ratio >= 2.0:
            volume_score = 17
        elif volume_ratio >= 1.5:
            volume_score = 14
        elif volume_ratio >= 1.2:
            volume_score = 12
        elif volume_ratio >= 1.0:
            volume_score = 10
        elif volume_ratio >= 0.8:
            volume_score = 7
        else:
            volume_score = 4
    else:
        volume_score = 10

    # ── Breadth Score (52W position) ─────────────────────────────────────────
    ltp = stock_core.ltp
    year_high = stock_core.year_high
    year_low = stock_core.year_low

    if ltp and year_high and year_low and year_high > year_low:
        position = (ltp - year_low) / (year_high - year_low)
        if direction == "BULLISH":
            if position < 0.25:
                breadth_score = 10
            elif position < 0.40:
                breadth_score = 8
            elif position < 0.60:
                breadth_score = 6
            else:
                breadth_score = 3
        elif direction == "BEARISH":
            if position > 0.75:
                breadth_score = 10
            elif position > 0.60:
                breadth_score = 8
            elif position > 0.40:
                breadth_score = 6
            else:
                breadth_score = 3
        else:
            breadth_score = 6 if 0.4 <= position <= 0.6 else 4
    else:
        breadth_score = 5

    # ── VIX Score (real India VIX if available) ──────────────────────────────
    if india_vix is not None:
        # VIX <12: very low vol → options cheap, good for buying
        # VIX 12-18: normal
        # VIX 18-25: elevated volatility → risk exists
        # VIX >25: extreme fear → contrarian opportunity, but risky
        if direction == "BULLISH":
            if 12 <= india_vix <= 18:
                vix_score = 10  # perfect entry window
            elif india_vix < 12:
                vix_score = 7  # low vol, small moves expected
            elif india_vix <= 22:
                vix_score = 8  # slight fear, good for cheap options
            elif india_vix <= 28:
                vix_score = 5  # elevated risk
            else:
                vix_score = 3  # extreme fear — avoid
        elif direction == "BEARISH":
            if india_vix >= 20:
                vix_score = 10  # fear spike, good for PE
            elif india_vix >= 15:
                vix_score = 8
            else:
                vix_score = 5
    elif option_day_high and option_day_low and option_day_low > 0:
        volatility_pct = ((option_day_high - option_day_low) / option_day_low) * 100
        if volatility_pct > 25:
            vix_score = 10
        elif volatility_pct > 15:
            vix_score = 8
        elif volatility_pct > 10:
            vix_score = 6
        elif volatility_pct > 5:
            vix_score = 4
        else:
            vix_score = 2

    # ── PCR Score (real PCR if available) ────────────────────────────────────
    if pcr is not None:
        # PCR < 0.7: bullish (more calls, low fear)
        # PCR 0.7-1.0: neutral
        # PCR 1.0-1.3: slightly bearish
        # PCR > 1.3: extreme bearish (contrarian buy signal for CE)
        if direction == "BULLISH":
            if pcr > 1.3:
                pcr_score = 10  # extreme bearishness = contrarian CE buy
            elif pcr > 1.0:
                pcr_score = 8
            elif 0.7 <= pcr <= 1.0:
                pcr_score = 6
            else:
                pcr_score = 4  # PCR too low, CEs already expensive
        elif direction == "BEARISH":
            if pcr < 0.7:
                pcr_score = 10  # extreme bullishness = contrarian PE buy
            elif pcr < 1.0:
                pcr_score = 8
            else:
                pcr_score = 5
    else:
        # Fallback: entry discount proxy
        if entry_discount_pct >= 6.0:
            pcr_score = 10
        elif entry_discount_pct >= 4.0:
            pcr_score = 9
        elif entry_discount_pct >= 3.0:
            pcr_score = 7
        elif entry_discount_pct >= 2.0:
            pcr_score = 6
        elif entry_discount_pct >= 1.0:
            pcr_score = 4

    # ── GEX / Liquidity Score ─────────────────────────────────────────────────
    if option_ltp >= 150:
        gex_score = 10
    elif option_ltp >= 100:
        gex_score = 9
    elif option_ltp >= 50:
        gex_score = 8
    elif option_ltp >= 20:
        gex_score = 7
    elif option_ltp >= 10:
        gex_score = 5
    elif option_ltp < 5:
        gex_score = 2

    # ── Fundamental Proxy ─────────────────────────────────────────────────────
    if ltp and year_high and year_low and year_high > year_low:
        position_val = (ltp - year_low) / (year_high - year_low)
        if 0.3 <= position_val <= 0.7:
            fundamental_score = 8
        else:
            fundamental_score = 6
    else:
        fundamental_score = 5

    # ── Strategy Alignment Bonus ──────────────────────────────────────────────
    if strategy in ("ORB_BREAKOUT", "VWAP_REVERSION"):
        strategy_bonus = 5

    # ── Technical Analysis Bonus (RSI, MACD, Trend, OBV, ADX, BB, Stoch + Batch 1) ─
    tech_bonus, tech_tags = compute_technical_confluence_bonus(
        direction=direction,
        rsi=rsi,
        macd_bullish=macd_bullish,
        macd_above_zero=macd_above_zero,
        trend_alignment=trend_alignment,
        obv_trend=obv_trend,
        adx=adx,
        bb_pct_b=bb_pct_b,
        stoch_k=stoch_k,
        # Batch 1 additions
        williams_r=ts.get("williams_r"),
        cci=_cci,
        vpt_trend=_vpt,
        ad_trend=_ad,
        ichimoku_price_vs_cloud=_ichimoku.get("price_vs_cloud"),
        ichimoku_tk_cross=_ichimoku.get("tenkan_kijun_cross"),
        ichimoku_bullish=_ichimoku.get("bullish_signal"),
        ichimoku_bearish=_ichimoku.get("bearish_signal"),
        rsi_divergence=_rsi_div.get("divergence"),
        rsi_div_type=_rsi_div.get("type"),
        candle_bias=_candle.get("bias"),
        mf_alignment=_mf.get("alignment"),
        has_bull_chart_pattern=_chart.get("has_bullish_pattern", False),
        has_bear_chart_pattern=_chart.get("has_bearish_pattern", False),
    )

    # ── Expiry Penalty ────────────────────────────────────────────────────────
    if minutes_to_expiry < 60:
        technical_score = int(technical_score * 0.6)
        volume_score = int(volume_score * 0.6)
        pcr_score = int(pcr_score * 0.7)
    elif minutes_to_expiry < 180:
        technical_score = int(technical_score * 0.8)
        volume_score = int(volume_score * 0.8)

    total_confluence = (
        technical_score + volume_score + breadth_score
        + pcr_score + vix_score + gex_score + fundamental_score + strategy_bonus
        + tech_bonus  # additive technical bonus from RSI/MACD/trend
    )
    confluence_score = int(clamp(total_confluence, 0, 100))

    if confluence_score >= 80:
        conviction_level = "HIGH"
    elif confluence_score >= 58:
        conviction_level = "MEDIUM"
    else:
        conviction_level = "LOW"

    return confluence_score, conviction_level


def _get_signal_quality(confluence_score: int) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if confluence_score >= 78:
        return "HIGH"
    if confluence_score >= 65:
        return "MEDIUM"
    return "LOW"


async def build_fno_signal(
    contract: FNOContract,
    stock_core: StockCoreNormalized,
    option_ltp: float,
    refreshed_at: str,
    minutes_to_expiry: int,
    option_day_high: float | None = None,
    option_day_low: float | None = None,
    india_vix: float | None = None,
    pcr: float | None = None,
    # ── New: pre-computed technical snapshot from research engine ──────────
    tech_snapshot: dict | None = None,
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
    elif underlying_bias == "NEUTRAL":
        if pos is not None:
            if pos < 0.3 and contract.option_type == "CE":
                direction = "BULLISH"
                trigger_factors.append("NearLow_CE_Opportunity")
            elif pos > 0.7 and contract.option_type == "PE":
                direction = "BEARISH"
                trigger_factors.append("NearHigh_PE_Opportunity")
            elif 0.3 <= pos <= 0.7:
                if contract.option_type == "CE" and option_ltp < underlying_ltp * 0.05:
                    direction = "BULLISH"
                    trigger_factors.append("CheapCE_Neutral")
                elif contract.option_type == "PE" and option_ltp < underlying_ltp * 0.05:
                    direction = "BEARISH"
                    trigger_factors.append("CheapPE_Neutral")
                else:
                    direction = "NEUTRAL"
            else:
                direction = "NEUTRAL"
        else:
            if contract.option_type == "CE" and option_ltp < underlying_ltp * 0.04:
                direction = "BULLISH"
                trigger_factors.append("VeryC heapCE")
            elif contract.option_type == "PE" and option_ltp < underlying_ltp * 0.04:
                direction = "BEARISH"
                trigger_factors.append("VeryC heapPE")
            else:
                direction = "NEUTRAL"
    else:
        direction = "NEUTRAL"

    entry_price = round(option_ltp, 2)
    
    try:
        candles = await asyncio.wait_for(
            _fetch_historical_candles_from_kite(contract, interval="minute", candles=10),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        candles = None
    except Exception:
        candles = None
    
    if candles and len(candles) >= 5:
        dip_analysis = _analyze_micro_dip_prediction(candles, option_ltp)
        
        if dip_analysis["dip_expected"] and dip_analysis["confidence"] >= 0.35:
            predicted_dip = dip_analysis["predicted_dip_price"]
            entry_price = round(predicted_dip, 2)
            trigger_factors.append(f"MicroDipEntry=Conf{int(dip_analysis['confidence']*100)}%")
            trigger_factors.append(dip_analysis["reason"][:50])
        else:
            if option_day_low is not None and option_day_low > 0 and option_day_low < option_ltp:
                conservative_entry = option_ltp * 0.98
                entry_price = round(max(conservative_entry, option_day_low), 2)
                trigger_factors.append("EntryOptimized=Conservative")
    else:
        if option_day_low is not None and option_day_low > 0 and option_day_low < option_ltp:
            distance_to_low_pct = ((option_ltp - option_day_low) / option_ltp) * 100
            
            if distance_to_low_pct > 3.0:
                predicted_dip_pct = min(0.03 + (distance_to_low_pct - 3.0) * 0.01, 0.06)
                predicted_dip = option_ltp * (1 - predicted_dip_pct)
                entry_price = round(max(predicted_dip, option_day_low * 1.01), 2)
                trigger_factors.append(f"SmartDipEntry={predicted_dip_pct*100:.1f}%Below")
            else:
                conservative_entry = option_ltp * 0.985
                entry_price = round(max(conservative_entry, option_day_low), 2)
                trigger_factors.append("EntryOptimized=Conservative")
        else:
            entry_price = round(option_ltp * 0.995, 2)
            trigger_factors.append("EntryOptimized=Minimal")

    entry_discount_pct = ((option_ltp - entry_price) / option_ltp) * 100 if option_ltp > entry_price else 0.5
    
    # ── Extract tech snapshot data ─────────────────────────────────────────
    ts = tech_snapshot or {}
    underlying_atr = ts.get("atr")  # Daily ATR of underlying from research engine
    tech_rsi = ts.get("rsi")
    tech_macd = ts.get("macd") or {}
    tech_bb = ts.get("bollinger") or {}
    tech_alignment = ts.get("trend_alignment")
    tech_obv = (ts.get("obv") or {}).get("trend")
    tech_adx = ts.get("adx")
    tech_stoch = ts.get("stochastic") or {}
    # Batch 1 extras
    _ichimoku = ts.get("ichimoku") or {}
    _rsi_div = ts.get("rsi_divergence") or {}
    _candle = ts.get("candlestick_patterns") or {}
    _mf = ts.get("multiframe_trend") or {}
    _chart = ts.get("chart_patterns") or {}
    _cci = (ts.get("cci") or {}).get("cci")
    _vpt = (ts.get("vpt") or {}).get("trend")
    _ad = (ts.get("ad_line") or {}).get("trend")

    # ── Batch 5: Strategy Library Selection ────────────────────────────────
    _vix_curr = india_vix
    _adx_curr = tech_adx
    _rsi_curr = tech_rsi
    _regime_obj = classify_market_regime_enhanced(
        vix=_vix_curr, adx=_adx_curr, rsi=_rsi_curr
    )
    _regime = _regime_obj.get("regime", "NORMAL_VOL_TREND")
    _selected_strategy = select_strategy_for_signal(
        regime=_regime,
        direction=direction,
        adx=_adx_curr,
        vix=_vix_curr,
        instrument=contract.underlying,
    )
    _strategy_name = _selected_strategy.get("name", "Standard") if _selected_strategy else "Standard"
    _strategy_id = _selected_strategy.get("id", "S3_SUPERTREND") if _selected_strategy else "S3_SUPERTREND"
    if _selected_strategy:
        trigger_factors.append(f"Strategy:{_strategy_id}")
        trigger_factors.append(f"Regime:{_regime}")

    # ── Batch 4: Macro Context ────────────────────────────────────────────
    _sector_str = fundamental.get("sector") if fundamental else None
    _macro_ctx: dict = {}
    try:
        _macro_ctx = compute_macro_context(
            active_events=[],  # can be extended to pull from a global event config
            vix=_vix_curr,
            adx=_adx_curr,
            rsi=_rsi_curr,
            sector=_sector_str,
        )
        macro_bias = _macro_ctx.get("macro_bias", "NEUTRAL")
        if macro_bias == "HEADWIND" and direction == "BULLISH":
            trigger_factors.append(f"MacroHeadwind:{_sector_str}")
        elif macro_bias == "TAILWIND" and direction == "BULLISH":
            trigger_factors.append(f"MacroTailwind:{_sector_str}")
    except Exception:
        pass

    # ── Batch 5: Constituent-weighted NIFTY/BANKNIFTY breadth (Action 5) ──
    _index_breadth: dict = {}
    if contract.underlying in ("NIFTY", "BANKNIFTY"):
        try:
            _index_breadth = await _compute_enhanced_index_breadth(
                index_name=contract.underlying, top_n=12
            )
            _ib_bias = _index_breadth.get("weighted_bias", "NEUTRAL")
            _ib_score = _index_breadth.get("breadth_score", 50)
            if _ib_score >= 60 and direction == "BULLISH":
                trigger_factors.append(f"IndexBreadth:{_ib_score}%Bullish")
            elif _ib_score <= 40 and direction == "BEARISH":
                trigger_factors.append(f"IndexBreadth:{100-_ib_score}%Bearish")
        except Exception:
            pass
    
    # ── ATR-based targets (data-driven, not fixed %) ──────────────────────
    # Use min(minutes_to_expiry, minutes_to_session_close) for intraday realism
    mins_to_session_close = get_minutes_to_session_close()
    effective_minutes = (
        min(minutes_to_expiry, mins_to_session_close)
        if mins_to_session_close > 0
        else minutes_to_expiry
    )
    target1, target2 = compute_atr_based_fno_targets(
        entry_price=entry_price,
        underlying_ltp=float(underlying_ltp),
        atr=underlying_atr,
        minutes_to_expiry=effective_minutes,
        option_type=contract.option_type,
        vix=india_vix,
    )
    
    stop_loss = round(entry_price * 0.80, 2)
    
    if target1 > option_ltp * 1.20:
        target1 = round(option_ltp * 1.15, 2)
    if target2 > option_ltp * 1.80:
        target2 = round(option_ltp * 1.65, 2)

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
    
    if risk_reward_target2 < 1.2:
        min_target2_needed = entry_price + (1.2 * risk)
        target2 = round(max(target2, min_target2_needed), 2)
        risk_reward_target2 = round((target2 - entry_price) / risk, 2)
    
    remaining_trading_days = get_remaining_trading_days(contract.expiry)

    if remaining_trading_days >= 5:
        best_exit_days = min(int(remaining_trading_days * 0.6), remaining_trading_days - 1)
        max_ltp_multiplier = 1.4
    elif remaining_trading_days >= 3:
        best_exit_days = min(int(remaining_trading_days * 0.7), remaining_trading_days - 1)
        max_ltp_multiplier = 1.25
    elif remaining_trading_days >= 2:
        best_exit_days = 1
        max_ltp_multiplier = 1.15
    else:
        best_exit_days = 0
        max_ltp_multiplier = 1.05

    max_ltp_projection = round(entry_price * max_ltp_multiplier, 2)
    max_ltp_projection = min(max_ltp_projection, target2)

    # Theta decay: VIX-based model (not fixed multiplier)
    if remaining_trading_days > 0 and best_exit_days > 0:
        theta_decay, theta_method = compute_vix_theta_decay(
            entry_price=entry_price,
            remaining_trading_days=remaining_trading_days,
            best_exit_days=best_exit_days,
            india_vix=india_vix,
            iv_override=ts.get("iv") if ts else None,
        )
        best_exit_price = round(max(max_ltp_projection - theta_decay, entry_price * 1.01), 2)
    else:
        theta_decay = 0.0
        theta_method = "none"
        best_exit_price = max_ltp_projection

    # Compute actual calendar date for best exit
    best_exit_date_obj = get_nth_trading_day_from_today(best_exit_days) if best_exit_days and best_exit_days > 0 else None
    best_exit_date_str = best_exit_date_obj.strftime("%d %b %Y") if best_exit_date_obj else None

    # Add theta method to trigger_factors for signal transparency
    if theta_method and theta_method != "none":
        trigger_factors.append(f"ThetaModel={theta_method}")

    underlying_day_change_pct = None
    if stock_core.prev_close and stock_core.prev_close > 0:
        underlying_day_change_pct = round(((stock_core.ltp - stock_core.prev_close) / stock_core.prev_close) * 100, 2)

    entry_discount_pct = ((option_ltp - entry_price) / option_ltp) * 100 if option_ltp > entry_price else 0.5

    # ── ORB / VWAP Strategy Classification ───────────────────────────────────
    strategy: str | None = None
    if stock_core.open is not None and stock_core.ltp is not None and stock_core.open > 0:
        pct_from_open = ((stock_core.ltp - stock_core.open) / stock_core.open) * 100
        vwap_proxy = stock_core.open + (stock_core.ltp - stock_core.open) * 0.5

        if abs(pct_from_open) >= 0.3:
            strategy = "ORB_BREAKOUT"
            trigger_factors.append(f"ORB_Breakout={pct_from_open:.2f}%_from_open")
        elif vwap_proxy and abs(stock_core.ltp - vwap_proxy) / max(vwap_proxy, 1) < 0.003:
            strategy = "VWAP_REVERSION"
            trigger_factors.append("VWAP_Reversion")

    confluence_score, conviction_level = _calculate_confluence_score_master_spec(
        stock_core=stock_core,
        direction=direction,
        bias_score=bias_score,
        risk_reward_target2=risk_reward_target2,
        option_ltp=option_ltp,
        minutes_to_expiry=minutes_to_expiry,
        entry_discount_pct=entry_discount_pct,
        option_day_high=option_day_high,
        option_day_low=option_day_low,
        india_vix=india_vix,
        pcr=pcr,
        strategy=strategy,
        # Pass technical bonus inputs from research engine
        rsi=tech_rsi,
        macd_bullish=tech_macd.get("bullish_crossover"),
        macd_above_zero=tech_macd.get("above_zero"),
        trend_alignment=tech_alignment,
        obv_trend=tech_obv,
        adx=tech_adx,
        bb_pct_b=tech_bb.get("pct_b"),
        stoch_k=(tech_stoch.get("%K")),
    )
    
    # Add technical tags to trigger_factors
    if ts.get("data_available") and tech_alignment:
        trigger_factors.append(f"TrendAlign={tech_alignment}")
    if tech_rsi is not None:
        trigger_factors.append(f"RSI={tech_rsi:.0f}")
    if tech_adx is not None and tech_adx > 20:
        trigger_factors.append(f"ADX={tech_adx:.0f}")
    
    signal_quality = _get_signal_quality(confluence_score)

    is_potential_trade = direction != "NEUTRAL" and confluence_score >= 78 and risk_reward_target2 >= 1.2
    if is_potential_trade:
        trigger_factors.append(f"Conviction={conviction_level}")

    ltp_margin_to_t1_amount = round(max(target1 - option_ltp, 0.0), 2)
    ltp_margin_to_t1_pct = round(((target1 - option_ltp) / max(option_ltp, 0.01)) * 100, 2)
    achievable_profit_pct = round(((target1 - entry_price) / max(entry_price, 0.01)) * 100, 2)

    return FNOSignalResponse(
        script=contract.script,
        underlying=contract.underlying,
        expiry=contract.expiry,
        strike=contract.strike,
        option_type=contract.option_type,
        exchange=contract.exchange,
        lot_size=contract.lot_size,
        underlying_ltp=round(underlying_ltp, 2),
        underlying_day_high=round(stock_core.high, 2) if stock_core.high is not None else None,
        underlying_day_low=round(stock_core.low, 2) if stock_core.low is not None else None,
        underlying_day_change_pct=underlying_day_change_pct,
        underlying_bias_score=round(bias_score, 2),
        option_ltp=round(option_ltp, 2),
        option_day_high=round(option_day_high, 2) if option_day_high is not None else None,
        option_day_low=round(option_day_low, 2) if option_day_low is not None else None,
        ltp_margin_to_t1_amount=ltp_margin_to_t1_amount,
        ltp_margin_to_t1_pct=ltp_margin_to_t1_pct,
        achievable_profit_pct=achievable_profit_pct,
        direction=direction,
        strategy=(
            f"{strategy or conviction_level+' Conviction'} Trade"
            if is_potential_trade
            else "Directional Projection (Low Confidence)"
        ),
        strategy_library_id=_strategy_id,
        strategy_library_name=_strategy_name,
        market_regime=_regime,
        macro_context=_macro_ctx if _macro_ctx else None,
        index_breadth=_index_breadth if _index_breadth.get("available") else None,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target1=target1,
        target2=target2,
        risk_reward_target1=risk_reward_target1,
        risk_reward_target2=risk_reward_target2,
        max_ltp_projection=max_ltp_projection,
        best_exit_days=best_exit_days,
        best_exit_price=best_exit_price,
        remaining_trading_days=remaining_trading_days,
        best_exit_date_str=best_exit_date_str,
        trigger_factors=trigger_factors,
        confluence_score=confluence_score,
        signal_quality=signal_quality,
        conviction_level=conviction_level,
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
    stock_data = StockCoreNormalized(**(await _get_stock_core_cached(contract.underlying)))
    snapshot = await _fetch_live_option_snapshot(contract)
    option_ltp = float(snapshot.get("ltp"))
    return await build_fno_signal(
        contract,
        stock_data,
        option_ltp,
        refreshed_at,
        minutes_to_expiry,
        option_day_high=_to_float(snapshot.get("day_high")),
        option_day_low=_to_float(snapshot.get("day_low")),
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



async def _compute_enhanced_index_breadth(
    index_name: str,
    top_n: int = 12,
) -> dict:
    """
    Compute constituent-weighted index bias using tech snapshots for top N stocks.
    Uses NIFTY50_WEIGHTS / BANKNIFTY_WEIGHTS from research_engine.
    Returns compute_index_constituent_bias() result.
    """
    weights = NIFTY50_WEIGHTS if index_name == "NIFTY" else BANKNIFTY_WEIGHTS
    # Pick top N by weight
    top_symbols = sorted(weights.items(), key=lambda x: -x[1])[:top_n]

    constituent_signals: list[dict] = []

    async def _get_constituent_signal(sym: str, w: float) -> dict | None:
        try:
            hist = await _get_hist_ohlcv(sym, period="3mo")
            if hist is None or len(hist) < 20:
                return None
            ts = compute_full_technical_snapshot(sym, hist)
            return {
                "symbol": sym,
                "tech_bias": ts.get("technical_bias", "NEUTRAL"),
                "direction": ts.get("technical_bias", "NEUTRAL"),
                "conviction": min(
                    1.0,
                    abs(ts.get("bullish_signal_count", 0) - ts.get("bearish_signal_count", 0)) / 10
                ),
                "weight_override": w,
            }
        except Exception:
            return None

    results = await asyncio.gather(*[_get_constituent_signal(sym, w) for sym, w in top_symbols])
    constituent_signals = [r for r in results if r is not None]

    if not constituent_signals:
        return {"available": False, "weighted_bias": "NEUTRAL", "breadth_score": 50}

    bias_result = compute_index_constituent_bias(constituent_signals, index_name)
    bias_result["constituent_count_fetched"] = len(constituent_signals)
    bias_result["available"] = True
    return bias_result



async def _build_index_projection(index_name: Literal["NIFTY", "BANKNIFTY"], refreshed_at: str) -> IndexProjectionPane:
    try:
        stock = StockCoreNormalized(**(await _get_stock_core_cached(index_name)))
    except Exception:
        fallback_spot = await asyncio.to_thread(market_data_client.get_index_ltp, index_name)
        stock = StockCoreNormalized(
            symbol=index_name,
            sector="Index",
            ltp=fallback_spot,
            open=fallback_spot,
            high=fallback_spot,
            low=fallback_spot,
            prev_close=fallback_spot,
            volume=0.0,
            market_cap=None,
            pe_ratio=None,
            eps=None,
            book_value=None,
            year_high=fallback_spot,
            year_low=fallback_spot,
        )
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

    rows: list[FNOSignalResponse] = []
    if contracts:
        kite_map = await _fetch_option_snapshots_from_kite(contracts)

        # ── Compute real PCR from option chain OI ────────────────────────────
        total_ce_oi = 0.0
        total_pe_oi = 0.0
        for contract in contracts:
            snap = kite_map.get(contract.script)
            if snap and snap.get("oi"):
                oi_val = float(snap["oi"] or 0)
                if contract.option_type == "CE":
                    total_ce_oi += oi_val
                elif contract.option_type == "PE":
                    total_pe_oi += oi_val
        pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else None

        # ── Fetch India VIX ──────────────────────────────────────────────────
        india_vix = await _get_india_vix()

        # ── Fetch index historical OHLCV for tech snapshot ───────────────────
        idx_symbol = "^NSEI" if index_name == "NIFTY" else "^NSEBANK"
        index_tech_snap: dict = {}
        try:
            # For NIFTY/BANKNIFTY, use yfinance with special ticker
            hist_index = await _get_hist_ohlcv(index_name.replace("^", ""), period="6mo")
            if hist_index is None or hist_index.empty:
                # Try alternate symbol
                import yfinance as yf
                import pandas as pd
                def _fetch_index_hist():
                    t = yf.Ticker(idx_symbol)
                    return t.history(period="6mo", auto_adjust=True)
                hist_df_raw = await asyncio.to_thread(_fetch_index_hist)
                if hist_df_raw is not None and not hist_df_raw.empty:
                    hist_index = hist_df_raw
            if hist_index is not None and not hist_index.empty:
                index_tech_snap = compute_full_technical_snapshot(index_name, hist_index, ltp=stock.ltp)
        except Exception as exc:
            logger.warning(f"Index tech snapshot failed for {index_name}: {exc}")

        for contract in contracts:
            minutes_to_expiry = get_minutes_to_expiry(contract)
            try:
                snapshot = kite_map.get(contract.script)
                if snapshot is None:
                    snapshot = await _fetch_live_option_snapshot(contract)
                option_ltp = float(snapshot.get("ltp"))
                signal = await build_fno_signal(
                    contract,
                    stock,
                    option_ltp,
                    refreshed_at,
                    minutes_to_expiry,
                    option_day_high=_to_float(snapshot.get("day_high")),
                    option_day_low=_to_float(snapshot.get("day_low")),
                    india_vix=india_vix,
                    pcr=pcr,
                    tech_snapshot=index_tech_snap,
                )
                rows.append(signal)
            except HTTPException:
                continue
            except Exception:
                continue

    directional_candidates = [
        item
        for item in rows
        if item.direction != "NEUTRAL" and item.confluence_score >= 78 and item.risk_reward_target2 >= 1.3
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

    async def _safe_report_core(symbol: str) -> dict:
        try:
            return await _get_stock_core_cached(symbol)
        except Exception:
            return {
                "symbol": symbol,
                "sector": "Unknown",
                "ltp": None,
                "open": None,
                "high": None,
                "low": None,
                "prev_close": None,
                "volume": 0.0,
                "market_cap": None,
                "pe_ratio": None,
                "eps": None,
                "book_value": None,
                "year_high": None,
                "year_low": None,
            }

    report_rows = await asyncio.gather(*[_safe_report_core(symbol) for symbol, _ in weight_source])
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
        and item.confluence_score >= 58
        and item.risk_reward_target2 >= 1.2
        and item.risk_reward_target1 >= 0.8
        and item.expiry_risk != "HIGH"
        and (item.target1 - item.entry_price) / max(item.entry_price, 0.01) <= 0.18
    ]
    assured_signals.sort(key=lambda row: row.confluence_score, reverse=True)

    watchlist_signals: list[FNOSignalResponse] = []

    if len(assured_signals) < 2:
        fallback_candidates = [
            item
            for item in rows
            if item.script not in paired_scripts
            and strike_range_min <= item.strike <= strike_range_max
            and item.expiry_risk != "HIGH"
            and item.direction != "NEUTRAL"
            and item.confluence_score >= 45
            and item.risk_reward_target2 >= 1.2
        ]
        fallback_candidates.sort(key=lambda row: row.confluence_score, reverse=True)
        
        existing_scripts = {s.script for s in assured_signals}
        for candidate in fallback_candidates:
            if candidate.script not in existing_scripts:
                assured_signals.append(
                    candidate.model_copy(update={
                        "strategy": f"{candidate.conviction_level} Conviction Trade (Neutral Market)"
                    })
                )
                if len(assured_signals) >= 2:
                    break
        
        if len(assured_signals) < 2 and len(rows) > 0:
            all_available = [
                item for item in rows
                if item.expiry_risk != "HIGH"
                and item.script not in paired_scripts
                and item.risk_reward_target2 >= 1.2
            ]
            all_available.sort(key=lambda row: row.confluence_score, reverse=True)
            
            existing_scripts = {s.script for s in assured_signals}
            for candidate in all_available:
                if candidate.script not in existing_scripts:
                    assured_signals.append(
                        candidate.model_copy(update={
                            "strategy": f"Best Available Trade (Score: {candidate.confluence_score})"
                        })
                    )
                    if len(assured_signals) >= 2:
                        break

    directional_count = len([item for item in rows if item.direction != "NEUTRAL"])
    high_conf_count = len([item for item in rows if item.confluence_score >= 80])
    medium_conf_count = len([item for item in rows if 70 <= item.confluence_score < 80])
    bias_aligned_count = (
        len([item for item in rows if item.direction == expected_direction])
        if expected_direction != "NEUTRAL"
        else 0
    )
    rejection_note = None
    if not assured_signals:
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
    logger.info(f"Building stock F&O signals for {len(symbols)} symbols: {symbols}")
    cores = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_cores = [StockCoreNormalized(**row) for row in cores]
    semaphore = asyncio.Semaphore(4)

    # Fetch India VIX once for all stock signals
    india_vix = await _get_india_vix()

    async def _build_for_symbol(symbol: str, core: StockCoreNormalized) -> FNOSignalResponse | None:
        if core.ltp is None:
            logger.warning(f"{symbol}: No LTP available")
            return None

        # ── Eligibility filter ────────────────────────────────────────────
        fundamental = await _get_fundamental_data(symbol)
        eligibility = check_stock_eligibility(
            ltp=core.ltp,
            market_cap_cr=None,
            fundamental=fundamental,
        )
        if not eligibility["eligible"]:
            logger.info(f"{symbol}: DISQUALIFIED — {', '.join(eligibility['flags'])}")
            return None

        # ── Research engine: fetch historical OHLCV and compute technicals ─
        tech_snap: dict = {}
        try:
            hist_df = await _get_hist_ohlcv(symbol, period="6mo")
            if hist_df is not None and not hist_df.empty:
                tech_snap = compute_full_technical_snapshot(symbol, hist_df, ltp=core.ltp)
        except Exception as exc:
            logger.warning(f"{symbol}: tech snapshot failed: {exc}")

        step = 20 if core.ltp > 400 else 10
        strike = round(core.ltp / step) * step
        logger.info(f"{symbol}: LTP={core.ltp}, Strike={strike}, Eligible=True")

        async with semaphore:
            expiry = await _get_nearest_expiry(symbol, prefer_monthly=True)
            symbol_rows: list[FNOSignalResponse] = []
            for option_type in ["CE", "PE"]:
                lot_size_val = await _resolve_verified_lot_size(symbol, None)
                contract = FNOContract(
                    script=_format_script(symbol, expiry, strike, option_type),
                    underlying=symbol,
                    expiry=expiry,
                    expiry_time_ist="15:30",
                    strike=float(strike),
                    option_type=option_type,
                    exchange="NFO",
                    lot_size=lot_size_val,
                )
                minutes_to_expiry = get_minutes_to_expiry(contract)
                if minutes_to_expiry <= 15:
                    logger.warning(f"{symbol} {option_type}: Expiry too soon ({minutes_to_expiry}m)")
                    continue

                try:
                    snapshot = await _fetch_live_option_snapshot(contract)
                    option_ltp = float(snapshot.get("ltp"))
                except Exception as exc:
                    logger.warning(f"{symbol} {option_type}: Failed to fetch snapshot: {exc}")
                    continue

                if option_ltp is None or option_ltp <= 0:
                    logger.warning(f"{symbol} {option_type}: Invalid LTP: {option_ltp}")
                    continue

                try:
                    signal = await build_fno_signal(
                        contract,
                        core,
                        float(option_ltp),
                        refreshed_at,
                        minutes_to_expiry,
                        option_day_high=_to_float(snapshot.get("day_high")),
                        option_day_low=_to_float(snapshot.get("day_low")),
                        india_vix=india_vix,
                        tech_snapshot=tech_snap,
                    )
                    logger.info(f"{symbol} {option_type}: Signal generated - Direction={signal.direction}, Confluence={signal.confluence_score}, Conviction={signal.conviction_level}")
                except HTTPException as exc:
                    logger.warning(f"{symbol} {option_type}: Signal generation failed: {exc.detail}")
                    continue

                if signal.direction != "NEUTRAL":
                    symbol_rows.append(signal)
                else:
                    logger.info(f"{symbol} {option_type}: Direction is NEUTRAL, skipping")

            if not symbol_rows:
                logger.info(f"{symbol}: No non-NEUTRAL signals")
                return None

            logger.info(f"{symbol}: {len(symbol_rows)} signals before filtering")
            
            # Enforce 78% minimum confluence score per Master Spec requirement
            potential = [
                row
                for row in symbol_rows
                if row.confluence_score >= 78
                and row.risk_reward_target2 >= 1.2
                and row.expiry_risk != "HIGH"
            ]
            
            if potential:
                potential.sort(key=lambda row: row.confluence_score, reverse=True)
                logger.info(f"{symbol}: QUALIFIED - Confluence={potential[0].confluence_score}, Conviction={potential[0].conviction_level}")
                return potential[0]
            else:
                for row in symbol_rows:
                    reasons = []
                    if row.confluence_score < 78:
                        reasons.append(f"Confluence {row.confluence_score} < 78 (minimum required)")
                    if row.risk_reward_target2 < 1.2:
                        reasons.append(f"R:R {row.risk_reward_target2:.2f} < 1.2")
                    if row.expiry_risk == "HIGH":
                        reasons.append("HIGH expiry risk")
                    if reasons:
                        logger.info(f"{symbol} {row.option_type}: {', '.join(reasons)}")
                return None

    built = await asyncio.gather(*[_build_for_symbol(symbol, normalized_cores[idx]) for idx, symbol in enumerate(symbols)])
    results = [item for item in built if item is not None]
    results.sort(key=lambda row: row.confluence_score, reverse=True)
    
    logger.info(f"Stock F&O signals: {len(results)} total, returning top 20")
    return results[:20]


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
    fundamental_semaphore = asyncio.Semaphore(5)  # limit concurrent yfinance calls
    hist_semaphore = asyncio.Semaphore(3)  # limit concurrent yfinance historical calls

    async def _fetch_one(symbol: str) -> dict | None:
        async with semaphore:
            try:
                core = await _get_stock_core_cached(symbol)
                if core.get("ltp") is None:
                    return None
                return core
            except Exception:
                return None

    async def _fetch_fundamental_one(symbol: str) -> tuple[str, dict]:
        async with fundamental_semaphore:
            try:
                data = await _get_fundamental_data(symbol)
                return (symbol, data)
            except Exception:
                return (symbol, {})

    async def _fetch_hist_one(symbol: str) -> tuple[str, float | None]:
        """Fetch historical vol for a symbol."""
        async with hist_semaphore:
            try:
                hist_df = await _get_hist_ohlcv(symbol, period="1y")
                if hist_df is not None and not hist_df.empty:
                    hist_vol = compute_historical_volatility(hist_df["Close"])
                    return (symbol, hist_vol)
            except Exception:
                pass
            return (symbol, None)

    fetched = await asyncio.gather(*[_fetch_one(symbol) for symbol in universe])
    results = [row for row in fetched if row is not None]
    valid_symbols = [row["symbol"] for row in results]

    # Fetch fundamentals and hist vols in parallel (uses cache, so mostly fast after first run)
    fundamental_results = await asyncio.gather(*[_fetch_fundamental_one(sym) for sym in valid_symbols])
    fundamental_map = {sym: data for sym, data in fundamental_results}

    hist_vol_results = await asyncio.gather(*[_fetch_hist_one(sym) for sym in valid_symbols])
    hist_vol_map = {sym: vol for sym, vol in hist_vol_results}

    candidates: list[MultibaggerCandidate] = []
    for row in results:
        stock = StockCoreNormalized(**row)
        if stock.ltp is None:
            continue

        fundamental = fundamental_map.get(stock.symbol, {})

        # ── Apply eligibility filters ───────────────────────────────────
        eligibility = check_stock_eligibility(
            ltp=stock.ltp,
            market_cap_cr=stock.market_cap,
            fundamental=fundamental,
        )
        # Inject hist_vol into fundamental dict for price band calculation
        hist_vol = hist_vol_map.get(stock.symbol)
        if hist_vol is not None:
            fundamental = {**fundamental, "hist_vol": hist_vol}

        analysis = compute_multibagger_analysis(stock, fundamental=fundamental)

        # Lower eligibility score if filters failed (don't fully exclude, just down-rank)
        if not eligibility["eligible"]:
            analysis["multibagger_score"] = max(0, analysis["multibagger_score"] - 20)
            analysis["is_potential_multibagger"] = False
            analysis["thesis"] = f"[ELIGIBILITY FLAGS: {'; '.join(eligibility['flags'])}] " + analysis.get("thesis", "")

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
                # Fundamental fields
                roe=analysis.get("roe"),
                roce=analysis.get("roce"),
                piotroski_score=analysis.get("piotroski_score"),
                beneish_m_score=analysis.get("beneish_m_score"),
                eps_growth_pct=analysis.get("eps_growth_pct"),
                debt_to_equity=analysis.get("debt_to_equity"),
                current_ratio=analysis.get("current_ratio"),
                gross_margin=analysis.get("gross_margin"),
                vol_bands=analysis.get("vol_bands"),
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
    buy_to_ltp_pct = round((buy_to_ltp_diff / buy_price) * 100, 2) if (buy_to_ltp_diff is not None and buy_price > 0) else None
    floating_pnl_amount = round((float(latest_option_ltp) - buy_price) * units, 2) if latest_option_ltp is not None else None
    floating_pnl_pct = buy_to_ltp_pct
    ltp_to_t1_diff = round(max(float(target1) - float(latest_option_ltp), 0.0), 2) if (target1 is not None and latest_option_ltp is not None) else None
    ltp_to_t2_diff = round(max(float(target2) - float(latest_option_ltp), 0.0), 2) if (target2 is not None and latest_option_ltp is not None) else None

    sold_price = _to_float(position.get("sold_price"))
    realized_pnl = _to_float(position.get("realized_pnl"))
    if realized_pnl is None and sold_price is not None:
        realized_pnl = round((sold_price - buy_price) * units, 2)

    can_sell = position.get("status") == "OPEN"

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
        buy_to_ltp_pct=buy_to_ltp_pct,
        floating_pnl_amount=floating_pnl_amount,
        floating_pnl_pct=floating_pnl_pct,
        ltp_to_t1_diff=ltp_to_t1_diff,
        ltp_to_t2_diff=ltp_to_t2_diff,
        target1_achieved=target1_achieved,
        target2_achieved=target2_achieved,
        can_sell=can_sell,
        sold_price=sold_price,
        realized_pnl=realized_pnl,
        projected_exit_price=position.get("projected_exit_price"),
        best_exit_price=position.get("best_exit_price"),
        best_exit_days=position.get("best_exit_days"),
        best_exit_date_str=position.get("best_exit_date_str"),
        remaining_trading_days=int(position.get("remaining_trading_days") or 0),
        recovery_potential=position.get("recovery_potential"),
        minutes_to_expiry=int(position.get("minutes_to_expiry", 0)),
        revised_exit_plan=position.get("revised_exit_plan", ""),
    )


async def _refresh_open_position(position: dict) -> dict:
    corrected_lot_size = int(position.get("lot_size") or 1)
    if corrected_lot_size <= 1:
        corrected_lot_size = await _resolve_verified_lot_size(
            str(position.get("underlying", "")),
            str(position.get("script", "")),
        )

    contract_dict = {
        "script": position["script"],
        "underlying": position["underlying"],
        "expiry": position["expiry_date"],
        "expiry_time_ist": position.get("expiry_time_ist", "15:30"),
        "strike": position["strike"],
        "option_type": position["option_type"],
        "exchange": "NFO",
        "lot_size": corrected_lot_size,
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
                    "lot_size": corrected_lot_size,
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
    best_exit_days: int | None = None
    best_exit_date_str: str | None = None

    # Compute best_exit_days based on actual remaining trading days
    remaining_trading_days = get_remaining_trading_days(position["expiry_date"])
    if remaining_trading_days >= 14:
        best_exit_days = max(1, min(int(remaining_trading_days * 0.6), remaining_trading_days - 1))
    elif remaining_trading_days >= 7:
        best_exit_days = max(1, min(int(remaining_trading_days * 0.7), remaining_trading_days - 1))
    elif remaining_trading_days >= 3:
        best_exit_days = 2
    else:
        best_exit_days = min(1, remaining_trading_days) if remaining_trading_days > 0 else 0

    if best_exit_days and best_exit_days > 0:
        best_exit_date_obj = get_nth_trading_day_from_today(best_exit_days)
        best_exit_date_str = best_exit_date_obj.strftime("%d %b %Y")

    # ── Dynamic target revision (increase T1/T2 when market is favorable) ─
    dynamic_revision_note: str | None = None
    revised_exit_plan: str = "Hold with trailing stop once target1 hits"
    try:
        now_ist = datetime.now(IST)
        session_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        mins_to_close = max(0, int((session_close - now_ist).total_seconds() / 60))
        india_vix_for_pos = await _get_india_vix()
        # Get underlying LTP for dynamic revision
        underlying_sym = position.get("underlying") or position.get("script", "").split("2")[0][:10]
        underlying_core = None
        if underlying_sym:
            try:
                underlying_core = await _get_stock_core_cached(underlying_sym.upper())
            except Exception:
                pass
        underlying_ltp_val = float(underlying_core.get("ltp", 0) or 0) if underlying_core else 0.0
        underlying_entry_val = float(position.get("underlying_entry_price", underlying_ltp_val) or underlying_ltp_val)
        option_type_pos = "CE" if "CE" in position.get("script", "").upper() else "PE"
        dir_pos = "BULLISH" if option_type_pos == "CE" else "BEARISH"
        rev_t1, rev_t2, dynamic_revision_note = compute_dynamic_target_revision(
            entry_price=buy_price,
            current_ltp=latest_option_ltp,
            current_t1=revised_target1,
            current_t2=revised_target2,
            underlying_ltp=underlying_ltp_val,
            underlying_entry=underlying_entry_val,
            india_vix=india_vix_for_pos,
            minutes_to_session_close=mins_to_close,
            remaining_trading_days=remaining_trading_days,
            direction=dir_pos,
        )
        if rev_t1 > revised_target1:
            revised_target1 = rev_t1
        if rev_t2 > revised_target2:
            revised_target2 = rev_t2
        if dynamic_revision_note:
            revised_exit_plan = dynamic_revision_note
    except Exception as exc:
        logger.warning("Dynamic target revision failed: %s", exc)

    alert = None

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

    # ── Research Engine: Enhanced urgent exit detection ──────────────────
    if alert is None:
        now_ist = datetime.now(IST)
        session_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        mins_to_close = max(0, int((session_close - now_ist).total_seconds() / 60))
        urgent_info = check_urgent_exit(
            position={
                "buy_price": position.get("buy_price", 0),
                "remaining_trading_days": remaining_trading_days,
            },
            current_ltp=latest_option_ltp,
            minutes_to_session_close=mins_to_close,
        )
        if urgent_info.get("urgent_exit"):
            alert = "URGENT_EXIT_ENGINE"
            revised_exit_plan = urgent_info["reason"]
            if urgent_info.get("best_price_hint"):
                best_exit_price = urgent_info["best_price_hint"]

    # ── Batch 5: Signal Lifecycle State Machine ───────────────────────────
    current_signal_state = position.get("signal_state", "ACTIVE")
    _stop_loss_price = float(position.get("stop_loss") or (buy_price * 0.88))
    option_type_sm = "CE" if "CE" in position.get("script", "").upper() else "PE"
    direction_sm = "BULLISH" if option_type_sm == "CE" else "BEARISH"
    sm_result = transition_signal_state(
        current_state=current_signal_state,
        ltp=latest_option_ltp,
        entry_price=buy_price,
        sl_price=_stop_loss_price,
        t1_price=revised_target1,
        t2_price=revised_target2,
        direction=direction_sm,
        minutes_to_expiry=minutes_to_expiry,
    )
    new_signal_state = sm_result["new_state"]
    if sm_result.get("urgent_exit") and alert is None:
        alert = "URGENT_EXIT_SM"
        revised_exit_plan = sm_result.get("reason", revised_exit_plan)
    # Override terminal states to update position status
    if new_signal_state in ("EXPIRED", "CLOSED_LOSS", "CLOSED_WIN", "CANCELLED") and position.get("status") == "OPEN":
        # Only mark as closed if state machine says terminal — set alert but keep status OPEN for user to confirm sell
        if new_signal_state == "EXPIRED" and alert is None:
            alert = "EXPIRED"
    if new_signal_state in ("WATCHING_SL", "CLOSED_LOSS") and alert is None:
        alert = "SL_WATCH"

    updated = await db.custom_positions.find_one_and_update(
        {"id": position["id"]},
        {
            "$set": {
                "latest_option_ltp": round(float(latest_option_ltp), 2),
                "lot_size": corrected_lot_size,
                "target1": revised_target1,
                "target2": revised_target2,
                "stop_loss": _stop_loss_price,
                "signal_state": new_signal_state,
                "signal_state_reason": sm_result.get("reason"),
                "minutes_to_expiry": minutes_to_expiry,
                "alert": alert,
                "projected_exit_price": projected_exit_price,
                "best_exit_price": best_exit_price,
                "best_exit_days": best_exit_days,
                "best_exit_date_str": best_exit_date_str,
                "remaining_trading_days": remaining_trading_days,
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


# ─── NSE Holiday Management Endpoints ─────────────────────────────────────────

@api_router.get("/admin/nse-holidays")
async def admin_get_nse_holidays(owner_user: dict = Depends(get_owner_user)):
    """List all NSE holidays currently stored, grouped by year."""
    _ = owner_user
    holidays = get_nse_holidays()
    # Also fetch full records from DB for display
    cursor = db["nse_holidays"].find({}, {"_id": 0}).sort("date", 1)
    records = await cursor.to_list(500)
    return {
        "total_in_memory": len(holidays),
        "holidays": records,
    }


@api_router.post("/admin/nse-holidays/refresh")
async def admin_refresh_nse_holidays(
    owner_user: dict = Depends(get_owner_user),
    year: int = Query(..., ge=2025, le=2030, description="Calendar year to refresh"),
):
    """Manually trigger a holiday fetch for a specific year."""
    global NSE_HOLIDAYS
    _ = owner_user
    from services.holiday_manager import fetch_and_update_holidays
    success = await fetch_and_update_holidays(year)
    if success:
        NSE_HOLIDAYS = get_nse_holidays()
    return {
        "success": success,
        "year": year,
        "total_holidays": len(NSE_HOLIDAYS),
        "message": f"Holidays for {year} {'updated from external source' if success else 'could not be fetched; defaults remain'}.",
    }



# ── Strategy Backtest Persistence (Batch 5) ───────────────────────────────────

@api_router.get("/admin/strategy-stats")
async def get_strategy_stats(
    strategy_id: str | None = Query(default=None),
    admin_user: dict = Depends(get_admin_user),
):
    """Return aggregated backtest stats per strategy_id."""
    query: dict = {}
    if strategy_id:
        query["strategy_id"] = strategy_id
    records = await db.strategy_backtest.find(query, {"_id": 0}).to_list(length=500)

    agg: dict[str, dict] = {}
    for r in records:
        sid = r.get("strategy_id", "UNKNOWN")
        if sid not in agg:
            agg[sid] = {"strategy_id": sid, "total_trades": 0, "wins": 0,
                        "total_r_multiple": 0.0}
        agg[sid]["total_trades"] += 1
        if r.get("win"):
            agg[sid]["wins"] += 1
        agg[sid]["total_r_multiple"] = round(
            agg[sid]["total_r_multiple"] + (r.get("r_multiple") or 0), 3
        )

    summary = []
    for sid, stats in agg.items():
        t = stats["total_trades"]
        stats["win_rate"] = round(stats["wins"] / t, 3) if t > 0 else None
        stats["expectancy"] = round(stats["total_r_multiple"] / t, 3) if t > 0 else None
        eligible, reason = check_strategy_eligible(stats, min_trades=10)
        stats["eligible"] = eligible
        stats["auto_disabled"] = not eligible
        stats["eligibility_reason"] = reason
        # Enrich with strategy definition
        strat_def = STRATEGY_LIBRARY.get(sid, {})
        stats["strategy_name"] = strat_def.get("name", sid)
        stats["strategy_type"] = strat_def.get("type", "UNKNOWN")
        summary.append(stats)

    summary.sort(key=lambda x: x.get("total_trades", 0), reverse=True)
    return {"strategy_stats": summary, "total_records": len(records)}


@api_router.post("/admin/strategy-stats/record")
async def record_strategy_result(
    strategy_id: str = Query(..., description="e.g. S1_ORB, SW2_200DMA_BOUNCE"),
    symbol: str = Query(...),
    win: bool = Query(...),
    r_multiple: float = Query(..., description="R-multiple: +1.0 = 1R gain, -1.0 = full SL"),
    admin_user: dict = Depends(get_admin_user),
):
    """Record a trade result for a strategy to persist backtest stats."""
    record = {
        "id": str(uuid.uuid4()),
        "strategy_id": strategy_id,
        "symbol": symbol,
        "win": win,
        "r_multiple": round(r_multiple, 3),
        "recorded_at": _utc_now_iso(),
        "recorded_by": admin_user.get("username", "admin"),
    }
    await db.strategy_backtest.insert_one(record)

    # Recompute current stats
    all_records = await db.strategy_backtest.find(
        {"strategy_id": strategy_id}, {"_id": 0}
    ).to_list(length=500)
    stats: dict[str, Any] = {"total_trades": 0, "wins": 0, "total_r_multiple": 0.0}
    for r in all_records:
        stats["total_trades"] += 1
        if r.get("win"):
            stats["wins"] += 1
        stats["total_r_multiple"] += r.get("r_multiple") or 0
    t = stats["total_trades"]
    if t > 0:
        stats["win_rate"] = round(stats["wins"] / t, 3)
        stats["expectancy"] = round(stats["total_r_multiple"] / t, 3)
    eligible, reason = check_strategy_eligible(stats, min_trades=10)
    return {
        "recorded": True,
        "strategy_id": strategy_id,
        "current_stats": stats,
        "eligible": eligible,
        "auto_disabled": not eligible,
        "reason": reason,
    }


@api_router.get("/strategy-library")
async def get_strategy_library(current_user: dict = Depends(get_current_user)):
    """Return the full F&O strategy library with definitions and entry conditions."""
    return {
        "strategies": [
            {"id": sid, **strat}
            for sid, strat in STRATEGY_LIBRARY.items()
        ],
        "total": len(STRATEGY_LIBRARY),
    }



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


@api_router.delete("/admin/domain-mappings/{domain}")
async def admin_delete_domain_mapping(
    domain: str,
    owner_user: dict = Depends(get_owner_user),
):
    """Delete a domain mapping from DB and attempt nginx config cleanup."""
    key = _validate_domain(domain)
    result = await db.domain_mappings.delete_one({"domain": key})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Domain mapping not found")

    # Attempt nginx config removal
    try:
        import os
        import subprocess
        nginx_conf = f"/etc/nginx/sites-available/{key}"
        nginx_link = f"/etc/nginx/sites-enabled/{key}"
        for path in (nginx_conf, nginx_link):
            if os.path.exists(path):
                os.remove(path)
        subprocess.run(["nginx", "-s", "reload"], capture_output=True, timeout=5)
    except Exception as exc:
        logger.debug("Nginx config cleanup skipped: %s", exc)

    return {"deleted": True, "domain": key}


@api_router.post("/admin/domain-mappings/{domain}/map")
async def admin_map_domain(
    domain: str,
    owner_user: dict = Depends(get_owner_user),
):
    """Write Nginx reverse-proxy config for the domain and attempt reload."""
    import os
    import subprocess
    key = _validate_domain(domain)
    row = await db.domain_mappings.find_one({"domain": key}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Domain mapping not found — add it first")

    nginx_config = f"""server {{
    listen 80;
    server_name {key};

    location / {{
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}

    location /api/ {{
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
"""
    nginx_status = "NGINX_CONFIG_GENERATED"
    nginx_error = None
    conf_path = f"/etc/nginx/sites-available/{key}"
    link_path = f"/etc/nginx/sites-enabled/{key}"
    try:
        with open(conf_path, "w") as fh:
            fh.write(nginx_config)
        if not os.path.exists(link_path):
            os.symlink(conf_path, link_path)
        result = subprocess.run(["nginx", "-t"], capture_output=True, timeout=5)
        if result.returncode == 0:
            subprocess.run(["nginx", "-s", "reload"], capture_output=True, timeout=5)
            nginx_status = "ACTIVE"
        else:
            nginx_error = result.stderr.decode()[:300]
    except Exception as exc:
        nginx_error = str(exc)[:200]
        logger.info("Nginx map attempted for %s: %s", key, nginx_error)

    await db.domain_mappings.update_one(
        {"domain": key},
        {"$set": {"status": nginx_status, "nginx_config": nginx_config, "updated_at": _utc_now_iso()}},
    )

    return {
        "mapped": True,
        "domain": key,
        "nginx_status": nginx_status,
        "nginx_error": nginx_error,
        "nginx_config_snippet": nginx_config,
        "note": "DNS must still point to this server's IP for traffic to reach this app.",
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
        nifty_projection = await asyncio.wait_for(_build_index_projection("NIFTY", refreshed_at), timeout=120)
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
        banknifty_projection = await asyncio.wait_for(_build_index_projection("BANKNIFTY", refreshed_at), timeout=120)
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
        stock_signals = await asyncio.wait_for(_build_stock_fno_signals(refreshed_at), timeout=60)
        logger.info(f"Stock F&O signals generated: {len(stock_signals)}")
    except asyncio.TimeoutError:
        logger.warning("Stock F&O signal generation timed out after 60s")
        stock_signals = []
    except Exception as exc:
        logger.error(f"Stock F&O signal generation failed: {exc}")
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

    # ── Market Regime classification (Enhanced Batch 3) ──────────────────
    india_vix = await _get_india_vix()
    # Get ADX/RSI from NIFTY tech snapshot if available
    _nifty_ts = None
    try:
        _nifty_hist = await _get_hist_ohlcv("NIFTY", period="3mo")
        if _nifty_hist is not None:
            _nifty_ts = compute_full_technical_snapshot("NIFTY", _nifty_hist)
    except Exception:
        pass
    _nifty_adx = _nifty_ts.get("adx") if _nifty_ts else None
    _nifty_rsi = _nifty_ts.get("rsi") if _nifty_ts else None
    market_regime = classify_market_regime_enhanced(
        vix=india_vix, adx=_nifty_adx, rsi=_nifty_rsi
    )
    market_session = get_market_session_status()

    # ── No-signals alert with specific reason ─────────────────────────────
    no_signals_alert = None
    all_top_trades = [row for row in top_trades if row.is_potential_trade]
    if not all_top_trades:
        reasons: list[str] = []
        # Check index projections
        if nifty_projection.rejection_note:
            reasons.append(f"NIFTY: {nifty_projection.rejection_note}")
        if banknifty_projection.rejection_note:
            reasons.append(f"BANKNIFTY: {banknifty_projection.rejection_note}")
        if not stock_signals:
            reasons.append("Individual stock signals: No scripts passed 78% confluence & R:R ≥ 1.2 filters")
        # Market regime context
        regime = market_regime.get("regime", "UNKNOWN")
        if regime in ("LOW_VOL_RANGE",):
            reasons.append(f"Market in {regime} — directional setups lacking conviction; consider non-directional strategies")
        elif regime in ("CRASH_MODE",):
            reasons.append(f"Market in {regime} — extreme volatility; avoid aggressive directional entries")
        # Session context
        if not market_session.get("is_open"):
            reasons.append(f"Market is currently CLOSED ({market_session.get('status', 'CLOSED')}) — signals based on last available prices")
        reason_text = " | ".join(reasons) if reasons else "Current market conditions do not meet minimum 78% confluence threshold"
        no_signals_alert = f"No script signals currently available. Reason: {reason_text}"

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
        no_signals_alert=no_signals_alert,
        market_regime=market_regime,
        market_session=market_session,
    )


@api_router.post("/fno/custom-position", response_model=CustomPositionCreateResponse)
async def create_custom_position(
    payload: CustomPositionCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if payload.buy_price <= 0:
        raise HTTPException(status_code=400, detail="Buy price must be greater than 0")

    contract = await _resolve_contract_from_input(payload.script)
    final_lot_size = await _resolve_verified_lot_size(contract.underlying, contract.script)
    if final_lot_size > 0 and final_lot_size != contract.lot_size:
        contract = contract.model_copy(update={"lot_size": final_lot_size})
    minutes_to_expiry = get_minutes_to_expiry(contract)
    _validate_expiry_guard(minutes_to_expiry)

    updated_user, charged = await _consume_credits(current_user, 1.0)
    try:
        latest_snapshot = await _fetch_live_option_snapshot(contract)
        latest_option_ltp = float(latest_snapshot.get("ltp"))
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
        "quantity_lots": int(payload.quantity_lots),
        "buy_price": round(float(payload.buy_price), 2),
        "created_at": now_iso,
        "last_update": now_iso,
        "status": "OPEN",
        "signal_state": "ACTIVE",          # Batch 5: lifecycle state machine
        "alert": None,
        "latest_option_ltp": round(float(latest_option_ltp), 2),
        "target1": round(float(payload.buy_price) * 1.12, 2),
        "target2": round(float(payload.buy_price) * 1.5, 2),
        "stop_loss": round(float(payload.buy_price) * 0.88, 2),   # Default SL = -12% from entry
        "projected_exit_price": None,
        "best_exit_price": None,
        "best_exit_days": None,
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
            if int(row.get("lot_size") or 1) <= 1:
                corrected = await _resolve_verified_lot_size(str(row.get("underlying", "")), str(row.get("script", "")))
                if corrected > 1:
                    row = await db.custom_positions.find_one_and_update(
                        {"id": row["id"], "user_key": current_user["user_key"]},
                        {"$set": {"lot_size": corrected, "last_update": _utc_now_iso()}},
                        projection={"_id": 0},
                        return_document=ReturnDocument.AFTER,
                    ) or row
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


@api_router.delete("/fno/custom-position/{position_id}")
async def remove_custom_position(position_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.custom_positions.delete_one(
        {
            "id": position_id,
            "user_key": current_user["user_key"],
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Custom position not found")
    return {"removed": True, "id": position_id}


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
        failed_symbols=analysis.failed_symbols,
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
        failed_symbols=analysis.failed_symbols,
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


class MultibaggerCustomSearchRequest(BaseModel):
    symbol: str


@api_router.post("/multibagger/custom-search", response_model=MultibaggerCandidate)
async def multibagger_custom_search(
    payload: MultibaggerCustomSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Analyze any NSE symbol on-demand using the multibagger scoring engine."""
    symbol = payload.symbol.strip().upper()
    refreshed_at = _utc_now_iso()

    try:
        core = await _get_stock_core_cached(symbol)
        if core.get("ltp") is None:
            raise HTTPException(
                status_code=404,
                detail=f"No live data for '{symbol}'. Ensure it is a valid NSE symbol (e.g. RELIANCE, INFY).",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' not found or unavailable: {exc}",
        ) from exc

    stock = StockCoreNormalized(**core)
    fundamental: dict = {}
    try:
        fundamental = await _get_fundamental_data(symbol)
    except Exception:
        pass

    analysis = compute_multibagger_analysis(stock, fundamental=fundamental)

    return MultibaggerCandidate(
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
        roe=analysis.get("roe"),
        roce=analysis.get("roce"),
        piotroski_score=analysis.get("piotroski_score"),
        beneish_m_score=analysis.get("beneish_m_score"),
        eps_growth_pct=analysis.get("eps_growth_pct"),
        debt_to_equity=analysis.get("debt_to_equity"),
        current_ratio=analysis.get("current_ratio"),
        gross_margin=analysis.get("gross_margin"),
        vol_bands=analysis.get("vol_bands"),
    )
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


@api_router.get("/sector-momentum")
async def get_sector_momentum(
    force_refresh: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """
    Compute or return cached sector momentum dashboard.
    Returns momentum scores, 1W/1M/3M returns, RSI, ADX for 15 NSE sectors.
    Results cached for 30 minutes. Use ?force_refresh=true to bypass cache.
    """
    _ = current_user
    now_ts = datetime.now(timezone.utc).timestamp()

    # In-memory cache check
    if not force_refresh and SECTOR_MOMENTUM_CACHE:
        cached_ts = SECTOR_MOMENTUM_CACHE.get("_ts", 0)
        if (now_ts - cached_ts) < SECTOR_MOMENTUM_CACHE_TTL_SECONDS:
            data = {k: v for k, v in SECTOR_MOMENTUM_CACHE.items() if not k.startswith("_")}
            data["from_cache"] = True
            return data

    # MongoDB cache check
    if not force_refresh:
        try:
            cached_doc = await db.sector_momentum_cache.find_one(
                {"_key": "sector_momentum"}, {"_id": 0}
            )
            if cached_doc and (now_ts - float(cached_doc.get("cached_at_ts", 0))) < SECTOR_MOMENTUM_CACHE_TTL_SECONDS:
                payload = {k: v for k, v in cached_doc.items() if k not in ("_key", "cached_at_ts")}
                SECTOR_MOMENTUM_CACHE.update({**payload, "_ts": now_ts})
                payload["from_cache"] = True
                return payload
        except Exception:
            pass

    # Compute fresh
    try:
        result = await compute_sector_momentum_dashboard()
    except Exception as exc:
        logger.error("Sector momentum computation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sector momentum computation failed: {exc}")

    # Store in caches
    SECTOR_MOMENTUM_CACHE.update({**result, "_ts": now_ts})
    try:
        await db.sector_momentum_cache.update_one(
            {"_key": "sector_momentum"},
            {"$set": {"_key": "sector_momentum", "cached_at_ts": now_ts, **result}},
            upsert=True,
        )
    except Exception:
        pass

    result["from_cache"] = False
    return result


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
    global NSE_HOLIDAYS
    # Initialize NSE holiday manager (seeds DB, loads into memory, starts background updater)
    loaded = await init_holiday_manager(db)
    NSE_HOLIDAYS = loaded
    logger.info("NSE_HOLIDAYS loaded: %d dates", len(NSE_HOLIDAYS))

    await _ensure_owner_exists()
    await _sync_script_master_daily()
    await _sync_kite_option_master_daily()


@app.on_event("shutdown")
async def shutdown_db_client():
    await shutdown_holiday_manager()
    client.close()
