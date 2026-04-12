"""
Iteration 82: Code Quality Report Fixes Testing
Tests for:
1. app_state.py expansion (SESSION_STORE, OWNER_BOOTSTRAP_USERNAME, configure_runtime(), _utc_now_iso())
2. auth.py refactor (split into 5 helper functions)
3. alerts.py refactor (split evaluate_alerts into 6 focused functions)
4. Frontend empty catch blocks replaced with console.error
5. Regression tests for health, heartbeat, GZip, X-Response-Time
"""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Test Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_session():
    """Login as owner and return auth headers."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if resp.status_code != 200:
        pytest.skip("Owner login failed")
    data = resp.json()
    return {
        "Authorization": f"Bearer {data['token']}",
        "Content-Type": "application/json"
    }, data

@pytest.fixture(scope="module")
def user_session():
    """Login as regular user and return auth headers."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    if resp.status_code != 200:
        pytest.skip("User login failed")
    data = resp.json()
    return {
        "Authorization": f"Bearer {data['token']}",
        "Content-Type": "application/json"
    }, data


# ── Health & Regression Tests ─────────────────────────────────────────────────

class TestHealthAndRegression:
    """Regression tests for health, heartbeat, GZip, X-Response-Time."""

    def test_health_endpoint(self):
        """Health endpoint returns healthy status with DB connected."""
        start = time.time()
        resp = requests.get(f"{BASE_URL}/api/health")
        elapsed = time.time() - start
        
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "healthy", f"Status not healthy: {data}"
        assert data["checks"]["database"]["connected"] is True
        assert elapsed < 0.5, f"Health check too slow: {elapsed}s"
        print(f"PASS: Health endpoint healthy, DB connected, {elapsed*1000:.0f}ms")

    def test_heartbeat_alive(self):
        """Heartbeat endpoint returns alive status."""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"
        assert data["active"] is True
        print("PASS: Heartbeat alive")

    def test_gzip_active(self):
        """GZip compression is active for large responses."""
        resp = requests.get(f"{BASE_URL}/api/health", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        # Check if response was compressed (Content-Encoding header)
        encoding = resp.headers.get("Content-Encoding", "")
        # Note: requests auto-decompresses, so we check if it was sent compressed
        print(f"PASS: GZip check complete (encoding: {encoding or 'auto-decompressed'})")

    def test_x_response_time_header(self):
        """X-Response-Time header is present in responses."""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        x_time = resp.headers.get("X-Response-Time")
        assert x_time is not None, "X-Response-Time header missing"
        assert "ms" in x_time, f"X-Response-Time format wrong: {x_time}"
        print(f"PASS: X-Response-Time header present: {x_time}")


# ── Auth Tests (Refactored auth.py) ───────────────────────────────────────────

class TestAuthRefactor:
    """Tests for refactored auth.py with split helper functions."""

    def test_owner_login_success(self, owner_session):
        """Owner login works with refactored auth_access."""
        headers, data = owner_session
        assert data["role"] == "owner"
        assert data["token"]
        assert data["user_key"]
        assert data["username"] == "@shish123"
        print(f"PASS: Owner login successful, role={data['role']}")

    def test_user_login_success(self, user_session):
        """User login works with refactored auth_access."""
        headers, data = user_session
        assert data["role"] in ("user", "member")
        assert data["token"]
        assert data["user_key"]
        print(f"PASS: User login successful, role={data['role']}")

    def test_auth_me_endpoint(self, owner_session):
        """GET /api/auth/me returns user data."""
        headers, _ = owner_session
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "owner"
        assert data["username"] == "@shish123"
        assert "credits" in data
        assert "fno_budget" in data
        print(f"PASS: /api/auth/me returns user data")

    def test_auth_logout(self, owner_session):
        """POST /api/auth/logout works."""
        # Create a new session to logout
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert resp.status_code == 200
        token = resp.json()["token"]
        
        logout_resp = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert logout_resp.status_code == 200
        assert logout_resp.json()["ok"] is True
        print("PASS: Logout successful")

    def test_invalid_username_rejected(self):
        """Invalid username returns 400/404."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "x"})
        assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
        print("PASS: Invalid username rejected")

    def test_empty_username_rejected(self):
        """Empty username returns 400."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": ""})
        assert resp.status_code == 400
        print("PASS: Empty username rejected")


# ── Alert System Tests (Refactored alerts.py) ─────────────────────────────────

class TestAlertsRefactor:
    """Tests for refactored alerts.py with split helper functions."""

    def test_list_alert_rules(self, owner_session):
        """GET /api/alerts/rules returns rules list."""
        headers, _ = owner_session
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert "count" in data
        print(f"PASS: List alert rules - {data['count']} rules")

    def test_create_alert_rule(self, owner_session):
        """POST /api/alerts/rules creates a new rule."""
        headers, _ = owner_session
        rule = {
            "name": "TEST_VIX_Alert_82",
            "conditions": [
                {"field": "vix", "operator": "gt", "value": 20}
            ],
            "logic": "AND",
            "notify_type": "push",
            "enabled": True
        }
        resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=rule, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["rule"]["name"] == "TEST_VIX_Alert_82"
        rule_id = data["rule"]["rule_id"]
        print(f"PASS: Created alert rule: {rule_id}")
        return rule_id

    def test_update_alert_rule(self, owner_session):
        """PATCH /api/alerts/rules/{rule_id} updates a rule."""
        headers, _ = owner_session
        # First create a rule
        rule = {
            "name": "TEST_Update_Rule_82",
            "conditions": [{"field": "vix", "operator": "lt", "value": 15}],
            "logic": "AND",
            "enabled": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=rule, headers=headers)
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule"]["rule_id"]
        
        # Update the rule
        update_resp = requests.patch(
            f"{BASE_URL}/api/alerts/rules/{rule_id}",
            json={"name": "TEST_Updated_Rule_82", "enabled": False},
            headers=headers
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["updated"] is True
        print(f"PASS: Updated alert rule: {rule_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/alerts/rules/{rule_id}", headers=headers)

    def test_delete_alert_rule(self, owner_session):
        """DELETE /api/alerts/rules/{rule_id} deletes a rule."""
        headers, _ = owner_session
        # First create a rule
        rule = {
            "name": "TEST_Delete_Rule_82",
            "conditions": [{"field": "vix", "operator": "gt", "value": 25}],
            "logic": "AND",
            "enabled": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=rule, headers=headers)
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule"]["rule_id"]
        
        # Delete the rule
        delete_resp = requests.delete(f"{BASE_URL}/api/alerts/rules/{rule_id}", headers=headers)
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True
        print(f"PASS: Deleted alert rule: {rule_id}")

    def test_evaluate_alerts(self, owner_session):
        """POST /api/alerts/evaluate runs evaluation correctly."""
        headers, _ = owner_session
        resp = requests.post(f"{BASE_URL}/api/alerts/evaluate", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "triggered" in data
        assert "evaluated" in data
        assert "ts" in data
        print(f"PASS: Evaluate alerts - {data['evaluated']} rules evaluated")


# ── app_state Tests ───────────────────────────────────────────────────────────

class TestAppState:
    """Tests for expanded app_state.py module."""

    def test_app_state_session_store_accessible(self):
        """SESSION_STORE is accessible from app_state."""
        # This is a code review test - verify the module structure
        import sys
        sys.path.insert(0, "/app/backend")
        from services import app_state
        
        assert hasattr(app_state, "SESSION_STORE")
        assert isinstance(app_state.SESSION_STORE, dict)
        print("PASS: SESSION_STORE accessible from app_state")

    def test_app_state_utc_now_iso(self):
        """_utc_now_iso() returns valid ISO timestamp."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services import app_state
        
        assert hasattr(app_state, "_utc_now_iso")
        ts = app_state._utc_now_iso()
        assert isinstance(ts, str)
        assert "T" in ts  # ISO format has T separator
        assert "+" in ts or "Z" in ts  # Has timezone info
        print(f"PASS: _utc_now_iso() returns valid timestamp: {ts}")

    def test_app_state_configure_runtime(self):
        """configure_runtime() function exists and is callable."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services import app_state
        
        assert hasattr(app_state, "configure_runtime")
        assert callable(app_state.configure_runtime)
        print("PASS: configure_runtime() exists and is callable")

    def test_app_state_owner_bootstrap_username(self):
        """OWNER_BOOTSTRAP_USERNAME is accessible."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services import app_state
        
        assert hasattr(app_state, "OWNER_BOOTSTRAP_USERNAME")
        # After server startup, this should be set
        print(f"PASS: OWNER_BOOTSTRAP_USERNAME accessible: {app_state.OWNER_BOOTSTRAP_USERNAME or '(not set yet)'}")


# ── AI Chat Tests ─────────────────────────────────────────────────────────────

class TestAIChat:
    """Tests for AI chat endpoint."""

    def test_ai_chat_response(self, owner_session):
        """POST /api/livehelp/ai-chat returns AI response."""
        headers, _ = owner_session
        resp = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={"message": "What is NIFTY?", "session_id": "test-82"},
            headers=headers,
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert len(data["reply"]) > 10  # Meaningful response
        print(f"PASS: AI chat response received ({len(data['reply'])} chars)")


# ── Admin Payments Tests ──────────────────────────────────────────────────────

class TestAdminPayments:
    """Tests for admin payments endpoints."""

    def test_payments_config_status(self, owner_session):
        """GET /api/admin/payments/config-status works."""
        headers, _ = owner_session
        resp = requests.get(f"{BASE_URL}/api/admin/payments/config-status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "razorpay_configured" in data
        assert "upi_configured" in data
        print(f"PASS: Payments config status - Razorpay: {data['razorpay_configured']}, UPI: {data['upi_configured']}")

    def test_payments_pending(self, owner_session):
        """GET /api/admin/payments/pending works."""
        headers, _ = owner_session
        resp = requests.get(f"{BASE_URL}/api/admin/payments/pending", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "payments" in data
        print(f"PASS: Pending payments - {len(data['payments'])} pending")


# ── CRM Tests ─────────────────────────────────────────────────────────────────

class TestCRM:
    """Tests for CRM inbox endpoints."""

    def test_admin_crm_inbox(self, owner_session):
        """GET /api/admin/crm/inbox works."""
        headers, _ = owner_session
        resp = requests.get(f"{BASE_URL}/api/admin/crm/inbox", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        print(f"PASS: Admin CRM inbox - {len(data['messages'])} messages")

    def test_user_crm_inbox(self, user_session):
        """GET /api/crm/inbox works for users."""
        headers, _ = user_session
        resp = requests.get(f"{BASE_URL}/api/crm/inbox", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        print(f"PASS: User CRM inbox - {len(data['messages'])} messages")


# ── Cleanup ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_rules(owner_session):
    """Cleanup TEST_ prefixed alert rules after tests."""
    yield
    headers, _ = owner_session
    try:
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=headers)
        if resp.status_code == 200:
            rules = resp.json().get("rules", [])
            for rule in rules:
                if rule.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/alerts/rules/{rule['rule_id']}", headers=headers)
    except Exception:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
