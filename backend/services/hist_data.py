"""
Historical OHLCV data — Kite-only, with in-memory + MongoDB cache.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from services.kite_client import _fetch_kite_hist_ohlcv_for_equity
from services.utils import utc_now_iso as _utc_now_iso

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


async def _get_hist_ohlcv(symbol: str, period: str = "1y"):
    """
    Get historical OHLCV as pandas DataFrame with 6h in-memory cache and 12h MongoDB cache.
    Returns pd.DataFrame or None.
    """
    _s = _srv()
    db = _s.db
    now_ts = datetime.now(timezone.utc).timestamp()
    cache_key = f"{symbol}_{period}"

    # In-memory cache
    if cache_key in _s.HIST_OHLCV_CACHE:
        cached = _s.HIST_OHLCV_CACHE[cache_key]
        if (now_ts - cached.get("_ts", 0)) < _s.HIST_OHLCV_CACHE_TTL_SECONDS:
            records = cached.get("records", [])
            if records:
                df = pd.DataFrame(records)
                df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                   "close": "Close", "volume": "Volume"}, inplace=True)
                return df

    # MongoDB cache (12h)
    try:
        cached_doc = await db.hist_ohlcv_cache.find_one({"symbol": symbol, "period": period}, {"_id": 0})
        if cached_doc and (now_ts - float(cached_doc.get("cached_at_ts", 0))) < 43200:
            records = cached_doc.get("records", [])
            if records:
                _s.HIST_OHLCV_CACHE[cache_key] = {"records": records, "_ts": now_ts}
                df = pd.DataFrame(records)
                df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                   "close": "Close", "volume": "Volume"}, inplace=True)
                return df
    except Exception:
        pass

    # Primary (and sole source): Kite historical API
    # No third-party fallback — Kite is the sole historical data source
    raw = await _fetch_kite_hist_ohlcv_for_equity(symbol, period)
    if not raw or not raw.get("records"):
        raw = None

    if not raw or not raw.get("records"):
        return None

    # Store in caches
    _s.HIST_OHLCV_CACHE[cache_key] = {"records": raw["records"], "_ts": now_ts}
    try:
        await db.hist_ohlcv_cache.update_one(
            {"symbol": symbol, "period": period},
            {"$set": {"symbol": symbol, "period": period, "records": raw["records"],
                      "cached_at_ts": now_ts, "updated_at": _utc_now_iso()}},
            upsert=True,
        )
    except Exception:
        pass

    df = pd.DataFrame(raw["records"])
    df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                       "close": "Close", "volume": "Volume"}, inplace=True)
    return df
