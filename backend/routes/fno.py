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

        # ── Phase 1+2: NIFTY + BANKNIFTY in parallel (with inline keepalive) ──
        _t0 = _time.monotonic()
        yield _ndjson_line({"type": "progress", "phase": "nifty", "message": "Computing NIFTY & BANKNIFTY projections in parallel..."})
        nifty_task = asyncio.ensure_future(_build_index_phase("NIFTY", refreshed_at, _srv))
        bn_task = asyncio.ensure_future(_build_index_phase("BANKNIFTY", refreshed_at, _srv))

        while not nifty_task.done() or not bn_task.done():
            pending = []
            if not nifty_task.done():
                pending.append(nifty_task)
            if not bn_task.done():
                pending.append(bn_task)
            try:
                await asyncio.wait(pending, timeout=5, return_when=asyncio.FIRST_COMPLETED)
            except Exception:
                pass
            if not nifty_task.done() or not bn_task.done():
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

        # ── Post-generation side effects (extracted for readability) ───
        await _post_generation_effects(
            _perf, _time, _t0, _gen_start, refreshed_at,
            signals, stock_signals, custom_signal,
            nifty_projection, banknifty_projection,
            current_user, _srv,
        )

    return StreamingResponse(_stream_generate(), media_type="application/x-ndjson")


async def _post_generation_effects(
    _perf, _time, _t0, _gen_start, refreshed_at,
    signals, stock_signals, custom_signal,
    nifty_projection, banknifty_projection,
    current_user, _srv,
):
    """Post-generation: perf tracking, signal logging, journal, IV capture."""
    await _log_perf_metrics(_perf, _time, _t0, _gen_start, refreshed_at, signals)
    all_sigs = [*signals, *stock_signals] + ([custom_signal] if custom_signal else [])
    await _log_signals_to_db(_srv, all_sigs)
    await _log_journal_entries(_srv, current_user, all_sigs, refreshed_at)
    await _capture_iv_snapshots(_srv, nifty_projection, banknifty_projection)


async def _log_perf_metrics(_perf, _time, _t0, _gen_start, refreshed_at, signals):
    """Record generation performance metrics."""
    import services.app_state as _app_state
    _perf["assembly_ms"] = round((_time.monotonic() - _t0) * 1000)
    _perf["total_ms"] = round((_time.monotonic() - _gen_start) * 1000)
    _perf["ts"] = refreshed_at
    _perf["signal_count"] = len(signals)
    _app_state.LAST_FNO_PERF = _perf
    logger.info("FNO generation perf: %s", _perf)
    try:
        await _app_state.db.generation_perf_history.insert_one({"type": "fno", **_perf})
    except Exception as exc:
        logger.debug("Perf history insert failed: %s", exc)


async def _log_signals_to_db(_srv, all_sigs):
    """Log generated signals to the signal log collection."""
    try:
        from services.sticky_card_engine import log_generated_signal
        for sig in all_sigs:
            sig_dict = json.loads(sig.model_dump_json()) if hasattr(sig, 'model_dump_json') else sig.__dict__
            await log_generated_signal(_srv.db, sig_dict)
    except Exception as exc:
        logger.debug("Signal log failed: %s", exc)


async def _log_journal_entries(_srv, current_user, all_sigs, refreshed_at):
    """Auto-log signal generation events to the trading journal."""
    try:
        from routes.journal import log_journal_entry
        user_key = current_user.get("user_key", "")
        for sig in all_sigs:
            sd = json.loads(sig.model_dump_json()) if hasattr(sig, 'model_dump_json') else {}
            await log_journal_entry(user_key, {
                "event_type": "signal_generated",
                "symbol": sd.get("tradingsymbol") or sd.get("underlying", ""),
                "direction": sd.get("direction"),
                "entry_price": sd.get("premium_ltp"),
                "confluence_score": sd.get("confluence_score"),
                "signal_quality": sd.get("signal_quality"),
                "targets": {"t1": sd.get("target1"), "t2": sd.get("target2")},
                "stop_loss": sd.get("stop_loss"),
                "notes": f"Generated at {refreshed_at}",
            })
    except Exception as exc:
        logger.debug("Journal log failed: %s", exc)


async def _capture_iv_snapshots(_srv, nifty_projection, banknifty_projection):
    """Capture IV term structure snapshots from projections."""
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
    except Exception as exc:
        logger.debug("IV capture failed: %s", exc)


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
    except Exception:
        latest_option_ltp = None

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
        "alert": "LIVE_LTP_UNAVAILABLE" if latest_option_ltp is None else None,
        "latest_option_ltp": round(float(latest_option_ltp), 2) if latest_option_ltp is not None else None,
        **_srv._compute_initial_option_targets(float(payload.buy_price)),
        "stop_loss": _srv._compute_initial_option_sl(float(payload.buy_price)),
        "projected_exit_price": None,
        "best_exit_price": None,
        "best_exit_days": None,
        "recovery_potential": None,
        "sold_price": None,
        "realized_pnl": None,
        "minutes_to_expiry": minutes_to_expiry,
        "revised_exit_plan": "Hold with trailing stop once target1 hits" if latest_option_ltp is not None else "Position saved; live option price unavailable. Monitoring resumes when a confirmed Kite quote is available.",
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

    cutoff = datetime.now(tz.utc) - timedelta(hours=24)
    cursor = _srv.db.fno_signal_log.find(
        {
            "generated_at": {"$gte": cutoff},
            "best_budget_entry": {"$gt": 0},
        },
        {"_id": 0},
    ).sort("generated_at", -1).limit(20)
    signals = await cursor.to_list(length=20)

    if not signals:
        return {"alerts": [], "count": 0, "checked_at": _srv._utc_now_iso()}

    seen = {}
    for s in signals:
        sym = s.get("option_symbol", "")
        if sym and sym not in seen:
            seen[sym] = s
    unique_signals = list(seen.values())

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

    alerts.sort(key=lambda a: (not a["now_buy"], a["pct_from_bbe"]))

    return {
        "alerts": alerts,
        "count": len(alerts),
        "now_buy_count": sum(1 for a in alerts if a["now_buy"]),
        "checked_at": _srv._utc_now_iso(),
    }


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

