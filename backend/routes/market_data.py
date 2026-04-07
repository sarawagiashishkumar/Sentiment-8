"""
Market data route handlers.

Endpoints: /script-master/*, /sector-momentum, /kite/*
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from deps import get_current_user, get_owner_user

logger = logging.getLogger(__name__)

market_data_router = APIRouter()


# ── Script Master ─────────────────────────────────────────────────────────────

@market_data_router.get("/script-master/lookup")
async def script_master_lookup(q: str = Query(default="")):
    import server as _srv

    query = q.strip()
    if not query:
        return {"query": query, "matches": []}

    await _srv._sync_script_master_daily()
    resolved = await _srv._resolve_symbol_input(query)
    row = await _srv.db.script_master.find_one(
        {"canonical_symbol": resolved},
        {"_id": 0, "canonical_symbol": 1, "display_name": 1, "aliases": 1},
    )
    if not row:
        return {"query": query, "matches": []}
    return {
        "query": query,
        "matches": [
            {
                "symbol": row.get("canonical_symbol"),
                "display_name": row.get("display_name"),
                "aliases": row.get("aliases", []),
            }
        ],
    }


@market_data_router.post("/script-master/refresh")
async def script_master_refresh(owner_user: dict = Depends(get_owner_user)):
    import server as _srv
    from datetime import datetime

    _ = owner_user
    _srv.SCRIPT_MASTER_LAST_SYNC_DATE = None
    await _srv._sync_script_master_daily(force=True)
    return {"refreshed": True, "date": datetime.now(_srv.IST).date().isoformat()}


# ── Sector Momentum ───────────────────────────────────────────────────────────

@market_data_router.get("/sector-momentum")
async def get_sector_momentum(
    force_refresh: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """
    Compute or return cached sector momentum dashboard.
    Returns momentum scores, 1W/1M/3M returns, RSI, ADX for 15 NSE sectors.
    Results cached for 30 minutes. Use ?force_refresh=true to bypass cache.
    """
    import server as _srv
    from datetime import datetime, timezone
    from services.sector_momentum import compute_sector_momentum_dashboard

    _ = current_user
    now_ts = datetime.now(timezone.utc).timestamp()

    # In-memory cache check
    if not force_refresh and _srv.SECTOR_MOMENTUM_CACHE:
        cached_ts = _srv.SECTOR_MOMENTUM_CACHE.get("_ts", 0)
        if (now_ts - cached_ts) < _srv.SECTOR_MOMENTUM_CACHE_TTL_SECONDS:
            data = {k: v for k, v in _srv.SECTOR_MOMENTUM_CACHE.items() if not k.startswith("_")}
            data["from_cache"] = True
            return data

    # MongoDB cache check
    if not force_refresh:
        try:
            cached_doc = await _srv.db.sector_momentum_cache.find_one(
                {"_key": "sector_momentum"}, {"_id": 0}
            )
            if cached_doc and (now_ts - float(cached_doc.get("cached_at_ts", 0))) < _srv.SECTOR_MOMENTUM_CACHE_TTL_SECONDS:
                payload = {k: v for k, v in cached_doc.items() if k not in ("_key", "cached_at_ts")}
                _srv.SECTOR_MOMENTUM_CACHE.update({**payload, "_ts": now_ts})
                payload["from_cache"] = True
                return payload
        except Exception:
            pass

    # Compute fresh
    try:
        result = await compute_sector_momentum_dashboard(db=_srv.db)
    except Exception as exc:
        logger.error("Sector momentum computation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sector momentum computation failed: {exc}")

    # Store in caches
    _srv.SECTOR_MOMENTUM_CACHE.update({**result, "_ts": now_ts})
    try:
        await _srv.db.sector_momentum_cache.update_one(
            {"_key": "sector_momentum"},
            {"$set": {"_key": "sector_momentum", "cached_at_ts": now_ts, **result}},
            upsert=True,
        )
    except Exception:
        pass

    result["from_cache"] = False
    return result


# ── Kite Connect Integration ─────────────────────────────────────────────────

@market_data_router.get("/kite/auth-url")
async def get_kite_auth_url(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    if not _srv.KITE_API_KEY or not _srv.KITE_API_SECRET or not _srv.KITE_REDIRECT_URL:
        raise HTTPException(status_code=400, detail="Kite credentials not configured")
    return {
        "auth_url": f"https://kite.zerodha.com/connect/login?v=3&api_key={_srv.KITE_API_KEY}",
        "redirect_url": _srv.KITE_REDIRECT_URL,
    }


@market_data_router.get("/kite/callback")
async def kite_callback(request_token: str = Query(...), status: str | None = Query(default=None)):
    import asyncio
    import server as _srv
    import requests

    _ = status
    if not _srv.KITE_API_KEY or not _srv.KITE_API_SECRET:
        raise HTTPException(status_code=400, detail="Kite credentials not configured")

    checksum = hashlib.sha256(
        f"{_srv.KITE_API_KEY}{request_token}{_srv.KITE_API_SECRET}".encode()
    ).hexdigest()

    def _create_session() -> dict:
        response = requests.post(
            "https://api.kite.trade/session/token",
            data={
                "api_key": _srv.KITE_API_KEY,
                "request_token": request_token,
                "checksum": checksum,
            },
            headers={"X-Kite-Version": "3"},
            timeout=15,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Kite session exchange failed")
        payload = response.json()
        if payload.get("status") != "success":
            raise HTTPException(status_code=502, detail="Kite session exchange failed")
        return payload.get("data", {})

    session_data = await asyncio.to_thread(_create_session)
    access_token = str(session_data.get("access_token", "")).strip()
    if not access_token:
        raise HTTPException(status_code=502, detail="Kite access token missing")

    today = _srv._today_ist()
    await _srv.db.system_meta.update_one(
        {"key": "kite_session"},
        {
            "$set": {
                "key": "kite_session",
                "date": today,
                "api_key": _srv.KITE_API_KEY,
                "access_token": access_token,
                "public_token": session_data.get("public_token"),
                "user_id": session_data.get("user_id"),
                "user_name": session_data.get("user_name"),
                "updated_at": _srv._utc_now_iso(),
            }
        },
        upsert=True,
    )

    await _srv._sync_kite_option_master_daily(force=True)
    return {
        "connected": True,
        "user_id": session_data.get("user_id"),
        "updated_at": _srv._utc_now_iso(),
    }


@market_data_router.get("/kite/status")
async def kite_status(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    row = await _srv.db.system_meta.find_one({"key": "kite_session"}, {"_id": 0, "access_token": 0})
    if not row:
        return {"connected": False}
    return {
        "connected": bool(row.get("date") == _srv._today_ist()),
        "date": row.get("date"),
        "user_id": row.get("user_id"),
        "updated_at": row.get("updated_at"),
    }


@market_data_router.post("/kite/refresh-option-master")
async def kite_refresh_option_master(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    await _srv._sync_kite_option_master_daily(force=True)
    meta = await _srv.db.system_meta.find_one({"key": "kite_option_master_sync"}, {"_id": 0})
    return {"refreshed": True, "meta": meta or {}}


@market_data_router.post("/kite/postback")
async def kite_postback(payload: dict):
    _ = payload
    return {"received": True}


@market_data_router.get("/kite/policy")
async def kite_policy(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    return {
        "read_only_mode": _srv.KITE_READ_ONLY_MODE,
        "trading_enabled": False,
        "allowed_data_endpoints": _srv.KITE_ALLOWED_DATA_ENDPOINTS,
        "blocked_categories": ["orders", "gtt", "positions-write", "basket-orders"],
    }
