"""
F&O Signal Engine — Core signal building logic.

Extracted from server.py for modularity. All functions use lazy
`import server as _srv` for accessing server.py globals (db, IST,
market_data_client, etc.) to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any, Literal

from fastapi import HTTPException

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


# ── Pure utility functions ─────────────────────────────────────────────────────

def _compute_initial_option_targets(buy_price: float) -> dict:
    """
    ATR-tiered initial T1/T2 for custom positions at creation.
    Based on typical NSE option intraday move ranges by price tier.
    NOT fixed percentages — approximates expected ATR-scale moves for each tier.
    Recalibrated to real ATR values on first refresh cycle.
    """
    bp = max(buy_price, 0.5)
    if bp < 15:
        t1 = round(bp + 1.5, 2)
        t2 = round(bp + 3.5, 2)
    elif bp < 30:
        t1 = round(bp + 3.0, 2)
        t2 = round(bp + 7.0, 2)
    elif bp < 60:
        t1 = round(bp + 6.0, 2)
        t2 = round(bp + 14.0, 2)
    elif bp < 100:
        t1 = round(bp + 10.0, 2)
        t2 = round(bp + 23.0, 2)
    elif bp < 200:
        t1 = round(bp + 16.0, 2)
        t2 = round(bp + 36.0, 2)
    else:
        # Higher-priced options: use ~8% move for T1, ~18% for T2 — close to 1-ATR
        t1 = round(bp + bp * 0.08, 2)
        t2 = round(bp + bp * 0.18, 2)
    return {
        "target1": t1,
        "target2": t2,
        "original_target1": t1,
        "original_target2": t2,
    }


def _compute_initial_option_sl(buy_price: float) -> float:
    """
    ATR-tiered initial SL for custom positions.
    Approximates a 1.5-ATR adverse move by price tier.
    NOT a fixed percentage.
    """
    bp = max(buy_price, 0.5)
    if bp < 15:
        sl_distance = 1.5
    elif bp < 30:
        sl_distance = 3.0
    elif bp < 60:
        sl_distance = 6.0
    elif bp < 100:
        sl_distance = 9.0
    elif bp < 200:
        sl_distance = 14.0
    else:
        sl_distance = bp * 0.08
    return round(max(bp - sl_distance, bp * 0.5), 2)  # floor at 50% of entry



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
    # ── Batch B: Forensic quality inputs ────────────────────────────────
    piotroski_score: int | None = None,
    beneish_m_score: float | None = None,
    altman_z_zone: str | None = None,
    # ── Batch 1 extras (from tech_snapshot) ─────────────────────────────
    tech_snapshot: dict | None = None,
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

    # ── Fundamental Quality Score (Batch B: Forensic-based) ──────────────────
    # Use real Piotroski, Beneish, Altman data when available.
    # Falls back to 52W position proxy when no forensic data is present.
    if piotroski_score is not None:
        # Piotroski F-Score (0-9): 7-9 = strong, 5-6 = decent, 0-4 = poor
        if piotroski_score >= 7:
            fundamental_score = 10
        elif piotroski_score >= 5:
            fundamental_score = 7
        elif piotroski_score >= 3:
            fundamental_score = 4
        else:
            fundamental_score = 2
        # Beneish M-Score: > -2.22 signals potential earnings manipulation
        if beneish_m_score is not None and beneish_m_score > -2.22:
            fundamental_score = max(0, fundamental_score - 3)
        # Altman Z-Zone: DISTRESS = high bankruptcy risk, SAFE = financially sound
        if altman_z_zone == "DISTRESS":
            fundamental_score = max(0, fundamental_score - 4)
        elif altman_z_zone == "SAFE":
            fundamental_score = min(10, fundamental_score + 2)
    else:
        # No forensic data — use 52W position as proxy
        ltp = stock_core.ltp
        year_high = stock_core.year_high
        year_low = stock_core.year_low
        if ltp and year_high and year_low and year_high > year_low:
            position_val = (ltp - year_low) / (year_high - year_low)
            fundamental_score = 8 if 0.3 <= position_val <= 0.7 else 6
        else:
            fundamental_score = 5

    # ── Strategy Alignment Bonus ──────────────────────────────────────────────
    if strategy in ("ORB_BREAKOUT", "VWAP_REVERSION"):
        strategy_bonus = 5

    # ── Technical Analysis Bonus (RSI, MACD, Trend, OBV, ADX, BB, Stoch + Batch 1) ─
    _ts = tech_snapshot or {}
    _cci_val = (_ts.get("cci") or {}).get("cci")
    _vpt_val = (_ts.get("vpt") or {}).get("trend")
    _ad_val = (_ts.get("ad_line") or {}).get("trend")
    _ichimoku_val = _ts.get("ichimoku") or {}
    _rsi_div_val = _ts.get("rsi_divergence") or {}
    _candle_val = _ts.get("candlestick_patterns") or {}
    _mf_val = _ts.get("multiframe_trend") or {}
    _chart_val = _ts.get("chart_patterns") or {}
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
        williams_r=_ts.get("williams_r"),
        cci=_cci_val,
        vpt_trend=_vpt_val,
        ad_trend=_ad_val,
        ichimoku_price_vs_cloud=_ichimoku_val.get("price_vs_cloud"),
        ichimoku_tk_cross=_ichimoku_val.get("tenkan_kijun_cross"),
        ichimoku_bullish=_ichimoku_val.get("bullish_signal"),
        ichimoku_bearish=_ichimoku_val.get("bearish_signal"),
        rsi_divergence=_rsi_div_val.get("divergence"),
        rsi_div_type=_rsi_div_val.get("type"),
        candle_bias=_candle_val.get("bias"),
        mf_alignment=_mf_val.get("alignment"),
        has_bull_chart_pattern=_chart_val.get("has_bullish_pattern", False),
        has_bear_chart_pattern=_chart_val.get("has_bearish_pattern", False),
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


def _format_script(underlying: str, expiry: str, strike: float, option_type: str) -> str:
    date_obj = datetime.strptime(expiry, "%Y-%m-%d")
    return f"{underlying}{date_obj.strftime('%d%b').upper()}{int(strike)}{option_type}"


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



def _infer_stock_option_type(core: StockCoreNormalized) -> Literal["CE", "PE"] | None:
    _srv_mod = _srv()
    if core.ltp is None:
        return None
    pos = _srv_mod._position_in_range(core.ltp, core.year_low, core.year_high)
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



# ── Functions with server.py dependencies (lazy import) ─────────────────────────

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


    # ── Batch 5: Strategy Library Selection (Batch C: with threshold enforcement) ─
    _vix_curr = india_vix
    _adx_curr = tech_adx
    _rsi_curr = tech_rsi
    _regime_obj = classify_market_regime_enhanced(
        vix=_vix_curr, adx=_adx_curr, rsi=_rsi_curr
    )
    _regime = _regime_obj.get("regime", "NORMAL_VOL_TREND")
    # Load strategy stats from DB to enforce ≥75% win rate / ≥0.40R expectancy
    _strategy_stats_data = await _get_strategy_stats_for_selection()
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

    # ── Batch 4: Macro Context ────────────────────────────────────────────
    _sector_str = fundamental.get("sector") if fundamental else None
    _macro_ctx: dict = {}
    try:
        _active_events = await _get_active_macro_events()
        _macro_ctx = compute_macro_context(
            active_events=_active_events,
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

    # ── Best Budget Entry: Pullback zone to prevent "momentum peak" entries ───
    # Identifies the floor the premium is likely to retrace to before continuing
    # in the signal direction. UI alerts the user to WAIT for this price.
    # Uses session_low support + percentage pullback model.
    _bbe_pct = 0.12 if entry_price > 100 else (0.15 if entry_price > 50 else 0.20)
    _bbe_pullback_target = round(entry_price * (1 - _bbe_pct), 2)
    if option_day_low is not None and option_day_low > 0 and option_day_low < entry_price:
        # Use day-low support: best entry near session floor (just above it)
        _bbe_from_low = round(option_day_low * 1.02, 2)
        best_budget_entry = max(_bbe_pullback_target, _bbe_from_low)
    else:
        best_budget_entry = _bbe_pullback_target
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
                _v2_suppress_reason = f"V2_score={_v2_score}<78"
            elif _v2_score < 78:
                _should_suppress = True
                _v2_suppress_reason = f"V2_score={_v2_score}<78"

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

    is_potential_trade = direction != "NEUTRAL" and confluence_score >= 78 and risk_reward_target2 >= 1.2
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
        expiry_risk=_expiry_risk_bucket(minutes_to_expiry),
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
        _user_budget = float(os.environ.get("DEFAULT_USER_BUDGET", "500000"))
        _sizing = compute_position_size(
            user_budget=_user_budget,
            option_premium=option_ltp,
            lot_size=contract.lot_size,
            sl_price=stop_loss,
            entry_price=best_budget_entry or entry_price,
        )
        _sig_resp.not_affordable = _sizing["not_affordable"]
        _sig_resp.sizing_info = _sizing
    except Exception:
        pass  # sizing is optional annotation, never blocks signal

    return _sig_resp


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


async def _build_report(index_name: Literal["NIFTY", "BANKNIFTY"], weighted: bool) -> IndexAnalysisReport:
    _s = _srv()
    NIFTY_WEIGHT_PROXY = _s.NIFTY_WEIGHT_PROXY
    BANKNIFTY_WEIGHT_PROXY = _s.BANKNIFTY_WEIGHT_PROXY
    get_stock_core = _s.get_stock_core
    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY
    symbols = [symbol for symbol, _ in weight_source]
    rows = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_rows = [StockCoreNormalized(**row) for row in rows]
    return _compute_report_from_rows(index_name, weight_source, normalized_rows, weighted)


async def _compute_enhanced_index_breadth(
    index_name: str,
    top_n: int = 12,
) -> dict:
    _s = _srv()
    _get_hist_ohlcv = _s._get_hist_ohlcv
    NIFTY50_WEIGHTS = _s.NIFTY50_WEIGHTS
    BANKNIFTY_WEIGHTS = _s.BANKNIFTY_WEIGHTS
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

    # ── Batch 1 NEW: Compute enhanced weighted breadth (section 2.2) ─────
    # Convert constituent_signals to format expected by compute_weighted_breadth
    try:
        _breadth_data = []
        for sig in constituent_signals:
            _bias = sig.get("tech_bias", "NEUTRAL")
            _breadth_data.append({
                "symbol": sig["symbol"],
                "weight_pct": sig.get("weight_override", 1.0),
                "in_uptrend": _bias == "BULLISH",
                "above_vwap": _bias in ("BULLISH",),  # proxy when VWAP unavailable
                "intraday_return_pct": 0.0,  # will be enhanced with live data later
                "intraday_volatility": 0.0,
                "rsi": None,
                "macd_bullish": False,
            })
        _weighted_breadth = compute_weighted_breadth(_breadth_data, index_name)
        bias_result["weighted_breadth"] = _weighted_breadth
        logger.debug(f"{index_name} weighted breadth: {_weighted_breadth.get('breadth_score', 0)}")
    except Exception as _wb_err:
        logger.debug(f"Weighted breadth computation failed for {index_name}: {_wb_err}")

    return bias_result


async def _build_index_projection(index_name: Literal["NIFTY", "BANKNIFTY"], refreshed_at: str) -> IndexProjectionPane:
    _s = _srv()
    IST = _s.IST
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP
    db = _s.db
    _get_stock_core_cached = _s._get_stock_core_cached
    market_data_client = _s.market_data_client
    get_minutes_to_expiry = _s.get_minutes_to_expiry
    _fetch_option_snapshots_from_kite = _s._fetch_option_snapshots_from_kite
    compute_option_chain_analytics = _s.compute_option_chain_analytics
    _get_india_vix = _s._get_india_vix
    _get_hist_ohlcv = _s._get_hist_ohlcv
    _fetch_live_option_snapshot = _s._fetch_live_option_snapshot
    _to_float = _s._to_float
    get_stock_core = _s.get_stock_core
    NIFTY_WEIGHT_PROXY = _s.NIFTY_WEIGHT_PROXY
    BANKNIFTY_WEIGHT_PROXY = _s.BANKNIFTY_WEIGHT_PROXY
    clamp = _s.clamp
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

    # ── BATCH 1: LOG-ONLY feature audit ──────────────────────────────────
    try:
        _vix = await _get_india_vix()
        _adx_for_regime = None
        try:
            _hist = await _get_hist_ohlcv(index_name, interval="day", candles=30)
            if _hist and _hist.get("closes") and len(_hist["closes"]) >= 14:
                from services.indicators import compute_atr_based_fno_targets
                import pandas as pd
                _h_df = pd.DataFrame({"High": _hist["highs"], "Low": _hist["lows"], "Close": _hist["closes"]})
                _dx_series = pd.Series(dtype=float)
                for i in range(1, len(_h_df)):
                    _plus_dm = max(_h_df["High"].iloc[i] - _h_df["High"].iloc[i-1], 0)
                    _minus_dm = max(_h_df["Low"].iloc[i-1] - _h_df["Low"].iloc[i], 0)
                    _tr = max(_h_df["High"].iloc[i] - _h_df["Low"].iloc[i],
                             abs(_h_df["High"].iloc[i] - _h_df["Close"].iloc[i-1]),
                             abs(_h_df["Low"].iloc[i] - _h_df["Close"].iloc[i-1]))
                    _dx_series.loc[i] = abs(_plus_dm - _minus_dm) / max(_tr, 0.01) * 100
                if len(_dx_series) >= 14:
                    _adx_for_regime = float(_dx_series.rolling(14).mean().iloc[-1])
        except Exception:
            pass
        await log_batch1_features(index_name, db, vix=_vix, adx=_adx_for_regime)
    except Exception as exc:
        logger.debug(f"[BATCH1] Feature audit skipped: {exc}")

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

        # ── Compute full option chain analytics (Max Pain, PCR, IV Rank, GEX, OI Buildup)
        # All analytics computed in pure Python from live Kite OI/IV/Gamma data (Master Spec).
        _chain_analytics = compute_option_chain_analytics(contracts, kite_map, stock.ltp, step)
        pcr         = _chain_analytics.get("pcr")
        _max_pain   = _chain_analytics.get("max_pain")
        _iv_rank    = _chain_analytics.get("iv_rank")
        _gex        = _chain_analytics.get("gex")
        _oi_buildup = _chain_analytics.get("oi_buildup")
        _atm_iv     = _chain_analytics.get("atm_iv")

        # ── 52-Week IV Rank enrichment ──────────────────────────────────────
        _iv_rank_52w = None
        if _atm_iv and _atm_iv > 0:
            try:
                await capture_atm_iv(db, index_name, _atm_iv)
                _iv_52w = await get_iv_stats_52w(db, index_name, _atm_iv)
                _iv_rank_52w = _iv_52w.get("iv_rank_52w")
            except Exception:
                pass  # Non-fatal: 52-week IV is enrichment only

        # ── Fetch India VIX ──────────────────────────────────────────────────
        india_vix = await _get_india_vix()

        # ── Fetch index historical OHLCV for tech snapshot ───────────────────
        index_tech_snap: dict = {}
        try:
            # Kite is the sole historical data source
            hist_index = await _get_hist_ohlcv(index_name.replace("^", ""), period="6mo")
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
                    fundamental={},  # Index has no individual fundamental data
                    max_pain=_max_pain,
                    iv_rank=_iv_rank,
                    iv_rank_52w=_iv_rank_52w,
                    atm_iv=_atm_iv,
                    oi_buildup=_oi_buildup,
                    gex=_gex,
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
        assured_signals=assured_signals[:4],  # Cap: top 4 per index
        watchlist_signals=watchlist_signals[:8],
        non_directional_strategies=non_directional,
        rejection_note=rejection_note,
        with_consolidated_report=with_report,
        without_consolidated_report=without_report,
    )


async def _build_stock_fno_signals(refreshed_at: str) -> list[FNOSignalResponse]:
    _s = _srv()
    db = _s.db
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP
    get_stock_core = _s.get_stock_core
    get_minutes_to_expiry = _s.get_minutes_to_expiry
    _get_india_vix = _s._get_india_vix
    _get_fundamental_data = _s._get_fundamental_data
    check_stock_eligibility = _s.check_stock_eligibility
    _get_hist_ohlcv = _s._get_hist_ohlcv
    _resolve_verified_lot_size = _s._resolve_verified_lot_size
    _fetch_option_snapshots_from_kite = _s._fetch_option_snapshots_from_kite
    compute_option_chain_analytics = _s.compute_option_chain_analytics
    _fetch_live_option_snapshot = _s._fetch_live_option_snapshot
    _to_float = _s._to_float
    from services.fo_universe import get_fo_universe
    # ── Mini-Batch: Use full F&O universe instead of hardcoded 14 stocks ──
    all_symbols = get_fo_universe(lot_size_map=LOT_SIZE_MAP, include_indices=False)
    logger.info(f"F&O universe: {len(all_symbols)} total symbols")

    # ── Pre-filter: Only process symbols that have lot sizes and option data ──
    # This avoids fetching data for 181 symbols when most won't have live chains.
    # First: Get symbols that exist in kite_option_master (have option chains)
    available_in_kite: set[str] = set()
    try:
        coll = db.get_collection("kite_option_master")
        db_underlyings = await coll.distinct("underlying")
        available_in_kite = {u for u in db_underlyings if u and u not in ("NIFTY", "BANKNIFTY")}
    except Exception:
        pass

    # If Kite data available, filter to those. Otherwise use LOT_SIZE_MAP stocks.
    if available_in_kite:
        symbols = sorted(available_in_kite & set(all_symbols))
    else:
        # Fallback: use all symbols that have lot sizes
        symbols = [s for s in all_symbols if s in LOT_SIZE_MAP]

    # Safety cap: process max 40 stocks to stay within gateway timeout
    MAX_SCAN = 40
    if len(symbols) > MAX_SCAN:
        # Prioritize: pick a diverse set — large-cap names first + random others
        _priority = [
            "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "LT",
            "BAJFINANCE", "ITC", "KOTAKBANK", "AXISBANK", "TATAMOTORS", "MARUTI",
            "SUNPHARMA", "BHARTIARTL", "HCLTECH", "WIPRO", "TITAN", "ADANIENT",
            "M&M", "NTPC", "TATASTEEL", "DRREDDY", "CIPLA", "HINDALCO",
        ]
        priority_set = [s for s in _priority if s in symbols]
        remaining = [s for s in symbols if s not in _priority]
        symbols = (priority_set + remaining)[:MAX_SCAN]

    logger.info(f"Building stock F&O signals for {len(symbols)} symbols (from {len(all_symbols)} universe)")
    cores = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_cores = [StockCoreNormalized(**row) for row in cores]
    semaphore = asyncio.Semaphore(8)  # Higher concurrency for speed

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
            lot_size_val = await _resolve_verified_lot_size(symbol, None)

            # ── Option chain analytics: fetch ±5 strikes for PCR / Max Pain / GEX / OI Buildup ──
            _n_extra = 5
            _ana_contracts = [
                FNOContract(
                    script=_format_script(symbol, expiry, float(k), ot),
                    underlying=symbol,
                    expiry=expiry,
                    expiry_time_ist="15:30",
                    strike=float(k),
                    option_type=ot,
                    exchange="NFO",
                    lot_size=lot_size_val,
                )
                for k in range(
                    int(strike - _n_extra * step),
                    int(strike + _n_extra * step + step),
                    step,
                )
                for ot in ["CE", "PE"]
            ]
            _ana_kite_map: dict[str, dict] = {}
            try:
                _ana_kite_map = await _fetch_option_snapshots_from_kite(_ana_contracts)
            except Exception:
                pass
            _stock_analytics: dict = {}
            _stock_iv_rank_52w = None
            if _ana_kite_map:
                _stock_analytics = compute_option_chain_analytics(
                    _ana_contracts, _ana_kite_map, core.ltp, step
                )
                # ── 52-Week IV Rank for stock ────────────────────────
                _stock_atm_iv = _stock_analytics.get("atm_iv")
                if _stock_atm_iv and _stock_atm_iv > 0:
                    try:
                        await capture_atm_iv(db, symbol, _stock_atm_iv)
                        _iv_52 = await get_iv_stats_52w(db, symbol, _stock_atm_iv)
                        _stock_iv_rank_52w = _iv_52.get("iv_rank_52w")
                    except Exception:
                        pass

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
                    lot_size=lot_size_val,
                )
                minutes_to_expiry = get_minutes_to_expiry(contract)
                if minutes_to_expiry <= 15:
                    logger.warning(f"{symbol} {option_type}: Expiry too soon ({minutes_to_expiry}m)")
                    continue

                # Reuse snapshot from analytics map if available; else fetch individually
                snapshot = _ana_kite_map.get(contract.script)
                if snapshot is None:
                    try:
                        snapshot = await _fetch_live_option_snapshot(contract)
                    except Exception as exc:
                        logger.warning(f"{symbol} {option_type}: Failed to fetch snapshot: {exc}")
                        continue
                option_ltp = _to_float(snapshot.get("ltp"))
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
                        fundamental=fundamental,
                        max_pain=_stock_analytics.get("max_pain"),
                        iv_rank=_stock_analytics.get("iv_rank"),
                        iv_rank_52w=_stock_iv_rank_52w,
                        atm_iv=_stock_analytics.get("atm_iv"),
                        oi_buildup=_stock_analytics.get("oi_buildup"),
                        gex=_stock_analytics.get("gex"),
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
    
    logger.info(f"Stock F&O signals: {len(results)} total from {len(symbols)}-symbol universe, returning top 10")
    return results[:10]

