"""
Iteration 87: Phase 33 Clean Desk Testing
- Plans comparison page (new nav tab)
- Payment history tab in admin payments
- Fraud dashboard with summary cards + filters
- Domain mapping extraction (admin_domains.py)
- Type hints on services/app_state.py
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    return resp.json().get("token")

@pytest.fixture(scope="module")
def owner_headers(owner_token):
    """Auth headers for owner."""
    return {"Authorization": f"Bearer {owner_token}"}

@pytest.fixture(scope="module")
def user_token():
    """Get regular user auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    return resp.json().get("token")

@pytest.fixture(scope="module")
def user_headers(user_token):
    """Auth headers for regular user."""
    return {"Authorization": f"Bearer {user_token}"}


# ── Health & Regression Tests ─────────────────────────────────────────────────

class TestHealthRegression:
    """Basic health checks."""
    
    def test_health_endpoint(self):
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("healthy", "degraded")
        assert "checks" in data
        print("PASS: Health endpoint healthy")
    
    def test_heartbeat(self):
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "alive"
        print("PASS: Heartbeat alive")


class TestAuth:
    """Authentication tests."""
    
    def test_owner_login(self, owner_token):
        assert owner_token is not None
        assert len(owner_token) > 10
        print("PASS: Owner @shish123 login works")
    
    def test_user_login(self, user_token):
        assert user_token is not None
        assert len(user_token) > 10
        print("PASS: User Manas@2005 login works")
    
    def test_auth_me(self, owner_headers):
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") == "owner"
        assert data.get("username") == "@shish123"
        print("PASS: /api/auth/me returns owner data")


# ── Plans/Packages Tests (for Plan Comparison Page) ───────────────────────────

class TestPackages:
    """Test /api/admin/packages endpoint used by Plans page."""
    
    def test_get_packages(self, owner_headers):
        """Verify packages endpoint returns tier data for Plans page."""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "packages" in data
        assert "default_feature_costs" in data
        
        packages = data["packages"]
        # Should have at least free, basic, pro, unlimited
        assert "free" in packages, "Missing free tier"
        assert "basic" in packages, "Missing basic tier"
        assert "pro" in packages, "Missing pro tier"
        assert "unlimited" in packages, "Missing unlimited tier"
        
        # Verify each package has required fields
        for key, pkg in packages.items():
            assert "label" in pkg, f"Package {key} missing label"
            assert "credits" in pkg, f"Package {key} missing credits"
            assert "limits" in pkg, f"Package {key} missing limits"
        
        print(f"PASS: GET /api/admin/packages returns {len(packages)} tiers (free/basic/pro/unlimited)")
    
    def test_packages_have_correct_structure(self, owner_headers):
        """Verify package structure matches what PlanComparison.jsx expects."""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check free tier structure
        free = data["packages"].get("free", {})
        assert free.get("label") == "Free Tier"
        assert free.get("credits") == 10
        assert "fno_generate_daily" in free.get("limits", {})
        
        # Check unlimited tier
        unlimited = data["packages"].get("unlimited", {})
        assert unlimited.get("credits") == 999999
        
        print("PASS: Package structure matches PlanComparison.jsx expectations")
    
    def test_create_and_delete_package(self, owner_headers):
        """Test package CRUD for Plans management."""
        # Create test package
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/packages",
            headers=owner_headers,
            json={
                "key": "test_plan_it87",
                "label": "Test Plan IT87",
                "credits": 50,
                "limits": {"fno_generate_daily": 10}
            }
        )
        assert create_resp.status_code == 200
        assert create_resp.json().get("ok") is True
        print("PASS: Created test_plan_it87 package")
        
        # Verify it exists
        get_resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert "test_plan_it87" in get_resp.json()["packages"]
        print("PASS: Package verified in list")
        
        # Delete it
        del_resp = requests.delete(
            f"{BASE_URL}/api/admin/packages/test_plan_it87",
            headers=owner_headers
        )
        assert del_resp.status_code == 200
        assert del_resp.json().get("deleted") is True
        print("PASS: Package deleted")
        
        # Verify deletion
        get_resp2 = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert "test_plan_it87" not in get_resp2.json()["packages"]
        print("PASS: Package removal verified")


# ── Payment History Tests ─────────────────────────────────────────────────────

class TestPaymentHistory:
    """Test new /api/admin/payments/history endpoint."""
    
    def test_payment_history_endpoint(self, owner_headers):
        """Verify payment history endpoint returns correct structure."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/payments/history?limit=50",
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "payments" in data
        assert "total" in data
        assert isinstance(data["payments"], list)
        assert isinstance(data["total"], int)
        
        print(f"PASS: GET /api/admin/payments/history returns {len(data['payments'])} payments, total={data['total']}")
    
    def test_payment_history_pagination(self, owner_headers):
        """Test pagination parameters."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/payments/history?limit=10&skip=0",
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert data["count"] <= 10
        print("PASS: Payment history pagination works")
    
    def test_pending_payments_endpoint(self, owner_headers):
        """Verify pending payments endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/pending", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "payments" in data
        print(f"PASS: GET /api/admin/payments/pending returns {len(data['payments'])} pending")


# ── Fraud Detection Tests ─────────────────────────────────────────────────────

class TestFraudDetection:
    """Test fraud detection endpoints for enhanced dashboard."""
    
    def test_fraud_incidents_endpoint(self, owner_headers):
        """Verify fraud incidents endpoint returns data for summary cards."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/fraud-incidents?status=all",
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "incidents" in data
        assert isinstance(data["incidents"], list)
        
        # Frontend calculates pending/resolved from this list
        print(f"PASS: GET /api/admin/fraud-incidents returns {len(data['incidents'])} incidents")
    
    def test_fraud_incidents_filter_pending(self, owner_headers):
        """Test filtering by pending status."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/fraud-incidents?status=pending",
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # All returned should be pending
        for inc in data.get("incidents", []):
            assert inc.get("status") == "pending"
        print("PASS: Fraud incidents filter by pending works")


# ── Domain Mapping Extraction Tests ───────────────────────────────────────────

class TestDomainMappingExtraction:
    """Test domain endpoints moved to admin_domains.py."""
    
    def test_dns_instructions_endpoint(self, owner_headers):
        """Verify DNS instructions endpoint works after extraction."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/dns-instructions?domain=test.example.com",
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "fqdn" in data
        assert "root_domain" in data
        assert "host_label" in data
        assert "record_type" in data
        assert "steps" in data
        
        assert data["fqdn"] == "test.example.com"
        assert data["record_type"] == "A"
        assert isinstance(data["steps"], list)
        
        print("PASS: GET /api/admin/dns-instructions works after extraction")
    
    def test_domain_mapping_crud(self, owner_headers):
        """Test domain mapping create/delete after extraction."""
        # Create
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/domain-mappings",
            headers=owner_headers,
            json={
                "domain": "test-it87.example.com",
                "target_record": "1.2.3.4",
                "record_type": "A"
            }
        )
        assert create_resp.status_code == 200
        data = create_resp.json()
        assert data.get("domain") == "test-it87.example.com"
        print("PASS: Domain mapping created")
        
        # Delete
        del_resp = requests.delete(
            f"{BASE_URL}/api/admin/domain-mappings/test-it87.example.com",
            headers=owner_headers
        )
        assert del_resp.status_code == 200
        assert del_resp.json().get("deleted") is True
        print("PASS: Domain mapping deleted")


# ── Feature Costs Tests ───────────────────────────────────────────────────────

class TestFeatureCosts:
    """Test feature costs endpoint."""
    
    def test_get_feature_costs(self, owner_headers):
        """Verify feature costs are returned with packages."""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        costs = data.get("default_feature_costs", {})
        # Should have standard features
        expected_features = [
            "fno_generate", "multibagger_generate", "portfolio_analyze",
            "custom_position", "backtest_run", "iv_collect",
            "reports_view", "watchlist_add", "alert_rule_create"
        ]
        for feat in expected_features:
            assert feat in costs, f"Missing feature cost: {feat}"
        
        print(f"PASS: Feature costs returned with {len(costs)} features")
    
    def test_update_feature_costs(self, owner_headers):
        """Test updating global feature costs."""
        # Get current
        get_resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        original_costs = get_resp.json().get("default_feature_costs", {})
        original_fno = original_costs.get("fno_generate", 2.0)
        
        # Update
        update_resp = requests.patch(
            f"{BASE_URL}/api/admin/feature-costs",
            headers=owner_headers,
            json={"costs": {"fno_generate": 2.5}}
        )
        assert update_resp.status_code == 200
        assert update_resp.json().get("ok") is True
        print("PASS: Feature cost update accepted")
        
        # Restore
        restore_resp = requests.patch(
            f"{BASE_URL}/api/admin/feature-costs",
            headers=owner_headers,
            json={"costs": {"fno_generate": original_fno}}
        )
        assert restore_resp.status_code == 200
        print("PASS: Feature cost restored")
    
    def test_invalid_feature_key_rejected(self, owner_headers):
        """Test that invalid feature keys are rejected."""
        resp = requests.patch(
            f"{BASE_URL}/api/admin/feature-costs",
            headers=owner_headers,
            json={"costs": {"invalid_feature_xyz": 1.0}}
        )
        assert resp.status_code == 400
        print("PASS: Invalid feature key rejected")


# ── Admin Regression Tests ────────────────────────────────────────────────────

class TestAdminRegression:
    """Regression tests for existing admin functionality."""
    
    def test_admin_config(self, owner_headers):
        """Verify admin config endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/admin/config", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "api_controls" in data
        assert "kite" in data
        print("PASS: Admin config endpoint works")
    
    def test_admin_macro_events(self, owner_headers):
        """Verify macro events endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/admin/macro-events", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "all_events" in data
        print("PASS: Admin macro events works")
    
    def test_admin_data_stats(self, owner_headers):
        """Verify data stats endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/admin/data/stats", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        print("PASS: Admin data stats works")
    
    def test_admin_users_list(self, owner_headers):
        """Verify users list endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"PASS: Admin users list returns {len(data)} users")
    
    def test_suspend_unsuspend_regression(self, owner_headers):
        """Verify suspend/unsuspend still works."""
        # Get a non-owner user
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        users = users_resp.json()
        test_user = None
        for u in users:
            if u.get("role") != "owner":
                test_user = u
                break
        
        if not test_user:
            pytest.skip("No non-owner user to test suspend")
        
        user_key = test_user.get("user_key")
        
        # Toggle suspend
        resp = requests.post(
            f"{BASE_URL}/api/admin/users/{user_key}/suspend",
            headers=owner_headers
        )
        assert resp.status_code == 200
        new_state = resp.json().get("suspended")
        print(f"PASS: Suspend toggle worked, new state: {new_state}")
        
        # Toggle back
        resp2 = requests.post(
            f"{BASE_URL}/api/admin/users/{user_key}/suspend",
            headers=owner_headers
        )
        assert resp2.status_code == 200
        print("PASS: Suspend toggle back worked")
    
    def test_topup_regression(self, owner_headers):
        """Verify topup still works."""
        # Get a non-owner user
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        users = users_resp.json()
        test_user = None
        for u in users:
            if u.get("role") != "owner":
                test_user = u
                break
        
        if not test_user:
            pytest.skip("No non-owner user to test topup")
        
        user_key = test_user.get("user_key")
        
        resp = requests.post(
            f"{BASE_URL}/api/admin/users/{user_key}/topup",
            headers=owner_headers,
            json={"credits": 1.0}
        )
        assert resp.status_code == 200
        assert resp.json().get("added") == 1.0
        print("PASS: Topup regression works")
    
    def test_csv_export_regression(self, owner_headers):
        """Verify CSV export still works."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/users/export",
            headers=owner_headers
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        content = resp.text
        assert "user_key" in content
        assert "username" in content
        print("PASS: CSV export regression works")


# ── Payment Config Tests ──────────────────────────────────────────────────────

class TestPaymentConfig:
    """Test payment configuration endpoints."""
    
    def test_payment_config_status(self, owner_headers):
        """Verify payment config status endpoint."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/payments/config-status",
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "razorpay_configured" in data
        assert "upi_configured" in data
        print("PASS: Payment config status endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
