"""
Validators — Input validation helpers.

Extracted from server.py for modularity. Pure functions, no DB dependency.
"""
from __future__ import annotations

import re
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9@._-]{6,}$")


def _validate_expiry_guard(minutes_to_expiry: int) -> None:
    if minutes_to_expiry <= 0:
        raise HTTPException(status_code=400, detail="Contract expired. No projections available.")
    if minutes_to_expiry <= 15:
        raise HTTPException(status_code=400, detail="Too close to expiry for safe projections.")


def _validate_username(username: str) -> str:
    value = username.strip()
    if not USERNAME_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="Username must be at least 6 chars and can use letters, numbers, @ . _ -",
        )
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise HTTPException(status_code=400, detail="Username must include at least one letter and one number")
    return value


def _validate_domain(domain: str) -> str:
    value = domain.strip().lower()
    if not re.fullmatch(r"^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$", value):
        raise HTTPException(status_code=400, detail="Invalid domain format")
    return value


def _split_domain_root_and_host(fqdn: str) -> tuple[str, str]:
    parts = fqdn.split(".")
    if len(parts) <= 2:
        return fqdn, "@"
    root_domain = ".".join(parts[-2:])
    host_label = ".".join(parts[:-2])
    return root_domain, host_label or "@"


def _normalize_target_record(target_record: str) -> str:
    value = target_record.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Target record is required")
    if "://" in value:
        parsed = urlparse(value)
        if parsed.hostname:
            return parsed.hostname.lower()
    return value.lower()


def _resolve_ipv4(value: str) -> str | None:
    if re.fullmatch(r"^\d{1,3}(\.\d{1,3}){3}$", value):
        return value
    try:
        return socket.gethostbyname(value)
    except Exception:
        return None
