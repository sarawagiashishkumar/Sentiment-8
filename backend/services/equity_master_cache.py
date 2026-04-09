"""
Equity Master Cache — Single source of truth for all equity data.

Written by refresh functions (Kite OHLCV, fundamentals, technicals).
Read by price_band_engine, multibagger_engine, portfolio_engine.
Zero redundant API calls — fetch once, consume everywhere.
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

CACHE_COLLECTION = "equity_master_cache"
STALE_MARKET_HOURS_SEC = 30 * 60      # 30 min during market hours
STALE_POST_CLOSE_SEC = 25 * 3600      # 25 hours post-close


class CacheMissError(Exception):
    pass


def _srv():
    import server
    return server


# ── Reader functions ─────────────────────────────────────────────────

async def get_symbol(symbol: str) -> dict | None:
    """Return cached document or None."""
    _s = _srv()
    doc = await _s.db[CACHE_COLLECTION].find_one(
        {"symbol": symbol.upper()}, {"_id": 0}
    )
    return doc


async def is_stale(symbol: str) -> bool:
    """Check if cached document is stale."""
    doc = await get_symbol(symbol)
    if doc is None:
        return True
    last_refresh = doc.get("last_refreshed_at")
    if last_refresh is None:
        return True
    if isinstance(last_refresh, str):
        try:
            last_refresh = datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return True
    now = datetime.now(timezone.utc)
    age_sec = (now - last_refresh).total_seconds()
    # Check if within market hours (IST 09:15-15:30 = UTC 03:45-10:00)
    utc_hour = now.hour
    is_market_hours = 3 <= utc_hour <= 10
    threshold = STALE_MARKET_HOURS_SEC if is_market_hours else STALE_POST_CLOSE_SEC
    return age_sec > threshold


# ── Computation helpers ──────────────────────────────────────────────

def _compute_hv(closes: list[float], window: int) -> float | None:
    """Compute annualised historical volatility from log returns."""
    if len(closes) < window + 1:
        return None
    arr = np.array(closes[-(window + 1):], dtype=float)
    log_returns = np.diff(np.log(arr))
    if len(log_returns) < window:
        return None
    std = float(np.std(log_returns[-window:], ddof=1))
    return round(std * math.sqrt(252), 4)


def _compute_trend(closes: list[float], ema_short: int = 20, ema_long: int = 50) -> str:
    """Simple trend classification: up/down/sideways."""
    if len(closes) < ema_long + 5:
        return "sideways"
    s = pd.Series(closes)
    ema_s = s.ewm(span=ema_short, adjust=False).mean().iloc[-1]
    ema_l = s.ewm(span=ema_long, adjust=False).mean().iloc[-1]
    ltp = closes[-1]
    if ltp > ema_s > ema_l:
        return "up"
    elif ltp < ema_s < ema_l:
        return "down"
    return "sideways"


def _compute_supertrend_signal(highs: list[float], lows: list[float],
                                closes: list[float], period: int = 10,
                                multiplier: float = 3.0) -> str:
    """Compute current supertrend signal: 'buy' or 'sell'."""
    if len(closes) < period + 1:
        return "sell"
    df = pd.DataFrame({"high": highs, "low": lows, "close": closes})
    hl2 = (df["high"] + df["low"]) / 2
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    st_upper = upper.copy()
    st_lower = lower.copy()
    for i in range(1, len(df)):
        if not np.isnan(st_lower.iloc[i - 1]) and st_lower.iloc[i] > st_lower.iloc[i - 1] and df["close"].iloc[i - 1] > st_lower.iloc[i - 1]:
            pass
        elif not np.isnan(st_lower.iloc[i - 1]) and df["close"].iloc[i - 1] > st_lower.iloc[i - 1]:
            st_lower.iloc[i] = max(st_lower.iloc[i], st_lower.iloc[i - 1])
        if not np.isnan(st_upper.iloc[i - 1]) and st_upper.iloc[i] < st_upper.iloc[i - 1] and df["close"].iloc[i - 1] < st_upper.iloc[i - 1]:
            pass
        elif not np.isnan(st_upper.iloc[i - 1]) and df["close"].iloc[i - 1] < st_upper.iloc[i - 1]:
            st_upper.iloc[i] = min(st_upper.iloc[i], st_upper.iloc[i - 1])
    direction = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > st_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < st_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
    return "buy" if direction.iloc[-1] == 1 else "sell"


def _compute_demand_supply_zones(hist: pd.DataFrame, n: int = 3) -> tuple[list[dict], list[dict]]:
    """Identify top demand (support) and supply (resistance) zones from swing points."""
    demand, supply = [], []
    if len(hist) < 20:
        return demand, supply
    highs = hist["high" if "high" in hist.columns else "High"].values
    lows = hist["low" if "low" in hist.columns else "Low"].values
    volumes = hist["volume" if "volume" in hist.columns else "Volume"].values if ("volume" in hist.columns or "Volume" in hist.columns) else np.ones(len(hist))
    avg_vol = float(np.mean(volumes)) if len(volumes) > 0 else 1.0
    # Swing lows = demand zones
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            strength = float(volumes[i] / avg_vol) if avg_vol > 0 else 1.0
            demand.append({"low": round(float(lows[i]) * 0.995, 2), "high": round(float(lows[i]) * 1.005, 2), "strength": round(strength, 2)})
    # Swing highs = supply zones
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            strength = float(volumes[i] / avg_vol) if avg_vol > 0 else 1.0
            supply.append({"low": round(float(highs[i]) * 0.995, 2), "high": round(float(highs[i]) * 1.005, 2), "strength": round(strength, 2)})
    demand.sort(key=lambda x: x["strength"], reverse=True)
    supply.sort(key=lambda x: x["strength"], reverse=True)
    return demand[:n], supply[:n]


def _compute_camarilla_pivots(high: float, low: float, close: float) -> dict:
    """Compute Camarilla pivot points."""
    r = high - low
    return {
        "R3": round(close + r * 1.1 / 4, 2),
        "R4": round(close + r * 1.1 / 2, 2),
        "S3": round(close - r * 1.1 / 4, 2),
        "S4": round(close - r * 1.1 / 2, 2),
    }


def _compute_delivery_pct_trend(delivery_pcts: list[float]) -> str:
    """Classify delivery percentage trend from recent data."""
    if len(delivery_pcts) < 5:
        return "flat"
    recent = np.mean(delivery_pcts[:5])
    older = np.mean(delivery_pcts[5:min(20, len(delivery_pcts))])
    if recent > older * 1.1:
        return "rising"
    elif recent < older * 0.9:
        return "falling"
    return "flat"


# ── Writer: build full cache document from raw data ──────────────────

async def _build_cache_document(symbol: str) -> dict | None:
    """Build a complete equity_master_cache document for a symbol."""
    _s = _srv()
    from services.kite_client import _fetch_kite_hist_ohlcv_for_equity
    from services.hist_data import _get_hist_ohlcv
    from services.india_vix import _get_india_vix
    from services.indicators import compute_rsi, compute_macd, compute_atr, compute_adx, compute_obv, compute_ema
    from services.advanced_indicators import compute_fibonacci_levels, compute_pivot_points, compute_support_resistance
    from services.regime_engine import regime_classify
    from services.forensic_audit import compute_altman_z_score, compute_roic_vs_wacc, compute_growth_quality

    # Fetch core data from Kite via existing cache
    stock_core = None
    try:
        stock_core = await _s._get_stock_core_cached(symbol)
    except Exception:
        pass
    if not stock_core or not stock_core.get("ltp"):
        logger.debug("No stock core data for %s", symbol)
        return None
    ltp = float(stock_core.get("ltp", 0))
    if ltp <= 0:
        return None

    # Fetch historical OHLCV (1Y daily)
    hist_df = await _get_hist_ohlcv(symbol, "1y")
    if hist_df is None or len(hist_df) < 30:
        logger.debug("Insufficient OHLCV data for %s", symbol)
        return None

    # Normalize column names
    col_map = {}
    for c in hist_df.columns:
        cl = c.lower()
        if cl in ("open", "high", "low", "close", "volume", "date"):
            col_map[c] = cl
    hist_df = hist_df.rename(columns=col_map)
    for needed in ("open", "high", "low", "close", "volume"):
        if needed not in hist_df.columns:
            if needed.capitalize() in hist_df.columns:
                hist_df[needed] = hist_df[needed.capitalize()]

    closes = hist_df["close"].tolist()
    highs = hist_df["high"].tolist()
    lows = hist_df["low"].tolist()
    volumes = hist_df["volume"].tolist()

    # OHLCV records for storage (last 252 trading days)
    ohlcv_daily_1y = []
    for _, row in hist_df.tail(252).iterrows():
        ohlcv_daily_1y.append({
            "date": str(row.get("date", "")),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })

    # Volatility windows
    hv_10d = _compute_hv(closes, 10)
    hv_20d = _compute_hv(closes, 20)
    hv_60d = _compute_hv(closes, 60)
    hv_90d = _compute_hv(closes, 90)
    hv_252d = _compute_hv(closes, min(252, len(closes) - 1)) if len(closes) > 50 else None

    # IV from iv_history collection
    iv_doc = await _s.db.iv_history.find_one(
        {"symbol": symbol}, {"_id": 0, "iv_atm": 1, "iv_rank_52w": 1},
        sort=[("snapshot_date", -1)]
    )
    iv_atm = float(iv_doc["iv_atm"]) if iv_doc and iv_doc.get("iv_atm") else None
    iv_rank_52w = float(iv_doc["iv_rank_52w"]) if iv_doc and iv_doc.get("iv_rank_52w") else None
    realized_vs_iv_ratio = round(hv_20d / iv_atm, 4) if (hv_20d and iv_atm and iv_atm > 0) else None

    # ATR
    atr_14_daily = compute_atr(hist_df, 14)
    # Weekly ATR (resample if enough data)
    atr_14_weekly = None
    if len(hist_df) >= 70:
        weekly_df = hist_df.tail(70).copy()
        weekly_df.index = pd.RangeIndex(len(weekly_df))
        # Group every 5 rows as a "week"
        week_groups = [weekly_df.iloc[i:i+5] for i in range(0, len(weekly_df), 5)]
        if len(week_groups) >= 15:
            w_data = []
            for wg in week_groups:
                w_data.append({"high": wg["high"].max(), "low": wg["low"].min(), "close": wg["close"].iloc[-1]})
            w_df = pd.DataFrame(w_data)
            atr_14_weekly = compute_atr(w_df, 14)

    # Price levels
    week_52_high = float(max(highs[-252:])) if len(highs) >= 252 else float(max(highs))
    week_52_low = float(min(lows[-252:])) if len(lows) >= 252 else float(min(lows))
    month_3_high = float(max(highs[-63:])) if len(highs) >= 63 else float(max(highs))
    month_3_low = float(min(lows[-63:])) if len(lows) >= 63 else float(min(lows))
    month_1_high = float(max(highs[-21:])) if len(highs) >= 21 else float(max(highs))
    month_1_low = float(min(lows[-21:])) if len(lows) >= 21 else float(min(lows))
    all_time_high = week_52_high  # best available from 1Y data
    pct_below_ath = round((1 - ltp / all_time_high) * 100, 2) if all_time_high > 0 else 0

    # Technical structure
    sup_res = compute_support_resistance(hist_df)
    support_levels = sup_res.get("support_levels", [])[:5] if sup_res else []
    resistance_levels = sup_res.get("resistance_levels", [])[:5] if sup_res else []
    fib = compute_fibonacci_levels(hist_df)
    fib_retracements = fib.get("levels", {}) if fib else {}
    pivots = compute_pivot_points(hist_df)
    pivot_classic = pivots if pivots else {}
    cam = _compute_camarilla_pivots(highs[-1], lows[-1], closes[-1]) if closes else {}
    demand_zones, supply_zones = _compute_demand_supply_zones(hist_df)
    nearest_support = max([s for s in support_levels if s < ltp], default=ltp * 0.95)
    nearest_resistance = min([r for r in resistance_levels if r > ltp], default=ltp * 1.05)

    # Multi-timeframe trend
    trend_daily = _compute_trend(closes, 20, 50)
    trend_weekly = _compute_trend(closes[-252:], 10, 26) if len(closes) >= 60 else "sideways"
    trend_monthly = _compute_trend(closes, 50, 100) if len(closes) >= 120 else "sideways"
    if trend_daily == "up" and trend_weekly == "up" and trend_monthly == "up":
        trend_alignment = "bullish"
    elif trend_daily == "down" and trend_weekly == "down" and trend_monthly == "down":
        trend_alignment = "bearish"
    else:
        trend_alignment = "mixed"

    ema_50_daily = compute_ema(pd.Series(closes), 50)
    ema_200_daily = compute_ema(pd.Series(closes), 200)
    pct_above_200dma = round((ltp / ema_200_daily - 1) * 100, 2) if ema_200_daily and ema_200_daily > 0 else None
    supertrend_signal = _compute_supertrend_signal(highs, lows, closes)
    adx_14_daily = compute_adx(hist_df, 14)
    rsi_14_daily = compute_rsi(pd.Series(closes), 14)
    macd_result = compute_macd(pd.Series(closes))
    macd_histogram_daily = macd_result.get("histogram") if macd_result else None

    # Volume & Delivery
    obv_result = compute_obv(hist_df)
    obv_trend = obv_result.get("trend", "neutral") if obv_result else "neutral"
    avg_volume_20d = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))

    # Regime
    india_vix = await _get_india_vix()
    regime_result = regime_classify(india_vix=india_vix or 15, realized_vol=hv_20d, adx=adx_14_daily)
    regime_label = regime_result.get("regime_label", "NormalVolRange") if regime_result else "NormalVolRange"

    # Fundamental data from DB (already computed by fno_signal_engine)
    fund_doc = await _s.db.fundamental_cache.find_one({"symbol": symbol}, {"_id": 0})
    piotroski_f_score = int(fund_doc.get("piotroski_score", 0)) if fund_doc else None
    beneish_m_score = float(fund_doc.get("beneish_m_score", 0)) if fund_doc and fund_doc.get("beneish_m_score") is not None else None

    # Forensic data from DB
    forensic_doc = await _s.db.forensic_cache.find_one({"symbol": symbol}, {"_id": 0})
    altman_z_score = None
    accrual_ratio = None
    pledging_pct = 0.0
    contingent_liability_flag = False
    if forensic_doc:
        altman_z_score = forensic_doc.get("altman_z_score")
        accrual_ratio = forensic_doc.get("accrual_ratio")
        pledging_pct = float(forensic_doc.get("pledging_pct", 0))
        contingent_liability_flag = bool(forensic_doc.get("contingent_liability_flag", False))

    # Growth metrics
    roic_vs_wacc = None
    roic = None
    wacc = None
    fcf_yield = None
    revenue_cagr_3y = None
    ebitda_margin_latest = None
    ebitda_margin_trend = "stable"
    eps_cagr_3y = None
    roe = None
    debt_to_mcap_pct = None
    cfo_to_net_profit = None
    net_profit_positive_q1 = None
    net_profit_positive_q2 = None
    net_profit_positive_q3 = None
    market_cap_cr = None
    market_cap_category = "Unknown"

    if fund_doc:
        roe = fund_doc.get("roe")
        roic_data = fund_doc.get("roic_vs_wacc")
        if isinstance(roic_data, dict):
            roic = roic_data.get("roic")
            wacc = roic_data.get("wacc")
            roic_vs_wacc = roic_data.get("spread")
        fcf_yield = fund_doc.get("fcf_yield")
        revenue_cagr_3y = fund_doc.get("revenue_cagr_3y") or fund_doc.get("revenue_cagr")
        eps_cagr_3y = fund_doc.get("eps_cagr_3y") or fund_doc.get("eps_growth")
        ebitda_margin_latest = fund_doc.get("ebitda_margin_latest") or fund_doc.get("ebitda_margin")
        ebitda_margin_trend = fund_doc.get("ebitda_margin_trend", "stable")
        debt_to_mcap_pct = fund_doc.get("debt_to_mcap_pct")
        cfo_to_net_profit = fund_doc.get("cfo_to_net_profit")
        net_profit_positive_q1 = fund_doc.get("net_profit_positive_q1")
        net_profit_positive_q2 = fund_doc.get("net_profit_positive_q2")
        net_profit_positive_q3 = fund_doc.get("net_profit_positive_q3")
        market_cap_cr = fund_doc.get("market_cap_cr")
        if market_cap_cr:
            mc = float(market_cap_cr)
            if mc >= 20000:
                market_cap_category = "LargeCap"
            elif mc >= 5000:
                market_cap_category = "MidCap"
            else:
                market_cap_category = "SmallCap"

    # Eligibility gate
    passes_eligibility = True
    eligibility_fail_reason = None
    if ltp <= 0:
        passes_eligibility = False
        eligibility_fail_reason = "LTP is zero or negative"
    elif len(closes) < 30:
        passes_eligibility = False
        eligibility_fail_reason = "Insufficient price history (<30 days)"
    elif avg_volume_20d < 10000:
        passes_eligibility = False
        eligibility_fail_reason = "Low liquidity (avg vol < 10K)"

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "symbol": symbol.upper(),
        "isin": stock_core.get("isin", ""),
        "kite_instrument_token": stock_core.get("instrument_token", 0),
        "sector": stock_core.get("sector", ""),
        "sub_sector": stock_core.get("sub_sector", ""),
        "index_memberships": stock_core.get("index_memberships", []),
        "market_cap_category": market_cap_category,
        "market_cap_cr": market_cap_cr,
        "ltp": round(ltp, 2),
        "as_of_timestamp": now_iso,
        "last_refreshed_at": now_iso,
        "ohlcv_daily_1y": ohlcv_daily_1y,
        "hv_10d": hv_10d,
        "hv_20d": hv_20d,
        "hv_60d": hv_60d,
        "hv_90d": hv_90d,
        "hv_252d": hv_252d,
        "realized_vs_iv_ratio": realized_vs_iv_ratio,
        "iv_rank_52w": iv_rank_52w,
        "atr_14_daily": round(float(atr_14_daily), 2) if atr_14_daily else None,
        "atr_14_weekly": round(float(atr_14_weekly), 2) if atr_14_weekly else None,
        "week_52_high": round(week_52_high, 2),
        "week_52_low": round(week_52_low, 2),
        "month_3_high": round(month_3_high, 2),
        "month_3_low": round(month_3_low, 2),
        "month_1_high": round(month_1_high, 2),
        "month_1_low": round(month_1_low, 2),
        "all_time_high": round(all_time_high, 2),
        "all_time_high_date": None,
        "pct_below_ath": pct_below_ath,
        "ipo_price": None,
        "support_levels": [round(s, 2) for s in support_levels],
        "resistance_levels": [round(r, 2) for r in resistance_levels],
        "fib_retracements": {k: round(v, 2) for k, v in fib_retracements.items()} if isinstance(fib_retracements, dict) else {},
        "pivot_classic": {k: round(v, 2) for k, v in pivot_classic.items() if isinstance(v, (int, float))} if pivot_classic else {},
        "pivot_camarilla": cam,
        "demand_zones": demand_zones,
        "supply_zones": supply_zones,
        "nearest_support": round(nearest_support, 2),
        "nearest_resistance": round(nearest_resistance, 2),
        "trend_monthly": trend_monthly,
        "trend_weekly": trend_weekly,
        "trend_daily": trend_daily,
        "trend_alignment": trend_alignment,
        "ema_50_daily": round(float(ema_50_daily), 2) if ema_50_daily else None,
        "ema_200_daily": round(float(ema_200_daily), 2) if ema_200_daily else None,
        "pct_above_200dma": pct_above_200dma,
        "supertrend_signal": supertrend_signal,
        "adx_14_daily": round(float(adx_14_daily), 2) if adx_14_daily else None,
        "rsi_14_daily": round(float(rsi_14_daily), 2) if rsi_14_daily else None,
        "macd_histogram_daily": round(float(macd_histogram_daily), 4) if macd_histogram_daily else None,
        "obv_trend": obv_trend,
        "avg_volume_20d": round(avg_volume_20d, 0),
        "delivery_pct_trend": "flat",
        "regime_label": regime_label,
        "sector_regime_label": regime_label,
        "piotroski_f_score": piotroski_f_score,
        "beneish_m_score": beneish_m_score,
        "altman_z_score": altman_z_score,
        "accrual_ratio": accrual_ratio,
        "cfo_to_net_profit": cfo_to_net_profit,
        "pledging_pct": pledging_pct,
        "contingent_liability_flag": contingent_liability_flag,
        "revenue_cagr_3y": revenue_cagr_3y,
        "ebitda_margin_latest": ebitda_margin_latest,
        "ebitda_margin_trend": ebitda_margin_trend,
        "eps_cagr_3y": eps_cagr_3y,
        "roe": roe,
        "roic": roic,
        "wacc": wacc,
        "roic_vs_wacc": roic_vs_wacc,
        "fcf_yield": fcf_yield,
        "debt_to_mcap_pct": debt_to_mcap_pct,
        "net_profit_positive_q1": net_profit_positive_q1,
        "net_profit_positive_q2": net_profit_positive_q2,
        "net_profit_positive_q3": net_profit_positive_q3,
        "macro_tailwind_sectors": [],
        "macro_headwind_sectors": [],
        "pli_beneficiary": False,
        "govt_capex_beneficiary": False,
        "passes_eligibility": passes_eligibility,
        "eligibility_fail_reason": eligibility_fail_reason,
    }


async def refresh_symbol(symbol: str) -> dict | None:
    """Build and upsert cache document for a single symbol."""
    _s = _srv()
    doc = await _build_cache_document(symbol)
    if doc is None:
        return None
    await _s.db[CACHE_COLLECTION].update_one(
        {"symbol": symbol.upper()},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def refresh_universe(symbols: list[str], concurrency: int = 5) -> int:
    """Batch refresh cache for a list of symbols. Returns count of successful refreshes."""
    sem = asyncio.Semaphore(concurrency)
    count = 0

    async def _refresh_one(sym: str):
        nonlocal count
        async with sem:
            try:
                result = await refresh_symbol(sym)
                if result:
                    count += 1
            except Exception as exc:
                logger.warning("Cache refresh failed for %s: %s", sym, exc)

    await asyncio.gather(*[_refresh_one(s) for s in symbols])
    logger.info("equity_master_cache refreshed: %d/%d symbols", count, len(symbols))
    return count
