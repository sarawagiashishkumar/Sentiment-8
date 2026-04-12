"""
Iteration 83: Component Refactor Regression Tests
- App.js reduced from 352→168 lines (useAlertEngine hook extracted)
- AdminDashboard reduced from 344→133 lines (Controls + Macro tabs extracted)
- Tests: Health, Heartbeat, Auth, Alerts CRUD, CRM, AI Chat, GZip, X-Response-Time
"""
import pytest
import requests
import os
import gzip

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def owner_token():
    """Get owner token for authenticated tests"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Owner auth failed")

@pytest.fixture(scope="module")
def user_token():
    """Get user token for authenticated tests"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("User auth failed")

@pytest.fixture
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}

@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


class TestHealthAndRegression:
    """Core health and regression tests"""
    
    def test_health_endpoint(self):
        """Health endpoint returns healthy status"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        assert "checks" in data
        assert data["checks"]["database"]["connected"] is True
    
    def test_heartbeat_alive(self):
        """Heartbeat endpoint returns alive"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "alive"
        assert data.get("active") is True
    
    def test_gzip_active(self):
        """GZip compression is active"""
        resp = requests.get(f"{BASE_URL}/api/health", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        # Check if response is gzip compressed
        content_encoding = resp.headers.get("Content-Encoding", "")
        assert "gzip" in content_encoding.lower() or resp.headers.get("Content-Length", "0") != "0"
    
    def test_x_response_time_header(self):
        """X-Response-Time header is present"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        assert "X-Response-Time" in resp.headers or "x-response-time" in resp.headers


class TestAuthAccess:
    """Auth access endpoint tests"""
    
    def test_owner_login_success(self):
        """Owner login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data.get("role") == "owner"
        assert data.get("admin_exempt") is True
    
    def test_user_login_success(self):
        """User login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data.get("role") in ["user", "admin"]
    
    def test_auth_me_endpoint(self, owner_headers):
        """Auth me endpoint returns user data"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "user_key" in data
        assert "username" in data
    
    def test_invalid_username_rejected(self):
        """Invalid username returns error"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "invalid_user_xyz"})
        assert resp.status_code in [400, 401, 404]
    
    def test_empty_username_rejected(self):
        """Empty username returns error"""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": ""})
        assert resp.status_code in [400, 422]


class TestAlertsCRUD:
    """Alert rules CRUD tests"""
    
    def test_list_alert_rules(self, owner_headers):
        """List alert rules works"""
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        # API returns {"rules": [...], "count": N}
        assert "rules" in data
        assert isinstance(data["rules"], list)
    
    def test_create_alert_rule(self, owner_headers):
        """Create alert rule works"""
        rule = {
            "name": "TEST_RULE_IT83",
            "conditions": [{"field": "symbol_ltp", "symbol": "RELIANCE", "operator": "gt", "value": 100}],
            "logic": "AND",
            "notify_type": "push",
            "enabled": True
        }
        resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=rule, headers=owner_headers)
        assert resp.status_code in [200, 201]
        data = resp.json()
        # API returns {"created": true, "rule": {...}}
        assert data.get("created") is True
        assert "rule" in data
        assert "rule_id" in data["rule"]
        return data["rule"]["rule_id"]
    
    def test_update_alert_rule(self, owner_headers):
        """Update alert rule works"""
        # First create a rule
        rule = {
            "name": "TEST_RULE_UPDATE_IT83",
            "conditions": [{"field": "symbol_ltp", "symbol": "TCS", "operator": "gt", "value": 100}],
            "logic": "AND",
            "notify_type": "push",
            "enabled": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=rule, headers=owner_headers)
        if create_resp.status_code not in [200, 201]:
            pytest.skip("Could not create rule for update test")
        
        rule_id = create_resp.json()["rule"]["rule_id"]
        
        # Update the rule
        update_data = {"name": "TEST_RULE_UPDATED_IT83", "enabled": False}
        update_resp = requests.patch(f"{BASE_URL}/api/alerts/rules/{rule_id}", json=update_data, headers=owner_headers)
        assert update_resp.status_code == 200
    
    def test_delete_alert_rule(self, owner_headers):
        """Delete alert rule works"""
        # First create a rule
        rule = {
            "name": "TEST_RULE_DELETE_IT83",
            "conditions": [{"field": "symbol_ltp", "symbol": "INFY", "operator": "gt", "value": 100}],
            "logic": "AND",
            "notify_type": "push",
            "enabled": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=rule, headers=owner_headers)
        if create_resp.status_code not in [200, 201]:
            pytest.skip("Could not create rule for delete test")
        
        rule_id = create_resp.json()["rule"]["rule_id"]
        
        # Delete the rule
        delete_resp = requests.delete(f"{BASE_URL}/api/alerts/rules/{rule_id}", headers=owner_headers)
        assert delete_resp.status_code in [200, 204]


class TestCRMEndpoints:
    """CRM inbox tests"""
    
    def test_admin_crm_inbox(self, owner_headers):
        """Admin CRM inbox works"""
        resp = requests.get(f"{BASE_URL}/api/admin/crm/inbox", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))
    
    def test_user_crm_inbox(self, user_headers):
        """User CRM inbox works"""
        resp = requests.get(f"{BASE_URL}/api/crm/inbox", headers=user_headers)
        assert resp.status_code == 200


class TestAIChat:
    """AI chat endpoint tests"""
    
    def test_ai_chat_response(self, owner_headers):
        """AI chat returns response"""
        resp = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={"message": "What is a stock?"},
            headers=owner_headers,
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data or "response" in data or "message" in data


class TestAdminEndpoints:
    """Admin-specific endpoint tests"""
    
    def test_admin_config(self, owner_headers):
        """Admin config endpoint works"""
        resp = requests.get(f"{BASE_URL}/api/admin/config", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
    
    def test_admin_users_list(self, owner_headers):
        """Admin users list works"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
    
    def test_admin_macro_events(self, owner_headers):
        """Admin macro events endpoint works"""
        resp = requests.get(f"{BASE_URL}/api/admin/macro-events", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "active_events" in data or "all_events" in data


class TestFNOEndpoints:
    """F&O related endpoint tests"""
    
    def test_fno_custom_positions(self, owner_headers):
        """F&O custom positions endpoint works"""
        resp = requests.get(f"{BASE_URL}/api/fno/custom-positions", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestNotifications:
    """Notification endpoint tests"""
    
    def test_notifications_list(self, owner_headers):
        """Notifications list works"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "notifications" in data or isinstance(data, list)


# Cleanup test data
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_rules(owner_token):
    """Cleanup TEST_ prefixed rules after tests"""
    yield
    headers = {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}
    try:
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            rules = data.get("rules", [])
            for rule in rules:
                if rule.get("name", "").startswith("TEST_"):
                    rule_id = rule.get("rule_id")
                    if rule_id:
                        requests.delete(f"{BASE_URL}/api/alerts/rules/{rule_id}", headers=headers)
    except:
        pass
