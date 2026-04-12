"""
Historical OHLCV data — Kite-only, with in-memory + MongoDB cache.
Uses app_state for DB/cache access — no circular server import.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

import services.app_state as _state
from services.kite_client import _fetch_kite_hist_ohlcv_for_equity

logger = logging.getLogger(__name__)

# In-memory cache (populated at runtime)
_HIST_CACHE: dict = {}
_HIST_CACHE_TTL = 21600  # 6 hours


async def _get_hist_ohlcv(symbol: str, period: str = "1y"):
    """Get historical OHLCV as pandas DataFrame with 6h in-memory + 12h MongoDB cache."""
    db = _state.db
    if db is None:
        return None

    now_ts = datetime.now(timezone.utc).timestamp()
    cache_key = f"{symbol}_{period}"

    # In-memory cache (6h)
    cached = _HIST_CACHE.get(cache_key)
    if cached and (now_ts - cached.get("_ts", 0)) < _HIST_CACHE_TTL:
        records = cached.get("records", [])
        if records:
            return _records_to_df(records)

    # MongoDB cache (12h)
    try:
        cached_doc = await db.hist_ohlcv_cache.find_one(
            {"symbol": symbol, "period": period}, {"_id": 0}
        )
        if cached_doc and (now_ts - float(cached_doc.get("cached_at_ts", 0))) < 43200:
            records = cached_doc.get("records", [])
            if records:
                _HIST_CACHE[cache_key] = {"records": records, "_ts": now_ts}
                return _records_to_df(records)
    except Exception:
        pass

    # Fetch from Kite
    raw = await _fetch_kite_hist_ohlcv_for_equity(symbol, period)
    if not raw or not raw.get("records"):
        return None

    records = raw["records"]
    _HIST_CACHE[cache_key] = {"records": records, "_ts": now_ts}

    # Persist to MongoDB
    try:
        await db.hist_ohlcv_cache.update_one(
            {"symbol": symbol, "period": period},
            {"$set": {
                "symbol": symbol, "period": period, "records": records,
                "cached_at_ts": now_ts, "updated_at": _state._utc_now_iso(),
            }},
            upsert=True,
        )
    except Exception:
        pass

    return _records_to_df(records)


def _records_to_df(records: list) -> pd.DataFrame:
    """Convert OHLCV records to standardized DataFrame."""
    df = pd.DataFrame(records)
    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }, inplace=True)
    return df
