"""
Iteration 42: Comprehensive Regression Tests after Business Logic Extraction

Tests verify that all endpoints work correctly after extracting:
- services/fno_signal_engine.py (2,249 lines - F&O signal building)
- services/multibagger_engine.py (617 lines - multibagger screening)
- services/portfolio_engine.py (436 lines - portfolio analysis)

NOTE: Kite Connect API session is expired, so endpoints returning 0 signals
or placeholder data is EXPECTED behavior. Tests verify response SHAPE and
structure, not data values.
"""
import os
import pytest
import requests
import json
import time

from tests.helpers.test_utils import get_base_url, safe_streaming_get, safe_streaming_post

BASE_URL = get_base_url()
ADMIN_USERNAME = "@shish123"
ADMIN_PASSWORD = "1234"


class TestBackendHealth:
    """Basic health checks - run first to ensure backend is up."""

    def test_api_root_accessible(self):
        """Test that API root is accessible."""
        response = requests.get(f"{BASE_URL}/api/", timeout=10)
        # May return 404 or 200 depending on root route config
        assert response.status_code in [200, 404, 307]
        print(f"PASS: API root accessible (status={response.status_code})")

    def test_health_endpoint(self):
        """Test health endpoint if available."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        # Health endpoint may not exist, but should not 500
        assert response.status_code in [200, 404]
        print(f"PASS: Health endpoint check (status={response.status_code})")


class TestAuthEndpoint:
    """Authentication endpoint tests."""

    def test_auth_access_login(self):
        """Test admin login returns token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, f"No token in response: {data}"
        assert len(data["token"]) > 10, "Token too short"
        print(f"PASS: Auth login successful, token length={len(data['token'])}")
        return data["token"]

    def test_auth_invalid_credentials(self):
        """Test invalid credentials return 400 or 401."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "invalid_user", "password": "wrong"},
            timeout=10,
        )
        # App returns 400 for invalid credentials (validation error)
        assert response.status_code in [400, 401], f"Expected 400 or 401, got {response.status_code}"
        print("PASS: Invalid credentials correctly rejected")


class TestSectorMomentumEndpoint:
    """Sector momentum endpoint tests - verified in iteration 41."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
        return response.json().get("token")

    def test_sector_momentum_returns_200(self, auth_token):
        """Test sector momentum endpoint returns 200."""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Sector momentum returns 200")

    def test_sector_momentum_response_shape(self, auth_token):
        """Test sector momentum response has correct shape."""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required top-level keys
        assert "sectors" in data, "Missing 'sectors' key"
        assert "summary" in data, "Missing 'summary' key"
        assert "refreshed_at" in data, "Missing 'refreshed_at' key"
        assert "from_cache" in data, "Missing 'from_cache' key"
        
        assert isinstance(data["sectors"], list), "sectors should be a list"
        assert isinstance(data["summary"], dict), "summary should be a dict"
        print(f"PASS: Sector momentum response shape correct, {len(data['sectors'])} sectors")

    def test_sector_momentum_has_8_sectors(self, auth_token):
        """Test that exactly 8 NSE sectors are returned."""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        sectors = data.get("sectors", [])
        assert len(sectors) >= 1, f"Expected >= 1 sectors, got {len(sectors)}"
        
        expected_sectors = {"Banking", "IT", "Auto", "Pharma", "FMCG", "Metal", "Realty", "Energy"}
        actual_sectors = {s.get("sector") for s in sectors}
        assert actual_sectors == expected_sectors, f"Sector mismatch: {actual_sectors}"
        print("PASS: All 8 NSE sectors present")


class TestFNOGenerateEndpoint:
    """F&O generate endpoint tests - NDJSON streaming."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
        return response.json().get("token")

    def test_fno_generate_content_type(self, auth_token):
        """Test FNO generate returns NDJSON content type."""
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
            stream=True,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_type = response.headers.get("content-type", "")
        assert "application/x-ndjson" in content_type, f"Expected NDJSON, got {content_type}"
        print("PASS: FNO generate returns NDJSON content type")

    def test_fno_generate_first_line_is_progress(self, auth_token):
        """Test FNO generate first line has type=progress."""
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
            stream=True,
        )
        assert response.status_code == 200
        
        # Read first line only
        first_line = None
        for line in response.iter_lines():
            if line:
                first_line = line.decode("utf-8")
                break
        
        assert first_line is not None, "No lines received"
        first_obj = json.loads(first_line)
        assert first_obj.get("type") == "progress", f"First line type should be 'progress', got {first_obj}"
        print(f"PASS: FNO generate first line is progress: {first_obj.get('message', '')}")

    def test_fno_generate_complete_response_shape(self, auth_token):
        """Test FNO generate complete response has required keys."""
        response = safe_streaming_post(
            f"{BASE_URL}/api/fno/generate",
            json_body={},
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            skip_msg="FNO generate unavailable (Kite/timeout)",
        )
        assert response.status_code == 200
        
        # Collect all lines and find the complete line
        complete_data = None
        for line in response.text.splitlines():
            if line.strip():
                obj = json.loads(line)
                if obj.get("type") == "complete":
                    complete_data = obj.get("data", {})
                    break
        
        if complete_data is None:
            pytest.skip("No 'complete' line received — stream may have been truncated by timeout")
        
        # Check required keys in complete response
        required_keys = ["signals", "nifty_projection", "banknifty_projection", "stock_signals", "market_regime"]
        for key in required_keys:
            assert key in complete_data, f"Missing key '{key}' in complete response"
        
        print(f"PASS: FNO generate complete response has all required keys")
        print(f"  - signals: {len(complete_data.get('signals', []))}")
        print(f"  - stock_signals: {len(complete_data.get('stock_signals', []))}")
        print(f"  - market_regime: {complete_data.get('market_regime', {}).get('regime', 'N/A')}")


class TestFNOSignalsIndexEndpoint:
    """Test /api/fno/signals/index endpoint."""

    def test_fno_signals_index_returns_list(self):
        """Test FNO signals index returns a list."""
        response = safe_streaming_get(
            f"{BASE_URL}/api/fno/signals/index",
            timeout=60,
            skip_msg="FNO signals index unavailable (Kite/timeout)",
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: FNO signals index returns list with {len(data)} signals")


class TestPortfolioAnalyzeEndpoint:
    """Portfolio analyze endpoint tests."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
        return response.json().get("token")

    def test_portfolio_analyze_returns_200(self, auth_token):
        """Test portfolio analyze with valid positions returns 200."""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2500, "quantity": 10},
                {"symbol": "TCS", "avg_price": 3500, "quantity": 5},
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Portfolio analyze returns 200")

    def test_portfolio_analyze_response_shape(self, auth_token):
        """Test portfolio analyze response has required keys."""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2500, "quantity": 10},
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required keys
        assert "stocks" in data, "Missing 'stocks' key"
        assert "portfolio_risk_metrics" in data, "Missing 'portfolio_risk_metrics' key"
        assert isinstance(data["stocks"], list), "stocks should be a list"
        
        if data["stocks"]:
            stock = data["stocks"][0]
            assert "symbol" in stock, "Stock missing 'symbol'"
            assert "ltp" in stock, "Stock missing 'ltp'"
            assert "pnl_pct" in stock, "Stock missing 'pnl_pct'"
        
        print(f"PASS: Portfolio analyze response shape correct, {len(data['stocks'])} stocks analyzed")


class TestMultibaggerEndpoints:
    """Multibagger endpoint tests - NDJSON streaming."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
        return response.json().get("token")

    def test_multibagger_candidates_content_type(self):
        """Test multibagger candidates returns NDJSON content type."""
        response = requests.get(
            f"{BASE_URL}/api/multibagger/candidates",
            timeout=15,
            stream=True,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_type = response.headers.get("content-type", "")
        assert "application/x-ndjson" in content_type, f"Expected NDJSON, got {content_type}"
        print("PASS: Multibagger candidates returns NDJSON content type")

    def test_multibagger_candidates_first_line_is_progress(self):
        """Test multibagger candidates first line has type=progress."""
        response = requests.get(
            f"{BASE_URL}/api/multibagger/candidates",
            timeout=15,
            stream=True,
        )
        assert response.status_code == 200
        
        # Read first line only
        first_line = None
        for line in response.iter_lines():
            if line:
                first_line = line.decode("utf-8")
                break
        
        assert first_line is not None, "No lines received"
        first_obj = json.loads(first_line)
        assert first_obj.get("type") == "progress", f"First line type should be 'progress', got {first_obj}"
        print(f"PASS: Multibagger candidates first line is progress")

    def test_multibagger_generate_content_type(self, auth_token):
        """Test multibagger generate returns NDJSON content type."""
        response = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
            stream=True,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_type = response.headers.get("content-type", "")
        assert "application/x-ndjson" in content_type, f"Expected NDJSON, got {content_type}"
        print("PASS: Multibagger generate returns NDJSON content type")

    def test_multibagger_generate_first_line_is_progress(self, auth_token):
        """Test multibagger generate first line has type=progress."""
        response = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
            stream=True,
        )
        assert response.status_code == 200
        
        # Read first line only
        first_line = None
        for line in response.iter_lines():
            if line:
                first_line = line.decode("utf-8")
                break
        
        assert first_line is not None, "No lines received"
        first_obj = json.loads(first_line)
        assert first_obj.get("type") == "progress", f"First line type should be 'progress', got {first_obj}"
        print(f"PASS: Multibagger generate first line is progress")


class TestAdminEndpoints:
    """Admin endpoint tests."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
        return response.json().get("token")

    def test_admin_users_list(self, auth_token):
        """Test admin users list endpoint."""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: Admin users list returns {len(data)} users")


class TestServiceModuleImports:
    """Test that all service modules import correctly."""

    def test_fno_signal_engine_imports(self):
        """Test fno_signal_engine.py imports without errors."""
        import importlib
        mod = importlib.import_module("services.fno_signal_engine")
        assert hasattr(mod, "build_fno_signal"), (
            "fno_signal_engine missing 'build_fno_signal' function"
        )
        print("PASS: fno_signal_engine imports work")

    def test_multibagger_engine_imports(self):
        """Test multibagger_engine.py imports without errors."""
        import importlib
        mod = importlib.import_module("services.multibagger_engine")
        assert mod is not None
        print("PASS: multibagger_engine imports work")

    def test_portfolio_engine_imports(self):
        """Test portfolio_engine.py imports without errors."""
        import importlib
        mod = importlib.import_module("services.portfolio_engine")
        assert mod is not None
        print("PASS: portfolio_engine imports work")


class TestRouteModuleImports:
    """Test that all route modules import correctly."""

    def test_fno_routes_accessible(self):
        """Test fno routes are accessible."""
        response = requests.get(f"{BASE_URL}/api/fno/scripts/search?q=NIFTY", timeout=10)
        assert response.status_code == 200, f"FNO routes not accessible: {response.status_code}"
        print("PASS: FNO routes accessible")

    def test_portfolio_routes_accessible(self):
        """Test portfolio routes are accessible (auth required)."""
        # Get auth token
        auth_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if auth_resp.status_code != 200:
            pytest.skip("Auth failed")
        token = auth_resp.json().get("token")
        
        response = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "TCS", "avg_price": 3000, "quantity": 1}]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        assert response.status_code == 200, f"Portfolio routes not accessible: {response.status_code}"
        print("PASS: Portfolio routes accessible")

    def test_multibagger_routes_accessible(self):
        """Test multibagger routes are accessible."""
        response = safe_streaming_get(
            f"{BASE_URL}/api/multibagger/candidates",
            timeout=120,
            skip_msg="Multibagger candidates unavailable (Kite/timeout)",
        )
        assert response.status_code == 200, f"Multibagger routes not accessible: {response.status_code}"
        print("PASS: Multibagger routes accessible")

    def test_admin_routes_accessible(self):
        """Test admin routes are accessible (auth required)."""
        # Get auth token
        auth_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if auth_resp.status_code != 200:
            pytest.skip("Auth failed")
        token = auth_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert response.status_code == 200, f"Admin routes not accessible: {response.status_code}"
        print("PASS: Admin routes accessible")

    def test_market_data_routes_accessible(self):
        """Test market data routes are accessible (auth required)."""
        # Get auth token
        auth_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if auth_resp.status_code != 200:
            pytest.skip("Auth failed")
        token = auth_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"Market data routes not accessible: {response.status_code}"
        print("PASS: Market data routes accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
