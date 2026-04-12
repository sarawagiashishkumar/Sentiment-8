"""
Admin route handlers.

All endpoints under /admin/* are defined here.
Auth dependencies come from deps.py; server.py helpers
are accessed via deferred `import server` inside handler bodies.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from deps import get_admin_user, get_owner_user, _is_owner
import services.app_state as _state
from models import (
    AdminCreateUserRequest,
    AdminSetCreditsRequest,
    AdminSetQuotaRequest,
    AdminUserProfileUpdateRequest,
    AdminUserView,
    ApiControlUpdateRequest,
    MacroEventsUpdateRequest,
)
from services.backtest_engine import (
    delete_csv_seed,
    list_csv_seeds,
    save_csv_seed,
)
from services.macro_context import (
    SECTOR_MACRO_IMPACT_MAP,
    get_all_macro_events,
)
from services.strategy_library import (
    STRATEGY_LIBRARY,
    check_strategy_eligible,
)

logger = logging.getLogger(__name__)

admin_router = APIRouter()


# ── User Management ──────────────────────────────────────────────────────────

@admin_router.get("/admin/users", response_model=List[AdminUserView])
async def admin_list_users(admin_user: dict = Depends(get_admin_user)):
    import server as _srv

    if _is_owner(admin_user):
        rows = await _srv.db.app_users.find({}, {"_id": 0}).to_list(5000)
    else:
        rows = await _srv.db.app_users.find(
            {
                "$or": [
                    {"username": admin_user["username"]},
                    {"created_by": admin_user["username"]},
                    {"role": "owner"},
                ]
            },
            {"_id": 0},
        ).to_list(5000)
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    unique_rows = []
    seen_usernames: set[str] = set()
    for row in rows:
        username = row.get("username")
        if not username or username in seen_usernames:
            continue
        seen_usernames.add(username)
        unique_rows.append(row)
    return [_srv._map_user_view(row) for row in unique_rows]


@admin_router.post("/admin/users", response_model=AdminUserView)
async def admin_create_user(
    payload: AdminCreateUserRequest,
    admin_user: dict = Depends(get_admin_user),
):
    import server as _srv

    username = (payload.username or payload.password or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    username = _srv._validate_username(username)

    if await _srv._get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")

    role = payload.role
    if admin_user["role"] == "sub_admin":
        if role != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can create only Basic Users")
        if int(admin_user.get("quota_used", 0)) >= int(admin_user.get("quota_limit", 0)):
            raise HTTPException(status_code=403, detail="Sub-Admin user creation quota exhausted")

    doc = {
        "user_key": str(uuid.uuid4()),
        "username": username,
        "role": role,
        "credits": max(0.0, float(payload.initial_credits)),
        "created_at": _srv._utc_now_iso(),
        "created_by": admin_user["username"],
        "quota_limit": max(1, int(payload.quota_limit)) if role == "sub_admin" else 0,
        "quota_used": 0,
    }
    await _srv.db.app_users.insert_one(doc)

    if admin_user["role"] == "sub_admin":
        await _srv.db.app_users.update_one(
            {"user_key": admin_user["user_key"]},
            {"$inc": {"quota_used": 1}},
        )

    return _srv._map_user_view(doc)


@admin_router.patch("/admin/users/{user_ref}/credits", response_model=AdminUserView)
async def admin_set_credits(
    user_ref: str,
    payload: AdminSetCreditsRequest,
    admin_user: dict = Depends(get_admin_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner" and not _is_owner(admin_user):
        raise HTTPException(status_code=403, detail="Only Owner can modify Owner")

    if admin_user["role"] == "sub_admin":
        if target.get("created_by") != admin_user["username"] or target["role"] != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can modify only own basic users")

    updated = await _srv.db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"credits": max(0.0, float(payload.credits))}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return _srv._map_user_view(updated)


@admin_router.patch("/admin/users/{user_ref}/quota", response_model=AdminUserView)
async def admin_set_quota(
    user_ref: str,
    payload: AdminSetQuotaRequest,
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    _ = owner_user
    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] != "sub_admin":
        raise HTTPException(status_code=400, detail="Quota applies only to Sub-Admin")

    updated = await _srv.db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"quota_limit": max(1, int(payload.quota_limit))}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return _srv._map_user_view(updated)


@admin_router.delete("/admin/users/{user_ref}")
async def admin_delete_user(user_ref: str, admin_user: dict = Depends(get_admin_user)):
    import server as _srv

    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot be deleted")

    if admin_user["role"] == "sub_admin":
        if target.get("created_by") != admin_user["username"] or target["role"] != "user":
            raise HTTPException(
                status_code=403, detail="Sub-Admin can delete only own basic users"
            )

    await _srv.db.app_users.delete_one({"user_key": target["user_key"]})
    for token, session in list(_srv.SESSION_STORE.items()):
        if session.get("user_key") == target["user_key"]:
            _srv.SESSION_STORE.pop(token, None)
    return {"deleted": True}


@admin_router.post("/admin/users/{user_ref}/suspend")
async def admin_toggle_suspend(user_ref: str, admin_user: dict = Depends(get_admin_user)):
    """Toggle suspend/unsuspend for a user."""
    import server as _srv
    from pymongo import ReturnDocument

    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(404, "User not found")
    if target["role"] == "owner":
        raise HTTPException(400, "Owner cannot be suspended")

    new_state = not target.get("suspended", False)
    updated = await _state.db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"suspended": new_state}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return {"user_key": target["user_key"], "suspended": new_state, "username": updated.get("username")}


class BulkCreditRequest(BaseModel):
    user_keys: list[str]
    credits_delta: float


@admin_router.post("/admin/users/bulk-credits")
async def admin_bulk_credit_adjustment(
    payload: BulkCreditRequest,
    admin_user: dict = Depends(get_owner_user),
):
    """Bulk adjust credits for multiple users. credits_delta can be positive (topup) or negative."""
    results = []
    for uk in payload.user_keys:
        user = await _state.db.app_users.find_one({"user_key": uk}, {"_id": 0})
        if not user:
            results.append({"user_key": uk, "ok": False, "reason": "not_found"})
            continue
        new_credits = max(0, round(float(user.get("credits", 0)) + payload.credits_delta, 2))
        await _state.db.app_users.update_one({"user_key": uk}, {"$set": {"credits": new_credits}})
        results.append({"user_key": uk, "ok": True, "new_credits": new_credits})
    return {"results": results, "adjusted": sum(1 for r in results if r["ok"])}


class TopupRequest(BaseModel):
    credits: float


@admin_router.post("/admin/users/{user_ref}/topup")
async def admin_topup_credits(
    user_ref: str,
    payload: TopupRequest,
    admin_user: dict = Depends(get_admin_user),
):
    """Add credits to a user (topup). Always positive."""
    import server as _srv
    from pymongo import ReturnDocument

    if payload.credits <= 0:
        raise HTTPException(400, "Topup amount must be positive")
    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(404, "User not found")

    new_credits = round(float(target.get("credits", 0)) + payload.credits, 2)
    await _state.db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"credits": new_credits}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return {"user_key": target["user_key"], "credits": new_credits, "added": payload.credits}


@admin_router.get("/admin/users/export")
async def admin_export_users_csv(admin_user: dict = Depends(get_owner_user)):
    """Export all users as CSV."""
    from fastapi.responses import StreamingResponse
    import io
    import csv

    users = await _state.db.app_users.find({}, {"_id": 0}).to_list(10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_key", "username", "role", "credits", "package", "suspended", "created_by", "created_at"])
    for u in users:
        writer.writerow([
            u.get("user_key", ""), u.get("username", ""), u.get("role", ""),
            u.get("credits", 0), u.get("package", "free"),
            u.get("suspended", False), u.get("created_by", ""), u.get("created_at", ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


@admin_router.patch("/admin/users/{user_ref}/profile", response_model=AdminUserView)
async def admin_update_user_profile(
    user_ref: str,
    payload: AdminUserProfileUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    _ = owner_user
    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    updates: dict[str, object] = {}
    new_username: str | None = None
    if payload.username is not None:
        new_username = _srv._validate_username(payload.username)
        if new_username != target.get("username"):
            existing = await _srv._get_user_by_username(new_username)
            if existing and existing.get("user_key") != target.get("user_key"):
                raise HTTPException(status_code=400, detail="Username already exists")
        updates["username"] = new_username

    if payload.role is not None:
        updates["role"] = payload.role

    if not updates:
        raise HTTPException(status_code=400, detail="No profile changes provided")

    old_username = target.get("username")
    updated = await _srv.db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": updates},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    if new_username and old_username and old_username != new_username:
        await _srv.db.app_users.update_many(
            {"created_by": old_username},
            {"$set": {"created_by": new_username}},
        )

    return _srv._map_user_view(updated)


@admin_router.patch("/admin/self/username", response_model=AdminUserView)
async def admin_update_own_username(
    payload: AdminUserProfileUpdateRequest,
    admin_user: dict = Depends(get_admin_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    if not payload.username:
        raise HTTPException(status_code=400, detail="Username is required")

    new_username = _srv._validate_username(payload.username)
    if new_username != admin_user.get("username"):
        existing = await _srv._get_user_by_username(new_username)
        if existing and existing.get("user_key") != admin_user.get("user_key"):
            raise HTTPException(status_code=400, detail="Username already exists")

    old_username = admin_user.get("username")
    updated = await _srv.db.app_users.find_one_and_update(
        {"user_key": admin_user["user_key"]},
        {"$set": {"username": new_username}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    if old_username and old_username != new_username:
        await _srv.db.app_users.update_many(
            {"created_by": old_username},
            {"$set": {"created_by": new_username}},
        )
    return _srv._map_user_view(updated)


# ── Config & API Controls ────────────────────────────────────────────────────

@admin_router.get("/admin/config")
async def admin_get_config(owner_user: dict = Depends(get_owner_user)):
    import server as _srv
    from urllib.parse import urlparse

    _ = owner_user
    api_controls = await _srv._get_api_controls(force_refresh=True)
    domains = await _srv.db.domain_mappings.find({}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    kite_status = await _srv.db.system_meta.find_one(
        {"key": "kite_session"}, {"_id": 0, "access_token": 0}
    )
    hosting_domain = ""
    hosting_ip = None
    kite_redirect_url = _srv.KITE_REDIRECT_URL
    if kite_redirect_url:
        parsed = urlparse(kite_redirect_url)
        hosting_domain = parsed.hostname or ""
        if hosting_domain:
            hosting_ip = _srv._resolve_ipv4(hosting_domain)

    return {
        "api_controls": api_controls,
        "domain_mappings": domains,
        "kite": {
            "connected": bool(kite_status and kite_status.get("date") == _srv._today_ist()),
            "user_id": (kite_status or {}).get("user_id"),
            "updated_at": (kite_status or {}).get("updated_at"),
            "redirect_url": kite_redirect_url,
            "postback_url": os.environ.get("KITE_POSTBACK_URL"),
        },
        "hosting_dns_reference": {
            "hosting_domain": hosting_domain,
            "resolved_ipv4": hosting_ip,
            "recommended_record_type": "A",
            "example_apex_host": "@",
            "example_subdomain_host": "trade",
        },
        "dns_note": (
            "A-record mapping requires DNS ownership changes at your domain registrar; "
            "app can store and verify mapping status only."
        ),
        "dns_instructions": [
            "Do NOT change registrar nameservers.",
            "Open your current DNS Control Zone for the domain.",
            "Add/Update an A record for host '@' (apex) or your subdomain label (for example 'trade').",
            "Set the value to the hosting IPv4 shown in hosting_dns_reference.resolved_ipv4 (or target value configured below).",
            "Use TTL 300 seconds and remove conflicting A records for the same host.",
            "Verify propagation using nslookup/dig after 1-10 minutes.",
        ],
    }


@admin_router.patch("/admin/api-controls")
async def admin_update_api_controls(
    payload: ApiControlUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv

    _ = owner_user
    current = await _srv._get_api_controls(force_refresh=True)
    updated = {
        "kite_data_enabled": current.get("kite_data_enabled", True),
        "moneycontrol_data_enabled": current.get("moneycontrol_data_enabled", True),
        "strict_live_only": current.get("strict_live_only", True),
    }
    if payload.kite_data_enabled is not None:
        updated["kite_data_enabled"] = bool(payload.kite_data_enabled)
    if payload.moneycontrol_data_enabled is not None:
        updated["moneycontrol_data_enabled"] = bool(payload.moneycontrol_data_enabled)
    if payload.strict_live_only is not None:
        updated["strict_live_only"] = bool(payload.strict_live_only)

    await _srv.db.system_meta.update_one(
        {"key": "api_controls"},
        {
            "$set": {
                "key": "api_controls",
                **updated,
                "updated_at": _srv._utc_now_iso(),
                "updated_by": owner_user.get("username"),
            }
        },
        upsert=True,
    )
    await _srv._get_api_controls(force_refresh=True)
    return {"updated": True, "api_controls": updated}


# ── NSE Holiday Management ───────────────────────────────────────────────────

@admin_router.get("/admin/nse-holidays")
async def admin_get_nse_holidays(owner_user: dict = Depends(get_owner_user)):
    import server as _srv
    from services.holiday_manager import get_nse_holidays

    _ = owner_user
    holidays = get_nse_holidays()
    cursor = _srv.db["nse_holidays"].find({}, {"_id": 0}).sort("date", 1)
    records = await cursor.to_list(500)
    return {
        "total_in_memory": len(holidays),
        "holidays": records,
    }


@admin_router.post("/admin/nse-holidays/refresh")
async def admin_refresh_nse_holidays(
    owner_user: dict = Depends(get_owner_user),
    year: int = Query(..., ge=2025, le=2030, description="Calendar year to refresh"),
):
    import server as _srv
    from services.holiday_manager import fetch_and_update_holidays, get_nse_holidays

    _ = owner_user
    success = await fetch_and_update_holidays(year)
    if success:
        _srv.NSE_HOLIDAYS = get_nse_holidays()
    return {
        "success": success,
        "year": year,
        "total_holidays": len(_srv.NSE_HOLIDAYS),
        "message": (
            f"Holidays for {year} "
            f"{'updated from external source' if success else 'could not be fetched; defaults remain'}."
        ),
    }


# ── Macro Events ──────────────────────────────────────────────────────────────

@admin_router.get("/admin/macro-events")
async def admin_get_macro_events(owner_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = owner_user
    active = await _srv._get_active_macro_events()
    all_events = get_all_macro_events()
    enriched = []
    for key in all_events:
        data = SECTOR_MACRO_IMPACT_MAP.get(key, {})
        enriched.append(
            {
                "key": key,
                "description": data.get("impact_description", ""),
                "intensity": data.get("intensity", "MEDIUM"),
                "beneficiaries": data.get("beneficiaries", []),
                "losers": data.get("losers", []),
                "active": key in active,
            }
        )
    return {
        "active_events": active,
        "total_active": len(active),
        "all_events": enriched,
    }


@admin_router.post("/admin/macro-events/update")
async def admin_update_macro_events(
    body: MacroEventsUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv

    _ = owner_user
    valid_keys = set(get_all_macro_events())
    invalid = [e for e in body.events if e not in valid_keys]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event keys: {invalid}. Valid keys: {sorted(valid_keys)}",
        )
    await _srv.db["macro_config"].update_one(
        {"config_id": "active_events"},
        {
            "$set": {
                "config_id": "active_events",
                "events": body.events,
                "updated_at": _srv._utc_now_iso(),
            }
        },
        upsert=True,
    )
    return {
        "success": True,
        "active_events": body.events,
        "total_active": len(body.events),
        "message": f"Active macro events updated. {len(body.events)} events now active.",
    }


# ── Strategy Stats ────────────────────────────────────────────────────────────

@admin_router.get("/admin/strategy-stats")
async def get_strategy_stats(
    strategy_id: str | None = Query(default=None),
    admin_user: dict = Depends(get_admin_user),
):
    """Return aggregated backtest stats per strategy_id."""
    import server as _srv

    query: dict = {}
    if strategy_id:
        query["strategy_id"] = strategy_id
    records = await _srv.db.strategy_backtest.find(query, {"_id": 0}).to_list(length=500)

    agg: dict[str, dict] = {}
    for r in records:
        sid = r.get("strategy_id", "UNKNOWN")
        if sid not in agg:
            agg[sid] = {
                "strategy_id": sid,
                "total_trades": 0,
                "wins": 0,
                "total_r_multiple": 0.0,
            }
        agg[sid]["total_trades"] += 1
        if r.get("win"):
            agg[sid]["wins"] += 1
        agg[sid]["total_r_multiple"] = round(
            agg[sid]["total_r_multiple"] + (r.get("r_multiple") or 0), 3
        )

    summary = []
    for sid, stats in agg.items():
        t = stats["total_trades"]
        stats["win_rate"] = round(stats["wins"] / t, 3) if t > 0 else None
        stats["expectancy"] = round(stats["total_r_multiple"] / t, 3) if t > 0 else None
        eligible, reason = check_strategy_eligible(stats, min_trades=10)
        stats["eligible"] = eligible
        stats["auto_disabled"] = not eligible
        stats["eligibility_reason"] = reason
        strat_def = STRATEGY_LIBRARY.get(sid, {})
        stats["strategy_name"] = strat_def.get("name", sid)
        stats["strategy_type"] = strat_def.get("type", "UNKNOWN")
        summary.append(stats)

    summary.sort(key=lambda x: x.get("total_trades", 0), reverse=True)
    return {"strategy_stats": summary, "total_records": len(records)}


@admin_router.post("/admin/strategy-stats/record")
async def record_strategy_result(
    strategy_id: str = Query(..., description="e.g. S1_ORB, SW2_200DMA_BOUNCE"),
    symbol: str = Query(...),
    win: bool = Query(...),
    r_multiple: float = Query(..., description="R-multiple: +1.0 = 1R gain, -1.0 = full SL"),
    admin_user: dict = Depends(get_admin_user),
):
    """Record a trade result for a strategy to persist backtest stats."""
    import server as _srv

    record = {
        "id": str(uuid.uuid4()),
        "strategy_id": strategy_id,
        "symbol": symbol,
        "win": win,
        "r_multiple": round(r_multiple, 3),
        "recorded_at": _srv._utc_now_iso(),
        "recorded_by": admin_user.get("username", "admin"),
    }
    await _srv.db.strategy_backtest.insert_one(record)

    all_records = await _srv.db.strategy_backtest.find(
        {"strategy_id": strategy_id}, {"_id": 0}
    ).to_list(length=500)
    stats: dict[str, Any] = {"total_trades": 0, "wins": 0, "total_r_multiple": 0.0}
    for r in all_records:
        stats["total_trades"] += 1
        if r.get("win"):
            stats["wins"] += 1
        stats["total_r_multiple"] += r.get("r_multiple") or 0
    t = stats["total_trades"]
    if t > 0:
        stats["win_rate"] = round(stats["wins"] / t, 3)
        stats["expectancy"] = round(stats["total_r_multiple"] / t, 3)
    eligible, reason = check_strategy_eligible(stats, min_trades=10)
    return {
        "recorded": True,
        "strategy_id": strategy_id,
        "current_stats": stats,
        "eligible": eligible,
        "auto_disabled": not eligible,
        "reason": reason,
    }


# ── CSV Seed Management ──────────────────────────────────────────────────────

@admin_router.get("/admin/csv-seeds")
async def list_csv_seeds_endpoint(current_user: dict = Depends(get_owner_user)):
    """List all verified CSV seed files for OHLCV data (admin only)."""
    seeds = list_csv_seeds()
    return {
        "seeds": seeds,
        "count": len(seeds),
        "seed_dir": str(os.environ.get("OHLCV_CSV_SEED_DIR", "/app/data/ohlcv_seeds")),
        "guide": (
            "Upload CSV files with columns: date,open,high,low,close,volume. "
            "Files are named {SYMBOL}.csv (e.g., NIFTY.csv, RELIANCE.csv). "
            "These are used ONLY when Kite Connect is unavailable."
        ),
    }


@admin_router.post("/admin/csv-seeds/{symbol}")
async def upload_csv_seed(
    symbol: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_owner_user),
):
    """Upload a verified CSV seed file for a symbol (admin only)."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    result = save_csv_seed(symbol, text)
    if result.get("error"):
        raise HTTPException(400, detail=result["error"])
    return result


@admin_router.delete("/admin/csv-seeds/{symbol}")
async def delete_csv_seed_endpoint(
    symbol: str,
    current_user: dict = Depends(get_owner_user),
):
    """Delete a CSV seed file for a symbol (admin only)."""
    result = delete_csv_seed(symbol)
    if result.get("error"):
        raise HTTPException(404, detail=result["error"])
    return result


# ── Permission & Package Management (Tiered System) ──────────────────────────

DEFAULT_FEATURE_COSTS = {
    "fno_generate": 2.0,
    "multibagger_generate": 2.0,
    "portfolio_analyze": 0.2,
    "custom_position": 1.0,
    "backtest_run": 0.5,
    "iv_collect": 0.0,
    "reports_view": 0.0,
    "watchlist_add": 0.0,
    "alert_rule_create": 0.0,
}

DEFAULT_USAGE_LIMITS = {
    "fno_generate_daily": 50,
    "multibagger_generate_daily": 20,
    "portfolio_analyze_daily": 100,
    "custom_position_total": 50,
    "backtest_run_daily": 20,
    "alert_rules_total": 10,
    "watchlist_items_total": 50,
}

PACKAGES = {
    "free": {"label": "Free Tier", "credits": 10, "limits": {**DEFAULT_USAGE_LIMITS, "fno_generate_daily": 5, "multibagger_generate_daily": 3, "alert_rules_total": 3, "watchlist_items_total": 10}},
    "basic": {"label": "Basic", "credits": 100, "limits": {**DEFAULT_USAGE_LIMITS, "fno_generate_daily": 20, "multibagger_generate_daily": 10}},
    "pro": {"label": "Pro", "credits": 500, "limits": DEFAULT_USAGE_LIMITS},
    "unlimited": {"label": "Unlimited", "credits": 999999, "limits": {k: 999999 for k in DEFAULT_USAGE_LIMITS}},
}


async def _get_packages() -> dict:
    """Get packages from DB, falling back to hardcoded defaults."""
    db_pkgs = await _state.db.system_meta.find_one({"key": "packages"}, {"_id": 0})
    if db_pkgs and db_pkgs.get("data"):
        return db_pkgs["data"]
    return PACKAGES


async def _get_feature_costs() -> dict:
    """Get global feature costs from DB, falling back to hardcoded defaults."""
    doc = await _state.db.system_meta.find_one({"key": "feature_costs"}, {"_id": 0})
    if doc and doc.get("data"):
        return {**DEFAULT_FEATURE_COSTS, **doc["data"]}
    return DEFAULT_FEATURE_COSTS


class PermissionUpdate(BaseModel):
    feature_costs: dict | None = None  # Override per-feature credit costs
    usage_limits: dict | None = None   # Override usage caps
    package: str | None = None         # Assign a package tier
    feature_restrictions: list[str] | None = None  # List of disabled features


@admin_router.get("/admin/packages")
async def get_available_packages(admin_user: dict = Depends(get_admin_user)):
    """List all available service packages with costs and limits."""
    pkgs = await _get_packages()
    costs = await _get_feature_costs()
    return {
        "packages": pkgs,
        "default_feature_costs": costs,
        "default_usage_limits": DEFAULT_USAGE_LIMITS,
    }


class PackageCreateUpdate(BaseModel):
    key: str
    label: str
    credits: float
    limits: dict


@admin_router.post("/admin/packages")
async def create_or_update_package(
    payload: PackageCreateUpdate,
    admin_user: dict = Depends(get_owner_user),
):
    """Create or update a package tier. Persisted to MongoDB."""
    pkgs = await _get_packages()
    pkgs[payload.key] = {
        "label": payload.label,
        "credits": payload.credits,
        "limits": {**DEFAULT_USAGE_LIMITS, **payload.limits},
    }
    await _state.db.system_meta.update_one(
        {"key": "packages"},
        {"$set": {"key": "packages", "data": pkgs}},
        upsert=True,
    )
    return {"ok": True, "package_key": payload.key, "total_packages": len(pkgs)}


@admin_router.delete("/admin/packages/{package_key}")
async def delete_package(
    package_key: str,
    admin_user: dict = Depends(get_owner_user),
):
    """Delete a custom package tier. Cannot delete 'free'."""
    if package_key == "free":
        raise HTTPException(400, "Cannot delete the free tier")
    pkgs = await _get_packages()
    if package_key not in pkgs:
        raise HTTPException(404, "Package not found")
    # Check if any users are on this package
    user_count = await _state.db.app_users.count_documents({"package": package_key})
    if user_count > 0:
        raise HTTPException(400, f"Cannot delete: {user_count} users are on this package. Migrate them first.")
    del pkgs[package_key]
    await _state.db.system_meta.update_one(
        {"key": "packages"},
        {"$set": {"key": "packages", "data": pkgs}},
        upsert=True,
    )
    return {"deleted": True, "package_key": package_key}


class FeatureCostsUpdate(BaseModel):
    costs: dict


@admin_router.patch("/admin/feature-costs")
async def update_global_feature_costs(
    payload: FeatureCostsUpdate,
    admin_user: dict = Depends(get_owner_user),
):
    """Update global default feature credit costs."""
    invalid = [k for k in payload.costs if k not in DEFAULT_FEATURE_COSTS]
    if invalid:
        raise HTTPException(400, f"Invalid feature keys: {invalid}")
    await _state.db.system_meta.update_one(
        {"key": "feature_costs"},
        {"$set": {"key": "feature_costs", "data": payload.costs}},
        upsert=True,
    )
    return {"ok": True, "updated_features": list(payload.costs.keys())}


@admin_router.get("/admin/users/{user_ref}/permissions")
async def get_user_permissions(
    user_ref: str,
    admin_user: dict = Depends(get_admin_user),
):
    """Get a user's current permissions, package, and usage."""
    import server as _srv

    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(404, "User not found")

    package = target.get("package", "free")
    all_pkgs = await _get_packages()
    pkg_config = all_pkgs.get(package, all_pkgs.get("free", PACKAGES["free"]))

    # Merge custom overrides with package defaults
    global_costs = await _get_feature_costs()
    feature_costs = {**global_costs, **(pkg_config.get("feature_costs", {})), **(target.get("feature_costs", {}))}
    usage_limits = {**pkg_config.get("limits", DEFAULT_USAGE_LIMITS), **(target.get("usage_limits", {}))}
    restrictions = target.get("feature_restrictions", [])

    # Get current day usage
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp()
    usage = {}
    for feature in ["fno_generate", "multibagger_generate", "portfolio_analyze", "backtest_run"]:
        count = await _state.db.usage_tracking.count_documents({
            "user_key": target["user_key"],
            "feature": feature,
            "ts_epoch": {"$gte": today_start},
        })
        usage[f"{feature}_today"] = count

    # Total counts
    for feature in ["custom_position", "alert_rules", "watchlist_items"]:
        if feature == "custom_position":
            count = await _state.db.custom_positions.count_documents({"user_key": target["user_key"], "status": "OPEN"})
        elif feature == "alert_rules":
            count = await _state.db.alert_rules.count_documents({"user_key": target["user_key"]})
        elif feature == "watchlist_items":
            count = await _state.db.user_watchlist.count_documents({"user_key": target["user_key"]})
        else:
            count = 0
        usage[f"{feature}_total"] = count

    return {
        "user_key": target["user_key"],
        "username": target.get("username"),
        "package": package,
        "package_label": pkg_config.get("label", "Free"),
        "feature_costs": feature_costs,
        "usage_limits": usage_limits,
        "feature_restrictions": restrictions,
        "current_usage": usage,
        "suspended": target.get("suspended", False),
    }


@admin_router.patch("/admin/users/{user_ref}/permissions")
async def update_user_permissions(
    user_ref: str,
    payload: PermissionUpdate,
    admin_user: dict = Depends(get_admin_user),
):
    """Update a user's permissions, package tier, or feature restrictions."""
    import server as _srv
    from pymongo import ReturnDocument

    target = await _srv._get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(404, "User not found")

    if target["role"] == "owner" and not _is_owner(admin_user):
        raise HTTPException(403, "Only Owner can modify Owner permissions")

    all_pkgs = await _get_packages()
    updates = {}
    if payload.package is not None:
        if payload.package not in all_pkgs:
            raise HTTPException(400, f"Invalid package. Options: {list(all_pkgs.keys())}")
        updates["package"] = payload.package
        # Apply package credits
        pkg = all_pkgs[payload.package]
        updates["credits"] = max(float(target.get("credits", 0)), pkg["credits"])

    if payload.feature_costs is not None:
        # Validate keys
        invalid = [k for k in payload.feature_costs if k not in DEFAULT_FEATURE_COSTS]
        if invalid:
            raise HTTPException(400, f"Invalid feature cost keys: {invalid}")
        updates["feature_costs"] = payload.feature_costs

    if payload.usage_limits is not None:
        invalid = [k for k in payload.usage_limits if k not in DEFAULT_USAGE_LIMITS]
        if invalid:
            raise HTTPException(400, f"Invalid usage limit keys: {invalid}")
        updates["usage_limits"] = payload.usage_limits

    if payload.feature_restrictions is not None:
        updates["feature_restrictions"] = payload.feature_restrictions

    if not updates:
        raise HTTPException(400, "No changes provided")

    await _state.db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": updates},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )

    return {"updated": True, "user_key": target["user_key"], "changes": list(updates.keys())}


async def check_usage_limit(user: dict, feature: str) -> bool:
    """Check if a user has exceeded their usage limit for a feature. Returns True if OK."""
    package = user.get("package", "free")
    pkg_config = PACKAGES.get(package, PACKAGES["free"])
    limits = {**pkg_config.get("limits", DEFAULT_USAGE_LIMITS), **(user.get("usage_limits", {}))}

    # Check feature restrictions
    restrictions = user.get("feature_restrictions", [])
    if feature in restrictions:
        return False

    daily_key = f"{feature}_daily"

    if daily_key in limits:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp()
        count = await _state.db.usage_tracking.count_documents({
            "user_key": user["user_key"],
            "feature": feature,
            "ts_epoch": {"$gte": today_start},
        })
        if count >= limits[daily_key]:
            return False

    return True


async def track_usage(user_key: str, feature: str):
    """Record a feature usage event for limit tracking."""
    await _state.db.usage_tracking.insert_one({
        "user_key": user_key,
        "feature": feature,
        "ts_epoch": datetime.now(timezone.utc).timestamp(),
    })


# ── Data Cleanup & Expanded CRUD ──────────────────────────────────────────────

@admin_router.delete("/admin/data/crm-messages")
async def purge_crm_messages(
    older_than_days: int = Query(default=0, description="Delete messages older than N days (0=all)"),
    admin_user: dict = Depends(get_owner_user),
):
    """Purge CRM messages. 0 days = delete ALL."""
    query = {}
    if older_than_days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
        query = {"ts_epoch": {"$lt": cutoff}}
    result = await _state.db.crm_messages.delete_many(query)
    return {"deleted": result.deleted_count, "collection": "crm_messages"}


@admin_router.delete("/admin/data/notifications")
async def purge_notifications(
    older_than_days: int = Query(default=0),
    admin_user: dict = Depends(get_owner_user),
):
    """Purge user notifications."""
    query = {}
    if older_than_days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
        query = {"ts": {"$lt": cutoff}}
    result = await _state.db.user_notifications.delete_many(query)
    return {"deleted": result.deleted_count, "collection": "user_notifications"}


@admin_router.delete("/admin/data/livehelp-messages")
async def purge_livehelp_messages(admin_user: dict = Depends(get_owner_user)):
    """Purge all live help chat messages."""
    result = await _state.db.livehelp_messages.delete_many({})
    return {"deleted": result.deleted_count, "collection": "livehelp_messages"}


@admin_router.delete("/admin/data/fraud-incidents")
async def purge_fraud_incidents(
    status: str = Query(default="all"),
    admin_user: dict = Depends(get_owner_user),
):
    """Purge fraud incidents."""
    query = {} if status == "all" else {"status": status}
    result = await _state.db.fraud_incidents.delete_many(query)
    return {"deleted": result.deleted_count, "collection": "fraud_incidents"}


@admin_router.delete("/admin/data/payments")
async def purge_payments(
    status: str = Query(default="all"),
    admin_user: dict = Depends(get_owner_user),
):
    """Purge payment records."""
    query = {} if status == "all" else {"status": status}
    result = await _state.db.payments.delete_many(query)
    return {"deleted": result.deleted_count, "collection": "payments"}


@admin_router.delete("/admin/data/login-sessions")
async def purge_login_sessions(admin_user: dict = Depends(get_owner_user)):
    """Purge login session history."""
    result = await _state.db.login_sessions.delete_many({})
    return {"deleted": result.deleted_count, "collection": "login_sessions"}


@admin_router.delete("/admin/data/usage-tracking")
async def purge_usage_tracking(admin_user: dict = Depends(get_owner_user)):
    """Purge usage tracking records."""
    result = await _state.db.usage_tracking.delete_many({})
    return {"deleted": result.deleted_count, "collection": "usage_tracking"}


@admin_router.get("/admin/data/stats")
async def get_data_stats(admin_user: dict = Depends(get_admin_user)):
    """Get document counts for all data collections."""
    collections = [
        "crm_messages", "user_notifications", "livehelp_messages",
        "fraud_incidents", "payments", "login_sessions", "usage_tracking",
        "alert_rules", "trading_journal", "fno_signal_log",
    ]
    stats = {}
    for col in collections:
        try:
            stats[col] = await _state.db[col].count_documents({})
        except Exception:
            stats[col] = -1
    return {"stats": stats}


@admin_router.get("/admin/users/search")
async def search_users(
    q: str = Query(default="", min_length=1),
    admin_user: dict = Depends(get_admin_user),
):
    """Search users by username (partial match)."""
    cursor = _state.db.app_users.find(
        {"username": {"$regex": q, "$options": "i"}},
        {"_id": 0},
    ).limit(20)
    users = await cursor.to_list(20)
    return {"users": users, "count": len(users)}
