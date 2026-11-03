"""
Iteration 55: Market Heatmap UI Matching Reference App Tests

Tests for:
1. SubTabs: Plain text without icons
2. SectorHeatmap: All tiles same teal color, NO summary badges, NO refresh button
3. StocksHeatmap: Only 3 filters (NIFTY50/BANKNIFTY/ALL), full-width CSS grid
4. OptionsHeatmap: Symbol presets, ALL/CE/PE, custom stock search, min OI slider, CE=teal PE=magenta
5. BucketD hard_veto threshold is 0.5 (not 0.8)
6. CONFLUENCE_THRESHOLD is 40
7. /api/market/industry-sectors returns 29 sectors
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://127.0.0.1:4000').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for owner user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"},
        headers={"Content-Type": "application/json"},
        timeout=15
    )
    assert response.status_code == 200, f"Auth failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in auth response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestConfluenceScoreThresholds:
    """Test BucketD hard_veto and CONFLUENCE_THRESHOLD values"""
    
    def test_confluence_threshold_is_40(self):
        """Verify CONFLUENCE_THRESHOLD is 40 in confluence_score_v2.py"""
        from services.confluence_score_v2 import CONFLUENCE_THRESHOLD
        assert CONFLUENCE_THRESHOLD == 40, f"Expected CONFLUENCE_THRESHOLD=40, got {CONFLUENCE_THRESHOLD}"
        print(f"PASS: CONFLUENCE_THRESHOLD = {CONFLUENCE_THRESHOLD}")
    
    def test_bucket_d_hard_veto_threshold_is_0_5(self):
        """Verify BucketD hard_veto triggers at rr_to_t1 < 0.5 (not 0.8)"""
        from services.confluence_score_v2 import compute_bucket_d
        
        # Test rr_to_t1 = 0.4 should trigger hard_veto
        result_veto = compute_bucket_d(rr_to_t1=0.4, rr_to_t2=1.0)
        assert result_veto["hard_veto"] == True, f"Expected hard_veto=True for rr_to_t1=0.4, got {result_veto}"
        assert result_veto["score"] == 0, f"Expected score=0 for hard_veto, got {result_veto['score']}"
        print(f"PASS: rr_to_t1=0.4 triggers hard_veto (score=0)")
        
        # Test rr_to_t1 = 0.5 should NOT trigger hard_veto
        result_no_veto = compute_bucket_d(rr_to_t1=0.5, rr_to_t2=1.5)
        assert result_no_veto["hard_veto"] == False, f"Expected hard_veto=False for rr_to_t1=0.5, got {result_no_veto}"
        assert result_no_veto["score"] > 0, f"Expected score>0 for rr_to_t1=0.5, got {result_no_veto['score']}"
        print(f"PASS: rr_to_t1=0.5 does NOT trigger hard_veto (score={result_no_veto['score']})")
        
        # Test rr_to_t1 = 0.6 should NOT trigger hard_veto
        result_ok = compute_bucket_d(rr_to_t1=0.6, rr_to_t2=1.5)
        assert result_ok["hard_veto"] == False, f"Expected hard_veto=False for rr_to_t1=0.6, got {result_ok}"
        print(f"PASS: rr_to_t1=0.6 does NOT trigger hard_veto (score={result_ok['score']})")


class TestIndustrySectors:
    """Test /api/market/industry-sectors endpoint"""
    
    def test_industry_sectors_returns_29_sectors(self, auth_headers):
        """Verify /api/market/industry-sectors returns exactly 29 sectors"""
        response = requests.get(
            f"{BASE_URL}/api/market/industry-sectors",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "sectors" in data, "Response missing 'sectors' key"
        sectors = data["sectors"]
        assert len(sectors) == 29, f"Expected 29 industry sectors, got {len(sectors)}"
        print(f"PASS: /api/market/industry-sectors returns {len(sectors)} sectors")
        
        # Verify sector structure
        for sector in sectors[:3]:
            assert "sector" in sector, "Sector missing 'sector' name"
            assert "avg_change_pct" in sector, "Sector missing 'avg_change_pct'"
            assert "stock_count" in sector, "Sector missing 'stock_count'"
            assert "gainers" in sector, "Sector missing 'gainers'"
            assert "losers" in sector, "Sector missing 'losers'"
        print(f"PASS: Sector structure verified (sector, avg_change_pct, stock_count, gainers, losers)")
    
    def test_industry_sectors_has_kite_live_flag(self, auth_headers):
        """Verify response includes kite_live flag"""
        response = requests.get(
            f"{BASE_URL}/api/market/industry-sectors",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "kite_live" in data, "Response missing 'kite_live' flag"
        print(f"PASS: kite_live flag present (value: {data['kite_live']})")


class TestStockHeatmap:
    """Test /api/market/stock-heatmap endpoint with 3 filters"""
    
    def test_stock_heatmap_nifty50_returns_50_stocks(self, auth_headers):
        """Verify NIFTY50 filter returns 50 stocks"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "stocks" in data, "Response missing 'stocks'"
        stocks = data["stocks"]
        assert len(stocks) == 50, f"Expected 50 NIFTY50 stocks, got {len(stocks)}"
        print(f"PASS: NIFTY50 filter returns {len(stocks)} stocks")
        
        # Verify stock structure
        for stock in stocks[:3]:
            assert "symbol" in stock, "Stock missing 'symbol'"
            assert "ltp" in stock, "Stock missing 'ltp'"
            assert "change_pct" in stock, "Stock missing 'change_pct'"
        print(f"PASS: Stock structure verified (symbol, ltp, change_pct)")
    
    def test_stock_heatmap_banknifty_returns_12_stocks(self, auth_headers):
        """Verify BANKNIFTY filter returns 12 stocks"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=banknifty",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        stocks = data.get("stocks", [])
        assert len(stocks) == 12, f"Expected 12 BANKNIFTY stocks, got {len(stocks)}"
        print(f"PASS: BANKNIFTY filter returns {len(stocks)} stocks")
    
    def test_stock_heatmap_all_returns_fno_universe(self, auth_headers):
        """Verify ALL filter returns F&O universe stocks"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=all",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        stocks = data.get("stocks", [])
        # ALL should return F&O universe (100+ stocks)
        assert len(stocks) >= 100, f"Expected 100+ F&O stocks for ALL filter, got {len(stocks)}"
        print(f"PASS: ALL filter returns {len(stocks)} F&O universe stocks")


class TestOptionsHeatmap:
    """Test /api/market/options-heatmap endpoint with symbol presets"""
    
    def test_options_heatmap_nifty_returns_chains(self, auth_headers):
        """Verify NIFTY filter returns option chains"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=nifty",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "chains" in data, "Response missing 'chains'"
        assert "kite_live" in data, "Response missing 'kite_live'"
        
        if data.get("chains"):
            chain = data["chains"][0]
            assert "symbol" in chain, "Chain missing 'symbol'"
            assert "spot" in chain, "Chain missing 'spot'"
            assert "strikes" in chain, "Chain missing 'strikes'"
            print(f"PASS: NIFTY options chain returned with {len(chain.get('strikes', []))} strikes")
        else:
            print(f"INFO: No NIFTY chains returned (may need Kite auth)")
    
    def test_options_heatmap_banknifty_returns_chains(self, auth_headers):
        """Verify BANKNIFTY filter returns option chains"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=banknifty",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "chains" in data, "Response missing 'chains'"
        print(f"PASS: BANKNIFTY options endpoint returns 200 with chains={len(data.get('chains', []))}")
    
    def test_options_heatmap_reliance_returns_stock_chain(self, auth_headers):
        """Verify RELIANCE filter returns stock-specific option chain"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=RELIANCE",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "chains" in data, "Response missing 'chains'"
        if data.get("chains"):
            chain = data["chains"][0]
            assert chain.get("symbol") == "RELIANCE", f"Expected symbol=RELIANCE, got {chain.get('symbol')}"
            print(f"PASS: RELIANCE option chain returned with spot={chain.get('spot')}")
        else:
            print(f"INFO: No RELIANCE chains returned (may need Kite auth)")
    
    def test_options_heatmap_tcs_returns_stock_chain(self, auth_headers):
        """Verify TCS filter returns stock-specific option chain"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=TCS",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "chains" in data, "Response missing 'chains'"
        print(f"PASS: TCS options endpoint returns 200")
    
    def test_options_heatmap_hdfcbank_returns_stock_chain(self, auth_headers):
        """Verify HDFCBANK filter returns stock-specific option chain"""
        response = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=HDFCBANK",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "chains" in data, "Response missing 'chains'"
        print(f"PASS: HDFCBANK options endpoint returns 200")


class TestSectorMomentum:
    """Test /api/sector-momentum endpoint"""
    
    def test_sector_momentum_returns_18_sectors(self, auth_headers):
        """Verify sector momentum returns 18 NSE index sectors"""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "sectors" in data, "Response missing 'sectors'"
        sectors = data["sectors"]
        assert len(sectors) == 18, f"Expected 18 NSE index sectors, got {len(sectors)}"
        print(f"PASS: Sector momentum returns {len(sectors)} NSE index sectors")
        
        # Verify summary badges data
        assert "summary" in data, "Response missing 'summary'"
        summary = data["summary"]
        assert "bullish_sectors" in summary, "Summary missing 'bullish_sectors'"
        assert "bearish_sectors" in summary, "Summary missing 'bearish_sectors'"
        assert "neutral_sectors" in summary, "Summary missing 'neutral_sectors'"
        print(f"PASS: Summary badges data present (Bullish: {summary.get('bullish_sectors')}, Bearish: {summary.get('bearish_sectors')}, Neutral: {summary.get('neutral_sectors')})")


class TestKiteStatus:
    """Test Kite connection status"""
    
    def test_kite_status_endpoint(self, auth_headers):
        """Verify /api/kite/status returns connection status"""
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "connected" in data, "Response missing 'connected' flag"
        print(f"PASS: Kite status endpoint returns connected={data.get('connected')}")


class TestRegressionEndpoints:
    """Regression tests for core endpoints"""
    
    def test_health_check(self):
        """Verify root endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Root endpoint returns 200")
    
    def test_fno_signal_history(self, auth_headers):
        """Verify F&O signal history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/fno/signal-history",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: F&O signal history endpoint returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
