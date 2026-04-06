"""
Macro, Geopolitical & Regime Context — Batch 3 of the Master Spec.
Enhanced 8-regime classifier, SECTOR_MACRO_IMPACT_MAP, compute_macro_context.
"""
from __future__ import annotations

import logging
import re as _re
from typing import Any

logger = logging.getLogger(__name__)


# ── 3.1 Enhanced Market Regime Classifier ────────────────────────────────────

REGIME_STRATEGY_GRID: dict[str, dict[str, str]] = {
    "LOW_VOL_TREND_BULL": {
        "primary": "LONG_CALL / BULL_CALL_SPREAD",
        "secondary": "SHORT_PUT / COVERED_CALL",
        "avoid": "LONG_STRADDLE",
        "rationale": "Low VIX + uptrend: options cheap, buy calls or sell puts for premium income.",
    },
    "LOW_VOL_RANGE": {
        "primary": "IRON_CONDOR / SHORT_STRADDLE",
        "secondary": "SHORT_STRANGLE",
        "avoid": "NAKED_DIRECTIONAL",
        "rationale": "VIX < 12 + range-bound: sell options to collect time premium.",
    },
    "NORMAL_VOL_TREND": {
        "primary": "STANDARD_DIRECTIONAL / DEBIT_SPREAD",
        "secondary": "COVERED_CALL",
        "avoid": "CONDORS_ON_TRENDING_MARKET",
        "rationale": "VIX 12–18 + trending: standard directional plays with defined risk.",
    },
    "NORMAL_VOL_RANGE": {
        "primary": "IRON_CONDOR / CREDIT_SPREAD",
        "secondary": "BUTTERFLY",
        "avoid": "STRADDLE",
        "rationale": "VIX 12–18 + range: credit spreads at extreme strikes.",
    },
    "HIGH_VOL_TREND": {
        "primary": "STRADDLE / STRANGLE / LONG_OPTIONS",
        "secondary": "DEBIT_SPREAD",
        "avoid": "SHORT_NAKED_OPTIONS",
        "rationale": "VIX 18–25 + trend: buy options as IV is rising with the move.",
    },
    "HIGH_VOL_CRASH": {
        "primary": "PROTECTIVE_PUTS / BEAR_SPREAD",
        "secondary": "LONG_VOLATILITY",
        "avoid": "SHORT_PUTS / LONG_FUTURES",
        "rationale": "VIX >25 + crash: protect capital, use bear spreads if IV not extreme.",
    },
    "PRE_EVENT": {
        "primary": "LONG_STRADDLE / LONG_STRANGLE",
        "secondary": "DEBIT_SPREAD",
        "avoid": "SHORT_OPTIONS",
        "rationale": "Event upcoming: buy volatility before IV crush post-event.",
    },
    "POST_EVENT_IV_CRUSH": {
        "primary": "CREDIT_SPREAD / IRON_CONDOR",
        "secondary": "SHORT_STRADDLE",
        "avoid": "LONG_OPTIONS",
        "rationale": "Post-event IV crush: sell overpriced options as IV collapses.",
    },
}


def classify_market_regime_enhanced(
    vix: float | None,
    adx: float | None = None,
    rsi: float | None = None,
    days_to_event: int | None = None,
    post_event_hours: int | None = None,
) -> dict[str, Any]:
    """
    Enhanced 8-regime market classifier.
    Returns regime, strategy grid, description, and color.
    """
    if vix is None:
        return {
            "regime": "UNKNOWN",
            "vix": None,
            "vix_bucket": "UNKNOWN",
            "trend_strength": "UNKNOWN",
            "strategy": REGIME_STRATEGY_GRID.get("NORMAL_VOL_TREND", {}),
            "options_strategy": "STANDARD_DIRECTIONAL",
            "description": "VIX unavailable — using standard strategy",
            "color": "gray",
        }

    if vix < 12:
        vix_bucket = "LOW"
    elif vix < 18:
        vix_bucket = "NORMAL"
    elif vix < 25:
        vix_bucket = "ELEVATED"
    else:
        vix_bucket = "PANIC"

    trending = adx is not None and adx > 22
    bullish_trend = trending and rsi is not None and rsi > 50

    if days_to_event is not None and 0 <= days_to_event <= 2:
        regime = "PRE_EVENT"
        color = "purple"
        desc = f"VIX {vix:.1f} — Event in {days_to_event}d: buy volatility (IV likely to expand)."
    elif post_event_hours is not None and post_event_hours <= 24:
        regime = "POST_EVENT_IV_CRUSH"
        color = "cyan"
        desc = f"VIX {vix:.1f} — Post-event IV crush: sell overpriced options."
    elif vix >= 25:
        regime = "HIGH_VOL_CRASH"
        color = "red"
        desc = f"VIX {vix:.1f} (PANIC) — Protect capital. Defensive posture."
    elif vix >= 18:
        regime = "HIGH_VOL_TREND" if trending else "HIGH_VOL_TREND"
        color = "orange"
        desc = f"VIX {vix:.1f} (ELEVATED) — High vol {'+ trend' if trending else ': buy options on confirmation'}."
    elif vix < 12:
        regime = "LOW_VOL_TREND_BULL" if bullish_trend else "LOW_VOL_RANGE"
        color = "blue" if bullish_trend else "teal"
        desc = (
            f"VIX {vix:.1f} (LOW) — Bull trend; buy calls / sell puts."
            if bullish_trend
            else f"VIX {vix:.1f} (LOW) — Range-bound; Iron Condors / Short Straddles."
        )
    else:
        regime = "NORMAL_VOL_TREND" if trending else "NORMAL_VOL_RANGE"
        color = "green" if trending else "lime"
        desc = (
            f"VIX {vix:.1f} (NORMAL) — Trending market; directional plays."
            if trending
            else f"VIX {vix:.1f} (NORMAL) — Range; credit spreads."
        )

    if adx is not None:
        desc += f" ADX {adx:.0f} ({'strong' if adx > 30 else 'moderate' if adx > 20 else 'weak'} trend)."
    if rsi is not None:
        if rsi > 70:
            desc += f" RSI {rsi:.0f} — overbought."
        elif rsi < 30:
            desc += f" RSI {rsi:.0f} — oversold."

    strategy_grid = REGIME_STRATEGY_GRID.get(regime, REGIME_STRATEGY_GRID["NORMAL_VOL_TREND"])

    return {
        "regime": regime,
        "vix": round(vix, 2),
        "vix_bucket": vix_bucket,
        "adx": round(adx, 1) if adx is not None else None,
        "index_rsi": round(rsi, 1) if rsi is not None else None,
        "trend_strength": "STRONG" if adx and adx > 30 else ("MODERATE" if adx and adx > 20 else "WEAK"),
        "options_strategy": strategy_grid["primary"],
        "strategy": strategy_grid,
        "description": desc,
        "color": color,
    }


# ── 3.2 Sector Impact Map ────────────────────────────────────────────────────

SECTOR_MACRO_IMPACT_MAP: dict[str, dict[str, Any]] = {
    "RBI_RATE_HIKE": {
        "beneficiaries": ["Banking", "Financial Services", "Insurance"],
        "losers": ["Real Estate", "Auto", "Capital Goods", "NBFC"],
        "impact_description": "Rate hike → NIM expansion for banks; real estate and rate-sensitive sectors hurt.",
        "intensity": "HIGH",
    },
    "RBI_RATE_CUT": {
        "beneficiaries": ["Real Estate", "Auto", "Capital Goods", "NBFC", "Housing Finance"],
        "losers": ["Banking"],
        "impact_description": "Rate cut → cheaper credit boosts consumption, real estate, and CapEx.",
        "intensity": "HIGH",
    },
    "CRUDE_SPIKE": {
        "beneficiaries": ["Oil & Gas (upstream)", "Exploration"],
        "losers": ["Airlines", "Paint", "Chemicals", "Logistics", "Tyre", "FMCG"],
        "impact_description": "Crude +20%+ → input cost pressure on oil consumers; upstream oil gains.",
        "intensity": "HIGH",
    },
    "CRUDE_FALL": {
        "beneficiaries": ["Airlines", "Paint", "Chemicals", "Logistics", "Tyre", "FMCG"],
        "losers": ["Oil & Gas (upstream)"],
        "impact_description": "Crude fall → input cost relief for downstream consumers.",
        "intensity": "MEDIUM",
    },
    "FII_OUTFLOW": {
        "beneficiaries": ["Export-oriented IT", "Pharma (USD earners)"],
        "losers": ["Banking", "FMCG", "Real Estate", "Large-cap index"],
        "impact_description": "FII selling → pressure on large-caps and index stocks; INR weakens.",
        "intensity": "HIGH",
    },
    "FII_INFLOW": {
        "beneficiaries": ["Banking", "Financials", "Large-cap index", "Auto"],
        "losers": [],
        "impact_description": "FII buying → broad market rally, especially financials and large-caps.",
        "intensity": "MEDIUM",
    },
    "USD_STRENGTHENING": {
        "beneficiaries": ["IT", "Pharma", "Textiles", "Chemicals (exporters)"],
        "losers": ["Oil importers", "Capital Goods (imports)", "Aviation"],
        "impact_description": "Strong dollar → INR weakens; export-oriented sectors gain.",
        "intensity": "MEDIUM",
    },
    "INR_WEAKENING": {
        "beneficiaries": ["IT", "Pharma", "Textiles"],
        "losers": ["Airlines", "Refineries", "Importers"],
        "impact_description": "INR depreciation → export sectors gain; import-heavy sectors hurt.",
        "intensity": "MEDIUM",
    },
    "INDIA_BUDGET_CAPEX": {
        "beneficiaries": ["Infrastructure", "Capital Goods", "Cement", "Steel", "Defence"],
        "losers": [],
        "impact_description": "Government capex push → infra and capital goods stocks rally.",
        "intensity": "HIGH",
    },
    "PLI_SCHEME": {
        "beneficiaries": ["Manufacturing", "Electronics", "Pharma API", "Textiles", "Auto EV"],
        "losers": [],
        "impact_description": "PLI scheme → import substitution and export push for eligible sectors.",
        "intensity": "MEDIUM",
    },
    "US_FED_RATE_HIKE": {
        "beneficiaries": ["Export IT", "Pharma"],
        "losers": ["FII-driven sectors", "Real Estate", "Gold"],
        "impact_description": "US rate hike → capital flows to US; risk-off for EM including India.",
        "intensity": "MEDIUM",
    },
    "CHINA_SLOWDOWN": {
        "beneficiaries": ["Indian manufacturers (import substitution)", "Specialty Chemicals"],
        "losers": ["Metal exporters", "Commodity importers"],
        "impact_description": "China slowdown → metal prices fall; import substitute opportunity for India.",
        "intensity": "MEDIUM",
    },
    "GEOPOLITICAL_CONFLICT": {
        "beneficiaries": ["Defence", "Gold", "Energy"],
        "losers": ["Aviation", "Tourism", "Consumer Discretionary"],
        "impact_description": "Geopolitical uncertainty → safe haven rally; risk-off for consumer sectors.",
        "intensity": "HIGH",
    },
    "EV_ADOPTION_THEME": {
        "beneficiaries": ["EV OEM", "Battery", "Charging Infra", "Lithium mining"],
        "losers": ["ICE Auto ancillaries", "Fuel retail"],
        "impact_description": "EV theme → structural beneficiaries; ICE supply chain faces disruption.",
        "intensity": "MEDIUM",
    },
    "SEMICONDUCTOR_SHORTAGE": {
        "beneficiaries": ["Indian ATMP", "Chip design"],
        "losers": ["Auto (chip-dependent)", "Electronics OEM"],
        "impact_description": "Global chip shortage → auto production cuts; domestic semicon opportunity.",
        "intensity": "MEDIUM",
    },
}


def compute_macro_context(
    active_events: list[str] | None = None,
    vix: float | None = None,
    adx: float | None = None,
    rsi: float | None = None,
    days_to_next_event: int | None = None,
    sector: str | None = None,
    geopolitical_risk: bool = False,
) -> dict[str, Any]:
    """
    Compute macro context for a given sector or signal.
    active_events: list of keys from SECTOR_MACRO_IMPACT_MAP
    Returns: regime, sector_bias, event_impacts, geopolitical_flag, strategy_suggestion.
    """
    regime_data = classify_market_regime_enhanced(
        vix=vix, adx=adx, rsi=rsi,
        days_to_event=days_to_next_event,
    )

    sector_impact: dict[str, Any] = {"beneficiary": False, "loser": False, "events": []}
    event_impacts: list[dict] = []

    if active_events and sector:
        sector_lower = sector.lower()

        def _sector_in(name: str) -> bool:
            return bool(_re.search(r'\b' + _re.escape(sector_lower) + r'\b', name.lower()))

        for event_key in active_events:
            impact = SECTOR_MACRO_IMPACT_MAP.get(event_key)
            if impact is None:
                continue
            is_ben = any(_sector_in(b) for b in impact["beneficiaries"])
            is_loser = any(_sector_in(l) for l in impact["losers"])
            event_impacts.append({
                "event": event_key,
                "beneficiary": is_ben,
                "loser": is_loser,
                "description": impact["impact_description"],
                "intensity": impact["intensity"],
            })
            if is_ben:
                sector_impact["beneficiary"] = True
                sector_impact["events"].append(f"+{event_key}")
            if is_loser:
                sector_impact["loser"] = True
                sector_impact["events"].append(f"-{event_key}")

    net_events = [e for e in event_impacts]
    ben_count = sum(1 for e in net_events if e["beneficiary"])
    loser_count = sum(1 for e in net_events if e["loser"])
    macro_bias = (
        "TAILWIND" if ben_count > loser_count
        else "HEADWIND" if loser_count > ben_count
        else "NEUTRAL"
    )

    geopolitical_flag: dict[str, Any] = {"active": False}
    if geopolitical_risk or (active_events and "GEOPOLITICAL_CONFLICT" in active_events):
        geopolitical_flag = {
            "active": True,
            "sector_impact": SECTOR_MACRO_IMPACT_MAP["GEOPOLITICAL_CONFLICT"],
            "risk_level": "HIGH",
        }

    return {
        "regime": regime_data,
        "macro_bias": macro_bias,
        "sector_impact": sector_impact,
        "event_impacts": event_impacts,
        "geopolitical_flag": geopolitical_flag,
        "strategy_suggestion": regime_data.get("strategy", {}),
        "active_macro_events": active_events or [],
    }


def get_sector_macro_beneficiaries(event_key: str) -> dict[str, Any]:
    """Return beneficiaries and losers for a macro event."""
    return SECTOR_MACRO_IMPACT_MAP.get(event_key, {})


def get_all_macro_events() -> list[str]:
    """Return all defined macro event keys."""
    return list(SECTOR_MACRO_IMPACT_MAP.keys())
