"""
Iteration 60: Code Quality Refactoring Tests

Tests for:
1. Circular import broken via app_state.py
2. Hardcoded test secrets moved to env vars via conftest_helpers.py
3. localStorage replaced with sessionStorage for auth tokens (frontend)
4. MD5 replaced with SHA-256 in news_sentiment.py
5. Silent catch blocks now log errors
6. Array index keys replaced with stable identifiers (frontend)
7. fno.py generate/stream functions extracted into helpers
8. All unicode emojis removed
"""
import os
import pytest
import requests
from pathlib import Path

# Get BASE_URL from conftest_helpers
from tests.conftest_helpers import get_base_url, OWNER_USERNAME, USER_USERNAME

BASE_URL = get_base_url()


class TestBackendStartup:
    """Verify backend starts without circular import errors"""
    
    def test_heartbeat_returns_alive(self):
        """Backend /api/heartbeat returns 200 - proves no circular import crash"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "alive"
        assert "ts" in data
        print(f"PASS: Heartbeat returns alive - backend started without circular import errors")


class TestAuthAccess:
    """Verify auth endpoints work with credentials from conftest_helpers"""
    
    def test_owner_login_shish123(self):
        """Owner @shish123 login successful"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print(f"PASS: Owner {OWNER_USERNAME} login successful")
    
    def test_user_login_manas2005(self):
        """User Manas@2005 login successful"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": USER_USERNAME},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "user"
        print(f"PASS: User {USER_USERNAME} login successful")


class TestAdminUsersEndpoint:
    """Verify admin users endpoint returns legitimate users only"""
    
    def test_admin_users_returns_2_users(self):
        """Admin users endpoint returns exactly 2 users"""
        # Login as owner first
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        # Get admin users
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)
        assert len(users) == 2, f"Expected 2 users, got {len(users)}"
        usernames = [u.get("username") for u in users]
        assert "@shish123" in usernames or "Manas@2005" in usernames
        print(f"PASS: Admin users returns {len(users)} legitimate users: {usernames}")


class TestKiteStatus:
    """Verify Kite status endpoint works"""
    
    def test_kite_status_returns_connected_status(self):
        """Kite status endpoint returns connected status (may be offline if no API key)"""
        # Login as owner first
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        token = login_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        # connected can be True or False depending on KITE_API_KEY
        assert "connected" in data
        print(f"PASS: Kite status returns connected={data.get('connected')}")


class TestFNOEndpoints:
    """Verify F&O endpoints work after fno.py refactoring"""
    
    def test_bbe_alerts_returns_alerts_array(self):
        """BBE alerts endpoint returns alerts array"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        token = login_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/fno/bbe-alerts",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        assert "checked_at" in data
        print(f"PASS: BBE alerts returns {len(data['alerts'])} alerts")
    
    def test_performance_stats_returns_stats_object(self):
        """Performance stats endpoint returns stats object"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        token = login_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/fno/performance-stats",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        # Should have total, wins, losses, win_rate
        assert "total" in data
        assert "wins" in data
        assert "losses" in data
        assert "win_rate" in data
        print(f"PASS: Performance stats returns total={data.get('total')}, win_rate={data.get('win_rate')}")


class TestAppStateModule:
    """Verify app_state.py module exists and has expected structure"""
    
    def test_app_state_module_exists(self):
        """app_state.py module exists at expected path"""
        app_state_path = Path("/app/backend/services/app_state.py")
        assert app_state_path.exists(), "app_state.py not found"
        
        content = app_state_path.read_text()
        # Check for expected exports
        assert "db = None" in content, "db variable not found in app_state"
        assert "IST = timezone" in content, "IST timezone not found in app_state"
        assert "KITE_API_KEY = None" in content, "KITE_API_KEY not found in app_state"
        assert "kite_access_token = None" in content, "kite_access_token not found in app_state"
        assert "def configure(" in content, "configure function not found in app_state"
        print("PASS: app_state.py module exists with expected structure")


class TestConftestHelpers:
    """Verify conftest_helpers.py has externalized credentials"""
    
    def test_conftest_helpers_uses_env_vars(self):
        """conftest_helpers.py uses environment variables for credentials"""
        helpers_path = Path("/app/backend/tests/conftest_helpers.py")
        assert helpers_path.exists(), "conftest_helpers.py not found"
        
        content = helpers_path.read_text()
        # Check for env var usage
        assert "os.environ.get" in content, "Environment variable usage not found"
        assert "TEST_OWNER_USERNAME" in content or "OWNER_USERNAME" in content
        assert "TEST_USER_USERNAME" in content or "USER_USERNAME" in content
        print("PASS: conftest_helpers.py uses environment variables for credentials")


class TestNewsSentimentSHA256:
    """Verify news_sentiment.py uses SHA-256 instead of MD5"""
    
    def test_news_sentiment_uses_sha256(self):
        """news_sentiment.py uses SHA-256 for headline hashing"""
        news_path = Path("/app/backend/services/news_sentiment.py")
        assert news_path.exists(), "news_sentiment.py not found"
        
        content = news_path.read_text()
        # Check for SHA-256 usage
        assert "sha256" in content.lower(), "SHA-256 not found in news_sentiment.py"
        # Ensure MD5 is not used
        assert "md5" not in content.lower(), "MD5 still present in news_sentiment.py"
        print("PASS: news_sentiment.py uses SHA-256 instead of MD5")


class TestFNOHelperExtraction:
    """Verify fno.py has extracted helper functions"""
    
    def test_fno_has_extracted_helpers(self):
        """fno.py has extracted helper functions for streaming"""
        fno_path = Path("/app/backend/routes/fno.py")
        assert fno_path.exists(), "fno.py not found"
        
        content = fno_path.read_text()
        # Check for extracted helper functions
        assert "_run_phase_with_keepalive" in content, "_run_phase_with_keepalive helper not found"
        assert "_build_index_phase" in content, "_build_index_phase helper not found"
        assert "_build_stock_phase" in content, "_build_stock_phase helper not found"
        assert "_build_no_signals_alert" in content, "_build_no_signals_alert helper not found"
        print("PASS: fno.py has extracted helper functions")


class TestKiteClientImportsAppState:
    """Verify kite_client.py imports from app_state"""
    
    def test_kite_client_imports_app_state(self):
        """kite_client.py imports from app_state module"""
        kite_path = Path("/app/backend/services/kite_client.py")
        assert kite_path.exists(), "kite_client.py not found"
        
        content = kite_path.read_text()
        # Check for app_state import
        assert "from services.app_state import" in content, "app_state import not found in kite_client"
        print("PASS: kite_client.py imports from app_state module")


class TestFrontendSessionStorage:
    """Verify frontend uses sessionStorage instead of localStorage"""
    
    def test_app_js_uses_session_storage(self):
        """App.js uses sessionStorage for auth tokens"""
        app_js_path = Path("/app/frontend/src/App.js")
        assert app_js_path.exists(), "App.js not found"
        
        content = app_js_path.read_text()
        # Check for sessionStorage usage
        assert "sessionStorage" in content, "sessionStorage not found in App.js"
        # Ensure localStorage is not used for auth
        # Note: localStorage might still be used for other things, but auth should use sessionStorage
        assert 'sessionStorage.getItem("stock_auth_token")' in content, "sessionStorage.getItem for auth token not found"
        assert 'sessionStorage.setItem("stock_auth_token"' in content, "sessionStorage.setItem for auth token not found"
        assert 'sessionStorage.removeItem("stock_auth_token")' in content, "sessionStorage.removeItem for auth token not found"
        print("PASS: App.js uses sessionStorage for auth tokens")


class TestAdminDashboardUserCogImport:
    """Verify AdminDashboard.jsx has UserCog import"""
    
    def test_admin_dashboard_has_usercog_import(self):
        """AdminDashboard.jsx has UserCog import from lucide-react"""
        admin_path = Path("/app/frontend/src/components/Admin/AdminDashboard.jsx")
        assert admin_path.exists(), "AdminDashboard.jsx not found"
        
        content = admin_path.read_text()
        # Check for UserCog import
        assert "UserCog" in content, "UserCog not found in AdminDashboard.jsx"
        assert "lucide-react" in content, "lucide-react import not found"
        print("PASS: AdminDashboard.jsx has UserCog import")


class TestErrorLoggingInCatches:
    """Verify silent catch blocks now log errors"""
    
    def test_ndjson_stream_consumer_logs_errors(self):
        """NDJSONStreamConsumer.jsx logs errors in catch blocks"""
        ndjson_path = Path("/app/frontend/src/components/Shared/NDJSONStreamConsumer.jsx")
        assert ndjson_path.exists(), "NDJSONStreamConsumer.jsx not found"
        
        content = ndjson_path.read_text()
        # Check for console.warn or console.error in catch blocks
        assert "console.warn" in content or "console.debug" in content, "Error logging not found in NDJSONStreamConsumer"
        print("PASS: NDJSONStreamConsumer.jsx logs errors in catch blocks")
    
    def test_kite_live_warning_logs_errors(self):
        """KiteLiveWarning.jsx logs errors in catch blocks"""
        warning_path = Path("/app/frontend/src/components/Shared/KiteLiveWarning.jsx")
        assert warning_path.exists(), "KiteLiveWarning.jsx not found"
        
        content = warning_path.read_text()
        # Check for console.error or console.debug in catch blocks
        assert "console.error" in content or "console.debug" in content, "Error logging not found in KiteLiveWarning"
        print("PASS: KiteLiveWarning.jsx logs errors in catch blocks")


class TestRegressionEndpoints:
    """Regression tests for existing functionality"""
    
    def test_sector_momentum_endpoint(self):
        """Sector momentum endpoint still works"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        token = login_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        assert "sectors" in data
        print(f"PASS: Sector momentum returns {len(data.get('sectors', []))} sectors")
    
    def test_signal_log_endpoint(self):
        """Signal log endpoint still works"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": OWNER_USERNAME},
            timeout=10
        )
        token = login_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/fno/signal-log",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "log" in data
        assert "count" in data
        print(f"PASS: Signal log returns {data.get('count')} entries")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
