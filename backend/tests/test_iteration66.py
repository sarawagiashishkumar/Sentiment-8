"""
Iteration 66 Backend Tests
Tests for 4 polish tasks:
1. Admin Performance Dashboard tab (generation-timings endpoint with history)
2. Error boundary component (frontend-only, no backend test needed)
3. Loading skeleton states (frontend-only, no backend test needed)
4. Mobile responsiveness (frontend-only, no backend test needed)

Focus: Backend API verification for generation-timings endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Owner login failed")

@pytest.fixture(scope="module")
def user_token():
    """Get regular user auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("User login failed")

@pytest.fixture(scope="module")
def owner_headers(owner_token):
    """Auth headers for owner"""
    return {"Authorization": f"Bearer {owner_token}"}

@pytest.fixture(scope="module")
def user_headers(user_token):
    """Auth headers for regular user"""
    return {"Authorization": f"Bearer {user_token}"}


# ── Health Check ──────────────────────────────────────────────────────────────

class TestBackendHealth:
    """Basic health check tests"""
    
    def test_heartbeat_returns_active(self):
        """Heartbeat endpoint should return active status"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert "active" in data or "status" in data
        print(f"PASS: Heartbeat returns {data}")


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


# ── Generation Timings Endpoint (Iteration 66 Task 1) ─────────────────────────

class TestGenerationTimingsEndpoint:
    """Tests for /fno/generation-timings endpoint - Admin Performance Dashboard"""
    
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
        print(f"  fno: {data['fno']}")
        print(f"  multibagger: {data['multibagger']}")
        print(f"  history count: {len(data['history'])}")
    
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
        
        if has_timing:
            # Verify timing fields exist
            assert "nifty_ms" in fno or "total_ms" in fno
            print(f"PASS: FNO has timing data: total_ms={fno.get('total_ms')}")
        else:
            print(f"PASS: FNO shows 'no run yet' message (expected)")
    
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
        
        if has_timing:
            print(f"PASS: Multibagger has timing data: total_ms={mb.get('total_ms')}")
        else:
            print(f"PASS: Multibagger shows 'no run yet' message (expected)")
    
    def test_generation_timings_history_structure(self, owner_headers):
        """History array should contain valid entries if present"""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        history = data.get("history", [])
        
        # History can be empty (no generations run yet)
        if len(history) == 0:
            print(f"PASS: History is empty (expected - no generations run yet)")
        else:
            # Verify first entry has expected fields
            entry = history[0]
            assert "type" in entry, "History entry should have 'type' field"
            assert entry["type"] in ["fno", "multibagger"], f"Invalid type: {entry['type']}"
            print(f"PASS: History has {len(history)} entries, first type={entry['type']}")
    
    def test_generation_timings_requires_owner(self, user_headers):
        """Regular user should not access generation-timings (owner-only)"""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=user_headers)
        # Should be 403 Forbidden for non-owner
        assert resp.status_code in [401, 403], f"Expected 401/403 for non-owner, got {resp.status_code}"
        print(f"PASS: Non-owner correctly denied access (status={resp.status_code})")


# ── Admin Page Tabs (Iteration 66 Task 1) ─────────────────────────────────────

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


# ── Stock Heatmap (for skeleton loading test context) ─────────────────────────

class TestStockHeatmap:
    """Tests for stock heatmap endpoint"""
    
    def test_stock_heatmap_returns_data(self, owner_headers):
        """Stock heatmap should return data structure"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data or "kite_live" in data
        print(f"PASS: Stock heatmap returns data, kite_live={data.get('kite_live')}")


# ── F&O Endpoints ─────────────────────────────────────────────────────────────

class TestFNOEndpoints:
    """Tests for F&O endpoints"""
    
    def test_fno_custom_positions(self, owner_headers):
        """F&O custom positions should return list"""
        resp = requests.get(f"{BASE_URL}/api/fno/custom-positions", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: F&O custom positions returns {len(data)} positions")


# ── Logout Test ───────────────────────────────────────────────────────────────

class TestLogoutFlow:
    """Logout endpoint test"""
    
    def test_logout_endpoint(self, owner_headers):
        """Logout should succeed"""
        resp = requests.post(f"{BASE_URL}/api/auth/logout", headers=owner_headers)
        assert resp.status_code == 200
        print(f"PASS: Logout successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
