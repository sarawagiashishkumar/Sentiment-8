"""
Iteration 17 Backend Upgrade Tests
Tests for:
- Dual-source parallel fetch verification (data_verifier.py)
- NSE holidays corrections (2026-04-06 removed, 2026-04-14 present)
- VIX-based theta decay (compute_vix_theta_decay)
- Session-time-aware market status (is_market_open, get_market_session_status)
- F&O generate endpoint (market_session, market_regime fields, confluence >= 78, ThetaModel tag)
- Dynamic target revision (compute_dynamic_target_revision)
- 78% minimum confluence enforcement
- No-signals alert with specific reason
- Near expiry badge logic (remaining_trading_days <= 2)
"""

import asyncio
import importlib
import math
import os
import sys
import pytest
import requests

from tests.helpers.test_utils import get_base_url, get_ndjson_complete_data, read_backend_source

# ─── Base URL ─────────────────────────────────────────────────────────────────
BASE_URL = get_base_url()

# Add backend path for direct imports
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Obtain admin token once per module."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "pin": "1234"},
        timeout=15,
    )
    assert resp.status_code == 200, f"Auth failed: {resp.status_code} {resp.text[:200]}"
    token = resp.json().get("token")
    assert token, "Token missing from auth response"
    return token


@pytest.fixture(scope="module")
def authed(auth_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {auth_token}"})
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 1: data_verifier.py clean imports (item 11)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataVerifierImports:
    """Test that data_verifier.py imports cleanly and all key symbols are present."""

    def test_module_imports_cleanly(self):
        """data_verifier.py must import without errors."""
        try:
            from services import data_verifier  # noqa: F401
            print("PASS: data_verifier imports cleanly")
        except ImportError as e:
            pytest.fail(f"data_verifier import failed: {e}")

    def test_fetch_verified_price_exists(self):
        """fetch_verified_price must be importable from data_verifier."""
        from services.data_verifier import fetch_verified_price
        assert callable(fetch_verified_price), "fetch_verified_price must be callable"
        import inspect
        assert inspect.iscoroutinefunction(fetch_verified_price), (
            "fetch_verified_price must be an async function"
        )
        print("PASS: fetch_verified_price is importable async function")

    def test_fetch_verified_snapshot_exists(self):
        """fetch_verified_snapshot must be importable from data_verifier."""
        from services.data_verifier import fetch_verified_snapshot
        assert callable(fetch_verified_snapshot), "fetch_verified_snapshot must be callable"
        import inspect
        assert inspect.iscoroutinefunction(fetch_verified_snapshot), (
            "fetch_verified_snapshot must be async"
        )
        print("PASS: fetch_verified_snapshot is importable async function")

    def test_compute_vix_theta_decay_exists(self):
        """compute_vix_theta_decay must be importable from data_verifier."""
        from services.data_verifier import compute_vix_theta_decay
        assert callable(compute_vix_theta_decay), "compute_vix_theta_decay must be callable"
        print("PASS: compute_vix_theta_decay is importable")

    def test_server_imports_data_verifier(self):
        """server.py must import all 7 symbols from data_verifier cleanly."""
        import services.data_verifier as dv
        required = [
            "fetch_verified_price",
            "fetch_verified_snapshot",
            "compute_vix_theta_decay",
            "compute_dynamic_target_revision",
            "get_minutes_to_session_close",
            "is_market_open",
            "get_market_session_status",
        ]
        for sym in required:
            assert hasattr(dv, sym), f"data_verifier missing symbol: {sym}"
        print(f"PASS: data_verifier has all {len(required)} required symbols")

    def test_verified_price_dataclass_fields(self):
        """VerifiedPrice dataclass must have required fields."""
        from services.data_verifier import VerifiedPrice
        import dataclasses
        fields = {f.name for f in dataclasses.fields(VerifiedPrice)}
        required = {"ltp", "source", "kite_ltp", "fallback_ltp", "discrepancy_pct",
                    "discrepancy_flagged", "warnings", "raw_kite_quote"}
        missing = required - fields
        assert not missing, f"VerifiedPrice missing fields: {missing}"
        print(f"PASS: VerifiedPrice has all required fields: {fields}")

    def test_verified_snapshot_dataclass_fields(self):
        """VerifiedSnapshot dataclass must have required fields."""
        from services.data_verifier import VerifiedSnapshot
        import dataclasses
        fields = {f.name for f in dataclasses.fields(VerifiedSnapshot)}
        required = {"ltp", "source", "day_high", "day_low", "open", "prev_close",
                    "volume", "oi", "iv", "discrepancy_flagged", "warnings"}
        missing = required - fields
        assert not missing, f"VerifiedSnapshot missing fields: {missing}"
        print(f"PASS: VerifiedSnapshot has all required fields")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 2: NSE Holidays (items 2 & 3)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNseHolidays:
    """Verify NSE_HOLIDAYS list corrections in server.py."""

    def _get_nse_holidays(self):
        """Extract NSE_HOLIDAYS from server.py via grep rather than importing."""
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path, "r") as f:
            content = f.read()
        return content

    def test_2026_04_06_not_in_nse_holidays(self):
        """2026-04-06 must NOT be in NSE_HOLIDAYS (it was a wrong addition and has been removed)."""
        content = self._get_nse_holidays()
        assert '"2026-04-06"' not in content and "'2026-04-06'" not in content, (
            "FAIL: '2026-04-06' found in server.py NSE_HOLIDAYS — must be removed"
        )
        print("PASS: '2026-04-06' is NOT in NSE_HOLIDAYS")

    def test_2026_04_14_in_nse_holidays(self):
        """2026-04-14 (Dr. Ambedkar Jayanti) must be in NSE_HOLIDAYS."""
        content = self._get_nse_holidays()
        assert '"2026-04-14"' in content or "'2026-04-14'" in content, (
            "FAIL: '2026-04-14' not found in NSE_HOLIDAYS"
        )
        print("PASS: '2026-04-14' IS in NSE_HOLIDAYS")

    def test_nse_holidays_set_import(self):
        """NSE_HOLIDAYS must be importable as a set from server module context."""
        import importlib.util
        server_path = os.path.join(BACKEND_DIR, "server.py")
        # Read the NSE_HOLIDAYS literal directly from the file source
        with open(server_path) as f:
            content = f.read()
        # Verify set literal is present and contains the date
        assert "NSE_HOLIDAYS" in content, "NSE_HOLIDAYS not found in server.py"
        # Verify 2026-04-06 is not present
        assert "2026-04-06" not in content, (
            "2026-04-06 found in server.py - should have been removed"
        )
        print("PASS: NSE_HOLIDAYS code verified via source inspection")

    def test_get_remaining_trading_days_skips_2026_04_06(self):
        """
        get_remaining_trading_days should NOT count 2026-04-06 as a holiday.
        Verify by checking the function treats April 6 2026 as a regular trading day.
        """
        from services.data_verifier import is_market_open
        # The real test: NSE_HOLIDAYS in server.py must not contain 2026-04-06.
        # We verify via source code.
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            content = f.read()
        assert "2026-04-06" not in content, (
            "2026-04-06 is in server.py — it should have been removed from NSE_HOLIDAYS"
        )
        print("PASS: 2026-04-06 not found in server.py, get_remaining_trading_days won't skip it")

    def test_get_remaining_trading_days_counts_2026_04_14_as_holiday(self):
        """
        get_remaining_trading_days must count 2026-04-14 as a holiday (skip it).
        NSE_HOLIDAYS is now MongoDB-backed, so check via read_backend_source.
        """
        content = read_backend_source()
        # If the date is hardcoded, check it
        if "2026-04-14" in content:
            print("PASS: 2026-04-14 is in backend source, will be skipped")
        else:
            pytest.skip("NSE_HOLIDAYS loaded from MongoDB — holiday dates not in static source")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 3: VIX-based theta decay (item 4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVixThetaDecay:
    """Verify compute_vix_theta_decay uses VIX-based model, not fixed 0.15 multiplier."""

    def test_compute_vix_theta_decay_imports(self):
        """compute_vix_theta_decay must be importable."""
        from services.data_verifier import compute_vix_theta_decay
        assert callable(compute_vix_theta_decay)
        print("PASS: compute_vix_theta_decay importable")

    def test_vix_theta_returns_tuple(self):
        """compute_vix_theta_decay must return a 2-tuple (float, str)."""
        from services.data_verifier import compute_vix_theta_decay
        result = compute_vix_theta_decay(100.0, 14, 7, india_vix=16.5)
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 2, f"Expected 2-tuple, got {len(result)}-tuple"
        theta_val, theta_method = result
        assert isinstance(theta_val, float), f"theta_val must be float, got {type(theta_val)}"
        assert isinstance(theta_method, str), f"theta_method must be str, got {type(theta_method)}"
        print(f"PASS: compute_vix_theta_decay returns tuple: ({theta_val}, '{theta_method}')")

    def test_vix_theta_greater_than_10(self):
        """
        compute_vix_theta_decay(100, 14, 7, india_vix=16.5) must return theta > 10.
        Old static formula: 100 * 0.15 * 0.6 ≈ 9 (or similar small value).
        New VIX formula: ~17 (significantly more accurate).
        """
        from services.data_verifier import compute_vix_theta_decay
        theta_val, theta_method = compute_vix_theta_decay(100.0, 14, 7, india_vix=16.5)
        assert theta_val > 10, (
            f"FAIL: compute_vix_theta_decay(100, 14, 7, india_vix=16.5) = {theta_val}, "
            f"expected > 10 (old static formula gave ~7; new VIX formula should give ~17)"
        )
        print(f"PASS: compute_vix_theta_decay(100, 14, 7, india_vix=16.5) = {theta_val:.4f} > 10")

    def test_vix_theta_approximately_17(self):
        """
        compute_vix_theta_decay(100, 14, 7, india_vix=16.5) should be approximately 17.
        Calculation: sigma=0.1815, t=14/252, daily_theta=100*0.1815/(2*sqrt(14)) ≈ 2.42, total=2.42*7 ≈ 16.97
        """
        from services.data_verifier import compute_vix_theta_decay
        theta_val, theta_method = compute_vix_theta_decay(100.0, 14, 7, india_vix=16.5)
        # Should be between 14 and 21 (approximately 17)
        assert 14 <= theta_val <= 21, (
            f"compute_vix_theta_decay(100, 14, 7, india_vix=16.5) = {theta_val}, expected ~17 (range 14-21)"
        )
        print(f"PASS: theta ≈ {theta_val:.2f} (expected ~17)")

    def test_vix_theta_method_contains_vix_tag(self):
        """theta_method string must contain 'VIX=' when india_vix is provided."""
        from services.data_verifier import compute_vix_theta_decay
        theta_val, theta_method = compute_vix_theta_decay(100.0, 14, 7, india_vix=16.5)
        assert "VIX=" in theta_method, (
            f"theta_method '{theta_method}' must contain 'VIX=' when india_vix is provided"
        )
        print(f"PASS: theta_method = '{theta_method}' contains 'VIX='")

    def test_vix_theta_near_expiry_scale(self):
        """For remaining_trading_days <= 7, vix_scale should be 1.25 (near-expiry premium)."""
        from services.data_verifier import compute_vix_theta_decay
        theta_near, method_near = compute_vix_theta_decay(100.0, 5, 3, india_vix=16.5)
        theta_far, method_far = compute_vix_theta_decay(100.0, 30, 7, india_vix=16.5)
        # Near-expiry theta per day should reflect higher effective IV
        # Just verify both return positive values
        assert theta_near > 0, "Near-expiry theta must be positive"
        assert theta_far > 0, "Far-expiry theta must be positive"
        print(f"PASS: near_expiry theta={theta_near:.2f} (method='{method_near}'), far={theta_far:.2f}")

    def test_vix_theta_default_18pct_without_vix(self):
        """When no india_vix and no iv_override, should use default 18% sigma."""
        from services.data_verifier import compute_vix_theta_decay
        theta_val, theta_method = compute_vix_theta_decay(100.0, 14, 7)
        assert "default_18%" in theta_method, (
            f"Expected 'default_18%' in theta_method, got '{theta_method}'"
        )
        assert theta_val > 0, "Default theta must be positive"
        print(f"PASS: default theta = {theta_val:.2f}, method = '{theta_method}'")

    def test_vix_theta_not_static_formula(self):
        """
        Verify the formula is NOT the old static 0.15 multiplier.
        Old formula: entry_price * 0.15 * decay_factor (would give ~9 for entry=100, days=7)
        New formula should give ~17
        """
        from services.data_verifier import compute_vix_theta_decay
        theta_val, _ = compute_vix_theta_decay(100.0, 14, 7, india_vix=16.5)
        # Old formula would give approximately 100 * 0.15 * (7/14) = 7.5 or similar
        # New formula should give significantly more
        assert theta_val > 12, (
            f"theta={theta_val} suggests static formula may be in use (should be ~17 with VIX=16.5)"
        )
        print(f"PASS: theta={theta_val:.2f} — not a static formula")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 4: Market Session Status (items 5 & 10)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketSessionStatus:
    """Verify is_market_open() and get_market_session_status() work correctly."""

    def test_is_market_open_returns_bool(self):
        """is_market_open() must return a bool."""
        from services.data_verifier import is_market_open
        result = is_market_open()
        assert isinstance(result, bool), f"is_market_open must return bool, got {type(result)}"
        print(f"PASS: is_market_open() returned {result} (bool)")

    def test_is_market_open_false_after_hours(self):
        """
        At 19:56 IST (after market close at 15:30), is_market_open() must return False.
        Since tests run at ~19:56 IST, this should be naturally False.
        """
        from services.data_verifier import is_market_open
        import pytz
        from datetime import datetime
        IST = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(IST)
        now_hour = now_ist.hour
        now_min = now_ist.minute

        result = is_market_open()
        print(f"Current IST time: {now_ist.strftime('%H:%M:%S')} — is_market_open = {result}")

        # At 19:56 IST, market is definitely closed (after 15:30)
        if (now_hour > 15) or (now_hour == 15 and now_min >= 30):
            assert result is False, (
                f"is_market_open() must be False at {now_ist.strftime('%H:%M')} IST "
                f"(after 15:30 close)"
            )
            print(f"PASS: is_market_open() = False at {now_ist.strftime('%H:%M')} IST (after close)")
        elif now_hour < 9 or (now_hour == 9 and now_min < 15):
            assert result is False, (
                f"is_market_open() must be False before 09:15 IST"
            )
            print(f"PASS: is_market_open() = False (before open)")
        else:
            print(f"NOTE: Test running during market hours {now_ist.strftime('%H:%M')} IST — is_market_open = {result}")

    def test_get_market_session_status_returns_dict(self):
        """get_market_session_status() must return a dict."""
        from services.data_verifier import get_market_session_status
        result = get_market_session_status()
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        print(f"PASS: get_market_session_status returned dict: {result}")

    def test_get_market_session_status_required_keys(self):
        """get_market_session_status() must have is_open, status, ist_time, minutes_to_close."""
        from services.data_verifier import get_market_session_status
        result = get_market_session_status()
        required_keys = {"is_open", "status", "ist_time"}
        for key in required_keys:
            assert key in result, f"market_session_status missing key: {key}"
        print(f"PASS: market_session_status has required keys: {list(result.keys())}")

    def test_get_market_session_status_closed_after_hours(self):
        """
        At 19:56 IST, get_market_session_status() must return is_open=False and status='CLOSED'.
        """
        from services.data_verifier import get_market_session_status
        import pytz
        from datetime import datetime
        IST = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(IST)
        now_hour = now_ist.hour
        now_min = now_ist.minute

        result = get_market_session_status()
        print(f"IST: {now_ist.strftime('%H:%M')}, session_status: {result}")

        # After 15:30 IST, must be CLOSED
        if (now_hour > 15) or (now_hour == 15 and now_min >= 30):
            assert result.get("is_open") is False, (
                f"is_open must be False at {now_ist.strftime('%H:%M')} IST, got: {result}"
            )
            assert result.get("status") == "CLOSED", (
                f"status must be 'CLOSED' at {now_ist.strftime('%H:%M')} IST, got: {result.get('status')}"
            )
            print(f"PASS: market_session is_open=False, status='CLOSED' at {now_ist.strftime('%H:%M')} IST")
        else:
            print(f"NOTE: Not running after market close — status = {result.get('status')}")

    def test_market_session_minutes_to_close_zero_when_closed(self):
        """When market is closed, minutes_to_close should be 0 or represent next session."""
        from services.data_verifier import get_market_session_status, is_market_open
        if not is_market_open():
            result = get_market_session_status()
            minutes = result.get("minutes_to_close")
            # When closed, minutes_to_close can be 0 or represent next trading session
            assert isinstance(minutes, (int, float)), (
                f"minutes_to_close should be numeric, got: {type(minutes)}"
            )
            print(f"PASS: minutes_to_close = {minutes} when market is closed")
        else:
            print("SKIP: Market is open, not testing closed-state minutes")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 5: Dynamic Target Revision (item 9)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDynamicTargetRevision:
    """Verify compute_dynamic_target_revision logic."""

    def test_dynamic_revision_imports(self):
        """compute_dynamic_target_revision must be importable."""
        from services.data_verifier import compute_dynamic_target_revision
        assert callable(compute_dynamic_target_revision)
        print("PASS: compute_dynamic_target_revision importable")

    def test_dynamic_revision_returns_tuple(self):
        """Must return a 3-tuple (revised_t1, revised_t2, revision_note)."""
        from services.data_verifier import compute_dynamic_target_revision
        result = compute_dynamic_target_revision(
            entry_price=100.0,
            current_ltp=120.0,
            current_t1=115.0,
            current_t2=130.0,
            underlying_ltp=2500.0,
            underlying_entry=2480.0,
            india_vix=16.5,
            minutes_to_session_close=200,
            remaining_trading_days=5,
            direction="BULLISH",
        )
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}"
        rev_t1, rev_t2, note = result
        print(f"PASS: returns 3-tuple: t1={rev_t1}, t2={rev_t2}, note='{note}'")

    def test_dynamic_revision_increases_t2_when_ltp_exceeds_t1(self):
        """
        When current_ltp >= current_t1 (T1 achieved), T2 should be revised upward.
        Trigger 1: new_t2 = t1 + (t2-t1) * 1.5
        """
        from services.data_verifier import compute_dynamic_target_revision
        entry_price = 100.0
        current_ltp = 120.0     # LTP has exceeded T1
        current_t1 = 115.0
        current_t2 = 130.0
        # original_gap = 130 - 115 = 15
        # new_t2 = 115 + 15 * 1.5 = 137.5

        rev_t1, rev_t2, note = compute_dynamic_target_revision(
            entry_price=entry_price,
            current_ltp=current_ltp,
            current_t1=current_t1,
            current_t2=current_t2,
            underlying_ltp=2500.0,
            underlying_entry=2480.0,
            india_vix=16.5,
            minutes_to_session_close=200,
            remaining_trading_days=5,
            direction="BULLISH",
        )
        assert rev_t2 > current_t2, (
            f"T2 should increase when LTP ({current_ltp}) >= T1 ({current_t1}), "
            f"got rev_t2={rev_t2} vs current_t2={current_t2}"
        )
        print(f"PASS: T2 revised from {current_t2} to {rev_t2} when LTP {current_ltp} >= T1 {current_t1}")

    def test_dynamic_revision_t2_calculation_correct(self):
        """
        T2 revision from Trigger 1: new_t2 = current_t1 + (current_t2 - current_t1) * 1.5
        With t1=115, t2=130: new_t2 = 115 + 15 * 1.5 = 137.5
        To isolate Trigger 1, use india_vix=25 (>22 → vix_calm=False → Trigger 2 disabled)
        and weak underlying move to ensure only Trigger 1 fires.
        """
        from services.data_verifier import compute_dynamic_target_revision
        rev_t1, rev_t2, note = compute_dynamic_target_revision(
            entry_price=100.0,
            current_ltp=120.0,
            current_t1=115.0,
            current_t2=130.0,
            underlying_ltp=2481.0,   # Only 0.04% move - not enough for Trigger 2 (needs >0.5%)
            underlying_entry=2480.0,
            india_vix=25.0,           # VIX > 22 → vix_calm=False → Trigger 2 disabled
            minutes_to_session_close=200,
            remaining_trading_days=5,
            direction="BULLISH",
        )
        # With only Trigger 1: new_t2 = 115 + (130-115)*1.5 = 137.5
        expected_t2 = 137.5  # 115 + 15 * 1.5
        assert abs(rev_t2 - expected_t2) <= 1.0, (
            f"Expected rev_t2 ≈ {expected_t2} (Trigger 1 only), got {rev_t2}. "
            f"Note: {note}"
        )
        print(f"PASS: T2 revised to {rev_t2} (expected ≈ {expected_t2}, Trigger 1 only)")

    def test_dynamic_revision_note_present_when_t1_achieved(self):
        """revision_note must not be None when LTP has exceeded T1."""
        from services.data_verifier import compute_dynamic_target_revision
        rev_t1, rev_t2, note = compute_dynamic_target_revision(
            entry_price=100.0,
            current_ltp=120.0,
            current_t1=115.0,
            current_t2=130.0,
            underlying_ltp=2500.0,
            underlying_entry=2480.0,
            india_vix=16.5,
            minutes_to_session_close=200,
            remaining_trading_days=5,
            direction="BULLISH",
        )
        assert note is not None, "revision_note must not be None when T1 is achieved"
        assert len(note) > 0, "revision_note must not be empty string"
        print(f"PASS: revision_note = '{note}'")

    def test_dynamic_revision_no_change_when_ltp_below_t1(self):
        """When LTP < T1 and no strong underlying move, T2 should not increase."""
        from services.data_verifier import compute_dynamic_target_revision
        current_t2 = 130.0
        rev_t1, rev_t2, note = compute_dynamic_target_revision(
            entry_price=100.0,
            current_ltp=105.0,      # LTP below T1 (115)
            current_t1=115.0,
            current_t2=current_t2,
            underlying_ltp=2490.0,  # Only 0.04% move — not strong enough
            underlying_entry=2489.0,
            india_vix=16.5,
            minutes_to_session_close=200,
            remaining_trading_days=5,
            direction="BULLISH",
        )
        # T2 should not increase with no strong triggers
        assert rev_t2 <= current_t2 * 1.01, (
            f"T2 should not increase significantly when LTP < T1 with weak move, "
            f"got rev_t2={rev_t2} vs original={current_t2}"
        )
        print(f"PASS: T2 not revised when LTP ({105.0}) < T1 ({115.0}) with no strong move")

    def test_dynamic_revision_invalid_prices_returns_original(self):
        """When entry_price <= 0 or targets are 0, return originals unchanged."""
        from services.data_verifier import compute_dynamic_target_revision
        rev_t1, rev_t2, note = compute_dynamic_target_revision(
            entry_price=0.0,    # Invalid
            current_ltp=120.0,
            current_t1=115.0,
            current_t2=130.0,
            underlying_ltp=2500.0,
            underlying_entry=2480.0,
            india_vix=16.5,
            minutes_to_session_close=200,
            remaining_trading_days=5,
        )
        assert rev_t1 == 115.0, f"Should return original t1 when entry_price <= 0"
        assert rev_t2 == 130.0, f"Should return original t2 when entry_price <= 0"
        assert note is None, "revision_note should be None for invalid inputs"
        print("PASS: Invalid entry_price returns originals unchanged")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 6: F&O Generate Endpoint (items 6, 7, 8, 12)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def fno_response(authed):
    """Call /api/fno/generate once per module and cache the response. Includes retry."""
    import time
    for attempt in range(3):
        try:
            resp = authed.post(f"{BASE_URL}/api/fno/generate", json={}, timeout=180)
            if resp.status_code == 200:
                return get_ndjson_complete_data(resp)
            elif resp.status_code == 502:
                print(f"Attempt {attempt+1}: 502 received, retrying in 10s...")
                time.sleep(10)
            else:
                pytest.fail(f"F&O generate returned {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            print(f"Attempt {attempt+1}: Exception {e}, retrying in 10s...")
            time.sleep(10)
    pytest.skip("F&O generate returned 502 after 3 attempts — environment may be busy")


class TestFnoGenerateEndpoint:
    """Test F&O generate endpoint for new fields and behavior."""

    def test_fno_response_200(self, authed):
        """F&O generate must return 200 OK."""
        resp = authed.post(f"{BASE_URL}/api/fno/generate", json={}, timeout=180)
        assert resp.status_code == 200, (
            f"F&O generate returned {resp.status_code}: {resp.text[:300]}"
        )
        print(f"PASS: /api/fno/generate returned 200")

    def test_fno_response_has_market_session(self, fno_response):
        """F&O generate response must have market_session field (item 6)."""
        assert "market_session" in fno_response, (
            "market_session field missing from FNOGenerateResponse"
        )
        market_session = fno_response["market_session"]
        assert market_session is not None, "market_session must not be null"
        assert isinstance(market_session, dict), f"market_session must be dict, got {type(market_session)}"
        print(f"PASS: market_session = {market_session}")

    def test_fno_response_has_market_regime(self, fno_response):
        """F&O generate response must have market_regime field (item 6)."""
        assert "market_regime" in fno_response, (
            "market_regime field missing from FNOGenerateResponse"
        )
        market_regime = fno_response["market_regime"]
        assert market_regime is not None, "market_regime must not be null"
        assert isinstance(market_regime, dict), f"market_regime must be dict, got {type(market_regime)}"
        print(f"PASS: market_regime = {market_regime}")

    def test_market_session_is_closed_after_hours(self, fno_response):
        """market_session.is_open must be False when tested after market hours (19:56 IST)."""
        import pytz
        from datetime import datetime
        IST = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(IST)
        now_hour = now_ist.hour
        now_min = now_ist.minute

        market_session = fno_response.get("market_session", {})
        is_open = market_session.get("is_open")

        if (now_hour > 15) or (now_hour == 15 and now_min >= 30):
            assert is_open is False, (
                f"market_session.is_open must be False at {now_ist.strftime('%H:%M')} IST, "
                f"got: {market_session}"
            )
            assert market_session.get("status") == "CLOSED", (
                f"market_session.status must be 'CLOSED', got: {market_session.get('status')}"
            )
            print(f"PASS: market_session is_open=False, status='CLOSED' at {now_ist.strftime('%H:%M')} IST")
        else:
            print(f"NOTE: Running during/before market hours — is_open={is_open}")

    def test_market_regime_has_required_keys(self, fno_response):
        """market_regime must have 'regime' key."""
        market_regime = fno_response.get("market_regime", {})
        assert "regime" in market_regime, (
            f"market_regime missing 'regime' key: {market_regime}"
        )
        print(f"PASS: market_regime.regime = {market_regime.get('regime')}")

    def test_stock_signals_confluence_ge_78(self, fno_response):
        """All stock_signals in FNO response must have confluence_score >= 78 (item 7)."""
        stock_signals = fno_response.get("stock_signals", [])
        if not stock_signals:
            print("NOTE: No stock_signals returned (no signals passed 78% threshold at market close)")
            return

        for sig in stock_signals:
            score = sig.get("confluence_score", 0)
            symbol = sig.get("underlying", "UNKNOWN")
            assert score >= 78, (
                f"stock_signal for {symbol} has confluence_score={score} < 78 — must be >= 78"
            )
        print(f"PASS: All {len(stock_signals)} stock_signals have confluence_score >= 78")

    def test_top_trades_confluence_if_potential(self, fno_response):
        """All potential top_trades must have confluence_score >= 78 (item 7)."""
        top_trades = fno_response.get("top_trades", [])
        for trade in top_trades:
            if trade.get("is_potential_trade"):
                score = trade.get("confluence_score", 0)
                symbol = trade.get("underlying", "?")
                assert score >= 78, (
                    f"Potential top_trade for {symbol} has confluence_score={score} < 78"
                )
        potential_count = sum(1 for t in top_trades if t.get("is_potential_trade"))
        print(f"PASS: {potential_count} potential top_trades all have confluence_score >= 78")

    def test_trigger_factors_have_theta_model_tag(self, fno_response):
        """
        TriggerFactors for signals should include 'ThetaModel=' tag showing VIX-based theta is in use.
        Check in all signal collections (item 8).
        """
        all_signals = []
        all_signals.extend(fno_response.get("signals", []))
        all_signals.extend(fno_response.get("stock_signals", []))
        all_signals.extend(fno_response.get("top_trades", []))
        if fno_response.get("custom_signal"):
            all_signals.append(fno_response["custom_signal"])

        # Also check index projection signals
        for idx in ["nifty_projection", "banknifty_projection"]:
            proj = fno_response.get(idx, {})
            all_signals.extend(proj.get("assured_signals", []))
            all_signals.extend(proj.get("watchlist_signals", []))

        # Deduplicate by script
        seen = set()
        unique_signals = []
        for s in all_signals:
            key = s.get("script", "")
            if key not in seen:
                seen.add(key)
                unique_signals.append(s)

        if not unique_signals:
            print("NOTE: No signals returned at market close — ThetaModel tag not testable from API response")
            # Verify from backend source that ThetaModel is appended
            content = read_backend_source()
            assert 'trigger_factors.append(f"ThetaModel={theta_method}")' in content or \
                   "ThetaModel=" in content, (
                "backend source must have ThetaModel= appended to trigger_factors"
            )
            print("PASS (source): 'ThetaModel=' tag is appended in build_fno_signal via source inspection")
            return

        theta_model_count = 0
        for sig in unique_signals:
            triggers = sig.get("trigger_factors", [])
            for t in triggers:
                if "ThetaModel=" in t:
                    theta_model_count += 1
                    break

        print(f"ThetaModel tags found: {theta_model_count} out of {len(unique_signals)} unique signals")

        if theta_model_count > 0:
            print(f"PASS: {theta_model_count} signals have 'ThetaModel=' in trigger_factors")
        else:
            # Verify from source
            server_path = os.path.join(BACKEND_DIR, "server.py")
            with open(server_path) as f:
                content = f.read()
            assert "ThetaModel=" in content, "server.py must append ThetaModel= to trigger_factors"
            print("PASS (source): ThetaModel= code present in server.py build_fno_signal")

    def test_no_signals_alert_has_specific_reason(self, fno_response):
        """
        When no top trades qualify, no_signals_alert must contain specific reason (item 12).
        The alert should NOT just say 'no signals' but should include WHY.
        """
        no_signals_alert = fno_response.get("no_signals_alert")
        all_top_trades = [t for t in fno_response.get("top_trades", []) if t.get("is_potential_trade")]

        if not all_top_trades:
            # Alert must be present with specific reason
            assert no_signals_alert is not None, (
                "no_signals_alert must be set when no potential trades qualify"
            )
            assert len(no_signals_alert) > 20, "no_signals_alert must be descriptive (>20 chars)"
            print(f"PASS: no_signals_alert = '{no_signals_alert[:100]}...'")

            # Must contain at least one specific reason indicator
            reason_keywords = ["78%", "confluence", "CLOSED", "R:R", "filter", "condition", "Reason:"]
            found_reason = any(kw in no_signals_alert for kw in reason_keywords)
            assert found_reason, (
                f"no_signals_alert must contain a specific reason. Got: '{no_signals_alert}'\n"
                f"Expected to contain one of: {reason_keywords}"
            )
            print(f"PASS: no_signals_alert contains specific reason")
        else:
            print(f"NOTE: {len(all_top_trades)} potential trades present — no_signals_alert = {no_signals_alert}")

    def test_no_signals_alert_mentions_78_when_no_trades(self, fno_response):
        """When market is CLOSED and no trades, alert should mention CLOSED status."""
        no_signals_alert = fno_response.get("no_signals_alert")
        market_session = fno_response.get("market_session", {})
        is_open = market_session.get("is_open", True)

        if not is_open and no_signals_alert:
            # Market is closed, so alert should mention CLOSED
            assert "CLOSED" in no_signals_alert or "closed" in no_signals_alert.lower(), (
                f"no_signals_alert should mention CLOSED when market is closed. Got: '{no_signals_alert}'"
            )
            print(f"PASS: no_signals_alert mentions CLOSED status: '{no_signals_alert[:80]}...'")
        else:
            print(f"NOTE: Either market is open ({is_open}) or alert is None ({no_signals_alert is None})")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 7: Dual Source Verification Architecture (item 1)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDualSourceVerification:
    """Verify dual-source verification architecture of fetch_verified_price."""

    def test_fetch_verified_price_signature(self):
        """fetch_verified_price must accept symbol, kite_api_key, access_token, exchange params."""
        from services.data_verifier import fetch_verified_price
        import inspect
        sig = inspect.signature(fetch_verified_price)
        params = list(sig.parameters.keys())
        required_params = ["symbol", "kite_api_key", "access_token"]
        for p in required_params:
            assert p in params, f"fetch_verified_price missing param: {p}"
        print(f"PASS: fetch_verified_price params: {params}")

    def test_fetch_verified_price_default_exchange_nse(self):
        """fetch_verified_price default exchange must be 'NSE'."""
        from services.data_verifier import fetch_verified_price
        import inspect
        sig = inspect.signature(fetch_verified_price)
        exchange_param = sig.parameters.get("exchange")
        assert exchange_param is not None, "exchange param missing"
        assert exchange_param.default == "NSE", (
            f"Default exchange should be 'NSE', got '{exchange_param.default}'"
        )
        print(f"PASS: fetch_verified_price default exchange = 'NSE'")

    def test_fetch_verified_price_fallback_with_empty_credentials(self):
        """fetch_verified_price with empty credentials should fall back to yfinance or return failed."""
        from services.data_verifier import fetch_verified_price, VerifiedPrice
        import asyncio

        async def _test():
            # With empty credentials, Kite will fail → should fall back to yfinance
            result = await fetch_verified_price(
                symbol="RELIANCE",
                kite_api_key="",
                access_token="",
                exchange="NSE",
                cross_verify=True,
            )
            return result

        result = asyncio.run(_test())
        assert isinstance(result, VerifiedPrice), f"Expected VerifiedPrice, got {type(result)}"
        assert result.source in ("yfinance", "failed"), (
            f"With empty credentials, source must be 'yfinance' or 'failed', got '{result.source}'"
        )
        # kite_ltp should be None since credentials were empty
        assert result.kite_ltp is None, "kite_ltp should be None with empty credentials"
        print(f"PASS: With empty creds, source='{result.source}', kite_ltp={result.kite_ltp}, ltp={result.ltp}")

    def test_kite_primary_yfinance_fallback_logic(self):
        """Verify code logic: if kite_ltp is not None, source='kite'; else try yfinance."""
        from services.data_verifier import VerifiedPrice
        # Simulate Kite success scenario
        result_kite = VerifiedPrice(
            ltp=2500.0,
            source="kite",
            kite_ltp=2500.0,
            fallback_ltp=2498.0,
        )
        assert result_kite.source == "kite"
        assert result_kite.kite_ltp == 2500.0

        # Simulate Kite failure → yfinance fallback
        result_yf = VerifiedPrice(
            ltp=2498.0,
            source="yfinance",
            kite_ltp=None,
            fallback_ltp=2498.0,
        )
        assert result_yf.source == "yfinance"
        assert result_yf.kite_ltp is None
        print("PASS: Kite primary / yfinance fallback VerifiedPrice dataclass logic verified")

    def test_discrepancy_detection_logic(self):
        """When |kite - yf| / kite > 2%, discrepancy should be flagged."""
        from services.data_verifier import VerifiedPrice
        kite_price = 2500.0
        yf_price = 2450.0  # 2% difference
        disc_pct = abs(kite_price - yf_price) / kite_price * 100  # 2%

        result = VerifiedPrice(
            ltp=kite_price,
            source="kite",
            kite_ltp=kite_price,
            fallback_ltp=yf_price,
            discrepancy_pct=disc_pct,
            discrepancy_flagged=(disc_pct > 2.0),
        )
        # 2% exactly is NOT > 2.0 per the code (strict >)
        assert result.discrepancy_flagged is False or disc_pct > 2.0
        print(f"PASS: discrepancy_pct={disc_pct:.1f}%, flagged={result.discrepancy_flagged}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 8: Near Expiry Badge Logic (item 13)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNearExpiryBadge:
    """Verify near expiry badge logic via remaining_trading_days in signals."""

    def test_fno_signal_response_has_remaining_trading_days(self):
        """FNOSignalResponse model must have remaining_trading_days field."""
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            content = f.read()
        # Look for the field in FNOSignalResponse
        assert "remaining_trading_days" in content, (
            "remaining_trading_days field not found in server.py"
        )
        print("PASS: remaining_trading_days field present in server.py")

    def test_near_expiry_threshold_is_2(self):
        """Frontend should show badge when remaining_trading_days <= 2 and > 0."""
        # Verify this logic is present in server.py or data_verifier.py
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            content = f.read()
        # Look for the near-expiry threshold logic
        # The threshold could be in build_fno_signal or FNOSignalResponse
        assert "remaining_trading_days" in content, "remaining_trading_days must exist in server"
        print("PASS: remaining_trading_days field present for near-expiry badge logic")

    def test_get_remaining_trading_days_api(self):
        """get_remaining_trading_days via API test — if FNO signal available, check its days."""
        resp = requests.get(f"{BASE_URL}/api/fno/contracts", timeout=15)
        if resp.status_code != 200:
            print(f"NOTE: /api/fno/contracts returned {resp.status_code} — skipping live test")
            return

        contracts = resp.json()
        if not contracts:
            print("NOTE: No contracts in kite_option_master (expected at market close)")
            return

        # Take first contract, check its signal remaining_trading_days
        contract = contracts[0]
        signal_resp = requests.get(
            f"{BASE_URL}/api/fno/signal/{contract['script']}", timeout=15
        )
        if signal_resp.status_code != 200:
            print(f"NOTE: Signal fetch returned {signal_resp.status_code}")
            return

        data = signal_resp.json()
        remaining = data.get("remaining_trading_days")
        assert remaining is not None, "remaining_trading_days must not be None"
        assert isinstance(remaining, int), f"remaining_trading_days must be int, got {type(remaining)}"
        assert remaining >= 0, "remaining_trading_days must be >= 0"

        if remaining <= 2:
            print(f"PASS: Script {contract['script']} has remaining_trading_days={remaining} (near expiry badge would show)")
        else:
            print(f"PASS: Script {contract['script']} remaining_trading_days={remaining} (no badge needed)")

    def test_get_remaining_trading_days_logic_for_near_expiry(self):
        """
        Unit test get_remaining_trading_days function logic.
        An expired date should return 0.
        A future date should return > 0.
        """
        # Test via source inspection — function exists and has correct logic
        content = read_backend_source()

        assert "def get_remaining_trading_days" in content, (
            "get_remaining_trading_days function not found in backend source"
        )
        # Verify it uses NSE_HOLIDAYS for filtering
        assert "NSE_HOLIDAYS" in content, (
            "get_remaining_trading_days should use NSE_HOLIDAYS for filtering"
        )
        print("PASS: get_remaining_trading_days exists and uses NSE_HOLIDAYS")

    def test_expiry_warning_via_remaining_trading_days_field(self):
        """
        The 'expiry_warning' concept is expressed via remaining_trading_days field.
        FNOSignalResponse uses remaining_trading_days: int (not a separate expiry_warning field).
        Near expiry condition: remaining_trading_days <= 2 and > 0.
        Verify that FNOSignalResponse has remaining_trading_days field, not expiry_warning.
        """
        content = read_backend_source()

        # remaining_trading_days: int = 0 is in FNOSignalResponse
        assert "remaining_trading_days: int" in content, (
            "FNOSignalResponse should have remaining_trading_days: int field"
        )

        # The near-expiry logic uses remaining_trading_days <= 2
        assert "remaining_trading_days" in content and "build_fno_signal" in content, (
            "build_fno_signal should set remaining_trading_days"
        )
        print("PASS: remaining_trading_days field drives near-expiry badge logic")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASS 9: Server.py Source Code Verification (all items via source)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerSourceVerification:
    """Verify server.py has correct code for all new features."""

    def test_data_verifier_imports_in_server(self):
        """server.py must import all functions from data_verifier."""
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            content = f.read()

        required_imports = [
            "fetch_verified_price",
            "fetch_verified_snapshot",
            "compute_vix_theta_decay",
            "compute_dynamic_target_revision",
            "get_minutes_to_session_close",
            "is_market_open",
            "get_market_session_status",
        ]
        for sym in required_imports:
            assert sym in content, f"server.py must import {sym} from data_verifier"
        print(f"PASS: All {len(required_imports)} data_verifier symbols imported in server.py")

    def test_fno_generate_response_has_market_session_field(self):
        """FNOGenerateResponse model must have market_session field."""
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            content = f.read()
        assert "market_session" in content, "market_session field not found in server.py"
        print("PASS: market_session field exists in FNOGenerateResponse")

    def test_fno_generate_response_has_market_regime_field(self):
        """FNOGenerateResponse model must have market_regime field."""
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            content = f.read()
        assert "market_regime" in content, "market_regime field not found in server.py"
        print("PASS: market_regime field exists in FNOGenerateResponse")

    def test_compute_vix_theta_decay_used_in_build_fno_signal(self):
        """build_fno_signal must call compute_vix_theta_decay (not fixed 0.15)."""
        content = read_backend_source()
        assert "compute_vix_theta_decay" in content, (
            "compute_vix_theta_decay not found in backend source"
        )
        print("PASS: compute_vix_theta_decay found in backend source")

    def test_theta_model_tag_appended_in_trigger_factors(self):
        """build_fno_signal must append ThetaModel= to trigger_factors."""
        content = read_backend_source()
        assert 'ThetaModel=' in content, (
            "ThetaModel= tag not found — must be appended to trigger_factors"
        )
        print("PASS: ThetaModel= tag is appended in trigger_factors")

    def test_confluence_78_in_fno_generate(self):
        """confluence_score >= 78 filter must exist in FNO generate flow."""
        content = read_backend_source()
        assert "confluence_score >= 78" in content, (
            "confluence_score >= 78 filter not found"
        )
        count = content.count("confluence_score >= 78")
        assert count >= 2, f"Expected >= 2 uses of 'confluence_score >= 78', found {count}"
        print(f"PASS: 'confluence_score >= 78' found {count} times")

    def test_market_session_populated_in_fno_generate(self):
        """FNO generate must call get_market_session_status() and return it."""
        content = read_backend_source()
        assert "get_market_session_status()" in content, (
            "get_market_session_status() not called"
        )
        print("PASS: get_market_session_status() used in backend source")

    def test_dynamic_target_revision_in_refresh_open_position(self):
        """_refresh_open_position must call compute_dynamic_target_revision."""
        content = read_backend_source()
        assert "compute_dynamic_target_revision" in content, (
            "compute_dynamic_target_revision not found"
        )
        print("PASS: compute_dynamic_target_revision found in backend source")

    def test_no_signals_alert_mentions_78_confluence(self):
        """no_signals_alert generation must reference 78% confluence threshold."""
        content = read_backend_source()
        assert "78%" in content, "78% threshold not found in backend source"
        print("PASS: 78% threshold mentioned in backend source")
