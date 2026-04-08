"""
52-Week IV History — Stores and retrieves ATM Implied Volatility
snapshots per underlying for true IV Rank (percentile) computation.

Collection: iv_history
Schema:
  { underlying: str, date: str (YYYY-MM-DD), atm_iv: float, ts: datetime }

Index: (underlying, date) unique compound — one snapshot per day per underlying.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

COLLECTION = "iv_history"
LOOKBACK_DAYS = 365  # ~252 trading days


async def ensure_indexes(db) -> None:
    """Create compound index on (underlying, date) if not exists."""
    coll = db[COLLECTION]
    await coll.create_index(
        [("underlying", 1), ("date", 1)],
        unique=True,
        name="underlying_date_unique",
    )
    await coll.create_index(
        [("underlying", 1), ("ts", -1)],
        name="underlying_ts_desc",
    )
    logger.info("iv_history indexes ensured")


async def capture_atm_iv(
    db,
    underlying: str,
    atm_iv: float,
    ts: datetime | None = None,
) -> bool:
    """
    Store a daily ATM IV snapshot. Upserts on (underlying, date).
    Returns True if a new document was inserted, False if updated.
    """
    if atm_iv is None or atm_iv <= 0:
        return False

    now = ts or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    result = await db[COLLECTION].update_one(
        {"underlying": underlying, "date": date_str},
        {
            "$set": {
                "atm_iv": round(atm_iv, 4),
                "ts": now,
            },
            "$setOnInsert": {
                "underlying": underlying,
                "date": date_str,
            },
        },
        upsert=True,
    )
    return result.upserted_id is not None


async def get_iv_history(
    db,
    underlying: str,
    days: int = LOOKBACK_DAYS,
) -> list[float]:
    """
    Retrieve up to `days` of historical ATM IV values,
    sorted oldest to newest.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = db[COLLECTION].find(
        {"underlying": underlying, "ts": {"$gte": cutoff}},
        {"_id": 0, "atm_iv": 1},
    ).sort("ts", 1)

    return [doc["atm_iv"] async for doc in cursor if doc.get("atm_iv")]


async def get_iv_rank_52w(
    db,
    underlying: str,
    current_atm_iv: float | None,
) -> float | None:
    """
    Compute true 52-week IV Rank (percentile) for the given underlying.

    IV Rank = (count of historical IVs <= current IV) / total count * 100

    Returns None if insufficient history (<20 data points) or no current IV.
    """
    if current_atm_iv is None or current_atm_iv <= 0:
        return None

    history = await get_iv_history(db, underlying)
    if len(history) < 20:
        return None

    below = sum(1 for iv in history if iv <= current_atm_iv)
    rank = round((below / len(history)) * 100, 1)
    return rank


async def get_iv_stats_52w(
    db,
    underlying: str,
    current_atm_iv: float | None,
) -> dict:
    """
    Full 52-week IV statistics for enriched signal display.
    Returns dict with iv_rank_52w, iv_min_52w, iv_max_52w, iv_mean_52w,
    history_days, or empty values if insufficient data.
    """
    if current_atm_iv is None or current_atm_iv <= 0:
        return {"iv_rank_52w": None, "history_days": 0}

    history = await get_iv_history(db, underlying)
    n = len(history)
    if n < 20:
        return {"iv_rank_52w": None, "history_days": n}

    below = sum(1 for iv in history if iv <= current_atm_iv)
    rank = round((below / n) * 100, 1)

    return {
        "iv_rank_52w": rank,
        "iv_min_52w": round(min(history), 2),
        "iv_max_52w": round(max(history), 2),
        "iv_mean_52w": round(sum(history) / n, 2),
        "history_days": n,
    }
