"""
Iteration 67 Backend Tests
Tests for 3 tasks:
1. Persistent Notification Center (frontend-only, but verify backend still works after fno_utils extraction)
2. fno_utils.py extraction (verify fno_signal_engine still works)
3. Performance threshold alerts (frontend-only, verify generation-timings endpoint)

Focus: Backend API verification after fno_utils.py extraction
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def owner_token():
    """Get owner auth token - fresh for each test class"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Owner login failed")

@pytest.fixture(scope="class")
def user_token():
    """Get regular user auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("User login failed")

@pytest.fixture(scope="class")
def owner_headers(owner_token):
    """Auth headers for owner"""
    return {"Authorization": f"Bearer {owner_token}"}

@pytest.fixture(scope="class")
def user_headers(user_token):
    """Auth headers for regular user"""
    return {"Authorization": f"Bearer {user_token}"}


# ── Health Check ──────────────────────────────────────────────────────────────

class TestBackendHealth:
    """Basic health check tests"""
    
    def test_heartbeat_returns_active(self):
        """Heartbeat endpoint should return active=True"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active") == True, f"Expected active=True, got {data}"
        print(f"PASS: Heartbeat returns active=True")


# ── Auth Tests ────────────────────────────────────────────────────────────────

class TestAuthAccess:
    """Authentication endpoint tests"""
    
    def test_owner_login_shish123(self):
        """Owner login with @shish123 should succeed"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print(f"PASS: Owner login successful, role={data.get('role')}")
    
    def test_user_login_manas2005(self):
        """User login with Manas@2005 should succeed"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        print(f"PASS: User login successful")


# ── Generation Timings Endpoint (Task 3: Performance threshold alerts) ────────

class TestGenerationTimingsEndpoint:
    """Tests for /fno/generation-timings endpoint - Performance Dashboard"""
    
    def test_generation_timings_endpoint_exists(self, owner_headers):
        """Endpoint should exist and return fno, multibagger, and history fields"""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Must have all 3 required fields
        assert "fno" in data, "Missing 'fno' field in response"
        assert "multibagger" in data, "Missing 'multibagger' field in response"
        assert "history" in data, "Missing 'history' field in response"
        
        # History should be a list
        assert isinstance(data["history"], list), "history should be a list"
        
        print(f"PASS: generation-timings returns fno, multibagger, history fields")
    
    def test_generation_timings_fno_structure(self, owner_headers):
        """FNO timing should have message or timing fields"""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        fno = data.get("fno", {})
        
        # Either has timing data or 'no run yet' message
        has_timing = "total_ms" in fno
        has_message = "message" in fno
        assert has_timing or has_message, "FNO should have timing data or message"
        print(f"PASS: FNO structure valid (has_timing={has_timing}, has_message={has_message})")
    
    def test_generation_timings_multibagger_structure(self, owner_headers):
        """Multibagger timing should have message or timing fields"""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        mb = data.get("multibagger", {})
        
        # Either has timing data or 'no run yet' message
        has_timing = "total_ms" in mb
        has_message = "message" in mb
        assert has_timing or has_message, "Multibagger should have timing data or message"
        print(f"PASS: Multibagger structure valid (has_timing={has_timing}, has_message={has_message})")


# ── Stock Heatmap (verify backend still works after fno_utils extraction) ─────

class TestStockHeatmap:
    """Tests for stock heatmap endpoint"""
    
    def test_stock_heatmap_returns_data(self, owner_headers):
        """Stock heatmap should return data structure"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data or "kite_live" in data
        print(f"PASS: Stock heatmap returns data, kite_live={data.get('kite_live')}")


# ── F&O Endpoints (verify fno_signal_engine still works after fno_utils extraction) ─

class TestFNOEndpoints:
    """Tests for F&O endpoints - verify fno_utils extraction didn't break anything"""
    
    def test_fno_custom_positions(self, owner_headers):
        """F&O custom positions should return list"""
        resp = requests.get(f"{BASE_URL}/api/fno/custom-positions", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: F&O custom positions returns {len(data)} positions")
    
    def test_fno_bbe_alerts(self, owner_headers):
        """F&O BBE alerts endpoint should work"""
        resp = requests.get(f"{BASE_URL}/api/fno/bbe-alerts", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Returns dict with 'alerts' key
        assert "alerts" in data or isinstance(data, list)
        alerts = data.get("alerts", data) if isinstance(data, dict) else data
        print(f"PASS: F&O BBE alerts returns {len(alerts)} alerts")
    
    def test_fno_events(self, owner_headers):
        """F&O events endpoint should work"""
        resp = requests.get(f"{BASE_URL}/api/fno/events", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: F&O events returns {len(data)} events")
    
    def test_fno_performance_stats(self, owner_headers):
        """F&O performance stats endpoint should work"""
        resp = requests.get(f"{BASE_URL}/api/fno/performance-stats", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should have some structure
        assert isinstance(data, dict)
        print(f"PASS: F&O performance stats returns data")


# ── Admin Endpoints ───────────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Tests for admin endpoints"""
    
    def test_admin_users_list(self, owner_headers):
        """Admin users list should work"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: Admin users list returns {len(data)} users")
    
    def test_kite_status_endpoint(self, owner_headers):
        """Kite status endpoint should return connected status"""
        resp = requests.get(f"{BASE_URL}/api/kite/status", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        print(f"PASS: Kite status returns connected={data.get('connected')}")


# ── Logout Test (run last) ────────────────────────────────────────────────────

class TestLogoutFlow:
    """Logout endpoint test - run last"""
    
    def test_logout_endpoint(self, owner_headers):
        """Logout should succeed"""
        resp = requests.post(f"{BASE_URL}/api/auth/logout", headers=owner_headers)
        assert resp.status_code == 200
        print(f"PASS: Logout successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
