"""
4-Bucket Confluence Score — Section 7 of Master Spec.

Replaces the old "Piotroski + RSI" style scoring with a 4-bucket system:
  A = Strategy & backtest robustness (0-100)
  B = Intraday direction & structure (0-100)
  C = Options, order-flow & sentiment (0-100)
  D = Trade quality & portfolio fit (0-100)

Final Score = 0.30*A + 0.30*B + 0.25*C + 0.15*D
If Score < 78 → suppress signal.

Fundamentals (Piotroski, Altman) are ONLY eligibility gates (section 1.5),
NOT included in A/B/C/D for intraday F&O.

All calculations are pure Python. NO LLM numeric work.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bucket A — Strategy & Backtest Robustness (0-100)
# ---------------------------------------------------------------------------

def compute_bucket_a(
    win_rate: float | None = None,
    expectancy_r: float | None = None,
    trade_count: int | None = None,
    strategy_enabled: bool = True,
) -> dict[str, Any]:
    """
    Score based on strategy backtest performance.

    If config disabled or trade_count < 100 → A = 0.
    Else map (win_rate, expectancy_R) into [0,100].
    """
    if not strategy_enabled or (trade_count is not None and trade_count < 100):
        return {"score": 0, "reason": "strategy_disabled_or_insufficient_data"}

    # Default values when no backtest data available
    wr = win_rate if win_rate is not None else 0.65
    er = expectancy_r if expectancy_r is not None else 0.30
    tc = trade_count if trade_count is not None else 0

    # Win rate contribution (0-60)
    if wr >= 0.85:
        wr_score = 60
    elif wr >= 0.80:
        wr_score = 55
    elif wr >= 0.75:
        wr_score = 48
    elif wr >= 0.70:
        wr_score = 40
    elif wr >= 0.65:
        wr_score = 30
    elif wr >= 0.60:
        wr_score = 20
    else:
        wr_score = 10

    # Expectancy R contribution (0-30)
    if er >= 1.0:
        er_score = 30
    elif er >= 0.70:
        er_score = 25
    elif er >= 0.50:
        er_score = 20
    elif er >= 0.40:
        er_score = 15
    elif er >= 0.30:
        er_score = 10
    else:
        er_score = 5

    # Trade count confidence (0-10)
    if tc >= 200:
        tc_score = 10
    elif tc >= 100:
        tc_score = 8
    elif tc >= 50:
        tc_score = 5
    else:
        tc_score = 2  # provisional

    score = min(100, wr_score + er_score + tc_score)

    return {
        "score": score,
        "win_rate": wr,
        "expectancy_r": er,
        "trade_count": tc,
        "breakdown": {"wr_score": wr_score, "er_score": er_score, "tc_score": tc_score},
    }


# ---------------------------------------------------------------------------
# Bucket B — Intraday Direction & Structure (0-100)
# ---------------------------------------------------------------------------

def compute_bucket_b(
    direction: str = "NEUTRAL",
    bias_score: float = 0.0,
    trend_alignment: str | None = None,
    rsi: float | None = None,
    macd_bullish: bool | None = None,
    adx: float | None = None,
    above_vwap: bool | None = None,
    sector_breadth_score: float | None = None,
    index_breadth_score: float | None = None,
    regime: str = "LowVolRange",
    stoch_k: float | None = None,
) -> dict[str, Any]:
    """
    Score based on intraday direction, multi-timeframe alignment,
    sector/index breadth, and regime.
    """
    score = 0

    # 1. Direction clarity (0-25)
    if direction == "NEUTRAL":
        dir_score = 0
    else:
        abs_bias = abs(bias_score)
        if abs_bias > 2.5:
            dir_score = 25
        elif abs_bias > 1.5:
            dir_score = 20
        elif abs_bias > 0.8:
            dir_score = 15
        elif abs_bias > 0.3:
            dir_score = 10
        else:
            dir_score = 5
    score += dir_score

    # 2. Trend alignment (0-20)
    ta_score = 0
    if trend_alignment:
        ta_upper = trend_alignment.upper()
        if direction == "BULLISH" and ta_upper == "BULLISH":
            ta_score = 20
        elif direction == "BEARISH" and ta_upper == "BEARISH":
            ta_score = 20
        elif ta_upper == "NEUTRAL":
            ta_score = 8
        elif ta_upper in ("BULLISH", "BEARISH"):
            ta_score = 3  # misaligned
    else:
        ta_score = 8  # unknown
    score += ta_score

    # 3. RSI context (0-15)
    rsi_score = 7  # default neutral
    if rsi is not None:
        if direction == "BULLISH":
            if 30 <= rsi <= 50:
                rsi_score = 15  # pullback zone — ideal for CE
            elif 50 < rsi <= 65:
                rsi_score = 12
            elif rsi < 30:
                rsi_score = 10  # oversold bounce
            elif rsi > 70:
                rsi_score = 3   # overbought — risky for fresh CE
        elif direction == "BEARISH":
            if 50 <= rsi <= 70:
                rsi_score = 15  # pullback zone — ideal for PE
            elif 35 < rsi < 50:
                rsi_score = 12
            elif rsi > 70:
                rsi_score = 10  # overbought — good for PE
            elif rsi < 30:
                rsi_score = 3   # oversold — risky for fresh PE
    score += rsi_score

    # 4. ADX trend strength (0-10)
    adx_score = 5
    if adx is not None:
        if adx >= 30:
            adx_score = 10  # strong trend
        elif adx >= 22:
            adx_score = 7
        elif adx >= 15:
            adx_score = 4
        else:
            adx_score = 2  # no trend
    score += adx_score

    # 5. MACD confirmation (0-8)
    macd_score = 4
    if macd_bullish is not None:
        if (direction == "BULLISH" and macd_bullish) or (direction == "BEARISH" and not macd_bullish):
            macd_score = 8
        elif (direction == "BULLISH" and not macd_bullish) or (direction == "BEARISH" and macd_bullish):
            macd_score = 1  # conflicting
    score += macd_score

    # 6. Breadth / sector support (0-12)
    breadth_score_val = 6
    if index_breadth_score is not None:
        if direction == "BULLISH" and index_breadth_score >= 60:
            breadth_score_val = 12
        elif direction == "BEARISH" and index_breadth_score <= 40:
            breadth_score_val = 12
        elif 40 < index_breadth_score < 60:
            breadth_score_val = 6
        else:
            breadth_score_val = 2  # conflicting
    elif sector_breadth_score is not None:
        if sector_breadth_score >= 60:
            breadth_score_val = 8
        elif sector_breadth_score <= 40:
            breadth_score_val = 8
        else:
            breadth_score_val = 5
    score += breadth_score_val

    # 7. Regime compatibility (0-10)
    regime_score = 5
    favorable_regimes = {
        "BULLISH": {"LowVolTrend": 10, "HighVolTrend": 7, "LowVolRange": 4, "PostEventIVCrush": 3},
        "BEARISH": {"HighVolCrash": 10, "HighVolTrend": 7, "LowVolRange": 4, "PreEvent": 6},
    }
    regime_map = favorable_regimes.get(direction, {})
    regime_score = regime_map.get(regime, 5)
    score += regime_score

    score = min(100, score)

    return {
        "score": score,
        "breakdown": {
            "direction": dir_score,
            "trend_alignment": ta_score,
            "rsi": rsi_score,
            "adx": adx_score,
            "macd": macd_score,
            "breadth": breadth_score_val,
            "regime": regime_score,
        },
    }


# ---------------------------------------------------------------------------
# Bucket C — Options, Order-Flow & Sentiment (0-100)
# ---------------------------------------------------------------------------

def compute_bucket_c(
    oi_buildup: str | None = None,
    iv_rank: float | None = None,
    is_liquid: bool = True,
    spread_pct: float | None = None,
    flow_band: str = "NeutralFlow",
    news_flag: str = "NEUTRAL",
    direction: str = "BULLISH",
    pcr: float | None = None,
    volume_ratio: float | None = None,
) -> dict[str, Any]:
    """
    Score based on options data, order flow, and news sentiment.
    """
    score = 0

    # 1. OI buildup alignment (0-25)
    oi_score = 12  # default neutral
    if oi_buildup:
        if direction == "BULLISH":
            if oi_buildup == "LONG_BUILDUP":
                oi_score = 25
            elif oi_buildup == "SHORT_COVERING":
                oi_score = 20
            elif oi_buildup == "SHORT_BUILDUP":
                oi_score = 5   # conflicting
            elif oi_buildup == "LONG_UNWINDING":
                oi_score = 3   # bad for bulls
        elif direction == "BEARISH":
            if oi_buildup == "SHORT_BUILDUP":
                oi_score = 25
            elif oi_buildup == "LONG_UNWINDING":
                oi_score = 20
            elif oi_buildup == "LONG_BUILDUP":
                oi_score = 5
            elif oi_buildup == "SHORT_COVERING":
                oi_score = 3
    score += oi_score

    # 2. IV Rank (0-20)
    iv_score = 10
    if iv_rank is not None:
        if direction == "BULLISH":
            # Low IV = cheap options = good for buying
            if iv_rank < 20:
                iv_score = 20
            elif iv_rank < 40:
                iv_score = 15
            elif iv_rank < 60:
                iv_score = 10
            elif iv_rank < 80:
                iv_score = 5
            else:
                iv_score = 2  # very expensive
        elif direction == "BEARISH":
            # High IV = fear = good for PE buying
            if iv_rank > 70:
                iv_score = 18
            elif iv_rank > 50:
                iv_score = 14
            else:
                iv_score = 8
    score += iv_score

    # 3. Liquidity (0-15)
    liq_score = 8
    if not is_liquid:
        liq_score = 2  # heavy penalty
    elif spread_pct is not None:
        if spread_pct < 0.5:
            liq_score = 15
        elif spread_pct < 1.0:
            liq_score = 12
        elif spread_pct < 2.0:
            liq_score = 8
        else:
            liq_score = 3
    score += liq_score

    # 4. Order flow (0-15)
    flow_score = 7
    if direction == "BULLISH":
        flow_map = {"StrongBuyFlow": 15, "ModerateBuyFlow": 12, "NeutralFlow": 7,
                     "ModerateSellFlow": 3, "StrongSellFlow": 0}
    else:
        flow_map = {"StrongSellFlow": 15, "ModerateSellFlow": 12, "NeutralFlow": 7,
                     "ModerateBuyFlow": 3, "StrongBuyFlow": 0}
    flow_score = flow_map.get(flow_band, 7)
    score += flow_score

    # 5. News sentiment (0-15)
    news_score = 7
    if direction == "BULLISH":
        if news_flag == "POSITIVE":
            news_score = 15
        elif news_flag == "NEGATIVE":
            news_score = 0  # strong penalty
    elif direction == "BEARISH":
        if news_flag == "NEGATIVE":
            news_score = 15  # fear helps PE
        elif news_flag == "POSITIVE":
            news_score = 0
    score += news_score

    # 6. PCR alignment (0-10)
    pcr_score = 5
    if pcr is not None:
        if direction == "BULLISH":
            if pcr > 1.3:
                pcr_score = 10  # extreme bearish sentiment = contrarian CE buy
            elif pcr > 1.0:
                pcr_score = 8
            elif 0.7 <= pcr <= 1.0:
                pcr_score = 5
            else:
                pcr_score = 2
        elif direction == "BEARISH":
            if pcr < 0.7:
                pcr_score = 10
            elif pcr < 1.0:
                pcr_score = 7
            else:
                pcr_score = 4
    score += pcr_score

    score = min(100, score)

    return {
        "score": score,
        "breakdown": {
            "oi_buildup": oi_score,
            "iv_rank": iv_score,
            "liquidity": liq_score,
            "flow": flow_score,
            "news": news_score,
            "pcr": pcr_score,
        },
    }


# ---------------------------------------------------------------------------
# Bucket D — Trade Quality & Portfolio Fit (0-100)
# ---------------------------------------------------------------------------

def compute_bucket_d(
    rr_to_t1: float = 1.0,
    rr_to_t2: float = 1.5,
    rr_to_best_exit: float | None = None,
    t1_p_hit: float | None = None,
    t2_p_hit: float | None = None,
    sl_distance_pct: float = 10.0,
    existing_exposure_same_direction: int = 0,
    existing_exposure_same_sector: int = 0,
) -> dict[str, Any]:
    """
    Score based on trade quality (R:R, probability) and portfolio fit.

    Hard vetoes:
      rr_to_t1 < 1.0  → D = 0 (hard zero, signal should be suppressed)
      rr_to_t2 < 1.5  → D capped at 50

    Adjustments:
      t2_p_hit < 0.45 → D -= 15
      rr_to_best_exit >= 2.0 AND t2_p_hit >= 0.55 → D += 10 (bonus)
    """
    # Hard veto: R:R to T1 below 1.0
    if rr_to_t1 < 1.0:
        return {
            "score": 0,
            "hard_veto": True,
            "veto_reason": f"rr_to_t1={rr_to_t1:.2f}<1.0",
            "breakdown": {
                "rr_t1": 0, "rr_t2": 0, "probability": 0,
                "sl_distance": 0, "concentration": 0,
                "rr_best_exit": 0, "t2_prob_adj": 0, "exit_bonus": 0,
            },
        }

    score = 0

    # 1. R:R to T1 (0-30)
    if rr_to_t1 >= 2.5:
        rr1_score = 30
    elif rr_to_t1 >= 2.0:
        rr1_score = 25
    elif rr_to_t1 >= 1.5:
        rr1_score = 20
    elif rr_to_t1 >= 1.2:
        rr1_score = 15
    elif rr_to_t1 >= 1.0:
        rr1_score = 10
    else:
        rr1_score = 2
    score += rr1_score

    # 2. R:R to T2 (0-20)
    if rr_to_t2 >= 3.0:
        rr2_score = 20
    elif rr_to_t2 >= 2.0:
        rr2_score = 16
    elif rr_to_t2 >= 1.5:
        rr2_score = 12
    elif rr_to_t2 >= 1.2:
        rr2_score = 8
    else:
        rr2_score = 2
    score += rr2_score

    # 3. Probability of T1 hit (0-20)
    prob_score = 10
    if t1_p_hit is not None:
        if t1_p_hit >= 0.80:
            prob_score = 20
        elif t1_p_hit >= 0.70:
            prob_score = 16
        elif t1_p_hit >= 0.60:
            prob_score = 12
        elif t1_p_hit >= 0.50:
            prob_score = 8
        else:
            prob_score = 4
    score += prob_score

    # 4. SL distance (0-15)
    if sl_distance_pct <= 8:
        sl_score = 15
    elif sl_distance_pct <= 12:
        sl_score = 12
    elif sl_distance_pct <= 18:
        sl_score = 8
    elif sl_distance_pct <= 25:
        sl_score = 5
    else:
        sl_score = 2
    score += sl_score

    # 5. Portfolio concentration penalty (0-15)
    conc_score = 15
    if existing_exposure_same_direction >= 3:
        conc_score = 3
    elif existing_exposure_same_direction >= 2:
        conc_score = 8
    if existing_exposure_same_sector >= 2:
        conc_score = min(conc_score, 5)
    score += conc_score

    # 6. T2 probability penalty: if t2_p_hit < 0.45 → subtract 15
    t2_prob_adj = 0
    _t2_p = t2_p_hit if t2_p_hit is not None else 0.0
    if _t2_p < 0.45:
        t2_prob_adj = -15
        score += t2_prob_adj

    # 7. Best Exit bonus: rr_to_best_exit >= 2.0 AND t2_p_hit >= 0.55 → +10
    exit_bonus = 0
    _rr_be = rr_to_best_exit if rr_to_best_exit is not None else 0.0
    if _rr_be >= 2.0 and _t2_p >= 0.55:
        exit_bonus = 10
        score += exit_bonus

    # Cap: if rr_to_t2 < 1.5, D capped at 50
    if rr_to_t2 < 1.5:
        score = min(score, 50)

    score = min(100, max(0, score))

    return {
        "score": score,
        "hard_veto": False,
        "breakdown": {
            "rr_t1": rr1_score,
            "rr_t2": rr2_score,
            "probability": prob_score,
            "sl_distance": sl_score,
            "concentration": conc_score,
            "t2_prob_adj": t2_prob_adj,
            "exit_bonus": exit_bonus,
            "rr_best_exit": round(_rr_be, 2),
        },
    }


# ---------------------------------------------------------------------------
# Final Confluence Score (section 7.6)
# ---------------------------------------------------------------------------

BUCKET_WEIGHTS = {"A": 0.30, "B": 0.30, "C": 0.25, "D": 0.15}
CONFLUENCE_THRESHOLD = 78


def compute_confluence_score_v2(
    bucket_a: dict,
    bucket_b: dict,
    bucket_c: dict,
    bucket_d: dict,
) -> dict[str, Any]:
    """
    Compute final Confluence Score from 4 buckets.

    Score = 0.30*A + 0.30*B + 0.25*C + 0.15*D
    If Score < 78 → signal should be suppressed.

    Returns: {score, conviction, buckets, should_suppress}
    """
    a = bucket_a.get("score", 0)
    b = bucket_b.get("score", 0)
    c = bucket_c.get("score", 0)
    d = bucket_d.get("score", 0)

    score = round(
        BUCKET_WEIGHTS["A"] * a
        + BUCKET_WEIGHTS["B"] * b
        + BUCKET_WEIGHTS["C"] * c
        + BUCKET_WEIGHTS["D"] * d
    )
    score = min(100, max(0, score))

    # Conviction level
    if score >= 90:
        conviction = "VERY_HIGH"
    elif score >= 85:
        conviction = "HIGH"
    elif score >= 80:
        conviction = "MEDIUM_HIGH"
    elif score >= 78:
        conviction = "MEDIUM"
    elif score >= 70:
        conviction = "LOW"
    else:
        conviction = "VERY_LOW"

    return {
        "score": score,
        "conviction": conviction,
        "should_suppress": score < CONFLUENCE_THRESHOLD,
        "buckets": {
            "A": a,
            "B": b,
            "C": c,
            "D": d,
        },
        "weights": dict(BUCKET_WEIGHTS),
        "breakdown": {
            "A_detail": bucket_a.get("breakdown"),
            "B_detail": bucket_b.get("breakdown"),
            "C_detail": bucket_c.get("breakdown"),
            "D_detail": bucket_d.get("breakdown"),
        },
    }
