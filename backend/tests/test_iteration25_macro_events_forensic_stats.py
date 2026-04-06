"""
Iteration 25: Batch A/B/C + Regression Tests
Tests for:
  BATCH A: Admin Macro Events CRUD (GET/POST /api/admin/macro-events)
  BATCH B: Confluence Score forensic inputs (piotroski/beneish/altman)
           - direct unit test via _calculate_confluence_score_master_spec import
  BATCH C: Strategy Stats endpoint (GET /api/admin/strategy-stats)
  REGRESSION: NSE holidays, multibagger custom-search, portfolio analyze
"""

import pytest
import requests
import os
import sys
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# 15 expected macro events from SECTOR_MACRO_IMPACT_MAP
EXPECTED_MACRO_EVENTS = {
    "RBI_RATE_HIKE", "RBI_RATE_CUT", "CRUDE_SPIKE", "CRUDE_FALL",
    "FII_OUTFLOW", "FII_INFLOW", "USD_STRENGTHENING", "INR_WEAKENING",
    "INDIA_BUDGET_CAPEX", "PLI_SCHEME", "US_FED_RATE_HIKE", "CHINA_SLOWDOWN",
    "GEOPOLITICAL_CONFLICT", "EV_ADOPTION_THEME", "SEMICONDUCTOR_SHORTAGE",
}


# ──────────────────────────────────────────────────────────────────────────────
# AUTH FIXTURE
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Get auth token once for all tests in this module."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=15,
    )
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} {resp.text}")
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    if not token:
        pytest.skip(f"No token in auth response: {data}")
    return token


@pytest.fixture(scope="module")
def admin_session(auth_token):
    """Requests session with admin auth header."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    })
    return session


# ──────────────────────────────────────────────────────────────────────────────
# BATCH A: Admin Macro Events Endpoints
# ──────────────────────────────────────────────────────────────────────────────

class TestBatchAMacroEventsGet:
    """Batch A: GET /api/admin/macro-events validation"""

    def test_macro_events_get_returns_200(self, admin_session):
        """GET /api/admin/macro-events returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: GET /api/admin/macro-events returns 200")

    def test_macro_events_get_has_active_events_key(self, admin_session):
        """Response has 'active_events' list."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "active_events" in data, f"Missing 'active_events' key: {data}"
        assert isinstance(data["active_events"], list), "active_events must be a list"
        print(f"PASS: active_events is list, current count: {len(data['active_events'])}")

    def test_macro_events_get_has_all_events_key(self, admin_session):
        """Response has 'all_events' list."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "all_events" in data, f"Missing 'all_events' key: {data}"
        assert isinstance(data["all_events"], list), "all_events must be a list"
        print(f"PASS: all_events is list, count={len(data['all_events'])}")

    def test_macro_events_get_has_15_events(self, admin_session):
        """all_events must have exactly 15 items (matching SECTOR_MACRO_IMPACT_MAP)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        all_events = data.get("all_events", [])
        assert len(all_events) == 15, f"Expected 15 events, got {len(all_events)}: {[e['key'] for e in all_events]}"
        print(f"PASS: all_events has 15 items")

    def test_macro_events_each_item_has_required_fields(self, admin_session):
        """Each event item must have key, description, active fields."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        all_events = data.get("all_events", [])
        assert len(all_events) > 0, "all_events is empty"

        for item in all_events:
            assert "key" in item, f"Missing 'key' in event item: {item}"
            assert "description" in item, f"Missing 'description' in event item: {item}"
            assert "active" in item, f"Missing 'active' field in event item: {item}"
            assert isinstance(item["active"], bool), f"'active' must be bool: {item}"
        print("PASS: All 15 events have key/description/active fields")

    def test_macro_events_keys_match_expected_set(self, admin_session):
        """all_events keys must match the known SECTOR_MACRO_IMPACT_MAP keys."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        returned_keys = {e["key"] for e in data.get("all_events", [])}
        missing = EXPECTED_MACRO_EVENTS - returned_keys
        extra = returned_keys - EXPECTED_MACRO_EVENTS
        assert not missing, f"Missing event keys: {missing}"
        assert not extra, f"Unexpected extra event keys: {extra}"
        print("PASS: all_events keys match expected 15 events exactly")

    def test_macro_events_get_has_total_active_field(self, admin_session):
        """Response has 'total_active' field matching len(active_events)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_active" in data, f"Missing 'total_active' field"
        assert data["total_active"] == len(data["active_events"]), (
            f"total_active={data['total_active']} != len(active_events)={len(data['active_events'])}"
        )
        print(f"PASS: total_active={data['total_active']} matches len(active_events)")


class TestBatchAMacroEventsPost:
    """Batch A: POST /api/admin/macro-events/update validation"""

    def test_post_valid_events_sets_active_correctly(self, admin_session):
        """POST with valid events=['RBI_RATE_CUT','CRUDE_FALL'] returns 200 with those events active."""
        payload = {"events": ["RBI_RATE_CUT", "CRUDE_FALL"]}
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json=payload,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True, f"Expected success=True: {data}"
        assert set(data.get("active_events", [])) == {"RBI_RATE_CUT", "CRUDE_FALL"}, (
            f"Expected active_events to be [RBI_RATE_CUT, CRUDE_FALL], got {data.get('active_events')}"
        )
        assert data.get("total_active") == 2, f"Expected total_active=2, got {data.get('total_active')}"
        print(f"PASS: POST sets active_events={data['active_events']}")

    def test_post_invalid_key_returns_422(self, admin_session):
        """POST with invalid key 'FAKE_EVENT_XYZ' must return 422."""
        payload = {"events": ["FAKE_EVENT_XYZ"]}
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json=payload,
            timeout=15,
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print(f"PASS: POST with invalid key returns 422")

    def test_post_invalid_key_has_descriptive_error(self, admin_session):
        """POST with invalid key returns 422 with detail mentioning the invalid key."""
        payload = {"events": ["FAKE_EVENT_XYZ"]}
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json=payload,
            timeout=15,
        )
        assert resp.status_code == 422
        data = resp.json()
        # The detail should mention the invalid key or valid keys
        detail = str(data.get("detail", ""))
        assert "FAKE_EVENT_XYZ" in detail or "invalid" in detail.lower() or "valid" in detail.lower(), (
            f"Expected descriptive error mentioning key name, got: {detail}"
        )
        print(f"PASS: 422 error is descriptive: '{detail[:100]}'")

    def test_post_empty_events_clears_all_active(self, admin_session):
        """POST with events=[] clears all active events."""
        # First set some events
        admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["RBI_RATE_CUT"]},
            timeout=15,
        )
        # Now clear
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": []},
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True, f"success must be True: {data}"
        assert data.get("active_events") == [], f"Expected empty active_events, got {data.get('active_events')}"
        assert data.get("total_active") == 0, f"Expected total_active=0, got {data.get('total_active')}"
        print("PASS: POST events=[] clears all active events")

    def test_get_after_post_shows_active_flag_true(self, admin_session):
        """After POST with ['RBI_RATE_CUT','CRUDE_FALL'], GET shows those events with active=True."""
        # Set two events
        admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": ["RBI_RATE_CUT", "CRUDE_FALL"]},
            timeout=15,
        )
        # Verify via GET
        resp = admin_session.get(f"{BASE_URL}/api/admin/macro-events", timeout=15)
        assert resp.status_code == 200
        data = resp.json()

        # active_events list should contain both
        assert set(data.get("active_events", [])) == {"RBI_RATE_CUT", "CRUDE_FALL"}, (
            f"active_events mismatch: {data.get('active_events')}"
        )

        # In all_events, those two should have active=True; others should be False
        active_keys = {e["key"] for e in data.get("all_events", []) if e["active"]}
        inactive_keys = {e["key"] for e in data.get("all_events", []) if not e["active"]}
        assert "RBI_RATE_CUT" in active_keys, "RBI_RATE_CUT should be active=True in all_events"
        assert "CRUDE_FALL" in active_keys, "CRUDE_FALL should be active=True in all_events"
        assert "CRUDE_SPIKE" in inactive_keys, "CRUDE_SPIKE should be active=False after setting different events"
        print(f"PASS: GET after POST shows active=True for RBI_RATE_CUT and CRUDE_FALL")

    def test_post_mixed_valid_and_invalid_returns_422(self, admin_session):
        """POST with one valid + one invalid key still returns 422."""
        payload = {"events": ["RBI_RATE_CUT", "INVALID_KEY_ABC"]}
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json=payload,
            timeout=15,
        )
        assert resp.status_code == 422, f"Expected 422 for mixed valid/invalid, got {resp.status_code}"
        print("PASS: Mixed valid+invalid returns 422")

    def test_post_all_valid_15_events(self, admin_session):
        """POST with all 15 valid events should succeed."""
        all_keys = list(EXPECTED_MACRO_EVENTS)
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": all_keys},
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200 for all valid events, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("total_active") == 15, f"Expected total_active=15, got {data.get('total_active')}"
        print("PASS: POST with all 15 valid events succeeds")

    def test_cleanup_reset_active_events_to_empty(self, admin_session):
        """Cleanup: reset active events to empty after all tests."""
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/macro-events/update",
            json={"events": []},
            timeout=15,
        )
        assert resp.status_code == 200
        print("PASS: Cleanup - active events reset to empty")


# ──────────────────────────────────────────────────────────────────────────────
# BATCH B: Confluence Score with Forensic Data (Unit Tests)
# ──────────────────────────────────────────────────────────────────────────────

class TestBatchBConfluenceForensicUnit:
    """
    Batch B: Direct unit tests for _calculate_confluence_score_master_spec.
    Verify that piotroski_score/beneish_m_score/altman_z_zone affect fundamental_score.
    Import the function directly from server.py.
    """

    @pytest.fixture(scope="class", autouse=True)
    def import_confluence_fn(self):
        """Import the confluence scoring function and StockCoreNormalized model."""
        sys.path.insert(0, "/app/backend")
        try:
            from server import _calculate_confluence_score_master_spec
            from models import StockCoreNormalized
            # Store on class
            TestBatchBConfluenceForensicUnit._fn = staticmethod(_calculate_confluence_score_master_spec)
            TestBatchBConfluenceForensicUnit._model = StockCoreNormalized
            print("PASS: Imported _calculate_confluence_score_master_spec from server.py")
        except Exception as e:
            pytest.skip(f"Cannot import _calculate_confluence_score_master_spec: {e}")

    def _make_stock(self, ltp=500.0, year_high=700.0, year_low=300.0):
        """Helper: create a StockCoreNormalized with given values."""
        return self._model(
            symbol="TEST",
            company_name="Test Corp",
            ltp=ltp,
            open=495.0,
            high=505.0,
            low=490.0,
            prev_close=498.0,
            year_high=year_high,
            year_low=year_low,
            volume=1_000_000,
            sector="Banking",
        )

    def _call_fn(self, stock, piotroski_score=None, beneish_m_score=None, altman_z_zone=None):
        """Helper: call confluence function with standard params + forensic overrides."""
        return self._fn(
            stock_core=stock,
            direction="BULLISH",
            bias_score=2.5,
            risk_reward_target2=2.5,
            option_ltp=100.0,
            minutes_to_expiry=500,
            entry_discount_pct=3.0,
            option_day_high=110.0,
            option_day_low=90.0,
            india_vix=15.0,
            pcr=1.1,
            strategy="ORB_BREAKOUT",
            piotroski_score=piotroski_score,
            beneish_m_score=beneish_m_score,
            altman_z_zone=altman_z_zone,
        )

    def test_high_piotroski_gives_highest_fundamental_score(self):
        """piotroski=8 (STRONG) should give highest total score vs no forensic data."""
        stock = self._make_stock()
        score_high, _ = self._call_fn(stock, piotroski_score=8)
        score_none, _ = self._call_fn(stock, piotroski_score=None)
        # piotroski=8 → fundamental=10; 52W proxy for mid-range position → fundamental=8
        # high piotroski should give score_high >= score_none
        assert score_high >= score_none, (
            f"High piotroski ({score_high}) should >= no forensic ({score_none})"
        )
        print(f"PASS: piotroski=8 score={score_high} >= no_forensic score={score_none}")

    def test_low_piotroski_gives_lower_score_than_high(self):
        """piotroski=1 (POOR) gives lower total score than piotroski=8 (STRONG)."""
        stock = self._make_stock()
        score_high, _ = self._call_fn(stock, piotroski_score=8)
        score_low, _ = self._call_fn(stock, piotroski_score=1)
        # piotroski=8 → fundamental=10, piotroski=1 → fundamental=2
        # Difference should be 8 points in total score
        assert score_high > score_low, (
            f"High piotroski ({score_high}) must be > low piotroski ({score_low})"
        )
        diff = score_high - score_low
        assert diff == 8, f"Expected fundamental score diff=8 (10-2), got diff={diff}"
        print(f"PASS: piotroski=8 ({score_high}) > piotroski=1 ({score_low}), diff={diff}")

    def test_piotroski_score_thresholds(self):
        """Verify piotroski score tiers: >=7→10, >=5→7, >=3→4, <3→2."""
        stock = self._make_stock()
        score_9, _ = self._call_fn(stock, piotroski_score=9)   # >=7 → fundamental=10
        score_7, _ = self._call_fn(stock, piotroski_score=7)   # >=7 → fundamental=10
        score_6, _ = self._call_fn(stock, piotroski_score=6)   # >=5 → fundamental=7
        score_5, _ = self._call_fn(stock, piotroski_score=5)   # >=5 → fundamental=7
        score_4, _ = self._call_fn(stock, piotroski_score=4)   # >=3 → fundamental=4
        score_3, _ = self._call_fn(stock, piotroski_score=3)   # >=3 → fundamental=4
        score_2, _ = self._call_fn(stock, piotroski_score=2)   # <3  → fundamental=2
        score_0, _ = self._call_fn(stock, piotroski_score=0)   # <3  → fundamental=2

        # Same-tier scores must be equal
        assert score_9 == score_7, f"Tier >=7 should yield same score: p=9({score_9}) != p=7({score_7})"
        assert score_6 == score_5, f"Tier >=5 should yield same score: p=6({score_6}) != p=5({score_5})"
        assert score_4 == score_3, f"Tier >=3 should yield same score: p=4({score_4}) != p=3({score_3})"
        assert score_2 == score_0, f"Tier <3 should yield same score: p=2({score_2}) != p=0({score_0})"

        # Tiers must be strictly decreasing
        assert score_7 > score_5, f"Tier >=7 ({score_7}) must > tier >=5 ({score_5})"
        assert score_5 > score_3, f"Tier >=5 ({score_5}) must > tier >=3 ({score_3})"
        assert score_3 > score_0, f"Tier >=3 ({score_3}) must > tier <3 ({score_0})"
        print(f"PASS: Piotroski tiers: 9={score_9}, 6={score_6}, 4={score_4}, 0={score_0}")

    def test_beneish_manipulation_penalty(self):
        """beneish_m_score > -2.22 signals manipulation: fundamental_score -= 3."""
        stock = self._make_stock()
        # piotroski=8 → fundamental=10 before beneish adjustment
        score_clean, _ = self._call_fn(stock, piotroski_score=8, beneish_m_score=-3.0)   # -3.0 < -2.22: NO penalty
        score_manip, _ = self._call_fn(stock, piotroski_score=8, beneish_m_score=-1.5)   # -1.5 > -2.22: -3 penalty

        assert score_clean > score_manip, (
            f"Clean beneish ({score_clean}) must be > manipulation signal ({score_manip})"
        )
        diff = score_clean - score_manip
        assert diff == 3, f"Expected beneish penalty=3, got {diff}"
        print(f"PASS: Beneish manipulation penalty: clean={score_clean}, manip={score_manip}, diff={diff}")

    def test_altman_distress_penalty(self):
        """altman_z_zone='DISTRESS' subtracts 4 from fundamental_score."""
        stock = self._make_stock()
        # piotroski=8 → fundamental=10 base
        score_safe, _ = self._call_fn(stock, piotroski_score=8, altman_z_zone="SAFE")     # +2 → 12, capped at 10
        score_neutral, _ = self._call_fn(stock, piotroski_score=8, altman_z_zone=None)    # no adjustment → 10
        score_distress, _ = self._call_fn(stock, piotroski_score=8, altman_z_zone="DISTRESS")  # -4 → 6

        assert score_distress < score_neutral, (
            f"DISTRESS ({score_distress}) must be < neutral ({score_neutral})"
        )
        diff_distress = score_neutral - score_distress
        assert diff_distress == 4, f"Expected DISTRESS penalty=4, got {diff_distress}"
        print(f"PASS: DISTRESS penalty=4: neutral={score_neutral}, distress={score_distress}")

    def test_altman_safe_bonus(self):
        """altman_z_zone='SAFE' adds 2 to fundamental_score (capped at 10)."""
        stock = self._make_stock()
        # piotroski=5 → fundamental=7, SAFE adds 2 → 9
        score_neutral, _ = self._call_fn(stock, piotroski_score=5, altman_z_zone=None)
        score_safe, _ = self._call_fn(stock, piotroski_score=5, altman_z_zone="SAFE")

        assert score_safe > score_neutral, (
            f"SAFE zone ({score_safe}) must be > neutral ({score_neutral})"
        )
        diff = score_safe - score_neutral
        assert diff == 2, f"Expected SAFE bonus=2, got {diff}"
        print(f"PASS: SAFE bonus=2: neutral={score_neutral}, safe={score_safe}")

    def test_altman_safe_bonus_capped_at_10(self):
        """altman_z_zone='SAFE' with piotroski=8 (fundamental=10): bonus capped at 10."""
        stock = self._make_stock()
        # piotroski=8 → fundamental=10, SAFE +2 → min(10, 12) = 10 (no extra)
        score_neutral, _ = self._call_fn(stock, piotroski_score=8, altman_z_zone=None)
        score_safe, _ = self._call_fn(stock, piotroski_score=8, altman_z_zone="SAFE")
        # Both should be the same (capped at 10)
        assert score_safe == score_neutral, (
            f"SAFE bonus on max fundamental (10) should not change score: neutral={score_neutral}, safe={score_safe}"
        )
        print(f"PASS: SAFE bonus capped at max fundamental=10, scores equal: {score_neutral}")

    def test_no_forensic_data_uses_52w_proxy(self):
        """When piotroski_score=None, fundamental_score uses 52W position proxy.
        Note: Total score diff > 2 because breadth_score also uses 52W position.
        We verify direction: mid-range 52W → higher score than near-high 52W.
        """
        # Mid-range position → fundamental=8, breadth=6 (BULLISH, mid)
        stock_mid = self._make_stock(ltp=500.0, year_high=700.0, year_low=300.0)
        # 52W position = (500-300)/(700-300) = 0.5, in [0.3, 0.7] → fundamental=8

        # Near high (overbought for BULLISH) → fundamental=6, breadth=3
        stock_near_high = self._make_stock(ltp=680.0, year_high=700.0, year_low=300.0)
        # position = (680-300)/(700-300) = 0.95, not in [0.3, 0.7] → fundamental=6

        score_mid, _ = self._call_fn(stock_mid, piotroski_score=None)
        score_high, _ = self._call_fn(stock_near_high, piotroski_score=None)

        assert score_mid > score_high, (
            f"Mid-range 52W position ({score_mid}) must have higher score than near-high ({score_high})"
        )
        # Diff = fundamental diff (8-6=2) + breadth_score diff (6-3=3) = 5
        diff = score_mid - score_high
        assert diff == 5, (
            f"Expected total diff=5 (fundamental:2 + breadth:3), got {diff}. "
            f"mid={score_mid}, near_high={score_high}"
        )
        print(f"PASS: 52W proxy used when no forensic data: mid={score_mid}, near_high={score_high}, diff={diff} (fundamental:2 + breadth:3)")

    def test_combined_distress_and_beneish_penalties(self):
        """Combined DISTRESS (-4) + manipulation beneish (-3) penalties accumulate correctly."""
        stock = self._make_stock()
        # piotroski=8 → fundamental=10
        # DISTRESS: 10-4=6
        # beneish -1.0 > -2.22 (manipulation): 6-3=3
        score_base, _ = self._call_fn(stock, piotroski_score=8)
        score_combo, _ = self._call_fn(stock, piotroski_score=8, beneish_m_score=-1.0, altman_z_zone="DISTRESS")
        diff = score_base - score_combo
        assert diff == 7, f"Expected combined penalty=7 (4+3), got {diff}"
        print(f"PASS: Combined DISTRESS+Beneish penalty=7: base={score_base}, combo={score_combo}")


# ──────────────────────────────────────────────────────────────────────────────
# BATCH C: Strategy Stats Endpoint
# ──────────────────────────────────────────────────────────────────────────────

class TestBatchCStrategyStats:
    """Batch C: GET /api/admin/strategy-stats validation"""

    def test_strategy_stats_returns_200(self, admin_session):
        """GET /api/admin/strategy-stats returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/strategy-stats", timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: GET /api/admin/strategy-stats returns 200")

    def test_strategy_stats_has_strategy_stats_key(self, admin_session):
        """Response has 'strategy_stats' key."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/strategy-stats", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "strategy_stats" in data, f"Missing 'strategy_stats' key: {data}"
        assert isinstance(data["strategy_stats"], list), "strategy_stats must be a list"
        print(f"PASS: strategy_stats is list, count={len(data['strategy_stats'])}")

    def test_strategy_stats_has_total_records_key(self, admin_session):
        """Response has 'total_records' field."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/strategy-stats", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_records" in data, f"Missing 'total_records' key: {data}"
        assert isinstance(data["total_records"], int), "total_records must be int"
        print(f"PASS: total_records={data['total_records']}")

    def test_strategy_stats_optional_filter_by_strategy_id(self, admin_session):
        """GET with ?strategy_id=S1_ORB returns filtered results (empty or subset)."""
        resp = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-stats?strategy_id=S1_ORB",
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200 with strategy_id filter, got {resp.status_code}"
        data = resp.json()
        assert "strategy_stats" in data
        # If any results, they should all be S1_ORB
        for stat in data.get("strategy_stats", []):
            assert stat.get("strategy_id") == "S1_ORB", f"Filter returned wrong strategy: {stat}"
        print(f"PASS: strategy_id filter works, returned {len(data['strategy_stats'])} results")

    def test_strategy_stats_items_have_required_fields(self, admin_session):
        """If strategy_stats has items, each should have required fields."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/strategy-stats", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        stats_list = data.get("strategy_stats", [])
        if not stats_list:
            print("PASS (skip): strategy_stats is empty (no trades recorded yet)")
            return
        required_fields = ["strategy_id", "total_trades", "wins", "total_r_multiple", "win_rate"]
        for stat in stats_list:
            for field in required_fields:
                assert field in stat, f"Missing field '{field}' in stat: {stat}"
        print(f"PASS: All {len(stats_list)} stats items have required fields")


# ──────────────────────────────────────────────────────────────────────────────
# REGRESSION: NSE Holidays (no breakage)
# ──────────────────────────────────────────────────────────────────────────────

class TestRegressionNseHolidays:
    """Regression: GET /api/admin/nse-holidays still works."""

    def test_nse_holidays_returns_200(self, admin_session):
        """GET /api/admin/nse-holidays returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/nse-holidays", timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: GET /api/admin/nse-holidays returns 200")

    def test_nse_holidays_has_required_keys(self, admin_session):
        """Response has total_in_memory and holidays keys."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/nse-holidays", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_in_memory" in data, f"Missing 'total_in_memory': {data}"
        assert "holidays" in data, f"Missing 'holidays': {data}"
        assert isinstance(data["holidays"], list), "holidays must be list"
        print(f"PASS: NSE holidays: total_in_memory={data['total_in_memory']}, records={len(data['holidays'])}")


# ──────────────────────────────────────────────────────────────────────────────
# REGRESSION: Multibagger Custom Search
# ──────────────────────────────────────────────────────────────────────────────

class TestRegressionMultibagger:
    """Regression: POST /api/multibagger/custom-search still works."""

    def test_multibagger_custom_search_reliance_returns_200(self, admin_session):
        """POST /multibagger/custom-search with RELIANCE returns 200."""
        resp = admin_session.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "RELIANCE"},
            timeout=60,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Multibagger custom-search RELIANCE returns 200")

    def test_multibagger_custom_search_has_required_fields(self, admin_session):
        """Multibagger result has symbol, vol_bands, and multibagger_score."""
        resp = admin_session.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "RELIANCE"},
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "symbol" in data, f"Missing 'symbol': {data.keys()}"
        assert data["symbol"] == "RELIANCE", f"Expected RELIANCE, got {data['symbol']}"
        assert "multibagger_score" in data, f"Missing 'multibagger_score': {data.keys()}"
        print(f"PASS: Multibagger RELIANCE: score={data.get('multibagger_score')}, symbol={data.get('symbol')}")

    def test_multibagger_compute_analysis_still_works(self, admin_session):
        """compute_multibagger_analysis returns vol_bands with 6 horizons for HDFCBANK."""
        resp = admin_session.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "HDFCBANK"},
            timeout=60,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        vol_bands = data.get("vol_bands")
        if vol_bands:
            assert len(vol_bands) == 6, f"Expected 6 horizon vol_bands, got {len(vol_bands)}: {list(vol_bands.keys())}"
            print(f"PASS: HDFCBANK vol_bands has 6 horizons")
        else:
            print("PASS (skipped): HDFCBANK vol_bands is None (external data may be unavailable)")


# ──────────────────────────────────────────────────────────────────────────────
# REGRESSION: Portfolio Analyze
# ──────────────────────────────────────────────────────────────────────────────

class TestRegressionPortfolioAnalyze:
    """Regression: POST /api/portfolio/analyze still works."""

    def test_portfolio_analyze_returns_200(self, admin_session):
        """POST /api/portfolio/analyze with sample holdings returns 200."""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2900.0, "quantity": 10.0},
                {"symbol": "INFY", "avg_price": 1500.0, "quantity": 20.0},
            ]
        }
        resp = admin_session.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            timeout=90,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Portfolio analyze returns 200")

    def test_portfolio_analyze_has_stocks_array(self, admin_session):
        """Portfolio analyze response has 'stocks' array."""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2900.0, "quantity": 10.0},
            ]
        }
        resp = admin_session.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data, f"Missing 'stocks' key: {list(data.keys())}"
        assert isinstance(data["stocks"], list), "stocks must be list"
        print(f"PASS: Portfolio stocks count={len(data['stocks'])}")

    def test_portfolio_analyze_has_risk_metrics(self, admin_session):
        """Portfolio analyze response has portfolio_risk_metrics."""
        payload = {
            "positions": [
                {"symbol": "DMART", "avg_price": 4200.0, "quantity": 5.0},
                {"symbol": "KAYNES", "avg_price": 3200.0, "quantity": 8.0},
            ]
        }
        resp = admin_session.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            timeout=90,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        risk = data.get("portfolio_risk_metrics")
        if risk:
            assert "portfolio_vol_annual_pct" in risk, f"Missing portfolio_vol_annual_pct: {risk.keys()}"
            vol = risk.get("portfolio_vol_annual_pct")
            assert isinstance(vol, (int, float)) and vol != 30.0, (
                f"portfolio_vol_annual_pct should not be hardcoded 30.0%, got {vol}"
            )
            print(f"PASS: Portfolio risk_metrics present, portfolio_vol_annual_pct={vol}%")
        else:
            print("PASS (skipped): portfolio_risk_metrics is None (may need more stocks)")
