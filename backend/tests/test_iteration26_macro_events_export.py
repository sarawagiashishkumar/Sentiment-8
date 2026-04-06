"""
Iteration 26: Tests for Admin Macro Events toggle UI/API and F&O Export enhancements.
Covers:
  - GET /api/admin/macro-events returns active_events + all_events (15 items)
  - POST /api/admin/macro-events/update toggles single event, reflected in GET
  - POST with invalid key returns 422
  - POST empty events clears all active
  - Regression: health check still OK
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Authenticate as owner user and return token."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
    )
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in response: {data}"
    return token


@pytest.fixture(scope="module")
def owner_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def session(owner_headers):
    s = requests.Session()
    s.headers.update(owner_headers)
    return s


# ── Batch A: GET macro-events ─────────────────────────────────────────────────

class TestMacroEventsGet:
    """GET /api/admin/macro-events validation"""

    def test_get_returns_200(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: GET /api/admin/macro-events → 200")

    def test_response_has_active_events_key(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        assert "active_events" in data, f"Missing active_events key: {data.keys()}"
        assert isinstance(data["active_events"], list), "active_events should be a list"
        print(f"PASS: active_events is list, current: {data['active_events']}")

    def test_response_has_all_events_key(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        assert "all_events" in data, f"Missing all_events key: {data.keys()}"
        assert isinstance(data["all_events"], list), "all_events should be a list"
        print(f"PASS: all_events is list, count: {len(data['all_events'])}")

    def test_all_events_has_15_items(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        count = len(data["all_events"])
        assert count == 15, f"Expected 15 events, got {count}"
        print(f"PASS: all_events has exactly 15 items")

    def test_each_event_has_required_fields(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        required_fields = {"key", "description", "intensity", "active"}
        for ev in data["all_events"]:
            missing = required_fields - ev.keys()
            assert not missing, f"Event missing fields {missing}: {ev}"
        print("PASS: All events have key/description/intensity/active fields")

    def test_response_has_total_active_field(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        assert "total_active" in data, f"Missing total_active: {data.keys()}"
        assert isinstance(data["total_active"], int), "total_active should be int"
        assert data["total_active"] == len(data["active_events"]), \
            f"total_active mismatch: {data['total_active']} vs {len(data['active_events'])}"
        print(f"PASS: total_active = {data['total_active']}")

    def test_rbi_rate_cut_event_exists_in_all_events(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        keys = [ev["key"] for ev in data["all_events"]]
        assert "RBI_RATE_CUT" in keys, f"RBI_RATE_CUT not found in events: {keys}"
        print("PASS: RBI_RATE_CUT event exists in all_events")

    def test_intensity_values_are_valid(self, session):
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        valid_intensities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for ev in data["all_events"]:
            assert ev["intensity"] in valid_intensities, \
                f"Invalid intensity '{ev['intensity']}' for event {ev['key']}"
        print("PASS: All events have valid intensity values")


# ── Batch B: POST toggle macro-events ─────────────────────────────────────────

class TestMacroEventsToggle:
    """POST /api/admin/macro-events/update toggle logic"""

    def test_post_set_rbi_rate_cut_returns_200(self, session):
        resp = session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["RBI_RATE_CUT"]},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert "RBI_RATE_CUT" in data.get("active_events", [])
        print(f"PASS: POST set RBI_RATE_CUT → success, active_events: {data['active_events']}")

    def test_get_reflects_rbi_rate_cut_active(self, session):
        """After POST setting RBI_RATE_CUT, GET should show it as active"""
        # First set it
        session.post(f"{BASE_URL}/api/admin/macro-events/update", json={"events": ["RBI_RATE_CUT"]})
        # Then verify
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        assert "RBI_RATE_CUT" in data["active_events"], \
            f"RBI_RATE_CUT not in active_events after POST: {data['active_events']}"
        # Also verify in all_events
        rbi_event = next((e for e in data["all_events"] if e["key"] == "RBI_RATE_CUT"), None)
        assert rbi_event is not None
        assert rbi_event["active"] is True, f"RBI_RATE_CUT active flag not True in all_events"
        print(f"PASS: GET confirms RBI_RATE_CUT active=True after POST")

    def test_post_deactivate_rbi_rate_cut(self, session):
        """Toggle off: POST with events=[] clears RBI_RATE_CUT"""
        # First activate
        session.post(f"{BASE_URL}/api/admin/macro-events/update", json={"events": ["RBI_RATE_CUT"]})
        # Then deactivate
        resp = session.post(f"{BASE_URL}/api/admin/macro-events/update", json={"events": []})
        assert resp.status_code == 200
        data = resp.json()
        assert "RBI_RATE_CUT" not in data.get("active_events", [])
        print("PASS: POST empty events deactivates RBI_RATE_CUT")

    def test_get_reflects_rbi_rate_cut_inactive_after_clear(self, session):
        """After clearing events, GET should show RBI_RATE_CUT as inactive"""
        session.post(f"{BASE_URL}/api/admin/macro-events/update", json={"events": []})
        resp = session.get(f"{BASE_URL}/api/admin/macro-events")
        data = resp.json()
        assert "RBI_RATE_CUT" not in data["active_events"], \
            f"RBI_RATE_CUT still in active_events: {data['active_events']}"
        rbi_event = next((e for e in data["all_events"] if e["key"] == "RBI_RATE_CUT"), None)
        assert rbi_event is not None
        assert rbi_event["active"] is False, f"RBI_RATE_CUT active flag should be False"
        print("PASS: GET confirms RBI_RATE_CUT active=False after clearing")

    def test_post_invalid_key_returns_422(self, session):
        resp = session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["INVALID_EVENT_KEY"]},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("PASS: POST invalid key → 422")

    def test_post_invalid_key_error_mentions_key(self, session):
        resp = session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["BAD_KEY_XYZ"]},
        )
        data = resp.json()
        detail = str(data.get("detail", ""))
        assert "BAD_KEY_XYZ" in detail or "invalid" in detail.lower(), \
            f"Error detail doesn't mention invalid key: {detail}"
        print(f"PASS: 422 error mentions key: {detail[:80]}")

    def test_post_multiple_valid_events(self, session):
        resp = session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["RBI_RATE_CUT", "CRUDE_FALL"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_active"] == 2
        assert "RBI_RATE_CUT" in data["active_events"]
        assert "CRUDE_FALL" in data["active_events"]
        print("PASS: POST multiple valid events → total_active=2")

    def test_cleanup_reset_to_empty(self, session):
        """Cleanup: reset active events to empty after testing"""
        resp = session.post(f"{BASE_URL}/api/admin/macro-events/update", json={"events": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_active"] == 0
        print("PASS: Cleanup - all events reset to empty")


# ── Batch C: Regression checks ────────────────────────────────────────────────

class TestRegression:
    """Regression checks to ensure existing features still work"""

    def test_backend_reachable(self):
        """Check any known endpoint returns a response (not 5xx)"""
        resp = requests.get(f"{BASE_URL}/api/nse-holidays")
        assert resp.status_code != 500, f"Backend error: {resp.status_code}"
        print(f"PASS: /api/nse-holidays → {resp.status_code} (backend reachable)")

    def test_macro_events_accessible_without_token_returns_401(self):
        """Macro events should be owner-only"""
        resp = requests.get(f"{BASE_URL}/api/admin/macro-events")
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {resp.status_code}"
        print(f"PASS: /api/admin/macro-events without auth → {resp.status_code}")

    def test_post_macro_events_without_auth_returns_401(self):
        resp = requests.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["RBI_RATE_CUT"]},
        )
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {resp.status_code}"
        print(f"PASS: POST macro-events without auth → {resp.status_code}")
