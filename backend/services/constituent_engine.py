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
    Returns a dict with all fields needed by compute_weighted_breadth:
      symbol, weight_pct, in_uptrend, above_vwap,
      intraday_return_pct, intraday_volatility, rsi, macd_bullish,
      atr_14, trend_1m, trend_5m, trend_15m, trend_alignment_score,
      vwap_position, sector_rank_today (filled later by caller)
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

    # Fetch OHLCV from Kite (1-minute bars for intraday)
    try:
        ohlcv = await _s._get_hist_ohlcv(symbol, interval="minute", candles=375)
    except Exception:
        ohlcv = None

    if not ohlcv or not ohlcv.get("closes"):
        return result

    import pandas as pd
    closes = ohlcv["closes"]
    highs = ohlcv.get("highs", closes)
    lows = ohlcv.get("lows", closes)
    opens = ohlcv.get("opens", closes)
    volumes = ohlcv.get("volumes", [0] * len(closes))

    if len(closes) < 10:
        return result

    bars_df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows,
        "Close": closes, "Volume": volumes,
    })

    result["available"] = True

    # Intraday technicals (RSI, MACD, stochastic, return, volatility)
    tech = compute_intraday_technicals(bars_df)
    result["rsi"] = tech.get("rsi_14")
    result["intraday_return_pct"] = tech.get("intraday_return_pct", 0.0)
    result["intraday_volatility"] = tech.get("intraday_volatility")
    macd_data = tech.get("macd")
    result["macd_bullish"] = macd_data.get("bullish", False) if isinstance(macd_data, dict) else False

    # ATR(14) from bars
    if len(bars_df) >= 14:
        tr = pd.concat([
            bars_df["High"] - bars_df["Low"],
            (bars_df["High"] - bars_df["Close"].shift(1)).abs(),
            (bars_df["Low"] - bars_df["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_val = float(tr.rolling(14).mean().iloc[-1])
        result["atr_14"] = round(atr_val, 2) if atr_val == atr_val else None
    else:
        result["atr_14"] = None

    # VWAP features
    vwap = compute_vwap_features(bars_df, current_ltp=closes[-1], atr=result["atr_14"])
    result["above_vwap"] = vwap.get("above_vwap", False)
    result["vwap_position"] = "above" if result["above_vwap"] else "below"

    # Trend per timeframe (using EMA 9/21 cross on resampled bars)
    def _classify_trend(df: pd.DataFrame) -> str:
        if df is None or len(df) < 21:
            return "sideways"
        close = df["Close"]
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        if float(ema9.iloc[-1]) > float(ema21.iloc[-1]) * 1.001:
            return "up"
        elif float(ema9.iloc[-1]) < float(ema21.iloc[-1]) * 0.999:
            return "down"
        return "sideways"

    result["trend_1m"] = _classify_trend(bars_df)

    # Resample to 5m and 15m
    try:
        bars_5m_df = bars_df.iloc[::5].reset_index(drop=True) if len(bars_df) >= 25 else None
        bars_15m_df = bars_df.iloc[::15].reset_index(drop=True) if len(bars_df) >= 45 else None
    except Exception:
        bars_5m_df = None
        bars_15m_df = None

    result["trend_5m"] = _classify_trend(bars_5m_df) if bars_5m_df is not None else "sideways"
    result["trend_15m"] = _classify_trend(bars_15m_df) if bars_15m_df is not None else "sideways"

    # Trend alignment score (0-4: count of timeframes in same direction)
    trends = [result["trend_1m"], result["trend_5m"], result["trend_15m"]]
    up_count = trends.count("up")
    down_count = trends.count("down")
    result["trend_alignment_score"] = max(up_count, down_count)
    result["in_uptrend"] = up_count >= 2  # majority uptrend

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
