"""
F&O Strategy Library, Backtest Stats & Signal State Machine — Batch 5 of the Master Spec.
13 trading strategies, eligibility filters, state machine, constituent-weighted index bias.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── 5.1 Strategy Library ─────────────────────────────────────────────────────

STRATEGY_LIBRARY: dict[str, dict[str, Any]] = {
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

        if regime not in preferred and "NORMAL_VOL_TREND" not in preferred:
            continue

        instrument_match = (
            instrument_type_upper in instruments
            or "LIQUID_STOCKS" in instruments
            or instrument_type_upper in ("NIFTY", "BANKNIFTY")
        )
        if not instrument_match:
            continue

        if strategy_stats:
            stats = strategy_stats.get(sid)
            if stats:
                win_rate = stats.get("win_rate", 0)
                expectancy = stats.get("expectancy", 0)
                disabled = stats.get("disabled", False)
                if disabled or win_rate < 0.75 or expectancy < 0.40:
                    continue

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

    disabled = (
        total >= 20
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
    "PENDING", "ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2",
    "CLOSED_WIN", "CLOSED_LOSS", "EXPIRED", "CANCELLED",
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

    if minutes_to_expiry <= 0:
        return {"new_state": "EXPIRED", "reason": "Contract expired", "urgent_exit": True}
    if minutes_to_expiry <= 15 and current_state in ("ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2"):
        return {"new_state": "EXPIRED", "reason": "< 15 mins to expiry — exit immediately", "urgent_exit": True}

    urgent_exit = False
    new_state = current_state
    reason = "No change"

    is_long = direction == "BULLISH"

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
    breadth_score = max(0, min(100, round(norm_bull - norm_bear + 50)))

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
