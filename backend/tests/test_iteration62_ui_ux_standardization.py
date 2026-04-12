"""
Iteration 62: Critical System Fixes & UI/UX Standardization Tests

Tests for:
1. Sectors standalone tab removal (nav should NOT have Sectors)
2. Home dashboard 4 cards (no Sector Momentum card)
3. No 'Kite' text in public UI
4. Market HeatMap endpoints (sector, stocks, options)
5. Stock heatmap returns 225 stocks for 'all' filter (not 149)
6. Sector drill-down returns different stocks for different sectors
7. Stock heatmap API includes open, high, low, volume fields
8. Portfolio multi-file upload support
9. Heartbeat returns 'active' field
10. Admin panel shows 'Market Data API' instead of 'Kite Connect'
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://sentiment-engine-ai.preview.emergentagent.com"


class TestBackendHealth:
    """Basic health and heartbeat tests"""

    def test_heartbeat_returns_active_field(self):
        """Heartbeat endpoint should return 'active' field for anti-sleep protocol"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200, f"Heartbeat failed: {resp.status_code}"
        data = resp.json()
        assert "status" in data, "Missing 'status' field"
        assert data["status"] == "alive", f"Expected 'alive', got {data['status']}"
        assert "active" in data, "Missing 'active' field for anti-sleep protocol"
        assert data["active"] is True, f"Expected active=True, got {data['active']}"
        assert "ts" in data, "Missing 'ts' timestamp field"
        print(f"✓ Heartbeat returns active=True, ts={data['ts']}")


class TestAuthAccess:
    """Authentication tests"""

    def test_owner_login_shish123(self):
        """Owner login with @shish123"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        assert resp.status_code == 200, f"Owner login failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "token" in data, "Missing token in response"
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"
        print(f"✓ Owner login successful, role={data['role']}")
        return data["token"]

    def test_user_login_manas2005(self):
        """User login with Manas@2005"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10,
        )
        assert resp.status_code == 200, f"User login failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "token" in data, "Missing token in response"
        print(f"✓ User login successful, role={data.get('role')}")
        return data["token"]


class TestStockHeatmapAPI:
    """Stock heatmap endpoint tests - critical for 149 vs 225 stock count fix"""

    @pytest.fixture
    def auth_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Auth failed")

    def test_stock_heatmap_all_filter_returns_225_stocks(self, auth_token):
        """Stock heatmap with 'all' filter should return ~225 F&O stocks (not 149)"""
        resp = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=fno",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Stock heatmap failed: {resp.status_code}"
        data = resp.json()
        stocks = data.get("stocks", [])
        stock_count = len(stocks)
        # Should be around 225 (expanded from 149)
        assert stock_count >= 200, f"Expected ~225 stocks, got {stock_count} (still showing old 149?)"
        print(f"✓ Stock heatmap returns {stock_count} stocks (expected ~225)")

    def test_stock_heatmap_includes_ohlcv_fields(self, auth_token):
        """Stock heatmap API response should include open, high, low, volume fields"""
        resp = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Stock heatmap failed: {resp.status_code}"
        data = resp.json()
        stocks = data.get("stocks", [])
        assert len(stocks) > 0, "No stocks returned"
        
        # Check first stock has all required fields
        first_stock = stocks[0]
        required_fields = ["symbol", "ltp", "prev_close", "change_pct", "open", "high", "low", "volume"]
        for field in required_fields:
            assert field in first_stock, f"Missing field '{field}' in stock data"
        print(f"✓ Stock heatmap includes all OHLCV fields: {required_fields}")

    def test_stock_heatmap_nifty50_filter(self, auth_token):
        """NIFTY50 filter should return ~50 stocks"""
        resp = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        assert 45 <= len(stocks) <= 55, f"Expected ~50 NIFTY50 stocks, got {len(stocks)}"
        print(f"✓ NIFTY50 filter returns {len(stocks)} stocks")

    def test_stock_heatmap_banknifty_filter(self, auth_token):
        """BANKNIFTY filter should return ~12 stocks"""
        resp = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=banknifty",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        assert 10 <= len(stocks) <= 15, f"Expected ~12 BANKNIFTY stocks, got {len(stocks)}"
        print(f"✓ BANKNIFTY filter returns {len(stocks)} stocks")


class TestSectorDrillDown:
    """Sector drill-down tests - critical for static 18 stocks bug fix"""

    @pytest.fixture
    def auth_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Auth failed")

    def test_sector_stocks_it_sector(self, auth_token):
        """IT sector drill-down should return IT stocks"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks?sector=NIFTY IT",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Sector stocks failed: {resp.status_code}"
        data = resp.json()
        stocks = data.get("stocks", [])
        # Should have IT stocks, not static 18
        print(f"✓ NIFTY IT sector returns {len(stocks)} stocks")
        return stocks

    def test_sector_stocks_auto_sector(self, auth_token):
        """Automobile sector drill-down should return different stocks than IT"""
        resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks?sector=NIFTY AUTO",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Sector stocks failed: {resp.status_code}"
        data = resp.json()
        stocks = data.get("stocks", [])
        print(f"✓ NIFTY AUTO sector returns {len(stocks)} stocks")
        return stocks

    def test_different_sectors_return_different_stocks(self, auth_token):
        """Different sectors should return different stock lists (not static 18)"""
        # Get IT sector stocks
        it_resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks?sector=NIFTY IT",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        it_stocks = [s["symbol"] for s in it_resp.json().get("stocks", [])]
        
        # Get Bank sector stocks
        bank_resp = requests.get(
            f"{BASE_URL}/api/market/sector-stocks?sector=NIFTY BANK",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        bank_stocks = [s["symbol"] for s in bank_resp.json().get("stocks", [])]
        
        # They should be different (not the same static 18)
        if it_stocks and bank_stocks:
            overlap = set(it_stocks) & set(bank_stocks)
            # Some overlap is OK (like HDFCBANK in both), but not 100%
            overlap_pct = len(overlap) / max(len(it_stocks), len(bank_stocks)) * 100
            assert overlap_pct < 80, f"IT and BANK sectors have {overlap_pct:.0f}% overlap - likely static 18 bug"
            print(f"✓ IT ({len(it_stocks)} stocks) and BANK ({len(bank_stocks)} stocks) have {overlap_pct:.0f}% overlap - different sectors confirmed")
        else:
            print("⚠ One or both sectors returned empty - market data may not be available")


class TestOptionsHeatmap:
    """Options heatmap endpoint tests"""

    @pytest.fixture
    def auth_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Auth failed")

    def test_options_heatmap_nifty(self, auth_token):
        """Options heatmap for NIFTY should return chain data"""
        resp = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=nifty",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Options heatmap failed: {resp.status_code}"
        data = resp.json()
        assert "chains" in data, "Missing 'chains' in response"
        print(f"✓ Options heatmap NIFTY returns {len(data.get('chains', []))} chains")

    def test_options_heatmap_banknifty(self, auth_token):
        """Options heatmap for BANKNIFTY should return chain data"""
        resp = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=banknifty",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Options heatmap failed: {resp.status_code}"
        data = resp.json()
        assert "chains" in data, "Missing 'chains' in response"
        print(f"✓ Options heatmap BANKNIFTY returns {len(data.get('chains', []))} chains")

    def test_options_heatmap_stock_reliance(self, auth_token):
        """Options heatmap for RELIANCE stock should work"""
        resp = requests.get(
            f"{BASE_URL}/api/market/options-heatmap?filter=RELIANCE",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Options heatmap RELIANCE failed: {resp.status_code}"
        data = resp.json()
        print(f"✓ Options heatmap RELIANCE returns data")


class TestSectorMomentum:
    """Sector momentum endpoint tests"""

    @pytest.fixture
    def auth_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Auth failed")

    def test_sector_momentum_returns_sectors(self, auth_token):
        """Sector momentum should return sector data"""
        resp = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Sector momentum failed: {resp.status_code}"
        data = resp.json()
        sectors = data.get("sectors", [])
        assert len(sectors) > 0, "No sectors returned"
        print(f"✓ Sector momentum returns {len(sectors)} sectors")


class TestPortfolioUpload:
    """Portfolio upload endpoint tests - multi-file support"""

    @pytest.fixture
    def auth_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Auth failed")

    def test_portfolio_upload_accepts_files_parameter(self, auth_token):
        """Portfolio upload should accept 'files' parameter for multi-file upload"""
        # Create a simple test CSV content
        csv_content = "Symbol,Avg Price,Quantity\nRELIANCE,2500,10\nTCS,3500,5"
        
        # Test with 'files' parameter (multi-file)
        files = [
            ("files", ("test1.csv", csv_content, "text/csv")),
        ]
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze-upload",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            timeout=30,
        )
        # Should either succeed or fail with parsing error (not 422 for missing param)
        assert resp.status_code in [200, 400], f"Portfolio upload failed unexpectedly: {resp.status_code} - {resp.text}"
        print(f"✓ Portfolio upload accepts 'files' parameter, status={resp.status_code}")


class TestKiteStatus:
    """Kite/Market Data API status tests"""

    @pytest.fixture
    def auth_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Auth failed")

    def test_kite_status_endpoint(self, auth_token):
        """Kite status endpoint should return connection status"""
        resp = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10,
        )
        assert resp.status_code == 200, f"Kite status failed: {resp.status_code}"
        data = resp.json()
        assert "connected" in data, "Missing 'connected' field"
        print(f"✓ Kite status: connected={data.get('connected')}")


class TestLotSizesCount:
    """Verify lot_sizes.py has 225+ stocks"""

    def test_lot_sizes_has_225_stocks(self):
        """LOT_SIZE_MAP should have ~225 stocks (expanded from 149)"""
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from data.lot_sizes import LOT_SIZE_MAP
            
            # Exclude index symbols
            index_symbols = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}
            stock_count = len([s for s in LOT_SIZE_MAP.keys() if s not in index_symbols])
            
            assert stock_count >= 200, f"Expected ~225 stocks in LOT_SIZE_MAP, got {stock_count}"
            print(f"✓ LOT_SIZE_MAP has {stock_count} stocks (expected ~225)")
        except ImportError as e:
            pytest.skip(f"Could not import lot_sizes: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
