import asyncio
import math
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
    get_all_macro_events,
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
    # ── Batch 1 NEW: Index Constituents & Breadth ─────────────────────────
    get_constituents,
    get_constituents_sync,
    get_all_nifty500_symbols,
    compute_weighted_breadth,
    # ── Batch 1 NEW: Intraday Features & Order Flow ──────────────────────
    compute_vwap_features,
    compute_intraday_technicals,
    compute_order_book_imbalance,
    compute_volume_delta,
    classify_flow_band,
    classify_regime_enhanced,
    build_intraday_feature_vector,
    # ── Batch 1 NEW: Options Chain Features ───────────────────────────────
    classify_oi_buildup,
    compute_iv_rank,
    compute_bid_ask_spread,
    compute_enhanced_option_features,
    # ── Batch 1 NEW: News Sentiment ──────────────────────────────────────
    refresh_news_cache,
    get_symbol_sentiment,
    get_sector_sentiment,
    get_market_sentiment_summary,
    # ── Batch 2 NEW: MFE/MAE Engine, Probability & Theta ─────────────────
    build_mfe_mae_library,
    build_probability_table,
    select_targets_from_probability,
    compute_empirical_theta,
    compute_forward_mfe,
    compute_best_exit_online,
    reevaluate_signal_targets,
    check_no_chasing_rule,
    check_0dte_atm_safety,
    # ── Batch 3 NEW: 4-Bucket Confluence Score ───────────────────────────
    compute_bucket_a,
    compute_bucket_b,
    compute_bucket_c,
    compute_bucket_d,
    compute_confluence_score_v2,
    CONFLUENCE_THRESHOLD,
    # ── Mini-Batch: F&O Universe ─────────────────────────────────────────
    get_fo_universe,
    get_fo_universe_from_db,
    # ── Batch 4 NEW: Position Monitoring & Alerts ────────────────────────
    generate_position_alerts as generate_monitoring_alerts,
    # ── Step 3 NEW: Strategy Backtest Engine ──────────────────────────────
    run_backtest_batch,
    fetch_strategy_backtest,
    is_strategy_enabled as is_backtest_enabled,
    list_csv_seeds,
    save_csv_seed,
    delete_csv_seed,
    # ── Step 4 NEW: Position Sizing Calculator ────────────────────────────
    compute_position_size,
    annotate_signal_affordability,
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
from services.iv_history import (
    capture_atm_iv as _capture_atm_iv,
    ensure_indexes as _ensure_iv_indexes,
    get_iv_stats_52w,
)

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

# ── Configure shared auth dependencies for route modules ──────────────────────
import deps as _deps_module
_deps_module.configure(db, SESSION_STORE)

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
    # Index — VERIFIED NSE lot sizes (updated Apr 2026)
    "NIFTY":       65,   # NSE revised: was 75, now 65 as of Apr 2026
    "BANKNIFTY":   30,
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

# ── Global data-source config: imported from canonical data_policy module ───
from services.data_policy import KITE_IS_SOURCE_OF_TRUTH, USE_YFINANCE  # noqa: F401

# ── Extracted service modules (business logic moved from server.py) ───────────
from services.fno_signal_engine import (
    _analyze_micro_dip_prediction,
    _build_contract,
    _build_index_projection,
    _build_report,
    _build_signal_for_contract,
    _build_stock_fno_signals,
    _calculate_confluence_score_master_spec,
    _compute_enhanced_index_breadth,
    _compute_initial_option_sl,
    _compute_initial_option_targets,
    _compute_report_from_rows,
    _format_script,
    _get_nearest_expiry,
    _get_signal_quality,
    _infer_stock_option_type,
    _resolve_contract_from_input,
    _safe_signal,
    build_fno_signal,
)
from services.multibagger_engine import (
    _build_multibagger_candidates,
    _get_multibagger_universe,
    compute_multibagger_analysis,
)
from services.portfolio_engine import (
    _analyze_portfolio_positions,
    _portfolio_horizon_ranges,
)

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
    MacroEventsUpdateRequest, MonitoringEvent,
    UserSettingsUpdate,
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

    # Kite equity quote is the preferred live source (per Master Spec)
    data = await _fetch_kite_equity_core(symbol)
    if data is None:
        data = await get_stock_core(symbol)
    STOCK_CORE_CACHE[key] = {"ts": now, "data": data}
    return data


async def _fetch_kite_equity_core(symbol: str) -> dict | None:
    """
    Fetch live equity snapshot from Kite /quote API (primary source).
    Uses NSE:SYMBOL format — no instrument token required.
    Falls back to None so callers can use Moneycontrol/RapidAPI.
    """
    access_token = await _get_kite_access_token()
    if not access_token or not KITE_API_KEY:
        return None
    symbol_upper = symbol.upper().strip()
    # Indexes use a separate Kite endpoint — handled by _build_index_projection
    if symbol_upper in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}:
        return None

    def _fetch() -> dict | None:
        try:
            resp = requests.get(
                "https://api.kite.trade/quote",
                params=[("i", f"NSE:{symbol_upper}")],
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {KITE_API_KEY}:{access_token}",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            row = resp.json().get("data", {}).get(f"NSE:{symbol_upper}", {})
            if not row:
                return None
            ltp = _to_float(row.get("last_price"))
            if ltp is None or ltp <= 0:
                return None
            ohlc = row.get("ohlc") or {}
            return {
                "symbol": symbol_upper,
                "company_name": symbol_upper,
                "ltp": ltp,
                "open": _to_float(ohlc.get("open")),
                "high": _to_float(ohlc.get("high")),
                "low": _to_float(ohlc.get("low")),
                "prev_close": _to_float(ohlc.get("close")),  # Kite "close" = previous close
                "year_high": None,
                "year_low": None,
                "volume": int(_to_float(row.get("volume")) or 0),
                "market_cap": None,
                "pe_ratio": None,
                "book_value": None,
                "eps": None,
                "sector": "NSE",
            }
        except Exception:
            return None

    return await asyncio.to_thread(_fetch)


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
            # ── Mini-Batch: Use full F&O universe for option chain loading ──
            allowed = {"NIFTY", "BANKNIFTY", *get_fo_universe(lot_size_map=LOT_SIZE_MAP)}
            rows: list[dict] = []
            equity_rows: list[dict] = []
            for row in reader:
                exchange = str(row.get("exchange", "")).upper().strip()
                instrument_type = str(row.get("instrument_type", "")).upper().strip()
                tradingsymbol = str(row.get("tradingsymbol", "")).strip().upper()

                # Capture NSE equity tokens for Kite historical OHLCV (Data Failover)
                if exchange == "NSE" and instrument_type == "EQ" and tradingsymbol:
                    raw_token = row.get("instrument_token", "")
                    eq_token = None
                    try:
                        eq_token = int(float(str(raw_token).strip())) if raw_token else None
                    except (ValueError, TypeError):
                        eq_token = None
                    if eq_token:
                        equity_rows.append({"symbol": tradingsymbol, "instrument_token": eq_token})

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
            return rows, equity_rows
        except Exception as exc:
            logger.warning("Kite option master refresh failed: %s", exc)
            return [], []

    rows, equity_rows = await asyncio.to_thread(_load_rows)
    if not rows:
        return

    # Store F&O option contracts
    await db.kite_option_master.delete_many({})
    for start in range(0, len(rows), 5000):
        await db.kite_option_master.insert_many(rows[start : start + 5000], ordered=False)

    # Store NSE equity instrument tokens for historical OHLCV (Kite-first data policy)
    if equity_rows:
        await db.kite_equity_master.delete_many({})
        for start in range(0, len(equity_rows), 5000):
            await db.kite_equity_master.insert_many(equity_rows[start : start + 5000], ordered=False)
        logger.info("Kite equity master synced: %d equity tokens stored", len(equity_rows))

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
                _greeks = (row or {}).get("greeks") or {}
                rows[instrument] = {
                    "ltp": float(ltp),
                    "day_high": _to_float(ohlc.get("high")),
                    "day_low": _to_float(ohlc.get("low")),
                    "day_open": _to_float(ohlc.get("open")),
                    "oi": _to_float(row.get("oi")),
                    "oi_day_high": _to_float(row.get("oi_day_high")),
                    "oi_day_low": _to_float(row.get("oi_day_low")),
                    "volume": _to_float(row.get("volume")),
                    # Greeks — available for F&O instruments from Kite /quote
                    "iv": _to_float(_greeks.get("iv")),
                    "gamma": _to_float(_greeks.get("gamma")),
                    "delta": _to_float(_greeks.get("delta")),
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


def compute_option_chain_analytics(
    contracts: list,
    kite_map: dict[str, dict],
    underlying_ltp: float,
    step: int = 50,
) -> dict:
    """
    Pure Python computation of option chain analytics from live Kite OI/IV/Gamma data.
    All math strictly in Python — no LLM estimation, per Master Spec rule.

    Returns:
      max_pain  — Strike that minimises total option payout to buyers (₹ value)
      pcr       — Put/Call OI ratio
      iv_rank   — ATM IV percentile within current chain (0–100 proxy; no 52W history needed)
      gex       — Net gamma exposure (CE GEX − PE GEX), scaled; +ve = stabilising, −ve = amplifying
      oi_buildup — ATM CE OI change classification
    """
    ce_data: dict[float, dict] = {}
    pe_data: dict[float, dict] = {}

    for contract in contracts:
        snap = kite_map.get(contract.script if hasattr(contract, "script") else str(contract))
        if snap is None:
            continue
        strike = float(contract.strike if hasattr(contract, "strike") else 0)
        oi        = float(snap.get("oi")        or 0)
        ltp       = float(snap.get("ltp")       or 0)
        gamma     = float(snap.get("gamma")     or 0)
        iv        = float(snap.get("iv")        or 0)
        oi_open   = float(snap.get("oi_day_low") or oi)   # Lowest OI of day ≈ opening OI
        day_open  = float(snap.get("day_open")  or ltp)

        record = {"oi": oi, "ltp": ltp, "gamma": gamma, "iv": iv,
                  "oi_open": oi_open, "day_open": day_open}
        opt_type = contract.option_type if hasattr(contract, "option_type") else ""
        if opt_type == "CE":
            ce_data[strike] = record
        elif opt_type == "PE":
            pe_data[strike] = record

    all_strikes = sorted(set(list(ce_data.keys()) + list(pe_data.keys())))
    if not all_strikes:
        return {"max_pain": None, "pcr": None, "iv_rank": None, "gex": None, "oi_buildup": None}

    # 1. Max Pain — strike minimising total intrinsic-value payout to option buyers
    max_pain_strike = None
    min_pain_val = float("inf")
    for test_strike in all_strikes:
        total_pain = 0.0
        for s in all_strikes:
            # CE buyers profit when underlying > strike
            total_pain += max(0.0, test_strike - s) * ce_data.get(s, {}).get("oi", 0)
            # PE buyers profit when underlying < strike
            total_pain += max(0.0, s - test_strike) * pe_data.get(s, {}).get("oi", 0)
        if total_pain < min_pain_val:
            min_pain_val = total_pain
            max_pain_strike = test_strike

    # 2. PCR
    total_ce_oi = sum(d["oi"] for d in ce_data.values())
    total_pe_oi = sum(d["oi"] for d in pe_data.values())
    pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else None

    # 3. IV Rank (within-chain proxy; ATM IV vs chain min/max)
    atm_strike = round(underlying_ltp / max(step, 1)) * step
    atm_iv = max(
        ce_data.get(atm_strike, {}).get("iv", 0),
        pe_data.get(atm_strike, {}).get("iv", 0),
    )
    all_ivs = [d["iv"] for d in list(ce_data.values()) + list(pe_data.values()) if d["iv"] > 0]
    iv_rank: float | None = None
    if all_ivs and atm_iv > 0:
        iv_min, iv_max = min(all_ivs), max(all_ivs)
        iv_rank = round((atm_iv - iv_min) / (iv_max - iv_min) * 100, 1) if iv_max > iv_min else 50.0

    # 4. GEX — net gamma exposure (CE-side positive, PE-side negative convention)
    #    GEX_unit = gamma × OI; scale by spot² / 10M for human-readable number
    ce_gex_raw = sum(d["gamma"] * d["oi"] for d in ce_data.values() if d["gamma"] > 0)
    pe_gex_raw = sum(d["gamma"] * d["oi"] for d in pe_data.values() if d["gamma"] > 0)
    gex: float | None = None
    if ce_gex_raw > 0 or pe_gex_raw > 0:
        gex = round((ce_gex_raw - pe_gex_raw) * (underlying_ltp ** 2) / 10_000_000, 2)

    # 5. OI Buildup — ATM CE classification (OI change + price direction)
    oi_buildup: str | None = None
    atm_ce = ce_data.get(atm_strike, {})
    if atm_ce and atm_ce["oi"] > 0 and atm_ce["oi_open"] > 0:
        oi_chg_pct = (atm_ce["oi"] - atm_ce["oi_open"]) / atm_ce["oi_open"]
        price_chg_pct = (
            (atm_ce["ltp"] - atm_ce["day_open"]) / max(atm_ce["day_open"], 0.01)
            if atm_ce["day_open"] > 0 else 0.0
        )
        oi_up    = oi_chg_pct    > 0.02
        oi_down  = oi_chg_pct    < -0.02
        price_up = price_chg_pct > 0.01
        price_dn = price_chg_pct < -0.01
        if oi_up   and price_up: oi_buildup = "LONG_BUILDUP"
        elif oi_up   and price_dn: oi_buildup = "SHORT_BUILDUP"
        elif oi_down and price_up: oi_buildup = "SHORT_COVERING"
        elif oi_down and price_dn: oi_buildup = "LONG_UNWINDING"
        else: oi_buildup = "NEUTRAL"

    return {
        "max_pain":  float(max_pain_strike) if max_pain_strike is not None else None,
        "pcr":       pcr,
        "iv_rank":   iv_rank,
        "atm_iv":    round(atm_iv, 4) if atm_iv > 0 else None,
        "gex":       gex,
        "oi_buildup": oi_buildup,
    }


async def _fetch_kite_hist_ohlcv_for_equity(symbol: str, period: str = "1y") -> dict | None:
    """
    Fetch daily historical OHLCV from Kite for NSE equity instruments (Kite-first policy).
    Requires valid Kite access token + instrument token in kite_equity_master.
    Returns {'records': [...]} with open/high/low/close/volume dicts, or None.
    """
    access_token = await _get_kite_access_token()
    if not access_token or not KITE_API_KEY:
        return None

    token_row = await db.kite_equity_master.find_one(
        {"symbol": symbol.upper().strip()}, {"_id": 0, "instrument_token": 1}
    )
    if not token_row or not token_row.get("instrument_token"):
        # Token not cached → trigger sync and retry once
        await _sync_kite_option_master_daily()
        token_row = await db.kite_equity_master.find_one(
            {"symbol": symbol.upper().strip()}, {"_id": 0, "instrument_token": 1}
        )
    if not token_row or not token_row.get("instrument_token"):
        return None

    instrument_token = int(token_row["instrument_token"])
    period_days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
    days = period_days_map.get(period, 365)
    from_dt = datetime.now(timezone.utc) - timedelta(days=days)
    to_dt   = datetime.now(timezone.utc)

    def _fetch():
        try:
            url = (
                f"https://api.kite.trade/instruments/historical/{instrument_token}/day"
                f"?from={from_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
                f"&to={to_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
            )
            resp = requests.get(
                url,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {KITE_API_KEY}:{access_token}",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return None
            candles = resp.json().get("data", {}).get("candles", [])
            # Kite candle format: [datetime_str, open, high, low, close, volume]
            records = []
            for c in candles:
                if len(c) < 6:
                    continue
                records.append({
                    "date": str(c[0])[:10],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": int(c[5] or 0),
                })
            return {"records": records} if records else None
        except Exception as exc:
            logger.debug("Kite hist OHLCV failed for %s: %s", symbol, exc)
            return None

    return await asyncio.to_thread(_fetch)


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


# ── _analyze_micro_dip_prediction — extracted to services/ ──

# ── _portfolio_horizon_ranges — extracted to services/ ──


# ── _analyze_portfolio_positions — extracted to services/ ──
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
        *get_fo_universe(lot_size_map=LOT_SIZE_MAP),
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


# Auth dependencies are now in deps.py (shared with route modules)
from deps import get_current_user, get_admin_user, get_owner_user


# ─── India VIX ────────────────────────────────────────────────────────────────

async def _get_india_vix() -> float | None:
    """Fetch India VIX — Kite Connect only, with 5-minute cache."""
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = INDIA_VIX_CACHE.get("value")
    cached_ts = INDIA_VIX_CACHE.get("ts", 0.0)
    if cached is not None and (now_ts - cached_ts) < INDIA_VIX_CACHE_TTL_SECONDS:
        return float(cached)

    vix = None

    # ── PRIMARY (and sole source): Kite quote for India VIX ───────────────
    access_token = await _get_kite_access_token()
    if access_token and KITE_API_KEY:
        def _fetch_vix_kite() -> float | None:
            try:
                # India VIX instrument token on NSE is 264969 (standard)
                vix_tokens = ["NSE:INDIA VIX", "NSE:INDIAVIX"]
                for sym in vix_tokens:
                    resp = requests.get(
                        "https://api.kite.trade/quote/ltp",
                        params={"i": sym},
                        headers={
                            "X-Kite-Version": "3",
                            "Authorization": f"token {KITE_API_KEY}:{access_token}",
                        },
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        for key, val in data.items():
                            ltp = val.get("last_price")
                            if ltp and float(ltp) > 0:
                                return float(ltp)
                return None
            except Exception as exc:
                logger.debug("Kite VIX fetch failed: %s", exc)
                return None

        try:
            vix = await asyncio.wait_for(asyncio.to_thread(_fetch_vix_kite), timeout=8.0)
            if vix:
                logger.debug(f"India VIX from Kite: {vix:.1f}")
        except Exception:
            pass

    # No third-party fallback — Kite is the sole VIX source

    if vix is not None:
        INDIA_VIX_CACHE["value"] = vix
        INDIA_VIX_CACHE["ts"] = now_ts
    return vix


# ── Calendar Days helpers (theta decay over weekends/holidays) ───────────────

# ── _compute_initial_option_targets — extracted to services/ ──


# ── _compute_initial_option_sl — extracted to services/ ──

def _get_calendar_days_to_date(target_date_str: str) -> int:
    """Calendar days from today (IST) to date string. Includes weekends/holidays."""
    try:
        today = datetime.now(IST).date()
        target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        return max(0, (target - today).days)
    except Exception:
        return 0


def _get_calendar_days_for_nth_trading_day(n: int) -> int:
    """Calendar days until the nth TRADING day from today (includes non-trading gaps)."""
    try:
        from datetime import timedelta
        today = datetime.now(IST).date()
        count = 0
        current = today
        while count < max(n, 0):
            current += timedelta(days=1)
            if current.weekday() < 5 and current.isoformat() not in NSE_HOLIDAYS:
                count += 1
        return max(0, (current - today).days)
    except Exception:
        return max(n, 0)


# ── Batch A: Active Macro Events helper ──────────────────────────────────────

async def _get_active_macro_events() -> list[str]:
    """
    Read the currently active macro events from MongoDB (macro_config collection).
    Returns a list of event keys from SECTOR_MACRO_IMPACT_MAP.
    Admin can update via POST /admin/macro-events/update.
    """
    try:
        rec = await db["macro_config"].find_one({"config_id": "active_events"}, {"_id": 0})
        if rec and isinstance(rec.get("events"), list):
            # Filter to only valid known event keys
            valid = set(get_all_macro_events())
            return [e for e in rec["events"] if e in valid]
    except Exception as exc:
        logger.warning("Failed to read active macro events from DB: %s", exc)
    return []


# ── Batch C: Strategy Stats helper for threshold enforcement ─────────────────

async def _get_strategy_stats_for_selection() -> dict[str, dict]:
    """
    Load aggregated strategy backtest stats from MongoDB (strategy_backtest collection).
    Used by select_strategy_for_signal to enforce ≥75% win rate / ≥0.40R expectancy.
    Returns dict keyed by strategy_id.
    """
    try:
        records = await db.strategy_backtest.find({}, {"_id": 0}).to_list(length=500)
        # Aggregate by strategy_id (same logic as admin endpoint)
        agg: dict[str, dict] = {}
        for r in records:
            sid = r.get("strategy_id", "UNKNOWN")
            if sid not in agg:
                agg[sid] = {"wins": 0, "total_trades": 0, "total_r_multiple": 0.0, "disabled": False}
            agg[sid]["total_trades"] += 1
            if r.get("win"):
                agg[sid]["wins"] += 1
            agg[sid]["total_r_multiple"] += r.get("r_multiple", 0.0)
            if r.get("disabled"):
                agg[sid]["disabled"] = True
        stats_map: dict[str, dict] = {}
        for sid, s in agg.items():
            total = s["total_trades"]
            stats_map[sid] = {
                "win_rate": s["wins"] / total if total > 0 else 0.0,
                "expectancy": s["total_r_multiple"] / total if total > 0 else 0.0,
                "disabled": s["disabled"],
            }
        return stats_map
    except Exception as exc:
        logger.warning("Failed to load strategy stats for selection: %s", exc)
        return {}


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


# DISABLED — yfinance only. No Kite equivalent for fundamental scoring.
# USE_YFINANCE must remain false in production.
# Piotroski/Beneish scores are decorative/offline-research only.
# This function must NEVER influence live signals, validation, or backtests.
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

    # Fetch from yfinance (only if USE_YFINANCE=True; fundamental data has no Kite equivalent)
    data = {}
    if USE_YFINANCE:
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

    # Primary (and sole source): Kite historical API
    raw = await _fetch_kite_hist_ohlcv_for_equity(symbol, period)
    if not raw or not raw.get("records"):
        # No third-party fallback — Kite is the sole historical data source
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


# ── compute_multibagger_analysis — extracted to services/ ──
# ── _calculate_confluence_score_master_spec — extracted to services/ ──

# ── _get_signal_quality — extracted to services/ ──


# ── build_fno_signal — extracted to services/ ──


# ── _get_nearest_expiry — extracted to services/ ──


# ── _format_script — extracted to services/ ──


# ── _build_contract — extracted to services/ ──


# ── _resolve_contract_from_input — extracted to services/ ──


# ── _build_signal_for_contract — extracted to services/ ──


# ── _safe_signal — extracted to services/ ──


# ── _build_report — extracted to services/ ──


# ── _compute_report_from_rows — extracted to services/ ──


# ── _compute_enhanced_index_breadth — extracted to services/ ──



# ── _build_index_projection — extracted to services/ ──


# ── _infer_stock_option_type — extracted to services/ ──


# ── _build_stock_fno_signals — extracted to services/ ──


# ── _get_multibagger_universe — extracted to services/ ──


# ── _build_multibagger_candidates — extracted to services/ ──
def _build_monitoring_events(raw_events: list[dict]) -> list[MonitoringEvent]:
    """Convert raw monitoring event dicts (from MongoDB) to MonitoringEvent models."""
    result: list[MonitoringEvent] = []
    for evt in raw_events:
        details = {k: v for k, v in evt.items() if k not in _MONITORING_EVENT_COMMON_KEYS}
        result.append(MonitoringEvent(
            type=evt.get("type", ""),
            symbol=evt.get("symbol", ""),
            underlying=evt.get("underlying", ""),
            script=evt.get("script", ""),
            direction=evt.get("direction", ""),
            timestamp=evt.get("timestamp", ""),
            severity=evt.get("severity", "MEDIUM"),
            reason=evt.get("reason", ""),
            details=details,
        ))
    return result


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
        monitoring_events=_build_monitoring_events(position.get("monitoring_events", [])),
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
        # Ensure best_exit_price is never below the last known option LTP
        _last_known_ltp  = float(position.get("latest_option_ltp") or 0)
        _current_be      = float(position.get("best_exit_price") or 0)
        _entry_floor     = round(float(position.get("buy_price") or 0) * 1.01, 2)
        _corrected_be    = max(_current_be, _last_known_ltp, _entry_floor) if _last_known_ltp > 0 else _current_be
        _unavail_update: dict = {
            "alert": "LIVE_LTP_UNAVAILABLE",
            "lot_size": corrected_lot_size,
            "minutes_to_expiry": minutes_to_expiry,
            "last_update": _utc_now_iso(),
            "revised_exit_plan": "Live option feed unavailable; showing last confirmed option LTP.",
        }
        if _corrected_be > _current_be:
            _unavail_update["best_exit_price"] = _corrected_be
        updated = await db.custom_positions.find_one_and_update(
            {"id": position["id"]},
            {"$set": _unavail_update},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return updated
    buy_price = float(position["buy_price"])
    pnl_pct = ((latest_option_ltp - buy_price) / buy_price) if buy_price > 0 else 0.0
    revised_target1 = round(float(position.get("target1") or _compute_initial_option_targets(buy_price)["target1"]), 2)
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

    # EXPIRY-AWARE: detect if the option expires today (IST)
    _today_ist = datetime.now(IST).strftime("%Y-%m-%d")
    # Normalize: check both "expiry_date" and "expiry" fields; handle missing/malformed values
    _exp_raw = position.get("expiry_date") or position.get("expiry") or ""
    try:
        _exp_norm = datetime.strptime(str(_exp_raw), "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        _exp_norm = ""
    _expiry_is_today = (_exp_norm == _today_ist)

    if _expiry_is_today:
        # Same-day expiry: use session-sigma peak projection (NOT just current LTP)
        # Formula: entry + (1.5 × session_sigma × delta) − (0.5 × session_theta)
        best_exit_days = 0
        best_exit_date_str = "Today (Exit Before 3:30 PM)"
        try:
            _pos_entry_sd = float(position.get("buy_price") or 0)
            _pos_vix_sd = await _get_india_vix() if _pos_entry_sd > 0 else 15.0
            if _pos_entry_sd > 0:
                _und_sym_sd = (position.get("underlying") or
                               position.get("script", "").split("2")[0][:10])
                _und_ltp_sd = 0.0
                if _und_sym_sd:
                    try:
                        _und_core_sd = await _get_stock_core_cached(_und_sym_sd.upper())
                        _und_ltp_sd = float(_und_core_sd.get("ltp") or 0)
                    except Exception:
                        pass
                _now_sd = datetime.now(IST)
                _mkt_close_sd = _now_sd.replace(hour=15, minute=30, second=0, microsecond=0)
                _rem_sd = max(1, int((_mkt_close_sd - _now_sd).total_seconds() / 60)) if _now_sd < _mkt_close_sd else 1
                _frac_sd = min(_rem_sd / 375.0, 1.0)
                _vf_sd = 1.3 if _pos_vix_sd > 25 else (1.15 if _pos_vix_sd > 20 else (0.85 if _pos_vix_sd < 12 else 1.0))
                _atr_sd = max(_und_ltp_sd * 0.012, _pos_entry_sd * 0.05) if _und_ltp_sd > 0 else _pos_entry_sd * 0.05
                _ss_sd = _atr_sd * math.sqrt(_frac_sd) * _vf_sd
                _strike_sd = float(position.get("strike") or _pos_entry_sd)
                _type_sd = "CE" if "CE" in position.get("script", "").upper() else "PE"
                _delta_sd = 0.45
                if _und_ltp_sd > 0 and _strike_sd > 0:
                    _m_sd = _und_ltp_sd / _strike_sd if _type_sd == "CE" else _strike_sd / _und_ltp_sd
                    if _m_sd >= 1.08:   _delta_sd = 0.80
                    elif _m_sd >= 1.04: _delta_sd = 0.65
                    elif _m_sd >= 0.97: _delta_sd = 0.45
                    elif _m_sd >= 0.93: _delta_sd = 0.28
                    else:               _delta_sd = 0.15
                _theta_sd = (_pos_entry_sd * _vf_sd * 0.25 / math.sqrt(max(_frac_sd, 0.01))) * _frac_sd
                _peak_sd = _ss_sd * 1.5 * _delta_sd - _theta_sd * 0.5
                _peak_sd = max(_peak_sd, _pos_entry_sd * 0.02)
                _t2_sd = float(position.get("target2") or (_pos_entry_sd * 1.5))
                _raw_sd_exit = round(min(
                    _pos_entry_sd + _peak_sd,
                    _t2_sd * 1.10,
                    _pos_entry_sd * 2.0,
                ), 2)
                _ltp_floor = latest_option_ltp if (latest_option_ltp and latest_option_ltp > 0) else round(_pos_entry_sd * 1.01, 2)
                best_exit_price = max(_raw_sd_exit, _ltp_floor)
            elif latest_option_ltp and latest_option_ltp > 0:
                best_exit_price = latest_option_ltp
        except Exception:
            if latest_option_ltp and latest_option_ltp > 0:
                best_exit_price = latest_option_ltp
    elif remaining_trading_days >= 14:
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
        # ATR-based max LTP projection minus theta — same formula as build_fno_signal.
        # Best exit MUST be ≥ current LTP (never show an exit price below the live market).
        try:
            _pos_entry = float(position.get("buy_price") or 0)
            _pos_vix = await _get_india_vix()
            if _pos_entry > 0:
                # Fetch underlying LTP for moneyness-based delta estimation
                _und_sym = (position.get("underlying") or
                            position.get("script", "").split("2")[0][:10])
                _und_ltp = 0.0
                if _und_sym:
                    try:
                        _und_core = await _get_stock_core_cached(_und_sym.upper())
                        _und_ltp = float(_und_core.get("ltp") or 0)
                    except Exception:
                        pass

                # ATR proxy: 1.2% of underlying or 5% of option entry
                _pos_atr_proxy = (
                    max(_und_ltp * 0.012, _pos_entry * 0.05)
                    if _und_ltp > 0 else _pos_entry * 0.05
                )
                _pos_max_move = _pos_atr_proxy * math.sqrt(max(best_exit_days, 1)) * 2.0

                # Delta proxy from moneyness (same tiers as build_fno_signal)
                _pos_strike = float(position.get("strike") or _pos_entry)
                _pos_opt_type = "CE" if "CE" in position.get("script", "").upper() else "PE"
                _pos_be_delta = 0.45
                if _und_ltp > 0 and _pos_strike > 0:
                    _pos_mono = (
                        _und_ltp / _pos_strike if _pos_opt_type == "CE"
                        else _pos_strike / _und_ltp
                    )
                    if _pos_mono >= 1.08:   _pos_be_delta = 0.80
                    elif _pos_mono >= 1.04: _pos_be_delta = 0.65
                    elif _pos_mono >= 0.97: _pos_be_delta = 0.45
                    elif _pos_mono >= 0.93: _pos_be_delta = 0.28
                    else:                   _pos_be_delta = 0.15

                _pos_max_gain = _pos_max_move * _pos_be_delta * 1.2
                _pos_target2  = float(position.get("target2") or (_pos_entry * 1.5))
                max_ltp_projection = round(min(
                    _pos_entry + _pos_max_gain,
                    _pos_entry * 3.0,      # Hard cap: never > 3× entry
                    _pos_target2 * 1.20,   # Cap at 20% above stored T2
                ), 2)

                # Theta decay: same VIX-based calendar-day model as build_fno_signal
                _cal_to_expiry = (
                    _get_calendar_days_to_date(position["expiry"])
                    if position.get("expiry") else max(remaining_trading_days, 1)
                )
                _cal_to_best_exit = _get_calendar_days_for_nth_trading_day(best_exit_days)
                _pos_theta, _ = compute_vix_theta_decay(
                    entry_price=_pos_entry,
                    remaining_trading_days=remaining_trading_days,
                    best_exit_days=best_exit_days,
                    india_vix=_pos_vix,
                    calendar_days_to_expiry=_cal_to_expiry,
                    calendar_best_exit_days=_cal_to_best_exit,
                )
                # Final: best_exit ≥ current_ltp (never below live market price)
                _raw_best = round(max_ltp_projection - _pos_theta, 2)
                best_exit_price = max(_raw_best, latest_option_ltp, round(_pos_entry * 1.01, 2))
        except Exception:
            pass

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
            # Pass original targets to prevent compounding loop
            original_t1=float(position.get("original_target1") or 0),
            original_t2=float(position.get("original_target2") or 0),
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

    # ── Compute realistic 60-second optimal advised price ────────────────
    # Based on typical bid-ask spread width for NSE options at each price tier.
    # NOT a fixed percentage — this is the achievable sell price in the next 60 seconds.
    if latest_option_ltp < 15:
        _increment_60s = 0.20
    elif latest_option_ltp < 30:
        _increment_60s = 0.50
    elif latest_option_ltp < 60:
        _increment_60s = 1.00
    elif latest_option_ltp < 120:
        _increment_60s = 1.50
    elif latest_option_ltp < 200:
        _increment_60s = 2.00
    else:
        _increment_60s = round(latest_option_ltp * 0.007, 1)  # 0.7% for high-priced options
    optimal_advised_price = round(latest_option_ltp + _increment_60s, 2)

    if pnl_pct <= -0.35 and recovery_potential <= 0.14:
        alert = "EXIT_NOW_HIGH_LOSS"
        best_exit_price = optimal_advised_price
        revised_exit_plan = (
            f"URGENT EXIT: Loss >35% and recovery potential is weak "
            f"({recovery_potential * 100:.1f}%). Optimal exit near ₹{optimal_advised_price} "
            f"(max expected price in next 60 sec)."
        )
    elif minutes_to_expiry <= 15:
        alert = "EXIT_URGENT_TIME"
        best_exit_price = optimal_advised_price
        revised_exit_plan = (
            f"URGENT EXIT: <15 min to expiry. "
            f"Optimal liquidation price: ₹{optimal_advised_price} (60-sec window)."
        )
    elif pnl_pct <= -0.12:
        alert = "EXIT_URGENT_LOSS"
        best_exit_price = optimal_advised_price
        revised_exit_plan = (
            f"URGENT EXIT: Loss exceeded 12% from entry. "
            f"Exit now near ₹{optimal_advised_price}."
        )
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
    # ATR-based SL fallback: use stored SL if available, else estimate from buy_price ATR proxy
    _stored_sl = position.get("stop_loss")
    if _stored_sl and float(_stored_sl) > 0:
        _stop_loss_price = float(_stored_sl)
    else:
        # No stored SL: estimate using typical ATR proxy (12% of buy for ATM options)
        # This is NOT a fixed %; it approximates a 1.5-ATR SL for a typical option
        _stop_loss_price = round(float(buy_price) * 0.88, 2)
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

    # ── Batch 4: Position Monitoring & Alerts (Section 8) ─────────────────
    _monitoring_events: list[dict] = []
    _mon_state_snapshot: dict = {}
    try:
        _mon_underlying = position.get("underlying", "")
        _mon_vix = await _get_india_vix() or 15.0
        _mon_und_ltp = 0.0
        if _mon_underlying:
            try:
                _mon_core = await _get_stock_core_cached(_mon_underlying.upper())
                _mon_und_ltp = float(_mon_core.get("ltp") or 0)
            except Exception:
                pass

        # Regime classification (reuses existing service)
        _mon_regime = classify_regime_enhanced(
            india_vix=_mon_vix, realized_vol=None, adx=None,
        )

        # News sentiment (cached RSS feed, fast)
        _mon_news: dict = {}
        if _mon_underlying:
            try:
                _mon_news = get_symbol_sentiment(_mon_underlying)
            except Exception:
                pass

        # Flow band: default (live order book unavailable during position refresh)
        _mon_flow_band = "NeutralFlow"

        # Retrieve previous state snapshots for shift detection
        _mon_prev_regime = position.get("_mon_previous_regime")
        _mon_prev_news_flag = position.get("_mon_previous_news_flag", "NEUTRAL")
        _mon_orig_p_t1 = position.get("_mon_original_p_hit_t1")
        _mon_orig_p_t2 = position.get("_mon_original_p_hit_t2")

        # Current P_hit proxy from recovery_potential
        _mon_p_t1 = recovery_potential if recovery_potential is not None else None
        _mon_p_t2 = round(recovery_potential * 0.6, 4) if recovery_potential else None

        # Minutes to session close (15:30 IST)
        _mon_now = datetime.now(IST)
        _mon_close = _mon_now.replace(hour=15, minute=30, second=0, microsecond=0)
        _mon_mins = max(0, int((_mon_close - _mon_now).total_seconds() / 60))

        # P(recovery) heuristic: based on PnL direction and recovery_potential
        _mon_p_rec = None
        if pnl_pct < 0 and recovery_potential is not None:
            _mon_p_rec = min(recovery_potential * 2.0, 0.95) if recovery_potential > 0 else 0.05

        # Generate alert events via position_monitor engine
        _monitoring_events = generate_monitoring_alerts(
            position=position,
            current_ltp=latest_option_ltp,
            entry_price=buy_price,
            stop_loss=_stop_loss_price,
            minutes_remaining=_mon_mins,
            news_sentiment=_mon_news,
            previous_news_flag=_mon_prev_news_flag,
            current_regime=_mon_regime,
            previous_regime=_mon_prev_regime,
            current_p_hit_t1=_mon_p_t1,
            original_p_hit_t1=_mon_orig_p_t1,
            current_p_hit_t2=_mon_p_t2,
            original_p_hit_t2=_mon_orig_p_t2,
            p_recovery=_mon_p_rec,
            flow_band=_mon_flow_band,
        )

        # Build state snapshot for next refresh cycle
        _mon_state_snapshot = {
            "_mon_previous_regime": _mon_regime.get("regime"),
            "_mon_previous_news_flag": _mon_news.get("news_flag", "NEUTRAL"),
        }
        # Set original P_hit baselines on first observation
        if _mon_orig_p_t1 is None and _mon_p_t1 is not None:
            _mon_state_snapshot["_mon_original_p_hit_t1"] = _mon_p_t1
        if _mon_orig_p_t2 is None and _mon_p_t2 is not None:
            _mon_state_snapshot["_mon_original_p_hit_t2"] = _mon_p_t2

        # Verbose monitoring log (toggleable)
        if _monitoring_events and os.environ.get("MONITORING_LOG_VERBOSE", "1") == "1":
            for _mevt in _monitoring_events:
                logger.info(
                    "MONITOR [%s] %s %s | Sev=%s | %s",
                    _mevt.get("type"), _mevt.get("symbol"), _mevt.get("direction"),
                    _mevt.get("severity"), _mevt.get("reason", "")[:120],
                )
    except Exception as _mon_err:
        logger.debug("Position monitoring failed for %s: %s", position.get("id"), _mon_err)

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
                "monitoring_events": _monitoring_events,
                **_mon_state_snapshot,
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
        fno_budget=float(user.get("fno_budget", 500000)),
        account_risk_pct=float(user.get("account_risk_pct", 2.0)),
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
        fno_budget=float(current_user.get("fno_budget", 500000)),
        account_risk_pct=float(current_user.get("account_risk_pct", 2.0)),
    )


@api_router.patch("/auth/settings")
async def update_user_settings(
    payload: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update user's F&O trading settings (fno_budget, account_risk_pct)."""
    update_fields = {}
    if payload.fno_budget is not None:
        if payload.fno_budget < 0:
            raise HTTPException(status_code=400, detail="Budget must be non-negative")
        update_fields["fno_budget"] = payload.fno_budget
    if payload.account_risk_pct is not None:
        if not (0 < payload.account_risk_pct <= 100):
            raise HTTPException(status_code=400, detail="Risk % must be between 0 and 100")
        update_fields["account_risk_pct"] = payload.account_risk_pct
    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    await db.app_users.update_one(
        {"user_key": current_user["user_key"]},
        {"$set": update_fields},
    )
    updated = await _get_user_by_key(current_user["user_key"])
    return {
        "ok": True,
        "fno_budget": float(updated.get("fno_budget", 500000)),
        "account_risk_pct": float(updated.get("account_risk_pct", 2.0)),
    }



# ── Endpoints extracted to routes/ ── (removed 36 lines) ──

# ── Endpoints extracted to routes/ ── (removed 476 lines) ──

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




# ── Endpoints extracted to routes/ ── (removed 192 lines) ──


# ── Endpoints extracted to routes/ ── (removed 16 lines) ──

# ── Endpoints extracted to routes/ ── (removed 463 lines) ──


# ── Endpoints extracted to routes/ ── (removed 56 lines) ──

# ── Endpoints extracted to routes/ ── (removed 12 lines) ──

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

# ── Endpoints extracted to routes/ ── (removed 92 lines) ──

async def get_fno_contracts():
    return [FNOContract(**row) for row in FNO_CONTRACTS]



# ── Endpoints extracted to routes/ ── (removed 36 lines) ──


# ── Endpoints extracted to routes/ ── (removed 164 lines) ──

# ── Include extracted route modules ───────────────────────────────────────────
from routes.fno import fno_router
from routes.admin import admin_router
from routes.market_data import market_data_router
from routes.portfolio import portfolio_router
from routes.multibagger import multibagger_router
from routes.batch_jobs import batch_router
api_router.include_router(fno_router)
api_router.include_router(admin_router)
api_router.include_router(market_data_router)
api_router.include_router(portfolio_router)
api_router.include_router(multibagger_router)
api_router.include_router(batch_router, prefix="/batch")

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

    # ── One-time migration: backfill original_target1/original_target2 for existing positions
    # that were created before this field was added, to prevent the T2 compounding bug.
    # Also resets any positions whose T2 was corrupted by the bug (T2 > 3× buy_price).
    try:
        cursor = db.custom_positions.find(
            {"status": "OPEN"},
            {"_id": 0, "id": 1, "buy_price": 1, "target1": 1, "target2": 1, "original_target2": 1}
        )
        positions_to_check = await cursor.to_list(length=500)
        fixed_count = 0
        for pos in positions_to_check:
            bp = float(pos.get("buy_price") or 0)
            if bp <= 0:
                continue
            t2 = float(pos.get("target2") or 0)
            clean_targets = _compute_initial_option_targets(bp)
            clean_t1 = clean_targets["original_target1"]
            clean_t2 = clean_targets["original_target2"]
            clean_sl = _compute_initial_option_sl(bp)
            max_allowed = bp * 3.0
            orig_t2_stored = pos.get("original_target2")
            needs_update = (
                orig_t2_stored is None                         # Missing field
                or float(orig_t2_stored or 0) > max_allowed   # Corrupt stored original
                or t2 > max_allowed                            # Corrupt live target2
            )
            if needs_update:
                await db.custom_positions.update_one(
                    {"id": pos["id"]},
                    {"$set": {
                        "original_target1": clean_t1,
                        "original_target2": clean_t2,
                        # Also reset live target2 if it was corrupted
                        **({"target1": clean_t1, "target2": clean_t2, "stop_loss": clean_sl} if t2 > max_allowed else {}),
                    }}
                )
                fixed_count += 1
        if fixed_count:
            logger.info("Migrated/fixed original_target for %d positions (T2 compounding guard)", fixed_count)
    except Exception as exc:
        logger.warning("original_target migration failed (non-fatal): %s", exc)

    # ── Purge garbage custom positions created by testing/dev (buy_price=999999 or missing expiry_date)
    try:
        purge_result = await db.custom_positions.delete_many({
            "$or": [
                {"buy_price": {"$gte": 999000}},  # Test/garbage entries
                {"expiry_date": None},
                {"expiry_date": {"$exists": False}},
            ]
        })
        if purge_result.deleted_count:
            logger.info("Purged %d garbage custom positions (buy_price≥999000 or missing expiry_date)",
                        purge_result.deleted_count)
    except Exception as exc:
        logger.warning("Garbage position purge failed (non-fatal): %s", exc)

    # ── Batch 1 NEW: Seed index constituents DB table ────────────────────
    try:
        from services.index_constituents import _ensure_db_table as _seed_constituents
        await _seed_constituents(db)
        logger.info("Index constituents DB table seeded/verified")
    except Exception as exc:
        logger.warning("Index constituents seeding failed (non-fatal): %s", exc)

    # ── Batch 1 NEW: Prime news sentiment cache (background) ─────────────
    try:
        refresh_news_cache()
        logger.info("News sentiment cache primed on startup")
    except Exception as exc:
        logger.warning("News cache prime failed (non-fatal): %s", exc)

    # ── IV History indexes ────────────────────────────────────────────────
    try:
        await _ensure_iv_indexes(db)
    except Exception as exc:
        logger.warning("IV history index creation failed (non-fatal): %s", exc)

    # ── Regime History indexes ────────────────────────────────────────────
    try:
        from services.regime_engine import ensure_indexes as _ensure_regime_indexes
        await _ensure_regime_indexes(db)
    except Exception as exc:
        logger.warning("Regime history index creation failed (non-fatal): %s", exc)

    # ── Batch 2 NEW: MFE/MAE Library, Theta Curves, Forward MFE indexes ──
    try:
        from services.mfe_mae_engine import ensure_indexes as _ensure_mfe_indexes
        await _ensure_mfe_indexes(db)
    except Exception as exc:
        logger.warning("MFE/MAE index creation failed (non-fatal): %s", exc)

    # ── Batch 4 NEW: Sticky Cards, Popup Events indexes + news monitor ────
    try:
        from services.sticky_card_engine import ensure_indexes as _ensure_sticky_indexes
        await _ensure_sticky_indexes(db)
    except Exception as exc:
        logger.warning("Sticky card index creation failed (non-fatal): %s", exc)

    try:
        from services.sticky_card_engine import ensure_history_indexes as _ensure_hist_indexes
        await _ensure_hist_indexes(db)
    except Exception as exc:
        logger.warning("Signal history index creation failed (non-fatal): %s", exc)

    try:
        from services.iv_analytics import ensure_iv_analytics_indexes as _ensure_iv_an_indexes
        await _ensure_iv_an_indexes(db)
    except Exception as exc:
        logger.warning("IV analytics index creation failed (non-fatal): %s", exc)

    try:
        import asyncio as _aio
        from services.news_sentiment import start_continuous_monitor, stop_continuous_monitor
        from services.sticky_card_engine import get_watch_list_symbols

        async def _get_monitor_watch_list():
            return await get_watch_list_symbols(db)

        _monitor = _aio.create_task(
            start_continuous_monitor(_get_monitor_watch_list)
        )
        logger.info("News continuous monitor background task started")
    except Exception as exc:
        logger.warning("News continuous monitor start failed (non-fatal): %s", exc)


@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        from services.news_sentiment import stop_continuous_monitor
        stop_continuous_monitor()
    except Exception:
        pass
    await shutdown_holiday_manager()
    client.close()
