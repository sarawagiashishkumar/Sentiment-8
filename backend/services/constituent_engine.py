"""
Constituent Engine — Section 2 of Master Spec v2.0.

Provides:
  - shared_technical_pipeline(symbol)  per-constituent technical snapshot
  - compute_breadth_metrics(index)     weighted aggregate breadth for index
  - top_contributors(breadth_data)     top 3 bullish/bearish by weight

Uses Kite data via lazy server import. Wraps existing index_constituents.py
and intraday_features.py for the full pipeline.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from services.index_constituents import (
    get_constituents,
    compute_weighted_breadth,
    get_constituents_sync,
)
from services.intraday_features import (
    compute_intraday_technicals,
    compute_vwap_features,
)

logger = logging.getLogger(__name__)


def _srv():
    import server
    return server


async def shared_technical_pipeline(
    symbol: str,
    bars_1m=None,
    bars_5m=None,
    bars_15m=None,
) -> dict[str, Any]:
    """
    Run the shared technical pipeline for a single constituent.
    Uses Kite /quote for live data + daily candles for trend analysis.
    Returns a dict with all fields needed by compute_weighted_breadth.
    """
    _s = _srv()

    result: dict[str, Any] = {
        "symbol": symbol,
        "available": False,
        "in_uptrend": False,
        "above_vwap": False,
        "intraday_return_pct": 0.0,
        "intraday_volatility": None,
        "rsi": None,
        "macd_bullish": False,
        "atr_14": None,
        "trend_1m": "sideways",
        "trend_5m": "sideways",
        "trend_15m": "sideways",
        "trend_alignment_score": 0,
        "vwap_position": "below",
    }

    # Use daily candles for trend + RSI/MACD (always available via Kite)
    try:
        ohlcv_df = await _s._get_hist_ohlcv(symbol, period="3mo")
    except Exception:
        ohlcv_df = None

    if ohlcv_df is None or len(ohlcv_df) < 14:
        # Even without historical data, try Kite /quote for live intraday return
        try:
            from services.kite_client import fetch_kite_batch_quotes
            quotes = await fetch_kite_batch_quotes([symbol])
            q = quotes.get(symbol, {})
            if q.get("ltp") and q.get("prev_close"):
                result["available"] = True
                result["intraday_return_pct"] = q["change_pct"]
                result["in_uptrend"] = q["change_pct"] > 0
                result["above_vwap"] = q["ltp"] > q["prev_close"]  # approximation
        except Exception:
            pass
        return result

    result["available"] = True
    closes = ohlcv_df["Close"].tolist()
    highs = ohlcv_df["High"].tolist()
    lows = ohlcv_df["Low"].tolist()

    import pandas as pd
    import numpy as np

    # RSI(14)
    if len(closes) >= 14:
        delta = ohlcv_df["Close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        result["rsi"] = round(rsi_val, 1) if rsi_val == rsi_val else None

    # MACD (12,26,9)
    if len(closes) >= 26:
        ema12 = ohlcv_df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = ohlcv_df["Close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        result["macd_bullish"] = float(macd_line.iloc[-1]) > float(signal_line.iloc[-1])

    # ATR(14)
    if len(ohlcv_df) >= 14:
        tr = pd.concat([
            ohlcv_df["High"] - ohlcv_df["Low"],
            (ohlcv_df["High"] - ohlcv_df["Close"].shift(1)).abs(),
            (ohlcv_df["Low"] - ohlcv_df["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_val = float(tr.rolling(14).mean().iloc[-1])
        result["atr_14"] = round(atr_val, 2) if atr_val == atr_val else None

    # Trend from daily EMA(9/21)
    def _classify_trend(close_series) -> str:
        if len(close_series) < 21:
            return "sideways"
        ema9 = close_series.ewm(span=9, adjust=False).mean()
        ema21 = close_series.ewm(span=21, adjust=False).mean()
        if float(ema9.iloc[-1]) > float(ema21.iloc[-1]) * 1.001:
            return "up"
        elif float(ema9.iloc[-1]) < float(ema21.iloc[-1]) * 0.999:
            return "down"
        return "sideways"

    trend_daily = _classify_trend(ohlcv_df["Close"])
    result["trend_5m"] = trend_daily
    result["trend_15m"] = trend_daily

    # Intraday return from Kite /quote
    try:
        from services.kite_client import fetch_kite_batch_quotes
        quotes = await fetch_kite_batch_quotes([symbol])
        q = quotes.get(symbol, {})
        if q.get("ltp") and q.get("prev_close"):
            result["intraday_return_pct"] = q["change_pct"]
            result["above_vwap"] = q["ltp"] > q["prev_close"]
            result["trend_1m"] = "up" if q["change_pct"] > 0.3 else ("down" if q["change_pct"] < -0.3 else "sideways")
    except Exception:
        pass

    # Trend alignment
    trends = [result["trend_1m"], result["trend_5m"], result["trend_15m"]]
    up_count = trends.count("up")
    down_count = trends.count("down")
    result["trend_alignment_score"] = max(up_count, down_count)
    result["in_uptrend"] = up_count >= 2

    return result


async def compute_breadth_metrics(
    db,
    index_name: Literal["NIFTY", "BANKNIFTY"],
    concurrency: int = 5,
) -> dict[str, Any]:
    """
    Compute full breadth metrics for an index.

    1. Fetch constituents + weights
    2. Run shared_technical_pipeline for each (with concurrency limit)
    3. Aggregate using compute_weighted_breadth
    4. Add top3 bullish/bearish contributors

    Returns dict with all breadth fields + contributors.
    """
    weights = await get_constituents(db, index_name)
    if not weights:
        weights = get_constituents_sync(index_name)

    if not weights:
        logger.warning(f"No constituents for {index_name}")
        return {
            "index_name": index_name,
            "pct_weight_in_uptrend": 50.0,
            "pct_weight_above_vwap": 50.0,
            "weighted_avg_intraday_return": 0.0,
            "weighted_avg_atr": 0.0,
            "breadth_score": 50.0,
            "top3_bullish": [],
            "top3_bearish": [],
            "constituents_scanned": 0,
        }

    symbols = list(weights.keys())

    # Run pipeline with concurrency limiter
    sem = asyncio.Semaphore(concurrency)

    async def _scan(sym: str):
        async with sem:
            try:
                return await shared_technical_pipeline(sym)
            except Exception as exc:
                logger.debug(f"Pipeline failed for {sym}: {exc}")
                return {"symbol": sym, "available": False}

    tasks = [_scan(sym) for sym in symbols]
    results = await asyncio.gather(*tasks)

    # Build constituent_data list for weighted breadth
    constituent_data = []
    for r in results:
        sym = r.get("symbol", "")
        w = weights.get(sym, 0.0)
        constituent_data.append({
            "symbol": sym,
            "weight_pct": w,
            "in_uptrend": r.get("in_uptrend", False),
            "above_vwap": r.get("above_vwap", False),
            "intraday_return_pct": r.get("intraday_return_pct", 0.0),
            "intraday_volatility": r.get("intraday_volatility", 0.0),
            "rsi": r.get("rsi"),
            "macd_bullish": r.get("macd_bullish", False),
            "atr_14": r.get("atr_14"),
            "trend_alignment_score": r.get("trend_alignment_score", 0),
            "trend_15m": r.get("trend_15m", "sideways"),
            "vwap_position": r.get("vwap_position", "below"),
            "available": r.get("available", False),
        })

    # Compute weighted breadth
    breadth = compute_weighted_breadth(constituent_data, index_name)

    # Weighted avg ATR
    total_w = sum(d["weight_pct"] for d in constituent_data if d["atr_14"])
    if total_w > 0:
        weighted_atr = sum(
            (d["atr_14"] or 0) * d["weight_pct"]
            for d in constituent_data if d["atr_14"]
        ) / total_w
    else:
        weighted_atr = 0.0

    # Top 3 bullish contributors (by weight in uptrend)
    bullish_sorted = sorted(
        [d for d in constituent_data if d["in_uptrend"]],
        key=lambda x: x["weight_pct"], reverse=True,
    )
    top3_bullish = [
        {"symbol": d["symbol"], "weight": d["weight_pct"],
         "return_pct": d["intraday_return_pct"]}
        for d in bullish_sorted[:3]
    ]

    # Top 3 bearish contributors (by weight in downtrend)
    bearish_sorted = sorted(
        [d for d in constituent_data if not d["in_uptrend"] and d.get("available")],
        key=lambda x: x["weight_pct"], reverse=True,
    )
    top3_bearish = [
        {"symbol": d["symbol"], "weight": d["weight_pct"],
         "return_pct": d["intraday_return_pct"]}
        for d in bearish_sorted[:3]
    ]

    return {
        "index_name": index_name,
        **breadth,
        "weighted_avg_atr": round(weighted_atr, 2),
        "top3_bullish": top3_bullish,
        "top3_bearish": top3_bearish,
        "constituents_scanned": sum(1 for d in constituent_data if d["available"]),
        "constituent_data": constituent_data,
    }


def top_contributors(
    breadth_result: dict[str, Any],
    direction: Literal["bullish", "bearish"] = "bullish",
    n: int = 3,
) -> list[dict]:
    """Extract top N contributors from breadth_result."""
    key = f"top3_{direction}"
    return breadth_result.get(key, [])[:n]
