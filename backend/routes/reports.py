"""
Aggregated Reporting Engine — Daily/Weekly P&L reports.
"""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

reports_router = APIRouter()


async def _aggregate_report(user_key: str, from_ts: float, to_ts: float) -> dict:
    """Build aggregated report from journal + signals + perf history.
    Uses MongoDB aggregation pipelines for server-side computation."""
    # Journal entries in range
    journal_cursor = _state.db.trading_journal.find(
        {"user_key": user_key, "ts_epoch": {"$gte": from_ts, "$lte": to_ts}},
        {"_id": 0},
    ).sort("ts_epoch", -1).limit(500)
    journal_entries = await journal_cursor.to_list(500)

    signals = [e for e in journal_entries if e.get("event_type") == "signal_generated"]
    closed = [e for e in journal_entries if e.get("event_type") == "position_closed"]

    total_pnl = sum(e.get("pnl", 0) for e in closed)
    wins = [e for e in closed if (e.get("pnl") or 0) > 0]
    losses = [e for e in closed if (e.get("pnl") or 0) < 0]

    best_trade = max(closed, key=lambda e: e.get("pnl", 0), default=None)
    worst_trade = min(closed, key=lambda e: e.get("pnl", 0), default=None)

    # Symbol exposure via MongoDB aggregation pipeline (server-side grouping)
    symbol_pipeline = [
        {"$match": {"user_key": user_key, "ts_epoch": {"$gte": from_ts, "$lte": to_ts}, "event_type": "signal_generated"}},
        {"$group": {"_id": "$symbol", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    symbol_cursor = _state.db.trading_journal.aggregate(symbol_pipeline)
    top_symbols = [{"symbol": doc["_id"], "count": doc["count"]} async for doc in symbol_cursor]

    # Quality distribution via aggregation
    quality_pipeline = [
        {"$match": {"user_key": user_key, "ts_epoch": {"$gte": from_ts, "$lte": to_ts}, "event_type": "signal_generated"}},
        {"$group": {"_id": {"$ifNull": ["$signal_quality", "UNKNOWN"]}, "count": {"$sum": 1}}},
    ]
    quality_cursor = _state.db.trading_journal.aggregate(quality_pipeline)
    quality_dist = {doc["_id"]: doc["count"] async for doc in quality_cursor}

    # Generation perf in range — use aggregation for avg
    from_iso = datetime.fromtimestamp(from_ts, tz=timezone.utc).isoformat()
    to_iso = datetime.fromtimestamp(to_ts, tz=timezone.utc).isoformat()
    perf_pipeline = [
        {"$match": {"ts": {"$gte": from_iso, "$lte": to_iso}}},
        {"$group": {"_id": None, "avg_total_ms": {"$avg": "$total_ms"}, "count": {"$sum": 1}}},
    ]
    perf_cursor = _state.db.generation_perf_history.aggregate(perf_pipeline)
    perf_docs = await perf_cursor.to_list(1)
    avg_gen_time = round(perf_docs[0]["avg_total_ms"]) if perf_docs and perf_docs[0].get("avg_total_ms") else 0
    gen_runs = perf_docs[0]["count"] if perf_docs else 0

    return {
        "total_signals": len(signals),
        "closed_trades": len(closed),
        "total_pnl": round(total_pnl, 2),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / max(len(wins) + len(losses), 1) * 100, 1),
        "best_trade": {"symbol": best_trade.get("symbol"), "pnl": best_trade.get("pnl")} if best_trade else None,
        "worst_trade": {"symbol": worst_trade.get("symbol"), "pnl": worst_trade.get("pnl")} if worst_trade else None,
        "top_symbols": top_symbols,
        "quality_distribution": quality_dist,
        "generation_runs": gen_runs,
        "avg_generation_ms": avg_gen_time,
        "journal_entries": journal_entries[:50],
    }


@reports_router.get("/reports/daily-summary")
async def daily_summary(
    date: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    """Get daily P&L report. Default: today."""
    user_key = current_user.get("user_key", "")
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            target = datetime.now(timezone.utc)
    else:
        target = datetime.now(timezone.utc)

    from_ts = target.replace(hour=0, minute=0, second=0).timestamp()
    to_ts = target.replace(hour=23, minute=59, second=59).timestamp()

    report = await _aggregate_report(user_key, from_ts, to_ts)
    report["period"] = "daily"
    report["date"] = target.strftime("%Y-%m-%d")
    return report


@reports_router.get("/reports/weekly-summary")
async def weekly_summary(current_user: dict = Depends(get_current_user)):
    """Get weekly P&L report (last 7 days)."""
    user_key = current_user.get("user_key", "")
    now = datetime.now(timezone.utc)
    from_ts = (now - timedelta(days=7)).timestamp()
    to_ts = now.timestamp()

    report = await _aggregate_report(user_key, from_ts, to_ts)
    report["period"] = "weekly"
    report["from_date"] = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    report["to_date"] = now.strftime("%Y-%m-%d")
    return report
