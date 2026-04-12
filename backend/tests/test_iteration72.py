"""
Iteration 72 Backend Tests - v2
Tests for:
- Risk Dashboard (GET /api/risk/portfolio-summary)
- Advanced Backtester with 8 strategies (POST /api/fno/run-backtest)
- WebSocket endpoint existence (/api/ws/prices)
- Options Heatmap expiry dropdown (available_expiries in response)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://backend-refactor-p2.preview.emergentagent.com")

class TestBackendHealth:
    """Basic health checks"""
    
    def test_heartbeat_returns_active(self):
        """Heartbeat should return active=True"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active") is True
        print("PASS - heartbeat returns active=True")

class TestAuthFlow:
    """Authentication tests"""
    
    def test_owner_login_shish123(self):
        """Owner login with @shish123"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data, f"Expected 'token' in response, got keys: {list(data.keys())}"
        assert data.get("role") == "owner"
        print("PASS - owner login successful, role=owner")
        return data["token"]
    
    def test_user_login_manas2005(self):
        """User login with Manas@2005"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"}, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data, f"Expected 'token' in response, got keys: {list(data.keys())}"
        print("PASS - user login successful")

@pytest.fixture(scope="module")
def auth_token():
    """Get owner auth token for authenticated tests"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Authentication failed")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestRiskDashboard:
    """Risk Dashboard endpoint tests - NEW in iteration 72"""
    
    def test_risk_portfolio_summary_returns_required_fields(self, auth_headers):
        """GET /api/risk/portfolio-summary should return greeks, drawdown, correlation, concentration"""
        resp = requests.get(f"{BASE_URL}/api/risk/portfolio-summary", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Check required top-level fields
        assert "open_positions" in data
        assert "unique_symbols" in data
        assert "greeks" in data
        assert "drawdown" in data
        assert "correlation" in data
        assert "concentration" in data
        assert "margin" in data
        assert "equity_curve" in data
        
        # Check greeks structure
        greeks = data["greeks"]
        assert "net_delta" in greeks
        assert "net_theta" in greeks
        assert "net_vega" in greeks
        
        # Check drawdown structure
        drawdown = data["drawdown"]
        assert "max_drawdown_30d_pct" in drawdown
        assert "closed_trades_30d" in drawdown
        
        # Check correlation structure
        correlation = data["correlation"]
        assert "correlated_pairs" in correlation
        
        print(f"PASS - Risk portfolio summary returns all required fields: greeks={greeks}, drawdown={drawdown}")


class TestAdvancedBacktester:
    """Strategy Backtester tests - Enhanced in iteration 72 with 8 strategies"""
    
    def test_backtest_momentum_ce(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=momentum_ce"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "NIFTY",
            "strategy": "momentum_ce",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        assert "trades" in data
        assert "equity_curve" in data
        print(f"PASS - Backtest momentum_ce returns summary, trades, equity_curve")
    
    def test_backtest_iron_condor(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=iron_condor (multi-leg)"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "NIFTY",
            "strategy": "iron_condor",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        assert "trades" in data
        assert "equity_curve" in data
        # Iron condor should have 4 legs if trades exist
        if data["trades"]:
            assert data["trades"][0].get("legs", 1) == 4, f"Iron condor should have 4 legs, got {data['trades'][0].get('legs')}"
        print(f"PASS - Backtest iron_condor returns summary, trades with 4 legs")
    
    def test_backtest_bull_call_spread(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=bull_call_spread"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "RELIANCE",
            "strategy": "bull_call_spread",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        assert "trades" in data
        # Bull call spread should have 2 legs if trades exist
        if data["trades"]:
            assert data["trades"][0].get("legs", 1) == 2, f"Bull call spread should have 2 legs"
        print(f"PASS - Backtest bull_call_spread returns summary, trades with 2 legs")
    
    def test_backtest_bear_put_spread(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=bear_put_spread"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "NIFTY",
            "strategy": "bear_put_spread",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        print(f"PASS - Backtest bear_put_spread returns summary")
    
    def test_backtest_straddle(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=straddle"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "BANKNIFTY",
            "strategy": "straddle",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        # Straddle should have 2 legs if trades exist
        if data["trades"]:
            assert data["trades"][0].get("legs", 1) == 2
        print(f"PASS - Backtest straddle returns summary")
    
    def test_backtest_butterfly(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=butterfly"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "NIFTY",
            "strategy": "butterfly",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        # Butterfly should have 3 legs if trades exist
        if data["trades"]:
            assert data["trades"][0].get("legs", 1) == 3
        print(f"PASS - Backtest butterfly returns summary")
    
    def test_backtest_calendar_spread(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=calendar_spread"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "NIFTY",
            "strategy": "calendar_spread",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        print(f"PASS - Backtest calendar_spread returns summary")
    
    def test_backtest_momentum_pe(self, auth_headers):
        """POST /api/fno/run-backtest with strategy=momentum_pe"""
        resp = requests.post(f"{BASE_URL}/api/fno/run-backtest", json={
            "symbol": "NIFTY",
            "strategy": "momentum_pe",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }, headers=auth_headers, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "summary" in data
        print(f"PASS - Backtest momentum_pe returns summary")


class TestOptionsHeatmapExpiry:
    """Options Heatmap expiry dropdown tests - Fixed in iteration 72"""
    
    def test_options_heatmap_returns_available_expiries(self, auth_headers):
        """GET /api/market/options-heatmap should return available_expiries array"""
        resp = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=nifty", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Check chains exist
        assert "chains" in data
        
        # If chains exist, check for available_expiries
        if data["chains"]:
            chain = data["chains"][0]
            assert "available_expiries" in chain, "available_expiries array missing from chain"
            expiries = chain["available_expiries"]
            assert isinstance(expiries, list), "available_expiries should be a list"
            print(f"PASS - Options heatmap returns available_expiries: {len(expiries)} expiries found")
        else:
            print("PASS - Options heatmap returns chains (empty - Kite not connected)")
    
    def test_options_heatmap_with_expiry_param(self, auth_headers):
        """GET /api/market/options-heatmap with expiry param should filter by expiry"""
        # First get available expiries
        resp1 = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=nifty", headers=auth_headers, timeout=15)
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        if data1["chains"] and data1["chains"][0].get("available_expiries"):
            expiry = data1["chains"][0]["available_expiries"][0]
            # Now fetch with specific expiry
            resp2 = requests.get(f"{BASE_URL}/api/market/options-heatmap?filter=nifty&expiry={expiry}", headers=auth_headers, timeout=15)
            assert resp2.status_code == 200
            data2 = resp2.json()
            if data2["chains"]:
                assert data2["chains"][0].get("expiry") == expiry
            print(f"PASS - Options heatmap with expiry param works: {expiry}")
        else:
            print("PASS - Options heatmap expiry param test skipped (no expiries available)")


class TestWebSocketEndpoint:
    """WebSocket endpoint existence test - NEW in iteration 72"""
    
    def test_websocket_endpoint_defined_in_server(self):
        """WebSocket endpoint /api/ws/prices should be defined in server.py"""
        # WebSocket endpoints return 404 for HTTP GET requests (expected behavior)
        # We verify the endpoint exists by checking the server code
        # The actual WS connection test would require a WebSocket client
        import subprocess
        result = subprocess.run(
            ["grep", "-c", "@app.websocket.*ws/prices", "/app/backend/server.py"],
            capture_output=True, text=True
        )
        count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
        assert count >= 1, "WebSocket endpoint /api/ws/prices not found in server.py"
        print("PASS - WebSocket endpoint /api/ws/prices is defined in server.py")


class TestExistingFeatures:
    """Verify existing features still work"""
    
    def test_reports_daily_summary(self, auth_headers):
        """GET /api/reports/daily-summary should work"""
        resp = requests.get(f"{BASE_URL}/api/reports/daily-summary", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "total_signals" in data
        assert "period" in data
        print("PASS - Reports daily summary works")
    
    def test_watchlist_get(self, auth_headers):
        """GET /api/watchlist should return items array"""
        resp = requests.get(f"{BASE_URL}/api/watchlist", headers=auth_headers, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "items" in data
        print("PASS - Watchlist GET returns items array")
    
    def test_fno_custom_positions(self, auth_headers):
        """GET /api/fno/custom-positions should work"""
        resp = requests.get(f"{BASE_URL}/api/fno/custom-positions", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        assert isinstance(resp.json(), list)
        print("PASS - F&O custom positions returns list")
    
    def test_stock_heatmap(self, auth_headers):
        """GET /api/market/stock-heatmap should work"""
        resp = requests.get(f"{BASE_URL}/api/market/stock-heatmap?filter=fno", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "stocks" in data
        print("PASS - Stock heatmap returns stocks")
    
    def test_journal_get(self, auth_headers):
        """GET /api/journal should work"""
        resp = requests.get(f"{BASE_URL}/api/journal", headers=auth_headers, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "entries" in data
        print("PASS - Journal GET returns entries")
    
    def test_fno_generation_timings(self, auth_headers):
        """GET /api/fno/generation-timings should work"""
        resp = requests.get(f"{BASE_URL}/api/fno/generation-timings", headers=auth_headers, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "fno" in data or "multibagger" in data
        print("PASS - F&O generation timings works")


class TestNoKiteText:
    """Verify no Kite text in public UI responses"""
    
    def test_heartbeat_no_kite(self):
        """Heartbeat should not mention Kite"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200
        text = resp.text.lower()
        assert "kite" not in text, "Kite mentioned in heartbeat"
        print("PASS - Heartbeat has no Kite text")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
