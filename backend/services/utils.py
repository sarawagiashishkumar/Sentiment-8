"""
Pure utility functions — no I/O, no database access.

Extracted from server.py for modularization.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def sanitize_float(value) -> float | None:
    """Return None if value is NaN, Infinity or not a valid finite float."""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def estimate_option_ltp(underlying_ltp: float, strike: float, option_type: str) -> float:
    intrinsic = (
        max(underlying_ltp - strike, 0)
        if option_type == "CE"
        else max(strike - underlying_ltp, 0)
    )
    time_value = max(underlying_ltp * 0.002, 5)
    return round(intrinsic + time_value, 2)


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "")
    if raw in {"", "-", "--", "na", "n/a", "none", "null"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def normalize_symbol_key(value: str) -> str:
    return re.sub(r"[-\s.]+", "", value.strip().upper())
