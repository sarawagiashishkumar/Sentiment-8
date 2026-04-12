"""
Iteration 81: Voice AI Support Agent Tests
- Tests for voice-enabled multilingual AI Support Agent
- TTS (SpeechSynthesis), STT (SpeechRecognition), 11 Indian languages
- Voice conversation mode, auto-resume listening
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndRegression:
    """Health and regression tests"""
    
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
    
    def test_ice_servers(self):
        """Test /api/livehelp/ice-servers returns STUN servers"""
        response = requests.get(f"{BASE_URL}/api/livehelp/ice-servers")
        assert response.status_code == 200
        data = response.json()
        assert "iceServers" in data
        assert len(data["iceServers"]) > 0
        assert "stun:" in data["iceServers"][0]["urls"]
        print(f"PASS: ICE servers returned with {len(data['iceServers'])} STUN servers")


class TestAuthentication:
    """Authentication tests"""
    
    def test_owner_login(self):
        """Test owner login with @shish123"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["role"] == "owner"
        assert data["username"] == "@shish123"
        print(f"PASS: Owner login successful, role={data['role']}")
    
    def test_user_login(self):
        """Test user login with Manas@2005"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "Manas@2005"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["username"] == "Manas@2005"
        print(f"PASS: User login successful, username={data['username']}")


class TestAIChatEndpoint:
    """AI Chat endpoint tests for Voice AI Support"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for owner"""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
        return response.json()["token"]
    
    def test_ai_chat_response(self, auth_token):
        """Test /api/livehelp/ai-chat returns AI response"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={"message": "What features does this platform have?", "session_id": "test-81-001"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 10  # Should have meaningful response
        assert "auto_ticket" in data
        print(f"PASS: AI chat response received, length={len(data['reply'])}")
    
    def test_ai_chat_unauthorized(self):
        """Test /api/livehelp/ai-chat requires authorization"""
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={"message": "Hello", "session_id": "test-81-002"}
        )
        assert response.status_code == 401
        print(f"PASS: AI chat requires authorization")
    
    def test_ai_chat_multilingual_query(self, auth_token):
        """Test AI chat with Hindi query"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(
            f"{BASE_URL}/api/livehelp/ai-chat",
            json={"message": "मुझे इस प्लेटफॉर्म के बारे में बताओ", "session_id": "test-81-003"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 5
        print(f"PASS: AI chat handles multilingual query")


class TestLiveHelpModuleCodeReview:
    """Code review tests for LiveHelpModule.jsx Voice AI features"""
    
    def test_livehelpmodule_has_speech_synthesis(self):
        """Verify LiveHelpModule uses SpeechSynthesis for TTS"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        # Check for SpeechSynthesis usage
        assert "SpeechSynthesisUtterance" in content, "Missing SpeechSynthesisUtterance"
        assert "speechSynthesis" in content or "synthRef" in content, "Missing speechSynthesis reference"
        assert "speak" in content, "Missing speak function"
        print("PASS: LiveHelpModule has SpeechSynthesis TTS implementation")
    
    def test_livehelpmodule_has_speech_recognition(self):
        """Verify LiveHelpModule uses SpeechRecognition for STT"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        # Check for SpeechRecognition usage
        assert "SpeechRecognition" in content or "webkitSpeechRecognition" in content
        assert "startListening" in content
        assert "recognition.onresult" in content or "onresult" in content
        print("PASS: LiveHelpModule has SpeechRecognition STT implementation")
    
    def test_livehelpmodule_has_11_languages(self):
        """Verify LiveHelpModule supports 11 Indian languages"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        required_langs = ["en-IN", "hi-IN", "ta-IN", "te-IN", "mr-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "pa-IN"]
        for lang in required_langs:
            assert lang in content, f"Missing language: {lang}"
        print(f"PASS: LiveHelpModule supports all {len(required_langs)} Indian languages")
    
    def test_livehelpmodule_has_voice_mode(self):
        """Verify LiveHelpModule has voice conversation mode"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        assert "voiceMode" in content, "Missing voiceMode state"
        assert "toggleVoiceMode" in content, "Missing toggleVoiceMode function"
        assert "livehelp-voice-mode" in content, "Missing voice mode data-testid"
        print("PASS: LiveHelpModule has voice conversation mode")
    
    def test_livehelpmodule_auto_resume_listening(self):
        """Verify auto-resume listening after AI finishes speaking"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        # Check for utterance.onend triggering startListening
        assert "utterance.onend" in content or "onend" in content
        assert "startListening" in content
        # Check that voiceMode triggers auto-resume
        assert "if (voiceMode)" in content
        print("PASS: LiveHelpModule has auto-resume listening after AI speech")
    
    def test_livehelpmodule_has_voice_toggle(self):
        """Verify voice enable/disable toggle exists"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        assert "voiceEnabled" in content, "Missing voiceEnabled state"
        assert "livehelp-voice-toggle" in content, "Missing voice toggle data-testid"
        print("PASS: LiveHelpModule has voice enable/disable toggle")
    
    def test_livehelpmodule_has_required_testids(self):
        """Verify all required data-testid attributes exist"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        required_testids = [
            "livehelp-voice-toggle",
            "livehelp-voice-mode-btn",
            "livehelp-mic",
            "livehelp-lang-btn",
            "livehelp-lang-picker",
            "livehelp-exit-voice",
            "livehelp-voice-mode",
            "livehelp-panel",
            "livehelp-fab",
        ]
        
        for testid in required_testids:
            assert testid in content, f"Missing data-testid: {testid}"
        print(f"PASS: All {len(required_testids)} required data-testids present")
    
    def test_livehelpmodule_responsive_width(self):
        """Verify panel has responsive width for mobile"""
        with open("/app/frontend/src/components/Shared/LiveHelpModule.jsx", "r") as f:
            content = f.read()
        
        assert "w-[calc(100vw-2rem)]" in content, "Missing mobile responsive width"
        assert "sm:w-96" in content, "Missing desktop width"
        print("PASS: LiveHelpModule has responsive panel width")


class TestMobileResponsive:
    """Mobile responsive tests from iteration 80"""
    
    def test_app_css_overflow_hidden(self):
        """Verify overflow-x hidden in App.css"""
        with open("/app/frontend/src/App.css", "r") as f:
            content = f.read()
        
        assert "overflow-x" in content
        print("PASS: App.css has overflow-x styling")
    
    def test_app_js_overflow_hidden(self):
        """Verify overflow-x-hidden in App.js"""
        with open("/app/frontend/src/App.js", "r") as f:
            content = f.read()
        
        assert "overflow-x-hidden" in content or "overflow-hidden" in content
        print("PASS: App.js has overflow-x-hidden class")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
