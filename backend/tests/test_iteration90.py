"""
Iteration 90: Type hints verification, security fix validation, and restored endpoint testing.

Tests:
1. Type-hinted models/__init__.py doesn't break API serialization
2. Security-fixed test file (test_structured_changes_portfolio_fno.py) still passes
3. Restored /fno/scripts/search endpoint works
4. Regression: All critical endpoints still work
"""
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

from tests.helpers.test_utils import get_base_url

load_dotenv(Path("/app/frontend/.env"))
BASE_URL = get_base_url()
OWNER_USERNAME = "@shish123"
USER_USERNAME = "Manas@2005"


@pytest.fixture(scope="session")
def api_base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not configured")
    return BASE_URL.rstrip("/") + "/api"


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return session


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client: requests.Session, api_base_url: str, username: str) -> dict:
    response = client.post(f"{api_base_url}/auth/access", json={"username": username}, timeout=30)
    assert response.status_code == 200, f"Login failed: {response.text}"
    payload = response.json()
    assert isinstance(payload.get("token"), str) and payload["token"]
    return payload


# ── Auth Tests ────────────────────────────────────────────────────────────────

class TestAuth:
    """Authentication endpoint tests - verify type-hinted models serialize correctly"""
    
    def test_owner_login(self, api_client, api_base_url):
        """Test owner @shish123 login - verifies AccessResponse model serialization"""
        payload = _login(api_client, api_base_url, OWNER_USERNAME)
        assert payload["role"] == "owner"
        assert "token" in payload
        assert "credits" in payload
        assert "user_key" in payload
        assert "username" in payload
        assert "admin_exempt" in payload
        # Verify new fields from type-hinted model
        assert "fno_budget" in payload
        assert "account_risk_pct" in payload
        print(f"PASS: Owner login works, role={payload['role']}")
    
    def test_user_login_suspended(self, api_client, api_base_url):
        """Test user Manas@2005 login - expected to be suspended"""
        response = api_client.post(
            f"{api_base_url}/auth/access", 
            json={"username": USER_USERNAME}, 
            timeout=30
        )
        # User is suspended - this is expected behavior
        if response.status_code == 403:
            data = response.json()
            assert "ACCOUNT_SUSPENDED" in data.get("detail", "")
            print(f"PASS: User {USER_USERNAME} is suspended as expected")
        elif response.status_code == 200:
            payload = response.json()
            assert payload["role"] in ["user", "sub_admin"]
            print(f"PASS: User login works, role={payload['role']}")
    
    def test_auth_me_endpoint(self, api_client, api_base_url):
        """Test GET /api/auth/me returns role, credits, package, suspended fields"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(f"{api_base_url}/auth/me", headers=headers, timeout=30)
        assert response.status_code == 200, f"GET /auth/me failed: {response.text}"
        
        data = response.json()
        # Verify MeResponse model fields
        assert "role" in data
        assert "credits" in data
        assert "user_key" in data
        assert "username" in data
        assert "admin_exempt" in data
        assert "fno_budget" in data
        assert "account_risk_pct" in data
        assert "package" in data  # New field from type-hinted model
        assert "suspended" in data  # New field from type-hinted model
        print(f"PASS: GET /auth/me returns all fields including package={data.get('package')}, suspended={data.get('suspended')}")


# ── Restored Endpoint Test ────────────────────────────────────────────────────

class TestRestoredEndpoint:
    """Test the restored /fno/scripts/search endpoint"""
    
    def test_fno_scripts_search_nifty(self, api_client, api_base_url):
        """Test GET /api/fno/scripts/search?q=NIFTY returns query and suggestions"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(
            f"{api_base_url}/fno/scripts/search",
            params={"q": "NIFTY"},
            headers=headers,
            timeout=30
        )
        assert response.status_code == 200, f"GET /fno/scripts/search failed: {response.text}"
        
        data = response.json()
        # Verify ScriptSearchResult model fields
        assert "query" in data
        assert "suggestions" in data
        assert data["query"] == "NIFTY"
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) > 0, "Expected at least one NIFTY suggestion"
        print(f"PASS: /fno/scripts/search?q=NIFTY returns {len(data['suggestions'])} suggestions")
    
    def test_fno_scripts_search_empty(self, api_client, api_base_url):
        """Test GET /api/fno/scripts/search with empty query returns all scripts"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(
            f"{api_base_url}/fno/scripts/search",
            params={"q": ""},
            headers=headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "query" in data
        assert "suggestions" in data
        assert data["query"] == ""
        assert isinstance(data["suggestions"], list)
        print(f"PASS: /fno/scripts/search with empty query returns {len(data['suggestions'])} suggestions")
    
    def test_fno_scripts_search_banknifty(self, api_client, api_base_url):
        """Test GET /api/fno/scripts/search?q=BANKNIFTY"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(
            f"{api_base_url}/fno/scripts/search",
            params={"q": "BANKNIFTY"},
            headers=headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["query"] == "BANKNIFTY"
        assert isinstance(data["suggestions"], list)
        # BANKNIFTY scripts should be in suggestions
        banknifty_scripts = [s for s in data["suggestions"] if "BANKNIFTY" in s]
        assert len(banknifty_scripts) > 0, "Expected BANKNIFTY scripts in suggestions"
        print(f"PASS: /fno/scripts/search?q=BANKNIFTY returns {len(banknifty_scripts)} BANKNIFTY scripts")


# ── Admin Endpoint Tests ──────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Test admin endpoints - verify type-hinted models serialize correctly"""
    
    def test_admin_users_list(self, api_client, api_base_url):
        """Test GET /api/admin/users returns users with suspended, package fields"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(f"{api_base_url}/admin/users", headers=headers, timeout=30)
        assert response.status_code == 200, f"GET /admin/users failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            user = data[0]
            # Verify AdminUserView model fields
            assert "user_key" in user
            assert "username" in user
            assert "role" in user
            assert "credits" in user
            assert "suspended" in user  # New field from type-hinted model
            assert "package" in user  # New field from type-hinted model
        print(f"PASS: GET /admin/users returns {len(data)} users with suspended/package fields")
    
    def test_admin_packages(self, api_client, api_base_url):
        """Test GET /api/admin/packages returns packages"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(f"{api_base_url}/admin/packages", headers=headers, timeout=30)
        assert response.status_code == 200, f"GET /admin/packages failed: {response.text}"
        
        data = response.json()
        # Endpoint returns dict with 'packages' key containing package tiers
        assert isinstance(data, dict)
        assert "packages" in data
        packages = data["packages"]
        assert isinstance(packages, dict)
        # Should have at least 4 tiers: free, basic, pro, unlimited
        assert len(packages) >= 4, f"Expected at least 4 packages, got {len(packages)}"
        expected_tiers = {"free", "basic", "pro", "unlimited"}
        assert expected_tiers.issubset(set(packages.keys())), f"Missing expected tiers: {expected_tiers - set(packages.keys())}"
        print(f"PASS: GET /admin/packages returns {len(packages)} packages: {list(packages.keys())}")


# ── Health & News Endpoints ───────────────────────────────────────────────────

class TestHealthAndNews:
    """Test health and news endpoints"""
    
    def test_health_endpoint(self, api_client, api_base_url):
        """Test GET /api/health returns 200"""
        response = api_client.get(f"{api_base_url}/health", timeout=30)
        assert response.status_code == 200, f"GET /health failed: {response.text}"
        print("PASS: GET /health returns 200")
    
    def test_news_forecast_endpoint(self, api_client, api_base_url):
        """Test GET /api/news/forecast returns session, index_forecasts"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(f"{api_base_url}/news/forecast", headers=headers, timeout=60)
        assert response.status_code == 200, f"GET /news/forecast failed: {response.text}"
        
        data = response.json()
        assert "session" in data
        assert "index_forecasts" in data
        print(f"PASS: GET /news/forecast returns session={data.get('session')}")


# ── F&O Custom Positions ──────────────────────────────────────────────────────

class TestFNOCustomPositions:
    """Test F&O custom positions endpoint - verify type-hinted models serialize correctly"""
    
    def test_custom_positions_list(self, api_client, api_base_url):
        """Test POST /api/fno/custom-positions returns list"""
        owner = _login(api_client, api_base_url, OWNER_USERNAME)
        headers = _auth_headers(owner["token"])
        
        response = api_client.get(f"{api_base_url}/fno/custom-positions", headers=headers, timeout=30)
        assert response.status_code == 200, f"GET /fno/custom-positions failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        # Verify CustomPositionResponse model fields if any positions exist
        if len(data) > 0:
            pos = data[0]
            assert "id" in pos
            assert "script" in pos
            assert "underlying" in pos
            assert "status" in pos
            assert "minutes_to_expiry" in pos
            assert "monitoring_events" in pos  # list[MonitoringEvent] field
        print(f"PASS: GET /fno/custom-positions returns {len(data)} positions")


# ── Type Hints Verification ───────────────────────────────────────────────────

class TestTypeHintsVerification:
    """Verify type-hinted models don't break API serialization"""
    
    def test_models_import(self):
        """Test that models/__init__.py imports without errors"""
        try:
            from models import (
                AccessResponse, MeResponse, AdminUserView,
                FNOSignalResponse, CustomPositionResponse,
                ScriptSearchResult, MultibaggerCandidate
            )
            print("PASS: All models import successfully")
        except ImportError as e:
            pytest.fail(f"Model import failed: {e}")
    
    def test_model_validator_works(self):
        """Test that model_validator in MultibaggerCandidate works with NaN sanitization"""
        from models import MultibaggerCandidate
        import math
        
        # Test with NaN values - should be sanitized to None
        data = {
            "symbol": "TEST",
            "company_name": "Test Company",
            "sector": "IT",
            "ltp": float('nan'),  # Should become None
            "market_cap_cr": float('inf'),  # Should become None
            "pe_ratio": 15.5,  # Should remain
            "tier_pass_count": 3,
            "is_potential_multibagger": True,
            "multibagger_score": 75,
            "targeted_upside_price": {"1Y": 100},
            "targeted_upside_profit_pct": {"1Y": 10},
            "thesis": "Test thesis",
            "analysis_refreshed_at": "2026-01-01T00:00:00Z"
        }
        
        candidate = MultibaggerCandidate(**data)
        assert candidate.ltp is None, "NaN should be sanitized to None"
        assert candidate.market_cap_cr is None, "Inf should be sanitized to None"
        assert candidate.pe_ratio == 15.5, "Valid float should remain"
        print("PASS: model_validator NaN sanitization works correctly")
    
    def test_dict_any_type_hints(self):
        """Test that dict[str, Any] type hints work correctly"""
        from models import FNOSignalResponse
        
        # Create a signal with dict fields
        signal_data = {
            "script": "NIFTY25JAN24000CE",
            "underlying": "NIFTY",
            "expiry": "2025-01-30",
            "strike": 24000,
            "option_type": "CE",
            "exchange": "NFO",
            "lot_size": 50,
            "underlying_ltp": 23500,
            "option_ltp": 150,
            "ltp_margin_to_t1_amount": 50,
            "ltp_margin_to_t1_pct": 33.3,
            "achievable_profit_pct": 33.3,
            "direction": "BULLISH",
            "strategy": "LONG_CALL",
            "entry_price": 150,
            "stop_loss": 100,
            "target1": 200,
            "target2": 250,
            "risk_reward_target1": 1.5,
            "risk_reward_target2": 2.0,
            "trigger_factors": ["RSI_OVERSOLD", "SUPPORT_BOUNCE"],
            "confluence_score": 75,
            "signal_quality": "HIGH",
            "is_potential_trade": True,
            "minutes_to_expiry": 1440,
            "expiry_risk": "LOW",
            "data_source": "LIVE_OPTION_CHAIN",
            "analysis_refreshed_at": "2026-01-01T00:00:00Z",
            "macro_context": {"vix": 15.5, "regime": "NORMAL"},  # dict[str, Any]
            "index_breadth": {"advance": 30, "decline": 20},  # dict[str, Any]
            "sizing_info": {"lots": 2, "margin": 50000}  # dict[str, Any]
        }
        
        signal = FNOSignalResponse(**signal_data)
        assert signal.macro_context == {"vix": 15.5, "regime": "NORMAL"}
        assert signal.index_breadth == {"advance": 30, "decline": 20}
        assert signal.sizing_info == {"lots": 2, "margin": 50000}
        print("PASS: dict[str, Any] type hints work correctly")
    
    def test_list_str_type_hints(self):
        """Test that list[str] type hints work correctly"""
        from models import FNOSignalResponse
        
        signal_data = {
            "script": "NIFTY25JAN24000CE",
            "underlying": "NIFTY",
            "expiry": "2025-01-30",
            "strike": 24000,
            "option_type": "CE",
            "exchange": "NFO",
            "lot_size": 50,
            "underlying_ltp": 23500,
            "option_ltp": 150,
            "ltp_margin_to_t1_amount": 50,
            "ltp_margin_to_t1_pct": 33.3,
            "achievable_profit_pct": 33.3,
            "direction": "BULLISH",
            "strategy": "LONG_CALL",
            "entry_price": 150,
            "stop_loss": 100,
            "target1": 200,
            "target2": 250,
            "risk_reward_target1": 1.5,
            "risk_reward_target2": 2.0,
            "trigger_factors": ["RSI_OVERSOLD", "SUPPORT_BOUNCE", "VOLUME_SPIKE"],  # list[str]
            "confluence_score": 75,
            "signal_quality": "HIGH",
            "is_potential_trade": True,
            "minutes_to_expiry": 1440,
            "expiry_risk": "LOW",
            "data_source": "LIVE_OPTION_CHAIN",
            "analysis_refreshed_at": "2026-01-01T00:00:00Z"
        }
        
        signal = FNOSignalResponse(**signal_data)
        assert signal.trigger_factors == ["RSI_OVERSOLD", "SUPPORT_BOUNCE", "VOLUME_SPIKE"]
        assert isinstance(signal.trigger_factors, list)
        print("PASS: list[str] type hints work correctly")


# ── Security Fix Verification ─────────────────────────────────────────────────

class TestSecurityFix:
    """Verify the security fix in test_structured_changes_portfolio_fno.py"""
    
    def test_read_backend_source_function_exists(self):
        """Test that read_backend_source function exists and works"""
        from tests.helpers.test_utils import read_backend_source
        
        source = read_backend_source()
        assert isinstance(source, str)
        assert len(source) > 0
        assert "server.py" in source or "routes" in source
        print("PASS: read_backend_source function works")
    
    def test_no_exec_module_in_test_file(self):
        """Verify exec_module pattern is not used (only in comments) in test_structured_changes_portfolio_fno.py"""
        test_file = Path("/app/backend/tests/test_structured_changes_portfolio_fno.py")
        content = test_file.read_text()
        
        # exec_module should only appear in comments (explaining the security fix)
        # Check that it's not used as actual code (e.g., "loader.exec_module(" pattern)
        assert "loader.exec_module(" not in content, "exec_module should not be called as code"
        assert ".exec_module(" not in content, "exec_module should not be called as code"
        
        # Should contain read_backend_source for source inspection
        assert "read_backend_source" in content, "Should use read_backend_source for source inspection"
        
        # Verify the comment explaining the security fix exists
        assert "SECURITY: Use source-file inspection instead of exec_module" in content
        
        print("PASS: Security fix verified - exec_module only in comments, read_backend_source used for inspection")
