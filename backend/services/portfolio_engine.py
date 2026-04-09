"""
Portfolio Analysis Engine — Position analysis, horizon ranges, P&L.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Literal

from fastapi import HTTPException

from models import (
    PortfolioAnalyzeResponse,
    PortfolioExpectedSignal,
    PortfolioHorizonRange,
    PortfolioPositionInput,
    PortfolioStockAnalysis,
    StockCoreNormalized,
)
from services.technical_core import (
    compute_full_technical_snapshot,
)
from services.indicators import (
    compute_historical_volatility,
    compute_realistic_price_bands,
)

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


def _portfolio_horizon_ranges(
    value_flag: str,
    price_zone: str,
    pnl_pct: float,
    ltp: float | None = None,
    hist_vol: float | None = None,
    sector: str = "Unknown",
    pe_ratio: float | None = None,
    piotroski_score: int | None = None,
    rsi: float | None = None,
    trend_alignment: str | None = None,
    beneish_m_score: float | None = None,
) -> dict[str, PortfolioHorizonRange]:
    """
    Compute realistic horizon ranges using historical volatility + quality-adjusted drift.
    Falls back to valuation-based static ranges if hist_vol is not available.
    """
    # If we have historical volatility, use the research engine for accurate bands
    if hist_vol is not None and ltp is not None and ltp > 0:
        vol_bands = compute_realistic_price_bands(
            ltp=ltp,
            hist_vol=hist_vol,
            sector=sector,
            pe_ratio=pe_ratio,
            piotroski_score=piotroski_score,
            rsi=rsi,
            trend_alignment=trend_alignment,
            beneish_m_score=beneish_m_score,
        )
        response: dict[str, PortfolioHorizonRange] = {}
        for horizon in ["1W", "1M", "3M", "6M", "9M", "1Y"]:
            band = vol_bands.get(horizon, {})
            upside_pct = band.get("upside_pct", 5.0)
            downside_pct = band.get("downside_pct", -5.0)
            flag: Literal["GREEN", "RED"] = band.get("flag", "GREEN")
            response[horizon] = PortfolioHorizonRange(
                upside_pct=round(upside_pct, 2),
                downside_pct=round(downside_pct, 2),
                flag=flag,
            )
        return response

    # Fallback: valuation-based static approach (only when no hist_vol)
    if value_flag == "Attractive" and price_zone == "Near 52W low":
        base_up, base_down = 20.0, 8.0
    elif value_flag == "Expensive" and price_zone == "Near 52W high":
        base_up, base_down = 8.0, 20.0
    elif value_flag == "Expensive":
        base_up, base_down = 10.0, 16.0
    elif value_flag == "Attractive":
        base_up, base_down = 16.0, 10.0
    else:
        base_up, base_down = 12.0, 12.0

    overbought_penalty = 3 if pnl_pct > 20 else 0
    oversold_bonus = 3 if pnl_pct < -10 else 0

    horizons = {
        "1W": 0.25,
        "1M": 0.45,
        "3M": 0.8,
        "6M": 1.0,
        "9M": 1.2,
        "1Y": 1.35,
    }
    response2: dict[str, PortfolioHorizonRange] = {}
    for horizon, multiplier in horizons.items():
        upside = max(1.0, (base_up + oversold_bonus - overbought_penalty) * multiplier)
        downside = max(1.0, (base_down + overbought_penalty - oversold_bonus) * multiplier)
        flag2: Literal["GREEN", "RED"] = "GREEN" if upside >= downside * 1.15 else "RED"
        response2[horizon] = PortfolioHorizonRange(
            upside_pct=round(upside, 2),
            downside_pct=round(-downside, 2),
            flag=flag2,
        )
    return response2


async def _analyze_portfolio_positions(positions: list[dict]) -> PortfolioAnalyzeResponse:
    _s = _srv()
    _resolve_symbol_input = _s._resolve_symbol_input
    _to_float = _s._to_float
    _get_stock_core_cached = _s._get_stock_core_cached
    _get_fundamental_data = _s._get_fundamental_data
    _get_hist_ohlcv = _s._get_hist_ohlcv
    _position_in_range = _s._position_in_range
    IST = _s.IST
    get_stock_core = _s.get_stock_core
    from services.portfolio_risk import (
        merge_duplicate_holdings,
        compute_portfolio_correlation_matrix,
        compute_portfolio_stress_tests,
        compute_diversification_audit,
        compute_upcoming_catalysts,
        compute_master_stock_snapshot,
    )
    from services.indicators import compute_portfolio_risk_metrics
    from services.technical_core import compute_portfolio_verdict
    from services.price_band_engine import compute_price_bands as compute_new_price_bands
    from services import equity_master_cache
    # ── Batch 4: Merge duplicate holdings first ───────────────────────────
    positions = merge_duplicate_holdings(positions)

    normalized_positions = []
    for row in positions:
        raw_symbol = str(row.get("symbol", "")).strip()
        symbol = await _resolve_symbol_input(raw_symbol)
        avg_price = _to_float(row.get("avg_price"))
        quantity = _to_float(row.get("quantity"))
        if not symbol or avg_price is None or quantity is None or quantity <= 0:
            continue
        normalized_positions.append(
            {
                "symbol": symbol,
                "avg_price": float(avg_price),
                "quantity": float(quantity),
            }
        )

    if not normalized_positions:
        raise HTTPException(status_code=400, detail="No valid portfolio positions found")

    cores = await asyncio.gather(*[get_stock_core(item["symbol"]) for item in normalized_positions], return_exceptions=True)
    stock_rows: list[dict] = []
    failed_symbols: list[str] = []
    total_current_value = 0.0
    for idx, core in enumerate(cores):
        pos = normalized_positions[idx]
        sym = pos["symbol"]

        # Handle exceptions or None LTP — try symbol variations before giving up
        if isinstance(core, Exception) or (isinstance(core, dict) and StockCoreNormalized(**core).ltp is None):
            # Try EQ variant, uppercase trim
            variants = [
                sym.upper().strip(),
                sym.upper().replace("-EQ", "").replace(".NS", "").strip(),
                f"{sym.upper().strip()}-EQ",
            ]
            resolved_core = None
            for variant in variants:
                if variant == sym:
                    continue
                try:
                    candidate = await get_stock_core(variant)
                    if candidate and StockCoreNormalized(**candidate).ltp is not None:
                        resolved_core = candidate
                        break
                except Exception:
                    continue
            if resolved_core is None:
                logger.warning("Portfolio: No live data for symbol %s — skipping", sym)
                failed_symbols.append(sym)
                continue
            core = resolved_core

        stock = StockCoreNormalized(**core)
        if stock.ltp is None:
            logger.warning("Portfolio: LTP still None for symbol %s after fallback — skipping", sym)
            failed_symbols.append(sym)
            continue
        cost = pos["avg_price"] * pos["quantity"]
        current_value = stock.ltp * pos["quantity"]
        pnl_pct = ((stock.ltp - pos["avg_price"]) / pos["avg_price"]) * 100 if pos["avg_price"] > 0 else 0.0

        total_current_value += current_value
        stock_rows.append(
            {
                "core": stock,
                "avg_price": pos["avg_price"],
                "quantity": pos["quantity"],
                "cost": cost,
                "current_value": current_value,
                "pnl_pct": pnl_pct,
            }
        )

    if not stock_rows:
        raise HTTPException(
            status_code=400,
            detail=f"No live data available for provided symbols. Failed: {', '.join(failed_symbols) or 'all'}"
        )

    analyses: list[PortfolioStockAnalysis] = []
    hist_vol_map: dict[str, float] = {}  # Track per-stock hist_vol for risk metrics
    for row in stock_rows:
        stock = row["core"]
        pe = stock.pe_ratio
        if pe is None:
            value_flag: Literal["Attractive", "Fair", "Expensive"] = "Fair"
        elif pe <= 18:
            value_flag = "Attractive"
        elif pe <= 35:
            value_flag = "Fair"
        else:
            value_flag = "Expensive"

        position = _position_in_range(stock.ltp, stock.year_low, stock.year_high)
        if position is None:
            price_zone: Literal["Near 52W low", "Mid range", "Near 52W high"] = "Mid range"
        elif position <= 0.25:
            price_zone = "Near 52W low"
        elif position >= 0.75:
            price_zone = "Near 52W high"
        else:
            price_zone = "Mid range"

        day_change = 0.0
        if stock.prev_close is not None and stock.prev_close > 0:
            day_change = ((stock.ltp - stock.prev_close) / stock.prev_close) * 100
        if day_change > 0.5:
            momentum_proxy: Literal["Positive trend", "Flat", "Negative trend"] = "Positive trend"
        elif day_change < -0.5:
            momentum_proxy = "Negative trend"
        else:
            momentum_proxy = "Flat"

        if (stock.eps or 0) > 0 and (pe or 0) <= 30:
            quality_proxy: Literal["Stable quality", "Speculative", "Moderate"] = "Stable quality"
        elif (stock.eps or 0) <= 0 or (pe or 0) > 45:
            quality_proxy = "Speculative"
        else:
            quality_proxy = "Moderate"

        expected_signals: dict[str, PortfolioExpectedSignal] = {}

        # ── Use research engine verdict ──────────────────────────────────
        allocation_pct = (row["current_value"] / total_current_value) * 100 if total_current_value > 0 else 0.0

        # ── Step 1: Fetch fundamental cache ─────────────────────────────
        try:
            _fund = await _get_fundamental_data(stock.symbol)
        except Exception:
            _fund = {}
        _piotroski = _fund.get("piotroski_score") if _fund else None
        _beneish = _fund.get("beneish_m_score") if _fund else None
        _hist_vol_val = None
        _rsi_val = None
        _trend_val = None
        _master_snap: dict | None = None

        # ── Step 2: Fetch hist OHLCV for technical snapshot ──────────────
        try:
            _hist_df = await _get_hist_ohlcv(stock.symbol, period="1y")
            if _hist_df is not None and len(_hist_df) >= 20:
                _ts = compute_full_technical_snapshot(stock.symbol, _hist_df, ltp=stock.ltp)
                _hist_vol_val = _ts.get("hist_vol")
                _rsi_val = _ts.get("rsi")
                _trend_val = _ts.get("trend_alignment")
                _master_snap = compute_master_stock_snapshot(
                    symbol=stock.symbol,
                    ltp=stock.ltp,
                    hist=_hist_df,
                    sector=stock.sector,
                    market_cap=stock.market_cap,
                    index_memberships=[],
                )
        except Exception:
            pass

        # ── Step 3: Compute horizon ranges with ALL quality parameters ───
        # This single call uses hist_vol + Piotroski + RSI + trend + Beneish
        # for quality-adjusted drift instead of fixed 7%.
        if _hist_vol_val is not None:
            hist_vol_map[stock.symbol] = _hist_vol_val
        expected_ranges = _portfolio_horizon_ranges(
            value_flag,
            price_zone,
            row["pnl_pct"],
            ltp=stock.ltp,
            hist_vol=_hist_vol_val,
            sector=stock.sector or "Unknown",
            pe_ratio=stock.pe_ratio,
            piotroski_score=_piotroski,
            rsi=_rsi_val,
            trend_alignment=_trend_val,
            beneish_m_score=_beneish,
        )

        # ── Step 4: Build expected_signals from computed ranges ──────────
        for horizon, hr in expected_ranges.items():
            max_expected_price = round(stock.ltp * (1 + (hr.upside_pct / 100)), 2)
            min_expected_price = round(stock.ltp * (1 + (hr.downside_pct / 100)), 2)
            delta_amount = max_expected_price - row["avg_price"]
            delta_pct = (delta_amount / row["avg_price"]) * 100 if row["avg_price"] > 0 else 0.0
            expected_signals[horizon] = PortfolioExpectedSignal(
                max_expected_price=max_expected_price,
                min_expected_price=min_expected_price,
                amount_signal=f"{delta_amount:+.2f}",
                percent_signal=f"{delta_pct:+.2f}%",
                direction="PROFIT" if delta_amount >= 0 else "LOSS",
            )

        recommendation, comments = compute_portfolio_verdict(
            pnl_pct=row["pnl_pct"],
            price_zone=price_zone,
            value_flag=value_flag,
            rsi=_rsi_val,
            trend_alignment=_trend_val,
            piotroski=_piotroski,
            beneish=_beneish,
            hist_vol=_hist_vol_val,
            allocation_pct=allocation_pct,
        )

        _altman = _fund.get("altman_z_zone") if _fund else None
        _roic_spread = _fund.get("roic_wacc_spread") if _fund else None
        comments_list = comments.split("; ") if comments else []
        if _altman == "DISTRESS" and "Exit or avoid" not in comments:
            comments_list.append("Altman Z-Score in DISTRESS zone — review solvency risk")
        if _roic_spread is not None and _roic_spread < -3:
            comments_list.append(f"ROIC < WACC by {abs(_roic_spread):.1f}% — value destructive")
        comments = "; ".join(comments_list) if comments_list else comments

        # ── Phase 4: Price Band + Master Verdict Integration ─────────
        _holding_price_bands = None
        _holding_band_error = None
        _holding_verdict = None
        try:
            _cache_doc = await equity_master_cache.get_symbol(stock.symbol)
            if _cache_doc and not await equity_master_cache.is_stale(stock.symbol):
                _band_result = await compute_new_price_bands(stock.symbol)
                if _band_result.get("error"):
                    _holding_band_error = _band_result["error"]
                else:
                    _holding_price_bands = _band_result.get("bands")
                _holding_verdict = _compute_holding_verdict(
                    unrealised_pnl_pct=row["pnl_pct"],
                    doc=_cache_doc,
                    band_error=_holding_band_error,
                )
            else:
                _holding_band_error = "cache_miss_or_stale"
                _holding_verdict = "WAIT_AND_WATCH"
        except Exception as _hv_exc:
            logger.debug("Portfolio holding verdict failed for %s: %s", stock.symbol, _hv_exc)
            _holding_verdict = "WAIT_AND_WATCH"

        analyses.append(
            PortfolioStockAnalysis(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector,
                ltp=round(stock.ltp, 2),
                market_cap=stock.market_cap,
                pe_ratio=stock.pe_ratio,
                year_high=stock.year_high,
                year_low=stock.year_low,
                eps=stock.eps,
                avg_price=round(row["avg_price"], 2),
                quantity=round(row["quantity"], 2),
                allocation_pct=round(allocation_pct, 2),
                pnl_pct=round(row["pnl_pct"], 2),
                value_flag=value_flag,
                price_zone=price_zone,
                momentum_proxy=momentum_proxy,
                quality_proxy=quality_proxy,
                expected_ranges=expected_ranges,
                expected_signals=expected_signals,
                recommendation=recommendation,
                comments=comments,
                master_snapshot=_master_snap,
                altman_z_zone=_altman,
                roic_wacc_spread=_roic_spread,
                piotroski_score=_piotroski,
                beneish_m_score=_beneish,
                price_bands=_holding_price_bands,
                band_error=_holding_band_error,
                holding_verdict=_holding_verdict,
            )
        )

    analyses.sort(key=lambda row: row.allocation_pct, reverse=True)

    # ── Portfolio-level risk metrics ──────────────────────────────────────
    holdings_for_risk = [
        {
            "symbol": a.symbol,
            "ltp": a.ltp,
            "current_value": a.ltp * a.quantity if a.ltp and a.quantity else 0,
            "pnl_pct": a.pnl_pct,
            "sector": a.sector or "Unknown",
            "market_cap": a.market_cap,
            "hist_vol": hist_vol_map.get(a.symbol, 0.30),  # Use actual computed hist_vol
        }
        for a in analyses
    ]
    portfolio_risk = compute_portfolio_risk_metrics(holdings=holdings_for_risk)

    # ── Batch 4: Enhanced portfolio analytics ────────────────────────────────
    # Stress tests
    stress_tests = compute_portfolio_stress_tests(holdings=holdings_for_risk)

    # Diversification audit
    div_audit = compute_diversification_audit(holdings=holdings_for_risk)

    # Correlation matrix (from historical returns — 90 day window)
    returns_dict: dict[str, list[float]] = {}
    for a in analyses[:15]:  # cap at 15 to limit API calls
        try:
            hist_c = await _get_hist_ohlcv(a.symbol, period="3mo")
            if hist_c is not None and len(hist_c) >= 20:
                rets = hist_c["Close"].pct_change().dropna().tolist()
                returns_dict[a.symbol] = rets
        except Exception:
            pass
    corr_matrix = compute_portfolio_correlation_matrix(returns_dict)

    # Upcoming catalysts (next 15 days)
    catalyst_data = compute_upcoming_catalysts(
        symbols=[a.symbol for a in analyses],
        days_window=15,
    )

    # Merge metadata into response
    enhanced_risk = {
        **(portfolio_risk if isinstance(portfolio_risk, dict) else portfolio_risk.dict() if hasattr(portfolio_risk, 'dict') else {}),
        "stress_tests": stress_tests,
        "diversification_audit": div_audit,
        "correlation_matrix": corr_matrix,
        "upcoming_catalysts": catalyst_data,
    }

    return PortfolioAnalyzeResponse(
        cost_charged=0.0,
        credits_remaining=0.0,
        parsed_positions_count=len(analyses),
        stocks=analyses,
        failed_symbols=failed_symbols,
        portfolio_risk_metrics=portfolio_risk,
        enhanced_analytics=enhanced_risk,
    )


def _compute_holding_verdict(unrealised_pnl_pct: float, doc: dict, band_error: str | None = None) -> str:
    """
    Rule-based verdict engine for portfolio holdings.
    Uses equity_master_cache data — no API calls.
    Returns first matching verdict in priority order.
    """
    altman_z = doc.get("altman_z_score")
    debt_mcap = doc.get("debt_to_mcap_pct") or 0
    beneish = doc.get("beneish_m_score")
    piotroski = doc.get("piotroski_f_score")
    margin_trend = doc.get("ebitda_margin_trend", "stable")
    trend_align = doc.get("trend_alignment", "mixed")
    adx = doc.get("adx_14_daily")
    rsi = doc.get("rsi_14_daily")
    roic_spread = doc.get("roic_vs_wacc")
    pct_below_ath = doc.get("pct_below_ath") or 100

    # EXIT_IMMEDIATELY
    if altman_z is not None and altman_z < 1.23 and debt_mcap > 40:
        return "EXIT_IMMEDIATELY"
    if beneish is not None and beneish > -1.00:
        return "EXIT_IMMEDIATELY"
    if piotroski is not None and piotroski <= 2 and unrealised_pnl_pct < -15:
        return "EXIT_IMMEDIATELY"

    # PARTIAL_EXIT
    if unrealised_pnl_pct > 80 and pct_below_ath < 5:
        return "PARTIAL_EXIT"
    if beneish is not None and beneish > -1.78:
        return "PARTIAL_EXIT"
    if margin_trend == "contracting" and unrealised_pnl_pct > 30:
        return "PARTIAL_EXIT"

    # WAIT_AND_WATCH
    if trend_align == "mixed":
        return "WAIT_AND_WATCH"
    if adx is not None and adx < 18:
        return "WAIT_AND_WATCH"
    if band_error is not None:
        return "WAIT_AND_WATCH"

    # BUY_MORE_NOW
    if (piotroski is not None and piotroski >= 7
            and beneish is not None and beneish < -1.78
            and roic_spread is not None and roic_spread > 5
            and trend_align == "bullish"
            and rsi is not None and rsi < 55
            and unrealised_pnl_pct > -10):
        return "BUY_MORE_NOW"

    # ACCUMULATE_ON_DIPS
    if (piotroski is not None and piotroski >= 6
            and trend_align in ("bullish", "mixed")
            and rsi is not None and 40 <= rsi <= 65
            and -20 <= unrealised_pnl_pct <= 40):
        return "ACCUMULATE_ON_DIPS"

    # STRONG_HOLD
    if (piotroski is not None and piotroski >= 7
            and trend_align == "bullish"
            and unrealised_pnl_pct > 15):
        return "STRONG_HOLD"

    return "WAIT_AND_WATCH"



