"""
Kite Connect Client — All Kite API interactions.

Extracted from server.py for modularity. Uses lazy `import server as _srv`
for accessing server.py globals (db, caches, config) to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
from fastapi import HTTPException

from models import FNOContract, StockCoreNormalized
from services.utils import (
    to_float as _to_float,
    utc_now_iso as _utc_now_iso,
    normalize_symbol_key as _normalize_symbol_key,
    estimate_option_ltp as _estimate_option_ltp,
)
from services.date_utils import today_ist as _today_ist

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module for complex functions not in app_state."""
    import server
    return server


# Import shared state directly — breaks circular import for basic access
from services.app_state import db as _app_db, KITE_API_KEY as _app_kite_key


# ── Kite Access Token ─────────────────────────────────────────────────────────

async def _get_kite_access_token() -> str | None:
    if not _app_kite_key:
        return None
    session = await _app_db.system_meta.find_one({"key": "kite_session"}, {"_id": 0})
    if not session:
        return None
    if session.get("date") != _today_ist():
        return None
    token = str(session.get("access_token", "")).strip()
    return token or None


# ── Kite Equity Core ──────────────────────────────────────────────────────────

async def _fetch_kite_equity_core(symbol: str) -> dict | None:
    """
    Fetch live equity snapshot from Kite /quote API (primary source).
    Uses NSE:SYMBOL format — no instrument token required.
    Falls back to None so callers can use Moneycontrol/RapidAPI.
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY:
        return None
    symbol_upper = symbol.upper().strip()
    if symbol_upper in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}:
        return None

    def _fetch() -> dict | None:
        try:
            resp = requests.get(
                "https://api.kite.trade/quote",
                params=[("i", f"NSE:{symbol_upper}")],
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 10),
            )
            if resp.status_code != 200:
                return None
            row = resp.json().get("data", {}).get(f"NSE:{symbol_upper}", {})
            if not row:
                return None
            ltp = _to_float(row.get("last_price"))
            if ltp is None or ltp <= 0:
                return None
            ohlc = row.get("ohlc") or {}
            return {
                "symbol": symbol_upper,
                "company_name": symbol_upper,
                "ltp": ltp,
                "open": _to_float(ohlc.get("open")),
                "high": _to_float(ohlc.get("high")),
                "low": _to_float(ohlc.get("low")),
                "prev_close": _to_float(ohlc.get("close")),
                "year_high": None,
                "year_low": None,
                "volume": int(_to_float(row.get("volume")) or 0),
                "market_cap": None,
                "pe_ratio": None,
                "book_value": None,
                "eps": None,
                "sector": "NSE",
            }
        except Exception:
            return None

    return await asyncio.to_thread(_fetch)


# ── Kite Batch Quote (NSE:symbol format — no instrument tokens needed) ────────

async def fetch_kite_batch_quotes(symbols: list[str], exchange: str = "NSE") -> dict[str, dict]:
    """
    Fetch live quotes for multiple symbols in a single Kite API call.
    Uses exchange:tradingsymbol format (e.g., NSE:RELIANCE).
    Kite /quote accepts up to 500 instruments per request.
    Returns {symbol: {ltp, open, high, low, prev_close, volume, ...}}
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY or not symbols:
        return {}

    result: dict[str, dict] = {}
    _consecutive_failures = 0

    def _fetch_batch(batch: list[str]) -> dict[str, dict]:
        params = [("i", f"{exchange}:{sym}") for sym in batch]
        try:
            resp = requests.get(
                "https://api.kite.trade/quote",
                params=params,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 8),
            )
            if resp.status_code != 200:
                logger.warning("Kite batch quote HTTP %s: %s", resp.status_code, resp.text[:200])
                return {}
            data = resp.json().get("data", {})
            out: dict[str, dict] = {}
            for key, row in data.items():
                sym = key.split(":")[-1] if ":" in key else key
                ltp = _to_float(row.get("last_price"))
                if ltp is None or ltp <= 0:
                    continue
                ohlc = row.get("ohlc") or {}
                out[sym] = {
                    "ltp": float(ltp),
                    "open": _to_float(ohlc.get("open")),
                    "high": _to_float(ohlc.get("high")),
                    "low": _to_float(ohlc.get("low")),
                    "prev_close": _to_float(ohlc.get("close")),
                    "volume": int(_to_float(row.get("volume")) or 0),
                    "change_pct": round(
                        ((ltp - _to_float(ohlc.get("close"))) / _to_float(ohlc.get("close")) * 100)
                        if _to_float(ohlc.get("close")) else 0,
                        2,
                    ),
                    "oi": _to_float(row.get("oi")),
                }
            return out
        except Exception as exc:
            logger.warning("Kite batch quote failed: %s", exc)
            return {}

    # Kite accepts max 500 per call; batch in chunks of 400
    for idx in range(0, len(symbols), 400):
        if _consecutive_failures >= 2:
            logger.warning("Kite circuit breaker: %d consecutive failures, skipping remaining batches", _consecutive_failures)
            break
        batch = symbols[idx: idx + 400]
        rows = await asyncio.to_thread(_fetch_batch, batch)
        if rows:
            _consecutive_failures = 0
        else:
            _consecutive_failures += 1
        result.update(rows)

    return result


async def fetch_kite_batch_option_quotes(tradingsymbols: list[str]) -> dict[str, dict]:
    """
    Fetch live option quotes using NFO:tradingsymbol format directly.
    No kite_option_master DB lookup needed.
    Returns {tradingsymbol: {ltp, day_high, day_low, oi, iv, ...}}
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY or not tradingsymbols:
        return {}

    result: dict[str, dict] = {}

    def _fetch_batch(batch: list[str]) -> dict[str, dict]:
        params = [("i", f"NFO:{sym}") for sym in batch]
        try:
            resp = requests.get(
                "https://api.kite.trade/quote",
                params=params,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 8),
            )
            if resp.status_code != 200:
                return {}
            data = resp.json().get("data", {})
            out: dict[str, dict] = {}
            for key, row in data.items():
                sym = key.split(":")[-1] if ":" in key else key
                ltp = _to_float(row.get("last_price"))
                ohlc = row.get("ohlc") or {}
                greeks = row.get("greeks") or {}
                out[sym] = {
                    "ltp": float(ltp) if ltp else 0,
                    "day_high": _to_float(ohlc.get("high")),
                    "day_low": _to_float(ohlc.get("low")),
                    "oi": _to_float(row.get("oi")),
                    "volume": int(_to_float(row.get("volume")) or 0),
                    "iv": _to_float(greeks.get("iv")),
                    "delta": _to_float(greeks.get("delta")),
                    "gamma": _to_float(greeks.get("gamma")),
                }
            return out
        except Exception as exc:
            logger.warning("Kite batch option quote failed: %s", exc)
            return {}

    for idx in range(0, len(tradingsymbols), 400):
        batch = tradingsymbols[idx: idx + 400]
        rows = await asyncio.to_thread(_fetch_batch, batch)
        result.update(rows)

    return result


# ── Kite Option Master Sync ──────────────────────────────────────────────────

async def _sync_kite_option_master_daily(force: bool = False) -> None:
    _s = _srv()
    today = _today_ist()
    if not force and _s.KITE_OPTION_MASTER_LAST_SYNC_DATE == today:
        return

    meta = await _s.db.system_meta.find_one({"key": "kite_option_master_sync"}, {"_id": 0})
    if (not force) and meta and meta.get("date") == today and int(meta.get("updated_count", 0) or 0) > 0:
        _s.KITE_OPTION_MASTER_LAST_SYNC_DATE = today
        return

    if not _s.KITE_API_KEY:
        return

    from services.research_engine import get_fo_universe

    def _load_rows() -> tuple[list[dict], list[dict]]:
        try:
            response = requests.get(_s.KITE_SCRIPT_MASTER_URL, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                return [], []

            reader = csv.DictReader(io.StringIO(response.text))
            allowed = {"NIFTY", "BANKNIFTY", *get_fo_universe(lot_size_map=_s.LOT_SIZE_MAP)}
            rows: list[dict] = []
            equity_rows: list[dict] = []
            for row in reader:
                exchange = str(row.get("exchange", "")).upper().strip()
                instrument_type = str(row.get("instrument_type", "")).upper().strip()
                tradingsymbol = str(row.get("tradingsymbol", "")).strip().upper()

                if exchange == "NSE" and instrument_type == "EQ" and tradingsymbol:
                    raw_token = row.get("instrument_token", "")
                    eq_token = None
                    try:
                        eq_token = int(float(str(raw_token).strip())) if raw_token else None
                    except (ValueError, TypeError):
                        eq_token = None
                    if eq_token:
                        equity_rows.append({"symbol": tradingsymbol, "instrument_token": eq_token})

                if exchange != "NFO" or instrument_type not in {"CE", "PE"}:
                    continue

                expiry = str(row.get("expiry", "")).strip()
                strike = _to_float(row.get("strike"))
                tradingsymbol = str(row.get("tradingsymbol", "")).strip().upper()
                if not expiry or strike is None or not tradingsymbol:
                    continue

                raw_name = str(row.get("name", "")).strip().upper()
                underlying = _normalize_symbol_key(raw_name) if raw_name else ""
                if not underlying:
                    underlying = next((symbol for symbol in allowed if tradingsymbol.startswith(symbol)), "")
                if underlying not in allowed:
                    continue

                raw_token = row.get("instrument_token", "")
                numeric_token = None
                try:
                    if raw_token:
                        numeric_token = int(float(str(raw_token).strip()))
                except (ValueError, TypeError):
                    numeric_token = None

                rows.append(
                    {
                        "underlying": underlying,
                        "expiry": expiry,
                        "strike": float(strike),
                        "option_type": instrument_type,
                        "tradingsymbol": tradingsymbol,
                        "instrument": f"NFO:{tradingsymbol}",
                        "instrument_token": numeric_token,
                        "lot_size": int(_to_float(row.get("lot_size")) or _s.LOT_SIZE_MAP.get(underlying, 1)),
                        "updated_at": _utc_now_iso(),
                    }
                )
            return rows, equity_rows
        except Exception as exc:
            logger.warning("Kite option master refresh failed: %s", exc)
            return [], []

    rows, equity_rows = await asyncio.to_thread(_load_rows)
    if not rows:
        return

    await _s.db.kite_option_master.delete_many({})
    for start in range(0, len(rows), 5000):
        await _s.db.kite_option_master.insert_many(rows[start : start + 5000], ordered=False)

    if equity_rows:
        await _s.db.kite_equity_master.delete_many({})
        for start in range(0, len(equity_rows), 5000):
            await _s.db.kite_equity_master.insert_many(equity_rows[start : start + 5000], ordered=False)
        logger.info("Kite equity master synced: %d equity tokens stored", len(equity_rows))

    await _s.db.system_meta.update_one(
        {"key": "kite_option_master_sync"},
        {
            "$set": {
                "key": "kite_option_master_sync",
                "date": today,
                "updated_count": len(rows),
                "updated_at": _utc_now_iso(),
            }
        },
        upsert=True,
    )
    _s.KITE_OPTION_MASTER_LAST_SYNC_DATE = today


# ── Lot Size Resolution ───────────────────────────────────────────────────────

async def _resolve_kite_lot_size_for_script(script: str) -> int | None:
    if not script:
        return None
    _s = _srv()
    await _sync_kite_option_master_daily()
    row = await _s.db.kite_option_master.find_one(
        {"tradingsymbol": script.upper()},
        {"_id": 0, "lot_size": 1},
    )
    if not row:
        return None
    lot_size = int(_to_float(row.get("lot_size")) or 0)
    return lot_size if lot_size > 0 else None


async def _resolve_verified_lot_size(underlying: str, script: str | None = None) -> int:
    if script:
        by_script = await _resolve_kite_lot_size_for_script(script)
        if by_script and by_script > 0:
            return int(by_script)

    _s = _srv()
    await _sync_kite_option_master_daily()
    row = await _s.db.kite_option_master.find_one(
        {"underlying": _normalize_symbol_key(underlying)},
        {"_id": 0, "lot_size": 1},
    )
    if row:
        lot_size = int(_to_float(row.get("lot_size")) or 0)
        if lot_size > 0:
            return lot_size

    mapped = int(_s.LOT_SIZE_MAP.get(_normalize_symbol_key(underlying), 1) or 1)
    return mapped if mapped > 0 else 1


# ── Instrument Resolution ─────────────────────────────────────────────────────

async def _resolve_kite_instrument_for_contract(contract: FNOContract) -> str | None:
    """Returns numeric instrument_token for historical API, falls back to NFO:tradingsymbol."""
    _s = _srv()
    rows = await _s.db.kite_option_master.find(
        {
            "underlying": contract.underlying,
            "expiry": contract.expiry,
            "option_type": contract.option_type,
        },
        {"_id": 0, "instrument": 1, "instrument_token": 1, "strike": 1},
    ).to_list(500)
    if not rows:
        return None

    target_strike = float(contract.strike)
    rows.sort(key=lambda item: abs(float(item.get("strike", 0.0)) - target_strike))
    best = rows[0]
    if abs(float(best.get("strike", 0.0)) - target_strike) > 0.01:
        return None
    numeric_token = best.get("instrument_token")
    if numeric_token and str(numeric_token).isdigit():
        return str(numeric_token)
    instrument = str(best.get("instrument", "")).strip()
    return instrument or None


# ── Option Snapshots ──────────────────────────────────────────────────────────

async def _fetch_option_snapshot_from_kite(contract: FNOContract) -> dict | None:
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY:
        return None

    await _sync_kite_option_master_daily()
    instrument = await _resolve_kite_instrument_for_contract(contract)
    if not instrument:
        return None

    def _fetch_snapshot() -> dict | None:
        try:
            response = requests.get(
                "https://api.kite.trade/quote",
                params={"i": instrument},
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 12),
            )
            if response.status_code != 200:
                return None
            payload = response.json()
            data = payload.get("data", {})
            row = data.get(instrument, {})
            last_price = _to_float(row.get("last_price"))
            if last_price is None or last_price <= 0:
                return None
            ohlc = row.get("ohlc") or {}
            day_high = _to_float(ohlc.get("high"))
            day_low = _to_float(ohlc.get("low"))
            return {
                "ltp": float(last_price),
                "day_high": float(day_high) if day_high is not None else None,
                "day_low": float(day_low) if day_low is not None else None,
            }
        except Exception:
            return None

    return await asyncio.to_thread(_fetch_snapshot)


async def _fetch_option_ltp_from_kite(contract: FNOContract) -> float | None:
    snapshot = await _fetch_option_snapshot_from_kite(contract)
    if not snapshot:
        return None
    return _to_float(snapshot.get("ltp"))


async def _fetch_option_ltps_from_kite(contracts: list[FNOContract]) -> dict[str, float]:
    """
    Fetch option LTPs using Kite /quote/ltp with NFO:tradingsymbol format.
    No kite_option_master DB lookup needed — Kite accepts NFO:tradingsymbol directly.
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY or not contracts:
        return {}

    # Build script → NFO:tradingsymbol mapping directly from contract
    script_to_nfo: dict[str, str] = {}
    for c in contracts:
        script_to_nfo[c.script] = f"NFO:{c.script}"

    nfo_keys = list(script_to_nfo.values())

    def _fetch_batch(batch: list[str]) -> dict[str, float]:
        params = [("i", item) for item in batch]
        try:
            response = requests.get(
                "https://api.kite.trade/quote/ltp",
                params=params,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 15),
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            data = payload.get("data", {})
            rows: dict[str, float] = {}
            for instrument, row in data.items():
                price = _to_float((row or {}).get("last_price"))
                if price is not None and price > 0:
                    rows[instrument] = float(price)
            return rows
        except Exception:
            return {}

    instrument_ltp: dict[str, float] = {}
    for idx in range(0, len(nfo_keys), 200):
        batch = nfo_keys[idx: idx + 200]
        rows = await asyncio.to_thread(_fetch_batch, batch)
        instrument_ltp.update(rows)

    response: dict[str, float] = {}
    for script, nfo_key in script_to_nfo.items():
        value = instrument_ltp.get(nfo_key)
        if value is not None and value > 0:
            response[script] = float(value)
    return response


async def _fetch_option_snapshots_from_kite(contracts: list[FNOContract]) -> dict[str, dict]:
    """
    Fetch option snapshots (LTP, day_high, day_low, OI, IV, greeks) using
    Kite /quote with NFO:tradingsymbol format. No kite_option_master needed.
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY or not contracts:
        return {}

    # Build script → NFO:tradingsymbol mapping directly
    script_to_nfo: dict[str, str] = {}
    for c in contracts:
        script_to_nfo[c.script] = f"NFO:{c.script}"

    nfo_keys = list(set(script_to_nfo.values()))
    instrument_snapshot: dict[str, dict] = {}

    def _fetch_batch(batch: list[str]) -> dict[str, dict]:
        params = [("i", item) for item in batch]
        try:
            response = requests.get(
                "https://api.kite.trade/quote",
                params=params,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 15),
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            data = payload.get("data", {})
            rows: dict[str, dict] = {}
            for instrument, row in data.items():
                ltp = _to_float((row or {}).get("last_price"))
                ohlc = (row or {}).get("ohlc") or {}
                if ltp is None or ltp <= 0:
                    continue
                _greeks = (row or {}).get("greeks") or {}
                rows[instrument] = {
                    "ltp": float(ltp),
                    "day_high": _to_float(ohlc.get("high")),
                    "day_low": _to_float(ohlc.get("low")),
                    "day_open": _to_float(ohlc.get("open")),
                    "oi": _to_float(row.get("oi")),
                    "oi_day_high": _to_float(row.get("oi_day_high")),
                    "oi_day_low": _to_float(row.get("oi_day_low")),
                    "volume": _to_float(row.get("volume")),
                    "iv": _to_float(_greeks.get("iv")),
                    "gamma": _to_float(_greeks.get("gamma")),
                    "delta": _to_float(_greeks.get("delta")),
                }
            return rows
        except Exception:
            return {}

    for idx in range(0, len(nfo_keys), 200):
        batch = nfo_keys[idx: idx + 200]
        rows = await asyncio.to_thread(_fetch_batch, batch)
        instrument_snapshot.update(rows)

    response: dict[str, dict] = {}
    for script, nfo_key in script_to_nfo.items():
        row = instrument_snapshot.get(nfo_key)
        if row and _to_float(row.get("ltp")):
            response[script] = row
    return response


# ── Option Chain Analytics ────────────────────────────────────────────────────

def compute_option_chain_analytics(
    contracts: list,
    kite_map: dict[str, dict],
    underlying_ltp: float,
    step: int = 50,
) -> dict:
    """
    Pure Python computation of option chain analytics from live Kite OI/IV/Gamma data.
    All math strictly in Python — no LLM estimation, per Master Spec rule.
    """
    ce_data: dict[float, dict] = {}
    pe_data: dict[float, dict] = {}

    for contract in contracts:
        snap = kite_map.get(contract.script if hasattr(contract, "script") else str(contract))
        if snap is None:
            continue
        strike = float(contract.strike if hasattr(contract, "strike") else 0)
        oi        = float(snap.get("oi")        or 0)
        ltp       = float(snap.get("ltp")       or 0)
        gamma     = float(snap.get("gamma")     or 0)
        iv        = float(snap.get("iv")        or 0)
        oi_open   = float(snap.get("oi_day_low") or oi)
        day_open  = float(snap.get("day_open")  or ltp)

        record = {"oi": oi, "ltp": ltp, "gamma": gamma, "iv": iv,
                  "oi_open": oi_open, "day_open": day_open}
        opt_type = contract.option_type if hasattr(contract, "option_type") else ""
        if opt_type == "CE":
            ce_data[strike] = record
        elif opt_type == "PE":
            pe_data[strike] = record

    all_strikes = sorted(set(list(ce_data.keys()) + list(pe_data.keys())))
    if not all_strikes:
        return {"max_pain": None, "pcr": None, "iv_rank": None, "gex": None, "oi_buildup": None}

    # 1. Max Pain
    max_pain_strike = None
    min_pain_val = float("inf")
    for test_strike in all_strikes:
        total_pain = 0.0
        for s in all_strikes:
            total_pain += max(0.0, test_strike - s) * ce_data.get(s, {}).get("oi", 0)
            total_pain += max(0.0, s - test_strike) * pe_data.get(s, {}).get("oi", 0)
        if total_pain < min_pain_val:
            min_pain_val = total_pain
            max_pain_strike = test_strike

    # 2. PCR
    total_ce_oi = sum(d["oi"] for d in ce_data.values())
    total_pe_oi = sum(d["oi"] for d in pe_data.values())
    pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else None

    # 3. IV Rank
    atm_strike = round(underlying_ltp / max(step, 1)) * step
    atm_iv = max(
        ce_data.get(atm_strike, {}).get("iv", 0),
        pe_data.get(atm_strike, {}).get("iv", 0),
    )
    all_ivs = [d["iv"] for d in list(ce_data.values()) + list(pe_data.values()) if d["iv"] > 0]
    iv_rank: float | None = None
    if all_ivs and atm_iv > 0:
        iv_min, iv_max = min(all_ivs), max(all_ivs)
        iv_rank = round((atm_iv - iv_min) / (iv_max - iv_min) * 100, 1) if iv_max > iv_min else 50.0

    # 4. GEX
    ce_gex_raw = sum(d["gamma"] * d["oi"] for d in ce_data.values() if d["gamma"] > 0)
    pe_gex_raw = sum(d["gamma"] * d["oi"] for d in pe_data.values() if d["gamma"] > 0)
    gex: float | None = None
    if ce_gex_raw > 0 or pe_gex_raw > 0:
        gex = round((ce_gex_raw - pe_gex_raw) * (underlying_ltp ** 2) / 10_000_000, 2)

    # 5. OI Buildup
    oi_buildup: str | None = None
    atm_ce = ce_data.get(atm_strike, {})
    if atm_ce and atm_ce["oi"] > 0 and atm_ce["oi_open"] > 0:
        oi_chg_pct = (atm_ce["oi"] - atm_ce["oi_open"]) / atm_ce["oi_open"]
        price_chg_pct = (
            (atm_ce["ltp"] - atm_ce["day_open"]) / max(atm_ce["day_open"], 0.01)
            if atm_ce["day_open"] > 0 else 0.0
        )
        oi_up    = oi_chg_pct    > 0.02
        oi_down  = oi_chg_pct    < -0.02
        price_up = price_chg_pct > 0.01
        price_dn = price_chg_pct < -0.01
        if oi_up   and price_up: oi_buildup = "LONG_BUILDUP"
        elif oi_up   and price_dn: oi_buildup = "SHORT_BUILDUP"
        elif oi_down and price_up: oi_buildup = "SHORT_COVERING"
        elif oi_down and price_dn: oi_buildup = "LONG_UNWINDING"
        else: oi_buildup = "NEUTRAL"

    return {
        "max_pain":  float(max_pain_strike) if max_pain_strike is not None else None,
        "pcr":       pcr,
        "iv_rank":   iv_rank,
        "atm_iv":    round(atm_iv, 4) if atm_iv > 0 else None,
        "gex":       gex,
        "oi_buildup": oi_buildup,
    }


# ── Historical OHLCV from Kite ────────────────────────────────────────────────

async def _fetch_kite_hist_ohlcv_for_equity(symbol: str, period: str = "1y") -> dict | None:
    """
    Fetch daily historical OHLCV from Kite for NSE equity instruments.
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY:
        return None

    token_row = await _s.db.kite_equity_master.find_one(
        {"symbol": symbol.upper().strip()}, {"_id": 0, "instrument_token": 1}
    )
    if not token_row or not token_row.get("instrument_token"):
        await _sync_kite_option_master_daily()
        token_row = await _s.db.kite_equity_master.find_one(
            {"symbol": symbol.upper().strip()}, {"_id": 0, "instrument_token": 1}
        )
    if not token_row or not token_row.get("instrument_token"):
        return None

    instrument_token = int(token_row["instrument_token"])
    period_days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
    days = period_days_map.get(period, 365)
    from_dt = datetime.now(timezone.utc) - timedelta(days=days)
    to_dt   = datetime.now(timezone.utc)

    def _fetch():
        try:
            url = (
                f"https://api.kite.trade/instruments/historical/{instrument_token}/day"
                f"?from={from_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
                f"&to={to_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
            )
            resp = requests.get(
                url,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(5, 15),
            )
            if resp.status_code != 200:
                return None
            candles = resp.json().get("data", {}).get("candles", [])
            records = []
            for c in candles:
                if len(c) < 6:
                    continue
                records.append({
                    "date": str(c[0])[:10],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": int(c[5] or 0),
                })
            return {"records": records} if records else None
        except Exception as exc:
            logger.debug("Kite hist OHLCV failed for %s: %s", symbol, exc)
            return None

    return await asyncio.to_thread(_fetch)


# ── Live Option Snapshot (Kite only — no MoneyControl fallback) ───────────────

async def _fetch_live_option_snapshot(contract: FNOContract) -> dict:
    """Fetch live option snapshot from Kite. No MoneyControl fallback per user directive."""
    _s = _srv()
    controls = await _s._get_api_controls()

    if controls.get("kite_data_enabled", True):
        kite_snapshot = await _fetch_option_snapshot_from_kite(contract)
        if kite_snapshot and _to_float(kite_snapshot.get("ltp")):
            return kite_snapshot

    # Last resort: model-based estimation if not strict mode
    if not controls.get("strict_live_only", True):
        core = StockCoreNormalized(**(await _s._get_stock_core_cached(contract.underlying)))
        if core.ltp is not None:
            modeled = _estimate_option_ltp(core.ltp, contract.strike, contract.option_type)
            if modeled > 0:
                return {"ltp": float(modeled), "day_high": None, "day_low": None}

    raise HTTPException(status_code=502, detail=f"Live option LTP unavailable for {contract.script} — ensure Kite is connected")


async def _fetch_live_option_ltp(contract: FNOContract) -> float:
    snapshot = await _fetch_live_option_snapshot(contract)
    return float(snapshot.get("ltp"))


# ── Historical Candles (Minute-level) ─────────────────────────────────────────

async def _fetch_historical_candles_from_kite(contract: FNOContract, interval: str = "minute", candles: int = 10) -> list[dict] | None:
    """
    Fetch historical OHLCV candles from Kite for micro-trend analysis.
    """
    access_token = await _get_kite_access_token()
    _s = _srv()
    if not access_token or not _s.KITE_API_KEY:
        return None

    await _sync_kite_option_master_daily()
    instrument = await _resolve_kite_instrument_for_contract(contract)
    if not instrument:
        return None

    def _fetch_candles() -> list[dict] | None:
        try:
            from_date = datetime.now(_s.IST) - timedelta(minutes=candles + 5)
            to_date = datetime.now(_s.IST)

            response = requests.get(
                f"https://api.kite.trade/instruments/historical/{instrument}/{interval}",
                params={
                    "from": from_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "to": to_date.strftime("%Y-%m-%d %H:%M:%S"),
                },
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                },
                timeout=(3, 5),
            )
            if response.status_code != 200:
                logger.warning(
                    "Historical candles API %s for instrument=%s: %s",
                    response.status_code, instrument, response.text[:300]
                )
                return None

            payload = response.json()
            data = payload.get("data", {})
            candles_data = data.get("candles", [])

            if not candles_data:
                return None

            parsed = []
            for candle in candles_data[-candles:]:
                if len(candle) >= 6:
                    parsed.append({
                        "timestamp": candle[0],
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": int(candle[5]),
                    })
            return parsed if parsed else None
        except Exception as exc:
            logger.warning("Failed to fetch historical candles: %s", exc)
            return None

    return await asyncio.to_thread(_fetch_candles)
