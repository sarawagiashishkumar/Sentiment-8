"""
Research Engine — All numeric calculations for Indian Equities & F&O.
Rules:
 - All calculations are in pure Python/NumPy/Pandas.
 - NO hallucinated numbers. If data is missing, return None explicitly.
 - Used by F&O Signals, Multibagger Screener, and Portfolio Analysis.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
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
    # Sector default volatility proxies (annualized)
    sector_vol_map = {
        "Bank": 0.30, "Financial Services": 0.28, "IT": 0.25,
        "Pharma": 0.28, "FMCG": 0.20, "Auto": 0.28, "Energy": 0.30,
        "Metal": 0.38, "Realty": 0.40, "Cement": 0.26, "Index": 0.18,
        "Unknown": 0.32,
    }
    if hist_vol is None or hist_vol <= 0:
        # Determine volatility from sector
        base_vol = 0.30
        for key, val in sector_vol_map.items():
            if key.lower() in sector.lower():
                base_vol = val
                break
        # PE-based adjustment: high PE = higher growth expectations = higher vol
        if pe_ratio is not None and pe_ratio > 50:
            base_vol = min(base_vol * 1.2, 0.55)
        hist_vol = base_vol

    hist_vol = max(0.10, min(hist_vol, 0.80))  # clamp to reasonable range

    bands: dict[str, dict[str, float]] = {}
    for horizon, t_days in HORIZON_TRADING_DAYS.items():
        t = t_days / 252
        sigma_t = hist_vol * math.sqrt(t)

        # Conservative scenario (1-sigma band around drift 0)
        cons_low = round(ltp * math.exp(-1.5 * sigma_t) - ltp, 2)   # negative
        cons_high = round(ltp * math.exp(1.0 * sigma_t) - ltp, 2)   # positive
        cons_low_pct = round((cons_low / ltp) * 100, 2)
        cons_high_pct = round((cons_high / ltp) * 100, 2)

        # Expected scenario (slight positive drift = risk premium ~7% annual)
        drift = 0.07 * t
        exp_low = round(ltp * math.exp(drift - sigma_t) - ltp, 2)
        exp_high = round(ltp * math.exp(drift + 1.5 * sigma_t) - ltp, 2)
        exp_low_pct = round((exp_low / ltp) * 100, 2)
        exp_high_pct = round((exp_high / ltp) * 100, 2)

        # Optimistic scenario (+2 sigma)
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

    # ADX overlay for trend strength
    if adx is not None:
        if adx > 30:
            desc += f" ADX {adx:.0f} confirms strong trend."
        elif adx > 20:
            desc += f" ADX {adx:.0f} — moderate trend."
        else:
            desc += f" ADX {adx:.0f} — weak/choppy trend."

    # RSI overlay for index momentum
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
    Apply stock selection filters per Master Spec section 2:
    1. Price ≥ ₹50
    2. Total debt < 30% of market cap
    3. Net profit positive in at least one of last 3 quarters
    Returns dict: {eligible: bool, flags: list[str], pass_count: int}
    """
    flags: list[str] = []
    eligible = True
    f = fundamental or {}

    # Filter 1: Price ≥ ₹50
    if ltp is None or ltp < 50:
        flags.append(f"Price ₹{ltp or 0:.1f} < ₹50 minimum")
        eligible = False

    # Filter 2: Total debt < 30% of market cap
    # debt_to_equity from yfinance is expressed as percentage (D/E * 100)
    # We approximate: total_debt ≈ debt_to_equity_pct/100 × book_value_per_share × shares
    # Simpler: if D/E > 2.5 AND market_cap is small, flag it
    # Better: use total_debt_to_market_cap if available
    total_debt_ratio = f.get("total_debt_to_market_cap")
    if total_debt_ratio is not None:
        if total_debt_ratio >= 0.30:
            flags.append(f"Total debt {total_debt_ratio*100:.0f}% of mktcap ≥ 30% limit")
            eligible = False
    else:
        # Fallback: D/E proxy
        de = f.get("debt_to_equity")
        if de is not None and de > 200:  # D/E ratio > 200% is very high debt
            flags.append(f"Very high D/E {de:.0f}% — potential debt concern")
            # Don't auto-disqualify but flag it

    # Filter 3: Net profit positive in at least 1 of last 3 quarters
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
    Falls back to volatility-adjusted fixed % if ATR unavailable.
    Returns (target1, target2) in option price terms.
    """
    # Time factor
    if minutes_to_expiry < 180:
        time_factor = 0.55
    elif minutes_to_expiry < 360:
        time_factor = 0.75
    elif minutes_to_expiry < 960:  # intraday (< 1 day remaining)
        time_factor = 0.90
    else:
        time_factor = 1.0

    # VIX volatility factor
    vix_factor = 1.0
    if vix is not None:
        if vix > 25:
            vix_factor = 1.25
        elif vix > 18:
            vix_factor = 1.10
        elif vix < 12:
            vix_factor = 0.85

    if atr is not None and underlying_ltp > 0 and atr > 0:
        # ATR as % of underlying
        atr_pct = atr / underlying_ltp
        # Option delta proxy: ATM ≈ 0.5, use 0.45 conservatively
        delta_proxy = 0.45
        # T1 = 1× ATR move in option terms
        t1_pct = atr_pct * delta_proxy * time_factor * vix_factor
        # T2 = 2× ATR move in option terms
        t2_pct = atr_pct * delta_proxy * 2.0 * time_factor * vix_factor
    else:
        # Fallback: price-tier based
        if entry_price > 100:
            base_t1, base_t2 = 0.08, 0.22
        elif entry_price > 30:
            base_t1, base_t2 = 0.10, 0.30
        else:
            base_t1, base_t2 = 0.12, 0.40
        t1_pct = base_t1 * time_factor * vix_factor
        t2_pct = base_t2 * time_factor * vix_factor

    # Apply caps to keep realistic
    t1_pct = max(min(t1_pct, 0.18), 0.04)   # 4–18% for T1
    t2_pct = max(min(t2_pct, 0.60), 0.10)   # 10–60% for T2

    target1 = round(entry_price * (1 + t1_pct), 2)
    target2 = round(entry_price * (1 + t2_pct), 2)

    return target1, target2


# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO RISK METRICS
# ─────────────────────────────────────────────────────────────────────────────

def compute_portfolio_risk_metrics(
    holdings: list[dict],
    nifty_hist: pd.DataFrame | None = None,
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
    # Annual volatilities per stock
    vols = [h.get("hist_vol", 0.30) for h in holdings]

    # Weighted portfolio return
    portfolio_return_pct = sum(p * w for p, w in zip(pnl_pcts, weights))

    # Portfolio volatility (simplified; assumes low correlation = sqrt of weighted variance)
    port_vol_annual = float(np.sqrt(sum((w * v) ** 2 for w, v in zip(weights, vols))))

    # Beta vs NIFTY (simplified: use average of stock betas if available)
    betas = [h.get("beta", 1.0) for h in holdings if "beta" in h]
    portfolio_beta = float(np.dot(weights[:len(betas)], betas)) if betas else 1.0

    # Sharpe proxy (annualized; risk-free rate = 6.5% = RBI repo)
    risk_free = 6.5
    # Portfolio return as annualized (pnl_pct is total, not annualized — treat as best proxy)
    sharpe = (portfolio_return_pct - risk_free) / (port_vol_annual * 100) if port_vol_annual > 0 else 0.0

    # Max drawdown (worst single stock loss as proxy)
    max_dd = min(pnl_pcts) if pnl_pcts else 0.0

    # 1-day VaR 95% (parametric)
    var_95_daily = -1.645 * port_vol_annual / math.sqrt(252) * 100

    # Win rate
    wins = sum(1 for p in pnl_pcts if p > 0)
    win_rate = round(wins / len(pnl_pcts) * 100, 1) if pnl_pcts else 0.0

    # Largest holding %
    largest_holding_pct = round(max(weights) * 100, 1) if weights else 0.0

    # Sector concentration
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


# ─────────────────────────────────────────────────────────────────────────────
# FULL TECHNICAL SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def compute_full_technical_snapshot(
    symbol: str,
    hist: pd.DataFrame,
    ltp: float | None = None,
) -> dict[str, Any]:
    """
    Comprehensive technical snapshot (Batch 1 enhanced).
    Includes: RSI, MACD, BB, ATR, ADX, OBV, Stochastic, SMAs/EMAs, Hist-Vol,
              Williams %R, CCI, VPT, A/D Line, Ichimoku, Fibonacci, Pivot Points,
              Support/Resistance, RSI Divergence, Candlestick Patterns,
              Multi-timeframe Trend, Chart Patterns.
    """
    if hist is None or hist.empty:
        return {"symbol": symbol, "data_available": False}

    close = hist["Close"]

    # ── Core indicators ───────────────────────────────────────────────────────
    rsi = compute_rsi(close)
    macd_data = compute_macd(close)
    bb_data = compute_bollinger(close)
    atr_val = compute_atr(hist)
    adx_val = compute_adx(hist)
    obv_data = compute_obv(hist)
    stoch = compute_stochastic(hist)

    # ── Moving averages ───────────────────────────────────────────────────────
    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    ema_20 = compute_ema(close, 20)
    ema_9 = compute_ema(close, 9)

    # ── Volatility ────────────────────────────────────────────────────────────
    hist_vol = compute_historical_volatility(close)

    # ── Advanced indicators (Batch 1) ─────────────────────────────────────────
    williams_r = compute_williams_r(hist)
    cci_data = compute_cci(hist)
    vpt_data = compute_vpt(hist)
    ad_data = compute_ad_line(hist)
    ichimoku = compute_ichimoku(hist)
    fibonacci = compute_fibonacci_levels(hist)
    pivots = compute_pivot_points(hist)
    sr = compute_support_resistance(hist)
    rsi_div = detect_rsi_divergence(hist)
    candle_patterns = detect_candlestick_patterns(hist)
    mf_trend = compute_multiframe_trend(hist)
    chart_pats = detect_chart_patterns(hist)

    # ── Trend alignment (MA-based) ────────────────────────────────────────────
    price = float(close.iloc[-1]) if ltp is None else ltp
    above_sma50 = price > sma_50 if sma_50 is not None else None
    above_sma200 = price > sma_200 if sma_200 is not None else None
    above_ema20 = price > ema_20 if ema_20 is not None else None

    if above_sma200 is True and above_sma50 is True and above_ema20 is True:
        trend_alignment = "BULLISH_ALIGNED"
    elif above_sma200 is False and above_sma50 is False and above_ema20 is False:
        trend_alignment = "BEARISH_ALIGNED"
    elif above_sma50 is True and above_ema20 is True:
        trend_alignment = "SHORT_TERM_BULLISH"
    elif above_sma50 is False and above_ema20 is False:
        trend_alignment = "SHORT_TERM_BEARISH"
    else:
        trend_alignment = "MIXED"

    # ── Aggregated signal count ───────────────────────────────────────────────
    bullish_signals = 0
    bearish_signals = 0

    # RSI
    if rsi is not None:
        if rsi < 40:
            bullish_signals += 1
        elif rsi > 65:
            bearish_signals += 1

    # MACD
    if macd_data.get("bullish_crossover"):
        bullish_signals += 1
    if macd_data.get("bearish_crossover"):
        bearish_signals += 1
    if macd_data.get("above_zero"):
        bullish_signals += 1
    else:
        bearish_signals += 1

    # MA alignment
    if trend_alignment == "BULLISH_ALIGNED":
        bullish_signals += 2
    elif trend_alignment == "BEARISH_ALIGNED":
        bearish_signals += 2

    # BB
    if bb_data.get("near_lower"):
        bullish_signals += 1
    if bb_data.get("near_upper"):
        bearish_signals += 1

    # OBV
    if obv_data.get("trend") == "RISING":
        bullish_signals += 1
    elif obv_data.get("trend") == "FALLING":
        bearish_signals += 1

    # Williams %R
    if williams_r is not None:
        if williams_r < -80:
            bullish_signals += 1
        elif williams_r > -20:
            bearish_signals += 1

    # CCI
    if cci_data.get("oversold"):
        bullish_signals += 1
    if cci_data.get("overbought"):
        bearish_signals += 1

    # VPT
    if vpt_data.get("trend") == "RISING":
        bullish_signals += 1
    elif vpt_data.get("trend") == "FALLING":
        bearish_signals += 1

    # Ichimoku
    if ichimoku.get("bullish_signal"):
        bullish_signals += 2
    if ichimoku.get("bearish_signal"):
        bearish_signals += 2
    if ichimoku.get("tenkan_kijun_cross") == "BULLISH":
        bullish_signals += 1
    elif ichimoku.get("tenkan_kijun_cross") == "BEARISH":
        bearish_signals += 1

    # RSI Divergence
    if rsi_div.get("bullish"):
        bullish_signals += 1
    if rsi_div.get("bearish"):
        bearish_signals += 1

    # Candlestick
    if candle_patterns.get("bias") == "BULLISH":
        bullish_signals += 1
    elif candle_patterns.get("bias") == "BEARISH":
        bearish_signals += 1

    # Multi-timeframe
    mf_align = mf_trend.get("alignment", "MIXED")
    if mf_align in ("STRONGLY_BULLISH",):
        bullish_signals += 2
    elif mf_align == "BULLISH":
        bullish_signals += 1
    elif mf_align in ("STRONGLY_BEARISH",):
        bearish_signals += 2
    elif mf_align == "BEARISH":
        bearish_signals += 1

    # Chart patterns
    if chart_pats.get("has_bullish_pattern"):
        bullish_signals += 1
    if chart_pats.get("has_bearish_pattern"):
        bearish_signals += 1

    technical_bias = (
        "BULLISH" if bullish_signals > bearish_signals + 1
        else "BEARISH" if bearish_signals > bullish_signals + 1
        else "NEUTRAL"
    )

    return {
        "symbol": symbol,
        "data_available": True,
        # Core
        "rsi": round(rsi, 1) if rsi is not None else None,
        "macd": macd_data,
        "bollinger": bb_data,
        "atr": round(atr_val, 2) if atr_val is not None else None,
        "adx": round(adx_val, 1) if adx_val is not None else None,
        "stochastic": stoch,
        "obv": obv_data,
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "ema_20": round(ema_20, 2) if ema_20 is not None else None,
        "ema_9": round(ema_9, 2) if ema_9 is not None else None,
        "hist_vol": hist_vol,
        "hist_vol_pct": round(hist_vol * 100, 1) if hist_vol is not None else None,
        "trend_alignment": trend_alignment,
        "above_sma50": above_sma50,
        "above_sma200": above_sma200,
        "above_ema20": above_ema20,
        # Advanced (Batch 1)
        "williams_r": williams_r,
        "williams_r_oversold": williams_r is not None and williams_r < -80,
        "williams_r_overbought": williams_r is not None and williams_r > -20,
        "cci": cci_data,
        "vpt": vpt_data,
        "ad_line": ad_data,
        "ichimoku": ichimoku,
        "fibonacci": fibonacci,
        "pivot_points": pivots,
        "support_resistance": sr,
        "rsi_divergence": rsi_div,
        "candlestick_patterns": candle_patterns,
        "multiframe_trend": mf_trend,
        "chart_patterns": chart_pats,
        # Bias summary
        "technical_bias": technical_bias,
        "bullish_signal_count": bullish_signals,
        "bearish_signal_count": bearish_signals,
        "data_points": len(hist),
    }


# ─────────────────────────────────────────────────────────────────────────────
# URGENT EXIT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def check_urgent_exit(
    position: dict,
    current_ltp: float,
    minutes_to_session_close: int,
    market_regime: dict | None = None,
) -> dict[str, Any]:
    """
    Detect if a custom position needs URGENT EXIT.
    Conditions:
    1. Time < 60 min to 3:30 PM AND position is in loss > 10%
    2. LTP has dropped > 25% from entry AND time < 90 min to close
    3. Expiry today AND position in loss
    Returns: {urgent_exit: bool, reason: str, best_price_hint: float | None}
    """
    buy_price = float(position.get("buy_price", 0))
    remaining_trading_days = int(position.get("remaining_trading_days", 99))
    if buy_price <= 0 or current_ltp <= 0:
        return {"urgent_exit": False, "reason": ""}

    pnl_pct = ((current_ltp - buy_price) / buy_price) * 100
    loss_pct = abs(pnl_pct) if pnl_pct < 0 else 0.0

    # Expiry today condition
    if remaining_trading_days == 0:
        if pnl_pct < 0:
            return {
                "urgent_exit": True,
                "reason": f"EXPIRY TODAY with loss {pnl_pct:.1f}% — exit immediately at best price",
                "best_price_hint": round(current_ltp * 1.005, 2),  # try to get slightly above LTP
            }
        elif minutes_to_session_close <= 45:
            return {
                "urgent_exit": True,
                "reason": f"EXPIRY TODAY — {minutes_to_session_close}m to close; lock in profit now",
                "best_price_hint": round(current_ltp * 0.998, 2),
            }

    # Near close with significant loss
    if minutes_to_session_close <= 60 and loss_pct >= 10:
        return {
            "urgent_exit": True,
            "reason": f"Only {minutes_to_session_close}m to market close with {loss_pct:.1f}% loss — recovery unlikely; exit at best price within 60s",
            "best_price_hint": round(current_ltp * 1.005, 2),
        }

    # Sharp drop from entry
    if loss_pct >= 25 and minutes_to_session_close <= 90:
        return {
            "urgent_exit": True,
            "reason": f"Sharp {loss_pct:.1f}% decline from entry with only {minutes_to_session_close}m to close — trend reversal confirmed; exit at best price",
            "best_price_hint": round(current_ltp * 1.008, 2),
        }

    # Crash regime + loss
    if market_regime and market_regime.get("regime") == "CRASH_MODE" and loss_pct >= 15:
        return {
            "urgent_exit": True,
            "reason": f"Market in CRASH regime (VIX={market_regime.get('vix', 'N/A')}) with {loss_pct:.1f}% position loss — exit recommended",
            "best_price_hint": round(current_ltp * 1.01, 2),
        }

    return {"urgent_exit": False, "reason": "", "best_price_hint": None}


# ─────────────────────────────────────────────────────────────────────────────
# CONFLUENCE SCORE ENHANCEMENTS (additive inputs)
# ─────────────────────────────────────────────────────────────────────────────

def compute_technical_confluence_bonus(
    direction: str,
    rsi: float | None,
    macd_bullish: bool | None,
    macd_above_zero: bool | None,
    trend_alignment: str | None,
    obv_trend: str | None,
    adx: float | None,
    bb_pct_b: float | None,
    stoch_k: float | None,
    # Batch 1 additions (all optional for backward compat)
    williams_r: float | None = None,
    cci: float | None = None,
    vpt_trend: str | None = None,
    ichimoku_price_vs_cloud: str | None = None,
    ichimoku_tk_cross: str | None = None,
    ichimoku_bullish: bool | None = None,
    ichimoku_bearish: bool | None = None,
    rsi_divergence: str | None = None,
    rsi_div_type: str | None = None,
    candle_bias: str | None = None,
    mf_alignment: str | None = None,
    has_bull_chart_pattern: bool = False,
    has_bear_chart_pattern: bool = False,
    ad_trend: str | None = None,
) -> tuple[int, list[str]]:
    """
    Compute additive technical bonus score for confluence scoring (Batch 1 enhanced).
    Returns (bonus_score: int, trigger_tags: list[str]).
    Cap raised to 18 to accommodate Batch 1 indicators.
    """
    bonus = 0
    tags: list[str] = []

    # ── RSI (max 4 pts) ───────────────────────────────────────────────────────
    if rsi is not None:
        if direction == "BULLISH":
            if 35 <= rsi <= 50:
                bonus += 4; tags.append(f"RSI={rsi:.0f}(OversoldRecovery)")
            elif 25 <= rsi < 35:
                bonus += 3; tags.append(f"RSI={rsi:.0f}(Oversold)")
            elif 50 < rsi <= 60:
                bonus += 2; tags.append(f"RSI={rsi:.0f}(Rising)")
            elif rsi > 70:
                bonus -= 2; tags.append(f"RSI={rsi:.0f}(Overbought-Caution)")
        elif direction == "BEARISH":
            if 50 <= rsi <= 65:
                bonus += 4; tags.append(f"RSI={rsi:.0f}(Overbought)")
            elif rsi > 65:
                bonus += 3; tags.append(f"RSI={rsi:.0f}(ExtremOverbought)")
            elif 40 < rsi < 50:
                bonus += 2; tags.append(f"RSI={rsi:.0f}(Falling)")
            elif rsi < 30:
                bonus -= 2; tags.append(f"RSI={rsi:.0f}(Oversold-Caution)")

    # ── MACD (max 3 pts) ──────────────────────────────────────────────────────
    if macd_bullish is not None:
        if direction == "BULLISH" and macd_bullish:
            bonus += 3; tags.append("MACD_BullishCross")
        elif direction == "BEARISH" and not macd_bullish and macd_above_zero is False:
            bonus += 3; tags.append("MACD_BearishCross")
        elif direction == "BULLISH" and macd_above_zero:
            bonus += 1; tags.append("MACD_AboveZero")
        elif direction == "BEARISH" and not macd_above_zero:
            bonus += 1; tags.append("MACD_BelowZero")

    # ── MA Trend alignment (max 3 pts) ────────────────────────────────────────
    if trend_alignment == "BULLISH_ALIGNED" and direction == "BULLISH":
        bonus += 3; tags.append("TrendAligned_Bullish")
    elif trend_alignment == "BEARISH_ALIGNED" and direction == "BEARISH":
        bonus += 3; tags.append("TrendAligned_Bearish")
    elif trend_alignment == "SHORT_TERM_BULLISH" and direction == "BULLISH":
        bonus += 1; tags.append("ShortTermBullish")
    elif trend_alignment == "SHORT_TERM_BEARISH" and direction == "BEARISH":
        bonus += 1; tags.append("ShortTermBearish")

    # ── OBV (max 1 pt) ────────────────────────────────────────────────────────
    if obv_trend == "RISING" and direction == "BULLISH":
        bonus += 1; tags.append("OBV_Rising")
    elif obv_trend == "FALLING" and direction == "BEARISH":
        bonus += 1; tags.append("OBV_Falling")

    # ── ADX (max 2 pts) ───────────────────────────────────────────────────────
    if adx is not None:
        if adx > 30:
            bonus += 2; tags.append(f"ADX={adx:.0f}(StrongTrend)")
        elif adx > 20:
            bonus += 1; tags.append(f"ADX={adx:.0f}(ModTrend)")

    # ── BB position (max 1 pt) ────────────────────────────────────────────────
    if bb_pct_b is not None:
        if bb_pct_b < 0.15 and direction == "BULLISH":
            bonus += 1; tags.append("BB_NearSupport")
        elif bb_pct_b > 0.85 and direction == "BEARISH":
            bonus += 1; tags.append("BB_NearResistance")

    # ── Stochastic (max 1 pt) ─────────────────────────────────────────────────
    if stoch_k is not None:
        if stoch_k < 20 and direction == "BULLISH":
            bonus += 1; tags.append(f"Stoch={stoch_k:.0f}(Oversold)")
        elif stoch_k > 80 and direction == "BEARISH":
            bonus += 1; tags.append(f"Stoch={stoch_k:.0f}(Overbought)")

    # ── Williams %R (max 1 pt) ────────────────────────────────────────────────
    if williams_r is not None:
        if williams_r < -80 and direction == "BULLISH":
            bonus += 1; tags.append(f"WilliamsR={williams_r:.0f}(Oversold)")
        elif williams_r > -20 and direction == "BEARISH":
            bonus += 1; tags.append(f"WilliamsR={williams_r:.0f}(Overbought)")

    # ── CCI (max 1 pt) ────────────────────────────────────────────────────────
    if cci is not None:
        if cci < -100 and direction == "BULLISH":
            bonus += 1; tags.append(f"CCI={cci:.0f}(Oversold)")
        elif cci > 100 and direction == "BEARISH":
            bonus += 1; tags.append(f"CCI={cci:.0f}(Overbought)")

    # ── VPT + A/D confirmation (max 1 pt) ─────────────────────────────────────
    if vpt_trend == "RISING" and direction == "BULLISH":
        bonus += 1; tags.append("VPT_Rising")
    elif vpt_trend == "FALLING" and direction == "BEARISH":
        bonus += 1; tags.append("VPT_Falling")
    elif ad_trend == "RISING" and direction == "BULLISH":
        bonus += 1; tags.append("AD_Accumulation")
    elif ad_trend == "FALLING" and direction == "BEARISH":
        bonus += 1; tags.append("AD_Distribution")

    # ── Ichimoku (max 3 pts) ──────────────────────────────────────────────────
    if ichimoku_bullish and direction == "BULLISH":
        bonus += 3; tags.append("Ichimoku_BullishFull")
    elif ichimoku_bearish and direction == "BEARISH":
        bonus += 3; tags.append("Ichimoku_BearishFull")
    elif ichimoku_price_vs_cloud == "ABOVE" and direction == "BULLISH":
        bonus += 2; tags.append("Ichimoku_PriceAboveCloud")
    elif ichimoku_price_vs_cloud == "BELOW" and direction == "BEARISH":
        bonus += 2; tags.append("Ichimoku_PriceBelowCloud")
    elif ichimoku_price_vs_cloud == "INSIDE":
        bonus -= 1; tags.append("Ichimoku_InsideCloud(Uncertainty)")

    if ichimoku_tk_cross == "BULLISH" and direction == "BULLISH":
        bonus += 1; tags.append("Ichimoku_TKCross_Bullish")
    elif ichimoku_tk_cross == "BEARISH" and direction == "BEARISH":
        bonus += 1; tags.append("Ichimoku_TKCross_Bearish")

    # ── RSI Divergence (max 2 pts) ────────────────────────────────────────────
    if rsi_divergence == "BULLISH" and direction == "BULLISH":
        pts = 2 if rsi_div_type == "REGULAR" else 1
        bonus += pts; tags.append(f"RSIDivergence_{rsi_div_type}_Bullish")
    elif rsi_divergence == "BEARISH" and direction == "BEARISH":
        pts = 2 if rsi_div_type == "REGULAR" else 1
        bonus += pts; tags.append(f"RSIDivergence_{rsi_div_type}_Bearish")

    # ── Candlestick patterns (max 2 pts) ──────────────────────────────────────
    if candle_bias == "BULLISH" and direction == "BULLISH":
        bonus += 2; tags.append("CandlePattern_Bullish")
    elif candle_bias == "BEARISH" and direction == "BEARISH":
        bonus += 2; tags.append("CandlePattern_Bearish")
    elif candle_bias is not None and candle_bias != "NEUTRAL" and candle_bias != direction:
        bonus -= 1; tags.append(f"CandlePattern_{candle_bias}(ContraDirection)")

    # ── Multi-timeframe alignment (max 2 pts) ─────────────────────────────────
    if mf_alignment in ("STRONGLY_BULLISH",) and direction == "BULLISH":
        bonus += 2; tags.append("MTF_StronglyBullish")
    elif mf_alignment == "BULLISH" and direction == "BULLISH":
        bonus += 1; tags.append("MTF_Bullish")
    elif mf_alignment in ("STRONGLY_BEARISH",) and direction == "BEARISH":
        bonus += 2; tags.append("MTF_StronglyBearish")
    elif mf_alignment == "BEARISH" and direction == "BEARISH":
        bonus += 1; tags.append("MTF_Bearish")

    # ── Chart patterns (max 1 pt) ─────────────────────────────────────────────
    if has_bull_chart_pattern and direction == "BULLISH":
        bonus += 1; tags.append("ChartPattern_Bullish(Flag/Pennant)")
    elif has_bear_chart_pattern and direction == "BEARISH":
        bonus += 1; tags.append("ChartPattern_Bearish(Flag/Pennant)")

    # Cap: -6 to +18
    bonus = max(-6, min(bonus, 18))
    return bonus, tags


# ─────────────────────────────────────────────────────────────────────────────
# ENHANCED PORTFOLIO VERDICT
# ─────────────────────────────────────────────────────────────────────────────

def compute_portfolio_verdict(
    pnl_pct: float,
    price_zone: str,
    value_flag: str,
    rsi: float | None,
    trend_alignment: str | None,
    piotroski: float | None,
    beneish: float | None,
    hist_vol: float | None,
    allocation_pct: float,
) -> tuple[str, str]:
    """
    Compute standardized verdict and comments for portfolio holding.
    Returns (verdict: str, comments: str)
    Verdict scale: STRONG HOLD | BUY MORE NOW | ACCUMULATE ON DIPS |
                   WAIT & WATCH | PARTIAL EXIT | EXIT IMMEDIATELY
    """
    comments_parts: list[str] = []
    verdict_score = 0  # Higher = more bullish

    # P&L
    if pnl_pct > 30:
        verdict_score -= 1
        comments_parts.append(f"Up {pnl_pct:.1f}% — consider partial profit booking")
    elif pnl_pct > 0:
        verdict_score += 1
    elif pnl_pct < -25:
        verdict_score -= 2
        comments_parts.append(f"Down {abs(pnl_pct):.1f}% — review thesis before averaging")
    elif pnl_pct < 0:
        verdict_score -= 1
        comments_parts.append(f"Down {abs(pnl_pct):.1f}% — monitor closely")

    # Valuation
    if value_flag == "Attractive":
        verdict_score += 2
        comments_parts.append("Attractive valuation")
    elif value_flag == "Expensive":
        verdict_score -= 1
        comments_parts.append("Expensive valuation")

    # Price zone
    if price_zone == "Near 52W low":
        verdict_score += 2
        comments_parts.append("Near 52W low — potential base building")
    elif price_zone == "Near 52W high":
        verdict_score -= 1
        comments_parts.append("Near 52W high — momentum but limited upside buffer")

    # Technical indicators
    if rsi is not None:
        if rsi < 35:
            verdict_score += 2
            comments_parts.append(f"RSI {rsi:.0f} — oversold territory, potential bounce")
        elif rsi > 70:
            verdict_score -= 1
            comments_parts.append(f"RSI {rsi:.0f} — overbought, near-term pullback possible")
        else:
            comments_parts.append(f"RSI {rsi:.0f} — neutral momentum")

    if trend_alignment == "BULLISH_ALIGNED":
        verdict_score += 2
        comments_parts.append("Multi-timeframe bullish trend aligned")
    elif trend_alignment == "BEARISH_ALIGNED":
        verdict_score -= 2
        comments_parts.append("Multi-timeframe bearish trend — cautious stance")
    elif trend_alignment == "MIXED":
        comments_parts.append("Mixed trend signals — wait for confirmation")

    # Forensic quality
    if piotroski is not None:
        if piotroski >= 7:
            verdict_score += 1
            comments_parts.append(f"Piotroski F-Score {piotroski}/9 — high quality")
        elif piotroski <= 3:
            verdict_score -= 1
            comments_parts.append(f"Piotroski F-Score {piotroski}/9 — weak financials")

    if beneish is not None and beneish > -2.22:
        verdict_score -= 1
        comments_parts.append(f"Beneish M-Score {beneish:.2f} — earnings quality concern")

    # Concentration penalty
    if allocation_pct > 20:
        comments_parts.append(f"Over-concentrated ({allocation_pct:.1f}% of portfolio) — consider rebalancing")

    # Volatility context
    if hist_vol is not None and hist_vol > 0.45:
        comments_parts.append(f"High volatility stock ({hist_vol*100:.0f}% annual vol) — position sizing caution")

    # Verdict mapping
    if verdict_score >= 5:
        verdict = "BUY MORE NOW"
    elif verdict_score >= 3:
        verdict = "ACCUMULATE ON DIPS"
    elif verdict_score >= 1:
        verdict = "STRONG HOLD"
    elif verdict_score >= -1:
        verdict = "WAIT & WATCH"
    elif verdict_score >= -3:
        verdict = "PARTIAL EXIT"
    else:
        verdict = "EXIT IMMEDIATELY"

    comments = "; ".join(comments_parts) if comments_parts else "Balanced profile — hold and monitor."
    return verdict, comments



# ─────────────────────────────────────────────────────────────────────────────
# BATCH 1: ADVANCED TECHNICAL INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def compute_williams_r(hist: pd.DataFrame, period: int = 14) -> float | None:
    """Williams %R: -100 to 0. Oversold < -80, Overbought > -20."""
    if hist is None or len(hist) < period:
        return None
    high = hist["High"].rolling(period).max()
    low = hist["Low"].rolling(period).min()
    close = hist["Close"]
    wr = -100 * (high - close) / (high - low).replace(0, np.nan)
    val = wr.iloc[-1]
    return round(float(val), 2) if not pd.isna(val) else None


def compute_cci(hist: pd.DataFrame, period: int = 20) -> dict[str, Any]:
    """Commodity Channel Index. >+100 = overbought, <-100 = oversold."""
    if hist is None or len(hist) < period:
        return {"cci": None, "overbought": False, "oversold": False}
    typical_price = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    sma_tp = typical_price.rolling(period).mean()
    mad = typical_price.rolling(period).apply(lambda x: float(np.abs(x - x.mean()).mean()), raw=True)
    cci = (typical_price - sma_tp) / (0.015 * mad.replace(0, np.nan))
    val = cci.iloc[-1]
    v = round(float(val), 2) if not pd.isna(val) else None
    return {
        "cci": v,
        "overbought": v is not None and v > 100,
        "oversold": v is not None and v < -100,
    }


def compute_vpt(hist: pd.DataFrame) -> dict[str, Any]:
    """Volume Price Trend (VPT). Trend: RISING/FALLING/FLAT."""
    if hist is None or len(hist) < 5:
        return {"vpt": None, "trend": "FLAT"}
    close = hist["Close"]
    volume = hist["Volume"]
    price_change_pct = close.pct_change().fillna(0)
    vpt = (volume * price_change_pct).cumsum()
    recent = vpt.iloc[-5:]
    r0 = float(recent.iloc[0])
    r1 = float(recent.iloc[-1])
    trend = "RISING" if r1 > r0 * 1.005 else ("FALLING" if r1 < r0 * 0.995 else "FLAT")
    return {"vpt": round(float(vpt.iloc[-1]), 2), "trend": trend}


def compute_ad_line(hist: pd.DataFrame) -> dict[str, Any]:
    """Accumulation/Distribution Line. Trend: RISING/FALLING/FLAT."""
    if hist is None or len(hist) < 5:
        return {"ad": None, "trend": "FLAT"}
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    volume = hist["Volume"]
    hl_diff = (high - low).replace(0, np.nan)
    clv = ((close - low) - (high - close)) / hl_diff
    clv = clv.fillna(0)
    ad = (clv * volume).cumsum()
    recent = ad.iloc[-10:]
    r0 = float(recent.iloc[0]) if not pd.isna(recent.iloc[0]) else 0
    r1 = float(recent.iloc[-1]) if not pd.isna(recent.iloc[-1]) else 0
    trend = "RISING" if r1 > r0 * 1.005 else ("FALLING" if r1 < r0 * 0.995 else "FLAT")
    return {"ad": round(float(ad.iloc[-1]), 2), "trend": trend}


def compute_ichimoku(hist: pd.DataFrame) -> dict[str, Any]:
    """
    Ichimoku Cloud: Tenkan (9), Kijun (26), Senkou A/B, Chikou, Kumo.
    Returns cloud color, price vs cloud, TK cross, Kumo twist, and signal flags.
    """
    if hist is None or len(hist) < 52:
        return {"available": False}

    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    def safe(s, idx=-1):
        v = s.iloc[idx]
        return float(v) if not pd.isna(v) else None

    t = safe(tenkan)
    k = safe(kijun)
    sa = safe(senkou_a)
    sb = safe(senkou_b)
    c = float(close.iloc[-1])

    cloud_color = "GREEN" if (sa is not None and sb is not None and sa > sb) else "RED"

    price_vs_cloud = "UNKNOWN"
    if sa is not None and sb is not None:
        cloud_top = max(sa, sb)
        cloud_bottom = min(sa, sb)
        if c > cloud_top:
            price_vs_cloud = "ABOVE"
        elif c < cloud_bottom:
            price_vs_cloud = "BELOW"
        else:
            price_vs_cloud = "INSIDE"

    tk_cross = "NONE"
    if t is not None and k is not None and len(tenkan) >= 2 and len(kijun) >= 2:
        prev_t = safe(tenkan, -2)
        prev_k = safe(kijun, -2)
        if prev_t is not None and prev_k is not None:
            if t > k and prev_t <= prev_k:
                tk_cross = "BULLISH"
            elif t < k and prev_t >= prev_k:
                tk_cross = "BEARISH"

    kumo_twist = False
    if sa is not None and sb is not None:
        prev_sa = safe(senkou_a, -2)
        prev_sb = safe(senkou_b, -2)
        if prev_sa is not None and prev_sb is not None:
            if (sa > sb and prev_sa <= prev_sb) or (sa < sb and prev_sa >= prev_sb):
                kumo_twist = True

    bullish_signal = (
        price_vs_cloud == "ABOVE"
        and cloud_color == "GREEN"
        and t is not None and k is not None and t > k
    )
    bearish_signal = (
        price_vs_cloud == "BELOW"
        and cloud_color == "RED"
        and t is not None and k is not None and t < k
    )

    return {
        "available": True,
        "tenkan": round(t, 2) if t is not None else None,
        "kijun": round(k, 2) if k is not None else None,
        "senkou_a": round(sa, 2) if sa is not None else None,
        "senkou_b": round(sb, 2) if sb is not None else None,
        "cloud_color": cloud_color,
        "price_vs_cloud": price_vs_cloud,
        "tenkan_kijun_cross": tk_cross,
        "kumo_twist": kumo_twist,
        "bullish_signal": bullish_signal,
        "bearish_signal": bearish_signal,
    }


def compute_fibonacci_levels(hist: pd.DataFrame, lookback: int = 100) -> dict[str, Any]:
    """
    Fibonacci retracement and extension levels using recent swing high/low.
    Ratios: 23.6%, 38.2%, 50%, 61.8%, 78.6% (retracement) + 127.2%, 161.8% (extension).
    """
    if hist is None or len(hist) < 20:
        return {"available": False}

    window = hist.tail(min(lookback, len(hist)))
    swing_high = float(window["High"].max())
    swing_low = float(window["Low"].min())
    ltp = float(hist["Close"].iloc[-1])

    if swing_high <= swing_low or swing_low <= 0:
        return {"available": False}

    price_range = swing_high - swing_low

    retrace_ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    extend_ratios = [1.272, 1.618, 2.0]

    retracements = {
        f"fib_{int(r * 1000)}": round(swing_high - r * price_range, 2)
        for r in retrace_ratios
    }
    extensions = {
        f"fib_ext_{int(r * 1000)}": round(swing_low + r * price_range, 2)
        for r in extend_ratios
    }

    all_levels = list(retracements.values())
    nearest = min(all_levels, key=lambda x: abs(x - ltp))
    nearest_pct_away = round(abs(nearest - ltp) / ltp * 100, 2)

    fib_382 = retracements.get("fib_382", swing_high - 0.382 * price_range)
    fib_618 = retracements.get("fib_618", swing_high - 0.618 * price_range)

    if ltp >= fib_382:
        fib_zone = "UPPER_HALF"
    elif ltp >= fib_618:
        fib_zone = "MIDDLE"
    else:
        fib_zone = "LOWER_HALF"

    return {
        "available": True,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "lookback_bars": len(window),
        "retracements": retracements,
        "extensions": extensions,
        "nearest_level": round(nearest, 2),
        "nearest_level_pct_away": nearest_pct_away,
        "fib_zone": fib_zone,
        "fib_236": retracements.get("fib_236"),
        "fib_382": retracements.get("fib_382"),
        "fib_500": retracements.get("fib_500"),
        "fib_618": retracements.get("fib_618"),
        "fib_786": retracements.get("fib_786"),
    }


def compute_pivot_points(hist: pd.DataFrame) -> dict[str, Any]:
    """
    Classic pivots (PP, S1/S2/S3, R1/R2/R3) and Camarilla (H3/H4, L3/L4)
    based on previous session's OHLC.
    """
    if hist is None or len(hist) < 2:
        return {"available": False}

    prev = hist.iloc[-2]
    h = float(prev["High"])
    l = float(prev["Low"])
    c = float(prev["Close"])
    ltp = float(hist["Close"].iloc[-1])

    pp = (h + l + c) / 3
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)
    r3 = h + 2 * (pp - l)
    s3 = l - 2 * (h - pp)

    diff = h - l
    ch4 = round(c + diff * 1.1 / 2, 2)
    ch3 = round(c + diff * 1.1 / 4, 2)
    cl3 = round(c - diff * 1.1 / 4, 2)
    cl4 = round(c - diff * 1.1 / 2, 2)

    supports = [s1, s2, s3]
    resistances = [r1, r2, r3]
    ns = max((x for x in supports if x < ltp), default=s3)
    nr = min((x for x in resistances if x > ltp), default=r1)

    return {
        "available": True,
        "classic": {
            "pp": round(pp, 2),
            "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
            "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
        },
        "camarilla": {
            "h4": ch4, "h3": ch3, "l3": cl3, "l4": cl4,
        },
        "ltp_vs_pp": "ABOVE" if ltp > pp else "BELOW",
        "nearest_support": round(ns, 2),
        "nearest_resistance": round(nr, 2),
    }


def compute_support_resistance(
    hist: pd.DataFrame, lookback: int = 60, n_levels: int = 3
) -> dict[str, Any]:
    """
    Identify horizontal support/resistance levels from swing highs/lows.
    Groups nearby levels into clusters (within 0.5%).
    """
    if hist is None or len(hist) < 20:
        return {"support_levels": [], "resistance_levels": [], "available": False}

    window = hist.tail(min(lookback, len(hist)))
    high_arr = window["High"].values
    low_arr = window["Low"].values
    close_arr = window["Close"].values
    ltp = float(close_arr[-1])

    swing_highs: list[float] = []
    swing_lows: list[float] = []
    for i in range(2, len(high_arr) - 2):
        if (high_arr[i] > high_arr[i-1] and high_arr[i] > high_arr[i-2]
                and high_arr[i] > high_arr[i+1] and high_arr[i] > high_arr[i+2]):
            swing_highs.append(float(high_arr[i]))
        if (low_arr[i] < low_arr[i-1] and low_arr[i] < low_arr[i-2]
                and low_arr[i] < low_arr[i+1] and low_arr[i] < low_arr[i+2]):
            swing_lows.append(float(low_arr[i]))

    def cluster(levels: list[float], thresh: float = 0.005) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        groups: list[list[float]] = [[levels[0]]]
        for lvl in levels[1:]:
            if abs(lvl - groups[-1][-1]) / max(groups[-1][-1], 1) < thresh:
                groups[-1].append(lvl)
            else:
                groups.append([lvl])
        return [round(sum(g) / len(g), 2) for g in groups]

    resistance_levels = sorted(
        [l for l in cluster(swing_highs) if l > ltp]
    )[:n_levels]
    support_levels = sorted(
        [l for l in cluster(swing_lows) if l < ltp], reverse=True
    )[:n_levels]

    return {
        "available": True,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "nearest_support": support_levels[0] if support_levels else None,
        "nearest_resistance": resistance_levels[0] if resistance_levels else None,
    }


def detect_rsi_divergence(
    hist: pd.DataFrame, rsi_period: int = 14, lookback: int = 20
) -> dict[str, Any]:
    """
    Detect RSI divergence (regular + hidden, bullish + bearish).
    Regular Bullish: price lower low + RSI higher low → potential reversal up.
    Regular Bearish: price higher high + RSI lower high → potential reversal down.
    Hidden Bullish: price higher low + RSI lower low → trend continuation.
    Hidden Bearish: price lower high + RSI higher high → trend continuation down.
    """
    if hist is None or len(hist) < rsi_period + lookback + 5:
        return {"divergence": "NONE", "type": None, "bullish": False, "bearish": False}

    close = hist["Close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = (100 - (100 / (1 + rs))).dropna()
    price_series = close[-len(rsi_series):]

    n = min(lookback, len(rsi_series))
    rsi_w = rsi_series.iloc[-n:].values
    price_w = price_series.iloc[-n:].values

    def find_extremes(arr: np.ndarray, kind: str) -> list[tuple[int, float]]:
        result = []
        for i in range(1, len(arr) - 1):
            if kind == "high" and arr[i] > arr[i-1] and arr[i] > arr[i+1]:
                result.append((i, float(arr[i])))
            elif kind == "low" and arr[i] < arr[i-1] and arr[i] < arr[i+1]:
                result.append((i, float(arr[i])))
        return result

    ph = find_extremes(price_w, "high")
    pl = find_extremes(price_w, "low")
    rh = find_extremes(rsi_w, "high")
    rl = find_extremes(rsi_w, "low")

    divergence = "NONE"
    div_type = None

    if len(ph) >= 2 and len(rh) >= 2:
        if ph[-1][1] > ph[-2][1] and rh[-1][1] < rh[-2][1]:
            divergence, div_type = "BEARISH", "REGULAR"
        elif ph[-1][1] < ph[-2][1] and rh[-1][1] > rh[-2][1]:
            if divergence == "NONE":
                divergence, div_type = "BEARISH", "HIDDEN"

    if len(pl) >= 2 and len(rl) >= 2:
        if pl[-1][1] < pl[-2][1] and rl[-1][1] > rl[-2][1]:
            divergence, div_type = "BULLISH", "REGULAR"
        elif pl[-1][1] > pl[-2][1] and rl[-1][1] < rl[-2][1]:
            if divergence == "NONE":
                divergence, div_type = "BULLISH", "HIDDEN"

    return {
        "divergence": divergence,
        "type": div_type,
        "bullish": divergence == "BULLISH",
        "bearish": divergence == "BEARISH",
        "description": (
            f"{div_type} {divergence} divergence detected"
            if divergence != "NONE" else "No divergence"
        ),
    }


def detect_candlestick_patterns(hist: pd.DataFrame, lookback: int = 5) -> dict[str, Any]:
    """
    Detect common single/double/triple candlestick patterns on recent candles.
    Patterns: Doji, Hammer, Inverted Hammer, Shooting Star,
              Bullish/Bearish Engulfing, Bullish/Bearish Harami,
              Morning Star, Evening Star.
    """
    if hist is None or len(hist) < 3:
        return {"patterns": [], "bias": "NEUTRAL"}

    df = hist.tail(max(lookback, 3))
    o = df["Open"].values.astype(float)
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    c = df["Close"].values.astype(float)
    n = len(o)
    i = n - 1  # latest candle index

    def body(idx): return abs(c[idx] - o[idx])
    def full_range(idx): return max(h[idx] - l[idx], 1e-6)
    def upper_wick(idx): return h[idx] - max(o[idx], c[idx])
    def lower_wick(idx): return min(o[idx], c[idx]) - l[idx]
    def is_bull(idx): return c[idx] > o[idx]
    def is_bear(idx): return c[idx] < o[idx]

    patterns: list[str] = []

    if body(i) < 0.1 * full_range(i):
        patterns.append("DOJI")

    if (lower_wick(i) >= 2 * max(body(i), 1e-4)
            and upper_wick(i) < 0.3 * full_range(i)
            and body(i) / full_range(i) < 0.35):
        patterns.append("HAMMER")

    if (upper_wick(i) >= 2 * max(body(i), 1e-4)
            and lower_wick(i) < 0.3 * full_range(i)
            and is_bull(i)):
        patterns.append("INVERTED_HAMMER")

    if (upper_wick(i) >= 2 * max(body(i), 1e-4)
            and lower_wick(i) < 0.3 * full_range(i)
            and is_bear(i)):
        patterns.append("SHOOTING_STAR")

    if i >= 1:
        if is_bear(i-1) and is_bull(i) and o[i] <= c[i-1] and c[i] >= o[i-1]:
            patterns.append("BULLISH_ENGULFING")
        if is_bull(i-1) and is_bear(i) and o[i] >= c[i-1] and c[i] <= o[i-1]:
            patterns.append("BEARISH_ENGULFING")
        if is_bear(i-1) and is_bull(i) and c[i-1] < o[i] < o[i-1] and o[i-1] > c[i] > c[i-1]:
            patterns.append("BULLISH_HARAMI")
        if is_bull(i-1) and is_bear(i) and o[i-1] < o[i] < c[i-1] and c[i-1] > c[i] > o[i-1]:
            patterns.append("BEARISH_HARAMI")

    if i >= 2:
        if (is_bear(i-2) and body(i-1) < 0.3 * body(i-2) and is_bull(i)
                and c[i] > (o[i-2] + c[i-2]) / 2):
            patterns.append("MORNING_STAR")
        if (is_bull(i-2) and body(i-1) < 0.3 * body(i-2) and is_bear(i)
                and c[i] < (o[i-2] + c[i-2]) / 2):
            patterns.append("EVENING_STAR")

    BULL_PATTERNS = {"HAMMER", "INVERTED_HAMMER", "BULLISH_ENGULFING", "BULLISH_HARAMI", "MORNING_STAR"}
    BEAR_PATTERNS = {"SHOOTING_STAR", "BEARISH_ENGULFING", "BEARISH_HARAMI", "EVENING_STAR"}

    b_cnt = sum(1 for p in patterns if p in BULL_PATTERNS)
    bear_cnt = sum(1 for p in patterns if p in BEAR_PATTERNS)
    bias = "BULLISH" if b_cnt > bear_cnt else ("BEARISH" if bear_cnt > b_cnt else "NEUTRAL")

    return {
        "patterns": patterns,
        "bias": bias,
        "bullish_count": b_cnt,
        "bearish_count": bear_cnt,
    }


def compute_multiframe_trend(hist: pd.DataFrame) -> dict[str, Any]:
    """
    Derive trend for Daily (20d), Weekly (~12w), Monthly (~6m) using daily OHLCV.
    Alignment: STRONGLY_BULLISH / BULLISH / MIXED / BEARISH / STRONGLY_BEARISH.
    """
    if hist is None or len(hist) < 50:
        return {
            "daily": "NEUTRAL", "weekly": "NEUTRAL", "monthly": "NEUTRAL",
            "alignment": "MIXED", "bullish_frames": 0, "bearish_frames": 0,
        }

    def trend_from_close(s: pd.Series) -> str:
        if len(s) < 5:
            return "NEUTRAL"
        fast = s.ewm(span=max(3, len(s)//4), adjust=False).mean()
        slow = s.ewm(span=max(5, len(s)//2), adjust=False).mean()
        if float(fast.iloc[-1]) > float(slow.iloc[-1]) and float(s.iloc[-1]) > float(s.mean()):
            return "BULLISH"
        if float(fast.iloc[-1]) < float(slow.iloc[-1]) and float(s.iloc[-1]) < float(s.mean()):
            return "BEARISH"
        return "NEUTRAL"

    daily_trend = trend_from_close(hist["Close"].tail(20))

    weekly_trend = "NEUTRAL"
    try:
        if isinstance(hist.index, pd.DatetimeIndex):
            wkly = hist["Close"].resample("W").last().dropna().tail(12)
            weekly_trend = trend_from_close(wkly)
        else:
            weekly_trend = trend_from_close(hist["Close"].tail(60).iloc[::5])
    except Exception:
        pass

    monthly_trend = "NEUTRAL"
    try:
        if isinstance(hist.index, pd.DatetimeIndex):
            mthly = hist["Close"].resample("ME").last().dropna().tail(6)
            monthly_trend = trend_from_close(mthly)
        else:
            monthly_trend = trend_from_close(hist["Close"].tail(126).iloc[::21])
    except Exception:
        pass

    trends = [daily_trend, weekly_trend, monthly_trend]
    bull_cnt = trends.count("BULLISH")
    bear_cnt = trends.count("BEARISH")

    if bull_cnt == 3:
        alignment = "STRONGLY_BULLISH"
    elif bull_cnt == 2:
        alignment = "BULLISH"
    elif bear_cnt == 3:
        alignment = "STRONGLY_BEARISH"
    elif bear_cnt == 2:
        alignment = "BEARISH"
    else:
        alignment = "MIXED"

    return {
        "daily": daily_trend,
        "weekly": weekly_trend,
        "monthly": monthly_trend,
        "alignment": alignment,
        "bullish_frames": bull_cnt,
        "bearish_frames": bear_cnt,
    }


def detect_chart_patterns(hist: pd.DataFrame, lookback: int = 60) -> dict[str, Any]:
    """
    Detect Bull Flag, Bear Flag, and Pennant patterns using price action.
    Requires at least 30 bars. Returns list of detected patterns with confidence.
    """
    if hist is None or len(hist) < 30:
        return {"patterns": [], "has_bullish_pattern": False, "has_bearish_pattern": False,
                "description": "Insufficient data"}

    window = hist.tail(min(lookback, len(hist)))
    close = window["Close"].values.astype(float)
    volume = window["Volume"].values.astype(float)
    n = len(close)

    patterns: list[dict] = []
    pole_end = int(n * 0.55)
    flag_start = int(n * 0.60)

    if pole_end < 5 or flag_start >= n - 3:
        return {"patterns": [], "has_bullish_pattern": False, "has_bearish_pattern": False,
                "description": "Pattern window too small"}

    pole = close[:pole_end]
    flag_seg = close[flag_start:]
    pole_move = (float(pole[-1]) - float(pole[0])) / max(float(pole[0]), 1)
    flag_range = (float(flag_seg.max()) - float(flag_seg.min())) / max(float(pole[-1]), 1)
    pole_vol = float(np.mean(volume[:pole_end])) if pole_end > 0 else 1
    flag_vol = float(np.mean(volume[flag_start:])) if flag_start < n else pole_vol

    if pole_move > 0.05 and flag_range < 0.05 and flag_vol < pole_vol * 0.92:
        conf = "HIGH" if pole_move > 0.10 else "MEDIUM"
        patterns.append({
            "type": "BULL_FLAG",
            "confidence": conf,
            "description": f"Bull flag: +{pole_move*100:.1f}% pole, {flag_range*100:.1f}% consolidation, volume contracting",
        })

    if pole_move < -0.05 and flag_range < 0.05:
        conf = "HIGH" if pole_move < -0.10 else "MEDIUM"
        patterns.append({
            "type": "BEAR_FLAG",
            "confidence": conf,
            "description": f"Bear flag: {pole_move*100:.1f}% drop, {flag_range*100:.1f}% consolidation",
        })

    if abs(pole_move) > 0.04 and n - flag_start >= 5:
        step = max(1, (n - flag_start) // 5)
        idxs = list(range(flag_start, n, step))
        if len(idxs) >= 3:
            flag_highs = [float(close[max(0, j-1): min(n, j+2)].max()) for j in idxs]
            flag_lows = [float(close[max(0, j-1): min(n, j+2)].min()) for j in idxs]
            h_slope = (flag_highs[-1] - flag_highs[0]) / max(abs(flag_highs[0]), 1)
            l_slope = (flag_lows[-1] - flag_lows[0]) / max(abs(flag_lows[0]), 1)
            if h_slope < -0.005 and l_slope > 0.005:
                direction = "BULLISH" if pole_move > 0 else "BEARISH"
                patterns.append({
                    "type": f"{direction}_PENNANT",
                    "confidence": "MEDIUM",
                    "description": f"{direction} pennant forming after {pole_move*100:.1f}% move",
                })

    return {
        "patterns": patterns,
        "has_bullish_pattern": any(p["type"].startswith("BULL") for p in patterns),
        "has_bearish_pattern": any(p["type"].startswith("BEAR") for p in patterns),
        "description": (
            "; ".join(p["description"] for p in patterns)
            if patterns else "No chart pattern detected"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# BATCH 2: FORENSIC FINANCIAL AUDIT
# ─────────────────────────────────────────────────────────────────────────────

def compute_altman_z_score(
    working_capital: float | None,
    retained_earnings: float | None,
    ebit: float | None,
    market_cap: float | None,
    total_liabilities: float | None,
    revenue: float | None,
    total_assets: float | None,
) -> dict[str, Any]:
    """
    Altman Z-Score (5-variable, public company model).
    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT / Total Assets
    X4 = Market Cap / Total Liabilities
    X5 = Revenue / Total Assets
    Zones: >2.99 Safe, 1.81–2.99 Grey, <1.81 Distress
    """
    required = [working_capital, ebit, market_cap, total_liabilities, revenue, total_assets]
    if any(v is None for v in required) or total_assets <= 0 or total_liabilities <= 0:
        return {"z_score": None, "zone": "UNKNOWN", "available": False}

    re = retained_earnings or 0.0
    x1 = working_capital / total_assets
    x2 = re / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities
    x5 = revenue / total_assets

    z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5

    if math.isnan(z) or math.isinf(z):
        return {"z_score": None, "zone": "UNKNOWN", "available": False}

    if z > 2.99:
        zone, color = "SAFE", "green"
        description = f"Z={z:.2f} — Safe Zone. Low bankruptcy risk."
    elif z > 1.81:
        zone, color = "GREY", "yellow"
        description = f"Z={z:.2f} — Grey Zone. Monitor leverage and profitability."
    else:
        zone, color = "DISTRESS", "red"
        description = f"Z={z:.2f} — Distress Zone. High bankruptcy risk — avoid."

    return {
        "available": True,
        "z_score": round(z, 3),
        "zone": zone,
        "color": color,
        "description": description,
        "components": {
            "x1_working_capital_ratio": round(x1, 4),
            "x2_retained_earnings_ratio": round(x2, 4),
            "x3_ebit_ratio": round(x3, 4),
            "x4_market_cap_to_liabilities": round(x4, 4),
            "x5_asset_turnover": round(x5, 4),
        },
    }


def compute_earnings_quality(
    operating_cash_flow: float | None,
    net_income: float | None,
    total_assets: float | None,
    total_assets_prev: float | None = None,
) -> dict[str, Any]:
    """
    Earnings quality metrics:
    - CFO/NI ratio: >1.0 = high quality, <0.5 = accrual-heavy
    - Accrual ratio: (NI - CFO) / Avg Total Assets (positive = accruals increasing, red flag)
    """
    result: dict[str, Any] = {"available": False}

    if operating_cash_flow is None or net_income is None:
        return result

    cfo_ni_ratio = None
    if net_income != 0:
        cfo_ni_ratio = round(operating_cash_flow / net_income, 3)

    accrual_ratio = None
    avg_assets = total_assets
    if total_assets is not None and total_assets > 0:
        if total_assets_prev is not None and total_assets_prev > 0:
            avg_assets = (total_assets + total_assets_prev) / 2
        accrual = (net_income - operating_cash_flow) / avg_assets
        accrual_ratio = round(accrual, 4)

    # Quality assessment
    quality = "HIGH"
    flags: list[str] = []
    if cfo_ni_ratio is not None:
        if cfo_ni_ratio < 0.5:
            quality = "LOW"
            flags.append(f"CFO/NI={cfo_ni_ratio:.2f} (<0.5) — earnings may be accrual-heavy")
        elif cfo_ni_ratio < 0.8:
            quality = "MEDIUM"
            flags.append(f"CFO/NI={cfo_ni_ratio:.2f} (<0.8) — moderate earnings quality")

    if accrual_ratio is not None and accrual_ratio > 0.05:
        quality = "LOW" if quality == "HIGH" else quality
        flags.append(f"Accrual ratio={accrual_ratio:.3f} (>0.05) — positive accruals signal concern")

    return {
        "available": True,
        "cfo_ni_ratio": cfo_ni_ratio,
        "accrual_ratio": accrual_ratio,
        "earnings_quality": quality,
        "flags": flags,
    }


def compute_forensic_red_flags(
    accounts_receivable: float | None,
    revenue: float | None,
    revenue_prev: float | None,
    inventory: float | None,
    cogs: float | None,
    accounts_payable: float | None,
    cwip: float | None,
    total_assets: float | None,
    goodwill: float | None,
    net_worth: float | None,
    shares_outstanding: float | None,
    shares_outstanding_prev: float | None,
    total_debt: float | None,
    operating_income: float | None,
    net_income: float | None,
    deferred_tax_liability: float | None,
    deferred_tax_liability_prev: float | None,
    pledged_shares_pct: float | None = None,
    contingent_liabilities: float | None = None,
) -> dict[str, Any]:
    """
    Forensic red-flag checklist. Computes and flags:
    - Debtor days, Inventory days, Creditor days
    - CWIP / Total Assets
    - Goodwill / Net Worth
    - Share dilution YoY
    - Deferred tax anomalies
    - Pledging %
    - Contingent liabilities / Total Assets
    Returns red_flag_count (0–10+) and details list.
    """
    flags: list[str] = []
    metrics: dict[str, Any] = {}

    # Debtor days
    if accounts_receivable is not None and revenue is not None and revenue > 0:
        debtor_days = round((accounts_receivable / revenue) * 365, 1)
        metrics["debtor_days"] = debtor_days
        if debtor_days > 90:
            flags.append(f"High debtor days: {debtor_days:.0f}d (>90d — slow collection risk)")
        elif debtor_days > 60:
            flags.append(f"Elevated debtor days: {debtor_days:.0f}d (>60d — monitor)")

    # Inventory days
    if inventory is not None and cogs is not None and cogs > 0:
        inv_days = round((inventory / cogs) * 365, 1)
        metrics["inventory_days"] = inv_days
        if inv_days > 180:
            flags.append(f"High inventory days: {inv_days:.0f}d (>180d — excess stock risk)")
        elif inv_days > 90:
            flags.append(f"Elevated inventory days: {inv_days:.0f}d (>90d)")

    # Creditor days
    if accounts_payable is not None and cogs is not None and cogs > 0:
        cred_days = round((accounts_payable / cogs) * 365, 1)
        metrics["creditor_days"] = cred_days
        if cred_days > 120:
            flags.append(f"High creditor days: {cred_days:.0f}d (>120d — stretched payables)")

    # CWIP / Total Assets
    if cwip is not None and total_assets is not None and total_assets > 0:
        cwip_ratio = round(cwip / total_assets, 3)
        metrics["cwip_to_assets"] = cwip_ratio
        if cwip_ratio > 0.20:
            flags.append(f"CWIP = {cwip_ratio*100:.1f}% of assets (>20% — project delay/stalling risk)")

    # Goodwill / Net Worth
    if goodwill is not None and net_worth is not None and net_worth > 0:
        gw_ratio = round(goodwill / net_worth, 3)
        metrics["goodwill_to_net_worth"] = gw_ratio
        if gw_ratio > 0.5:
            flags.append(f"Goodwill = {gw_ratio*100:.1f}% of net worth (>50% — intangible-heavy)")

    # Share dilution
    if shares_outstanding is not None and shares_outstanding_prev is not None and shares_outstanding_prev > 0:
        dilution_pct = round((shares_outstanding - shares_outstanding_prev) / shares_outstanding_prev * 100, 2)
        metrics["dilution_pct_yoy"] = dilution_pct
        if dilution_pct > 5:
            flags.append(f"Share dilution: +{dilution_pct:.1f}% YoY (>5% — equity value erosion)")

    # Deferred tax anomaly
    if (deferred_tax_liability is not None and deferred_tax_liability_prev is not None
            and deferred_tax_liability_prev > 0):
        dtl_growth = round((deferred_tax_liability - deferred_tax_liability_prev) / deferred_tax_liability_prev * 100, 1)
        metrics["deferred_tax_growth_pct"] = dtl_growth
        if dtl_growth > 50:
            flags.append(f"Deferred tax liability grew {dtl_growth:.0f}% YoY (potential timing manipulation)")

    # Pledging
    if pledged_shares_pct is not None:
        metrics["pledged_pct"] = pledged_shares_pct
        if pledged_shares_pct > 50:
            flags.append(f"High promoter pledging: {pledged_shares_pct:.1f}% (>50% — distress signal)")
        elif pledged_shares_pct > 25:
            flags.append(f"Elevated promoter pledging: {pledged_shares_pct:.1f}% (>25% — monitor)")

    # Contingent liabilities
    if contingent_liabilities is not None and total_assets is not None and total_assets > 0:
        cl_ratio = round(contingent_liabilities / total_assets, 3)
        metrics["contingent_liab_to_assets"] = cl_ratio
        if cl_ratio > 0.15:
            flags.append(f"Contingent liabilities = {cl_ratio*100:.1f}% of assets (>15% — hidden risk)")

    red_flag_count = len(flags)
    severity = (
        "HIGH" if red_flag_count >= 4 else
        "MEDIUM" if red_flag_count >= 2 else
        "LOW" if red_flag_count == 1 else
        "CLEAN"
    )

    return {
        "red_flag_count": red_flag_count,
        "severity": severity,
        "flags": flags,
        "metrics": metrics,
    }


def compute_roic_vs_wacc(
    ebit: float | None,
    tax_rate: float = 0.25,
    invested_capital: float | None = None,
    total_assets: float | None = None,
    current_liabilities: float | None = None,
    total_debt: float | None = None,
    market_cap: float | None = None,
    cost_of_debt: float = 0.08,
    cost_of_equity: float = 0.12,
) -> dict[str, Any]:
    """
    Compute ROIC and estimate WACC. Returns ROIC - WACC spread.
    ROIC = NOPAT / Invested Capital
    WACC = Ke×(E/V) + Kd×(D/V)×(1-t)
    Positive spread = value creation; negative = value destruction.
    """
    if ebit is None:
        return {"roic": None, "wacc": None, "spread": None, "available": False}

    nopat = ebit * (1 - tax_rate)

    # Invested capital
    ic = invested_capital
    if ic is None:
        if total_assets is not None and current_liabilities is not None:
            ic = total_assets - current_liabilities
        elif total_assets is not None:
            ic = total_assets * 0.7

    if ic is None or ic <= 0:
        return {"roic": None, "wacc": None, "spread": None, "available": False}

    roic = round(nopat / ic * 100, 2)

    # WACC estimation
    wacc = cost_of_equity * 100  # default if no debt/equity split
    if total_debt is not None and market_cap is not None:
        v = total_debt + market_cap
        if v > 0:
            e_ratio = market_cap / v
            d_ratio = total_debt / v
            wacc = round((cost_of_equity * e_ratio + cost_of_debt * (1 - tax_rate) * d_ratio) * 100, 2)

    spread = round(roic - wacc, 2)
    value_creation = spread > 0

    return {
        "available": True,
        "roic": roic,
        "wacc": wacc,
        "spread": spread,
        "value_creation": value_creation,
        "description": (
            f"ROIC {roic:.1f}% vs WACC {wacc:.1f}% — "
            + ("Value CREATING (+{:.1f}%)".format(spread) if value_creation
               else "Value DESTROYING ({:.1f}%)".format(spread))
        ),
    }


def compute_growth_quality(
    revenues: list[float | None],
    ebitda_margins: list[float | None],
    fcf_yield: float | None = None,
) -> dict[str, Any]:
    """
    Compute growth quality metrics:
    - Revenue CAGR (multi-year)
    - EBITDA margin trend (improving / stable / deteriorating)
    - FCF yield assessment
    revenues: list of annual revenues [newest, ..., oldest] (at least 2)
    ebitda_margins: list of annual EBITDA margins % [newest, ..., oldest]
    """
    result: dict[str, Any] = {"available": False}

    valid_revs = [r for r in revenues if r is not None and r > 0]
    if len(valid_revs) >= 2:
        n_years = len(valid_revs) - 1
        rev_cagr = round(((valid_revs[0] / valid_revs[-1]) ** (1 / n_years) - 1) * 100, 2)
        result["revenue_cagr"] = rev_cagr
        result["revenue_cagr_years"] = n_years
        result["revenue_quality"] = (
            "STRONG" if rev_cagr >= 15 else
            "GOOD" if rev_cagr >= 8 else
            "WEAK" if rev_cagr >= 0 else
            "DECLINING"
        )
        result["available"] = True

    valid_margins = [m for m in ebitda_margins if m is not None]
    if len(valid_margins) >= 2:
        margin_trend = "STABLE"
        recent_avg = sum(valid_margins[:2]) / 2
        older_avg = sum(valid_margins[-2:]) / 2
        margin_delta = recent_avg - older_avg
        if margin_delta > 2:
            margin_trend = "IMPROVING"
        elif margin_delta < -2:
            margin_trend = "DETERIORATING"
        result["ebitda_margin_latest"] = round(valid_margins[0], 2)
        result["ebitda_margin_trend"] = margin_trend
        result["ebitda_margin_delta"] = round(margin_delta, 2)
        result["available"] = True

    if fcf_yield is not None:
        result["fcf_yield"] = fcf_yield
        result["fcf_quality"] = (
            "STRONG" if fcf_yield > 5 else
            "MODERATE" if fcf_yield > 2 else
            "WEAK" if fcf_yield >= 0 else
            "NEGATIVE"
        )
        result["available"] = True

    return result


def compute_forensic_audit(
    altman_inputs: dict,
    earnings_quality_inputs: dict,
    red_flag_inputs: dict,
    roic_inputs: dict,
    growth_inputs: dict,
    piotroski_score: int | None = None,
    beneish_m_score: float | None = None,
) -> dict[str, Any]:
    """
    Master forensic audit function. Aggregates all sub-scores into a single
    forensic_audit dict with overall_risk_level and composite_score (0-100).
    Higher composite_score = better quality / lower forensic risk.
    """
    altman = compute_altman_z_score(**altman_inputs)
    eq = compute_earnings_quality(**earnings_quality_inputs)
    rf = compute_forensic_red_flags(**red_flag_inputs)
    roic = compute_roic_vs_wacc(**roic_inputs)
    growth = compute_growth_quality(**growth_inputs)

    score = 50  # baseline
    risk_flags: list[str] = []

    # Altman Z-Score (max ±20)
    if altman.get("available"):
        z = altman["z_score"]
        if altman["zone"] == "SAFE":
            score += 15
        elif altman["zone"] == "GREY":
            score += 5
        else:
            score -= 15; risk_flags.append(f"Altman Z={z:.2f} DISTRESS zone")

    # Piotroski (max ±15)
    if piotroski_score is not None:
        if piotroski_score >= 7:
            score += 15
        elif piotroski_score >= 5:
            score += 5
        else:
            score -= 10; risk_flags.append(f"Piotroski F={piotroski_score}/9 (weak financials)")

    # Beneish M-Score (max ±10)
    if beneish_m_score is not None:
        if beneish_m_score > -2.22:
            score -= 10; risk_flags.append(f"Beneish M={beneish_m_score:.2f} (manipulation risk)")
        else:
            score += 8

    # Earnings quality (max ±10)
    if eq.get("available"):
        eq_score = {"HIGH": 10, "MEDIUM": 2, "LOW": -8}.get(eq.get("earnings_quality", "MEDIUM"), 0)
        score += eq_score
        if eq_score < 0:
            risk_flags.extend(eq.get("flags", []))

    # Red flags (each -4)
    rf_count = rf.get("red_flag_count", 0)
    score -= rf_count * 4
    risk_flags.extend(rf.get("flags", []))

    # ROIC vs WACC (max ±8)
    if roic.get("available"):
        spread = roic.get("spread", 0) or 0
        if spread > 3:
            score += 8
        elif spread > 0:
            score += 3
        elif spread < -3:
            score -= 8; risk_flags.append(f"ROIC<WACC by {abs(spread):.1f}% — value destruction")
        else:
            score -= 3

    # Growth quality (max ±5)
    if growth.get("available"):
        rev_q = growth.get("revenue_quality", "WEAK")
        if rev_q == "STRONG":
            score += 5
        elif rev_q == "GOOD":
            score += 2
        elif rev_q == "DECLINING":
            score -= 5
        if growth.get("ebitda_margin_trend") == "DETERIORATING":
            score -= 3; risk_flags.append("EBITDA margin deteriorating")

    composite_score = max(0, min(100, score))
    overall_risk = (
        "LOW" if composite_score >= 70 else
        "MEDIUM" if composite_score >= 45 else
        "HIGH"
    )

    return {
        "composite_score": composite_score,
        "overall_risk": overall_risk,
        "altman_z": altman,
        "earnings_quality": eq,
        "red_flags": rf,
        "roic_vs_wacc": roic,
        "growth_quality": growth,
        "piotroski_score": piotroski_score,
        "beneish_m_score": beneish_m_score,
        "risk_flags": risk_flags[:10],  # top 10 flags
        "investable": composite_score >= 50 and overall_risk != "HIGH",
    }



# ─────────────────────────────────────────────────────────────────────────────
# BATCH 3: MACRO, GEOPOLITICAL & REGIME CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

# ── 3.1 Enhanced Market Regime Classifier ────────────────────────────────────

REGIME_STRATEGY_GRID: dict[str, dict[str, str]] = {
    "LOW_VOL_TREND_BULL": {
        "primary": "LONG_CALL / BULL_CALL_SPREAD",
        "secondary": "SHORT_PUT / COVERED_CALL",
        "avoid": "LONG_STRADDLE",
        "rationale": "Low VIX + uptrend: options cheap, buy calls or sell puts for premium income.",
    },
    "LOW_VOL_RANGE": {
        "primary": "IRON_CONDOR / SHORT_STRADDLE",
        "secondary": "SHORT_STRANGLE",
        "avoid": "NAKED_DIRECTIONAL",
        "rationale": "VIX < 12 + range-bound: sell options to collect time premium.",
    },
    "NORMAL_VOL_TREND": {
        "primary": "STANDARD_DIRECTIONAL / DEBIT_SPREAD",
        "secondary": "COVERED_CALL",
        "avoid": "CONDORS_ON_TRENDING_MARKET",
        "rationale": "VIX 12–18 + trending: standard directional plays with defined risk.",
    },
    "NORMAL_VOL_RANGE": {
        "primary": "IRON_CONDOR / CREDIT_SPREAD",
        "secondary": "BUTTERFLY",
        "avoid": "STRADDLE",
        "rationale": "VIX 12–18 + range: credit spreads at extreme strikes.",
    },
    "HIGH_VOL_TREND": {
        "primary": "STRADDLE / STRANGLE / LONG_OPTIONS",
        "secondary": "DEBIT_SPREAD",
        "avoid": "SHORT_NAKED_OPTIONS",
        "rationale": "VIX 18–25 + trend: buy options as IV is rising with the move.",
    },
    "HIGH_VOL_CRASH": {
        "primary": "PROTECTIVE_PUTS / BEAR_SPREAD",
        "secondary": "LONG_VOLATILITY",
        "avoid": "SHORT_PUTS / LONG_FUTURES",
        "rationale": "VIX >25 + crash: protect capital, use bear spreads if IV not extreme.",
    },
    "PRE_EVENT": {
        "primary": "LONG_STRADDLE / LONG_STRANGLE",
        "secondary": "DEBIT_SPREAD",
        "avoid": "SHORT_OPTIONS",
        "rationale": "Event upcoming: buy volatility before IV crush post-event.",
    },
    "POST_EVENT_IV_CRUSH": {
        "primary": "CREDIT_SPREAD / IRON_CONDOR",
        "secondary": "SHORT_STRADDLE",
        "avoid": "LONG_OPTIONS",
        "rationale": "Post-event IV crush: sell overpriced options as IV collapses.",
    },
}


def classify_market_regime_enhanced(
    vix: float | None,
    adx: float | None = None,
    rsi: float | None = None,
    days_to_event: int | None = None,
    post_event_hours: int | None = None,
) -> dict[str, Any]:
    """
    Enhanced 8-regime market classifier:
    LOW_VOL_TREND_BULL, LOW_VOL_RANGE, NORMAL_VOL_TREND, NORMAL_VOL_RANGE,
    HIGH_VOL_TREND, HIGH_VOL_CRASH, PRE_EVENT, POST_EVENT_IV_CRUSH.
    Returns regime, strategy grid, description, and color.
    """
    if vix is None:
        return {
            "regime": "UNKNOWN",
            "vix": None,
            "vix_bucket": "UNKNOWN",
            "trend_strength": "UNKNOWN",
            "strategy": REGIME_STRATEGY_GRID.get("NORMAL_VOL_TREND", {}),
            "options_strategy": "STANDARD_DIRECTIONAL",
            "description": "VIX unavailable — using standard strategy",
            "color": "gray",
        }

    # VIX bucket
    if vix < 12:
        vix_bucket = "LOW"
    elif vix < 18:
        vix_bucket = "NORMAL"
    elif vix < 25:
        vix_bucket = "ELEVATED"
    else:
        vix_bucket = "PANIC"

    # Trend strength
    trending = adx is not None and adx > 22
    bullish_trend = (
        trending and rsi is not None and rsi > 50
    )

    # Event context overrides
    if days_to_event is not None and 0 <= days_to_event <= 2:
        regime = "PRE_EVENT"
        color = "purple"
        desc = f"VIX {vix:.1f} — Event in {days_to_event}d: buy volatility (IV likely to expand)."
    elif post_event_hours is not None and post_event_hours <= 24:
        regime = "POST_EVENT_IV_CRUSH"
        color = "cyan"
        desc = f"VIX {vix:.1f} — Post-event IV crush: sell overpriced options."
    elif vix >= 25:
        regime = "HIGH_VOL_CRASH"
        color = "red"
        desc = f"VIX {vix:.1f} (PANIC) — Protect capital. Defensive posture."
    elif vix >= 18:
        regime = "HIGH_VOL_TREND" if trending else "HIGH_VOL_TREND"
        color = "orange"
        desc = f"VIX {vix:.1f} (ELEVATED) — High vol {'+ trend' if trending else ': buy options on confirmation'}."
    elif vix < 12:
        regime = "LOW_VOL_TREND_BULL" if bullish_trend else "LOW_VOL_RANGE"
        color = "blue" if bullish_trend else "teal"
        desc = (
            f"VIX {vix:.1f} (LOW) — Bull trend; buy calls / sell puts."
            if bullish_trend
            else f"VIX {vix:.1f} (LOW) — Range-bound; Iron Condors / Short Straddles."
        )
    else:
        regime = "NORMAL_VOL_TREND" if trending else "NORMAL_VOL_RANGE"
        color = "green" if trending else "lime"
        desc = (
            f"VIX {vix:.1f} (NORMAL) — Trending market; directional plays."
            if trending
            else f"VIX {vix:.1f} (NORMAL) — Range; credit spreads."
        )

    # ADX + RSI annotations
    if adx is not None:
        desc += f" ADX {adx:.0f} ({'strong' if adx > 30 else 'moderate' if adx > 20 else 'weak'} trend)."
    if rsi is not None:
        if rsi > 70:
            desc += f" RSI {rsi:.0f} — overbought."
        elif rsi < 30:
            desc += f" RSI {rsi:.0f} — oversold."

    strategy_grid = REGIME_STRATEGY_GRID.get(regime, REGIME_STRATEGY_GRID["NORMAL_VOL_TREND"])

    return {
        "regime": regime,
        "vix": round(vix, 2),
        "vix_bucket": vix_bucket,
        "adx": round(adx, 1) if adx is not None else None,
        "index_rsi": round(rsi, 1) if rsi is not None else None,
        "trend_strength": "STRONG" if adx and adx > 30 else ("MODERATE" if adx and adx > 20 else "WEAK"),
        "options_strategy": strategy_grid["primary"],
        "strategy": strategy_grid,
        "description": desc,
        "color": color,
    }


# ── 3.2 Sector Impact Map ────────────────────────────────────────────────────

SECTOR_MACRO_IMPACT_MAP: dict[str, dict[str, Any]] = {
    "RBI_RATE_HIKE": {
        "beneficiaries": ["Banking", "Financial Services", "Insurance"],
        "losers": ["Real Estate", "Auto", "Capital Goods", "NBFC"],
        "impact_description": "Rate hike → NIM expansion for banks; real estate and rate-sensitive sectors hurt.",
        "intensity": "HIGH",
    },
    "RBI_RATE_CUT": {
        "beneficiaries": ["Real Estate", "Auto", "Capital Goods", "NBFC", "Housing Finance"],
        "losers": ["Banking"],
        "impact_description": "Rate cut → cheaper credit boosts consumption, real estate, and CapEx.",
        "intensity": "HIGH",
    },
    "CRUDE_SPIKE": {
        "beneficiaries": ["Oil & Gas (upstream)", "Exploration"],
        "losers": ["Airlines", "Paint", "Chemicals", "Logistics", "Tyre", "FMCG"],
        "impact_description": "Crude +20%+ → input cost pressure on oil consumers; upstream oil gains.",
        "intensity": "HIGH",
    },
    "CRUDE_FALL": {
        "beneficiaries": ["Airlines", "Paint", "Chemicals", "Logistics", "Tyre", "FMCG"],
        "losers": ["Oil & Gas (upstream)"],
        "impact_description": "Crude fall → input cost relief for downstream consumers.",
        "intensity": "MEDIUM",
    },
    "FII_OUTFLOW": {
        "beneficiaries": ["Export-oriented IT", "Pharma (USD earners)"],
        "losers": ["Banking", "FMCG", "Real Estate", "Large-cap index"],
        "impact_description": "FII selling → pressure on large-caps and index stocks; INR weakens.",
        "intensity": "HIGH",
    },
    "FII_INFLOW": {
        "beneficiaries": ["Banking", "Financials", "Large-cap index", "Auto"],
        "losers": [],
        "impact_description": "FII buying → broad market rally, especially financials and large-caps.",
        "intensity": "MEDIUM",
    },
    "USD_STRENGTHENING": {
        "beneficiaries": ["IT", "Pharma", "Textiles", "Chemicals (exporters)"],
        "losers": ["Oil importers", "Capital Goods (imports)", "Aviation"],
        "impact_description": "Strong dollar → INR weakens; export-oriented sectors gain.",
        "intensity": "MEDIUM",
    },
    "INR_WEAKENING": {
        "beneficiaries": ["IT", "Pharma", "Textiles"],
        "losers": ["Airlines", "Refineries", "Importers"],
        "impact_description": "INR depreciation → export sectors gain; import-heavy sectors hurt.",
        "intensity": "MEDIUM",
    },
    "INDIA_BUDGET_CAPEX": {
        "beneficiaries": ["Infrastructure", "Capital Goods", "Cement", "Steel", "Defence"],
        "losers": [],
        "impact_description": "Government capex push → infra and capital goods stocks rally.",
        "intensity": "HIGH",
    },
    "PLI_SCHEME": {
        "beneficiaries": ["Manufacturing", "Electronics", "Pharma API", "Textiles", "Auto EV"],
        "losers": [],
        "impact_description": "PLI scheme → import substitution and export push for eligible sectors.",
        "intensity": "MEDIUM",
    },
    "US_FED_RATE_HIKE": {
        "beneficiaries": ["Export IT", "Pharma"],
        "losers": ["FII-driven sectors", "Real Estate", "Gold"],
        "impact_description": "US rate hike → capital flows to US; risk-off for EM including India.",
        "intensity": "MEDIUM",
    },
    "CHINA_SLOWDOWN": {
        "beneficiaries": ["Indian manufacturers (import substitution)", "Specialty Chemicals"],
        "losers": ["Metal exporters", "Commodity importers"],
        "impact_description": "China slowdown → metal prices fall; import substitute opportunity for India.",
        "intensity": "MEDIUM",
    },
    "GEOPOLITICAL_CONFLICT": {
        "beneficiaries": ["Defence", "Gold", "Energy"],
        "losers": ["Aviation", "Tourism", "Consumer Discretionary"],
        "impact_description": "Geopolitical uncertainty → safe haven rally; risk-off for consumer sectors.",
        "intensity": "HIGH",
    },
    "EV_ADOPTION_THEME": {
        "beneficiaries": ["EV OEM", "Battery", "Charging Infra", "Lithium mining"],
        "losers": ["ICE Auto ancillaries", "Fuel retail"],
        "impact_description": "EV theme → structural beneficiaries; ICE supply chain faces disruption.",
        "intensity": "MEDIUM",
    },
    "SEMICONDUCTOR_SHORTAGE": {
        "beneficiaries": ["Indian ATMP", "Chip design"],
        "losers": ["Auto (chip-dependent)", "Electronics OEM"],
        "impact_description": "Global chip shortage → auto production cuts; domestic semicon opportunity.",
        "intensity": "MEDIUM",
    },
}


def compute_macro_context(
    active_events: list[str] | None = None,
    vix: float | None = None,
    adx: float | None = None,
    rsi: float | None = None,
    days_to_next_event: int | None = None,
    sector: str | None = None,
    geopolitical_risk: bool = False,
) -> dict[str, Any]:
    """
    Compute macro context for a given sector or signal.
    active_events: list of keys from SECTOR_MACRO_IMPACT_MAP (e.g., ["CRUDE_SPIKE", "FII_OUTFLOW"])
    Returns: regime, sector_bias, event_impacts, geopolitical_flag, strategy_suggestion.
    """
    regime_data = classify_market_regime_enhanced(
        vix=vix, adx=adx, rsi=rsi,
        days_to_event=days_to_next_event,
    )

    sector_impact: dict[str, Any] = {"beneficiary": False, "loser": False, "events": []}
    event_impacts: list[dict] = []

    if active_events and sector:
        sector_lower = sector.lower()
        for event_key in active_events:
            impact = SECTOR_MACRO_IMPACT_MAP.get(event_key)
            if impact is None:
                continue
            is_ben = any(sector_lower in b.lower() for b in impact["beneficiaries"])
            is_loser = any(sector_lower in l.lower() for l in impact["losers"])
            event_impacts.append({
                "event": event_key,
                "beneficiary": is_ben,
                "loser": is_loser,
                "description": impact["impact_description"],
                "intensity": impact["intensity"],
            })
            if is_ben:
                sector_impact["beneficiary"] = True
                sector_impact["events"].append(f"+{event_key}")
            if is_loser:
                sector_impact["loser"] = True
                sector_impact["events"].append(f"-{event_key}")

    # Net macro bias for sector
    net_events = [e for e in event_impacts]
    ben_count = sum(1 for e in net_events if e["beneficiary"])
    loser_count = sum(1 for e in net_events if e["loser"])
    macro_bias = (
        "TAILWIND" if ben_count > loser_count
        else "HEADWIND" if loser_count > ben_count
        else "NEUTRAL"
    )

    geopolitical_flag: dict[str, Any] = {"active": False}
    if geopolitical_risk or (active_events and "GEOPOLITICAL_CONFLICT" in active_events):
        geopolitical_flag = {
            "active": True,
            "sector_impact": SECTOR_MACRO_IMPACT_MAP["GEOPOLITICAL_CONFLICT"],
            "risk_level": "HIGH",
        }

    return {
        "regime": regime_data,
        "macro_bias": macro_bias,
        "sector_impact": sector_impact,
        "event_impacts": event_impacts,
        "geopolitical_flag": geopolitical_flag,
        "strategy_suggestion": regime_data.get("strategy", {}),
        "active_macro_events": active_events or [],
    }


def get_sector_macro_beneficiaries(event_key: str) -> dict[str, Any]:
    """Return beneficiaries and losers for a macro event."""
    return SECTOR_MACRO_IMPACT_MAP.get(event_key, {})


def get_all_macro_events() -> list[str]:
    """Return all defined macro event keys."""
    return list(SECTOR_MACRO_IMPACT_MAP.keys())



# ─────────────────────────────────────────────────────────────────────────────
# BATCH 4: PORTFOLIO-LEVEL RISK ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

def compute_portfolio_correlation_matrix(
    returns_dict: dict[str, list[float]],
    min_length: int = 20,
) -> dict[str, Any]:
    """
    Compute pairwise Pearson correlation matrix from daily return series.
    returns_dict: {symbol: [daily_returns]} — at least 20 data points each.
    Returns: correlation_matrix (symbol×symbol), high_correlation_pairs (>0.7).
    """
    if not returns_dict or len(returns_dict) < 2:
        return {"available": False, "matrix": {}, "high_correlation_pairs": []}

    # Filter symbols with sufficient data
    valid = {
        sym: rets for sym, rets in returns_dict.items()
        if rets is not None and len(rets) >= min_length
    }
    if len(valid) < 2:
        return {"available": False, "matrix": {}, "high_correlation_pairs": []}

    symbols = sorted(valid.keys())
    n = min(len(v) for v in valid.values())

    # Build matrix using numpy
    arr = np.array([valid[s][-n:] for s in symbols])
    try:
        corr = np.corrcoef(arr)
    except Exception:
        return {"available": False, "matrix": {}, "high_correlation_pairs": []}

    corr_matrix: dict[str, dict[str, float]] = {}
    high_pairs: list[dict] = []

    for i, si in enumerate(symbols):
        corr_matrix[si] = {}
        for j, sj in enumerate(symbols):
            val = round(float(corr[i, j]), 3)
            corr_matrix[si][sj] = val
            if i < j and abs(val) > 0.70:
                high_pairs.append({
                    "symbol_a": si,
                    "symbol_b": sj,
                    "correlation": val,
                    "type": "POSITIVE" if val > 0 else "NEGATIVE",
                    "risk_note": (
                        "High positive correlation — concentration risk"
                        if val > 0.7 else
                        "High negative correlation — natural hedge"
                    ),
                })

    return {
        "available": True,
        "symbols": symbols,
        "matrix": corr_matrix,
        "high_correlation_pairs": high_pairs,
        "has_concentration_risk": any(p["correlation"] > 0.70 for p in high_pairs),
    }


STRESS_SCENARIOS: dict[str, dict[str, Any]] = {
    "NIFTY_CRASH_10PCT": {
        "description": "Nifty drops 10% — broad market sell-off",
        "index_shock": -0.10,
        "beta_driven": True,
        "sector_overrides": {"Gold": 0.05, "Pharma": -0.03, "IT": -0.12},
    },
    "CRUDE_SPIKE_30PCT": {
        "description": "Crude oil spikes 30% — input cost surge",
        "index_shock": -0.04,
        "beta_driven": False,
        "sector_overrides": {
            "Airlines": -0.20, "Paint": -0.12, "Chemicals": -0.10,
            "Oil & Gas": 0.15, "Exploration": 0.15, "Tyre": -0.08,
        },
    },
    "INR_WEAKENS_5PCT": {
        "description": "INR weakens 5% vs USD",
        "index_shock": -0.02,
        "beta_driven": False,
        "sector_overrides": {
            "IT": 0.08, "Pharma": 0.05, "Textiles": 0.04,
            "Airlines": -0.06, "Refineries": -0.04,
        },
    },
    "US_RECESSION": {
        "description": "US recession — global risk-off, FII outflows",
        "index_shock": -0.15,
        "beta_driven": True,
        "sector_overrides": {
            "IT": -0.18, "Metals": -0.12, "Pharma": -0.02,
            "FMCG": -0.04, "Banking": -0.14,
        },
    },
    "RBI_RATE_HIKE_50BPS": {
        "description": "RBI surprise 50bps rate hike",
        "index_shock": -0.05,
        "beta_driven": False,
        "sector_overrides": {
            "Real Estate": -0.12, "Auto": -0.08, "Banking": 0.03,
            "NBFC": -0.10, "Capital Goods": -0.06,
        },
    },
}


def compute_portfolio_stress_tests(
    holdings: list[dict],
) -> dict[str, Any]:
    """
    Compute portfolio P&L impact under 5 stress scenarios.
    holdings: list of {symbol, sector, current_value, portfolio_beta}
    Returns: scenario_results with impact_pct and estimated_loss per scenario.
    """
    if not holdings:
        return {"available": False, "scenarios": {}}

    total_value = sum(h.get("current_value", 0) for h in holdings if h.get("current_value"))
    if total_value <= 0:
        return {"available": False, "scenarios": {}}

    scenario_results: dict[str, dict] = {}

    for scenario_key, scenario in STRESS_SCENARIOS.items():
        index_shock = scenario["index_shock"]
        sector_overrides: dict[str, float] = scenario.get("sector_overrides", {})
        total_impact = 0.0
        stock_impacts: list[dict] = []

        for holding in holdings:
            sym = holding.get("symbol", "")
            sector = holding.get("sector", "")
            val = holding.get("current_value", 0) or 0
            beta = holding.get("portfolio_beta") or 1.0

            # Sector override or beta-driven shock
            sector_shock = None
            for sec_key, shock in sector_overrides.items():
                if sec_key.lower() in sector.lower():
                    sector_shock = shock
                    break

            if sector_shock is not None:
                shock = sector_shock
            elif scenario["beta_driven"]:
                shock = index_shock * beta
            else:
                shock = index_shock * 0.5

            impact_value = val * shock
            total_impact += impact_value
            if abs(impact_value) > 0:
                stock_impacts.append({
                    "symbol": sym,
                    "shock_pct": round(shock * 100, 1),
                    "impact": round(impact_value),
                })

        impact_pct = round(total_impact / total_value * 100, 2) if total_value > 0 else 0
        stock_impacts.sort(key=lambda x: x["impact"])

        scenario_results[scenario_key] = {
            "description": scenario["description"],
            "portfolio_impact_pct": impact_pct,
            "portfolio_impact_value": round(total_impact),
            "severity": (
                "CRITICAL" if impact_pct < -15 else
                "HIGH" if impact_pct < -8 else
                "MEDIUM" if impact_pct < -3 else
                "LOW"
            ),
            "top_losers": stock_impacts[:3],
        }

    worst_scenario = min(scenario_results.items(), key=lambda x: x[1]["portfolio_impact_pct"])

    return {
        "available": True,
        "scenarios": scenario_results,
        "worst_scenario": worst_scenario[0],
        "worst_case_loss_pct": worst_scenario[1]["portfolio_impact_pct"],
    }


def compute_diversification_audit(
    holdings: list[dict],
) -> dict[str, Any]:
    """
    Audit portfolio diversification:
    - Sector allocation %
    - Market-cap split (Large/Mid/Small)
    - Cyclical vs Defensive
    - Domestic vs Export
    - Micro-cap exposure flag
    """
    if not holdings:
        return {"available": False}

    total_value = sum(h.get("current_value", 0) for h in holdings if h.get("current_value"))
    if total_value <= 0:
        return {"available": False}

    sector_alloc: dict[str, float] = {}
    cap_alloc: dict[str, float] = {"Large": 0, "Mid": 0, "Small": 0, "Unknown": 0}
    cyclical_val = 0.0
    defensive_val = 0.0
    domestic_val = 0.0
    export_val = 0.0
    micro_cap_val = 0.0

    CYCLICAL_SECTORS = {"auto", "metals", "capital goods", "real estate", "banking", "finance", "oil"}
    DEFENSIVE_SECTORS = {"fmcg", "pharma", "healthcare", "utilities", "consumer staples"}
    EXPORT_SECTORS = {"it", "pharma", "textiles", "chemicals", "technology"}

    for h in holdings:
        val = h.get("current_value", 0) or 0
        sector = (h.get("sector") or "Unknown").lower()
        market_cap = h.get("market_cap")
        symbol = h.get("symbol", "")

        # Sector allocation
        sector_name = h.get("sector") or "Unknown"
        sector_alloc[sector_name] = sector_alloc.get(sector_name, 0) + val

        # Market cap classification
        if market_cap is not None:
            if market_cap > 200e9:  # > 20k Cr = Large cap
                cap_alloc["Large"] += val
            elif market_cap > 50e9:  # 5k–20k Cr = Mid cap
                cap_alloc["Mid"] += val
            elif market_cap > 5e9:   # 500–5k Cr = Small cap
                cap_alloc["Small"] += val
                if market_cap < 5e9:
                    micro_cap_val += val
            else:
                cap_alloc["Unknown"] += val
        else:
            cap_alloc["Unknown"] += val

        # Cyclical/Defensive
        if any(s in sector for s in CYCLICAL_SECTORS):
            cyclical_val += val
        elif any(s in sector for s in DEFENSIVE_SECTORS):
            defensive_val += val

        # Domestic/Export
        if any(s in sector for s in EXPORT_SECTORS):
            export_val += val
        else:
            domestic_val += val

    # Convert to percentages
    sector_pct = {k: round(v / total_value * 100, 1) for k, v in sector_alloc.items()}
    cap_pct = {k: round(v / total_value * 100, 1) for k, v in cap_alloc.items()}

    # Flags
    flags: list[str] = []
    top_sector = max(sector_pct.items(), key=lambda x: x[1]) if sector_pct else (None, 0)
    top_holding = max(holdings, key=lambda h: h.get("current_value", 0), default=None)
    top_holding_pct = round(
        (top_holding.get("current_value", 0) / total_value * 100) if top_holding else 0, 1
    )

    if top_sector[1] > 40:
        flags.append(f"Over-concentrated in {top_sector[0]} ({top_sector[1]:.0f}% of portfolio)")
    if top_holding_pct > 20:
        flags.append(f"Single stock > 20%: {top_holding.get('symbol', '')} at {top_holding_pct:.0f}%")
    if micro_cap_val / total_value > 0.25:
        flags.append(f"Micro-cap exposure {micro_cap_val/total_value*100:.0f}% > 25% — high risk")
    if cap_pct.get("Unknown", 0) > 30:
        flags.append("Market cap data missing for >30% of portfolio")

    return {
        "available": True,
        "sector_allocation_pct": dict(sorted(sector_pct.items(), key=lambda x: -x[1])),
        "market_cap_split_pct": cap_pct,
        "cyclical_pct": round(cyclical_val / total_value * 100, 1),
        "defensive_pct": round(defensive_val / total_value * 100, 1),
        "domestic_pct": round(domestic_val / total_value * 100, 1),
        "export_pct": round(export_val / total_value * 100, 1),
        "micro_cap_pct": round(micro_cap_val / total_value * 100, 1),
        "flags": flags,
        "top_sector": top_sector[0],
        "top_sector_pct": top_sector[1],
        "top_holding_pct": top_holding_pct,
    }


# ── Upcoming Catalysts (static calendar-based) ───────────────────────────────

# RBI and key macro event schedule (approximate, updated manually)
RBI_MEETING_DATES_2025_2026 = [
    "2025-04-09", "2025-06-06", "2025-08-06", "2025-10-08",
    "2025-12-05", "2026-02-06", "2026-04-07", "2026-06-05",
    "2026-08-05", "2026-10-07", "2026-12-04",
]

FED_MEETING_DATES_2025_2026 = [
    "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-17",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
]


def compute_upcoming_catalysts(
    symbols: list[str],
    earnings_dates: dict[str, str] | None = None,
    days_window: int = 15,
) -> dict[str, Any]:
    """
    Flag upcoming catalysts for given symbols within days_window days.
    earnings_dates: {symbol: 'YYYY-MM-DD'}
    Returns: catalyst_flags per symbol and macro_events list.
    """
    try:
        from datetime import date, timedelta
        today = date.today()
        window_end = today + timedelta(days=days_window)

        catalysts: dict[str, list[str]] = {}

        # Stock-level catalysts (earnings)
        if earnings_dates:
            for sym in symbols:
                ed = earnings_dates.get(sym)
                if ed:
                    try:
                        ed_date = date.fromisoformat(ed)
                        days_away = (ed_date - today).days
                        if 0 <= days_away <= days_window:
                            catalysts.setdefault(sym, []).append(
                                f"Earnings in {days_away}d ({ed_date.strftime('%d %b %Y')})"
                            )
                    except Exception:
                        pass

        # RBI meetings
        rbi_upcoming = []
        for d_str in RBI_MEETING_DATES_2025_2026:
            try:
                d = date.fromisoformat(d_str)
                days_away = (d - today).days
                if 0 <= days_away <= days_window:
                    rbi_upcoming.append({
                        "event": "RBI Policy Meeting",
                        "date": d_str,
                        "days_away": days_away,
                        "sector_impact": ["Banking", "Real Estate", "Auto", "NBFC"],
                    })
            except Exception:
                pass

        # Fed meetings
        fed_upcoming = []
        for d_str in FED_MEETING_DATES_2025_2026:
            try:
                d = date.fromisoformat(d_str)
                days_away = (d - today).days
                if 0 <= days_away <= days_window:
                    fed_upcoming.append({
                        "event": "US Fed Meeting",
                        "date": d_str,
                        "days_away": days_away,
                        "sector_impact": ["IT", "Banking", "Metals"],
                    })
            except Exception:
                pass

        macro_events = rbi_upcoming + fed_upcoming
        macro_events.sort(key=lambda x: x["days_away"])

        return {
            "available": True,
            "stock_catalysts": catalysts,
            "macro_events": macro_events[:5],  # top 5 nearest
            "has_near_term_events": bool(macro_events or catalysts),
            "window_days": days_window,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def merge_duplicate_holdings(holdings: list[dict]) -> list[dict]:
    """
    Merge positions and holdings with the same symbol into a single entry
    using weighted-average cost price and aggregated quantities.
    Preserves the first occurrence's metadata (sector, market_cap, etc.).
    """
    merged: dict[str, dict] = {}

    for h in holdings:
        sym = h.get("symbol") or h.get("script", "")
        if not sym:
            continue

        if sym not in merged:
            merged[sym] = dict(h)
            merged[sym]["_total_cost"] = (h.get("avg_price", 0) or 0) * (h.get("quantity", 0) or 0)
            merged[sym]["_total_qty"] = h.get("quantity", 0) or 0
        else:
            qty = h.get("quantity", 0) or 0
            cost = (h.get("avg_price", 0) or 0) * qty
            merged[sym]["_total_cost"] += cost
            merged[sym]["_total_qty"] += qty
            # Update current value
            cv = h.get("current_value", 0) or 0
            merged[sym]["current_value"] = (merged[sym].get("current_value", 0) or 0) + cv
            pnl = h.get("unrealized_pnl", 0) or 0
            merged[sym]["unrealized_pnl"] = (merged[sym].get("unrealized_pnl", 0) or 0) + pnl

    # Compute weighted avg price
    result = []
    for sym, h in merged.items():
        total_qty = h["_total_qty"]
        total_cost = h["_total_cost"]
        if total_qty > 0:
            h["avg_price"] = round(total_cost / total_qty, 2)
            h["quantity"] = total_qty
        del h["_total_cost"]
        del h["_total_qty"]
        result.append(h)

    return result


def compute_master_stock_snapshot(
    symbol: str,
    ltp: float | None,
    hist: pd.DataFrame | None,
    sector: str | None = None,
    market_cap: float | None = None,
    index_memberships: list[str] | None = None,
    ipo_date: str | None = None,
    ipo_price: float | None = None,
) -> dict[str, Any]:
    """
    MASTER stock snapshot per spec:
    - Identity: symbol, sector, market-cap category, index memberships
    - Price levels: 52W high/low %, 3M/1M high/low, ATH % below (using hist)
    - IPO info if listed < 5 years
    """
    snap: dict[str, Any] = {
        "symbol": symbol,
        "sector": sector,
        "market_cap": market_cap,
        "index_memberships": index_memberships or [],
        "ltp": ltp,
    }

    # Market cap category
    if market_cap is not None:
        if market_cap > 200e9:
            snap["market_cap_category"] = "LARGE_CAP"
        elif market_cap > 50e9:
            snap["market_cap_category"] = "MID_CAP"
        elif market_cap > 5e9:
            snap["market_cap_category"] = "SMALL_CAP"
        else:
            snap["market_cap_category"] = "MICRO_CAP"
    else:
        snap["market_cap_category"] = "UNKNOWN"

    if hist is not None and not hist.empty and ltp is not None:
        n = len(hist)

        # 52W high/low (last 252 trading days)
        w52 = hist.tail(min(252, n))
        w52_high = float(w52["High"].max())
        w52_low = float(w52["Low"].min())
        snap["week52_high"] = round(w52_high, 2)
        snap["week52_low"] = round(w52_low, 2)
        snap["pct_from_52w_high"] = round((ltp - w52_high) / w52_high * 100, 2)
        snap["pct_from_52w_low"] = round((ltp - w52_low) / w52_low * 100, 2)

        # 3M and 1M high/low
        w3m = hist.tail(min(63, n))
        w1m = hist.tail(min(21, n))
        snap["month3_high"] = round(float(w3m["High"].max()), 2)
        snap["month3_low"] = round(float(w3m["Low"].min()), 2)
        snap["month1_high"] = round(float(w1m["High"].max()), 2)
        snap["month1_low"] = round(float(w1m["Low"].min()), 2)

        # ATH (all-time high from available data)
        ath = float(hist["High"].max())
        snap["ath"] = round(ath, 2)
        snap["pct_below_ath"] = round((ltp - ath) / ath * 100, 2)

    # IPO info (if listed < 5 years)
    if ipo_date is not None:
        try:
            from datetime import date
            ipo_dt = date.fromisoformat(ipo_date)
            years_since = (date.today() - ipo_dt).days / 365.25
            if years_since < 5:
                snap["ipo_date"] = ipo_date
                snap["ipo_price"] = ipo_price
                snap["years_since_ipo"] = round(years_since, 1)
                if ipo_price and ltp:
                    snap["ipo_return_pct"] = round((ltp - ipo_price) / ipo_price * 100, 2)
        except Exception:
            pass

    return snap



# ─────────────────────────────────────────────────────────────────────────────
# BATCH 5: F&O STRATEGY LIBRARY, BACKTEST STATS & SIGNAL STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────

# ── 5.1 Strategy Library ─────────────────────────────────────────────────────

STRATEGY_LIBRARY: dict[str, dict[str, Any]] = {
    # ── Intraday/Index Futures ──────────────────────────────────────────────
    "S1_ORB": {
        "name": "Opening Range Breakout",
        "type": "INTRADAY",
        "description": "Breakout above/below 9:15–9:30 AM range on NIFTY/BANKNIFTY futures.",
        "entry_conditions": [
            "Price closes above (CE) or below (PE) 9:15–9:30 ORB high/low",
            "Volume spike > 1.5× 5-day average at breakout candle",
            "VIX < 22 (not extreme fear)",
        ],
        "preferred_regime": ["LOW_VOL_TREND_BULL", "NORMAL_VOL_TREND", "HIGH_VOL_TREND"],
        "instruments": ["NIFTY", "BANKNIFTY"],
        "timeframe": "INTRADAY",
        "sl_method": "ORB_RANGE_MIDPOINT",
        "target_method": "1.5R_TO_2R",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "S2_VWAP": {
        "name": "VWAP Reversion",
        "type": "INTRADAY",
        "description": "Price deviates >0.5% from VWAP, mean-revert toward VWAP.",
        "entry_conditions": [
            "Price >0.5% above VWAP (for PE) or >0.5% below (for CE)",
            "RSI diverging from VWAP deviation (overbought/oversold)",
            "Volume declining on the divergent move",
        ],
        "preferred_regime": ["NORMAL_VOL_RANGE", "LOW_VOL_RANGE"],
        "instruments": ["NIFTY", "BANKNIFTY", "LIQUID_STOCKS"],
        "timeframe": "INTRADAY",
        "sl_method": "1PCT_BEYOND_DEVIATION",
        "target_method": "VWAP_TOUCH",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "S3_SUPERTREND": {
        "name": "Supertrend Crossover + EMA",
        "type": "INTRADAY",
        "description": "Supertrend direction change with EMA alignment and volume confirmation.",
        "entry_conditions": [
            "Supertrend flips from bearish → bullish (CE) or bullish → bearish (PE)",
            "Price above EMA9 and EMA20 for CE; below for PE",
            "Volume ≥ 1.2× 5-period average at crossover",
        ],
        "preferred_regime": ["LOW_VOL_TREND_BULL", "NORMAL_VOL_TREND"],
        "instruments": ["NIFTY", "BANKNIFTY", "LIQUID_STOCKS"],
        "timeframe": "INTRADAY",
        "sl_method": "ATR_BASED_1X",
        "target_method": "2X_ATR",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "S4_MACD_ADX": {
        "name": "MACD Momentum + ADX Trend Filter",
        "type": "INTRADAY",
        "description": "MACD crossover with ADX > 20 confirming trend strength.",
        "entry_conditions": [
            "MACD histogram turns positive (bullish) or negative (bearish)",
            "ADX > 20 (trend confirmed)",
            "Price above/below 20EMA",
        ],
        "preferred_regime": ["NORMAL_VOL_TREND", "HIGH_VOL_TREND"],
        "instruments": ["NIFTY", "BANKNIFTY", "LIQUID_STOCKS"],
        "timeframe": "INTRADAY",
        "sl_method": "ATR_BASED_1.5X",
        "target_method": "2X_SL",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "S5_RSI_REVERSION": {
        "name": "RSI Mean Reversion",
        "type": "INTRADAY",
        "description": "RSI <30 (bullish) or >70 (bearish) with candle confirmation.",
        "entry_conditions": [
            "RSI crosses above 30 from oversold (CE) or below 70 (PE)",
            "Confirming candlestick pattern (hammer/engulfing for CE)",
            "Price at key support/resistance level",
        ],
        "preferred_regime": ["LOW_VOL_RANGE", "NORMAL_VOL_RANGE"],
        "instruments": ["LIQUID_STOCKS"],
        "timeframe": "INTRADAY",
        "sl_method": "RECENT_SWING_LOW_HIGH",
        "target_method": "1.5R",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    # ── Swing Strategies ────────────────────────────────────────────────────
    "SW1_52W_BREAKOUT": {
        "name": "52-Week High Breakout",
        "type": "SWING",
        "description": "Price breaks above 52W high with volume surge and fundamental gate.",
        "entry_conditions": [
            "Price closes above 52W high",
            "Volume > 2× 20-day average on breakout day",
            "ROE > 12%, D/E < 1",
            "Piotroski F-Score ≥ 6",
        ],
        "preferred_regime": ["LOW_VOL_TREND_BULL", "NORMAL_VOL_TREND"],
        "instruments": ["LIQUID_STOCKS"],
        "timeframe": "SWING_2_10D",
        "sl_method": "52W_HIGH_ZONE",
        "target_method": "ATR_EXTENSION_3X",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "SW2_200DMA_BOUNCE": {
        "name": "200DMA Bounce + RSI",
        "type": "SWING",
        "description": "Price bounces from 200DMA with RSI in 40–55 range and higher-low pattern.",
        "entry_conditions": [
            "Price touches or dips slightly below 200DMA then recovers above",
            "RSI in 40–55 range (not oversold)",
            "Higher low on daily chart confirmed",
        ],
        "preferred_regime": ["NORMAL_VOL_RANGE", "LOW_VOL_RANGE"],
        "instruments": ["NIFTY", "BANKNIFTY", "LIQUID_STOCKS"],
        "timeframe": "SWING_2_10D",
        "sl_method": "BELOW_200DMA_2PCT",
        "target_method": "PREVIOUS_SWING_HIGH",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "SW3_FLAG_BREAKOUT": {
        "name": "Flag Pattern Breakout",
        "type": "SWING",
        "description": "Bull flag or pennant breakout with volume confirmation.",
        "entry_conditions": [
            "Bull flag or pennant pattern detected (pole + consolidation)",
            "Breakout above flag/pennant resistance on high volume",
            "Volume > 1.5× 20-day average on breakout",
        ],
        "preferred_regime": ["LOW_VOL_TREND_BULL", "NORMAL_VOL_TREND"],
        "instruments": ["LIQUID_STOCKS"],
        "timeframe": "SWING_2_5D",
        "sl_method": "FLAG_LOW",
        "target_method": "POLE_LENGTH_PROJECTED",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    # ── Expiry/Options Strategies ────────────────────────────────────────────
    "E1_SHORT_STRADDLE": {
        "name": "Short Straddle",
        "type": "EXPIRY",
        "description": "Sell ATM CE + PE simultaneously to capture theta decay in low-vol range.",
        "entry_conditions": [
            "VIX < 14 (low volatility environment)",
            "DTE 7–15 days",
            "PCR between 0.85–1.15 (neutral market)",
            "No major event within 5 trading days",
        ],
        "preferred_regime": ["LOW_VOL_RANGE", "NORMAL_VOL_RANGE"],
        "instruments": ["NIFTY", "BANKNIFTY"],
        "timeframe": "EXPIRY_WEEKLY",
        "legs": ["SHORT_ATM_CE", "SHORT_ATM_PE"],
        "max_loss": "UNLIMITED (hedge required)",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "E2_IRON_CONDOR": {
        "name": "Iron Condor",
        "type": "EXPIRY",
        "description": "Sell OTM CE + OTM PE, buy further OTM to cap losses.",
        "entry_conditions": [
            "VIX 12–18 (normal volatility)",
            "ADX < 20 (range-bound)",
            "DTE 7–21 days",
            "Select wings at ±1 to ±2 SD from spot",
        ],
        "preferred_regime": ["LOW_VOL_RANGE", "NORMAL_VOL_RANGE"],
        "instruments": ["NIFTY", "BANKNIFTY"],
        "timeframe": "EXPIRY_WEEKLY",
        "legs": ["SELL_OTM_CE", "BUY_FURTHER_OTM_CE", "SELL_OTM_PE", "BUY_FURTHER_OTM_PE"],
        "max_loss": "DEFINED (wing width - premium received)",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "E3_CALENDAR_SPREAD": {
        "name": "Calendar Spread",
        "type": "EXPIRY",
        "description": "Buy far-month ATM, sell near-month ATM to exploit IV term structure.",
        "entry_conditions": [
            "Near-month IV significantly higher than far-month IV",
            "IV term structure inverted (near > far)",
            "Pre-event: buy volatility in far month",
        ],
        "preferred_regime": ["PRE_EVENT", "NORMAL_VOL_RANGE"],
        "instruments": ["NIFTY", "BANKNIFTY"],
        "timeframe": "MULTI_EXPIRY",
        "legs": ["BUY_FAR_ATM", "SELL_NEAR_ATM"],
        "max_loss": "DEBIT_PAID",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    # ── Screener-Linked Strategies ───────────────────────────────────────────
    "SF1_SCREENER_MOMENTUM": {
        "name": "Screener Momentum Filter",
        "type": "SCREENER_LINKED",
        "description": "Top multibagger screener stocks with breakout/pullback trigger.",
        "entry_conditions": [
            "Stock appears in top 10 multibagger screener",
            "Price breaks above key resistance or at pullback to support",
            "RSI 45–65 range (not extreme)",
        ],
        "preferred_regime": ["LOW_VOL_TREND_BULL", "NORMAL_VOL_TREND"],
        "instruments": ["LIQUID_STOCKS"],
        "timeframe": "SWING_5_20D",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
    "SF2_FORENSIC_QUALITY": {
        "name": "Forensic Quality + Momentum",
        "type": "SCREENER_LINKED",
        "description": "High-quality stocks (Beneish/Piotroski) with Supertrend + 50DMA trigger.",
        "entry_conditions": [
            "Beneish M-Score < -2.22 (low manipulation risk)",
            "Piotroski F-Score ≥ 7",
            "Supertrend bullish + price above 50DMA",
        ],
        "preferred_regime": ["LOW_VOL_TREND_BULL", "NORMAL_VOL_TREND"],
        "instruments": ["LIQUID_STOCKS"],
        "timeframe": "SWING_10_30D",
        "min_win_rate": 0.75,
        "min_expectancy": 0.40,
    },
}


def get_strategy_by_id(strategy_id: str) -> dict[str, Any] | None:
    """Return strategy definition by key (e.g., 'S1_ORB')."""
    return STRATEGY_LIBRARY.get(strategy_id)


def get_eligible_strategies(
    regime: str,
    instrument_type: str = "NIFTY",
    strategy_stats: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    """
    Return strategies eligible for current regime and instrument type.
    Filters by: regime match, instrument type, and backtest thresholds
    (win_rate >= 75%, expectancy >= 0.40R if stats provided).
    """
    instrument_type_upper = instrument_type.upper()
    eligible: list[dict] = []

    for sid, strategy in STRATEGY_LIBRARY.items():
        preferred = strategy.get("preferred_regime", [])
        instruments = strategy.get("instruments", [])

        # Regime match
        if regime not in preferred and "NORMAL_VOL_TREND" not in preferred:
            continue

        # Instrument match
        instrument_match = (
            instrument_type_upper in instruments
            or "LIQUID_STOCKS" in instruments
            or instrument_type_upper in ("NIFTY", "BANKNIFTY")
        )
        if not instrument_match:
            continue

        # Backtest threshold check
        if strategy_stats:
            stats = strategy_stats.get(sid)
            if stats:
                win_rate = stats.get("win_rate", 0)
                expectancy = stats.get("expectancy", 0)
                disabled = stats.get("disabled", False)
                if disabled or win_rate < 0.75 or expectancy < 0.40:
                    continue  # Auto-disabled strategy

        eligible.append({"id": sid, **strategy})

    return eligible


def select_strategy_for_signal(
    regime: str,
    direction: str,
    adx: float | None = None,
    vix: float | None = None,
    strategy_stats: dict[str, dict] | None = None,
    instrument: str = "NIFTY",
    is_swing: bool = False,
) -> dict[str, Any] | None:
    """
    Auto-select the most appropriate strategy for a signal given regime + direction.
    Returns the selected strategy dict or None.
    """
    eligible = get_eligible_strategies(regime, instrument, strategy_stats)
    if not eligible:
        return None

    # Prioritize based on regime and direction
    preferred_types = []
    if is_swing:
        preferred_types = ["SWING", "SCREENER_LINKED"]
    elif regime in ("PRE_EVENT", "HIGH_VOL_TREND"):
        preferred_types = ["EXPIRY"]
    elif regime in ("LOW_VOL_RANGE", "NORMAL_VOL_RANGE"):
        preferred_types = ["EXPIRY", "INTRADAY"]
    else:
        preferred_types = ["INTRADAY", "SCREENER_LINKED"]

    for ptype in preferred_types:
        for s in eligible:
            if s.get("type") == ptype:
                return s

    return eligible[0] if eligible else None


# ── 5.2 Backtest Stats Management ────────────────────────────────────────────

def update_backtest_stats(
    existing_stats: dict,
    new_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Update rolling backtest statistics for a strategy/instrument config.
    new_result: {"win": True/False, "r_multiple": float, "symbol": str}
    Returns updated stats dict.
    """
    stats = dict(existing_stats)
    total = stats.get("total_trades", 0) + 1
    wins = stats.get("wins", 0) + (1 if new_result.get("win") else 0)
    losses = total - wins
    total_r = stats.get("total_r_multiple", 0.0) + new_result.get("r_multiple", 0.0)

    win_rate = wins / total if total > 0 else 0
    expectancy = total_r / total if total > 0 else 0

    # Auto-disable if below thresholds and enough trades
    disabled = (
        total >= 20  # minimum sample
        and (win_rate < 0.75 or expectancy < 0.40)
    )

    stats.update({
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 3),
        "total_r_multiple": round(total_r, 3),
        "expectancy": round(expectancy, 3),
        "disabled": disabled,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })
    return stats


def check_strategy_eligible(
    stats: dict | None,
    min_trades: int = 10,
) -> tuple[bool, str]:
    """
    Check if a strategy meets eligibility thresholds.
    Returns (eligible: bool, reason: str).
    """
    if stats is None:
        return True, "No backtest data — allowing as new strategy"

    total = stats.get("total_trades", 0)
    if total < min_trades:
        return True, f"Insufficient backtests ({total}/{min_trades}) — allowing provisionally"

    win_rate = stats.get("win_rate", 1.0)
    expectancy = stats.get("expectancy", 1.0)
    disabled = stats.get("disabled", False)

    if disabled:
        return False, f"Strategy auto-disabled: win_rate={win_rate:.0%}, expectancy={expectancy:.2f}R"
    if win_rate < 0.75:
        return False, f"Win rate {win_rate:.0%} < 75% threshold"
    if expectancy < 0.40:
        return False, f"Expectancy {expectancy:.2f}R < 0.40R threshold"
    return True, f"Strategy eligible: {win_rate:.0%} win rate, {expectancy:.2f}R expectancy"


# ── 5.3 Signal Lifecycle State Machine ───────────────────────────────────────

SIGNAL_STATES = [
    "PENDING",
    "ACTIVE",
    "WATCHING_SL",
    "WATCHING_T1",
    "WATCHING_T2",
    "CLOSED_WIN",
    "CLOSED_LOSS",
    "EXPIRED",
    "CANCELLED",
]

SIGNAL_TRANSITIONS: dict[str, list[str]] = {
    "PENDING":     ["ACTIVE", "CANCELLED"],
    "ACTIVE":      ["WATCHING_SL", "WATCHING_T1", "CANCELLED", "EXPIRED"],
    "WATCHING_SL": ["CLOSED_LOSS", "WATCHING_T1", "CANCELLED", "EXPIRED"],
    "WATCHING_T1": ["WATCHING_T2", "CLOSED_WIN", "WATCHING_SL", "EXPIRED"],
    "WATCHING_T2": ["CLOSED_WIN", "WATCHING_SL", "EXPIRED"],
    "CLOSED_WIN":  [],
    "CLOSED_LOSS": [],
    "EXPIRED":     [],
    "CANCELLED":   [],
}


def transition_signal_state(
    current_state: str,
    ltp: float,
    entry_price: float,
    sl_price: float,
    t1_price: float,
    t2_price: float | None,
    direction: str = "BULLISH",
    minutes_to_expiry: int = 9999,
) -> dict[str, Any]:
    """
    Evaluate signal state transition based on live price vs entry/SL/T1/T2.
    Returns: new_state, trigger_reason, and event flags.
    """
    if current_state not in SIGNAL_STATES:
        return {"new_state": "CANCELLED", "reason": "Unknown state", "urgent_exit": False}

    allowed = SIGNAL_TRANSITIONS.get(current_state, [])
    if not allowed:
        return {"new_state": current_state, "reason": "Terminal state", "urgent_exit": False}

    # Expired check
    if minutes_to_expiry <= 0:
        return {"new_state": "EXPIRED", "reason": "Contract expired", "urgent_exit": True}
    if minutes_to_expiry <= 15 and current_state in ("ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2"):
        return {"new_state": "EXPIRED", "reason": "< 15 mins to expiry — exit immediately", "urgent_exit": True}

    urgent_exit = False
    new_state = current_state
    reason = "No change"

    is_long = direction == "BULLISH"

    # SL hit check
    sl_hit = (ltp <= sl_price) if is_long else (ltp >= sl_price)
    t1_hit = (ltp >= t1_price) if is_long else (ltp <= t1_price)
    t2_hit = (ltp >= t2_price) if (is_long and t2_price is not None) else (ltp <= t2_price if t2_price is not None else False)

    if current_state in ("ACTIVE", "PENDING"):
        if sl_hit:
            new_state = "WATCHING_SL"
            reason = f"LTP {ltp} approaching SL {sl_price}"
        elif t1_hit:
            new_state = "WATCHING_T1"
            reason = f"T1 {t1_price} reached"
        else:
            new_state = "ACTIVE"
            reason = "Monitoring entry zone"

    elif current_state == "WATCHING_SL":
        if sl_hit:
            new_state = "CLOSED_LOSS"
            reason = f"SL {sl_price} hit — loss trade"
        elif t1_hit:
            new_state = "WATCHING_T1"
            reason = f"Recovered — T1 {t1_price} reached"
            urgent_exit = False

    elif current_state == "WATCHING_T1":
        if t2_hit and t2_price is not None:
            new_state = "WATCHING_T2"
            reason = f"T2 {t2_price} reached"
        elif t2_price is None or t1_hit:
            new_state = "CLOSED_WIN"
            reason = f"T1 {t1_price} achieved — WIN"
        elif sl_hit:
            new_state = "WATCHING_SL"
            reason = f"Pulled back toward SL {sl_price}"

    elif current_state == "WATCHING_T2":
        if sl_hit:
            new_state = "WATCHING_SL"
            reason = f"T2 rollback toward SL {sl_price}"
        elif t2_hit:
            new_state = "CLOSED_WIN"
            reason = f"T2 {t2_price} achieved — WIN"

    # Urgent exit if trend reversal + near expiry
    if minutes_to_expiry <= 60 and new_state in ("WATCHING_SL",):
        urgent_exit = True
        reason += " | URGENT EXIT: < 60 min to expiry + SL pressure"

    return {
        "new_state": new_state,
        "reason": reason,
        "urgent_exit": urgent_exit,
        "sl_hit": sl_hit,
        "t1_hit": t1_hit,
        "t2_hit": t2_hit,
    }


# ── 5.4 Constituent-weighted Index Bias ─────────────────────────────────────

# NIFTY 50 approximate constituent weights (as of Feb 2026, top 20 by weight)
NIFTY50_WEIGHTS: dict[str, float] = {
    "RELIANCE": 9.8, "HDFCBANK": 8.5, "ICICIBANK": 7.9, "INFY": 6.0,
    "TCS": 4.8, "BAJFINANCE": 3.6, "HINDUNILVR": 3.0, "SBIN": 2.9,
    "KOTAKBANK": 2.8, "LT": 2.6, "BHARTIARTL": 2.5, "AXISBANK": 2.4,
    "ITC": 2.3, "ASIANPAINT": 1.9, "MARUTI": 1.8, "SUNPHARMA": 1.7,
    "WIPRO": 1.5, "TITAN": 1.4, "ULTRACEMCO": 1.3, "TECHM": 1.2,
    "HCLTECH": 1.1, "NESTLEIND": 1.0, "POWERGRID": 0.9, "NTPC": 0.9,
    "M&M": 0.9, "TATASTEEL": 0.8, "ONGC": 0.8, "BPCL": 0.7,
    "JSWSTEEL": 0.7, "COALINDIA": 0.6, "INDUSINDBK": 0.6, "GRASIM": 0.6,
    "CIPLA": 0.5, "BRITANNIA": 0.5, "EICHERMOT": 0.5, "BAJAJFINSV": 0.5,
    "ADANIENT": 0.5, "HDFCLIFE": 0.4, "SBILIFE": 0.4, "DRREDDY": 0.4,
    "APOLLOHOSP": 0.4, "TATACONSUM": 0.3, "TATAMOTOR": 0.3, "ADANIPORTS": 0.3,
    "DIVISLAB": 0.3, "BAJAJ-AUTO": 0.3, "HEROMOTOCO": 0.3, "SHRIRAMFIN": 0.3,
    "BEL": 0.2, "HINDALCO": 0.2,
}

# BANKNIFTY constituent weights (approximate)
BANKNIFTY_WEIGHTS: dict[str, float] = {
    "HDFCBANK": 28.0, "ICICIBANK": 24.0, "AXISBANK": 12.0, "KOTAKBANK": 10.0,
    "SBIN": 9.0, "INDUSINDBK": 4.5, "AUBANK": 2.5, "BANDHANBNK": 2.0,
    "FEDERALBNK": 2.0, "IDFCFIRSTB": 2.0, "PNB": 2.0, "BANKBARODA": 2.0,
}


def compute_index_constituent_bias(
    constituent_signals: list[dict],
    index_name: str = "NIFTY",
) -> dict[str, Any]:
    """
    Compute weighted index bias from constituent signals.
    constituent_signals: list of {symbol, tech_bias, direction, conviction, weight_override}
    Returns: weighted_bias (BULLISH/BEARISH/NEUTRAL), breadth score, top contributors.
    """
    weights = NIFTY50_WEIGHTS if index_name == "NIFTY" else BANKNIFTY_WEIGHTS

    if not constituent_signals:
        return {
            "weighted_bias": "NEUTRAL",
            "breadth_score": 50,
            "bull_weight": 0,
            "bear_weight": 0,
            "top_positive": [],
            "top_negative": [],
            "conviction": "LOW",
        }

    total_weight = 0.0
    bull_weight = 0.0
    bear_weight = 0.0
    contributors: list[dict] = []

    for cs in constituent_signals:
        sym = cs.get("symbol", "")
        w = cs.get("weight_override") or weights.get(sym, 0.5)
        bias = cs.get("tech_bias", "NEUTRAL")
        direction = cs.get("direction", bias)
        conviction = cs.get("conviction", 0.5)

        total_weight += w
        if direction in ("BULLISH", "LONG"):
            bull_weight += w * conviction
        elif direction in ("BEARISH", "SHORT"):
            bear_weight += w * conviction

        contributors.append({
            "symbol": sym,
            "direction": direction,
            "weight": w,
            "conviction": conviction,
            "contribution": w * conviction if direction in ("BULLISH", "LONG") else -(w * conviction),
        })

    if total_weight == 0:
        return {"weighted_bias": "NEUTRAL", "breadth_score": 50, "bull_weight": 0, "bear_weight": 0,
                "top_positive": [], "top_negative": [], "conviction": "LOW"}

    norm_bull = bull_weight / total_weight * 100
    norm_bear = bear_weight / total_weight * 100
    breadth_score = round(norm_bull - norm_bear + 50)  # 50 = neutral

    if norm_bull > norm_bear + 10:
        weighted_bias = "BULLISH"
        conv = "HIGH" if norm_bull > norm_bear + 25 else "MEDIUM"
    elif norm_bear > norm_bull + 10:
        weighted_bias = "BEARISH"
        conv = "HIGH" if norm_bear > norm_bull + 25 else "MEDIUM"
    else:
        weighted_bias = "NEUTRAL"
        conv = "LOW"

    contributors.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    top_pos = [c for c in contributors if c["contribution"] > 0][:3]
    top_neg = [c for c in contributors if c["contribution"] < 0][:3]

    return {
        "index_name": index_name,
        "weighted_bias": weighted_bias,
        "breadth_score": breadth_score,
        "bull_weight_pct": round(norm_bull, 1),
        "bear_weight_pct": round(norm_bear, 1),
        "top_positive_contributors": top_pos,
        "top_negative_contributors": top_neg,
        "conviction": conv,
        "constituent_count": len(constituent_signals),
    }

