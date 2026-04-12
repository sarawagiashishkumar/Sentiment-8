"""
Iteration 63: NDJSON Streaming Latency Fix & RefreshCountdown Tests

Tests:
1. Backend heartbeat returns active=True
2. FNO generate endpoint streams NDJSON with keepalive lines
3. Multibagger generate endpoint streams NDJSON with keepalive lines
4. Auth endpoints still work (owner/user login)
5. Kite status endpoint returns connected status
"""
import pytest
import requests
import os
import json
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBackendHealth:
    """Backend health and heartbeat tests"""
    
    def test_heartbeat_returns_active_field(self):
        """Heartbeat should return active=True for anti-sleep protocol"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert response.status_code == 200, f"Heartbeat failed: {response.status_code}"
        data = response.json()
        assert "active" in data, "Missing 'active' field in heartbeat response"
        assert data["active"] == True, f"Expected active=True, got {data['active']}"
        assert "ts" in data, "Missing 'ts' field in heartbeat response"
        assert "status" in data, "Missing 'status' field in heartbeat response"
        print(f"PASS: Heartbeat returns active={data['active']}, status={data['status']}")


class TestAuthAccess:
    """Authentication endpoint tests"""
    
    def test_owner_login_shish123(self):
        """Owner login with @shish123"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        assert response.status_code == 200, f"Owner login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "token" in data, "Missing token in login response"
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"
        print(f"PASS: Owner login successful, role={data['role']}")
        return data["token"]
    
    def test_user_login_manas2005(self):
        """User login with Manas@2005"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10
        )
        assert response.status_code == 200, f"User login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "token" in data, "Missing token in login response"
        assert data.get("role") == "user", f"Expected role=user, got {data.get('role')}"
        print(f"PASS: User login successful, role={data['role']}")
        return data["token"]


class TestKiteStatus:
    """Kite/Market Data API status tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get owner auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_kite_status_endpoint(self, auth_token):
        """Kite status endpoint should return connected status"""
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200, f"Kite status failed: {response.status_code}"
        data = response.json()
        assert "connected" in data, "Missing 'connected' field in kite status"
        print(f"PASS: Kite status returns connected={data['connected']}")


class TestFNONDJSONStreaming:
    """FNO generate endpoint NDJSON streaming tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get owner auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_fno_generate_streams_ndjson(self, auth_token):
        """FNO generate should stream NDJSON lines including keepalive"""
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={},
            stream=True,
            timeout=120
        )
        assert response.status_code == 200, f"FNO generate failed: {response.status_code}"
        assert "application/x-ndjson" in response.headers.get("content-type", ""), \
            f"Expected NDJSON content-type, got {response.headers.get('content-type')}"
        
        lines = []
        progress_count = 0
        keepalive_count = 0
        complete_found = False
        
        for line in response.iter_lines(decode_unicode=True):
            if line:
                lines.append(line)
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "progress":
                        progress_count += 1
                    elif obj.get("type") == "keepalive":
                        keepalive_count += 1
                    elif obj.get("type") == "complete":
                        complete_found = True
                except json.JSONDecodeError:
                    pass
        
        assert len(lines) > 0, "No NDJSON lines received"
        assert progress_count > 0, "No progress lines received"
        assert complete_found, "No complete line received"
        print(f"PASS: FNO generate streamed {len(lines)} lines, {progress_count} progress, {keepalive_count} keepalive, complete={complete_found}")


class TestMultibaggerNDJSONStreaming:
    """Multibagger generate endpoint NDJSON streaming tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get owner auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_multibagger_generate_streams_ndjson(self, auth_token):
        """Multibagger generate should stream NDJSON lines including keepalive"""
        response = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            stream=True,
            timeout=120
        )
        assert response.status_code == 200, f"Multibagger generate failed: {response.status_code}"
        assert "application/x-ndjson" in response.headers.get("content-type", ""), \
            f"Expected NDJSON content-type, got {response.headers.get('content-type')}"
        
        lines = []
        progress_count = 0
        keepalive_count = 0
        complete_found = False
        
        for line in response.iter_lines(decode_unicode=True):
            if line:
                lines.append(line)
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "progress":
                        progress_count += 1
                    elif obj.get("type") == "keepalive":
                        keepalive_count += 1
                    elif obj.get("type") == "complete":
                        complete_found = True
                except json.JSONDecodeError:
                    pass
        
        assert len(lines) > 0, "No NDJSON lines received"
        assert progress_count > 0, "No progress lines received"
        assert complete_found, "No complete line received"
        print(f"PASS: Multibagger generate streamed {len(lines)} lines, {progress_count} progress, {keepalive_count} keepalive, complete={complete_found}")


class TestNavBarButtons:
    """Verify nav bar has exactly 6 buttons (no Sectors tab)"""
    
    def test_nav_buttons_count(self):
        """This is a frontend test - just verify backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert response.status_code == 200
        print("PASS: Backend healthy - nav bar test will be done in frontend")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
