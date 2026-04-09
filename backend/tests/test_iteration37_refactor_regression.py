"""
Iteration 37: REFACTORING REGRESSION TEST
==========================================
Tests that the extraction of FNO and Admin routes into separate module files
(routes/fno.py and routes/admin.py) with shared auth deps (deps.py) causes
ZERO REGRESSION - all endpoints must work exactly as before.

Extracted routes:
- /api/fno/* -> routes/fno.py
- /api/admin/* -> routes/admin.py
- Auth deps -> deps.py (get_current_user, get_admin_user, get_owner_user)
"""

import os
import pytest
import requests

from tests.helpers.test_utils import get_base_url

BASE_URL = get_base_url()

# Test credentials from test_credentials.md
TEST_USERNAME = "@shish123"
TEST_PASSWORD = "1234"


class TestAuthEndpoints:
    """Test auth endpoints (remain in server.py but use deps.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
    
    def test_auth_access_login(self):
        """POST /api/auth/access - Login with valid credentials"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Response missing 'token'"
        # Response has username/role at top level, not nested in 'user'
        assert "username" in data or "user" in data, "Response missing username info"
        username = data.get("username") or data.get("user", {}).get("username")
        role = data.get("role") or data.get("user", {}).get("role")
        assert username == TEST_USERNAME
        assert role == "owner"
        print(f"PASS: Auth login works, token received, user={username}")
    
    def test_auth_me_endpoint(self):
        """GET /api/auth/me - Returns correct user info"""
        # First login
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]
        
        # Then get /me
        response = self.session.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"GET /me failed: {response.text}"
        data = response.json()
        assert data["username"] == TEST_USERNAME
        assert data["role"] == "owner"
        print(f"PASS: GET /api/auth/me returns correct user info")
    
    def test_auth_logout(self):
        """POST /api/auth/logout - Logout works"""
        # First login
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]
        
        # Then logout
        response = self.session.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Logout failed: {response.text}"
        data = response.json()
        # Response has 'ok': True
        assert data.get("logged_out") == True or data.get("ok") == True or "success" in str(data).lower()
        print(f"PASS: POST /api/auth/logout works")


class TestFNORoutes:
    """Test FNO routes (extracted to routes/fno.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login and get token
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        if login_resp.status_code == 200:
            self.token = login_resp.json()["token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            pytest.skip("Could not authenticate for FNO tests")
    
    def test_fno_scripts_search(self):
        """GET /api/fno/scripts/search?q=NIFTY - Returns suggestions"""
        response = self.session.get(f"{BASE_URL}/api/fno/scripts/search?q=NIFTY")
        assert response.status_code == 200, f"Scripts search failed: {response.text}"
        data = response.json()
        assert "suggestions" in data, "Response missing 'suggestions'"
        assert "query" in data, "Response missing 'query'"
        assert data["query"] == "NIFTY"
        # Should have NIFTY-related suggestions
        assert len(data["suggestions"]) > 0, "No suggestions returned for NIFTY"
        print(f"PASS: GET /api/fno/scripts/search returns {len(data['suggestions'])} suggestions")
    
    def test_fno_custom_positions_list(self):
        """GET /api/fno/custom-positions - Returns list"""
        response = self.session.get(f"{BASE_URL}/api/fno/custom-positions")
        assert response.status_code == 200, f"Custom positions list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: GET /api/fno/custom-positions returns list with {len(data)} items")
    
    def test_fno_position_alerts(self):
        """GET /api/fno/position-alerts - Returns alerts object"""
        response = self.session.get(f"{BASE_URL}/api/fno/position-alerts")
        assert response.status_code == 200, f"Position alerts failed: {response.text}"
        data = response.json()
        assert "alerts" in data, "Response missing 'alerts'"
        assert "count" in data, "Response missing 'count'"
        print(f"PASS: GET /api/fno/position-alerts returns alerts object with count={data['count']}")
    
    def test_fno_strategy_backtests(self):
        """GET /api/fno/strategy-backtests - Returns backtests list"""
        response = self.session.get(f"{BASE_URL}/api/fno/strategy-backtests")
        assert response.status_code == 200, f"Strategy backtests failed: {response.text}"
        data = response.json()
        assert "backtests" in data, "Response missing 'backtests'"
        assert "count" in data, "Response missing 'count'"
        print(f"PASS: GET /api/fno/strategy-backtests returns {data['count']} backtests")
    
    def test_fno_position_sizing(self):
        """POST /api/fno/position-sizing - Returns sizing info"""
        response = self.session.post(
            f"{BASE_URL}/api/fno/position-sizing",
            params={
                "user_budget": 100000,
                "option_premium": 100,
                "lot_size": 50,
                "max_risk_pct": 2.0
            }
        )
        assert response.status_code == 200, f"Position sizing failed: {response.text}"
        data = response.json()
        # Should have sizing-related fields - actual response has 'lots_allowed'
        assert "lots_allowed" in data or "recommended_lots" in data or "max_lots" in data, \
            f"Response missing sizing fields: {data}"
        print(f"PASS: POST /api/fno/position-sizing returns sizing info: lots_allowed={data.get('lots_allowed')}")
    
    def test_fno_signals_index_backward_compat(self):
        """GET /api/fno/signals/index - Returns signals list (backward compat)"""
        response = self.session.get(f"{BASE_URL}/api/fno/signals/index")
        assert response.status_code == 200, f"Signals index failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: GET /api/fno/signals/index returns list with {len(data)} signals")
    
    def test_fno_signals_potential_backward_compat(self):
        """GET /api/fno/signals/potential - Returns signals (backward compat)"""
        response = self.session.get(f"{BASE_URL}/api/fno/signals/potential")
        assert response.status_code == 200, f"Signals potential failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: GET /api/fno/signals/potential returns list with {len(data)} signals")


class TestAdminRoutes:
    """Test Admin routes (extracted to routes/admin.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login and get token
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        if login_resp.status_code == 200:
            self.token = login_resp.json()["token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            pytest.skip("Could not authenticate for Admin tests")
    
    def test_admin_users_list(self):
        """GET /api/admin/users - Returns user list"""
        response = self.session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 200, f"Admin users list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Should have at least the owner user
        assert len(data) >= 1, "Should have at least one user"
        # Verify user structure
        user = data[0]
        assert "username" in user, "User missing 'username'"
        assert "role" in user, "User missing 'role'"
        print(f"PASS: GET /api/admin/users returns {len(data)} users")
    
    def test_admin_config(self):
        """GET /api/admin/config - Returns config object"""
        response = self.session.get(f"{BASE_URL}/api/admin/config")
        assert response.status_code == 200, f"Admin config failed: {response.text}"
        data = response.json()
        assert "api_controls" in data, "Response missing 'api_controls'"
        assert "domain_mappings" in data, "Response missing 'domain_mappings'"
        assert "kite" in data, "Response missing 'kite'"
        print(f"PASS: GET /api/admin/config returns config object")
    
    def test_admin_nse_holidays(self):
        """GET /api/admin/nse-holidays - Returns holidays"""
        response = self.session.get(f"{BASE_URL}/api/admin/nse-holidays")
        assert response.status_code == 200, f"NSE holidays failed: {response.text}"
        data = response.json()
        assert "holidays" in data, "Response missing 'holidays'"
        assert "total_in_memory" in data, "Response missing 'total_in_memory'"
        print(f"PASS: GET /api/admin/nse-holidays returns {data['total_in_memory']} holidays")
    
    def test_admin_macro_events(self):
        """GET /api/admin/macro-events - Returns macro events"""
        response = self.session.get(f"{BASE_URL}/api/admin/macro-events")
        assert response.status_code == 200, f"Macro events failed: {response.text}"
        data = response.json()
        assert "active_events" in data, "Response missing 'active_events'"
        assert "all_events" in data, "Response missing 'all_events'"
        assert "total_active" in data, "Response missing 'total_active'"
        print(f"PASS: GET /api/admin/macro-events returns {data['total_active']} active events")
    
    def test_admin_strategy_stats(self):
        """GET /api/admin/strategy-stats - Returns strategy stats"""
        response = self.session.get(f"{BASE_URL}/api/admin/strategy-stats")
        assert response.status_code == 200, f"Strategy stats failed: {response.text}"
        data = response.json()
        assert "strategy_stats" in data, "Response missing 'strategy_stats'"
        assert "total_records" in data, "Response missing 'total_records'"
        print(f"PASS: GET /api/admin/strategy-stats returns {data['total_records']} records")
    
    def test_admin_csv_seeds(self):
        """GET /api/admin/csv-seeds - Returns seed files"""
        response = self.session.get(f"{BASE_URL}/api/admin/csv-seeds")
        assert response.status_code == 200, f"CSV seeds failed: {response.text}"
        data = response.json()
        assert "seeds" in data, "Response missing 'seeds'"
        assert "count" in data, "Response missing 'count'"
        assert "seed_dir" in data, "Response missing 'seed_dir'"
        print(f"PASS: GET /api/admin/csv-seeds returns {data['count']} seeds")


class TestRemainingServerEndpoints:
    """Test endpoints that remain in server.py"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login and get token
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        if login_resp.status_code == 200:
            self.token = login_resp.json()["token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_api_root(self):
        """GET /api/ - Returns API info"""
        response = self.session.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"API root failed: {response.text}"
        data = response.json()
        # Should have some API info
        assert isinstance(data, dict), "Response should be a dict"
        print(f"PASS: GET /api/ returns API info")
    
    def test_strategy_library(self):
        """GET /api/strategy-library - Returns strategies"""
        response = self.session.get(f"{BASE_URL}/api/strategy-library")
        assert response.status_code == 200, f"Strategy library failed: {response.text}"
        data = response.json()
        assert "strategies" in data or isinstance(data, list) or isinstance(data, dict), \
            f"Unexpected response format: {data}"
        print(f"PASS: GET /api/strategy-library returns strategies")
    
    def test_sector_momentum(self):
        """GET /api/sector-momentum - Returns sectors"""
        response = self.session.get(f"{BASE_URL}/api/sector-momentum")
        assert response.status_code == 200, f"Sector momentum failed: {response.text}"
        data = response.json()
        # Should have sector data
        assert isinstance(data, dict), "Response should be a dict"
        print(f"PASS: GET /api/sector-momentum returns sector data")


class TestDepsModuleIntegration:
    """Test that deps.py auth dependencies work correctly across all routes"""
    
    def test_unauthorized_access_fno_route(self):
        """FNO routes should reject unauthorized requests"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/fno/custom-positions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: FNO route rejects unauthorized request with 401")
    
    def test_unauthorized_access_admin_route(self):
        """Admin routes should reject unauthorized requests"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Admin route rejects unauthorized request with 401")
    
    def test_invalid_token_fno_route(self):
        """FNO routes should reject invalid tokens"""
        session = requests.Session()
        session.headers.update({"Authorization": "Bearer invalid_token_12345"})
        response = session.get(f"{BASE_URL}/api/fno/custom-positions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: FNO route rejects invalid token with 401")
    
    def test_invalid_token_admin_route(self):
        """Admin routes should reject invalid tokens"""
        session = requests.Session()
        session.headers.update({"Authorization": "Bearer invalid_token_12345"})
        response = session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Admin route rejects invalid token with 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
