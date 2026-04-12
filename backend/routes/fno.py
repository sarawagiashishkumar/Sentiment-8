"""
FNO (Futures & Options) route handlers.

All endpoints under /fno/* are defined here.
Auth dependencies come from deps.py; heavy business logic helpers
are accessed via deferred `import server` inside handler bodies
to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from deps import get_current_user, get_owner_user
from models import (
    CustomPositionCreateRequest,
    CustomPositionCreateResponse,
    CustomPositionResponse,
    CustomPositionSellRequest,
    FNOGenerateRequest,
    FNOGenerateResponse,
    FNOSignalResponse,
    IndexAnalysisReport,
    IndexProjectionPane,
    ScriptSearchResult,
)
from data.fno_contracts import FNO_CONTRACTS
from services.backtest_engine import (
    is_strategy_enabled as is_backtest_enabled,
    run_backtest_batch,
)
from services.position_sizing import compute_position_size

logger = logging.getLogger(__name__)

fno_router = APIRouter()


def _ndjson_line(obj: dict) -> str:
    """Serialize a dict to a single NDJSON line."""
    return json.dumps(obj, default=str) + "\n"


def _empty_index_pane(name: str, note: str) -> IndexProjectionPane:
    report = IndexAnalysisReport(
        report_type="with_consolidated",
        breadth_score=0, momentum_score=0, bias="NEUTRAL",
        top_contributors=[], summary=note,
    )
    return IndexProjectionPane(
        index_name=name, spot=0,
        strike_range_min=0, strike_range_max=0,
        assured_signals=[], watchlist_signals=[],
        non_directional_strategies=[],
        rejection_note=note,
        with_consolidated_report=report,
        without_consolidated_report=report.model_copy(update={"report_type": "without_consolidated"}),
    )


# ── /fno/generate ─────────────────────────────────────────────────────────────

# NOTE: The old _run_phase_with_keepalive buffered keepalive lines and returned
# them as a list. This is WRONG — keepalives must stream to the client immediately
# to prevent proxy/ingress idle timeouts. The fix: inline the keepalive loop
# directly in the generator so `yield` sends them to the wire instantly.


async def _build_index_phase(index_name, refreshed_at, _srv):
    """Build a single index projection. Returns projection only (no buffered keepalives)."""
    try:
        projection = await _srv._build_index_projection(index_name, refreshed_at)
    except Exception:
        projection = _empty_index_pane(index_name, f"{index_name} projection temporarily unavailable")
    return projection


async def _build_stock_phase(refreshed_at, _srv):
    """Build stock F&O signals. Returns stock_signals only (no buffered keepalives)."""
    try:
        stock_signals = await _srv._build_stock_fno_signals(refreshed_at)
        logger.info("Stock F&O signals generated: %d", len(stock_signals))
    except asyncio.TimeoutError:
        logger.warning("Stock F&O signal generation timed out")
        stock_signals = []
    except Exception as exc:
        logger.error("Stock F&O signal generation failed: %s", exc)
        stock_signals = []
    return stock_signals


def _build_no_signals_alert(nifty_projection, banknifty_projection, stock_signals, top_trades, market_regime, market_session, threshold_display):
    """Build the 'no signals available' alert text if no potential trades found."""
    all_top_trades = [r for r in top_trades if r.is_potential_trade]
    if all_top_trades:
        return None
    reasons = []
    if nifty_projection.rejection_note:
        reasons.append(f"NIFTY: {nifty_projection.rejection_note}")
    if banknifty_projection.rejection_note:
        reasons.append(f"BANKNIFTY: {banknifty_projection.rejection_note}")
    if not stock_signals:
        reasons.append(f"Individual stock signals: No scripts passed {threshold_display}% confluence & R:R >= 1.2 filters")
    regime = market_regime.get("regime", "UNKNOWN")
    if regime in ("LOW_VOL_RANGE",):
        reasons.append(f"Market in {regime} — directional setups lacking conviction")
    elif regime in ("CRASH_MODE",):
        reasons.append(f"Market in {regime} — extreme volatility")
    if not market_session.get("is_open"):
        reasons.append(f"Market CLOSED ({market_session.get('status', 'CLOSED')})")
    reason_text = " | ".join(reasons) if reasons else f"Current market conditions do not meet minimum {threshold_display}% confluence threshold"
    return f"No script signals currently available. Reason: {reason_text}"


@fno_router.post("/fno/generate")
async def generate_fno_signals(
    payload: FNOGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Stream F&O signal generation as NDJSON lines for progressive UI rendering."""
    import server as _srv
    from services.technical_core import compute_full_technical_snapshot
    from services.macro_context import classify_market_regime_enhanced
    from services.data_verifier import get_market_session_status
    from services.fno_signal_engine import _ctx_user_budget, _ctx_account_risk_pct
    from datetime import datetime

    # Consume credits upfront (fast)
    updated_user, charged = await _srv._consume_credits(current_user, 2)
    refreshed_at = _srv._utc_now_iso()

    # Set user's budget/risk context for signal engine position sizing
    _user_budget = float(current_user.get("fno_budget", 500000))
    _user_risk_pct = float(current_user.get("account_risk_pct", 2.0))
    _ctx_user_budget.set(_user_budget)
    _ctx_account_risk_pct.set(_user_risk_pct)

    async def _stream_generate() -> AsyncGenerator[str, None]:
        import time as _time
        _perf = {}
        _gen_start = _time.monotonic()

        _now_ist = datetime.now(_srv.IST)
        _is_market_hrs = (
            _now_ist.weekday() < 5
            and (_now_ist.hour > 9 or (_now_ist.hour == 9 and _now_ist.minute >= 15))
            and (_now_ist.hour < 15 or (_now_ist.hour == 15 and _now_ist.minute <= 30))
        )
        if not _is_market_hrs:
            yield _ndjson_line({"type": "progress", "phase": "market_hours", "message": "Market closed — using last available data"})

        # ── Phase 1: NIFTY projection (with inline keepalive) ──────────────
        _t0 = _time.monotonic()
        yield _ndjson_line({"type": "progress", "phase": "nifty", "message": "Computing NIFTY projection..."})
        nifty_task = asyncio.ensure_future(_build_index_phase("NIFTY", refreshed_at, _srv))
        while not nifty_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(nifty_task), timeout=5)
            except asyncio.TimeoutError:
                yield _ndjson_line({"type": "keepalive", "ts": _srv._utc_now_iso()})
        nifty_projection = nifty_task.result()
        _perf["nifty_ms"] = round((_time.monotonic() - _t0) * 1000)
        yield _ndjson_line({"type": "progress", "phase": "nifty_done", "message": f"NIFTY: {len(nifty_projection.assured_signals)} signals ({_perf['nifty_ms']}ms)"})

        # Send partial NIFTY results immediately so frontend can display them
        nifty_partial = {
            "nifty_projection": json.loads(nifty_projection.model_dump_json()) if hasattr(nifty_projection, 'model_dump_json') else {},
            "signals_so_far": len(nifty_projection.assured_signals),
        }
        yield _ndjson_line({"type": "partial", "phase": "nifty", "data": nifty_partial})

        # ── Phase 2: BANKNIFTY projection (with inline keepalive) ──────────
        _t0 = _time.monotonic()
        yield _ndjson_line({"type": "progress", "phase": "banknifty", "message": "Computing BANKNIFTY projection..."})
        bn_task = asyncio.ensure_future(_build_index_phase("BANKNIFTY", refreshed_at, _srv))
        while not bn_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(bn_task), timeout=5)
            except asyncio.TimeoutError:
                yield _ndjson_line({"type": "keepalive", "ts": _srv._utc_now_iso()})
        banknifty_projection = bn_task.result()
        _perf["banknifty_ms"] = round((_time.monotonic() - _t0) * 1000)
        yield _ndjson_line({"type": "progress", "phase": "banknifty_done", "message": f"BANKNIFTY: {len(banknifty_projection.assured_signals)} signals ({_perf['banknifty_ms']}ms)"})

        # Send partial BANKNIFTY results
        banknifty_partial = {
            "banknifty_projection": json.loads(banknifty_projection.model_dump_json()) if hasattr(banknifty_projection, 'model_dump_json') else {},
            "signals_so_far": len(nifty_projection.assured_signals) + len(banknifty_projection.assured_signals),
        }
        yield _ndjson_line({"type": "partial", "phase": "banknifty", "data": banknifty_partial})

        # ── Phase 3: Stock F&O signals (with inline keepalive) ─────────────
        _t0 = _time.monotonic()
        yield _ndjson_line({"type": "progress", "phase": "stocks", "message": "Scanning stock F&O universe..."})
        stock_task = asyncio.ensure_future(_build_stock_phase(refreshed_at, _srv))
        while not stock_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(stock_task), timeout=5)
            except asyncio.TimeoutError:
                yield _ndjson_line({"type": "keepalive", "ts": _srv._utc_now_iso()})
        stock_signals = stock_task.result()
        _perf["stocks_ms"] = round((_time.monotonic() - _t0) * 1000)
        yield _ndjson_line({"type": "progress", "phase": "stocks_done", "message": f"Stocks: {len(stock_signals)} signals ({_perf['stocks_ms']}ms)"})

        # ── Phase 4: Custom signal (if requested) ────────────────────────
        custom_signal = None
        if payload.custom_script:
            yield _ndjson_line({"type": "progress", "phase": "custom", "message": f"Analyzing {payload.custom_script}..."})
            contract = await _srv._resolve_contract_from_input(payload.custom_script)
            try:
                custom_signal = await _srv._build_signal_for_contract(contract, refreshed_at)
            except Exception as exc:
                yield _ndjson_line({"type": "progress", "phase": "custom_error", "message": f"Custom signal failed: {exc}"})

        # ── Phase 5: Assembly ─────────────────────────────────────────────
        _t0 = _time.monotonic()
        yield _ndjson_line({"type": "progress", "phase": "assembly", "message": "Assembling final results..."})

        potential_signals = [*nifty_projection.assured_signals, *banknifty_projection.assured_signals]
        signals = sorted(potential_signals, key=lambda r: r.confluence_score, reverse=True)

        top_pool = [*signals, *stock_signals]
        if custom_signal:
            top_pool.append(custom_signal)
        top_trades = sorted(
            top_pool,
            key=lambda r: (r.is_potential_trade, r.confluence_score),
            reverse=True,
        )[:4]

        india_vix = await _srv._get_india_vix()
        _nifty_ts = None
        try:
            _nifty_hist = await _srv._get_hist_ohlcv("NIFTY", period="3mo")
            if _nifty_hist is not None:
                _nifty_ts = compute_full_technical_snapshot("NIFTY", _nifty_hist)
        except Exception:
            pass
        _nifty_adx = _nifty_ts.get("adx") if _nifty_ts else None
        _nifty_rsi = _nifty_ts.get("rsi") if _nifty_ts else None
        market_regime = classify_market_regime_enhanced(vix=india_vix, adx=_nifty_adx, rsi=_nifty_rsi)
        market_session = get_market_session_status()

        no_signals_alert = _build_no_signals_alert(
            nifty_projection, banknifty_projection, stock_signals,
            top_trades, market_regime, market_session, _srv.CONFLUENCE_THRESHOLD_DISPLAY,
        )

        response = FNOGenerateResponse(
            cost_charged=charged,
            credits_remaining=round(float(updated_user.get("credits", 0)), 2),
            analysis_refreshed_at=refreshed_at,
            signals=signals,
            potential_signals=[r for r in signals if r.is_potential_trade],
            top_trades=top_trades,
            custom_signal=custom_signal,
            nifty_projection=nifty_projection,
            banknifty_projection=banknifty_projection,
            stock_signals=stock_signals,
            no_signals_alert=no_signals_alert,
            market_regime=market_regime,
            market_session=market_session,
        )

        yield _ndjson_line({"type": "complete", "data": json.loads(response.model_dump_json())})

        # ── Store perf timings ────────────────────────────────────────────
        _perf["assembly_ms"] = round((_time.monotonic() - _t0) * 1000)
        _perf["total_ms"] = round((_time.monotonic() - _gen_start) * 1000)
        _perf["ts"] = refreshed_at
        import services.app_state as _app_state
        _app_state.LAST_FNO_PERF = _perf
        logger.info("FNO generation perf: %s", _perf)

        # ── Auto-capture: log all generated signals to signal_log ──
        try:
            from services.sticky_card_engine import log_generated_signal
            all_sigs = [*signals, *stock_signals]
            if custom_signal:
                all_sigs.append(custom_signal)
            for sig in all_sigs:
                sig_dict = json.loads(sig.model_dump_json()) if hasattr(sig, 'model_dump_json') else sig.__dict__
                await log_generated_signal(_srv.db, sig_dict)
        except Exception as _log_err:
            pass  # signal logging is optional, never blocks response

        # ── Auto-capture: IV term structure snapshots ──
        try:
            from services.iv_analytics import capture_iv_term_structure
            for proj in (nifty_projection, banknifty_projection):
                if proj and hasattr(proj, 'assured_signals') and proj.assured_signals:
                    sym = proj.assured_signals[0].underlying or ""
                    expiry_iv_map = {}
                    for s in proj.assured_signals:
                        if s.expiry and s.atm_iv:
                            expiry_iv_map[s.expiry] = s.atm_iv
                    if expiry_iv_map:
                        await capture_iv_term_structure(_srv.db, sym, expiry_iv_map)
        except Exception:
            pass  # IV capture is optional

    return StreamingResponse(_stream_generate(), media_type="application/x-ndjson")


# ── /fno/custom-position (CRUD) ──────────────────────────────────────────────

@fno_router.post("/fno/custom-position", response_model=CustomPositionCreateResponse)
async def create_custom_position(
    payload: CustomPositionCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    import server as _srv

    if payload.buy_price <= 0:
        raise HTTPException(status_code=400, detail="Buy price must be greater than 0")

    contract = await _srv._resolve_contract_from_input(payload.script)
    final_lot_size = await _srv._resolve_verified_lot_size(contract.underlying, contract.script)
    if final_lot_size > 0 and final_lot_size != contract.lot_size:
        contract = contract.model_copy(update={"lot_size": final_lot_size})
    minutes_to_expiry = _srv.get_minutes_to_expiry(contract)
    _srv._validate_expiry_guard(minutes_to_expiry)

    updated_user, charged = await _srv._consume_credits(current_user, 1.0)
    try:
        latest_snapshot = await _srv._fetch_live_option_snapshot(contract)
        latest_option_ltp = float(latest_snapshot.get("ltp"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch live option LTP") from exc

    position_id = str(uuid.uuid4())
    now_iso = _srv._utc_now_iso()
    doc = {
        "id": position_id,
        "user_key": current_user["user_key"],
        "script": contract.script,
        "underlying": contract.underlying,
        "expiry_date": contract.expiry,
        "expiry_time_ist": contract.expiry_time_ist,
        "strike": contract.strike,
        "option_type": contract.option_type,
        "lot_size": contract.lot_size,
        "quantity_lots": int(payload.quantity_lots),
        "buy_price": round(float(payload.buy_price), 2),
        "created_at": now_iso,
        "last_update": now_iso,
        "status": "OPEN",
        "signal_state": "ACTIVE",
        "alert": None,
        "latest_option_ltp": round(float(latest_option_ltp), 2),
        **_srv._compute_initial_option_targets(float(payload.buy_price)),
        "stop_loss": _srv._compute_initial_option_sl(float(payload.buy_price)),
        "projected_exit_price": None,
        "best_exit_price": None,
        "best_exit_days": None,
        "recovery_potential": None,
        "sold_price": None,
        "realized_pnl": None,
        "minutes_to_expiry": minutes_to_expiry,
        "revised_exit_plan": "Hold with trailing stop once target1 hits",
    }

    await _srv.db.custom_positions.insert_one(doc)
    return CustomPositionCreateResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        position=_srv._position_to_response(doc),
    )


@fno_router.get("/fno/custom-positions", response_model=List[CustomPositionResponse])
async def list_custom_positions(current_user: dict = Depends(get_current_user)):
    import server as _srv
    from pymongo import ReturnDocument

    rows = await _srv.db.custom_positions.find(
        {"user_key": current_user["user_key"], "status": {"$in": ["OPEN", "SOLD"]}},
        {"_id": 0},
    ).to_list(200)

    refreshed: list[CustomPositionResponse] = []
    for row in rows:
        if row.get("status") == "SOLD":
            if int(row.get("lot_size") or 1) <= 1:
                corrected = await _srv._resolve_verified_lot_size(
                    str(row.get("underlying", "")), str(row.get("script", ""))
                )
                if corrected > 1:
                    row = await _srv.db.custom_positions.find_one_and_update(
                        {"id": row["id"], "user_key": current_user["user_key"]},
                        {"$set": {"lot_size": corrected, "last_update": _srv._utc_now_iso()}},
                        projection={"_id": 0},
                        return_document=ReturnDocument.AFTER,
                    ) or row
            refreshed.append(_srv._position_to_response(row))
            continue
        try:
            updated = await _srv._refresh_open_position(row)
            if updated and updated.get("status") == "OPEN":
                refreshed.append(_srv._position_to_response(updated))
        except Exception as exc:
            logger.warning("Failed to refresh custom position %s: %s", row.get("id"), exc)
            fallback = {
                **row,
                "alert": row.get("alert") or "REFRESH_ERROR",
                "revised_exit_plan": row.get("revised_exit_plan")
                or "Temporary refresh issue; retry in a moment",
            }
            refreshed.append(_srv._position_to_response(fallback))
            continue

    refreshed.sort(key=lambda item: item.created_at, reverse=True)
    return refreshed


@fno_router.post("/fno/custom-position/{position_id}/sell", response_model=CustomPositionResponse)
async def sell_custom_position(
    position_id: str,
    payload: CustomPositionSellRequest,
    current_user: dict = Depends(get_current_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    if payload.sold_price <= 0:
        raise HTTPException(status_code=400, detail="Sold price must be greater than 0")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Please confirm sale before submitting")

    row = await _srv.db.custom_positions.find_one(
        {"id": position_id, "user_key": current_user["user_key"], "status": "OPEN"},
        {"_id": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Open custom position not found")

    units = max(1, int(row.get("lot_size", 1)) * int(row.get("quantity_lots", 1) or 1))
    realized_pnl = round((float(payload.sold_price) - float(row["buy_price"])) * units, 2)

    updated = await _srv.db.custom_positions.find_one_and_update(
        {"id": position_id, "user_key": current_user["user_key"], "status": "OPEN"},
        {
            "$set": {
                "status": "SOLD",
                "alert": "SOLD",
                "sold_price": round(float(payload.sold_price), 2),
                "realized_pnl": realized_pnl,
                "last_update": _srv._utc_now_iso(),
                "revised_exit_plan": "Position sold by user.",
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Open custom position not found")
    return _srv._position_to_response(updated)


@fno_router.post("/fno/custom-position/{position_id}/close")
async def close_custom_position(
    position_id: str,
    current_user: dict = Depends(get_current_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    updated = await _srv.db.custom_positions.find_one_and_update(
        {
            "id": position_id,
            "user_key": current_user["user_key"],
            "status": "OPEN",
        },
        {
            "$set": {
                "status": "CLOSED",
                "last_update": _srv._utc_now_iso(),
                "alert": "CLOSED_BY_USER",
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Custom position not found")
    return {"closed": True, "id": position_id}


@fno_router.delete("/fno/custom-position/{position_id}")
async def remove_custom_position(
    position_id: str,
    current_user: dict = Depends(get_current_user),
):
    import server as _srv

    result = await _srv.db.custom_positions.delete_one(
        {
            "id": position_id,
            "user_key": current_user["user_key"],
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Custom position not found")
    return {"removed": True, "id": position_id}


# ── /fno/position-alerts ──────────────────────────────────────────────────────

@fno_router.get("/fno/position-alerts")
async def get_position_alerts(current_user: dict = Depends(get_current_user)):
    """Aggregated monitoring events across all OPEN positions for current user."""
    import server as _srv

    rows = await _srv.db.custom_positions.find(
        {"user_key": current_user["user_key"], "status": "OPEN"},
        {"_id": 0, "id": 1, "script": 1, "underlying": 1, "monitoring_events": 1},
    ).to_list(200)

    all_events: list[dict] = []
    for row in rows:
        events = row.get("monitoring_events", [])
        for evt in events:
            evt_copy = {**evt, "position_id": row.get("id")}
            all_events.append(evt_copy)

    _sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_events.sort(
        key=lambda e: (
            _sev_order.get(e.get("severity", "MEDIUM"), 2),
            e.get("timestamp", ""),
        ),
    )

    return {"alerts": all_events, "count": len(all_events)}


# ── /fno/backtest-batch & strategy-backtests ──────────────────────────────────

@fno_router.post("/fno/backtest-batch")
async def trigger_backtest_batch(current_user: dict = Depends(get_owner_user)):
    """Run strategy backtests for all strategy x instrument combinations. Owner-only."""
    import server as _srv
    from services.strategy_library import STRATEGY_LIBRARY

    result = await run_backtest_batch(_srv.db, STRATEGY_LIBRARY)
    return result


@fno_router.get("/fno/strategy-backtests")
async def list_strategy_backtests_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """List all strategy backtest records with their enable/disable status."""
    import server as _srv

    rows = await _srv.db.strategy_backtests.find({}, {"_id": 0}).to_list(500)
    for r in rows:
        r["enabled"] = is_backtest_enabled(r)
    return {"backtests": rows, "count": len(rows)}


# ── /fno/position-sizing ─────────────────────────────────────────────────────

@fno_router.post("/fno/position-sizing")
async def calculate_position_sizing(
    user_budget: float = 100000,
    option_premium: float = 100,
    lot_size: int = 50,
    sl_price: float | None = None,
    entry_price: float | None = None,
    max_risk_pct: float = 2.0,
    atr14: float | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Calculate position sizing for a given trade setup (enhanced with ATR14)."""
    _acct_risk = float(current_user.get("account_risk_pct", max_risk_pct))
    result = compute_position_size(
        user_budget=user_budget,
        option_premium=option_premium,
        lot_size=lot_size,
        sl_price=sl_price,
        entry_price=entry_price,
        max_risk_per_trade_pct=max_risk_pct,
        atr14=atr14,
        account_risk_pct=_acct_risk,
    )
    return result


# ── /fno/scripts/search ──────────────────────────────────────────────────────

@fno_router.get("/fno/scripts/search", response_model=ScriptSearchResult)
async def search_scripts(q: str = Query(default="")):
    query = q.strip().upper()
    suggestions = []
    for row in FNO_CONTRACTS:
        script = row["script"]
        if not query or query in script:
            suggestions.append(script)
    suggestions = sorted(set(suggestions))[:30]
    return ScriptSearchResult(query=query, suggestions=suggestions)


# ── Backward-compatibility endpoints ─────────────────────────────────────────

@fno_router.get("/fno/signal/{script}", response_model=FNOSignalResponse)
async def get_single_fno_signal(
    script: str, refresh_nonce: str | None = Query(default=None),
):
    import server as _srv

    _ = refresh_nonce
    contract = await _srv._resolve_contract_from_input(script)
    try:
        return await _srv._build_signal_for_contract(contract, _srv._utc_now_iso())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@fno_router.get("/fno/signals/index", response_model=List[FNOSignalResponse])
async def get_index_fno_signals(refresh_nonce: str | None = Query(default=None)):
    import server as _srv

    _ = refresh_nonce
    refreshed_at = _srv._utc_now_iso()
    nifty_projection, bank_projection = await asyncio.gather(
        _srv._build_index_projection("NIFTY", refreshed_at),
        _srv._build_index_projection("BANKNIFTY", refreshed_at),
    )
    return sorted(
        [*nifty_projection.assured_signals, *bank_projection.assured_signals],
        key=lambda row: row.confluence_score,
        reverse=True,
    )


@fno_router.get("/fno/signals/potential", response_model=List[FNOSignalResponse])
async def get_potential_index_signals(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    rows = await get_index_fno_signals(refresh_nonce=None)
    if rows:
        return rows[:6]
    return rows



# ===========================================================================
# Batch 4: Sticky Card & Popup Event Endpoints
# ===========================================================================

@fno_router.get("/fno/events")
async def get_popup_events(
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_owner_user),
):
    """Get unacknowledged popup events (most recent first)."""
    import server as _srv
    from services.sticky_card_engine import get_unacknowledged_events
    return await get_unacknowledged_events(_srv.db, limit=limit)


@fno_router.post("/events/acknowledge")
async def acknowledge_popup_event(
    event_id: str = Query(...),
    user=Depends(get_owner_user),
):
    """Acknowledge (dismiss) a single popup event."""
    import server as _srv
    from services.sticky_card_engine import acknowledge_event
    ok = await acknowledge_event(_srv.db, event_id)
    return {"acknowledged": ok}


@fno_router.post("/fno/events/acknowledge-all")
async def acknowledge_all_popup_events(user=Depends(get_owner_user)):
    """Acknowledge all pending popup events."""
    import server as _srv
    from services.sticky_card_engine import acknowledge_all_events
    count = await acknowledge_all_events(_srv.db)
    return {"acknowledged_count": count}


@fno_router.get("/fno/sticky-cards")
async def get_sticky_cards(
    include_terminal: bool = Query(default=False),
    user=Depends(get_owner_user),
):
    """Get all sticky cards (active only by default)."""
    import server as _srv
    from services.sticky_card_engine import get_all_cards
    return await get_all_cards(_srv.db, include_terminal=include_terminal)


@fno_router.post("/fno/sticky-cards/{signal_id}/cancel")
async def cancel_sticky_card(
    signal_id: str,
    user=Depends(get_owner_user),
):
    """Cancel a sticky card (user-initiated)."""
    import server as _srv
    from services.sticky_card_engine import cancel_card
    ok = await cancel_card(_srv.db, signal_id)
    if not ok:
        raise HTTPException(404, "Card not found or already in terminal state")
    return {"cancelled": True, "signal_id": signal_id}


@fno_router.post("/fno/sticky-cards/refresh")
async def trigger_sticky_card_refresh(user=Depends(get_owner_user)):
    """Manually trigger a refresh cycle for all active sticky cards."""
    import server as _srv
    from services.sticky_card_engine import refresh_sticky_cards
    result = await refresh_sticky_cards(_srv.db)
    return result


# ---------------------------------------------------------------------------
# Signal History & Performance Tracking
# ---------------------------------------------------------------------------

@fno_router.get("/fno/signal-history")
async def get_signal_history_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    user=Depends(get_owner_user),
):
    """Get paginated signal history (archived terminal cards with outcomes)."""
    import server as _srv
    from services.sticky_card_engine import get_signal_history
    history = await get_signal_history(_srv.db, limit=limit, skip=skip)
    return {"history": history, "count": len(history)}


@fno_router.get("/fno/performance-stats")
async def get_performance_stats_endpoint(user=Depends(get_owner_user)):
    """Get aggregated performance statistics from signal history."""
    import server as _srv
    from services.sticky_card_engine import get_performance_stats
    stats = await get_performance_stats(_srv.db)
    return stats


@fno_router.get("/fno/generation-timings")
async def get_generation_timings(user=Depends(get_owner_user)):
    """Get last F&O and Multibagger generation phase timings for performance monitoring."""
    import services.app_state as _app_state
    return {
        "fno": _app_state.LAST_FNO_PERF or {"message": "No F&O generation run yet"},
        "multibagger": _app_state.LAST_MB_PERF or {"message": "No Multibagger generation run yet"},
    }


@fno_router.get("/fno/signal-log")
async def get_signal_log_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    user=Depends(get_owner_user),
):
    """Get paginated signal generation log (all generated signals)."""
    import server as _srv
    from services.sticky_card_engine import get_signal_log
    log = await get_signal_log(_srv.db, limit=limit, skip=skip)
    return {"log": log, "count": len(log)}



# ---------------------------------------------------------------------------
# BBE (Budget Entry) Alerts: Real-time LTP monitoring against BBE zones
# ---------------------------------------------------------------------------

@fno_router.get("/fno/bbe-alerts")
async def get_bbe_alerts(user=Depends(get_current_user)):
    """
    Fetch recent signals with budget_entry_alert=True, get live LTP,
    and return which signals have entered the BBE zone (LTP <= BBE).
    This is a 'NOW BUY' detection endpoint.
    """
    import server as _srv
    from datetime import datetime, timedelta, timezone as tz

    # Get signals from last 24h that have BBE set
    cutoff = datetime.now(tz.utc) - timedelta(hours=24)
    cursor = _srv.db.fno_signal_log.find(
        {
            "generated_at": {"$gte": cutoff},
            "best_budget_entry": {"$ne": None},
            "best_budget_entry": {"$gt": 0},
        },
        {"_id": 0},
    ).sort("generated_at", -1).limit(20)
    signals = await cursor.to_list(length=20)

    if not signals:
        return {"alerts": [], "count": 0, "checked_at": _srv._utc_now_iso()}

    # Deduplicate by option_symbol (keep latest)
    seen = {}
    for s in signals:
        sym = s.get("option_symbol", "")
        if sym and sym not in seen:
            seen[sym] = s
    unique_signals = list(seen.values())

    # Batch-fetch live LTP from Kite
    alerts = []
    try:
        from services.kite_client import fetch_kite_batch_option_quotes
        option_symbols = [s['option_symbol'] for s in unique_signals if s.get("option_symbol")]
        if option_symbols:
            quotes = await fetch_kite_batch_option_quotes(option_symbols)
            for s in unique_signals:
                sym = s.get("option_symbol", "")
                quote = quotes.get(sym, {})
                ltp = quote.get("ltp", 0)
                bbe = s.get("best_budget_entry", 0)
                entry = s.get("entry_price", 0)

                if ltp <= 0 or bbe <= 0:
                    continue

                in_bbe_zone = ltp <= bbe
                pct_from_bbe = round(((ltp - bbe) / bbe) * 100, 2) if bbe > 0 else 0

                alerts.append({
                    "option_symbol": s.get("option_symbol"),
                    "symbol": s.get("symbol"),
                    "direction": s.get("direction"),
                    "entry_price": entry,
                    "best_budget_entry": bbe,
                    "stop_loss": s.get("stop_loss"),
                    "target1": s.get("target1"),
                    "confluence_score": s.get("confluence_score"),
                    "signal_quality": s.get("signal_quality"),
                    "live_ltp": ltp,
                    "in_bbe_zone": in_bbe_zone,
                    "pct_from_bbe": pct_from_bbe,
                    "now_buy": in_bbe_zone,
                    "generated_at": s.get("generated_at").isoformat() if s.get("generated_at") else None,
                })
    except Exception as exc:
        logger.warning("BBE alert LTP fetch failed: %s", exc)

    # Sort: NOW BUY signals first, then by proximity to BBE
    alerts.sort(key=lambda a: (not a["now_buy"], a["pct_from_bbe"]))

    return {
        "alerts": alerts,
        "count": len(alerts),
        "now_buy_count": sum(1 for a in alerts if a["now_buy"]),
        "checked_at": _srv._utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# IV Analytics: IV Cone + IV Term Structure
# ---------------------------------------------------------------------------

@fno_router.get("/fno/iv-cone/{symbol}")
async def get_iv_cone(
    symbol: str,
    lookback_days: int = Query(default=365, ge=30, le=730),
    user=Depends(get_owner_user),
):
    """Get IV Cone data with percentile bands for a symbol."""
    import server as _srv
    from services.iv_analytics import compute_iv_cone
    return await compute_iv_cone(_srv.db, symbol.upper(), lookback_days)


@fno_router.get("/fno/iv-term-structure/{symbol}")
async def get_iv_term_structure_endpoint(
    symbol: str,
    user=Depends(get_owner_user),
):
    """Get latest IV term structure for a symbol."""
    import server as _srv
    from services.iv_analytics import get_iv_term_structure
    return await get_iv_term_structure(_srv.db, symbol.upper())


@fno_router.post("/fno/iv-collect-now")
async def collect_iv_now(user=Depends(get_owner_user)):
    """Manual one-shot IV snapshot collection for NIFTY and BANKNIFTY.
    Captures current ATM IV without requiring full signal generation."""
    import server as _srv
    from services.kite_client import fetch_kite_batch_quotes, fetch_kite_batch_option_quotes
    from services.iv_history import capture_atm_iv
    from services.iv_analytics import capture_iv_term_structure
    import services.app_state as _state

    results = {}
    for symbol in ["NIFTY", "BANKNIFTY"]:
        try:
            step = 50 if symbol == "NIFTY" else 100
            # Get spot
            idx_quotes = await fetch_kite_batch_quotes(
                ["NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"], exchange="NSE"
            )
            spot = 0
            for v in idx_quotes.values():
                spot = v.get("ltp", 0)
            if spot <= 0:
                results[symbol] = {"captured": False, "reason": "spot_unavailable"}
                continue

            # Find nearest expiry
            pipeline = [
                {"$match": {"underlying": symbol}},
                {"$group": {"_id": "$expiry"}},
                {"$sort": {"_id": 1}},
                {"$limit": 3},
            ]
            expiry_docs = await _state.db.kite_option_master.aggregate(pipeline).to_list(3)
            if not expiry_docs:
                results[symbol] = {"captured": False, "reason": "no_option_master"}
                continue

            nearest_expiry = expiry_docs[0]["_id"]
            atm_strike = round(spot / step) * step

            # Fetch ATM CE and PE
            option_rows = await _state.db.kite_option_master.find(
                {"underlying": symbol, "expiry": nearest_expiry, "strike": float(atm_strike)},
                {"_id": 0, "tradingsymbol": 1, "option_type": 1},
            ).to_list(10)

            if option_rows:
                ts_list = [r["tradingsymbol"] for r in option_rows]
                quotes = await fetch_kite_batch_option_quotes(ts_list)
                atm_iv = None
                for ts, q in quotes.items():
                    iv = q.get("iv")
                    if iv and iv > 0:
                        atm_iv = iv / 100 if iv > 1 else iv  # normalize
                        break

                if atm_iv and atm_iv > 0:
                    await capture_atm_iv(_state.db, symbol, atm_iv)

                    # Also capture term structure for all available expiries
                    expiry_iv_map = {}
                    for exp_doc in expiry_docs:
                        exp = exp_doc["_id"]
                        exp_atm_rows = await _state.db.kite_option_master.find(
                            {"underlying": symbol, "expiry": exp, "strike": float(atm_strike)},
                            {"_id": 0, "tradingsymbol": 1},
                        ).to_list(5)
                        if exp_atm_rows:
                            exp_ts = [r["tradingsymbol"] for r in exp_atm_rows]
                            exp_quotes = await fetch_kite_batch_option_quotes(exp_ts)
                            for q in exp_quotes.values():
                                if q.get("iv") and q["iv"] > 0:
                                    expiry_iv_map[exp] = q["iv"] / 100 if q["iv"] > 1 else q["iv"]
                                    break

                    if expiry_iv_map:
                        await capture_iv_term_structure(_state.db, symbol, expiry_iv_map)

                    results[symbol] = {"captured": True, "atm_iv": round(atm_iv * 100, 2), "spot": spot, "strike": atm_strike, "expiry": nearest_expiry, "term_expiries": len(expiry_iv_map)}
                else:
                    results[symbol] = {"captured": False, "reason": "no_iv_in_quotes"}
            else:
                results[symbol] = {"captured": False, "reason": "no_atm_options"}
        except Exception as exc:
            logger.warning("IV collect-now failed for %s: %s", symbol, exc)
            results[symbol] = {"captured": False, "reason": str(exc)[:100]}

    return {"results": results}


# ---------------------------------------------------------------------------
# Multi-timeframe Analysis
# ---------------------------------------------------------------------------

@fno_router.get("/fno/multi-timeframe/{symbol}")
async def get_multi_timeframe(
    symbol: str,
    user=Depends(get_owner_user),
):
    """Get detailed multi-timeframe technical analysis for a symbol."""
    import server as _srv
    from services.multiframe_analysis import compute_detailed_multiframe

    # Fetch OHLCV from cache or Kite
    hist_df = await _srv._get_hist_ohlcv(symbol.upper(), period="1y")
    if hist_df is None or hist_df.empty:
        return {
            "symbol": symbol.upper(),
            "data_available": False,
            "frames": {},
            "alignment": "NO_DATA",
            "message": "No historical OHLCV data available for this symbol.",
        }

    return compute_detailed_multiframe(hist_df, symbol.upper())
