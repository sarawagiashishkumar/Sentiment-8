"""
Iteration 89 Backend Tests
Tests for:
1. News & Sentiment endpoints (forecast, market-summary, symbol)
2. Custom API CRUD endpoints
3. Payment config status with razorpay_enabled, offline_enabled, has_qr_image
4. Regression tests for auth and admin
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token for @shish123"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    return resp.json().get("token")

@pytest.fixture(scope="module")
def user_token():
    """Get user auth token for Manas@2005"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    return resp.json().get("token")

@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


# ── Auth Tests ────────────────────────────────────────────────────────────────

class TestAuth:
    """Authentication endpoint tests"""
    
    def test_owner_login(self):
        """Test owner @shish123 login"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        # User data is returned directly, not nested under "user"
        assert "role" in data
        assert data["role"] == "owner"
        print(f"PASS: Owner login - role={data['role']}")
    
    def test_user_login(self):
        """Test user Manas@2005 login"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "role" in data
        print(f"PASS: User login - role={data['role']}")


# ── News & Sentiment Tests ────────────────────────────────────────────────────

class TestNewsSentiment:
    """News & Sentiment engine endpoint tests"""
    
    def test_news_forecast_endpoint(self, owner_headers):
        """GET /api/news/forecast returns session, index_forecasts, top_stock_sentiments"""
        resp = requests.get(f"{BASE_URL}/api/news/forecast", headers=owner_headers)
        assert resp.status_code == 200, f"Forecast failed: {resp.text}"
        data = resp.json()
        
        # Validate required fields
        assert "session" in data, "Missing 'session' field"
        assert data["session"] in ["pre_market", "post_market", "intraday"], f"Invalid session: {data['session']}"
        
        assert "index_forecasts" in data, "Missing 'index_forecasts' field"
        assert "NIFTY" in data["index_forecasts"], "Missing NIFTY forecast"
        assert "BANKNIFTY" in data["index_forecasts"], "Missing BANKNIFTY forecast"
        
        # Validate NIFTY forecast structure
        nifty = data["index_forecasts"]["NIFTY"]
        assert "bias" in nifty, "Missing bias in NIFTY forecast"
        assert nifty["bias"] in ["BULLISH", "BEARISH", "NEUTRAL"], f"Invalid bias: {nifty['bias']}"
        assert "sentiment_score" in nifty
        
        # Validate BANKNIFTY forecast structure
        banknifty = data["index_forecasts"]["BANKNIFTY"]
        assert "bias" in banknifty
        assert banknifty["bias"] in ["BULLISH", "BEARISH", "NEUTRAL"]
        
        assert "top_stock_sentiments" in data, "Missing 'top_stock_sentiments' field"
        assert isinstance(data["top_stock_sentiments"], list)
        
        print(f"PASS: News forecast - session={data['session']}, NIFTY bias={nifty['bias']}, BANKNIFTY bias={banknifty['bias']}, stocks={len(data['top_stock_sentiments'])}")
    
    def test_news_market_summary_endpoint(self, owner_headers):
        """GET /api/news/market-summary returns sentiment counts"""
        resp = requests.get(f"{BASE_URL}/api/news/market-summary", headers=owner_headers)
        assert resp.status_code == 200, f"Market summary failed: {resp.text}"
        data = resp.json()
        
        # Should have sentiment counts
        assert isinstance(data, dict)
        print(f"PASS: Market summary - data={data}")
    
    def test_news_symbol_endpoint(self, owner_headers):
        """GET /api/news/symbol/NIFTY returns headlines and sentiment"""
        resp = requests.get(f"{BASE_URL}/api/news/symbol/NIFTY", headers=owner_headers)
        assert resp.status_code == 200, f"Symbol news failed: {resp.text}"
        data = resp.json()
        
        assert "symbol" in data
        assert data["symbol"] == "NIFTY"
        assert "headlines" in data
        assert isinstance(data["headlines"], list)
        assert "sentiment" in data
        
        print(f"PASS: Symbol news - symbol={data['symbol']}, headlines={len(data['headlines'])}")
    
    def test_news_symbol_reliance(self, owner_headers):
        """GET /api/news/symbol/RELIANCE returns headlines and sentiment"""
        resp = requests.get(f"{BASE_URL}/api/news/symbol/RELIANCE", headers=owner_headers)
        assert resp.status_code == 200, f"RELIANCE news failed: {resp.text}"
        data = resp.json()
        
        assert data["symbol"] == "RELIANCE"
        assert "headlines" in data
        assert "sentiment" in data
        print(f"PASS: RELIANCE news - headlines={len(data['headlines'])}")


# ── Custom API CRUD Tests ─────────────────────────────────────────────────────

class TestCustomApiCRUD:
    """Custom API endpoints CRUD tests"""
    
    def test_list_custom_apis(self, owner_headers):
        """GET /api/admin/custom-apis lists custom APIs"""
        resp = requests.get(f"{BASE_URL}/api/admin/custom-apis", headers=owner_headers)
        assert resp.status_code == 200, f"List custom APIs failed: {resp.text}"
        data = resp.json()
        
        assert "apis" in data
        assert isinstance(data["apis"], list)
        assert "count" in data
        print(f"PASS: List custom APIs - count={data['count']}")
    
    def test_create_custom_api(self, owner_headers):
        """POST /api/admin/custom-apis creates a custom API endpoint"""
        payload = {
            "name": "TEST_API_89",
            "url": "https://httpbin.org/get",
            "method": "GET",
            "description": "Test API for iteration 89",
            "enabled": True
        }
        resp = requests.post(f"{BASE_URL}/api/admin/custom-apis", json=payload, headers=owner_headers)
        assert resp.status_code == 200, f"Create custom API failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") == True
        assert data.get("name") == "TEST_API_89"
        print(f"PASS: Create custom API - name={data['name']}")
    
    def test_verify_custom_api_created(self, owner_headers):
        """Verify the custom API was persisted"""
        resp = requests.get(f"{BASE_URL}/api/admin/custom-apis", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        api_names = [api["name"] for api in data["apis"]]
        assert "TEST_API_89" in api_names, f"TEST_API_89 not found in {api_names}"
        print(f"PASS: Custom API persisted - found TEST_API_89")
    
    def test_test_custom_api(self, owner_headers):
        """POST /api/admin/custom-apis/{name}/test returns status ok/error"""
        resp = requests.post(f"{BASE_URL}/api/admin/custom-apis/TEST_API_89/test", json={}, headers=owner_headers)
        assert resp.status_code == 200, f"Test custom API failed: {resp.text}"
        data = resp.json()
        
        assert "status" in data
        assert data["status"] in ["ok", "error"]
        print(f"PASS: Test custom API - status={data['status']}")
    
    def test_delete_custom_api(self, owner_headers):
        """DELETE /api/admin/custom-apis/{name} removes the API"""
        resp = requests.delete(f"{BASE_URL}/api/admin/custom-apis/TEST_API_89", headers=owner_headers)
        assert resp.status_code == 200, f"Delete custom API failed: {resp.text}"
        data = resp.json()
        
        assert data.get("deleted") == True
        assert data.get("name") == "TEST_API_89"
        print(f"PASS: Delete custom API - name={data['name']}")
    
    def test_verify_custom_api_deleted(self, owner_headers):
        """Verify the custom API was removed"""
        resp = requests.get(f"{BASE_URL}/api/admin/custom-apis", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        api_names = [api["name"] for api in data["apis"]]
        assert "TEST_API_89" not in api_names, f"TEST_API_89 should be deleted but found in {api_names}"
        print(f"PASS: Custom API deleted - TEST_API_89 not in list")


# ── Payment Config Tests ──────────────────────────────────────────────────────

class TestPaymentConfig:
    """Payment configuration endpoint tests"""
    
    def test_payment_config_status(self, owner_headers):
        """GET /api/admin/payments/config-status returns razorpay_enabled, offline_enabled, has_qr_image"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/config-status", headers=owner_headers)
        assert resp.status_code == 200, f"Payment config status failed: {resp.text}"
        data = resp.json()
        
        # Validate required fields
        assert "razorpay_configured" in data
        assert "razorpay_enabled" in data
        assert "offline_enabled" in data
        assert "has_qr_image" in data
        
        print(f"PASS: Payment config status - razorpay_enabled={data['razorpay_enabled']}, offline_enabled={data['offline_enabled']}, has_qr_image={data['has_qr_image']}")
    
    def test_payment_pending_list(self, owner_headers):
        """GET /api/admin/payments/pending returns pending payments list"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/pending", headers=owner_headers)
        assert resp.status_code == 200, f"Pending payments failed: {resp.text}"
        data = resp.json()
        
        assert "payments" in data
        assert isinstance(data["payments"], list)
        assert "count" in data
        print(f"PASS: Pending payments - count={data['count']}")
    
    def test_payment_history(self, owner_headers):
        """GET /api/admin/payments/history returns payment history"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/history?limit=10", headers=owner_headers)
        assert resp.status_code == 200, f"Payment history failed: {resp.text}"
        data = resp.json()
        
        assert "payments" in data
        assert isinstance(data["payments"], list)
        assert "total" in data
        print(f"PASS: Payment history - count={len(data['payments'])}, total={data['total']}")


# ── Admin Regression Tests ────────────────────────────────────────────────────

class TestAdminRegression:
    """Admin endpoint regression tests"""
    
    def test_admin_users_list(self, owner_headers):
        """GET /api/admin/users returns user list"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert resp.status_code == 200, f"Admin users failed: {resp.text}"
        data = resp.json()
        
        assert isinstance(data, list)
        assert len(data) >= 2, "Should have at least 2 users"
        print(f"PASS: Admin users - count={len(data)}")
    
    def test_admin_packages(self, owner_headers):
        """GET /api/admin/packages returns package tiers"""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200, f"Admin packages failed: {resp.text}"
        data = resp.json()
        
        assert "packages" in data
        packages = data["packages"]
        assert "free" in packages
        assert "basic" in packages
        assert "pro" in packages
        assert "unlimited" in packages
        print(f"PASS: Admin packages - tiers={list(packages.keys())}")
    
    def test_admin_config(self, owner_headers):
        """GET /api/admin/config returns admin configuration"""
        resp = requests.get(f"{BASE_URL}/api/admin/config", headers=owner_headers)
        assert resp.status_code == 200, f"Admin config failed: {resp.text}"
        data = resp.json()
        
        assert "api_controls" in data
        print(f"PASS: Admin config - api_controls present")


# ── Health & Heartbeat Regression ─────────────────────────────────────────────

class TestHealthRegression:
    """Health and heartbeat endpoint tests"""
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy status"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print(f"PASS: Health endpoint - status={data['status']}")
    
    def test_heartbeat_endpoint(self, owner_headers):
        """GET /api/heartbeat returns alive status"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "alive"
        print(f"PASS: Heartbeat endpoint - status={data['status']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
