"""
Admin domain mapping route handlers.

CRUD for custom domain configurations extracted from admin.py.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_owner_user
import services.app_state as _state
from models import DomainMappingCreateRequest, DomainMappingStatusUpdateRequest

logger = logging.getLogger(__name__)

admin_domains_router = APIRouter()


@admin_domains_router.post("/admin/domain-mappings")
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


@admin_domains_router.patch("/admin/domain-mappings/{domain}")
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


@admin_domains_router.get("/admin/dns-instructions")
async def admin_dns_instructions(
    domain: str = Query(...),
    target_record: str | None = Query(default=None),
    owner_user: dict = Depends(get_owner_user),
):
    import server as _srv

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


@admin_domains_router.delete("/admin/domain-mappings/{domain}")
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


@admin_domains_router.post("/admin/domain-mappings/{domain}/map")
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
