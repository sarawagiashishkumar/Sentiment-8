"""
FNO Backtest route handlers.

Strategy simulation and backtest endpoints extracted from fno.py.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from deps import get_current_user, get_owner_user
from services.backtest_engine import (
    is_strategy_enabled as is_backtest_enabled,
    run_backtest_batch,
)

logger = logging.getLogger(__name__)

fno_backtest_router = APIRouter()


class RunBacktestRequest(BaseModel):
    symbol: str
    strategy: str
    date_from: str
    date_to: str


@fno_backtest_router.post("/fno/backtest-batch")
async def trigger_backtest_batch(current_user: dict = Depends(get_owner_user)):
    """Run strategy backtests for all strategy x instrument combinations. Owner-only."""
    import server as _srv
    from services.strategy_library import STRATEGY_LIBRARY

    result = await run_backtest_batch(_srv.db, STRATEGY_LIBRARY)
    return result


@fno_backtest_router.get("/fno/strategy-backtests")
async def list_strategy_backtests_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """List all strategy backtest records with their enable/disable status."""
    import server as _srv

    rows = await _srv.db.strategy_backtests.find({}, {"_id": 0}).to_list(500)
    for r in rows:
        r["enabled"] = is_backtest_enabled(r)
    return {"backtests": rows, "count": len(rows)}


@fno_backtest_router.post("/fno/run-backtest")
async def run_single_backtest(
    req: RunBacktestRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run a single strategy backtest for the given symbol and date range."""
    from services.kite_client import fetch_kite_historical_candles

    symbol = req.symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "Symbol required")

    try:
        from datetime import datetime as _dt
        d_from = _dt.strptime(req.date_from, "%Y-%m-%d")
        d_to = _dt.strptime(req.date_to, "%Y-%m-%d")
        days = max((d_to - d_from).days, 1)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    candles = await fetch_kite_historical_candles(symbol, interval="day", days=min(days + 5, 365))
    if not candles:
        return {"summary": {}, "trades": [], "equity_curve": [],
                "error": f"No historical data available for {symbol}. Ensure Market Data API is connected."}

    trades, equity_curve = run_strategy_simulation(candles, req.strategy)

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    total_pnl = sum(t["pnl"] for t in trades)

    peak = 100000
    max_dd = 0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = (peak - pt["equity"]) / peak * 100
        if dd > max_dd:
            max_dd = dd

    summary = {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / max(len(trades), 1) * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "max_drawdown": round(max_dd, 1),
        "profit_factor": round(sum(t["pnl"] for t in wins) / max(abs(sum(t["pnl"] for t in losses)), 0.01), 2) if losses else 0,
        "sharpe_ratio": round(total_pnl / max(len(trades), 1) / max(1, (sum((t["pnl"] - total_pnl/max(len(trades),1))**2 for t in trades) / max(len(trades),1))**0.5), 2) if trades else 0,
        "strategy": req.strategy,
    }

    return {"summary": summary, "trades": trades, "equity_curve": equity_curve}


def run_strategy_simulation(candles: list[dict], strategy: str) -> tuple[list[dict], list[dict]]:
    """Run strategy-specific simulation on OHLCV candles. Returns (trades, equity_curve)."""
    trades = []
    equity = 100000
    equity_curve = []
    lot = 10

    def _date_str(c):
        d = c.get("date", "")
        return d[:10] if isinstance(d, str) else str(d)

    if strategy in ("momentum_ce", "momentum_pe"):
        is_long = strategy == "momentum_ce"
        for i in range(2, len(candles)):
            prev2, curr = candles[i - 2], candles[i]
            equity_curve.append({"date": _date_str(curr), "equity": round(equity, 2)})
            momentum = (curr["close"] - prev2["close"]) / prev2["close"] * 100
            trigger = (is_long and momentum > 0.5) or (not is_long and momentum < -0.5)
            if trigger and i + 1 < len(candles):
                exit_c = candles[i + 1]
                pnl = ((exit_c["close"] - curr["close"]) if is_long else (curr["close"] - exit_c["close"])) * lot
                equity += pnl
                trades.append({"entry_date": _date_str(curr), "exit_date": _date_str(exit_c), "direction": "LONG" if is_long else "SHORT", "entry_price": round(curr["close"], 2), "exit_price": round(exit_c["close"], 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl / (curr["close"] * lot) * 100, 2), "holding_days": 1, "legs": 1})

    elif strategy == "bull_call_spread":
        for i in range(2, len(candles)):
            curr = candles[i]
            equity_curve.append({"date": _date_str(curr), "equity": round(equity, 2)})
            if i < 3:
                continue
            prev = candles[i - 1]
            if curr["close"] > prev["close"] and prev["close"] > candles[i - 2]["close"] and i + 2 < len(candles):
                entry = curr["close"]
                premium_paid = entry * 0.02
                exit_c = candles[i + 2]
                spread_gain = max(exit_c["close"] - entry, 0) * 0.5 - premium_paid
                pnl = spread_gain * lot
                equity += pnl
                trades.append({"entry_date": _date_str(curr), "exit_date": _date_str(exit_c), "direction": "LONG", "entry_price": round(entry, 2), "exit_price": round(exit_c["close"], 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl / (premium_paid * lot) * 100, 2), "holding_days": 2, "legs": 2, "strategy_type": "Bull Call Spread"})

    elif strategy == "bear_put_spread":
        for i in range(2, len(candles)):
            curr = candles[i]
            equity_curve.append({"date": _date_str(curr), "equity": round(equity, 2)})
            if i < 3:
                continue
            prev = candles[i - 1]
            if curr["close"] < prev["close"] and prev["close"] < candles[i - 2]["close"] and i + 2 < len(candles):
                entry = curr["close"]
                premium_paid = entry * 0.02
                exit_c = candles[i + 2]
                spread_gain = max(entry - exit_c["close"], 0) * 0.5 - premium_paid
                pnl = spread_gain * lot
                equity += pnl
                trades.append({"entry_date": _date_str(curr), "exit_date": _date_str(exit_c), "direction": "SHORT", "entry_price": round(entry, 2), "exit_price": round(exit_c["close"], 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl / (premium_paid * lot) * 100, 2), "holding_days": 2, "legs": 2, "strategy_type": "Bear Put Spread"})

    elif strategy in ("straddle", "iron_condor", "butterfly", "calendar_spread"):
        for i in range(3, len(candles)):
            curr = candles[i]
            equity_curve.append({"date": _date_str(curr), "equity": round(equity, 2)})
            if i + 3 >= len(candles):
                continue
            avg_price = curr["close"]
            premium_collected = avg_price * 0.015

            exit_c = candles[i + 3]
            actual_move = abs(exit_c["close"] - curr["close"])

            if strategy == "straddle":
                pnl = (premium_collected * 2 - actual_move) * lot
            elif strategy == "iron_condor":
                pnl = (premium_collected * 1.5 - max(actual_move - avg_price * 0.01, 0)) * lot
            elif strategy == "butterfly":
                center_dist = actual_move / avg_price * 100
                pnl = (premium_collected - abs(center_dist) * avg_price * 0.005) * lot
            else:  # calendar_spread
                theta_decay = premium_collected * 0.3
                pnl = (theta_decay - actual_move * 0.3) * lot

            equity += pnl
            legs = {"straddle": 2, "iron_condor": 4, "butterfly": 3, "calendar_spread": 2}
            trades.append({"entry_date": _date_str(curr), "exit_date": _date_str(exit_c), "direction": "NEUTRAL", "entry_price": round(avg_price, 2), "exit_price": round(exit_c["close"], 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl / (premium_collected * lot) * 100, 2), "holding_days": 3, "legs": legs.get(strategy, 2), "strategy_type": strategy.replace("_", " ").title()})

    else:
        for i in range(1, len(candles)):
            curr = candles[i]
            equity_curve.append({"date": _date_str(curr), "equity": round(equity, 2)})
            if i + 1 < len(candles):
                exit_c = candles[i + 1]
                pnl = (exit_c["close"] - curr["close"]) * lot
                equity += pnl
                trades.append({"entry_date": _date_str(curr), "exit_date": _date_str(exit_c), "direction": "LONG", "entry_price": round(curr["close"], 2), "exit_price": round(exit_c["close"], 2), "pnl": round(pnl, 2), "holding_days": 1, "legs": 1})

    return trades, equity_curve
