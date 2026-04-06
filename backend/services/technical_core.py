"""
Technical Core — Full technical snapshot, urgent exit detection,
confluence scoring, and portfolio verdict.
Depends on: indicators.py + advanced_indicators.py
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from services.indicators import (
    compute_rsi, compute_macd, compute_bollinger, compute_atr, compute_adx,
    compute_obv, compute_sma, compute_ema, compute_stochastic,
    compute_historical_volatility,
)
from services.advanced_indicators import (
    compute_williams_r, compute_cci, compute_vpt, compute_ad_line,
    compute_ichimoku, compute_fibonacci_levels, compute_pivot_points,
    compute_support_resistance, detect_rsi_divergence,
    detect_candlestick_patterns, compute_multiframe_trend, detect_chart_patterns,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# FULL TECHNICAL SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def compute_full_technical_snapshot(
    symbol: str,
    hist: pd.DataFrame,
    ltp: float | None = None,
) -> dict[str, Any]:
    """
    Comprehensive technical snapshot (Batch 1 enhanced).
    Includes: RSI, MACD, BB, ATR, ADX, OBV, Stochastic, SMAs/EMAs, Hist-Vol,
              Williams %R, CCI, VPT, A/D Line, Ichimoku, Fibonacci, Pivot Points,
              Support/Resistance, RSI Divergence, Candlestick Patterns,
              Multi-timeframe Trend, Chart Patterns.
    """
    if hist is None or hist.empty:
        return {"symbol": symbol, "data_available": False}

    close = hist["Close"]

    # ── Core indicators ───────────────────────────────────────────────────────
    rsi = compute_rsi(close)
    macd_data = compute_macd(close)
    bb_data = compute_bollinger(close)
    atr_val = compute_atr(hist)
    adx_val = compute_adx(hist)
    obv_data = compute_obv(hist)
    stoch = compute_stochastic(hist)

    # ── Moving averages ───────────────────────────────────────────────────────
    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    ema_20 = compute_ema(close, 20)
    ema_9 = compute_ema(close, 9)

    # ── Volatility ────────────────────────────────────────────────────────────
    hist_vol = compute_historical_volatility(close)

    # ── Advanced indicators (Batch 1) ─────────────────────────────────────────
    williams_r = compute_williams_r(hist)
    cci_data = compute_cci(hist)
    vpt_data = compute_vpt(hist)
    ad_data = compute_ad_line(hist)
    ichimoku = compute_ichimoku(hist)
    fibonacci = compute_fibonacci_levels(hist)
    pivots = compute_pivot_points(hist)
    sr = compute_support_resistance(hist)
    rsi_div = detect_rsi_divergence(hist)
    candle_patterns = detect_candlestick_patterns(hist)
    mf_trend = compute_multiframe_trend(hist)
    chart_pats = detect_chart_patterns(hist)

    # ── Trend alignment (MA-based) ────────────────────────────────────────────
    price = float(close.iloc[-1]) if ltp is None else ltp
    above_sma50 = price > sma_50 if sma_50 is not None else None
    above_sma200 = price > sma_200 if sma_200 is not None else None
    above_ema20 = price > ema_20 if ema_20 is not None else None

    if above_sma200 is True and above_sma50 is True and above_ema20 is True:
        trend_alignment = "BULLISH_ALIGNED"
    elif above_sma200 is False and above_sma50 is False and above_ema20 is False:
        trend_alignment = "BEARISH_ALIGNED"
    elif above_sma50 is True and above_ema20 is True:
        trend_alignment = "SHORT_TERM_BULLISH"
    elif above_sma50 is False and above_ema20 is False:
        trend_alignment = "SHORT_TERM_BEARISH"
    else:
        trend_alignment = "MIXED"

    # ── Aggregated signal count ───────────────────────────────────────────────
    bullish_signals = 0
    bearish_signals = 0

    if rsi is not None:
        if rsi < 40:
            bullish_signals += 1
        elif rsi > 65:
            bearish_signals += 1

    if macd_data.get("bullish_crossover"):
        bullish_signals += 1
    if macd_data.get("bearish_crossover"):
        bearish_signals += 1
    if macd_data.get("above_zero"):
        bullish_signals += 1
    else:
        bearish_signals += 1

    if trend_alignment == "BULLISH_ALIGNED":
        bullish_signals += 2
    elif trend_alignment == "BEARISH_ALIGNED":
        bearish_signals += 2

    if bb_data.get("near_lower"):
        bullish_signals += 1
    if bb_data.get("near_upper"):
        bearish_signals += 1

    if obv_data.get("trend") == "RISING":
        bullish_signals += 1
    elif obv_data.get("trend") == "FALLING":
        bearish_signals += 1

    if williams_r is not None:
        if williams_r < -80:
            bullish_signals += 1
        elif williams_r > -20:
            bearish_signals += 1

    if cci_data.get("oversold"):
        bullish_signals += 1
    if cci_data.get("overbought"):
        bearish_signals += 1

    if vpt_data.get("trend") == "RISING":
        bullish_signals += 1
    elif vpt_data.get("trend") == "FALLING":
        bearish_signals += 1

    if ichimoku.get("bullish_signal"):
        bullish_signals += 2
    if ichimoku.get("bearish_signal"):
        bearish_signals += 2
    if ichimoku.get("tenkan_kijun_cross") == "BULLISH":
        bullish_signals += 1
    elif ichimoku.get("tenkan_kijun_cross") == "BEARISH":
        bearish_signals += 1

    if rsi_div.get("bullish"):
        bullish_signals += 1
    if rsi_div.get("bearish"):
        bearish_signals += 1

    if candle_patterns.get("bias") == "BULLISH":
        bullish_signals += 1
    elif candle_patterns.get("bias") == "BEARISH":
        bearish_signals += 1

    mf_align = mf_trend.get("alignment", "MIXED")
    if mf_align in ("STRONGLY_BULLISH",):
        bullish_signals += 2
    elif mf_align == "BULLISH":
        bullish_signals += 1
    elif mf_align in ("STRONGLY_BEARISH",):
        bearish_signals += 2
    elif mf_align == "BEARISH":
        bearish_signals += 1

    if chart_pats.get("has_bullish_pattern"):
        bullish_signals += 1
    if chart_pats.get("has_bearish_pattern"):
        bearish_signals += 1

    technical_bias = (
        "BULLISH" if bullish_signals > bearish_signals + 1
        else "BEARISH" if bearish_signals > bullish_signals + 1
        else "NEUTRAL"
    )

    return {
        "symbol": symbol,
        "data_available": True,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "macd": macd_data,
        "bollinger": bb_data,
        "atr": round(atr_val, 2) if atr_val is not None else None,
        "adx": round(adx_val, 1) if adx_val is not None else None,
        "stochastic": stoch,
        "obv": obv_data,
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "ema_20": round(ema_20, 2) if ema_20 is not None else None,
        "ema_9": round(ema_9, 2) if ema_9 is not None else None,
        "hist_vol": hist_vol,
        "hist_vol_pct": round(hist_vol * 100, 1) if hist_vol is not None else None,
        "trend_alignment": trend_alignment,
        "above_sma50": above_sma50,
        "above_sma200": above_sma200,
        "above_ema20": above_ema20,
        "williams_r": williams_r,
        "williams_r_oversold": williams_r is not None and williams_r < -80,
        "williams_r_overbought": williams_r is not None and williams_r > -20,
        "cci": cci_data,
        "vpt": vpt_data,
        "ad_line": ad_data,
        "ichimoku": ichimoku,
        "fibonacci": fibonacci,
        "pivot_points": pivots,
        "support_resistance": sr,
        "rsi_divergence": rsi_div,
        "candlestick_patterns": candle_patterns,
        "multiframe_trend": mf_trend,
        "chart_patterns": chart_pats,
        "technical_bias": technical_bias,
        "bullish_signal_count": bullish_signals,
        "bearish_signal_count": bearish_signals,
        "data_points": len(hist),
    }


# ─────────────────────────────────────────────────────────────────────────────
# URGENT EXIT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def check_urgent_exit(
    position: dict,
    current_ltp: float,
    minutes_to_session_close: int,
    market_regime: dict | None = None,
) -> dict[str, Any]:
    """
    Detect if a custom position needs URGENT EXIT.
    """
    buy_price = float(position.get("buy_price", 0))
    remaining_trading_days = int(position.get("remaining_trading_days", 99))
    if buy_price <= 0 or current_ltp <= 0:
        return {"urgent_exit": False, "reason": ""}

    pnl_pct = ((current_ltp - buy_price) / buy_price) * 100
    loss_pct = abs(pnl_pct) if pnl_pct < 0 else 0.0

    if remaining_trading_days == 0:
        if pnl_pct < 0:
            return {
                "urgent_exit": True,
                "reason": f"EXPIRY TODAY with loss {pnl_pct:.1f}% — exit immediately at best price",
                "best_price_hint": round(current_ltp * 1.005, 2),
            }
        elif minutes_to_session_close <= 45:
            return {
                "urgent_exit": True,
                "reason": f"EXPIRY TODAY — {minutes_to_session_close}m to close; lock in profit now",
                "best_price_hint": round(current_ltp * 0.998, 2),
            }

    if minutes_to_session_close <= 60 and loss_pct >= 10:
        return {
            "urgent_exit": True,
            "reason": f"Only {minutes_to_session_close}m to market close with {loss_pct:.1f}% loss — recovery unlikely; exit at best price within 60s",
            "best_price_hint": round(current_ltp * 1.005, 2),
        }

    if loss_pct >= 25 and minutes_to_session_close <= 90:
        return {
            "urgent_exit": True,
            "reason": f"Sharp {loss_pct:.1f}% decline from entry with only {minutes_to_session_close}m to close — trend reversal confirmed; exit at best price",
            "best_price_hint": round(current_ltp * 1.008, 2),
        }

    if market_regime and market_regime.get("regime") == "CRASH_MODE" and loss_pct >= 15:
        return {
            "urgent_exit": True,
            "reason": f"Market in CRASH regime (VIX={market_regime.get('vix', 'N/A')}) with {loss_pct:.1f}% position loss — exit recommended",
            "best_price_hint": round(current_ltp * 1.01, 2),
        }

    return {"urgent_exit": False, "reason": "", "best_price_hint": None}


# ─────────────────────────────────────────────────────────────────────────────
# CONFLUENCE SCORE ENHANCEMENTS (additive inputs)
# ─────────────────────────────────────────────────────────────────────────────

def compute_technical_confluence_bonus(
    direction: str,
    rsi: float | None,
    macd_bullish: bool | None,
    macd_above_zero: bool | None,
    trend_alignment: str | None,
    obv_trend: str | None,
    adx: float | None,
    bb_pct_b: float | None,
    stoch_k: float | None,
    williams_r: float | None = None,
    cci: float | None = None,
    vpt_trend: str | None = None,
    ichimoku_price_vs_cloud: str | None = None,
    ichimoku_tk_cross: str | None = None,
    ichimoku_bullish: bool | None = None,
    ichimoku_bearish: bool | None = None,
    rsi_divergence: str | None = None,
    rsi_div_type: str | None = None,
    candle_bias: str | None = None,
    mf_alignment: str | None = None,
    has_bull_chart_pattern: bool = False,
    has_bear_chart_pattern: bool = False,
    ad_trend: str | None = None,
) -> tuple[int, list[str]]:
    """
    Compute additive technical bonus score for confluence scoring (Batch 1 enhanced).
    Returns (bonus_score: int, trigger_tags: list[str]).
    Cap raised to 18 to accommodate Batch 1 indicators.
    """
    bonus = 0
    tags: list[str] = []

    if rsi is not None:
        if direction == "BULLISH":
            if 35 <= rsi <= 50:
                bonus += 4; tags.append(f"RSI={rsi:.0f}(OversoldRecovery)")
            elif 25 <= rsi < 35:
                bonus += 3; tags.append(f"RSI={rsi:.0f}(Oversold)")
            elif 50 < rsi <= 60:
                bonus += 2; tags.append(f"RSI={rsi:.0f}(Rising)")
            elif rsi > 70:
                bonus -= 2; tags.append(f"RSI={rsi:.0f}(Overbought-Caution)")
        elif direction == "BEARISH":
            if 50 <= rsi <= 65:
                bonus += 4; tags.append(f"RSI={rsi:.0f}(Overbought)")
            elif rsi > 65:
                bonus += 3; tags.append(f"RSI={rsi:.0f}(ExtremOverbought)")
            elif 40 < rsi < 50:
                bonus += 2; tags.append(f"RSI={rsi:.0f}(Falling)")
            elif rsi < 30:
                bonus -= 2; tags.append(f"RSI={rsi:.0f}(Oversold-Caution)")

    if macd_bullish is not None:
        if direction == "BULLISH" and macd_bullish:
            bonus += 3; tags.append("MACD_BullishCross")
        elif direction == "BEARISH" and not macd_bullish and macd_above_zero is False:
            bonus += 3; tags.append("MACD_BearishCross")
        elif direction == "BULLISH" and macd_above_zero:
            bonus += 1; tags.append("MACD_AboveZero")
        elif direction == "BEARISH" and not macd_above_zero:
            bonus += 1; tags.append("MACD_BelowZero")

    if trend_alignment == "BULLISH_ALIGNED" and direction == "BULLISH":
        bonus += 3; tags.append("TrendAligned_Bullish")
    elif trend_alignment == "BEARISH_ALIGNED" and direction == "BEARISH":
        bonus += 3; tags.append("TrendAligned_Bearish")
    elif trend_alignment == "SHORT_TERM_BULLISH" and direction == "BULLISH":
        bonus += 1; tags.append("ShortTermBullish")
    elif trend_alignment == "SHORT_TERM_BEARISH" and direction == "BEARISH":
        bonus += 1; tags.append("ShortTermBearish")

    if obv_trend == "RISING" and direction == "BULLISH":
        bonus += 1; tags.append("OBV_Rising")
    elif obv_trend == "FALLING" and direction == "BEARISH":
        bonus += 1; tags.append("OBV_Falling")

    if adx is not None:
        if adx > 30:
            bonus += 2; tags.append(f"ADX={adx:.0f}(StrongTrend)")
        elif adx > 20:
            bonus += 1; tags.append(f"ADX={adx:.0f}(ModTrend)")

    if bb_pct_b is not None:
        if bb_pct_b < 0.15 and direction == "BULLISH":
            bonus += 1; tags.append("BB_NearSupport")
        elif bb_pct_b > 0.85 and direction == "BEARISH":
            bonus += 1; tags.append("BB_NearResistance")

    if stoch_k is not None:
        if stoch_k < 20 and direction == "BULLISH":
            bonus += 1; tags.append(f"Stoch={stoch_k:.0f}(Oversold)")
        elif stoch_k > 80 and direction == "BEARISH":
            bonus += 1; tags.append(f"Stoch={stoch_k:.0f}(Overbought)")

    if williams_r is not None:
        if williams_r < -80 and direction == "BULLISH":
            bonus += 1; tags.append(f"WilliamsR={williams_r:.0f}(Oversold)")
        elif williams_r > -20 and direction == "BEARISH":
            bonus += 1; tags.append(f"WilliamsR={williams_r:.0f}(Overbought)")

    if cci is not None:
        if cci < -100 and direction == "BULLISH":
            bonus += 1; tags.append(f"CCI={cci:.0f}(Oversold)")
        elif cci > 100 and direction == "BEARISH":
            bonus += 1; tags.append(f"CCI={cci:.0f}(Overbought)")

    if vpt_trend == "RISING" and direction == "BULLISH":
        bonus += 1; tags.append("VPT_Rising")
    elif vpt_trend == "FALLING" and direction == "BEARISH":
        bonus += 1; tags.append("VPT_Falling")
    elif ad_trend == "RISING" and direction == "BULLISH":
        bonus += 1; tags.append("AD_Accumulation")
    elif ad_trend == "FALLING" and direction == "BEARISH":
        bonus += 1; tags.append("AD_Distribution")

    if ichimoku_bullish and direction == "BULLISH":
        bonus += 3; tags.append("Ichimoku_BullishFull")
    elif ichimoku_bearish and direction == "BEARISH":
        bonus += 3; tags.append("Ichimoku_BearishFull")
    elif ichimoku_price_vs_cloud == "ABOVE" and direction == "BULLISH":
        bonus += 2; tags.append("Ichimoku_PriceAboveCloud")
    elif ichimoku_price_vs_cloud == "BELOW" and direction == "BEARISH":
        bonus += 2; tags.append("Ichimoku_PriceBelowCloud")
    elif ichimoku_price_vs_cloud == "INSIDE":
        bonus -= 1; tags.append("Ichimoku_InsideCloud(Uncertainty)")

    if ichimoku_tk_cross == "BULLISH" and direction == "BULLISH":
        bonus += 1; tags.append("Ichimoku_TKCross_Bullish")
    elif ichimoku_tk_cross == "BEARISH" and direction == "BEARISH":
        bonus += 1; tags.append("Ichimoku_TKCross_Bearish")

    if rsi_divergence == "BULLISH" and direction == "BULLISH":
        pts = 2 if rsi_div_type == "REGULAR" else 1
        bonus += pts; tags.append(f"RSIDivergence_{rsi_div_type}_Bullish")
    elif rsi_divergence == "BEARISH" and direction == "BEARISH":
        pts = 2 if rsi_div_type == "REGULAR" else 1
        bonus += pts; tags.append(f"RSIDivergence_{rsi_div_type}_Bearish")

    if candle_bias == "BULLISH" and direction == "BULLISH":
        bonus += 2; tags.append("CandlePattern_Bullish")
    elif candle_bias == "BEARISH" and direction == "BEARISH":
        bonus += 2; tags.append("CandlePattern_Bearish")
    elif candle_bias is not None and candle_bias != "NEUTRAL" and candle_bias != direction:
        bonus -= 1; tags.append(f"CandlePattern_{candle_bias}(ContraDirection)")

    if mf_alignment in ("STRONGLY_BULLISH",) and direction == "BULLISH":
        bonus += 2; tags.append("MTF_StronglyBullish")
    elif mf_alignment == "BULLISH" and direction == "BULLISH":
        bonus += 1; tags.append("MTF_Bullish")
    elif mf_alignment in ("STRONGLY_BEARISH",) and direction == "BEARISH":
        bonus += 2; tags.append("MTF_StronglyBearish")
    elif mf_alignment == "BEARISH" and direction == "BEARISH":
        bonus += 1; tags.append("MTF_Bearish")

    if has_bull_chart_pattern and direction == "BULLISH":
        bonus += 1; tags.append("ChartPattern_Bullish(Flag/Pennant)")
    elif has_bear_chart_pattern and direction == "BEARISH":
        bonus += 1; tags.append("ChartPattern_Bearish(Flag/Pennant)")

    bonus = max(-6, min(bonus, 18))
    return bonus, tags


# ─────────────────────────────────────────────────────────────────────────────
# ENHANCED PORTFOLIO VERDICT
# ─────────────────────────────────────────────────────────────────────────────

def compute_portfolio_verdict(
    pnl_pct: float,
    price_zone: str,
    value_flag: str,
    rsi: float | None,
    trend_alignment: str | None,
    piotroski: float | None,
    beneish: float | None,
    hist_vol: float | None,
    allocation_pct: float,
) -> tuple[str, str]:
    """
    Compute standardized verdict and comments for portfolio holding.
    Returns (verdict: str, comments: str)
    """
    comments_parts: list[str] = []
    verdict_score = 0

    if pnl_pct > 30:
        verdict_score -= 1
        comments_parts.append(f"Up {pnl_pct:.1f}% — consider partial profit booking")
    elif pnl_pct > 0:
        verdict_score += 1
    elif pnl_pct < -25:
        verdict_score -= 2
        comments_parts.append(f"Down {abs(pnl_pct):.1f}% — review thesis before averaging")
    elif pnl_pct < 0:
        verdict_score -= 1
        comments_parts.append(f"Down {abs(pnl_pct):.1f}% — monitor closely")

    if value_flag == "Attractive":
        verdict_score += 2
        comments_parts.append("Attractive valuation")
    elif value_flag == "Expensive":
        verdict_score -= 1
        comments_parts.append("Expensive valuation")

    if price_zone == "Near 52W low":
        verdict_score += 2
        comments_parts.append("Near 52W low — potential base building")
    elif price_zone == "Near 52W high":
        verdict_score -= 1
        comments_parts.append("Near 52W high — momentum but limited upside buffer")

    if rsi is not None:
        if rsi < 35:
            verdict_score += 2
            comments_parts.append(f"RSI {rsi:.0f} — oversold territory, potential bounce")
        elif rsi > 70:
            verdict_score -= 1
            comments_parts.append(f"RSI {rsi:.0f} — overbought, near-term pullback possible")
        else:
            comments_parts.append(f"RSI {rsi:.0f} — neutral momentum")

    if trend_alignment == "BULLISH_ALIGNED":
        verdict_score += 2
        comments_parts.append("Multi-timeframe bullish trend aligned")
    elif trend_alignment == "BEARISH_ALIGNED":
        verdict_score -= 2
        comments_parts.append("Multi-timeframe bearish trend — cautious stance")
    elif trend_alignment == "MIXED":
        comments_parts.append("Mixed trend signals — wait for confirmation")

    if piotroski is not None:
        if piotroski >= 7:
            verdict_score += 1
            comments_parts.append(f"Piotroski F-Score {piotroski}/9 — high quality")
        elif piotroski <= 3:
            verdict_score -= 1
            comments_parts.append(f"Piotroski F-Score {piotroski}/9 — weak financials")

    if beneish is not None and beneish > -2.22:
        verdict_score -= 1
        comments_parts.append(f"Beneish M-Score {beneish:.2f} — earnings quality concern")

    if allocation_pct > 20:
        comments_parts.append(f"Over-concentrated ({allocation_pct:.1f}% of portfolio) — consider rebalancing")

    if hist_vol is not None and hist_vol > 0.45:
        comments_parts.append(f"High volatility stock ({hist_vol*100:.0f}% annual vol) — position sizing caution")

    if verdict_score >= 5:
        verdict = "BUY MORE NOW"
    elif verdict_score >= 3:
        verdict = "ACCUMULATE ON DIPS"
    elif verdict_score >= 1:
        verdict = "STRONG HOLD"
    elif verdict_score >= -1:
        verdict = "WAIT & WATCH"
    elif verdict_score >= -3:
        verdict = "PARTIAL EXIT"
    else:
        verdict = "EXIT IMMEDIATELY"

    comments = "; ".join(comments_parts) if comments_parts else "Balanced profile — hold and monitor."
    return verdict, comments
