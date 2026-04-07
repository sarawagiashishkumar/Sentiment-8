"""
Intraday Sentiment & Feature Engine — Section 3 of Master Spec.

Computes multi-timeframe technicals, VWAP distance, sector momentum,
and order-flow features for each eligible underlying.

All calculations are pure Python/Pandas/NumPy. NO LLM numeric work.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 3.1  Underlying + sector momentum feature engine
# ---------------------------------------------------------------------------

def compute_multi_timeframe_emas(
    bars_1m: pd.DataFrame | None = None,
    bars_5m: pd.DataFrame | None = None,
    bars_15m: pd.DataFrame | None = None,
    bars_60m: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Compute EMAs and slopes on multiple intraday timeframes.

    Each bars_Xm DataFrame should have columns: ['Close'] (at minimum).
    Returns dict with EMA values and slopes per timeframe.
    """
    result: dict[str, Any] = {}

    for label, df, periods in [
        ("1m", bars_1m, [9, 21]),
        ("5m", bars_5m, [9, 21, 55]),
        ("15m", bars_15m, [9, 21, 55]),
        ("60m", bars_60m, [20, 50]),
    ]:
        if df is None or df.empty or "Close" not in df.columns:
            result[label] = {"available": False}
            continue

        close = df["Close"].dropna()
        if len(close) < 5:
            result[label] = {"available": False}
            continue

        tf_data: dict[str, Any] = {"available": True}
        current_price = float(close.iloc[-1])
        tf_data["ltp"] = current_price

        for p in periods:
            if len(close) >= p:
                ema = close.ewm(span=p, adjust=False).mean()
                ema_val = float(ema.iloc[-1])
                # Slope: (ema[-1] - ema[-3]) / ema[-3] if enough data
                slope = 0.0
                if len(ema) >= 4:
                    prev = float(ema.iloc[-4])
                    slope = ((ema_val - prev) / prev) * 100 if prev != 0 else 0.0
                tf_data[f"ema_{p}"] = round(ema_val, 2)
                tf_data[f"ema_{p}_slope"] = round(slope, 4)
                tf_data[f"above_ema_{p}"] = current_price > ema_val

        result[label] = tf_data

    return result


def compute_vwap_features(
    bars: pd.DataFrame | None,
    current_ltp: float | None = None,
    atr: float | None = None,
) -> dict[str, Any]:
    """
    Compute VWAP and distance metrics.

    bars should have: ['Close', 'Volume', 'High', 'Low'] columns.
    Returns: vwap, vwap_distance, vwap_distance_atr_normalized, above_vwap.
    """
    if bars is None or bars.empty:
        return {"available": False}

    required = {"Close", "Volume", "High", "Low"}
    if not required.issubset(set(bars.columns)):
        return {"available": False}

    # Typical price × volume
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
    cum_tp_vol = (typical * bars["Volume"]).cumsum()
    cum_vol = bars["Volume"].cumsum()

    vwap_series = cum_tp_vol / cum_vol.replace(0, np.nan)
    vwap_val = float(vwap_series.iloc[-1]) if not vwap_series.empty and not pd.isna(vwap_series.iloc[-1]) else None

    if vwap_val is None:
        return {"available": False}

    ltp = current_ltp if current_ltp is not None else float(bars["Close"].iloc[-1])
    distance = ltp - vwap_val
    distance_pct = (distance / vwap_val) * 100 if vwap_val != 0 else 0.0

    # ATR-normalized distance
    distance_atr = (distance / atr) if atr and atr > 0 else None

    return {
        "available": True,
        "vwap": round(vwap_val, 2),
        "ltp": round(ltp, 2),
        "distance": round(distance, 2),
        "distance_pct": round(distance_pct, 2),
        "distance_atr": round(distance_atr, 3) if distance_atr is not None else None,
        "above_vwap": ltp > vwap_val,
    }


def compute_intraday_technicals(
    bars: pd.DataFrame | None,
    current_ltp: float | None = None,
) -> dict[str, Any]:
    """
    Compute a full set of intraday technicals from bar data.

    bars should have: ['Close', 'High', 'Low', 'Volume', 'Open'] columns.
    Returns: rsi_14, macd dict, stochastic dict, and basic stats.
    """
    if bars is None or bars.empty:
        return {"available": False}

    close = bars.get("Close")
    if close is None or len(close) < 15:
        return {"available": False}

    result: dict[str, Any] = {"available": True}

    # RSI(14)
    delta = close.diff().dropna()
    if len(delta) >= 14:
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        result["rsi_14"] = round(float(val), 1) if not pd.isna(val) else None
    else:
        result["rsi_14"] = None

    # MACD
    if len(close) >= 26:
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        result["macd"] = {
            "macd_line": round(float(macd_line.iloc[-1]), 4),
            "signal_line": round(float(signal_line.iloc[-1]), 4),
            "histogram": round(float(histogram.iloc[-1]), 4),
            "bullish": float(macd_line.iloc[-1]) > float(signal_line.iloc[-1]),
        }
    else:
        result["macd"] = None

    # Stochastic(14,3,3)
    if len(bars) >= 14 and "High" in bars.columns and "Low" in bars.columns:
        high14 = bars["High"].rolling(14).max()
        low14 = bars["Low"].rolling(14).min()
        k_raw = ((close - low14) / (high14 - low14).replace(0, np.nan)) * 100
        k = k_raw.rolling(3).mean()
        d = k.rolling(3).mean()
        result["stochastic"] = {
            "k": round(float(k.iloc[-1]), 1) if not pd.isna(k.iloc[-1]) else None,
            "d": round(float(d.iloc[-1]), 1) if not pd.isna(d.iloc[-1]) else None,
        }
    else:
        result["stochastic"] = None

    # Intraday return
    if "Open" in bars.columns and len(bars) > 0:
        open_val = float(bars["Open"].iloc[0])
        close_val = float(close.iloc[-1])
        if open_val > 0:
            result["intraday_return_pct"] = round(((close_val - open_val) / open_val) * 100, 2)
        else:
            result["intraday_return_pct"] = 0.0
    else:
        result["intraday_return_pct"] = 0.0

    # Intraday volatility (annualized from bar returns)
    if len(close) >= 10:
        returns = close.pct_change().dropna()
        if len(returns) >= 5:
            # Assuming ~375 1-minute bars in a session
            bar_vol = float(returns.std())
            bars_per_day = max(len(returns), 60)
            daily_vol = bar_vol * math.sqrt(bars_per_day)
            annual_vol = daily_vol * math.sqrt(252)
            result["intraday_volatility"] = round(annual_vol, 4)
        else:
            result["intraday_volatility"] = None
    else:
        result["intraday_volatility"] = None

    return result


# ---------------------------------------------------------------------------
# 3.3  Order Book Imbalance & Volume Delta
# ---------------------------------------------------------------------------

FlowBand = Literal[
    "StrongBuyFlow", "ModerateBuyFlow", "NeutralFlow",
    "ModerateSellFlow", "StrongSellFlow"
]


def compute_order_book_imbalance(
    bid_volumes: list[float],
    ask_volumes: list[float],
) -> dict[str, Any]:
    """
    Compute Order Book Imbalance (OBI) from best N bid/ask levels.

    OBI = (BidVolume - AskVolume) / (BidVolume + AskVolume)
    Range: -1.0 (all asks) to +1.0 (all bids).
    """
    total_bid = sum(bid_volumes) if bid_volumes else 0.0
    total_ask = sum(ask_volumes) if ask_volumes else 0.0
    total = total_bid + total_ask

    if total <= 0:
        return {"obi": 0.0, "total_bid_volume": 0, "total_ask_volume": 0}

    obi = (total_bid - total_ask) / total
    return {
        "obi": round(obi, 4),
        "total_bid_volume": total_bid,
        "total_ask_volume": total_ask,
    }


def compute_volume_delta(
    bars: pd.DataFrame | None,
) -> dict[str, Any]:
    """
    Compute aggressive buy vs sell volume delta from bar data.

    Heuristic: if Close > Open → bar volume counted as buy; else sell.
    Returns cumulative volume_delta and per-bar deltas.
    """
    if bars is None or bars.empty:
        return {"volume_delta": 0.0, "buy_volume": 0, "sell_volume": 0, "available": False}

    if "Close" not in bars.columns or "Open" not in bars.columns or "Volume" not in bars.columns:
        return {"volume_delta": 0.0, "buy_volume": 0, "sell_volume": 0, "available": False}

    buy_vol = 0.0
    sell_vol = 0.0
    for _, row in bars.iterrows():
        vol = float(row.get("Volume", 0) or 0)
        if float(row["Close"]) >= float(row["Open"]):
            buy_vol += vol
        else:
            sell_vol += vol

    delta = buy_vol - sell_vol
    return {
        "volume_delta": round(delta, 0),
        "buy_volume": round(buy_vol, 0),
        "sell_volume": round(sell_vol, 0),
        "available": True,
    }


def classify_flow_band(
    obi: float,
    volume_delta: float,
    avg_volume: float | None = None,
) -> FlowBand:
    """
    Classify order flow into discrete bands using OBI and volume delta.

    Thresholds:
      OBI > +0.30 AND vol_delta > 0 → StrongBuyFlow
      OBI > +0.10 AND vol_delta > 0 → ModerateBuyFlow
      OBI < -0.30 AND vol_delta < 0 → StrongSellFlow
      OBI < -0.10 AND vol_delta < 0 → ModerateSellFlow
      else → NeutralFlow
    """
    # Normalize volume delta if avg_volume is available
    vd_ratio = 0.0
    if avg_volume and avg_volume > 0:
        vd_ratio = volume_delta / avg_volume
    else:
        vd_ratio = 1.0 if volume_delta > 0 else (-1.0 if volume_delta < 0 else 0.0)

    if obi > 0.30 and vd_ratio > 0:
        return "StrongBuyFlow"
    elif obi > 0.10 and vd_ratio > 0:
        return "ModerateBuyFlow"
    elif obi < -0.30 and vd_ratio < 0:
        return "StrongSellFlow"
    elif obi < -0.10 and vd_ratio < 0:
        return "ModerateSellFlow"
    else:
        return "NeutralFlow"


# ---------------------------------------------------------------------------
# 3.4  Market Regime Classification (enhanced per spec)
# ---------------------------------------------------------------------------

RegimeLabel = Literal[
    "LowVolTrend", "LowVolRange",
    "HighVolTrend", "HighVolCrash",
    "PreEvent", "PostEventIVCrush",
]


def classify_regime_enhanced(
    india_vix: float | None,
    realized_vol: float | None,
    adx: float | None,
    has_upcoming_event: bool = False,
    recent_iv_drop_pct: float | None = None,
) -> dict[str, Any]:
    """
    Classify market regime using VIX, realized vol, and ADX.

    Returns:
      - regime: RegimeLabel
      - vix_level: str (low/normal/elevated/extreme)
      - trend_strength: str (weak/moderate/strong)
      - confidence: float (0-1)
    """
    vix = india_vix or 15.0  # default if unavailable
    hv = realized_vol or 0.15
    _adx = adx or 20.0

    # Classify VIX level
    if vix < 13:
        vix_level = "low"
    elif vix < 18:
        vix_level = "normal"
    elif vix < 25:
        vix_level = "elevated"
    else:
        vix_level = "extreme"

    # Classify trend strength
    if _adx >= 30:
        trend_str = "strong"
    elif _adx >= 20:
        trend_str = "moderate"
    else:
        trend_str = "weak"

    # Event-based regimes take priority
    if has_upcoming_event and vix_level in ("elevated", "extreme"):
        regime: RegimeLabel = "PreEvent"
        confidence = 0.75
    elif recent_iv_drop_pct is not None and recent_iv_drop_pct > 15 and vix_level in ("low", "normal"):
        regime = "PostEventIVCrush"
        confidence = 0.70
    elif vix_level == "extreme" and trend_str in ("moderate", "strong"):
        regime = "HighVolCrash"
        confidence = 0.85
    elif vix_level in ("elevated", "extreme") and trend_str == "strong":
        regime = "HighVolTrend"
        confidence = 0.80
    elif vix_level in ("low", "normal") and trend_str in ("moderate", "strong"):
        regime = "LowVolTrend"
        confidence = 0.80
    else:
        regime = "LowVolRange"
        confidence = 0.65

    return {
        "regime": regime,
        "vix_level": vix_level,
        "vix_value": round(vix, 1),
        "trend_strength": trend_str,
        "adx_value": round(_adx, 1),
        "realized_vol": round(hv, 4) if hv else None,
        "confidence": round(confidence, 2),
    }


# ---------------------------------------------------------------------------
# Composite intraday feature vector for a single underlying
# ---------------------------------------------------------------------------

def build_intraday_feature_vector(
    symbol: str,
    bars_daily: pd.DataFrame | None = None,
    bars_intraday: pd.DataFrame | None = None,
    vwap_data: dict | None = None,
    order_flow: dict | None = None,
    regime: dict | None = None,
    sector_breadth: dict | None = None,
) -> dict[str, Any]:
    """
    Aggregate all intraday features into a single feature dict for a symbol.

    This is the canonical feature vector used by:
    - Target engine (section 5) for P_hit lookups
    - Confluence Score Bucket B (section 7)
    """
    vwap = vwap_data or {}
    flow = order_flow or {}
    reg = regime or {}
    sector = sector_breadth or {}

    # Intraday technicals from daily bars (fallback)
    intra_tech = compute_intraday_technicals(bars_intraday or bars_daily)

    return {
        "symbol": symbol,
        "rsi_14": intra_tech.get("rsi_14"),
        "macd": intra_tech.get("macd"),
        "stochastic": intra_tech.get("stochastic"),
        "intraday_return_pct": intra_tech.get("intraday_return_pct", 0.0),
        "intraday_volatility": intra_tech.get("intraday_volatility"),
        "vwap_distance_pct": vwap.get("distance_pct"),
        "vwap_distance_atr": vwap.get("distance_atr"),
        "above_vwap": vwap.get("above_vwap"),
        "flow_band": flow.get("flow_band", "NeutralFlow"),
        "obi": flow.get("obi", 0.0),
        "volume_delta": flow.get("volume_delta", 0.0),
        "regime": reg.get("regime", "LowVolRange"),
        "regime_confidence": reg.get("confidence", 0.5),
        "sector_breadth_score": sector.get("breadth_score"),
        "sector_pct_uptrend": sector.get("pct_weight_in_uptrend"),
    }
