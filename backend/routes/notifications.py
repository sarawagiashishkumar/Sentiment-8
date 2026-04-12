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

    # Analytics summary
    total = len(items)
    unread = len([n for n in items if not n.get("read")])
    by_cat = {}
    for n in items:
        cat = n.get("category", "info")
        by_cat[cat] = by_cat.get(cat, 0) + 1

    return {
        "notifications": items,
        "analytics": {
            "total": total,
            "unread": unread,
            "by_category": by_cat,
        },
    }


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
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).timestamp()}},
    )
    # Track acknowledgement for analytics
    if result.modified_count > 0:
        await _state.db.notification_analytics.insert_one({
            "user_key": user_key,
            "action": "read_all",
            "count": result.modified_count,
            "ts": datetime.now(timezone.utc).timestamp(),
        })
    return {"modified": result.modified_count}


@notification_router.delete("/notifications")
async def clear_all_notifications(current_user: dict = Depends(get_current_user)):
    """Clear all notifications for current user."""
    user_key = current_user.get("user_key", "")
    result = await _state.db.user_notifications.delete_many({"user_key": user_key})
    return {"deleted": result.deleted_count}


@notification_router.get("/notifications/analytics")
async def get_notification_analytics(current_user: dict = Depends(get_current_user)):
    """Get notification analytics — alert frequency and response latency."""
    user_key = current_user.get("user_key", "")

    # Alert frequency (last 7 days)
    cutoff_7d = datetime.now(timezone.utc).timestamp() - 7 * 86400
    pipeline = [
        {"$match": {"user_key": user_key, "ts": {"$gte": cutoff_7d}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]
    freq_cursor = _state.db.user_notifications.aggregate(pipeline)
    freq_data = {doc["_id"]: doc["count"] async for doc in freq_cursor}

    # Response latency (time between alert creation and read)
    read_pipeline = [
        {"$match": {"user_key": user_key, "read": True, "read_at": {"$exists": True}, "ts": {"$gte": cutoff_7d}}},
        {"$project": {"latency": {"$subtract": ["$read_at", "$ts"]}}},
        {"$group": {"_id": None, "avg_latency": {"$avg": "$latency"}, "count": {"$sum": 1}}},
    ]
    latency_cursor = _state.db.user_notifications.aggregate(read_pipeline)
    latency_docs = await latency_cursor.to_list(1)
    avg_latency_secs = round(latency_docs[0]["avg_latency"], 1) if latency_docs and latency_docs[0].get("avg_latency") else None

    # Total alerts last 24h
    cutoff_24h = datetime.now(timezone.utc).timestamp() - 86400
    total_24h = await _state.db.user_notifications.count_documents({"user_key": user_key, "ts": {"$gte": cutoff_24h}})

    return {
        "frequency_7d": freq_data,
        "total_24h": total_24h,
        "avg_response_latency_secs": avg_latency_secs,
        "read_count_7d": latency_docs[0]["count"] if latency_docs else 0,
    }
