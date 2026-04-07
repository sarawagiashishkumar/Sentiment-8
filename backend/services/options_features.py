"""
Options Chain Features — Section 3.2 of Master Spec.

Enhanced OI/IV analysis, bid-ask spread, depth metrics, and
IV rank computation for each F&O script candidate.

All calculations are pure Python. NO LLM numeric work.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

from services.data_policy import KITE_IS_SOURCE_OF_TRUTH  # noqa: F401 — policy anchor

logger = logging.getLogger(__name__)

# OI buildup classification labels
OI_BUILDUP_TYPES = Literal[
    "LONG_BUILDUP", "SHORT_BUILDUP",
    "LONG_UNWINDING", "SHORT_COVERING",
    "NEUTRAL",
]


def classify_oi_buildup(
    price_change_pct: float,
    oi_change_pct: float,
) -> str:
    """
    Classify OI buildup from price change and OI change.

    Rules:
      Price ↑ + OI ↑ → LONG_BUILDUP (fresh longs)
      Price ↓ + OI ↑ → SHORT_BUILDUP (fresh shorts)
      Price ↑ + OI ↓ → SHORT_COVERING (shorts exiting)
      Price ↓ + OI ↓ → LONG_UNWINDING (longs exiting)
      Otherwise → NEUTRAL
    """
    if abs(price_change_pct) < 0.1 and abs(oi_change_pct) < 1.0:
        return "NEUTRAL"

    if price_change_pct > 0 and oi_change_pct > 0:
        return "LONG_BUILDUP"
    elif price_change_pct < 0 and oi_change_pct > 0:
        return "SHORT_BUILDUP"
    elif price_change_pct > 0 and oi_change_pct < 0:
        return "SHORT_COVERING"
    elif price_change_pct < 0 and oi_change_pct < 0:
        return "LONG_UNWINDING"
    return "NEUTRAL"


def compute_iv_rank(
    current_iv: float | None,
    iv_history: list[float] | None = None,
    chain_ivs: list[float] | None = None,
) -> float | None:
    """
    Compute IV Rank as percentile of current IV vs history.

    If 1Y IV history is available, use that (proper IV Rank).
    Fallback: use within-chain IVs as a proxy.
    Returns 0-100 scale or None if insufficient data.
    """
    if current_iv is None or current_iv <= 0:
        return None

    # Prefer historical IV if available
    reference = iv_history if iv_history and len(iv_history) >= 20 else chain_ivs

    if not reference or len(reference) < 5:
        return None

    valid = [v for v in reference if v is not None and v > 0]
    if len(valid) < 5:
        return None

    sorted_ivs = sorted(valid)
    below = sum(1 for v in sorted_ivs if v <= current_iv)
    rank = (below / len(sorted_ivs)) * 100
    return round(rank, 1)


def compute_bid_ask_spread(
    best_bid: float | None,
    best_ask: float | None,
) -> dict[str, Any]:
    """
    Compute bid-ask spread as absolute and percentage of mid-price.

    Returns: spread, spread_pct, mid_price, is_liquid (spread < 2%).
    """
    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
        return {"available": False, "is_liquid": False}

    spread = best_ask - best_bid
    mid = (best_bid + best_ask) / 2
    spread_pct = (spread / mid) * 100 if mid > 0 else 100.0

    return {
        "available": True,
        "spread": round(spread, 2),
        "spread_pct": round(spread_pct, 2),
        "mid_price": round(mid, 2),
        "is_liquid": spread_pct < 2.0,
    }


def compute_depth_score(
    bid_depths: list[dict] | None,
    ask_depths: list[dict] | None,
) -> dict[str, Any]:
    """
    Score order book depth from top N levels.

    Each level dict: {"price": float, "quantity": int}
    Returns: bid_depth_total, ask_depth_total, depth_ratio, score (0-100).
    """
    if not bid_depths or not ask_depths:
        return {"available": False, "score": 50}

    bid_total = sum(d.get("quantity", 0) for d in bid_depths[:5])
    ask_total = sum(d.get("quantity", 0) for d in ask_depths[:5])

    total = bid_total + ask_total
    if total <= 0:
        return {"available": False, "score": 50}

    ratio = bid_total / ask_total if ask_total > 0 else 2.0

    # Score: balanced depth + high volume = good liquidity
    if ratio > 1.5:
        score = 75  # strong bid support
    elif ratio > 1.1:
        score = 65
    elif ratio > 0.9:
        score = 50  # balanced
    elif ratio > 0.7:
        score = 35
    else:
        score = 25  # weak bid support

    # Bonus for high absolute depth
    if total > 50000:
        score = min(100, score + 15)
    elif total > 10000:
        score = min(100, score + 8)

    return {
        "available": True,
        "bid_depth_total": bid_total,
        "ask_depth_total": ask_total,
        "depth_ratio": round(ratio, 2),
        "score": score,
    }


def compute_enhanced_option_features(
    option_snapshot: dict | None,
    underlying_ltp: float | None = None,
    strike: float | None = None,
    option_type: str = "CE",
    chain_ivs: list[float] | None = None,
) -> dict[str, Any]:
    """
    Build full options feature dict for a single contract.

    option_snapshot from Kite: {ltp, oi, volume, bid, ask, iv, ...}
    Returns composite features for Confluence Score Bucket C.
    """
    if option_snapshot is None:
        return {"available": False}

    snap = option_snapshot
    result: dict[str, Any] = {"available": True}

    # Basic prices
    ltp = snap.get("ltp") or snap.get("last_price")
    result["option_ltp"] = ltp

    # OI data
    oi = snap.get("oi", 0) or 0
    oi_change = snap.get("oi_change", 0) or snap.get("oi_day_change", 0) or 0
    result["oi"] = oi
    result["oi_change"] = oi_change

    # OI change %
    if oi > 0 and oi_change != 0:
        oi_change_pct = (oi_change / (oi - oi_change)) * 100 if (oi - oi_change) > 0 else 0
    else:
        oi_change_pct = 0.0
    result["oi_change_pct"] = round(oi_change_pct, 1)

    # Price change % (intraday)
    prev = snap.get("ohlc", {}).get("close") or snap.get("prev_close")
    if ltp and prev and prev > 0:
        price_change_pct = ((ltp - prev) / prev) * 100
    else:
        price_change_pct = 0.0
    result["price_change_pct"] = round(price_change_pct, 2)

    # OI buildup classification
    result["oi_buildup"] = classify_oi_buildup(price_change_pct, oi_change_pct)

    # IV
    iv = snap.get("iv") or snap.get("implied_volatility")
    result["iv"] = iv

    # IV Rank
    result["iv_rank"] = compute_iv_rank(iv, chain_ivs=chain_ivs)

    # Bid-ask spread
    bid = snap.get("bid") or snap.get("depth", {}).get("buy", [{}])[0].get("price")
    ask = snap.get("ask") or snap.get("depth", {}).get("sell", [{}])[0].get("price")
    result["spread_data"] = compute_bid_ask_spread(bid, ask)
    result["is_liquid"] = result["spread_data"].get("is_liquid", False)

    # Volume
    result["volume"] = snap.get("volume", 0) or 0

    # Moneyness
    if underlying_ltp and strike:
        if option_type == "CE":
            moneyness = (underlying_ltp - strike) / underlying_ltp * 100
        else:
            moneyness = (strike - underlying_ltp) / underlying_ltp * 100
        result["moneyness_pct"] = round(moneyness, 2)
        if moneyness > 2:
            result["moneyness"] = "ITM"
        elif moneyness < -2:
            result["moneyness"] = "OTM"
        else:
            result["moneyness"] = "ATM"
    else:
        result["moneyness"] = "UNKNOWN"
        result["moneyness_pct"] = None

    return result
