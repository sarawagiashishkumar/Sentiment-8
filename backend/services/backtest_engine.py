"""
Backtest Engine — Step 3 of the Master Spec.

PROD RULE: All OHLCV and historical data for Indian markets must come from
Kite Connect or verified exchange APIs. Do not use yfinance or unofficial
sources in production paths. CSV seed files (manually verified) are the only
offline fallback.

Provides:
  1. OHLCV fetching: Kite Connect primary, CSV seed fallback.
  2. Backtest computation: replays last 12 months of trades per strategy × instrument.
  3. Stats aggregation: trade_count, win_rate, expectancy_R, max_drawdown_R.
  4. Seeder: upserts results into `strategy_backtests` MongoDB collection.
  5. DB reader: fetch_strategy_backtest() for Bucket A consumption.
"""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Global config: yfinance is DISABLED in production ──────────────────────
USE_YFINANCE: bool = os.environ.get("USE_YFINANCE", "false").lower() in ("1", "true", "yes")

# Directory for manually verified CSV seed files
CSV_SEED_DIR = Path(os.environ.get("OHLCV_CSV_SEED_DIR", "/app/data/ohlcv_seeds"))

# ── Schema ─────────────────────────────────────────────────────────────────
ENABLE_THRESHOLD = {
    "min_trade_count": 100,
    "min_win_rate": 0.75,
    "min_expectancy_r": 0.40,
}


def make_config_key(strategy_id: str, instrument: str) -> str:
    return f"{strategy_id}__{instrument}"


# ══════════════════════════════════════════════════════════════════════════
#   OHLCV DATA SOURCES  (Kite primary → CSV seed fallback → skip)
# ══════════════════════════════════════════════════════════════════════════

# ── Kite Connect Historical Data (PRIMARY) ────────────────────────────────

def _kite_instrument_token_sync(symbol: str, db_sync_client) -> int | None:
    """Look up instrument token from kite_equity_master (synchronous pymongo)."""
    try:
        row = db_sync_client.kite_equity_master.find_one(
            {"symbol": symbol.upper().strip()}, {"_id": 0, "instrument_token": 1}
        )
        if row and row.get("instrument_token"):
            return int(row["instrument_token"])
    except Exception:
        pass
    # Index tokens
    INDEX_TOKENS = {"NIFTY": 256265, "NIFTY50": 256265, "BANKNIFTY": 260105}
    return INDEX_TOKENS.get(symbol.upper())


def get_ohlcv_from_kite(
    symbol: str,
    from_dt: datetime,
    to_dt: datetime,
    interval: str = "day",
    api_key: str | None = None,
    access_token: str | None = None,
    db_sync_client=None,
) -> dict[str, list[float]] | None:
    """
    Fetch OHLCV from Kite Connect Historical Data API.

    Returns dict with keys: opens, highs, lows, closes, volumes
    or None on failure.
    """
    _api_key = api_key or os.environ.get("KITE_API_KEY")
    _access_token = access_token or os.environ.get("KITE_ACCESS_TOKEN")

    if not _api_key or not _access_token:
        logger.info("Kite auth not available (no API key or access token), skipping %s", symbol)
        return None

    # Resolve instrument token
    instrument_token = None
    INDEX_TOKENS = {"NIFTY": 256265, "NIFTY50": 256265, "BANKNIFTY": 260105}
    if symbol.upper() in INDEX_TOKENS:
        instrument_token = INDEX_TOKENS[symbol.upper()]
    elif db_sync_client is not None:
        instrument_token = _kite_instrument_token_sync(symbol, db_sync_client)

    if instrument_token is None:
        logger.debug("No instrument token for %s, skipping", symbol)
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
            logger.warning("Kite historical API %s for %s (token=%s): %s",
                           resp.status_code, symbol, instrument_token, resp.text[:200])
            return None

        candles = resp.json().get("data", {}).get("candles", [])
        if not candles:
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

        if len(closes) < 30:
            logger.debug("Kite returned only %d candles for %s (need ≥30)", len(closes), symbol)
            return None

        logger.info("Kite OHLCV for %s: %d candles (%s to %s)",
                     symbol, len(closes), from_dt.strftime('%Y-%m-%d'), to_dt.strftime('%Y-%m-%d'))
        return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}

    except Exception as e:
        logger.warning("Kite OHLCV fetch failed for %s: %s", symbol, e)
        return None


# ── CSV Seed Files (VERIFIED OFFLINE FALLBACK) ────────────────────────────

def get_ohlcv_from_csv_seed(symbol: str) -> dict[str, list[float]] | None:
    """
    Load OHLCV from a manually verified CSV seed file.

    Expected CSV format: date,open,high,low,close,volume
    Files are in CSV_SEED_DIR named as {SYMBOL}.csv (e.g., NIFTY.csv, RELIANCE.csv).
    """
    csv_path = CSV_SEED_DIR / f"{symbol.upper()}.csv"
    if not csv_path.exists():
        return None

    try:
        opens, highs, lows, closes, volumes = [], [], [], [], []
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    opens.append(float(row["open"]))
                    highs.append(float(row["high"]))
                    lows.append(float(row["low"]))
                    closes.append(float(row["close"]))
                    volumes.append(float(row.get("volume", 0)))
                except (ValueError, KeyError):
                    continue

        if len(closes) < 30:
            logger.debug("CSV seed for %s has only %d rows (need ≥30)", symbol, len(closes))
            return None

        logger.info("CSV seed loaded for %s: %d candles from %s", symbol, len(closes), csv_path)
        return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}

    except Exception as e:
        logger.warning("CSV seed read failed for %s: %s", symbol, e)
        return None


# ── Unified OHLCV Fetcher (Kite → CSV → skip) ────────────────────────────

def fetch_12m_ohlcv(
    symbol: str,
    api_key: str | None = None,
    access_token: str | None = None,
    db_sync_client=None,
) -> dict[str, list[float]] | None:
    """
    Fetch 12 months of daily OHLCV for a symbol.

    Priority:
      1. Kite Connect Historical Data API (primary, mandatory for normal operation)
      2. Manual CSV seed import (offline, verified)
      3. Skip (log and return None)

    NEVER uses yfinance in production.
    """
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)

    # 1. Kite Connect (primary)
    data = get_ohlcv_from_kite(
        symbol, start_dt, end_dt, interval="day",
        api_key=api_key, access_token=access_token,
        db_sync_client=db_sync_client,
    )
    if data:
        return data

    # 2. CSV seed (verified offline fallback)
    data = get_ohlcv_from_csv_seed(symbol)
    if data:
        return data

    # 3. Skip
    logger.info("No OHLCV data available for %s (Kite unavailable, no CSV seed)", symbol)
    return None


# ══════════════════════════════════════════════════════════════════════════
#   TRADE SIMULATORS  (pure Python, no external data dependencies)
# ══════════════════════════════════════════════════════════════════════════

def _compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    rsi_values: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return rsi_values
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rsi_values[period] = 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values[i + 1] = 100.0
        else:
            rsi_values[i + 1] = 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi_values


def _compute_ema(values: list[float], period: int) -> list[float | None]:
    ema: list[float | None] = [None] * len(values)
    if len(values) < period:
        return ema
    sma = sum(values[:period]) / period
    ema[period - 1] = sma
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        ema[i] = values[i] * k + (ema[i - 1] or sma) * (1 - k)
    return ema


def _compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    atr: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return atr
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return atr
    first_atr = sum(trs[:period]) / period
    atr[period] = first_atr
    for i in range(period, len(trs)):
        atr[i + 1] = (atr[i] * (period - 1) + trs[i]) / period
    return atr


def _simulate_orb_trades(opens, highs, lows, closes, volumes):
    trades = []
    vol_avg_window = 5
    for i in range(vol_avg_window, len(closes) - 1):
        avg_vol = sum(volumes[i - vol_avg_window:i]) / vol_avg_window
        if avg_vol <= 0:
            continue
        if volumes[i] / avg_vol < 1.3:
            continue
        orb_range = highs[i] - lows[i]
        if orb_range <= 0:
            continue
        if closes[i] > opens[i]:
            entry = highs[i]
            sl = opens[i] - orb_range * 0.1
            risk = max(entry - sl, 0.01)
            r_mult = (highs[i + 1] - entry - (entry - lows[i + 1]) * 0.5) / risk
        else:
            entry = lows[i]
            sl = opens[i] + orb_range * 0.1
            risk = max(sl - entry, 0.01)
            r_mult = (entry - lows[i + 1] - (highs[i + 1] - entry) * 0.5) / risk
        trades.append({"r_mult": round(r_mult, 3), "win": r_mult > 0})
    return trades


def _simulate_rsi_reversion_trades(closes, highs, lows):
    trades = []
    rsi_vals = _compute_rsi(closes, 14)
    atr_vals = _compute_atr(highs, lows, closes, 14)
    for i in range(15, len(closes) - 2):
        r, atr_v = rsi_vals[i], atr_vals[i]
        if r is None or atr_v is None or atr_v <= 0:
            continue
        prev_r = rsi_vals[i - 1]
        if prev_r is None:
            continue
        if prev_r < 30 and r >= 30:
            risk = max(1.5 * atr_v, 0.01)
            trades.append({"r_mult": round((closes[i + 1] - closes[i]) / risk, 3), "win": closes[i + 1] > closes[i]})
        elif prev_r > 70 and r <= 70:
            risk = max(1.5 * atr_v, 0.01)
            trades.append({"r_mult": round((closes[i] - closes[i + 1]) / risk, 3), "win": closes[i + 1] < closes[i]})
    return trades


def _simulate_macd_trades(closes, highs, lows):
    trades = []
    ema12 = _compute_ema(closes, 12)
    ema26 = _compute_ema(closes, 26)
    atr_vals = _compute_atr(highs, lows, closes, 14)
    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema12[i] is not None and ema26[i] is not None:
            macd_line[i] = ema12[i] - ema26[i]
    macd_vals = [v for v in macd_line if v is not None]
    if len(macd_vals) < 9:
        return trades
    signal_line = _compute_ema(macd_vals, 9)
    macd_start = next(i for i, v in enumerate(macd_line) if v is not None)
    for j in range(1, len(macd_vals) - 1):
        i = macd_start + j
        if i + 1 >= len(closes):
            break
        if signal_line[j] is None or signal_line[j - 1] is None:
            continue
        atr_v = atr_vals[i] if i < len(atr_vals) else None
        if atr_v is None or atr_v <= 0:
            continue
        risk = 1.5 * atr_v
        if macd_vals[j - 1] < (signal_line[j - 1] or 0) and macd_vals[j] > (signal_line[j] or 0):
            trades.append({"r_mult": round((closes[i + 1] - closes[i]) / risk, 3), "win": closes[i + 1] > closes[i]})
        elif macd_vals[j - 1] > (signal_line[j - 1] or 0) and macd_vals[j] < (signal_line[j] or 0):
            trades.append({"r_mult": round((closes[i] - closes[i + 1]) / risk, 3), "win": closes[i + 1] < closes[i]})
    return trades


def _simulate_supertrend_trades(closes, highs, lows, period=10, multiplier=3.0):
    trades = []
    atr_vals = _compute_atr(highs, lows, closes, period)
    n = len(closes)
    if n < period + 2:
        return trades
    upper_band = [0.0] * n
    lower_band = [0.0] * n
    direction = [1] * n
    for i in range(period, n):
        atr_v = atr_vals[i]
        if atr_v is None:
            continue
        mid = (highs[i] + lows[i]) / 2
        upper_band[i] = mid + multiplier * atr_v
        lower_band[i] = mid - multiplier * atr_v
        if i == period:
            direction[i] = 1 if closes[i] > upper_band[i] else -1
            continue
        if direction[i - 1] == 1:
            lower_band[i] = max(lower_band[i], lower_band[i - 1]) if lower_band[i - 1] != 0 else lower_band[i]
            direction[i] = -1 if closes[i] < lower_band[i] else 1
        else:
            upper_band[i] = min(upper_band[i], upper_band[i - 1]) if upper_band[i - 1] != 0 else upper_band[i]
            direction[i] = 1 if closes[i] > upper_band[i] else -1
    for i in range(period + 1, n - 1):
        atr_v = atr_vals[i]
        if atr_v is None or atr_v <= 0:
            continue
        risk = max(1.0 * atr_v, 0.01)
        if direction[i - 1] == -1 and direction[i] == 1:
            trades.append({"r_mult": round((closes[i + 1] - closes[i]) / risk, 3), "win": closes[i + 1] > closes[i]})
        elif direction[i - 1] == 1 and direction[i] == -1:
            trades.append({"r_mult": round((closes[i] - closes[i + 1]) / risk, 3), "win": closes[i + 1] < closes[i]})
    return trades


def _simulate_vwap_reversion_trades(closes, volumes, highs, lows):
    trades = []
    atr_vals = _compute_atr(highs, lows, closes, 14)
    ema20 = _compute_ema(closes, 20)
    for i in range(21, len(closes) - 1):
        vwap_proxy, atr_v = ema20[i], atr_vals[i]
        if vwap_proxy is None or atr_v is None or atr_v <= 0 or vwap_proxy <= 0:
            continue
        deviation_pct = (closes[i] - vwap_proxy) / vwap_proxy * 100
        risk = 1.0 * atr_v
        if deviation_pct < -0.5:
            trades.append({"r_mult": round((closes[i + 1] - closes[i]) / risk, 3), "win": closes[i + 1] > closes[i]})
        elif deviation_pct > 0.5:
            trades.append({"r_mult": round((closes[i] - closes[i + 1]) / risk, 3), "win": closes[i + 1] < closes[i]})
    return trades


STRATEGY_SIMULATORS = {
    "S1_ORB": "orb", "S2_VWAP": "vwap", "S3_SUPERTREND": "supertrend",
    "S4_MACD_ADX": "macd", "S5_RSI_REVERSION": "rsi",
    "SW1_52W_BREAKOUT": "supertrend", "SW2_200DMA_BOUNCE": "rsi",
    "SW3_FLAG_BREAKOUT": "supertrend",
    "E1_SHORT_STRADDLE": "macd", "E2_IRON_CONDOR": "vwap", "E3_CALENDAR_SPREAD": "vwap",
    "SF1_SCREENER_MOMENTUM": "macd", "SF2_FORENSIC_QUALITY": "rsi",
}


def simulate_trades_for_strategy(strategy_id, opens, highs, lows, closes, volumes):
    sim = STRATEGY_SIMULATORS.get(strategy_id, "macd")
    if sim == "orb":
        return _simulate_orb_trades(opens, highs, lows, closes, volumes)
    elif sim == "vwap":
        return _simulate_vwap_reversion_trades(closes, volumes, highs, lows)
    elif sim == "supertrend":
        return _simulate_supertrend_trades(closes, highs, lows)
    elif sim == "rsi":
        return _simulate_rsi_reversion_trades(closes, highs, lows)
    elif sim == "macd":
        return _simulate_macd_trades(closes, highs, lows)
    return []


# ── Stats Aggregation ─────────────────────────────────────────────────────

def compute_backtest_stats(trades: list[dict]) -> dict[str, Any]:
    if not trades:
        return {"trade_count": 0, "win_rate": 0.0, "expectancy_R": 0.0, "max_drawdown_R": 0.0}
    wins = sum(1 for t in trades if t["win"])
    total = len(trades)
    r_mults = [t["r_mult"] for t in trades]
    cumulative, peak, max_dd = 0.0, 0.0, 0.0
    for r in r_mults:
        cumulative += r
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return {
        "trade_count": total,
        "win_rate": round(wins / total, 4),
        "expectancy_R": round(sum(r_mults) / total, 4),
        "max_drawdown_R": round(max_dd, 2),
    }


def is_strategy_enabled(stats: dict[str, Any]) -> bool:
    if not stats:
        return False
    return (
        stats.get("trade_count", 0) >= ENABLE_THRESHOLD["min_trade_count"]
        and stats.get("win_rate", 0) >= ENABLE_THRESHOLD["min_win_rate"]
        and stats.get("expectancy_R", 0) >= ENABLE_THRESHOLD["min_expectancy_r"]
    )


# ══════════════════════════════════════════════════════════════════════════
#   BATCH JOB  (run backtests → upsert into strategy_backtests)
# ══════════════════════════════════════════════════════════════════════════

async def run_backtest_batch(db, strategy_library: dict[str, dict]) -> dict[str, Any]:
    """
    Run backtests for all strategy × instrument combinations.

    Uses Kite Connect as primary OHLCV source, CSV seeds as fallback.
    NEVER uses yfinance.
    """
    # Production assertion
    if os.environ.get("ENV") == "prod":
        assert not USE_YFINANCE, "yfinance must be disabled in production"

    results: dict[str, Any] = {"updated": 0, "skipped": 0, "errors": 0, "details": [],
                                "data_source": "kite_connect + csv_seed"}
    now_iso = datetime.now(timezone.utc).isoformat()

    # Resolve Kite credentials
    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")

    # Get Kite access token from DB session (system_meta.kite_session)
    if not access_token:
        try:
            session_doc = await db.system_meta.find_one(
                {"key": "kite_session"}, {"_id": 0, "access_token": 1, "api_key": 1},
            )
            if session_doc:
                access_token = session_doc.get("access_token")
                if not api_key:
                    api_key = session_doc.get("api_key")
        except Exception:
            pass

    # Sync MongoDB client for instrument token lookup in threads
    from pymongo import MongoClient
    sync_client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_name = os.environ.get("DB_NAME", "trading_signals")
    sync_db = sync_client[db_name]

    # Unique instruments
    instrument_set: set[str] = set()
    for sdef in strategy_library.values():
        for inst in sdef.get("instruments", []):
            if inst == "LIQUID_STOCKS":
                instrument_set.update(["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"])
            else:
                instrument_set.add(inst)

    # Fetch OHLCV per instrument
    ohlcv_cache: dict[str, dict] = {}
    for inst in instrument_set:
        data = fetch_12m_ohlcv(
            inst, api_key=api_key, access_token=access_token, db_sync_client=sync_db,
        )
        if data:
            ohlcv_cache[inst] = data
            logger.info("OHLCV ready for %s: %d bars", inst, len(data["closes"]))

    sync_client.close()

    # Run backtests per strategy × instrument
    for sid, sdef in strategy_library.items():
        expanded: list[str] = []
        for inst in sdef.get("instruments", []):
            if inst == "LIQUID_STOCKS":
                expanded.extend(["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"])
            else:
                expanded.append(inst)

        for inst in expanded:
            config_key = make_config_key(sid, inst)
            ohlcv = ohlcv_cache.get(inst)
            if not ohlcv:
                results["skipped"] += 1
                continue
            try:
                trades = simulate_trades_for_strategy(
                    sid, ohlcv["opens"], ohlcv["highs"], ohlcv["lows"],
                    ohlcv["closes"], ohlcv["volumes"],
                )
                stats = compute_backtest_stats(trades)
                doc = {
                    "strategy_id": sid, "instrument_universe": inst,
                    "config_key": config_key, **stats, "last_updated": now_iso,
                }
                await db.strategy_backtests.update_one(
                    {"config_key": config_key}, {"$set": doc}, upsert=True,
                )
                results["updated"] += 1
                results["details"].append({
                    "config_key": config_key, "trade_count": stats["trade_count"],
                    "win_rate": stats["win_rate"], "expectancy_R": stats["expectancy_R"],
                    "enabled": is_strategy_enabled(stats),
                })
                logger.info("Backtest %s: trades=%d wr=%.2f exp=%.3f enabled=%s",
                            config_key, stats["trade_count"], stats["win_rate"],
                            stats["expectancy_R"], is_strategy_enabled(stats))
            except Exception as e:
                logger.warning("Backtest failed for %s: %s", config_key, e)
                results["errors"] += 1

    return results


# ── DB Reader for Bucket A ────────────────────────────────────────────────

async def fetch_strategy_backtest(db, strategy_id: str, instrument: str) -> dict[str, Any] | None:
    config_key = make_config_key(strategy_id, instrument)
    doc = await db.strategy_backtests.find_one({"config_key": config_key}, {"_id": 0})
    return doc


# ── CSV Seed Management ──────────────────────────────────────────────────

def list_csv_seeds() -> list[dict[str, Any]]:
    """List all available CSV seed files with metadata."""
    if not CSV_SEED_DIR.exists():
        return []
    seeds = []
    for f in sorted(CSV_SEED_DIR.glob("*.csv")):
        try:
            line_count = sum(1 for _ in open(f)) - 1  # exclude header
            seeds.append({
                "symbol": f.stem.upper(),
                "file": f.name,
                "rows": line_count,
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        except Exception:
            pass
    return seeds


def save_csv_seed(symbol: str, content: str) -> dict[str, Any]:
    """
    Save a CSV seed file for a symbol.

    Validates basic structure (must have date,open,high,low,close columns).
    """
    CSV_SEED_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = CSV_SEED_DIR / f"{symbol.upper()}.csv"

    lines = content.strip().split("\n")
    if len(lines) < 2:
        return {"error": "CSV must have at least a header and one data row"}

    header = lines[0].lower().replace(" ", "")
    required = {"date", "open", "high", "low", "close"}
    header_cols = set(header.split(","))
    missing = required - header_cols
    if missing:
        return {"error": f"Missing required columns: {missing}"}

    with open(csv_path, "w") as f:
        f.write(content)

    row_count = len(lines) - 1
    return {"saved": True, "symbol": symbol.upper(), "rows": row_count, "path": str(csv_path)}


def delete_csv_seed(symbol: str) -> dict[str, Any]:
    """Delete a CSV seed file."""
    csv_path = CSV_SEED_DIR / f"{symbol.upper()}.csv"
    if csv_path.exists():
        csv_path.unlink()
        return {"deleted": True, "symbol": symbol.upper()}
    return {"error": f"No CSV seed found for {symbol}"}
