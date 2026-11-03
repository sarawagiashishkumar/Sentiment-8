"""
Auth route handlers — login, logout, me, settings.
Uses app_state for shared state (no circular import server).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request

import services.app_state as _state
from deps import get_current_user, hash_session_token
from models import AccessRequest, AccessResponse, MeResponse, UserSettingsUpdate

logger = logging.getLogger(__name__)

auth_router = APIRouter()


# ── Helper: split from monolithic auth_access for testability ─────────────────

async def _resolve_credential(raw: str) -> str:
    """Normalize and validate the login credential."""
    from services.validators import _validate_username
    credential = raw.strip()
    if not credential:
        raise HTTPException(400, "Username is required")
    if credential == _state.LEGACY_OWNER_ALIAS:
        credential = _state.OWNER_BOOTSTRAP_USERNAME
    return _validate_username(credential)


async def _lookup_user(credential: str) -> dict:
    """Find or bootstrap the user account."""
    from services.user_service import _ensure_owner_exists, _get_user_by_username
    user = await _get_user_by_username(credential)
    if not user and credential == _state.OWNER_BOOTSTRAP_USERNAME:
        user = await _ensure_owner_exists()
    if not user:
        raise HTTPException(404, "Username not found. Please contact admin.")
    return user


def _check_suspended(user: dict):
    """Raise 403 if account is suspended."""
    if user.get("suspended"):
        fee = user.get("reactivation_fee", 2500)
        raise HTTPException(
            403,
            f"ACCOUNT_SUSPENDED|Your account has been suspended due to a Fraud Login Attempt. "
            f"A reactivation fee of INR {fee} is required. "
            f"Please use the contact form below to request reactivation.",
        )


async def _check_fraud(user: dict, request: Request):
    """Run geospatial fraud check for non-admin users."""
    if user.get("role") in ("owner", "sub_admin"):
        return
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    user_agent = request.headers.get("User-Agent", "")
    try:
        from routes.fraud import check_impossible_travel, suspend_account_for_fraud
        fraud_info = await check_impossible_travel(user["user_key"], ip, user_agent)
        if fraud_info:
            await suspend_account_for_fraud(user["user_key"], fraud_info)
            raise HTTPException(
                403,
                f"ACCOUNT_SUSPENDED|Fraud Login Attempt detected. "
                f"Impossible travel from {fraud_info.get('previous_location', 'Unknown')} "
                f"to {fraud_info.get('current_location', 'Unknown')} "
                f"({fraud_info.get('distance_km', 0)} km in {fraud_info.get('elapsed_hours', 0)} hours). "
                f"Account suspended. Reactivation fee: INR 2,500.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Fraud check failed (non-fatal): %s", exc)


async def _create_session(user_key: str) -> str:
    """Create a 24-hour session and persist only its token hash."""
    token = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=24)
    _state.SESSION_STORE[token] = {
        "user_key": user_key,
        "created_at": created_at.isoformat(),
    }

    if _state.db is not None:
        await _state.db.login_sessions.insert_one({
            "token_hash": hash_session_token(token),
            "user_key": user_key,
            "created_at": created_at,
            "expires_at": expires_at,
            "ts_epoch": created_at.timestamp(),
        })
    return token


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_router.post("/auth/access", response_model=AccessResponse)
async def auth_access(payload: AccessRequest, request: Request):
    from services.user_service import _ensure_owner_exists, _is_credit_exempt
    await _ensure_owner_exists()

    credential = await _resolve_credential(payload.username or payload.password or "")
    user = await _lookup_user(credential)
    _check_suspended(user)
    await _check_fraud(user, request)

    token = await _create_session(user["user_key"])
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
    _ = current_user
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        _state.SESSION_STORE.pop(token, None)
        if _state.db is not None:
            await _state.db.login_sessions.delete_one({"token_hash": hash_session_token(token)})
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
    """Update user's F&O trading settings."""
    from services.user_service import _get_user_by_key
    update_fields = {}
    if payload.fno_budget is not None:
        if payload.fno_budget < 0:
            raise HTTPException(400, "Budget must be non-negative")
        update_fields["fno_budget"] = payload.fno_budget
    if payload.account_risk_pct is not None:
        if not (0 < payload.account_risk_pct <= 100):
            raise HTTPException(400, "Risk % must be between 0 and 100")
        update_fields["account_risk_pct"] = payload.account_risk_pct
    if not update_fields:
        raise HTTPException(400, "No valid fields to update")
    await _state.db.app_users.update_one(
        {"user_key": current_user["user_key"]},
        {"$set": update_fields},
    )
    updated = await _get_user_by_key(current_user["user_key"])
    return {
        "ok": True,
        "fno_budget": float(updated.get("fno_budget", 500000)),
        "account_risk_pct": float(updated.get("account_risk_pct", 2.0)),
    }
