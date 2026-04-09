"""
Multibagger Screening Engine — Core scoring and candidate building.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from models import MultibaggerCandidate, StockCoreNormalized
from services.technical_core import (
    compute_full_technical_snapshot,
)
from services.indicators import (
    compute_historical_volatility,
    compute_realistic_price_bands,
    check_stock_eligibility,
)
from services.macro_context import compute_macro_context
from services.price_band_engine import compute_price_bands as compute_new_price_bands
from services import equity_master_cache

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


# ── Helper functions (copied from server.py to avoid circular imports) ────────

def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a value between lower and upper bounds."""
    return max(lower, min(upper, value))


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    """Return None if numerator or denominator is None or denominator is 0."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _position_in_range(ltp: float | None, year_low: float | None, year_high: float | None) -> float | None:
    """Return position of LTP within 52W range (0=at low, 1=at high)."""
    if ltp is None or year_low is None or year_high is None or year_high <= year_low:
        return None
    return clamp((ltp - year_low) / (year_high - year_low), 0.0, 1.0)


def compute_multibagger_analysis(
    stock: StockCoreNormalized,
    fundamental: dict | None = None,
    active_macro_events: list[str] | None = None,
    india_vix: float | None = None,
) -> dict:
    ltp = stock.ltp
    market_cap = stock.market_cap
    pe = stock.pe_ratio
    book_value = stock.book_value
    eps = stock.eps
    year_high = stock.year_high
    year_low = stock.year_low

    pb_ratio_est = _safe_ratio(ltp, book_value)
    upside_to_52w_high_pct = (
        ((year_high - ltp) / ltp) * 100
        if year_high is not None and ltp is not None and ltp > 0
        else None
    )
    growth_proxy_pct = (
        ((year_high - year_low) / year_low) * 100
        if year_high is not None and year_low is not None and year_low > 0 and year_high > year_low
        else None
    )
    peg_ratio_est = _safe_ratio(pe, growth_proxy_pct) if growth_proxy_pct is not None else None
    day_change_pct = (
        ((ltp - stock.prev_close) / stock.prev_close) * 100
        if ltp is not None and stock.prev_close is not None and stock.prev_close > 0
        else 0.0
    )
    position = _position_in_range(ltp, year_low, year_high)

    tier_scores = {f"tier_{idx}": 0.0 for idx in range(1, 9)}

    # Tier 1: Business quality (ROE/ROCE/margin/revenue CAGR proxy)
    if market_cap is not None and market_cap >= 2_000:
        tier_scores["tier_1"] += 7
    if eps is not None and eps > 0:
        tier_scores["tier_1"] += 6
    if pe is not None and 8 <= pe <= 35:
        tier_scores["tier_1"] += 5

    # Tier 2: Financial health (leverage/liquidity proxy)
    if pb_ratio_est is not None and pb_ratio_est <= 5:
        tier_scores["tier_2"] += 5
    if market_cap is not None and market_cap >= 1_000:
        tier_scores["tier_2"] += 4
    if stock.volume >= 120_000:
        tier_scores["tier_2"] += 3

    # Tier 3: Growth trajectory proxy
    if growth_proxy_pct is not None:
        tier_scores["tier_3"] += clamp(growth_proxy_pct / 10, 0, 7)
    if ltp is not None and stock.open is not None and ltp > stock.open:
        tier_scores["tier_3"] += 3
    if day_change_pct > 0:
        tier_scores["tier_3"] += 2

    # Tier 4: Forensic quality proxy (Beneish/Piotroski/CFO proxy)
    if eps is not None and eps > 0:
        tier_scores["tier_4"] += 5
    if pe is not None and 6 <= pe <= 45:
        tier_scores["tier_4"] += 4
    if stock.sector != "Unknown":
        tier_scores["tier_4"] += 3

    # Tier 5: Valuation
    if peg_ratio_est is not None and peg_ratio_est <= 1.8:
        tier_scores["tier_5"] += 6
    if pe is not None and 10 <= pe <= 32:
        tier_scores["tier_5"] += 4
    if pb_ratio_est is not None and pb_ratio_est <= 3.5:
        tier_scores["tier_5"] += 2

    # Tier 6: Technical setup (Supertrend/50DMA/RSI proxy)
    if position is not None and 0.30 <= position <= 0.75:
        tier_scores["tier_6"] += 6
    if ltp is not None and stock.prev_close is not None and ltp > stock.prev_close:
        tier_scores["tier_6"] += 4
    if stock.volume >= 150_000:
        tier_scores["tier_6"] += 4

    # Tier 7: Institutional interest proxy
    if market_cap is not None and market_cap >= 12_000:
        tier_scores["tier_7"] += 6
    if stock.volume >= 250_000:
        tier_scores["tier_7"] += 4

    # Tier 8: Risk flags (deductions)
    risk_deduction = 0
    if pe is not None and pe > 60:
        risk_deduction += 4
    if eps is not None and eps <= 0:
        risk_deduction += 3
    if position is not None and position > 0.92:
        risk_deduction += 2
    if ltp is not None and ltp < 10:
        risk_deduction += 3
    tier_scores["tier_8"] = -float(risk_deduction)

    # Fixed weighted score composition
    raw_score = (
        tier_scores["tier_1"]
        + tier_scores["tier_2"]
        + tier_scores["tier_3"]
        + tier_scores["tier_4"]
        + tier_scores["tier_5"]
        + tier_scores["tier_6"]
        + tier_scores["tier_7"]
        + tier_scores["tier_8"]
    )
    final_score = int(clamp(round(raw_score), 0, 100))

    tier_thresholds = {
        "tier_1": 10,
        "tier_2": 7,
        "tier_3": 7,
        "tier_4": 7,
        "tier_5": 6,
        "tier_6": 7,
        "tier_7": 5,
    }
    tier_pass_count = sum(1 for key, threshold in tier_thresholds.items() if tier_scores.get(key, 0) >= threshold)

    mandatory_filters = (
        ltp is not None
        and ltp > 10
        and market_cap is not None
        and market_cap >= 500
        and eps is not None
        and eps > 0
    )
    is_potential_multibagger = bool(mandatory_filters and final_score >= 70 and tier_pass_count >= 5)

    # RSI: use real RSI from historical data if available (injected by _build_multibagger_candidates)
    # Falls back to 52W-position proxy only when hist data is unavailable
    _real_rsi = fundamental.get("rsi") if fundamental else None
    if _real_rsi is not None and 0 < _real_rsi <= 100:
        current_rsi_level = round(_real_rsi, 2)
    else:
        # Proxy: map 52W-position (0=near-low, 1=near-high) to RSI range 30–70
        current_rsi_level = round(30 + (position if position is not None else 0.5) * 40, 2) if ltp is not None else None
    gtt_buy_price = None
    if ltp is not None:
        base_buy = ltp * 0.965
        if year_low is not None and year_low > 0:
            base_buy = max(base_buy, year_low * 1.03)
        gtt_buy_price = round(base_buy, 2)

    duration_base = {
        "1W": 0.012,
        "1M": 0.045,
        "3M": 0.11,
        "6M": 0.19,
        "9M": 0.27,
        "1Y": 0.34,
    }
    momentum_adj = (final_score - 55) / 280
    targeted_upside_price = {}
    targeted_upside_profit_pct = {}

    # Use historical volatility from fundamental data if available
    hist_vol = fundamental.get("hist_vol") if fundamental else None

    # Compute volatility-based realistic price bands with quality-adjusted drift
    _mb_piotroski = fundamental.get("piotroski_score") if fundamental else None
    _mb_beneish = fundamental.get("beneish_m_score") if fundamental else None
    _mb_rsi = fundamental.get("rsi") if fundamental else None
    _mb_trend = fundamental.get("trend_alignment") if fundamental else None
    vol_bands = compute_realistic_price_bands(
        ltp=float(ltp),
        hist_vol=hist_vol,
        sector=getattr(stock, "sector", "Unknown") if hasattr(stock, "sector") else "Unknown",
        pe_ratio=pe,
        piotroski_score=_mb_piotroski,
        rsi=_mb_rsi,
        trend_alignment=_mb_trend,
        beneish_m_score=_mb_beneish,
        india_vix=india_vix,
    ) if ltp is not None else {}

    for key, base in duration_base.items():
        if ltp is None:
            targeted_upside_price[key] = None
            targeted_upside_profit_pct[key] = None
            continue

        # Use volatility-based expected high if available, else fall back to scoring-based
        if vol_bands and key in vol_bands:
            # Expected upside from vol-based band
            exp_upside_pct = vol_bands[key].get("upside_pct", 0) / 100
            growth = max(exp_upside_pct, 0.005)
        else:
            growth = base + momentum_adj
            if upside_to_52w_high_pct is not None and upside_to_52w_high_pct > 0:
                growth = min(growth, (upside_to_52w_high_pct / 100) * 1.25)
            growth = max(growth, 0.005)

        target_price = round(ltp * (1 + growth), 2)
        roi_pct = round(((target_price - ltp) / ltp) * 100, 2)

        targeted_upside_price[key] = target_price
        targeted_upside_profit_pct[key] = roi_pct

    thesis_parts = []

    # Score summary
    if final_score >= 80:
        thesis_parts.append(f"Strong multibagger profile (Score: {final_score}/100, {tier_pass_count}/7 tiers passed)")
    elif final_score >= 70:
        thesis_parts.append(f"Balanced quality-growth setup (Score: {final_score}/100, {tier_pass_count}/7 tiers passed)")
    else:
        thesis_parts.append(f"Developing setup needing confirmation (Score: {final_score}/100, {tier_pass_count}/7 tiers passed)")

    # Valuation
    if pe is not None and ltp is not None:
        if pe < 15:
            thesis_parts.append(f"Attractively valued at P/E {round(pe, 1)}x (undervalued territory)")
        elif pe < 25:
            thesis_parts.append(f"Fairly valued at P/E {round(pe, 1)}x")
        else:
            thesis_parts.append(f"Premium P/E {round(pe, 1)}x — growth premium required")

    if pb_ratio_est is not None:
        if pb_ratio_est < 2.0:
            thesis_parts.append(f"Trades at P/B {round(pb_ratio_est, 2)}x — below book, possible margin-of-safety")
        else:
            thesis_parts.append(f"P/B {round(pb_ratio_est, 2)}x")

    # Upside
    if upside_to_52w_high_pct is not None and upside_to_52w_high_pct > 0:
        thesis_parts.append(f"Potential upside to 52W high: {round(upside_to_52w_high_pct, 1)}%")

    # Fundamental overlays
    if fundamental:
        roe_val = fundamental.get("roe")
        roce_val = fundamental.get("roce")
        piotroski = fundamental.get("piotroski_score")
        beneish = fundamental.get("beneish_m_score")
        eps_g = fundamental.get("eps_growth_pct")
        de = fundamental.get("debt_to_equity")

        if roe_val is not None:
            if roe_val >= 20:
                thesis_parts.append(f"High ROE {roe_val}% — efficient capital use")
            elif roe_val >= 12:
                thesis_parts.append(f"Adequate ROE {roe_val}%")
            else:
                thesis_parts.append(f"Low ROE {roe_val}% — profitability concern")

        if roce_val is not None:
            if roce_val >= 15:
                thesis_parts.append(f"Strong ROCE {roce_val}%")
            else:
                thesis_parts.append(f"ROCE {roce_val}%")

        if piotroski is not None:
            if piotroski >= 7:
                thesis_parts.append(f"Piotroski F-Score {piotroski}/9 — high quality financials")
            elif piotroski >= 5:
                thesis_parts.append(f"Piotroski F-Score {piotroski}/9 — decent quality")
            else:
                thesis_parts.append(f"Piotroski F-Score {piotroski}/9 — review financials carefully")

        if beneish is not None:
            if beneish > -2.22:
                thesis_parts.append(f"Beneish M-Score {beneish} — potential earnings manipulation risk")
            else:
                thesis_parts.append(f"Beneish M-Score {beneish} — clean earnings quality")

        if eps_g is not None:
            thesis_parts.append(f"Expected EPS growth: {eps_g}%")

        if de is not None:
            if de < 0.5:
                thesis_parts.append(f"Low leverage (D/E {round(de, 2)}) — strong balance sheet")
            elif de < 1.5:
                thesis_parts.append(f"Moderate leverage (D/E {round(de, 2)})")
            else:
                thesis_parts.append(f"High leverage (D/E {round(de, 2)}) — watch debt servicing")

        # ── New fundamental fields ───────────────────────────────────────
        revenue_cagr = fundamental.get("revenue_cagr_3y")
        fcf_yield_val = fundamental.get("fcf_yield")
        debt_to_mktcap = fundamental.get("total_debt_to_market_cap")
        recent_profitable = fundamental.get("recent_profit_positive")

        if revenue_cagr is not None:
            if revenue_cagr >= 20:
                thesis_parts.append(f"Strong revenue CAGR {revenue_cagr:.1f}% (3Y)")
            elif revenue_cagr >= 10:
                thesis_parts.append(f"Healthy revenue CAGR {revenue_cagr:.1f}% (3Y)")
            elif revenue_cagr < 0:
                thesis_parts.append(f"Revenue decline {revenue_cagr:.1f}% CAGR — monitor closely")

        if fcf_yield_val is not None:
            if fcf_yield_val > 5:
                thesis_parts.append(f"Strong FCF yield {fcf_yield_val:.1f}% — cash generative business")
            elif fcf_yield_val < 0:
                thesis_parts.append(f"Negative FCF yield {fcf_yield_val:.1f}% — cash burn concern")

        if debt_to_mktcap is not None and debt_to_mktcap >= 0.20:
            thesis_parts.append(f"Debt {debt_to_mktcap*100:.0f}% of market cap — watch leverage")

        if recent_profitable is False:
            thesis_parts.append("No profitable quarter in last 3Q — revenue recovery needed")

        # ── Batch 2: Altman Z, ROIC vs WACC, Earnings Quality ───────────────
        altman_z_s = fundamental.get("altman_z_score")
        altman_z_zone = fundamental.get("altman_z_zone")
        roic_val = fundamental.get("roic")
        wacc_val = fundamental.get("wacc")
        roic_spread = fundamental.get("roic_wacc_spread")
        cfo_ni = fundamental.get("cfo_ni_ratio")
        ebitda_trend = fundamental.get("ebitda_margin_trend")

        if altman_z_zone is not None:
            if altman_z_zone == "SAFE":
                thesis_parts.append(f"Altman Z={altman_z_s:.2f} — financially sound")
            elif altman_z_zone == "GREY":
                thesis_parts.append(f"Altman Z={altman_z_s:.2f} — grey zone; watch leverage")
            else:
                thesis_parts.append(f"Altman Z={altman_z_s:.2f} — DISTRESS zone (red flag)")

        if roic_spread is not None:
            if roic_spread > 3:
                thesis_parts.append(f"ROIC {roic_val:.1f}% > WACC {wacc_val:.1f}% — value creating (+{roic_spread:.1f}%)")
            elif roic_spread < -3:
                thesis_parts.append(f"ROIC {roic_val:.1f}% < WACC {wacc_val:.1f}% — value destroying ({roic_spread:.1f}%)")

        if cfo_ni is not None:
            if cfo_ni < 0.5:
                thesis_parts.append(f"CFO/NI={cfo_ni:.2f} — low earnings quality (accrual-heavy)")
            elif cfo_ni >= 1.0:
                thesis_parts.append(f"CFO/NI={cfo_ni:.2f} — high earnings quality")

        if ebitda_trend == "DETERIORATING":
            thesis_parts.append("EBITDA margin deteriorating — margin compression risk")

        # ── Batch 4: Macro Context for Multibagger ────────────────────────
        try:
            _mb_sector = fundamental.get("sector") if fundamental else None
            _mb_macro = compute_macro_context(
                active_events=active_macro_events or [],
                vix=None,   # VIX not available in sync context; regime will use UNKNOWN
                sector=_mb_sector,
            )
            _mb_bias = _mb_macro.get("macro_bias", "NEUTRAL")
            if _mb_bias == "TAILWIND":
                thesis_parts.append(f"Sector '{_mb_sector}' has macro tailwind — favorable environment")
            elif _mb_bias == "HEADWIND":
                thesis_parts.append(f"Sector '{_mb_sector}' facing macro headwind — risk factor")
        except Exception:
            _mb_macro = {}
            _mb_bias = "NEUTRAL"

    # Tier breakdown
    passed_tiers = [k for k, threshold in tier_thresholds.items() if tier_scores.get(k, 0) >= threshold]
    if passed_tiers:
        tier_labels = {
            "tier_1": "Valuation", "tier_2": "Profitability", "tier_3": "Growth",
            "tier_4": "Balance Sheet", "tier_5": "Momentum", "tier_6": "Sector Tailwind", "tier_7": "Technical",
        }
        passed_names = [tier_labels.get(t, t) for t in passed_tiers]
        thesis_parts.append(f"Passing tiers: {', '.join(passed_names)}")

    if peg_ratio_est is not None:
        thesis_parts.append(f"PEG proxy: {round(peg_ratio_est, 2)}")

    thesis = " | ".join(thesis_parts)

    # Extract fundamental fields for direct model return
    roe_ret = fundamental.get("roe") if fundamental else None
    roce_ret = fundamental.get("roce") if fundamental else None
    piotroski_ret = fundamental.get("piotroski_score") if fundamental else None
    beneish_ret = fundamental.get("beneish_m_score") if fundamental else None
    eps_growth_ret = fundamental.get("eps_growth_pct") if fundamental else None
    de_ret = fundamental.get("debt_to_equity") if fundamental else None
    cr_ret = fundamental.get("current_ratio") if fundamental else None
    gm_ret = fundamental.get("gross_margin") if fundamental else None

    return {
        "multibagger_score": final_score,
        "upside_to_52w_high_pct": round(upside_to_52w_high_pct, 2) if upside_to_52w_high_pct is not None else None,
        "pb_ratio_est": round(pb_ratio_est, 2) if pb_ratio_est is not None else None,
        "peg_ratio_est": round(peg_ratio_est, 2) if peg_ratio_est is not None else None,
        "tier_pass_count": tier_pass_count,
        "is_potential_multibagger": is_potential_multibagger,
        "current_rsi_level": current_rsi_level,
        "gtt_buy_price": gtt_buy_price,
        "targeted_upside_price": targeted_upside_price,
        "targeted_upside_profit_pct": targeted_upside_profit_pct,
        "thesis": thesis,
        "roe": roe_ret,
        "roce": roce_ret,
        "piotroski_score": piotroski_ret,
        "beneish_m_score": beneish_ret,
        "eps_growth_pct": eps_growth_ret,
        "debt_to_equity": de_ret,
        "current_ratio": cr_ret,
        "gross_margin": gm_ret,
        "revenue_cagr_3y": fundamental.get("revenue_cagr_3y") if fundamental else None,
        "fcf_yield": fundamental.get("fcf_yield") if fundamental else None,
        "total_debt_to_market_cap": fundamental.get("total_debt_to_market_cap") if fundamental else None,
        "recent_profit_positive": fundamental.get("recent_profit_positive") if fundamental else None,
        # Batch 2 forensic
        "altman_z_score": fundamental.get("altman_z_score") if fundamental else None,
        "altman_z_zone": fundamental.get("altman_z_zone") if fundamental else None,
        "roic": fundamental.get("roic") if fundamental else None,
        "wacc": fundamental.get("wacc") if fundamental else None,
        "roic_wacc_spread": fundamental.get("roic_wacc_spread") if fundamental else None,
        "cfo_ni_ratio": fundamental.get("cfo_ni_ratio") if fundamental else None,
        "ebitda_margin_latest": fundamental.get("ebitda_margin_latest") if fundamental else None,
        "ebitda_margin_trend": fundamental.get("ebitda_margin_trend") if fundamental else None,
        "vol_bands": vol_bands,  # volatility-based realistic price bands for all horizons
        # ── Phase 3: New price band engine fields (from equity_master_cache) ──
        "price_bands": None,            # Populated by caller from price_band_engine
        "band_computation_status": None, # Populated by caller
        "forensic_flag": None,
        "conviction_penalty": 0,
        "sf2_high_conviction": False,
        "macro_tailwind": False,
        "pli_beneficiary": False,
        "govt_capex_beneficiary": False,
        "trend_alignment": fundamental.get("trend_alignment") if fundamental else None,
        "regime_label": "",
        "data_source": "equity_master_cache",
        "cache_as_of": None,
    }




async def _get_multibagger_universe() -> list[str]:
    _s = _srv()
    db = _s.db
    _sync_script_master_daily = _s._sync_script_master_daily
    _normalize_symbol_key = _s._normalize_symbol_key
    MULTIBAGGER_UNIVERSE = _s.MULTIBAGGER_UNIVERSE
    await _sync_script_master_daily()
    base = [_normalize_symbol_key(symbol) for symbol in MULTIBAGGER_UNIVERSE]
    base = [symbol for symbol in base if symbol and symbol not in {"NIFTY", "BANKNIFTY"}]

    rows = await db.script_master.find({}, {"_id": 0, "canonical_symbol": 1}).to_list(5000)
    dynamic_symbols: list[str] = []
    for row in rows:
        symbol = _normalize_symbol_key(str(row.get("canonical_symbol", "")))
        if not symbol or symbol in {"NIFTY", "BANKNIFTY"}:
            continue
        if len(symbol) < 2 or len(symbol) > 15:
            continue
        dynamic_symbols.append(symbol)

    merged = list(dict.fromkeys([*base, *dynamic_symbols]))
    # Runtime guard for FastAPI response performance while still covering a broad NSE universe slice
    return merged[:300]


async def _build_multibagger_candidates(refreshed_at: str) -> list[MultibaggerCandidate]:
    _s = _srv()
    _get_stock_core_cached = _s._get_stock_core_cached
    _get_fundamental_data = _s._get_fundamental_data
    _get_hist_ohlcv = _s._get_hist_ohlcv
    _get_india_vix = _s._get_india_vix
    _get_active_macro_events = _s._get_active_macro_events
    universe = await _get_multibagger_universe()

    semaphore = asyncio.Semaphore(18)
    fundamental_semaphore = asyncio.Semaphore(5)  # limit concurrent fundamental data calls
    hist_semaphore = asyncio.Semaphore(3)  # limit concurrent historical data calls

    async def _fetch_one(symbol: str) -> dict | None:
        async with semaphore:
            try:
                core = await _get_stock_core_cached(symbol)
                if core.get("ltp") is None:
                    return None
                return core
            except Exception:
                return None

    async def _fetch_fundamental_one(symbol: str) -> tuple[str, dict]:
        async with fundamental_semaphore:
            try:
                data = await _get_fundamental_data(symbol)
                return (symbol, data)
            except Exception:
                return (symbol, {})

    async def _fetch_hist_one(symbol: str) -> tuple[str, dict]:
        """Fetch historical vol, RSI, and trend_alignment for a symbol."""
        async with hist_semaphore:
            try:
                hist_df = await _get_hist_ohlcv(symbol, period="1y")
                if hist_df is not None and not hist_df.empty:
                    hist_vol = compute_historical_volatility(hist_df["Close"])
                    tech_snap = compute_full_technical_snapshot(symbol, hist_df)
                    return (symbol, {
                        "hist_vol": hist_vol,
                        "rsi": tech_snap.get("rsi"),
                        "trend_alignment": tech_snap.get("trend_alignment"),
                    })
            except Exception:
                pass
            return (symbol, {})

    fetched = await asyncio.gather(*[_fetch_one(symbol) for symbol in universe])
    results = [row for row in fetched if row is not None]
    valid_symbols = [row["symbol"] for row in results]

    # Fetch fundamentals and hist vols in parallel (uses cache, so mostly fast after first run)
    fundamental_results = await asyncio.gather(*[_fetch_fundamental_one(sym) for sym in valid_symbols])
    fundamental_map = {sym: data for sym, data in fundamental_results}

    hist_vol_results = await asyncio.gather(*[_fetch_hist_one(sym) for sym in valid_symbols])
    hist_tech_map = {sym: data for sym, data in hist_vol_results}

    # Fetch active macro events and India VIX once for all stocks
    _active_macro_evts = await _get_active_macro_events()
    _mb_india_vix = await _get_india_vix()

    candidates: list[MultibaggerCandidate] = []
    for row in results:
        stock = StockCoreNormalized(**row)
        if stock.ltp is None:
            continue

        fundamental = fundamental_map.get(stock.symbol, {})

        # ── Apply eligibility filters ───────────────────────────────────
        eligibility = check_stock_eligibility(
            ltp=stock.ltp,
            market_cap_cr=stock.market_cap,
            fundamental=fundamental,
        )
        # Inject hist_vol, RSI, and trend_alignment into fundamental dict
        hist_tech = hist_tech_map.get(stock.symbol, {})
        if hist_tech:
            fundamental = {**fundamental, **{k: v for k, v in hist_tech.items() if v is not None}}

        analysis = compute_multibagger_analysis(
            stock, fundamental=fundamental,
            active_macro_events=_active_macro_evts,
            india_vix=_mb_india_vix,
        )

        # Lower eligibility score if filters failed (don't fully exclude, just down-rank)
        if not eligibility["eligible"]:
            analysis["multibagger_score"] = max(0, analysis["multibagger_score"] - 20)
            analysis["is_potential_multibagger"] = False
            analysis["thesis"] = f"[ELIGIBILITY FLAGS: {'; '.join(eligibility['flags'])}] " + analysis.get("thesis", "")

        # ── Phase 3: Equity Master Cache + Price Band Integration ─────
        conviction_penalty = 0
        forensic_flag = None
        sf2_high_conviction = False
        price_bands = None
        band_status = "PENDING"
        cache_as_of = None

        try:
            cache_doc = await equity_master_cache.get_symbol(stock.symbol)
            if cache_doc and not await equity_master_cache.is_stale(stock.symbol):
                cache_as_of = cache_doc.get("as_of_timestamp")

                # Forensic quality gates (additive penalties)
                _beneish = cache_doc.get("beneish_m_score")
                _piotroski = cache_doc.get("piotroski_f_score")
                _pledging = cache_doc.get("pledging_pct", 0)
                _debt_mcap = cache_doc.get("debt_to_mcap_pct")

                if _beneish is not None and _beneish > -1.78:
                    forensic_flag = "BENEISH_RISK"
                    conviction_penalty -= 15
                if _piotroski is not None and _piotroski < 4:
                    forensic_flag = forensic_flag or "WEAK_PIOTROSKI"
                    conviction_penalty -= 10
                if _pledging and float(_pledging) > 20:
                    forensic_flag = forensic_flag or "HIGH_PLEDGING"
                    conviction_penalty -= 10
                if _debt_mcap is not None and float(_debt_mcap) >= 30:
                    # Skip candidate — too leveraged
                    continue

                # Compute new price bands
                bands_result = await compute_new_price_bands(stock.symbol)
                if bands_result.get("error"):
                    band_status = bands_result["error"].upper()
                else:
                    price_bands = bands_result.get("bands")
                    band_status = "OK"

                # SF2 high-conviction tag
                sf2_high_conviction = bool(
                    _piotroski is not None and _piotroski >= 7
                    and _beneish is not None and _beneish < -1.78
                    and cache_doc.get("supertrend_signal") == "buy"
                    and cache_doc.get("ltp", 0) > (cache_doc.get("ema_50_daily") or 0)
                    and cache_doc.get("trend_alignment") == "bullish"
                )

                # Macro tagging
                analysis["macro_tailwind"] = bool(cache_doc.get("sector") in (cache_doc.get("macro_tailwind_sectors") or []))
                analysis["pli_beneficiary"] = bool(cache_doc.get("pli_beneficiary"))
                analysis["govt_capex_beneficiary"] = bool(cache_doc.get("govt_capex_beneficiary"))
                analysis["trend_alignment"] = cache_doc.get("trend_alignment")
                analysis["regime_label"] = cache_doc.get("regime_label", "")
                analysis["week_52_high"] = cache_doc.get("week_52_high")
                analysis["week_52_low"] = cache_doc.get("week_52_low")
                analysis["pct_below_ath"] = cache_doc.get("pct_below_ath")
                analysis["roic_vs_wacc"] = cache_doc.get("roic_vs_wacc")
                analysis["fcf_yield"] = cache_doc.get("fcf_yield")
                analysis["eps_cagr_3y"] = cache_doc.get("eps_cagr_3y")
                analysis["ebitda_margin_trend"] = cache_doc.get("ebitda_margin_trend")
            else:
                band_status = "CACHE_MISS" if not cache_doc else "STALE"
        except Exception as exc:
            logger.debug("Cache/band integration failed for %s: %s", stock.symbol, exc)
            band_status = "ERROR"

        # Apply conviction penalty
        if conviction_penalty != 0:
            analysis["multibagger_score"] = max(0, analysis["multibagger_score"] + conviction_penalty)

        analysis["price_bands"] = price_bands
        analysis["band_computation_status"] = band_status
        analysis["forensic_flag"] = forensic_flag
        analysis["conviction_penalty"] = conviction_penalty
        analysis["sf2_high_conviction"] = sf2_high_conviction
        analysis["cache_as_of"] = cache_as_of

        candidates.append(
            MultibaggerCandidate(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector,
                ltp=stock.ltp,
                market_cap_cr=stock.market_cap,
                pe_ratio=stock.pe_ratio,
                year_high=stock.year_high,
                year_low=stock.year_low,
                upside_to_52w_high_pct=analysis["upside_to_52w_high_pct"],
                pb_ratio_est=analysis["pb_ratio_est"],
                peg_ratio_est=analysis["peg_ratio_est"],
                tier_pass_count=analysis["tier_pass_count"],
                is_potential_multibagger=analysis["is_potential_multibagger"],
                multibagger_score=analysis["multibagger_score"],
                current_rsi_level=analysis["current_rsi_level"],
                gtt_buy_price=analysis["gtt_buy_price"],
                targeted_upside_price=analysis["targeted_upside_price"],
                targeted_upside_profit_pct=analysis["targeted_upside_profit_pct"],
                thesis=analysis["thesis"],
                analysis_refreshed_at=refreshed_at,
                # Fundamental fields
                roe=analysis.get("roe"),
                roce=analysis.get("roce"),
                piotroski_score=analysis.get("piotroski_score"),
                beneish_m_score=analysis.get("beneish_m_score"),
                eps_growth_pct=analysis.get("eps_growth_pct"),
                debt_to_equity=analysis.get("debt_to_equity"),
                current_ratio=analysis.get("current_ratio"),
                gross_margin=analysis.get("gross_margin"),
                vol_bands=analysis.get("vol_bands"),
                # Phase 3: New fields
                price_bands=price_bands,
                band_computation_status=band_status,
                forensic_flag=forensic_flag,
                conviction_penalty=conviction_penalty,
                sf2_high_conviction=sf2_high_conviction,
                macro_tailwind=analysis.get("macro_tailwind", False),
                pli_beneficiary=analysis.get("pli_beneficiary", False),
                govt_capex_beneficiary=analysis.get("govt_capex_beneficiary", False),
                trend_alignment=analysis.get("trend_alignment"),
                regime_label=analysis.get("regime_label", ""),
                pct_below_ath=analysis.get("pct_below_ath"),
                roic_vs_wacc=analysis.get("roic_vs_wacc"),
                fcf_yield_val=analysis.get("fcf_yield"),
                eps_cagr_3y=analysis.get("eps_cagr_3y"),
                ebitda_margin_trend=analysis.get("ebitda_margin_trend"),
                data_source="equity_master_cache",
                cache_as_of=cache_as_of,
            )
        )

    candidates.sort(
        key=lambda row: (row.is_potential_multibagger, row.multibagger_score),
        reverse=True,
    )
    return candidates[:80]


_MONITORING_EVENT_COMMON_KEYS = frozenset({
    "type", "symbol", "underlying", "script", "direction",
    "timestamp", "severity", "reason",
})



