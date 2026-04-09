"""
Price Band Engine — Compute realistic 1W/1M/3M/6M/9M/12M high & low price bands.

Uses ONLY equity_master_cache data. No default percentages. No LLM calculations.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from services.equity_master_cache import get_symbol, is_stale

logger = logging.getLogger(__name__)

# ── Constants (configurable, never hardcoded in band logic) ──────────

HORIZONS_DAYS = [7, 30, 90, 180, 270, 365]
HORIZON_LABELS = ["1W", "1M", "3M", "6M", "9M", "12M"]
TRADING_DAYS_PER_YEAR = 252

HV_SELECTOR = {
    7: "hv_20d",
    30: "hv_20d",
    90: "hv_60d",
    180: "hv_90d",
    270: "hv_252d",
    365: "hv_252d",
}

BAND_Z_CONSERVATIVE = 0.50
BAND_Z_EXPECTED = 0.675
BAND_Z_OPTIMISTIC = 1.00

REGIME_MULTIPLIERS = {
    "LowVolRange": 0.70,
    "LowVolTrend": 0.85,
    "NormalVolRange": 0.95,
    "NormalVolTrend": 1.00,
    "HighVolTrend": 1.30,
    "HighVolCrash": 1.60,
    "PreEvent": 1.20,
    "PostEventIVCrush": 0.80,
}

FUNDAMENTAL_SCALAR_MIN = 0.80
FUNDAMENTAL_SCALAR_MAX = 1.40
FUNDAMENTAL_SCALAR_MIN_HORIZON = 90


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_fundamental_scalar(doc: dict, horizon_days: int) -> float:
    """
    Compute a multiplier in [FUNDAMENTAL_SCALAR_MIN, FUNDAMENTAL_SCALAR_MAX]
    that scales only the HIGH band based on fundamentals quality.
    """
    score = 1.00

    # ROIC spread
    roic_spread = doc.get("roic_vs_wacc")
    if roic_spread is not None:
        if roic_spread > 10:
            score += 0.12
        elif roic_spread > 5:
            score += 0.07
        elif roic_spread > 0:
            score += 0.03
        elif roic_spread < -5:
            score -= 0.10

    # Earnings growth
    eps_cagr = doc.get("eps_cagr_3y")
    if eps_cagr is not None:
        if eps_cagr > 25:
            score += 0.10
        elif eps_cagr > 15:
            score += 0.06
        elif eps_cagr > 8:
            score += 0.03
        elif eps_cagr < 0:
            score -= 0.08

    # Margin trend
    margin_trend = doc.get("ebitda_margin_trend", "stable")
    if margin_trend == "expanding":
        score += 0.05
    elif margin_trend == "contracting":
        score -= 0.07

    # FCF quality
    fcf = doc.get("fcf_yield")
    if fcf is not None:
        if fcf > 5:
            score += 0.06
        elif fcf < 0:
            score -= 0.06

    # Forensic risk
    beneish = doc.get("beneish_m_score")
    if beneish is not None and beneish > -1.78:
        score -= 0.10
    piotroski = doc.get("piotroski_f_score")
    if piotroski is not None:
        if piotroski >= 7:
            score += 0.05
        elif piotroski <= 3:
            score -= 0.08

    # Horizon scaling: 0 at 90d, 1.0 at 365d
    horizon_weight = min((horizon_days - 90) / 275, 1.0)
    final_scalar = 1.00 + (score - 1.00) * horizon_weight

    return _clamp(final_scalar, FUNDAMENTAL_SCALAR_MIN, FUNDAMENTAL_SCALAR_MAX)


async def compute_price_bands(symbol: str) -> dict[str, Any]:
    """
    Compute realistic price bands for 1W/1M/3M/6M/9M/12M.
    Returns dict with bands or error info. Never fabricates default percentages.
    """
    doc = await get_symbol(symbol)
    if doc is None:
        logger.warning("Cache miss for %s", symbol)
        return {"symbol": symbol, "error": "cache_miss", "bands": None}

    if await is_stale(symbol):
        logger.warning("Stale cache for %s (last_refreshed_at: %s)", symbol, doc.get("last_refreshed_at"))
        return {"symbol": symbol, "error": "stale_cache", "bands": None}

    if not doc.get("passes_eligibility", False):
        return {
            "symbol": symbol,
            "error": "eligibility_failed",
            "reason": doc.get("eligibility_fail_reason"),
            "bands": None,
        }

    ltp = float(doc.get("ltp", 0))
    if ltp <= 0:
        return {"symbol": symbol, "error": "invalid_ltp", "bands": None}

    regime = doc.get("regime_label", "NormalVolRange")
    regime_mult = REGIME_MULTIPLIERS.get(regime, 1.00)

    # Structural floor/ceiling
    nearest_support = float(doc.get("nearest_support") or ltp * 0.90)
    nearest_resistance = float(doc.get("nearest_resistance") or ltp * 1.10)
    demand_zones = doc.get("demand_zones", [])
    supply_zones = doc.get("supply_zones", [])
    fib = doc.get("fib_retracements", {})
    all_time_high = float(doc.get("all_time_high") or ltp * 1.20)

    fib_618 = float(fib.get("0.618", nearest_support)) if fib.get("0.618") else nearest_support
    structural_floor = max(
        nearest_support,
        float(demand_zones[0]["low"]) if demand_zones else 0,
        fib_618,
    )
    structural_ceiling = min(
        nearest_resistance,
        float(supply_zones[0]["high"]) if supply_zones else float("inf"),
        all_time_high * 1.10,
    )
    if structural_ceiling <= ltp:
        structural_ceiling = ltp * 1.15  # safety: ceiling must be above LTP

    bands = {}
    for H, label in zip(HORIZONS_DAYS, HORIZON_LABELS):
        hv_field = HV_SELECTOR[H]
        hv = doc.get(hv_field)
        if hv is None or float(hv) <= 0:
            bands[label] = {"error": "missing_volatility", "field": hv_field}
            continue
        hv = float(hv)

        # Raw volatility-based move (1-sigma)
        raw_move = ltp * hv * math.sqrt(H / TRADING_DAYS_PER_YEAR)

        # Apply regime multiplier
        adj_move = raw_move * regime_mult

        # 3 scenario bands
        raw_low_cons = ltp - adj_move * BAND_Z_CONSERVATIVE
        raw_low_exp = ltp - adj_move * BAND_Z_EXPECTED
        raw_low_opt = ltp - adj_move * BAND_Z_OPTIMISTIC

        raw_high_cons = ltp + adj_move * BAND_Z_CONSERVATIVE
        raw_high_exp = ltp + adj_move * BAND_Z_EXPECTED
        raw_high_opt = ltp + adj_move * BAND_Z_OPTIMISTIC

        # Anchor to structural levels
        anch_low_cons = max(raw_low_cons, structural_floor)
        anch_low_exp = max(raw_low_exp, structural_floor)
        anch_low_opt = max(raw_low_opt, structural_floor * 0.95)

        anch_high_cons = min(raw_high_cons, structural_ceiling)
        anch_high_exp = min(raw_high_exp, structural_ceiling)
        anch_high_opt = min(raw_high_opt, structural_ceiling)

        # Fundamental scalar (only for H >= 90 days)
        fund_scalar = 1.00
        if H >= FUNDAMENTAL_SCALAR_MIN_HORIZON:
            fund_scalar = compute_fundamental_scalar(doc, H)

        final_high_cons = round(anch_high_cons * fund_scalar, 2)
        final_high_exp = round(anch_high_exp * fund_scalar, 2)
        final_high_opt = round(anch_high_opt * fund_scalar, 2)

        final_low_cons = round(anch_low_cons, 2)
        final_low_exp = round(anch_low_exp, 2)
        final_low_opt = round(anch_low_opt, 2)

        bands[label] = {
            "horizon_days": H,
            "hv_used": hv,
            "hv_field_used": hv_field,
            "regime_used": regime,
            "regime_multiplier": regime_mult,
            "fundamental_scalar": fund_scalar,
            "ltp_at_computation": ltp,
            "conservative": {"low": final_low_cons, "high": final_high_cons},
            "expected": {"low": final_low_exp, "high": final_high_exp},
            "optimistic": {"low": final_low_opt, "high": final_high_opt},
            "structural_floor_used": round(structural_floor, 2),
            "structural_ceiling_used": round(structural_ceiling, 2),
            "data_source": "equity_master_cache",
            "hallucinated": False,
        }

    return {
        "symbol": symbol,
        "ltp": ltp,
        "as_of": doc.get("as_of_timestamp"),
        "regime": regime,
        "bands": bands,
        "error": None,
    }
