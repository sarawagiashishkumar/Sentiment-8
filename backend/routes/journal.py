"""
Trading Journal — Automated audit trail of signals, entries, exits, and P&L.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user, get_owner_user

logger = logging.getLogger(__name__)

journal_router = APIRouter()


class JournalEntry(BaseModel):
    event_type: str  # signal_generated | position_opened | position_closed | position_updated
    symbol: str
    direction: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: int | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    holding_duration_mins: int | None = None
    confluence_score: float | None = None
    signal_quality: str | None = None
    targets: dict | None = None
    stop_loss: float | None = None
    notes: str | None = None
    meta: dict | None = None


async def log_journal_entry(user_key: str, entry: dict):
    """Helper to auto-log journal entries from signal generation or position events."""
    doc = {
        "user_key": user_key,
        "ts": datetime.now(timezone.utc).isoformat(),
        "ts_epoch": datetime.now(timezone.utc).timestamp(),
        **entry,
    }
    try:
        await _state.db.trading_journal.insert_one(doc)
    except Exception as exc:
        logger.warning("Journal log failed: %s", exc)


@journal_router.get("/journal")
async def get_journal(
    limit: int = Query(default=50, le=200),
    event_type: str = Query(default=""),
    symbol: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    """Get trading journal entries for current user."""
    user_key = current_user.get("user_key", "")
    query = {"user_key": user_key}
    if event_type:
        query["event_type"] = event_type
    if symbol:
        query["symbol"] = {"$regex": symbol.upper(), "$options": "i"}

    cursor = _state.db.trading_journal.find(
        query, {"_id": 0}
    ).sort("ts_epoch", -1).limit(limit)
    entries = await cursor.to_list(limit)

    # Compute summary stats
    closed = [e for e in entries if e.get("event_type") == "position_closed"]
    total_pnl = sum(e.get("pnl", 0) for e in closed)
    wins = len([e for e in closed if (e.get("pnl") or 0) > 0])
    losses = len([e for e in closed if (e.get("pnl") or 0) < 0])
    win_rate = round(wins / max(wins + losses, 1) * 100, 1)
    avg_hold = round(sum(e.get("holding_duration_mins", 0) for e in closed) / max(len(closed), 1), 0)

    return {
        "entries": entries,
        "summary": {
            "total_entries": len(entries),
            "closed_trades": len(closed),
            "total_pnl": round(total_pnl, 2),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_holding_mins": avg_hold,
        },
    }


@journal_router.post("/journal")
async def add_journal_entry(
    entry: JournalEntry,
    current_user: dict = Depends(get_current_user),
):
    """Manually add a journal entry."""
    user_key = current_user.get("user_key", "")
    doc = entry.model_dump(exclude_none=True)
    await log_journal_entry(user_key, doc)
    return {"logged": True}


@journal_router.delete("/journal")
async def clear_journal(current_user: dict = Depends(get_owner_user)):
    """Clear all journal entries (owner only)."""
    user_key = current_user.get("user_key", "")
    result = await _state.db.trading_journal.delete_many({"user_key": user_key})
    return {"deleted": result.deleted_count}


async def ensure_journal_indexes(database):
    """Create indexes for trading journal collection."""
    try:
        await database.trading_journal.create_index([("user_key", 1), ("ts_epoch", -1)])
        await database.trading_journal.create_index([("user_key", 1), ("event_type", 1)])
        await database.trading_journal.create_index([("user_key", 1), ("symbol", 1)])
        logger.info("Trading journal indexes ensured")
    except Exception as exc:
        logger.warning("Trading journal index creation failed: %s", exc)
