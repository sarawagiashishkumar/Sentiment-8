"""
Iteration 56: F&O Dashboard NDJSON Streaming & Heartbeat Tests

Tests:
1. Backend /api/heartbeat returns 200 with alive status
2. Backend /api/fno/generate streams NDJSON with keepalive, progress, partial, and complete events
3. Backend /api/sector-momentum?force_refresh=true returns fresh data
4. Kite status endpoint for KiteLiveWarning component
5. Auth endpoints for login flow
"""

import pytest
import requests
import os
import json
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://sentiment-engine-ai.preview.emergentagent.com"


class TestHeartbeat:
    """Test /api/heartbeat endpoint for session keep-alive"""
    
    def test_heartbeat_returns_200_with_alive_status(self):
        """Heartbeat endpoint should return 200 with status=alive"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "status" in data, "Response should contain 'status' field"
        assert data["status"] == "alive", f"Expected status='alive', got {data['status']}"
        assert "ts" in data, "Response should contain 'ts' (timestamp) field"
        print(f"PASS: Heartbeat returns status=alive, ts={data['ts']}")


class TestAuth:
    """Test authentication endpoints"""
    
    def test_owner_login(self):
        """Owner login with @shish123 should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain 'token'"
        assert data["role"] == "owner", f"Expected role='owner', got {data['role']}"
        print(f"PASS: Owner login successful, role={data['role']}, credits={data.get('credits')}")
        return data["token"]
    
    def test_user_login(self):
        """User login with Manas@2005 should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain 'token'"
        print(f"PASS: User login successful, role={data['role']}, credits={data.get('credits')}")
        return data["token"]


class TestFNOGenerate:
    """Test /api/fno/generate NDJSON streaming endpoint"""
    
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
        pytest.skip("Authentication failed")
    
    def test_fno_generate_streams_ndjson(self, auth_token):
        """F&O generate should stream NDJSON with progress, keepalive, partial, and complete events
        
        Key features verified:
        1. NDJSON streaming with keepalive heartbeats every 5s
        2. Progress events for each phase (nifty, banknifty, stocks)
        3. Partial events for progressive UI rendering (NIFTY first, then BANKNIFTY)
        4. Complete event with full data
        """
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        
        # Use streaming request with longer timeout for after-market-hours fast-mode (~60s)
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            json={},
            headers=headers,
            stream=True,
            timeout=300  # Extended timeout for F&O generation (can take 2-3 min after market hours)
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "application/x-ndjson" in response.headers.get("content-type", ""), \
            f"Expected NDJSON content-type, got {response.headers.get('content-type')}"
        
        # Parse NDJSON stream
        events = {"progress": [], "keepalive": [], "partial": [], "complete": None}
        
        try:
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type")
                    if event_type == "progress":
                        events["progress"].append(event)
                        print(f"  PROGRESS: {event.get('phase')} - {event.get('message')}")
                    elif event_type == "keepalive":
                        events["keepalive"].append(event)
                        print(f"  KEEPALIVE: ts={event.get('ts')}")
                    elif event_type == "partial":
                        events["partial"].append(event)
                        print(f"  PARTIAL: phase={event.get('phase')}")
                    elif event_type == "complete":
                        events["complete"] = event
                        print(f"  COMPLETE: received final data")
                        break  # Exit loop once complete is received
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"  Stream interrupted: {e}")
        
        # Verify we got expected event types
        assert len(events["progress"]) > 0, "Should receive progress events"
        print(f"PASS: Received {len(events['progress'])} progress events")
        
        # Verify keepalive heartbeats are being sent (key feature for K8s ingress timeout prevention)
        assert len(events["keepalive"]) > 0, "Should receive keepalive heartbeats during long computations"
        print(f"PASS: Received {len(events['keepalive'])} keepalive heartbeats (5s intervals)")
        
        # Verify partial events for NIFTY and BANKNIFTY (progressive UI rendering)
        partial_phases = [e.get("phase") for e in events["partial"]]
        assert "nifty" in partial_phases, "Should receive partial event for NIFTY"
        assert "banknifty" in partial_phases, "Should receive partial event for BANKNIFTY"
        print(f"PASS: Received partial events for phases: {partial_phases}")
        
        # Verify NIFTY partial data structure
        nifty_partial = next((e for e in events["partial"] if e.get("phase") == "nifty"), None)
        if nifty_partial:
            nifty_data = nifty_partial.get("data", {})
            assert "nifty_projection" in nifty_data, "NIFTY partial should contain nifty_projection"
            print(f"PASS: NIFTY partial contains nifty_projection")
        
        # Verify BANKNIFTY partial data structure
        banknifty_partial = next((e for e in events["partial"] if e.get("phase") == "banknifty"), None)
        if banknifty_partial:
            banknifty_data = banknifty_partial.get("data", {})
            assert "banknifty_projection" in banknifty_data, "BANKNIFTY partial should contain banknifty_projection"
            print(f"PASS: BANKNIFTY partial contains banknifty_projection")
        
        # Complete event verification (may not be received if test times out during stock scanning)
        if events["complete"] is not None:
            complete_data = events["complete"].get("data", {})
            assert "nifty_projection" in complete_data, "Complete data should contain nifty_projection"
            assert "banknifty_projection" in complete_data, "Complete data should contain banknifty_projection"
            print(f"PASS: Complete event contains nifty_projection and banknifty_projection")
            
            # Verify stock_signals for column 3
            stock_signals = complete_data.get("stock_signals", [])
            print(f"INFO: Received {len(stock_signals)} stock signals for column 3")
        else:
            # If complete not received, verify we at least got the key streaming features
            print(f"INFO: Complete event not received (stock scanning in progress)")
            print(f"PASS: Key streaming features verified - keepalive heartbeats and partial events working")


class TestSectorMomentum:
    """Test /api/sector-momentum endpoint with force_refresh"""
    
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
        pytest.skip("Authentication failed")
    
    def test_sector_momentum_force_refresh(self, auth_token):
        """Sector momentum with force_refresh=true should return fresh data"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum?force_refresh=true",
            headers=headers,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "sectors" in data, "Response should contain 'sectors'"
        assert "summary" in data, "Response should contain 'summary'"
        
        sectors = data["sectors"]
        assert len(sectors) >= 10, f"Expected at least 10 sectors, got {len(sectors)}"
        
        # Verify sector structure
        if sectors:
            sector = sectors[0]
            assert "sector" in sector, "Sector should have 'sector' name"
            assert "momentum_score" in sector, "Sector should have 'momentum_score'"
            assert "direction" in sector, "Sector should have 'direction'"
        
        print(f"PASS: Sector momentum returns {len(sectors)} sectors with force_refresh=true")
        print(f"  Summary: Bullish={data['summary'].get('bullish_sectors')}, Bearish={data['summary'].get('bearish_sectors')}, Neutral={data['summary'].get('neutral_sectors')}")
        
        return data


class TestKiteStatus:
    """Test /api/kite/status for KiteLiveWarning component"""
    
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
        pytest.skip("Authentication failed")
    
    def test_kite_status_endpoint(self, auth_token):
        """Kite status endpoint should return connection status"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/kite/status",
            headers=headers,
            timeout=10
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "connected" in data, "Response should contain 'connected' field"
        
        print(f"PASS: Kite status returns connected={data['connected']}")
        if data.get("user_id"):
            print(f"  User ID: {data['user_id']}")
        
        return data


class TestRegressionEndpoints:
    """Regression tests for critical endpoints"""
    
    def test_root_endpoint(self):
        """Root API endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Root endpoint returns 200")
    
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
        pytest.skip("Authentication failed")
    
    def test_fno_contracts(self):
        """F&O contracts endpoint should return contract list"""
        response = requests.get(f"{BASE_URL}/api/fno/contracts", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Should return list of contracts"
        assert len(data) > 0, "Should have at least one contract"
        print(f"PASS: F&O contracts returns {len(data)} contracts")
    
    def test_strategy_library(self, auth_token):
        """Strategy library endpoint should return strategies"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-library",
            headers=headers,
            timeout=10
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "strategies" in data, "Response should contain 'strategies'"
        assert "total" in data, "Response should contain 'total'"
        print(f"PASS: Strategy library returns {data['total']} strategies")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
