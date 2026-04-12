"""
Iteration 61: Phase 9 Code Quality Refactoring Tests

Tests for:
1. Backend starts without import errors (heartbeat)
2. Auth login works for owner (@shish123)
3. Admin users endpoint returns valid user list
4. Kite status endpoint returns status
5. Sector momentum endpoint (tests app_state.db migration)
6. Market sector-stocks endpoint (tests app_state.db migration)
7. F&O BBE alerts endpoint returns alerts array
8. app_state.py has expanded state vars (KITE_API_SECRET, KITE_REDIRECT_URL, SECTOR_MOMENTUM_CACHE)
9. market_data.py uses _state imports instead of lazy server imports
10. script_master.py uses static datetime import (not __import__)
11. batch_jobs.py has extracted helper functions
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://sentiment-engine-ai.preview.emergentagent.com"


@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token for authenticated requests."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Owner login failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    """Auth headers for authenticated requests."""
    return {"Authorization": f"Bearer {owner_token}"}


# ── Backend Startup Tests ─────────────────────────────────────────────────────

class TestBackendStartup:
    """Verify backend starts without import errors."""

    def test_heartbeat_returns_alive(self):
        """Backend should start without circular import errors."""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200, f"Heartbeat failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "alive", f"Expected status=alive, got {data}"
        print("PASS: Backend started without import errors, heartbeat returns alive")


# ── Auth Tests ────────────────────────────────────────────────────────────────

class TestAuthAccess:
    """Test auth login endpoints."""

    def test_owner_login_shish123(self):
        """Owner @shish123 login should succeed."""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Owner login failed: {resp.text}"
        data = resp.json()
        assert "token" in data, "Missing token in response"
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"
        assert data.get("username") == "@shish123", f"Expected username=@shish123, got {data.get('username')}"
        print(f"PASS: Owner @shish123 login successful, token length: {len(data['token'])}")

    def test_user_login_manas2005(self):
        """User Manas@2005 login should succeed."""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=15,
        )
        assert resp.status_code == 200, f"User login failed: {resp.text}"
        data = resp.json()
        assert "token" in data, "Missing token in response"
        assert data.get("role") == "user", f"Expected role=user, got {data.get('role')}"
        print(f"PASS: User Manas@2005 login successful")


# ── Admin Endpoint Tests ──────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Test admin endpoints."""

    def test_admin_users_returns_valid_list(self, auth_headers):
        """Admin users endpoint should return valid user list."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Admin users failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) >= 2, f"Expected at least 2 users, got {len(data)}"
        
        # Verify user structure
        usernames = [u.get("username") for u in data]
        assert "@shish123" in usernames, "Owner @shish123 not in user list"
        assert "Manas@2005" in usernames, "User Manas@2005 not in user list"
        print(f"PASS: Admin users returns {len(data)} users including @shish123 and Manas@2005")


# ── Kite Status Tests ─────────────────────────────────────────────────────────

class TestKiteStatus:
    """Test Kite status endpoint."""

    def test_kite_status_returns_status(self, auth_headers):
        """Kite status endpoint should return connected status."""
        resp = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Kite status failed: {resp.text}"
        data = resp.json()
        # Should have 'connected' field (true or false)
        assert "connected" in data, f"Missing 'connected' field in response: {data}"
        print(f"PASS: Kite status returns connected={data.get('connected')}")


# ── Sector Momentum Tests (app_state.db migration) ────────────────────────────

class TestSectorMomentum:
    """Test sector momentum endpoint - validates app_state.db migration."""

    def test_sector_momentum_returns_data(self, auth_headers):
        """Sector momentum should return sector data using _state.db."""
        resp = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60,  # Can be slow
        )
        assert resp.status_code == 200, f"Sector momentum failed: {resp.text}"
        data = resp.json()
        
        # Should have sectors array
        assert "sectors" in data, f"Missing 'sectors' field: {data.keys()}"
        sectors = data.get("sectors", [])
        assert len(sectors) >= 10, f"Expected at least 10 sectors, got {len(sectors)}"
        
        # Verify sector structure
        if sectors:
            first_sector = sectors[0]
            assert "sector" in first_sector or "name" in first_sector, f"Missing sector name: {first_sector}"
        
        print(f"PASS: Sector momentum returns {len(sectors)} sectors (app_state.db migration works)")


# ── Market Sector Stocks Tests (app_state.db migration) ───────────────────────

class TestMarketSectorStocks:
    """Test market sector-stocks endpoint - validates app_state.db migration."""

    def test_sector_stocks_returns_stocks(self, auth_headers):
        """Sector stocks should return stocks for NIFTY IT using _state.db."""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "NIFTY IT"},
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Sector stocks failed: {resp.text}"
        data = resp.json()
        
        # Should have stocks array
        assert "stocks" in data, f"Missing 'stocks' field: {data.keys()}"
        stocks = data.get("stocks", [])
        
        # Should have sector field
        assert "sector" in data, f"Missing 'sector' field: {data.keys()}"
        
        print(f"PASS: Sector stocks returns {len(stocks)} stocks for sector '{data.get('sector')}' (app_state.db migration works)")


# ── F&O BBE Alerts Tests ──────────────────────────────────────────────────────

class TestFNOEndpoints:
    """Test F&O endpoints."""

    def test_bbe_alerts_returns_array(self, auth_headers):
        """BBE alerts should return alerts array."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/bbe-alerts",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"BBE alerts failed: {resp.text}"
        data = resp.json()
        
        # Should have alerts array
        assert "alerts" in data, f"Missing 'alerts' field: {data.keys()}"
        alerts = data.get("alerts", [])
        assert isinstance(alerts, list), f"Expected alerts to be list, got {type(alerts)}"
        
        print(f"PASS: BBE alerts returns {len(alerts)} alerts")


# ── Code Structure Tests ──────────────────────────────────────────────────────

class TestAppStateModule:
    """Test app_state.py has expanded state vars."""

    def test_app_state_has_expanded_vars(self):
        """app_state.py should have KITE_API_SECRET, KITE_REDIRECT_URL, SECTOR_MOMENTUM_CACHE."""
        app_state_path = "/app/backend/services/app_state.py"
        with open(app_state_path, "r") as f:
            content = f.read()
        
        # Check for expanded state vars
        assert "KITE_API_SECRET" in content, "Missing KITE_API_SECRET in app_state.py"
        assert "KITE_REDIRECT_URL" in content, "Missing KITE_REDIRECT_URL in app_state.py"
        assert "SECTOR_MOMENTUM_CACHE" in content, "Missing SECTOR_MOMENTUM_CACHE in app_state.py"
        assert "SCRIPT_MASTER_LAST_SYNC_DATE" in content, "Missing SCRIPT_MASTER_LAST_SYNC_DATE in app_state.py"
        
        print("PASS: app_state.py has expanded state vars (KITE_API_SECRET, KITE_REDIRECT_URL, SECTOR_MOMENTUM_CACHE, SCRIPT_MASTER_LAST_SYNC_DATE)")


class TestMarketDataImports:
    """Test market_data.py uses _state imports."""

    def test_market_data_uses_state_imports(self):
        """market_data.py should import from services.app_state as _state."""
        market_data_path = "/app/backend/routes/market_data.py"
        with open(market_data_path, "r") as f:
            content = f.read()
        
        # Check for _state import
        assert "import services.app_state as _state" in content, "Missing 'import services.app_state as _state' in market_data.py"
        
        # Check for _state.db usage
        assert "_state.db" in content, "Missing _state.db usage in market_data.py"
        
        # Check for _state.KITE_API_KEY usage
        assert "_state.KITE_API_KEY" in content, "Missing _state.KITE_API_KEY usage in market_data.py"
        
        # Check for _state.SECTOR_MOMENTUM_CACHE usage
        assert "_state.SECTOR_MOMENTUM_CACHE" in content, "Missing _state.SECTOR_MOMENTUM_CACHE usage in market_data.py"
        
        print("PASS: market_data.py uses _state imports (db, KITE_API_KEY, SECTOR_MOMENTUM_CACHE)")


class TestScriptMasterStaticImport:
    """Test script_master.py uses static datetime import."""

    def test_script_master_static_datetime_import(self):
        """script_master.py should use static 'from datetime import datetime' not __import__."""
        script_master_path = "/app/backend/services/script_master.py"
        with open(script_master_path, "r") as f:
            content = f.read()
        
        # Check for static datetime import
        assert "from datetime import datetime" in content, "Missing static datetime import in script_master.py"
        
        # Check that __import__('datetime') is NOT used
        assert "__import__('datetime')" not in content, "Found dynamic __import__('datetime') in script_master.py - should use static import"
        
        print("PASS: script_master.py uses static datetime import (not __import__)")


class TestBatchJobsHelperExtraction:
    """Test batch_jobs.py has extracted helper functions."""

    def test_batch_jobs_has_extracted_helpers(self):
        """batch_jobs.py should have _build_mfe_for_symbol and _build_fwd_mfe_for_symbol helpers."""
        batch_jobs_path = "/app/backend/routes/batch_jobs.py"
        with open(batch_jobs_path, "r") as f:
            content = f.read()
        
        # Check for extracted helper functions
        assert "async def _build_mfe_for_symbol" in content, "Missing _build_mfe_for_symbol helper in batch_jobs.py"
        assert "async def _build_fwd_mfe_for_symbol" in content, "Missing _build_fwd_mfe_for_symbol helper in batch_jobs.py"
        
        # Check that helpers are called in main functions
        assert "_build_mfe_for_symbol(" in content, "_build_mfe_for_symbol not called in batch_jobs.py"
        assert "_build_fwd_mfe_for_symbol(" in content, "_build_fwd_mfe_for_symbol not called in batch_jobs.py"
        
        print("PASS: batch_jobs.py has extracted helper functions (_build_mfe_for_symbol, _build_fwd_mfe_for_symbol)")


class TestKiteLiveWarningRef:
    """Test KiteLiveWarning uses disconnectedRef instead of state."""

    def test_kite_live_warning_uses_ref(self):
        """KiteLiveWarning.jsx should use disconnectedRef for stale closure fix."""
        kite_warning_path = "/app/frontend/src/components/Shared/KiteLiveWarning.jsx"
        with open(kite_warning_path, "r") as f:
            content = f.read()
        
        # Check for disconnectedRef
        assert "disconnectedRef" in content, "Missing disconnectedRef in KiteLiveWarning.jsx"
        assert "useRef" in content, "Missing useRef import in KiteLiveWarning.jsx"
        
        # Check that disconnectedRef.current is used in callback
        assert "disconnectedRef.current" in content, "Missing disconnectedRef.current usage in KiteLiveWarning.jsx"
        
        print("PASS: KiteLiveWarning.jsx uses disconnectedRef for stale closure fix")


class TestFNOIVAnalyticsConstants:
    """Test FNOIVAnalytics has extracted chart constants."""

    def test_fno_iv_analytics_has_chart_constants(self):
        """FNOIVAnalytics.jsx should have extracted chart style constants."""
        fno_iv_path = "/app/frontend/src/components/FNO/FNOIVAnalytics.jsx"
        with open(fno_iv_path, "r") as f:
            content = f.read()
        
        # Check for extracted chart constants
        assert "CHART_TICK" in content, "Missing CHART_TICK constant in FNOIVAnalytics.jsx"
        assert "CHART_GRID_DASH" in content, "Missing CHART_GRID_DASH constant in FNOIVAnalytics.jsx"
        assert "CHART_GRID_STROKE" in content, "Missing CHART_GRID_STROKE constant in FNOIVAnalytics.jsx"
        assert "TOOLTIP_STYLE" in content, "Missing TOOLTIP_STYLE constant in FNOIVAnalytics.jsx"
        
        # Check that constants are defined at module level (before function)
        lines = content.split("\n")
        chart_tick_line = None
        function_line = None
        for i, line in enumerate(lines):
            if "const CHART_TICK" in line and chart_tick_line is None:
                chart_tick_line = i
            if "export function FNOIVAnalytics" in line and function_line is None:
                function_line = i
        
        assert chart_tick_line is not None, "CHART_TICK not found"
        assert function_line is not None, "FNOIVAnalytics function not found"
        assert chart_tick_line < function_line, "CHART_TICK should be defined before FNOIVAnalytics function (module-level constant)"
        
        print("PASS: FNOIVAnalytics.jsx has extracted chart style constants at module level")


# ── Regression Tests ──────────────────────────────────────────────────────────

class TestRegressionEndpoints:
    """Regression tests for existing functionality."""

    def test_sector_momentum_endpoint(self, auth_headers):
        """Sector momentum should still work after app_state migration."""
        resp = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200, f"Sector momentum regression failed: {resp.text}"
        data = resp.json()
        sectors = data.get("sectors", [])
        assert len(sectors) >= 10, f"Expected at least 10 sectors, got {len(sectors)}"
        print(f"PASS: Sector momentum regression - {len(sectors)} sectors returned")

    def test_sector_drilldown_works(self, auth_headers):
        """Sector drill-down should work after app_state migration."""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "NIFTY IT"},
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Sector drill-down regression failed: {resp.text}"
        data = resp.json()
        stocks = data.get("stocks", [])
        print(f"PASS: Sector drill-down regression - {len(stocks)} stocks for NIFTY IT")
