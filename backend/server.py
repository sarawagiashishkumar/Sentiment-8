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

# ── Extracted service modules (Phase 2: kite_client, fundamental_data, user, validators) ──
from services.kite_client import (  # noqa: F401
    _get_kite_access_token,
    _fetch_kite_equity_core,
    _sync_kite_option_master_daily,
    _resolve_kite_lot_size_for_script,
    _resolve_verified_lot_size,
    _resolve_kite_instrument_for_contract,
    _fetch_option_snapshot_from_kite,
    _fetch_option_ltp_from_kite,
    _fetch_option_ltps_from_kite,
    _fetch_option_snapshots_from_kite,
    compute_option_chain_analytics,
    _fetch_kite_hist_ohlcv_for_equity,
    _fetch_live_option_snapshot,
    _fetch_live_option_ltp,
    _fetch_historical_candles_from_kite,
)
from services.fundamental_data import (  # noqa: F401
    _compute_piotroski_score_from_data,
    _compute_beneish_m_score_from_data,
    _fetch_yfinance_fundamentals,
    _get_fundamental_data,
)
from services.user_service import (  # noqa: F401
    _ensure_owner_exists,
    _get_user_by_key,
    _get_user_by_username,
    _get_user_by_ref,
    _is_owner,
    _is_admin,
    _is_credit_exempt,
    _consume_credits,
    _map_user_view,
)
from services.validators import (  # noqa: F401
    _validate_expiry_guard,
    _validate_username,
    _validate_domain,
    _split_domain_root_and_host,
    _normalize_target_record,
    _resolve_ipv4,
)
from services.multibagger_engine import _MONITORING_EVENT_COMMON_KEYS  # noqa: F401

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

# SYMBOL_HEADERS, AVG_HEADERS, QTY_HEADERS re-imported from services/position_parser.py above

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

# ── Re-exports from extracted modules (keep backward compat for `import server as _srv`) ──
from services.utils import (  # noqa: F401
    clamp, sanitize_float as _sanitize_float, utc_now_iso as _utc_now_iso,
    safe_ratio as _safe_ratio, estimate_option_ltp as _estimate_option_ltp,
    normalize_header as _normalize_header, to_float as _to_float,
    normalize_symbol_key as _normalize_symbol_key,
)
from services.date_utils import (  # noqa: F401
    today_ist as _today_ist, position_in_range as _position_in_range,
    get_minutes_to_expiry, expiry_risk_bucket as _expiry_risk_bucket,
    get_remaining_trading_days, get_nth_trading_day_from_today,
    get_calendar_days_to_date as _get_calendar_days_to_date,
    get_calendar_days_for_nth_trading_day as _get_calendar_days_for_nth_trading_day,
)


# ── Position parser extracted to services/position_parser.py ──
from services.position_parser import (  # noqa: F401
    SYMBOL_HEADERS, AVG_HEADERS, QTY_HEADERS,
    normalize_positions_from_rows as _normalize_positions_from_rows,
    extract_positions_from_text_lines as _extract_positions_from_text_lines,
    parse_positions_from_csv_text as _parse_positions_from_csv_text,
    parse_positions_from_excel_bytes as _parse_positions_from_excel_bytes,
    parse_positions_from_pdf_bytes as _parse_positions_from_pdf_bytes,
    parse_positions_from_image_bytes as _parse_positions_from_image_bytes,
    parse_positions_from_upload as _parse_positions_from_upload,
    _is_tesseract_ready, _find_column, _detect_qty_avg_orientation,
    _pick_avg_and_qty, _pil_image_to_bytes,
)



# _today_ist extracted to services/date_utils.py


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


# _fetch_kite_equity_core — extracted to services/kite_client.py


# _sync_kite_option_master_daily — extracted to services/kite_client.py


# _resolve_kite_lot_size_for_script, _resolve_verified_lot_size — extracted to services/kite_client.py


# _get_kite_access_token — extracted to services/kite_client.py


# _resolve_kite_instrument_for_contract — extracted to services/kite_client.py


# _fetch_option_snapshot_from_kite, _fetch_option_ltp_from_kite — extracted to services/kite_client.py


# _fetch_option_ltps_from_kite — extracted to services/kite_client.py


# _fetch_option_snapshots_from_kite — extracted to services/kite_client.py


# compute_option_chain_analytics — extracted to services/kite_client.py


# _fetch_kite_hist_ohlcv_for_equity — extracted to services/kite_client.py


# _fetch_live_option_snapshot, _fetch_live_option_ltp — extracted to services/kite_client.py


# _fetch_historical_candles_from_kite — extracted to services/kite_client.py


# ── _analyze_micro_dip_prediction — extracted to services/ ──

# ── _portfolio_horizon_ranges — extracted to services/ ──


# ── _analyze_portfolio_positions — extracted to services/ ──
# _position_in_range, get_minutes_to_expiry, _expiry_risk_bucket,
# get_remaining_trading_days, get_nth_trading_day_from_today
# extracted to services/date_utils.py (re-imported above)


# _validate_expiry_guard .. _resolve_ipv4 — extracted to services/validators.py


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


# _ensure_owner_exists — extracted to services/user_service.py


# _get_user_by_key, _get_user_by_username, _get_user_by_ref — extracted to services/user_service.py


# _is_owner, _is_admin, _is_credit_exempt — extracted to services/user_service.py


# _consume_credits — extracted to services/user_service.py


# _map_user_view — extracted to services/user_service.py


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

# _get_calendar_days_to_date, _get_calendar_days_for_nth_trading_day
# extracted to services/date_utils.py (re-imported above)


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
# _compute_piotroski_score_from_data, _compute_beneish_m_score_from_data,
# _fetch_yfinance_fundamentals, _get_fundamental_data — extracted to services/fundamental_data.py



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

@api_router.get("/fno/contracts")
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
