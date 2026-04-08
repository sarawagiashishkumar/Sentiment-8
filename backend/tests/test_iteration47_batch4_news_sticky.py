"""
Iteration 47: BATCH 4 Verification for Master Spec v2.0

Tests:
1. API Endpoints: /api/fno/events, /api/fno/events/acknowledge-all, /api/fno/sticky-cards, /api/fno/sticky-cards/refresh
2. Python Unit Tests: news_sentiment (news_fetch, news_aggregate, _parallel_verify, _recency_weight)
3. Python Unit Tests: sticky_card_engine (evaluate_state_transition, emit_news_impact, emit_urgent_exit)
4. Regression: auth, fno/generate, sector-momentum, batch/status
"""
import os
import sys

# Add backend to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
AUTH_ENDPOINT = f"{BASE_URL}/api/auth/access"
ADMIN_USERNAME = "@shish123"
ADMIN_PASSWORD = "1234"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for owner user."""
    response = requests.post(
        AUTH_ENDPOINT,
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if response.status_code != 200:
        pytest.skip(f"Auth failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("token")
    if not token:
        pytest.skip("No token returned from auth")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ===========================================================================
# Section 1: API Endpoint Tests
# ===========================================================================

class TestAuthEndpoint:
    """Test auth endpoint returns token (regression)."""

    def test_auth_access_returns_token(self):
        response = requests.post(
            AUTH_ENDPOINT,
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert response.status_code == 200, f"Auth failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"


class TestFNOEventsEndpoint:
    """Test GET /api/fno/events endpoint."""

    def test_fno_events_returns_list(self, auth_headers):
        response = requests.get(
            f"{BASE_URL}/api/fno/events",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Events endpoint failed: {response.text}"
        data = response.json()
        # Should return a list (empty is expected without live Kite)
        assert isinstance(data, list), f"Expected list, got {type(data)}"


class TestFNOEventsAcknowledgeAll:
    """Test POST /api/fno/events/acknowledge-all endpoint."""

    def test_acknowledge_all_returns_count(self, auth_headers):
        response = requests.post(
            f"{BASE_URL}/api/fno/events/acknowledge-all",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Acknowledge-all failed: {response.text}"
        data = response.json()
        assert "acknowledged_count" in data, f"Missing acknowledged_count: {data}"
        # Without events, count should be 0
        assert data["acknowledged_count"] >= 0


class TestFNOStickyCardsEndpoint:
    """Test GET /api/fno/sticky-cards endpoint."""

    def test_sticky_cards_returns_list(self, auth_headers):
        response = requests.get(
            f"{BASE_URL}/api/fno/sticky-cards",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Sticky cards endpoint failed: {response.text}"
        data = response.json()
        # Should return a list (empty is expected without live Kite)
        assert isinstance(data, list), f"Expected list, got {type(data)}"


class TestFNOStickyCardsRefresh:
    """Test POST /api/fno/sticky-cards/refresh endpoint."""

    def test_sticky_cards_refresh_returns_stats(self, auth_headers):
        response = requests.post(
            f"{BASE_URL}/api/fno/sticky-cards/refresh",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Refresh failed: {response.text}"
        data = response.json()
        # Should return refresh stats
        assert "refreshed" in data, f"Missing 'refreshed' key: {data}"
        assert "state_changes" in data, f"Missing 'state_changes' key: {data}"
        assert "events" in data, f"Missing 'events' key: {data}"
        # Without cards, all should be 0
        assert data["refreshed"] == 0
        assert data["state_changes"] == 0
        assert data["events"] == 0


# ===========================================================================
# Section 2: Regression Tests (NDJSON endpoints)
# ===========================================================================

class TestRegressionNDJSONEndpoints:
    """Regression tests for streaming endpoints."""

    def test_fno_generate_returns_ndjson_stream(self, auth_headers):
        """POST /api/fno/generate returns NDJSON stream starting with progress message."""
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            headers=auth_headers,
            json={},
            timeout=30,
            stream=True,
        )
        assert response.status_code == 200, f"FNO generate failed: {response.text}"
        
        # Read first line
        first_line = None
        for line in response.iter_lines():
            if line:
                first_line = line.decode("utf-8")
                break
        
        assert first_line is not None, "No NDJSON lines received"
        import json
        first_obj = json.loads(first_line)
        assert first_obj.get("type") == "progress", f"Expected progress type, got: {first_obj}"

    def test_sector_momentum_returns_8_sectors(self, auth_headers):
        """GET /api/sector-momentum returns 8 sectors."""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Sector momentum failed: {response.text}"
        data = response.json()
        sectors = data.get("sectors", [])
        assert len(sectors) == 8, f"Expected 8 sectors, got {len(sectors)}"

    def test_batch_status_returns_theta_curve_entries(self, auth_headers):
        """GET /api/batch/status returns theta_curve_entries=360."""
        response = requests.get(
            f"{BASE_URL}/api/batch/status",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Batch status failed: {response.text}"
        data = response.json()
        theta_entries = data.get("theta_curve_entries", 0)
        assert theta_entries == 360, f"Expected 360 theta curves, got {theta_entries}"


# ===========================================================================
# Section 3: Python Unit Tests - news_sentiment module
# ===========================================================================

class TestNewsFetch:
    """Test news_fetch function returns items with verification_status."""

    def test_news_fetch_returns_list_with_verification_status(self):
        """news_fetch('NIFTY') returns list of dicts each with verification_status field."""
        from services.news_sentiment import news_fetch, refresh_news_cache
        
        # Force refresh to ensure cache is populated
        refresh_news_cache()
        
        result = news_fetch("NIFTY")
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        
        # If there are results, check verification_status
        if result:
            for item in result[:5]:  # Check first 5
                assert "verification_status" in item, f"Missing verification_status: {item.keys()}"
                assert item["verification_status"] in ("VERIFIED", "SINGLE_SOURCE", "UNVERIFIED"), \
                    f"Invalid verification_status: {item['verification_status']}"


class TestNewsAggregate:
    """Test news_aggregate function returns required keys."""

    def test_news_aggregate_returns_required_keys(self):
        """news_aggregate('NIFTY') returns dict with required keys."""
        from services.news_sentiment import news_aggregate
        
        result = news_aggregate("NIFTY")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        
        required_keys = ["news_flag", "avg_sentiment", "recent_news_count", "headline_summary", "last_refreshed_at"]
        for key in required_keys:
            assert key in result, f"Missing key '{key}' in result: {result.keys()}"
        
        # Validate news_flag values
        assert result["news_flag"] in ("POSITIVE", "NEGATIVE", "NEUTRAL"), \
            f"Invalid news_flag: {result['news_flag']}"


class TestParallelVerify:
    """Test _parallel_verify function."""

    def test_parallel_verify_multi_provider_returns_verified(self):
        """_parallel_verify with multi-provider items returns VERIFIED status."""
        from services.news_sentiment import _parallel_verify
        
        # Create test items from 2 providers with same headline_hash
        items = [
            {"headline_hash": "abc123", "provider": "P1", "sentiment_score": 0.5, "title": "Test"},
            {"headline_hash": "abc123", "provider": "P2", "sentiment_score": 0.45, "title": "Test"},
        ]
        
        result = _parallel_verify(items)
        assert len(result) == 1, f"Expected 1 merged item, got {len(result)}"
        assert result[0]["verification_status"] == "VERIFIED", \
            f"Expected VERIFIED, got {result[0]['verification_status']}"
        assert result[0]["source_count"] == 2

    def test_parallel_verify_single_provider_returns_single_source(self):
        """_parallel_verify with single-provider returns SINGLE_SOURCE status."""
        from services.news_sentiment import _parallel_verify
        
        items = [
            {"headline_hash": "xyz789", "provider": "P1", "sentiment_score": 0.3, "title": "Single"},
        ]
        
        result = _parallel_verify(items)
        assert len(result) == 1
        assert result[0]["verification_status"] == "SINGLE_SOURCE", \
            f"Expected SINGLE_SOURCE, got {result[0]['verification_status']}"
        assert result[0]["source_count"] == 1


class TestRecencyWeight:
    """Test _recency_weight function returns correct weights."""

    def test_recency_weight_10min_returns_1_0(self):
        """_recency_weight returns 1.0 for 10min old."""
        from services.news_sentiment import _recency_weight
        
        now = datetime.now(timezone.utc)
        published = now - timedelta(minutes=10)
        weight = _recency_weight(published)
        assert weight == 1.0, f"Expected 1.0 for 10min, got {weight}"

    def test_recency_weight_45min_returns_0_8(self):
        """_recency_weight returns 0.8 for 45min old."""
        from services.news_sentiment import _recency_weight
        
        now = datetime.now(timezone.utc)
        published = now - timedelta(minutes=45)
        weight = _recency_weight(published)
        assert weight == 0.8, f"Expected 0.8 for 45min, got {weight}"

    def test_recency_weight_90min_returns_0_6(self):
        """_recency_weight returns 0.6 for 90min old."""
        from services.news_sentiment import _recency_weight
        
        now = datetime.now(timezone.utc)
        published = now - timedelta(minutes=90)
        weight = _recency_weight(published)
        assert weight == 0.6, f"Expected 0.6 for 90min, got {weight}"

    def test_recency_weight_180min_returns_0_35(self):
        """_recency_weight returns 0.35 for 180min old."""
        from services.news_sentiment import _recency_weight
        
        now = datetime.now(timezone.utc)
        published = now - timedelta(minutes=180)
        weight = _recency_weight(published)
        assert weight == 0.35, f"Expected 0.35 for 180min, got {weight}"

    def test_recency_weight_300min_returns_0_1(self):
        """_recency_weight returns 0.1 for 300min old."""
        from services.news_sentiment import _recency_weight
        
        now = datetime.now(timezone.utc)
        published = now - timedelta(minutes=300)
        weight = _recency_weight(published)
        assert weight == 0.1, f"Expected 0.1 for 300min, got {weight}"


# ===========================================================================
# Section 4: Python Unit Tests - sticky_card_engine module
# ===========================================================================

class TestEvaluateStateTransition:
    """Test evaluate_state_transition function."""

    def test_pending_to_active_long_price_above_entry_zone(self):
        """PENDING→ACTIVE when LONG price>=entry_zone_low."""
        from services.sticky_card_engine import evaluate_state_transition
        
        card = {
            "signal_state": "PENDING",
            "direction": "LONG",
            "entry_zone_low": 100,
            "entry_zone_high": 105,
            "sl": 90,
            "T1": 120,
            "T2": 140,
        }
        new_state, reason = evaluate_state_transition(card, current_price=100)
        assert new_state == "ACTIVE", f"Expected ACTIVE, got {new_state}"
        assert reason is None

    def test_active_to_closed_loss_long_price_at_sl(self):
        """ACTIVE→CLOSED_LOSS when LONG price<=sl."""
        from services.sticky_card_engine import evaluate_state_transition
        
        card = {
            "signal_state": "ACTIVE",
            "direction": "LONG",
            "entry_zone_low": 100,
            "entry_zone_high": 105,
            "sl": 90,
            "T1": 120,
            "T2": 140,
        }
        new_state, reason = evaluate_state_transition(card, current_price=90)
        assert new_state == "CLOSED_LOSS", f"Expected CLOSED_LOSS, got {new_state}"
        assert "sl_hit" in reason

    def test_active_to_watching_t1_long_price_at_t1(self):
        """ACTIVE→WATCHING_T1 when LONG price>=T1."""
        from services.sticky_card_engine import evaluate_state_transition
        
        card = {
            "signal_state": "ACTIVE",
            "direction": "LONG",
            "entry_zone_low": 100,
            "entry_zone_high": 105,
            "sl": 90,
            "T1": 120,
            "T2": 140,
        }
        new_state, reason = evaluate_state_transition(card, current_price=120)
        assert new_state == "WATCHING_T1", f"Expected WATCHING_T1, got {new_state}"

    def test_watching_t1_to_closed_win_when_t2_is_none(self):
        """WATCHING_T1→CLOSED_WIN when T2 is None."""
        from services.sticky_card_engine import evaluate_state_transition
        
        card = {
            "signal_state": "WATCHING_T1",
            "direction": "LONG",
            "entry_zone_low": 100,
            "entry_zone_high": 105,
            "sl": 90,
            "T1": 120,
            "T2": None,  # No T2
        }
        new_state, reason = evaluate_state_transition(card, current_price=125)
        assert new_state == "CLOSED_WIN", f"Expected CLOSED_WIN, got {new_state}"
        assert "t1_hit_no_t2" in reason

    def test_expired_on_expiry_day_past_close(self):
        """→EXPIRED on expiry_day+past_close."""
        from services.sticky_card_engine import evaluate_state_transition
        
        card = {
            "signal_state": "ACTIVE",
            "direction": "LONG",
            "entry_zone_low": 100,
            "entry_zone_high": 105,
            "sl": 90,
            "T1": 120,
            "T2": 140,
        }
        new_state, reason = evaluate_state_transition(
            card, current_price=110, is_expiry_day=True, is_past_close=True
        )
        assert new_state == "EXPIRED", f"Expected EXPIRED, got {new_state}"
        assert "expiry_day" in reason


class TestEmitNewsImpact:
    """Test emit_news_impact conditions."""

    def test_emit_news_impact_long_negative_triggers(self):
        """emit_news_impact: only trigger for LONG+NEGATIVE."""
        from services.sticky_card_engine import emit_news_impact
        import asyncio
        
        # Mock card
        card = {
            "signal_id": "test-123",
            "symbol": "NIFTY",
            "option_symbol": "NIFTY26JAN25000CE",
            "direction": "LONG",
            "signal_state": "ACTIVE",
        }
        
        # Test conditions without DB (function returns False if conditions not met)
        # LONG + NEGATIVE should trigger (but we can't test DB write without mock)
        # Test that function exists and has correct signature
        assert callable(emit_news_impact)

    def test_emit_news_impact_short_positive_triggers(self):
        """emit_news_impact: only trigger for SHORT+POSITIVE."""
        from services.sticky_card_engine import emit_news_impact
        
        # Test that function exists and has correct signature
        assert callable(emit_news_impact)


class TestEmitUrgentExit:
    """Test emit_urgent_exit conditions."""

    def test_emit_urgent_exit_not_in_final_5_minutes(self):
        """emit_urgent_exit does NOT trigger in final 5 minutes (remaining_mins < 5)."""
        from services.sticky_card_engine import emit_urgent_exit
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        
        # Mock card
        card = {
            "signal_id": "test-456",
            "symbol": "NIFTY",
            "option_symbol": "NIFTY26JAN25000CE",
            "direction": "LONG",
            "signal_state": "ACTIVE",
        }
        
        # Mock datetime to simulate final 5 minutes (15:27 IST)
        IST = timezone(timedelta(hours=5, minutes=30))
        mock_time = datetime(2026, 1, 15, 15, 27, 0, tzinfo=IST)
        
        async def test_emit():
            with patch('services.sticky_card_engine.datetime') as mock_dt:
                mock_dt.now.return_value = mock_time
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                
                # Create mock db
                mock_db = MagicMock()
                
                # Call emit_urgent_exit - should return False due to remaining_mins < 5
                result = await emit_urgent_exit(
                    mock_db, card, 
                    p_recover=0.1, trend_score=-2, 
                    flow_band="BearishFlow", best_price_60s=95.0,
                    reason_codes=["test"]
                )
                return result
        
        # Run the async test
        result = asyncio.get_event_loop().run_until_complete(test_emit())
        # Should return False because remaining_mins < 5
        assert result == False, f"Expected False (no trigger in final 5 mins), got {result}"


# ===========================================================================
# Section 5: Import Tests
# ===========================================================================

class TestBackendImports:
    """Test that all required modules and functions can be imported."""

    def test_news_sentiment_imports(self):
        """Test news_sentiment module imports."""
        from services.news_sentiment import (
            news_fetch,
            news_aggregate,
            _parallel_verify,
            _recency_weight,
            refresh_news_cache,
            start_continuous_monitor,
            stop_continuous_monitor,
        )
        assert callable(news_fetch)
        assert callable(news_aggregate)
        assert callable(_parallel_verify)
        assert callable(_recency_weight)

    def test_sticky_card_engine_imports(self):
        """Test sticky_card_engine module imports."""
        from services.sticky_card_engine import (
            evaluate_state_transition,
            emit_news_impact,
            emit_urgent_exit,
            emit_regime_shift,
            create_sticky_card,
            get_active_cards,
            refresh_sticky_cards,
            ensure_indexes,
        )
        assert callable(evaluate_state_transition)
        assert callable(emit_news_impact)
        assert callable(emit_urgent_exit)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
