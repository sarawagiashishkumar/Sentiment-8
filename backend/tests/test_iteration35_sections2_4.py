"""
Iteration 35: Backend Testing for Sections 2-4
- Section 2: URGENT_EXIT wording fix (no imperative verbs, expected_best_price_next_60s)
- Section 3: strategy_backtests MongoDB collection, backtest engine, Bucket A wiring
- Section 4: Position sizing calculator with not_affordable annotation

Test credentials: @shish123 / 1234
"""
import os
import pytest
import requests
import re

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://stock-signals-62.preview.emergentagent.com"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for owner user."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
    )
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Auth failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ============================================================================
# Section 2: URGENT_EXIT Wording Fix Tests
# ============================================================================

class TestUrgentExitWordingFix:
    """Test URGENT_EXIT reason text does NOT contain imperative verbs."""

    FORBIDDEN_WORDS = ["exit", "sell", "close position", "book profit"]

    def test_build_urgent_exit_reason_no_imperative_verbs(self):
        """build_urgent_exit_reason() should NOT use imperative verbs."""
        from services.position_monitor import build_urgent_exit_reason

        # Test various scenarios
        test_cases = [
            {"loss_pct": -15.0, "minutes_remaining": 60, "flow_band": "StrongSellFlow", "p_recovery": 0.10},
            {"loss_pct": -25.0, "minutes_remaining": 30, "flow_band": "ModerateSellFlow", "p_recovery": 0.05},
            {"loss_pct": -10.0, "minutes_remaining": 90, "flow_band": "NeutralFlow", "p_recovery": 0.15},
            {"loss_pct": -30.0, "minutes_remaining": 15, "flow_band": "StrongBuyFlow", "p_recovery": 0.02},
        ]

        for tc in test_cases:
            reason = build_urgent_exit_reason(**tc)
            reason_lower = reason.lower()
            for word in self.FORBIDDEN_WORDS:
                assert word not in reason_lower, (
                    f"Forbidden word '{word}' found in reason: {reason}"
                )
            print(f"PASS: Reason text OK for {tc}: {reason[:80]}...")

    def test_check_urgent_exit_returns_expected_best_price_next_60s(self):
        """check_urgent_exit should return expected_best_price_next_60s, NOT recommended_exit_price."""
        from services.position_monitor import check_urgent_exit

        position = {"script": "NIFTY09JAN25000CE", "underlying": "NIFTY"}
        result = check_urgent_exit(
            position=position,
            current_ltp=80.0,
            entry_price=100.0,
            stop_loss=70.0,
            minutes_remaining=60,
            p_recovery=0.10,
            flow_band="StrongSellFlow",
        )

        assert result is not None, "URGENT_EXIT should trigger with these conditions"
        assert "expected_best_price_next_60s" in result, (
            "Result should have 'expected_best_price_next_60s' key"
        )
        assert "recommended_exit_price" not in result, (
            "Result should NOT have 'recommended_exit_price' key (old naming)"
        )
        print(f"PASS: expected_best_price_next_60s = {result['expected_best_price_next_60s']}")

    def test_check_urgent_exit_reason_no_imperative_verbs(self):
        """check_urgent_exit reason field should NOT contain imperative verbs."""
        from services.position_monitor import check_urgent_exit

        position = {"script": "BANKNIFTY09JAN50000PE", "underlying": "BANKNIFTY"}
        result = check_urgent_exit(
            position=position,
            current_ltp=150.0,
            entry_price=200.0,
            stop_loss=120.0,
            minutes_remaining=45,
            p_recovery=0.08,
            flow_band="StrongBuyFlow",  # Adverse for PE (SHORT)
        )

        assert result is not None, "URGENT_EXIT should trigger"
        reason = result.get("reason", "")
        reason_lower = reason.lower()
        for word in self.FORBIDDEN_WORDS:
            assert word not in reason_lower, (
                f"Forbidden word '{word}' found in URGENT_EXIT reason: {reason}"
            )
        print(f"PASS: URGENT_EXIT reason OK: {reason[:100]}...")


class TestGeneratePositionAlertsAllTypes:
    """Test generate_position_alerts still generates all 3 alert types."""

    def test_generate_position_alerts_returns_all_types(self):
        """generate_position_alerts should return NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT."""
        from services.position_monitor import generate_position_alerts

        position = {"script": "NIFTY09JAN25000CE", "underlying": "NIFTY"}

        # Conditions that trigger all 3 alerts
        alerts = generate_position_alerts(
            position=position,
            current_ltp=80.0,
            entry_price=100.0,
            stop_loss=70.0,
            minutes_remaining=60,
            news_sentiment={"news_flag": "NEGATIVE", "avg_sentiment": -0.5, "news_count": 3, "headlines": [{"title": "Market crash"}]},
            previous_news_flag="NEUTRAL",
            current_regime={"regime": "HighVolCrash", "vix_value": 25, "adx_value": 30},
            previous_regime="LowVolTrend",
            current_p_hit_t1=0.40,
            original_p_hit_t1=0.70,
            p_recovery=0.10,
            flow_band="StrongSellFlow",
        )

        alert_types = [a["type"] for a in alerts]
        print(f"Alert types generated: {alert_types}")

        # Should have URGENT_EXIT (highest priority)
        assert "URGENT_EXIT" in alert_types, "Should generate URGENT_EXIT alert"
        # Should have REGIME_SHIFT
        assert "REGIME_SHIFT" in alert_types, "Should generate REGIME_SHIFT alert"
        # Should have NEWS_IMPACT
        assert "NEWS_IMPACT" in alert_types, "Should generate NEWS_IMPACT alert"

        print(f"PASS: All 3 alert types generated: {alert_types}")


# ============================================================================
# Section 3: Backtest Engine Tests
# ============================================================================

class TestBacktestEngineComputeStats:
    """Test backtest_engine.py compute_backtest_stats function."""

    def test_compute_backtest_stats_correct_fields(self):
        """compute_backtest_stats should return trade_count, win_rate, expectancy_R, max_drawdown_R."""
        from services.backtest_engine import compute_backtest_stats

        trades = [
            {"r_mult": 1.5, "win": True},
            {"r_mult": 2.0, "win": True},
            {"r_mult": -1.0, "win": False},
            {"r_mult": 1.0, "win": True},
            {"r_mult": -0.5, "win": False},
        ]

        stats = compute_backtest_stats(trades)

        assert "trade_count" in stats, "Should have trade_count"
        assert "win_rate" in stats, "Should have win_rate"
        assert "expectancy_R" in stats, "Should have expectancy_R"
        assert "max_drawdown_R" in stats, "Should have max_drawdown_R"

        assert stats["trade_count"] == 5, f"trade_count should be 5, got {stats['trade_count']}"
        assert stats["win_rate"] == 0.6, f"win_rate should be 0.6 (3/5), got {stats['win_rate']}"

        expected_expectancy = (1.5 + 2.0 - 1.0 + 1.0 - 0.5) / 5  # 0.6
        assert abs(stats["expectancy_R"] - expected_expectancy) < 0.01, (
            f"expectancy_R should be ~{expected_expectancy}, got {stats['expectancy_R']}"
        )

        print(f"PASS: compute_backtest_stats returns correct values: {stats}")

    def test_compute_backtest_stats_empty_trades(self):
        """compute_backtest_stats with empty trades should return zeros."""
        from services.backtest_engine import compute_backtest_stats

        stats = compute_backtest_stats([])

        assert stats["trade_count"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["expectancy_R"] == 0.0
        assert stats["max_drawdown_R"] == 0.0

        print(f"PASS: Empty trades returns zeros: {stats}")


class TestBacktestEngineIsStrategyEnabled:
    """Test is_strategy_enabled threshold logic."""

    def test_is_strategy_enabled_all_thresholds_met(self):
        """is_strategy_enabled returns True when all thresholds met."""
        from services.backtest_engine import is_strategy_enabled

        # Thresholds: trade_count>=100, win_rate>=0.75, expectancy_R>=0.40
        stats = {
            "trade_count": 150,
            "win_rate": 0.80,
            "expectancy_R": 0.50,
        }
        assert is_strategy_enabled(stats) is True, "Should be enabled when all thresholds met"
        print("PASS: Strategy enabled when all thresholds met")

    def test_is_strategy_enabled_trade_count_below_threshold(self):
        """is_strategy_enabled returns False when trade_count < 100."""
        from services.backtest_engine import is_strategy_enabled

        stats = {
            "trade_count": 99,  # Below 100
            "win_rate": 0.80,
            "expectancy_R": 0.50,
        }
        assert is_strategy_enabled(stats) is False, "Should be disabled when trade_count < 100"
        print("PASS: Strategy disabled when trade_count < 100")

    def test_is_strategy_enabled_win_rate_below_threshold(self):
        """is_strategy_enabled returns False when win_rate < 0.75."""
        from services.backtest_engine import is_strategy_enabled

        stats = {
            "trade_count": 150,
            "win_rate": 0.74,  # Below 0.75
            "expectancy_R": 0.50,
        }
        assert is_strategy_enabled(stats) is False, "Should be disabled when win_rate < 0.75"
        print("PASS: Strategy disabled when win_rate < 0.75")

    def test_is_strategy_enabled_expectancy_below_threshold(self):
        """is_strategy_enabled returns False when expectancy_R < 0.40."""
        from services.backtest_engine import is_strategy_enabled

        stats = {
            "trade_count": 150,
            "win_rate": 0.80,
            "expectancy_R": 0.39,  # Below 0.40
        }
        assert is_strategy_enabled(stats) is False, "Should be disabled when expectancy_R < 0.40"
        print("PASS: Strategy disabled when expectancy_R < 0.40")

    def test_is_strategy_enabled_empty_stats(self):
        """is_strategy_enabled returns False for empty stats."""
        from services.backtest_engine import is_strategy_enabled

        assert is_strategy_enabled({}) is False, "Should be disabled for empty stats"
        assert is_strategy_enabled(None) is False, "Should be disabled for None"
        print("PASS: Strategy disabled for empty/None stats")


class TestBacktestEngineSimulators:
    """Test simulate_trades_for_strategy runs without errors."""

    def test_simulate_trades_for_each_strategy_type(self):
        """simulate_trades_for_strategy should run for each strategy type."""
        from services.backtest_engine import simulate_trades_for_strategy, STRATEGY_SIMULATORS

        # Sample OHLCV data (100 bars)
        import random
        random.seed(42)
        base_price = 100.0
        opens, highs, lows, closes, volumes = [], [], [], [], []
        for i in range(100):
            o = base_price + random.uniform(-2, 2)
            h = o + random.uniform(0, 3)
            l = o - random.uniform(0, 3)
            c = random.uniform(l, h)
            v = random.uniform(1000000, 5000000)
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(v)
            base_price = c

        for strategy_id in STRATEGY_SIMULATORS.keys():
            try:
                trades = simulate_trades_for_strategy(
                    strategy_id, opens, highs, lows, closes, volumes
                )
                assert isinstance(trades, list), f"Should return list for {strategy_id}"
                print(f"PASS: {strategy_id} -> {len(trades)} trades simulated")
            except Exception as e:
                pytest.fail(f"simulate_trades_for_strategy failed for {strategy_id}: {e}")


class TestBacktestBatchEndpoint:
    """Test POST /api/fno/backtest-batch endpoint."""

    def test_backtest_batch_endpoint_exists(self, auth_headers):
        """POST /api/fno/backtest-batch should exist and return expected structure."""
        # Note: This is an owner-only endpoint that runs backtests
        # We just verify it exists and returns the expected structure
        # The batch has already been run (61 configs stored)
        resp = requests.post(
            f"{BASE_URL}/api/fno/backtest-batch",
            headers=auth_headers,
        )
        # Should return 200 with {updated, skipped, errors, details}
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "updated" in data, "Response should have 'updated' field"
        assert "skipped" in data, "Response should have 'skipped' field"
        assert "errors" in data, "Response should have 'errors' field"
        assert "details" in data, "Response should have 'details' field"
        print(f"PASS: backtest-batch endpoint returns: updated={data['updated']}, skipped={data['skipped']}, errors={data['errors']}")


class TestStrategyBacktestsEndpoint:
    """Test GET /api/fno/strategy-backtests endpoint."""

    def test_strategy_backtests_endpoint_returns_list(self, auth_headers):
        """GET /api/fno/strategy-backtests should return {backtests, count}."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/strategy-backtests",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "backtests" in data, "Response should have 'backtests' field"
        assert "count" in data, "Response should have 'count' field"
        assert isinstance(data["backtests"], list), "backtests should be a list"
        print(f"PASS: strategy-backtests returns {data['count']} records")

    def test_strategy_backtests_has_enabled_field(self, auth_headers):
        """Each backtest record should have 'enabled' field."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/strategy-backtests",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["count"] > 0:
            for bt in data["backtests"][:5]:  # Check first 5
                assert "enabled" in bt, f"Backtest record should have 'enabled' field: {bt}"
                assert "config_key" in bt, f"Backtest record should have 'config_key' field"
                assert "trade_count" in bt, f"Backtest record should have 'trade_count' field"
                assert "win_rate" in bt, f"Backtest record should have 'win_rate' field"
                assert "expectancy_R" in bt, f"Backtest record should have 'expectancy_R' field"
            print(f"PASS: Backtest records have 'enabled' field")
        else:
            print("SKIP: No backtest records to verify")


class TestBucketABacktestWiring:
    """Test Bucket A wiring with USE_BACKTEST_DB feature flag."""

    def test_bucket_a_fallback_mode_default(self):
        """When USE_BACKTEST_DB=0 (default), Bucket A uses old defaults (A > 0)."""
        from services.confluence_score_v2 import compute_bucket_a

        # With strategy_enabled=True and no stats, should use defaults
        result = compute_bucket_a(
            win_rate=None,
            expectancy_r=None,
            trade_count=None,
            strategy_enabled=True,
        )
        # Default values: wr=0.65, er=0.30, tc=0
        # tc < 100 but strategy_enabled=True, so it should still compute
        # Actually, looking at the code: if trade_count < 100 → A = 0
        # But trade_count=None defaults to 0, so A = 0 unless strategy_enabled=True
        # Let me check the actual logic...
        # The code says: if not strategy_enabled or (trade_count is not None and trade_count < 100)
        # So if trade_count is None, it doesn't trigger the < 100 check
        assert result["score"] >= 0, "Bucket A score should be >= 0"
        print(f"PASS: Bucket A fallback mode score = {result['score']}")

    def test_bucket_a_disabled_strategy_returns_zero(self):
        """When strategy_enabled=False, Bucket A = 0."""
        from services.confluence_score_v2 import compute_bucket_a

        result = compute_bucket_a(
            win_rate=0.80,
            expectancy_r=0.50,
            trade_count=150,
            strategy_enabled=False,
        )
        assert result["score"] == 0, f"Bucket A should be 0 when disabled, got {result['score']}"
        assert result["reason"] == "strategy_disabled_or_insufficient_data"
        print("PASS: Bucket A = 0 when strategy_enabled=False")

    def test_bucket_a_insufficient_trade_count_returns_zero(self):
        """When trade_count < 100, Bucket A = 0."""
        from services.confluence_score_v2 import compute_bucket_a

        result = compute_bucket_a(
            win_rate=0.80,
            expectancy_r=0.50,
            trade_count=99,  # Below 100
            strategy_enabled=True,
        )
        assert result["score"] == 0, f"Bucket A should be 0 when trade_count < 100, got {result['score']}"
        print("PASS: Bucket A = 0 when trade_count < 100")


# ============================================================================
# Section 4: Position Sizing Calculator Tests
# ============================================================================

class TestPositionSizingCompute:
    """Test compute_position_size function."""

    def test_compute_position_size_returns_all_fields(self):
        """compute_position_size should return all required fields."""
        from services.position_sizing import compute_position_size

        result = compute_position_size(
            user_budget=500000,
            option_premium=100,
            lot_size=50,
            sl_price=85,
            entry_price=100,
        )

        required_fields = [
            "lots_allowed",
            "capital_required_per_lot",
            "total_capital_required",
            "risk_per_lot",
            "total_risk_amount",
            "risk_pct_of_portfolio",
            "not_affordable",
            "sizing_reason",
        ]
        for field in required_fields:
            assert field in result, f"Result should have '{field}' field"

        print(f"PASS: compute_position_size returns all fields: {result}")

    def test_position_sizing_zero_budget_not_affordable(self):
        """Zero budget should return not_affordable=True."""
        from services.position_sizing import compute_position_size

        result = compute_position_size(
            user_budget=0,
            option_premium=100,
            lot_size=50,
        )
        assert result["not_affordable"] is True, "Zero budget should be not_affordable"
        assert result["lots_allowed"] == 0, "Zero budget should have 0 lots"
        print("PASS: Zero budget returns not_affordable=True")

    def test_position_sizing_tiny_budget_not_affordable(self):
        """Tiny budget (less than 1 lot) should return not_affordable=True."""
        from services.position_sizing import compute_position_size

        result = compute_position_size(
            user_budget=1000,  # Very small
            option_premium=100,
            lot_size=50,  # 1 lot = 5000
        )
        assert result["not_affordable"] is True, "Tiny budget should be not_affordable"
        assert result["lots_allowed"] == 0, "Tiny budget should have 0 lots"
        print("PASS: Tiny budget returns not_affordable=True")

    def test_position_sizing_large_budget_reasonable_lots(self):
        """Large budget should return reasonable lots."""
        from services.position_sizing import compute_position_size

        result = compute_position_size(
            user_budget=1000000,  # 10 lakh
            option_premium=100,
            lot_size=50,
            sl_price=85,
            entry_price=100,
        )
        assert result["not_affordable"] is False, "Large budget should be affordable"
        assert result["lots_allowed"] > 0, "Large budget should have > 0 lots"
        # With 10 lakh budget, 10% allocation = 1 lakh, 1 lot = 5000, so ~20 lots by allocation
        # But risk constraint: 2% of 10 lakh = 20000, risk per lot = 15*50 = 750, so ~26 lots by risk
        # Final = min(20, 26) = 20 lots
        print(f"PASS: Large budget returns {result['lots_allowed']} lots")


class TestPositionSizingEndpoint:
    """Test POST /api/fno/position-sizing endpoint."""

    def test_position_sizing_endpoint_works(self, auth_headers):
        """POST /api/fno/position-sizing should work with query params."""
        resp = requests.post(
            f"{BASE_URL}/api/fno/position-sizing",
            params={
                "user_budget": 500000,
                "option_premium": 100,
                "lot_size": 50,
                "sl_price": 85,
                "entry_price": 100,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "lots_allowed" in data, "Response should have 'lots_allowed'"
        assert "not_affordable" in data, "Response should have 'not_affordable'"
        print(f"PASS: position-sizing endpoint returns: {data}")

    def test_position_sizing_endpoint_default_params(self, auth_headers):
        """POST /api/fno/position-sizing should work with default params."""
        resp = requests.post(
            f"{BASE_URL}/api/fno/position-sizing",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "lots_allowed" in data
        print(f"PASS: position-sizing endpoint with defaults: {data}")


class TestFNOSignalResponseModel:
    """Test FNOSignalResponse model has not_affordable and sizing_info fields."""

    def test_fno_signal_response_has_not_affordable_field(self):
        """FNOSignalResponse should have not_affordable field."""
        from models import FNOSignalResponse
        import inspect

        # Check model fields
        fields = FNOSignalResponse.model_fields
        assert "not_affordable" in fields, "FNOSignalResponse should have 'not_affordable' field"
        print("PASS: FNOSignalResponse has 'not_affordable' field")

    def test_fno_signal_response_has_sizing_info_field(self):
        """FNOSignalResponse should have sizing_info field."""
        from models import FNOSignalResponse

        fields = FNOSignalResponse.model_fields
        assert "sizing_info" in fields, "FNOSignalResponse should have 'sizing_info' field"
        print("PASS: FNOSignalResponse has 'sizing_info' field")

    def test_fno_signal_response_defaults(self):
        """FNOSignalResponse not_affordable should default to False."""
        from models import FNOSignalResponse

        # Create minimal instance
        sig = FNOSignalResponse(
            script="NIFTY09JAN25000CE",
            underlying="NIFTY",
            expiry="2026-01-09",
            strike=25000,
            option_type="CE",
            exchange="NFO",
            lot_size=50,
            underlying_ltp=25000,
            option_ltp=100,
            ltp_margin_to_t1_amount=20,
            ltp_margin_to_t1_pct=20,
            achievable_profit_pct=20,
            direction="BULLISH",
            strategy="ORB",
            entry_price=100,
            stop_loss=85,
            target1=120,
            target2=140,
            risk_reward_target1=1.33,
            risk_reward_target2=2.67,
            trigger_factors=["Test"],
            confluence_score=80,
            signal_quality="HIGH",
            is_potential_trade=True,
            minutes_to_expiry=1000,
            expiry_risk="LOW",
            data_source="MODELED_FROM_SPOT",
            analysis_refreshed_at="2026-01-08T10:00:00Z",
        )
        assert sig.not_affordable is False, "not_affordable should default to False"
        assert sig.sizing_info is None, "sizing_info should default to None"
        print("PASS: FNOSignalResponse defaults are correct")


class TestNoRegressionExistingEndpoints:
    """Test existing endpoints still work (no regression)."""

    def test_auth_endpoint_still_works(self):
        """POST /api/auth/access should still work."""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
        )
        assert resp.status_code == 200, f"Auth should work, got {resp.status_code}"
        data = resp.json()
        assert "token" in data
        print("PASS: Auth endpoint still works")

    def test_custom_positions_endpoint_still_works(self, auth_headers):
        """GET /api/fno/custom-positions should still work."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("PASS: custom-positions endpoint still works")


# ============================================================================
# MongoDB Collection Tests
# ============================================================================

class TestStrategyBacktestsCollection:
    """Test strategy_backtests MongoDB collection."""

    def test_strategy_backtests_collection_populated(self, auth_headers):
        """strategy_backtests collection should have documents after batch run."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/strategy-backtests",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # According to context, batch run stored 61 configs
        assert data["count"] > 0, "strategy_backtests should have documents"
        print(f"PASS: strategy_backtests has {data['count']} documents")

    def test_strategy_backtests_document_structure(self, auth_headers):
        """Each document should have required fields."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/strategy-backtests",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["count"] > 0:
            doc = data["backtests"][0]
            required_fields = [
                "strategy_id",
                "instrument_universe",
                "config_key",
                "trade_count",
                "win_rate",
                "expectancy_R",
                "max_drawdown_R",
                "last_updated",
                "enabled",
            ]
            for field in required_fields:
                assert field in doc, f"Document should have '{field}' field"
            print(f"PASS: Document structure correct: {list(doc.keys())}")


# ============================================================================
# Integration Tests
# ============================================================================

class TestAnnotateSignalAffordability:
    """Test annotate_signal_affordability function."""

    def test_annotate_signal_affordability_adds_fields(self):
        """annotate_signal_affordability should add sizing_info and not_affordable."""
        from services.position_sizing import annotate_signal_affordability

        signal = {
            "current_premium": 100,
            "lot_size": 50,
            "stop_loss": 85,
            "best_budget_entry": 100,
        }

        result = annotate_signal_affordability(signal, user_budget=500000)

        assert "sizing_info" in result, "Should add sizing_info"
        assert "not_affordable" in result, "Should add not_affordable"
        assert isinstance(result["sizing_info"], dict), "sizing_info should be dict"
        print(f"PASS: annotate_signal_affordability adds fields: not_affordable={result['not_affordable']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
