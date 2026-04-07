"""
Sticky Card Monitoring & Alerts — Batch 4 of Master Spec (Section 8).

Implements continuous monitoring for active/sticky F&O positions and
generates backend alert events:
  - NEWS_IMPACT: Adverse news for position direction
  - REGIME_SHIFT: Material regime change with probability drop
  - URGENT_EXIT: Low recovery probability + adverse flow reversal

All calculations are pure Python. NO LLM numeric work.
Events are data-only (no frontend changes).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

EventType = Literal["NEWS_IMPACT", "REGIME_SHIFT", "URGENT_EXIT"]

# Thresholds for alert generation
NEWS_IMPACT_SENTIMENT_THRESHOLD = 0.15
REGIME_SHIFT_P_HIT_DROP_THRESHOLD = 0.15  # 15% drop in P_hit triggers alert
URGENT_EXIT_RECOVERY_THRESHOLD = 0.20  # P(recovery) below 20%
URGENT_EXIT_MIN_REMAINING_MINUTES = 90  # Only trigger in last ~90 min


# ---------------------------------------------------------------------------
# 8.1-8.2  Position Feature Recomputation
# ---------------------------------------------------------------------------

def recompute_position_features(
    position: dict,
    current_ltp: float | None = None,
    underlying_ltp: float | None = None,
    regime: dict | None = None,
    news_sentiment: dict | None = None,
    sector_sentiment: dict | None = None,
    flow_band: str = "NeutralFlow",
    obi: float = 0.0,
    p_hit_t1: float | None = None,
    p_hit_t2: float | None = None,
    p_sl_first: float | None = None,
    best_exit_updated: dict | None = None,
) -> dict[str, Any]:
    """
    Recompute and store the live feature vector for a sticky position.

    Returns dict with all updated fields to be persisted alongside position.
    """
    now = datetime.now(timezone.utc).isoformat()
    entry = float(position.get("buy_price", 0))
    direction = "LONG" if str(position.get("script", "")).upper().endswith("CE") else "SHORT"

    features = {
        "monitoring_updated_at": now,
        "direction": direction,
        "current_option_ltp": current_ltp,
        "underlying_ltp": underlying_ltp,
        "regime": regime.get("regime") if regime else None,
        "regime_confidence": regime.get("confidence") if regime else None,
        "news_flag": news_sentiment.get("news_flag", "NEUTRAL") if news_sentiment else "NEUTRAL",
        "news_sentiment_score": news_sentiment.get("avg_sentiment", 0.0) if news_sentiment else 0.0,
        "news_count": news_sentiment.get("news_count", 0) if news_sentiment else 0,
        "sector_news_flag": sector_sentiment.get("news_flag", "NEUTRAL") if sector_sentiment else "NEUTRAL",
        "flow_band": flow_band,
        "obi": obi,
        "p_hit_t1": p_hit_t1,
        "p_hit_t2": p_hit_t2,
        "p_sl_first": p_sl_first,
    }

    # Unrealized P&L
    if current_ltp and entry > 0:
        features["unrealized_pnl_pct"] = round(((current_ltp - entry) / entry) * 100, 2)
    else:
        features["unrealized_pnl_pct"] = 0.0

    # Best exit update
    if best_exit_updated:
        features["best_exit_price_live"] = best_exit_updated.get("best_exit_price")
        features["best_exit_method"] = best_exit_updated.get("method")

    return features


# ---------------------------------------------------------------------------
# 8.3  Alert Event Generators
# ---------------------------------------------------------------------------

def check_news_impact(
    position: dict,
    news_sentiment: dict | None,
    previous_news_flag: str = "NEUTRAL",
) -> dict[str, Any] | None:
    """
    Check for NEWS_IMPACT alert condition.

    Triggers when:
    - Long trade + NewsFlag becomes NEGATIVE
    - Short trade + NewsFlag becomes POSITIVE

    Returns event payload or None.
    """
    if not news_sentiment:
        return None

    direction = "LONG" if str(position.get("script", "")).upper().endswith("CE") else "SHORT"
    current_flag = news_sentiment.get("news_flag", "NEUTRAL")
    avg_sentiment = news_sentiment.get("avg_sentiment", 0.0)
    news_count = news_sentiment.get("news_count", 0)

    # Only trigger on actual flag change or strong sentiment
    if current_flag == "NEUTRAL":
        return None

    adverse = False
    if direction == "LONG" and current_flag == "NEGATIVE":
        adverse = True
    elif direction == "SHORT" and current_flag == "POSITIVE":
        adverse = True

    if not adverse:
        return None

    # Build headline summary
    headlines = news_sentiment.get("headlines", [])
    top_headline = headlines[0]["title"] if headlines else "Market sentiment shift detected"

    return {
        "type": "NEWS_IMPACT",
        "symbol": position.get("underlying", position.get("script", "?")),
        "underlying": position.get("underlying", ""),
        "script": position.get("script", ""),
        "direction": direction,
        "sentiment_score": round(avg_sentiment, 3),
        "news_flag": current_flag,
        "news_count": news_count,
        "previous_flag": previous_news_flag,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": f"{'Negative' if current_flag == 'NEGATIVE' else 'Positive'} news cluster detected ({news_count} articles, avg sentiment {avg_sentiment:.2f}). Top: \"{top_headline[:80]}\"",
        "severity": "HIGH" if abs(avg_sentiment) > 0.3 else "MEDIUM",
    }


def check_regime_shift(
    position: dict,
    current_regime: dict | None,
    previous_regime: str | None,
    current_p_hit_t1: float | None = None,
    original_p_hit_t1: float | None = None,
    current_p_hit_t2: float | None = None,
    original_p_hit_t2: float | None = None,
) -> dict[str, Any] | None:
    """
    Check for REGIME_SHIFT alert condition.

    Triggers when:
    - Regime label changes materially (e.g. LowVolTrend → HighVolCrash)
    - AND probabilities P_hit drop sharply vs originals

    Returns event payload or None.
    """
    if not current_regime or not previous_regime:
        return None

    new_regime = current_regime.get("regime", "LowVolRange")

    # No change
    if new_regime == previous_regime:
        return None

    # Define material shifts (adverse for longs)
    adverse_shifts = {
        ("LowVolTrend", "HighVolCrash"),
        ("LowVolTrend", "HighVolTrend"),
        ("LowVolRange", "HighVolCrash"),
        ("LowVolTrend", "PreEvent"),
        ("PostEventIVCrush", "HighVolCrash"),
    }

    # Check if the shift is material
    shift_pair = (previous_regime, new_regime)
    is_material = shift_pair in adverse_shifts

    # Also check probability drop
    p_hit_drop = 0.0
    if current_p_hit_t1 is not None and original_p_hit_t1 is not None:
        p_hit_drop = original_p_hit_t1 - current_p_hit_t1

    if not is_material and p_hit_drop < REGIME_SHIFT_P_HIT_DROP_THRESHOLD:
        return None

    direction = "LONG" if str(position.get("script", "")).upper().endswith("CE") else "SHORT"

    return {
        "type": "REGIME_SHIFT",
        "symbol": position.get("underlying", ""),
        "underlying": position.get("underlying", ""),
        "script": position.get("script", ""),
        "direction": direction,
        "old_regime": previous_regime,
        "new_regime": new_regime,
        "vix_value": current_regime.get("vix_value"),
        "adx_value": current_regime.get("adx_value"),
        "p_hit_t1_drop": round(p_hit_drop, 3) if p_hit_drop else None,
        "current_p_hit_t1": current_p_hit_t1,
        "original_p_hit_t1": original_p_hit_t1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": f"Regime shifted from {previous_regime} to {new_regime}. "
                  + (f"P(hit T1) dropped by {p_hit_drop:.0%}. " if p_hit_drop > 0 else "")
                  + f"VIX={current_regime.get('vix_value', '?')}, ADX={current_regime.get('adx_value', '?')}",
        "severity": "HIGH" if is_material else "MEDIUM",
    }


def build_urgent_exit_reason(
    loss_pct: float,
    minutes_remaining: int,
    flow_band: str = "NeutralFlow",
    p_recovery: float | None = None,
) -> str:
    """
    Build neutral, risk-focused reason text for URGENT_EXIT events.

    Rules:
    - NEVER use imperative verbs: "exit", "sell", "close", "book profit".
    - Only describes: state (loss %, time), risk level, and a pointer to
      the details dict for suggested risk-control price.
    """
    risk_level = "High" if loss_pct < -20 or (p_recovery is not None and p_recovery < 0.10) else "Elevated"

    # Describe flow direction neutrally (avoid raw band labels with imperative words)
    if "Sell" in flow_band or "sell" in flow_band:
        flow_desc = "adverse (bearish pressure)"
    elif "Buy" in flow_band or "buy" in flow_band:
        flow_desc = "adverse (bullish pressure)"
    else:
        flow_desc = "neutral"

    parts: list[str] = [
        f"Loss {loss_pct:.1f}% with {minutes_remaining}min remaining.",
    ]
    if p_recovery is not None:
        parts.append(f"Recovery probability {p_recovery:.0%}; order-flow {flow_desc}.")
    else:
        parts.append(f"Significant drawdown near session end; order-flow {flow_desc}.")

    parts.append(
        f"{risk_level} downside risk flagged; see suggested risk-control price in details."
    )
    return " ".join(parts)


def check_urgent_exit(
    position: dict,
    current_ltp: float | None,
    entry_price: float,
    stop_loss: float | None,
    minutes_remaining: int,
    p_recovery: float | None = None,
    flow_band: str = "NeutralFlow",
    previous_flow_band: str | None = None,
    optimal_exit_price: float | None = None,
) -> dict[str, Any] | None:
    """
    Check for URGENT_EXIT alert condition.

    Triggers when ALL are true:
    - Low probability of recovering to entry/SL before 15:30
    - Order-flow shows clear reversal against trade
    - Remaining time is short

    Returns event payload or None.
    """
    if current_ltp is None or entry_price <= 0:
        return None

    direction = "LONG" if str(position.get("script", "")).upper().endswith("CE") else "SHORT"

    # Check if underwater
    pnl_pct = ((current_ltp - entry_price) / entry_price) * 100

    # For URGENT_EXIT, position must be losing
    if pnl_pct >= 0:
        return None

    # Check time constraint
    if minutes_remaining > URGENT_EXIT_MIN_REMAINING_MINUTES:
        return None

    # Check flow reversal
    flow_reversed = False
    if direction == "LONG":
        adverse_flows = {"StrongSellFlow", "ModerateSellFlow"}
        if flow_band in adverse_flows:
            flow_reversed = True
    else:
        adverse_flows = {"StrongBuyFlow", "ModerateBuyFlow"}
        if flow_band in adverse_flows:
            flow_reversed = True

    # Check recovery probability
    low_recovery = False
    if p_recovery is not None and p_recovery < URGENT_EXIT_RECOVERY_THRESHOLD:
        low_recovery = True
    elif pnl_pct < -15 and minutes_remaining < 60:
        # Heuristic: deep loss near close = low recovery
        low_recovery = True

    # All conditions must be met
    if not (low_recovery and flow_reversed):
        return None

    # Estimate expected best achievable price in the next 60 seconds
    # (MFE + microstructure-based, NOT a guaranteed level)
    if optimal_exit_price is None:
        if current_ltp < 15:
            exit_adj = 0.20
        elif current_ltp < 50:
            exit_adj = 0.50
        elif current_ltp < 100:
            exit_adj = 1.0
        else:
            exit_adj = round(current_ltp * 0.007, 2)
        optimal_exit_price = round(current_ltp + exit_adj, 2)

    return {
        "type": "URGENT_EXIT",
        "symbol": position.get("underlying", ""),
        "underlying": position.get("underlying", ""),
        "script": position.get("script", ""),
        "direction": direction,
        "current_ltp": current_ltp,
        "entry_price": entry_price,
        "unrealized_pnl_pct": round(pnl_pct, 1),
        "expected_best_price_next_60s": optimal_exit_price,
        "minutes_remaining": minutes_remaining,
        "flow_band": flow_band,
        "p_recovery": round(p_recovery, 3) if p_recovery is not None else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": build_urgent_exit_reason(
            loss_pct=pnl_pct,
            minutes_remaining=minutes_remaining,
            flow_band=flow_band,
            p_recovery=p_recovery,
        ),
        "severity": "CRITICAL",
    }


# ---------------------------------------------------------------------------
# 8.3 (cont.)  Aggregate alert checker for a single position
# ---------------------------------------------------------------------------

def generate_position_alerts(
    position: dict,
    current_ltp: float | None = None,
    entry_price: float = 0.0,
    stop_loss: float | None = None,
    minutes_remaining: int = 375,
    news_sentiment: dict | None = None,
    previous_news_flag: str = "NEUTRAL",
    current_regime: dict | None = None,
    previous_regime: str | None = None,
    current_p_hit_t1: float | None = None,
    original_p_hit_t1: float | None = None,
    current_p_hit_t2: float | None = None,
    original_p_hit_t2: float | None = None,
    p_recovery: float | None = None,
    flow_band: str = "NeutralFlow",
    previous_flow_band: str | None = None,
    optimal_exit_price: float | None = None,
) -> list[dict[str, Any]]:
    """
    Run all alert checks for a position. Returns list of triggered events.
    Priority: URGENT_EXIT > REGIME_SHIFT > NEWS_IMPACT.
    """
    alerts: list[dict] = []

    # URGENT_EXIT (highest priority)
    ue = check_urgent_exit(
        position, current_ltp, entry_price, stop_loss,
        minutes_remaining, p_recovery, flow_band,
        previous_flow_band, optimal_exit_price,
    )
    if ue:
        alerts.append(ue)

    # REGIME_SHIFT
    rs = check_regime_shift(
        position, current_regime, previous_regime,
        current_p_hit_t1, original_p_hit_t1,
        current_p_hit_t2, original_p_hit_t2,
    )
    if rs:
        alerts.append(rs)

    # NEWS_IMPACT
    ni = check_news_impact(position, news_sentiment, previous_news_flag)
    if ni:
        alerts.append(ni)

    return alerts
