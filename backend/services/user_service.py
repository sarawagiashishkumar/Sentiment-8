"""
User Service — User CRUD and role helpers.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from pymongo import ReturnDocument

from models import AdminUserView
from services.utils import utc_now_iso as _utc_now_iso

import logging
logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


async def _ensure_owner_exists() -> dict:
    _s = _srv()
    owner_doc = await _s.db.app_users.find_one_and_update(
        {"username": _s.OWNER_BOOTSTRAP_USERNAME},
        {
            "$setOnInsert": {
                "user_key": str(uuid.uuid4()),
                "username": _s.OWNER_BOOTSTRAP_USERNAME,
                "role": "owner",
                "credits": 0,
                "created_at": _utc_now_iso(),
                "created_by": "SYSTEM",
                "quota_limit": 10_000,
                "quota_used": 0,
            }
        },
        upsert=True,
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return owner_doc


async def _get_user_by_key(user_key: str) -> dict | None:
    return await _srv().db.app_users.find_one({"user_key": user_key}, {"_id": 0})


async def _get_user_by_username(username: str) -> dict | None:
    return await _srv().db.app_users.find_one({"username": username}, {"_id": 0})


async def _get_user_by_ref(user_ref: str) -> dict | None:
    _s = _srv()
    candidate = await _s.db.app_users.find_one({"user_key": user_ref}, {"_id": 0})
    if candidate:
        return candidate
    return await _s.db.app_users.find_one({"username": user_ref}, {"_id": 0})


def _is_owner(user: dict) -> bool:
    return user.get("role") == "owner"


def _is_admin(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


def _is_credit_exempt(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


async def _consume_credits(user: dict, cost: float) -> tuple[dict, float]:
    if _is_credit_exempt(user):
        latest = await _get_user_by_key(user["user_key"])
        return latest or user, 0.0

    _s = _srv()
    updated = await _s.db.app_users.find_one_and_update(
        {"user_key": user["user_key"], "credits": {"$gte": cost}},
        {"$inc": {"credits": -cost}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        latest = await _get_user_by_key(user["user_key"])
        current = float(latest.get("credits", 0)) if latest else 0.0
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Required {round(cost,2)}, available {round(current,2)}",
        )
    return updated, float(cost)


def _map_user_view(user: dict) -> AdminUserView:
    role_raw = str(user.get("role", "user"))
    if role_raw == "admin":
        role_raw = "owner"
    role: Literal["owner", "sub_admin", "user"] = role_raw if role_raw in {"owner", "sub_admin", "user"} else "user"
    username = user.get("username") or f"legacy-{str(user.get('user_key', 'user'))[:6]}"

    return AdminUserView(
        user_key=user.get("user_key", str(uuid.uuid4())),
        username=username,
        role=role,
        credits=round(float(user.get("credits", 0)), 2),
        created_at=user.get("created_at", ""),
        created_by=user.get("created_by", "SYSTEM"),
        quota_limit=int(user.get("quota_limit", 0)),
        quota_used=int(user.get("quota_used", 0)),
        credential_label=f"{username} as {role}",
    )
