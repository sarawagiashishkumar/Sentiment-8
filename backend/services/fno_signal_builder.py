"""
F&O Signal Builder — Core build_fno_signal function.

Extracted from fno_signal_engine.py for modularity.
Contains the massive build_fno_signal() async function which:
  - Fetches underlying features, option features, order flow
  - Runs confluence scoring
  - Computes targets, SL, position sizing
  - Returns FNOSignalResponse
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Literal

from models import (
    FNOContract,
    FNOSignalResponse,
    StockCoreNormalized,
)

from services.fno_confluence import (
    _compute_initial_option_targets,
    _compute_initial_option_sl,
    _calculate_confluence_score_master_spec,
    _get_signal_quality,
    clamp,
)
from services.fno_utils import _infer_stock_option_type, _analyze_micro_dip_prediction
from services.technical_core import compute_full_technical_snapshot
from services.mfe_mae_engine import get_cached_prob_table, get_cached_fwd_mfe
from services.backtest_engine import fetch_strategy_backtest
from services.iv_history import capture_atm_iv, get_iv_stats_52w
from services.confluence_score_v2 import CONFLUENCE_THRESHOLD, is_actionable_fno_signal

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module."""
    import server
    return server


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
    # ── Batch A: fundamental data for macro context & forensic confluence ──
    fundamental: dict | None = None,
    # ── Option chain analytics (Max Pain, IV Rank, GEX, OI Buildup) ────────
    max_pain: float | None = None,
    iv_rank: float | None = None,
    iv_rank_52w: float | None = None,
    atm_iv: float | None = None,
    oi_buildup: str | None = None,
    gex: float | None = None,
) -> FNOSignalResponse:
    import time as _time
    _phase_timings = {}
    _fn_start = _time.monotonic()
    _s = _srv()
    IST = _s.IST
    _position_in_range = _s._position_in_range
    _fetch_historical_candles_from_kite = _s._fetch_historical_candles_from_kite
    _get_strategy_stats_for_selection = _s._get_strategy_stats_for_selection
    _get_active_macro_events = _s._get_active_macro_events
    _get_hist_ohlcv = _s._get_hist_ohlcv
    get_remaining_trading_days = _s.get_remaining_trading_days
    get_nth_trading_day_from_today = _s.get_nth_trading_day_from_today
    _get_calendar_days_to_date = _s._get_calendar_days_to_date
    _get_calendar_days_for_nth_trading_day = _s._get_calendar_days_for_nth_trading_day
    _expiry_risk_bucket = _s._expiry_risk_bucket
    db = _s.db
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
                trigger_factors.append("VeryCheapCE")
            elif contract.option_type == "PE" and option_ltp < underlying_ltp * 0.04:
                direction = "BEARISH"
                trigger_factors.append("VeryCheapPE")
            else:
                direction = "NEUTRAL"
    else:
        direction = "NEUTRAL"

    entry_price = round(option_ltp, 2)
    
    # Skip historical candle fetch after market hours (saves 100s+ due to Kite timeouts)
    _now_check = datetime.now(_s.IST)
    _is_live_market = (
        _now_check.weekday() < 5
        and (_now_check.hour > 9 or (_now_check.hour == 9 and _now_check.minute >= 15))
        and (_now_check.hour < 15 or (_now_check.hour == 15 and _now_check.minute <= 30))
    )
    candles = None
    if _is_live_market:
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


    # ── Batch 5: Strategy Library Selection (Batch C: with threshold enforcement) ─
    _vix_curr = india_vix
    _adx_curr = tech_adx
    _rsi_curr = tech_rsi
    _regime_obj = classify_market_regime_enhanced(
        vix=_vix_curr, adx=_adx_curr, rsi=_rsi_curr
    )
    _regime = _regime_obj.get("regime", "NORMAL_VOL_TREND")
    # ── Parallel fetch: strategy stats + macro events (independent operations) ──
    _phase_t0 = _time.monotonic()
    _strategy_stats_data, _active_events = await asyncio.gather(
        _get_strategy_stats_for_selection(),
        _get_active_macro_events(),
        return_exceptions=True,
    )
    if isinstance(_strategy_stats_data, BaseException):
        _strategy_stats_data = None
    if isinstance(_active_events, BaseException):
        _active_events = []
    _phase_timings["parallel_fetch_strategy_macro_ms"] = round((_time.monotonic() - _phase_t0) * 1000, 1)

    _selected_strategy = select_strategy_for_signal(
        regime=_regime,
        direction=direction,
        adx=_adx_curr,
        vix=_vix_curr,
        instrument=contract.underlying,
        strategy_stats=_strategy_stats_data if _strategy_stats_data else None,
    )
    # Enforce Master Spec Rule: block signal if backtest data shows no qualifying strategy.
    # Only apply when ≥10 backtested trades exist to make a reliable determination.
    if _selected_strategy is None:
        _sufficient_backtest = any(
            s.get("total_trades", 0) >= 10 for s in (_strategy_stats_data or {}).values()
        )
        if _sufficient_backtest:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Signal blocked: no strategy passes ≥75% win-rate / ≥0.40R expectancy "
                    f"for {direction} in {_regime} regime. "
                    "Add more backtest records or re-evaluate active strategies."
                ),
            )
        # Insufficient data — allow provisionally with built-in default
        _strategy_name = "Standard"
        _strategy_id = "S3_SUPERTREND"
    else:
        _strategy_name = _selected_strategy.get("name", "Standard")
        _strategy_id = _selected_strategy.get("id", "S3_SUPERTREND")
        trigger_factors.append(f"Strategy:{_strategy_id}")
        trigger_factors.append(f"Regime:{_regime}")

    # ── Batch 4: Macro Context (uses pre-fetched _active_events) ─────────
    _sector_str = fundamental.get("sector") if fundamental else None
    _macro_ctx: dict = {}
    try:
        _macro_ctx = compute_macro_context(
            active_events=_active_events if isinstance(_active_events, list) else [],
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
        elif macro_bias == "TAILWIND" and direction == "BEARISH":
            trigger_factors.append(f"MacroTailwind_vs_Bearish:{_sector_str}")
    except Exception:
        pass

    # ── Batch 1 NEW: Enhanced regime classification ───────────────────────
    _has_event = bool(_macro_ctx.get("macro_bias") == "HEADWIND")
    _hv_from_snap = ts.get("hist_vol") if ts else None
    _enhanced_regime = classify_regime_enhanced(
        india_vix=india_vix,
        realized_vol=_hv_from_snap,
        adx=_adx_curr,
        has_upcoming_event=_has_event,
    )
    trigger_factors.append(f"RegimeV2:{_enhanced_regime.get('regime', 'LowVolRange')}")

    # ── Batch 1 NEW: News sentiment for underlying ───────────────────────
    _news_sentiment: dict = {}
    try:
        _news_sentiment = get_symbol_sentiment(contract.underlying)
        _news_flag = _news_sentiment.get("news_flag", "NEUTRAL")
        if _news_flag != "NEUTRAL":
            trigger_factors.append(f"News:{_news_flag}(n={_news_sentiment.get('news_count', 0)})")
    except Exception as _ne:
        logger.debug(f"News sentiment failed for {contract.underlying}: {_ne}")

    # ── Batch 1 NEW: Sector sentiment ────────────────────────────────────
    _sector_sentiment: dict = {}
    if _sector_str:
        try:
            _sector_sentiment = get_sector_sentiment(_sector_str)
            _sec_flag = _sector_sentiment.get("news_flag", "NEUTRAL")
            if _sec_flag != "NEUTRAL":
                trigger_factors.append(f"SectorNews:{_sec_flag}")
        except Exception:
            pass

    # ── Batch 1 NEW: Intraday features (compute & log, NOT scoring yet) ──
    _intraday_features: dict = {}
    try:
        _intraday_features = build_intraday_feature_vector(
            symbol=contract.underlying,
            bars_daily=None,
            bars_intraday=None,
            regime=_enhanced_regime,
        )
        _flow = _intraday_features.get("flow_band", "NeutralFlow")
        if _flow != "NeutralFlow":
            trigger_factors.append(f"Flow:{_flow}")
    except Exception as _fe:
        logger.debug(f"Intraday features failed for {contract.underlying}: {_fe}")

    # ── Batch 1 NEW: Enhanced option features (compute & log) ────────────
    _enhanced_opt_features: dict = {}
    try:
        _opt_snap = {"ltp": option_ltp, "oi": 0, "iv": None}
        _enhanced_opt_features = compute_enhanced_option_features(
            option_snapshot=_opt_snap,
            underlying_ltp=float(underlying_ltp),
            strike=float(contract.strike),
            option_type=contract.option_type,
        )
        _mono_label = _enhanced_opt_features.get("moneyness", "UNKNOWN")
        if _mono_label != "UNKNOWN":
            trigger_factors.append(f"Moneyness:{_mono_label}")
    except Exception:
        pass

    # ── Batch 5: Constituent-weighted NIFTY/BANKNIFTY breadth (Action 5) ──
    _index_breadth: dict = {}
    if contract.underlying in ("NIFTY", "BANKNIFTY"):
        try:
            from services.fno_builders import _compute_enhanced_index_breadth
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
        strike=float(contract.strike),
    )
    
    # ── Stop Loss: ATR-based, NOT a fixed % of entry ──────────────────────────
    _atr_proxy = underlying_atr or (float(underlying_ltp) * 0.012)
    _delta_proxy = 0.45
    if contract.strike and float(underlying_ltp) > 0:
        _sl_mono = (float(underlying_ltp) / float(contract.strike)
                    if contract.option_type == "CE"
                    else float(contract.strike) / float(underlying_ltp))
        if _sl_mono >= 1.08:    _delta_proxy = 0.80
        elif _sl_mono >= 1.04:  _delta_proxy = 0.65
        elif _sl_mono >= 0.97:  _delta_proxy = 0.45
        elif _sl_mono >= 0.93:  _delta_proxy = 0.28
        else:                   _delta_proxy = 0.15
    _atr_sl_dist = max(entry_price * 0.07, min(_atr_proxy * _delta_proxy * 1.5, entry_price * 0.25))
    stop_loss = max(round(entry_price - _atr_sl_dist, 2), round(entry_price * 0.01, 2))

    # ── Expiry-today flag (moved early — used by MFE, 0DTE, and target caps) ──
    _today_ist = datetime.now(IST).strftime("%Y-%m-%d")
    _is_expiry_today = (contract.expiry == _today_ist) if contract.expiry else False

    # ── Batch 2: MFE/MAE probability-based target refinement (cache-first) ──
    # First try MongoDB cached library, then compute on-the-fly as fallback.
    _prob_targets: dict = {}
    _mfe_library: list = []
    _hist_for_mfe = None
    _prob_table = None
    _dte_for_mfe = 0 if _is_expiry_today else max(get_remaining_trading_days(contract.expiry), 1)
    _iv_for_mfe = (_enhanced_opt_features or {}).get("iv") or india_vix
    _theta_daily_for_v2 = 0.0
    try:
        _s = _srv()
        db = _s.db

        # Step 1: Try cached probability table from MongoDB
        _cached_pt = await get_cached_prob_table(
            db, contract.underlying, _strategy_id, _dte_for_mfe, _iv_for_mfe,
        )
        if _cached_pt:
            _prob_table = _cached_pt
            trigger_factors.append("MFE:cached")
        else:
            # Step 2: Compute on-the-fly and persist for next time
            _hist_for_mfe = await _get_hist_ohlcv(contract.underlying, period="1y")
            if _hist_for_mfe is not None and not _hist_for_mfe.empty and len(_hist_for_mfe) >= 100:
                _atr_for_mfe = underlying_atr or (float(underlying_ltp) * 0.012)
                _sl_dist_pct = ((entry_price - stop_loss) / entry_price) * 100
                # Build and persist
                _build_result = await build_and_store_mfe_library(
                    db, contract.underlying, _hist_for_mfe, _atr_for_mfe,
                    strategy_id=_strategy_id,
                    dte=_dte_for_mfe,
                    iv=_iv_for_mfe,
                    sl_distance_pct=max(_sl_dist_pct, 5.0),
                )
                if _build_result.get("stored"):
                    _cached_pt = await get_cached_prob_table(
                        db, contract.underlying, _strategy_id, _dte_for_mfe, _iv_for_mfe,
                    )
                    if _cached_pt:
                        _prob_table = _cached_pt
                        trigger_factors.append("MFE:computed")
                else:
                    # Fallback: inline compute without persistence
                    _mfe_library = build_mfe_mae_library(
                        hist_df=_hist_for_mfe,
                        atr=_atr_for_mfe,
                        strategy_id=_strategy_id,
                        direction="LONG",
                        window_bars=min(75, len(_hist_for_mfe) // 4),
                    )
                    if _mfe_library and len(_mfe_library) >= 20:
                        _prob_table = build_probability_table(
                            _mfe_library,
                            sl_distance_pct=max(_sl_dist_pct, 5.0),
                        )

        # Step 3: Use select_targets_v2 for consolidated target selection
        _flow_band_v2 = _intraday_features.get("flow_band", "NeutralFlow") if _intraday_features else "NeutralFlow"
        _regime_label_v2 = _enhanced_regime.get("regime", "LowVolRange") if _enhanced_regime else "LowVolRange"
        _dte_band_v2 = _classify_dte_band(_dte_for_mfe)
        _iv_regime_v2 = _classify_iv_regime(_iv_for_mfe)

        # Determine time-of-day band
        _mins_to_close = get_minutes_to_session_close()
        if _mins_to_close > 300:
            _tod_band = "EARLY_SESSION"
        elif _mins_to_close > 120:
            _tod_band = "MID_SESSION"
        else:
            _tod_band = "LATE_SESSION"

        # Get theta estimate for target adjustment
        try:
            _opt_class_v2 = "index_weekly" if contract.underlying in ("NIFTY", "BANKNIFTY") else "stock_monthly"
            _mono_v2 = (_enhanced_opt_features or {}).get("moneyness", "ATM")
            from services.mfe_mae_engine import get_cached_theta, compute_empirical_theta
            _theta_cached = await get_cached_theta(db, _opt_class_v2, _mono_v2, _iv_regime_v2, _dte_for_mfe)
            if _theta_cached:
                _theta_daily_for_v2 = _theta_cached.get("total_theta", 0)
            else:
                _cal_days = max(int(_dte_for_mfe * 1.4), _dte_for_mfe + 1) if _dte_for_mfe > 0 else 1
                _theta_result = compute_empirical_theta(entry_price, _dte_for_mfe, _cal_days, _iv_regime_v2, _opt_class_v2, _mono_v2)
                _theta_daily_for_v2 = _theta_result.get("total_theta", 0)
        except Exception:
            _theta_daily_for_v2 = 0.0

        _v2_targets = select_targets_v2(
            entry_price=entry_price,
            stop_loss=stop_loss,
            atr=underlying_atr or (float(underlying_ltp) * 0.012),
            prob_table=_prob_table,
            mins_to_1530=effective_minutes,
            dte=_dte_for_mfe,
            iv_regime=_iv_regime_v2,
            regime_label=_regime_label_v2,
            flow_band=_flow_band_v2,
            dte_band=_dte_band_v2,
            tod_band=_tod_band,
            theta_daily=_theta_daily_for_v2,
        )

        if not _v2_targets.get("abort"):
            _vt1 = _v2_targets.get("t1")
            _vt2 = _v2_targets.get("t2")
            # Use V2 targets only if they are MORE conservative
            if _vt1 and _vt1 < target1:
                target1 = _vt1
                trigger_factors.append(f"V2T1:P={_v2_targets.get('p_hit_t1', 0):.0%}")
            if _vt2 and _vt2 < target2:
                target2 = _vt2
                trigger_factors.append(f"V2T2:P={_v2_targets.get('p_hit_t2', 0):.0%}")
            target2 = max(target2, round(target1 * 1.05, 2))

            # Carry probability data for Bucket D
            _prob_targets = {
                "t1_p_hit": _v2_targets.get("p_hit_t1"),
                "t2_p_hit": _v2_targets.get("p_hit_t2"),
                "method": "v2_targets",
            }
        else:
            # V2 targets aborted (no achievable T1), keep ATR-based targets
            trigger_factors.append(f"V2Abort:{_v2_targets.get('reason', 'unknown')}")
            # Still try old probability refinement as secondary fallback
            if _prob_table:
                _old_prob = select_targets_from_probability(
                    _prob_table, entry_price=entry_price,
                    stop_loss=stop_loss, minutes_remaining=effective_minutes,
                )
                if _old_prob.get("method") == "probability_based":
                    _pt1 = _old_prob.get("t1")
                    _pt2 = _old_prob.get("t2")
                    if _pt1 and _pt1 < target1:
                        target1 = _pt1
                    if _pt2 and _pt2 < target2:
                        target2 = _pt2
                    target2 = max(target2, round(target1 * 1.05, 2))
                    _prob_targets = _old_prob
    except Exception as _mfe_err:
        logger.debug(f"MFE/MAE target selection failed: {_mfe_err}")

    # ── Batch 2 NEW: No-chasing rule (section 1.8) ───────────────────────
    try:
        _expected_max_band = (underlying_atr or entry_price * 0.012) * _delta_proxy * 3.0
        _chase_check = check_no_chasing_rule(
            current_ltp=option_ltp,
            entry_price=entry_price,
            expected_max_band=_expected_max_band,
        )
        if not _chase_check.get("allow_entry", True):
            trigger_factors.append(f"NoChase:{_chase_check.get('pct_of_band_achieved', 0):.0f}%")
            # Don't block the signal yet (Batch 3 scoring will handle suppression)
    except Exception:
        pass

    # ── Batch 2 NEW: 0DTE ATM safety check (section 1.8 extra) ──────────
    try:
        _now_ist = datetime.now(IST)
        _dte_for_check = 0 if _is_expiry_today else max(get_remaining_trading_days(contract.expiry), 1)
        _zero_dte_check = check_0dte_atm_safety(
            underlying_ltp=float(underlying_ltp),
            strike=float(contract.strike),
            entry_time_hour=_now_ist.hour,
            dte=_dte_for_check if _is_expiry_today else 1,
        )
        if not _zero_dte_check.get("allow_entry", True):
            trigger_factors.append("0DTE_ATM_BLOCKED")
            logger.info(f"{contract.script}: {_zero_dte_check.get('reason')}")
    except Exception:
        pass

    # ── Best Budget Entry: 3-Source Pullback Model ──────────────────────────────
    # Identifies the floor the premium is likely to retrace to before continuing.
    # SOURCE 1: MAE-based (historical "lowest price before T1" from MFE library)
    # SOURCE 2: Kite day_low session floor support
    # SOURCE 3: ATR-adjusted pullback baseline (replaces old fixed %)
    #
    # Final BBE = max(all three sources, SL_floor) capped at entry * 0.97

    # Source 3: ATR-based pullback (dynamic, replaces fixed 12/15/20%)
    # Use underlying ATR * delta proxy to estimate option ATR
    _option_atr_est = max((_atr_proxy * _delta_proxy), entry_price * 0.02)
    _bbe_atr_pullback = round(entry_price - _option_atr_est * 1.5, 2)

    # Source 1: MAE-based (try to get MAE from cached MFE library)
    _bbe_mae_target = None
    try:
        from services.mfe_mae_engine import fetch_mfe_library
        _dte_band = "short" if _dte_for_mfe <= 3 else "medium"
        _mfe_lib = await fetch_mfe_library(
            db, contract.underlying, "S3_SUPERTREND", _dte_band, "medium", max_age_hours=72
        )
        if _mfe_lib and _mfe_lib.get("stats", {}).get("median_mae_pct"):
            _mae_median_pct = _mfe_lib["stats"]["median_mae_pct"]
            _bbe_mae_target = round(entry_price * (1 - _mae_median_pct / 100), 2)
    except Exception:
        pass

    # Source 2: Kite day_low support (session floor + 2%)
    _bbe_from_low = None
    if option_day_low is not None and option_day_low > 0 and option_day_low < entry_price:
        _bbe_from_low = round(option_day_low * 1.02, 2)

    # Combine: take the MAX of available sources (best/safest entry)
    _bbe_candidates = [_bbe_atr_pullback]
    if _bbe_mae_target is not None and _bbe_mae_target > 0:
        _bbe_candidates.append(_bbe_mae_target)
    if _bbe_from_low is not None:
        _bbe_candidates.append(_bbe_from_low)
    best_budget_entry = max(_bbe_candidates)

    # Floor: never inside the SL zone (SL + 5% buffer)
    best_budget_entry = max(best_budget_entry, round(stop_loss * 1.05, 2))
    # Ceiling: always at least 3% below current entry (it IS a pullback)
    best_budget_entry = min(best_budget_entry, round(entry_price * 0.97, 2))
    best_budget_entry = round(best_budget_entry, 2)
    # Alert when pullback opportunity is meaningful (≥ 3% below current entry price)
    budget_entry_alert = (entry_price - best_budget_entry) / max(entry_price, 0.01) >= 0.03

    # Sanity check: T1 must not exceed an extreme intraday move (6 ATRs × delta)
    # This replaces the old hard percentage cap which was hiding real ATR results
    _max_realistic_session_gain = _atr_proxy * _delta_proxy * 6.0  # 6 ATRs extreme move
    if target1 - entry_price > _max_realistic_session_gain:
        target1 = round(entry_price + _max_realistic_session_gain * 0.65, 2)
    if target2 - entry_price > _max_realistic_session_gain * 1.8:
        target2 = round(entry_price + _max_realistic_session_gain * 1.5, 2)

    if minutes_to_expiry < 60 and entry_price > 0:
        required_gain = (target1 - entry_price) / entry_price
        if required_gain > 0.12:
            raise HTTPException(
                status_code=400,
                detail="Insufficient time to expiry for this upside. No projections shown.",
            )

    # SAME-DAY EXPIRY CAP: when option expires today, cap T2 at 2× entry (100% gain max).
    # On expiry day, achieving 3× entry requires a 2–3 ATR underlying move which is
    # statistically improbable in a single session. This keeps targets realistic.
    if _is_expiry_today:
        _same_day_t2_cap = round(entry_price * 2.0, 2)   # Hard cap: 100% gain on expiry day
        _same_day_t1_cap = round(entry_price * 1.50, 2)  # T1 cap: 50% gain on expiry day
        target1 = min(target1, _same_day_t1_cap)
        target2 = min(target2, _same_day_t2_cap)
        target2 = max(target2, round(target1 * 1.05, 2))  # Ensure T2 > T1

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
    elif remaining_trading_days >= 3:
        best_exit_days = min(int(remaining_trading_days * 0.7), remaining_trading_days - 1)
    elif remaining_trading_days >= 2:
        best_exit_days = 1
    else:
        best_exit_days = 0

    # ── ATR-based max achievable option projection ────────────────────────────
    # Maximum underlying move = ATR × sqrt(best_exit_days) × 2σ scenario
    # Maximum option gain = underlying_move × moneyness_delta
    _atr_for_best_exit = underlying_atr or (float(underlying_ltp) * 0.012)
    _underlying_max_move = _atr_for_best_exit * math.sqrt(max(best_exit_days, 1)) * 2.0
    # Re-compute delta_proxy for best exit (same moneyness logic)
    _be_delta = 0.45
    if contract.strike and float(underlying_ltp) > 0:
        _mono = float(underlying_ltp) / float(contract.strike) if contract.option_type == "CE" else float(contract.strike) / float(underlying_ltp)
        if _mono >= 1.08: _be_delta = 0.80
        elif _mono >= 1.04: _be_delta = 0.65
        elif _mono >= 0.97: _be_delta = 0.45
        elif _mono >= 0.93: _be_delta = 0.28
        else: _be_delta = 0.15
    _max_option_gain_from_atr = _underlying_max_move * _be_delta * 1.2  # 20% leverage premium
    max_ltp_projection = round(min(
        entry_price + _max_option_gain_from_atr,
        entry_price * 3.0,  # Hard cap: never more than 3x entry
        target2 * 1.20,     # Cap at 20% above T2 to stay realistic
    ), 2)

    # Theta decay: VIX-based model, with calendar days for weekends/holidays
    if remaining_trading_days > 0 and best_exit_days > 0:
        # Count actual calendar days including weekends/holidays between today and best exit
        _cal_to_expiry = _get_calendar_days_to_date(contract.expiry) if contract.expiry else remaining_trading_days
        _cal_to_best_exit = _get_calendar_days_for_nth_trading_day(best_exit_days)
        theta_decay, theta_method = compute_vix_theta_decay(
            entry_price=entry_price,
            remaining_trading_days=remaining_trading_days,
            best_exit_days=best_exit_days,
            india_vix=india_vix,
            iv_override=ts.get("iv") if ts else None,
            calendar_days_to_expiry=_cal_to_expiry,
            calendar_best_exit_days=_cal_to_best_exit,
        )
        best_exit_price = round(max(max_ltp_projection - theta_decay, entry_price * 1.01), 2)
    else:
        theta_decay = 0.0
        theta_method = "none"
        best_exit_price = max_ltp_projection

    # SAME-DAY EXPIRY: Override best_exit_price with session-sigma peak projection.
    # Full-day ATR overestimates the achievable price when only a fraction of session remains.
    # Formula: entry + (1.5 × session_sigma × delta) − (0.5 × session_theta)
    if _is_expiry_today:
        _now_be = datetime.now(IST)
        _mkt_close_be = _now_be.replace(hour=15, minute=30, second=0, microsecond=0)
        _rem_sess_min_be = max(1, int((_mkt_close_be - _now_be).total_seconds() / 60)) if _now_be < _mkt_close_be else 1
        _sess_frac_be = min(_rem_sess_min_be / 375.0, 1.0)
        _vix_f_be = 1.0
        if india_vix:
            if india_vix > 25:   _vix_f_be = 1.30
            elif india_vix > 20: _vix_f_be = 1.15
            elif india_vix < 12: _vix_f_be = 0.85
        _atr_be_sd = underlying_atr or (float(underlying_ltp) * 0.012)
        _sess_sigma_be = _atr_be_sd * math.sqrt(_sess_frac_be) * _vix_f_be
        _theta_be_session = (entry_price * _vix_f_be * 0.25 / math.sqrt(max(_sess_frac_be, 0.01))) * _sess_frac_be
        _peak_gain_sd = _sess_sigma_be * 1.5 * _be_delta - _theta_be_session * 0.5
        _peak_gain_sd = max(_peak_gain_sd, entry_price * 0.02)  # Floor: 2% of entry
        best_exit_price = round(min(
            entry_price + _peak_gain_sd,
            target2 * 1.10,         # Cap: max 10% above T2
            entry_price * 2.0,      # Hard cap: 100% gain on expiry day
        ), 2)
        best_exit_price = max(best_exit_price, entry_price * 1.01)  # Never below entry+1%

    # ── Batch 2: Forward MFE-based Best Exit refinement (cache-first) ────
    # Try cached forward MFE from MongoDB first, then compute on-the-fly.
    if not _is_expiry_today and remaining_trading_days > 0:
        try:
            _iv_regime_str = _enhanced_regime.get("regime", "LowVolTrend") if _enhanced_regime else "LowVolTrend"
            _mono_label_be = _enhanced_opt_features.get("moneyness", "ATM") if _enhanced_opt_features else "ATM"
            _opt_class = "index_weekly" if contract.underlying in ("NIFTY", "BANKNIFTY") else "stock_monthly"

            # Step 1: Try cached forward MFE
            _s = _srv()
            _cached_fwd = await get_cached_fwd_mfe(
                _s.db, contract.underlying, remaining_trading_days, _iv_regime_str,
            )
            if _cached_fwd and _cached_fwd.get("reliable"):
                # Apply cached percentile to current entry price
                _adj_pct = _cached_fwd.get("theta_adj_p80_pct", 0)
                _be_price_cached = round(entry_price * (1 + _adj_pct / 100), 2)
                if _be_price_cached < best_exit_price:
                    best_exit_price = _be_price_cached
                    trigger_factors.append("BestExitMFE:cached")
                if _cached_fwd.get("best_exit_day") is not None:
                    best_exit_days = _cached_fwd["best_exit_day"]
            else:
                # Step 2: Compute on-the-fly
                _hist_for_be = _hist_for_mfe  # Reuse cached data, avoid redundant fetch
                _be_online = compute_best_exit_online(
                    entry_price=entry_price,
                    remaining_trading_days=remaining_trading_days,
                    dte=remaining_trading_days,
                    iv_regime=_enhanced_regime.get("vix_level", "normal").upper() + "_IV" if _enhanced_regime else "NORMAL_IV",
                    market_regime=_iv_regime_str,
                    hist_df=_hist_for_be,
                    atr=underlying_atr,
                    vix=india_vix,
                    option_class=_opt_class,
                    moneyness=_mono_label_be,
                )
                if _be_online.get("reliable"):
                    _be_price_new = _be_online["best_exit_price"]
                    if _be_price_new < best_exit_price:
                        best_exit_price = round(_be_price_new, 2)
                        trigger_factors.append(f"BestExitMFE:{_be_online.get('method', 'fwd')}")
                    if _be_online.get("best_exit_day") is not None:
                        best_exit_days = _be_online["best_exit_day"]

                    # Persist for next time (fire-and-forget)
                    if _hist_for_be is not None and not _hist_for_be.empty:
                        try:
                            await build_and_store_forward_mfe(
                                _s.db, contract.underlying, _hist_for_be,
                                atr=underlying_atr or (float(underlying_ltp) * 0.012),
                                remaining_trading_days=remaining_trading_days,
                                regime=_iv_regime_str,
                                iv_regime=_enhanced_regime.get("vix_level", "normal").upper() + "_IV" if _enhanced_regime else "NORMAL_IV",
                                option_class=_opt_class,
                                moneyness=_mono_label_be,
                            )
                        except Exception:
                            pass  # Non-critical: persistence failure doesn't block signal
        except Exception as _be_err:
            logger.debug(f"Forward MFE best exit failed: {_be_err}")

    # Compute actual calendar date for best exit
    if _is_expiry_today:
        best_exit_date_str = "Today (Exit Before 3:30 PM)"
    elif best_exit_date_obj := (get_nth_trading_day_from_today(best_exit_days) if best_exit_days and best_exit_days > 0 else None):
        best_exit_date_str = best_exit_date_obj.strftime("%d %b %Y")
    else:
        best_exit_date_str = None

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
        # Batch B: forensic scores for real fundamental_score calculation
        piotroski_score=fundamental.get("piotroski_score") if fundamental else None,
        beneish_m_score=fundamental.get("beneish_m_score") if fundamental else None,
        altman_z_zone=fundamental.get("altman_z_zone") if fundamental else None,
        # Batch 1 extras via tech_snapshot
        tech_snapshot=ts,
    )

    # ── Batch 3: 4-Bucket Confluence Score V2 (section 7) ────────────────
    # Feature flag: USE_NEW_SCORING controls V1 vs V2 scoring
    _confluence_v1 = confluence_score
    _conviction_v1 = conviction_level
    _use_v2_scoring = os.environ.get("USE_NEW_SCORING", "true").lower() == "true"

    # V2 scoring breakdown (populated only when V2 active)
    _v2_bucket_a = None
    _v2_bucket_b = None
    _v2_bucket_c = None
    _v2_bucket_d = None
    _v2_suppress_reason = None
    _v2_regime_label = _enhanced_regime.get("regime", "LowVolRange") if _enhanced_regime else "LowVolRange"
    _v2_flow_band = _intraday_features.get("flow_band", "NeutralFlow") if _intraday_features else "NeutralFlow"
    _v2_news_flag = _news_sentiment.get("news_flag", "NEUTRAL") if _news_sentiment else "NEUTRAL"

    if _use_v2_scoring:
        try:
            # Bucket A: Strategy & backtest robustness
            _use_backtest_db = os.environ.get("USE_BACKTEST_DB", "0") == "1"
            _strat_stats = {}
            _bucket_a_strategy_enabled = True
            if _use_backtest_db:
                try:
                    _matched_strategy_id = _strategy_id if _strategy_id else None
                    _underlying_for_bt = contract.underlying.replace(" ", "")
                    if _matched_strategy_id and _underlying_for_bt:
                        _bt_doc = await fetch_strategy_backtest(db, _matched_strategy_id, _underlying_for_bt)
                        if _bt_doc:
                            _strat_stats = _bt_doc
                            _bucket_a_strategy_enabled = is_backtest_enabled(_bt_doc)
                        else:
                            _bucket_a_strategy_enabled = False
                except Exception as _bt_err:
                    logger.debug("Backtest fetch failed for Bucket A: %s", _bt_err)
            _v2_bucket_a = compute_bucket_a(
                win_rate=_strat_stats.get("win_rate"),
                expectancy_r=_strat_stats.get("expectancy_R") or _strat_stats.get("expectancy_r"),
                trade_count=_strat_stats.get("trade_count"),
                strategy_enabled=_bucket_a_strategy_enabled,
            )

            # Bucket B: Direction & structure — WIRE REAL BREADTH (Item 2)
            _index_bscore = None
            _sector_bscore = None
            if contract.underlying in ("NIFTY", "BANKNIFTY"):
                # Use constituent_engine breadth for index signals
                _ib_pct = _index_breadth.get("breadth_score") if _index_breadth else None
                if _ib_pct is not None:
                    # Map breadth % to bucket B sub-score (0-100 scale)
                    if _ib_pct >= 65:
                        _index_bscore = _ib_pct  # full B contribution
                    elif _ib_pct >= 50:
                        _index_bscore = _ib_pct * 0.7  # partial
                    else:
                        _index_bscore = 0  # insufficient breadth
            else:
                # For stock signals: use sector sentiment as breadth proxy
                if _sector_sentiment:
                    _sec_flag = _sector_sentiment.get("news_flag", "NEUTRAL")
                    _sec_count = _sector_sentiment.get("news_count", 0)
                    if _sec_flag == "POSITIVE":
                        _sector_bscore = min(100, 60 + _sec_count * 5)
                    elif _sec_flag == "NEGATIVE":
                        _sector_bscore = max(0, 40 - _sec_count * 5)
                    else:
                        _sector_bscore = 50

            _v2_bucket_b = compute_bucket_b(
                direction=direction,
                bias_score=bias_score,
                trend_alignment=tech_alignment,
                rsi=tech_rsi,
                macd_bullish=tech_macd.get("bullish_crossover") if tech_macd else None,
                adx=tech_adx,
                above_vwap=None,
                sector_breadth_score=_sector_bscore,
                index_breadth_score=_index_bscore,
                regime=_v2_regime_label,
                stoch_k=tech_stoch.get("%K") if tech_stoch else None,
            )

            # Bucket C: Options, order-flow & sentiment
            _oi_buildup_c = _enhanced_opt_features.get("oi_buildup") if _enhanced_opt_features else oi_buildup
            _iv_rank_c = _enhanced_opt_features.get("iv_rank") if _enhanced_opt_features else iv_rank
            _is_liquid_c = _enhanced_opt_features.get("is_liquid", True) if _enhanced_opt_features else True
            _spread_pct_c = None
            if _enhanced_opt_features and _enhanced_opt_features.get("spread_data"):
                _spread_pct_c = _enhanced_opt_features["spread_data"].get("spread_pct")

            _v2_bucket_c = compute_bucket_c(
                oi_buildup=_oi_buildup_c,
                iv_rank=_iv_rank_c,
                is_liquid=_is_liquid_c,
                spread_pct=_spread_pct_c,
                flow_band=_v2_flow_band,
                news_flag=_v2_news_flag,
                direction=direction,
                pcr=pcr,
            )

            # Bucket D: Trade quality — WIRE FULL MFE DATA (Item 3)
            _risk_d = max(entry_price - stop_loss, 0.01)
            _rr_t1_d = (target1 - entry_price) / _risk_d if _risk_d > 0 else 0
            _rr_t2_d = (target2 - entry_price) / _risk_d if _risk_d > 0 else 0
            _sl_dist_pct_d = (_risk_d / entry_price) * 100 if entry_price > 0 else 10
            _t1_phit_d = _prob_targets.get("t1_p_hit") if _prob_targets else None
            _t2_phit_d = _prob_targets.get("t2_p_hit") if _prob_targets else None
            # Compute rr_to_best_exit from best_exit_price
            _rr_best_exit_d = None
            if best_exit_price and best_exit_price > entry_price and _risk_d > 0:
                _rr_best_exit_d = (best_exit_price - entry_price) / _risk_d

            _v2_bucket_d = compute_bucket_d(
                rr_to_t1=_rr_t1_d,
                rr_to_t2=_rr_t2_d,
                rr_to_best_exit=_rr_best_exit_d,
                t1_p_hit=_t1_phit_d,
                t2_p_hit=_t2_phit_d,
                sl_distance_pct=_sl_dist_pct_d,
            )

            # Log partial data warning for Bucket D
            if _t2_phit_d is None or _rr_best_exit_d is None:
                logger.debug(
                    f"Bucket D: partial data for {contract.script}, "
                    f"t2_p_hit={_t2_phit_d}, rr_best_exit={_rr_best_exit_d}, conservative scoring applied"
                )

            # Final V2 Score
            _v2_result = compute_confluence_score_v2(_v2_bucket_a, _v2_bucket_b, _v2_bucket_c, _v2_bucket_d)
            _v2_score = _v2_result["score"]
            _v2_conviction = _v2_result["conviction"]

            # ITEM 5: Act on should_suppress flag
            _should_suppress = _v2_result.get("should_suppress", False)
            # Also check hard veto from Bucket D
            if _v2_bucket_d.get("hard_veto"):
                _should_suppress = True
                _v2_suppress_reason = f"BucketD_hard_veto:{_v2_bucket_d.get('veto_reason', 'rr<1')}"
            elif _should_suppress:
                _v2_suppress_reason = f"V2_score={_v2_score}<{CONFLUENCE_THRESHOLD}"
            elif _v2_score < CONFLUENCE_THRESHOLD:
                _should_suppress = True
                _v2_suppress_reason = f"V2_score={_v2_score}<{CONFLUENCE_THRESHOLD}"

            if _should_suppress:
                logger.info(
                    f"SUPPRESSED: {contract.script} score={_v2_score} "
                    f"reason={_v2_suppress_reason} "
                    f"A={_v2_bucket_a['score']} B={_v2_bucket_b['score']} "
                    f"C={_v2_bucket_c['score']} D={_v2_bucket_d['score']}"
                )
                return None  # Signal suppressed — skip this candidate

            # Use V2 score as the primary score
            confluence_score = _v2_score
            conviction_level = _v2_conviction

            # Log comparison for audit
            if abs(_v2_score - _confluence_v1) > 10:
                logger.info(
                    f"{contract.script}: ConfluenceV1={_confluence_v1} V2={_v2_score} "
                    f"A={_v2_bucket_a['score']} B={_v2_bucket_b['score']} "
                    f"C={_v2_bucket_c['score']} D={_v2_bucket_d['score']}"
                )

            trigger_factors.append(
                f"V2Score:A{_v2_bucket_a['score']}B{_v2_bucket_b['score']}"
                f"C{_v2_bucket_c['score']}D{_v2_bucket_d['score']}"
            )

        except Exception as _v2_err:
            logger.warning(f"Confluence V2 scoring failed for {contract.script}: {_v2_err}. Using V1 fallback.")
            trigger_factors.append(f"V1Fallback:{_confluence_v1}")
    else:
        # USE_NEW_SCORING=false → V1 path
        trigger_factors.append(f"V1Score:{_confluence_v1}")
    
    # Add technical tags to trigger_factors
    if ts.get("data_available") and tech_alignment:
        trigger_factors.append(f"TrendAlign={tech_alignment}")
    if tech_rsi is not None:
        trigger_factors.append(f"RSI={tech_rsi:.0f}")
    if tech_adx is not None and tech_adx > 20:
        trigger_factors.append(f"ADX={tech_adx:.0f}")
    
    signal_quality = _get_signal_quality(confluence_score)
    signal_expiry_risk = _expiry_risk_bucket(minutes_to_expiry)

    is_potential_trade = is_actionable_fno_signal(
        confluence_score,
        direction,
        risk_reward_target2,
        signal_expiry_risk,
    )
    if is_potential_trade:
        trigger_factors.append(f"Conviction={conviction_level}")

    # ── High-confidence target assurance (80+ confluence) ─────────────────────
    # Recalibrate T1/T2 using tighter sigma multipliers (0.35×/0.65× vs 0.50×/1.00×)
    # to deliver near-guaranteed intraday hits for confirmed strong signals.
    if confluence_score >= 80:
        _t1_hc, _t2_hc = compute_atr_based_fno_targets(
            entry_price=entry_price,
            underlying_ltp=float(underlying_ltp),
            atr=underlying_atr,
            minutes_to_expiry=effective_minutes,
            option_type=contract.option_type,
            vix=india_vix,
            strike=float(contract.strike),
            high_confidence=True,
        )
        # Only replace if HC targets are more conservative (lower = higher certainty)
        target1 = min(target1, _t1_hc)
        target2 = min(target2, _t2_hc)
        # Re-apply same-day caps after HC adjustment
        if _is_expiry_today:
            target1 = min(target1, round(entry_price * 1.50, 2))
            target2 = min(target2, round(entry_price * 2.0, 2))
        target2 = max(target2, round(target1 * 1.05, 2))
        # Recompute risk/reward with tighter targets
        _risk_hc = max(entry_price - stop_loss, 0.01)
        risk_reward_target1 = round((target1 - entry_price) / _risk_hc, 2)
        risk_reward_target2 = round((target2 - entry_price) / _risk_hc, 2)
        trigger_factors.append(f"AssuredTargets:HC{confluence_score}")

    ltp_margin_to_t1_amount = round(max(target1 - option_ltp, 0.0), 2)
    ltp_margin_to_t1_pct = round(((target1 - option_ltp) / max(option_ltp, 0.01)) * 100, 2)
    achievable_profit_pct = round(((target1 - entry_price) / max(entry_price, 0.01)) * 100, 2)

    _sig_resp = FNOSignalResponse(
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
        near_expiry_badge=(remaining_trading_days == 2),  # tomorrow-expiry warning
        expiry_today_badge=_is_expiry_today,              # EXPIRY TODAY pulsing badge
        best_budget_entry=best_budget_entry,              # Pullback entry advisory
        budget_entry_alert=budget_entry_alert,            # Show "wait for pullback" UI alert
        trigger_factors=trigger_factors,
        confluence_score=confluence_score,
        signal_quality=signal_quality,
        conviction_level=conviction_level,
        is_potential_trade=is_potential_trade,
        minutes_to_expiry=minutes_to_expiry,
        expiry_risk=signal_expiry_risk,
        data_source="LIVE_OPTION_CHAIN",
        analysis_refreshed_at=refreshed_at,
        max_pain=max_pain,
        iv_rank=iv_rank,
        iv_rank_52w=iv_rank_52w,
        atm_iv=atm_iv,
        oi_buildup=oi_buildup,
        gex=gex,
        # Batch 3: V2 Scoring Breakdown (Item 6)
        confluence_score_v2=float(_v2_bucket_a["score"] + _v2_bucket_b["score"] + _v2_bucket_c["score"] + _v2_bucket_d["score"]) / 4.0 if (_v2_bucket_a and _v2_bucket_b and _v2_bucket_c and _v2_bucket_d) else None,
        score_bucket_A=float(_v2_bucket_a["score"]) if _v2_bucket_a else None,
        score_bucket_B=float(_v2_bucket_b["score"]) if _v2_bucket_b else None,
        score_bucket_C=float(_v2_bucket_c["score"]) if _v2_bucket_c else None,
        score_bucket_D=float(_v2_bucket_d["score"]) if _v2_bucket_d else None,
        score_suppress_reason=_v2_suppress_reason,
        score_regime_label=_v2_regime_label,
        score_flow_band=_v2_flow_band,
        score_news_flag=_v2_news_flag,
    )

    # ── Step 4: Position Sizing Annotation (additive, does not block signals) ──
    try:
        _ctx_budget = _ctx_user_budget.get()
        _ctx_risk = _ctx_account_risk_pct.get()
        _user_budget = float(_ctx_budget) if _ctx_budget is not None else float(os.environ.get("DEFAULT_USER_BUDGET", "500000"))
        _acct_risk = float(_ctx_risk) if _ctx_risk is not None else None
        _sizing = compute_position_size(
            user_budget=_user_budget,
            option_premium=option_ltp,
            lot_size=contract.lot_size,
            sl_price=stop_loss,
            entry_price=best_budget_entry or entry_price,
            atr14=underlying_atr,
            account_risk_pct=_acct_risk,
        )
        _sig_resp.not_affordable = _sizing["not_affordable"]
        _sig_resp.sizing_info = _sizing
    except Exception:
        pass  # sizing is optional annotation, never blocks signal

    # ── Profiling: store per-function timings ─────────────────────────
    _phase_timings["total_ms"] = round((_time.monotonic() - _fn_start) * 1000)
    logger.debug("build_fno_signal profiling [%s]: %s", contract.tradingsymbol, _phase_timings)

    return _sig_resp


