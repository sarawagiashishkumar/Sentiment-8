"""
Fundamental Data — yfinance-based scoring functions.

Extracted from server.py. DISABLED in production (Kite has no fundamental equivalent).
Piotroski/Beneish scores are decorative/offline-research only.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

from services.utils import (
    sanitize_float as _sanitize_float,
    to_float as _to_float,
    utc_now_iso as _utc_now_iso,
)

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


def _compute_piotroski_score_from_data(info: dict, fin: object, bs: object, cf: object) -> int:
    """
    Compute simplified Piotroski F-score (0-9) from yfinance data.
    Returns integer score. Higher = better quality.
    """
    import pandas as pd
    score = 0
    try:
        # 1. ROA > 0
        roa = info.get("returnOnAssets")
        if roa is not None and float(roa) > 0:
            score += 1

        # 2. Operating cash flow > 0
        if cf is not None and not cf.empty:
            ocf_row = None
            for lbl in ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash From Operations"]:
                if lbl in cf.index:
                    ocf_row = cf.loc[lbl]
                    break
            if ocf_row is not None and len(ocf_row) > 0:
                if float(ocf_row.iloc[0]) > 0:
                    score += 1

        # 3. ROA change YoY > 0
        if bs is not None and not bs.empty and fin is not None and not fin.empty:
            net_income_row = None
            total_assets_row = None
            for lbl in ["Net Income", "Net Income Applicable To Common Shares", "Net Income From Continuing Ops"]:
                if lbl in fin.index:
                    net_income_row = fin.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    total_assets_row = bs.loc[lbl]
                    break
            if net_income_row is not None and total_assets_row is not None and len(net_income_row) >= 2:
                ta_0 = float(total_assets_row.iloc[0]) if len(total_assets_row) > 0 else 1
                ta_1 = float(total_assets_row.iloc[1]) if len(total_assets_row) > 1 else ta_0
                roa_0 = float(net_income_row.iloc[0]) / max(ta_0, 1)
                roa_1 = float(net_income_row.iloc[1]) / max(ta_1, 1)
                if roa_0 > roa_1:
                    score += 1

        # 4. Cash flow > ROA (accruals)
        if cf is not None and not cf.empty and bs is not None and not bs.empty:
            ocf_row = None
            total_assets_row = None
            net_income_row = None
            for lbl in ["Operating Cash Flow", "Total Cash From Operating Activities"]:
                if lbl in cf.index:
                    ocf_row = cf.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    total_assets_row = bs.loc[lbl]
                    break
            for lbl in ["Net Income", "Net Income Applicable To Common Shares"]:
                if lbl in fin.index:
                    net_income_row = fin.loc[lbl]
                    break
            if ocf_row is not None and total_assets_row is not None and net_income_row is not None:
                ta = float(total_assets_row.iloc[0]) if len(total_assets_row) > 0 else 1
                ocf = float(ocf_row.iloc[0]) if len(ocf_row) > 0 else 0
                ni = float(net_income_row.iloc[0]) if len(net_income_row) > 0 else 0
                if (ocf / max(ta, 1)) > (ni / max(ta, 1)):
                    score += 1

        # 5. Leverage decrease (long-term debt)
        if bs is not None and not bs.empty:
            ltd_row = None
            ta_row = None
            for lbl in ["Long Term Debt", "LongTermDebt", "Long-Term Debt"]:
                if lbl in bs.index:
                    ltd_row = bs.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    ta_row = bs.loc[lbl]
                    break
            if ltd_row is not None and ta_row is not None and len(ltd_row) >= 2:
                lev_0 = float(ltd_row.iloc[0]) / max(float(ta_row.iloc[0]), 1)
                lev_1 = float(ltd_row.iloc[1]) / max(float(ta_row.iloc[1]) if len(ta_row) > 1 else float(ta_row.iloc[0]), 1)
                if lev_0 < lev_1:
                    score += 1

        # 6. Current ratio improvement
        cr = info.get("currentRatio")
        if cr is not None and float(cr) > 1.0:
            score += 1

        # 7. No new shares issued
        shares = info.get("sharesOutstanding")
        float_shares = info.get("floatShares")
        if shares and float_shares and float(float_shares) <= float(shares) * 1.02:
            score += 1

        # 8. Gross margin > 0
        gm = info.get("grossMargins")
        if gm is not None and float(gm) > 0:
            score += 1

        # 9. Asset turnover improvement
        if fin is not None and not fin.empty and bs is not None and not bs.empty:
            rev_row = None
            ta_row = None
            for lbl in ["Total Revenue", "Revenue"]:
                if lbl in fin.index:
                    rev_row = fin.loc[lbl]
                    break
            for lbl in ["Total Assets"]:
                if lbl in bs.index:
                    ta_row = bs.loc[lbl]
                    break
            if rev_row is not None and ta_row is not None and len(rev_row) >= 2:
                at_0 = float(rev_row.iloc[0]) / max(float(ta_row.iloc[0]), 1)
                at_1 = float(rev_row.iloc[1]) / max(float(ta_row.iloc[1]) if len(ta_row) > 1 else float(ta_row.iloc[0]), 1)
                if at_0 > at_1:
                    score += 1
    except Exception as exc:
        logger.debug("Piotroski score error: %s", exc)
    return score


def _compute_beneish_m_score_from_data(fin: object, bs: object) -> float | None:
    """
    Compute simplified Beneish M-score from yfinance data.
    M-score > -2.22 suggests potential earnings manipulation.
    """
    try:
        if fin is None or bs is None or fin.empty or bs.empty:
            return None
        if len(fin.columns) < 2:
            return None

        def _get(df, labels):
            for lbl in labels:
                if lbl in df.index:
                    row = df.loc[lbl]
                    v0_raw = float(row.iloc[0]) if len(row) > 0 else 0
                    v1_raw = float(row.iloc[1]) if len(row) > 1 else v0_raw
                    v0 = 0.0 if (math.isnan(v0_raw) or math.isinf(v0_raw)) else v0_raw
                    v1 = 0.0 if (math.isnan(v1_raw) or math.isinf(v1_raw)) else v1_raw
                    return v0, v1
            return None, None

        rev_0, rev_1 = _get(fin, ["Total Revenue", "Revenue"])
        cogs_0, cogs_1 = _get(fin, ["Cost Of Revenue", "Cost of Goods Sold", "Cost Of Goods Sold"])
        ni_0, ni_1 = _get(fin, ["Net Income", "Net Income Applicable To Common Shares"])
        sga_0, sga_1 = _get(fin, ["Selling General Administrative", "Selling General And Administration"])
        ta_0, ta_1 = _get(bs, ["Total Assets"])
        ca_0, ca_1 = _get(bs, ["Total Current Assets", "Current Assets"])
        cl_0, cl_1 = _get(bs, ["Total Current Liabilities", "Current Liabilities"])
        ar_0, ar_1 = _get(bs, ["Net Receivables", "Accounts Receivable"])
        ppe_0, ppe_1 = _get(bs, ["Net PPE", "Property Plant Equipment Net", "Property Plant And Equipment Net"])
        dep_0, dep_1 = _get(fin, ["Depreciation", "Depreciation And Amortization"])
        ltd_0, ltd_1 = _get(bs, ["Long Term Debt"])

        if not all([rev_0, rev_1, ta_0, ta_1]):
            return None

        ar_0 = ar_0 or 0
        ar_1 = ar_1 or 0
        dsri = (ar_0 / max(rev_0, 1)) / max(ar_1 / max(rev_1, 1), 0.001) if rev_1 and ar_1 else 1.0

        gm_0 = (rev_0 - (cogs_0 or 0)) / max(rev_0, 1)
        gm_1 = (rev_1 - (cogs_1 or 0)) / max(rev_1, 1)
        gmi = gm_1 / max(gm_0, 0.001) if gm_0 else 1.0

        ca_0 = ca_0 or ta_0 * 0.3
        ca_1 = ca_1 or ta_1 * 0.3
        ppe_0 = ppe_0 or ta_0 * 0.3
        ppe_1 = ppe_1 or ta_1 * 0.3
        aq_0 = 1 - (ca_0 + ppe_0) / max(ta_0, 1)
        aq_1 = 1 - (ca_1 + ppe_1) / max(ta_1, 1)
        aqi = aq_0 / max(aq_1, 0.001)

        sgi = rev_0 / max(rev_1, 1)

        dep_0 = dep_0 or 0
        dep_1 = dep_1 or 0
        depi_0 = dep_0 / max(dep_0 + ppe_0, 1)
        depi_1 = dep_1 / max(dep_1 + ppe_1, 1)
        depi = depi_1 / max(depi_0, 0.001) if depi_0 else 1.0

        sga_0 = sga_0 or rev_0 * 0.1
        sga_1 = sga_1 or rev_1 * 0.1
        sgai_0 = sga_0 / max(rev_0, 1)
        sgai_1 = sga_1 / max(rev_1, 1)
        sgai = sgai_0 / max(sgai_1, 0.001)

        ltd_0 = ltd_0 or 0
        ltd_1 = ltd_1 or 0
        cl_0 = cl_0 or ta_0 * 0.2
        cl_1 = cl_1 or ta_1 * 0.2
        lev_0 = (ltd_0 + cl_0) / max(ta_0, 1)
        lev_1 = (ltd_1 + cl_1) / max(ta_1, 1)
        lvgi = lev_0 / max(lev_1, 0.001)

        ni_0 = ni_0 or 0
        tata = (ni_0 - (dep_0 or 0)) / max(ta_0, 1)

        m_score = (
            -4.84
            + 0.92 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )
        result = round(float(m_score), 3)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception as exc:
        logger.debug("Beneish M-score error: %s", exc)
        return None


# DISABLED — yfinance only. No Kite equivalent for fundamental scoring.
# USE_YFINANCE must remain false in production.
def _fetch_yfinance_fundamentals(symbol: str) -> dict:
    """Synchronous yfinance fetch (run in async thread)."""
    try:
        import yfinance as yf
        from services.research_engine import (
            compute_altman_z_score,
            compute_earnings_quality,
            compute_roic_vs_wacc,
            compute_growth_quality,
        )

        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info or {}

        roe = info.get("returnOnEquity")
        if roe is not None:
            roe = _sanitize_float(round(float(roe) * 100, 2))

        roce = None
        fin, bs, cf = None, None, None
        try:
            fin = ticker.financials
            bs = ticker.balance_sheet
            cf = ticker.cashflow
            if fin is not None and bs is not None and not fin.empty and not bs.empty:
                ebit = None
                ta = None
                cl = None
                for lbl in ["Operating Income", "EBIT", "Ebit"]:
                    if lbl in fin.index:
                        ebit = float(fin.loc[lbl].iloc[0])
                        break
                for lbl in ["Total Assets"]:
                    if lbl in bs.index:
                        ta = float(bs.loc[lbl].iloc[0])
                        break
                for lbl in ["Total Current Liabilities", "Current Liabilities"]:
                    if lbl in bs.index:
                        cl = float(bs.loc[lbl].iloc[0])
                        break
                if ebit is not None and ta is not None and cl is not None:
                    cap_emp = ta - cl
                    if cap_emp > 0:
                        roce = round((ebit / cap_emp) * 100, 2)
        except Exception:
            fin, bs, cf = None, None, None

        eps_growth = None
        try:
            trailing_eps = info.get("trailingEps")
            forward_eps = info.get("forwardEps")
            if trailing_eps and forward_eps and float(trailing_eps) > 0:
                eps_growth = round(((float(forward_eps) - float(trailing_eps)) / abs(float(trailing_eps))) * 100, 2)
        except Exception:
            pass

        piotroski = None
        beneish = None
        try:
            if fin is not None and bs is not None and not fin.empty and not bs.empty:
                piotroski = _compute_piotroski_score_from_data(info, fin, bs, cf)
                beneish = _compute_beneish_m_score_from_data(fin, bs)
        except Exception:
            pass

        gross_margin = info.get("grossMargins")
        if gross_margin is not None:
            gross_margin = _sanitize_float(round(float(gross_margin) * 100, 2))

        total_debt_to_market_cap = None
        try:
            total_debt = _to_float(info.get("totalDebt"))
            market_cap_raw = _to_float(info.get("marketCap"))
            if total_debt is not None and market_cap_raw is not None and market_cap_raw > 0:
                total_debt_to_market_cap = _sanitize_float(round(total_debt / market_cap_raw, 4))
        except Exception:
            pass

        recent_profit_positive = None
        try:
            q_fin = ticker.quarterly_financials
            if q_fin is not None and not q_fin.empty:
                net_income_labels = ["Net Income", "Net Income From Continuing Operations", "NetIncome"]
                for lbl in net_income_labels:
                    if lbl in q_fin.index:
                        recent_3q = q_fin.loc[lbl].iloc[:3].tolist()
                        recent_profit_positive = any(v > 0 for v in recent_3q if v is not None and str(v) != "nan")
                        break
        except Exception:
            recent_profit_positive = None

        revenue_cagr_3y = None
        try:
            if fin is not None and not fin.empty:
                rev_labels = ["Total Revenue", "Revenue", "Operating Revenue"]
                for lbl in rev_labels:
                    if lbl in fin.index:
                        rev_series = fin.loc[lbl].dropna()
                        if len(rev_series) >= 3:
                            oldest = float(rev_series.iloc[-1])
                            newest = float(rev_series.iloc[0])
                            n = len(rev_series) - 1
                            if oldest > 0 and newest > 0 and n > 0:
                                revenue_cagr_3y = _sanitize_float(round(((newest / oldest) ** (1 / n) - 1) * 100, 2))
                        break
        except Exception:
            pass

        fcf_yield = None
        try:
            free_cashflow = _to_float(info.get("freeCashflow"))
            market_cap_raw2 = _to_float(info.get("marketCap"))
            if free_cashflow is not None and market_cap_raw2 is not None and market_cap_raw2 > 0:
                fcf_yield = _sanitize_float(round((free_cashflow / market_cap_raw2) * 100, 2))
        except Exception:
            pass

        # ── Batch 2: Altman Z-Score ──────────────────────────────────────────
        altman_z_result: dict = {}
        try:
            if bs is not None and not bs.empty and fin is not None and not fin.empty:
                def _b2_get(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None

                ta_z = _b2_get(bs, ["Total Assets"])
                ca_z = _b2_get(bs, ["Total Current Assets", "Current Assets"])
                cl_z = _b2_get(bs, ["Total Current Liabilities", "Current Liabilities"])
                re_z = _b2_get(bs, ["Retained Earnings", "Retained Earnings (Deficit)"])
                tl_z = _b2_get(bs, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
                rev_z = _b2_get(fin, ["Total Revenue", "Revenue"])
                ebit_z = _b2_get(fin, ["Operating Income", "EBIT", "Ebit"])
                mc_z = _to_float(info.get("marketCap"))

                wc_z = (ca_z - cl_z) if (ca_z is not None and cl_z is not None) else None

                if all(v is not None for v in [ta_z, rev_z, ebit_z, mc_z, tl_z]) and ta_z > 0 and tl_z > 0:
                    altman_z_result = compute_altman_z_score(
                        working_capital=wc_z,
                        retained_earnings=re_z,
                        ebit=ebit_z,
                        market_cap=mc_z,
                        total_liabilities=tl_z,
                        revenue=rev_z,
                        total_assets=ta_z,
                    )
        except Exception as exc:
            logger.debug("Altman Z error for %s: %s", symbol, exc)

        # ── Batch 2: Earnings Quality ────────────────────────────────────────
        earnings_quality_result: dict = {}
        try:
            if cf is not None and not cf.empty and fin is not None and not fin.empty:
                def _cf_get(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None

                ocf_eq = _cf_get(cf, ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash From Operations"])
                ni_eq = _cf_get(fin, ["Net Income", "Net Income Applicable To Common Shares"])
                def _b2_get_bs(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None
                ta_eq = _b2_get_bs(bs, ["Total Assets"]) if bs is not None and not bs.empty else None

                if ocf_eq is not None and ni_eq is not None:
                    earnings_quality_result = compute_earnings_quality(
                        operating_cash_flow=ocf_eq,
                        net_income=ni_eq,
                        total_assets=ta_eq,
                    )
        except Exception as exc:
            logger.debug("Earnings quality error for %s: %s", symbol, exc)

        # ── Batch 2: ROIC vs WACC ───────────────────────────────────────────
        roic_result: dict = {}
        try:
            if fin is not None and not fin.empty and bs is not None and not bs.empty:
                def _rv_get(df, labels):
                    for lbl in labels:
                        if lbl in df.index:
                            v = df.loc[lbl].iloc[0] if len(df.loc[lbl]) > 0 else None
                            return float(v) if v is not None and str(v) != "nan" else None
                    return None

                ebit_rv = _rv_get(fin, ["Operating Income", "EBIT", "Ebit"])
                ta_rv = _rv_get(bs, ["Total Assets"])
                cl_rv = _rv_get(bs, ["Total Current Liabilities", "Current Liabilities"])
                td_rv = _to_float(info.get("totalDebt"))
                mc_rv = _to_float(info.get("marketCap"))
                eff_tax = _to_float(info.get("effectiveTaxRate")) or 0.25

                if ebit_rv is not None:
                    ic_rv = (ta_rv - cl_rv) if (ta_rv is not None and cl_rv is not None) else None
                    roic_result = compute_roic_vs_wacc(
                        ebit=ebit_rv,
                        tax_rate=min(max(float(eff_tax), 0.15), 0.40),
                        invested_capital=ic_rv,
                        total_assets=ta_rv,
                        current_liabilities=cl_rv,
                        total_debt=td_rv,
                        market_cap=mc_rv,
                    )
        except Exception as exc:
            logger.debug("ROIC vs WACC error for %s: %s", symbol, exc)

        # ── Batch 2: Growth Quality ──────────────────────────────────────────
        growth_quality_result: dict = {}
        try:
            if fin is not None and not fin.empty:
                def _gq_get_series(df, labels, n=4):
                    for lbl in labels:
                        if lbl in df.index:
                            return [float(v) if str(v) != "nan" else None for v in df.loc[lbl].iloc[:n].tolist()]
                    return []

                rev_list = _gq_get_series(fin, ["Total Revenue", "Revenue"])
                ebit_list = _gq_get_series(fin, ["Operating Income", "EBIT", "Ebit"])
                ebitda_margins = []
                if rev_list and ebit_list:
                    for r, e in zip(rev_list, ebit_list):
                        if r and r > 0 and e is not None:
                            ebitda_margins.append(round(e / r * 100, 2))
                        else:
                            ebitda_margins.append(None)

                if rev_list:
                    growth_quality_result = compute_growth_quality(
                        revenues=rev_list,
                        ebitda_margins=ebitda_margins,
                        fcf_yield=fcf_yield,
                    )
        except Exception as exc:
            logger.debug("Growth quality error for %s: %s", symbol, exc)

        return {
            "roe": _sanitize_float(roe),
            "roce": _sanitize_float(roce),
            "piotroski_score": piotroski,
            "beneish_m_score": _sanitize_float(beneish),
            "eps_growth_pct": _sanitize_float(eps_growth),
            "gross_margin": _sanitize_float(gross_margin),
            "debt_to_equity": _sanitize_float(info.get("debtToEquity")),
            "current_ratio": _sanitize_float(info.get("currentRatio")),
            "total_debt_to_market_cap": total_debt_to_market_cap,
            "recent_profit_positive": recent_profit_positive,
            "revenue_cagr_3y": revenue_cagr_3y,
            "fcf_yield": fcf_yield,
            "altman_z": altman_z_result if altman_z_result.get("available") else None,
            "altman_z_score": altman_z_result.get("z_score") if altman_z_result.get("available") else None,
            "altman_z_zone": altman_z_result.get("zone") if altman_z_result.get("available") else None,
            "earnings_quality": earnings_quality_result if earnings_quality_result.get("available") else None,
            "cfo_ni_ratio": earnings_quality_result.get("cfo_ni_ratio"),
            "accrual_ratio": earnings_quality_result.get("accrual_ratio"),
            "roic_vs_wacc": roic_result if roic_result.get("available") else None,
            "roic": roic_result.get("roic"),
            "wacc": roic_result.get("wacc"),
            "roic_wacc_spread": roic_result.get("spread"),
            "growth_quality": growth_quality_result if growth_quality_result.get("available") else None,
            "ebitda_margin_latest": growth_quality_result.get("ebitda_margin_latest"),
            "ebitda_margin_trend": growth_quality_result.get("ebitda_margin_trend"),
        }
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return {}


async def _get_fundamental_data(symbol: str) -> dict:
    """Fetch fundamental data via yfinance with MongoDB + in-memory cache (24h TTL)."""
    _s = _srv()
    now_ts = datetime.now(timezone.utc).timestamp()

    # In-memory cache
    if symbol in _s.FUNDAMENTAL_CACHE:
        cached = _s.FUNDAMENTAL_CACHE[symbol]
        if (now_ts - cached.get("_ts", 0)) < _s.FUNDAMENTAL_CACHE_TTL_SECONDS:
            return cached

    # MongoDB cache
    try:
        cached_doc = await _s.db.fundamental_cache.find_one({"symbol": symbol}, {"_id": 0})
        if cached_doc:
            cached_at = cached_doc.get("cached_at_ts", 0)
            if (now_ts - float(cached_at or 0)) < _s.FUNDAMENTAL_CACHE_TTL_SECONDS:
                cached_doc["_ts"] = float(cached_at or now_ts)
                _s.FUNDAMENTAL_CACHE[symbol] = cached_doc
                return cached_doc
    except Exception:
        pass

    # Fetch from yfinance (only if USE_YFINANCE=True)
    from services.data_policy import USE_YFINANCE
    data = {}
    if USE_YFINANCE:
        try:
            data = await asyncio.wait_for(asyncio.to_thread(_fetch_yfinance_fundamentals, symbol), timeout=15.0)
        except Exception:
            data = {}

    result = {
        "symbol": symbol,
        "roe": data.get("roe"),
        "roce": data.get("roce"),
        "piotroski_score": data.get("piotroski_score"),
        "beneish_m_score": data.get("beneish_m_score"),
        "eps_growth_pct": data.get("eps_growth_pct"),
        "gross_margin": data.get("gross_margin"),
        "debt_to_equity": data.get("debt_to_equity"),
        "current_ratio": data.get("current_ratio"),
        "total_debt_to_market_cap": data.get("total_debt_to_market_cap"),
        "recent_profit_positive": data.get("recent_profit_positive"),
        "revenue_cagr_3y": data.get("revenue_cagr_3y"),
        "fcf_yield": data.get("fcf_yield"),
        "altman_z_score": data.get("altman_z_score"),
        "altman_z_zone": data.get("altman_z_zone"),
        "altman_z": data.get("altman_z"),
        "cfo_ni_ratio": data.get("cfo_ni_ratio"),
        "accrual_ratio": data.get("accrual_ratio"),
        "earnings_quality": data.get("earnings_quality"),
        "roic": data.get("roic"),
        "wacc": data.get("wacc"),
        "roic_wacc_spread": data.get("roic_wacc_spread"),
        "roic_vs_wacc": data.get("roic_vs_wacc"),
        "growth_quality": data.get("growth_quality"),
        "ebitda_margin_latest": data.get("ebitda_margin_latest"),
        "ebitda_margin_trend": data.get("ebitda_margin_trend"),
        "cached_at_ts": now_ts,
        "_ts": now_ts,
    }

    try:
        store_doc = {k: v for k, v in result.items() if k != "_ts"}
        await _s.db.fundamental_cache.update_one(
            {"symbol": symbol},
            {"$set": store_doc},
            upsert=True,
        )
    except Exception:
        pass

    _s.FUNDAMENTAL_CACHE[symbol] = result
    return result
