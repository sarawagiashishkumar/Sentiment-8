"""
Shared FastAPI auth dependencies.

This module holds auth-related FastAPI Depends() callables so that
both server.py and route files (routes/*.py) can import them without
circular dependencies.

db and SESSION_STORE are injected by server.py via configure().
"""
from __future__ import annotations

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
    session = SESSION_STORE.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = await _get_user_by_key(session["user_key"])
    if not user:
        SESSION_STORE.pop(token, None)
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
