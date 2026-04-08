"""
Date, time and trading-day utility functions.

Extracted from server.py for modularization.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Literal

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def get_minutes_to_expiry(contract, nse_holidays: set[str] | None = None) -> int:
    """Minutes from now (IST) to contract expiry."""
    from services.holiday_manager import get_nse_holidays
    expiry_date_str = contract["expiry"] if isinstance(contract, dict) else contract.expiry
    expiry_time_str = (
        contract.get("expiry_time_ist", "15:30")
        if isinstance(contract, dict)
        else getattr(contract, "expiry_time_ist", "15:30")
    )
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    hh, mm = map(int, expiry_time_str.split(":"))
    expiry_dt = datetime.combine(expiry_date, time(hh, mm, tzinfo=IST))
    now = datetime.now(IST)
    return int((expiry_dt - now).total_seconds() / 60)


def expiry_risk_bucket(minutes_to_expiry: int) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if minutes_to_expiry < 180:
        return "HIGH"
    if minutes_to_expiry < 1440:
        return "MEDIUM"
    return "LOW"


def get_remaining_trading_days(expiry_date_str: str, nse_holidays: set[str] | None = None) -> int:
    """Count NSE trading days from today (IST) to expiry date (inclusive)."""
    from services.holiday_manager import get_nse_holidays
    holidays = nse_holidays or get_nse_holidays() or set()
    today = datetime.now(IST).date()
    try:
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    except ValueError:
        return 0

    if expiry_date < today:
        return 0

    count = 0
    now_ist = datetime.now(IST)
    market_still_open_today = (now_ist.hour < 15) or (now_ist.hour == 15 and now_ist.minute < 30)
    d = today
    if market_still_open_today and d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
        if d <= expiry_date:
            count += 1

    d = today + timedelta(days=1)
    while d <= expiry_date:
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
            count += 1
        d += timedelta(days=1)

    return count


def get_nth_trading_day_from_today(n: int, nse_holidays: set[str] | None = None) -> "datetime.date":
    """Return the calendar date that is exactly N trading days from today (IST)."""
    from services.holiday_manager import get_nse_holidays
    holidays = nse_holidays or get_nse_holidays() or set()
    if n <= 0:
        return datetime.now(IST).date()
    today = datetime.now(IST).date()
    d = today
    count = 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
            count += 1
    return d


def get_calendar_days_to_date(target_date_str: str) -> int:
    """Calendar days from today (IST) to date string. Includes weekends/holidays."""
    try:
        today = datetime.now(IST).date()
        target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        return max(0, (target - today).days)
    except Exception:
        return 0


def get_calendar_days_for_nth_trading_day(n: int, nse_holidays: set[str] | None = None) -> int:
    """Calendar days until the nth TRADING day from today (includes non-trading gaps)."""
    from services.holiday_manager import get_nse_holidays
    holidays = nse_holidays or get_nse_holidays() or set()
    try:
        today = datetime.now(IST).date()
        count = 0
        current = today
        while count < max(n, 0):
            current += timedelta(days=1)
            if current.weekday() < 5 and current.isoformat() not in holidays:
                count += 1
        return max(0, (current - today).days)
    except Exception:
        return max(n, 0)


def position_in_range(ltp: float | None, year_low: float | None, year_high: float | None) -> float | None:
    if ltp is None or year_low is None or year_high is None or year_high <= year_low:
        return None
    return max(0.0, min(1.0, (ltp - year_low) / (year_high - year_low)))
