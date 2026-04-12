"""
Live Help Module — Native WebRTC signaling + text chat + session analysis.
Zero third-party dependencies. Uses FastAPI WebSocket for signaling.
Auto-generates CRM tickets for detected bugs.
"""
import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

livehelp_router = APIRouter()

# ── In-memory state for active help sessions ──────────────────────────────────
_active_sessions: dict[str, dict] = {}  # session_id -> {user_ws, admin_ws, ...}
_user_session_map: dict[str, str] = {}  # user_key -> session_id
_admin_connections: dict[str, WebSocket] = {}  # admin_user_key -> ws

# ── Session Log Tracker ───────────────────────────────────────────────────────
_session_logs: dict[str, list] = defaultdict(list)  # user_key -> [{action, ts, ...}]

# Troubleshooting rules: pattern -> help message
TROUBLESHOOTING_RULES = {
    "kite_disconnect": {
        "pattern": ["kite/status", "connected.*false"],
        "response": "Your market data connection appears to be disconnected. Please ask your administrator to re-authenticate the data source from the Admin panel.",
        "severity": "high",
    },
    "credit_exhausted": {
        "pattern": ["credits.*0", "insufficient"],
        "response": "Your account credits may be exhausted. Contact your administrator to top up credits, or wait for the daily reset if applicable.",
        "severity": "medium",
    },
    "generation_timeout": {
        "pattern": ["timeout", "generation.*fail"],
        "response": "Signal generation timed out. This usually happens during high market volatility. Try again in a few moments — the system will retry with fresh data.",
        "severity": "medium",
    },
    "no_signals": {
        "pattern": ["no.*signal", "no_signals_alert"],
        "response": "No trading signals were found in this scan. This is normal when market conditions don't meet the minimum quality threshold. The system is designed to protect you from low-conviction trades.",
        "severity": "low",
    },
    "data_stale": {
        "pattern": ["stale", "market.*closed"],
        "response": "You're viewing cached data from the last trading session. Live data refreshes automatically when the market opens (Mon-Fri, 9:15 AM - 3:30 PM IST).",
        "severity": "low",
    },
    "upload_failed": {
        "pattern": ["upload.*fail", "portfolio.*error"],
        "response": "File upload encountered an issue. Please ensure your file is a CSV, Excel, or PDF under 10MB. Column headers should include Symbol, Quantity, and Average Price.",
        "severity": "medium",
    },
}


def _analyze_session_log(user_key: str) -> list[dict]:
    """Analyze recent session logs and return troubleshooting suggestions."""
    logs = _session_logs.get(user_key, [])
    if not logs:
        return []

    recent = logs[-20:]  # Last 20 actions
    log_text = " ".join(json.dumps(entry) for entry in recent).lower()

    suggestions = []
    for rule_id, rule in TROUBLESHOOTING_RULES.items():
        matched = any(p in log_text for p in rule["pattern"])
        if matched:
            suggestions.append({
                "rule_id": rule_id,
                "message": rule["response"],
                "severity": rule["severity"],
            })

    return suggestions


async def _auto_generate_ticket(user_key: str, error_info: str):
    """Auto-generate a CRM ticket for detected bugs."""
    user = await _state.db.app_users.find_one({"user_key": user_key}, {"_id": 0, "username": 1})
    username = (user or {}).get("username", "Unknown")

    await _state.db.crm_messages.insert_one({
        "message_id": str(uuid.uuid4()),
        "from_user_key": user_key,
        "from_username": username,
        "to": "admin",
        "subject": f"Auto-Ticket: Bug Detected — {username}",
        "body": f"The Live Help system detected an issue during user session.\n\nUser: {username}\nError: {error_info}\n\nSession logs are available for review.",
        "type": "auto_bug_ticket",
        "status": "unread",
        "ts": datetime.now(timezone.utc).isoformat(),
        "ts_epoch": datetime.now(timezone.utc).timestamp(),
    })
    logger.info("Auto-generated bug ticket for user %s: %s", username, error_info[:100])


# ── REST Endpoints ────────────────────────────────────────────────────────────

@livehelp_router.post("/livehelp/log-action")
async def log_session_action(
    action: dict,
    current_user: dict = Depends(get_current_user),
):
    """Log a user session action for analysis (API calls, errors, navigation)."""
    user_key = current_user.get("user_key", "")
    entry = {
        "action": action.get("action", ""),
        "endpoint": action.get("endpoint", ""),
        "status": action.get("status", ""),
        "error": action.get("error", ""),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _session_logs[user_key].append(entry)
    # Keep only last 100 entries per user
    if len(_session_logs[user_key]) > 100:
        _session_logs[user_key] = _session_logs[user_key][-100:]

    # Auto-detect errors and generate tickets
    if action.get("status") in ("500", "502", "503") or action.get("error"):
        error_desc = f"Endpoint: {action.get('endpoint', 'unknown')} | Status: {action.get('status', '')} | Error: {action.get('error', '')}"
        await _auto_generate_ticket(user_key, error_desc)

    return {"logged": True}


@livehelp_router.get("/livehelp/session-analysis")
async def get_session_analysis(current_user: dict = Depends(get_current_user)):
    """Get troubleshooting analysis for current user's session."""
    user_key = current_user.get("user_key", "")
    suggestions = _analyze_session_log(user_key)
    log_count = len(_session_logs.get(user_key, []))
    return {"suggestions": suggestions, "log_count": log_count}


@livehelp_router.get("/livehelp/ice-servers")
async def get_ice_servers():
    """Return ICE server config for WebRTC peer connections."""
    ice = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
        {"urls": "stun:stun2.l.google.com:19302"},
        {"urls": "stun:stun3.l.google.com:19302"},
        {"urls": "stun:stun4.l.google.com:19302"},
    ]
    return {"iceServers": ice}


@livehelp_router.get("/livehelp/chat-history")
async def get_chat_history(current_user: dict = Depends(get_current_user)):
    """Get recent chat messages for the current user."""
    user_key = current_user.get("user_key", "")
    cursor = _state.db.livehelp_messages.find(
        {"$or": [{"from_user_key": user_key}, {"to_user_key": user_key}]},
        {"_id": 0},
    ).sort("ts_epoch", -1).limit(50)
    messages = await cursor.to_list(50)
    messages.reverse()
    return {"messages": messages}


@livehelp_router.get("/livehelp/active-sessions")
async def list_active_help_sessions(admin_user: dict = Depends(get_current_user)):
    """Admin: List active help sessions."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        from fastapi import HTTPException
        raise HTTPException(403, "Admin only")
    sessions = []
    for sid, info in _active_sessions.items():
        sessions.append({
            "session_id": sid,
            "user_key": info.get("user_key", ""),
            "username": info.get("username", ""),
            "started_at": info.get("started_at", ""),
            "mode": info.get("mode", "text"),
            "has_admin": info.get("admin_ws") is not None,
        })
    return {"sessions": sessions, "count": len(sessions)}


@livehelp_router.get("/admin/livehelp/user-logs/{user_key}")
async def get_user_session_logs(user_key: str, admin_user: dict = Depends(get_current_user)):
    """Admin: Get session logs for a specific user (for debugging)."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        from fastapi import HTTPException
        raise HTTPException(403, "Admin only")
    logs = _session_logs.get(user_key, [])[-50:]
    suggestions = _analyze_session_log(user_key)
    return {"logs": logs, "suggestions": suggestions, "count": len(logs)}


# ── Chat History Persistence ──────────────────────────────────────────────────

@livehelp_router.get("/livehelp/ice-servers")
async def get_ice_servers():
    """Return ICE server config for WebRTC peer connections."""
    WEBRTC_ICE_SERVERS = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
        {"urls": "stun:stun2.l.google.com:19302"},
        {"urls": "stun:stun3.l.google.com:19302"},
        {"urls": "stun:stun4.l.google.com:19302"},
    ]
    return {"iceServers": WEBRTC_ICE_SERVERS}
    """Get recent chat messages for the current user."""
    user_key = current_user.get("user_key", "")
    cursor = _state.db.livehelp_messages.find(
        {"$or": [{"from_user_key": user_key}, {"to_user_key": user_key}]},
        {"_id": 0},
    ).sort("ts_epoch", -1).limit(50)
    messages = await cursor.to_list(50)
    messages.reverse()
    return {"messages": messages}
