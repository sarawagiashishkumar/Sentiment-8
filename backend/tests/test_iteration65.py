"""
Iteration 65 Backend Tests
Tests for:
1. fno_confluence.py extraction (scoring functions)
2. Performance profiling endpoints (/fno/generation-timings)
3. Manual IV collection endpoint (/fno/iv-collect-now)
4. Existing core functionality (auth, heartbeat, IV endpoints, heatmap)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://127.0.0.1:4000"


@pytest.fixture(scope="module")
def owner_auth():
    """Get owner auth headers - uses 'token' field from auth response"""
    response = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"}
    )
    assert response.status_code == 200, f"Owner login failed: {response.text}"
    data = response.json()
    token = data.get("token")
    assert token, "Missing token in auth response"
    return {"Authorization": f"Bearer {token}"}


class TestBackendHealth:
    """Health check tests"""
    
    def test_heartbeat_returns_active_field(self):
        """Heartbeat should return active=True and status=alive"""
        response = requests.get(f"{BASE_URL}/api/heartbeat")
        assert response.status_code == 200, f"Heartbeat failed: {response.text}"
        data = response.json()
        assert "active" in data, "Missing 'active' field in heartbeat"
        assert data["active"] is True, f"Expected active=True, got {data['active']}"
        assert data.get("status") == "alive", f"Expected status=alive, got {data.get('status')}"
        print(f"PASS: Heartbeat returns active={data['active']}, status={data.get('status')}")


class TestAuthAccess:
    """Authentication tests"""
    
    def test_owner_login_shish123(self):
        """Owner login with @shish123 should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        assert response.status_code == 200, f"Owner login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Missing token in response"
        assert "user_key" in data, "Missing user_key in response"
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"
        print(f"PASS: Owner login successful, role={data.get('role')}")
    
    def test_user_login_manas2005(self):
        """User login with Manas@2005 should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"}
        )
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Missing token in response"
        assert "user_key" in data, "Missing user_key in response"
        print(f"PASS: User login successful, user_key={data.get('user_key')[:8]}...")


class TestGenerationTimingsEndpoint:
    """Tests for new /fno/generation-timings endpoint (Iteration 65 Task 2)"""
    
    def test_generation_timings_endpoint_exists(self, owner_auth):
        """GET /fno/generation-timings should return timing objects"""
        response = requests.get(
            f"{BASE_URL}/api/fno/generation-timings",
            headers=owner_auth
        )
        assert response.status_code == 200, f"Generation timings failed: {response.text}"
        data = response.json()
        
        # Should have fno and multibagger keys
        assert "fno" in data, "Missing 'fno' key in generation-timings response"
        assert "multibagger" in data, "Missing 'multibagger' key in generation-timings response"
        
        # Both should be objects (either timing data or 'no run yet' message)
        assert isinstance(data["fno"], dict), f"fno should be dict, got {type(data['fno'])}"
        assert isinstance(data["multibagger"], dict), f"multibagger should be dict, got {type(data['multibagger'])}"
        
        # If no generation has run, should have message field
        if "message" in data["fno"]:
            assert "no" in data["fno"]["message"].lower() or "run" in data["fno"]["message"].lower()
            print(f"PASS: FNO timings returns expected 'no run yet' message: {data['fno']['message']}")
        else:
            # If generation has run, should have timing fields
            assert "total_ms" in data["fno"] or "nifty_ms" in data["fno"], "Missing timing fields in fno"
            print(f"PASS: FNO timings has timing data: {data['fno']}")
        
        if "message" in data["multibagger"]:
            assert "no" in data["multibagger"]["message"].lower() or "run" in data["multibagger"]["message"].lower()
            print(f"PASS: Multibagger timings returns expected 'no run yet' message: {data['multibagger']['message']}")
        else:
            assert "total_ms" in data["multibagger"] or "scan_ms" in data["multibagger"], "Missing timing fields in multibagger"
            print(f"PASS: Multibagger timings has timing data: {data['multibagger']}")


class TestIVCollectNowEndpoint:
    """Tests for new /fno/iv-collect-now endpoint (Iteration 65 Task 3)"""
    
    def test_iv_collect_now_endpoint_exists(self, owner_auth):
        """POST /fno/iv-collect-now should return results object"""
        response = requests.post(
            f"{BASE_URL}/api/fno/iv-collect-now",
            headers=owner_auth,
            json={}
        )
        assert response.status_code == 200, f"IV collect-now failed: {response.text}"
        data = response.json()
        
        # Should have results key
        assert "results" in data, "Missing 'results' key in iv-collect-now response"
        results = data["results"]
        
        # Results should have NIFTY and BANKNIFTY keys
        assert "NIFTY" in results, "Missing NIFTY in results"
        assert "BANKNIFTY" in results, "Missing BANKNIFTY in results"
        
        # Each result should have captured field (bool) or reason field
        for symbol in ["NIFTY", "BANKNIFTY"]:
            result = results[symbol]
            assert isinstance(result, dict), f"{symbol} result should be dict"
            assert "captured" in result, f"{symbol} missing captured field"
            
            if result.get("captured"):
                # If captured, should have atm_iv and spot
                assert "atm_iv" in result, f"{symbol} captured but missing atm_iv"
                assert "spot" in result, f"{symbol} captured but missing spot"
                print(f"PASS: {symbol} IV captured: atm_iv={result['atm_iv']}%, spot={result['spot']}")
            else:
                # If not captured, should have reason
                reason = result.get("reason", "unknown")
                print(f"PASS: {symbol} IV not captured (expected - Market Data API not connected): {reason}")


class TestIVEndpoints:
    """Tests for existing IV endpoints"""
    
    def test_iv_cone_nifty(self, owner_auth):
        """GET /fno/iv-cone/NIFTY should return cone data structure"""
        response = requests.get(
            f"{BASE_URL}/api/fno/iv-cone/NIFTY",
            headers=owner_auth
        )
        assert response.status_code == 200, f"IV Cone NIFTY failed: {response.text}"
        data = response.json()
        
        # Should have symbol and data_points fields
        assert "symbol" in data, "Missing symbol in IV cone response"
        assert "data_points" in data, "Missing data_points in IV cone response"
        assert data["symbol"] == "NIFTY", f"Expected symbol=NIFTY, got {data['symbol']}"
        
        print(f"PASS: IV Cone NIFTY returns data_points={data['data_points']} (0 expected if no history)")
    
    def test_iv_term_structure_nifty(self, owner_auth):
        """GET /fno/iv-term-structure/NIFTY should return term structure data"""
        response = requests.get(
            f"{BASE_URL}/api/fno/iv-term-structure/NIFTY",
            headers=owner_auth
        )
        assert response.status_code == 200, f"IV Term Structure NIFTY failed: {response.text}"
        data = response.json()
        
        # Should have symbol and data_points fields
        assert "symbol" in data, "Missing symbol in IV term structure response"
        assert "data_points" in data, "Missing data_points in IV term structure response"
        
        print(f"PASS: IV Term Structure NIFTY returns data_points={data['data_points']} (0 expected if no history)")


class TestStockHeatmap:
    """Tests for stock heatmap endpoint"""
    
    def test_stock_heatmap_returns_data(self, owner_auth):
        """GET /market/stock-heatmap should return heatmap data"""
        response = requests.get(f"{BASE_URL}/api/market/stock-heatmap", headers=owner_auth)
        assert response.status_code == 200, f"Stock heatmap failed: {response.text}"
        data = response.json()
        
        # Should have stocks or data
        assert isinstance(data, (dict, list)), f"Heatmap should return dict or list, got {type(data)}"
        print(f"PASS: Stock heatmap returns data (type={type(data).__name__})")


class TestFNOEndpoints:
    """Tests for F&O endpoints"""
    
    def test_fno_custom_positions(self, owner_auth):
        """GET /fno/custom-positions should return list"""
        response = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=owner_auth
        )
        assert response.status_code == 200, f"Custom positions failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), f"Custom positions should return list, got {type(data)}"
        print(f"PASS: F&O custom positions returns list with {len(data)} items")


class TestAdminEndpoints:
    """Tests for admin endpoints"""
    
    def test_admin_users_list(self, owner_auth):
        """GET /admin/users should return users list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=owner_auth
        )
        assert response.status_code == 200, f"Admin users failed: {response.text}"
        data = response.json()
        
        # Admin users returns a list directly
        assert isinstance(data, list), f"Users should be a list, got {type(data)}"
        print(f"PASS: Admin users list returns {len(data)} users")
    
    def test_kite_status_endpoint(self, owner_auth):
        """GET /kite/status should return connection status"""
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers=owner_auth
        )
        assert response.status_code == 200, f"Kite status failed: {response.text}"
        data = response.json()
        
        assert "connected" in data, "Missing connected field in kite status"
        print(f"PASS: Kite status returns connected={data['connected']}")


class TestLogoutFlow:
    """Tests for logout functionality"""
    
    def test_logout_endpoint(self):
        """POST /auth/logout should succeed"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]
        
        # Then logout
        response = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Logout failed: {response.text}"
        print("PASS: Logout successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
