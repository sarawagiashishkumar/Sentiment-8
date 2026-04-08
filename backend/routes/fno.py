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
        _now_ist = datetime.now(_srv.IST)
        _is_market_hrs = (
            _now_ist.weekday() < 5
            and (_now_ist.hour > 9 or (_now_ist.hour == 9 and _now_ist.minute >= 15))
            and (_now_ist.hour < 15 or (_now_ist.hour == 15 and _now_ist.minute <= 30))
        )
        if not _is_market_hrs:
            yield _ndjson_line({"type": "progress", "phase": "market_hours", "message": "Market closed — using last available data"})

        # ── Phase 1: NIFTY projection ─────────────────────────────────────
        yield _ndjson_line({"type": "progress", "phase": "nifty", "message": "Computing NIFTY projection..."})
        try:
            nifty_projection = await asyncio.wait_for(
                _srv._build_index_projection("NIFTY", refreshed_at), timeout=120
            )
        except Exception:
            nifty_projection = _empty_index_pane("NIFTY", "NIFTY projection temporarily unavailable")
        yield _ndjson_line({"type": "progress", "phase": "nifty_done", "message": f"NIFTY: {len(nifty_projection.assured_signals)} signals"})

        # ── Phase 2: BANKNIFTY projection ─────────────────────────────────
        yield _ndjson_line({"type": "progress", "phase": "banknifty", "message": "Computing BANKNIFTY projection..."})
        try:
            banknifty_projection = await asyncio.wait_for(
                _srv._build_index_projection("BANKNIFTY", refreshed_at), timeout=120
            )
        except Exception:
            banknifty_projection = _empty_index_pane("BANKNIFTY", "BANKNIFTY projection temporarily unavailable")
        yield _ndjson_line({"type": "progress", "phase": "banknifty_done", "message": f"BANKNIFTY: {len(banknifty_projection.assured_signals)} signals"})

        # ── Phase 3: Stock F&O signals ────────────────────────────────────
        yield _ndjson_line({"type": "progress", "phase": "stocks", "message": "Scanning stock F&O universe..."})
        try:
            stock_signals = await asyncio.wait_for(
                _srv._build_stock_fno_signals(refreshed_at), timeout=120
            )
            logger.info("Stock F&O signals generated: %d", len(stock_signals))
        except asyncio.TimeoutError:
            logger.warning("Stock F&O signal generation timed out")
            stock_signals = []
        except Exception as exc:
            logger.error("Stock F&O signal generation failed: %s", exc)
            stock_signals = []
        yield _ndjson_line({"type": "progress", "phase": "stocks_done", "message": f"Stocks: {len(stock_signals)} signals"})

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

        no_signals_alert = None
        all_top_trades = [r for r in top_trades if r.is_potential_trade]
        if not all_top_trades:
            reasons: list[str] = []
            if nifty_projection.rejection_note:
                reasons.append(f"NIFTY: {nifty_projection.rejection_note}")
            if banknifty_projection.rejection_note:
                reasons.append(f"BANKNIFTY: {banknifty_projection.rejection_note}")
            if not stock_signals:
                reasons.append("Individual stock signals: No scripts passed 78% confluence & R:R >= 1.2 filters")
            regime = market_regime.get("regime", "UNKNOWN")
            if regime in ("LOW_VOL_RANGE",):
                reasons.append(f"Market in {regime} — directional setups lacking conviction")
            elif regime in ("CRASH_MODE",):
                reasons.append(f"Market in {regime} — extreme volatility")
            if not market_session.get("is_open"):
                reasons.append(f"Market CLOSED ({market_session.get('status', 'CLOSED')})")
            reason_text = " | ".join(reasons) if reasons else "Current market conditions do not meet minimum 78% confluence threshold"
            no_signals_alert = f"No script signals currently available. Reason: {reason_text}"

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
