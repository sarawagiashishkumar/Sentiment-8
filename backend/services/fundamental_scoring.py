"""
Fundamental scoring — Pure computation functions for financial analysis.

Extracted from server.py for modularization.
Contains Piotroski F-Score and Beneish M-Score computation.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


def compute_piotroski_score(info: dict, fin: object, bs: object, cf: object) -> int:
    """
    Compute simplified Piotroski F-score (0-9) from yfinance data.
    Returns integer score. Higher = better quality.
    """
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


def compute_beneish_m_score(fin: object, bs: object) -> float | None:
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
