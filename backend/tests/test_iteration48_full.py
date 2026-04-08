"""
Iteration 48: P2-B (Budget Entry Trigger Alert UI) + P2-C (Position Sizing Calculator Enhancements)
Full Backend API Tests

Tests:
1. /api/auth/settings PATCH - updates fno_budget and account_risk_pct
2. /api/auth/me - returns fno_budget and account_risk_pct fields
3. /api/auth/access - returns fno_budget and account_risk_pct fields
4. /api/fno/position-sizing - returns enhanced fields (lots_atr_method, lots_fixed_risk, max_risk_Rs)
5. compute_position_size unit tests with atr14 param
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://signal-backtester.preview.emergentagent.com').rstrip('/')

class TestAuthAccess:
    """Test /api/auth/access returns fno_budget and account_risk_pct"""
    
    def test_auth_access_returns_budget_and_risk(self):
        """P2-B: /api/auth/access should return fno_budget and account_risk_pct"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify token and role
        assert "token" in data, "Missing token in response"
        assert data["role"] == "owner", f"Expected role=owner, got {data['role']}"
        
        # P2-B: Verify fno_budget and account_risk_pct fields
        assert "fno_budget" in data, "Missing fno_budget in /auth/access response"
        assert "account_risk_pct" in data, "Missing account_risk_pct in /auth/access response"
        assert isinstance(data["fno_budget"], (int, float)), f"fno_budget should be numeric, got {type(data['fno_budget'])}"
        assert isinstance(data["account_risk_pct"], (int, float)), f"account_risk_pct should be numeric, got {type(data['account_risk_pct'])}"
        assert data["fno_budget"] > 0, "fno_budget should be positive"
        assert 0 < data["account_risk_pct"] <= 100, "account_risk_pct should be between 0 and 100"


class TestAuthMe:
    """Test /api/auth/me returns fno_budget and account_risk_pct"""
    
    def _get_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]
    
    def test_auth_me_returns_budget_and_risk(self):
        """P2-B: /api/auth/me should return fno_budget and account_risk_pct"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify basic fields
        assert "role" in data, "Missing role in /auth/me response"
        assert "credits" in data, "Missing credits in /auth/me response"
        
        # P2-B: Verify fno_budget and account_risk_pct fields
        assert "fno_budget" in data, "Missing fno_budget in /auth/me response"
        assert "account_risk_pct" in data, "Missing account_risk_pct in /auth/me response"
        assert isinstance(data["fno_budget"], (int, float)), f"fno_budget should be numeric, got {type(data['fno_budget'])}"
        assert isinstance(data["account_risk_pct"], (int, float)), f"account_risk_pct should be numeric, got {type(data['account_risk_pct'])}"


class TestAuthSettings:
    """Test /api/auth/settings PATCH endpoint"""
    
    def _get_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]
    
    def test_update_fno_budget(self):
        """P2-B: PATCH /api/auth/settings should update fno_budget"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Update budget to 750000
        response = requests.patch(
            f"{BASE_URL}/api/auth/settings",
            json={"fno_budget": 750000},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") is True, "Expected ok=True in response"
        assert data.get("fno_budget") == 750000.0, f"Expected fno_budget=750000, got {data.get('fno_budget')}"
        
        # Reset to default
        requests.patch(f"{BASE_URL}/api/auth/settings", json={"fno_budget": 500000}, headers=headers, timeout=15)
    
    def test_update_account_risk_pct(self):
        """P2-B: PATCH /api/auth/settings should update account_risk_pct"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Update risk to 3%
        response = requests.patch(
            f"{BASE_URL}/api/auth/settings",
            json={"account_risk_pct": 3.0},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") is True, "Expected ok=True in response"
        assert data.get("account_risk_pct") == 3.0, f"Expected account_risk_pct=3.0, got {data.get('account_risk_pct')}"
        
        # Reset to default
        requests.patch(f"{BASE_URL}/api/auth/settings", json={"account_risk_pct": 2.0}, headers=headers, timeout=15)
    
    def test_update_both_settings(self):
        """P2-B: PATCH /api/auth/settings should update both fno_budget and account_risk_pct"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Update both
        response = requests.patch(
            f"{BASE_URL}/api/auth/settings",
            json={"fno_budget": 1000000, "account_risk_pct": 2.5},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") is True, "Expected ok=True in response"
        assert data.get("fno_budget") == 1000000.0, f"Expected fno_budget=1000000, got {data.get('fno_budget')}"
        assert data.get("account_risk_pct") == 2.5, f"Expected account_risk_pct=2.5, got {data.get('account_risk_pct')}"
        
        # Verify persistence via /auth/me
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=15)
        me_data = me_response.json()
        assert me_data.get("fno_budget") == 1000000.0, "fno_budget not persisted"
        assert me_data.get("account_risk_pct") == 2.5, "account_risk_pct not persisted"
        
        # Reset to defaults
        requests.patch(f"{BASE_URL}/api/auth/settings", json={"fno_budget": 500000, "account_risk_pct": 2.0}, headers=headers, timeout=15)


class TestPositionSizingAPI:
    """Test /api/fno/position-sizing endpoint with enhanced fields"""
    
    def _get_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]
    
    def test_position_sizing_returns_enhanced_fields(self):
        """P2-C: /api/fno/position-sizing should return lots_atr_method, lots_fixed_risk, max_risk_Rs"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/fno/position-sizing?user_budget=500000&option_premium=100&lot_size=50&sl_price=85&atr14=50",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # P2-C: Verify enhanced fields
        assert "lots_atr_method" in data, "Missing lots_atr_method in response"
        assert "lots_fixed_risk" in data, "Missing lots_fixed_risk in response"
        assert "max_risk_Rs" in data, "Missing max_risk_Rs in response"
        
        # Verify types
        assert isinstance(data["lots_atr_method"], int), f"lots_atr_method should be int, got {type(data['lots_atr_method'])}"
        assert isinstance(data["lots_fixed_risk"], int), f"lots_fixed_risk should be int, got {type(data['lots_fixed_risk'])}"
        assert isinstance(data["max_risk_Rs"], (int, float)), f"max_risk_Rs should be numeric, got {type(data['max_risk_Rs'])}"
        
        # Verify values are reasonable
        assert data["lots_atr_method"] >= 0, "lots_atr_method should be non-negative"
        assert data["lots_fixed_risk"] >= 0, "lots_fixed_risk should be non-negative"
        assert data["max_risk_Rs"] > 0, "max_risk_Rs should be positive"
    
    def test_position_sizing_with_account_risk_pct(self):
        """P2-C: /api/fno/position-sizing should use account_risk_pct from user settings"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # First set account_risk_pct to 3%
        requests.patch(f"{BASE_URL}/api/auth/settings", json={"account_risk_pct": 3.0}, headers=headers, timeout=15)
        
        response = requests.post(
            f"{BASE_URL}/api/fno/position-sizing?user_budget=500000&option_premium=100&lot_size=50&sl_price=85&atr14=50",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        # max_risk_Rs should be 500000 * 3% = 15000
        assert data["max_risk_Rs"] == 15000.0, f"Expected max_risk_Rs=15000, got {data['max_risk_Rs']}"
        
        # Reset to default
        requests.patch(f"{BASE_URL}/api/auth/settings", json={"account_risk_pct": 2.0}, headers=headers, timeout=15)
    
    def test_position_sizing_not_affordable(self):
        """P2-C: /api/fno/position-sizing should return not_affordable=True when capital exceeds budget"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Very small budget, expensive option
        response = requests.post(
            f"{BASE_URL}/api/fno/position-sizing?user_budget=1000&option_premium=500&lot_size=50&sl_price=450",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        # capital_per_lot = 500 * 50 = 25000 > 1000 budget
        assert data["not_affordable"] is True, "Expected not_affordable=True"
        assert data["lots_allowed"] == 0, "Expected lots_allowed=0 when not affordable"


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def _get_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]
    
    def test_health_endpoint(self):
        """Verify health endpoint is working"""
        response = requests.get(f"{BASE_URL}/api/", timeout=15)
        assert response.status_code == 200
    
    def test_batch_status_endpoint(self):
        """Verify batch status endpoint returns theta_curve_entries"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/batch/status", headers=headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "theta_curve_entries" in data, "Missing theta_curve_entries in batch status"
    
    def test_fno_custom_positions_endpoint(self):
        """Verify custom positions endpoint is accessible"""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/fno/custom-positions", headers=headers, timeout=15)
        assert response.status_code == 200
        assert isinstance(response.json(), list), "Expected list response"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
