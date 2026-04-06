"""
Advanced Technical Indicators — Batch 1 of the Master Spec.
Williams %R, CCI, VPT, A/D Line, Ichimoku, Fibonacci,
Pivot Points, Support/Resistance, RSI Divergence,
Candlestick Patterns, Multi-timeframe Trend, Chart Patterns.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


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
    Ratios: 23.6%, 38.2%, 50%, 61.8%, 78.6% + extensions 127.2%, 161.8%, 200%.
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
    i = n - 1

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
