"""
Sector Momentum Dashboard — Backend Service.
Computes 1W/1M/3M returns, RSI, ADX, and momentum scores for 15 key NSE sectors.
Uses representative stocks from each sector, fetched via yfinance.
Results are cached in MongoDB for 30 minutes.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Sector → Representative NSE stocks mapping ───────────────────────────────
SECTOR_STOCKS: dict[str, list[str]] = {
    "IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "GODREJCP"],
    "Auto": ["MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "M&M", "HEROMOTOCO"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA", "VEDL"],
    "Realty": ["DLF", "LODHA", "PRESTIGE", "GODREJPROP", "OBEROIRLTY"],
    "Oil & Gas": ["RELIANCE", "ONGC", "IOC", "BPCL", "GAIL"],
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
    "Oil & Gas": "#f97316",
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


def _compute_adx(df: pd.DataFrame, period: int = 14) -> float | None:
    """Compute ADX for the last data point."""
    if len(df) < period * 2:
        return None
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)

        dm_plus = high.diff()
        dm_minus = -low.diff()
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


def _compute_hist_vol(closes: pd.Series, window: int = 21) -> float | None:
    """Compute annualized historical volatility."""
    if len(closes) < window + 1:
        return None
    log_returns = np.log(closes / closes.shift(1)).dropna()
    daily_vol = log_returns.tail(window).std()
    return round(float(daily_vol * math.sqrt(252)), 4)


def _fetch_sector_data_sync(symbols: list[str]) -> pd.DataFrame | None:
    """Synchronously download OHLCV data for a list of symbols via yfinance."""
    try:
        import yfinance as yf
        tickers = [f"{s}.NS" for s in symbols]
        df = yf.download(
            tickers,
            period="3mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        logger.warning("yfinance sector download failed: %s", exc)
        return None


def _get_close_series(df: pd.DataFrame, symbol: str) -> pd.Series | None:
    """Extract Close series for one symbol from a multi-ticker DataFrame."""
    try:
        if isinstance(df.columns, pd.MultiIndex):
            if ("Close", f"{symbol}.NS") in df.columns:
                s = df[("Close", f"{symbol}.NS")].dropna()
                return s if len(s) > 10 else None
        else:
            # Single-ticker download
            s = df["Close"].dropna()
            return s if len(s) > 10 else None
    except Exception:
        return None


def _compute_sector_metrics(
    sector: str,
    symbols: list[str],
    raw_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Compute 1W/1M/3M returns, RSI, ADX, and momentum score for one sector."""
    returns_1w: list[float] = []
    returns_1m: list[float] = []
    returns_3m: list[float] = []
    rsi_vals: list[float] = []
    adx_vals: list[float] = []

    if raw_df is not None:
        for sym in symbols:
            closes = _get_close_series(raw_df, sym)
            if closes is None or len(closes) < 10:
                continue

            n = len(closes)
            # Compute returns using available data
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

            # For ADX, try to extract OHLC from df
            try:
                if isinstance(raw_df.columns, pd.MultiIndex):
                    ohlc_df = pd.DataFrame({
                        "High": raw_df.get(("High", f"{sym}.NS")),
                        "Low": raw_df.get(("Low", f"{sym}.NS")),
                        "Close": raw_df.get(("Close", f"{sym}.NS")),
                    }).dropna()
                else:
                    ohlc_df = raw_df[["High", "Low", "Close"]].dropna()
                adx = _compute_adx(ohlc_df)
                if adx is not None:
                    adx_vals.append(adx)
            except Exception:
                pass

    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 2) if vals else None

    avg_1w = _avg(returns_1w)
    avg_1m = _avg(returns_1m)
    avg_3m = _avg(returns_3m)
    avg_rsi = _avg(rsi_vals)
    avg_adx = _avg(adx_vals)

    # ── Momentum Score (0-100) ────────────────────────────────────────────────
    # Start at 50 (neutral). Contributions from 1W, 1M, 3M returns and RSI.
    score = 50.0

    # 1W contribution: ±10 max
    if avg_1w is not None:
        score += max(-10.0, min(10.0, avg_1w * 2.0))

    # 1M contribution: ±15 max
    if avg_1m is not None:
        score += max(-15.0, min(15.0, avg_1m * 1.5))

    # 3M contribution: ±20 max
    if avg_3m is not None:
        score += max(-20.0, min(20.0, avg_3m * 0.8))

    # RSI contribution: ±10 max
    if avg_rsi is not None:
        score += (avg_rsi - 50) / 5.0  # ±10 for RSI deviation of 50 from neutral

    score = round(max(0.0, min(100.0, score)), 1)

    # ── Direction Classification ──────────────────────────────────────────────
    if score >= 70:
        direction = "STRONG_BULL"
        direction_label = "Strong Bullish"
        color_class = "text-emerald-300"
    elif score >= 57:
        direction = "BULL"
        direction_label = "Bullish"
        color_class = "text-green-400"
    elif score >= 43:
        direction = "NEUTRAL"
        direction_label = "Neutral"
        color_class = "text-yellow-300"
    elif score >= 30:
        direction = "BEAR"
        direction_label = "Bearish"
        color_class = "text-orange-400"
    else:
        direction = "STRONG_BEAR"
        direction_label = "Strong Bearish"
        color_class = "text-rose-400"

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
        "stocks_tracked": len(returns_1w),
        "data_available": len(returns_1w) > 0,
    }


# ── Main Dashboard Function ───────────────────────────────────────────────────

async def compute_sector_momentum_dashboard() -> dict[str, Any]:
    """
    Compute momentum metrics for all 15 sectors.
    Fetches yfinance data concurrently per sector.
    Returns list of sector metrics sorted by momentum score (desc).
    """
    # Group symbols for batch download
    all_symbols: list[str] = []
    for syms in SECTOR_STOCKS.values():
        all_symbols.extend(syms)
    unique_symbols = list(set(all_symbols))

    # Download all symbols in one call (faster than per-sector)
    try:
        raw_df = await asyncio.wait_for(
            asyncio.to_thread(_fetch_sector_data_sync, unique_symbols),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Sector data download timed out")
        raw_df = None
    except Exception as exc:
        logger.warning("Sector data download failed: %s", exc)
        raw_df = None

    sectors_data: list[dict] = []
    for sector, symbols in SECTOR_STOCKS.items():
        metrics = _compute_sector_metrics(sector, symbols, raw_df)
        sectors_data.append(metrics)

    # Sort by momentum score (highest first)
    sectors_data.sort(key=lambda x: x["momentum_score"], reverse=True)

    # Compute market breadth summary
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

    return {
        "sectors": sectors_data,
        "summary": {
            "bullish_sectors": bull_count,
            "bearish_sectors": bear_count,
            "neutral_sectors": total - bull_count - bear_count,
            "total_sectors": total,
            "avg_momentum_score": avg_score,
            "market_breadth": market_breadth,
            "data_available_sectors": data_available_count,
        },
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
