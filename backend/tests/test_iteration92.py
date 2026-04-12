"""
Iteration 92: Deep Code Review Bug Fix Verification Tests

Tests for:
1. Health check endpoint
2. Auth flow (login, /me)
3. Admin data stats (parallel queries)
4. Admin user search (sanitized output)
5. Admin packages (default_feature_costs)
6. News forecast endpoint
7. News market summary
8. Heartbeat endpoint
9. Strategy library endpoint
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sentiment-engine-ai.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def owner_token():
    """Get owner token for @shish123"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"},
        timeout=15
    )
    if resp.status_code != 200:
        pytest.skip(f"Owner login failed: {resp.status_code}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    """Auth headers with owner token"""
    return {"Authorization": f"Bearer {owner_token}"}


class TestHealthAndCore:
    """Test health check and core endpoints"""

    def test_health_endpoint(self):
        """1. Health check should return 'healthy' status"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        assert "checks" in data
        assert data["checks"]["database"]["status"] == "healthy"
        print(f"PASS: Health endpoint returns healthy status")

    def test_heartbeat_endpoint(self):
        """8. Heartbeat should return alive status"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "alive"
        assert data.get("active") is True
        print(f"PASS: Heartbeat returns alive status")


class TestAuthFlow:
    """Test authentication flow"""

    def test_owner_login(self):
        """2a. Login with @shish123 should return token"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data.get("role") == "owner"
        assert data.get("username") == "@shish123"
        print(f"PASS: Owner login returns token, role=owner")

    def test_auth_me_endpoint(self, auth_headers):
        """2b. /api/auth/me should return user info"""
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") == "owner"
        assert data.get("username") == "@shish123"
        assert "user_key" in data
        print(f"PASS: /api/auth/me returns user info with role=owner")


class TestAdminEndpoints:
    """Test admin endpoints with bug fixes"""

    def test_admin_data_stats_parallel(self, auth_headers):
        """3. Admin data stats should return all collection counts (parallel queries)"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/data/stats",
            headers=auth_headers,
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        stats = data["stats"]
        # Verify all expected collections are present
        expected_collections = [
            "crm_messages", "user_notifications", "livehelp_messages",
            "fraud_incidents", "payments", "login_sessions", "usage_tracking",
            "alert_rules", "trading_journal", "fno_signal_log"
        ]
        for col in expected_collections:
            assert col in stats, f"Missing collection: {col}"
            assert isinstance(stats[col], int), f"Collection {col} count should be int"
        print(f"PASS: Admin data stats returns all {len(expected_collections)} collection counts")

    def test_admin_user_search_sanitized(self, auth_headers):
        """4. Admin user search should return sanitized user views"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/users/search?q=shish",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "count" in data
        assert data["count"] >= 1
        
        # Verify sanitized output format from _map_user_view
        user = data["users"][0]
        assert "user_key" in user
        assert "username" in user
        assert "role" in user
        # Should NOT contain raw MongoDB fields
        assert "_id" not in user
        print(f"PASS: Admin user search returns {data['count']} sanitized user(s)")

    def test_admin_packages_with_feature_costs(self, auth_headers):
        """5. Admin packages should return packages with default_feature_costs"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/packages",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify packages structure
        assert "packages" in data
        packages = data["packages"]
        assert "free" in packages
        assert "basic" in packages
        assert "pro" in packages
        assert "unlimited" in packages
        
        # Verify default_feature_costs is present
        assert "default_feature_costs" in data
        costs = data["default_feature_costs"]
        assert "fno_generate" in costs
        assert "multibagger_generate" in costs
        assert "portfolio_analyze" in costs
        
        # Verify default_usage_limits is present
        assert "default_usage_limits" in data
        print(f"PASS: Admin packages returns {len(packages)} packages with default_feature_costs")


class TestNewsEndpoints:
    """Test news and sentiment endpoints"""

    def test_news_forecast(self, auth_headers):
        """6. News forecast should return session type and index forecasts"""
        resp = requests.get(
            f"{BASE_URL}/api/news/forecast",
            headers=auth_headers,
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify session type
        assert "session" in data
        assert data["session"] in ["pre_market", "market_hours", "post_market"]
        
        # Verify index forecasts
        assert "index_forecasts" in data
        forecasts = data["index_forecasts"]
        assert "NIFTY" in forecasts
        assert "BANKNIFTY" in forecasts
        
        # Verify NIFTY forecast structure
        nifty = forecasts["NIFTY"]
        assert "bias" in nifty
        assert "sentiment_score" in nifty
        assert "headline_count" in nifty
        print(f"PASS: News forecast returns session={data['session']} with NIFTY/BANKNIFTY forecasts")

    def test_news_market_summary(self, auth_headers):
        """7. News market summary should return sentiment data"""
        resp = requests.get(
            f"{BASE_URL}/api/news/market-summary",
            headers=auth_headers,
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify sentiment data structure
        assert "total_headlines" in data
        assert "avg_sentiment" in data
        assert "market_flag" in data
        assert "positive_pct" in data
        assert "negative_pct" in data
        
        # Verify market_flag is valid
        assert data["market_flag"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]
        print(f"PASS: News market summary returns market_flag={data['market_flag']}, {data['total_headlines']} headlines")


class TestStrategyLibrary:
    """Test strategy library endpoint"""

    def test_strategy_library(self, auth_headers):
        """9. Strategy library should return strategies list"""
        resp = requests.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=10
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "strategies" in data
        assert "total" in data
        assert data["total"] > 0
        
        # Verify strategy structure
        strategy = data["strategies"][0]
        assert "id" in strategy
        assert "name" in strategy
        assert "type" in strategy
        assert "entry_conditions" in strategy
        print(f"PASS: Strategy library returns {data['total']} strategies")


class TestCodeReviewFixes:
    """Verify specific code review bug fixes"""

    def test_session_cleanup_task_exists(self):
        """Verify session cleanup task is defined in server.py"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        # Read server.py and check for session cleanup task
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "_session_cleanup_task" in content, "Session cleanup task should be defined"
        assert "SESSION_STORE.pop" in content, "Session cleanup should remove stale sessions"
        print("PASS: Session cleanup task is defined in server.py")

    def test_help_room_cleanup_task_exists(self):
        """Verify help room cleanup task is defined in server.py"""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "_help_room_cleanup_task" in content, "Help room cleanup task should be defined"
        assert "_help_rooms.pop" in content, "Help room cleanup should remove stale rooms"
        print("PASS: Help room cleanup task is defined in server.py")

    def test_check_usage_limit_uses_db_packages(self):
        """Verify check_usage_limit uses DB packages via _get_packages()"""
        with open("/app/backend/routes/admin.py", "r") as f:
            content = f.read()
        
        # Find check_usage_limit function
        assert "async def check_usage_limit" in content
        # Verify it calls _get_packages()
        assert "await _get_packages()" in content, "check_usage_limit should use _get_packages()"
        print("PASS: check_usage_limit uses _get_packages() for DB packages")

    def test_search_users_uses_map_user_view(self):
        """Verify search_users sanitizes output with _map_user_view"""
        with open("/app/backend/routes/admin.py", "r") as f:
            content = f.read()
        
        # Find search_users function and verify it uses _map_user_view
        assert "async def search_users" in content
        assert "_srv._map_user_view" in content, "search_users should use _map_user_view"
        print("PASS: search_users uses _map_user_view for sanitized output")

    def test_data_stats_uses_parallel_queries(self):
        """Verify get_data_stats uses parallel queries with asyncio.gather"""
        with open("/app/backend/routes/admin.py", "r") as f:
            content = f.read()
        
        # Find get_data_stats function
        assert "async def get_data_stats" in content
        # Verify it uses asyncio.gather for parallel queries
        assert "_aio.gather" in content or "asyncio.gather" in content, "get_data_stats should use parallel queries"
        print("PASS: get_data_stats uses parallel queries with asyncio.gather")

    def test_session_logs_memory_cap(self):
        """Verify _session_logs has memory cap in livehelp.py"""
        with open("/app/backend/routes/livehelp.py", "r") as f:
            content = f.read()
        
        # Check for memory cap on _session_logs
        assert "_session_logs" in content
        # Should have some form of limit (maxlen or manual cap)
        assert "maxlen" in content or "[:100]" in content or "[-100:]" in content, \
            "_session_logs should have memory cap"
        print("PASS: _session_logs has memory cap in livehelp.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
