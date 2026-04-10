"""
Server-level cache helpers and DB lookup utilities.
Extracted from server.py for modularity.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ── In-memory caches ──────────────────────────────────────────────────────────
API_CONTROL_CACHE: dict[str, object] = {
    "kite_data_enabled": True,
    "moneycontrol_data_enabled": True,
    "strict_live_only": True,
}
API_CONTROL_CACHE_TS: datetime | None = None

STOCK_CORE_CACHE: dict[str, dict] = {}
STOCK_CORE_CACHE_TTL_SECONDS = 20

INDIA_VIX_CACHE: dict = {}
INDIA_VIX_CACHE_TTL_SECONDS = 300

FUNDAMENTAL_CACHE: dict[str, dict] = {}
FUNDAMENTAL_CACHE_TTL_SECONDS = 86400

HIST_OHLCV_CACHE: dict[str, dict] = {}
HIST_OHLCV_CACHE_TTL_SECONDS = 21600  # 6 hours

SECTOR_MOMENTUM_CACHE: dict = {}
SECTOR_MOMENTUM_CACHE_TTL_SECONDS = 1800  # 30 minutes


def _normalize_symbol_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


async def get_api_controls(db, force_refresh: bool = False) -> dict[str, bool]:
    global API_CONTROL_CACHE_TS
    now = datetime.now(IST)
    if (
        (not force_refresh)
        and API_CONTROL_CACHE_TS is not None
        and (now - API_CONTROL_CACHE_TS).total_seconds() < 45
    ):
        return {
            "kite_data_enabled": bool(API_CONTROL_CACHE.get("kite_data_enabled", True)),
            "moneycontrol_data_enabled": bool(API_CONTROL_CACHE.get("moneycontrol_data_enabled", True)),
            "strict_live_only": bool(API_CONTROL_CACHE.get("strict_live_only", True)),
        }

    row = await db.system_meta.find_one({"key": "api_controls"}, {"_id": 0})
    if row:
        API_CONTROL_CACHE["kite_data_enabled"] = bool(row.get("kite_data_enabled", True))
        API_CONTROL_CACHE["moneycontrol_data_enabled"] = bool(row.get("moneycontrol_data_enabled", True))
        API_CONTROL_CACHE["strict_live_only"] = bool(row.get("strict_live_only", True))
    API_CONTROL_CACHE_TS = now
    return {
        "kite_data_enabled": bool(API_CONTROL_CACHE.get("kite_data_enabled", True)),
        "moneycontrol_data_enabled": bool(API_CONTROL_CACHE.get("moneycontrol_data_enabled", True)),
        "strict_live_only": bool(API_CONTROL_CACHE.get("strict_live_only", True)),
    }


async def get_stock_core_cached(db, symbol: str) -> dict:
    from services.kite_client import _fetch_kite_equity_core
    from services.market_data import get_stock_core

    key = _normalize_symbol_key(symbol)
    now = datetime.now(timezone.utc).timestamp()
    cached = STOCK_CORE_CACHE.get(key)
    if cached and (now - float(cached.get("ts", 0))) <= STOCK_CORE_CACHE_TTL_SECONDS:
        return cached["data"]

    data = await _fetch_kite_equity_core(symbol)
    if data is None:
        data = await get_stock_core(symbol)
    STOCK_CORE_CACHE[key] = {"ts": now, "data": data}
    return data


async def get_active_macro_events(db) -> list[str]:
    """Read currently active macro events from MongoDB (macro_config collection)."""
    try:
        from services.research_engine import get_all_macro_events
        rec = await db["macro_config"].find_one({"config_id": "active_events"}, {"_id": 0})
        if rec and isinstance(rec.get("events"), list):
            valid = set(get_all_macro_events())
            return [e for e in rec["events"] if e in valid]
    except Exception as exc:
        logger.warning("Failed to read active macro events from DB: %s", exc)
    return []


async def get_strategy_stats_for_selection(db) -> dict[str, dict]:
    """Load aggregated strategy backtest stats from MongoDB."""
    try:
        records = await db.strategy_backtest.find({}, {"_id": 0}).to_list(length=500)
        agg: dict[str, dict] = {}
        for r in records:
            sid = r.get("strategy_id", "UNKNOWN")
            if sid not in agg:
                agg[sid] = {"wins": 0, "total_trades": 0, "total_r_multiple": 0.0, "disabled": False}
            agg[sid]["total_trades"] += 1
            if r.get("win"):
                agg[sid]["wins"] += 1
            agg[sid]["total_r_multiple"] += r.get("r_multiple", 0.0)
            if r.get("disabled"):
                agg[sid]["disabled"] = True
        stats_map: dict[str, dict] = {}
        for sid, s in agg.items():
            total = s["total_trades"]
            stats_map[sid] = {
                "win_rate": s["wins"] / total if total > 0 else 0.0,
                "expectancy": s["total_r_multiple"] / total if total > 0 else 0.0,
                "disabled": s["disabled"],
            }
        return stats_map
    except Exception as exc:
        logger.warning("Failed to load strategy stats for selection: %s", exc)
        return {}
