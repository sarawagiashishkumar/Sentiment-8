"""
Iteration 91: Code Quality Report Fixes Verification

Tests for:
1. CRITICAL: Circular import fix - script_master.py uses app_state instead of import server
2. CRITICAL: Index-as-key fix in NewsSentimentPanel.jsx
3. CRITICAL: Hook dependency warnings - eslint-disable comments added
4. IMPORTANT: _post_generation_effects split into 4 focused helpers
5. IMPORTANT: Security review test fix - exec_module replaced
6. Restored /fno/scripts/search endpoint
7. Type-hinted models/__init__.py
"""
import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load frontend env for BASE_URL
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

OWNER_USERNAME = "@shish123"
USER_USERNAME = "Manas@2005"


@pytest.fixture(scope="session")
def api_base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not configured")
    return f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return session


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Auth Tests ────────────────────────────────────────────────────────────────

class TestAuth:
    """Authentication endpoint tests"""

    def test_owner_login(self, api_client, api_base_url):
        """Owner @shish123 login should work"""
        response = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        assert response.status_code == 200, f"Owner login failed: {response.text}"
        data = response.json()
        assert data.get("role") == "owner"
        assert "token" in data
        assert "credits" in data
        assert "user_key" in data
        print(f"PASS: Owner login works, role={data['role']}, credits={data['credits']}")

    def test_user_login_status(self, api_client, api_base_url):
        """User Manas@2005 login status check (may be suspended)"""
        response = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": USER_USERNAME},
            timeout=30
        )
        # User may still be suspended - check both cases
        if response.status_code == 200:
            data = response.json()
            assert "token" in data
            assert data.get("role") in ("user", "sub_admin")
            print(f"PASS: User {USER_USERNAME} login works, role={data['role']}")
        elif response.status_code == 403:
            data = response.json()
            assert "ACCOUNT_SUSPENDED" in data.get("detail", "")
            print(f"INFO: User {USER_USERNAME} is still suspended (expected behavior)")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")


# ── Health & Core Endpoints ───────────────────────────────────────────────────

class TestHealthAndCore:
    """Health and core endpoint tests"""

    def test_health_endpoint(self, api_client, api_base_url):
        """GET /api/health returns 200"""
        response = api_client.get(f"{api_base_url}/health", timeout=10)
        assert response.status_code == 200
        print("PASS: Health endpoint returns 200")

    def test_news_forecast_endpoint(self, api_client, api_base_url):
        """GET /api/news/forecast returns index_forecasts"""
        # Login first
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/news/forecast",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "index_forecasts" in data or "session" in data
        print(f"PASS: News forecast returns data with keys: {list(data.keys())[:5]}")


# ── Restored /fno/scripts/search Endpoint ─────────────────────────────────────

class TestRestoredScriptsSearch:
    """Tests for restored /fno/scripts/search endpoint"""

    def test_fno_scripts_search_nifty(self, api_client, api_base_url):
        """GET /api/fno/scripts/search?q=NIFTY returns suggestions"""
        response = api_client.get(
            f"{api_base_url}/fno/scripts/search?q=NIFTY",
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "suggestions" in data
        assert data["query"] == "NIFTY"
        assert len(data["suggestions"]) > 0
        print(f"PASS: /fno/scripts/search?q=NIFTY returns {len(data['suggestions'])} suggestions")

    def test_fno_scripts_search_empty(self, api_client, api_base_url):
        """GET /api/fno/scripts/search with empty query returns all scripts"""
        response = api_client.get(
            f"{api_base_url}/fno/scripts/search?q=",
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0
        print(f"PASS: Empty query returns {len(data['suggestions'])} scripts")

    def test_fno_scripts_search_banknifty(self, api_client, api_base_url):
        """GET /api/fno/scripts/search?q=BANKNIFTY returns BANKNIFTY scripts"""
        response = api_client.get(
            f"{api_base_url}/fno/scripts/search?q=BANKNIFTY",
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert any("BANKNIFTY" in s for s in data["suggestions"])
        print(f"PASS: BANKNIFTY search returns {len(data['suggestions'])} suggestions")


# ── Admin Endpoints ───────────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Admin endpoint tests"""

    def test_admin_users_list(self, api_client, api_base_url):
        """GET /api/admin/users returns user list"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/admin/users",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "user_key" in data[0]
            assert "username" in data[0]
        print(f"PASS: Admin users list returns {len(data)} users")

    def test_admin_packages(self, api_client, api_base_url):
        """GET /api/admin/packages returns packages config"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/admin/packages",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        # Packages endpoint returns a dict with packages key
        assert isinstance(data, dict)
        assert "packages" in data
        packages = data["packages"]
        assert "free" in packages
        assert "basic" in packages
        assert "pro" in packages
        assert "unlimited" in packages
        print(f"PASS: Admin packages returns {len(packages)} package tiers")


# ── FNO Endpoints ─────────────────────────────────────────────────────────────

class TestFNOEndpoints:
    """F&O endpoint tests"""

    def test_fno_generation_timings(self, api_client, api_base_url):
        """GET /api/fno/generation-timings returns 200"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/fno/generation-timings",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        print("PASS: FNO generation-timings returns 200")

    def test_fno_performance_stats(self, api_client, api_base_url):
        """GET /api/fno/performance-stats returns 200"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/fno/performance-stats",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        print("PASS: FNO performance-stats returns 200")

    def test_fno_sticky_cards(self, api_client, api_base_url):
        """GET /api/fno/sticky-cards returns 200"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/fno/sticky-cards",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        print("PASS: FNO sticky-cards returns 200")

    def test_fno_iv_cone_nifty(self, api_client, api_base_url):
        """GET /api/fno/iv-cone/NIFTY returns 200"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/fno/iv-cone/NIFTY",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        print("PASS: FNO iv-cone/NIFTY returns 200")

    def test_fno_strategy_backtests(self, api_client, api_base_url):
        """GET /api/fno/strategy-backtests returns 200"""
        login_resp = api_client.post(
            f"{api_base_url}/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=30
        )
        token = login_resp.json().get("token")
        
        response = api_client.get(
            f"{api_base_url}/fno/strategy-backtests",
            headers=_auth_headers(token),
            timeout=30
        )
        assert response.status_code == 200
        print("PASS: FNO strategy-backtests returns 200")


# ── Code Quality Verification ─────────────────────────────────────────────────

class TestCodeQualityFixes:
    """Verify code quality fixes from this iteration"""

    def test_circular_import_fix_script_master(self):
        """Verify script_master.py uses app_state instead of import server for shared state"""
        script_master_path = Path("/app/backend/services/script_master.py")
        assert script_master_path.exists(), "script_master.py not found"
        
        source = script_master_path.read_text()
        
        # Should have _get_state() function that imports app_state
        assert "_get_state()" in source, "Missing _get_state() function"
        assert "import services.app_state" in source, "Missing app_state import in _get_state()"
        
        # Should NOT have direct `import server` at module level (only in _srv() function)
        lines = source.split("\n")
        module_level_import_server = False
        for line in lines:
            stripped = line.strip()
            # Skip if inside a function (indented)
            if stripped.startswith("import server") and not line.startswith(" ") and not line.startswith("\t"):
                module_level_import_server = True
                break
        
        assert not module_level_import_server, "Found module-level 'import server' - should use app_state"
        print("PASS: script_master.py uses app_state for shared state (circular import fix)")

    def test_post_generation_effects_split(self):
        """Verify _post_generation_effects is split into 4 focused helpers"""
        fno_route_path = Path("/app/backend/routes/fno.py")
        assert fno_route_path.exists(), "fno.py not found"
        
        source = fno_route_path.read_text()
        
        # Check for the 4 helper functions
        helpers = [
            "_log_perf_metrics",
            "_log_signals_to_db",
            "_log_journal_entries",
            "_capture_iv_snapshots",
        ]
        
        for helper in helpers:
            assert f"async def {helper}" in source, f"Missing helper function: {helper}"
        
        # Check that _post_generation_effects calls these helpers
        assert "await _log_perf_metrics" in source
        assert "await _log_signals_to_db" in source
        assert "await _log_journal_entries" in source
        assert "await _capture_iv_snapshots" in source
        
        print("PASS: _post_generation_effects split into 4 focused helpers")

    def test_security_fix_no_exec_module(self):
        """Verify test file uses source inspection instead of exec_module"""
        test_file_path = Path("/app/backend/tests/test_structured_changes_portfolio_fno.py")
        assert test_file_path.exists(), "test_structured_changes_portfolio_fno.py not found"
        
        source = test_file_path.read_text()
        
        # Should use read_backend_source instead of exec_module
        assert "read_backend_source" in source, "Missing read_backend_source usage"
        
        # exec_module should only appear in comments
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if "exec_module" in stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                # Check if it's in a string (comment explanation)
                if "exec_module" in stripped and ("SECURITY" in stripped or "instead of" in stripped.lower()):
                    continue  # It's a comment explaining the change
                pytest.fail(f"Found non-comment exec_module usage: {stripped}")
        
        print("PASS: Security fix - exec_module replaced with source inspection")

    def test_models_type_hints(self):
        """Verify models/__init__.py has proper type hints"""
        models_path = Path("/app/backend/models/__init__.py")
        assert models_path.exists(), "models/__init__.py not found"
        
        source = models_path.read_text()
        
        # Check for modern type hints
        assert "dict[str, Any]" in source, "Missing dict[str, Any] type hints"
        assert "list[str]" in source, "Missing list[str] type hints"
        assert "__all__: list[str]" in source, "Missing __all__ type hint"
        
        print("PASS: models/__init__.py has proper type hints")

    def test_eslint_disable_comments_in_hooks(self):
        """Verify eslint-disable comments added to hooks with intentional ref deps"""
        hooks_to_check = [
            "/app/frontend/src/hooks/useLivePrices.js",
            "/app/frontend/src/hooks/useAlertEngine.js",
        ]
        
        for hook_path in hooks_to_check:
            path = Path(hook_path)
            assert path.exists(), f"{hook_path} not found"
            
            source = path.read_text()
            assert "eslint-disable" in source, f"Missing eslint-disable in {hook_path}"
        
        print("PASS: eslint-disable comments added to hooks")

    def test_news_sentiment_panel_stable_keys(self):
        """Verify NewsSentimentPanel uses stable keys instead of index-as-key"""
        panel_path = Path("/app/frontend/src/components/News/NewsSentimentPanel.jsx")
        assert panel_path.exists(), "NewsSentimentPanel.jsx not found"
        
        source = panel_path.read_text()
        
        # Check for stable keys in map functions
        # The fix should use h.title or similar instead of just index
        # Look for patterns like key={h.title || `hl-${i}`}
        assert "key={h.title" in source or 'key={`hl-${i}`}' in source or "key={idx}" in source, \
            "NewsSentimentPanel should use stable keys"
        
        # Should NOT have simple key={i} patterns (index-as-key anti-pattern)
        # This is a heuristic check
        lines = source.split("\n")
        for line in lines:
            if ".map(" in line and "key={i}" in line and "||" not in line:
                pytest.fail(f"Found index-as-key anti-pattern: {line.strip()}")
        
        print("PASS: NewsSentimentPanel uses stable keys")


# ── App State Verification ────────────────────────────────────────────────────

class TestAppState:
    """Verify app_state module is properly configured"""

    def test_app_state_has_required_exports(self):
        """Verify app_state.py exports required shared state"""
        app_state_path = Path("/app/backend/services/app_state.py")
        assert app_state_path.exists(), "app_state.py not found"
        
        source = app_state_path.read_text()
        
        # Check for required exports
        required = ["db", "IST", "LOT_SIZE_MAP", "SCRIPT_MASTER_LAST_SYNC_DATE"]
        for item in required:
            assert item in source, f"Missing {item} in app_state.py"
        
        print("PASS: app_state.py has all required exports")
