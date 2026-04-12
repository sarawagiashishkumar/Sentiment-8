"""
Iteration 68 Tests:
1. Service Worker Push Notifications with ON/OFF toggle
2. Notification Persistence to MongoDB (/api/notifications CRUD)
3. Engine modularization (fno_signal_builder.py extraction)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestBackendHealth:
    """Basic health check tests"""

    def test_heartbeat_returns_active(self):
        """Heartbeat endpoint should return active=True"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("active") is True
        print("PASS - heartbeat returns active=True")


class TestAuthAccess:
    """Authentication tests"""

    def test_owner_login_shish123(self):
        """Owner login with @shish123"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print("PASS - owner login successful, role=owner")
        return data["token"]

    def test_user_login_manas2005(self):
        """User login with Manas@2005"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print("PASS - user login successful")
        return data["token"]


class TestNotificationEndpoints:
    """Test notification CRUD endpoints - Task 2"""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json()["token"]

    def test_get_notifications_returns_array(self, auth_token):
        """GET /api/notifications should return notifications array"""
        response = requests.get(
            f"{BASE_URL}/api/notifications",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert isinstance(data["notifications"], list)
        print(f"PASS - GET /api/notifications returns array with {len(data['notifications'])} items")

    def test_post_notifications_saves(self, auth_token):
        """POST /api/notifications should save notifications"""
        payload = {
            "notifications": [
                {
                    "category": "critical",
                    "title": "TEST_ALERT",
                    "message": "Test notification from iteration 68",
                    "symbol": "NIFTY"
                }
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/notifications",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("saved") == 1
        print("PASS - POST /api/notifications saves notifications")

    def test_patch_notifications_read_all(self, auth_token):
        """PATCH /api/notifications/read-all should mark all as read"""
        response = requests.patch(
            f"{BASE_URL}/api/notifications/read-all",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "modified" in data
        print(f"PASS - PATCH /api/notifications/read-all modified {data['modified']} items")

    def test_delete_notifications_clears_all(self, auth_token):
        """DELETE /api/notifications should clear all"""
        response = requests.delete(
            f"{BASE_URL}/api/notifications",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data
        print(f"PASS - DELETE /api/notifications deleted {data['deleted']} items")


class TestStockHeatmap:
    """Stock heatmap endpoint tests"""

    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json()["token"]

    def test_stock_heatmap_returns_data(self, auth_token):
        """Stock heatmap should return data"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "stocks" in data or "sectors" in data or isinstance(data, list)
        print("PASS - Stock heatmap returns data")


class TestFNOEndpoints:
    """F&O endpoints tests - verify engine extraction didn't break functionality"""

    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json()["token"]

    def test_fno_custom_positions(self, auth_token):
        """F&O custom positions should return list"""
        response = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS - F&O custom positions returns list with {len(data)} items")

    def test_fno_bbe_alerts(self, auth_token):
        """F&O BBE alerts should return alerts"""
        response = requests.get(
            f"{BASE_URL}/api/fno/bbe-alerts",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        print(f"PASS - F&O BBE alerts returns {len(data['alerts'])} alerts")

    def test_fno_events(self, auth_token):
        """F&O events should return list"""
        response = requests.get(
            f"{BASE_URL}/api/fno/events",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS - F&O events returns list with {len(data)} items")

    def test_fno_performance_stats(self, auth_token):
        """F&O performance stats should return data"""
        response = requests.get(
            f"{BASE_URL}/api/fno/performance-stats",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("PASS - F&O performance stats returns data")


class TestAdminEndpoints:
    """Admin endpoint tests"""

    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json()["token"]

    def test_admin_users_list(self, auth_token):
        """Admin users list should return users"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS - Admin users list returns {len(data)} users")

    def test_admin_config_kite_status(self, auth_token):
        """Admin config should return kite status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/config",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "kite" in data
        assert "connected" in data["kite"]
        print(f"PASS - Admin config returns kite connected={data['kite']['connected']}")


class TestLogoutFlow:
    """Logout flow tests"""

    def test_logout_endpoint(self):
        """Logout should work"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        token = login_response.json()["token"]

        # Then logout
        response = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        assert response.status_code == 200
        print("PASS - Logout successful")


class TestEngineModularization:
    """Test that engine modularization didn't break imports - Task 3"""

    def test_fno_signal_builder_exists(self):
        """fno_signal_builder.py should exist and be importable"""
        import sys
        sys.path.insert(0, "/app/backend")
        try:
            from services.fno_signal_builder import build_fno_signal
            assert callable(build_fno_signal)
            print("PASS - fno_signal_builder.py exists and build_fno_signal is importable")
        except ImportError as e:
            pytest.fail(f"Failed to import build_fno_signal: {e}")

    def test_fno_signal_engine_reduced(self):
        """fno_signal_engine.py should be reduced (re-exports build_fno_signal)"""
        import sys
        sys.path.insert(0, "/app/backend")
        try:
            from services.fno_signal_engine import build_fno_signal
            assert callable(build_fno_signal)
            print("PASS - fno_signal_engine.py re-exports build_fno_signal")
        except ImportError as e:
            pytest.fail(f"Failed to import from fno_signal_engine: {e}")

    def test_fno_signal_builder_line_count(self):
        """fno_signal_builder.py should be ~1180 lines"""
        with open("/app/backend/services/fno_signal_builder.py", "r") as f:
            lines = len(f.readlines())
        assert lines >= 1100, f"fno_signal_builder.py has {lines} lines, expected ~1180"
        print(f"PASS - fno_signal_builder.py has {lines} lines (expected ~1180)")

    def test_fno_signal_engine_line_count(self):
        """fno_signal_engine.py should be ~500 lines (82% reduction)"""
        with open("/app/backend/services/fno_signal_engine.py", "r") as f:
            lines = len(f.readlines())
        assert lines <= 600, f"fno_signal_engine.py has {lines} lines, expected ~500"
        print(f"PASS - fno_signal_engine.py has {lines} lines (expected ~500)")


class TestFNOContractsEndpoint:
    """F&O contracts endpoint tests"""

    def test_fno_contracts_endpoint_exists(self):
        """F&O contracts endpoint should exist"""
        response = requests.get(
            f"{BASE_URL}/api/fno/contracts",
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS - F&O contracts endpoint returns {len(data)} contracts")
