"""
F&O Signal Engine — Core signal building logic.

Extracted from server.py for modularity. All functions use lazy
`import server as _srv` for accessing server.py globals (db, IST,
market_data_client, etc.) to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any, Literal

from fastapi import HTTPException

# Context variables for per-request user settings (set in route handlers)
_ctx_user_budget = contextvars.ContextVar("user_budget", default=None)
_ctx_account_risk_pct = contextvars.ContextVar("account_risk_pct", default=None)

from models import (
    FNOContract,
    FNOSignalResponse,
    IndexAnalysisReport,
    IndexProjectionPane,
    NonDirectionalStrategy,
    StockCoreNormalized,
)
from services.indicators import (
    compute_atr_based_fno_targets,
    compute_historical_volatility,
)
from services.data_verifier import (
    compute_vix_theta_decay,
    get_minutes_to_session_close,
)
from services.mfe_mae_engine import (
    build_mfe_mae_library,
    build_probability_table,
    check_0dte_atm_safety,
    check_no_chasing_rule,
    compute_best_exit_online,
    select_targets_from_probability,
    select_targets_v2,
    get_cached_prob_table,
    get_cached_fwd_mfe,
    build_and_store_mfe_library,
    build_and_store_forward_mfe,
    _classify_dte_band,
    _classify_iv_regime,
)
from services.confluence_score_v2 import (
    compute_bucket_a,
    compute_bucket_b,
    compute_bucket_c,
    compute_bucket_d,
    compute_confluence_score_v2,
    CONFLUENCE_THRESHOLD,
)
from services.position_sizing import compute_position_size
from services.macro_context import (
    classify_market_regime_enhanced,
    compute_macro_context,
)
from services.intraday_features import (
    build_intraday_feature_vector,
    classify_regime_enhanced,
)
from services.strategy_library import select_strategy_for_signal
from services.news_sentiment import get_symbol_sentiment, get_sector_sentiment
from services.options_features import compute_enhanced_option_features
from services.technical_core import (
    compute_full_technical_snapshot,
    compute_historical_volatility,
    compute_technical_confluence_bonus,
)
from services.backtest_engine import (
    fetch_strategy_backtest,
    is_strategy_enabled as is_backtest_enabled,
)
from services.iv_history import capture_atm_iv, get_iv_stats_52w
from services.research_engine import (
    compute_index_constituent_bias,
    compute_weighted_breadth,
)
from services.constituent_engine import compute_breadth_metrics, shared_technical_pipeline
from services.regime_engine import regime_classify, store_regime
from services.options_features import compute_liquidity_flag, compute_pcr
from data.fno_contracts import get_fno_contract

logger = logging.getLogger(__name__)


# ── Server.py accessor (lazy import pattern) ──────────────────────────────────

def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


# ── Helper functions (copied from server.py to avoid circular imports) ────────

def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a value between lower and upper bounds."""
    return max(lower, min(upper, value))



# ── BATCH 1: Feature Wrapper Functions (Section 2+3 of Spec v2.0) ─────────────

async def compute_underlying_features(symbol: str) -> dict:
    """
    Compute underlying features per spec Section 3: UNDERLYING_FEATURES.
    Wraps shared_technical_pipeline and adds nearest support/resistance.
    """
    _s = _srv()

    pipeline = await shared_technical_pipeline(symbol)
    if not pipeline.get("available"):
        return {"symbol": symbol, "available": False}

    # Nearest support/resistance from recent swing highs/lows
    support, resistance = None, None
    try:
        ohlcv = await _s._get_hist_ohlcv(symbol, interval="day", candles=60)
        if ohlcv and ohlcv.get("highs") and ohlcv.get("lows"):
            highs = ohlcv["highs"]
            lows = ohlcv["lows"]
            closes = ohlcv["closes"]
            current = closes[-1] if closes else None
            if current:
                # Swing lows below current = support candidates
                recent_lows = sorted(set(lows[-20:]))
                supports = [l for l in recent_lows if l < current]
                if supports:
                    support = max(supports)  # nearest support below
                # Swing highs above current = resistance candidates
                recent_highs = sorted(set(highs[-20:]), reverse=True)
                resistances = [h for h in recent_highs if h > current]
                if resistances:
                    resistance = min(resistances)  # nearest resistance above
    except Exception:
        pass

    pipeline["nearest_support"] = round(support, 2) if support else None
    pipeline["nearest_resistance"] = round(resistance, 2) if resistance else None
    return pipeline


async def compute_option_features_full(
    option_snapshot: dict | None,
    underlying_ltp: float | None = None,
    strike: float | None = None,
    option_type: str = "CE",
    chain_ivs: list[float] | None = None,
    chain_data: list[dict] | None = None,
) -> dict:
    """
    Compute full option features per spec Section 3: OPTION_FEATURES.
    Wraps compute_enhanced_option_features and adds liquidity_flag + PCR.
    """
    from services.options_features import compute_enhanced_option_features

    features = compute_enhanced_option_features(
        option_snapshot, underlying_ltp, strike, option_type, chain_ivs,
    )
    if not features.get("available"):
        features["liquidity_flag"] = "ILLIQUID"
        features["pcr_series"] = None
        features["pcr_strike"] = None
        return features

    # Liquidity flag
    spread_pct = features.get("spread_data", {}).get("spread_pct")
    features["liquidity_flag"] = compute_liquidity_flag(
        spread_pct, features.get("volume", 0), features.get("oi", 0),
    )

    # PCR
    pcr = compute_pcr(chain_data, strike)
    features["pcr_series"] = pcr.get("pcr_series")
    features["pcr_strike"] = pcr.get("pcr_strike")

    return features


async def compute_order_flow_features(symbol: str) -> dict:
    """
    Compute order flow features per spec Section 3: ORDER_FLOW.
    Uses Kite order book depth for OBI and intraday bars for volume_delta.
    """
    _s = _srv()
    from services.intraday_features import (
        compute_order_book_imbalance,
        compute_volume_delta,
        classify_flow_band,
    )
    import pandas as pd

    result = {"symbol": symbol, "obi": 0.0, "volume_delta": 0.0, "flow_band": "NeutralFlow"}

    # OBI from Kite order book (if available)
    try:
        snapshot = await _s._fetch_live_option_snapshot(symbol)
        if snapshot:
            depth = snapshot.get("depth", {})
            buy_depths = depth.get("buy", [])
            sell_depths = depth.get("sell", [])
            bid_vols = [d.get("quantity", 0) for d in buy_depths[:5]]
            ask_vols = [d.get("quantity", 0) for d in sell_depths[:5]]
            obi_result = compute_order_book_imbalance(bid_vols, ask_vols)
            result["obi"] = obi_result.get("obi", 0.0)
            result["total_bid_volume"] = obi_result.get("total_bid_volume", 0)
            result["total_ask_volume"] = obi_result.get("total_ask_volume", 0)
    except Exception:
        pass

    # Volume delta from intraday bars
    try:
        ohlcv = await _s._get_hist_ohlcv(symbol, interval="minute", candles=60)
        if ohlcv and ohlcv.get("closes"):
            bars_df = pd.DataFrame({
                "Open": ohlcv["opens"],
                "Close": ohlcv["closes"],
                "Volume": ohlcv["volumes"],
            })
            vd = compute_volume_delta(bars_df)
            result["volume_delta"] = vd.get("volume_delta", 0.0)
            result["buy_volume"] = vd.get("buy_volume", 0)
            result["sell_volume"] = vd.get("sell_volume", 0)
    except Exception:
        pass

    # Classify flow band
    result["flow_band"] = classify_flow_band(
        result["obi"], result["volume_delta"],
    )

    return result


async def log_batch1_features(
    index_name: str,
    db,
    vix: float | None = None,
    adx: float | None = None,
    hv_20d: float | None = None,
) -> dict:
    """
    BATCH 1 LOG-ONLY: Compute and log all new feature layers for audit.
    Does NOT change scoring. Returns the full feature audit dict.
    """
    logger.info(f"[BATCH1-AUDIT] Computing features for {index_name}")

    # 1. Breadth metrics
    breadth = await compute_breadth_metrics(db, index_name)
    logger.info(
        f"[BATCH1-AUDIT] {index_name} breadth: score={breadth.get('breadth_score')}, "
        f"uptrend_wt={breadth.get('pct_weight_in_uptrend')}%, "
        f"vwap_wt={breadth.get('pct_weight_above_vwap')}%, "
        f"scanned={breadth.get('constituents_scanned')}"
    )

    # 2. Regime classification
    regime = regime_classify(
        india_vix=vix,
        realized_hv_20d=hv_20d,
        adx_14=adx,
        breadth_metrics=breadth,
    )
    logger.info(
        f"[BATCH1-AUDIT] {index_name} regime: {regime['regime_label']} "
        f"(VIX={regime['vix_value']}, ADX={regime['adx_value']}, "
        f"conf={regime['confidence']})"
    )

    # 3. Store regime for audit trail
    await store_regime(db, index_name, regime)

    # 4. Top contributors
    top_bull = breadth.get("top3_bullish", [])
    top_bear = breadth.get("top3_bearish", [])
    logger.info(
        f"[BATCH1-AUDIT] {index_name} top3 bullish: "
        f"{[c['symbol'] for c in top_bull]}"
    )
    logger.info(
        f"[BATCH1-AUDIT] {index_name} top3 bearish: "
        f"{[c['symbol'] for c in top_bear]}"
    )

    return {
        "index_name": index_name,
        "breadth": breadth,
        "regime": regime,
        "top3_bullish": top_bull,
        "top3_bearish": top_bear,
    }



# ── Scoring functions extracted to services/fno_confluence.py ──────────────
from services.fno_confluence import (  # noqa: E402, F401
    _compute_initial_option_targets,
    _compute_initial_option_sl,
    _calculate_confluence_score_master_spec,
    _get_signal_quality,
)



# ── Utility functions extracted to services/fno_utils.py ──────────────────
from services.fno_utils import (  # noqa: E402, F401
    _format_script,
    _compute_report_from_rows,
    _infer_stock_option_type,
    _analyze_micro_dip_prediction,
)



# ── Core signal builder extracted to services/fno_signal_builder.py ──────
from services.fno_signal_builder import build_fno_signal  # noqa: E402, F401

async def _get_nearest_expiry(underlying: str, prefer_monthly: bool = False) -> str:
    _s = _srv()
    IST = _s.IST
    market_data_client = _s.market_data_client
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


async def _build_contract(
    underlying: str,
    strike: float,
    option_type: Literal["CE", "PE"],
    prefer_monthly: bool = False,
) -> FNOContract:
    _s = _srv()
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP
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
    _s = _srv()
    IST = _s.IST
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP
    SCRIPT_PATTERN = _s.SCRIPT_PATTERN
    MONTH_MAP = _s.MONTH_MAP
    _resolve_symbol_input = _s._resolve_symbol_input
    get_stock_core = _s.get_stock_core
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


async def _build_signal_for_contract(contract: FNOContract, refreshed_at: str) -> FNOSignalResponse | None:
    _s = _srv()
    get_minutes_to_expiry = _s.get_minutes_to_expiry
    _validate_expiry_guard = _s._validate_expiry_guard
    _get_stock_core_cached = _s._get_stock_core_cached
    _fetch_live_option_snapshot = _s._fetch_live_option_snapshot
    _get_fundamental_data = _s._get_fundamental_data
    _to_float = _s._to_float
    minutes_to_expiry = get_minutes_to_expiry(contract)
    _validate_expiry_guard(minutes_to_expiry)
    stock_data = StockCoreNormalized(**(await _get_stock_core_cached(contract.underlying)))
    snapshot = await _fetch_live_option_snapshot(contract)
    option_ltp = float(snapshot.get("ltp"))
    # Fetch fundamental data for forensic scoring + macro sector context
    try:
        _fund_data = await _get_fundamental_data(contract.underlying)
    except Exception:
        _fund_data = {}
    return await build_fno_signal(
        contract,
        stock_data,
        option_ltp,
        refreshed_at,
        minutes_to_expiry,
        option_day_high=_to_float(snapshot.get("day_high")),
        option_day_low=_to_float(snapshot.get("day_low")),
        fundamental=_fund_data,
    )


async def _safe_signal(contract: FNOContract, refreshed_at: str, sem: asyncio.Semaphore) -> FNOSignalResponse | None:
    async with sem:
        try:
            return await _build_signal_for_contract(contract, refreshed_at)
        except Exception:
            return None


# ── Builders extracted to services/fno_builders.py for modularity ──────────
from services.fno_builders import (  # noqa: E402, F401
    _build_report,
    _compute_enhanced_index_breadth,
    _build_index_projection,
    _build_stock_fno_signals,
)
