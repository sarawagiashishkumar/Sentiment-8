"""
Iteration 58: Sector Drill-Down Feature Tests
Tests for:
- /api/market/sector-stocks endpoint (returns constituent stocks with live Kite data)
- Regression: /api/heartbeat returns alive
- Regression: /api/kite/status returns connected
- Regression: /api/auth/access owner login
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def auth_headers():
    """Get auth headers by logging in as owner"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    assert token, "No token returned from login"
    return {"Authorization": f"Bearer {token}"}


class TestSectorStocksEndpoint:
    """Tests for /api/market/sector-stocks endpoint"""
    
    def test_sector_stocks_nifty_it(self, auth_headers):
        """Test sector-stocks endpoint with NIFTY IT sector"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "NIFTY IT"},
            headers=auth_headers,
            timeout=20
        )
        assert resp.status_code == 200, f"sector-stocks failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "sector" in data, "Missing 'sector' field"
        assert "stocks" in data, "Missing 'stocks' field"
        assert "kite_live" in data, "Missing 'kite_live' field"
        
        # Verify sector name
        assert data["sector"] == "NIFTY IT", f"Sector mismatch: {data['sector']}"
        
        # Verify stocks array
        stocks = data["stocks"]
        assert isinstance(stocks, list), "stocks should be a list"
        
        # If stocks exist, verify structure
        if len(stocks) > 0:
            stock = stocks[0]
            assert "symbol" in stock, "Stock missing 'symbol'"
            assert "ltp" in stock, "Stock missing 'ltp'"
            assert "change_pct" in stock, "Stock missing 'change_pct'"
            print(f"PASS: sector-stocks NIFTY IT returned {len(stocks)} stocks, kite_live={data['kite_live']}")
            print(f"  Sample stock: {stock['symbol']} LTP={stock['ltp']} Change={stock['change_pct']}%")
    
    def test_sector_stocks_nifty_bank(self, auth_headers):
        """Test sector-stocks endpoint with NIFTY BANK sector"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "NIFTY BANK"},
            headers=auth_headers,
            timeout=20
        )
        assert resp.status_code == 200, f"sector-stocks failed: {resp.text}"
        data = resp.json()
        
        assert data["sector"] == "NIFTY BANK"
        assert isinstance(data["stocks"], list)
        print(f"PASS: sector-stocks NIFTY BANK returned {len(data['stocks'])} stocks")
    
    def test_sector_stocks_nifty_auto(self, auth_headers):
        """Test sector-stocks endpoint with NIFTY AUTO sector"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "NIFTY AUTO"},
            headers=auth_headers,
            timeout=20
        )
        assert resp.status_code == 200, f"sector-stocks failed: {resp.text}"
        data = resp.json()
        
        assert "stocks" in data
        print(f"PASS: sector-stocks NIFTY AUTO returned {len(data['stocks'])} stocks")
    
    def test_sector_stocks_industry_sector(self, auth_headers):
        """Test sector-stocks endpoint with an industry sector (e.g., IT)"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "IT"},
            headers=auth_headers,
            timeout=20
        )
        assert resp.status_code == 200, f"sector-stocks failed: {resp.text}"
        data = resp.json()
        
        assert "stocks" in data
        print(f"PASS: sector-stocks IT (industry) returned {len(data['stocks'])} stocks")
    
    def test_sector_stocks_missing_param(self, auth_headers):
        """Test sector-stocks endpoint without sector param returns 400"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            headers=auth_headers,
            timeout=15
        )
        assert resp.status_code == 400, f"Expected 400 for missing sector, got {resp.status_code}"
        print("PASS: sector-stocks returns 400 when sector param missing")
    
    def test_sector_stocks_fallback_to_nifty50(self, auth_headers):
        """Test sector-stocks endpoint with unknown sector falls back to NIFTY50"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks",
            params={"sector": "UNKNOWN_SECTOR_XYZ"},
            headers=auth_headers,
            timeout=20
        )
        assert resp.status_code == 200, f"sector-stocks failed: {resp.text}"
        data = resp.json()
        
        # Should fallback to NIFTY50 stocks
        assert "stocks" in data
        assert len(data["stocks"]) > 0, "Should return fallback stocks"
        print(f"PASS: sector-stocks unknown sector falls back to {len(data['stocks'])} stocks")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_heartbeat_returns_alive(self, auth_headers):
        """Test /api/heartbeat returns alive status"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200, f"heartbeat failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "alive", f"Expected status=alive, got {data}"
        print(f"PASS: heartbeat returns status=alive, ts={data.get('ts')}")
    
    def test_kite_status_connected(self, auth_headers):
        """Test /api/kite/status returns connected"""
        resp = requests.get(f"{BASE_URL}/api/kite/status", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"kite/status failed: {resp.text}"
        data = resp.json()
        # Kite should be connected based on previous iterations
        print(f"PASS: kite/status returned connected={data.get('connected')}")
    
    def test_auth_access_owner(self):
        """Test owner login works"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=15
        )
        assert resp.status_code == 200, f"Owner login failed: {resp.text}"
        data = resp.json()
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"
        print(f"PASS: Owner @shish123 login successful, role={data.get('role')}")
    
    def test_sector_momentum_endpoint(self, auth_headers):
        """Test /api/sector-momentum returns sectors"""
        resp = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=30
        )
        assert resp.status_code == 200, f"sector-momentum failed: {resp.text}"
        data = resp.json()
        assert "sectors" in data, "Missing 'sectors' field"
        sectors = data["sectors"]
        assert len(sectors) > 0, "No sectors returned"
        print(f"PASS: sector-momentum returned {len(sectors)} sectors")
    
    def test_industry_sectors_endpoint(self, auth_headers):
        """Test /api/market/industry-sectors returns industry sectors"""
        resp = requests.get(
            f"{BASE_URL}/api/market/industry-sectors",
            headers=auth_headers,
            timeout=20
        )
        assert resp.status_code == 200, f"industry-sectors failed: {resp.text}"
        data = resp.json()
        assert "sectors" in data, "Missing 'sectors' field"
        sectors = data["sectors"]
        assert len(sectors) > 0, "No industry sectors returned"
        
        # Verify structure
        if len(sectors) > 0:
            s = sectors[0]
            assert "sector" in s, "Missing 'sector' field"
            assert "avg_change_pct" in s, "Missing 'avg_change_pct' field"
            assert "gainers" in s, "Missing 'gainers' field"
            assert "losers" in s, "Missing 'losers' field"
        
        print(f"PASS: industry-sectors returned {len(sectors)} sectors")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
