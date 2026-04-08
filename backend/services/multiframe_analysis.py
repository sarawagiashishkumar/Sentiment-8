"""
Multi-timeframe Analysis — Detailed per-timeframe technical analysis.

Provides enriched multi-TF data beyond the existing compute_multiframe_trend,
including per-frame indicators (RSI, MACD direction, BB position, volume trend).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def compute_detailed_multiframe(hist: pd.DataFrame, symbol: str = "") -> dict[str, Any]:
    """
    Compute detailed multi-timeframe analysis from daily OHLCV data.
    Returns per-timeframe (Daily, Weekly, Monthly) indicators.
    """
    if hist is None or len(hist) < 50:
        return {
            "symbol": symbol,
            "data_available": False,
            "frames": {},
            "alignment": "INSUFFICIENT_DATA",
        }

    frames = {}

    # Daily (last 20 bars)
    daily = hist.tail(20).copy()
    frames["daily"] = _analyze_frame(daily, "Daily")

    # Weekly (resample or subsample)
    try:
        if isinstance(hist.index, pd.DatetimeIndex):
            weekly = hist.resample("W").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna().tail(12)
        else:
            weekly = hist.tail(60).iloc[::5].copy()
        frames["weekly"] = _analyze_frame(weekly, "Weekly")
    except Exception:
        frames["weekly"] = {"label": "Weekly", "trend": "NEUTRAL", "indicators": {}}

    # Monthly (resample or subsample)
    try:
        if isinstance(hist.index, pd.DatetimeIndex):
            monthly = hist.resample("ME").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna().tail(6)
        else:
            monthly = hist.tail(126).iloc[::21].copy()
        frames["monthly"] = _analyze_frame(monthly, "Monthly")
    except Exception:
        frames["monthly"] = {"label": "Monthly", "trend": "NEUTRAL", "indicators": {}}

    # Alignment
    trends = [f.get("trend", "NEUTRAL") for f in frames.values()]
    bull = trends.count("BULLISH")
    bear = trends.count("BEARISH")
    if bull == 3:
        alignment = "STRONGLY_BULLISH"
    elif bull >= 2:
        alignment = "BULLISH"
    elif bear == 3:
        alignment = "STRONGLY_BEARISH"
    elif bear >= 2:
        alignment = "BEARISH"
    else:
        alignment = "MIXED"

    return {
        "symbol": symbol,
        "data_available": True,
        "frames": frames,
        "alignment": alignment,
        "bullish_frames": bull,
        "bearish_frames": bear,
    }


def _analyze_frame(df: pd.DataFrame, label: str) -> dict[str, Any]:
    """Analyze a single timeframe DataFrame."""
    if df is None or len(df) < 3:
        return {"label": label, "trend": "NEUTRAL", "indicators": {}}

    close = df["Close"]
    high = df["High"] if "High" in df.columns else close
    low = df["Low"] if "Low" in df.columns else close

    # Trend via EMA crossover
    fast_ema = close.ewm(span=max(3, len(close) // 4), adjust=False).mean()
    slow_ema = close.ewm(span=max(5, len(close) // 2), adjust=False).mean()

    if float(fast_ema.iloc[-1]) > float(slow_ema.iloc[-1]) and float(close.iloc[-1]) > float(close.mean()):
        trend = "BULLISH"
    elif float(fast_ema.iloc[-1]) < float(slow_ema.iloc[-1]) and float(close.iloc[-1]) < float(close.mean()):
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    # RSI (simple)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(min(14, max(3, len(close) - 1))).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(min(14, max(3, len(close) - 1))).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(rs.dropna()) > 0 else 50.0

    # Bollinger position
    sma20 = close.rolling(min(20, len(close))).mean()
    std20 = close.rolling(min(20, len(close))).std()
    bb_upper = (sma20 + 2 * std20).iloc[-1] if len(std20.dropna()) > 0 else float(close.iloc[-1])
    bb_lower = (sma20 - 2 * std20).iloc[-1] if len(std20.dropna()) > 0 else float(close.iloc[-1])
    bb_mid = float(sma20.iloc[-1]) if len(sma20.dropna()) > 0 else float(close.iloc[-1])
    current = float(close.iloc[-1])

    bb_range = float(bb_upper) - float(bb_lower) if float(bb_upper) != float(bb_lower) else 1
    bb_pct = round((current - float(bb_lower)) / bb_range * 100, 1)

    # MACD direction
    ema12 = close.ewm(span=min(12, len(close)), adjust=False).mean()
    ema26 = close.ewm(span=min(26, len(close)), adjust=False).mean()
    macd_line = float(ema12.iloc[-1]) - float(ema26.iloc[-1])
    macd_dir = "BULLISH" if macd_line > 0 else "BEARISH"

    # Volume trend
    vol_trend = "NEUTRAL"
    if "Volume" in df.columns and len(df) >= 5:
        vol = df["Volume"]
        vol_avg = float(vol.tail(5).mean())
        vol_prev = float(vol.tail(10).head(5).mean()) if len(vol) >= 10 else vol_avg
        if vol_avg > vol_prev * 1.2:
            vol_trend = "RISING"
        elif vol_avg < vol_prev * 0.8:
            vol_trend = "DECLINING"

    # Price change
    pct_change = round((current / float(close.iloc[0]) - 1) * 100, 2) if float(close.iloc[0]) > 0 else 0

    return {
        "label": label,
        "trend": trend,
        "indicators": {
            "rsi": round(rsi, 1),
            "macd_direction": macd_dir,
            "bb_position_pct": bb_pct,
            "volume_trend": vol_trend,
            "price_change_pct": pct_change,
            "close": round(current, 2),
            "high": round(float(high.max()), 2),
            "low": round(float(low.min()), 2),
        },
    }
