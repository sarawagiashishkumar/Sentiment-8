"""
FNO Sticky Cards & Popup Event route handlers.

Card management, signal history, performance stats, and generation timings
extracted from fno.py.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_current_user, get_owner_user

logger = logging.getLogger(__name__)

fno_cards_router = APIRouter()


# ---------------------------------------------------------------------------
# Popup Events
# ---------------------------------------------------------------------------

@fno_cards_router.get("/fno/events")
async def get_popup_events(
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_owner_user),
):
    """Get unacknowledged popup events (most recent first)."""
    import server as _srv
    from services.sticky_card_engine import get_unacknowledged_events
    return await get_unacknowledged_events(_srv.db, limit=limit)


@fno_cards_router.post("/events/acknowledge")
async def acknowledge_popup_event(
    event_id: str = Query(...),
    user=Depends(get_owner_user),
):
    """Acknowledge (dismiss) a single popup event."""
    import server as _srv
    from services.sticky_card_engine import acknowledge_event
    ok = await acknowledge_event(_srv.db, event_id)
    return {"acknowledged": ok}


@fno_cards_router.post("/fno/events/acknowledge-all")
async def acknowledge_all_popup_events(user=Depends(get_owner_user)):
    """Acknowledge all pending popup events."""
    import server as _srv
    from services.sticky_card_engine import acknowledge_all_events
    count = await acknowledge_all_events(_srv.db)
    return {"acknowledged_count": count}


# ---------------------------------------------------------------------------
# Sticky Cards
# ---------------------------------------------------------------------------

@fno_cards_router.get("/fno/sticky-cards")
async def get_sticky_cards(
    include_terminal: bool = Query(default=False),
    user=Depends(get_owner_user),
):
    """Get all sticky cards (active only by default)."""
    import server as _srv
    from services.sticky_card_engine import get_all_cards
    return await get_all_cards(_srv.db, include_terminal=include_terminal)


@fno_cards_router.post("/fno/sticky-cards/{signal_id}/cancel")
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


@fno_cards_router.post("/fno/sticky-cards/refresh")
async def trigger_sticky_card_refresh(user=Depends(get_owner_user)):
    """Manually trigger a refresh cycle for all active sticky cards."""
    import server as _srv
    from services.sticky_card_engine import refresh_sticky_cards
    result = await refresh_sticky_cards(_srv.db)
    return result


# ---------------------------------------------------------------------------
# Signal History & Performance Tracking
# ---------------------------------------------------------------------------

@fno_cards_router.get("/fno/signal-history")
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


@fno_cards_router.get("/fno/performance-stats")
async def get_performance_stats_endpoint(user=Depends(get_owner_user)):
    """Get aggregated performance statistics from signal history."""
    import server as _srv
    from services.sticky_card_engine import get_performance_stats
    stats = await get_performance_stats(_srv.db)
    return stats


@fno_cards_router.get("/fno/generation-timings")
async def get_generation_timings(user=Depends(get_owner_user)):
    """Get last F&O and Multibagger generation phase timings + history."""
    import services.app_state as _app_state
    history = []
    try:
        cursor = _app_state.db.generation_perf_history.find(
            {}, {"_id": 0}
        ).sort("ts", -1).limit(50)
        history = await cursor.to_list(50)
    except Exception:
        pass
    return {
        "fno": _app_state.LAST_FNO_PERF or {"message": "No F&O generation run yet"},
        "multibagger": _app_state.LAST_MB_PERF or {"message": "No Multibagger generation run yet"},
        "history": history,
    }


@fno_cards_router.get("/fno/signal-log")
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
