"""
Iteration 53: Major Update Testing
- F&O signals breadth scanning fix (scanned=49 instead of 0)
- CONFLUENCE_THRESHOLD lowered from 78 to 40
- Kite session health monitor with 60s auto-check
- Warning popup for API errors (no 'Kite' name)
- Alarm sound on API failures
- Sector expansion from 8→18 indices
- Stocks heatmap: Treemap + List toggle, pagination
- Options heatmap: Chain + Treemap toggle
- Admin sub-tabs renamed
- F&O sub-tabs renamed
- Test users cleaned up
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:4000")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for @shish123"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestKiteStatus:
    """Test Kite session health monitoring"""
    
    def test_kite_status_returns_connected_true(self, auth_headers):
        """Kite is live today - should return connected:true"""
        resp = requests.get(f"{BASE_URL}/api/kite/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        # Kite is live today (April 10, 2026)
        assert data["connected"] is True, f"Expected connected=true, got {data}"
        assert "user_id" in data
        assert "date" in data


class TestSectorMomentumExpansion:
    """Test sector expansion from 8→18 indices"""
    
    def test_sector_momentum_returns_18_sectors(self, auth_headers):
        """GET /api/sector-momentum should return 18 sectors"""
        resp = requests.get(f"{BASE_URL}/api/sector-momentum", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        sectors = data.get("sectors", [])
        assert len(sectors) == 18, f"Expected 18 sectors, got {len(sectors)}"
        
        # Verify expected sectors are present
        sector_names = [s["sector"] for s in sectors]
        expected_sectors = [
            "Banking", "IT", "Auto", "Pharma", "FMCG", "Metal", "Realty", "Energy",
            "Infrastructure", "Financial Svcs", "Media", "PSE", "Private Bank",
            "PSU Bank", "Commodities", "Consumption", "Healthcare", "MNC"
        ]
        for expected in expected_sectors:
            assert expected in sector_names, f"Missing sector: {expected}"


class TestStockHeatmap:
    """Test stock heatmap endpoints with live Kite data"""
    
    def test_stock_heatmap_nifty50_returns_50_stocks(self, auth_headers):
        """GET /api/market/stock-heatmap?filter=nifty50 returns 50 stocks"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        assert len(stocks) == 50, f"Expected 50 stocks, got {len(stocks)}"
        assert data.get("kite_live") is True, "Expected kite_live=true"
        
        # Verify live LTP > 0 for most stocks
        live_count = sum(1 for s in stocks if s.get("ltp", 0) > 0)
        assert live_count >= 45, f"Expected at least 45 stocks with LTP > 0, got {live_count}"
    
    def test_stock_heatmap_fno_returns_149_stocks(self, auth_headers):
        """GET /api/market/stock-heatmap?filter=fno returns ~149 stocks"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=fno", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        assert len(stocks) >= 140, f"Expected ~149 stocks, got {len(stocks)}"
        assert data.get("kite_live") is True
        
        # Verify live LTP > 0 for most stocks
        live_count = sum(1 for s in stocks if s.get("ltp", 0) > 0)
        assert live_count >= 130, f"Expected at least 130 stocks with LTP > 0, got {live_count}"
    
    def test_stock_heatmap_banknifty_returns_12_stocks(self, auth_headers):
        """GET /api/market/stock-heatmap?filter=banknifty returns 12 stocks"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=banknifty", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        assert len(stocks) == 12, f"Expected 12 stocks, got {len(stocks)}"
        assert data.get("kite_live") is True


class TestOptionsHeatmap:
    """Test options heatmap endpoints"""
    
    def test_options_heatmap_nifty_returns_chains_with_pcr(self, auth_headers):
        """GET /api/market/options-heatmap?filter=nifty returns chains with PCR and strikes"""
        resp = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=nifty", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        chains = data.get("chains", [])
        assert len(chains) >= 1, "Expected at least 1 chain"
        assert data.get("kite_live") is True
        
        # Verify NIFTY chain structure
        nifty_chain = chains[0]
        assert nifty_chain.get("symbol") == "NIFTY"
        assert nifty_chain.get("spot", 0) > 0, "Expected spot price > 0"
        assert len(nifty_chain.get("strikes", [])) >= 10, "Expected at least 10 strikes"
        
        # Verify PCR in summary
        summary = data.get("summary", {})
        assert "pcr" in summary or summary.get("pcr") is not None
    
    def test_options_heatmap_banknifty_returns_chains(self, auth_headers):
        """GET /api/market/options-heatmap?filter=banknifty returns BANKNIFTY chains"""
        resp = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=banknifty", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        chains = data.get("chains", [])
        assert len(chains) >= 1, "Expected at least 1 chain"
        
        # Verify BANKNIFTY chain
        banknifty_chain = chains[0]
        assert banknifty_chain.get("symbol") == "BANKNIFTY"
        assert banknifty_chain.get("spot", 0) > 0, "Expected BANKNIFTY spot > 0"


class TestConfluenceThreshold:
    """Test CONFLUENCE_THRESHOLD change from 78 to 40"""
    
    def test_confluence_threshold_is_40(self):
        """Verify CONFLUENCE_THRESHOLD is set to 40"""
        from services.confluence_score_v2 import CONFLUENCE_THRESHOLD
        assert CONFLUENCE_THRESHOLD == 40, f"Expected CONFLUENCE_THRESHOLD=40, got {CONFLUENCE_THRESHOLD}"


class TestUserCleanup:
    """Test that only real users remain in database"""
    
    def test_only_real_users_in_database(self, auth_headers):
        """Database should have only 2-3 real users (no test users)"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert resp.status_code == 200
        users = resp.json()
        
        # Should have 2-3 users max
        assert len(users) <= 3, f"Expected max 3 users, got {len(users)}"
        
        # Verify expected users
        usernames = [u.get("username") for u in users]
        assert "@shish123" in usernames, "Missing owner @shish123"
        
        # No test users should exist
        for username in usernames:
            assert not username.startswith("TEST_"), f"Found test user: {username}"


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_health_check(self):
        """Health check endpoint"""
        resp = requests.get(f"{BASE_URL}/api/")
        assert resp.status_code == 200
    
    def test_fno_signal_history(self, auth_headers):
        """F&O signal history endpoint"""
        resp = requests.get(f"{BASE_URL}/api/fno/signal-history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Response has 'history' key, not 'signals'
        assert "history" in data or "signals" in data or isinstance(data, list)
    
    def test_fno_performance_stats(self, auth_headers):
        """F&O performance stats endpoint"""
        resp = requests.get(f"{BASE_URL}/api/fno/performance-stats", headers=auth_headers)
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
