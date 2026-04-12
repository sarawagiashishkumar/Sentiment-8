"""
Iteration 64: Refactoring + Feature Tests
- useAuth hook wired into App.js
- AdminDashboard split into sub-components
- fno_signal_engine.py modularized (builders extracted)
- IV Analytics enhanced with symbol presets
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture
def owner_token(api_client):
    """Get owner token using @shish123"""
    response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Owner authentication failed")

@pytest.fixture
def user_token(api_client):
    """Get user token using Manas@2005"""
    response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("User authentication failed")


class TestBackendHealth:
    """Backend heartbeat and health checks"""
    
    def test_heartbeat_returns_active_field(self, api_client):
        """Heartbeat should return active=True"""
        response = api_client.get(f"{BASE_URL}/api/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data, "Heartbeat missing 'active' field"
        assert data["active"] is True, "Heartbeat active should be True"
        assert "status" in data
        assert data["status"] == "alive"
        print(f"PASS: Heartbeat returns active={data['active']}, status={data['status']}")


class TestAuthAccess:
    """Authentication endpoint tests"""
    
    def test_owner_login_shish123(self, api_client):
        """Owner login with @shish123"""
        response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["role"] == "owner"
        assert "credits" in data
        assert "user_key" in data
        print(f"PASS: Owner login successful, role={data['role']}")
    
    def test_user_login_manas2005(self, api_client):
        """User login with Manas@2005"""
        response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["role"] in ["user", "sub_admin"]
        print(f"PASS: User login successful, role={data['role']}")
    
    def test_auth_me_endpoint(self, api_client, owner_token):
        """Test /auth/me returns user info"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "role" in data
        assert "user_key" in data
        print(f"PASS: /auth/me returns user info, role={data['role']}")


class TestStockHeatmap:
    """Stock heatmap endpoint tests"""
    
    def test_stock_heatmap_returns_data(self, api_client, owner_token):
        """Stock heatmap should return data structure"""
        response = api_client.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Should have stocks array and count
        assert "stocks" in data or "count" in data
        print(f"PASS: Stock heatmap returns data, count={data.get('count', len(data.get('stocks', [])))}")


class TestIVEndpoints:
    """IV Cone and Term Structure endpoint tests"""
    
    def test_iv_cone_nifty(self, api_client, owner_token):
        """IV Cone endpoint for NIFTY"""
        response = api_client.get(
            f"{BASE_URL}/api/fno/iv-cone/NIFTY",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert data["symbol"] == "NIFTY"
        assert "data_points" in data
        # data_points may be 0 if no history accumulated yet
        print(f"PASS: IV Cone NIFTY returns data_points={data['data_points']}")
    
    def test_iv_term_structure_nifty(self, api_client, owner_token):
        """IV Term Structure endpoint for NIFTY"""
        response = api_client.get(
            f"{BASE_URL}/api/fno/iv-term-structure/NIFTY",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert data["symbol"] == "NIFTY"
        assert "data_points" in data
        print(f"PASS: IV Term Structure NIFTY returns data_points={data['data_points']}")
    
    def test_iv_cone_banknifty(self, api_client, owner_token):
        """IV Cone endpoint for BANKNIFTY"""
        response = api_client.get(
            f"{BASE_URL}/api/fno/iv-cone/BANKNIFTY",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert data["symbol"] == "BANKNIFTY"
        print(f"PASS: IV Cone BANKNIFTY returns data_points={data.get('data_points', 0)}")


class TestAdminEndpoints:
    """Admin endpoint tests"""
    
    def test_admin_users_list(self, api_client, owner_token):
        """Admin users list endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Admin users list returns {len(data)} users")
    
    def test_kite_status_endpoint(self, api_client, owner_token):
        """Kite/Market Data API status endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/kite/status",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        print(f"PASS: Kite status returns connected={data['connected']}")


class TestFNOEndpoints:
    """F&O related endpoint tests"""
    
    def test_fno_custom_positions(self, api_client, owner_token):
        """F&O custom positions endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: F&O custom positions returns {len(data)} positions")


class TestLogoutFlow:
    """Logout endpoint test"""
    
    def test_logout_endpoint(self, api_client, owner_token):
        """Logout should work"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={}
        )
        # Logout may return 200 or 204
        assert response.status_code in [200, 204]
        print(f"PASS: Logout successful, status={response.status_code}")
