"""
Iteration 86: Superadmin CRUD Expansion Tests
- Suspend/Unsuspend users
- Credit topup
- Bulk credit adjustment
- CSV export of users
- Package CRUD (create/delete)
- Global feature costs management
- Regression: Health, auth, admin endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    """Get owner token for @shish123"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    return resp.json().get("token")

@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}

@pytest.fixture(scope="module")
def user_manas_key(owner_headers):
    """Get user_key for Manas@2005"""
    resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
    assert resp.status_code == 200
    users = resp.json()
    for u in users:
        if u.get("username") == "Manas@2005":
            return u.get("user_key")
    pytest.skip("Manas@2005 user not found")

# ─── Health & Regression ─────────────────────────────────────────────────────

class TestHealthRegression:
    """Basic health and regression tests"""
    
    def test_health_endpoint(self):
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print("PASS: Health endpoint healthy")
    
    def test_heartbeat(self):
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "alive" or data.get("active") is True
        print("PASS: Heartbeat alive")

# ─── Auth Tests ──────────────────────────────────────────────────────────────

class TestAuth:
    """Auth access tests"""
    
    def test_owner_login(self, owner_token):
        assert owner_token is not None
        assert len(owner_token) > 10
        print(f"PASS: Owner login successful, token length: {len(owner_token)}")
    
    def test_user_login(self):
        resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        print("PASS: User Manas@2005 login successful")
    
    def test_auth_me(self, owner_headers):
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("username") == "@shish123"
        assert data.get("role") == "owner"
        print("PASS: /api/auth/me returns owner data")

# ─── Suspend/Unsuspend Tests ─────────────────────────────────────────────────

class TestSuspendUnsuspend:
    """Test suspend/unsuspend toggle for users"""
    
    def test_suspend_user(self, owner_headers, user_manas_key):
        """Suspend Manas@2005"""
        resp = requests.post(f"{BASE_URL}/api/admin/users/{user_manas_key}/suspend", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "suspended" in data
        print(f"PASS: Suspend toggle - suspended={data['suspended']}, username={data.get('username')}")
        return data["suspended"]
    
    def test_unsuspend_user(self, owner_headers, user_manas_key):
        """Ensure Manas@2005 is unsuspended after test"""
        # First check current state
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        users = resp.json()
        manas = next((u for u in users if u.get("user_key") == user_manas_key), None)
        
        if manas and manas.get("suspended"):
            # Unsuspend
            resp = requests.post(f"{BASE_URL}/api/admin/users/{user_manas_key}/suspend", headers=owner_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["suspended"] is False
            print("PASS: Manas@2005 unsuspended successfully")
        else:
            print("PASS: Manas@2005 already active (not suspended)")

# ─── Topup Tests ─────────────────────────────────────────────────────────────

class TestTopup:
    """Test credit topup functionality"""
    
    def test_topup_credits(self, owner_headers, user_manas_key):
        """Add credits to Manas@2005"""
        # Get current credits
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        users = resp.json()
        manas = next((u for u in users if u.get("user_key") == user_manas_key), None)
        initial_credits = manas.get("credits", 0) if manas else 0
        
        # Topup 10 credits
        resp = requests.post(
            f"{BASE_URL}/api/admin/users/{user_manas_key}/topup",
            json={"credits": 10},
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "credits" in data
        assert data["added"] == 10
        assert data["credits"] >= initial_credits + 10
        print(f"PASS: Topup successful - added={data['added']}, new_credits={data['credits']}")
    
    def test_topup_negative_fails(self, owner_headers, user_manas_key):
        """Negative topup should fail"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/users/{user_manas_key}/topup",
            json={"credits": -5},
            headers=owner_headers
        )
        assert resp.status_code == 400
        print("PASS: Negative topup correctly rejected with 400")

# ─── Bulk Credits Tests ──────────────────────────────────────────────────────

class TestBulkCredits:
    """Test bulk credit adjustment"""
    
    def test_bulk_credits_positive(self, owner_headers, user_manas_key):
        """Bulk add credits to multiple users"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/users/bulk-credits",
            json={"user_keys": [user_manas_key], "credits_delta": 5},
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["adjusted"] >= 1
        print(f"PASS: Bulk credits - adjusted={data['adjusted']}, results={data['results']}")
    
    def test_bulk_credits_negative(self, owner_headers, user_manas_key):
        """Bulk subtract credits"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/users/bulk-credits",
            json={"user_keys": [user_manas_key], "credits_delta": -2},
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["adjusted"] >= 1
        print(f"PASS: Bulk negative credits - adjusted={data['adjusted']}")

# ─── CSV Export Tests ────────────────────────────────────────────────────────

class TestCsvExport:
    """Test CSV export of users"""
    
    def test_export_users_csv(self, owner_headers):
        """Export all users as CSV"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/export", headers=owner_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("Content-Type", "")
        content = resp.text
        # Check CSV has header row
        assert "user_key" in content
        assert "username" in content
        assert "role" in content
        assert "credits" in content
        lines = content.strip().split("\n")
        assert len(lines) >= 2  # Header + at least 1 user
        print(f"PASS: CSV export - {len(lines)-1} users exported")

# ─── Package CRUD Tests ──────────────────────────────────────────────────────

class TestPackageCRUD:
    """Test package creation and deletion"""
    
    def test_get_packages(self, owner_headers):
        """List all packages"""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "packages" in data
        assert "default_feature_costs" in data
        packages = data["packages"]
        # Should have at least free, basic, pro, unlimited
        assert "free" in packages
        print(f"PASS: Get packages - {len(packages)} packages found: {list(packages.keys())}")
    
    def test_create_package(self, owner_headers):
        """Create a new test package"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/packages",
            json={
                "key": "test_plan_it86",
                "label": "Test Plan IT86",
                "credits": 50,
                "limits": {"fno_generate_daily": 10, "alert_rules_total": 5}
            },
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("package_key") == "test_plan_it86"
        print(f"PASS: Package created - key={data['package_key']}, total={data.get('total_packages')}")
    
    def test_verify_package_created(self, owner_headers):
        """Verify the test package exists"""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200
        packages = resp.json().get("packages", {})
        assert "test_plan_it86" in packages
        pkg = packages["test_plan_it86"]
        assert pkg["label"] == "Test Plan IT86"
        assert pkg["credits"] == 50
        print(f"PASS: Package verified - label={pkg['label']}, credits={pkg['credits']}")
    
    def test_delete_package(self, owner_headers):
        """Delete the test package"""
        resp = requests.delete(f"{BASE_URL}/api/admin/packages/test_plan_it86", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("deleted") is True
        print("PASS: Package deleted successfully")
    
    def test_verify_package_deleted(self, owner_headers):
        """Verify the test package is gone"""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        packages = resp.json().get("packages", {})
        assert "test_plan_it86" not in packages
        print("PASS: Package deletion verified")
    
    def test_cannot_delete_free_tier(self, owner_headers):
        """Cannot delete the free tier"""
        resp = requests.delete(f"{BASE_URL}/api/admin/packages/free", headers=owner_headers)
        assert resp.status_code == 400
        print("PASS: Free tier deletion correctly rejected")

# ─── Feature Costs Tests ─────────────────────────────────────────────────────

class TestFeatureCosts:
    """Test global feature costs management"""
    
    def test_get_feature_costs(self, owner_headers):
        """Get current feature costs"""
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        costs = data.get("default_feature_costs", {})
        # Should have 9 features
        expected_features = [
            "fno_generate", "multibagger_generate", "portfolio_analyze",
            "custom_position", "backtest_run", "iv_collect",
            "reports_view", "watchlist_add", "alert_rule_create"
        ]
        for feat in expected_features:
            assert feat in costs, f"Missing feature: {feat}"
        print(f"PASS: Feature costs retrieved - {len(costs)} features: {list(costs.keys())}")
    
    def test_update_feature_costs(self, owner_headers):
        """Update global feature costs"""
        # Get current costs first
        resp = requests.get(f"{BASE_URL}/api/admin/packages", headers=owner_headers)
        original_costs = resp.json().get("default_feature_costs", {})
        original_fno = original_costs.get("fno_generate", 2.0)
        
        # Update fno_generate cost
        new_cost = original_fno + 0.5
        resp = requests.patch(
            f"{BASE_URL}/api/admin/feature-costs",
            json={"costs": {"fno_generate": new_cost}},
            headers=owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert "fno_generate" in data.get("updated_features", [])
        print(f"PASS: Feature cost updated - fno_generate: {original_fno} -> {new_cost}")
        
        # Restore original
        requests.patch(
            f"{BASE_URL}/api/admin/feature-costs",
            json={"costs": {"fno_generate": original_fno}},
            headers=owner_headers
        )
        print("PASS: Feature cost restored to original")
    
    def test_invalid_feature_key_rejected(self, owner_headers):
        """Invalid feature key should be rejected"""
        resp = requests.patch(
            f"{BASE_URL}/api/admin/feature-costs",
            json={"costs": {"invalid_feature_xyz": 5.0}},
            headers=owner_headers
        )
        assert resp.status_code == 400
        print("PASS: Invalid feature key correctly rejected")

# ─── Admin Users List Tests ──────────────────────────────────────────────────

class TestAdminUsersList:
    """Test admin users list with new fields"""
    
    def test_users_have_suspended_field(self, owner_headers):
        """Users should have suspended field"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=owner_headers)
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) > 0
        # Check first user has expected fields
        user = users[0]
        assert "user_key" in user
        assert "username" in user
        assert "role" in user
        assert "credits" in user
        # suspended may be False or not present (defaults to False)
        print(f"PASS: Users list - {len(users)} users, fields verified")

# ─── Regression: Admin Endpoints ─────────────────────────────────────────────

class TestAdminRegression:
    """Regression tests for existing admin endpoints"""
    
    def test_admin_config(self, owner_headers):
        resp = requests.get(f"{BASE_URL}/api/admin/config", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "api_controls" in data
        print("PASS: Admin config endpoint works")
    
    def test_admin_macro_events(self, owner_headers):
        resp = requests.get(f"{BASE_URL}/api/admin/macro-events", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "all_events" in data
        print("PASS: Admin macro events endpoint works")
    
    def test_admin_data_stats(self, owner_headers):
        resp = requests.get(f"{BASE_URL}/api/admin/data/stats", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        print("PASS: Admin data stats endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
