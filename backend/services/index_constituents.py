"""
Index Constituents & Breadth Metrics — Section 2 of Master Spec.

Maintains NIFTY 50 and BANKNIFTY constituent weights in a DB-backed table
with a clean abstraction layer. Computes weighted breadth aggregates for
use in regime classification and Confluence Score Bucket B.

All calculations are pure Python. NO LLM numeric work.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 2.1  Hardcoded constituent weights (refreshable via DB or config)
# ---------------------------------------------------------------------------
# Source: NSE Index Factsheet (approximate as of Apr 2026).
# Designed so that updating the data source later (scraper/NSEpy)
# requires NO logic changes — only this table changes.

_NIFTY50_CONSTITUENTS: dict[str, float] = {
    "HDFCBANK": 13.10, "RELIANCE": 9.60, "ICICIBANK": 8.40, "INFY": 6.00,
    "TCS": 4.40, "BHARTIARTL": 4.10, "ITC": 3.80, "LT": 3.50,
    "AXISBANK": 3.10, "KOTAKBANK": 2.80, "SBIN": 2.70, "BAJFINANCE": 2.40,
    "HCLTECH": 2.30, "MARUTI": 1.80, "SUNPHARMA": 1.70, "TITAN": 1.60,
    "NTPC": 1.55, "TATAMOTORS": 1.50, "ADANIENT": 1.45, "POWERGRID": 1.40,
    "M&M": 1.35, "ONGC": 1.30, "ULTRACEMCO": 1.25, "TATASTEEL": 1.20,
    "ASIANPAINT": 1.15, "NESTLEIND": 1.10, "JSWSTEEL": 1.05, "INDUSINDBK": 1.00,
    "WIPRO": 0.95, "BAJAJFINSV": 0.90, "TECHM": 0.85, "GRASIM": 0.80,
    "HINDALCO": 0.78, "COALINDIA": 0.75, "DRREDDY": 0.73, "HDFCLIFE": 0.70,
    "SBILIFE": 0.68, "DIVISLAB": 0.65, "CIPLA": 0.63, "EICHERMOT": 0.60,
    "APOLLOHOSP": 0.58, "HEROMOTOCO": 0.55, "BPCL": 0.53, "TATACONSUM": 0.50,
    "BRITANNIA": 0.48, "BAJAJ-AUTO": 0.45, "ADANIPORTS": 0.43, "UPL": 0.40,
    "SHRIRAMFIN": 0.38, "BEL": 0.35,
}

_BANKNIFTY_CONSTITUENTS: dict[str, float] = {
    "HDFCBANK": 29.00, "ICICIBANK": 23.00, "KOTAKBANK": 13.00,
    "AXISBANK": 11.00, "SBIN": 10.00, "INDUSINDBK": 4.00,
    "BANDHANBNK": 2.00, "FEDERALBNK": 2.00, "AUBANK": 2.00,
    "PNB": 1.50, "CANBK": 1.50, "BANKBARODA": 1.00,
}

# In-memory cache (refreshed from DB if available)
_constituent_cache: dict[str, dict[str, float]] = {
    "NIFTY": dict(_NIFTY50_CONSTITUENTS),
    "BANKNIFTY": dict(_BANKNIFTY_CONSTITUENTS),
}
_constituent_cache_ts: datetime | None = None

# MongoDB collection name for persistent storage
COLLECTION_NAME = "index_constituents"


async def _ensure_db_table(db) -> None:
    """Seed DB with hardcoded weights if collection is empty."""
    coll = db[COLLECTION_NAME]
    count = await coll.count_documents({})
    if count > 0:
        return
    docs = []
    for index_name, members in [("NIFTY", _NIFTY50_CONSTITUENTS), ("BANKNIFTY", _BANKNIFTY_CONSTITUENTS)]:
        for symbol, weight_pct in members.items():
            docs.append({
                "index_name": index_name,
                "symbol": symbol,
                "weight_pct": weight_pct,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
    if docs:
        await coll.insert_many(docs)
        logger.info(f"Seeded {len(docs)} index constituent records into DB")


async def get_constituents(db, index_name: str) -> dict[str, float]:
    """
    Return {symbol: weight_pct} for the given index.
    Tries DB first, falls back to hardcoded cache.
    """
    global _constituent_cache, _constituent_cache_ts
    # Try DB
    try:
        coll = db[COLLECTION_NAME]
        cursor = coll.find({"index_name": index_name}, {"_id": 0, "symbol": 1, "weight_pct": 1})
        result = {}
        async for doc in cursor:
            result[doc["symbol"]] = doc["weight_pct"]
        if result:
            _constituent_cache[index_name] = result
            _constituent_cache_ts = datetime.now(timezone.utc)
            return result
    except Exception as e:
        logger.warning(f"DB fetch for {index_name} constituents failed: {e}")

    return _constituent_cache.get(index_name, {})


async def update_constituents(db, index_name: str, weights: dict[str, float]) -> int:
    """
    Update constituent weights for an index.
    Returns number of records upserted.
    """
    coll = db[COLLECTION_NAME]
    count = 0
    now = datetime.now(timezone.utc).isoformat()
    for symbol, weight_pct in weights.items():
        await coll.update_one(
            {"index_name": index_name, "symbol": symbol},
            {"$set": {"weight_pct": weight_pct, "updated_at": now}},
            upsert=True,
        )
        count += 1
    # Update cache
    _constituent_cache[index_name] = dict(weights)
    _constituent_cache_ts = datetime.now(timezone.utc)
    logger.info(f"Updated {count} constituents for {index_name}")
    return count


def get_constituents_sync(index_name: str) -> dict[str, float]:
    """Synchronous accessor for cached constituents (no DB call)."""
    return dict(_constituent_cache.get(index_name, {}))


def get_all_nifty500_symbols() -> list[str]:
    """
    Return full NIFTY 500 universe symbols.
    For now returns NIFTY 50 + known F&O stocks as a starting point.
    This list will be expanded as we add dynamic index constituency parsing.
    """
    # Start with NIFTY 50 constituents
    symbols = set(_NIFTY50_CONSTITUENTS.keys())
    # Add BANKNIFTY constituents
    symbols.update(_BANKNIFTY_CONSTITUENTS.keys())
    return sorted(symbols)


# ---------------------------------------------------------------------------
# 2.2  Index breadth metrics (weighted)
# ---------------------------------------------------------------------------

def compute_weighted_breadth(
    constituent_data: list[dict[str, Any]],
    index_name: str,
) -> dict[str, Any]:
    """
    Compute weighted breadth aggregates for an index.

    Each item in constituent_data should have:
      - symbol: str
      - weight_pct: float
      - in_uptrend: bool (True if stock is trending up on multi-TF)
      - above_vwap: bool (True if LTP > VWAP)
      - intraday_return_pct: float (today's return %)
      - intraday_volatility: float (today's realized vol, annualized)
      - rsi: float | None
      - macd_bullish: bool

    Returns:
      - pct_weight_in_uptrend: float (0-100)
      - pct_weight_above_vwap: float (0-100)
      - weighted_avg_intraday_return: float
      - weighted_avg_intraday_volatility: float
      - breadth_score: float (0-100, composite)
      - bullish_count: int
      - bearish_count: int
      - total_weight_covered: float
    """
    if not constituent_data:
        return {
            "pct_weight_in_uptrend": 50.0,
            "pct_weight_above_vwap": 50.0,
            "weighted_avg_intraday_return": 0.0,
            "weighted_avg_intraday_volatility": 0.0,
            "breadth_score": 50.0,
            "bullish_count": 0,
            "bearish_count": 0,
            "total_weight_covered": 0.0,
        }

    weights_map = _constituent_cache.get(index_name, {})
    total_weight = 0.0
    uptrend_weight = 0.0
    above_vwap_weight = 0.0
    weighted_return = 0.0
    weighted_vol = 0.0
    bullish = 0
    bearish = 0

    for item in constituent_data:
        sym = item.get("symbol", "")
        w = item.get("weight_pct") or weights_map.get(sym, 1.0)
        total_weight += w

        if item.get("in_uptrend", False):
            uptrend_weight += w
            bullish += 1
        else:
            bearish += 1

        if item.get("above_vwap", False):
            above_vwap_weight += w

        ret = item.get("intraday_return_pct", 0.0) or 0.0
        vol = item.get("intraday_volatility", 0.0) or 0.0
        weighted_return += ret * w
        weighted_vol += vol * w

    if total_weight <= 0:
        total_weight = 1.0

    pct_uptrend = round((uptrend_weight / total_weight) * 100, 1)
    pct_above_vwap = round((above_vwap_weight / total_weight) * 100, 1)
    avg_return = round(weighted_return / total_weight, 3)
    avg_vol = round(weighted_vol / total_weight, 3)

    # Composite breadth score: blend of uptrend%, VWAP%, and return direction
    breadth_score = (
        0.40 * pct_uptrend
        + 0.35 * pct_above_vwap
        + 0.25 * min(100, max(0, 50 + avg_return * 10))  # normalize return to 0-100 scale
    )
    breadth_score = round(min(100, max(0, breadth_score)), 1)

    return {
        "pct_weight_in_uptrend": pct_uptrend,
        "pct_weight_above_vwap": pct_above_vwap,
        "weighted_avg_intraday_return": avg_return,
        "weighted_avg_intraday_volatility": avg_vol,
        "breadth_score": breadth_score,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "total_weight_covered": round(total_weight, 1),
    }
