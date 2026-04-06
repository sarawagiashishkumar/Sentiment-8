"""
Forensic Financial Audit — Batch 2 of the Master Spec.
Altman Z-Score, Earnings Quality, Forensic Red Flags,
ROIC vs WACC, Growth Quality, and Master Forensic Audit.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def compute_altman_z_score(
    working_capital: float | None,
    retained_earnings: float | None,
    ebit: float | None,
    market_cap: float | None,
    total_liabilities: float | None,
    revenue: float | None,
    total_assets: float | None,
) -> dict[str, Any]:
    """
    Altman Z-Score (5-variable, public company model).
    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
    Zones: >2.99 Safe, 1.81–2.99 Grey, <1.81 Distress
    """
    required = [working_capital, ebit, market_cap, total_liabilities, revenue, total_assets]
    if any(v is None for v in required) or total_assets <= 0 or total_liabilities <= 0:
        return {"z_score": None, "zone": "UNKNOWN", "available": False}

    re = retained_earnings or 0.0
    x1 = working_capital / total_assets
    x2 = re / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities
    x5 = revenue / total_assets

    z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5

    if math.isnan(z) or math.isinf(z):
        return {"z_score": None, "zone": "UNKNOWN", "available": False}

    if z > 2.99:
        zone, color = "SAFE", "green"
        description = f"Z={z:.2f} — Safe Zone. Low bankruptcy risk."
    elif z > 1.81:
        zone, color = "GREY", "yellow"
        description = f"Z={z:.2f} — Grey Zone. Monitor leverage and profitability."
    else:
        zone, color = "DISTRESS", "red"
        description = f"Z={z:.2f} — Distress Zone. High bankruptcy risk — avoid."

    return {
        "available": True,
        "z_score": round(z, 3),
        "zone": zone,
        "color": color,
        "description": description,
        "components": {
            "x1_working_capital_ratio": round(x1, 4),
            "x2_retained_earnings_ratio": round(x2, 4),
            "x3_ebit_ratio": round(x3, 4),
            "x4_market_cap_to_liabilities": round(x4, 4),
            "x5_asset_turnover": round(x5, 4),
        },
    }


def compute_earnings_quality(
    operating_cash_flow: float | None,
    net_income: float | None,
    total_assets: float | None,
    total_assets_prev: float | None = None,
) -> dict[str, Any]:
    """
    Earnings quality metrics:
    - CFO/NI ratio: >1.0 = high quality, <0.5 = accrual-heavy
    - Accrual ratio: (NI - CFO) / Avg Total Assets
    """
    result: dict[str, Any] = {"available": False}

    if operating_cash_flow is None or net_income is None:
        return result

    cfo_ni_ratio = None
    if net_income != 0:
        cfo_ni_ratio = round(operating_cash_flow / net_income, 3)

    accrual_ratio = None
    avg_assets = total_assets
    if total_assets is not None and total_assets > 0:
        if total_assets_prev is not None and total_assets_prev > 0:
            avg_assets = (total_assets + total_assets_prev) / 2
        accrual = (net_income - operating_cash_flow) / avg_assets
        accrual_ratio = round(accrual, 4)

    quality = "HIGH"
    flags: list[str] = []
    if cfo_ni_ratio is not None:
        if cfo_ni_ratio < 0.5:
            quality = "LOW"
            flags.append(f"CFO/NI={cfo_ni_ratio:.2f} (<0.5) — earnings may be accrual-heavy")
        elif cfo_ni_ratio < 0.8:
            quality = "MEDIUM"
            flags.append(f"CFO/NI={cfo_ni_ratio:.2f} (<0.8) — moderate earnings quality")

    if accrual_ratio is not None and accrual_ratio > 0.05:
        quality = "LOW" if quality == "HIGH" else quality
        flags.append(f"Accrual ratio={accrual_ratio:.3f} (>0.05) — positive accruals signal concern")

    return {
        "available": True,
        "cfo_ni_ratio": cfo_ni_ratio,
        "accrual_ratio": accrual_ratio,
        "earnings_quality": quality,
        "flags": flags,
    }


def compute_forensic_red_flags(
    accounts_receivable: float | None,
    revenue: float | None,
    revenue_prev: float | None,
    inventory: float | None,
    cogs: float | None,
    accounts_payable: float | None,
    cwip: float | None,
    total_assets: float | None,
    goodwill: float | None,
    net_worth: float | None,
    shares_outstanding: float | None,
    shares_outstanding_prev: float | None,
    total_debt: float | None,
    operating_income: float | None,
    net_income: float | None,
    deferred_tax_liability: float | None,
    deferred_tax_liability_prev: float | None,
    pledged_shares_pct: float | None = None,
    contingent_liabilities: float | None = None,
) -> dict[str, Any]:
    """
    Forensic red-flag checklist. Computes debtor days, inventory days, CWIP ratio,
    goodwill ratio, share dilution, deferred tax anomalies, pledging, contingent liabilities.
    Returns red_flag_count and details list.
    """
    flags: list[str] = []
    metrics: dict[str, Any] = {}

    if accounts_receivable is not None and revenue is not None and revenue > 0:
        debtor_days = round((accounts_receivable / revenue) * 365, 1)
        metrics["debtor_days"] = debtor_days
        if debtor_days > 90:
            flags.append(f"High debtor days: {debtor_days:.0f}d (>90d — slow collection risk)")
        elif debtor_days > 60:
            flags.append(f"Elevated debtor days: {debtor_days:.0f}d (>60d — monitor)")

    if inventory is not None and cogs is not None and cogs > 0:
        inv_days = round((inventory / cogs) * 365, 1)
        metrics["inventory_days"] = inv_days
        if inv_days > 180:
            flags.append(f"High inventory days: {inv_days:.0f}d (>180d — excess stock risk)")
        elif inv_days > 90:
            flags.append(f"Elevated inventory days: {inv_days:.0f}d (>90d)")

    if accounts_payable is not None and cogs is not None and cogs > 0:
        cred_days = round((accounts_payable / cogs) * 365, 1)
        metrics["creditor_days"] = cred_days
        if cred_days > 120:
            flags.append(f"High creditor days: {cred_days:.0f}d (>120d — stretched payables)")

    if cwip is not None and total_assets is not None and total_assets > 0:
        cwip_ratio = round(cwip / total_assets, 3)
        metrics["cwip_to_assets"] = cwip_ratio
        if cwip_ratio > 0.20:
            flags.append(f"CWIP = {cwip_ratio*100:.1f}% of assets (>20% — project delay/stalling risk)")

    if goodwill is not None and net_worth is not None and net_worth > 0:
        gw_ratio = round(goodwill / net_worth, 3)
        metrics["goodwill_to_net_worth"] = gw_ratio
        if gw_ratio > 0.5:
            flags.append(f"Goodwill = {gw_ratio*100:.1f}% of net worth (>50% — intangible-heavy)")

    if shares_outstanding is not None and shares_outstanding_prev is not None and shares_outstanding_prev > 0:
        dilution_pct = round((shares_outstanding - shares_outstanding_prev) / shares_outstanding_prev * 100, 2)
        metrics["dilution_pct_yoy"] = dilution_pct
        if dilution_pct > 5:
            flags.append(f"Share dilution: +{dilution_pct:.1f}% YoY (>5% — equity value erosion)")

    if (deferred_tax_liability is not None and deferred_tax_liability_prev is not None
            and deferred_tax_liability_prev > 0):
        dtl_growth = round((deferred_tax_liability - deferred_tax_liability_prev) / deferred_tax_liability_prev * 100, 1)
        metrics["deferred_tax_growth_pct"] = dtl_growth
        if dtl_growth > 50:
            flags.append(f"Deferred tax liability grew {dtl_growth:.0f}% YoY (potential timing manipulation)")

    if pledged_shares_pct is not None:
        metrics["pledged_pct"] = pledged_shares_pct
        if pledged_shares_pct > 50:
            flags.append(f"High promoter pledging: {pledged_shares_pct:.1f}% (>50% — distress signal)")
        elif pledged_shares_pct > 25:
            flags.append(f"Elevated promoter pledging: {pledged_shares_pct:.1f}% (>25% — monitor)")

    if contingent_liabilities is not None and total_assets is not None and total_assets > 0:
        cl_ratio = round(contingent_liabilities / total_assets, 3)
        metrics["contingent_liab_to_assets"] = cl_ratio
        if cl_ratio > 0.15:
            flags.append(f"Contingent liabilities = {cl_ratio*100:.1f}% of assets (>15% — hidden risk)")

    red_flag_count = len(flags)
    severity = (
        "HIGH" if red_flag_count >= 4 else
        "MEDIUM" if red_flag_count >= 2 else
        "LOW" if red_flag_count == 1 else
        "CLEAN"
    )

    return {
        "red_flag_count": red_flag_count,
        "severity": severity,
        "flags": flags,
        "metrics": metrics,
    }


def compute_roic_vs_wacc(
    ebit: float | None,
    tax_rate: float = 0.25,
    invested_capital: float | None = None,
    total_assets: float | None = None,
    current_liabilities: float | None = None,
    total_debt: float | None = None,
    market_cap: float | None = None,
    cost_of_debt: float = 0.08,
    cost_of_equity: float = 0.12,
) -> dict[str, Any]:
    """
    Compute ROIC and estimate WACC. Returns ROIC - WACC spread.
    Positive spread = value creation; negative = value destruction.
    """
    if ebit is None:
        return {"roic": None, "wacc": None, "spread": None, "available": False}

    nopat = ebit * (1 - tax_rate)

    ic = invested_capital
    if ic is None:
        if total_assets is not None and current_liabilities is not None:
            ic = total_assets - current_liabilities
        elif total_assets is not None:
            ic = total_assets * 0.7

    if ic is None or ic <= 0:
        return {"roic": None, "wacc": None, "spread": None, "available": False}

    roic = round(nopat / ic * 100, 2)

    wacc = cost_of_equity * 100
    if total_debt is not None and market_cap is not None:
        v = total_debt + market_cap
        if v > 0:
            e_ratio = market_cap / v
            d_ratio = total_debt / v
            wacc = round((cost_of_equity * e_ratio + cost_of_debt * (1 - tax_rate) * d_ratio) * 100, 2)

    spread = round(roic - wacc, 2)
    value_creation = spread > 0

    return {
        "available": True,
        "roic": roic,
        "wacc": wacc,
        "spread": spread,
        "value_creation": value_creation,
        "description": (
            f"ROIC {roic:.1f}% vs WACC {wacc:.1f}% — "
            + ("Value CREATING (+{:.1f}%)".format(spread) if value_creation
               else "Value DESTROYING ({:.1f}%)".format(spread))
        ),
    }


def compute_growth_quality(
    revenues: list[float | None],
    ebitda_margins: list[float | None],
    fcf_yield: float | None = None,
) -> dict[str, Any]:
    """
    Compute growth quality metrics: Revenue CAGR, EBITDA margin trend, FCF yield.
    revenues: list [newest, ..., oldest] (at least 2)
    ebitda_margins: list [newest, ..., oldest]
    """
    result: dict[str, Any] = {"available": False}

    valid_revs = [r for r in revenues if r is not None and r > 0]
    if len(valid_revs) >= 2:
        n_years = len(valid_revs) - 1
        rev_cagr = round(((valid_revs[0] / valid_revs[-1]) ** (1 / n_years) - 1) * 100, 2)
        result["revenue_cagr"] = rev_cagr
        result["revenue_cagr_years"] = n_years
        result["revenue_quality"] = (
            "STRONG" if rev_cagr >= 15 else
            "GOOD" if rev_cagr >= 8 else
            "WEAK" if rev_cagr >= 0 else
            "DECLINING"
        )
        result["available"] = True

    valid_margins = [m for m in ebitda_margins if m is not None]
    if len(valid_margins) >= 2:
        margin_trend = "STABLE"
        recent_avg = sum(valid_margins[:2]) / 2
        older_avg = sum(valid_margins[-2:]) / 2
        margin_delta = recent_avg - older_avg
        if margin_delta > 2:
            margin_trend = "IMPROVING"
        elif margin_delta < -2:
            margin_trend = "DETERIORATING"
        result["ebitda_margin_latest"] = round(valid_margins[0], 2)
        result["ebitda_margin_trend"] = margin_trend
        result["ebitda_margin_delta"] = round(margin_delta, 2)
        result["available"] = True

    if fcf_yield is not None:
        result["fcf_yield"] = fcf_yield
        result["fcf_quality"] = (
            "STRONG" if fcf_yield > 5 else
            "MODERATE" if fcf_yield > 2 else
            "WEAK" if fcf_yield >= 0 else
            "NEGATIVE"
        )
        result["available"] = True

    return result


def compute_forensic_audit(
    altman_inputs: dict,
    earnings_quality_inputs: dict,
    red_flag_inputs: dict,
    roic_inputs: dict,
    growth_inputs: dict,
    piotroski_score: int | None = None,
    beneish_m_score: float | None = None,
) -> dict[str, Any]:
    """
    Master forensic audit function. Aggregates all sub-scores into a single
    forensic_audit dict with overall_risk_level and composite_score (0-100).
    Higher composite_score = better quality / lower forensic risk.
    """
    altman = compute_altman_z_score(**altman_inputs)
    eq = compute_earnings_quality(**earnings_quality_inputs)
    rf = compute_forensic_red_flags(**red_flag_inputs)
    roic = compute_roic_vs_wacc(**roic_inputs)
    growth = compute_growth_quality(**growth_inputs)

    score = 50
    risk_flags: list[str] = []

    if altman.get("available"):
        z = altman["z_score"]
        if altman["zone"] == "SAFE":
            score += 15
        elif altman["zone"] == "GREY":
            score += 5
        else:
            score -= 15; risk_flags.append(f"Altman Z={z:.2f} DISTRESS zone")

    if piotroski_score is not None:
        if piotroski_score >= 7:
            score += 15
        elif piotroski_score >= 5:
            score += 5
        else:
            score -= 10; risk_flags.append(f"Piotroski F={piotroski_score}/9 (weak financials)")

    if beneish_m_score is not None:
        if beneish_m_score > -2.22:
            score -= 10; risk_flags.append(f"Beneish M={beneish_m_score:.2f} (manipulation risk)")
        else:
            score += 8

    if eq.get("available"):
        eq_score = {"HIGH": 10, "MEDIUM": 2, "LOW": -8}.get(eq.get("earnings_quality", "MEDIUM"), 0)
        score += eq_score
        if eq_score < 0:
            risk_flags.extend(eq.get("flags", []))

    rf_count = rf.get("red_flag_count", 0)
    score -= rf_count * 4
    risk_flags.extend(rf.get("flags", []))

    if roic.get("available"):
        spread = roic.get("spread", 0) or 0
        if spread > 3:
            score += 8
        elif spread > 0:
            score += 3
        elif spread < -3:
            score -= 8; risk_flags.append(f"ROIC<WACC by {abs(spread):.1f}% — value destruction")
        else:
            score -= 3

    if growth.get("available"):
        rev_q = growth.get("revenue_quality", "WEAK")
        if rev_q == "STRONG":
            score += 5
        elif rev_q == "GOOD":
            score += 2
        elif rev_q == "DECLINING":
            score -= 5
        if growth.get("ebitda_margin_trend") == "DETERIORATING":
            score -= 3; risk_flags.append("EBITDA margin deteriorating")

    composite_score = max(0, min(100, score))
    overall_risk = (
        "LOW" if composite_score >= 70 else
        "MEDIUM" if composite_score >= 45 else
        "HIGH"
    )

    return {
        "composite_score": composite_score,
        "overall_risk": overall_risk,
        "altman_z": altman,
        "earnings_quality": eq,
        "red_flags": rf,
        "roic_vs_wacc": roic,
        "growth_quality": growth,
        "piotroski_score": piotroski_score,
        "beneish_m_score": beneish_m_score,
        "risk_flags": risk_flags[:10],
        "investable": composite_score >= 50 and overall_risk != "HIGH",
    }
