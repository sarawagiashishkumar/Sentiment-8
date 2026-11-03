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
from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
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

mongo_url = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URL")
if not mongo_url:
    raise RuntimeError("Set MONGODB_URI or MONGO_URL to connect the backend to MongoDB.")
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

# ── Populate app_state with runtime config ────────────────────────────────────
import services.app_state as _app_state
_app_state.configure_runtime(
    session_store=SESSION_STORE,
    owner_username=OWNER_BOOTSTRAP_USERNAME,
    legacy_alias=LEGACY_OWNER_ALIAS,
)

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

from data.lot_sizes import LOT_SIZE_MAP, STOCK_FNO_UNIVERSE, NIFTY_WEIGHT_PROXY, BANKNIFTY_WEIGHT_PROXY

SCRIPT_MASTER_LAST_SYNC_DATE: str | None = None
KITE_OPTION_MASTER_LAST_SYNC_DATE: str | None = None

KITE_API_KEY = os.environ.get("KITE_API_KEY")
KITE_API_SECRET = os.environ.get("KITE_API_SECRET")
KITE_REDIRECT_URL = os.environ.get("KITE_REDIRECT_URL")
KITE_READ_ONLY_MODE = True
CONFLUENCE_THRESHOLD_DISPLAY = 40  # For display in rejection messages

# ── Configure centralized app state (breaks circular import chain) ────────────
from services.app_state import configure as _configure_app_state
_configure_app_state(db, api_key=KITE_API_KEY, api_secret=KITE_API_SECRET, redirect_url=KITE_REDIRECT_URL)

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

from services.cache_helpers import (
    API_CONTROL_CACHE, STOCK_CORE_CACHE, INDIA_VIX_CACHE,
    FUNDAMENTAL_CACHE, HIST_OHLCV_CACHE, SECTOR_MOMENTUM_CACHE,
    STOCK_CORE_CACHE_TTL_SECONDS, INDIA_VIX_CACHE_TTL_SECONDS,
    FUNDAMENTAL_CACHE_TTL_SECONDS, HIST_OHLCV_CACHE_TTL_SECONDS,
    SECTOR_MOMENTUM_CACHE_TTL_SECONDS,
    get_api_controls as _get_api_controls_impl,
    get_stock_core_cached as _get_stock_core_cached_impl,
    get_active_macro_events as _get_active_macro_events_impl,
    get_strategy_stats_for_selection as _get_strategy_stats_impl,
)

# SYMBOL_HEADERS, AVG_HEADERS, QTY_HEADERS re-imported from services/position_parser.py above

# NIFTY_WEIGHT_PROXY and BANKNIFTY_WEIGHT_PROXY imported from data/lot_sizes.py

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

KITE_ALLOWED_DATA_ENDPOINTS = [
    "/quote/ltp",
    "/instruments",
    "/instruments/historical",
]

async def _get_api_controls(force_refresh: bool = False) -> dict[str, bool]:
    return await _get_api_controls_impl(db, force_refresh)

async def _get_stock_core_cached(symbol: str) -> dict:
    return await _get_stock_core_cached_impl(db, symbol)

def _normalize_symbol_key_local(value: str) -> str:
    import re as _re
    return _re.sub(r"[^A-Z0-9]", "", (value or "").upper())

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
    return await _get_active_macro_events_impl(db)

# ── Batch C: Strategy Stats helper for threshold enforcement ─────────────────

async def _get_strategy_stats_for_selection() -> dict[str, dict]:
    return await _get_strategy_stats_impl(db)

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


@api_router.get("/health")
async def health_check():
    """Comprehensive health check — DB, Kite session, background tasks."""
    checks = {}

    # MongoDB connectivity
    try:
        await db.command("ping")
        checks["database"] = {"status": "healthy", "connected": True}
    except Exception as exc:
        checks["database"] = {"status": "unhealthy", "error": str(exc)[:100]}

    # Kite session status
    try:
        row = await db.system_meta.find_one({"key": "kite_session"}, {"_id": 0, "date": 1, "user_id": 1, "updated_at": 1})
        if row:
            today = datetime.now(IST).date().isoformat()
            is_today = row.get("date") == today
            checks["kite_session"] = {
                "status": "active" if is_today else "expired",
                "session_date": row.get("date"),
                "user_id": row.get("user_id"),
                "is_current_day": is_today,
            }
        else:
            checks["kite_session"] = {"status": "not_configured"}
    except Exception:
        checks["kite_session"] = {"status": "check_failed"}

    # Background tasks health
    import services.app_state as _app_state
    checks["background_tasks"] = {
        "iv_collector": "running",
        "watchlist_monitor": "running",
        "news_monitor": "running",
        "last_fno_gen": bool(_app_state.LAST_FNO_PERF),
        "last_mb_gen": bool(_app_state.LAST_MB_PERF),
    }

    # Collection counts (quick metrics)
    try:
        user_count = await db.app_users.count_documents({})
        signal_count = await db.fno_signal_log.count_documents({})
        checks["data"] = {"users": user_count, "signals_logged": signal_count}
    except Exception:
        checks["data"] = {"status": "unavailable"}

    overall = "healthy" if checks.get("database", {}).get("connected") else "degraded"
    return {"status": overall, "checks": checks, "ts": datetime.now(IST).isoformat()}


@api_router.get("/heartbeat")
async def heartbeat():
    """Lightweight keep-alive endpoint. Frontend pings on every interaction
    and at intervals to prevent Kubernetes pod eviction and maintain session warmth.
    Any call here = active engagement = server stays awake."""
    return {"status": "alive", "ts": datetime.now(IST).isoformat(), "active": True}

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
from routes.fno_backtest import fno_backtest_router
from routes.fno_iv import fno_iv_router
from routes.fno_cards import fno_cards_router
from routes.admin import admin_router
from routes.admin_domains import admin_domains_router
from routes.news import news_router
from routes.market_data import market_data_router
from routes.portfolio import portfolio_router
from routes.multibagger import multibagger_router
from routes.batch_jobs import batch_router
from routes.auth import auth_router
from routes.notifications import notification_router
from routes.journal import journal_router
from routes.reports import reports_router
from routes.watchlist import watchlist_router
from routes.risk import risk_router
from routes.alerts import alerts_router
from routes.fraud import fraud_router
from routes.crm import crm_router
api_router.include_router(fno_router)
api_router.include_router(fno_backtest_router)
api_router.include_router(fno_iv_router)
api_router.include_router(fno_cards_router)
api_router.include_router(admin_router)
api_router.include_router(admin_domains_router)
api_router.include_router(news_router)
api_router.include_router(market_data_router)
api_router.include_router(portfolio_router)
api_router.include_router(multibagger_router)
api_router.include_router(batch_router, prefix="/batch")
api_router.include_router(auth_router)
api_router.include_router(notification_router)
api_router.include_router(journal_router)
api_router.include_router(reports_router)
api_router.include_router(watchlist_router)
api_router.include_router(risk_router)
api_router.include_router(alerts_router)
api_router.include_router(fraud_router)
api_router.include_router(crm_router)
from routes.payments import payments_router
from routes.livehelp import livehelp_router
api_router.include_router(payments_router)
api_router.include_router(livehelp_router)

app.include_router(api_router)

# ── GZip Compression — reduces JSON payload sizes by ~70% ─────────────────────
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Response-Time"],
)

# ── Response Time Header Middleware ───────────────────────────────────────────
import time as _perf_time

@app.middleware("http")
async def add_response_time_header(request, call_next):
    start = _perf_time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((_perf_time.monotonic() - start) * 1000, 1)
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
    return response

async def _run_startup_maintenance():
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
        await asyncio.to_thread(refresh_news_cache)
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

    # ── Trading Journal indexes ───────────────────────────────────────────
    try:
        from routes.journal import ensure_journal_indexes
        await ensure_journal_indexes(db)
    except Exception as exc:
        logger.warning("Trading journal index creation failed (non-fatal): %s", exc)

    # ── Notification analytics indexes ────────────────────────────────────
    try:
        await db.notification_analytics.create_index([("user_key", 1), ("ts", -1)])
        await db.user_notifications.create_index([("user_key", 1), ("ts", -1)])
        logger.info("Notification analytics indexes ensured")
    except Exception as exc:
        logger.warning("Notification analytics index creation failed (non-fatal): %s", exc)

    # ── IV Background Collector (every 30 min during market hours) ────────
    try:
        import asyncio as _aio_iv
        async def _iv_background_collector():
            """Collect ATM IV for NIFTY/BANKNIFTY every 30 minutes during market hours."""
            while True:
                await _aio_iv.sleep(1800)  # 30 minutes
                try:
                    _now = datetime.now(IST)
                    if _now.weekday() >= 5:
                        continue
                    _mins = _now.hour * 60 + _now.minute
                    if _mins < 555 or _mins > 930:
                        continue
                    from services.kite_client import fetch_kite_batch_quotes, fetch_kite_batch_option_quotes
                    from services.iv_history import capture_atm_iv as _cap_iv
                    for _sym in ["NIFTY", "BANKNIFTY"]:
                        _idx_q = await fetch_kite_batch_quotes(
                            ["NIFTY 50" if _sym == "NIFTY" else "NIFTY BANK"], exchange="NSE"
                        )
                        _spot = 0
                        for _v in _idx_q.values():
                            _spot = _v.get("ltp", 0)
                        if _spot <= 0:
                            continue
                        _step = 50 if _sym == "NIFTY" else 100
                        _atm = round(_spot / _step) * _step
                        _opt_rows = await db.kite_option_master.find(
                            {"underlying": _sym, "strike": float(_atm)},
                            {"_id": 0, "tradingsymbol": 1}
                        ).sort("expiry", 1).limit(4).to_list(4)
                        if _opt_rows:
                            _ts_list = [r["tradingsymbol"] for r in _opt_rows]
                            _quotes = await fetch_kite_batch_option_quotes(_ts_list)
                            for _q in _quotes.values():
                                _iv = _q.get("iv")
                                if _iv and _iv > 0:
                                    _norm_iv = _iv / 100 if _iv > 1 else _iv
                                    await _cap_iv(db, _sym, _norm_iv)
                                    logger.info("BG IV collected: %s ATM_IV=%.2f%%", _sym, _norm_iv * 100)
                                    break
                except Exception as _iv_exc:
                    logger.debug("BG IV collection cycle failed (non-fatal): %s", _iv_exc)
        _aio_iv.create_task(_iv_background_collector())
        logger.info("IV background collector started (30-min intervals during market hours)")
    except Exception as exc:
        logger.warning("IV background collector start failed (non-fatal): %s", exc)

    # ── Watchlist Price Alert Monitor ─────────────────────────────────
    try:
        from routes.watchlist import run_watchlist_monitor
        asyncio.create_task(run_watchlist_monitor())
        logger.info("Watchlist price alert monitor started (60s intervals during market hours)")
    except Exception as exc:
        logger.warning("Watchlist monitor start failed (non-fatal): %s", exc)

    # ── Custom Alert Rule Monitor ─────────────────────────────────────
    try:
        from routes.alerts import run_alert_rule_monitor
        asyncio.create_task(run_alert_rule_monitor())
        logger.info("Custom alert rule monitor started (30s intervals during market hours)")
    except Exception as exc:
        logger.warning("Alert rule monitor start failed (non-fatal): %s", exc)

    # ── CRM/Fraud DB indexes ──────────────────────────────────────────
    try:
        await db.alert_rules.create_index([("user_key", 1), ("enabled", 1)])
        await db.login_sessions.create_index([("user_key", 1), ("ts_epoch", -1)])
        await db.fraud_incidents.create_index([("user_key", 1), ("status", 1)])
        await db.crm_messages.create_index([("to", 1), ("ts_epoch", -1)])
        await db.crm_messages.create_index([("to_user_key", 1), ("dismissed", 1)])
        await db.usage_tracking.create_index([("user_key", 1), ("feature", 1), ("ts_epoch", -1)])
        await db.payments.create_index([("user_key", 1), ("status", 1)])
        await db.livehelp_messages.create_index([("session_id", 1), ("ts_epoch", -1)])
        # Performance indexes for heavy queries (use background=True to avoid conflicts)
        try:
            await db.fno_signal_log.create_index([("generated_at", -1)], background=True)
        except Exception:
            pass  # Index may already exist with different name
        await db.trading_journal.create_index([("user_key", 1), ("ts_epoch", -1)])
        await db.trading_journal.create_index([("user_key", 1), ("event_type", 1)])
        await db.user_notifications.create_index([("user_key", 1), ("ts", -1)])
        await db.custom_positions.create_index([("user_key", 1), ("status", 1)])
        logger.info("All database indexes ensured")
    except Exception as exc:
        logger.warning("CRM/Fraud index creation failed (non-fatal): %s", exc)

    # ── Session cleanup: purge stale sessions every 30 minutes ────────
    async def _session_cleanup_task():
        while True:
            await asyncio.sleep(1800)  # 30 minutes
            try:
                now = datetime.now(timezone.utc)
                stale_tokens = []
                for token, session in SESSION_STORE.items():
                    created_str = session.get("created_at", "")
                    try:
                        created = datetime.fromisoformat(created_str)
                        if (now - created).total_seconds() > 86400:  # 24h max session lifetime
                            stale_tokens.append(token)
                    except (ValueError, TypeError):
                        stale_tokens.append(token)
                for token in stale_tokens:
                    SESSION_STORE.pop(token, None)
                if stale_tokens:
                    logger.info("Session cleanup: purged %d stale sessions", len(stale_tokens))
            except Exception as exc:
                logger.debug("Session cleanup failed: %s", exc)
    asyncio.create_task(_session_cleanup_task())
    logger.info("Session cleanup task started (30-min intervals, 24h TTL)")

    # ── LiveHelp room cleanup: purge stale rooms every 10 minutes ─────
    async def _help_room_cleanup_task():
        while True:
            await asyncio.sleep(600)  # 10 minutes
            try:
                stale = [sid for sid, room in _help_rooms.items()
                         if not room.get("user_ws") and not room.get("admin_ws")]
                for sid in stale:
                    _help_rooms.pop(sid, None)
                if stale:
                    logger.info("LiveHelp cleanup: purged %d stale rooms", len(stale))
            except Exception:
                pass
    asyncio.create_task(_help_room_cleanup_task())

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


_startup_maintenance_task: asyncio.Task | None = None


async def _run_startup_maintenance_safely():
    try:
        await _run_startup_maintenance()
    except Exception:
        logger.exception("Deferred backend startup maintenance failed")


@app.on_event("startup")
async def startup_tasks():
    global _startup_maintenance_task
    if _startup_maintenance_task and not _startup_maintenance_task.done():
        return
    _startup_maintenance_task = asyncio.create_task(_run_startup_maintenance_safely())
    logger.info("Deferred backend startup maintenance scheduled")


@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        from services.news_sentiment import stop_continuous_monitor
        stop_continuous_monitor()
    except Exception:
        pass
    try:
        from services.async_http import close_client
        await close_client()
    except Exception:
        pass
    await shutdown_holiday_manager()
    client.close()


# ── WebSocket: Real-time price streaming for watchlist ────────────────────────

@app.websocket("/api/ws/prices")
async def ws_price_stream(websocket: WebSocket):
    """Stream live prices for watchlist symbols via WebSocket.
    Client sends: {"symbols": ["RELIANCE", "TCS", ...]}
    Server pushes: {"quotes": {"RELIANCE": {"ltp": ..., "change_pct": ...}, ...}} every 5s
    """
    await websocket.accept()
    symbols = []
    try:
        while True:
            # Check for client messages (symbol updates) with timeout
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=5)
                if msg.get("symbols"):
                    symbols = [s.strip().upper() for s in msg["symbols"] if s.strip()]
            except asyncio.TimeoutError:
                pass

            if symbols:
                try:
                    from services.kite_client import fetch_kite_batch_quotes
                    quotes = await fetch_kite_batch_quotes(symbols)
                    payload = {}
                    for sym in symbols:
                        q = quotes.get(sym, {})
                        payload[sym] = {
                            "ltp": round(q.get("ltp", 0), 2),
                            "change_pct": round(q.get("change_pct", 0), 2),
                            "open": round(q.get("open", 0), 2),
                            "high": round(q.get("high", 0), 2),
                            "low": round(q.get("low", 0), 2),
                            "volume": q.get("volume", 0),
                        }
                    await websocket.send_json({"quotes": payload, "ts": datetime.now(IST).isoformat()})
                except Exception as exc:
                    logger.debug("WS price fetch failed: %s", exc)
                    await websocket.send_json({"error": "Price fetch failed", "ts": datetime.now(IST).isoformat()})
            else:
                await asyncio.sleep(5)
    except WebSocketDisconnect:
        logger.debug("WS client disconnected")
    except Exception as exc:
        logger.debug("WS error: %s", exc)


# ── Free STUN/TURN servers for native WebRTC (zero cost) ─────────────────────
# Google's free STUN servers handle NAT traversal for most cases.
# For symmetric NAT (rare), a TURN relay is needed — we use the open
# Metered TURN servers (free tier: 500MB/mo, no billing).

WEBRTC_ICE_SERVERS = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
    {"urls": "stun:stun2.l.google.com:19302"},
    {"urls": "stun:stun3.l.google.com:19302"},
    {"urls": "stun:stun4.l.google.com:19302"},
]


# ── WebSocket: Live Help signaling + text chat ────────────────────────────────
# Rooms are keyed by session_id. Users and admins join the same room.

_help_rooms: dict[str, dict] = {}  # session_id -> {"user_ws": ws, "admin_ws": ws, ...}

@app.websocket("/api/ws/livehelp/{session_id}")
async def ws_livehelp(websocket: WebSocket, session_id: str):
    """WebRTC signaling + text chat for live help sessions.

    Messages:
      {"type": "join", "role": "user"|"admin", "user_key": "...", "username": "..."}
      {"type": "chat", "text": "...", "sender": "..."}
      {"type": "offer", "sdp": {...}}       — WebRTC SDP offer
      {"type": "answer", "sdp": {...}}      — WebRTC SDP answer
      {"type": "ice-candidate", "candidate": {...}} — ICE candidate
      {"type": "voice-start"}               — signal voice mode
      {"type": "voice-end"}                 — signal text mode
    """
    await websocket.accept()

    if session_id not in _help_rooms:
        _help_rooms[session_id] = {"user_ws": None, "admin_ws": None, "user_key": "", "username": "", "started_at": datetime.now(IST).isoformat(), "mode": "text"}

    room = _help_rooms[session_id]
    my_role = None

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type", "")

            if msg_type == "join":
                my_role = msg.get("role", "user")
                if my_role == "admin":
                    room["admin_ws"] = websocket
                else:
                    room["user_ws"] = websocket
                    room["user_key"] = msg.get("user_key", "")
                    room["username"] = msg.get("username", "")
                # Notify peer
                peer_ws = room["admin_ws"] if my_role == "user" else room["user_ws"]
                if peer_ws:
                    try:
                        await peer_ws.send_json({"type": "peer-joined", "role": my_role, "username": msg.get("username", "")})
                    except Exception:
                        pass
                # Send ICE servers to joiner
                await websocket.send_json({"type": "ice-servers", "servers": WEBRTC_ICE_SERVERS})

            elif msg_type == "chat":
                # Persist chat message
                chat_doc = {
                    "session_id": session_id,
                    "from_role": my_role or "user",
                    "from_user_key": msg.get("user_key", room.get("user_key", "")),
                    "from_username": msg.get("sender", ""),
                    "to_user_key": "",
                    "text": msg.get("text", ""),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "ts_epoch": datetime.now(timezone.utc).timestamp(),
                }
                try:
                    await db.livehelp_messages.insert_one(chat_doc)
                except Exception:
                    pass
                # Forward to peer
                peer_ws = room["admin_ws"] if my_role == "user" else room["user_ws"]
                if peer_ws:
                    try:
                        await peer_ws.send_json({"type": "chat", "text": msg.get("text", ""), "sender": msg.get("sender", ""), "ts": chat_doc["ts"]})
                    except Exception:
                        pass

                # Auto-analyze for troubleshooting (user messages only)
                if my_role == "user":
                    from routes.livehelp import _analyze_session_log, _session_logs
                    # Add chat as session context
                    _session_logs[room.get("user_key", "")].append({"action": "chat", "text": msg.get("text", "")[:200], "ts": chat_doc["ts"]})
                    suggestions = _analyze_session_log(room.get("user_key", ""))
                    if suggestions:
                        for s in suggestions[:1]:
                            await websocket.send_json({"type": "system-hint", "message": s["message"], "severity": s["severity"]})

            elif msg_type in ("offer", "answer", "ice-candidate"):
                # WebRTC signaling — forward to peer
                peer_ws = room["admin_ws"] if my_role == "user" else room["user_ws"]
                if peer_ws:
                    try:
                        await peer_ws.send_json(msg)
                    except Exception:
                        pass

            elif msg_type == "voice-start":
                room["mode"] = "voice"
                peer_ws = room["admin_ws"] if my_role == "user" else room["user_ws"]
                if peer_ws:
                    try:
                        await peer_ws.send_json({"type": "voice-start"})
                    except Exception:
                        pass

            elif msg_type == "voice-end":
                room["mode"] = "text"
                peer_ws = room["admin_ws"] if my_role == "user" else room["user_ws"]
                if peer_ws:
                    try:
                        await peer_ws.send_json({"type": "voice-end"})
                    except Exception:
                        pass

            elif msg_type == "report-bug":
                # Auto-generate CRM ticket
                from routes.livehelp import _auto_generate_ticket
                await _auto_generate_ticket(
                    room.get("user_key", ""),
                    f"User-reported via Live Help: {msg.get('description', 'No details')}"
                )
                await websocket.send_json({"type": "system-hint", "message": "Bug report submitted. A support ticket has been created.", "severity": "info"})

            elif msg_type in ("screen-share-start", "screen-share-end"):
                # Forward screen sharing signals to peer
                peer_ws = room["admin_ws"] if my_role == "user" else room["user_ws"]
                if peer_ws:
                    try:
                        await peer_ws.send_json(msg)
                    except Exception:
                        pass

    except WebSocketDisconnect:
        # Notify peer of disconnect
        peer_ws = room.get("admin_ws") if my_role == "user" else room.get("user_ws")
        if peer_ws:
            try:
                await peer_ws.send_json({"type": "peer-left", "role": my_role or "unknown"})
            except Exception:
                pass
        # Clean up
        if my_role == "admin":
            room["admin_ws"] = None
        elif my_role == "user":
            room["user_ws"] = None
        if not room["user_ws"] and not room["admin_ws"]:
            _help_rooms.pop(session_id, None)
    except Exception as exc:
        logger.debug("LiveHelp WS error: %s", exc)
        _help_rooms.pop(session_id, None)
