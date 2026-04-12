"""
Watchlist — User-defined stock watchlist with price alerts.
Background monitor checks during market hours and pushes to notification center.
"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

watchlist_router = APIRouter()


class WatchlistItem(BaseModel):
    symbol: str
    alert_above: float | None = None
    alert_below: float | None = None
    notes: str | None = None


@watchlist_router.get("/watchlist")
async def get_watchlist(current_user: dict = Depends(get_current_user)):
    """Get user's watchlist."""
    user_key = current_user.get("user_key", "")
    items = await _state.db.user_watchlist.find(
        {"user_key": user_key}, {"_id": 0}
    ).sort("added_at", -1).to_list(50)
    return {"items": items}


@watchlist_router.post("/watchlist")
async def add_to_watchlist(item: WatchlistItem, current_user: dict = Depends(get_current_user)):
    """Add symbol to watchlist."""
    user_key = current_user.get("user_key", "")
    symbol = item.symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "Symbol required")

    existing = await _state.db.user_watchlist.find_one(
        {"user_key": user_key, "symbol": symbol}, {"_id": 0}
    )
    if existing:
        await _state.db.user_watchlist.update_one(
            {"user_key": user_key, "symbol": symbol},
            {"$set": {"alert_above": item.alert_above, "alert_below": item.alert_below, "notes": item.notes}},
        )
        return {"updated": True, "symbol": symbol}

    await _state.db.user_watchlist.insert_one({
        "user_key": user_key, "symbol": symbol,
        "alert_above": item.alert_above, "alert_below": item.alert_below,
        "notes": item.notes,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "last_triggered": None,
    })
    return {"added": True, "symbol": symbol}


@watchlist_router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str, current_user: dict = Depends(get_current_user)):
    """Remove symbol from watchlist."""
    user_key = current_user.get("user_key", "")
    result = await _state.db.user_watchlist.delete_one({"user_key": user_key, "symbol": symbol.upper()})
    return {"deleted": result.deleted_count > 0}


async def run_watchlist_monitor():
    """Background task: check watchlist alerts every 60s during market hours."""
    while True:
        await asyncio.sleep(60)
        try:
            _now = datetime.now(_state.IST)
            if _now.weekday() >= 5:
                continue
            _mins = _now.hour * 60 + _now.minute
            if _mins < 555 or _mins > 930:
                continue

            # Get all watchlist items with alerts
            all_items = await _state.db.user_watchlist.find(
                {"$or": [{"alert_above": {"$ne": None}}, {"alert_below": {"$ne": None}}]},
                {"_id": 0},
            ).to_list(500)

            if not all_items:
                continue

            # Batch fetch quotes
            symbols = list(set(item["symbol"] for item in all_items))
            from services.kite_client import fetch_kite_batch_quotes
            quotes = await fetch_kite_batch_quotes(symbols)

            now_ts = datetime.now(timezone.utc)
            ALERT_COOLDOWN_SECS = 3600  # 1-hour cooldown between re-triggers

            for item in all_items:
                q = quotes.get(item["symbol"], {})
                ltp = q.get("ltp", 0)
                if ltp <= 0:
                    continue

                # Skip if recently triggered (cooldown)
                last_trig = item.get("last_triggered")
                if last_trig:
                    try:
                        last_dt = datetime.fromisoformat(last_trig.replace("Z", "+00:00"))
                        if (now_ts - last_dt).total_seconds() < ALERT_COOLDOWN_SECS:
                            continue
                    except (ValueError, TypeError):
                        pass

                triggered = False
                msg = ""
                if item.get("alert_above") and ltp >= item["alert_above"]:
                    triggered = True
                    msg = f"{item['symbol']} crossed above {item['alert_above']} — LTP: {ltp}"
                elif item.get("alert_below") and ltp <= item["alert_below"]:
                    triggered = True
                    msg = f"{item['symbol']} dropped below {item['alert_below']} — LTP: {ltp}"

                if triggered:
                    # Push to notification collection
                    await _state.db.user_notifications.insert_one({
                        "user_key": item["user_key"],
                        "category": "warning",
                        "title": f"Price Alert: {item['symbol']}",
                        "message": msg,
                        "symbol": item["symbol"],
                        "ts": now_ts.timestamp(),
                        "read": False,
                    })
                    # Update last_triggered with cooldown tracking
                    await _state.db.user_watchlist.update_one(
                        {"user_key": item["user_key"], "symbol": item["symbol"]},
                        {"$set": {"last_triggered": now_ts.isoformat()}},
                    )
                    logger.info("Watchlist alert triggered: %s", msg)
        except Exception as exc:
            logger.debug("Watchlist monitor cycle failed: %s", exc)
