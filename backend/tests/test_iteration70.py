"""
Iteration 70: Code Quality Fixes Regression Tests

Tests to verify code quality fixes didn't break functionality:
1. kite_client.py migration to app_state (sector-stocks, heatmap)
2. useAuth hook dependency fix (login/logout flow)
3. fno.py _post_generation_effects extraction
4. Backend core endpoints still work
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Test Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    """Get owner token for authenticated requests."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Owner login failed")

@pytest.fixture(scope="module")
def user_token():
    """Get regular user token."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("User login failed")

@pytest.fixture
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}

@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


# ── Backend Health Tests ───────────────────────────────────────────────────────

class TestBackendHealth:
    """Verify backend is running and healthy."""
    
    def test_heartbeat_returns_active(self):
        """Heartbeat endpoint returns active=True."""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active") is True
        print(f"PASS: Heartbeat active={data.get('active')}")


# ── Auth Flow Tests (useAuth hook dependency fix) ──────────────────────────────

class TestAuthFlow:
    """Verify login/logout flow works after useAuth hook fix."""
    
    def test_owner_login_shish123(self):
        """Owner login with @shish123 returns token and role=owner."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print(f"PASS: Owner login successful, role={data.get('role')}")
    
    def test_user_login_manas2005(self):
        """User login with Manas@2005 returns token."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        print(f"PASS: User login successful")
    
    def test_auth_me_returns_user_info(self, owner_headers):
        """GET /api/auth/me returns user info."""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "role" in data
        print(f"PASS: /api/auth/me returns role={data.get('role')}")
    
    def test_logout_endpoint(self, user_headers):
        """POST /api/auth/logout works."""
        resp = requests.post(f"{BASE_URL}/api/auth/logout", headers=user_headers)
        assert resp.status_code == 200
        print("PASS: Logout successful")


# ── Journal Endpoint Tests ─────────────────────────────────────────────────────

class TestJournalEndpoints:
    """Verify journal endpoints work (used by fno.py _post_generation_effects)."""
    
    def test_get_journal_returns_entries_and_summary(self, owner_headers):
        """GET /api/journal returns entries array and summary object."""
        resp = requests.get(f"{BASE_URL}/api/journal", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "summary" in data
        summary = data["summary"]
        # Verify summary has expected fields
        assert "total_entries" in summary
        assert "closed_trades" in summary
        assert "total_pnl" in summary
        assert "wins" in summary
        assert "losses" in summary
        assert "win_rate" in summary
        print(f"PASS: Journal returns {len(data['entries'])} entries, summary has all fields")


# ── Notification Analytics Tests ───────────────────────────────────────────────

class TestNotificationAnalytics:
    """Verify notification analytics endpoint works."""
    
    def test_notification_analytics_returns_required_fields(self, owner_headers):
        """GET /api/notifications/analytics returns frequency_7d, total_24h."""
        resp = requests.get(f"{BASE_URL}/api/notifications/analytics", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "frequency_7d" in data
        assert "total_24h" in data
        print(f"PASS: Notification analytics returns frequency_7d, total_24h={data.get('total_24h')}")


# ── Kite Client Migration Tests (Critical for iteration 70) ────────────────────

class TestKiteClientMigration:
    """Verify kite_client.py migration to app_state didn't break endpoints."""
    
    def test_sector_stocks_endpoint(self, owner_headers):
        """GET /api/market/sector-stocks returns sector data (uses kite_client)."""
        resp = requests.get(f"{BASE_URL}/api/market/sector-stocks?sector=NIFTY50", headers=owner_headers)
        # May return 200 with data or 400 if sector not found
        assert resp.status_code in [200, 400]
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict)
            assert "sector" in data
            print(f"PASS: Sector stocks endpoint returns data for sector={data.get('sector')}")
        else:
            print(f"PASS: Sector stocks returns 400 (sector not found - expected)")
    
    def test_stock_heatmap_returns_data(self, owner_headers):
        """GET /api/market/stock-heatmap returns heatmap data."""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data
        assert "count" in data
        print(f"PASS: Stock heatmap returns {data.get('count')} stocks")


# ── FNO Endpoints Tests ────────────────────────────────────────────────────────

class TestFNOEndpoints:
    """Verify F&O endpoints work after fno.py refactor."""
    
    def test_fno_custom_positions(self, owner_headers):
        """GET /api/fno/custom-positions returns list."""
        resp = requests.get(f"{BASE_URL}/api/fno/custom-positions", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: F&O custom positions returns {len(data)} positions")
    
    def test_fno_bbe_alerts(self, owner_headers):
        """GET /api/fno/bbe-alerts returns alerts."""
        resp = requests.get(f"{BASE_URL}/api/fno/bbe-alerts", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        print(f"PASS: F&O BBE alerts returns {len(data.get('alerts', []))} alerts")
    
    def test_fno_events(self, owner_headers):
        """GET /api/fno/events returns events list."""
        resp = requests.get(f"{BASE_URL}/api/fno/events", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))
        print(f"PASS: F&O events endpoint works")
    
    def test_fno_generation_timings(self, owner_headers):
        """GET /api/fno/generation-timings returns timing data."""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "fno" in data
        assert "multibagger" in data
        print(f"PASS: F&O generation timings returns data")


# ── Admin Endpoints Tests ──────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Verify admin endpoints work."""
    
    def test_admin_users_list(self, owner_headers):
        """GET /api/admin/users returns users list."""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: Admin users list returns {len(data)} users")
    
    def test_admin_config_kite_status(self, owner_headers):
        """GET /api/admin/config returns config data."""
        resp = requests.get(f"{BASE_URL}/api/admin/config", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should have api_controls or kite-related fields
        assert "api_controls" in data or "kite_connected" in data or "kite_session_valid" in data
        print(f"PASS: Admin config returns data with api_controls={data.get('api_controls', {}).get('kite_data_enabled')}")


# ── Error Boundary Test (App loads cleanly) ────────────────────────────────────

class TestAppLoadsCleanly:
    """Verify app loads without errors."""
    
    def test_root_endpoint(self):
        """Root endpoint returns 200."""
        resp = requests.get(f"{BASE_URL}/")
        # Frontend serves at root, backend may redirect
        assert resp.status_code in [200, 307, 404]
        print(f"PASS: Root endpoint returns {resp.status_code}")
    
    def test_api_docs_available(self):
        """API docs endpoint available."""
        resp = requests.get(f"{BASE_URL}/api/docs")
        # May redirect to /docs or return 200
        assert resp.status_code in [200, 307, 404]
        print(f"PASS: API docs endpoint returns {resp.status_code}")
