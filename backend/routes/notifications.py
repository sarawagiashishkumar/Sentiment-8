"""
Notification persistence routes — store and retrieve user notifications across sessions.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

notification_router = APIRouter()


class NotificationCreate(BaseModel):
    category: str
    title: str
    message: str
    symbol: str | None = None


class NotificationBulk(BaseModel):
    notifications: list[NotificationCreate]


@notification_router.get("/notifications")
async def get_notifications(current_user: dict = Depends(get_current_user)):
    """Get recent notifications for the current user (last 100, within 24h)."""
    user_key = current_user.get("user_key", "")
    cutoff = datetime.now(timezone.utc).timestamp() - 86400
    cursor = _state.db.user_notifications.find(
        {"user_key": user_key, "ts": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("ts", -1).limit(100)
    items = await cursor.to_list(100)
    return {"notifications": items}


@notification_router.post("/notifications")
async def save_notifications(
    payload: NotificationBulk,
    current_user: dict = Depends(get_current_user),
):
    """Save a batch of notifications for the current user."""
    user_key = current_user.get("user_key", "")
    now_ts = datetime.now(timezone.utc).timestamp()
    docs = []
    for n in payload.notifications:
        docs.append({
            "user_key": user_key,
            "category": n.category,
            "title": n.title,
            "message": n.message,
            "symbol": n.symbol,
            "ts": now_ts,
            "read": False,
        })
    if docs:
        await _state.db.user_notifications.insert_many(docs)
    return {"saved": len(docs)}


@notification_router.patch("/notifications/read-all")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    """Mark all notifications as read for current user."""
    user_key = current_user.get("user_key", "")
    result = await _state.db.user_notifications.update_many(
        {"user_key": user_key, "read": False},
        {"$set": {"read": True}},
    )
    return {"modified": result.modified_count}


@notification_router.delete("/notifications")
async def clear_all_notifications(current_user: dict = Depends(get_current_user)):
    """Clear all notifications for current user."""
    user_key = current_user.get("user_key", "")
    result = await _state.db.user_notifications.delete_many({"user_key": user_key})
    return {"deleted": result.deleted_count}
