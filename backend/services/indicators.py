"""
Core Technical Indicators — Basic building blocks for research engine.
All calculations are pure Python/NumPy/Pandas.  NO hallucinated numbers.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# HORIZON TRADING DAYS
# ─────────────────────────────────────────────────────────────────────────────
HORIZON_TRADING_DAYS: dict[str, int] = {
    "1W": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "9M": 189,
    "1Y": 252,
}


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICAL INDICATORS  (all inputs: pd.Series or pd.DataFrame from yfinance)
# ─────────────────────────────────────────────────────────────────────────────

def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    """Return current RSI value (0–100). Returns None if insufficient data."""
    if close is None or len(close) < period + 2:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else None


def compute_macd(close: pd.Series) -> dict[str, Any]:
    """Return MACD line, signal line, histogram, and crossover flags."""
    if close is None or len(close) < 35:
        return {"macd": None, "signal": None, "histogram": None,
                "bullish_crossover": False, "bearish_crossover": False,
                "above_zero": False}
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    curr_m, prev_m = float(macd_line.iloc[-1]), float(macd_line.iloc[-2])
    curr_s, prev_s = float(signal_line.iloc[-1]), float(signal_line.iloc[-2])
    bullish = curr_m > curr_s and prev_m <= prev_s
    bearish = curr_m < curr_s and prev_m >= prev_s
    return {
        "macd": round(curr_m, 4),
        "signal": round(curr_s, 4),
        "histogram": round(float(histogram.iloc[-1]), 4),
        "bullish_crossover": bullish,
        "bearish_crossover": bearish,
        "above_zero": curr_m > 0,
    }


def compute_bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict[str, Any]:
    """Return Bollinger Band metrics including %B and squeeze detection."""
    if close is None or len(close) < period + 2:
        return {"upper": None, "lower": None, "sma": None, "pct_b": None,
                "squeeze": False, "near_upper": False, "near_lower": False}
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std

    c = float(close.iloc[-1])
    u = float(upper.iloc[-1])
    l_val = float(lower.iloc[-1])
    m = float(sma.iloc[-1])
    bw = (u - l_val) / m if m > 0 else 0
    pct_b = (c - l_val) / (u - l_val) if (u - l_val) > 0 else 0.5
    return {
        "upper": round(u, 2),
        "lower": round(l_val, 2),
        "sma": round(m, 2),
        "band_width": round(bw, 4),
        "pct_b": round(pct_b, 4),
        "squeeze": bw < 0.04,
        "near_upper": pct_b > 0.85,
        "near_lower": pct_b < 0.15,
    }


def compute_atr(hist: pd.DataFrame, period: int = 14) -> float | None:
    """Return current ATR value (absolute price). Returns None if insufficient data."""
    if hist is None or len(hist) < period + 2:
        return None
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(period).mean()
    val = atr_series.iloc[-1]
    return float(val) if not pd.isna(val) else None


def compute_adx(hist: pd.DataFrame, period: int = 14) -> float | None:
    """Return current ADX value. Returns None if insufficient data."""
    if hist is None or len(hist) < period * 2 + 2:
        return None
    try:
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        prev_high = high.shift(1)
        prev_low = low.shift(1)
        prev_close = close.shift(1)

        plus_dm = high - prev_high
        minus_dm = prev_low - low
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()
        pdi = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan))
        mdi = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan))
        dx = (100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan))
        adx = dx.ewm(span=period, adjust=False).mean()
        val = adx.iloc[-1]
        return float(val) if not pd.isna(val) else None
    except Exception:
        return None


def compute_obv(hist: pd.DataFrame) -> dict[str, Any]:
    """Return OBV trend direction (RISING/FALLING/FLAT) and last OBV value."""
    if hist is None or len(hist) < 5:
        return {"obv": None, "trend": "FLAT"}
    close = hist["Close"]
    volume = hist["Volume"]
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (volume * direction).cumsum()
    recent = obv.iloc[-5:]
    trend = "RISING" if recent.iloc[-1] > recent.iloc[0] * 1.01 else (
        "FALLING" if recent.iloc[-1] < recent.iloc[0] * 0.99 else "FLAT"
    )
    return {"obv": float(obv.iloc[-1]), "trend": trend}


def compute_sma(close: pd.Series, period: int) -> float | None:
    """Return current SMA value."""
    if close is None or len(close) < period:
        return None
    val = close.rolling(period).mean().iloc[-1]
    return float(val) if not pd.isna(val) else None


def compute_ema(close: pd.Series, period: int) -> float | None:
    """Return current EMA value."""
    if close is None or len(close) < period:
        return None
    val = close.ewm(span=period, adjust=False).mean().iloc[-1]
    return float(val) if not pd.isna(val) else None


def compute_stochastic(hist: pd.DataFrame, period: int = 14) -> dict[str, Any]:
    """Return %K and %D values."""
    if hist is None or len(hist) < period + 3:
        return {"%K": None, "%D": None, "overbought": False, "oversold": False}
    high = hist["High"].rolling(period).max()
    low = hist["Low"].rolling(period).min()
    close = hist["Close"]
    k = 100 * (close - low) / (high - low).replace(0, np.nan)
    d = k.rolling(3).mean()
    k_val = float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else None
    d_val = float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else None
    return {
        "%K": round(k_val, 2) if k_val is not None else None,
        "%D": round(d_val, 2) if d_val is not None else None,
        "overbought": k_val is not None and k_val > 80,
        "oversold": k_val is not None and k_val < 20,
    }


# ─────────────────────────────────────────────────────────────────────────────
# VOLATILITY & PRICE BANDS
# ─────────────────────────────────────────────────────────────────────────────

def compute_historical_volatility(close: pd.Series) -> float | None:
    """Return annualized historical volatility (e.g. 0.30 = 30%)."""
    if close is None or len(close) < 15:
        return None
    log_returns = np.log(close / close.shift(1)).dropna()
    if len(log_returns) < 10:
        return None
    daily_vol = float(log_returns.std())
    annual_vol = daily_vol * math.sqrt(252)
    return round(annual_vol, 4)


def compute_realistic_price_bands(
    ltp: float,
    hist_vol: float | None,
    sector: str = "Unknown",
    pe_ratio: float | None = None,
) -> dict[str, dict[str, float]]:
    """
    Compute realistic price bands using historical volatility.
    Returns dict keyed by horizon ("1W", "1M", "3M", "6M", "9M", "1Y").
    Each value has: upside_pct, downside_pct (negative), flag.
    Falls back to sector/PE-based estimates if hist_vol is unavailable.
    """
    sector_vol_map = {
        "Bank": 0.30, "Financial Services": 0.28, "IT": 0.25,
        "Pharma": 0.28, "FMCG": 0.20, "Auto": 0.28, "Energy": 0.30,
        "Metal": 0.38, "Realty": 0.40, "Cement": 0.26, "Index": 0.18,
        "Unknown": 0.32,
    }
    if hist_vol is None or hist_vol <= 0:
        base_vol = 0.30
        for key, val in sector_vol_map.items():
            if key.lower() in sector.lower():
                base_vol = val
                break
        if pe_ratio is not None and pe_ratio > 50:
            base_vol = min(base_vol * 1.2, 0.55)
        hist_vol = base_vol

    hist_vol = max(0.10, min(hist_vol, 0.80))

    bands: dict[str, dict[str, float]] = {}
    for horizon, t_days in HORIZON_TRADING_DAYS.items():
        t = t_days / 252
        sigma_t = hist_vol * math.sqrt(t)

        cons_low = round(ltp * math.exp(-1.5 * sigma_t) - ltp, 2)
        cons_high = round(ltp * math.exp(1.0 * sigma_t) - ltp, 2)
        cons_low_pct = round((cons_low / ltp) * 100, 2)
        cons_high_pct = round((cons_high / ltp) * 100, 2)

        drift = 0.07 * t
        exp_low = round(ltp * math.exp(drift - sigma_t) - ltp, 2)
        exp_high = round(ltp * math.exp(drift + 1.5 * sigma_t) - ltp, 2)
        exp_low_pct = round((exp_low / ltp) * 100, 2)
        exp_high_pct = round((exp_high / ltp) * 100, 2)

        opt_high = round(ltp * math.exp(drift + 2.0 * sigma_t) - ltp, 2)
        opt_high_pct = round((opt_high / ltp) * 100, 2)

        upside_pct = max(exp_high_pct, 1.0)
        downside_pct = min(exp_low_pct, -1.0)
        flag = "GREEN" if upside_pct >= abs(downside_pct) * 1.1 else "RED"

        bands[horizon] = {
            "upside_pct": upside_pct,
            "downside_pct": downside_pct,
            "flag": flag,
            "conservative_high_pct": cons_high_pct,
            "conservative_low_pct": cons_low_pct,
            "optimistic_high_pct": opt_high_pct,
            "hist_vol_pct": round(hist_vol * 100, 1),
        }
    return bands


# ─────────────────────────────────────────────────────────────────────────────
# MARKET REGIME CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_market_regime(
    vix: float | None,
    adx: float | None = None,
    rsi: float | None = None,
) -> dict[str, Any]:
    """
    Classify market regime based on VIX, ADX, and index RSI.
    Returns regime name, suggested F&O strategy, and description.
    """
    if vix is None:
        return {
            "regime": "UNKNOWN",
            "vix": None,
            "options_strategy": "STANDARD",
            "description": "VIX data unavailable — using standard strategy selection",
            "color": "gray",
        }

    if vix < 12:
        regime, strategy, color = "LOW_VOL_RANGE", "IRON_CONDOR", "blue"
        desc = f"VIX {vix:.1f} (Low) — Range-bound market. Iron Condors & Short Straddles preferred."
    elif vix < 18:
        regime, strategy, color = "NORMAL_VOL", "STANDARD_DIRECTIONAL", "green"
        desc = f"VIX {vix:.1f} (Normal) — Balanced environment. Standard directional options."
    elif vix < 25:
        regime, strategy, color = "ELEVATED_VOL", "LONG_OPTIONS", "yellow"
        desc = f"VIX {vix:.1f} (Elevated) — Options cheap; Buy CE/PE on confirmation."
    elif vix < 35:
        regime, strategy, color = "HIGH_VOL_TREND", "STRADDLE_STRANGLE", "orange"
        desc = f"VIX {vix:.1f} (High) — High volatility; Straddles/Strangles or selective directional."
    else:
        regime, strategy, color = "CRASH_MODE", "PROTECTIVE_PUTS", "red"
        desc = f"VIX {vix:.1f} (Extreme) — Crash conditions; Protect capital with PE hedges."

    if adx is not None:
        if adx > 30:
            desc += f" ADX {adx:.0f} confirms strong trend."
        elif adx > 20:
            desc += f" ADX {adx:.0f} — moderate trend."
        else:
            desc += f" ADX {adx:.0f} — weak/choppy trend."

    if rsi is not None:
        if rsi > 70:
            desc += f" Index RSI {rsi:.0f} — overbought zone, caution on longs."
        elif rsi < 30:
            desc += f" Index RSI {rsi:.0f} — oversold, potential bounce opportunity."
        else:
            desc += f" Index RSI {rsi:.0f} — neutral momentum."

    return {
        "regime": regime,
        "vix": round(vix, 2),
        "adx": round(adx, 1) if adx is not None else None,
        "index_rsi": round(rsi, 1) if rsi is not None else None,
        "options_strategy": strategy,
        "description": desc,
        "color": color,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STOCK ELIGIBILITY FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def check_stock_eligibility(
    ltp: float | None,
    market_cap_cr: float | None,
    fundamental: dict | None,
) -> dict[str, Any]:
    """
    Apply stock selection filters per Master Spec section 2.
    Returns dict: {eligible: bool, flags: list[str], pass_count: int}
    """
    flags: list[str] = []
    eligible = True
    f = fundamental or {}

    if ltp is None or ltp < 50:
        flags.append(f"Price ₹{ltp or 0:.1f} < ₹50 minimum")
        eligible = False

    total_debt_ratio = f.get("total_debt_to_market_cap")
    if total_debt_ratio is not None:
        if total_debt_ratio >= 0.30:
            flags.append(f"Total debt {total_debt_ratio*100:.0f}% of mktcap ≥ 30% limit")
            eligible = False
    else:
        de = f.get("debt_to_equity")
        if de is not None and de > 200:
            flags.append(f"Very high D/E {de:.0f}% — potential debt concern")

    recent_profit_positive = f.get("recent_profit_positive")
    if recent_profit_positive is False:
        flags.append("Net loss in all 3 recent quarters — no profitable quarter found")
        eligible = False

    pass_count = (1 if (ltp is not None and ltp >= 50) else 0) + \
                 (1 if total_debt_ratio is None or total_debt_ratio < 0.30 else 0) + \
                 (1 if recent_profit_positive is not False else 0)

    return {
        "eligible": eligible,
        "flags": flags,
        "pass_count": pass_count,
        "max_filters": 3,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ATR-BASED F&O TARGETS
# ─────────────────────────────────────────────────────────────────────────────

def compute_atr_based_fno_targets(
    entry_price: float,
    underlying_ltp: float,
    atr: float | None,
    minutes_to_expiry: int,
    option_type: str,
    vix: float | None = None,
) -> tuple[float, float]:
    """
    Compute data-driven T1/T2 targets for F&O options using underlying ATR.
    Returns (target1, target2) in option price terms.
    """
    if minutes_to_expiry < 180:
        time_factor = 0.55
    elif minutes_to_expiry < 360:
        time_factor = 0.75
    elif minutes_to_expiry < 960:
        time_factor = 0.90
    else:
        time_factor = 1.0

    vix_factor = 1.0
    if vix is not None:
        if vix > 25:
            vix_factor = 1.25
        elif vix > 18:
            vix_factor = 1.10
        elif vix < 12:
            vix_factor = 0.85

    if atr is not None and underlying_ltp > 0 and atr > 0:
        atr_pct = atr / underlying_ltp
        delta_proxy = 0.45
        t1_pct = atr_pct * delta_proxy * time_factor * vix_factor
        t2_pct = atr_pct * delta_proxy * 2.0 * time_factor * vix_factor
    else:
        if entry_price > 100:
            base_t1, base_t2 = 0.08, 0.22
        elif entry_price > 30:
            base_t1, base_t2 = 0.10, 0.30
        else:
            base_t1, base_t2 = 0.12, 0.40
        t1_pct = base_t1 * time_factor * vix_factor
        t2_pct = base_t2 * time_factor * vix_factor

    t1_pct = max(min(t1_pct, 0.18), 0.04)
    t2_pct = max(min(t2_pct, 0.60), 0.10)

    target1 = round(entry_price * (1 + t1_pct), 2)
    target2 = round(entry_price * (1 + t2_pct), 2)

    return target1, target2


# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO RISK METRICS
# ─────────────────────────────────────────────────────────────────────────────

def compute_portfolio_risk_metrics(
    holdings: list[dict],
    nifty_hist: "pd.DataFrame | None" = None,
) -> dict[str, Any]:
    """
    Compute portfolio-level risk metrics.
    holdings: list of dicts with keys: symbol, ltp, avg_price, quantity,
              current_value, pnl_pct, hist_vol (optional), hist_returns (optional)
    Returns: beta, sharpe_proxy, max_drawdown_pct, var_95_pct, portfolio_vol_annual,
             largest_holding_pct, sector_concentration, win_rate
    """
    if not holdings:
        return {}

    total_val = sum(h.get("current_value", 0) for h in holdings)
    if total_val <= 0:
        return {}

    weights = [h.get("current_value", 0) / total_val for h in holdings]
    pnl_pcts = [h.get("pnl_pct", 0) for h in holdings]
    vols = [h.get("hist_vol", 0.30) for h in holdings]

    portfolio_return_pct = sum(p * w for p, w in zip(pnl_pcts, weights))
    port_vol_annual = float(np.sqrt(sum((w * v) ** 2 for w, v in zip(weights, vols))))

    betas = [h.get("beta", 1.0) for h in holdings if "beta" in h]
    portfolio_beta = float(np.dot(weights[:len(betas)], betas)) if betas else 1.0

    risk_free = 6.5
    sharpe = (portfolio_return_pct - risk_free) / (port_vol_annual * 100) if port_vol_annual > 0 else 0.0

    max_dd = min(pnl_pcts) if pnl_pcts else 0.0
    var_95_daily = -1.645 * port_vol_annual / math.sqrt(252) * 100

    wins = sum(1 for p in pnl_pcts if p > 0)
    win_rate = round(wins / len(pnl_pcts) * 100, 1) if pnl_pcts else 0.0

    largest_holding_pct = round(max(weights) * 100, 1) if weights else 0.0

    sector_map: dict[str, float] = {}
    for h, w in zip(holdings, weights):
        sec = h.get("sector", "Unknown")
        sector_map[sec] = sector_map.get(sec, 0.0) + w * 100
    top_sector = max(sector_map, key=sector_map.get) if sector_map else "Unknown"
    top_sector_pct = round(sector_map.get(top_sector, 0.0), 1)

    return {
        "portfolio_return_pct": round(portfolio_return_pct, 2),
        "portfolio_vol_annual_pct": round(port_vol_annual * 100, 1),
        "portfolio_beta": round(portfolio_beta, 2),
        "sharpe_proxy": round(sharpe, 2),
        "max_single_drawdown_pct": round(max_dd, 2),
        "var_95_1day_pct": round(var_95_daily, 2),
        "win_rate_pct": win_rate,
        "largest_holding_pct": largest_holding_pct,
        "top_sector": top_sector,
        "top_sector_pct": top_sector_pct,
        "sector_breakdown": {k: round(v, 1) for k, v in sorted(sector_map.items(), key=lambda x: -x[1])},
        "total_holdings": len(holdings),
    }
