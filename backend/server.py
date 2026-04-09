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

# compute_option_chain_analytics — extracted to services/kite_client.py

# _position_in_range, get_minutes_to_expiry, _expiry_risk_bucket,
# get_remaining_trading_days, get_nth_trading_day_from_today
# extracted to services/date_utils.py (re-imported above)

def _normalize_symbol_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

# ── Script Master: extracted to services/script_master.py ──
from services.script_master import (  # noqa: F401
    _sync_script_master_daily,
    _resolve_symbol_input,
)

# Auth dependencies are now in deps.py (shared with route modules)
from deps import get_current_user, get_admin_user, get_owner_user

# ── India VIX: extracted to services/india_vix.py ──
from services.india_vix import _get_india_vix  # noqa: F401

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

# ── Hist OHLCV: extracted to services/hist_data.py ──
from services.hist_data import _get_hist_ohlcv  # noqa: F401

# ── Position Service: extracted to services/position_service.py ──
from services.position_service import (  # noqa: F401
    _build_monitoring_events,
    _position_to_response,
    _refresh_open_position,
)

@api_router.get("/")
async def root():
    return {"message": "AI Stock Research API"}

# ── Auth routes: extracted to routes/auth.py ──

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

@api_router.get("/fno/contracts")
async def get_fno_contracts():
    return [FNOContract(**row) for row in FNO_CONTRACTS]

# ── Include extracted route modules ───────────────────────────────────────────
from routes.fno import fno_router
from routes.admin import admin_router
from routes.market_data import market_data_router
from routes.portfolio import portfolio_router
from routes.multibagger import multibagger_router
from routes.batch_jobs import batch_router
from routes.auth import auth_router
api_router.include_router(fno_router)
api_router.include_router(admin_router)
api_router.include_router(market_data_router)
api_router.include_router(portfolio_router)
api_router.include_router(multibagger_router)
api_router.include_router(batch_router, prefix="/batch")
api_router.include_router(auth_router)

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
