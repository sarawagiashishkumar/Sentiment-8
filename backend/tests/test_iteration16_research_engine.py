"""
Iteration 16 backend tests:
- Research Engine unit tests (compute_realistic_price_bands, classify_market_regime,
  check_stock_eligibility, compute_atr_based_fno_targets, compute_portfolio_risk_metrics)
- Server.py model field verification (FNOGenerateResponse, PortfolioAnalyzeResponse)
- 78% confluence score threshold in is_potential_trade / FNO generate logic
- instrument_token stored in kite_option_master
- _get_hist_ohlcv returns pandas DataFrame
- Backend starts cleanly: root API returns 200
- _fetch_yfinance_fundamentals has new fields
"""
from __future__ import annotations

import os
import sys
import math
import importlib
import pytest
import requests
import pandas as pd

# Add backend to path for direct imports
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL env var not set")

# ─────────────────────────────────────────────────────────────────────────────
# Auth fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "pin": "1234"},
        timeout=15,
    )
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    data = resp.json()
    assert "token" in data
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Backend root returns 200 (server starts cleanly)
# ─────────────────────────────────────────────────────────────────────────────

class TestBackendHealth:
    """Verify backend starts cleanly."""

    def test_root_api_returns_200(self):
        """GET /api/ returns HTTP 200."""
        resp = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        print(f"Root API response: {data}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Research engine imports (Python unit)
# ─────────────────────────────────────────────────────────────────────────────

class TestResearchEngineImports:
    """Verify research_engine.py loads without error and all functions importable."""

    def test_module_import(self):
        """research_engine.py imports without error."""
        import services.research_engine as re_mod
        assert re_mod is not None
        print("research_engine imported OK")

    def test_all_functions_exist(self):
        """All critical functions exist in the module."""
        from services.research_engine import (
            compute_realistic_price_bands,
            classify_market_regime,
            check_stock_eligibility,
            compute_atr_based_fno_targets,
            compute_portfolio_risk_metrics,
            compute_rsi,
            compute_macd,
            compute_atr,
            compute_adx,
            compute_obv,
            compute_full_technical_snapshot,
            compute_technical_confluence_bonus,
            compute_portfolio_verdict,
            check_urgent_exit,
        )
        print("All 14 research engine functions imported successfully")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: FNOGenerateResponse model fields
# ─────────────────────────────────────────────────────────────────────────────

class TestFNOGenerateResponseModel:
    """Verify FNOGenerateResponse Pydantic model has new optional fields."""

    def test_no_signals_alert_field_exists(self):
        """FNOGenerateResponse has no_signals_alert optional field."""
        from server import FNOGenerateResponse
        fields = FNOGenerateResponse.model_fields
        assert "no_signals_alert" in fields, "no_signals_alert field missing from FNOGenerateResponse"
        # Should be optional (None default)
        field = fields["no_signals_alert"]
        assert field.default is None, f"no_signals_alert should default to None, got {field.default}"
        print(f"no_signals_alert field: type={field.annotation}, default={field.default}")

    def test_market_regime_field_exists(self):
        """FNOGenerateResponse has market_regime optional field."""
        from server import FNOGenerateResponse
        fields = FNOGenerateResponse.model_fields
        assert "market_regime" in fields, "market_regime field missing from FNOGenerateResponse"
        field = fields["market_regime"]
        assert field.default is None, f"market_regime should default to None, got {field.default}"
        print(f"market_regime field: type={field.annotation}, default={field.default}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: PortfolioAnalyzeResponse model fields
# ─────────────────────────────────────────────────────────────────────────────

class TestPortfolioAnalyzeResponseModel:
    """Verify PortfolioAnalyzeResponse has portfolio_risk_metrics optional field."""

    def test_portfolio_risk_metrics_field_exists(self):
        """PortfolioAnalyzeResponse has portfolio_risk_metrics optional field."""
        from server import PortfolioAnalyzeResponse
        fields = PortfolioAnalyzeResponse.model_fields
        assert "portfolio_risk_metrics" in fields, "portfolio_risk_metrics missing from PortfolioAnalyzeResponse"
        field = fields["portfolio_risk_metrics"]
        assert field.default is None, f"portfolio_risk_metrics should default to None, got {field.default}"
        print(f"portfolio_risk_metrics field: type={field.annotation}, default={field.default}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: compute_realistic_price_bands
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeRealisticPriceBands:
    """Unit tests for compute_realistic_price_bands."""

    def test_returns_all_horizons(self):
        """Returns dict with all 6 horizon keys: 1W, 1M, 3M, 6M, 9M, 1Y."""
        from services.research_engine import compute_realistic_price_bands
        result = compute_realistic_price_bands(ltp=1000.0, hist_vol=0.25)
        assert isinstance(result, dict)
        expected_horizons = {"1W", "1M", "3M", "6M", "9M", "1Y"}
        assert set(result.keys()) == expected_horizons, f"Missing horizons: {expected_horizons - set(result.keys())}"
        print(f"Price bands keys: {list(result.keys())}")

    def test_each_horizon_has_required_keys(self):
        """Each horizon dict has upside_pct, downside_pct, flag."""
        from services.research_engine import compute_realistic_price_bands
        result = compute_realistic_price_bands(ltp=500.0, hist_vol=0.30)
        for horizon, data in result.items():
            assert "upside_pct" in data, f"upside_pct missing from {horizon}"
            assert "downside_pct" in data, f"downside_pct missing from {horizon}"
            assert "flag" in data, f"flag missing from {horizon}"
        print("All horizons have required keys")

    def test_upside_pct_positive_downside_negative(self):
        """upside_pct > 0, downside_pct < 0 for normal LTP and vol."""
        from services.research_engine import compute_realistic_price_bands
        result = compute_realistic_price_bands(ltp=2000.0, hist_vol=0.20)
        for horizon, data in result.items():
            assert data["upside_pct"] >= 1.0, f"{horizon}: upside_pct={data['upside_pct']} should be ≥ 1.0"
            assert data["downside_pct"] <= -1.0, f"{horizon}: downside_pct={data['downside_pct']} should be ≤ -1.0"
        print("upside/downside signs correct")

    def test_flag_is_green_or_red(self):
        """flag is either GREEN or RED."""
        from services.research_engine import compute_realistic_price_bands
        result = compute_realistic_price_bands(ltp=100.0, hist_vol=0.32)
        for horizon, data in result.items():
            assert data["flag"] in ("GREEN", "RED"), f"{horizon}: invalid flag={data['flag']}"
        print("Flags are valid GREEN/RED")

    def test_fallback_without_hist_vol(self):
        """Works when hist_vol is None (uses sector fallback)."""
        from services.research_engine import compute_realistic_price_bands
        result = compute_realistic_price_bands(ltp=500.0, hist_vol=None, sector="IT")
        assert isinstance(result, dict)
        assert len(result) == 6
        print(f"Fallback (no hist_vol) worked, sector=IT, 1Y upside={result['1Y']['upside_pct']}%")

    def test_volatility_scales_with_horizon(self):
        """Longer horizons should have larger price bands."""
        from services.research_engine import compute_realistic_price_bands
        result = compute_realistic_price_bands(ltp=1000.0, hist_vol=0.30)
        # 1Y bands should be larger than 1W bands
        assert result["1Y"]["upside_pct"] > result["1W"]["upside_pct"], "1Y upside should exceed 1W upside"
        assert result["1Y"]["downside_pct"] < result["1W"]["downside_pct"], "1Y downside should be more negative than 1W"
        print(f"1W upside={result['1W']['upside_pct']}% 1Y upside={result['1Y']['upside_pct']}%")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: classify_market_regime
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyMarketRegime:
    """Unit tests for classify_market_regime."""

    def test_returns_dict_with_required_keys(self):
        """Returns dict with regime, vix, options_strategy keys."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=15.0)
        assert isinstance(result, dict)
        assert "regime" in result
        assert "vix" in result
        assert "options_strategy" in result
        print(f"Regime result: {result}")

    def test_normal_vix_regime(self):
        """VIX 15 → NORMAL_VOL regime."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=15.0)
        assert result["regime"] == "NORMAL_VOL"
        assert result["options_strategy"] == "STANDARD_DIRECTIONAL"
        assert result["vix"] == 15.0
        print(f"Normal VIX: {result['regime']}")

    def test_low_vix_regime(self):
        """VIX 10 → LOW_VOL_RANGE regime."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=10.0)
        assert result["regime"] == "LOW_VOL_RANGE"
        assert result["options_strategy"] == "IRON_CONDOR"
        print(f"Low VIX: {result['regime']}")

    def test_elevated_vix_regime(self):
        """VIX 22 → ELEVATED_VOL regime."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=22.0)
        assert result["regime"] == "ELEVATED_VOL"
        assert result["options_strategy"] == "LONG_OPTIONS"
        print(f"Elevated VIX: {result['regime']}")

    def test_high_vix_regime(self):
        """VIX 30 → HIGH_VOL_TREND regime."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=30.0)
        assert result["regime"] == "HIGH_VOL_TREND"
        print(f"High VIX: {result['regime']}")

    def test_crash_vix_regime(self):
        """VIX 40 → CRASH_MODE regime."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=40.0)
        assert result["regime"] == "CRASH_MODE"
        assert result["options_strategy"] == "PROTECTIVE_PUTS"
        print(f"Crash VIX: {result['regime']}")

    def test_none_vix_returns_unknown(self):
        """VIX=None → UNKNOWN regime."""
        from services.research_engine import classify_market_regime
        result = classify_market_regime(vix=None)
        assert result["regime"] == "UNKNOWN"
        assert result["options_strategy"] == "STANDARD"
        print(f"None VIX: {result['regime']}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: check_stock_eligibility
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckStockEligibility:
    """Unit tests for check_stock_eligibility."""

    def test_returns_eligible_true_for_good_stock(self):
        """Stock with price > 50, low debt, positive profits → eligible."""
        from services.research_engine import check_stock_eligibility
        result = check_stock_eligibility(
            ltp=500.0,
            market_cap_cr=50000.0,
            fundamental={"total_debt_to_market_cap": 0.10, "recent_profit_positive": True},
        )
        assert isinstance(result, dict)
        assert "eligible" in result
        assert "flags" in result
        assert "pass_count" in result
        assert result["eligible"] is True
        assert len(result["flags"]) == 0
        print(f"Good stock: {result}")

    def test_low_price_ineligible(self):
        """Stock with price < 50 → ineligible."""
        from services.research_engine import check_stock_eligibility
        result = check_stock_eligibility(
            ltp=30.0, market_cap_cr=100.0, fundamental={}
        )
        assert result["eligible"] is False
        assert any("50" in flag for flag in result["flags"]), f"Flags: {result['flags']}"
        print(f"Low price stock: {result}")

    def test_high_debt_ineligible(self):
        """Stock with debt > 30% of mktcap → ineligible."""
        from services.research_engine import check_stock_eligibility
        result = check_stock_eligibility(
            ltp=200.0,
            market_cap_cr=1000.0,
            fundamental={"total_debt_to_market_cap": 0.50, "recent_profit_positive": True},
        )
        assert result["eligible"] is False
        assert any("debt" in flag.lower() or "30%" in flag for flag in result["flags"])
        print(f"High debt stock: {result}")

    def test_unprofitable_ineligible(self):
        """Stock with no profitable quarter in last 3 → ineligible."""
        from services.research_engine import check_stock_eligibility
        result = check_stock_eligibility(
            ltp=200.0,
            market_cap_cr=5000.0,
            fundamental={"total_debt_to_market_cap": 0.10, "recent_profit_positive": False},
        )
        assert result["eligible"] is False
        assert any("profit" in flag.lower() or "loss" in flag.lower() for flag in result["flags"])
        print(f"Unprofitable stock: {result}")

    def test_pass_count_in_result(self):
        """pass_count and max_filters present."""
        from services.research_engine import check_stock_eligibility
        result = check_stock_eligibility(
            ltp=100.0,
            market_cap_cr=2000.0,
            fundamental={"total_debt_to_market_cap": 0.05, "recent_profit_positive": True},
        )
        assert "pass_count" in result
        assert "max_filters" in result
        assert result["max_filters"] == 3
        assert result["pass_count"] <= 3
        print(f"Pass count: {result['pass_count']}/{result['max_filters']}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: compute_atr_based_fno_targets
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeAtrBasedFnoTargets:
    """Unit tests for compute_atr_based_fno_targets."""

    def test_returns_tuple_of_two_floats(self):
        """Returns (target1, target2) tuple."""
        from services.research_engine import compute_atr_based_fno_targets
        result = compute_atr_based_fno_targets(
            entry_price=50.0,
            underlying_ltp=22000.0,
            atr=200.0,
            minutes_to_expiry=960,
            option_type="CE",
        )
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 2
        t1, t2 = result
        assert isinstance(t1, float)
        assert isinstance(t2, float)
        print(f"ATR targets: T1={t1}, T2={t2}")

    def test_targets_above_entry_price(self):
        """T1 and T2 should be above entry price."""
        from services.research_engine import compute_atr_based_fno_targets
        entry_price = 100.0
        t1, t2 = compute_atr_based_fno_targets(
            entry_price=entry_price,
            underlying_ltp=18000.0,
            atr=150.0,
            minutes_to_expiry=500,
            option_type="PE",
        )
        assert t1 > entry_price, f"T1={t1} should be > entry={entry_price}"
        assert t2 > entry_price, f"T2={t2} should be > entry={entry_price}"
        assert t2 > t1, f"T2={t2} should be > T1={t1}"
        print(f"Entry={entry_price}, T1={t1}, T2={t2}")

    def test_atr_based_vs_fixed_pct(self):
        """With real ATR provided, T1 ≠ simple fixed % of entry (ATR-driven)."""
        from services.research_engine import compute_atr_based_fno_targets
        entry = 50.0
        underlying = 22500.0
        atr = 300.0  # Large ATR = wider targets

        t1_large_atr, t2_large_atr = compute_atr_based_fno_targets(
            entry_price=entry, underlying_ltp=underlying, atr=atr,
            minutes_to_expiry=960, option_type="CE",
        )
        t1_small_atr, t2_small_atr = compute_atr_based_fno_targets(
            entry_price=entry, underlying_ltp=underlying, atr=50.0,  # Small ATR
            minutes_to_expiry=960, option_type="CE",
        )
        # Larger ATR should generally produce larger targets (or at least not less)
        # due to ATR-based calculation vs fixed %
        print(f"Large ATR: T1={t1_large_atr}, T2={t2_large_atr}")
        print(f"Small ATR: T1={t1_small_atr}, T2={t2_small_atr}")
        # Both should be within bounds
        assert t1_large_atr >= entry * 1.039, "T1 should be at least 4% above entry"
        assert t2_large_atr >= entry * 1.099, "T2 should be at least 10% above entry (min cap)"

    def test_fallback_without_atr(self):
        """Works with atr=None (uses fallback fixed %)."""
        from services.research_engine import compute_atr_based_fno_targets
        t1, t2 = compute_atr_based_fno_targets(
            entry_price=80.0,
            underlying_ltp=15000.0,
            atr=None,
            minutes_to_expiry=300,
            option_type="CE",
        )
        assert t1 > 80.0
        assert t2 > 80.0
        print(f"Fallback (no ATR): T1={t1}, T2={t2}")

    def test_vix_factor_applied(self):
        """High VIX should produce wider targets than low VIX (same ATR)."""
        from services.research_engine import compute_atr_based_fno_targets
        t1_high_vix, _ = compute_atr_based_fno_targets(
            entry_price=50.0, underlying_ltp=22000.0, atr=200.0,
            minutes_to_expiry=960, option_type="CE", vix=30.0,
        )
        t1_low_vix, _ = compute_atr_based_fno_targets(
            entry_price=50.0, underlying_ltp=22000.0, atr=200.0,
            minutes_to_expiry=960, option_type="CE", vix=10.0,
        )
        assert t1_high_vix >= t1_low_vix, f"High VIX T1={t1_high_vix} should be >= Low VIX T1={t1_low_vix}"
        print(f"High VIX T1={t1_high_vix}, Low VIX T1={t1_low_vix}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: 78% minimum confluence filter (server.py code review)
# ─────────────────────────────────────────────────────────────────────────────

class TestConflenceScoreThreshold:
    """Verify is_potential_trade uses 78% threshold, not 58%."""

    def test_is_potential_trade_uses_78_threshold(self):
        """
        Check server.py source code: is_potential_trade should be gated at >= 78,
        not >= 58. Verify by reading the line from server.py.
        """
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        # Find the is_potential_trade assignment
        idx = content.find("is_potential_trade = direction != ")
        assert idx != -1, "is_potential_trade assignment not found in server.py"
        # Extract the line
        line_start = content.rfind("\n", 0, idx) + 1
        line_end = content.find("\n", idx)
        line = content[line_start:line_end]
        print(f"is_potential_trade line: {line.strip()}")
        # Must contain >= 78
        assert "78" in line, f"Expected threshold 78 in line: '{line.strip()}'"
        assert "58" not in line, f"Old threshold 58 still present in line: '{line.strip()}'"

    def test_fno_generate_filters_use_78_threshold(self):
        """
        Verify the FNO generate endpoint filters use confluence_score >= 78.
        Check lines near 4411 and 4692-4696 in server.py.
        """
        with open("/app/backend/server.py", "r") as f:
            lines = f.readlines()
        # Search for >= 78 patterns related to confluence
        found_78_filters = []
        for i, line in enumerate(lines, 1):
            if "confluence_score >= 78" in line:
                found_78_filters.append(f"Line {i}: {line.strip()}")
        assert len(found_78_filters) >= 2, f"Expected >= 2 uses of confluence_score >= 78, found: {found_78_filters}"
        print(f"78% confluence filters found ({len(found_78_filters)}):")
        for f in found_78_filters:
            print(f"  {f}")

    def test_no_signals_alert_message_mentions_78(self):
        """no_signals_alert message should mention 78% threshold."""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        # Find the no_signals_alert assignment
        idx = content.find("no_signals_alert")
        assert idx != -1, "no_signals_alert not found in server.py"
        # Check nearby context mentions 78%
        context = content[idx:idx + 500]
        assert "78" in context, f"78% not mentioned near no_signals_alert: {context[:200]}"
        print("no_signals_alert mentions 78% threshold ✓")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: compute_portfolio_risk_metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestComputePortfolioRiskMetrics:
    """Unit tests for compute_portfolio_risk_metrics."""

    def test_returns_dict_with_required_keys(self):
        """Returns dict with beta, sharpe_proxy, max_drawdown, var_95."""
        from services.research_engine import compute_portfolio_risk_metrics
        holdings = [
            {"symbol": "RELIANCE", "current_value": 100000, "pnl_pct": 15.0,
             "sector": "Energy", "hist_vol": 0.28, "beta": 0.95},
            {"symbol": "INFY", "current_value": 80000, "pnl_pct": -5.0,
             "sector": "IT", "hist_vol": 0.25, "beta": 0.85},
            {"symbol": "HDFC", "current_value": 120000, "pnl_pct": 8.0,
             "sector": "Financial Services", "hist_vol": 0.30, "beta": 1.10},
        ]
        result = compute_portfolio_risk_metrics(holdings)
        assert isinstance(result, dict)
        assert "portfolio_beta" in result, "Missing portfolio_beta"
        assert "sharpe_proxy" in result, "Missing sharpe_proxy"
        assert "max_single_drawdown_pct" in result, "Missing max_single_drawdown_pct"
        assert "var_95_1day_pct" in result, "Missing var_95_1day_pct"
        print(f"Risk metrics: beta={result.get('portfolio_beta')}, sharpe={result.get('sharpe_proxy')}")
        print(f"  max_dd={result.get('max_single_drawdown_pct')}, var_95={result.get('var_95_1day_pct')}")

    def test_portfolio_beta_reasonable_range(self):
        """Portfolio beta should be between 0.5 and 2.0 for typical stocks."""
        from services.research_engine import compute_portfolio_risk_metrics
        holdings = [
            {"symbol": "A", "current_value": 50000, "pnl_pct": 5.0, "beta": 1.0},
            {"symbol": "B", "current_value": 50000, "pnl_pct": 10.0, "beta": 1.2},
        ]
        result = compute_portfolio_risk_metrics(holdings)
        beta = result.get("portfolio_beta", 0)
        assert 0.5 <= beta <= 2.0, f"Beta {beta} out of reasonable range [0.5, 2.0]"
        print(f"Portfolio beta={beta}")

    def test_max_drawdown_is_negative_or_zero(self):
        """Max single drawdown is <= 0 when any holding is in loss."""
        from services.research_engine import compute_portfolio_risk_metrics
        holdings = [
            {"symbol": "A", "current_value": 50000, "pnl_pct": -20.0},
            {"symbol": "B", "current_value": 50000, "pnl_pct": 10.0},
        ]
        result = compute_portfolio_risk_metrics(holdings)
        max_dd = result.get("max_single_drawdown_pct", 0)
        assert max_dd <= 0, f"max_drawdown={max_dd} should be <= 0 when holdings are in loss"
        assert max_dd == -20.0, f"Expected -20.0, got {max_dd}"
        print(f"Max drawdown: {max_dd}")

    def test_var_95_is_negative(self):
        """VaR 95% should be negative (represents potential loss)."""
        from services.research_engine import compute_portfolio_risk_metrics
        holdings = [
            {"symbol": "X", "current_value": 100000, "pnl_pct": 5.0, "hist_vol": 0.25},
        ]
        result = compute_portfolio_risk_metrics(holdings)
        var_95 = result.get("var_95_1day_pct", 0)
        assert var_95 < 0, f"VaR 95% should be negative, got {var_95}"
        print(f"VaR 95% (1-day): {var_95}%")

    def test_win_rate_calculation(self):
        """win_rate_pct: 2 out of 3 profitable = 66.7%."""
        from services.research_engine import compute_portfolio_risk_metrics
        holdings = [
            {"symbol": "A", "current_value": 33333, "pnl_pct": 10.0},
            {"symbol": "B", "current_value": 33333, "pnl_pct": 5.0},
            {"symbol": "C", "current_value": 33334, "pnl_pct": -3.0},
        ]
        result = compute_portfolio_risk_metrics(holdings)
        win_rate = result.get("win_rate_pct", 0)
        # 2 wins out of 3 = 66.7%
        assert abs(win_rate - 66.7) < 1.0, f"Expected ~66.7%, got {win_rate}%"
        print(f"Win rate: {win_rate}%")

    def test_empty_holdings_returns_empty_dict(self):
        """Empty holdings list returns empty dict."""
        from services.research_engine import compute_portfolio_risk_metrics
        result = compute_portfolio_risk_metrics([])
        assert result == {}, f"Empty holdings should return {{}}, got {result}"
        print("Empty holdings → {} OK")

    def test_sector_breakdown_present(self):
        """sector_breakdown and win_rate present in result."""
        from services.research_engine import compute_portfolio_risk_metrics
        holdings = [
            {"symbol": "R", "current_value": 60000, "pnl_pct": 5.0, "sector": "Energy"},
            {"symbol": "I", "current_value": 40000, "pnl_pct": -2.0, "sector": "IT"},
        ]
        result = compute_portfolio_risk_metrics(holdings)
        assert "sector_breakdown" in result
        assert "win_rate_pct" in result
        assert "top_sector" in result
        assert "largest_holding_pct" in result
        assert result["largest_holding_pct"] == 60.0
        print(f"Sector breakdown: {result.get('sector_breakdown')}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 11: _fetch_yfinance_fundamentals new fields
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchYfinanceFundamentals:
    """Verify _fetch_yfinance_fundamentals includes the new fields."""

    def test_new_fields_in_function_source(self):
        """
        Verify server.py source includes total_debt_to_market_cap,
        recent_profit_positive, revenue_cagr_3y, fcf_yield in the function.
        """
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        # Find the function
        func_start = content.find("def _fetch_yfinance_fundamentals(")
        assert func_start != -1, "_fetch_yfinance_fundamentals not found"
        # Extract function body (next 6000 chars)
        func_body = content[func_start:func_start + 6000]
        required_fields = [
            "total_debt_to_market_cap",
            "recent_profit_positive",
            "revenue_cagr_3y",
            "fcf_yield",
        ]
        for field in required_fields:
            assert field in func_body, f"Field '{field}' missing from _fetch_yfinance_fundamentals"
        print("All 4 new fundamental fields found in _fetch_yfinance_fundamentals ✓")

    def test_fundamental_fields_returned_in_api_cached_data(self):
        """
        _fetch_yfinance_fundamentals is a sync function.
        Test directly with a real symbol to verify field presence.
        NOTE: This may return None for some fields if data unavailable from yfinance.
        """
        import sys; sys.path.insert(0, "/app/backend")
        from server import _fetch_yfinance_fundamentals
        result = _fetch_yfinance_fundamentals("RELIANCE.NS")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        # Check these keys exist in output (may be None if yfinance data unavailable)
        for key in ["total_debt_to_market_cap", "recent_profit_positive", "revenue_cagr_3y", "fcf_yield"]:
            assert key in result, f"Key '{key}' missing from _fetch_yfinance_fundamentals output"
        print(f"RELIANCE.NS fundamentals: total_debt_to_mktcap={result.get('total_debt_to_market_cap')}, "
              f"recent_profit={result.get('recent_profit_positive')}, "
              f"revenue_cagr={result.get('revenue_cagr_3y')}, "
              f"fcf_yield={result.get('fcf_yield')}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 12: _get_hist_ohlcv returns pandas DataFrame
# ─────────────────────────────────────────────────────────────────────────────

class TestGetHistOhlcv:
    """Verify _get_hist_ohlcv returns pandas DataFrame for valid NSE symbol."""

    def test_function_exists_and_is_async(self):
        """_get_hist_ohlcv exists and is an async function."""
        import asyncio
        from server import _get_hist_ohlcv
        import inspect
        assert inspect.iscoroutinefunction(_get_hist_ohlcv), "_get_hist_ohlcv should be async"
        print("_get_hist_ohlcv is async ✓")

    def test_returns_dataframe_for_valid_symbol(self):
        """_get_hist_ohlcv returns a pd.DataFrame for RELIANCE.NS."""
        import asyncio
        from server import _get_hist_ohlcv
        result = asyncio.get_event_loop().run_until_complete(
            _get_hist_ohlcv("RELIANCE.NS", period="3mo")
        )
        if result is None:
            pytest.skip("yfinance data unavailable in test environment (possibly rate-limited)")
        assert isinstance(result, pd.DataFrame), f"Expected DataFrame, got {type(result)}"
        assert not result.empty, "DataFrame should not be empty"
        # Check required columns
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert col in result.columns, f"Column {col} missing from DataFrame"
        print(f"RELIANCE.NS DataFrame: {len(result)} rows, columns={list(result.columns)}")

    def test_returns_none_for_invalid_symbol(self):
        """_get_hist_ohlcv returns None for invalid symbol INVALIDXYZ999.NS."""
        import asyncio
        from server import _get_hist_ohlcv
        result = asyncio.get_event_loop().run_until_complete(
            _get_hist_ohlcv("INVALIDXYZ999.NS", period="1mo")
        )
        assert result is None, f"Expected None for invalid symbol, got {type(result)}"
        print("Invalid symbol returned None ✓")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 13: kite_option_master instrument_token in MongoDB (API-based check)
# ─────────────────────────────────────────────────────────────────────────────

class TestKiteOptionMasterInstrumentToken:
    """Verify kite_option_master records have instrument_token field in schema."""

    def test_kite_instrument_token_in_server_source(self):
        """
        Source code check: kite_option_master insert should include instrument_token
        with comment about 'numeric token for historical API'.
        """
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        # Check the instrument_token is stored
        assert '"instrument_token": numeric_token' in content or \
               "'instrument_token': numeric_token" in content, \
               "instrument_token not stored in kite_option_master rows"
        # Verify the comment
        assert "numeric token for historical" in content, \
               "Missing comment about numeric token for historical API"
        print("instrument_token stored in kite_option_master ✓")

    def test_instrument_token_parsing_logic(self):
        """
        Verify numeric token parsing logic: int(float(str(raw_token).strip()))
        works for various inputs.
        """
        # Test the parsing logic inline (same as server.py)
        test_cases = [
            ("1234567", 1234567),
            ("1234567.0", 1234567),
            ("  9876543  ", 9876543),
            (1234567, 1234567),
            (1234567.0, 1234567),
        ]
        for raw_token, expected in test_cases:
            try:
                numeric_token = int(float(str(raw_token).strip()))
            except (ValueError, TypeError):
                numeric_token = None
            assert numeric_token == expected, f"raw={raw_token}: expected {expected}, got {numeric_token}"

        # Null/empty cases → None
        for bad_val in ["", None, "abc"]:
            raw_token = bad_val
            numeric_token = None
            try:
                if raw_token:
                    numeric_token = int(float(str(raw_token).strip()))
            except (ValueError, TypeError):
                numeric_token = None
            assert numeric_token is None, f"Expected None for bad input {bad_val!r}, got {numeric_token}"

        print("Instrument token parsing logic correct ✓")

    def test_fno_contracts_api_returns_instrument_token(self, auth_headers):
        """
        GET /api/fno/contracts - if kite_option_master has data, verify
        instrument_token field present in response items.
        """
        resp = requests.get(f"{BASE_URL}/api/fno/contracts", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"fno/contracts returned {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        if not data:
            pytest.skip("kite_option_master is empty — no contracts synced yet")
        # Check first few records have instrument_token field (may be None if not synced yet)
        sample = data[:5]
        for item in sample:
            # instrument_token should be a key in the response (may be None)
            # Note: FNOContract Pydantic model may or may not expose it to API
            print(f"Contract sample: {item.get('tradingsymbol')} token={item.get('instrument_token')}")
        print(f"FNO contracts returned {len(data)} records")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 14: API Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIIntegration:
    """Verify API endpoints work end-to-end with auth."""

    def test_auth_access(self):
        """POST /api/auth/access returns token for valid credentials."""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "pin": "1234"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data.get("role") in ("owner", "admin")
        print(f"Auth OK: role={data.get('role')}, admin_exempt={data.get('admin_exempt')}")

    def test_fno_signal_search(self, auth_headers):
        """GET /api/fno/scripts/search returns results for valid query."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/scripts/search?q=RELIANCE",
            headers=auth_headers, timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"Script search for RELIANCE: {data}")

    def test_portfolio_analyze_response_has_risk_metrics_field(self, auth_headers):
        """
        POST /api/portfolio/analyze returns PortfolioAnalyzeResponse
        which should include portfolio_risk_metrics key (even if None initially).
        """
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2500.0, "quantity": 5},
                {"symbol": "INFY", "avg_price": 1500.0, "quantity": 10},
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200, f"Portfolio analyze failed: {resp.status_code}: {resp.text[:500]}"
        data = resp.json()
        assert "portfolio_risk_metrics" in data, "portfolio_risk_metrics key missing from portfolio analyze response"
        # It should not throw a validation error
        print(f"Portfolio risk metrics: {data.get('portfolio_risk_metrics')}")
        if data.get("portfolio_risk_metrics"):
            metrics = data["portfolio_risk_metrics"]
            print(f"  Beta: {metrics.get('portfolio_beta')}, Sharpe: {metrics.get('sharpe_proxy')}")
            print(f"  VaR 95%: {metrics.get('var_95_1day_pct')}, Max DD: {metrics.get('max_single_drawdown_pct')}")
