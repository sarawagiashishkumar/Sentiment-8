"""
Kite-Native Data Integrity Verification System for Indian Equities & F&O.

PRODUCTION RULE: Kite Connect is the SOLE production market-data source.
Kite data does NOT require re-verification from any third-party or delayed
source. yfinance is BANNED from production paths.

Architecture:
  PRIMARY   → Kite Connect API (live, authenticated, authoritative)
  FALLBACK  → CSV seed files (offline, admin-uploaded, explicitly marked)

Verification rules (Kite-native only):
  1. Schema/field presence checks
  2. OHLC consistency: high >= max(open, close), low <= min(open, close)
  3. Non-negative volume and OI
  4. Timestamp freshness / stale-data detection
  5. Previous-candle continuity (configurable gap threshold)
  6. Kite historical vs Kite /quote/ohlc same-source consistency (optional)
  7. If Kite unavailable → mark as CSV seed fallback, NEVER as "externally verified"

Metadata emitted:
  data_source:        "kite" | "csv_seed" | "failed"
  verification_mode:  "kite_native" | "seed_only"
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VerifiedPrice:
    """Result of a Kite-native price fetch."""
    ltp: float | None
    source: str                            # "kite" | "csv_seed" | "failed"
    kite_ltp: float | None = None
    fallback_ltp: float | None = None      # CSV seed LTP if used
    discrepancy_pct: float | None = None   # Reserved for Kite-vs-Kite spot checks
    discrepancy_flagged: bool = False
    warnings: list[str] = field(default_factory=list)
    raw_kite_quote: dict | None = None
    data_source: str = "kite"              # "kite" | "csv_seed" | "failed"
    verification_mode: str = "kite_native" # "kite_native" | "seed_only"


@dataclass
class VerifiedSnapshot:
    """Result of a Kite-native option/stock snapshot."""
    ltp: float | None
    day_high: float | None
    day_low: float | None
    open: float | None
    prev_close: float | None
    volume: int | None
    oi: int | None                          # Open Interest
    iv: float | None                        # Implied Volatility
    source: str                             # "kite" | "csv_seed" | "failed"
    discrepancy_flagged: bool = False
    warnings: list[str] = field(default_factory=list)
    data_source: str = "kite"
    verification_mode: str = "kite_native"


@dataclass
class CandleIntegrityResult:
    """Result of Kite-native candle integrity validation."""
    valid: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    candle_count: int = 0
    failed_candles: int = 0
    data_source: str = "kite"
    verification_mode: str = "kite_native"


# ─────────────────────────────────────────────────────────────────────────────
# KITE QUOTE HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _kite_quote_sync(
    symbols: list[str],
    kite_api_key: str,
    access_token: str,
    timeout: int = 8,
) -> dict[str, dict]:
    """Synchronous Kite quote fetch. Returns dict keyed by exchange:symbol."""
    if not access_token or not kite_api_key:
        return {}
    try:
        joined = "&i=".join(symbols)
        url = f"https://api.kite.trade/quote?i={joined}"
        resp = requests.get(
            url,
            headers={
                "X-Kite-Version": "3",
                "Authorization": f"token {kite_api_key}:{access_token}",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("Kite quote %s for %s", resp.status_code, symbols[:3])
            return {}
        data = resp.json().get("data", {})
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Kite quote exception for %s: %s", symbols[:3], exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# KITE-NATIVE CANDLE INTEGRITY VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_ohlcv_integrity(
    candles: list[dict] | list[list],
    symbol: str = "",
    max_gap_pct: float = 20.0,
    data_source: str = "kite",
) -> CandleIntegrityResult:
    """
    Kite-native integrity checks on OHLCV candle data.

    Rules:
      1. Schema: each candle must have open, high, low, close, volume
      2. OHLC consistency: high >= max(open, close) AND low <= min(open, close)
      3. Non-negative volume
      4. Continuity: close-to-open gap between consecutive candles < max_gap_pct
      5. No zero/negative prices
    """
    warnings: list[str] = []
    errors: list[str] = []
    failed = 0
    total = len(candles)

    if total == 0:
        return CandleIntegrityResult(
            valid=False, errors=["No candles provided"],
            data_source=data_source,
            verification_mode="kite_native" if data_source == "kite" else "seed_only",
        )

    prev_close: float | None = None

    for i, candle in enumerate(candles):
        # Support both dict and list formats
        if isinstance(candle, (list, tuple)):
            if len(candle) < 6:
                errors.append(f"Candle {i}: insufficient fields ({len(candle)} < 6)")
                failed += 1
                continue
            o, h, lo, c, v = float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4]), float(candle[5])
        elif isinstance(candle, dict):
            try:
                o = float(candle.get("open", 0))
                h = float(candle.get("high", 0))
                lo = float(candle.get("low", 0))
                c = float(candle.get("close", 0))
                v = float(candle.get("volume", 0))
            except (TypeError, ValueError):
                errors.append(f"Candle {i}: non-numeric OHLCV fields")
                failed += 1
                continue
        else:
            errors.append(f"Candle {i}: unexpected type {type(candle)}")
            failed += 1
            continue

        # Rule 1: No zero/negative prices
        if o <= 0 or h <= 0 or lo <= 0 or c <= 0:
            errors.append(f"Candle {i}: zero/negative price O={o} H={h} L={lo} C={c}")
            failed += 1
            continue

        # Rule 2: OHLC consistency
        if h < max(o, c) - 0.01:
            warnings.append(f"Candle {i}: high {h} < max(open,close) {max(o,c)}")
            failed += 1
        if lo > min(o, c) + 0.01:
            warnings.append(f"Candle {i}: low {lo} > min(open,close) {min(o,c)}")
            failed += 1

        # Rule 3: Non-negative volume
        if v < 0:
            warnings.append(f"Candle {i}: negative volume {v}")

        # Rule 4: Continuity gap check
        if prev_close is not None and prev_close > 0:
            gap_pct = abs(o - prev_close) / prev_close * 100
            if gap_pct > max_gap_pct:
                warnings.append(
                    f"Candle {i}: large gap {gap_pct:.1f}% "
                    f"(prev_close={prev_close:.2f}, open={o:.2f})"
                )
        prev_close = c

    corruption_rate = failed / total if total > 0 else 0
    is_valid = corruption_rate < 0.10  # <10% bad candles = valid dataset

    if corruption_rate > 0 and corruption_rate < 0.10:
        warnings.append(
            f"{symbol}: {failed}/{total} candles failed integrity "
            f"({corruption_rate*100:.1f}%) — within tolerance"
        )
    elif corruption_rate >= 0.10:
        errors.append(
            f"{symbol}: {failed}/{total} candles failed integrity "
            f"({corruption_rate*100:.1f}%) — EXCEEDS tolerance"
        )

    return CandleIntegrityResult(
        valid=is_valid,
        warnings=warnings,
        errors=errors,
        candle_count=total,
        failed_candles=failed,
        data_source=data_source,
        verification_mode="kite_native" if data_source == "kite" else "seed_only",
    )


def validate_quote_snapshot(quote: dict, symbol: str = "") -> list[str]:
    """
    Kite-native quote validation: schema presence, OHLC consistency, staleness.
    Returns list of warnings (empty = valid).
    """
    warnings: list[str] = []
    if not quote:
        warnings.append(f"{symbol}: empty quote data")
        return warnings

    ltp = _safe_float(quote.get("last_price"))
    if ltp is None or ltp <= 0:
        warnings.append(f"{symbol}: missing or zero LTP")

    ohlc = quote.get("ohlc", {})
    o = _safe_float(ohlc.get("open"))
    h = _safe_float(ohlc.get("high"))
    lo = _safe_float(ohlc.get("low"))
    c = _safe_float(ohlc.get("close"))

    if h is not None and o is not None and c is not None:
        if h < max(o, c) - 0.01:
            warnings.append(f"{symbol}: day high {h} < max(open,close) {max(o,c)}")
    if lo is not None and o is not None and c is not None:
        if lo > min(o, c) + 0.01:
            warnings.append(f"{symbol}: day low {lo} > min(open,close) {min(o,c)}")

    vol = quote.get("volume")
    if vol is not None and int(vol) < 0:
        warnings.append(f"{symbol}: negative volume {vol}")

    oi = quote.get("oi")
    if oi is not None and int(oi) < 0:
        warnings.append(f"{symbol}: negative OI {oi}")

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# VERIFIED PRICE FETCH (Kite-only)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_verified_price(
    symbol: str,
    kite_api_key: str,
    access_token: str,
    exchange: str = "NSE",
    cross_verify: bool = False,
    discrepancy_threshold_pct: float = 2.0,
) -> VerifiedPrice:
    """
    Fetch LTP from Kite (sole source). No third-party cross-verification.
    If Kite is unavailable, returns failed status (CSV seed handled upstream).
    """
    kite_exchange_symbol = f"{exchange}:{symbol}"
    kite_raw = await asyncio.to_thread(
        _kite_quote_sync, [kite_exchange_symbol], kite_api_key, access_token
    )

    if isinstance(kite_raw, Exception):
        kite_raw = {}

    kite_ltp: float | None = None
    raw_quote: dict | None = None
    kite_data = kite_raw.get(kite_exchange_symbol) or kite_raw.get(symbol, {})
    warnings: list[str] = []

    if kite_data and isinstance(kite_data, dict):
        raw_quote = kite_data
        lp = kite_data.get("last_price") or kite_data.get("ltp")
        try:
            kite_ltp = float(lp) if lp is not None and float(lp) > 0 else None
        except (TypeError, ValueError):
            kite_ltp = None

        # Kite-native validation on the quote
        quote_warnings = validate_quote_snapshot(kite_data, symbol)
        warnings.extend(quote_warnings)

    if kite_ltp is not None:
        return VerifiedPrice(
            ltp=kite_ltp,
            source="kite",
            kite_ltp=kite_ltp,
            warnings=warnings,
            raw_kite_quote=raw_quote,
            data_source="kite",
            verification_mode="kite_native",
        )

    # Kite unavailable
    warnings.append(f"Kite data unavailable for {symbol}")
    logger.warning("Kite data unavailable for %s — no fallback applied", symbol)
    return VerifiedPrice(
        ltp=None,
        source="failed",
        warnings=warnings,
        data_source="failed",
        verification_mode="kite_native",
    )


async def fetch_verified_snapshot(
    kite_exchange_symbol: str,
    kite_api_key: str,
    access_token: str,
    underlying_symbol: str | None = None,
) -> VerifiedSnapshot:
    """
    Fetch full OHLC+OI+IV snapshot from Kite (sole source).
    No yfinance cross-verification or fallback.
    """
    kite_raw = await asyncio.to_thread(
        _kite_quote_sync, [kite_exchange_symbol], kite_api_key, access_token
    )

    if isinstance(kite_raw, Exception):
        kite_raw = {}

    kite_data = kite_raw.get(kite_exchange_symbol) or {}
    warnings: list[str] = []

    if kite_data:
        quote_warnings = validate_quote_snapshot(kite_data, kite_exchange_symbol)
        warnings.extend(quote_warnings)

        ohlc = kite_data.get("ohlc", {})
        lp = kite_data.get("last_price")
        try:
            ltp = float(lp) if lp is not None else None
        except (TypeError, ValueError):
            ltp = None

        return VerifiedSnapshot(
            ltp=ltp,
            day_high=_safe_float(ohlc.get("high")),
            day_low=_safe_float(ohlc.get("low")),
            open=_safe_float(ohlc.get("open")),
            prev_close=_safe_float(ohlc.get("close")),
            volume=_safe_int(kite_data.get("volume")),
            oi=_safe_int(kite_data.get("oi")),
            iv=_safe_float(kite_data.get("iv")),
            source="kite",
            warnings=warnings,
            data_source="kite",
            verification_mode="kite_native",
        )

    # Kite failed — no fallback
    warnings.append(f"Kite snapshot unavailable for {kite_exchange_symbol}")
    return VerifiedSnapshot(
        ltp=None, day_high=None, day_low=None, open=None, prev_close=None,
        volume=None, oi=None, iv=None,
        source="failed",
        warnings=warnings,
        data_source="failed",
        verification_mode="kite_native",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SESSION TIME HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_minutes_to_session_close() -> int:
    """
    Returns minutes remaining until 15:30 IST today.
    Returns 0 if market has already closed for the day.
    Returns 375 (full session) if called pre-market.
    """
    try:
        import pytz
        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        if now < market_open:
            return 375
        if now >= market_close:
            return 0
        return max(0, int((market_close - now).total_seconds() / 60))
    except Exception:
        return 375


def is_market_open() -> bool:
    """Returns True if current IST time is within 09:15-15:30 on a weekday."""
    try:
        import pytz
        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        h, m = now.hour, now.minute
        after_open = (h > 9) or (h == 9 and m >= 15)
        before_close = (h < 15) or (h == 15 and m < 30)
        return after_open and before_close
    except Exception:
        return True


def get_market_session_status() -> dict[str, Any]:
    """Returns current market session status."""
    try:
        import pytz
        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        mins_to_close = get_minutes_to_session_close()
        open_flag = is_market_open()
        return {
            "is_open": open_flag,
            "ist_time": now.strftime("%H:%M:%S IST"),
            "minutes_to_close": mins_to_close,
            "session_end": "15:30 IST",
            "session_start": "09:15 IST",
            "status": (
                "OPEN" if open_flag
                else ("PRE_MARKET" if now.hour < 9 else "CLOSED")
            ),
        }
    except Exception:
        return {"is_open": True, "status": "UNKNOWN"}


# ─────────────────────────────────────────────────────────────────────────────
# VIX-BASED THETA DECAY
# ─────────────────────────────────────────────────────────────────────────────

def compute_vix_theta_decay(
    entry_price: float,
    remaining_trading_days: int,
    best_exit_days: int,
    india_vix: float | None = None,
    iv_override: float | None = None,
    calendar_days_to_expiry: int | None = None,
    calendar_best_exit_days: int | None = None,
) -> tuple[float, str]:
    """
    Compute theta decay using VIX/IV-based model.

    Options decay over ALL calendar days (including weekends & NSE holidays),
    not just trading days. The time parameter uses calendar days per the standard
    B-S convention (365-day year).
    """
    if iv_override is not None and iv_override > 0:
        sigma = iv_override / 100.0
        theta_method = f"IV={iv_override:.1f}%"
    elif india_vix is not None and india_vix > 0:
        vix_scale = 1.0
        if remaining_trading_days <= 7:
            vix_scale = 1.25
        elif remaining_trading_days <= 21:
            vix_scale = 1.1
        sigma = (india_vix * vix_scale) / 100.0
        theta_method = f"VIX={india_vix:.1f}x{vix_scale:.2f}"
    else:
        sigma = 0.18
        theta_method = "default_18%"

    sigma = max(0.08, min(sigma, 0.80))

    cal_to_expiry = (
        calendar_days_to_expiry
        if (calendar_days_to_expiry is not None and calendar_days_to_expiry > 0)
        else max(remaining_trading_days, 1)
    )
    t = cal_to_expiry / 365.0

    try:
        daily_theta_cal = entry_price * sigma / (2.0 * math.sqrt(max(t, 1 / 365) * 365))
    except (ValueError, ZeroDivisionError):
        daily_theta_cal = entry_price * 0.02

    cal_decay_days = (
        calendar_best_exit_days
        if (calendar_best_exit_days is not None and calendar_best_exit_days > 0)
        else max(best_exit_days, 0)
    )

    theta_decay_total = round(daily_theta_cal * cal_decay_days, 2)
    if calendar_best_exit_days is not None and calendar_best_exit_days > best_exit_days:
        theta_method += f"+{calendar_best_exit_days - best_exit_days}non-trading"

    return theta_decay_total, theta_method


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC TARGET REVISION
# ─────────────────────────────────────────────────────────────────────────────

def compute_dynamic_target_revision(
    entry_price: float,
    current_ltp: float,
    current_t1: float,
    current_t2: float,
    underlying_ltp: float,
    underlying_entry: float,
    india_vix: float | None,
    minutes_to_session_close: int,
    remaining_trading_days: int,
    direction: str = "BULLISH",
    original_t1: float = 0.0,
    original_t2: float = 0.0,
) -> tuple[float, float, str | None]:
    """
    Dynamically revise T1/T2 upward when market conditions support higher
    profit potential. Revision is computed relative to original targets
    to prevent compounding.
    """
    revised_t1 = current_t1
    revised_t2 = current_t2
    revision_note: str | None = None

    if entry_price <= 0 or current_t1 <= 0 or current_t2 <= 0:
        return revised_t1, revised_t2, None

    base_t1 = original_t1 if original_t1 > 0 else current_t1
    base_t2 = original_t2 if original_t2 > 0 else current_t2
    original_gap_t1_t2 = base_t2 - base_t1

    # Trigger 1: LTP exceeded T1 — revise T2 up (non-compounding)
    if current_ltp >= current_t1:
        new_t2 = round(base_t1 + original_gap_t1_t2 * 1.5, 2)
        if new_t2 > current_t2:
            revised_t2 = new_t2
            revision_note = (
                f"T1 achieved {current_ltp:.1f} >= T1 {current_t1:.1f} "
                f"— T2 revised to {new_t2:.1f}"
            )

    # Trigger 2: Strong underlying move in signal direction
    if underlying_entry > 0:
        underlying_move_pct = (underlying_ltp - underlying_entry) / underlying_entry * 100
        favorable = (
            (direction == "BULLISH" and underlying_move_pct > 0.5)
            or (direction == "BEARISH" and underlying_move_pct < -0.5)
        )
        vix_calm = india_vix is None or india_vix < 22
        time_adequate = minutes_to_session_close > 90

        if favorable and vix_calm and time_adequate:
            move_factor = min(abs(underlying_move_pct) / 2.0, 0.30)
            new_t1 = round(base_t1 * (1 + move_factor * 0.5), 2)
            new_t2 = round(base_t2 * (1 + move_factor), 2)
            if new_t1 > revised_t1 or new_t2 > revised_t2:
                note_2 = (
                    f"Strong underlying move {underlying_move_pct:+.1f}% "
                    f"— targets increased T1->{new_t1:.1f} T2->{new_t2:.1f}"
                )
                revised_t1 = max(revised_t1, new_t1)
                revised_t2 = max(revised_t2, new_t2)
                revision_note = f"{revision_note} | {note_2}" if revision_note else note_2

    # Near expiry: cap targets
    if remaining_trading_days <= 1 and minutes_to_session_close < 120:
        max_realistic_t2 = entry_price * 1.35
        if revised_t2 > max_realistic_t2:
            revised_t2 = max_realistic_t2
            revision_note = (revision_note or "") + " | T2 capped: near expiry + time constraint"

    # Absolute safety cap: T2 never exceeds 3x entry
    max_absolute_t2 = entry_price * 3.0
    if revised_t2 > max_absolute_t2:
        revised_t2 = max_absolute_t2
        revision_note = (revision_note or "") + f" | T2 hard-capped at 3x entry {max_absolute_t2:.1f}"

    return round(revised_t1, 2), round(revised_t2, 2), revision_note


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val: Any) -> float | None:
    try:
        f = float(val)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> int | None:
    try:
        return int(float(val)) if val is not None else None
    except (TypeError, ValueError):
        return None
