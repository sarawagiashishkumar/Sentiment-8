"""
Iteration 79 Backend Tests
- CRITICAL: Chunk loading fix verification (React.lazy removed)
- AI Support: POST /api/livehelp/ai-chat with GPT-4o-mini
- AI Support: Auto-ticket creation for bug reports
- Bug fixes: RiskDashboard null, watchlist cooldown, position_service regex
- Performance: Parallel NIFTY+BANKNIFTY generation
- Regression: health, heartbeat, alerts, ice-servers, gzip, x-response-time
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://backend-refactor-p2.preview.emergentagent.com"


class TestHealthAndRegression:
    """Health and regression endpoint tests"""

    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert "checks" in data
        print(f"PASS: Health endpoint healthy, DB connected: {data['checks']['database']['connected']}")

    def test_heartbeat_alive(self):
        """Test /api/heartbeat returns alive"""
        response = requests.get(f"{BASE_URL}/api/heartbeat", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "alive"
        print("PASS: Heartbeat alive")

    def test_x_response_time_header(self):
        """Test X-Response-Time header is present"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        assert response.status_code == 200
        assert "x-response-time" in response.headers or "X-Response-Time" in response.headers
        print(f"PASS: X-Response-Time header present: {response.headers.get('x-response-time', response.headers.get('X-Response-Time'))}")

    def test_ice_servers_endpoint(self):
        """Test /api/livehelp/ice-servers returns STUN servers"""
        response = requests.get(f"{BASE_URL}/api/livehelp/ice-servers", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert "iceServers" in data
        assert len(data["iceServers"]) >= 1
        assert "stun:" in data["iceServers"][0]["urls"]
        print(f"PASS: ICE servers returned: {len(data['iceServers'])} servers")


class TestAuthentication:
    """Authentication tests"""

    def test_owner_login(self):
        """Test owner login with @shish123"""
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
        print(f"PASS: Owner login successful, token: {data['token'][:20]}...")

    def test_user_login(self):
        """Test user login with Manas@2005"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "Manas@2005"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("role") == "user"
        print(f"PASS: User login successful, credits: {data.get('credits')}")


class TestAISupportChat:
    """AI Support Agent tests - GPT-4o-mini integration"""

    @pytest.fixture
    def owner_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")

    def test_ai_chat_basic_question(self, owner_token):
        """Test AI chat responds to basic platform question"""
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={
                "message": "What is the F&O Projections feature?",
                "session_id": "test-ai-79-basic"
            },
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 20  # AI should give meaningful response
        assert data.get("auto_ticket") is False
        print(f"PASS: AI chat responded: {data['reply'][:100]}...")

    def test_ai_chat_auto_ticket_on_bug_report(self, owner_token):
        """Test AI chat creates auto-ticket when user reports a bug"""
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={
                "message": "I found a bug - the portfolio page is not working and shows an error",
                "session_id": "test-ai-79-bug"
            },
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert data.get("auto_ticket") is True  # Should create ticket for bug keywords
        print(f"PASS: AI chat auto-ticket created for bug report: {data['auto_ticket']}")

    def test_ai_chat_no_ticket_for_normal_question(self, owner_token):
        """Test AI chat does NOT create ticket for normal questions"""
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={
                "message": "How do I add a stock to my watchlist?",
                "session_id": "test-ai-79-normal"
            },
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert data.get("auto_ticket") is False
        print(f"PASS: AI chat no ticket for normal question")


class TestAlertRules:
    """Alert rules endpoint tests"""

    @pytest.fixture
    def owner_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")

    def test_alert_rules_list(self, owner_token):
        """Test /api/alerts/rules returns list"""
        response = requests.get(
            f"{BASE_URL}/api/alerts/rules",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        print(f"PASS: Alert rules list returned: {len(data['rules'])} rules")


class TestRiskDashboard:
    """Risk Dashboard endpoint tests - verifies null safety fix"""

    @pytest.fixture
    def owner_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")

    def test_portfolio_risk_endpoint(self, owner_token):
        """Test /api/risk/portfolio-summary works (null safety)"""
        response = requests.get(
            f"{BASE_URL}/api/risk/portfolio-summary",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        # Verify structure exists even if empty
        assert "open_positions" in data
        assert "drawdown" in data
        assert "greeks" in data
        print(f"PASS: Risk dashboard endpoint works, open_positions: {data.get('open_positions')}")


class TestWatchlist:
    """Watchlist endpoint tests - verifies cooldown datetime fix"""

    @pytest.fixture
    def owner_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")

    def test_watchlist_endpoint(self, owner_token):
        """Test /api/watchlist returns items"""
        response = requests.get(
            f"{BASE_URL}/api/watchlist",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        print(f"PASS: Watchlist endpoint works, items: {len(data['items'])}")


class TestParallelFNOGeneration:
    """Verify parallel NIFTY+BANKNIFTY generation code exists"""

    def test_fno_route_has_parallel_code(self):
        """Verify fno.py uses asyncio.wait for parallel generation"""
        fno_path = "/app/backend/routes/fno.py"
        with open(fno_path, "r") as f:
            content = f.read()
        
        # Check for parallel execution pattern
        assert "asyncio.wait" in content or "asyncio.gather" in content
        assert "nifty_task" in content.lower() or "bn_task" in content.lower()
        print("PASS: FNO route has parallel NIFTY+BANKNIFTY code")


class TestPositionServiceRegex:
    """Verify position_service.py uses regex parser"""

    def test_position_service_regex_pattern(self):
        """Verify regex-based underlying extraction"""
        pos_path = "/app/backend/services/position_service.py"
        with open(pos_path, "r") as f:
            content = f.read()
        
        # Check for regex pattern
        assert "re.match" in content or "re.search" in content or "re.compile" in content
        assert r"[A-Z&]+" in content or "underlying" in content.lower()
        print("PASS: Position service uses regex for underlying extraction")


class TestRiskDashboardNullSafety:
    """Verify RiskDashboard.jsx has null safety for equity_curve"""

    def test_risk_dashboard_null_safety(self):
        """Verify equity_curve accessed safely"""
        risk_path = "/app/frontend/src/components/Portfolio/RiskDashboard.jsx"
        with open(risk_path, "r") as f:
            content = f.read()
        
        # Check for null safety pattern
        assert "data?.equity_curve" in content or "equity_curve || []" in content
        print("PASS: RiskDashboard has null safety for equity_curve")


class TestLiveHelpModuleAISupport:
    """Verify LiveHelpModule.jsx has AI Support features"""

    def test_livehelp_has_ai_support_label(self):
        """Verify FAB shows 'AI Support' label"""
        lh_path = "/app/frontend/src/components/Shared/LiveHelpModule.jsx"
        with open(lh_path, "r") as f:
            content = f.read()
        
        assert "AI Support" in content
        assert "Bot" in content  # Bot icon
        assert "livehelp-fab" in content
        print("PASS: LiveHelpModule has AI Support label and Bot icon")

    def test_livehelp_has_mic_button(self):
        """Verify mic button for voice input"""
        lh_path = "/app/frontend/src/components/Shared/LiveHelpModule.jsx"
        with open(lh_path, "r") as f:
            content = f.read()
        
        assert "livehelp-mic" in content
        assert "Mic" in content
        assert "SpeechRecognition" in content or "webkitSpeechRecognition" in content
        print("PASS: LiveHelpModule has mic button with Web Speech API")

    def test_livehelp_has_ai_chat_integration(self):
        """Verify AI chat endpoint integration"""
        lh_path = "/app/frontend/src/components/Shared/LiveHelpModule.jsx"
        with open(lh_path, "r") as f:
            content = f.read()
        
        assert "livehelp/ai-chat" in content
        assert "sendToAI" in content
        print("PASS: LiveHelpModule integrates with AI chat endpoint")


class TestAppJsNoLazyLoading:
    """Verify App.js has no React.lazy (chunk loading fix)"""

    def test_no_react_lazy_imports(self):
        """Verify React.lazy removed from App.js"""
        app_path = "/app/frontend/src/App.js"
        with open(app_path, "r") as f:
            content = f.read()
        
        # Should NOT have React.lazy
        assert "React.lazy" not in content
        assert "lazy(" not in content
        # Should have direct imports
        assert "import { HomeDashboard }" in content or "import {HomeDashboard}" in content
        assert "import { MultibaggerDashboard }" in content or "import {MultibaggerDashboard}" in content
        print("PASS: App.js uses direct imports (no React.lazy)")

    def test_no_suspense_wrapper(self):
        """Verify Suspense wrapper removed"""
        app_path = "/app/frontend/src/App.js"
        with open(app_path, "r") as f:
            content = f.read()
        
        # Should NOT have Suspense wrapping components
        assert "<Suspense" not in content
        print("PASS: App.js has no Suspense wrapper")


class TestReportsDashboard:
    """Reports endpoint tests"""

    @pytest.fixture
    def owner_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10
        )
        return response.json().get("token")

    def test_reports_daily_summary(self, owner_token):
        """Test /api/reports/daily-summary works"""
        response = requests.get(
            f"{BASE_URL}/api/reports/daily-summary",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data or "summary" in data or isinstance(data, dict)
        print(f"PASS: Reports daily-summary endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
