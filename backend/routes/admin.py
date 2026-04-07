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
from typing import Any, List, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from deps import get_admin_user, get_owner_user, _is_owner
from models import (
    AdminCreateUserRequest,
    AdminSetCreditsRequest,
    AdminSetQuotaRequest,
    AdminUserProfileUpdateRequest,
    AdminUserView,
    ApiControlUpdateRequest,
    DomainMappingCreateRequest,
    DomainMappingStatusUpdateRequest,
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


# ── Domain Mappings ───────────────────────────────────────────────────────────

@admin_router.post("/admin/domain-mappings")
async def admin_create_domain_mapping(
    payload: DomainMappingCreateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    domain = _srv._validate_domain(payload.domain)
    target_record = _srv._normalize_target_record(payload.target_record)
    root_domain, host_label = _srv._split_domain_root_and_host(domain)
    resolved_target_ip = _srv._resolve_ipv4(target_record)

    await _srv.db.domain_mappings.update_one(
        {"domain": domain},
        {
            "$set": {
                "domain": domain,
                "root_domain": root_domain,
                "host_label": host_label,
                "record_type": payload.record_type,
                "target_record": target_record,
                "resolved_target_ip": resolved_target_ip,
                "status": "PENDING",
                "updated_by": owner_user.get("username"),
                "updated_at": _srv._utc_now_iso(),
                "instructions": [
                    "Keep registrar nameservers unchanged.",
                    f"DNS host to add: {host_label}",
                    f"Record type: {payload.record_type}",
                    f"Record value: {resolved_target_ip or target_record}",
                    "TTL recommendation: 300 seconds",
                ],
            }
        },
        upsert=True,
    )
    row = await _srv.db.domain_mappings.find_one({"domain": domain}, {"_id": 0})
    return row


@admin_router.patch("/admin/domain-mappings/{domain}")
async def admin_update_domain_mapping(
    domain: str,
    payload: DomainMappingStatusUpdateRequest,
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv
    from pymongo import ReturnDocument

    key = _srv._validate_domain(domain)
    updated = await _srv.db.domain_mappings.find_one_and_update(
        {"domain": key},
        {
            "$set": {
                "status": payload.status,
                "updated_by": owner_user.get("username"),
                "updated_at": _srv._utc_now_iso(),
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Domain mapping not found")
    return updated


@admin_router.get("/admin/dns-instructions")
async def admin_dns_instructions(
    domain: str = Query(...),
    target_record: str | None = Query(default=None),
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv

    _ = owner_user
    fqdn = _srv._validate_domain(domain)
    root_domain, host_label = _srv._split_domain_root_and_host(fqdn)
    selected_target = _srv._normalize_target_record(target_record) if target_record else ""

    if not selected_target:
        row = await _srv.db.domain_mappings.find_one(
            {"domain": fqdn}, {"_id": 0, "target_record": 1, "resolved_target_ip": 1}
        )
        selected_target = (
            (row or {}).get("resolved_target_ip") or (row or {}).get("target_record") or ""
        )

    resolved = _srv._resolve_ipv4(selected_target) if selected_target else None
    value = resolved or selected_target

    return {
        "fqdn": fqdn,
        "root_domain": root_domain,
        "host_label": host_label,
        "record_type": "A",
        "record_value": value,
        "steps": [
            "Do not change current nameservers at registrar.",
            "Open DNS Zone of your current DNS provider.",
            f"Create/Update A record: Host={host_label}, Value={value}, TTL=300.",
            "Delete any conflicting A record for the same host label.",
            "Wait for propagation and verify via nslookup or dig.",
        ],
    }


@admin_router.delete("/admin/domain-mappings/{domain}")
async def admin_delete_domain_mapping(
    domain: str,
    owner_user: dict = Depends(get_owner_user),
):
    """Delete a domain mapping from DB and attempt nginx config cleanup."""
    import server as _srv
    import subprocess

    key = _srv._validate_domain(domain)
    result = await _srv.db.domain_mappings.delete_one({"domain": key})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Domain mapping not found")

    try:
        nginx_conf = f"/etc/nginx/sites-available/{key}"
        nginx_link = f"/etc/nginx/sites-enabled/{key}"
        for path in (nginx_conf, nginx_link):
            if os.path.exists(path):
                os.remove(path)
        subprocess.run(["nginx", "-s", "reload"], capture_output=True, timeout=5)
    except Exception as exc:
        logger.debug("Nginx config cleanup skipped: %s", exc)

    return {"deleted": True, "domain": key}


@admin_router.post("/admin/domain-mappings/{domain}/map")
async def admin_map_domain(
    domain: str,
    owner_user: dict = Depends(get_owner_user),
):
    """Write Nginx reverse-proxy config for the domain and attempt reload."""
    import server as _srv
    import subprocess

    key = _srv._validate_domain(domain)
    row = await _srv.db.domain_mappings.find_one({"domain": key}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Domain mapping not found — add it first")

    nginx_config = f"""server {{
    listen 80;
    server_name {key};

    location / {{
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}

    location /api/ {{
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
"""
    nginx_status = "NGINX_CONFIG_GENERATED"
    nginx_error = None
    conf_path = f"/etc/nginx/sites-available/{key}"
    link_path = f"/etc/nginx/sites-enabled/{key}"
    try:
        with open(conf_path, "w") as fh:
            fh.write(nginx_config)
        if not os.path.exists(link_path):
            os.symlink(conf_path, link_path)
        result = subprocess.run(["nginx", "-t"], capture_output=True, timeout=5)
        if result.returncode == 0:
            subprocess.run(["nginx", "-s", "reload"], capture_output=True, timeout=5)
            nginx_status = "ACTIVE"
        else:
            nginx_error = result.stderr.decode()[:300]
    except Exception as exc:
        nginx_error = str(exc)[:200]
        logger.info("Nginx map attempted for %s: %s", key, nginx_error)

    await _srv.db.domain_mappings.update_one(
        {"domain": key},
        {"$set": {"status": nginx_status, "nginx_config": nginx_config, "updated_at": _srv._utc_now_iso()}},
    )

    return {
        "mapped": True,
        "domain": key,
        "nginx_status": nginx_status,
        "nginx_error": nginx_error,
        "nginx_config_snippet": nginx_config,
        "note": "DNS must still point to this server's IP for traffic to reach this app.",
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
