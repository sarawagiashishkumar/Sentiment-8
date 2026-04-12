"""
Multibagger screener route handlers.

Endpoints: /multibagger/generate, /multibagger/candidates, /multibagger/custom-search
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deps import get_current_user
from models import (
    MultibaggerCandidate,
    MultibaggerGenerateResponse,
    StockCoreNormalized,
)

logger = logging.getLogger(__name__)

multibagger_router = APIRouter()


def _ndjson_line(obj: dict) -> str:
    return json.dumps(obj, default=str) + "\n"


class MultibaggerCustomSearchRequest(BaseModel):
    symbol: str


@multibagger_router.post("/multibagger/generate")
async def generate_multibaggers(current_user: dict = Depends(get_current_user)):
    """Stream multibagger candidate generation as NDJSON."""
    import server as _srv

    updated_user, charged = await _srv._consume_credits(current_user, 2.0)
    refreshed_at = _srv._utc_now_iso()

    async def _stream() -> AsyncGenerator[str, None]:
        import time as _time
        _gen_start = _time.monotonic()
        yield _ndjson_line({"type": "progress", "phase": "start", "message": "Scanning multibagger universe..."})

        # Run with inline keepalive to prevent proxy timeout
        task = asyncio.ensure_future(_srv._build_multibagger_candidates(refreshed_at))
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except asyncio.TimeoutError:
                yield _ndjson_line({"type": "keepalive", "ts": _srv._utc_now_iso()})
        candidates = task.result()
        potential_count = len([r for r in candidates if r.is_potential_multibagger])
        _scan_ms = round((_time.monotonic() - _gen_start) * 1000)

        yield _ndjson_line({"type": "progress", "phase": "scored", "message": f"Scored {len(candidates)} candidates, {potential_count} potential ({_scan_ms}ms)"})

        response = MultibaggerGenerateResponse(
            cost_charged=charged,
            credits_remaining=round(float(updated_user.get("credits", 0)), 2),
            analysis_refreshed_at=refreshed_at,
            candidates=candidates,
            potential_count=potential_count,
        )
        yield _ndjson_line({"type": "complete", "data": json.loads(response.model_dump_json())})

        # Store perf timings
        _total_ms = round((_time.monotonic() - _gen_start) * 1000)
        import services.app_state as _app_state
        _perf = {"scan_ms": _scan_ms, "total_ms": _total_ms, "candidates": len(candidates), "potential": potential_count, "ts": refreshed_at}
        _app_state.LAST_MB_PERF = _perf
        logger.info("Multibagger generation perf: scan=%dms total=%dms", _scan_ms, _total_ms)
        try:
            await _app_state.db.generation_perf_history.insert_one({
                "type": "multibagger", **_perf,
            })
        except Exception:
            pass

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@multibagger_router.get("/multibagger/candidates")
async def get_multibagger_candidates(
    refresh_nonce: str | None = Query(default=None),
    # Phase 5: Screener filters
    min_piotroski: int = Query(default=0, ge=0, le=9),
    max_beneish: float = Query(default=10.0),
    min_altman: float = Query(default=0.0),
    min_roic_vs_wacc: float = Query(default=-99.0),
    sf2_only: bool = Query(default=False),
    macro_tailwind_only: bool = Query(default=False),
    regime_label: str | None = Query(default=None),
    sort_by: str = Query(default="multibagger_score_desc"),
):
    """Stream multibagger candidates as NDJSON with optional screener filters."""
    import server as _srv

    _ = refresh_nonce

    async def _stream() -> AsyncGenerator[str, None]:
        yield _ndjson_line({"type": "progress", "phase": "start", "message": "Scanning candidates..."})
        candidates = await _srv._build_multibagger_candidates(_srv._utc_now_iso())

        # Apply screener filters
        filtered = []
        for c in candidates:
            if min_piotroski > 0 and (c.piotroski_score is None or c.piotroski_score < min_piotroski):
                continue
            if max_beneish < 10 and c.beneish_m_score is not None and c.beneish_m_score > max_beneish:
                continue
            if min_altman > 0:
                # altman_z not directly on model; skip filter if not available
                pass
            if min_roic_vs_wacc > -99 and (c.roic_vs_wacc is None or c.roic_vs_wacc < min_roic_vs_wacc):
                continue
            if sf2_only and not c.sf2_high_conviction:
                continue
            if macro_tailwind_only and not c.macro_tailwind:
                continue
            if regime_label and c.regime_label != regime_label:
                continue
            filtered.append(c)

        # Apply sort
        sort_map = {
            "multibagger_score_desc": lambda x: -(x.multibagger_score or 0),
            "piotroski_desc": lambda x: -(x.piotroski_score or 0),
            "roic_vs_wacc_desc": lambda x: -(x.roic_vs_wacc or -999),
            "fcf_yield_desc": lambda x: -(x.fcf_yield_val or -999),
            "eps_cagr_3y_desc": lambda x: -(x.eps_cagr_3y or -999),
            "pct_below_ath_asc": lambda x: (x.pct_below_ath or 999),
        }
        sort_fn = sort_map.get(sort_by, sort_map["multibagger_score_desc"])
        filtered.sort(key=sort_fn)

        data = [json.loads(c.model_dump_json()) for c in filtered]
        yield _ndjson_line({"type": "complete", "data": data})

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@multibagger_router.post("/multibagger/custom-search", response_model=MultibaggerCandidate)
async def multibagger_custom_search(
    payload: MultibaggerCustomSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Analyze any NSE symbol on-demand using the multibagger scoring engine."""
    import server as _srv
    from services.technical_core import compute_full_technical_snapshot

    _ = current_user
    symbol = payload.symbol.strip().upper()
    refreshed_at = _srv._utc_now_iso()

    try:
        core = await _srv._get_stock_core_cached(symbol)
        if core.get("ltp") is None:
            raise HTTPException(
                status_code=404,
                detail=f"No live data for '{symbol}'. Ensure it is a valid NSE symbol (e.g. RELIANCE, INFY).",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' not found or unavailable: {exc}",
        ) from exc

    stock = StockCoreNormalized(**core)
    fundamental: dict = {}
    try:
        fundamental = await _srv._get_fundamental_data(symbol)
    except Exception:
        pass

    # Fetch hist OHLCV to inject actual hist_vol and RSI/trend into analysis
    try:
        _cs_hist_df = await _srv._get_hist_ohlcv(symbol, period="1y")
        if _cs_hist_df is not None and len(_cs_hist_df) >= 20:
            _cs_ts = compute_full_technical_snapshot(symbol, _cs_hist_df, ltp=stock.ltp)
            _cs_hist_vol = _cs_ts.get("hist_vol")
            _cs_rsi = _cs_ts.get("rsi")
            _cs_trend = _cs_ts.get("trend_alignment")
            if _cs_hist_vol is not None:
                fundamental = {**fundamental, "hist_vol": _cs_hist_vol, "rsi": _cs_rsi, "trend_alignment": _cs_trend}
    except Exception:
        pass

    analysis = _srv.compute_multibagger_analysis(
        stock,
        fundamental=fundamental,
        active_macro_events=await _srv._get_active_macro_events(),
        india_vix=await _srv._get_india_vix(),
    )

    return MultibaggerCandidate(
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
        roe=analysis.get("roe"),
        roce=analysis.get("roce"),
        piotroski_score=analysis.get("piotroski_score"),
        beneish_m_score=analysis.get("beneish_m_score"),
        eps_growth_pct=analysis.get("eps_growth_pct"),
        debt_to_equity=analysis.get("debt_to_equity"),
        current_ratio=analysis.get("current_ratio"),
        gross_margin=analysis.get("gross_margin"),
        vol_bands=analysis.get("vol_bands"),
    )
