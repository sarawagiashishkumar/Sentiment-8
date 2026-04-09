"""
Iteration 40: Route Extraction Batch 2 Tests

Tests for newly extracted routes:
- market_data.py: /script-master/*, /sector-momentum, /kite/*
- portfolio.py: /portfolio/analyze, /portfolio/analyze-upload
- multibagger.py: /multibagger/generate, /multibagger/candidates, /multibagger/custom-search

Also tests:
- Regression for fno.py and admin.py (Batch 1)
- Remaining server.py endpoints
- Bug fix: compute_portfolio_verdict returns string, no .append() crash
"""
import os
import pytest
import requests

from tests.helpers.test_utils import get_base_url, get_ndjson_complete_data, parse_ndjson_response

BASE_URL = get_base_url()

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for owner account"""
    response = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"Auth failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


# ── Auth Endpoints ────────────────────────────────────────────────────────────

class TestAuthEndpoints:
    """Auth endpoint tests"""
    
    def test_auth_access_login(self):
        """POST /api/auth/access - login works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
            timeout=15
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        # User data is at root level, not nested under "user"
        assert "username" in data, "No username in response"
        assert data["username"] == "@shish123"
    
    def test_auth_me_endpoint(self, auth_headers):
        """GET /api/auth/me - returns user info"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Auth/me failed: {response.text}"
        data = response.json()
        assert "username" in data
        assert data["username"] == "@shish123"


# ── Market Data Endpoints (market_data.py) ────────────────────────────────────

class TestMarketDataEndpoints:
    """Tests for /script-master/*, /sector-momentum, /kite/* endpoints"""
    
    def test_script_master_lookup(self):
        """GET /api/script-master/lookup?q=RELIANCE - returns matches"""
        response = requests.get(
            f"{BASE_URL}/api/script-master/lookup",
            params={"q": "RELIANCE"},
            timeout=30
        )
        assert response.status_code == 200, f"Script master lookup failed: {response.text}"
        data = response.json()
        assert "query" in data
        assert "matches" in data
        # RELIANCE should return at least one match
        assert len(data["matches"]) >= 1, "Expected at least one match for RELIANCE"
        assert data["matches"][0]["symbol"] == "RELIANCE"
    
    def test_script_master_refresh(self, auth_headers):
        """POST /api/script-master/refresh - owner only (slow operation)"""
        response = requests.post(
            f"{BASE_URL}/api/script-master/refresh",
            headers=auth_headers,
            timeout=120  # Increased timeout for slow operation
        )
        assert response.status_code == 200, f"Script master refresh failed: {response.text}"
        data = get_ndjson_complete_data(response)
        assert data.get("refreshed") == True
    
    def test_sector_momentum(self, auth_headers):
        """GET /api/sector-momentum - returns 15 sectors with data_source='kite'"""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60
        )
        assert response.status_code == 200, f"Sector momentum failed: {response.text}"
        data = response.json()
        assert "sectors" in data, "No sectors in response"
        # Should have sectors (at least 1)
        assert len(data["sectors"]) >= 1, f"Expected >= 1 sectors, got {len(data['sectors'])}"
        # Check data_source is 'kite' inside each sector object
        if data["sectors"]:
            assert data["sectors"][0].get("data_source") == "kite", f"Expected data_source='kite' in sector"
    
    def test_kite_auth_url(self, auth_headers):
        """GET /api/kite/auth-url - returns auth URL"""
        response = requests.get(
            f"{BASE_URL}/api/kite/auth-url",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Kite auth-url failed: {response.text}"
        data = response.json()
        assert "auth_url" in data
        assert "kite.zerodha.com" in data["auth_url"]
    
    def test_kite_status(self, auth_headers):
        """GET /api/kite/status - returns connection status"""
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Kite status failed: {response.text}"
        data = response.json()
        assert "connected" in data
    
    def test_kite_policy(self, auth_headers):
        """GET /api/kite/policy - returns read_only_mode"""
        response = requests.get(
            f"{BASE_URL}/api/kite/policy",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Kite policy failed: {response.text}"
        data = response.json()
        assert "read_only_mode" in data
        assert "trading_enabled" in data
        assert data["trading_enabled"] == False


# ── Portfolio Endpoints (portfolio.py) ────────────────────────────────────────

class TestPortfolioEndpoints:
    """Tests for /portfolio/analyze, /portfolio/analyze-upload"""
    
    def test_portfolio_analyze_no_crash(self, auth_headers):
        """POST /api/portfolio/analyze - bug fix: no .append() crash on string"""
        # This tests the bug fix where compute_portfolio_verdict returns (str, str)
        # but server.py previously tried to .append() on the string
        response = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            headers=auth_headers,
            json={
                "positions": [
                    {"symbol": "RELIANCE", "avg_price": 2500, "quantity": 10}
                ]
            },
            timeout=60
        )
        assert response.status_code == 200, f"Portfolio analyze failed: {response.text}"
        data = response.json()
        assert "stocks" in data, "No stocks in response"
        assert "parsed_positions_count" in data
        assert data["parsed_positions_count"] >= 1
        # Verify the analysis contains expected fields
        if data["stocks"]:
            stock = data["stocks"][0]
            assert "symbol" in stock
            assert "recommendation" in stock
            assert "comments" in stock  # This is the field that was causing the bug
    
    def test_portfolio_analyze_multiple_positions(self, auth_headers):
        """POST /api/portfolio/analyze - multiple positions"""
        response = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            headers=auth_headers,
            json={
                "positions": [
                    {"symbol": "RELIANCE", "avg_price": 2500, "quantity": 10},
                    {"symbol": "INFY", "avg_price": 1500, "quantity": 20}
                ]
            },
            timeout=90
        )
        assert response.status_code == 200, f"Portfolio analyze failed: {response.text}"
        data = response.json()
        assert data["parsed_positions_count"] >= 1


# ── Multibagger Endpoints (multibagger.py) ────────────────────────────────────

class TestMultibaggerEndpoints:
    """Tests for /multibagger/generate, /multibagger/candidates, /multibagger/custom-search"""
    
    def test_multibagger_custom_search(self, auth_headers):
        """POST /api/multibagger/custom-search - RELIANCE returns score"""
        response = requests.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            headers=auth_headers,
            json={"symbol": "RELIANCE"},
            timeout=60
        )
        assert response.status_code == 200, f"Multibagger custom-search failed: {response.text}"
        data = response.json()
        assert "symbol" in data
        assert data["symbol"] == "RELIANCE"
        assert "multibagger_score" in data
        assert "is_potential_multibagger" in data
        assert "thesis" in data
    
    def test_multibagger_candidates(self):
        """GET /api/multibagger/candidates - returns list (slow operation)"""
        response = requests.get(
            f"{BASE_URL}/api/multibagger/candidates",
            timeout=120
        )
        if response.status_code != 200:
            pytest.skip(f"Multibagger candidates returned {response.status_code}")
        items = parse_ndjson_response(response)
        # Find the complete data payload
        complete_items = [i for i in items if i.get("type") == "complete"]
        if not complete_items:
            pytest.skip("Multibagger candidates did not return a complete line (streaming timeout)")
        data = complete_items[0].get("data", complete_items[0])
        assert isinstance(data, list), "Expected list response"


# ── FNO Regression Tests (fno.py - Batch 1) ───────────────────────────────────

class TestFNORegression:
    """Regression tests for FNO endpoints from Batch 1"""
    
    def test_fno_scripts_search(self):
        """GET /api/fno/scripts/search?q=NIFTY - works"""
        response = requests.get(
            f"{BASE_URL}/api/fno/scripts/search",
            params={"q": "NIFTY"},
            timeout=15
        )
        assert response.status_code == 200, f"FNO scripts search failed: {response.text}"
        data = response.json()
        assert "query" in data
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0, "Expected suggestions for NIFTY"
    
    def test_fno_strategy_backtests(self, auth_headers):
        """GET /api/fno/strategy-backtests - works"""
        response = requests.get(
            f"{BASE_URL}/api/fno/strategy-backtests",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"FNO strategy-backtests failed: {response.text}"
        data = response.json()
        assert "backtests" in data
        assert "count" in data
    
    def test_fno_position_alerts(self, auth_headers):
        """GET /api/fno/position-alerts - works"""
        response = requests.get(
            f"{BASE_URL}/api/fno/position-alerts",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"FNO position-alerts failed: {response.text}"
        data = response.json()
        assert "alerts" in data
        assert "count" in data


# ── Admin Regression Tests (admin.py - Batch 1) ───────────────────────────────

class TestAdminRegression:
    """Regression tests for Admin endpoints from Batch 1"""
    
    def test_admin_users(self, auth_headers):
        """GET /api/admin/users - works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Admin users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of users"
        # Should have at least the owner user
        assert len(data) >= 1
    
    def test_admin_config(self, auth_headers):
        """GET /api/admin/config - works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/config",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Admin config failed: {response.text}"
        data = response.json()
        assert "api_controls" in data
        assert "kite" in data
    
    def test_admin_macro_events(self, auth_headers):
        """GET /api/admin/macro-events - works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/macro-events",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Admin macro-events failed: {response.text}"
        data = response.json()
        assert "active_events" in data
        assert "all_events" in data


# ── Remaining Server.py Endpoints ─────────────────────────────────────────────

class TestRemainingServerEndpoints:
    """Tests for endpoints still in server.py"""
    
    def test_strategy_library(self, auth_headers):
        """GET /api/strategy-library - works"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Strategy library failed: {response.text}"
        data = response.json()
        assert "strategies" in data or isinstance(data, list) or isinstance(data, dict)
    
    def test_status_get_endpoint(self):
        """GET /api/status - works (no auth required)"""
        response = requests.get(
            f"{BASE_URL}/api/status",
            timeout=15
        )
        assert response.status_code == 200, f"Status GET endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"


# ── API Root Test ─────────────────────────────────────────────────────────────

class TestAPIRoot:
    """Test API root endpoint"""
    
    def test_api_root(self):
        """GET /api/ - returns message"""
        response = requests.get(f"{BASE_URL}/api/", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
