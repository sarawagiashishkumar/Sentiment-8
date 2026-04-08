"""
IV Analytics — IV Cone + IV Term Structure computation.

Provides:
  - IV Cone: Percentile bands (10th, 25th, 50th, 75th, 90th) from historical IV data
  - IV Term Structure: IV values across different expiry dates
  - Background IV collection for all F&O symbols
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION_IV = "iv_history"
COLLECTION_IV_TERM = "iv_term_structure"


async def compute_iv_cone(db, symbol: str, lookback_days: int = 365) -> dict:
    """
    Compute IV Cone for a symbol using historical ATM IV data.
    Returns percentile bands (10th, 25th, 50th, 75th, 90th) + daily IV points.
    Works with whatever data is available.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cursor = db[COLLECTION_IV].find(
        {"underlying": symbol, "ts": {"$gte": cutoff}},
        {"_id": 0, "date": 1, "atm_iv": 1},
    ).sort("ts", 1)

    points = []
    async for doc in cursor:
        if doc.get("atm_iv") and doc.get("atm_iv") > 0:
            points.append({"date": doc["date"], "iv": round(doc["atm_iv"] * 100, 2)})

    if not points:
        return {
            "symbol": symbol,
            "data_points": 0,
            "points": [],
            "bands": None,
            "current_iv": None,
            "message": "No IV history data yet. Data will accumulate as signals are generated.",
        }

    ivs = [p["iv"] for p in points]
    ivs_sorted = sorted(ivs)
    n = len(ivs_sorted)

    def percentile(pct):
        k = (n - 1) * (pct / 100)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(ivs_sorted[int(k)], 2)
        return round(ivs_sorted[f] * (c - k) + ivs_sorted[c] * (k - f), 2)

    bands = {
        "p10": percentile(10),
        "p25": percentile(25),
        "p50": percentile(50),
        "p75": percentile(75),
        "p90": percentile(90),
        "min": round(min(ivs), 2),
        "max": round(max(ivs), 2),
        "mean": round(sum(ivs) / n, 2),
    }

    current_iv = points[-1]["iv"] if points else None

    return {
        "symbol": symbol,
        "data_points": n,
        "points": points,
        "bands": bands,
        "current_iv": current_iv,
        "lookback_days": lookback_days,
    }


async def capture_iv_term_structure(
    db, symbol: str, expiry_iv_map: dict[str, float],
) -> None:
    """
    Store IV term structure snapshot: IV for each expiry date.
    expiry_iv_map: {"2026-04-28": 0.32, "2026-05-26": 0.28, ...}
    """
    if not expiry_iv_map:
        return
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    doc = {
        "symbol": symbol,
        "date": date_str,
        "expiry_ivs": {k: round(v, 4) for k, v in expiry_iv_map.items() if v and v > 0},
        "ts": now,
    }
    try:
        await db[COLLECTION_IV_TERM].update_one(
            {"symbol": symbol, "date": date_str},
            {"$set": doc},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"IV term structure capture failed for {symbol}: {e}")


async def get_iv_term_structure(db, symbol: str) -> dict:
    """
    Get latest IV term structure for a symbol.
    Returns IV values mapped to days-to-expiry.
    """
    doc = await db[COLLECTION_IV_TERM].find_one(
        {"symbol": symbol},
        {"_id": 0},
        sort=[("ts", -1)],
    )

    if not doc or not doc.get("expiry_ivs"):
        return {
            "symbol": symbol,
            "data_points": 0,
            "term_points": [],
            "message": "No term structure data yet. Generate F&O Projections to capture IV data.",
        }

    now = datetime.now(timezone.utc)
    term_points = []
    for expiry_str, iv_val in sorted(doc["expiry_ivs"].items()):
        try:
            expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            dte = max(0, (expiry_dt - now).days)
            term_points.append({
                "expiry": expiry_str,
                "dte": dte,
                "iv": round(iv_val * 100, 2),
            })
        except (ValueError, TypeError):
            continue

    return {
        "symbol": symbol,
        "data_points": len(term_points),
        "term_points": term_points,
        "captured_at": doc.get("date", ""),
    }


async def ensure_iv_analytics_indexes(db) -> None:
    """Create indexes for IV analytics collections."""
    await db[COLLECTION_IV_TERM].create_index(
        [("symbol", 1), ("date", 1)],
        unique=True,
        name="iv_term_symbol_date_unique",
    )
    await db[COLLECTION_IV_TERM].create_index(
        [("symbol", 1), ("ts", -1)],
        name="iv_term_symbol_ts_desc",
    )
    logger.info("IV analytics indexes ensured")
