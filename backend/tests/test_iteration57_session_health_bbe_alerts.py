"""
Iteration 57: Session Health Monitor, Market Heatmap Card, BBE Alerts, Signal Performance Tracking

Tests:
1. Session Health Indicator - /api/kite/status returns connected status
2. Heartbeat endpoint - /api/heartbeat returns alive status
3. BBE Alerts endpoint - /api/fno/bbe-alerts returns alerts array with checked_at
4. Performance Stats endpoint - /api/fno/performance-stats returns total, wins, losses, win_rate
5. Signal History endpoint - /api/fno/signal-history returns history array
6. Signal Log endpoint - /api/fno/signal-log returns log array with signal data
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"},
        timeout=15
    )
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    """Auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {owner_token}"}


class TestHeartbeat:
    """Heartbeat endpoint tests"""

    def test_heartbeat_returns_alive_status(self):
        """Test /api/heartbeat returns status=alive with timestamp"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200, f"Heartbeat failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "alive", f"Expected status=alive, got {data}"
        assert "ts" in data, "Missing timestamp in heartbeat response"


class TestSessionHealth:
    """Session Health / Kite Status tests"""

    def test_kite_status_returns_connected(self, auth_headers):
        """Test /api/kite/status returns connected status"""
        resp = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200, f"Kite status failed: {resp.text}"
        data = resp.json()
        assert "connected" in data, "Missing 'connected' field in kite status"
        # connected can be True or False, just verify field exists
        assert isinstance(data["connected"], bool), "connected should be boolean"


class TestBBEAlerts:
    """BBE (Budget Entry) Alerts endpoint tests"""

    def test_bbe_alerts_returns_alerts_array(self, auth_headers):
        """Test /api/fno/bbe-alerts returns alerts array with checked_at"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/bbe-alerts",
            headers=auth_headers,
            timeout=15
        )
        assert resp.status_code == 200, f"BBE alerts failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "alerts" in data, "Missing 'alerts' field"
        assert isinstance(data["alerts"], list), "alerts should be a list"
        assert "checked_at" in data, "Missing 'checked_at' timestamp"
        assert "count" in data, "Missing 'count' field"
        
        # If alerts exist, verify structure
        if data["alerts"]:
            alert = data["alerts"][0]
            expected_fields = ["option_symbol", "direction", "entry_price", "best_budget_entry", "live_ltp"]
            for field in expected_fields:
                assert field in alert, f"Missing '{field}' in alert"


class TestPerformanceStats:
    """Performance Stats endpoint tests"""

    def test_performance_stats_returns_required_fields(self, auth_headers):
        """Test /api/fno/performance-stats returns total, wins, losses, win_rate"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/performance-stats",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200, f"Performance stats failed: {resp.text}"
        data = resp.json()
        
        # Verify required fields
        required_fields = ["total", "wins", "losses", "win_rate"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' in performance stats"
        
        # Verify types
        assert isinstance(data["total"], int), "total should be int"
        assert isinstance(data["wins"], int), "wins should be int"
        assert isinstance(data["losses"], int), "losses should be int"
        assert isinstance(data["win_rate"], (int, float)), "win_rate should be numeric"


class TestSignalHistory:
    """Signal History endpoint tests"""

    def test_signal_history_returns_history_array(self, auth_headers):
        """Test /api/fno/signal-history returns history array"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/signal-history?limit=10",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200, f"Signal history failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "history" in data, "Missing 'history' field"
        assert isinstance(data["history"], list), "history should be a list"
        assert "count" in data, "Missing 'count' field"


class TestSignalLog:
    """Signal Log endpoint tests"""

    def test_signal_log_returns_log_array(self, auth_headers):
        """Test /api/fno/signal-log returns log array with signal data"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/signal-log?limit=10",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200, f"Signal log failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "log" in data, "Missing 'log' field"
        assert isinstance(data["log"], list), "log should be a list"
        assert "count" in data, "Missing 'count' field"
        
        # If log entries exist, verify structure
        if data["log"]:
            entry = data["log"][0]
            expected_fields = ["option_symbol", "direction", "entry_price", "confluence_score"]
            for field in expected_fields:
                assert field in entry, f"Missing '{field}' in signal log entry"


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_root_endpoint(self):
        """Test root endpoint returns 200"""
        resp = requests.get(f"{BASE_URL}/", timeout=10)
        assert resp.status_code == 200

    def test_auth_access_owner(self):
        """Test owner login works"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") == "owner"

    def test_auth_access_user(self):
        """Test user login works"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
