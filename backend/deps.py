"""
Shared FastAPI auth dependencies.

This module holds auth-related FastAPI Depends() callables so that
both server.py and route files (routes/*.py) can import them without
circular dependencies.

db and SESSION_STORE are injected by server.py via configure().
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import Depends, Header, HTTPException

# ── Module-level state (set by server.py at startup) ──────────────────────────
db = None
SESSION_STORE: Dict[str, dict] = {}


def configure(database, session_store: Dict[str, dict]):
    """Called once by server.py after creating db + SESSION_STORE."""
    global db, SESSION_STORE
    db = database
    SESSION_STORE = session_store


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_by_key(user_key: str) -> dict | None:
    return await db.app_users.find_one({"user_key": user_key}, {"_id": 0})


def hash_session_token(token: str) -> str:
    """Hash bearer tokens before persisting them to MongoDB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _find_session(token: str) -> dict | None:
    if db is not None:
        return await db.login_sessions.find_one(
            {
                "token_hash": hash_session_token(token),
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            },
            {"_id": 0, "user_key": 1},
        )

    session = SESSION_STORE.get(token)
    if not session:
        return None

    try:
        created_at = datetime.fromisoformat(session["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        SESSION_STORE.pop(token, None)
        return None

    if datetime.now(timezone.utc) - created_at > timedelta(hours=24):
        SESSION_STORE.pop(token, None)
        return None
    return session


def _is_owner(user: dict) -> bool:
    return user.get("role") == "owner"


def _is_admin(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


# ── FastAPI Dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        session = await _find_session(token)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Session store unavailable") from exc
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    user_key = session.get("user_key")
    if not user_key:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = await _get_user_by_key(user_key)
    if not user:
        SESSION_STORE.pop(token, None)
        if db is not None:
            await db.login_sessions.delete_one({"token_hash": hash_session_token(token)})
        raise HTTPException(status_code=401, detail="Session expired")
    return user


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


async def get_owner_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_owner(current_user):
        raise HTTPException(status_code=403, detail="Owner only")
    return current_user
