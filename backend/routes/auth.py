"""
Auth route handlers — login, logout, me, settings.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from deps import get_current_user
from models import AccessRequest, AccessResponse, MeResponse, UserSettingsUpdate

logger = logging.getLogger(__name__)

auth_router = APIRouter()


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


@auth_router.post("/auth/access", response_model=AccessResponse)
async def auth_access(payload: AccessRequest):
    _s = _srv()
    from services.user_service import _ensure_owner_exists, _get_user_by_username
    from services.validators import _validate_username
    from services.user_service import _is_credit_exempt

    await _ensure_owner_exists()
    credential = (payload.username or payload.password or "").strip()
    if not credential:
        raise HTTPException(status_code=400, detail="Username is required")

    if credential == _s.LEGACY_OWNER_ALIAS:
        credential = _s.OWNER_BOOTSTRAP_USERNAME
    credential = _validate_username(credential)

    user = await _get_user_by_username(credential)
    if not user and credential == _s.OWNER_BOOTSTRAP_USERNAME:
        user = await _ensure_owner_exists()
    if not user:
        raise HTTPException(status_code=404, detail="Username not found. Please contact admin.")

    token = str(uuid.uuid4())
    _s.SESSION_STORE[token] = {
        "user_key": user["user_key"],
        "created_at": _s._utc_now_iso(),
    }
    return AccessResponse(
        token=token,
        role=user["role"],
        credits=round(float(user.get("credits", 0)), 2),
        user_key=user["user_key"],
        username=user["username"],
        admin_exempt=_is_credit_exempt(user),
        fno_budget=float(user.get("fno_budget", 500000)),
        account_risk_pct=float(user.get("account_risk_pct", 2.0)),
    )


@auth_router.post("/auth/logout")
async def auth_logout(
    current_user: dict = Depends(get_current_user),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _s = _srv()
    _ = current_user
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        _s.SESSION_STORE.pop(token, None)
    return {"ok": True}


@auth_router.get("/auth/me", response_model=MeResponse)
async def auth_me(current_user: dict = Depends(get_current_user)):
    from services.user_service import _is_credit_exempt
    return MeResponse(
        role=current_user["role"],
        credits=round(float(current_user.get("credits", 0)), 2),
        user_key=current_user["user_key"],
        username=current_user["username"],
        admin_exempt=_is_credit_exempt(current_user),
        fno_budget=float(current_user.get("fno_budget", 500000)),
        account_risk_pct=float(current_user.get("account_risk_pct", 2.0)),
    )


@auth_router.patch("/auth/settings")
async def update_user_settings(
    payload: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update user's F&O trading settings (fno_budget, account_risk_pct)."""
    _s = _srv()
    from services.user_service import _get_user_by_key
    update_fields = {}
    if payload.fno_budget is not None:
        if payload.fno_budget < 0:
            raise HTTPException(status_code=400, detail="Budget must be non-negative")
        update_fields["fno_budget"] = payload.fno_budget
    if payload.account_risk_pct is not None:
        if not (0 < payload.account_risk_pct <= 100):
            raise HTTPException(status_code=400, detail="Risk % must be between 0 and 100")
        update_fields["account_risk_pct"] = payload.account_risk_pct
    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    await _s.db.app_users.update_one(
        {"user_key": current_user["user_key"]},
        {"$set": update_fields},
    )
    updated = await _get_user_by_key(current_user["user_key"])
    return {
        "ok": True,
        "fno_budget": float(updated.get("fno_budget", 500000)),
        "account_risk_pct": float(updated.get("account_risk_pct", 2.0)),
    }
