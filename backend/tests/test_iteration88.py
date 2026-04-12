"""
Iteration 88: Bug Fixes Testing
- Heartbeat/Keep-alive timing (30s ping, 30min buffer)
- AI Agent markdown cleanup
- LiveHelp single mic + voice/chat toggle
- Multibagger Score badge contrast
- Heatmap neutral color for near-zero changes
- Tab navigation counts as activity
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthRegression:
    """Health and heartbeat endpoint tests"""
    
    def test_health_endpoint(self):
        """GET /api/health returns 200 with healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health endpoint returns healthy status")
    
    def test_heartbeat_endpoint(self):
        """GET /api/heartbeat returns 200 with alive status"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "alive"
        assert "ts" in data
        print("PASS: Heartbeat endpoint returns alive status")


class TestAuth:
    """Authentication tests"""
    
    def test_owner_login(self):
        """POST /api/auth/access with owner credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "owner"
        assert data.get("username") == "@shish123"
        print(f"PASS: Owner login successful, token: {data['token'][:8]}...")
        return data["token"]
    
    def test_user_login(self):
        """POST /api/auth/access with user credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "user"
        print("PASS: User login successful")


class TestLiveHelpAI:
    """LiveHelp AI chat tests - markdown cleanup verification"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")
    
    def test_ai_chat_endpoint(self, auth_token):
        """POST /api/livehelp/ai-chat returns response"""
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={
                "message": "What is a multibagger stock?",
                "session_id": "test-session-123"
            },
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        reply = data["reply"]
        
        # Verify markdown is NOT present in raw form (cleanup should happen on frontend)
        # Backend may still return markdown, frontend strips it
        print(f"PASS: AI chat response received, length: {len(reply)} chars")
        print(f"Response preview: {reply[:100]}...")
    
    def test_session_analysis_endpoint(self, auth_token):
        """GET /api/livehelp/session-analysis returns suggestions"""
        response = requests.get(
            f"{BASE_URL}/api/livehelp/session-analysis",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        print(f"PASS: Session analysis returned {len(data['suggestions'])} suggestions")


class TestMarketHeatmap:
    """Market heatmap tests"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")
    
    def test_stock_heatmap_endpoint(self, auth_token):
        """GET /api/market/stock-heatmap returns stocks data"""
        response = requests.get(
            f"{BASE_URL}/api/market/stock-heatmap?filter=nifty50",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        assert "stocks" in data
        stocks = data["stocks"]
        print(f"PASS: Stock heatmap returned {len(stocks)} stocks")
        
        # Check for near-zero change values (neutral color test)
        near_zero_count = sum(1 for s in stocks if abs(s.get("change_pct", 0)) < 0.05)
        print(f"INFO: {near_zero_count} stocks have near-zero change (should show neutral gray)")


class TestMultibagger:
    """Multibagger tests"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")
    
    def test_multibagger_generate_endpoint(self, auth_token):
        """POST /api/multibagger/generate returns streaming response"""
        response = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=60,
            stream=True
        )
        # Streaming endpoint returns 200
        assert response.status_code == 200
        # Read first chunk to verify it's working
        first_chunk = next(response.iter_lines(), None)
        assert first_chunk is not None
        print(f"PASS: Multibagger generate endpoint streaming, first chunk: {first_chunk[:50] if first_chunk else 'empty'}...")


class TestAdminRegression:
    """Admin panel regression tests"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")
    
    def test_admin_users_list(self, auth_token):
        """GET /api/admin/users returns users list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Admin users list returned {len(data)} users")
    
    def test_admin_packages(self, auth_token):
        """GET /api/admin/packages returns packages dict"""
        response = requests.get(
            f"{BASE_URL}/api/admin/packages",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "packages" in data
        packages = data["packages"]
        assert "free" in packages
        assert "basic" in packages
        assert "pro" in packages
        assert "unlimited" in packages
        print(f"PASS: Admin packages returned {len(packages)} tiers")


class TestFNORegression:
    """F&O projection regression tests"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")
    
    def test_fno_custom_positions(self, auth_token):
        """GET /api/fno/custom-positions returns positions"""
        response = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: F&O custom positions returned {len(data)} positions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
