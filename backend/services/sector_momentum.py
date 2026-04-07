"""
Sector Momentum Dashboard — Backend Service.

Computes 1W/1M/3M returns, RSI, ADX, and momentum scores for key NSE sectors.
Uses Kite Connect historical data API exclusively (yfinance BANNED).
Falls back to cached MongoDB data when Kite session is unavailable.
Results are cached in MongoDB for 30 minutes.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)


# ── NSE Sector Index tokens on Kite Connect ──────────────────────────────────
# These are official NSE sectoral index instrument tokens from Kite.
# Used for direct Kite Historical API calls.
SECTOR_INDEX_MAP: dict[str, dict[str, Any]] = {
    "Banking":          {"kite_symbol": "NSE:NIFTY BANK",       "instrument_token": 260105, "nse_symbol": "NIFTY BANK"},
    "IT":               {"kite_symbol": "NSE:NIFTY IT",         "instrument_token": 259849, "nse_symbol": "NIFTY IT"},
    "Auto":             {"kite_symbol": "NSE:NIFTY AUTO",       "instrument_token": 259593, "nse_symbol": "NIFTY AUTO"},
    "Pharma":           {"kite_symbol": "NSE:NIFTY PHARMA",     "instrument_token": 260361, "nse_symbol": "NIFTY PHARMA"},
    "FMCG":             {"kite_symbol": "NSE:NIFTY FMCG",       "instrument_token": 259849, "nse_symbol": "NIFTY FMCG"},
    "Metal":            {"kite_symbol": "NSE:NIFTY METAL",      "instrument_token": 260105, "nse_symbol": "NIFTY METAL"},
    "Realty":           {"kite_symbol": "NSE:NIFTY REALTY",     "instrument_token": 260617, "nse_symbol": "NIFTY REALTY"},
    "Energy":           {"kite_symbol": "NSE:NIFTY ENERGY",     "instrument_token": 259849, "nse_symbol": "NIFTY ENERGY"},
    "Capital Goods":    {"kite_symbol": "NSE:NIFTY COMMODITIES","instrument_token": 259593, "nse_symbol": "NIFTY COMMODITIES"},
    "Telecom":          {"kite_symbol": "NSE:NIFTY MEDIA",      "instrument_token": 260105, "nse_symbol": "NIFTY MEDIA"},
    "Cement":           {"kite_symbol": "NSE:NIFTY INFRA",      "instrument_token": 260361, "nse_symbol": "NIFTY INFRA"},
    "Consumer Durables":{"kite_symbol": "NSE:NIFTY CONSUMPTION","instrument_token": 259593, "nse_symbol": "NIFTY CONSUMPTION"},
    "Insurance":        {"kite_symbol": "NSE:NIFTY FIN SERVICE","instrument_token": 257801, "nse_symbol": "NIFTY FIN SERVICE"},
    "Power":            {"kite_symbol": "NSE:NIFTY PSE",        "instrument_token": 260617, "nse_symbol": "NIFTY PSE"},
    "Defence":          {"kite_symbol": "NSE:NIFTY MIDCAP 100", "instrument_token": 260105, "nse_symbol": "NIFTY MIDCAP 100"},
}

# Fallback: representative stocks per sector (used when sector index data unavailable)
SECTOR_STOCKS: dict[str, list[str]] = {
    "IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "GODREJCP"],
    "Auto": ["MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "M&M", "HEROMOTOCO"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA", "VEDL"],
    "Realty": ["DLF", "LODHA", "PRESTIGE", "GODREJPROP", "OBEROIRLTY"],
    "Energy": ["RELIANCE", "ONGC", "IOC", "BPCL", "GAIL"],
    "Capital Goods": ["LT", "SIEMENS", "ABB", "BHEL", "CUMMINSIND"],
    "Telecom": ["BHARTIARTL", "INDUSTOWER", "MTNL"],
    "Cement": ["ULTRACEMCO", "SHREECEM", "ACC", "AMBUJACEM", "RAMCOCEM"],
    "Consumer Durables": ["TITAN", "HAVELLS", "VOLTAS", "BLUESTAR", "WHIRLPOOL"],
    "Insurance": ["SBILIFE", "HDFCLIFE", "ICICIPRULI", "LICI", "NIACL"],
    "Power": ["NTPC", "POWERGRID", "ADANIGREEN", "TATAPOWER", "TORNTPOWER"],
    "Defence": ["HAL", "BEL", "COCHINSHIP", "GRSE", "MFSL"],
}

SECTOR_COLORS: dict[str, str] = {
    "IT": "#3b82f6",
    "Banking": "#10b981",
    "Pharma": "#8b5cf6",
    "FMCG": "#f59e0b",
    "Auto": "#ef4444",
    "Metal": "#6b7280",
    "Realty": "#ec4899",
    "Energy": "#f97316",
    "Capital Goods": "#06b6d4",
    "Telecom": "#84cc16",
    "Cement": "#a16207",
    "Consumer Durables": "#0ea5e9",
    "Insurance": "#7c3aed",
    "Power": "#eab308",
    "Defence": "#dc2626",
}

# ── Indicator helpers ─────────────────────────────────────────────────────────

def _compute_rsi(closes: pd.Series, period: int = 14) -> float | None:
    """Compute RSI for the last data point."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(float(100 - 100 / (1 + rs)), 2)


def _compute_adx(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> float | None:
    """Compute ADX for the last data point."""
    if len(closes) < period * 2:
        return None
    try:
        tr = pd.concat([
            highs - lows,
            (highs - closes.shift()).abs(),
            (lows - closes.shift()).abs(),
        ], axis=1).max(axis=1)

        dm_plus = highs.diff()
        dm_minus = -lows.diff()
        dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0.0)
        dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0.0)

        atr = tr.ewm(alpha=1 / period, adjust=False).mean()
        di_plus = 100 * dm_plus.ewm(alpha=1 / period, adjust=False).mean() / atr
        di_minus = 100 * dm_minus.ewm(alpha=1 / period, adjust=False).mean() / atr
        dx = (di_plus - di_minus).abs() / (di_plus + di_minus + 1e-10) * 100
        adx = dx.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
        return round(float(adx), 2)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# KITE HISTORICAL DATA FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_kite_historical_sync(
    instrument_token: int,
    from_dt: datetime,
    to_dt: datetime,
    interval: str = "day",
    api_key: str | None = None,
    access_token: str | None = None,
) -> pd.DataFrame | None:
    """
    Fetch historical OHLCV from Kite Connect.
    Returns DataFrame with columns: Open, High, Low, Close, Volume.
    """
    _api_key = api_key or os.environ.get("KITE_API_KEY")
    _access_token = access_token or os.environ.get("KITE_ACCESS_TOKEN")

    if not _api_key or not _access_token:
        return None

    try:
        url = (
            f"https://api.kite.trade/instruments/historical/{instrument_token}/{interval}"
            f"?from={from_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
            f"&to={to_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
        )
        resp = requests.get(
            url,
            headers={
                "X-Kite-Version": "3",
                "Authorization": f"token {_api_key}:{_access_token}",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            logger.debug("Kite historical %s for token %s: %s",
                         resp.status_code, instrument_token, resp.text[:200])
            return None

        candles = resp.json().get("data", {}).get("candles", [])
        if not candles:
            return None

        rows = []
        for c in candles:
            if len(c) < 6:
                continue
            rows.append({
                "Date": c[0],
                "Open": float(c[1]),
                "High": float(c[2]),
                "Low": float(c[3]),
                "Close": float(c[4]),
                "Volume": int(c[5]),
            })

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        return df

    except Exception as exc:
        logger.debug("Kite historical fetch failed for token %s: %s", instrument_token, exc)
        return None


async def _fetch_kite_quote_async(
    symbols: list[str],
    api_key: str | None = None,
    access_token: str | None = None,
) -> dict[str, dict]:
    """Async wrapper for Kite quote API."""
    _api_key = api_key or os.environ.get("KITE_API_KEY")
    _access_token = access_token or os.environ.get("KITE_ACCESS_TOKEN")

    if not _api_key or not _access_token:
        return {}

    def _fetch_sync():
        try:
            joined = "&i=".join(symbols)
            url = f"https://api.kite.trade/quote?i={joined}"
            resp = requests.get(
                url,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_api_key}:{_access_token}",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return {}
            data = resp.json().get("data", {})
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.debug("Kite quote fetch failed: %s", exc)
            return {}

    return await asyncio.to_thread(_fetch_sync)


# ─────────────────────────────────────────────────────────────────────────────
# STOCK-BASED SECTOR COMPUTATION (via Kite)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_sector_stock_data_kite(
    symbols: list[str],
    api_key: str | None = None,
    access_token: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch 3-month historical data for each stock symbol via Kite."""
    _api_key = api_key or os.environ.get("KITE_API_KEY")
    _access_token = access_token or os.environ.get("KITE_ACCESS_TOKEN")

    if not _api_key or not _access_token:
        return {}

    # Resolve instrument tokens for stock symbols
    # Use standard NSE equity instrument tokens
    results: dict[str, pd.DataFrame] = {}
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=100)  # ~3 months

    async def _fetch_one(sym: str):
        # Look up instrument token from kite_option_master or use NSE equity convention
        try:
            import motor.motor_asyncio
            from server import db as _db
            doc = await _db.kite_option_master.find_one(
                {"tradingsymbol": sym, "exchange": "NSE", "instrument_type": "EQ"},
                {"_id": 0, "instrument_token": 1},
            )
            if doc and doc.get("instrument_token"):
                token = int(doc["instrument_token"])
            else:
                return sym, None
        except Exception:
            return sym, None

        df = await asyncio.to_thread(
            _fetch_kite_historical_sync, token, from_dt, to_dt, "day", _api_key, _access_token
        )
        return sym, df

    tasks = [_fetch_one(sym) for sym in symbols]
    for coro in asyncio.as_completed(tasks):
        sym, df = await coro
        if df is not None and len(df) > 10:
            results[sym] = df

    return results


def _compute_sector_metrics_from_stocks(
    sector: str,
    symbols: list[str],
    stock_data: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Compute sector metrics from constituent stock OHLCV data."""
    returns_1w: list[float] = []
    returns_1m: list[float] = []
    returns_3m: list[float] = []
    rsi_vals: list[float] = []
    adx_vals: list[float] = []

    for sym in symbols:
        df = stock_data.get(sym)
        if df is None or len(df) < 10:
            continue

        closes = df["Close"]
        n = len(closes)

        days_1w = min(5, n - 1)
        days_1m = min(21, n - 1)
        days_3m = min(63, n - 1)

        if days_1w >= 1:
            r1w = (closes.iloc[-1] - closes.iloc[-days_1w - 1]) / closes.iloc[-days_1w - 1] * 100
            returns_1w.append(float(r1w))
        if days_1m >= 1:
            r1m = (closes.iloc[-1] - closes.iloc[-days_1m - 1]) / closes.iloc[-days_1m - 1] * 100
            returns_1m.append(float(r1m))
        if days_3m >= 1:
            r3m = (closes.iloc[-1] - closes.iloc[-days_3m - 1]) / closes.iloc[-days_3m - 1] * 100
            returns_3m.append(float(r3m))

        rsi = _compute_rsi(closes)
        if rsi is not None:
            rsi_vals.append(rsi)

        adx = _compute_adx(df["High"], df["Low"], closes)
        if adx is not None:
            adx_vals.append(adx)

    return _build_sector_result(sector, returns_1w, returns_1m, returns_3m, rsi_vals, adx_vals, len(returns_1w))


def _compute_sector_metrics_from_index(
    sector: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    """Compute sector metrics from a single index OHLCV DataFrame."""
    closes = df["Close"]
    n = len(closes)

    returns_1w, returns_1m, returns_3m = [], [], []
    rsi_vals, adx_vals = [], []

    days_1w = min(5, n - 1)
    days_1m = min(21, n - 1)
    days_3m = min(63, n - 1)

    if days_1w >= 1:
        returns_1w.append(float((closes.iloc[-1] - closes.iloc[-days_1w - 1]) / closes.iloc[-days_1w - 1] * 100))
    if days_1m >= 1:
        returns_1m.append(float((closes.iloc[-1] - closes.iloc[-days_1m - 1]) / closes.iloc[-days_1m - 1] * 100))
    if days_3m >= 1:
        returns_3m.append(float((closes.iloc[-1] - closes.iloc[-days_3m - 1]) / closes.iloc[-days_3m - 1] * 100))

    rsi = _compute_rsi(closes)
    if rsi is not None:
        rsi_vals.append(rsi)

    adx = _compute_adx(df["High"], df["Low"], closes)
    if adx is not None:
        adx_vals.append(adx)

    return _build_sector_result(sector, returns_1w, returns_1m, returns_3m, rsi_vals, adx_vals, 1)


def _build_sector_result(
    sector: str,
    returns_1w: list[float],
    returns_1m: list[float],
    returns_3m: list[float],
    rsi_vals: list[float],
    adx_vals: list[float],
    stocks_tracked: int,
) -> dict[str, Any]:
    """Build the final sector metrics dict from computed values."""
    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 2) if vals else None

    avg_1w = _avg(returns_1w)
    avg_1m = _avg(returns_1m)
    avg_3m = _avg(returns_3m)
    avg_rsi = _avg(rsi_vals)
    avg_adx = _avg(adx_vals)

    # Momentum Score (0-100)
    score = 50.0
    if avg_1w is not None:
        score += max(-10.0, min(10.0, avg_1w * 2.0))
    if avg_1m is not None:
        score += max(-15.0, min(15.0, avg_1m * 1.5))
    if avg_3m is not None:
        score += max(-20.0, min(20.0, avg_3m * 0.8))
    if avg_rsi is not None:
        score += (avg_rsi - 50) / 5.0
    score = round(max(0.0, min(100.0, score)), 1)

    # Direction Classification
    if score >= 70:
        direction, direction_label, color_class = "STRONG_BULL", "Strong Bullish", "text-emerald-300"
    elif score >= 57:
        direction, direction_label, color_class = "BULL", "Bullish", "text-green-400"
    elif score >= 43:
        direction, direction_label, color_class = "NEUTRAL", "Neutral", "text-yellow-300"
    elif score >= 30:
        direction, direction_label, color_class = "BEAR", "Bearish", "text-orange-400"
    else:
        direction, direction_label, color_class = "STRONG_BEAR", "Strong Bearish", "text-rose-400"

    trend_strength = (
        "STRONG" if avg_adx and avg_adx > 25
        else "MODERATE" if avg_adx and avg_adx > 15
        else "WEAK"
    )

    return {
        "sector": sector,
        "momentum_score": score,
        "direction": direction,
        "direction_label": direction_label,
        "color_class": color_class,
        "hex_color": SECTOR_COLORS.get(sector, "#64748b"),
        "return_1w": avg_1w,
        "return_1m": avg_1m,
        "return_3m": avg_3m,
        "rsi": avg_rsi,
        "adx": avg_adx,
        "trend_strength": trend_strength,
        "stocks_tracked": stocks_tracked,
        "data_available": stocks_tracked > 0,
        "data_source": "kite",
    }


# ── MongoDB Cache Layer ──────────────────────────────────────────────────────

CACHE_TTL_MINUTES = 30


async def _get_cached_sector_data(db) -> dict[str, Any] | None:
    """Fetch cached sector momentum data from MongoDB if still fresh."""
    if db is None:
        return None
    try:
        doc = await db.sector_momentum_cache.find_one(
            {"cache_key": "sector_dashboard"}, {"_id": 0}
        )
        if not doc:
            return None
        cached_at = doc.get("cached_at")
        if cached_at:
            if isinstance(cached_at, str):
                cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < CACHE_TTL_MINUTES * 60:
                return doc.get("data")
    except Exception as exc:
        logger.debug("Sector cache read failed: %s", exc)
    return None


async def _set_cached_sector_data(db, data: dict[str, Any]):
    """Store sector momentum data in MongoDB cache."""
    if db is None:
        return
    try:
        await db.sector_momentum_cache.update_one(
            {"cache_key": "sector_dashboard"},
            {
                "$set": {
                    "cache_key": "sector_dashboard",
                    "data": data,
                    "cached_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        logger.debug("Sector cache write failed: %s", exc)


# ── Main Dashboard Function ───────────────────────────────────────────────────

async def compute_sector_momentum_dashboard(db=None) -> dict[str, Any]:
    """
    Compute momentum metrics for all 15 sectors using Kite Connect exclusively.

    Strategy:
      1. Check MongoDB cache (30-min TTL)
      2. Try Kite historical data for representative stocks per sector
      3. Compute metrics from available data
      4. Cache results
    """
    # Check cache first
    if db is not None:
        cached = await _get_cached_sector_data(db)
        if cached:
            logger.debug("Returning cached sector momentum data")
            return cached

    # Collect all unique symbols across sectors
    all_symbols: list[str] = []
    for syms in SECTOR_STOCKS.values():
        all_symbols.extend(syms)
    unique_symbols = list(set(all_symbols))

    # Fetch stock data from Kite
    stock_data: dict[str, pd.DataFrame] = {}
    try:
        stock_data = await asyncio.wait_for(
            _fetch_sector_stock_data_kite(unique_symbols),
            timeout=90.0,
        )
        logger.info("Kite sector data fetched: %d/%d stocks", len(stock_data), len(unique_symbols))
    except asyncio.TimeoutError:
        logger.warning("Kite sector data fetch timed out")
    except Exception as exc:
        logger.warning("Kite sector data fetch failed: %s", exc)

    # Compute per-sector metrics
    sectors_data: list[dict] = []
    for sector, symbols in SECTOR_STOCKS.items():
        metrics = _compute_sector_metrics_from_stocks(sector, symbols, stock_data)
        sectors_data.append(metrics)

    # Sort by momentum score (highest first)
    sectors_data.sort(key=lambda x: x["momentum_score"], reverse=True)

    # Market breadth summary
    bull_count = sum(1 for s in sectors_data if s["direction"] in ("STRONG_BULL", "BULL"))
    bear_count = sum(1 for s in sectors_data if s["direction"] in ("STRONG_BEAR", "BEAR"))
    total = len(sectors_data)
    data_available_count = sum(1 for s in sectors_data if s["data_available"])
    avg_score = round(sum(s["momentum_score"] for s in sectors_data) / total, 1) if total > 0 else 50.0

    market_breadth = (
        "BULL_DOMINANT" if bull_count >= total * 0.6
        else "BEAR_DOMINANT" if bear_count >= total * 0.6
        else "MIXED"
    )

    result = {
        "sectors": sectors_data,
        "summary": {
            "bullish_sectors": bull_count,
            "bearish_sectors": bear_count,
            "neutral_sectors": total - bull_count - bear_count,
            "total_sectors": total,
            "avg_momentum_score": avg_score,
            "market_breadth": market_breadth,
            "data_available_sectors": data_available_count,
            "data_source": "kite",
        },
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache the result
    if db is not None:
        await _set_cached_sector_data(db, result)

    return result
