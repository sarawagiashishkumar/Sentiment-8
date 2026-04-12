"""
Iteration 80 Tests: Mobile Responsive Fixes + Permissions Panel
Tests for:
1. Backend health and regression endpoints
2. Admin packages API (GET /api/admin/packages)
3. User permissions API (GET/PATCH /api/admin/users/{ref}/permissions)
4. AI chat endpoint
5. Alert rules CRUD
6. GZip and X-Response-Time headers
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndRegression:
    """Health and regression endpoint tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"]["connected"] == True
        print(f"PASS: Health endpoint healthy, DB connected")
    
    def test_heartbeat_alive(self):
        """Test /api/heartbeat returns alive"""
        response = requests.get(f"{BASE_URL}/api/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        print(f"PASS: Heartbeat alive")
    
    def test_x_response_time_header(self):
        """Test X-Response-Time header is present"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert "x-response-time" in response.headers
        print(f"PASS: X-Response-Time header present: {response.headers['x-response-time']}")


class TestAuthentication:
    """Authentication tests"""
    
    def test_owner_login(self):
        """Test owner login with @shish123"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["role"] == "owner"
        print(f"PASS: Owner login successful")
    
    def test_user_login(self):
        """Test user login with Manas@2005"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["role"] == "user"
        print(f"PASS: User login successful")


class TestAdminPackages:
    """Admin packages API tests"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json()["token"]
    
    def test_get_packages(self, owner_token):
        """Test GET /api/admin/packages returns packages with default_feature_costs and default_usage_limits"""
        response = requests.get(
            f"{BASE_URL}/api/admin/packages",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify packages structure
        assert "packages" in data
        packages = data["packages"]
        assert "free" in packages
        assert "basic" in packages
        assert "pro" in packages
        assert "unlimited" in packages
        
        # Verify each package has required fields
        for key, pkg in packages.items():
            assert "label" in pkg
            assert "credits" in pkg
            assert "limits" in pkg
        
        # Verify default_feature_costs
        assert "default_feature_costs" in data
        costs = data["default_feature_costs"]
        assert "fno_generate" in costs
        assert "multibagger_generate" in costs
        
        # Verify default_usage_limits
        assert "default_usage_limits" in data
        limits = data["default_usage_limits"]
        assert "fno_generate_daily" in limits
        assert "alert_rules_total" in limits
        
        print(f"PASS: Packages API returns {len(packages)} packages with costs and limits")
    
    def test_packages_unauthorized(self):
        """Test packages endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/admin/packages")
        assert response.status_code == 401
        print(f"PASS: Packages endpoint requires authorization")


class TestUserPermissions:
    """User permissions API tests"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json()["token"]
    
    @pytest.fixture
    def user_key(self, owner_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        users = response.json()
        # Find Manas@2005 user
        for user in users:
            if user["username"] == "Manas@2005":
                return user["user_key"]
        return users[0]["user_key"] if users else None
    
    def test_get_user_permissions(self, owner_token, user_key):
        """Test GET /api/admin/users/{ref}/permissions returns full permission object"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/{user_key}/permissions",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "user_key" in data
        assert "username" in data
        assert "package" in data
        assert "feature_costs" in data
        assert "usage_limits" in data
        assert "feature_restrictions" in data
        assert "current_usage" in data
        assert "suspended" in data
        
        print(f"PASS: User permissions returned for {data['username']}")
    
    def test_patch_user_permissions(self, owner_token, user_key):
        """Test PATCH /api/admin/users/{ref}/permissions updates all permission fields"""
        # First get current permissions
        get_response = requests.get(
            f"{BASE_URL}/api/admin/users/{user_key}/permissions",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        original = get_response.json()
        
        # Update permissions
        patch_response = requests.patch(
            f"{BASE_URL}/api/admin/users/{user_key}/permissions",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "package": "pro",
                "usage_limits": {"fno_generate_daily": 30},
                "feature_costs": {"fno_generate": 1.0},
                "feature_restrictions": []
            }
        )
        assert patch_response.status_code == 200
        patch_data = patch_response.json()
        assert patch_data["updated"] == True
        
        # Verify changes persisted
        verify_response = requests.get(
            f"{BASE_URL}/api/admin/users/{user_key}/permissions",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        verify_data = verify_response.json()
        assert verify_data["package"] == "pro"
        assert verify_data["usage_limits"]["fno_generate_daily"] == 30
        assert verify_data["feature_costs"]["fno_generate"] == 1.0
        
        # Restore original package
        requests.patch(
            f"{BASE_URL}/api/admin/users/{user_key}/permissions",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"package": original.get("package", "free")}
        )
        
        print(f"PASS: PATCH permissions updates all fields correctly")


class TestAIChat:
    """AI Support chat tests"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json()["token"]
    
    def test_ai_chat_response(self, owner_token):
        """Test /api/livehelp/ai-chat returns AI response"""
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"message": "What is options trading?"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 20  # Should have meaningful response
        print(f"PASS: AI chat responded with {len(data['reply'])} chars")


class TestAlertRules:
    """Alert rules CRUD tests"""
    
    @pytest.fixture
    def owner_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json()["token"]
    
    def test_get_alert_rules(self, owner_token):
        """Test GET /api/alerts/rules returns rules list"""
        response = requests.get(
            f"{BASE_URL}/api/alerts/rules",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        print(f"PASS: Alert rules returned {len(data['rules'])} rules")


class TestFrontendCodeReview:
    """Code review tests for mobile responsive fixes"""
    
    def test_app_css_scrollbar_hide(self):
        """Verify scrollbar-hide CSS utility exists"""
        with open("/app/frontend/src/App.css", "r") as f:
            css = f.read()
        assert ".scrollbar-hide::-webkit-scrollbar" in css
        assert "scrollbar-width: none" in css
        print("PASS: scrollbar-hide CSS utility present")
    
    def test_app_css_overflow_hidden(self):
        """Verify html/body/root have overflow-x hidden"""
        with open("/app/frontend/src/App.css", "r") as f:
            css = f.read()
        assert "overflow-x: hidden" in css
        assert "html, body, #root" in css
        print("PASS: html/body/root overflow-x hidden in CSS")
    
    def test_app_js_overflow_hidden(self):
        """Verify main element has overflow-x-hidden class"""
        with open("/app/frontend/src/App.js", "r") as f:
            js = f.read()
        assert "overflow-x-hidden" in js
        print("PASS: App.js main has overflow-x-hidden")
    
    def test_appsidebar_scrollable(self):
        """Verify AppSidebar nav is horizontally scrollable"""
        with open("/app/frontend/src/components/Layout/AppSidebar.jsx", "r") as f:
            jsx = f.read()
        assert "overflow-x-auto" in jsx
        assert "scrollbar-hide" in jsx
        assert "min-w-max" in jsx
        print("PASS: AppSidebar nav is horizontally scrollable with scrollbar-hide")
    
    def test_subtabs_scrollable(self):
        """Verify SubTabs is horizontally scrollable"""
        with open("/app/frontend/src/components/Layout/SubTabs.jsx", "r") as f:
            jsx = f.read()
        assert "overflow-x-auto" in jsx
        assert "scrollbar-hide" in jsx
        assert "min-w-max" in jsx
        assert "whitespace-nowrap" in jsx
        print("PASS: SubTabs is horizontally scrollable with scrollbar-hide")
    
    def test_permissions_panel_data_testids(self):
        """Verify AdminPermissionsPanel has required data-testids"""
        with open("/app/frontend/src/components/Admin/AdminCrmPanel.jsx", "r") as f:
            jsx = f.read()
        
        required_testids = [
            "admin-permissions-panel",
            "perm-user-",
            "perm-edit-toggle",
            "perm-save-all",
            "perm-package-select",
            "limit-",
            "cost-",
            "restrict-",
            "package-card-"
        ]
        
        for testid in required_testids:
            assert testid in jsx, f"Missing data-testid: {testid}"
        
        print("PASS: AdminPermissionsPanel has all required data-testids")
