"""
Portfolio-Level Risk Analytics — Batch 4 of the Master Spec.
Correlation matrix, stress tests, diversification audit,
upcoming catalysts, merge holdings, master stock snapshot.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_portfolio_correlation_matrix(
    returns_dict: dict[str, list[float]],
    min_length: int = 20,
) -> dict[str, Any]:
    """
    Compute pairwise Pearson correlation matrix from daily return series.
    returns_dict: {symbol: [daily_returns]} — at least 20 data points each.
    Returns: correlation_matrix (symbol×symbol), high_correlation_pairs (>0.7).
    """
    if not returns_dict or len(returns_dict) < 2:
        return {"available": False, "matrix": {}, "high_correlation_pairs": []}

    valid = {
        sym: rets for sym, rets in returns_dict.items()
        if rets is not None and len(rets) >= min_length
    }
    if len(valid) < 2:
        return {"available": False, "matrix": {}, "high_correlation_pairs": []}

    symbols = sorted(valid.keys())
    n = min(len(v) for v in valid.values())

    arr = np.array([valid[s][-n:] for s in symbols])
    try:
        corr = np.corrcoef(arr)
    except Exception:
        return {"available": False, "matrix": {}, "high_correlation_pairs": []}

    corr_matrix: dict[str, dict[str, float]] = {}
    high_pairs: list[dict] = []

    for i, si in enumerate(symbols):
        corr_matrix[si] = {}
        for j, sj in enumerate(symbols):
            val = round(float(corr[i, j]), 3)
            corr_matrix[si][sj] = val
            if i < j and abs(val) > 0.70:
                high_pairs.append({
                    "symbol_a": si,
                    "symbol_b": sj,
                    "correlation": val,
                    "type": "POSITIVE" if val > 0 else "NEGATIVE",
                    "risk_note": (
                        "High positive correlation — concentration risk"
                        if val > 0.7 else
                        "High negative correlation — natural hedge"
                    ),
                })

    return {
        "available": True,
        "symbols": symbols,
        "matrix": corr_matrix,
        "high_correlation_pairs": high_pairs,
        "has_concentration_risk": any(p["correlation"] > 0.70 for p in high_pairs),
    }


STRESS_SCENARIOS: dict[str, dict[str, Any]] = {
    "NIFTY_CRASH_10PCT": {
        "description": "Nifty drops 10% — broad market sell-off",
        "index_shock": -0.10,
        "beta_driven": True,
        "sector_overrides": {"Gold": 0.05, "Pharma": -0.03, "IT": -0.12},
    },
    "CRUDE_SPIKE_30PCT": {
        "description": "Crude oil spikes 30% — input cost surge",
        "index_shock": -0.04,
        "beta_driven": False,
        "sector_overrides": {
            "Airlines": -0.20, "Paint": -0.12, "Chemicals": -0.10,
            "Oil & Gas": 0.15, "Exploration": 0.15, "Tyre": -0.08,
        },
    },
    "INR_WEAKENS_5PCT": {
        "description": "INR weakens 5% vs USD",
        "index_shock": -0.02,
        "beta_driven": False,
        "sector_overrides": {
            "IT": 0.08, "Pharma": 0.05, "Textiles": 0.04,
            "Airlines": -0.06, "Refineries": -0.04,
        },
    },
    "US_RECESSION": {
        "description": "US recession — global risk-off, FII outflows",
        "index_shock": -0.15,
        "beta_driven": True,
        "sector_overrides": {
            "IT": -0.18, "Metals": -0.12, "Pharma": -0.02,
            "FMCG": -0.04, "Banking": -0.14,
        },
    },
    "RBI_RATE_HIKE_50BPS": {
        "description": "RBI surprise 50bps rate hike",
        "index_shock": -0.05,
        "beta_driven": False,
        "sector_overrides": {
            "Real Estate": -0.12, "Auto": -0.08, "Banking": 0.03,
            "NBFC": -0.10, "Capital Goods": -0.06,
        },
    },
}


def compute_portfolio_stress_tests(
    holdings: list[dict],
) -> dict[str, Any]:
    """
    Compute portfolio P&L impact under 5 stress scenarios.
    holdings: list of {symbol, sector, current_value, portfolio_beta}
    """
    if not holdings:
        return {"available": False, "scenarios": {}}

    total_value = sum(h.get("current_value", 0) for h in holdings if h.get("current_value"))
    if total_value <= 0:
        return {"available": False, "scenarios": {}}

    scenario_results: dict[str, dict] = {}

    for scenario_key, scenario in STRESS_SCENARIOS.items():
        index_shock = scenario["index_shock"]
        sector_overrides: dict[str, float] = scenario.get("sector_overrides", {})
        total_impact = 0.0
        stock_impacts: list[dict] = []

        for holding in holdings:
            sym = holding.get("symbol", "")
            sector = holding.get("sector", "")
            val = holding.get("current_value", 0) or 0
            beta = holding.get("portfolio_beta") or 1.0

            sector_shock = None
            for sec_key, shock in sector_overrides.items():
                if sec_key.lower() in sector.lower():
                    sector_shock = shock
                    break

            if sector_shock is not None:
                shock = sector_shock
            elif scenario["beta_driven"]:
                shock = index_shock * beta
            else:
                shock = index_shock * 0.5

            impact_value = val * shock
            total_impact += impact_value
            if abs(impact_value) > 0:
                stock_impacts.append({
                    "symbol": sym,
                    "shock_pct": round(shock * 100, 1),
                    "impact": round(impact_value),
                })

        impact_pct = round(total_impact / total_value * 100, 2) if total_value > 0 else 0
        stock_impacts.sort(key=lambda x: x["impact"])

        scenario_results[scenario_key] = {
            "description": scenario["description"],
            "portfolio_impact_pct": impact_pct,
            "portfolio_impact_value": round(total_impact),
            "severity": (
                "CRITICAL" if impact_pct < -15 else
                "HIGH" if impact_pct < -8 else
                "MEDIUM" if impact_pct < -3 else
                "LOW"
            ),
            "top_losers": stock_impacts[:3],
        }

    worst_scenario = min(scenario_results.items(), key=lambda x: x[1]["portfolio_impact_pct"])

    return {
        "available": True,
        "scenarios": scenario_results,
        "worst_scenario": worst_scenario[0],
        "worst_case_loss_pct": worst_scenario[1]["portfolio_impact_pct"],
    }


def compute_diversification_audit(
    holdings: list[dict],
) -> dict[str, Any]:
    """
    Audit portfolio diversification: sector allocation, market-cap split,
    cyclical vs defensive, domestic vs export, micro-cap exposure.
    """
    if not holdings:
        return {"available": False}

    total_value = sum(h.get("current_value", 0) for h in holdings if h.get("current_value"))
    if total_value <= 0:
        return {"available": False}

    sector_alloc: dict[str, float] = {}
    cap_alloc: dict[str, float] = {"Large": 0, "Mid": 0, "Small": 0, "Unknown": 0}
    cyclical_val = 0.0
    defensive_val = 0.0
    domestic_val = 0.0
    export_val = 0.0
    micro_cap_val = 0.0

    CYCLICAL_SECTORS = {"auto", "metals", "capital goods", "real estate", "banking", "finance", "oil"}
    DEFENSIVE_SECTORS = {"fmcg", "pharma", "healthcare", "utilities", "consumer staples"}
    EXPORT_SECTORS = {"it", "pharma", "textiles", "chemicals", "technology"}

    for h in holdings:
        val = h.get("current_value", 0) or 0
        sector = (h.get("sector") or "Unknown").lower()
        market_cap = h.get("market_cap")

        sector_name = h.get("sector") or "Unknown"
        sector_alloc[sector_name] = sector_alloc.get(sector_name, 0) + val

        if market_cap is not None:
            if market_cap > 200e9:
                cap_alloc["Large"] += val
            elif market_cap > 50e9:
                cap_alloc["Mid"] += val
            elif market_cap > 5e9:
                cap_alloc["Small"] += val
                if market_cap < 5e9:
                    micro_cap_val += val
            else:
                cap_alloc["Unknown"] += val
        else:
            cap_alloc["Unknown"] += val

        if any(s in sector for s in CYCLICAL_SECTORS):
            cyclical_val += val
        elif any(s in sector for s in DEFENSIVE_SECTORS):
            defensive_val += val

        if any(s in sector for s in EXPORT_SECTORS):
            export_val += val
        else:
            domestic_val += val

    sector_pct = {k: round(v / total_value * 100, 1) for k, v in sector_alloc.items()}
    cap_pct = {k: round(v / total_value * 100, 1) for k, v in cap_alloc.items()}

    flags: list[str] = []
    top_sector = max(sector_pct.items(), key=lambda x: x[1]) if sector_pct else (None, 0)
    top_holding = max(holdings, key=lambda h: h.get("current_value", 0), default=None)
    top_holding_pct = round(
        (top_holding.get("current_value", 0) / total_value * 100) if top_holding else 0, 1
    )

    if top_sector[1] > 40:
        flags.append(f"Over-concentrated in {top_sector[0]} ({top_sector[1]:.0f}% of portfolio)")
    if top_holding_pct > 20:
        flags.append(f"Single stock > 20%: {top_holding.get('symbol', '')} at {top_holding_pct:.0f}%")
    if micro_cap_val / total_value > 0.25:
        flags.append(f"Micro-cap exposure {micro_cap_val/total_value*100:.0f}% > 25% — high risk")
    if cap_pct.get("Unknown", 0) > 30:
        flags.append("Market cap data missing for >30% of portfolio")

    return {
        "available": True,
        "sector_allocation_pct": dict(sorted(sector_pct.items(), key=lambda x: -x[1])),
        "market_cap_split_pct": cap_pct,
        "cyclical_pct": round(cyclical_val / total_value * 100, 1),
        "defensive_pct": round(defensive_val / total_value * 100, 1),
        "domestic_pct": round(domestic_val / total_value * 100, 1),
        "export_pct": round(export_val / total_value * 100, 1),
        "micro_cap_pct": round(micro_cap_val / total_value * 100, 1),
        "flags": flags,
        "top_sector": top_sector[0],
        "top_sector_pct": top_sector[1],
        "top_holding_pct": top_holding_pct,
    }


RBI_MEETING_DATES_2025_2026 = [
    "2025-04-09", "2025-06-06", "2025-08-06", "2025-10-08",
    "2025-12-05", "2026-02-06", "2026-04-07", "2026-06-05",
    "2026-08-05", "2026-10-07", "2026-12-04",
]

FED_MEETING_DATES_2025_2026 = [
    "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-17",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
]


def compute_upcoming_catalysts(
    symbols: list[str],
    earnings_dates: dict[str, str] | None = None,
    days_window: int = 15,
) -> dict[str, Any]:
    """Flag upcoming catalysts for given symbols within days_window days."""
    try:
        today = date.today()
        window_end = today + timedelta(days=days_window)

        catalysts: dict[str, list[str]] = {}

        if earnings_dates:
            for sym in symbols:
                ed = earnings_dates.get(sym)
                if ed:
                    try:
                        ed_date = date.fromisoformat(ed)
                        days_away = (ed_date - today).days
                        if 0 <= days_away <= days_window:
                            catalysts.setdefault(sym, []).append(
                                f"Earnings in {days_away}d ({ed_date.strftime('%d %b %Y')})"
                            )
                    except Exception:
                        pass

        rbi_upcoming = []
        for d_str in RBI_MEETING_DATES_2025_2026:
            try:
                d = date.fromisoformat(d_str)
                days_away = (d - today).days
                if 0 <= days_away <= days_window:
                    rbi_upcoming.append({
                        "event": "RBI Policy Meeting",
                        "date": d_str,
                        "days_away": days_away,
                        "sector_impact": ["Banking", "Real Estate", "Auto", "NBFC"],
                    })
            except Exception:
                pass

        fed_upcoming = []
        for d_str in FED_MEETING_DATES_2025_2026:
            try:
                d = date.fromisoformat(d_str)
                days_away = (d - today).days
                if 0 <= days_away <= days_window:
                    fed_upcoming.append({
                        "event": "US Fed Meeting",
                        "date": d_str,
                        "days_away": days_away,
                        "sector_impact": ["IT", "Banking", "Metals"],
                    })
            except Exception:
                pass

        macro_events = rbi_upcoming + fed_upcoming
        macro_events.sort(key=lambda x: x["days_away"])

        return {
            "available": True,
            "stock_catalysts": catalysts,
            "macro_events": macro_events[:5],
            "has_near_term_events": bool(macro_events or catalysts),
            "window_days": days_window,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def merge_duplicate_holdings(holdings: list[dict]) -> list[dict]:
    """
    Merge positions and holdings with the same symbol into a single entry
    using weighted-average cost price and aggregated quantities.
    """
    merged: dict[str, dict] = {}

    for h in holdings:
        sym = h.get("symbol") or h.get("script", "")
        if not sym:
            continue

        if sym not in merged:
            merged[sym] = dict(h)
            merged[sym]["_total_cost"] = (h.get("avg_price", 0) or 0) * (h.get("quantity", 0) or 0)
            merged[sym]["_total_qty"] = h.get("quantity", 0) or 0
        else:
            qty = h.get("quantity", 0) or 0
            cost = (h.get("avg_price", 0) or 0) * qty
            merged[sym]["_total_cost"] += cost
            merged[sym]["_total_qty"] += qty
            cv = h.get("current_value", 0) or 0
            merged[sym]["current_value"] = (merged[sym].get("current_value", 0) or 0) + cv
            pnl = h.get("unrealized_pnl", 0) or 0
            merged[sym]["unrealized_pnl"] = (merged[sym].get("unrealized_pnl", 0) or 0) + pnl

    result = []
    for sym, h in merged.items():
        total_qty = h["_total_qty"]
        total_cost = h["_total_cost"]
        if total_qty > 0:
            h["avg_price"] = round(total_cost / total_qty, 2)
            h["quantity"] = total_qty
        del h["_total_cost"]
        del h["_total_qty"]
        result.append(h)

    return result


def compute_master_stock_snapshot(
    symbol: str,
    ltp: float | None,
    hist: "pd.DataFrame | None",
    sector: str | None = None,
    market_cap: float | None = None,
    index_memberships: list[str] | None = None,
    ipo_date: str | None = None,
    ipo_price: float | None = None,
) -> dict[str, Any]:
    """
    MASTER stock snapshot: identity, price levels (52W high/low, 3M/1M, ATH), IPO info.
    """
    snap: dict[str, Any] = {
        "symbol": symbol,
        "sector": sector,
        "market_cap": market_cap,
        "index_memberships": index_memberships or [],
        "ltp": ltp,
    }

    if market_cap is not None:
        if market_cap > 200e9:
            snap["market_cap_category"] = "LARGE_CAP"
        elif market_cap > 50e9:
            snap["market_cap_category"] = "MID_CAP"
        elif market_cap > 5e9:
            snap["market_cap_category"] = "SMALL_CAP"
        else:
            snap["market_cap_category"] = "MICRO_CAP"
    else:
        snap["market_cap_category"] = "UNKNOWN"

    if hist is not None and not hist.empty and ltp is not None:
        n = len(hist)

        w52 = hist.tail(min(252, n))
        w52_high = float(w52["High"].max())
        w52_low = float(w52["Low"].min())
        snap["week52_high"] = round(w52_high, 2)
        snap["week52_low"] = round(w52_low, 2)
        snap["pct_from_52w_high"] = round((ltp - w52_high) / w52_high * 100, 2)
        snap["pct_from_52w_low"] = round((ltp - w52_low) / w52_low * 100, 2)

        w3m = hist.tail(min(63, n))
        w1m = hist.tail(min(21, n))
        snap["month3_high"] = round(float(w3m["High"].max()), 2)
        snap["month3_low"] = round(float(w3m["Low"].min()), 2)
        snap["month1_high"] = round(float(w1m["High"].max()), 2)
        snap["month1_low"] = round(float(w1m["Low"].min()), 2)

        ath = float(hist["High"].max())
        snap["ath"] = round(ath, 2)
        snap["pct_below_ath"] = round((ltp - ath) / ath * 100, 2)

    if ipo_date is not None:
        try:
            ipo_dt = date.fromisoformat(ipo_date)
            years_since = (date.today() - ipo_dt).days / 365.25
            if years_since < 5:
                snap["ipo_date"] = ipo_date
                snap["ipo_price"] = ipo_price
                snap["years_since_ipo"] = round(years_since, 1)
                if ipo_price and ltp:
                    snap["ipo_return_pct"] = round((ltp - ipo_price) / ipo_price * 100, 2)
        except Exception:
            pass

    return snap
