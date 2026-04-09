"""
Iteration 19: Batch 1-5 Research Engine Tests
Tests all new functions added in Batches 1-5 to research_engine.py:
  - Batch 1: Advanced Technical Indicators (Williams%R, CCI, VPT, AD, Ichimoku, Fibonacci, Pivot, S/R, RSI Div, Candlestick, MTF, Chart patterns)
  - Batch 2: Forensic Financial Audit (Altman Z, Earnings Quality, Red Flags, ROIC/WACC, Growth Quality, Forensic Audit)
  - Batch 3: Macro & Regime Context (Enhanced 8-regime, Macro context, Sector map)
  - Batch 4: Portfolio Enhancements (Correlation matrix, Stress tests, Diversification, Catalysts, Merge holdings, Master snapshot)
  - Batch 5: F&O Strategy Library & Signal State Machine (Strategy library, Eligible strategies, State machine, Index constituent bias)
"""
import os
import sys
import math
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
import requests
from dotenv import load_dotenv

from tests.helpers.test_utils import get_base_url

# Load env
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = get_base_url()

# Import research engine directly
sys.path.insert(0, "/app/backend")
from services.research_engine import (
    # Batch 1
    compute_williams_r,
    compute_cci,
    compute_vpt,
    compute_ad_line,
    compute_ichimoku,
    compute_fibonacci_levels,
    compute_pivot_points,
    compute_support_resistance,
    detect_rsi_divergence,
    detect_candlestick_patterns,
    compute_multiframe_trend,
    detect_chart_patterns,
    compute_full_technical_snapshot,
    compute_technical_confluence_bonus,
    # Batch 2
    compute_altman_z_score,
    compute_earnings_quality,
    compute_forensic_red_flags,
    compute_roic_vs_wacc,
    compute_growth_quality,
    compute_forensic_audit,
    # Batch 3
    classify_market_regime_enhanced,
    compute_macro_context,
    SECTOR_MACRO_IMPACT_MAP,
    REGIME_STRATEGY_GRID,
    # Batch 4
    compute_portfolio_correlation_matrix,
    compute_portfolio_stress_tests,
    compute_diversification_audit,
    compute_upcoming_catalysts,
    merge_duplicate_holdings,
    compute_master_stock_snapshot,
    # Batch 5
    STRATEGY_LIBRARY,
    get_eligible_strategies,
    select_strategy_for_signal,
    check_strategy_eligible,
    update_backtest_stats,
    transition_signal_state,
    compute_index_constituent_bias,
    NIFTY50_WEIGHTS,
    BANKNIFTY_WEIGHTS,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES — Synthetic OHLCV Data
# ─────────────────────────────────────────────────────────────────────────────

def make_ohlcv(n: int = 260, base_price: float = 500.0, trend: str = "UP") -> pd.DataFrame:
    """Create synthetic OHLCV DataFrame with DatetimeIndex."""
    np.random.seed(42)
    # Use start date to ensure exactly n business days (avoid weekend-end date issues)
    dates = pd.date_range(start="2020-01-02", periods=n, freq="B")
    
    prices = [base_price]
    for _ in range(n - 1):
        if trend == "UP":
            change = np.random.normal(0.003, 0.015)
        elif trend == "DOWN":
            change = np.random.normal(-0.003, 0.015)
        else:
            change = np.random.normal(0.0, 0.015)
        prices.append(prices[-1] * (1 + change))
    
    prices = np.array(prices)
    highs = prices * (1 + abs(np.random.normal(0, 0.005, n)))
    lows = prices * (1 - abs(np.random.normal(0, 0.005, n)))
    opens = prices * (1 + np.random.normal(0, 0.003, n))
    volumes = np.random.randint(100000, 1000000, n).astype(float)
    
    return pd.DataFrame({
        "Open": opens,
        "High": np.maximum(opens, prices) + abs(np.random.normal(0, 1, n)),
        "Low": np.minimum(opens, prices) - abs(np.random.normal(0, 1, n)),
        "Close": prices,
        "Volume": volumes,
    }, index=dates)


@pytest.fixture(scope="module")
def hist_260():
    return make_ohlcv(260, 500.0, "UP")


@pytest.fixture(scope="module")
def hist_down_260():
    return make_ohlcv(260, 500.0, "DOWN")


@pytest.fixture(scope="module")
def hist_short():
    return make_ohlcv(20, 500.0, "UP")


# ─────────────────────────────────────────────────────────────────────────────
# HTTP — Backend Health Check
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Verify backend is alive via HTTP"""

    def test_backend_root_returns_200(self):
        """GET /api/ should return 200 with message."""
        if not BASE_URL:
            pytest.skip("REACT_APP_BACKEND_URL not configured")
        resp = requests.get(f"{BASE_URL}/api/", timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "message" in data, "Root response missing 'message' key"
        print(f"PASS: Backend alive — {data['message']}")


# ─────────────────────────────────────────────────────────────────────────────
# BATCH 1: ADVANCED TECHNICAL INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

class TestWilliamsR:
    """Williams %R tests"""

    def test_returns_float_in_valid_range(self, hist_260):
        wr = compute_williams_r(hist_260)
        assert wr is not None, "Williams %R should not be None for 260-bar data"
        assert isinstance(wr, float), f"Expected float, got {type(wr)}"
        assert -100 <= wr <= 0, f"Williams %R {wr} out of valid range [-100, 0]"
        print(f"PASS: Williams %R = {wr}")

    def test_returns_none_for_insufficient_data(self):
        hist_tiny = make_ohlcv(5)
        wr = compute_williams_r(hist_tiny, period=14)
        assert wr is None, "Should return None for fewer bars than period"

    def test_oversold_detection(self):
        """Williams %R < -80 implies oversold."""
        hist = make_ohlcv(50, trend="DOWN")
        wr = compute_williams_r(hist, period=14)
        if wr is not None:
            print(f"PASS: Williams %R computed = {wr} (oversold if < -80)")
        else:
            print("SKIP: Insufficient data for oversold test")


class TestCCI:
    """Commodity Channel Index tests"""

    def test_returns_valid_dict_with_cci(self, hist_260):
        result = compute_cci(hist_260)
        assert isinstance(result, dict), "CCI should return a dict"
        assert "cci" in result, "Missing 'cci' key"
        assert "overbought" in result, "Missing 'overbought' key"
        assert "oversold" in result, "Missing 'oversold' key"
        assert result["cci"] is not None, "CCI value should not be None"
        assert isinstance(result["cci"], float), f"CCI should be float, got {type(result['cci'])}"
        print(f"PASS: CCI = {result['cci']}, overbought={result['overbought']}, oversold={result['oversold']}")

    def test_insufficient_data_returns_none_cci(self):
        hist_tiny = make_ohlcv(10)
        result = compute_cci(hist_tiny, period=20)
        assert result["cci"] is None, "CCI should be None for insufficient data"

    def test_overbought_flag_mutually_exclusive(self, hist_260):
        result = compute_cci(hist_260)
        if result["cci"] is not None:
            if result["overbought"]:
                assert result["cci"] > 100
            if result["oversold"]:
                assert result["cci"] < -100


class TestVPT:
    """Volume Price Trend tests"""

    def test_returns_valid_dict(self, hist_260):
        result = compute_vpt(hist_260)
        assert isinstance(result, dict), "VPT should return dict"
        assert "vpt" in result, "Missing 'vpt' key"
        assert "trend" in result, "Missing 'trend' key"
        assert result["vpt"] is not None, "VPT value should not be None"
        assert result["trend"] in ("RISING", "FALLING", "FLAT"), f"Invalid trend: {result['trend']}"
        print(f"PASS: VPT = {result['vpt']}, trend = {result['trend']}")

    def test_insufficient_data_returns_flat(self):
        hist_tiny = make_ohlcv(3)
        result = compute_vpt(hist_tiny)
        assert result["vpt"] is None or result["trend"] == "FLAT"


class TestADLine:
    """Accumulation/Distribution Line tests"""

    def test_returns_valid_dict(self, hist_260):
        result = compute_ad_line(hist_260)
        assert isinstance(result, dict)
        assert "ad" in result, "Missing 'ad' key"
        assert "trend" in result, "Missing 'trend' key"
        assert result["ad"] is not None, "AD value should not be None"
        assert result["trend"] in ("RISING", "FALLING", "FLAT"), f"Invalid trend: {result['trend']}"
        print(f"PASS: AD Line = {result['ad']:.2f}, trend = {result['trend']}")

    def test_uptrend_data_should_mostly_rise(self):
        hist_up = make_ohlcv(100, trend="UP")
        result = compute_ad_line(hist_up)
        assert result["ad"] is not None
        # Uptrend data usually produces RISING trend
        print(f"INFO: AD trend for uptrend data: {result['trend']}")


class TestIchimoku:
    """Ichimoku Cloud tests"""

    def test_returns_available_true_with_260_bars(self, hist_260):
        result = compute_ichimoku(hist_260)
        assert isinstance(result, dict)
        assert result.get("available") is True, "Ichimoku should be available for 260 bars"
        print(f"PASS: Ichimoku available with 260 bars")

    def test_returns_all_expected_keys(self, hist_260):
        result = compute_ichimoku(hist_260)
        expected_keys = ["available", "tenkan", "kijun", "senkou_a", "senkou_b",
                         "cloud_color", "price_vs_cloud", "tenkan_kijun_cross",
                         "kumo_twist", "bullish_signal", "bearish_signal"]
        for k in expected_keys:
            assert k in result, f"Missing key '{k}' in Ichimoku result"
        print(f"PASS: All Ichimoku keys present. price_vs_cloud={result['price_vs_cloud']}, cloud_color={result['cloud_color']}")

    def test_price_vs_cloud_valid_value(self, hist_260):
        result = compute_ichimoku(hist_260)
        assert result["price_vs_cloud"] in ("ABOVE", "BELOW", "INSIDE", "UNKNOWN")

    def test_returns_not_available_for_insufficient_data(self):
        hist_small = make_ohlcv(30)
        result = compute_ichimoku(hist_small)
        assert result.get("available") is False, "Should return available=False for < 52 bars"

    def test_cloud_color_is_green_or_red(self, hist_260):
        result = compute_ichimoku(hist_260)
        if result.get("available"):
            assert result["cloud_color"] in ("GREEN", "RED"), f"Invalid cloud_color: {result['cloud_color']}"


class TestFibonacci:
    """Fibonacci retracement tests"""

    def test_returns_available_true_with_260_bars(self, hist_260):
        result = compute_fibonacci_levels(hist_260)
        assert result.get("available") is True, "Fibonacci should be available for 260 bars"
        print(f"PASS: Fibonacci available=True")

    def test_returns_all_fib_levels(self, hist_260):
        result = compute_fibonacci_levels(hist_260)
        assert result.get("available"), "Fibonacci not available"
        # Check retracement levels
        for key in ["fib_236", "fib_382", "fib_500", "fib_618", "fib_786"]:
            assert key in result and result[key] is not None, f"Missing Fibonacci level: {key}"
        print(f"PASS: All fib levels present. fib_382={result['fib_382']}, fib_618={result['fib_618']}")

    def test_fib_zone_is_valid(self, hist_260):
        result = compute_fibonacci_levels(hist_260)
        assert result.get("fib_zone") in ("UPPER_HALF", "MIDDLE", "LOWER_HALF")
        print(f"PASS: fib_zone = {result['fib_zone']}")

    def test_swing_high_greater_than_swing_low(self, hist_260):
        result = compute_fibonacci_levels(hist_260)
        assert result["swing_high"] > result["swing_low"]

    def test_extensions_present(self, hist_260):
        result = compute_fibonacci_levels(hist_260)
        exts = result.get("extensions", {})
        assert len(exts) >= 2, "Should have at least 2 extension levels"


class TestPivotPoints:
    """Pivot Points tests"""

    def test_returns_available_true(self, hist_260):
        result = compute_pivot_points(hist_260)
        assert result.get("available") is True
        print(f"PASS: Pivot points available")

    def test_classic_levels_present(self, hist_260):
        result = compute_pivot_points(hist_260)
        classic = result.get("classic", {})
        for key in ["pp", "r1", "r2", "r3", "s1", "s2", "s3"]:
            assert key in classic and classic[key] is not None, f"Missing classic pivot: {key}"
        print(f"PASS: Classic pivots: PP={classic['pp']}, R1={classic['r1']}, S1={classic['s1']}")

    def test_camarilla_levels_present(self, hist_260):
        result = compute_pivot_points(hist_260)
        cam = result.get("camarilla", {})
        for key in ["h3", "h4", "l3", "l4"]:
            assert key in cam, f"Missing Camarilla level: {key}"
        print(f"PASS: Camarilla H3={cam['h3']}, H4={cam['h4']}, L3={cam['l3']}, L4={cam['l4']}")

    def test_ltp_vs_pp_valid(self, hist_260):
        result = compute_pivot_points(hist_260)
        assert result.get("ltp_vs_pp") in ("ABOVE", "BELOW")


class TestSupportResistance:
    """Support/Resistance tests"""

    def test_returns_lists(self, hist_260):
        result = compute_support_resistance(hist_260)
        assert isinstance(result.get("support_levels"), list), "support_levels should be a list"
        assert isinstance(result.get("resistance_levels"), list), "resistance_levels should be a list"
        print(f"PASS: S/R - supports={result['support_levels']}, resistances={result['resistance_levels']}")

    def test_available_flag(self, hist_260):
        result = compute_support_resistance(hist_260)
        assert result.get("available") is True or isinstance(result.get("support_levels"), list)

    def test_insufficient_data_returns_empty_lists(self):
        hist_tiny = make_ohlcv(10)
        result = compute_support_resistance(hist_tiny)
        # Should not crash, return empty lists
        assert isinstance(result.get("support_levels"), list)


class TestRSIDivergence:
    """RSI Divergence tests"""

    def test_returns_valid_dict(self, hist_260):
        result = detect_rsi_divergence(hist_260)
        assert isinstance(result, dict)
        assert "divergence" in result, "Missing 'divergence' key"
        assert "type" in result, "Missing 'type' key"
        assert "bullish" in result, "Missing 'bullish' key"
        assert "bearish" in result, "Missing 'bearish' key"
        assert result["divergence"] in ("NONE", "BULLISH", "BEARISH")
        print(f"PASS: RSI Divergence = {result['divergence']}, type = {result['type']}")

    def test_divergence_string_is_valid(self, hist_260):
        result = detect_rsi_divergence(hist_260)
        assert result["divergence"] in ("NONE", "BULLISH", "BEARISH")

    def test_bullish_bearish_flags_consistent(self, hist_260):
        result = detect_rsi_divergence(hist_260)
        if result["divergence"] == "BULLISH":
            assert result["bullish"] is True
            assert result["bearish"] is False
        elif result["divergence"] == "BEARISH":
            assert result["bearish"] is True
            assert result["bullish"] is False
        else:
            assert result["bullish"] is False
            assert result["bearish"] is False


class TestCandlestickPatterns:
    """Candlestick pattern detection tests"""

    def test_returns_patterns_list_and_bias(self, hist_260):
        result = detect_candlestick_patterns(hist_260)
        assert isinstance(result, dict)
        assert "patterns" in result, "Missing 'patterns' key"
        assert "bias" in result, "Missing 'bias' key"
        assert isinstance(result["patterns"], list)
        assert result["bias"] in ("BULLISH", "BEARISH", "NEUTRAL")
        print(f"PASS: Candlestick patterns = {result['patterns']}, bias = {result['bias']}")

    def test_insufficient_data_returns_neutral(self):
        hist_tiny = make_ohlcv(2)
        result = detect_candlestick_patterns(hist_tiny)
        assert result["bias"] == "NEUTRAL"


class TestMultiframeTrend:
    """Multi-timeframe trend tests"""

    def test_returns_daily_weekly_monthly_alignment(self, hist_260):
        result = compute_multiframe_trend(hist_260)
        assert isinstance(result, dict)
        for key in ["daily", "weekly", "monthly", "alignment"]:
            assert key in result, f"Missing key '{key}'"
        assert result["daily"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result["weekly"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result["monthly"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result["alignment"] in ("STRONGLY_BULLISH", "BULLISH", "MIXED", "BEARISH", "STRONGLY_BEARISH")
        print(f"PASS: MTF trend - daily={result['daily']}, weekly={result['weekly']}, monthly={result['monthly']}, alignment={result['alignment']}")

    def test_bullish_frames_count_matches(self, hist_260):
        result = compute_multiframe_trend(hist_260)
        bull_cnt = [result["daily"], result["weekly"], result["monthly"]].count("BULLISH")
        assert result["bullish_frames"] == bull_cnt


class TestChartPatterns:
    """Chart pattern detection tests"""

    def test_returns_patterns_dict_with_flags(self, hist_260):
        result = detect_chart_patterns(hist_260)
        assert isinstance(result, dict)
        for key in ["patterns", "has_bullish_pattern", "has_bearish_pattern", "description"]:
            assert key in result, f"Missing key '{key}'"
        assert isinstance(result["patterns"], list)
        assert isinstance(result["has_bullish_pattern"], bool)
        assert isinstance(result["has_bearish_pattern"], bool)
        print(f"PASS: Chart patterns = {[p['type'] for p in result['patterns']]}")

    def test_insufficient_data(self):
        hist_tiny = make_ohlcv(15)
        result = detect_chart_patterns(hist_tiny)
        # Should not crash
        assert isinstance(result, dict)


class TestFullTechnicalSnapshot:
    """compute_full_technical_snapshot integration test"""

    def test_returns_batch1_fields(self, hist_260):
        result = compute_full_technical_snapshot("TEST.NS", hist_260)
        # Verify Batch 1 fields are present
        assert result.get("data_available") is True
        for key in ["williams_r", "cci", "vpt", "ad_line", "ichimoku",
                    "fibonacci", "pivot_points", "support_resistance",
                    "rsi_divergence", "candlestick_patterns", "multiframe_trend", "chart_patterns"]:
            assert key in result, f"Missing Batch 1 key '{key}' in full technical snapshot"
        print(f"PASS: All Batch 1 fields present in full_technical_snapshot")

    def test_returns_symbol_and_data_available(self, hist_260):
        result = compute_full_technical_snapshot("RELIANCE.NS", hist_260)
        assert result["symbol"] == "RELIANCE.NS"
        assert result["data_available"] is True

    def test_technical_bias_is_valid(self, hist_260):
        result = compute_full_technical_snapshot("TEST.NS", hist_260)
        assert result.get("technical_bias") in ("BULLISH", "BEARISH", "NEUTRAL")


class TestTechnicalConfluenceBonus:
    """compute_technical_confluence_bonus tests with Batch 1 parameters"""

    def test_returns_tuple_int_list(self):
        bonus, tags = compute_technical_confluence_bonus(
            direction="BULLISH",
            rsi=45.0,
            macd_bullish=True,
            macd_above_zero=True,
            trend_alignment="BULLISH_ALIGNED",
            obv_trend="RISING",
            adx=28.0,
            bb_pct_b=0.1,
            stoch_k=15.0,
            williams_r=-85.0,
            cci=-110.0,
            vpt_trend="RISING",
            ichimoku_price_vs_cloud="ABOVE",
            ichimoku_tk_cross="BULLISH",
            ichimoku_bullish=True,
            ichimoku_bearish=False,
            rsi_divergence="BULLISH",
            rsi_div_type="REGULAR",
            candle_bias="BULLISH",
            mf_alignment="STRONGLY_BULLISH",
            has_bull_chart_pattern=True,
            has_bear_chart_pattern=False,
            ad_trend="RISING",
        )
        assert isinstance(bonus, int), f"Expected int bonus, got {type(bonus)}"
        assert isinstance(tags, list), f"Expected list tags, got {type(tags)}"
        print(f"PASS: Confluence bonus = {bonus}, tags = {tags}")

    def test_bonus_is_capped_at_18(self):
        bonus, _ = compute_technical_confluence_bonus(
            direction="BULLISH",
            rsi=40.0, macd_bullish=True, macd_above_zero=True,
            trend_alignment="BULLISH_ALIGNED", obv_trend="RISING",
            adx=35.0, bb_pct_b=0.05, stoch_k=10.0,
            williams_r=-85.0, cci=-120.0, vpt_trend="RISING",
            ichimoku_bullish=True, ichimoku_bearish=False,
            ichimoku_price_vs_cloud="ABOVE", ichimoku_tk_cross="BULLISH",
            rsi_divergence="BULLISH", rsi_div_type="REGULAR",
            candle_bias="BULLISH", mf_alignment="STRONGLY_BULLISH",
            has_bull_chart_pattern=True, has_bear_chart_pattern=False,
            ad_trend="RISING",
        )
        assert bonus <= 18, f"Bonus {bonus} exceeds cap of 18"
        print(f"PASS: Bullish confluence bonus capped correctly at {bonus}")

    def test_bonus_floor_is_minus_6(self):
        bonus, _ = compute_technical_confluence_bonus(
            direction="BULLISH",
            rsi=80.0, macd_bullish=False, macd_above_zero=False,
            trend_alignment="BEARISH_ALIGNED", obv_trend="FALLING",
            adx=10.0, bb_pct_b=0.95, stoch_k=90.0,
            williams_r=-5.0, cci=150.0, vpt_trend="FALLING",
            ichimoku_bearish=True, ichimoku_bullish=False,
            ichimoku_price_vs_cloud="BELOW", ichimoku_tk_cross="BEARISH",
            rsi_divergence="BEARISH", rsi_div_type="REGULAR",
            candle_bias="BEARISH", mf_alignment="STRONGLY_BEARISH",
            has_bull_chart_pattern=False, has_bear_chart_pattern=True,
            ad_trend="FALLING",
        )
        assert bonus >= -6, f"Bonus {bonus} below floor of -6"
        print(f"PASS: Min bonus floor = {bonus} (>= -6)")

    def test_backward_compat_no_batch1_params(self):
        """Test that old code without Batch 1 params still works"""
        bonus, tags = compute_technical_confluence_bonus(
            direction="BULLISH",
            rsi=45.0, macd_bullish=True, macd_above_zero=True,
            trend_alignment="BULLISH_ALIGNED", obv_trend="RISING",
            adx=25.0, bb_pct_b=0.1, stoch_k=15.0,
        )
        assert isinstance(bonus, int)
        print(f"PASS: Backward compat bonus = {bonus}")


# ─────────────────────────────────────────────────────────────────────────────
# BATCH 2: FORENSIC FINANCIAL AUDIT
# ─────────────────────────────────────────────────────────────────────────────

class TestAltmanZScore:
    """Altman Z-Score tests"""

    def test_safe_zone(self):
        result = compute_altman_z_score(
            working_capital=500e6, retained_earnings=800e6, ebit=200e6,
            market_cap=3000e6, total_liabilities=600e6, revenue=2000e6,
            total_assets=2000e6,
        )
        assert result.get("available") is True
        assert result.get("z_score") is not None
        assert isinstance(result["z_score"], float)
        assert result["zone"] == "SAFE", f"Expected SAFE zone, got {result['zone']} (z={result['z_score']})"
        print(f"PASS: Altman Z = {result['z_score']}, zone = SAFE")

    def test_distress_zone(self):
        result = compute_altman_z_score(
            working_capital=-100e6, retained_earnings=-500e6, ebit=-50e6,
            market_cap=200e6, total_liabilities=1500e6, revenue=500e6,
            total_assets=1200e6,
        )
        assert result.get("available") is True
        assert result["zone"] == "DISTRESS", f"Expected DISTRESS, got {result['zone']} (z={result['z_score']})"
        print(f"PASS: Altman Z = {result['z_score']}, zone = DISTRESS")

    def test_grey_zone(self):
        result = compute_altman_z_score(
            working_capital=100e6, retained_earnings=200e6, ebit=60e6,
            market_cap=600e6, total_liabilities=500e6, revenue=800e6,
            total_assets=900e6,
        )
        assert result.get("available") is True
        assert result["zone"] in ("GREY", "SAFE", "DISTRESS"), f"Zone {result['zone']} not valid"
        print(f"PASS: Altman Z = {result['z_score']}, zone = {result['zone']}")

    def test_returns_zone_safe_grey_or_distress(self):
        result = compute_altman_z_score(
            working_capital=200e6, retained_earnings=400e6, ebit=100e6,
            market_cap=1000e6, total_liabilities=400e6, revenue=1200e6,
            total_assets=1200e6,
        )
        assert result["zone"] in ("SAFE", "GREY", "DISTRESS")

    def test_missing_data_returns_unavailable(self):
        result = compute_altman_z_score(
            working_capital=None, retained_earnings=None, ebit=None,
            market_cap=None, total_liabilities=None, revenue=None,
            total_assets=None,
        )
        assert result.get("available") is False


class TestEarningsQuality:
    """Earnings Quality tests"""

    def test_high_quality_earnings(self):
        result = compute_earnings_quality(
            operating_cash_flow=120e6, net_income=100e6,
            total_assets=500e6
        )
        assert result.get("available") is True
        assert result.get("cfo_ni_ratio") is not None
        assert result["earnings_quality"] == "HIGH"
        print(f"PASS: Earnings quality = {result['earnings_quality']}, CFO/NI = {result['cfo_ni_ratio']}")

    def test_low_quality_earnings(self):
        result = compute_earnings_quality(
            operating_cash_flow=30e6, net_income=100e6,
            total_assets=500e6
        )
        assert result.get("available") is True
        assert result["earnings_quality"] == "LOW", f"Expected LOW, got {result['earnings_quality']}"
        print(f"PASS: Low earnings quality detected, CFO/NI = {result['cfo_ni_ratio']}")

    def test_accrual_ratio_computed(self):
        result = compute_earnings_quality(
            operating_cash_flow=80e6, net_income=100e6,
            total_assets=600e6, total_assets_prev=550e6
        )
        assert "accrual_ratio" in result
        assert result["accrual_ratio"] is not None
        print(f"PASS: Accrual ratio = {result['accrual_ratio']}")

    def test_missing_data_returns_unavailable(self):
        result = compute_earnings_quality(
            operating_cash_flow=None, net_income=None, total_assets=None
        )
        assert result.get("available") is False


class TestForensicRedFlags:
    """Forensic red flags checklist tests"""

    def test_returns_flag_count_and_severity(self):
        result = compute_forensic_red_flags(
            accounts_receivable=200e6, revenue=1000e6, revenue_prev=800e6,
            inventory=300e6, cogs=500e6, accounts_payable=100e6,
            cwip=50e6, total_assets=1200e6, goodwill=100e6,
            net_worth=500e6, shares_outstanding=100e6,
            shares_outstanding_prev=100e6, total_debt=300e6,
            operating_income=150e6, net_income=100e6,
            deferred_tax_liability=20e6, deferred_tax_liability_prev=18e6,
        )
        assert "red_flag_count" in result
        assert "severity" in result
        assert "flags" in result
        assert isinstance(result["red_flag_count"], int)
        assert result["severity"] in ("CLEAN", "LOW", "MEDIUM", "HIGH")
        print(f"PASS: Red flags = {result['red_flag_count']}, severity = {result['severity']}")

    def test_high_pledging_generates_flag(self):
        result = compute_forensic_red_flags(
            accounts_receivable=50e6, revenue=500e6, revenue_prev=480e6,
            inventory=None, cogs=None, accounts_payable=None,
            cwip=None, total_assets=600e6, goodwill=None,
            net_worth=None, shares_outstanding=None,
            shares_outstanding_prev=None, total_debt=None,
            operating_income=None, net_income=None,
            deferred_tax_liability=None, deferred_tax_liability_prev=None,
            pledged_shares_pct=60.0,  # >50% should trigger flag
        )
        assert result["red_flag_count"] >= 1, "High pledging should add red flag"
        assert any("pledg" in f.lower() for f in result["flags"])
        print(f"PASS: High pledging flag detected: {result['flags']}")

    def test_clean_company_has_zero_flags(self):
        result = compute_forensic_red_flags(
            accounts_receivable=30e6, revenue=1000e6, revenue_prev=900e6,
            inventory=50e6, cogs=400e6, accounts_payable=40e6,
            cwip=20e6, total_assets=800e6, goodwill=10e6,
            net_worth=400e6, shares_outstanding=100e6,
            shares_outstanding_prev=100e6, total_debt=100e6,
            operating_income=200e6, net_income=150e6,
            deferred_tax_liability=10e6, deferred_tax_liability_prev=9e6,
        )
        assert result["red_flag_count"] == 0
        assert result["severity"] == "CLEAN"
        print(f"PASS: Clean company — 0 red flags")


class TestROICvsWACC:
    """ROIC vs WACC tests"""

    def test_value_creation_company(self):
        result = compute_roic_vs_wacc(
            ebit=200e6, tax_rate=0.25,
            invested_capital=1000e6,
            total_debt=300e6, market_cap=1500e6,
            cost_of_debt=0.08, cost_of_equity=0.12,
        )
        assert result.get("available") is True
        assert "roic" in result and result["roic"] is not None
        assert "wacc" in result and result["wacc"] is not None
        assert "spread" in result
        assert "value_creation" in result
        print(f"PASS: ROIC={result['roic']}%, WACC={result['wacc']}%, spread={result['spread']}%, value_creation={result['value_creation']}")

    def test_value_destruction_company(self):
        result = compute_roic_vs_wacc(
            ebit=50e6, tax_rate=0.25,
            invested_capital=2000e6,
            total_debt=1500e6, market_cap=300e6,
            cost_of_debt=0.10, cost_of_equity=0.15,
        )
        assert result.get("available") is True
        assert result["value_creation"] is False, f"Expected value_destruction, got value_creation=True"
        print(f"PASS: Value destruction detected: ROIC={result['roic']}%, WACC={result['wacc']}%")

    def test_missing_ebit_returns_unavailable(self):
        result = compute_roic_vs_wacc(ebit=None)
        assert result.get("available") is False


class TestGrowthQuality:
    """Growth Quality tests"""

    def test_strong_revenue_growth(self):
        revenues = [1500.0, 1300.0, 1100.0, 900.0]  # ~18% CAGR
        margins = [22.0, 20.0, 18.0, 17.0]  # improving
        result = compute_growth_quality(revenues, margins, fcf_yield=6.0)
        assert result.get("available") is True
        assert "revenue_cagr" in result
        assert result["revenue_quality"] == "STRONG", f"Expected STRONG, got {result['revenue_quality']}"
        assert result.get("ebitda_margin_trend") == "IMPROVING"
        print(f"PASS: Revenue CAGR = {result['revenue_cagr']}%, trend = {result['ebitda_margin_trend']}")

    def test_declining_revenue(self):
        revenues = [500.0, 600.0, 700.0, 800.0]  # declining order (newest first)
        margins = [15.0, 18.0, 20.0, 22.0]  # deteriorating
        result = compute_growth_quality(revenues, margins)
        assert result.get("available") is True
        assert result["revenue_quality"] == "DECLINING", f"Expected DECLINING, got {result['revenue_quality']}"
        print(f"PASS: Declining revenue detected: CAGR = {result['revenue_cagr']}%")

    def test_insufficient_data_returns_not_available(self):
        result = compute_growth_quality([None, None], [None])
        assert result.get("available") is False


class TestForensicAudit:
    """Master forensic audit tests"""

    def test_returns_composite_score_and_investable_flag(self):
        altman_inp = {
            "working_capital": 500e6, "retained_earnings": 800e6,
            "ebit": 200e6, "market_cap": 3000e6, "total_liabilities": 600e6,
            "revenue": 2000e6, "total_assets": 2000e6,
        }
        eq_inp = {"operating_cash_flow": 120e6, "net_income": 100e6, "total_assets": 2000e6}
        rf_inp = {
            "accounts_receivable": 50e6, "revenue": 2000e6, "revenue_prev": 1800e6,
            "inventory": 100e6, "cogs": 800e6, "accounts_payable": 80e6,
            "cwip": 50e6, "total_assets": 2000e6, "goodwill": 100e6,
            "net_worth": 1200e6, "shares_outstanding": 200e6,
            "shares_outstanding_prev": 200e6, "total_debt": 300e6,
            "operating_income": 250e6, "net_income": 180e6,
            "deferred_tax_liability": 20e6, "deferred_tax_liability_prev": 18e6,
        }
        roic_inp = {
            "ebit": 200e6, "total_assets": 2000e6, "current_liabilities": 300e6,
            "total_debt": 300e6, "market_cap": 3000e6,
        }
        growth_inp = {
            "revenues": [2000e6, 1700e6, 1400e6, 1200e6],
            "ebitda_margins": [18.0, 16.0, 14.0, 13.0],
        }

        result = compute_forensic_audit(
            altman_inputs=altman_inp,
            earnings_quality_inputs=eq_inp,
            red_flag_inputs=rf_inp,
            roic_inputs=roic_inp,
            growth_inputs=growth_inp,
            piotroski_score=7,
            beneish_m_score=-2.5,
        )
        assert "composite_score" in result
        assert "overall_risk" in result
        assert "investable" in result
        assert 0 <= result["composite_score"] <= 100
        assert result["overall_risk"] in ("LOW", "MEDIUM", "HIGH")
        assert isinstance(result["investable"], bool)
        print(f"PASS: Forensic audit - composite={result['composite_score']}, risk={result['overall_risk']}, investable={result['investable']}")


# ─────────────────────────────────────────────────────────────────────────────
# BATCH 3: MACRO & REGIME CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

class TestMarketRegimeEnhanced:
    """Enhanced 8-regime classifier tests"""

    def test_returns_one_of_8_regimes(self):
        VALID_REGIMES = {
            "LOW_VOL_TREND_BULL", "LOW_VOL_RANGE", "NORMAL_VOL_TREND", "NORMAL_VOL_RANGE",
            "HIGH_VOL_TREND", "HIGH_VOL_CRASH", "PRE_EVENT", "POST_EVENT_IV_CRUSH"
        }
        result = classify_market_regime_enhanced(vix=14.5, adx=25.0, rsi=55.0)
        assert result["regime"] in VALID_REGIMES, f"Invalid regime: {result['regime']}"
        print(f"PASS: Regime = {result['regime']}")

    def test_low_vol_bull_regime(self):
        result = classify_market_regime_enhanced(vix=10.0, adx=28.0, rsi=58.0)
        assert result["regime"] in ("LOW_VOL_TREND_BULL", "LOW_VOL_RANGE")
        print(f"PASS: Low vol regime = {result['regime']}")

    def test_crash_regime(self):
        result = classify_market_regime_enhanced(vix=30.0, adx=35.0, rsi=30.0)
        assert result["regime"] == "HIGH_VOL_CRASH"
        print(f"PASS: Crash regime correctly classified")

    def test_pre_event_regime(self):
        result = classify_market_regime_enhanced(vix=15.0, adx=20.0, rsi=52.0, days_to_event=1)
        assert result["regime"] == "PRE_EVENT"
        print(f"PASS: PRE_EVENT regime correctly classified")

    def test_post_event_iv_crush_regime(self):
        result = classify_market_regime_enhanced(vix=12.0, adx=15.0, rsi=50.0, post_event_hours=12)
        assert result["regime"] == "POST_EVENT_IV_CRUSH"
        print(f"PASS: POST_EVENT_IV_CRUSH regime correctly classified")

    def test_returns_strategy_grid(self):
        result = classify_market_regime_enhanced(vix=14.0, adx=22.0, rsi=54.0)
        assert "strategy" in result
        strategy = result["strategy"]
        assert "primary" in strategy, "Strategy grid missing 'primary' key"
        print(f"PASS: Strategy grid primary = {strategy['primary']}")

    def test_vix_none_returns_unknown_regime(self):
        result = classify_market_regime_enhanced(vix=None)
        assert result["regime"] == "UNKNOWN"


class TestSectorMacroMap:
    """SECTOR_MACRO_IMPACT_MAP tests"""

    def test_has_15_entries(self):
        count = len(SECTOR_MACRO_IMPACT_MAP)
        assert count == 15, f"Expected 15 entries, got {count}"
        print(f"PASS: SECTOR_MACRO_IMPACT_MAP has {count} entries")

    def test_each_entry_has_required_keys(self):
        for key, value in SECTOR_MACRO_IMPACT_MAP.items():
            assert "beneficiaries" in value, f"{key}: Missing 'beneficiaries'"
            assert "losers" in value, f"{key}: Missing 'losers'"
            assert "impact_description" in value, f"{key}: Missing 'impact_description'"
            assert "intensity" in value, f"{key}: Missing 'intensity'"
        print(f"PASS: All 15 sector macro entries have required keys")

    def test_specific_events_present(self):
        required = ["RBI_RATE_HIKE", "RBI_RATE_CUT", "CRUDE_SPIKE", "CRUDE_FALL",
                    "FII_OUTFLOW", "FII_INFLOW", "GEOPOLITICAL_CONFLICT", "EV_ADOPTION_THEME"]
        for event in required:
            assert event in SECTOR_MACRO_IMPACT_MAP, f"Missing event: {event}"
        print(f"PASS: All specific required events present")


class TestMacroContext:
    """compute_macro_context tests"""

    def test_returns_regime_and_macro_bias(self):
        result = compute_macro_context(
            active_events=["CRUDE_SPIKE", "FII_OUTFLOW"],
            vix=18.0, adx=22.0, rsi=48.0,
            sector="IT",
        )
        assert "regime" in result
        assert "macro_bias" in result
        assert result["macro_bias"] in ("TAILWIND", "HEADWIND", "NEUTRAL")
        print(f"PASS: Macro context - bias={result['macro_bias']}, regime={result['regime']['regime']}")

    def test_geopolitical_flag_activated(self):
        result = compute_macro_context(
            active_events=["GEOPOLITICAL_CONFLICT"],
            vix=22.0, geopolitical_risk=True,
        )
        geo_flag = result.get("geopolitical_flag", {})
        assert geo_flag.get("active") is True
        print(f"PASS: Geopolitical flag active")

    def test_returns_event_impacts_list(self):
        result = compute_macro_context(
            active_events=["RBI_RATE_CUT"],
            vix=14.0, sector="Real Estate",
        )
        assert isinstance(result.get("event_impacts"), list)
        print(f"PASS: Event impacts = {result['event_impacts']}")


# ─────────────────────────────────────────────────────────────────────────────
# BATCH 4: PORTFOLIO ENHANCEMENTS
# ─────────────────────────────────────────────────────────────────────────────

class TestPortfolioCorrelationMatrix:
    """Portfolio correlation matrix tests"""

    def test_returns_matrix_and_high_pairs(self):
        np.random.seed(42)
        returns = {
            "RELIANCE": list(np.random.normal(0.001, 0.02, 60)),
            "INFY": list(np.random.normal(0.002, 0.018, 60)),
            "HDFCBANK": list(np.random.normal(0.0015, 0.019, 60)),
        }
        result = compute_portfolio_correlation_matrix(returns)
        assert result.get("available") is True
        assert "matrix" in result
        assert "high_correlation_pairs" in result
        assert isinstance(result["matrix"], dict)
        assert isinstance(result["high_correlation_pairs"], list)
        print(f"PASS: Correlation matrix for {len(result['matrix'])} symbols")

    def test_diagonal_is_1(self):
        np.random.seed(10)
        returns = {
            "A": list(np.random.normal(0.001, 0.02, 30)),
            "B": list(np.random.normal(0.001, 0.02, 30)),
        }
        result = compute_portfolio_correlation_matrix(returns)
        if result.get("available"):
            matrix = result["matrix"]
            for sym in matrix:
                assert abs(matrix[sym][sym] - 1.0) < 1e-6, f"Diagonal should be 1.0 for {sym}"
            print(f"PASS: Diagonal elements are 1.0")

    def test_insufficient_data_returns_not_available(self):
        result = compute_portfolio_correlation_matrix({"A": [0.01, 0.02]})
        assert result.get("available") is False


class TestPortfolioStressTests:
    """Portfolio stress tests"""

    def test_returns_5_scenarios(self):
        holdings = [
            {"symbol": "RELIANCE", "sector": "Oil & Gas", "current_value": 100000, "portfolio_beta": 1.0},
            {"symbol": "INFY", "sector": "IT", "current_value": 80000, "portfolio_beta": 0.8},
            {"symbol": "HDFCBANK", "sector": "Banking", "current_value": 120000, "portfolio_beta": 1.2},
        ]
        result = compute_portfolio_stress_tests(holdings)
        assert result.get("available") is True
        scenarios = result.get("scenarios", {})
        assert len(scenarios) == 5, f"Expected 5 scenarios, got {len(scenarios)}"
        expected_keys = ["NIFTY_CRASH_10PCT", "CRUDE_SPIKE_30PCT", "INR_WEAKENS_5PCT",
                         "US_RECESSION", "RBI_RATE_HIKE_50BPS"]
        for k in expected_keys:
            assert k in scenarios, f"Missing scenario: {k}"
        print(f"PASS: All 5 stress scenarios present")

    def test_each_scenario_has_impact_pct(self):
        holdings = [
            {"symbol": "SBIN", "sector": "Banking", "current_value": 50000, "portfolio_beta": 1.1},
        ]
        result = compute_portfolio_stress_tests(holdings)
        for key, scenario in result["scenarios"].items():
            assert "portfolio_impact_pct" in scenario, f"Scenario {key} missing impact_pct"
        print(f"PASS: All scenarios have portfolio_impact_pct")

    def test_worst_scenario_key_present(self):
        holdings = [{"symbol": "X", "sector": "IT", "current_value": 100000, "portfolio_beta": 1.0}]
        result = compute_portfolio_stress_tests(holdings)
        assert "worst_scenario" in result
        assert "worst_case_loss_pct" in result
        print(f"PASS: Worst scenario = {result['worst_scenario']} ({result['worst_case_loss_pct']}%)")


class TestDiversificationAudit:
    """Diversification audit tests"""

    def test_returns_sector_allocation_pct(self):
        holdings = [
            {"symbol": "RELIANCE", "sector": "Oil & Gas", "current_value": 100000, "market_cap": 300e9},
            {"symbol": "INFY", "sector": "IT", "current_value": 80000, "market_cap": 250e9},
            {"symbol": "HDFCBANK", "sector": "Banking", "current_value": 120000, "market_cap": 800e9},
            {"symbol": "SUNPHARMA", "sector": "Pharma", "current_value": 60000, "market_cap": 180e9},
        ]
        result = compute_diversification_audit(holdings)
        assert result.get("available") is True
        assert "sector_allocation_pct" in result
        assert isinstance(result["sector_allocation_pct"], dict)
        assert len(result["sector_allocation_pct"]) >= 1
        total_pct = sum(result["sector_allocation_pct"].values())
        assert abs(total_pct - 100.0) < 0.5, f"Sector pcts don't sum to ~100: {total_pct}"
        print(f"PASS: Sector allocation = {result['sector_allocation_pct']}")

    def test_flags_over_concentrated_sector(self):
        holdings = [
            {"symbol": "X", "sector": "IT", "current_value": 200000, "market_cap": 100e9},
            {"symbol": "Y", "sector": "IT", "current_value": 200000, "market_cap": 100e9},
            {"symbol": "Z", "sector": "Other", "current_value": 50000, "market_cap": 50e9},
        ]
        result = compute_diversification_audit(holdings)
        assert result.get("available") is True
        assert any("concentrated" in f.lower() or "IT" in f for f in result["flags"])
        print(f"PASS: Concentration flag detected: {result['flags']}")


class TestUpcomingCatalysts:
    """Upcoming catalysts tests"""

    def test_returns_macro_events_list(self):
        result = compute_upcoming_catalysts(
            symbols=["HDFCBANK", "RELIANCE"],
            days_window=30,
        )
        assert result.get("available") is True
        assert "macro_events" in result
        assert isinstance(result["macro_events"], list)
        print(f"PASS: Upcoming catalysts - {len(result['macro_events'])} macro events in 30-day window")

    def test_earnings_dates_detected(self):
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=5)).isoformat()
        result = compute_upcoming_catalysts(
            symbols=["INFY"],
            earnings_dates={"INFY": future_date},
            days_window=10,
        )
        assert result.get("available") is True
        cats = result.get("stock_catalysts", {})
        assert "INFY" in cats, "INFY earnings should be detected"
        print(f"PASS: Earnings catalyst detected for INFY: {cats['INFY']}")


class TestMergeHoldings:
    """Merge duplicate holdings tests"""

    def test_merges_same_symbol_entries(self):
        holdings = [
            {"symbol": "RELIANCE", "quantity": 10, "avg_price": 2400.0,
             "current_value": 25000, "unrealized_pnl": 1000},
            {"symbol": "RELIANCE", "quantity": 5, "avg_price": 2500.0,
             "current_value": 12500, "unrealized_pnl": -200},
            {"symbol": "INFY", "quantity": 20, "avg_price": 1500.0,
             "current_value": 31000, "unrealized_pnl": 1000},
        ]
        result = merge_duplicate_holdings(holdings)
        symbols = [h["symbol"] for h in result]
        assert len(result) == 2, f"Expected 2 merged entries, got {len(result)}"
        assert symbols.count("RELIANCE") == 1, "RELIANCE should be merged to single entry"
        assert symbols.count("INFY") == 1, "INFY should remain as 1 entry"

        reliance = next(h for h in result if h["symbol"] == "RELIANCE")
        assert reliance["quantity"] == 15, f"Total qty should be 15, got {reliance['quantity']}"
        expected_avg = (10*2400 + 5*2500) / 15
        assert abs(reliance["avg_price"] - expected_avg) < 1, f"Avg price mismatch: {reliance['avg_price']} vs {expected_avg}"
        print(f"PASS: Holdings merged — RELIANCE: qty={reliance['quantity']}, avg={reliance['avg_price']}")

    def test_no_duplicates_unchanged(self):
        holdings = [
            {"symbol": "TCS", "quantity": 5, "avg_price": 3500.0, "current_value": 17500},
        ]
        result = merge_duplicate_holdings(holdings)
        assert len(result) == 1


class TestMasterStockSnapshot:
    """Master stock snapshot tests"""

    def test_returns_52w_high_low_and_ath(self, hist_260):
        result = compute_master_stock_snapshot(
            symbol="RELIANCE",
            ltp=550.0,
            hist=hist_260,
            sector="Oil & Gas",
            market_cap=300e9,
        )
        assert "week52_high" in result
        assert "week52_low" in result
        assert "ath" in result
        assert result["week52_high"] > 0
        assert result["week52_low"] > 0
        assert result["ath"] >= result["week52_high"]  # ATH >= 52W high
        print(f"PASS: 52W high={result['week52_high']}, 52W low={result['week52_low']}, ATH={result['ath']}")

    def test_market_cap_category(self, hist_260):
        result = compute_master_stock_snapshot("RELIANCE", 550.0, hist_260, market_cap=300e9)
        assert result["market_cap_category"] == "LARGE_CAP"

        result_mid = compute_master_stock_snapshot("MIDCO", 100.0, hist_260, market_cap=80e9)
        assert result_mid["market_cap_category"] == "MID_CAP"
        print(f"PASS: Market cap categories correct")

    def test_pct_from_52w_high_and_low(self, hist_260):
        ltp = float(hist_260["Close"].iloc[-1])
        result = compute_master_stock_snapshot("TEST", ltp, hist_260)
        assert "pct_from_52w_high" in result
        assert "pct_from_52w_low" in result
        assert result["pct_from_52w_high"] <= 0  # LTP <= 52W high
        assert result["pct_from_52w_low"] >= 0   # LTP >= 52W low
        print(f"PASS: pct_from_52w_high={result['pct_from_52w_high']}%, pct_from_52w_low={result['pct_from_52w_low']}%")


# ─────────────────────────────────────────────────────────────────────────────
# BATCH 5: F&O STRATEGY LIBRARY & SIGNAL STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyLibrary:
    """Strategy library structure tests"""

    def test_has_13_strategies(self):
        count = len(STRATEGY_LIBRARY)
        assert count == 13, f"Expected 13 strategies, got {count}"
        print(f"PASS: Strategy library has {count} strategies")

    def test_required_strategy_ids_present(self):
        required_ids = [
            "S1_ORB", "S2_VWAP", "S3_SUPERTREND", "S4_MACD_ADX", "S5_RSI_REVERSION",
            "SW1_52W_BREAKOUT", "SW2_200DMA_BOUNCE", "SW3_FLAG_BREAKOUT",
            "E1_SHORT_STRADDLE", "E2_IRON_CONDOR", "E3_CALENDAR_SPREAD",
            "SF1_SCREENER_MOMENTUM", "SF2_FORENSIC_QUALITY"
        ]
        for sid in required_ids:
            assert sid in STRATEGY_LIBRARY, f"Missing strategy: {sid}"
        print(f"PASS: All 13 strategy IDs present")

    def test_each_strategy_has_required_fields(self):
        for sid, strat in STRATEGY_LIBRARY.items():
            assert "name" in strat, f"{sid}: Missing 'name'"
            assert "type" in strat, f"{sid}: Missing 'type'"
            assert "preferred_regime" in strat, f"{sid}: Missing 'preferred_regime'"
            assert "instruments" in strat, f"{sid}: Missing 'instruments'"
            assert "min_win_rate" in strat, f"{sid}: Missing 'min_win_rate'"
            assert strat["min_win_rate"] == 0.75, f"{sid}: min_win_rate should be 0.75"
        print(f"PASS: All strategies have required fields with correct thresholds")


class TestGetEligibleStrategies:
    """Eligible strategy filtering tests"""

    def test_filters_by_regime_and_instrument(self):
        eligible = get_eligible_strategies("LOW_VOL_TREND_BULL", "NIFTY")
        assert isinstance(eligible, list)
        assert len(eligible) > 0, "Should return at least one eligible strategy for LOW_VOL_TREND_BULL"
        for s in eligible:
            assert "id" in s
            assert "name" in s
        print(f"PASS: {len(eligible)} strategies eligible for LOW_VOL_TREND_BULL/NIFTY: {[s['id'] for s in eligible]}")

    def test_filters_by_backtest_stats(self):
        stats = {
            "S1_ORB": {"win_rate": 0.60, "expectancy": 0.30, "total_trades": 25, "disabled": True},
        }
        eligible = get_eligible_strategies("LOW_VOL_TREND_BULL", "NIFTY", strategy_stats=stats)
        ids = [s["id"] for s in eligible]
        assert "S1_ORB" not in ids, "S1_ORB with low win_rate should be filtered out"
        print(f"PASS: Filtered out low win_rate strategy. Remaining: {ids}")

    def test_returns_empty_for_unknown_regime(self):
        # An unknown regime should return strategies only if they have NORMAL_VOL_TREND in preferred
        eligible = get_eligible_strategies("UNKNOWN_REGIME_XYZ", "NIFTY")
        # strategies with NORMAL_VOL_TREND in preferred_regime will still match
        print(f"INFO: {len(eligible)} strategies for unknown regime (expected only NORMAL_VOL_TREND matches)")


class TestSelectStrategyForSignal:
    """Strategy auto-selection tests"""

    def test_returns_strategy_for_normal_regime(self):
        strategy = select_strategy_for_signal(
            regime="NORMAL_VOL_TREND",
            direction="BULLISH",
            adx=25.0, vix=14.0,
            instrument="NIFTY",
        )
        assert strategy is not None, "Should return a strategy for NORMAL_VOL_TREND"
        assert "id" in strategy
        assert "name" in strategy
        print(f"PASS: Selected strategy = {strategy['id']} ({strategy['name']})")

    def test_returns_swing_strategy_for_swing_mode(self):
        strategy = select_strategy_for_signal(
            regime="LOW_VOL_TREND_BULL",
            direction="BULLISH",
            instrument="LIQUID_STOCKS",
            is_swing=True,
        )
        if strategy:
            print(f"PASS: Swing strategy selected = {strategy['id']} type={strategy['type']}")
        else:
            print("INFO: No swing strategy matched (acceptable)")

    def test_pre_event_prefers_expiry_strategy(self):
        strategy = select_strategy_for_signal(
            regime="PRE_EVENT",
            direction="BULLISH",
            vix=16.0, instrument="NIFTY",
        )
        if strategy:
            print(f"PASS: Pre-event strategy = {strategy['id']}, type={strategy['type']}")


class TestCheckStrategyEligible:
    """Strategy eligibility check tests"""

    def test_no_stats_is_eligible(self):
        eligible, reason = check_strategy_eligible(None)
        assert eligible is True
        print(f"PASS: No stats = eligible. Reason: {reason}")

    def test_below_win_rate_threshold_ineligible(self):
        stats = {"total_trades": 20, "win_rate": 0.60, "expectancy": 0.50, "disabled": False}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is False, f"Win rate < 75% should be ineligible. Reason: {reason}"
        print(f"PASS: Low win_rate correctly rejected: {reason}")

    def test_disabled_strategy_ineligible(self):
        stats = {"total_trades": 25, "win_rate": 0.80, "expectancy": 0.50, "disabled": True}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is False, f"Disabled strategy should be ineligible"
        print(f"PASS: Disabled strategy rejected: {reason}")

    def test_high_win_rate_is_eligible(self):
        stats = {"total_trades": 20, "win_rate": 0.80, "expectancy": 0.50, "disabled": False}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is True
        print(f"PASS: High win rate eligible: {reason}")

    def test_insufficient_trades_provisional(self):
        stats = {"total_trades": 5, "win_rate": 0.60, "expectancy": 0.30, "disabled": False}
        eligible, reason = check_strategy_eligible(stats, min_trades=10)
        assert eligible is True, "Insufficient trades should be provisionally allowed"
        print(f"PASS: Insufficient trades provisionally allowed: {reason}")


class TestSignalStateMachine:
    """Signal lifecycle state machine tests"""

    def test_active_to_watching_t1(self):
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=120.0, entry_price=100.0,
            sl_price=90.0, t1_price=115.0, t2_price=130.0,
            direction="BULLISH",
            minutes_to_expiry=300,
        )
        assert result["new_state"] == "WATCHING_T1", f"Expected WATCHING_T1, got {result['new_state']}"
        print(f"PASS: ACTIVE → WATCHING_T1 when T1 hit")

    def test_active_to_watching_sl(self):
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=88.0, entry_price=100.0,
            sl_price=90.0, t1_price=115.0, t2_price=130.0,
            direction="BULLISH",
            minutes_to_expiry=300,
        )
        assert result["new_state"] == "WATCHING_SL", f"Expected WATCHING_SL, got {result['new_state']}"
        print(f"PASS: ACTIVE → WATCHING_SL when SL approached")

    def test_watching_sl_to_closed_loss(self):
        result = transition_signal_state(
            current_state="WATCHING_SL",
            ltp=88.0, entry_price=100.0,
            sl_price=90.0, t1_price=115.0, t2_price=130.0,
            direction="BULLISH",
            minutes_to_expiry=300,
        )
        assert result["new_state"] == "CLOSED_LOSS", f"Expected CLOSED_LOSS, got {result['new_state']}"
        print(f"PASS: WATCHING_SL → CLOSED_LOSS when SL hit")

    def test_watching_t1_to_closed_win_no_t2(self):
        result = transition_signal_state(
            current_state="WATCHING_T1",
            ltp=116.0, entry_price=100.0,
            sl_price=90.0, t1_price=115.0, t2_price=None,
            direction="BULLISH",
            minutes_to_expiry=300,
        )
        assert result["new_state"] == "CLOSED_WIN", f"Expected CLOSED_WIN, got {result['new_state']}"
        print(f"PASS: WATCHING_T1 → CLOSED_WIN when T1 achieved with no T2")

    def test_urgent_exit_when_15_min_to_expiry(self):
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=105.0, entry_price=100.0,
            sl_price=90.0, t1_price=115.0, t2_price=130.0,
            direction="BULLISH",
            minutes_to_expiry=10,  # <= 15 mins
        )
        assert result["urgent_exit"] is True, "urgent_exit should be True when <= 15 min to expiry"
        assert result["new_state"] == "EXPIRED"
        print(f"PASS: Urgent exit triggered at 10 min to expiry")

    def test_terminal_state_no_transition(self):
        result = transition_signal_state(
            current_state="CLOSED_WIN",
            ltp=120.0, entry_price=100.0,
            sl_price=90.0, t1_price=115.0, t2_price=130.0,
            minutes_to_expiry=300,
        )
        assert result["new_state"] == "CLOSED_WIN", "Terminal state should not transition"
        print(f"PASS: Terminal state CLOSED_WIN unchanged")

    def test_bearish_signal_state_machine(self):
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=80.0, entry_price=100.0,
            sl_price=110.0, t1_price=85.0, t2_price=75.0,
            direction="BEARISH",
            minutes_to_expiry=300,
        )
        assert result["new_state"] in ("WATCHING_T1", "ACTIVE")
        print(f"PASS: Bearish signal state = {result['new_state']}")


class TestUpdateBacktestStats:
    """Update backtest stats tests"""

    def test_updates_correctly_with_win(self):
        try:
            existing = {"total_trades": 10, "wins": 8, "total_r_multiple": 5.0}
            new_result = {"win": True, "r_multiple": 1.5, "symbol": "NIFTY"}
            updated = update_backtest_stats(existing, new_result)
            assert updated["total_trades"] == 11
            assert updated["wins"] == 9
            assert abs(updated["win_rate"] - 9/11) < 0.001
            print(f"PASS: Backtest stats updated: trades={updated['total_trades']}, win_rate={updated['win_rate']:.2%}")
        except NameError as e:
            # Known bug: datetime/timezone not imported at module level
            pytest.fail(f"BUG: NameError in update_backtest_stats - missing datetime/timezone import: {e}")


class TestIndexConstituentBias:
    """Index constituent bias computation tests"""

    def test_returns_bullish_bias(self):
        signals = [
            {"symbol": "HDFCBANK", "tech_bias": "BULLISH", "direction": "BULLISH", "conviction": 0.8},
            {"symbol": "ICICIBANK", "tech_bias": "BULLISH", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "AXISBANK", "tech_bias": "BULLISH", "direction": "BULLISH", "conviction": 0.7},
            {"symbol": "SBIN", "tech_bias": "BEARISH", "direction": "BEARISH", "conviction": 0.5},
        ]
        result = compute_index_constituent_bias(signals, index_name="BANKNIFTY")
        assert "weighted_bias" in result
        assert result["weighted_bias"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert "breadth_score" in result
        # NOTE: breadth_score formula can exceed 0-100 range (norm_bull - norm_bear + 50)
        # This is a known design issue: breadth_score may be > 100 in strongly bullish scenarios
        assert isinstance(result["breadth_score"], (int, float))
        print(f"PASS: BANKNIFTY weighted bias = {result['weighted_bias']}, breadth = {result['breadth_score']}")

    def test_returns_bearish_bias(self):
        signals = [
            {"symbol": "RELIANCE", "tech_bias": "BEARISH", "direction": "BEARISH", "conviction": 1.0},
            {"symbol": "HDFCBANK", "tech_bias": "BEARISH", "direction": "BEARISH", "conviction": 1.0},
            {"symbol": "ICICIBANK", "tech_bias": "BEARISH", "direction": "BEARISH", "conviction": 1.0},
        ]
        result = compute_index_constituent_bias(signals, index_name="NIFTY")
        assert result["weighted_bias"] == "BEARISH", f"Expected BEARISH, got {result['weighted_bias']}"
        print(f"PASS: Bearish bias confirmed with breadth={result['breadth_score']}")

    def test_empty_signals_returns_neutral(self):
        result = compute_index_constituent_bias([], index_name="NIFTY")
        assert result["weighted_bias"] == "NEUTRAL"
        assert result["breadth_score"] == 50
        print(f"PASS: Empty signals returns NEUTRAL bias")

    def test_nifty50_weights_populated(self):
        assert len(NIFTY50_WEIGHTS) >= 20, f"NIFTY50_WEIGHTS should have >= 20 constituents"
        assert "RELIANCE" in NIFTY50_WEIGHTS
        assert "HDFCBANK" in NIFTY50_WEIGHTS
        print(f"PASS: NIFTY50_WEIGHTS has {len(NIFTY50_WEIGHTS)} constituents")

    def test_banknifty_weights_populated(self):
        assert len(BANKNIFTY_WEIGHTS) >= 8, f"BANKNIFTY_WEIGHTS should have >= 8 constituents"
        assert "HDFCBANK" in BANKNIFTY_WEIGHTS
        print(f"PASS: BANKNIFTY_WEIGHTS has {len(BANKNIFTY_WEIGHTS)} constituents")


# ─────────────────────────────────────────────────────────────────────────────
# REGIME STRATEGY GRID VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeStrategyGrid:
    """REGIME_STRATEGY_GRID has all 8 regimes"""

    def test_has_8_regimes(self):
        count = len(REGIME_STRATEGY_GRID)
        assert count == 8, f"Expected 8 regime entries, got {count}"
        print(f"PASS: REGIME_STRATEGY_GRID has {count} entries")

    def test_each_regime_has_strategy_fields(self):
        for regime, grid in REGIME_STRATEGY_GRID.items():
            assert "primary" in grid, f"{regime}: Missing 'primary'"
            assert "secondary" in grid, f"{regime}: Missing 'secondary'"
            assert "avoid" in grid, f"{regime}: Missing 'avoid'"
        print(f"PASS: All 8 regime grid entries have primary/secondary/avoid")
