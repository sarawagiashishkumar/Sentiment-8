"""
Backtest Engine — Step 3 of the Master Spec.

Provides:
  1. Backtest computation: replays last 12 months of trades per strategy × instrument
     using OHLCV history (yfinance daily as baseline, Kite intraday when available).
  2. Stats aggregation: trade_count, win_rate, expectancy_R, max_drawdown_R.
  3. Seeder: upserts results into `strategy_backtests` MongoDB collection.
  4. DB reader: fetch_strategy_backtest() for Bucket A consumption.

All calculations are pure Python. No LLM numeric work.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────────────
# {
#   "strategy_id": "S1_ORB",
#   "instrument_universe": "NIFTY",
#   "config_key": "S1_ORB__NIFTY",
#   "trade_count": 145,
#   "win_rate": 0.78,
#   "expectancy_R": 0.55,
#   "max_drawdown_R": -3.2,
#   "last_updated": "2026-04-08T02:00:00Z",
# }

ENABLE_THRESHOLD = {
    "min_trade_count": 100,
    "min_win_rate": 0.75,
    "min_expectancy_r": 0.40,
}


def make_config_key(strategy_id: str, instrument: str) -> str:
    return f"{strategy_id}__{instrument}"


# ── Simulated Trade Engine (daily OHLCV based) ────────────────────────────

def _compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Simple RSI from close prices."""
    rsi_values: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return rsi_values
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[period] = 100 - (100 / (1 + rs))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i + 1] = 100 - (100 / (1 + rs))
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
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return atr
    first_atr = sum(trs[:period]) / period
    atr[period] = first_atr
    for i in range(period, len(trs)):
        atr[i + 1] = (atr[i] * (period - 1) + trs[i]) / period
    return atr


def _simulate_orb_trades(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float],
    volumes: list[float],
) -> list[dict]:
    """Simulate ORB strategy using daily OHLCV as proxy for intraday ORB."""
    trades: list[dict] = []
    vol_avg_window = 5
    for i in range(vol_avg_window, len(closes) - 1):
        avg_vol = sum(volumes[i - vol_avg_window:i]) / vol_avg_window
        if avg_vol <= 0:
            continue
        vol_ratio = volumes[i] / avg_vol
        if vol_ratio < 1.3:
            continue
        orb_range = highs[i] - lows[i]
        if orb_range <= 0:
            continue
        # Determine direction from open-to-close
        if closes[i] > opens[i]:
            entry = highs[i]
            sl = opens[i] - orb_range * 0.1
            risk = max(entry - sl, 0.01)
            # Next day outcome
            max_fav = highs[i + 1] - entry
            max_adv = entry - lows[i + 1]
            r_mult = (max_fav - max_adv * 0.5) / risk
        else:
            entry = lows[i]
            sl = opens[i] + orb_range * 0.1
            risk = max(sl - entry, 0.01)
            max_fav = entry - lows[i + 1]
            max_adv = highs[i + 1] - entry
            r_mult = (max_fav - max_adv * 0.5) / risk

        win = r_mult > 0
        trades.append({"r_mult": round(r_mult, 3), "win": win})
    return trades


def _simulate_rsi_reversion_trades(
    closes: list[float], highs: list[float], lows: list[float],
) -> list[dict]:
    """Simulate RSI mean-reversion strategy."""
    trades: list[dict] = []
    rsi_vals = _compute_rsi(closes, 14)
    atr_vals = _compute_atr(highs, lows, closes, 14)
    for i in range(15, len(closes) - 2):
        r = rsi_vals[i]
        atr_v = atr_vals[i]
        if r is None or atr_v is None or atr_v <= 0:
            continue
        prev_r = rsi_vals[i - 1]
        if prev_r is None:
            continue
        # Bullish: RSI crosses above 30
        if prev_r < 30 and r >= 30:
            entry = closes[i]
            sl = entry - 1.5 * atr_v
            risk = max(entry - sl, 0.01)
            target = entry + 1.5 * risk
            actual_profit = closes[i + 1] - entry
            r_mult = actual_profit / risk
            trades.append({"r_mult": round(r_mult, 3), "win": r_mult > 0})
        # Bearish: RSI crosses below 70
        elif prev_r > 70 and r <= 70:
            entry = closes[i]
            sl = entry + 1.5 * atr_v
            risk = max(sl - entry, 0.01)
            actual_profit = entry - closes[i + 1]
            r_mult = actual_profit / risk
            trades.append({"r_mult": round(r_mult, 3), "win": r_mult > 0})
    return trades


def _simulate_macd_trades(
    closes: list[float], highs: list[float], lows: list[float],
) -> list[dict]:
    """Simulate MACD + ADX momentum strategy."""
    trades: list[dict] = []
    ema12 = _compute_ema(closes, 12)
    ema26 = _compute_ema(closes, 26)
    atr_vals = _compute_atr(highs, lows, closes, 14)

    macd_line: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if ema12[i] is not None and ema26[i] is not None:
            macd_line[i] = ema12[i] - ema26[i]

    # Signal line (9-period EMA of MACD)
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

        # Bullish crossover
        if macd_vals[j - 1] < (signal_line[j - 1] or 0) and macd_vals[j] > (signal_line[j] or 0):
            entry = closes[i]
            risk = 1.5 * atr_v
            sl = entry - risk
            actual = closes[i + 1] - entry
            r_mult = actual / risk
            trades.append({"r_mult": round(r_mult, 3), "win": r_mult > 0})
        # Bearish crossover
        elif macd_vals[j - 1] > (signal_line[j - 1] or 0) and macd_vals[j] < (signal_line[j] or 0):
            entry = closes[i]
            risk = 1.5 * atr_v
            sl = entry + risk
            actual = entry - closes[i + 1]
            r_mult = actual / risk
            trades.append({"r_mult": round(r_mult, 3), "win": r_mult > 0})
    return trades


def _simulate_supertrend_trades(
    closes: list[float], highs: list[float], lows: list[float],
    period: int = 10, multiplier: float = 3.0,
) -> list[dict]:
    """Simulate Supertrend crossover strategy."""
    trades: list[dict] = []
    atr_vals = _compute_atr(highs, lows, closes, period)
    n = len(closes)
    if n < period + 2:
        return trades

    upper_band = [0.0] * n
    lower_band = [0.0] * n
    supertrend = [0.0] * n
    direction = [1] * n  # 1 = up (bullish), -1 = down (bearish)

    for i in range(period, n):
        atr_v = atr_vals[i]
        if atr_v is None:
            continue
        mid = (highs[i] + lows[i]) / 2
        upper_band[i] = mid + multiplier * atr_v
        lower_band[i] = mid - multiplier * atr_v

        if i == period:
            direction[i] = 1 if closes[i] > upper_band[i] else -1
            supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]
            continue

        if direction[i - 1] == 1:
            lower_band[i] = max(lower_band[i], lower_band[i - 1]) if lower_band[i - 1] != 0 else lower_band[i]
            if closes[i] < lower_band[i]:
                direction[i] = -1
                supertrend[i] = upper_band[i]
            else:
                direction[i] = 1
                supertrend[i] = lower_band[i]
        else:
            upper_band[i] = min(upper_band[i], upper_band[i - 1]) if upper_band[i - 1] != 0 else upper_band[i]
            if closes[i] > upper_band[i]:
                direction[i] = 1
                supertrend[i] = lower_band[i]
            else:
                direction[i] = -1
                supertrend[i] = upper_band[i]

    for i in range(period + 1, n - 1):
        atr_v = atr_vals[i]
        if atr_v is None or atr_v <= 0:
            continue
        # Direction flip
        if direction[i - 1] == -1 and direction[i] == 1:
            entry = closes[i]
            risk = max(1.0 * atr_v, 0.01)
            actual = closes[i + 1] - entry
            trades.append({"r_mult": round(actual / risk, 3), "win": actual > 0})
        elif direction[i - 1] == 1 and direction[i] == -1:
            entry = closes[i]
            risk = max(1.0 * atr_v, 0.01)
            actual = entry - closes[i + 1]
            trades.append({"r_mult": round(actual / risk, 3), "win": actual > 0})
    return trades


def _simulate_vwap_reversion_trades(
    closes: list[float], volumes: list[float], highs: list[float], lows: list[float],
) -> list[dict]:
    """Simulate VWAP mean-reversion using daily data."""
    trades: list[dict] = []
    atr_vals = _compute_atr(highs, lows, closes, 14)
    # Approximate VWAP as cumulative volume-weighted average price (reset daily = use 20-day MA)
    ema20 = _compute_ema(closes, 20)
    for i in range(21, len(closes) - 1):
        vwap_proxy = ema20[i]
        atr_v = atr_vals[i]
        if vwap_proxy is None or atr_v is None or atr_v <= 0 or vwap_proxy <= 0:
            continue
        deviation_pct = (closes[i] - vwap_proxy) / vwap_proxy * 100

        risk = 1.0 * atr_v
        if deviation_pct < -0.5:
            # Bullish reversion
            actual = closes[i + 1] - closes[i]
            trades.append({"r_mult": round(actual / risk, 3), "win": actual > 0})
        elif deviation_pct > 0.5:
            # Bearish reversion
            actual = closes[i] - closes[i + 1]
            trades.append({"r_mult": round(actual / risk, 3), "win": actual > 0})
    return trades


# ── Strategy → Simulator Mapping ──────────────────────────────────────────

STRATEGY_SIMULATORS = {
    "S1_ORB": "orb",
    "S2_VWAP": "vwap",
    "S3_SUPERTREND": "supertrend",
    "S4_MACD_ADX": "macd",
    "S5_RSI_REVERSION": "rsi",
    "SW1_52W_BREAKOUT": "supertrend",  # proxy
    "SW2_200DMA_BOUNCE": "rsi",         # proxy
    "SW3_FLAG_BREAKOUT": "supertrend",  # proxy
    "E1_SHORT_STRADDLE": "macd",        # proxy for direction
    "E2_IRON_CONDOR": "vwap",           # proxy
    "E3_CALENDAR_SPREAD": "vwap",       # proxy
    "SF1_SCREENER_MOMENTUM": "macd",    # proxy
    "SF2_FORENSIC_QUALITY": "rsi",      # proxy
}


def simulate_trades_for_strategy(
    strategy_id: str,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
) -> list[dict]:
    """Run the appropriate simulator for a given strategy."""
    sim_type = STRATEGY_SIMULATORS.get(strategy_id, "macd")
    if sim_type == "orb":
        return _simulate_orb_trades(opens, highs, lows, closes, volumes)
    elif sim_type == "vwap":
        return _simulate_vwap_reversion_trades(closes, volumes, highs, lows)
    elif sim_type == "supertrend":
        return _simulate_supertrend_trades(closes, highs, lows)
    elif sim_type == "rsi":
        return _simulate_rsi_reversion_trades(closes, highs, lows)
    elif sim_type == "macd":
        return _simulate_macd_trades(closes, highs, lows)
    return []


# ── Stats Aggregation ─────────────────────────────────────────────────────

def compute_backtest_stats(trades: list[dict]) -> dict[str, Any]:
    """
    Compute aggregate statistics from a list of trades.

    Returns: {trade_count, win_rate, expectancy_R, max_drawdown_R}
    """
    if not trades:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "expectancy_R": 0.0,
            "max_drawdown_R": 0.0,
        }

    wins = sum(1 for t in trades if t["win"])
    total = len(trades)
    win_rate = wins / total if total > 0 else 0.0

    r_mults = [t["r_mult"] for t in trades]
    expectancy = sum(r_mults) / total if total > 0 else 0.0

    # Max drawdown in R terms (consecutive losing streak)
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in r_mults:
        cumulative += r
        peak = max(peak, cumulative)
        dd = cumulative - peak
        max_dd = min(max_dd, dd)

    return {
        "trade_count": total,
        "win_rate": round(win_rate, 4),
        "expectancy_R": round(expectancy, 4),
        "max_drawdown_R": round(max_dd, 2),
    }


def is_strategy_enabled(stats: dict[str, Any]) -> bool:
    """
    Check if a strategy config meets minimum thresholds for live signal generation.

    Enable ONLY IF: trade_count >= 100 AND win_rate >= 0.75 AND expectancy_R >= 0.40
    """
    if not stats:
        return False
    return (
        stats.get("trade_count", 0) >= ENABLE_THRESHOLD["min_trade_count"]
        and stats.get("win_rate", 0) >= ENABLE_THRESHOLD["min_win_rate"]
        and stats.get("expectancy_R", 0) >= ENABLE_THRESHOLD["min_expectancy_r"]
    )


# ── OHLCV Fetcher (yfinance) ─────────────────────────────────────────────

def _fetch_12m_ohlcv_yfinance(symbol: str) -> dict[str, list[float]] | None:
    """Fetch 12 months of daily OHLCV from yfinance."""
    try:
        import yfinance as yf
        ticker_sym = symbol
        if symbol in ("NIFTY", "NIFTY50"):
            ticker_sym = "^NSEI"
        elif symbol == "BANKNIFTY":
            ticker_sym = "^NSEBANK"
        elif not symbol.startswith("^") and ".NS" not in symbol:
            ticker_sym = f"{symbol}.NS"

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=365)
        df = yf.download(ticker_sym, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 60:
            return None

        # Handle MultiIndex columns from yfinance (flatten if needed)
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)

        return {
            "opens": [float(x) for x in df["Open"].values],
            "highs": [float(x) for x in df["High"].values],
            "lows": [float(x) for x in df["Low"].values],
            "closes": [float(x) for x in df["Close"].values],
            "volumes": [float(x) for x in df["Volume"].values],
        }
    except Exception as e:
        logger.warning("yfinance OHLCV fetch failed for %s: %s", symbol, e)
        return None


# ── Batch Job: Run Backtests & Upsert ────────────────────────────────────

async def run_backtest_batch(db, strategy_library: dict[str, dict]) -> dict[str, Any]:
    """
    Run backtests for all strategy × instrument combinations.

    Uses yfinance daily data as baseline. Upserts results into
    strategy_backtests collection.

    Returns summary of results.
    """
    results_summary: dict[str, Any] = {"updated": 0, "skipped": 0, "errors": 0, "details": []}
    now_iso = datetime.now(timezone.utc).isoformat()

    # Unique instruments across all strategies
    instrument_set: set[str] = set()
    for sid, sdef in strategy_library.items():
        for inst in sdef.get("instruments", []):
            if inst == "LIQUID_STOCKS":
                instrument_set.update(["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"])
            else:
                instrument_set.add(inst)

    # Fetch OHLCV data per instrument
    ohlcv_cache: dict[str, dict] = {}
    for inst in instrument_set:
        data = _fetch_12m_ohlcv_yfinance(inst)
        if data:
            ohlcv_cache[inst] = data
            logger.info("Fetched 12m OHLCV for %s: %d bars", inst, len(data["closes"]))

    for sid, sdef in strategy_library.items():
        instruments = sdef.get("instruments", [])
        expanded: list[str] = []
        for inst in instruments:
            if inst == "LIQUID_STOCKS":
                expanded.extend(["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"])
            else:
                expanded.append(inst)

        for inst in expanded:
            config_key = make_config_key(sid, inst)
            ohlcv = ohlcv_cache.get(inst)
            if not ohlcv:
                results_summary["skipped"] += 1
                continue

            try:
                trades = simulate_trades_for_strategy(
                    sid,
                    ohlcv["opens"], ohlcv["highs"], ohlcv["lows"],
                    ohlcv["closes"], ohlcv["volumes"],
                )
                stats = compute_backtest_stats(trades)
                doc = {
                    "strategy_id": sid,
                    "instrument_universe": inst,
                    "config_key": config_key,
                    **stats,
                    "last_updated": now_iso,
                }
                await db.strategy_backtests.update_one(
                    {"config_key": config_key},
                    {"$set": doc},
                    upsert=True,
                )
                results_summary["updated"] += 1
                results_summary["details"].append({
                    "config_key": config_key,
                    "trade_count": stats["trade_count"],
                    "win_rate": stats["win_rate"],
                    "expectancy_R": stats["expectancy_R"],
                    "enabled": is_strategy_enabled(stats),
                })
                logger.info(
                    "Backtest %s: trades=%d wr=%.2f exp=%.3f dd=%.1f enabled=%s",
                    config_key, stats["trade_count"], stats["win_rate"],
                    stats["expectancy_R"], stats["max_drawdown_R"],
                    is_strategy_enabled(stats),
                )
            except Exception as e:
                logger.warning("Backtest failed for %s: %s", config_key, e)
                results_summary["errors"] += 1

    return results_summary


# ── DB Reader for Bucket A ────────────────────────────────────────────────

async def fetch_strategy_backtest(
    db, strategy_id: str, instrument: str,
) -> dict[str, Any] | None:
    """
    Fetch backtest stats for a specific strategy × instrument from MongoDB.

    Returns None if no document exists.
    """
    config_key = make_config_key(strategy_id, instrument)
    doc = await db.strategy_backtests.find_one(
        {"config_key": config_key},
        {"_id": 0},
    )
    return doc
