"""
CRM Module — Two-way messaging between Admin and Users.
Admin can broadcast or target messages; users see them as dismissible notifications.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

crm_router = APIRouter()


class CrmMessageSend(BaseModel):
    to_user_key: str | None = None  # None = broadcast to all
    subject: str
    body: str
    priority: str = "normal"  # "normal", "high", "critical"


class CrmReply(BaseModel):
    subject: str = ""
    body: str


# ── Admin CRM Endpoints ──────────────────────────────────────────────────────

@crm_router.get("/admin/crm/inbox")
async def admin_crm_inbox(
    status: str = Query(default="all"),
    admin_user: dict = Depends(get_current_user),
):
    """Admin inbox — messages from users (support requests, fraud alerts, reactivation)."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    query = {"to": "admin"}
    if status == "unread":
        query["status"] = "unread"
    elif status == "read":
        query["status"] = "read"

    cursor = _state.db.crm_messages.find(
        query, {"_id": 0}
    ).sort("ts_epoch", -1).limit(100)
    messages = await cursor.to_list(100)

    unread = await _state.db.crm_messages.count_documents({"to": "admin", "status": "unread"})
    return {"messages": messages, "count": len(messages), "unread": unread}


@crm_router.patch("/admin/crm/read/{message_id}")
async def admin_mark_read(
    message_id: str,
    admin_user: dict = Depends(get_current_user),
):
    """Mark a CRM message as read."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    result = await _state.db.crm_messages.update_one(
        {"message_id": message_id, "to": "admin"},
        {"$set": {"status": "read", "read_at": datetime.now(timezone.utc).isoformat(), "read_by": admin_user.get("username")}},
    )
    return {"updated": result.modified_count > 0}


@crm_router.post("/admin/crm/send")
async def admin_send_message(
    msg: CrmMessageSend,
    admin_user: dict = Depends(get_current_user),
):
    """Admin sends a message to a specific user or broadcasts to all users."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    if not msg.subject.strip() or not msg.body.strip():
        raise HTTPException(400, "Subject and body required")

    now = datetime.now(timezone.utc)
    admin_username = admin_user.get("username", "Admin")

    if msg.to_user_key:
        # Target single user
        target = await _state.db.app_users.find_one({"user_key": msg.to_user_key}, {"_id": 0, "username": 1})
        if not target:
            raise HTTPException(404, "Target user not found")

        doc = {
            "message_id": str(uuid.uuid4()),
            "from_user_key": admin_user["user_key"],
            "from_username": admin_username,
            "to_user_key": msg.to_user_key,
            "to": "user",
            "subject": msg.subject.strip(),
            "body": msg.body.strip(),
            "priority": msg.priority,
            "type": "admin_message",
            "status": "unread",
            "dismissed": False,
            "ts": now.isoformat(),
            "ts_epoch": now.timestamp(),
        }
        await _state.db.crm_messages.insert_one(doc)

        # Also push as user notification
        await _state.db.user_notifications.insert_one({
            "user_key": msg.to_user_key,
            "category": "info" if msg.priority == "normal" else "critical",
            "title": f"Admin: {msg.subject.strip()}",
            "message": msg.body.strip()[:200],
            "ts": now.timestamp(),
            "read": False,
        })

        return {"sent": True, "to": target.get("username"), "message_id": doc["message_id"]}
    else:
        # Broadcast to all non-admin users
        users = await _state.db.app_users.find(
            {"role": {"$nin": ["owner", "sub_admin"]}},
            {"_id": 0, "user_key": 1, "username": 1},
        ).to_list(1000)

        broadcast_id = str(uuid.uuid4())
        docs = []
        notif_docs = []
        for user in users:
            msg_id = str(uuid.uuid4())
            docs.append({
                "message_id": msg_id,
                "broadcast_id": broadcast_id,
                "from_user_key": admin_user["user_key"],
                "from_username": admin_username,
                "to_user_key": user["user_key"],
                "to": "user",
                "subject": msg.subject.strip(),
                "body": msg.body.strip(),
                "priority": msg.priority,
                "type": "broadcast",
                "status": "unread",
                "dismissed": False,
                "ts": now.isoformat(),
                "ts_epoch": now.timestamp(),
            })
            notif_docs.append({
                "user_key": user["user_key"],
                "category": "info" if msg.priority == "normal" else "critical",
                "title": f"Announcement: {msg.subject.strip()}",
                "message": msg.body.strip()[:200],
                "ts": now.timestamp(),
                "read": False,
            })

        if docs:
            await _state.db.crm_messages.insert_many(docs)
        if notif_docs:
            await _state.db.user_notifications.insert_many(notif_docs)

        return {"sent": True, "broadcast": True, "recipients": len(docs), "broadcast_id": broadcast_id}


@crm_router.get("/admin/crm/sent")
async def admin_sent_messages(
    admin_user: dict = Depends(get_current_user),
):
    """List messages sent by admin."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    cursor = _state.db.crm_messages.find(
        {"to": "user", "from_user_key": admin_user["user_key"]},
        {"_id": 0},
    ).sort("ts_epoch", -1).limit(50)
    messages = await cursor.to_list(50)
    return {"messages": messages, "count": len(messages)}


# ── User CRM Endpoints ────────────────────────────────────────────────────────

@crm_router.get("/crm/inbox")
async def user_crm_inbox(current_user: dict = Depends(get_current_user)):
    """User inbox — messages from admin (announcements, targeted messages)."""
    user_key = current_user.get("user_key", "")
    cursor = _state.db.crm_messages.find(
        {"to_user_key": user_key, "to": "user", "dismissed": {"$ne": True}},
        {"_id": 0},
    ).sort("ts_epoch", -1).limit(50)
    messages = await cursor.to_list(50)

    unread = sum(1 for m in messages if m.get("status") == "unread")
    return {"messages": messages, "count": len(messages), "unread": unread}


@crm_router.patch("/crm/read/{message_id}")
async def user_mark_read(
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark a CRM message as read."""
    user_key = current_user.get("user_key", "")
    await _state.db.crm_messages.update_one(
        {"message_id": message_id, "to_user_key": user_key},
        {"$set": {"status": "read", "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@crm_router.patch("/crm/dismiss/{message_id}")
async def user_dismiss_message(
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Dismiss a CRM message (won't show again)."""
    user_key = current_user.get("user_key", "")
    await _state.db.crm_messages.update_one(
        {"message_id": message_id, "to_user_key": user_key},
        {"$set": {"dismissed": True}},
    )
    return {"ok": True}


@crm_router.post("/crm/reply/{message_id}")
async def user_reply_to_message(
    message_id: str,
    reply: CrmReply,
    current_user: dict = Depends(get_current_user),
):
    """User replies to an admin message."""
    user_key = current_user.get("user_key", "")
    username = current_user.get("username", "User")

    original = await _state.db.crm_messages.find_one(
        {"message_id": message_id, "to_user_key": user_key},
        {"_id": 0},
    )
    if not original:
        raise HTTPException(404, "Message not found")

    now = datetime.now(timezone.utc)
    reply_doc = {
        "message_id": str(uuid.uuid4()),
        "reply_to": message_id,
        "from_user_key": user_key,
        "from_username": username,
        "to": "admin",
        "subject": reply.subject or f"Re: {original.get('subject', '')}",
        "body": reply.body,
        "type": "user_reply",
        "status": "unread",
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
    }
    await _state.db.crm_messages.insert_one(reply_doc)
    return {"sent": True, "message_id": reply_doc["message_id"]}


@crm_router.post("/crm/contact")
async def user_contact_support(
    msg: CrmReply,
    current_user: dict = Depends(get_current_user),
):
    """User sends a support message to admin."""
    user_key = current_user.get("user_key", "")
    username = current_user.get("username", "User")

    now = datetime.now(timezone.utc)
    doc = {
        "message_id": str(uuid.uuid4()),
        "from_user_key": user_key,
        "from_username": username,
        "to": "admin",
        "subject": msg.subject or "Support Request",
        "body": msg.body,
        "type": "support_request",
        "status": "unread",
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
    }
    await _state.db.crm_messages.insert_one(doc)
    return {"sent": True, "message_id": doc["message_id"]}
