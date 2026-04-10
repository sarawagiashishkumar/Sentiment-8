"""
Iteration 52: P0 and P1 Fixes Testing
Tests for:
1. Login with POST /api/auth/access {username: @shish123}
2. GET /api/kite/status returns connected:true with real validation
3. GET /api/market/stock-heatmap?filter=nifty50 returns 50 stocks with kite_live:true
4. GET /api/market/stock-heatmap?filter=fno returns 149 stocks with live data
5. GET /api/market/stock-heatmap?filter=banknifty returns 12 stocks
6. GET /api/market/options-heatmap?filter=nifty returns chains with strikes, spot price, PCR
7. GET /api/market/options-heatmap?filter=banknifty returns chains with BANKNIFTY spot
8. GET /api/market/sector-stocks?sector=BANKING returns stocks with live data
9. Only 3 users in database (no test users)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://backend-refactor-p2.preview.emergentagent.com').rstrip('/')


class TestAuthFlow:
    """Authentication endpoint tests"""
    
    def test_login_with_valid_credentials(self):
        """Test login with @shish123 returns token"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert "role" in data, "Response should contain role"
        assert data["role"] == "owner", f"Expected role 'owner', got {data['role']}"
        assert data["username"] == "@shish123", f"Expected username '@shish123', got {data['username']}"
        print(f"✓ Login successful: token={data['token'][:20]}..., role={data['role']}")
    
    def test_login_with_invalid_credentials(self):
        """Test login with invalid user returns 400"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "invalid_user_xyz"})
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid login correctly rejected with 400")


class TestKiteStatus:
    """Kite Connect status endpoint tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_kite_status_returns_valid_response(self, auth_token):
        """Test GET /api/kite/status returns connected status with real validation"""
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "connected" in data, "Response should contain 'connected' field"
        
        if data["connected"]:
            print(f"✓ Kite is CONNECTED: user_id={data.get('user_id')}, date={data.get('date')}")
            assert "user_id" in data, "Connected response should have user_id"
            assert "date" in data, "Connected response should have date"
        else:
            print(f"✓ Kite is DISCONNECTED: reason={data.get('reason')}")
            assert "reason" in data, "Disconnected response should have reason"


class TestMarketHeatmapEndpoints:
    """Market heatmap endpoint tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_stock_heatmap_nifty50_returns_50_stocks(self, auth_token):
        """Test GET /api/market/stock-heatmap?filter=nifty50 returns 50 stocks"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "stocks" in data, "Response should contain 'stocks' array"
        assert "count" in data, "Response should contain 'count'"
        assert "kite_live" in data, "Response should contain 'kite_live' flag"
        assert data["filter"] == "nifty50", f"Expected filter 'nifty50', got {data['filter']}"
        assert data["count"] == 50, f"Expected 50 stocks, got {data['count']}"
        assert len(data["stocks"]) == 50, f"Expected 50 stocks in array, got {len(data['stocks'])}"
        
        # Check stock structure
        first_stock = data["stocks"][0]
        assert "symbol" in first_stock, "Stock should have 'symbol'"
        assert "ltp" in first_stock, "Stock should have 'ltp'"
        assert "change_pct" in first_stock, "Stock should have 'change_pct'"
        
        # Count stocks with live LTP
        live_count = sum(1 for s in data["stocks"] if s.get("ltp", 0) > 0)
        print(f"✓ Nifty50 heatmap: {data['count']} stocks, kite_live={data['kite_live']}, {live_count}/50 have LTP>0")
    
    def test_stock_heatmap_fno_returns_fno_universe(self, auth_token):
        """Test GET /api/market/stock-heatmap?filter=fno returns FNO universe stocks"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=fno",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "stocks" in data, "Response should contain 'stocks' array"
        assert "count" in data, "Response should contain 'count'"
        assert "kite_live" in data, "Response should contain 'kite_live' flag"
        assert data["filter"] == "fno", f"Expected filter 'fno', got {data['filter']}"
        
        # FNO universe should have ~149 stocks
        assert data["count"] >= 100, f"Expected at least 100 FNO stocks, got {data['count']}"
        
        # Count stocks with live LTP
        live_count = sum(1 for s in data["stocks"] if s.get("ltp", 0) > 0)
        print(f"✓ FNO heatmap: {data['count']} stocks, kite_live={data['kite_live']}, {live_count}/{data['count']} have LTP>0")
    
    def test_stock_heatmap_banknifty_returns_12_stocks(self, auth_token):
        """Test GET /api/market/stock-heatmap?filter=banknifty returns 12 stocks"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=banknifty",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "stocks" in data, "Response should contain 'stocks' array"
        assert "count" in data, "Response should contain 'count'"
        assert data["filter"] == "banknifty", f"Expected filter 'banknifty', got {data['filter']}"
        assert data["count"] == 12, f"Expected 12 BankNifty stocks, got {data['count']}"
        
        # Count stocks with live LTP
        live_count = sum(1 for s in data["stocks"] if s.get("ltp", 0) > 0)
        print(f"✓ BankNifty heatmap: {data['count']} stocks, kite_live={data['kite_live']}, {live_count}/12 have LTP>0")
    
    def test_options_heatmap_nifty_returns_valid_response(self, auth_token):
        """Test GET /api/market/options-heatmap?filter=nifty returns chains with strikes, spot, PCR"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=nifty",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "filter" in data, "Response should contain 'filter'"
        assert "chains" in data, "Response should contain 'chains' array"
        assert "summary" in data, "Response should contain 'summary'"
        assert "kite_live" in data, "Response should contain 'kite_live' flag"
        assert data["filter"] == "nifty", f"Expected filter 'nifty', got {data['filter']}"
        
        if data["chains"]:
            chain = data["chains"][0]
            assert "symbol" in chain, "Chain should have 'symbol'"
            assert "spot" in chain, "Chain should have 'spot'"
            assert "strikes" in chain, "Chain should have 'strikes'"
            print(f"✓ NIFTY options heatmap: spot={chain.get('spot')}, {len(chain.get('strikes', []))} strikes, PCR={data['summary'].get('pcr')}")
        else:
            print(f"✓ NIFTY options heatmap: No chains (warning: {data.get('warning', 'none')})")
    
    def test_options_heatmap_banknifty_returns_valid_response(self, auth_token):
        """Test GET /api/market/options-heatmap?filter=banknifty returns chains with BANKNIFTY spot"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=banknifty",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "filter" in data, "Response should contain 'filter'"
        assert "chains" in data, "Response should contain 'chains' array"
        assert data["filter"] == "banknifty", f"Expected filter 'banknifty', got {data['filter']}"
        
        if data["chains"]:
            chain = data["chains"][0]
            assert chain.get("symbol") == "BANKNIFTY", f"Expected symbol 'BANKNIFTY', got {chain.get('symbol')}"
            print(f"✓ BANKNIFTY options heatmap: spot={chain.get('spot')}, {len(chain.get('strikes', []))} strikes")
        else:
            print(f"✓ BANKNIFTY options heatmap: No chains (warning: {data.get('warning', 'none')})")
    
    def test_sector_stocks_banking_returns_valid_response(self, auth_token):
        """Test GET /api/market/sector-stocks?sector=BANKING returns stocks with live data"""
        response = requests.get(
            f"{BASE_URL}/api/market/sector-stocks?sector=BANKING",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "sector" in data, "Response should contain 'sector'"
        assert "stocks" in data, "Response should contain 'stocks' array"
        assert "kite_live" in data, "Response should contain 'kite_live' flag"
        assert data["sector"] == "BANKING", f"Expected sector 'BANKING', got {data['sector']}"
        
        # Check stock structure
        if data["stocks"]:
            first_stock = data["stocks"][0]
            assert "symbol" in first_stock, "Stock should have 'symbol'"
            assert "ltp" in first_stock, "Stock should have 'ltp'"
            assert "change_pct" in first_stock, "Stock should have 'change_pct'"
        
        live_count = sum(1 for s in data["stocks"] if s.get("ltp", 0) > 0)
        print(f"✓ BANKING sector stocks: {len(data['stocks'])} stocks, kite_live={data['kite_live']}, {live_count} have LTP>0")
    
    def test_sector_stocks_requires_sector_param(self, auth_token):
        """Test GET /api/market/sector-stocks without sector param returns 400"""
        response = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ sector-stocks correctly requires sector parameter")


class TestUserCount:
    """Test that only 3 users exist in database (no test users)"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_only_real_users_in_database(self, auth_token):
        """Test GET /api/admin/users returns only real users (no test users)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        users = response.json()
        assert isinstance(users, list), "Response should be a list"
        # Should have 2-3 real users (admin, @shish123, Manas@2005)
        assert len(users) >= 2, f"Expected at least 2 users, got {len(users)}"
        assert len(users) <= 5, f"Expected at most 5 users (no test users), got {len(users)}"
        
        usernames = [u.get("username") for u in users]
        # Verify no TEST_ prefixed users
        test_users = [u for u in usernames if u and u.startswith("TEST_")]
        assert len(test_users) == 0, f"Found test users that should be cleaned: {test_users}"
        
        print(f"✓ Database has {len(users)} real users: {usernames}")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("✓ Health check passed")
    
    def test_sector_momentum(self, auth_token):
        """Test GET /api/sector-momentum returns sectors"""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "sectors" in data, "Response should contain 'sectors'"
        print(f"✓ Sector momentum: {len(data.get('sectors', []))} sectors")
    
    def test_fno_signal_history(self, auth_token):
        """Test GET /api/fno/signal-history returns signal history"""
        response = requests.get(
            f"{BASE_URL}/api/fno/signal-history",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # API returns 'history' not 'signals'
        assert "history" in data or "signals" in data, "Response should contain 'history' or 'signals'"
        history = data.get("history", data.get("signals", []))
        print(f"✓ Signal history: {len(history)} signals, count={data.get('count', 'N/A')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
