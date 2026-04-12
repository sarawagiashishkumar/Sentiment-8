"""
Risk Dashboard — Portfolio-level risk metrics aggregation.
"""
import logging
import math
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

risk_router = APIRouter()


@risk_router.get("/risk/portfolio-summary")
async def portfolio_risk_summary(current_user: dict = Depends(get_current_user)):
    """Aggregate portfolio-level risk metrics from open positions and journal history."""
    user_key = current_user.get("user_key", "")

    # Get open custom positions
    positions = await _state.db.custom_positions.find(
        {"user_key": user_key, "status": {"$in": ["OPEN", "ACTIVE"]}},
        {"_id": 0},
    ).to_list(100)

    # Compute aggregate Greeks
    total_delta = 0
    total_theta = 0
    total_vega = 0
    total_margin = 0
    symbols_set = set()
    position_values = []

    for p in positions:
        total_delta += p.get("delta", 0) * p.get("quantity", 1)
        total_theta += p.get("theta", 0) * p.get("quantity", 1)
        total_vega += p.get("vega", 0) * p.get("quantity", 1)
        total_margin += p.get("margin_required", 0)
        symbols_set.add(p.get("symbol") or p.get("underlying", ""))
        ltp = p.get("ltp", 0) or p.get("premium_ltp", 0)
        qty = p.get("quantity", 1)
        position_values.append({"symbol": p.get("symbol", ""), "value": ltp * qty, "pnl": p.get("unrealized_pnl", 0)})

    # Max drawdown from journal
    cutoff_30d = datetime.now(timezone.utc).timestamp() - 30 * 86400
    journal_cursor = _state.db.trading_journal.find(
        {"user_key": user_key, "event_type": "position_closed", "ts_epoch": {"$gte": cutoff_30d}},
        {"_id": 0, "pnl": 1, "ts_epoch": 1},
    ).sort("ts_epoch", 1).limit(500)
    closed_entries = await journal_cursor.to_list(500)

    running_equity = 100000
    peak = running_equity
    max_drawdown = 0
    equity_curve = []
    for e in closed_entries:
        running_equity += e.get("pnl", 0)
        if running_equity > peak:
            peak = running_equity
        dd = (peak - running_equity) / peak * 100 if peak > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd
        equity_curve.append({"pnl": e.get("pnl", 0), "equity": round(running_equity, 2)})

    # Position correlation (simple: same underlying = correlated)
    underlying_groups = {}
    for p in positions:
        und = p.get("underlying") or p.get("symbol", "")
        if und not in underlying_groups:
            underlying_groups[und] = 0
        underlying_groups[und] += 1
    correlated_pairs = sum(1 for c in underlying_groups.values() if c > 1)

    # Concentration risk
    total_value = sum(abs(pv["value"]) for pv in position_values) or 1
    concentration = [{"symbol": pv["symbol"], "pct": round(abs(pv["value"]) / total_value * 100, 1)} for pv in position_values]
    concentration.sort(key=lambda x: x["pct"], reverse=True)

    return {
        "open_positions": len(positions),
        "unique_symbols": len(symbols_set),
        "greeks": {
            "net_delta": round(total_delta, 2),
            "net_theta": round(total_theta, 2),
            "net_vega": round(total_vega, 2),
        },
        "margin": {
            "total_required": round(total_margin, 2),
        },
        "drawdown": {
            "max_drawdown_30d_pct": round(max_drawdown, 2),
            "closed_trades_30d": len(closed_entries),
        },
        "correlation": {
            "correlated_pairs": correlated_pairs,
            "underlying_groups": underlying_groups,
        },
        "concentration": concentration[:10],
        "equity_curve": equity_curve[-50:],
    }
