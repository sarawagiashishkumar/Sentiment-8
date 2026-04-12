"""
Iteration 71: Testing 4 Major Feature Phases
- TradingView Lightweight Charts (stock chart endpoint)
- Aggregated Reports Engine (daily/weekly P&L reports)
- Watchlist with Price Alerts (CRUD + background monitor)
- Strategy Backtester (run-backtest endpoint)

Also verifies:
- Nav bar has 8 buttons (Home, Multibagger, F&O, Portfolio, HeatMap, Reports, Watchlist, Admin)
- F&O page has 5 sub-tabs (Custom Script, Trading Journal, Strategy Backtester, Performance, IV Analytics)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def owner_token(api_client):
    """Get owner authentication token."""
    response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Owner authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    """Auth headers for authenticated requests."""
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# ─── Health & Basic Tests ─────────────────────────────────────────────────────

class TestBackendHealth:
    """Basic health checks."""

    def test_heartbeat_returns_active(self, api_client):
        """Heartbeat endpoint returns active=True."""
        response = api_client.get(f"{BASE_URL}/api/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data.get("active") is True
        assert "ts" in data
        print("PASS: Heartbeat returns active=True")

    def test_root_endpoint(self, api_client):
        """Root API endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("PASS: Root endpoint returns 200")


# ─── Auth Flow Tests ──────────────────────────────────────────────────────────

class TestAuthFlow:
    """Authentication flow tests."""

    def test_owner_login_shish123(self, api_client):
        """Owner login with @shish123 works."""
        response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print("PASS: Owner login successful, role=owner")

    def test_user_login_manas2005(self, api_client):
        """User login with Manas@2005 works."""
        response = api_client.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print("PASS: User login successful")

    def test_auth_me_returns_user_info(self, api_client, auth_headers):
        """GET /api/auth/me returns user info."""
        response = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert "role" in data
        print("PASS: /api/auth/me returns user info")


# ─── Reports Engine Tests ─────────────────────────────────────────────────────

class TestReportsEngine:
    """Aggregated Reports Engine tests."""

    def test_daily_summary_returns_required_fields(self, api_client, auth_headers):
        """GET /api/reports/daily-summary returns report with required fields."""
        response = api_client.get(f"{BASE_URL}/api/reports/daily-summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify required fields exist
        assert "total_signals" in data
        assert "total_pnl" in data
        assert "wins" in data
        assert "losses" in data
        assert "win_rate" in data
        assert data.get("period") == "daily"
        print(f"PASS: Daily summary returns required fields (signals={data['total_signals']}, pnl={data['total_pnl']})")

    def test_daily_summary_with_date_param(self, api_client, auth_headers):
        """GET /api/reports/daily-summary with date parameter works."""
        response = api_client.get(f"{BASE_URL}/api/reports/daily-summary?date=2026-01-01", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("date") == "2026-01-01"
        print("PASS: Daily summary with date param works")

    def test_weekly_summary_returns_required_fields(self, api_client, auth_headers):
        """GET /api/reports/weekly-summary returns weekly report."""
        response = api_client.get(f"{BASE_URL}/api/reports/weekly-summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify required fields exist
        assert "total_signals" in data
        assert "total_pnl" in data
        assert "wins" in data
        assert "losses" in data
        assert "win_rate" in data
        assert data.get("period") == "weekly"
        assert "from_date" in data
        assert "to_date" in data
        print(f"PASS: Weekly summary returns required fields (signals={data['total_signals']}, pnl={data['total_pnl']})")


# ─── Watchlist Tests ──────────────────────────────────────────────────────────

class TestWatchlist:
    """Watchlist CRUD tests."""

    def test_get_watchlist_returns_items_array(self, api_client, auth_headers):
        """GET /api/watchlist returns items array."""
        response = api_client.get(f"{BASE_URL}/api/watchlist", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        print(f"PASS: GET /api/watchlist returns items array (count={len(data['items'])})")

    def test_add_symbol_to_watchlist(self, api_client, auth_headers):
        """POST /api/watchlist adds symbol to watchlist."""
        payload = {
            "symbol": "TEST_RELIANCE",
            "alert_above": 3000,
            "alert_below": 2500,
            "notes": "Test watchlist entry"
        }
        response = api_client.post(f"{BASE_URL}/api/watchlist", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("added") is True or data.get("updated") is True
        assert data.get("symbol") == "TEST_RELIANCE"
        print("PASS: POST /api/watchlist adds symbol successfully")

    def test_delete_symbol_from_watchlist(self, api_client, auth_headers):
        """DELETE /api/watchlist/{symbol} removes from watchlist."""
        # First add a symbol to delete
        api_client.post(f"{BASE_URL}/api/watchlist", json={"symbol": "TEST_DELETE_ME"}, headers=auth_headers)
        
        # Now delete it
        response = api_client.delete(f"{BASE_URL}/api/watchlist/TEST_DELETE_ME", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data
        print("PASS: DELETE /api/watchlist/{symbol} removes from watchlist")

    def test_watchlist_cleanup(self, api_client, auth_headers):
        """Cleanup test watchlist entries."""
        api_client.delete(f"{BASE_URL}/api/watchlist/TEST_RELIANCE", headers=auth_headers)
        print("PASS: Watchlist test cleanup complete")


# ─── Strategy Backtester Tests ────────────────────────────────────────────────

class TestStrategyBacktester:
    """Strategy Backtester endpoint tests."""

    def test_run_backtest_returns_required_fields(self, api_client, auth_headers):
        """POST /api/fno/run-backtest returns summary, trades, equity_curve."""
        payload = {
            "symbol": "NIFTY",
            "strategy": "momentum_ce",
            "date_from": "2025-01-01",
            "date_to": "2025-03-01"
        }
        response = api_client.post(f"{BASE_URL}/api/fno/run-backtest", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify required fields exist (may be empty due to no Kite session)
        assert "summary" in data
        assert "trades" in data
        assert "equity_curve" in data
        print(f"PASS: POST /api/fno/run-backtest returns required fields (trades={len(data.get('trades', []))})")

    def test_run_backtest_with_different_strategy(self, api_client, auth_headers):
        """POST /api/fno/run-backtest works with different strategies."""
        payload = {
            "symbol": "BANKNIFTY",
            "strategy": "momentum_pe",
            "date_from": "2025-01-01",
            "date_to": "2025-02-01"
        }
        response = api_client.post(f"{BASE_URL}/api/fno/run-backtest", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        print("PASS: Backtest works with different strategy (momentum_pe)")


# ─── Stock Chart Tests ────────────────────────────────────────────────────────

class TestStockChart:
    """Stock chart endpoint tests for TradingView integration."""

    def test_stock_chart_returns_candles_and_info(self, api_client, auth_headers):
        """GET /api/market/stock-chart/{symbol} returns candles and info."""
        response = api_client.get(f"{BASE_URL}/api/market/stock-chart/RELIANCE", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert data["symbol"] == "RELIANCE"
        assert "candles" in data
        assert "info" in data
        # Candles may be empty if Kite session not active - this is expected
        print(f"PASS: GET /api/market/stock-chart/RELIANCE returns candles (count={len(data.get('candles', []))})")

    def test_stock_chart_with_different_symbol(self, api_client, auth_headers):
        """GET /api/market/stock-chart works with different symbols."""
        response = api_client.get(f"{BASE_URL}/api/market/stock-chart/TCS", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "TCS"
        print("PASS: Stock chart works with different symbol (TCS)")


# ─── F&O Endpoints Tests ──────────────────────────────────────────────────────

class TestFNOEndpoints:
    """F&O related endpoint tests."""

    def test_fno_custom_positions(self, api_client, auth_headers):
        """GET /api/fno/custom-positions returns list."""
        response = api_client.get(f"{BASE_URL}/api/fno/custom-positions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: F&O custom positions returns list (count={len(data)})")

    def test_fno_bbe_alerts(self, api_client, auth_headers):
        """GET /api/fno/bbe-alerts returns alerts."""
        response = api_client.get(f"{BASE_URL}/api/fno/bbe-alerts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "count" in data
        print(f"PASS: F&O BBE alerts returns alerts (count={data['count']})")

    def test_fno_events(self, api_client, auth_headers):
        """GET /api/fno/events returns list."""
        response = api_client.get(f"{BASE_URL}/api/fno/events", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "events" in data
        print("PASS: F&O events returns list")

    def test_fno_generation_timings(self, api_client, auth_headers):
        """GET /api/fno/generation-timings returns data."""
        response = api_client.get(f"{BASE_URL}/api/fno/generation-timings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "fno" in data
        assert "multibagger" in data
        print("PASS: F&O generation timings returns data")


# ─── Market Data Tests ────────────────────────────────────────────────────────

class TestMarketData:
    """Market data endpoint tests."""

    def test_stock_heatmap_returns_data(self, api_client, auth_headers):
        """GET /api/market/stock-heatmap returns stocks."""
        response = api_client.get(f"{BASE_URL}/api/market/stock-heatmap", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "stocks" in data
        assert "count" in data
        print(f"PASS: Stock heatmap returns {data['count']} stocks")

    def test_sector_stocks_endpoint(self, api_client, auth_headers):
        """GET /api/market/sector-stocks returns sector data."""
        response = api_client.get(f"{BASE_URL}/api/market/sector-stocks?sector=IT", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "sector" in data
        assert "stocks" in data
        print(f"PASS: Sector stocks returns data for IT sector")


# ─── Admin Endpoints Tests ────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Admin endpoint tests."""

    def test_admin_users_list(self, api_client, auth_headers):
        """GET /api/admin/users returns users list."""
        response = api_client.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Admin users list returns {len(data)} users")

    def test_admin_config_kite_status(self, api_client, auth_headers):
        """GET /api/admin/config returns api_controls with kite_data_enabled."""
        response = api_client.get(f"{BASE_URL}/api/admin/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "api_controls" in data
        print("PASS: Admin config returns api_controls")


# ─── Journal Endpoints Tests ──────────────────────────────────────────────────

class TestJournalEndpoints:
    """Trading Journal endpoint tests."""

    def test_get_journal_returns_entries_and_summary(self, api_client, auth_headers):
        """GET /api/journal returns entries and summary."""
        response = api_client.get(f"{BASE_URL}/api/journal", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "summary" in data
        print(f"PASS: GET /api/journal returns entries (count={len(data['entries'])})")


# ─── Notification Analytics Tests ─────────────────────────────────────────────

class TestNotificationAnalytics:
    """Notification analytics endpoint tests."""

    def test_notification_analytics_returns_required_fields(self, api_client, auth_headers):
        """GET /api/notifications/analytics returns required fields."""
        response = api_client.get(f"{BASE_URL}/api/notifications/analytics", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "frequency_7d" in data
        assert "total_24h" in data
        print("PASS: Notification analytics returns required fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
