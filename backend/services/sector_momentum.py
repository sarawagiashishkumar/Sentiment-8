"""
Sector Momentum Dashboard — Kite-Native.

Computes 1W/1M/3M returns, RSI, ADX, and momentum scores for key NSE sectors.
Uses Kite Connect historical data API exclusively via get_ohlcv_from_kite().
Falls back to cached MongoDB data when Kite session is unavailable.
Results are cached in MongoDB for 30 minutes.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from services.data_policy import KITE_IS_SOURCE_OF_TRUTH  # noqa: F401 — policy anchor

logger = logging.getLogger(__name__)


# ── NSE Sector Index Kite instrument tokens ──────────────────────────────────
# These are official NSE indices with verified Kite Connect instrument tokens.
# get_ohlcv_from_kite() is called with these tokens for historical data.
SECTOR_INDEX_TOKENS: dict[str, int] = {
    "NIFTY BANK":       260105,
    "NIFTY IT":         259849,
    "NIFTY AUTO":       259593,
    "NIFTY PHARMA":     260361,
    "NIFTY FMCG":       260617,
    "NIFTY METAL":      259337,
    "NIFTY REALTY":     260873,
    "NIFTY ENERGY":     261129,
}

# Map display name → Kite index symbol
SECTOR_DISPLAY_MAP: dict[str, str] = {
    "Banking":   "NIFTY BANK",
    "IT":        "NIFTY IT",
    "Auto":      "NIFTY AUTO",
    "Pharma":    "NIFTY PHARMA",
    "FMCG":      "NIFTY FMCG",
    "Metal":     "NIFTY METAL",
    "Realty":    "NIFTY REALTY",
    "Energy":    "NIFTY ENERGY",
}

SECTOR_COLORS: dict[str, str] = {
    "Banking": "#10b981", "IT": "#3b82f6", "Auto": "#ef4444", "Pharma": "#8b5cf6",
    "FMCG": "#f59e0b", "Metal": "#6b7280", "Realty": "#ec4899", "Energy": "#f97316",
}

# ── Indicator helpers ─────────────────────────────────────────────────────────

def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [max(-d, 0) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _compute_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    n = len(closes)
    if n < period * 2:
        return None
    try:
        tr_list, dm_p_list, dm_n_list = [], [], []
        for i in range(1, n):
            h_diff = highs[i] - highs[i - 1]
            l_diff = lows[i - 1] - lows[i]
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_list.append(tr)
            dm_p_list.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
            dm_n_list.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)

        # Smoothed with EMA
        alpha = 1.0 / period
        atr = tr_list[0]
        sdm_p = dm_p_list[0]
        sdm_n = dm_n_list[0]
        dx_vals = []
        for i in range(1, len(tr_list)):
            atr = atr * (1 - alpha) + tr_list[i] * alpha
            sdm_p = sdm_p * (1 - alpha) + dm_p_list[i] * alpha
            sdm_n = sdm_n * (1 - alpha) + dm_n_list[i] * alpha
            if atr > 0:
                di_p = 100 * sdm_p / atr
                di_n = 100 * sdm_n / atr
                dx = abs(di_p - di_n) / (di_p + di_n + 1e-10) * 100
                dx_vals.append(dx)
        if not dx_vals:
            return None
        adx = dx_vals[0]
        for dx in dx_vals[1:]:
            adx = adx * (1 - alpha) + dx * alpha
        return round(adx, 2)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# KITE DATA FETCHER (reuses backtest_engine.get_ohlcv_from_kite)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_sector_ohlcv_kite(
    sector_index: str,
    instrument_token: int,
    interval: str = "day",
) -> dict[str, list[float]] | None:
    """
    Fetch 3-month OHLCV for a sector index using Kite Connect.
    Uses the same get_ohlcv_from_kite() abstraction as backtests.
    """
    from services.backtest_engine import get_ohlcv_from_kite

    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=100)

    def _fetch_sync():
        import os
        api_key = os.environ.get("KITE_API_KEY")
        access_token = os.environ.get("KITE_ACCESS_TOKEN")
        if not api_key or not access_token:
            # Try to get access token from DB
            return None

        import requests
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
                    "Authorization": f"token {api_key}:{access_token}",
                },
                timeout=20,
            )
            if resp.status_code != 200:
                logger.debug("Kite sector historical %s for %s: %s", resp.status_code, sector_index, resp.text[:200])
                return None

            candles = resp.json().get("data", {}).get("candles", [])
            if not candles or len(candles) < 10:
                return None

            opens, highs, lows, closes, volumes = [], [], [], [], []
            for c in candles:
                if len(c) < 6:
                    continue
                opens.append(float(c[1]))
                highs.append(float(c[2]))
                lows.append(float(c[3]))
                closes.append(float(c[4]))
                volumes.append(float(c[5] or 0))

            return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}
        except Exception as exc:
            logger.debug("Kite sector fetch failed for %s: %s", sector_index, exc)
            return None

    # Also try with DB-stored access token
    try:
        result = await asyncio.to_thread(_fetch_sync)
        if result:
            return result
    except Exception:
        pass

    # Fallback: try get_ohlcv_from_kite with token from kite_session in DB
    try:
        import motor.motor_asyncio
        from server import db as _db
        session = await _db.system_meta.find_one({"key": "kite_session"}, {"_id": 0})
        if session and session.get("access_token"):
            import os
            api_key = session.get("api_key") or os.environ.get("KITE_API_KEY")

            def _fetch_with_db_token():
                import requests
                url = (
                    f"https://api.kite.trade/instruments/historical/{instrument_token}/{interval}"
                    f"?from={from_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
                    f"&to={to_dt.strftime('%Y-%m-%d+%H:%M:%S')}"
                )
                resp = requests.get(
                    url,
                    headers={
                        "X-Kite-Version": "3",
                        "Authorization": f"token {api_key}:{session['access_token']}",
                    },
                    timeout=20,
                )
                if resp.status_code != 200:
                    return None
                candles = resp.json().get("data", {}).get("candles", [])
                if not candles or len(candles) < 10:
                    return None
                opens, highs, lows, closes, volumes = [], [], [], [], []
                for c in candles:
                    if len(c) < 6:
                        continue
                    opens.append(float(c[1]))
                    highs.append(float(c[2]))
                    lows.append(float(c[3]))
                    closes.append(float(c[4]))
                    volumes.append(float(c[5] or 0))
                return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}

            result = await asyncio.to_thread(_fetch_with_db_token)
            if result:
                logger.info("Sector %s fetched from Kite (DB session): %d candles", sector_index, len(result["closes"]))
                return result
    except Exception as exc:
        logger.debug("DB-session Kite fetch failed for %s: %s", sector_index, exc)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTOR METRICS COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def _compute_sector_metrics(
    sector: str,
    ohlcv: dict[str, list[float]],
) -> dict[str, Any]:
    """Compute momentum metrics from OHLCV data for a single sector index."""
    closes = ohlcv["closes"]
    highs = ohlcv["highs"]
    lows = ohlcv["lows"]
    n = len(closes)

    # Returns
    def _ret(days: int) -> float | None:
        if n > days and closes[-days - 1] > 0:
            return round((closes[-1] - closes[-days - 1]) / closes[-days - 1] * 100, 2)
        return None

    r1w = _ret(5)
    r1m = _ret(21)
    r3m = _ret(63)

    rsi = _compute_rsi(closes)
    adx = _compute_adx(highs, lows, closes)

    # Momentum Score (0-100)
    score = 50.0
    if r1w is not None:
        score += max(-10.0, min(10.0, r1w * 2.0))
    if r1m is not None:
        score += max(-15.0, min(15.0, r1m * 1.5))
    if r3m is not None:
        score += max(-20.0, min(20.0, r3m * 0.8))
    if rsi is not None:
        score += (rsi - 50) / 5.0
    score = round(max(0.0, min(100.0, score)), 1)

    # Direction Classification
    if score >= 70:
        direction, label, color_class = "STRONG_BULL", "Strong Bullish", "text-emerald-300"
    elif score >= 57:
        direction, label, color_class = "BULL", "Bullish", "text-green-400"
    elif score >= 43:
        direction, label, color_class = "NEUTRAL", "Neutral", "text-yellow-300"
    elif score >= 30:
        direction, label, color_class = "BEAR", "Bearish", "text-orange-400"
    else:
        direction, label, color_class = "STRONG_BEAR", "Strong Bearish", "text-rose-400"

    trend_strength = (
        "STRONG" if adx and adx > 25
        else "MODERATE" if adx and adx > 15
        else "WEAK"
    )

    return {
        "sector": sector,
        "momentum_score": score,
        "direction": direction,
        "direction_label": label,
        "color_class": color_class,
        "hex_color": SECTOR_COLORS.get(sector, "#64748b"),
        "return_1w": r1w,
        "return_1m": r1m,
        "return_3m": r3m,
        "rsi": rsi,
        "adx": adx,
        "trend_strength": trend_strength,
        "stocks_tracked": 1,
        "data_available": True,
        "data_source": "kite",
    }


def _empty_sector_metrics(sector: str) -> dict[str, Any]:
    """Placeholder metrics when data is unavailable."""
    return {
        "sector": sector,
        "momentum_score": 50.0,
        "direction": "NEUTRAL",
        "direction_label": "No Data",
        "color_class": "text-gray-400",
        "hex_color": SECTOR_COLORS.get(sector, "#64748b"),
        "return_1w": None, "return_1m": None, "return_3m": None,
        "rsi": None, "adx": None,
        "trend_strength": "UNKNOWN",
        "stocks_tracked": 0,
        "data_available": False,
        "data_source": "kite",
    }


# ── MongoDB Cache Layer ──────────────────────────────────────────────────────

CACHE_TTL_MINUTES = 30


async def _get_cached(db) -> dict | None:
    if db is None:
        return None
    try:
        doc = await db.sector_momentum_cache.find_one({"cache_key": "sector_dashboard"}, {"_id": 0})
        if not doc:
            return None
        cached_at = doc.get("cached_at")
        if cached_at:
            if isinstance(cached_at, str):
                cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < CACHE_TTL_MINUTES * 60:
                return doc.get("data")
    except Exception:
        pass
    return None


async def _set_cached(db, data: dict):
    if db is None:
        return
    try:
        await db.sector_momentum_cache.update_one(
            {"cache_key": "sector_dashboard"},
            {"$set": {"cache_key": "sector_dashboard", "data": data, "cached_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception:
        pass


# ── Main Dashboard Function ───────────────────────────────────────────────────

async def compute_sector_momentum_dashboard(db=None) -> dict[str, Any]:
    """
    Compute momentum for all NSE sector indices using Kite Connect exclusively.

    Strategy:
      1. Check MongoDB cache (30-min TTL)
      2. Fetch historical OHLCV from Kite for each sector index token
      3. Compute RSI/ADX/returns/momentum score
      4. Cache results
    """
    if db is not None:
        cached = await _get_cached(db)
        if cached:
            return cached

    sectors_data: list[dict] = []

    # Fetch all sector indices from Kite concurrently
    async def _fetch_one(sector: str, index_name: str, token: int):
        ohlcv = await _fetch_sector_ohlcv_kite(index_name, token, interval="day")
        if ohlcv and len(ohlcv.get("closes", [])) >= 10:
            return _compute_sector_metrics(sector, ohlcv)
        return _empty_sector_metrics(sector)

    tasks = []
    for sector, index_name in SECTOR_DISPLAY_MAP.items():
        token = SECTOR_INDEX_TOKENS.get(index_name)
        if token:
            tasks.append(_fetch_one(sector, index_name, token))
        else:
            sectors_data.append(_empty_sector_metrics(sector))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Sector fetch error: %s", r)
            elif isinstance(r, dict):
                sectors_data.append(r)

    sectors_data.sort(key=lambda x: x["momentum_score"], reverse=True)

    bull = sum(1 for s in sectors_data if s["direction"] in ("STRONG_BULL", "BULL"))
    bear = sum(1 for s in sectors_data if s["direction"] in ("STRONG_BEAR", "BEAR"))
    total = len(sectors_data)
    available = sum(1 for s in sectors_data if s["data_available"])
    avg = round(sum(s["momentum_score"] for s in sectors_data) / total, 1) if total > 0 else 50.0

    result = {
        "sectors": sectors_data,
        "summary": {
            "bullish_sectors": bull,
            "bearish_sectors": bear,
            "neutral_sectors": total - bull - bear,
            "total_sectors": total,
            "avg_momentum_score": avg,
            "market_breadth": "BULL_DOMINANT" if bull >= total * 0.6 else "BEAR_DOMINANT" if bear >= total * 0.6 else "MIXED",
            "data_available_sectors": available,
            "data_source": "kite",
        },
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }

    if db is not None:
        await _set_cached(db, result)

    return result
