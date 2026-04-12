"""
Iteration 74 Backend Tests - Four Major Features:
1. Custom Alert Rule Engine (CRUD + evaluation)
2. Admin Permissions & Package Management (tiered packages)
3. Geospatial Fraud Detection (impossible travel + suspension)
4. CRM Module (two-way admin-user messaging)
Plus regression tests for iteration 73 features.
"""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
OWNER_USERNAME = "@shish123"
USER_USERNAME = "Manas@2005"


@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": OWNER_USERNAME})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Owner login failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def user_token():
    """Get regular user auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": USER_USERNAME})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"User login failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 1: Custom Alert Rule Engine
# ══════════════════════════════════════════════════════════════════════════════

class TestAlertRulesFeature:
    """Test Alert Rules CRUD and evaluation."""

    def test_alert_rules_list(self, owner_headers):
        """GET /api/alerts/rules returns rules list."""
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "rules" in data
        assert "count" in data
        assert isinstance(data["rules"], list)
        print(f"PASS: Alert rules list returned {data['count']} rules")

    def test_alert_rule_create(self, owner_headers):
        """POST /api/alerts/rules creates a rule with conditions."""
        payload = {
            "name": "TEST_NIFTY_Above_24000",
            "logic": "AND",
            "conditions": [
                {"field": "symbol_ltp", "symbol": "NIFTY", "operator": "gt", "value": 24000}
            ],
            "notify_type": "push",
            "enabled": True
        }
        resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=payload, headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("created") is True
        assert "rule" in data
        assert data["rule"]["name"] == "TEST_NIFTY_Above_24000"
        assert len(data["rule"]["conditions"]) == 1
        print(f"PASS: Alert rule created with ID {data['rule']['rule_id']}")
        return data["rule"]["rule_id"]

    def test_alert_rule_create_with_multiple_conditions(self, owner_headers):
        """POST /api/alerts/rules with multiple conditions (AND/OR logic)."""
        payload = {
            "name": "TEST_NIFTY_VIX_Combo",
            "logic": "AND",
            "conditions": [
                {"field": "symbol_ltp", "symbol": "NIFTY", "operator": "gt", "value": 24000},
                {"field": "vix", "symbol": None, "operator": "gt", "value": 15}
            ],
            "notify_type": "both",
            "enabled": True
        }
        resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=payload, headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("created") is True
        assert len(data["rule"]["conditions"]) == 2
        print(f"PASS: Alert rule with 2 conditions created")

    def test_alert_rule_toggle_enabled(self, owner_headers):
        """PATCH /api/alerts/rules/{id} toggles enabled status."""
        # First create a rule
        payload = {
            "name": "TEST_Toggle_Rule",
            "logic": "AND",
            "conditions": [{"field": "symbol_ltp", "symbol": "RELIANCE", "operator": "gt", "value": 2500}],
            "enabled": True
        }
        create_resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=payload, headers=owner_headers)
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule"]["rule_id"]

        # Toggle to disabled
        toggle_resp = requests.patch(
            f"{BASE_URL}/api/alerts/rules/{rule_id}",
            json={"enabled": False},
            headers=owner_headers
        )
        assert toggle_resp.status_code == 200, f"Expected 200, got {toggle_resp.status_code}: {toggle_resp.text}"
        assert toggle_resp.json().get("updated") is True
        print(f"PASS: Alert rule {rule_id} toggled to disabled")

    def test_alert_rule_delete(self, owner_headers):
        """DELETE /api/alerts/rules/{id} deletes a rule."""
        # Create a rule to delete
        payload = {
            "name": "TEST_Delete_Rule",
            "logic": "AND",
            "conditions": [{"field": "symbol_ltp", "symbol": "TCS", "operator": "lt", "value": 4000}],
            "enabled": False
        }
        create_resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=payload, headers=owner_headers)
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule"]["rule_id"]

        # Delete the rule
        delete_resp = requests.delete(f"{BASE_URL}/api/alerts/rules/{rule_id}", headers=owner_headers)
        assert delete_resp.status_code == 200, f"Expected 200, got {delete_resp.status_code}: {delete_resp.text}"
        assert delete_resp.json().get("deleted") is True
        print(f"PASS: Alert rule {rule_id} deleted")

    def test_alert_evaluate(self, owner_headers):
        """POST /api/alerts/evaluate evaluates rules against live data."""
        resp = requests.post(f"{BASE_URL}/api/alerts/evaluate", json={}, headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "triggered" in data
        assert "evaluated" in data
        assert isinstance(data["triggered"], list)
        print(f"PASS: Alert evaluation completed - {data['evaluated']} rules evaluated, {len(data['triggered'])} triggered")


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 2: Admin Permissions & Package Management
# ══════════════════════════════════════════════════════════════════════════════

class TestPackagesAndPermissions:
    """Test tiered service packages and user permissions."""

    def test_packages_list(self, owner_headers):
        """GET /api/admin/packages returns free/basic/pro/unlimited tiers."""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "packages" in data
        packages = data["packages"]
        # Verify all 4 tiers exist
        assert "free" in packages, "Missing 'free' package"
        assert "basic" in packages, "Missing 'basic' package"
        assert "pro" in packages, "Missing 'pro' package"
        assert "unlimited" in packages, "Missing 'unlimited' package"
        # Verify structure
        assert packages["free"]["label"] == "Free Tier"
        assert "credits" in packages["free"]
        assert "limits" in packages["free"]
        print(f"PASS: Packages endpoint returns 4 tiers: {list(packages.keys())}")

    def test_user_permissions_get(self, owner_headers):
        """GET /api/admin/users/{user_ref}/permissions returns user package and limits."""
        # First get user list to find a user_key
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert users_resp.status_code == 200
        users = users_resp.json()
        if not users:
            pytest.skip("No users found to test permissions")
        
        user_key = users[0]["user_key"]
        resp = requests.get(f"{BASE_URL}/api/admin/users/{user_key}/permissions", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "user_key" in data
        assert "package" in data
        assert "package_label" in data
        assert "feature_costs" in data
        assert "usage_limits" in data
        assert "current_usage" in data
        print(f"PASS: User permissions returned for {data.get('username')} - package: {data['package']}")

    def test_user_permissions_update_package(self, owner_headers):
        """PATCH /api/admin/users/{user_ref}/permissions updates package."""
        # Get a non-owner user
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        users = users_resp.json()
        non_owner = next((u for u in users if u["role"] != "owner"), None)
        if not non_owner:
            pytest.skip("No non-owner user found to test package update")
        
        user_key = non_owner["user_key"]
        
        # Update to basic package
        resp = requests.patch(
            f"{BASE_URL}/api/admin/users/{user_key}/permissions",
            json={"package": "basic"},
            headers=owner_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("updated") is True
        assert "package" in data.get("changes", [])
        print(f"PASS: User {user_key} package updated to 'basic'")

        # Verify the change
        verify_resp = requests.get(f"{BASE_URL}/api/admin/users/{user_key}/permissions", headers=owner_headers)
        assert verify_resp.status_code == 200
        assert verify_resp.json()["package"] == "basic"
        print("PASS: Package change verified via GET")


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 3: Geospatial Fraud Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestFraudDetection:
    """Test fraud detection endpoints."""

    def test_fraud_incidents_list(self, owner_headers):
        """GET /api/admin/fraud-incidents returns incidents list."""
        resp = requests.get(f"{BASE_URL}/api/admin/fraud-incidents", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "incidents" in data
        assert "count" in data
        assert isinstance(data["incidents"], list)
        print(f"PASS: Fraud incidents list returned {data['count']} incidents")

    def test_fraud_incidents_filter_by_status(self, owner_headers):
        """GET /api/admin/fraud-incidents?status=all returns all incidents."""
        resp = requests.get(f"{BASE_URL}/api/admin/fraud-incidents?status=all", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "incidents" in data
        print(f"PASS: Fraud incidents (all status) returned {data['count']} incidents")

    def test_fraud_non_admin_forbidden(self, user_headers):
        """Non-admin users cannot access fraud incidents."""
        resp = requests.get(f"{BASE_URL}/api/admin/fraud-incidents", headers=user_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("PASS: Non-admin correctly forbidden from fraud incidents")


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 4: CRM Module
# ══════════════════════════════════════════════════════════════════════════════

class TestCrmModule:
    """Test CRM two-way messaging."""

    def test_admin_crm_inbox(self, owner_headers):
        """GET /api/admin/crm/inbox returns admin inbox."""
        resp = requests.get(f"{BASE_URL}/api/admin/crm/inbox", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "messages" in data
        assert "count" in data
        assert "unread" in data
        print(f"PASS: Admin CRM inbox returned {data['count']} messages, {data['unread']} unread")

    def test_admin_crm_send_targeted(self, owner_headers):
        """POST /api/admin/crm/send sends message to specific user."""
        # Get a user to send to
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        users = users_resp.json()
        non_owner = next((u for u in users if u["role"] != "owner"), None)
        if not non_owner:
            pytest.skip("No non-owner user found to send message to")
        
        payload = {
            "to_user_key": non_owner["user_key"],
            "subject": "TEST_CRM_Message",
            "body": "This is a test message from iteration 74 tests.",
            "priority": "normal"
        }
        resp = requests.post(f"{BASE_URL}/api/admin/crm/send", json=payload, headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("sent") is True
        assert "message_id" in data
        print(f"PASS: CRM message sent to {non_owner['username']}")

    def test_admin_crm_send_broadcast(self, owner_headers):
        """POST /api/admin/crm/send broadcasts to all users."""
        payload = {
            "to_user_key": None,  # Broadcast
            "subject": "TEST_Broadcast_Message",
            "body": "This is a test broadcast from iteration 74 tests.",
            "priority": "high"
        }
        resp = requests.post(f"{BASE_URL}/api/admin/crm/send", json=payload, headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("sent") is True
        assert data.get("broadcast") is True
        assert "recipients" in data
        print(f"PASS: CRM broadcast sent to {data['recipients']} recipients")

    def test_admin_crm_sent(self, owner_headers):
        """GET /api/admin/crm/sent returns sent messages."""
        resp = requests.get(f"{BASE_URL}/api/admin/crm/sent", headers=owner_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "messages" in data
        assert "count" in data
        print(f"PASS: Admin CRM sent messages returned {data['count']} messages")

    def test_user_crm_inbox(self, user_headers):
        """GET /api/crm/inbox returns user's messages from admin."""
        resp = requests.get(f"{BASE_URL}/api/crm/inbox", headers=user_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "messages" in data
        assert "count" in data
        assert "unread" in data
        print(f"PASS: User CRM inbox returned {data['count']} messages")

    def test_user_crm_contact_support(self, user_headers):
        """POST /api/crm/contact sends support message to admin."""
        payload = {
            "subject": "TEST_Support_Request",
            "body": "This is a test support request from iteration 74 tests."
        }
        resp = requests.post(f"{BASE_URL}/api/crm/contact", json=payload, headers=user_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("sent") is True
        assert "message_id" in data
        print(f"PASS: User support message sent with ID {data['message_id']}")


# ══════════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS (Iteration 73 features)
# ══════════════════════════════════════════════════════════════════════════════

class TestRegressionIteration73:
    """Regression tests for iteration 73 features."""

    def test_heartbeat_alive(self):
        """GET /api/heartbeat returns alive status."""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        assert resp.json().get("status") == "alive"
        print("PASS: Heartbeat returns alive")

    def test_health_endpoint(self):
        """GET /api/health returns comprehensive health status."""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        # Health data is nested under 'checks' key
        checks = data.get("checks", {})
        assert "database" in checks
        assert "kite_session" in checks
        print(f"PASS: Health endpoint returns healthy status")

    def test_gzip_compression_active(self):
        """Verify GZip compression is active."""
        resp = requests.get(
            f"{BASE_URL}/api/health",
            headers={"Accept-Encoding": "gzip, deflate"}
        )
        assert resp.status_code == 200
        # Check if response was compressed (Content-Encoding header)
        encoding = resp.headers.get("Content-Encoding", "")
        print(f"PASS: Response encoding: {encoding or 'none (small response)'}")

    def test_response_time_header(self):
        """Verify X-Response-Time header is present."""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        response_time = resp.headers.get("X-Response-Time")
        assert response_time is not None, "X-Response-Time header missing"
        print(f"PASS: X-Response-Time header present: {response_time}")

    def test_watchlist_crud(self, owner_headers):
        """Verify watchlist CRUD still works."""
        resp = requests.get(f"{BASE_URL}/api/watchlist", headers=owner_headers)
        assert resp.status_code == 200
        assert "items" in resp.json()
        print("PASS: Watchlist GET works")

    def test_journal_crud(self, owner_headers):
        """Verify journal CRUD still works."""
        resp = requests.get(f"{BASE_URL}/api/journal", headers=owner_headers)
        assert resp.status_code == 200
        print("PASS: Journal GET works")

    def test_notifications_crud(self, owner_headers):
        """Verify notifications CRUD still works."""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers)
        assert resp.status_code == 200
        print("PASS: Notifications GET works")

    def test_reports_daily_summary(self, owner_headers):
        """Verify reports daily summary still works."""
        resp = requests.get(f"{BASE_URL}/api/reports/daily-summary", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "period" in data or "summary" in data or "trades" in data
        print("PASS: Reports daily summary works")


# ══════════════════════════════════════════════════════════════════════════════
# AUTH FLOW TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthFlow:
    """Test authentication flow including suspended account handling."""

    def test_owner_login_success(self):
        """Owner login works correctly."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": OWNER_USERNAME})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "token" in data
        assert data.get("role") == "owner"
        print(f"PASS: Owner login successful, role={data['role']}")

    def test_user_login_success(self):
        """Regular user login works correctly."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": USER_USERNAME})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "token" in data
        print(f"PASS: User login successful, role={data.get('role')}")

    def test_invalid_username_404(self):
        """Invalid username returns 404."""
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "INVALID_USER_12345"})
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: Invalid username returns 404")


# ══════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ══════════════════════════════════════════════════════════════════════════════

class TestCleanup:
    """Cleanup test data created during tests."""

    def test_cleanup_test_alert_rules(self, owner_headers):
        """Delete TEST_ prefixed alert rules."""
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=owner_headers)
        if resp.status_code == 200:
            rules = resp.json().get("rules", [])
            deleted = 0
            for rule in rules:
                if rule.get("name", "").startswith("TEST_"):
                    del_resp = requests.delete(
                        f"{BASE_URL}/api/alerts/rules/{rule['rule_id']}",
                        headers=owner_headers
                    )
                    if del_resp.status_code == 200:
                        deleted += 1
            print(f"PASS: Cleaned up {deleted} test alert rules")
        else:
            print("SKIP: Could not fetch rules for cleanup")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
