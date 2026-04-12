"""
F&O Confluence Scoring — Pure computation functions for signal scoring.

Extracted from fno_signal_engine.py for modularity.
Contains: _compute_initial_option_targets, _compute_initial_option_sl,
          _calculate_confluence_score_master_spec, _get_signal_quality
"""
from __future__ import annotations

from typing import Literal

from models import StockCoreNormalized
from services.technical_core import compute_technical_confluence_bonus


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


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
    if confluence_score >= 75:
        return "HIGH"
    if confluence_score >= 55:
        return "MEDIUM"
    return "LOW"

