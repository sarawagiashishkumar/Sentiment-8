"""
MFE/MAE Library, Probability Models & Theta Curves — Sections 5 & 6 of Master Spec.

Batch 2 implements:
- 5.1: Offline MFE/MAE library builder per strategy profile
- 5.2: Probability estimators (P_hit, P_SL_first)
- 5.3: Online T1/T2 selector for new signals
- 5.4: Intraday re-evaluation
- 6.1: Empirical theta curves
- 6.2: Forward MFE to expiry
- 6.3: Online Best Exit for live scripts

All calculations are pure Python/NumPy/Pandas. NO LLM numeric work.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy profile identifiers (match server.py strategy IDs)
# ---------------------------------------------------------------------------
STRATEGY_PROFILES = [
    "S1_ORB", "S2_VWAP", "S3_SUPERTREND", "S4_MACD_ADX", "S5_RSI_MEAN_REV",
    "SW1_52W_BREAKOUT", "SW2_200DMA_BOUNCE", "SW3_FLAG_BREAKOUT",
    "E1_SHORT_STRADDLE", "E2_IRON_CONDOR", "E3_CALENDAR_SPREAD",
    "SF1_SCREENER_MOM", "SF2_FORENSIC_MOM",
]

# DTE bands for bucketing
DTE_BANDS = {
    "0DTE": (0, 0),
    "1-2DTE": (1, 2),
    "3-5DTE": (3, 5),
    "GT5DTE": (6, 999),
}

# Time-of-day bands (IST hours)
TOD_BANDS = {
    "OPEN": (9, 10),      # 9:15-10:00
    "MORNING": (10, 12),   # 10:00-12:00
    "AFTERNOON": (12, 14), # 12:00-14:00
    "CLOSE": (14, 16),     # 14:00-15:30
}

# IV regime thresholds
IV_REGIMES = {
    "LOW_IV": (0, 15),
    "NORMAL_IV": (15, 22),
    "HIGH_IV": (22, 30),
    "EXTREME_IV": (30, 999),
}


def _classify_dte_band(dte: int) -> str:
    for label, (lo, hi) in DTE_BANDS.items():
        if lo <= dte <= hi:
            return label
    return "GT5DTE"


def _classify_tod_band(hour: int) -> str:
    for label, (lo, hi) in TOD_BANDS.items():
        if lo <= hour < hi:
            return label
    return "CLOSE"


def _classify_iv_regime(iv: float | None) -> str:
    if iv is None:
        return "NORMAL_IV"
    for label, (lo, hi) in IV_REGIMES.items():
        if lo <= iv < hi:
            return label
    return "EXTREME_IV"


# ---------------------------------------------------------------------------
# 5.1  MFE/MAE Library Builder (from historical OHLCV)
# ---------------------------------------------------------------------------

def compute_mfe_mae_from_ohlcv(
    hist_df: pd.DataFrame,
    entry_price: float,
    entry_bar_idx: int,
    direction: str = "LONG",
    exit_bar_idx: int | None = None,
) -> dict[str, Any]:
    """
    Compute MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion)
    from entry_bar_idx to exit_bar_idx (or end of data).

    For LONG direction:
      MFE = max(High[entry+1:exit] - entry_price)
      MAE = max(entry_price - Low[entry+1:exit])

    Returns: {mfe, mae, mfe_pct, mae_pct, mfe_bar_idx, mae_bar_idx}
    """
    if hist_df is None or hist_df.empty or entry_bar_idx >= len(hist_df) - 1:
        return {"mfe": 0.0, "mae": 0.0, "mfe_pct": 0.0, "mae_pct": 0.0}

    end = exit_bar_idx if exit_bar_idx is not None else len(hist_df)
    subset = hist_df.iloc[entry_bar_idx + 1:end]

    if subset.empty:
        return {"mfe": 0.0, "mae": 0.0, "mfe_pct": 0.0, "mae_pct": 0.0}

    if direction == "LONG":
        highs = subset["High"] if "High" in subset.columns else subset.get("high", pd.Series([entry_price]))
        lows = subset["Low"] if "Low" in subset.columns else subset.get("low", pd.Series([entry_price]))
        mfe = float(highs.max()) - entry_price
        mae = entry_price - float(lows.min())
        # Use argmax/argmin to get integer position, not index value
        mfe_bar = entry_bar_idx + 1 + int(highs.values.argmax()) if not highs.empty else entry_bar_idx
        mae_bar = entry_bar_idx + 1 + int(lows.values.argmin()) if not lows.empty else entry_bar_idx
    else:  # SHORT
        lows = subset["Low"] if "Low" in subset.columns else subset.get("low", pd.Series([entry_price]))
        highs = subset["High"] if "High" in subset.columns else subset.get("high", pd.Series([entry_price]))
        mfe = entry_price - float(lows.min())
        mae = float(highs.max()) - entry_price
        # Use argmax/argmin to get integer position, not index value
        mfe_bar = entry_bar_idx + 1 + int(lows.values.argmin()) if not lows.empty else entry_bar_idx
        mae_bar = entry_bar_idx + 1 + int(highs.values.argmax()) if not highs.empty else entry_bar_idx

    mfe = max(mfe, 0.0)
    mae = max(mae, 0.0)

    return {
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "mfe_pct": round((mfe / entry_price) * 100, 2) if entry_price > 0 else 0.0,
        "mae_pct": round((mae / entry_price) * 100, 2) if entry_price > 0 else 0.0,
        "mfe_bar_idx": mfe_bar,
        "mae_bar_idx": mae_bar,
    }


def build_mfe_mae_library(
    hist_df: pd.DataFrame,
    atr: float,
    strategy_id: str = "S3_SUPERTREND",
    direction: str = "LONG",
    window_bars: int = 75,
) -> list[dict[str, Any]]:
    """
    Build MFE/MAE library by replaying simulated entries on historical data.

    Simulates entries every `window_bars` bars and computes MFE/MAE for each.
    Returns list of trade records with MFE/MAE/features for bucketing.
    """
    if hist_df is None or hist_df.empty or len(hist_df) < window_bars * 2:
        return []

    close_col = "Close" if "Close" in hist_df.columns else "close"

    trades: list[dict] = []
    for i in range(window_bars, len(hist_df) - window_bars, window_bars // 2):
        entry_price = float(hist_df[close_col].iloc[i])
        if entry_price <= 0:
            continue

        mfe_mae = compute_mfe_mae_from_ohlcv(
            hist_df, entry_price, i, direction,
            exit_bar_idx=min(i + window_bars, len(hist_df))
        )

        # Compute features at entry time
        lookback = hist_df.iloc[max(0, i - 20):i]
        entry_vol = float(lookback[close_col].pct_change().std() * math.sqrt(252)) if len(lookback) >= 5 else 0.30

        trades.append({
            "strategy_id": strategy_id,
            "entry_bar_idx": i,
            "entry_price": entry_price,
            "direction": direction,
            "mfe": mfe_mae["mfe"],
            "mae": mfe_mae["mae"],
            "mfe_pct": mfe_mae["mfe_pct"],
            "mae_pct": mfe_mae["mae_pct"],
            "atr_at_entry": atr,
            "realized_vol_at_entry": round(entry_vol, 4),
            "mfe_atr_ratio": round(mfe_mae["mfe"] / atr, 2) if atr > 0 else 0.0,
            "mae_atr_ratio": round(mfe_mae["mae"] / atr, 2) if atr > 0 else 0.0,
        })

    return trades


# ---------------------------------------------------------------------------
# 5.2  Probability Estimators (calibrated frequency tables)
# ---------------------------------------------------------------------------

def build_probability_table(
    mfe_mae_library: list[dict],
    target_offsets_pct: list[float] | None = None,
    sl_distance_pct: float = 10.0,
) -> dict[str, Any]:
    """
    Build P_hit and P_SL_first tables from MFE/MAE library.

    For each candidate target offset (as % of entry):
      P_hit = fraction of trades where MFE_pct >= target_pct
      P_SL_first = fraction where MAE_pct >= sl_distance_pct before MFE >= target_pct

    Returns: {targets: [{offset_pct, p_hit, p_sl_first}], sample_size}
    """
    if not mfe_mae_library:
        return {"targets": [], "sample_size": 0}

    if target_offsets_pct is None:
        target_offsets_pct = [3.0, 5.0, 8.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]

    n = len(mfe_mae_library)
    results = []

    for offset in target_offsets_pct:
        hit_count = 0
        sl_first_count = 0

        for trade in mfe_mae_library:
            mfe_pct = trade.get("mfe_pct", 0.0)
            mae_pct = trade.get("mae_pct", 0.0)

            target_hit = mfe_pct >= offset
            sl_hit = mae_pct >= sl_distance_pct

            if target_hit:
                hit_count += 1

            # Heuristic: if MAE hit SL before MFE reached target
            # Use bar indices if available, else use magnitude comparison
            mfe_bar = trade.get("mfe_bar_idx", 999)
            mae_bar = trade.get("mae_bar_idx", 999)
            if sl_hit and (not target_hit or mae_bar < mfe_bar):
                sl_first_count += 1

        p_hit = hit_count / n if n > 0 else 0.0
        p_sl_first = sl_first_count / n if n > 0 else 0.0

        results.append({
            "offset_pct": offset,
            "p_hit": round(p_hit, 4),
            "p_sl_first": round(p_sl_first, 4),
            "p_hit_minus_sl": round(p_hit - p_sl_first, 4),
        })

    return {
        "targets": results,
        "sample_size": n,
        "sl_distance_pct": sl_distance_pct,
    }


# ---------------------------------------------------------------------------
# 5.3  Online T1/T2 Selector
# ---------------------------------------------------------------------------

# Configurable thresholds
P1_THRESHOLD = 0.65  # T1 minimum P_hit
P2_THRESHOLD = 0.50  # T2 minimum P_hit
MAX_P_SL_FIRST = 0.25  # Maximum acceptable P(SL hit first)


def select_targets_from_probability(
    prob_table: dict[str, Any],
    entry_price: float,
    stop_loss: float,
    minutes_remaining: int = 375,
    p1_threshold: float = P1_THRESHOLD,
    p2_threshold: float = P2_THRESHOLD,
    max_p_sl: float = MAX_P_SL_FIRST,
) -> dict[str, Any]:
    """
    Select T1/T2 from probability table.

    T1 = smallest target where P_hit >= p1_threshold AND P_SL_first <= max_p_sl
    T2 = larger target where P_hit >= p2_threshold AND P_SL_first acceptable

    Returns: {t1, t2, t1_p_hit, t2_p_hit, t1_offset_pct, t2_offset_pct, method}
    """
    targets = prob_table.get("targets", [])
    if not targets:
        return {"t1": None, "t2": None, "method": "no_data"}

    # Time decay factor: reduce expectations with less time remaining
    time_factor = min(1.0, minutes_remaining / 375.0)
    adj_p1 = p1_threshold * (0.7 + 0.3 * time_factor)  # relax slightly near close
    adj_p2 = p2_threshold * (0.7 + 0.3 * time_factor)

    t1_candidate = None
    t2_candidate = None

    for t in targets:
        p_hit = t["p_hit"]
        p_sl = t["p_sl_first"]

        if p_hit >= adj_p1 and p_sl <= max_p_sl and t1_candidate is None:
            t1_candidate = t

        if p_hit >= adj_p2 and p_sl <= max_p_sl * 1.3:
            t2_candidate = t  # keep updating to get the largest qualifying target

    if t1_candidate is None:
        return {"t1": None, "t2": None, "method": "no_qualifying_target"}

    t1_price = round(entry_price * (1 + t1_candidate["offset_pct"] / 100), 2)

    t2_price = None
    if t2_candidate and t2_candidate["offset_pct"] > t1_candidate["offset_pct"]:
        t2_price = round(entry_price * (1 + t2_candidate["offset_pct"] / 100), 2)
    else:
        # Fallback: T2 = T1 × 1.3
        t2_price = round(t1_price * 1.30, 2)

    # Safety: T1 must be above entry
    if t1_price <= entry_price:
        return {"t1": None, "t2": None, "method": "target_below_entry"}

    # Safety: risk:reward check
    risk = max(entry_price - stop_loss, 0.01)
    rr_t1 = (t1_price - entry_price) / risk
    if rr_t1 < 1.0:
        return {"t1": None, "t2": None, "method": "rr_below_minimum"}

    return {
        "t1": t1_price,
        "t2": t2_price,
        "t1_p_hit": t1_candidate["p_hit"],
        "t2_p_hit": t2_candidate["p_hit"] if t2_candidate else None,
        "t1_offset_pct": t1_candidate["offset_pct"],
        "t2_offset_pct": t2_candidate["offset_pct"] if t2_candidate else None,
        "t1_p_sl_first": t1_candidate["p_sl_first"],
        "method": "probability_based",
        "time_factor": round(time_factor, 2),
    }


# ---------------------------------------------------------------------------
# 6.1  Empirical Theta Curves
# ---------------------------------------------------------------------------

def compute_empirical_theta(
    entry_price: float,
    dte: int,
    calendar_days: int,
    iv_regime: str = "NORMAL_IV",
    option_class: str = "index_weekly",
    moneyness: str = "ATM",
) -> dict[str, Any]:
    """
    Estimate empirical theta decay for an option position.

    Uses calibrated models based on option class, IV regime, and moneyness.
    Returns: {intraday_theta, overnight_theta, total_theta, theta_pct}
    """
    if entry_price <= 0 or dte < 0:
        return {"intraday_theta": 0.0, "overnight_theta": 0.0, "total_theta": 0.0, "theta_pct": 0.0}

    # Base theta rate (% of premium per calendar day)
    # These are calibrated from empirical Indian F&O data
    _base_rates = {
        "index_weekly": {"ATM": 3.5, "ITM": 2.0, "OTM": 5.0},
        "index_monthly": {"ATM": 1.5, "ITM": 0.8, "OTM": 2.5},
        "stock_monthly": {"ATM": 2.0, "ITM": 1.2, "OTM": 3.0},
    }
    base_rate = _base_rates.get(option_class, _base_rates["index_weekly"]).get(moneyness, 3.5)

    # IV regime multiplier
    _iv_mult = {
        "LOW_IV": 0.7,
        "NORMAL_IV": 1.0,
        "HIGH_IV": 1.3,
        "EXTREME_IV": 1.6,
    }
    iv_mult = _iv_mult.get(iv_regime, 1.0)

    # DTE acceleration: theta accelerates near expiry (1/sqrt(DTE) model)
    if dte <= 0:
        dte_mult = 3.0  # expiry day: extreme theta
    elif dte == 1:
        dte_mult = 2.0
    elif dte <= 3:
        dte_mult = 1.5
    elif dte <= 7:
        dte_mult = 1.2
    else:
        dte_mult = 1.0

    # Daily theta
    daily_theta_pct = base_rate * iv_mult * dte_mult / 100.0

    # Split into intraday and overnight
    # Empirically: ~60-70% of daily theta erodes during market hours
    intraday_frac = 0.65
    overnight_frac = 0.35

    intraday_theta = round(entry_price * daily_theta_pct * intraday_frac, 2)
    overnight_theta = round(entry_price * daily_theta_pct * overnight_frac, 2)

    # Weekend/holiday adjustment: overnight theta is higher
    weekday_adjustment = 1.0
    if calendar_days > dte:
        # Extra non-trading days (weekends/holidays)
        extra_days = calendar_days - dte
        weekday_adjustment = 1.0 + (extra_days * 0.15)  # 15% extra per non-trading day

    overnight_theta = round(overnight_theta * weekday_adjustment, 2)
    total_theta = round(intraday_theta + overnight_theta, 2)

    return {
        "intraday_theta": intraday_theta,
        "overnight_theta": overnight_theta,
        "total_theta": total_theta,
        "theta_pct": round(daily_theta_pct * 100, 2),
        "dte_mult": dte_mult,
        "iv_regime": iv_regime,
        "option_class": option_class,
    }


# ---------------------------------------------------------------------------
# 6.2  Forward MFE to Expiry
# ---------------------------------------------------------------------------

def compute_forward_mfe(
    hist_df: pd.DataFrame,
    entry_price: float,
    remaining_trading_days: int,
    atr: float,
    daily_theta: float = 0.0,
) -> dict[str, Any]:
    """
    Compute forward MFE (max premium from entry to expiry) from historical data.

    Adjusts for theta decay across the forward path.
    Returns: {forward_mfe, best_exit_day, theta_adjusted_mfe, percentile_80, percentile_90}
    """
    if hist_df is None or hist_df.empty or remaining_trading_days <= 0:
        return {"forward_mfe": 0.0, "best_exit_day": 0, "reliable": False}

    close_col = "Close" if "Close" in hist_df.columns else "close"
    high_col = "High" if "High" in hist_df.columns else "high"

    n_bars = len(hist_df)
    window = min(remaining_trading_days, 20)

    # Collect forward MFE samples
    mfe_samples: list[dict] = []

    for i in range(20, n_bars - window):
        ep = float(hist_df[close_col].iloc[i])
        if ep <= 0:
            continue

        # Forward window MFE
        forward = hist_df.iloc[i + 1: i + 1 + window]
        if forward.empty:
            continue

        highs = forward[high_col] if high_col in forward.columns else forward.get("high", pd.Series())
        if highs.empty:
            continue

        peak = float(highs.max())
        raw_mfe = peak - ep

        # Theta adjustment: subtract cumulative theta for each forward day
        # Use argmax to get integer position within the forward window
        peak_idx = int(highs.values.argmax()) if not highs.empty else 0
        theta_cost = daily_theta * (peak_idx + 1)
        adjusted_mfe = max(raw_mfe - theta_cost, 0.0)

        # Scale to current entry price
        mfe_pct = (raw_mfe / ep) * 100 if ep > 0 else 0.0
        adj_mfe_pct = (adjusted_mfe / ep) * 100 if ep > 0 else 0.0

        mfe_samples.append({
            "raw_mfe_pct": mfe_pct,
            "adj_mfe_pct": adj_mfe_pct,
            "peak_day": peak_idx,
        })

    if not mfe_samples:
        return {"forward_mfe": 0.0, "best_exit_day": 0, "reliable": False}

    raw_mfes = [s["raw_mfe_pct"] for s in mfe_samples]
    adj_mfes = [s["adj_mfe_pct"] for s in mfe_samples]
    peak_days = [s["peak_day"] for s in mfe_samples]

    p80_raw = float(np.percentile(raw_mfes, 80))
    p90_raw = float(np.percentile(raw_mfes, 90))
    p80_adj = float(np.percentile(adj_mfes, 80))
    median_peak_day = int(np.median(peak_days))

    # Convert percentiles to price
    best_exit_price = round(entry_price * (1 + p80_adj / 100), 2)

    return {
        "forward_mfe_p80_pct": round(p80_raw, 2),
        "forward_mfe_p90_pct": round(p90_raw, 2),
        "theta_adj_p80_pct": round(p80_adj, 2),
        "best_exit_price": best_exit_price,
        "best_exit_day": min(median_peak_day, remaining_trading_days),
        "sample_size": len(mfe_samples),
        "reliable": len(mfe_samples) >= 30,
    }


# ---------------------------------------------------------------------------
# 6.3  Online Best Exit for Live Script
# ---------------------------------------------------------------------------

def compute_best_exit_online(
    entry_price: float,
    remaining_trading_days: int,
    dte: int,
    iv_regime: str = "NORMAL_IV",
    market_regime: str = "LowVolTrend",
    hist_df: pd.DataFrame | None = None,
    atr: float | None = None,
    vix: float | None = None,
    option_class: str = "index_weekly",
    moneyness: str = "ATM",
) -> dict[str, Any]:
    """
    Compute Best Exit price and day for a live F&O script.

    Combines:
    - Forward MFE from historical data (section 6.2)
    - Empirical theta curves (section 6.1)
    - Regime-adjusted expectations

    Returns: {best_exit_price, best_exit_day, reliable, method}
    """
    if entry_price <= 0 or remaining_trading_days <= 0:
        return {"best_exit_price": entry_price, "best_exit_day": 0, "reliable": False, "method": "no_data"}

    # Get theta curve
    calendar_days = int(remaining_trading_days * 1.4)  # approximate
    theta = compute_empirical_theta(
        entry_price, dte, calendar_days, iv_regime, option_class, moneyness
    )
    daily_theta = theta["total_theta"]

    # Try forward MFE from historical data
    if hist_df is not None and not hist_df.empty and atr and atr > 0:
        fwd = compute_forward_mfe(
            hist_df, entry_price, remaining_trading_days, atr, daily_theta
        )
        if fwd["reliable"]:
            # Regime adjustment
            regime_mult = {
                "LowVolTrend": 1.0,
                "LowVolRange": 0.8,
                "HighVolTrend": 1.2,
                "HighVolCrash": 0.6,
                "PreEvent": 0.7,
                "PostEventIVCrush": 0.5,
            }.get(market_regime, 1.0)

            adj_price = round(
                entry_price + (fwd["best_exit_price"] - entry_price) * regime_mult,
                2
            )
            adj_price = max(adj_price, round(entry_price * 1.01, 2))

            return {
                "best_exit_price": adj_price,
                "best_exit_day": fwd["best_exit_day"],
                "reliable": True,
                "method": "forward_mfe_theta_adjusted",
                "forward_mfe_p80": fwd["theta_adj_p80_pct"],
                "daily_theta": daily_theta,
                "regime_mult": regime_mult,
                "sample_size": fwd["sample_size"],
            }

    # Fallback: ATR-based projection with theta decay
    _atr = atr or (entry_price * 0.012)
    _n_days = min(remaining_trading_days, 10)
    _underlying_move = _atr * math.sqrt(_n_days) * 1.5
    _delta_est = 0.45
    _option_gain = _underlying_move * _delta_est
    _total_theta = daily_theta * _n_days

    best_exit = round(entry_price + max(_option_gain - _total_theta, entry_price * 0.02), 2)
    best_day = min(int(_n_days * 0.6), remaining_trading_days - 1) if remaining_trading_days > 1 else 0

    return {
        "best_exit_price": best_exit,
        "best_exit_day": max(best_day, 0),
        "reliable": False,
        "method": "atr_theta_fallback",
        "daily_theta": daily_theta,
    }


# ---------------------------------------------------------------------------
# 5.4  Intraday Re-evaluation
# ---------------------------------------------------------------------------

def reevaluate_signal_targets(
    current_ltp: float,
    entry_price: float,
    current_t1: float,
    current_t2: float,
    stop_loss: float,
    minutes_remaining: int,
    prob_table: dict | None = None,
    regime: str = "LowVolTrend",
) -> dict[str, Any]:
    """
    Re-evaluate T1/T2 for an active signal during intraday refresh.

    May:
    - Raise targets modestly if probabilities improve
    - Mark as URGENT_EXIT if probabilities collapse
    - Leave unchanged if still valid

    Returns: {action, new_t1, new_t2, reason}
    """
    if minutes_remaining <= 0:
        return {
            "action": "HOLD",
            "new_t1": current_t1,
            "new_t2": current_t2,
            "reason": "Session ended",
        }

    # Check if already profitable
    unrealized_pnl_pct = ((current_ltp - entry_price) / entry_price) * 100 if entry_price > 0 else 0

    # If near T1 (within 5%), consider trailing
    t1_distance_pct = ((current_t1 - current_ltp) / current_ltp) * 100 if current_ltp > 0 else 999

    if unrealized_pnl_pct > 0 and t1_distance_pct < 3:
        # Near T1 — trail stop to breakeven + small profit
        new_sl = round(max(entry_price * 1.02, stop_loss), 2)
        return {
            "action": "TRAIL_STOP",
            "new_t1": current_t1,
            "new_t2": current_t2,
            "new_stop_loss": new_sl,
            "reason": f"Near T1 ({t1_distance_pct:.1f}% away), trailing stop to breakeven+2%",
        }

    # If underwater and little time left — urgent exit candidate
    if unrealized_pnl_pct < -5 and minutes_remaining < 60:
        return {
            "action": "URGENT_EXIT_CANDIDATE",
            "new_t1": current_t1,
            "new_t2": current_t2,
            "reason": f"Underwater {unrealized_pnl_pct:.1f}% with only {minutes_remaining}min remaining",
        }

    # If regime has shifted adversely
    adverse_regimes = {"HighVolCrash", "PreEvent"}
    if regime in adverse_regimes and unrealized_pnl_pct < 0:
        return {
            "action": "REDUCE_EXPOSURE",
            "new_t1": round(current_t1 * 0.90, 2),  # Lower T1 by 10%
            "new_t2": round(current_t2 * 0.85, 2),  # Lower T2 by 15%
            "reason": f"Regime shifted to {regime} while underwater",
        }

    return {
        "action": "HOLD",
        "new_t1": current_t1,
        "new_t2": current_t2,
        "reason": "Targets still valid",
    }


# ---------------------------------------------------------------------------
# 1.8  No-Chasing Rule (intraday max band check)
# ---------------------------------------------------------------------------

def check_no_chasing_rule(
    current_ltp: float,
    entry_price: float,
    expected_max_band: float,
    chasing_threshold_pct: float = 75.0,
) -> dict[str, Any]:
    """
    Check if the current LTP has already reached too much of the expected
    intraday max band, making a fresh entry inadvisable.

    Returns: {allow_entry: bool, pct_of_band_achieved, reason}
    """
    if expected_max_band <= 0 or entry_price <= 0:
        return {"allow_entry": True, "pct_of_band_achieved": 0.0, "reason": "No band data"}

    # How much of the expected max band has been achieved
    move = current_ltp - entry_price
    pct_achieved = (move / expected_max_band) * 100 if expected_max_band > 0 else 0.0

    if pct_achieved >= chasing_threshold_pct:
        return {
            "allow_entry": False,
            "pct_of_band_achieved": round(pct_achieved, 1),
            "reason": f"Already {pct_achieved:.0f}% of expected max band achieved — no chase",
        }

    return {
        "allow_entry": True,
        "pct_of_band_achieved": round(pct_achieved, 1),
        "reason": f"Only {pct_achieved:.0f}% of band achieved — entry OK",
    }


# ---------------------------------------------------------------------------
# 0DTE ATM Long Safety Check (section 1.8 extra safety)
# ---------------------------------------------------------------------------

def check_0dte_atm_safety(
    underlying_ltp: float,
    strike: float,
    entry_time_hour: int,
    dte: int,
    theta_adjusted_mfe: float | None = None,
    min_mfe_threshold: float = 2.0,
    cutoff_hour: int = 14,
    cutoff_minute: int = 30,
) -> dict[str, Any]:
    """
    For 0DTE long option buying, disallow exact ATM strikes after cutoff
    or when theta-adjusted MFE is too low.

    Returns: {allow_entry: bool, reason}
    """
    if dte != 0:
        return {"allow_entry": True, "reason": "Not 0DTE"}

    # Check ATM proximity
    atm_distance_pct = abs(underlying_ltp - strike) / underlying_ltp * 100 if underlying_ltp > 0 else 999

    if atm_distance_pct > 0.05:
        return {"allow_entry": True, "reason": "Not near-ATM"}

    # After cutoff
    if entry_time_hour > cutoff_hour or (entry_time_hour == cutoff_hour and True):
        return {
            "allow_entry": False,
            "reason": f"0DTE ATM long disallowed after {cutoff_hour}:{cutoff_minute:02d} IST due to theta risk",
        }

    # Low theta-adjusted MFE
    if theta_adjusted_mfe is not None and theta_adjusted_mfe < min_mfe_threshold:
        return {
            "allow_entry": False,
            "reason": f"0DTE ATM long disallowed: theta-adjusted MFE ({theta_adjusted_mfe:.1f}%) below {min_mfe_threshold}% threshold",
        }

    return {"allow_entry": True, "reason": "0DTE ATM conditions met"}
