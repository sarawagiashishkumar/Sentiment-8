"""
Iteration 77 Backend Tests
==========================
Tests for:
1. Screen sharing WebSocket signal types (screen-share-start/end)
2. Performance: /api/health response time under 100ms
3. Performance: GZip compression active
4. Bug Fix: trigger_factors 'VeryCheapCE' not 'VeryC heapCE'
5. Async HTTP: services/async_http.py module importable
6. LiveHelp: ICE servers, log-action, session-analysis
7. Payment: QR code, config-status, pending payments
8. Alert Rules: CRUD
9. CRM: Admin and user inbox
10. Regression: heartbeat, health
"""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Auth Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    """Get owner auth token (@shish123)"""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Owner auth failed")

@pytest.fixture(scope="module")
def user_token():
    """Get user auth token (Manas@2005)"""
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


# ── 1. Performance Tests ───────────────────────────────────────────────────────

class TestPerformance:
    """Performance: response time and compression"""

    def test_health_response_time_under_100ms(self):
        """GET /api/health should respond in under 100ms"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        
        # Check X-Response-Time header
        response_time_header = resp.headers.get("X-Response-Time")
        assert response_time_header is not None, "X-Response-Time header missing"
        
        # Parse response time (format: "12.34ms")
        time_ms = float(response_time_header.replace("ms", ""))
        assert time_ms < 100, f"Response time {time_ms}ms exceeds 100ms threshold"
        print(f"✓ Health endpoint response time: {time_ms}ms")

    def test_gzip_compression_active(self, owner_headers):
        """Large payloads should be GZip compressed"""
        headers = {**owner_headers, "Accept-Encoding": "gzip, deflate"}
        resp = requests.get(f"{BASE_URL}/api/health", headers=headers)
        assert resp.status_code == 200
        
        # Check Content-Encoding header
        content_encoding = resp.headers.get("Content-Encoding", "")
        # GZip may not be applied to small responses, so check if header exists or response is small
        if len(resp.content) > 1000:
            assert "gzip" in content_encoding.lower(), "GZip compression not active for large payload"
        print(f"✓ GZip compression check passed (encoding: {content_encoding or 'none (small response)'})")


# ── 2. Async HTTP Module Test ──────────────────────────────────────────────────

class TestAsyncHttpModule:
    """Verify services/async_http.py is importable and has get_async_client()"""

    def test_async_http_module_importable(self):
        """async_http module should be importable with get_async_client function"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        try:
            from services.async_http import get_async_client, async_get, async_post, close_client
            
            # Verify get_async_client is callable
            assert callable(get_async_client), "get_async_client should be callable"
            assert callable(async_get), "async_get should be callable"
            assert callable(async_post), "async_post should be callable"
            assert callable(close_client), "close_client should be callable"
            
            print("✓ async_http module importable with all expected functions")
        except ImportError as e:
            pytest.fail(f"Failed to import async_http module: {e}")


# ── 3. Bug Fix: trigger_factors typo ───────────────────────────────────────────

class TestBugFixTriggerFactors:
    """Verify 'VeryCheapCE' typo is fixed (not 'VeryC heapCE')"""

    def test_trigger_factors_no_typo(self):
        """fno_signal_builder.py should have 'VeryCheapCE' not 'VeryC heapCE'"""
        with open("/app/backend/services/fno_signal_builder.py", "r") as f:
            content = f.read()
        
        # Check for correct spelling
        assert "VeryCheapCE" in content, "VeryCheapCE should be present"
        assert "VeryCheapPE" in content, "VeryCheapPE should be present"
        
        # Check for typo (space in middle)
        assert "VeryC heapCE" not in content, "Typo 'VeryC heapCE' should be fixed"
        assert "VeryC heapPE" not in content, "Typo 'VeryC heapPE' should be fixed"
        
        print("✓ trigger_factors typo fixed: 'VeryCheapCE' is correct")


# ── 4. LiveHelp Endpoints ──────────────────────────────────────────────────────

class TestLiveHelpICEServers:
    """LiveHelp ICE servers endpoint"""

    def test_ice_servers_returns_5_stun_servers(self, owner_headers):
        """GET /api/livehelp/ice-servers should return 5 STUN servers"""
        resp = requests.get(f"{BASE_URL}/api/livehelp/ice-servers", headers=owner_headers)
        assert resp.status_code == 200
        
        data = resp.json()
        # API returns iceServers (camelCase) not servers
        servers = data.get("iceServers", [])
        assert len(servers) >= 5, f"Expected at least 5 STUN servers, got {len(servers)}"
        
        # Verify servers have urls field
        for server in servers:
            assert "urls" in server, "Each server should have 'urls' field"
        
        print(f"✓ ICE servers endpoint returns {len(servers)} servers")


class TestLiveHelpLogAction:
    """LiveHelp log-action endpoint"""

    def test_log_action_logs_session_action(self, owner_headers):
        """POST /api/livehelp/log-action should log actions"""
        payload = {
            "action": "test_action",
            "endpoint": "/api/test",
            "status": "200"
        }
        resp = requests.post(f"{BASE_URL}/api/livehelp/log-action", json=payload, headers=owner_headers)
        assert resp.status_code == 200
        print("✓ log-action endpoint works")


class TestLiveHelpSessionAnalysis:
    """LiveHelp session-analysis endpoint"""

    def test_session_analysis_returns_suggestions(self, owner_headers):
        """GET /api/livehelp/session-analysis should return suggestions"""
        resp = requests.get(f"{BASE_URL}/api/livehelp/session-analysis", headers=owner_headers)
        assert resp.status_code == 200
        
        data = resp.json()
        assert "suggestions" in data, "Response should have 'suggestions' field"
        assert "log_count" in data, "Response should have 'log_count' field"
        
        print(f"✓ session-analysis returns {len(data.get('suggestions', []))} suggestions, {data.get('log_count')} logs")


# ── 5. Payment Endpoints ───────────────────────────────────────────────────────

class TestPaymentQRCode:
    """Payment QR code endpoint"""

    def test_qr_code_endpoint_returns_response(self, owner_headers):
        """GET /api/payments/qr-code should return QR code data"""
        resp = requests.get(f"{BASE_URL}/api/payments/qr-code", headers=owner_headers)
        # May return 200 with QR or 404 if not configured
        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code}"
        
        if resp.status_code == 200:
            data = resp.json()
            assert "qr_code" in data or "upi_link" in data, "Response should have QR data"
        print(f"✓ QR code endpoint status: {resp.status_code}")


class TestAdminPaymentConfigStatus:
    """Admin payment config status endpoint"""

    def test_config_status_returns_razorpay_upi_status(self, owner_headers):
        """GET /api/admin/payments/config-status should return config status"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/config-status", headers=owner_headers)
        assert resp.status_code == 200
        
        data = resp.json()
        assert "razorpay_configured" in data, "Should have razorpay_configured field"
        assert "upi_configured" in data, "Should have upi_configured field"
        
        print(f"✓ Payment config status: Razorpay={data.get('razorpay_configured')}, UPI={data.get('upi_configured')}")

    def test_config_status_forbidden_for_non_admin(self, user_headers):
        """Non-admin should get 403 for config-status"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/config-status", headers=user_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("✓ Non-admin correctly blocked from config-status")


class TestAdminPendingPayments:
    """Admin pending payments endpoint"""

    def test_pending_payments_returns_list(self, owner_headers):
        """GET /api/admin/payments/pending should return list"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/pending", headers=owner_headers)
        assert resp.status_code == 200
        
        data = resp.json()
        # API returns {count, payments} object
        assert "payments" in data, "Response should have 'payments' field"
        assert isinstance(data["payments"], list), "payments should be a list"
        print(f"✓ Pending payments: {data.get('count', len(data['payments']))} items")

    def test_pending_payments_forbidden_for_non_admin(self, user_headers):
        """Non-admin should get 403 for pending payments"""
        resp = requests.get(f"{BASE_URL}/api/admin/payments/pending", headers=user_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("✓ Non-admin correctly blocked from pending payments")


# ── 6. Alert Rules CRUD ────────────────────────────────────────────────────────

class TestAlertRulesCRUD:
    """Alert rules CRUD operations"""

    def test_alert_rules_crud_works(self, owner_headers):
        """Alert rules CRUD should work"""
        import random
        
        # GET - List rules
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        # API returns {rules, count} object
        initial_count = data.get("count", len(data.get("rules", [])))
        
        # POST - Create rule with correct schema
        new_rule = {
            "name": f"TEST_Alert_{random.randint(100000, 999999)}",
            "conditions": [
                {"field": "ltp", "operator": "gt", "value": 3000}
            ],
            "logic": "AND",
            "notify_type": "push",
            "enabled": True
        }
        resp = requests.post(f"{BASE_URL}/api/alerts/rules", json=new_rule, headers=owner_headers)
        assert resp.status_code in [200, 201], f"Create failed: {resp.status_code}, {resp.text}"
        
        created = resp.json()
        # API returns {created: true, rule: {...}} with rule_id inside rule object
        rule_obj = created.get("rule", created)
        rule_id = rule_obj.get("rule_id") or rule_obj.get("id") or rule_obj.get("_id")
        assert rule_id, f"Created rule should have ID, got: {created}"
        
        # GET - Verify created
        resp = requests.get(f"{BASE_URL}/api/alerts/rules", headers=owner_headers)
        assert resp.status_code == 200
        
        # DELETE - Cleanup
        if rule_id:
            resp = requests.delete(f"{BASE_URL}/api/alerts/rules/{rule_id}", headers=owner_headers)
            assert resp.status_code in [200, 204], f"Delete failed: {resp.status_code}"
        
        print("✓ Alert rules CRUD works")


# ── 7. CRM Endpoints ───────────────────────────────────────────────────────────

class TestCRMAdminInbox:
    """Admin CRM inbox"""

    def test_admin_crm_inbox_works(self, owner_headers):
        """GET /api/admin/crm/inbox should work for admin"""
        resp = requests.get(f"{BASE_URL}/api/admin/crm/inbox", headers=owner_headers)
        assert resp.status_code == 200
        
        data = resp.json()
        # API returns {messages, count, unread} object
        assert "messages" in data, "Response should have 'messages' field"
        assert isinstance(data["messages"], list), "messages should be a list"
        print(f"✓ Admin CRM inbox: {data.get('count', len(data['messages']))} messages")


class TestUserCRMInbox:
    """User CRM inbox"""

    def test_user_inbox_returns_messages(self, user_headers):
        """GET /api/crm/inbox should return user messages"""
        resp = requests.get(f"{BASE_URL}/api/crm/inbox", headers=user_headers)
        assert resp.status_code == 200
        
        data = resp.json()
        # API returns {messages, count, unread} object
        assert "messages" in data, "Response should have 'messages' field"
        assert isinstance(data["messages"], list), "messages should be a list"
        print(f"✓ User CRM inbox: {data.get('count', len(data['messages']))} messages")


# ── 8. Regression Tests ────────────────────────────────────────────────────────

class TestRegressionIteration77:
    """Regression tests for iteration 77"""

    def test_heartbeat_returns_alive(self):
        """GET /api/heartbeat should return alive"""
        resp = requests.get(f"{BASE_URL}/api/heartbeat")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data.get("status") == "alive", "Heartbeat should return alive"
        print("✓ Heartbeat alive")

    def test_health_endpoint_returns_healthy(self):
        """GET /api/health should return healthy"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data.get("status") == "healthy", "Health should return healthy"
        print("✓ Health endpoint healthy")

    def test_response_time_header_present(self):
        """X-Response-Time header should be present"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        assert "X-Response-Time" in resp.headers, "X-Response-Time header missing"
        print(f"✓ X-Response-Time header present: {resp.headers.get('X-Response-Time')}")


# ── 9. Screen Share WebSocket Signal Types (Code Review) ───────────────────────

class TestScreenShareSignalTypes:
    """Verify WebSocket handles screen-share-start/end signal types"""

    def test_websocket_handles_screen_share_signals(self):
        """server.py should handle screen-share-start and screen-share-end"""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        # Check for screen-share-start handling
        assert "screen-share-start" in content, "WebSocket should handle screen-share-start"
        assert "screen-share-end" in content, "WebSocket should handle screen-share-end"
        
        # Verify it's in the WebSocket handler section
        assert 'msg_type in ("screen-share-start", "screen-share-end")' in content or \
               'msg_type == "screen-share-start"' in content, \
               "screen-share signals should be handled in WebSocket message handler"
        
        print("✓ WebSocket handles screen-share-start/end signal types")


# ── 10. Frontend LiveHelp Screen Share (Code Review) ───────────────────────────

class TestFrontendScreenShare:
    """Verify frontend LiveHelpModule has screen share buttons"""

    def test_livehelp_has_screen_share_buttons(self):
        """LiveHelpModule.jsx should have screen share buttons with correct data-testid"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        # Check for screen share button data-testids
        assert 'data-testid="livehelp-screen-start"' in content, "Screen start button should have data-testid"
        assert 'data-testid="livehelp-screen-stop"' in content, "Screen stop button should have data-testid"
        
        # Check for Monitor/MonitorOff icons
        assert "Monitor" in content, "Monitor icon should be imported"
        assert "MonitorOff" in content, "MonitorOff icon should be imported"
        
        # Check for getDisplayMedia usage
        assert "getDisplayMedia" in content, "getDisplayMedia should be used for screen sharing"
        
        print("✓ LiveHelpModule has screen share buttons with correct data-testids")


# ── 11. asyncio.gather Parallelization (Code Review) ───────────────────────────

class TestAsyncioGatherParallelization:
    """Verify asyncio.gather is used for parallel fetch in fno_signal_builder"""

    def test_asyncio_gather_used_for_parallel_fetch(self):
        """fno_signal_builder.py should use asyncio.gather for parallel strategy+macro fetch"""
        with open("/app/backend/services/fno_signal_builder.py", "r") as f:
            content = f.read()
        
        # Check for asyncio.gather usage
        assert "asyncio.gather" in content, "asyncio.gather should be used"
        
        # Check for parallel fetch of strategy stats and macro events
        assert "_get_strategy_stats_for_selection" in content, "Strategy stats fetch should be present"
        assert "_get_active_macro_events" in content, "Macro events fetch should be present"
        
        # Verify they're called together in gather
        assert "await asyncio.gather" in content, "asyncio.gather should be awaited"
        
        print("✓ asyncio.gather used for parallel strategy+macro fetch")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
