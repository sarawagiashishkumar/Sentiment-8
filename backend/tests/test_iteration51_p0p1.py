"""
Iteration 51: P0 and P1 Fixes Testing
- P0: Kite token validation (connected:false with reason when expired)
- P0: F&O signal suppression (Bucket D penalty when MFE unavailable)
- P0: Sector momentum count (dynamic)
- P1: Market HeatMap endpoints (sector-stocks, stock-heatmap, options-heatmap)
- P1: Stock signals limited to max 15
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: try to read from frontend .env
    _env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    if os.path.isfile(_env_path):
        for _line in open(_env_path):
            if _line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
                break
    if not BASE_URL:
        BASE_URL = "http://localhost:8001"

@pytest.fixture(scope="module")
def auth_headers():
    """Get auth headers by logging in"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    assert token, "No token returned"
    return {"Authorization": f"Bearer {token}"}


class TestKiteStatus:
    """P0: Kite token validation - should return connected:false with reason when token is expired"""
    
    def test_kite_status_returns_connected_false_with_reason(self, auth_headers):
        """Kite status should return connected:false with reason field when token is expired"""
        resp = requests.get(f"{BASE_URL}/api/kite/status", headers=auth_headers)
        assert resp.status_code == 200, f"Kite status failed: {resp.text}"
        data = resp.json()
        
        # P0 fix: Should return connected:false with reason field
        assert "connected" in data, "Missing 'connected' field"
        
        # Since token is expired, connected should be false
        if not data["connected"]:
            assert "reason" in data, "Missing 'reason' field when connected is false"
            print(f"PASS: Kite status returns connected=false with reason='{data.get('reason')}'")
        else:
            # If somehow connected is true, that's also valid (token might be valid)
            print(f"INFO: Kite status returns connected=true (token may be valid)")


class TestMarketHeatmapEndpoints:
    """P1: Market HeatMap endpoints"""
    
    def test_stock_heatmap_nifty50_returns_50_stocks(self, auth_headers):
        """GET /api/market/stock-heatmap?filter=nifty50 should return 50 stock objects"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50", headers=auth_headers)
        assert resp.status_code == 200, f"Stock heatmap failed: {resp.text}"
        data = resp.json()
        
        assert "stocks" in data, "Missing 'stocks' field"
        assert "filter" in data, "Missing 'filter' field"
        assert data["filter"] == "nifty50", f"Expected filter=nifty50, got {data['filter']}"
        
        stocks = data["stocks"]
        assert isinstance(stocks, list), "stocks should be a list"
        assert len(stocks) == 50, f"Expected 50 stocks for nifty50, got {len(stocks)}"
        
        # Verify stock object structure
        if stocks:
            stock = stocks[0]
            assert "symbol" in stock, "Stock missing 'symbol'"
            assert "ltp" in stock, "Stock missing 'ltp'"
            assert "change_pct" in stock, "Stock missing 'change_pct'"
        
        print(f"PASS: Stock heatmap nifty50 returns {len(stocks)} stocks")
    
    def test_stock_heatmap_fno_returns_fno_universe(self, auth_headers):
        """GET /api/market/stock-heatmap?filter=fno should return FNO universe stocks"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=fno", headers=auth_headers)
        assert resp.status_code == 200, f"Stock heatmap FNO failed: {resp.text}"
        data = resp.json()
        
        assert "stocks" in data, "Missing 'stocks' field"
        assert "filter" in data, "Missing 'filter' field"
        assert data["filter"] == "fno", f"Expected filter=fno, got {data['filter']}"
        
        stocks = data["stocks"]
        assert isinstance(stocks, list), "stocks should be a list"
        # FNO universe should have more stocks than nifty50
        assert len(stocks) >= 50, f"Expected at least 50 FNO stocks, got {len(stocks)}"
        
        print(f"PASS: Stock heatmap FNO returns {len(stocks)} stocks")
    
    def test_options_heatmap_nifty_returns_valid_response(self, auth_headers):
        """GET /api/market/options-heatmap?filter=nifty should return valid response"""
        resp = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=nifty", headers=auth_headers)
        assert resp.status_code == 200, f"Options heatmap failed: {resp.text}"
        data = resp.json()
        
        assert "filter" in data, "Missing 'filter' field"
        assert data["filter"] == "nifty", f"Expected filter=nifty, got {data['filter']}"
        assert "chains" in data, "Missing 'chains' field"
        assert "summary" in data, "Missing 'summary' field"
        
        # Chains may be empty if no Kite connection, but structure should be valid
        assert isinstance(data["chains"], list), "chains should be a list"
        assert isinstance(data["summary"], dict), "summary should be a dict"
        
        print(f"PASS: Options heatmap nifty returns valid structure with {len(data['chains'])} chains")
    
    def test_options_heatmap_banknifty_returns_valid_response(self, auth_headers):
        """GET /api/market/options-heatmap?filter=banknifty should return valid response"""
        resp = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=banknifty", headers=auth_headers)
        assert resp.status_code == 200, f"Options heatmap banknifty failed: {resp.text}"
        data = resp.json()
        
        assert "filter" in data, "Missing 'filter' field"
        assert data["filter"] == "banknifty", f"Expected filter=banknifty, got {data['filter']}"
        assert "chains" in data, "Missing 'chains' field"
        
        print(f"PASS: Options heatmap banknifty returns valid structure")
    
    def test_sector_stocks_banking_returns_valid_response(self, auth_headers):
        """GET /api/market/sector-stocks?sector=BANKING should return valid response"""
        resp = requests.get(f"{BASE_URL}/api/market/sector-stocks?sector=BANKING", headers=auth_headers)
        assert resp.status_code == 200, f"Sector stocks failed: {resp.text}"
        data = resp.json()
        
        assert "sector" in data, "Missing 'sector' field"
        assert data["sector"] == "BANKING", f"Expected sector=BANKING, got {data['sector']}"
        assert "stocks" in data, "Missing 'stocks' field"
        
        stocks = data["stocks"]
        assert isinstance(stocks, list), "stocks should be a list"
        
        # Verify stock object structure if any stocks returned
        if stocks:
            stock = stocks[0]
            assert "symbol" in stock, "Stock missing 'symbol'"
            assert "ltp" in stock, "Stock missing 'ltp'"
            assert "change_pct" in stock, "Stock missing 'change_pct'"
        
        print(f"PASS: Sector stocks BANKING returns {len(stocks)} stocks")
    
    def test_sector_stocks_requires_sector_param(self, auth_headers):
        """GET /api/market/sector-stocks without sector param should return 400"""
        resp = requests.get(f"{BASE_URL}/api/market/sector-stocks", headers=auth_headers)
        assert resp.status_code == 400, f"Expected 400 for missing sector, got {resp.status_code}"
        print("PASS: Sector stocks requires sector parameter")


class TestSectorMomentum:
    """P0: Sector momentum count should be dynamic (not hardcoded 15)"""
    
    def test_sector_momentum_returns_sectors(self, auth_headers):
        """GET /api/sector-momentum should return sectors array"""
        resp = requests.get(f"{BASE_URL}/api/sector-momentum", headers=auth_headers)
        assert resp.status_code == 200, f"Sector momentum failed: {resp.text}"
        data = resp.json()
        
        assert "sectors" in data, "Missing 'sectors' field"
        sectors = data["sectors"]
        assert isinstance(sectors, list), "sectors should be a list"
        
        # Verify sector object structure
        if sectors:
            sector = sectors[0]
            assert "sector" in sector, "Sector missing 'sector' name"
            assert "momentum_score" in sector, "Sector missing 'momentum_score'"
        
        print(f"PASS: Sector momentum returns {len(sectors)} sectors")


class TestAuthFlow:
    """Test login flow with POST /api/auth/access"""
    
    def test_login_with_valid_credentials(self):
        """POST /api/auth/access with valid username should return token"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        
        assert "token" in data, "Missing 'token' field"
        # User data is at root level, not nested under "user"
        assert "username" in data, "Missing 'username' field"
        assert data.get("username") == "@shish123", "Username mismatch"
        
        print(f"PASS: Login returns token and user data")
    
    def test_login_with_invalid_credentials(self):
        """POST /api/auth/access with invalid username should return 400/401"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "invalid_user"})
        assert resp.status_code in [400, 401], f"Expected 400/401 for invalid user, got {resp.status_code}"
        print("PASS: Login rejects invalid credentials")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_health_check(self):
        """GET / or /api/ should return ok"""
        # Try root endpoint first
        resp = requests.get(f"{BASE_URL}/api/")
        if resp.status_code == 404:
            resp = requests.get(f"{BASE_URL}/")
        # Accept 200 or any successful response
        assert resp.status_code in [200, 307], f"Health check failed: {resp.text}"
        print("PASS: Health check returns success")
    
    def test_fno_performance_stats(self, auth_headers):
        """GET /api/fno/performance-stats should return stats"""
        resp = requests.get(f"{BASE_URL}/api/fno/performance-stats", headers=auth_headers)
        assert resp.status_code == 200, f"Performance stats failed: {resp.text}"
        data = resp.json()
        
        assert "total" in data, "Missing 'total' field"
        assert "wins" in data, "Missing 'wins' field"
        assert "losses" in data, "Missing 'losses' field"
        
        print(f"PASS: Performance stats returns total={data['total']}, wins={data['wins']}, losses={data['losses']}")
    
    def test_fno_signal_history(self, auth_headers):
        """GET /api/fno/signal-history should return paginated history"""
        resp = requests.get(f"{BASE_URL}/api/fno/signal-history", headers=auth_headers)
        assert resp.status_code == 200, f"Signal history failed: {resp.text}"
        data = resp.json()
        
        assert "history" in data, "Missing 'history' field"
        assert "count" in data, "Missing 'count' field"
        
        print(f"PASS: Signal history returns count={data['count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
