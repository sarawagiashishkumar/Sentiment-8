"""
Iteration 69 Tests: Trading Journal, Notification Analytics, IV Background Collector
- Trading Journal CRUD (GET/POST/DELETE)
- Notification Analytics endpoint
- F&O page 4 sub-tabs verification
- Admin Performance tab with Notification Analytics section
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://backend-refactor-p2.preview.emergentagent.com"


class TestBackendHealth:
    """Basic health checks"""

    def test_heartbeat_returns_active(self):
        """Heartbeat should return active=True"""
        response = requests.get(f"{BASE_URL}/api/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data.get("active") is True
        assert "ts" in data
        print("PASS - heartbeat returns active=True")


class TestAuthAccess:
    """Authentication tests"""

    def test_owner_login_shish123(self):
        """Owner login with @shish123"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "owner"
        assert "token" in data
        print("PASS - owner login successful, role=owner")
        return data["token"]

    def test_user_login_manas2005(self):
        """User login with Manas@2005"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "user"
        assert "token" in data
        print("PASS - user login successful")
        return data["token"]


class TestJournalEndpoints:
    """Trading Journal CRUD tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get owner token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        self.owner_token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.owner_token}"}
        
        # Get user token for permission tests
        user_response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"}
        )
        self.user_token = user_response.json()["token"]
        self.user_headers = {"Authorization": f"Bearer {self.user_token}"}

    def test_get_journal_returns_entries_and_summary(self):
        """GET /api/journal returns entries array and summary object"""
        response = requests.get(f"{BASE_URL}/api/journal", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "entries" in data
        assert "summary" in data
        assert isinstance(data["entries"], list)
        
        # Verify summary has required fields
        summary = data["summary"]
        required_fields = ["total_entries", "closed_trades", "total_pnl", "wins", "losses", "win_rate", "avg_holding_mins"]
        for field in required_fields:
            assert field in summary, f"Missing summary field: {field}"
        
        print(f"PASS - GET /api/journal returns entries ({len(data['entries'])}) and summary with all required fields")

    def test_post_journal_saves_entry(self):
        """POST /api/journal saves journal entry"""
        entry = {
            "event_type": "signal_generated",
            "symbol": "TEST_NIFTY",
            "direction": "BULLISH",
            "confluence_score": 75.5,
            "signal_quality": "HIGH",
            "notes": "Test entry from iteration 69 pytest"
        }
        response = requests.post(
            f"{BASE_URL}/api/journal",
            json=entry,
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("logged") is True
        
        # Verify entry was saved by fetching
        get_response = requests.get(f"{BASE_URL}/api/journal?symbol=TEST_NIFTY", headers=self.headers)
        assert get_response.status_code == 200
        entries = get_response.json()["entries"]
        assert len(entries) >= 1
        assert any(e["symbol"] == "TEST_NIFTY" for e in entries)
        
        print("PASS - POST /api/journal saves entry and persists to DB")

    def test_journal_filter_by_event_type(self):
        """GET /api/journal with event_type filter"""
        response = requests.get(
            f"{BASE_URL}/api/journal?event_type=signal_generated",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        # All entries should be signal_generated
        for entry in data["entries"]:
            assert entry["event_type"] == "signal_generated"
        print("PASS - Journal filter by event_type works")

    def test_journal_filter_by_symbol(self):
        """GET /api/journal with symbol filter"""
        response = requests.get(
            f"{BASE_URL}/api/journal?symbol=NIFTY",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        # All entries should contain NIFTY in symbol
        for entry in data["entries"]:
            assert "NIFTY" in entry["symbol"].upper()
        print("PASS - Journal filter by symbol works")

    def test_delete_journal_owner_only(self):
        """DELETE /api/journal requires owner role"""
        # Non-owner should get 403
        response = requests.delete(
            f"{BASE_URL}/api/journal",
            headers=self.user_headers
        )
        assert response.status_code == 403
        print("PASS - DELETE /api/journal returns 403 for non-owner")

    def test_delete_journal_owner_succeeds(self):
        """DELETE /api/journal succeeds for owner"""
        # First add an entry to delete
        requests.post(
            f"{BASE_URL}/api/journal",
            json={"event_type": "signal_generated", "symbol": "DELETE_TEST"},
            headers=self.headers
        )
        
        # Owner should be able to delete
        response = requests.delete(
            f"{BASE_URL}/api/journal",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data
        print(f"PASS - DELETE /api/journal succeeds for owner, deleted {data['deleted']} entries")


class TestNotificationAnalytics:
    """Notification Analytics endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_notification_analytics_returns_required_fields(self):
        """GET /api/notifications/analytics returns frequency_7d, total_24h, avg_response_latency_secs, read_count_7d"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/analytics",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "frequency_7d" in data
        assert "total_24h" in data
        assert "avg_response_latency_secs" in data
        assert "read_count_7d" in data
        
        # frequency_7d should be a dict
        assert isinstance(data["frequency_7d"], dict)
        # total_24h should be an int
        assert isinstance(data["total_24h"], int)
        # read_count_7d should be an int
        assert isinstance(data["read_count_7d"], int)
        
        print(f"PASS - /api/notifications/analytics returns all required fields: total_24h={data['total_24h']}, read_count_7d={data['read_count_7d']}")


class TestStockHeatmap:
    """Stock heatmap endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_stock_heatmap_returns_data(self):
        """GET /api/market/stock-heatmap returns stocks array"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "stocks" in data
        assert isinstance(data["stocks"], list)
        assert len(data["stocks"]) > 0
        print(f"PASS - Stock heatmap returns {len(data['stocks'])} stocks")


class TestFNOEndpoints:
    """F&O related endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_fno_custom_positions(self):
        """GET /api/fno/custom-positions returns list"""
        response = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS - F&O custom positions returns list ({len(data)} positions)")

    def test_fno_bbe_alerts(self):
        """GET /api/fno/bbe-alerts returns alerts"""
        response = requests.get(
            f"{BASE_URL}/api/fno/bbe-alerts",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        print("PASS - F&O BBE alerts returns alerts")

    def test_fno_events(self):
        """GET /api/fno/events returns list"""
        response = requests.get(
            f"{BASE_URL}/api/fno/events",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print("PASS - F&O events returns list")

    def test_fno_generation_timings(self):
        """GET /api/fno/generation-timings returns timing data"""
        response = requests.get(
            f"{BASE_URL}/api/fno/generation-timings",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "fno" in data or "multibagger" in data or "history" in data
        print("PASS - F&O generation timings returns data")


class TestAdminEndpoints:
    """Admin endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get owner token for admin tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_admin_users_list(self):
        """GET /api/admin/users returns users list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS - Admin users list returns {len(data)} users")

    def test_admin_config_kite_status(self):
        """GET /api/admin/config returns kite status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/config",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        # Check for kite_connected or api_controls with kite_data_enabled
        has_kite_info = "kite_connected" in data or ("api_controls" in data and "kite_data_enabled" in data.get("api_controls", {}))
        assert has_kite_info
        print(f"PASS - Admin config returns kite status info")


class TestLogoutFlow:
    """Logout endpoint tests"""

    def test_logout_endpoint(self):
        """POST /api/auth/logout works"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        token = login_response.json()["token"]
        
        # Then logout
        response = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        print("PASS - Logout successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
