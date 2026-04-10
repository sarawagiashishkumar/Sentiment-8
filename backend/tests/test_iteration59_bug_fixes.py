"""
Iteration 59: Bug Fix Verification Tests
- AdminDashboard UserCog import fix
- Unicode \u2b50 removal from F&O components
- User verification (only 2 legitimate users)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHeartbeatRegression:
    """Verify heartbeat endpoint still works"""
    
    def test_heartbeat_returns_alive(self):
        response = requests.get(f"{BASE_URL}/api/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "alive"
        print(f"PASS: Heartbeat returns alive - {data}")


class TestAuthAccess:
    """Verify auth access for both legitimate users"""
    
    def test_owner_login_shish123(self):
        """Owner @shish123 should login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print(f"PASS: Owner @shish123 login successful - role={data.get('role')}")
        return data.get("token")
    
    def test_user_login_manas2005(self):
        """User Manas@2005 should login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print(f"PASS: User Manas@2005 login successful - role={data.get('role')}")


class TestAdminUsersEndpoint:
    """Verify admin users endpoint returns only legitimate users"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json().get("token")
    
    def test_admin_users_returns_only_legitimate_users(self, owner_token):
        """Admin users endpoint should return only Manas@2005 and @shish123"""
        headers = {"Authorization": f"Bearer {owner_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        assert response.status_code == 200
        users = response.json()
        
        # Should have exactly 2 users
        assert len(users) == 2, f"Expected 2 users, got {len(users)}: {[u.get('username') for u in users]}"
        
        # Extract usernames
        usernames = [u.get("username") for u in users]
        assert "Manas@2005" in usernames, f"Manas@2005 not found in {usernames}"
        assert "@shish123" in usernames, f"@shish123 not found in {usernames}"
        
        print(f"PASS: Admin users returns exactly 2 legitimate users: {usernames}")


class TestKiteStatusRegression:
    """Verify Kite status endpoint works"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json().get("token")
    
    def test_kite_status_returns_connected(self, owner_token):
        """Kite status should return connected status"""
        headers = {"Authorization": f"Bearer {owner_token}"}
        response = requests.get(f"{BASE_URL}/api/kite/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        print(f"PASS: Kite status returns connected={data.get('connected')}")


class TestSectorMomentumRegression:
    """Verify sector momentum endpoint still works"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json().get("token")
    
    def test_sector_momentum_returns_sectors(self, owner_token):
        """Sector momentum should return sectors array"""
        headers = {"Authorization": f"Bearer {owner_token}"}
        response = requests.get(f"{BASE_URL}/api/market/sector-momentum", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "sectors" in data
        assert len(data["sectors"]) > 0
        print(f"PASS: Sector momentum returns {len(data['sectors'])} sectors")


class TestSectorDrillDownRegression:
    """Verify sector drill-down endpoint still works"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json().get("token")
    
    def test_sector_stocks_returns_stocks(self, owner_token):
        """Sector stocks endpoint should return stocks array"""
        headers = {"Authorization": f"Bearer {owner_token}"}
        response = requests.get(f"{BASE_URL}/api/market/sector-stocks?sector=NIFTY%20IT", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "stocks" in data
        print(f"PASS: Sector stocks returns {len(data.get('stocks', []))} stocks for NIFTY IT")


class TestMarketHeatmapRegression:
    """Verify market heatmap endpoint still works"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json().get("token")
    
    def test_market_heatmap_returns_data(self, owner_token):
        """Market heatmap should return heatmap data"""
        headers = {"Authorization": f"Bearer {owner_token}"}
        response = requests.get(f"{BASE_URL}/api/market/heatmap", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have nse_sectors or industry_sectors
        assert "nse_sectors" in data or "industry_sectors" in data or "sectors" in data
        print(f"PASS: Market heatmap returns data with keys: {list(data.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
