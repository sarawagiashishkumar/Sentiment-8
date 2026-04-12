"""
F&O Utility Functions — Pure helpers for signal building.

Extracted from fno_signal_engine.py for modularity.
Contains: _format_script, _compute_report_from_rows,
          _infer_stock_option_type, _analyze_micro_dip_prediction
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from models import IndexAnalysisReport, StockCoreNormalized

logger = logging.getLogger(__name__)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _srv():
    """Lazy import server module for DB/API access."""
    import server
    return server

def _format_script(underlying: str, expiry: str, strike: float, option_type: str) -> str:
    date_obj = datetime.strptime(expiry, "%Y-%m-%d")
    return f"{underlying}{date_obj.strftime('%d%b').upper()}{int(strike)}{option_type}"


def _compute_report_from_rows(
    index_name: Literal["NIFTY", "BANKNIFTY"],
    weight_source: list[tuple[str, float]],
    rows: list[StockCoreNormalized],
    weighted: bool,
) -> IndexAnalysisReport:

    contributions: list[tuple[str, float]] = []
    bullish_count = 0
    total_weight = 0.0
    total_momentum = 0.0
    for idx, stock in enumerate(rows):
        day_change = 0.0
        if stock.ltp is not None and stock.prev_close is not None and stock.prev_close > 0:
            day_change = ((stock.ltp - stock.prev_close) / stock.prev_close) * 100

        if day_change > 0:
            bullish_count += 1

        weight = weight_source[idx][1] if weighted else 1.0
        total_weight += weight
        total_momentum += day_change * weight
        contributions.append((stock.symbol, day_change * weight))

    breadth_score = round((bullish_count / max(len(rows), 1)) * 100, 2)
    weighted_change = total_momentum / max(total_weight, 1)
    momentum_score = round(clamp(50 + (weighted_change * 8), 0, 100), 2)

    if momentum_score >= 58:
        bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif momentum_score <= 42:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    top_contributors = [f"{sym}:{round(val, 2)}" for sym, val in sorted(contributions, key=lambda x: abs(x[1]), reverse=True)[:3]]
    mode_text = "weighted constituent" if weighted else "equal constituent"

    return IndexAnalysisReport(
        report_type="with_consolidated" if weighted else "without_consolidated",
        breadth_score=breadth_score,
        momentum_score=momentum_score,
        bias=bias,
        top_contributors=top_contributors,
        summary=(
            f"{index_name} {mode_text} analysis: breadth {breadth_score} and momentum {momentum_score} suggests {bias.lower()} bias."
        ),
    )



def _infer_stock_option_type(core: StockCoreNormalized) -> Literal["CE", "PE"] | None:
    _srv_mod = _srv()
    if core.ltp is None:
        return None
    pos = _srv_mod._position_in_range(core.ltp, core.year_low, core.year_high)
    day_change_pct = (
        ((core.ltp - core.prev_close) / core.prev_close) * 100
        if core.prev_close is not None and core.prev_close > 0
        else 0.0
    )
    intraday_change_pct = (
        ((core.ltp - core.open) / core.open) * 100
        if core.open is not None and core.open > 0
        else 0.0
    )

    bias_score = (0.65 * day_change_pct) + (0.35 * intraday_change_pct)
    if pos is not None:
        bias_score += (pos - 0.5) * 1.2

    if bias_score >= 0.15:
        return "CE"
    if bias_score <= -0.15:
        return "PE"
    return None


def _analyze_micro_dip_prediction(candles: list[dict], current_ltp: float) -> dict:
    """
    Analyze 1-min candles to predict if a micro-dip is imminent.
    Returns: {
        'dip_expected': bool,
        'predicted_dip_price': float,
        'confidence': float (0-1),
        'reason': str
    }
    """
    if not candles or len(candles) < 5:
        return {
            "dip_expected": False,
            "predicted_dip_price": current_ltp,
            "confidence": 0.0,
            "reason": "Insufficient candle data",
        }

    recent_candles = candles[-5:]
    
    closes = [c["close"] for c in recent_candles]
    volumes = [c["volume"] for c in recent_candles]
    lows = [c["low"] for c in recent_candles]
    
    avg_volume = sum(volumes) / len(volumes)
    latest_volume = volumes[-1]
    recent_low = min(lows[-3:])
    
    price_momentum = (closes[-1] - closes[0]) / max(closes[0], 0.01)
    volume_spike = latest_volume / max(avg_volume, 1)
    
    distance_to_recent_low = ((current_ltp - recent_low) / max(current_ltp, 0.01)) * 100
    
    dip_indicators = []
    confidence_score = 0.0
    
    if price_momentum < -0.01:
        dip_indicators.append("DownwardMomentum")
        confidence_score += 0.25
    
    if volume_spike > 1.5:
        dip_indicators.append("VolumeSpike")
        confidence_score += 0.20
    
    if distance_to_recent_low > 2.0:
        dip_indicators.append("AboveRecentLow")
        confidence_score += 0.15
    
    consecutive_red = sum(1 for i in range(1, len(recent_candles)) if recent_candles[i]["close"] < recent_candles[i]["open"])
    if consecutive_red >= 3:
        dip_indicators.append(f"ConsecutiveRed={consecutive_red}")
        confidence_score += 0.25
    
    last_3_range = max(lows[-3:]) - min(lows[-3:])
    volatility_pct = (last_3_range / max(current_ltp, 0.01)) * 100
    if volatility_pct > 3.0:
        dip_indicators.append(f"HighVolatility={volatility_pct:.1f}%")
        confidence_score += 0.15
    
    dip_expected = confidence_score >= 0.35
    
    if dip_expected:
        dip_depth_pct = min(0.05 + (confidence_score - 0.35) * 0.15, 0.08)
        predicted_dip = current_ltp * (1 - dip_depth_pct)
        
        predicted_dip = max(predicted_dip, recent_low * 0.98)
    else:
        predicted_dip = current_ltp * 0.995
    
    return {
        "dip_expected": dip_expected,
        "predicted_dip_price": round(predicted_dip, 2),
        "confidence": round(min(confidence_score, 1.0), 2),
        "reason": f"Indicators: {', '.join(dip_indicators) if dip_indicators else 'No significant dip signals'}",
    }



# ── Functions with server.py dependencies (lazy import) ─────────────────────────
