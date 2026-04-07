"""
Dual-Source Data Verification System for Indian Equities & F&O.

PROD RULE: All OHLCV and historical data for Indian markets must come from
Kite Connect or verified exchange APIs. Do not use yfinance or unofficial
sources in production paths. yfinance calls are guarded by USE_YFINANCE env var.

Architecture:
  PRIMARY   → Kite Connect API (live, authenticated, authoritative)
  FALLBACK  → yfinance NSE (free, unauthenticated, cross-verification)

Rules:
  1. Always try Kite first with a short timeout (8s).
  2. If Kite fails or returns invalid data, use yfinance fallback.
  3. When both sources are available, cross-verify:
     - Stocks: flag discrepancy if |kite - yf| / kite > 2%
     - Indices: flag if > 0.5%
  4. Never block signal generation on cross-verification failures;
     always return best available data with source metadata.
  5. All discrepancies are logged; critical ones are surfaced in responses.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VerifiedPrice:
    """Result of a dual-source price fetch."""
    ltp: float | None
    source: str                          # "kite" | "yfinance" | "failed"
    kite_ltp: float | None = None
    fallback_ltp: float | None = None
    discrepancy_pct: float | None = None  # |kite - fallback| / kite × 100
    discrepancy_flagged: bool = False
    warnings: list[str] = field(default_factory=list)
    raw_kite_quote: dict | None = None


@dataclass
class VerifiedSnapshot:
    """Result of a dual-source option/stock snapshot."""
    ltp: float | None
    day_high: float | None
    day_low: float | None
    open: float | None
    prev_close: float | None
    volume: int | None
    oi: int | None                        # Open Interest (Kite only)
    iv: float | None                      # Implied Volatility (Kite only)
    source: str
    discrepancy_flagged: bool = False
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE-SOURCE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _kite_quote_sync(
    symbols: list[str],   # e.g. ["NSE:RELIANCE", "NFO:NIFTY24...CE"]
    kite_api_key: str,
    access_token: str,
    timeout: int = 8,
) -> dict[str, dict]:
    """Synchronous Kite quote fetch. Returns dict keyed by symbol."""
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


def _yfinance_ltp_sync(symbol: str) -> float | None:
    """
    Synchronous yfinance LTP for NSE equity.
    GUARDED: Only runs if USE_YFINANCE=True (disabled in production).
    """
    _use_yf = os.environ.get("USE_YFINANCE", "false").lower() in ("1", "true", "yes")
    if not _use_yf:
        return None
    try:
        import yfinance as yf

        # Index mapping
        index_map = {
            "NIFTY": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
        }
        yf_symbol = index_map.get(symbol.upper(), f"{symbol.upper()}.NS")

        ticker = yf.Ticker(yf_symbol)
        fast = ticker.fast_info
        price = getattr(fast, "last_price", None)
        if price is None:
            hist = ticker.history(period="1d", interval="1m")
            if hist is not None and not hist.empty:
                price = float(hist["Close"].iloc[-1])
        return float(price) if price is not None and float(price) > 0 else None
    except Exception as exc:
        logger.debug("yfinance LTP failed for %s: %s", symbol, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# VERIFIED PRICE FETCH
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_verified_price(
    symbol: str,
    kite_api_key: str,
    access_token: str,
    exchange: str = "NSE",
    cross_verify: bool = True,
    discrepancy_threshold_pct: float = 2.0,
) -> VerifiedPrice:
    """
    Fetch LTP from Kite (primary) with yfinance cross-verification.
    Returns VerifiedPrice with source metadata and any warnings.
    """
    kite_exchange_symbol = f"{exchange}:{symbol}"

    # ── Parallel fetch ────────────────────────────────────────────────────
    kite_coro = asyncio.to_thread(
        _kite_quote_sync, [kite_exchange_symbol], kite_api_key, access_token
    )
    if cross_verify:
        yf_coro = asyncio.to_thread(_yfinance_ltp_sync, symbol)
        kite_raw, yf_ltp = await asyncio.gather(kite_coro, yf_coro, return_exceptions=True)
    else:
        kite_raw = await kite_coro
        yf_ltp = None

    # Handle exceptions from gather
    if isinstance(kite_raw, Exception):
        kite_raw = {}
    if isinstance(yf_ltp, Exception):
        yf_ltp = None

    # ── Extract Kite LTP ──────────────────────────────────────────────────
    kite_ltp: float | None = None
    raw_quote: dict | None = None
    kite_data = kite_raw.get(kite_exchange_symbol) or kite_raw.get(symbol, {})
    if kite_data and isinstance(kite_data, dict):
        raw_quote = kite_data
        lp = kite_data.get("last_price") or kite_data.get("ltp")
        try:
            kite_ltp = float(lp) if lp is not None and float(lp) > 0 else None
        except (TypeError, ValueError):
            kite_ltp = None

    # ── yfinance fallback LTP ─────────────────────────────────────────────
    yf_price: float | None = None
    if yf_ltp is not None and not isinstance(yf_ltp, Exception):
        try:
            yf_price = float(yf_ltp) if float(yf_ltp) > 0 else None
        except (TypeError, ValueError):
            yf_price = None

    # ── Determine authoritative LTP + warnings ────────────────────────────
    warnings: list[str] = []
    discrepancy_pct: float | None = None
    discrepancy_flagged = False

    if kite_ltp is not None:
        ltp = kite_ltp
        source = "kite"

        if cross_verify and yf_price is not None:
            discrepancy_pct = abs(kite_ltp - yf_price) / kite_ltp * 100
            if discrepancy_pct > discrepancy_threshold_pct:
                discrepancy_flagged = True
                warnings.append(
                    f"Price discrepancy: Kite ₹{kite_ltp:.2f} vs yfinance ₹{yf_price:.2f} "
                    f"({discrepancy_pct:.1f}%) — using Kite (authoritative)"
                )
                logger.warning(
                    "PRICE DISCREPANCY %s: Kite=%.2f yf=%.2f (%.1f%%)",
                    symbol, kite_ltp, yf_price, discrepancy_pct
                )
    elif yf_price is not None:
        ltp = yf_price
        source = "yfinance"
        warnings.append(
            f"Kite data unavailable for {symbol}; using yfinance fallback ₹{yf_price:.2f}"
        )
        logger.warning("Kite unavailable for %s — using yfinance fallback %.2f", symbol, yf_price)
    else:
        ltp = None
        source = "failed"
        warnings.append(f"Both Kite and yfinance failed to fetch LTP for {symbol}")
        logger.error("All sources failed for %s", symbol)

    return VerifiedPrice(
        ltp=ltp,
        source=source,
        kite_ltp=kite_ltp,
        fallback_ltp=yf_price,
        discrepancy_pct=discrepancy_pct,
        discrepancy_flagged=discrepancy_flagged,
        warnings=warnings,
        raw_kite_quote=raw_quote,
    )


async def fetch_verified_snapshot(
    kite_exchange_symbol: str,  # e.g. "NFO:NIFTY2640722700CE" or "NSE:RELIANCE"
    kite_api_key: str,
    access_token: str,
    underlying_symbol: str | None = None,
) -> VerifiedSnapshot:
    """
    Fetch a full OHLC+OI+IV snapshot from Kite (primary).
    Falls back to yfinance OHLC for equities (options not available on yfinance).
    """
    kite_coro = asyncio.to_thread(
        _kite_quote_sync, [kite_exchange_symbol], kite_api_key, access_token
    )

    # For equities, run yfinance in parallel for cross-verification
    is_option = any(tag in kite_exchange_symbol for tag in ["CE", "PE", "FUT"])
    if not is_option and underlying_symbol:
        yf_coro = asyncio.to_thread(_yfinance_ltp_sync, underlying_symbol)
        kite_raw, yf_ltp = await asyncio.gather(kite_coro, yf_coro, return_exceptions=True)
    else:
        kite_raw = await kite_coro
        yf_ltp = None

    if isinstance(kite_raw, Exception):
        kite_raw = {}
    if isinstance(yf_ltp, Exception):
        yf_ltp = None

    kite_data = (kite_raw.get(kite_exchange_symbol) or {})
    warnings: list[str] = []
    discrepancy_flagged = False

    if kite_data:
        ohlc = kite_data.get("ohlc", {})
        lp = kite_data.get("last_price")
        try:
            ltp = float(lp) if lp is not None else None
        except (TypeError, ValueError):
            ltp = None

        # Cross-verify for equities
        if not is_option and yf_ltp is not None and ltp is not None:
            try:
                yf_price_f = float(yf_ltp)
                disc = abs(ltp - yf_price_f) / ltp * 100 if ltp > 0 else 0
                if disc > 2.0:
                    discrepancy_flagged = True
                    warnings.append(
                        f"Snapshot discrepancy: Kite ₹{ltp:.2f} vs yfinance ₹{yf_price_f:.2f} ({disc:.1f}%)"
                    )
            except (TypeError, ValueError):
                pass

        return VerifiedSnapshot(
            ltp=ltp,
            day_high=_safe_float(ohlc.get("high")),
            day_low=_safe_float(ohlc.get("low")),
            open=_safe_float(ohlc.get("open")),
            prev_close=_safe_float(kite_data.get("ohlc", {}).get("close") or kite_data.get("last_price")),
            volume=_safe_int(kite_data.get("volume")),
            oi=_safe_int(kite_data.get("oi")),
            iv=_safe_float(kite_data.get("iv")),
            source="kite",
            discrepancy_flagged=discrepancy_flagged,
            warnings=warnings,
        )

    # Kite failed — fall back for equities only
    yf_price: float | None = None
    if yf_ltp is not None:
        try:
            yf_price = float(yf_ltp) if float(yf_ltp) > 0 else None
        except (TypeError, ValueError):
            pass

    if yf_price is not None:
        warnings.append(
            f"Kite snapshot unavailable for {kite_exchange_symbol}; using yfinance fallback"
        )
        return VerifiedSnapshot(
            ltp=yf_price,
            day_high=None, day_low=None, open=None, prev_close=None,
            volume=None, oi=None, iv=None,
            source="yfinance",
            warnings=warnings,
        )

    warnings.append(f"All sources failed for {kite_exchange_symbol}")
    return VerifiedSnapshot(
        ltp=None, day_high=None, day_low=None, open=None, prev_close=None,
        volume=None, oi=None, iv=None,
        source="failed",
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SESSION TIME HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_minutes_to_session_close() -> int:
    """
    Returns minutes remaining until 15:30 IST today.
    Returns 0 if market has already closed for the day.
    Returns 375 (full session) if called pre-market (signals generated before open
    should use the full intraday session duration as their time horizon).
    """
    try:
        import pytz
        from datetime import datetime, time
        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        if now < market_open:
            return 375  # Full session ahead — do NOT return 0 (prevents targets from using full expiry)
        if now >= market_close:
            return 0  # Post-market
        return max(0, int((market_close - now).total_seconds() / 60))
    except Exception:
        return 375  # Default: full session


def is_market_open() -> bool:
    """Returns True if current IST time is within 09:15–15:30."""
    try:
        import pytz
        from datetime import datetime
        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        if now.weekday() >= 5:  # Weekend
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
        from datetime import datetime
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
    B-S convention (365-day year), so premium erodes correctly over non-trading days.

    Parameters:
        entry_price             : option premium at entry
        remaining_trading_days  : trading days to expiry
        best_exit_days          : trading days to planned exit
        india_vix               : India VIX (30-day expected vol, %)
        iv_override             : live IV for this option (%), if available
        calendar_days_to_expiry : actual calendar days to expiry (incl. weekends/holidays)
        calendar_best_exit_days : calendar days to planned exit (incl. non-trading days)

    Returns (theta_decay_total: float, theta_method: str)
    """
    # Determine annualized volatility proxy
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
        theta_method = f"VIX={india_vix:.1f}×{vix_scale:.2f}"
    else:
        sigma = 0.18
        theta_method = "default_18%"

    sigma = max(0.08, min(sigma, 0.80))

    # Use CALENDAR days for the Black-Scholes time parameter (options decay over weekends/holidays).
    # Fall back to trading days if calendar days not provided (legacy callers).
    cal_to_expiry = calendar_days_to_expiry if (calendar_days_to_expiry is not None and calendar_days_to_expiry > 0) else max(remaining_trading_days, 1)
    t = cal_to_expiry / 365.0  # calendar-year convention

    try:
        # Daily theta (calendar day basis): Θ ≈ (premium × σ) / (2 × √(T × 365))
        daily_theta_cal = entry_price * sigma / (2.0 * math.sqrt(max(t, 1 / 365) * 365))
    except (ValueError, ZeroDivisionError):
        daily_theta_cal = entry_price * 0.02

    # How many calendar days of decay to apply (incl. weekends/holidays between now and best exit)
    cal_decay_days = calendar_best_exit_days if (calendar_best_exit_days is not None and calendar_best_exit_days > 0) else max(best_exit_days, 0)

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
    Dynamically revise T1/T2 upward when market conditions support higher profit potential.

    Revision is ALWAYS computed relative to the original targets stored at position creation,
    NOT the already-revised values. This prevents compounding/infinite growth.

    Revision triggers:
    1. LTP has already exceeded T1 → revise T2 up by 1.5× ORIGINAL T2-T1 gap (one-time cap)
    2. Underlying has moved strongly in signal direction (> 0.5% since entry)
       AND VIX has not spiked → increase targets proportionally from ORIGINAL values
    3. Remaining session time is adequate (> 90 min) for target achievement

    Returns (revised_t1, revised_t2, revision_note)
    """
    revised_t1 = current_t1
    revised_t2 = current_t2
    revision_note: str | None = None

    if entry_price <= 0 or current_t1 <= 0 or current_t2 <= 0:
        return revised_t1, revised_t2, None

    # Use original targets for gap/factor calculation to prevent compounding.
    # Fall back to current values only if originals were never stored (legacy positions).
    base_t1 = original_t1 if original_t1 > 0 else current_t1
    base_t2 = original_t2 if original_t2 > 0 else current_t2
    original_gap_t1_t2 = base_t2 - base_t1

    # ── Trigger 1: LTP already exceeded T1 — revise T2 up (non-compounding) ─
    if current_ltp >= current_t1:
        new_t2 = round(base_t1 + original_gap_t1_t2 * 1.5, 2)
        if new_t2 > current_t2:
            revised_t2 = new_t2
            revision_note = f"T1 achieved ₹{current_ltp:.1f} ≥ T1 ₹{current_t1:.1f} — T2 revised up to ₹{new_t2:.1f}"

    # ── Trigger 2: Strong underlying move in signal direction (non-compounding) ─
    if underlying_entry > 0:
        underlying_move_pct = (underlying_ltp - underlying_entry) / underlying_entry * 100
        favorable = (
            (direction == "BULLISH" and underlying_move_pct > 0.5)
            or (direction == "BEARISH" and underlying_move_pct < -0.5)
        )
        vix_calm = india_vix is None or india_vix < 22  # VIX not spiking
        time_adequate = minutes_to_session_close > 90

        if favorable and vix_calm and time_adequate:
            move_factor = min(abs(underlying_move_pct) / 2.0, 0.30)  # cap at 30% increase
            # Apply factor to ORIGINAL targets, not the already-revised ones
            new_t1 = round(base_t1 * (1 + move_factor * 0.5), 2)
            new_t2 = round(base_t2 * (1 + move_factor), 2)
            if new_t1 > revised_t1 or new_t2 > revised_t2:
                revision_note_2 = (
                    f"Strong underlying move {underlying_move_pct:+.1f}% — targets increased "
                    f"T1→₹{new_t1:.1f} T2→₹{new_t2:.1f}"
                )
                revised_t1 = max(revised_t1, new_t1)
                revised_t2 = max(revised_t2, new_t2)
                revision_note = f"{revision_note} | {revision_note_2}" if revision_note else revision_note_2

    # ── Near expiry: cap targets to realistic achievable levels ──────────
    if remaining_trading_days <= 1 and minutes_to_session_close < 120:
        max_realistic_t2 = entry_price * 1.35
        if revised_t2 > max_realistic_t2:
            revised_t2 = max_realistic_t2
            revision_note = (revision_note or "") + " | T2 capped: near expiry + time constraint"

    # ── Absolute safety cap: T2 must never exceed 3× entry (max realistic option gain) ──
    max_absolute_t2 = entry_price * 3.0
    if revised_t2 > max_absolute_t2:
        revised_t2 = max_absolute_t2
        revision_note = (revision_note or "") + f" | T2 hard-capped at 3× entry ₹{max_absolute_t2:.1f}"

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
