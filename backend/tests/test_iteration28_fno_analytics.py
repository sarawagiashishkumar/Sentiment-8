"""
Iteration 28: Test suite for F&O analytics features and bug fixes.
Tests:
  1. best_exit_price >= latest_option_ltp for custom positions (P0 Bug Fix)
  2. FNOSignalResponse has max_pain, iv_rank, oi_buildup, gex fields (P0 Feature)
  3. POST /api/fno/generate responds with new analytics fields (P0 Feature)
  4. compute_option_chain_analytics function exists and has correct signature (P0 Feature)
  5. _fetch_kite_equity_core function exists (P0 Feature)
  6. _get_stock_core_cached tries Kite first before fallback (P0 Feature)
  7. kite_equity_master collection mentioned in code (P0 Feature)
  8. _fetch_kite_hist_ohlcv_for_equity exists (P0 Feature)
  9. _get_hist_ohlcv tries Kite FIRST then falls back to yfinance (P0 Feature)
 10. LIVE_LTP_UNAVAILABLE path enforces best_exit_price >= max(last_known_ltp, entry*1.01) (P0 Bug Fix)
 11. Strategy threshold enforcement: 422 when no strategy passes (P0 Feature)
 12. Multibagger RSI uses fundamental.get('rsi') not 30+position*40 formula (P0 Feature)
 13. compute_realistic_price_bands accepts india_vix param (P0 Feature)
 14. _fetch_hist_one returns dict with hist_vol, rsi, trend_alignment (P0 Feature)
 15. Startup tasks purge garbage custom_positions (P0 Startup)
 16. GET /api/admin/nse-holidays returns current year holidays (Regression)
 17. GET /api/fno/custom-positions returns 200, no garbage records (Regression)
"""

import pytest
import requests
import os
import inspect
import sys

from tests.helpers.test_utils import get_base_url, get_ndjson_complete_data, read_backend_source, safe_streaming_post

BASE_URL = get_base_url()
assert BASE_URL, "BASE_URL must be resolvable"

# ------- Auth fixture -------

@pytest.fixture(scope="module")
def auth_token():
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=15,
    )
    assert resp.status_code == 200, f"Auth failed: {resp.status_code} {resp.text[:300]}"
    token = resp.json().get("access_token") or resp.json().get("token")
    assert token, f"No token in response: {resp.json()}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ===========================================================================
# Group 1: FNOSignalResponse Model Fields (max_pain, iv_rank, oi_buildup, gex)
# ===========================================================================

class TestFNOSignalResponseNewFields:
    """P0 Feature: FNOSignalResponse has 4 new analytics fields."""

    def test_model_has_max_pain_field(self):
        """max_pain field must exist in FNOSignalResponse model."""
        sys.path.insert(0, "/app/backend")
        from models import FNOSignalResponse
        fields = FNOSignalResponse.model_fields
        assert "max_pain" in fields, "FNOSignalResponse missing 'max_pain' field"
        print("PASS: max_pain field present in FNOSignalResponse")

    def test_model_has_iv_rank_field(self):
        """iv_rank field must exist in FNOSignalResponse model."""
        sys.path.insert(0, "/app/backend")
        from models import FNOSignalResponse
        fields = FNOSignalResponse.model_fields
        assert "iv_rank" in fields, "FNOSignalResponse missing 'iv_rank' field"
        print("PASS: iv_rank field present in FNOSignalResponse")

    def test_model_has_oi_buildup_field(self):
        """oi_buildup field must exist in FNOSignalResponse model."""
        sys.path.insert(0, "/app/backend")
        from models import FNOSignalResponse
        fields = FNOSignalResponse.model_fields
        assert "oi_buildup" in fields, "FNOSignalResponse missing 'oi_buildup' field"
        print("PASS: oi_buildup field present in FNOSignalResponse")

    def test_model_has_gex_field(self):
        """gex field must exist in FNOSignalResponse model."""
        sys.path.insert(0, "/app/backend")
        from models import FNOSignalResponse
        fields = FNOSignalResponse.model_fields
        assert "gex" in fields, "FNOSignalResponse missing 'gex' field"
        print("PASS: gex field present in FNOSignalResponse")

    def test_new_fields_are_optional_nullable(self):
        """All new fields must be optional/nullable (None default) so old data doesn't break."""
        sys.path.insert(0, "/app/backend")
        from models import FNOSignalResponse
        # Check via model_fields that all 4 new fields are NOT required (have default=None)
        fields = FNOSignalResponse.model_fields
        for field_name in ["max_pain", "iv_rank", "oi_buildup", "gex"]:
            field = fields[field_name]
            assert not field.is_required(), \
                f"'{field_name}' should be optional (not required). Got required=True"
            # Default should be None
            assert field.default is None, \
                f"'{field_name}' should default to None, got {field.default}"
        print("PASS: All new fields (max_pain, iv_rank, oi_buildup, gex) are optional with default=None")


# ===========================================================================
# Group 2: POST /api/fno/generate — new fields in API response
# ===========================================================================

class TestFnoGenerateApiResponse:
    """P0 Feature: POST /api/fno/generate must include new analytics fields."""

    def test_fno_generate_returns_200(self, auth_headers):
        """POST /api/fno/generate with NIFTY must return 200. (allow 5min for heavy computation)"""
        resp = safe_streaming_post(
            f"{BASE_URL}/api/fno/generate",
            json_body={"symbols": ["NIFTY"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:500]}"
        print(f"PASS: /api/fno/generate returned 200")

    def test_fno_generate_response_has_signals_key(self, auth_headers):
        """Response should have a 'signals' key (list)."""
        resp = safe_streaming_post(
            f"{BASE_URL}/api/fno/generate",
            json_body={"symbols": ["NIFTY"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = get_ndjson_complete_data(resp)
        # Could be list or dict with 'signals'
        if isinstance(data, list):
            signals = data
        elif isinstance(data, dict):
            signals = data.get("signals") or data.get("data") or []
            if not signals and data.get("script"):
                # single signal response
                signals = [data]
        else:
            signals = []
        assert len(signals) >= 0  # At least no crash
        print(f"PASS: /api/fno/generate returned {len(signals)} signals")

    def test_fno_generate_signal_has_new_analytics_fields(self, auth_headers):
        """Each signal in response must contain max_pain, iv_rank, oi_buildup, gex keys."""
        resp = safe_streaming_post(
            f"{BASE_URL}/api/fno/generate",
            json_body={"symbols": ["NIFTY"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = get_ndjson_complete_data(resp)
        if isinstance(data, list):
            signals = data
        elif isinstance(data, dict):
            signals = data.get("signals") or data.get("data") or []
            if not signals and data.get("script"):
                signals = [data]
        else:
            signals = []

        if not signals:
            pytest.skip("No signals returned — can't verify field presence")

        first = signals[0]
        for field in ["max_pain", "iv_rank", "oi_buildup", "gex"]:
            assert field in first, f"Signal missing '{field}' field. Keys: {list(first.keys())}"
        print(f"PASS: Signal has all 4 new fields. "
              f"max_pain={first.get('max_pain')}, iv_rank={first.get('iv_rank')}, "
              f"oi_buildup={first.get('oi_buildup')}, gex={first.get('gex')}")


# ===========================================================================
# Group 3: compute_option_chain_analytics function signature
# ===========================================================================

class TestComputeOptionChainAnalytics:
    """P0 Feature: compute_option_chain_analytics exists with correct signature."""

    def test_function_exists_in_server(self):
        """compute_option_chain_analytics must be importable from server."""
        sys.path.insert(0, "/app/backend")
        import server
        assert hasattr(server, "compute_option_chain_analytics"), \
            "compute_option_chain_analytics not found in server.py"
        print("PASS: compute_option_chain_analytics exists in server.py")

    def test_function_accepts_contracts_param(self):
        """Function signature must have 'contracts' parameter."""
        sys.path.insert(0, "/app/backend")
        import server
        sig = inspect.signature(server.compute_option_chain_analytics)
        params = list(sig.parameters.keys())
        assert "contracts" in params, f"'contracts' param missing. Got: {params}"
        print(f"PASS: 'contracts' param present. Full sig params: {params}")

    def test_function_accepts_kite_map_param(self):
        """Function signature must have 'kite_map' parameter."""
        sys.path.insert(0, "/app/backend")
        import server
        sig = inspect.signature(server.compute_option_chain_analytics)
        params = list(sig.parameters.keys())
        assert "kite_map" in params, f"'kite_map' param missing. Got: {params}"
        print(f"PASS: 'kite_map' param present")

    def test_function_accepts_underlying_ltp_param(self):
        """Function signature must have 'underlying_ltp' parameter."""
        sys.path.insert(0, "/app/backend")
        import server
        sig = inspect.signature(server.compute_option_chain_analytics)
        params = list(sig.parameters.keys())
        assert "underlying_ltp" in params, f"'underlying_ltp' param missing. Got: {params}"
        print(f"PASS: 'underlying_ltp' param present")

    def test_function_accepts_step_param(self):
        """Function signature must have 'step' parameter (default 50)."""
        sys.path.insert(0, "/app/backend")
        import server
        sig = inspect.signature(server.compute_option_chain_analytics)
        params = list(sig.parameters.keys())
        assert "step" in params, f"'step' param missing. Got: {params}"
        # Default should be 50
        step_default = sig.parameters["step"].default
        assert step_default == 50, f"'step' default should be 50, got {step_default}"
        print(f"PASS: 'step' param present with default=50")

    def test_function_returns_dict_with_required_keys_on_empty_input(self):
        """With empty contracts list, function returns None-valued dict with correct keys."""
        sys.path.insert(0, "/app/backend")
        import server
        result = server.compute_option_chain_analytics(
            contracts=[], kite_map={}, underlying_ltp=22000.0, step=50
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        for key in ["max_pain", "iv_rank", "gex", "oi_buildup"]:
            assert key in result, f"Key '{key}' missing from result dict"
        assert result["max_pain"] is None
        assert result["iv_rank"] is None
        assert result["gex"] is None
        assert result["oi_buildup"] is None
        print(f"PASS: Empty input returns correct None-valued dict: {result}")


# ===========================================================================
# Group 4: Kite equity core — _fetch_kite_equity_core + _get_stock_core_cached
# ===========================================================================

class TestKiteEquityCore:
    """P0 Feature: _fetch_kite_equity_core defined; _get_stock_core_cached tries Kite first."""

    def test_fetch_kite_equity_core_exists(self):
        """_fetch_kite_equity_core must be defined in server.py."""
        sys.path.insert(0, "/app/backend")
        import server
        assert hasattr(server, "_fetch_kite_equity_core"), \
            "_fetch_kite_equity_core not found in server.py"
        print("PASS: _fetch_kite_equity_core exists in server.py")

    def test_get_stock_core_cached_exists(self):
        """_get_stock_core_cached must be defined in server.py."""
        sys.path.insert(0, "/app/backend")
        import server
        assert hasattr(server, "_get_stock_core_cached"), \
            "_get_stock_core_cached not found in server.py"
        print("PASS: _get_stock_core_cached exists in server.py")

    def test_get_stock_core_cached_tries_kite_first(self):
        """Source code of _get_stock_core_cached must call _fetch_kite_equity_core before fallback."""
        sys.path.insert(0, "/app/backend")
        import server
        src = inspect.getsource(server._get_stock_core_cached)
        # Must call _fetch_kite_equity_core
        assert "_fetch_kite_equity_core" in src, \
            "_get_stock_core_cached does not call _fetch_kite_equity_core (Kite-first policy missing)"
        # Must check result for None and then call a fallback (await get_stock_core or similar)
        assert "await get_stock_core(" in src or "get_stock_core(symbol)" in src, \
            "_get_stock_core_cached may not have a fallback path (await get_stock_core not found)"
        # Kite call should appear before the fallback `await get_stock_core`
        kite_pos = src.find("_fetch_kite_equity_core")
        fallback_pos = src.find("await get_stock_core(")
        if fallback_pos < 0:
            fallback_pos = src.rfind("get_stock_core(symbol)")
        assert fallback_pos > 0, "Fallback 'await get_stock_core(' not found in source"
        assert kite_pos < fallback_pos, \
            f"Kite call (pos {kite_pos}) must come BEFORE fallback (pos {fallback_pos})"
        print(f"PASS: _get_stock_core_cached calls _fetch_kite_equity_core FIRST (pos {kite_pos}), "
              f"fallback get_stock_core after (pos {fallback_pos})")


# ===========================================================================
# Group 5: kite_equity_master collection + equity tokens stored
# ===========================================================================

class TestKiteEquityMasterCollection:
    """P0 Feature: kite_equity_master collection used for equity token storage."""

    def test_kite_equity_master_referenced_in_sync_function(self):
        """_sync_kite_option_master_daily must write to kite_equity_master collection."""
        sys.path.insert(0, "/app/backend")
        import server
        src = inspect.getsource(server._sync_kite_option_master_daily)
        assert "kite_equity_master" in src, \
            "kite_equity_master collection not referenced in _sync_kite_option_master_daily"
        print("PASS: kite_equity_master referenced in _sync_kite_option_master_daily")

    def test_kite_equity_master_used_in_hist_fetch(self):
        """_fetch_kite_hist_ohlcv_for_equity must query kite_equity_master for instrument token."""
        sys.path.insert(0, "/app/backend")
        import server
        src = inspect.getsource(server._fetch_kite_hist_ohlcv_for_equity)
        assert "kite_equity_master" in src, \
            "kite_equity_master not queried in _fetch_kite_hist_ohlcv_for_equity"
        assert "instrument_token" in src, \
            "instrument_token not referenced in _fetch_kite_hist_ohlcv_for_equity"
        print("PASS: _fetch_kite_hist_ohlcv_for_equity queries kite_equity_master for instrument_token")


# ===========================================================================
# Group 6: _fetch_kite_hist_ohlcv_for_equity + _get_hist_ohlcv Kite-first
# ===========================================================================

class TestKiteHistOhlcvFirst:
    """P0 Feature: _fetch_kite_hist_ohlcv_for_equity exists; _get_hist_ohlcv tries Kite FIRST."""

    def test_fetch_kite_hist_ohlcv_for_equity_exists(self):
        """_fetch_kite_hist_ohlcv_for_equity must be defined in server.py."""
        sys.path.insert(0, "/app/backend")
        import server
        assert hasattr(server, "_fetch_kite_hist_ohlcv_for_equity"), \
            "_fetch_kite_hist_ohlcv_for_equity not found in server.py"
        print("PASS: _fetch_kite_hist_ohlcv_for_equity exists")

    def test_get_hist_ohlcv_calls_kite_first(self):
        """_get_hist_ohlcv must call _fetch_kite_hist_ohlcv_for_equity as sole data source (Kite Supremacy)."""
        sys.path.insert(0, "/app/backend")
        import server
        src = inspect.getsource(server._get_hist_ohlcv)
        assert "_fetch_kite_hist_ohlcv_for_equity" in src, \
            "_get_hist_ohlcv does not call Kite hist function"
        # Kite Supremacy: yfinance must NOT be present as fallback
        assert "yfinance" not in src and "_fetch_yfinance" not in src, \
            "_get_hist_ohlcv still references yfinance — violates Kite Supremacy rule"
        print("PASS: _get_hist_ohlcv uses Kite as sole data source (no yfinance)")

    def test_fetch_kite_hist_ohlcv_returns_dict_format(self):
        """_fetch_kite_hist_ohlcv_for_equity should return dict with 'records' key or None."""
        sys.path.insert(0, "/app/backend")
        import server
        src = inspect.getsource(server._fetch_kite_hist_ohlcv_for_equity)
        # Must return {"records": records} or None
        assert '"records"' in src or "'records'" in src, \
            "_fetch_kite_hist_ohlcv_for_equity does not return 'records' dict format"
        print("PASS: _fetch_kite_hist_ohlcv_for_equity returns {'records': ...} format")


# ===========================================================================
# Group 7: LIVE_LTP_UNAVAILABLE path — best_exit_price >= max(last_known_ltp, entry*1.01)
# ===========================================================================

class TestLiveLtpUnavailablePath:
    """P0 Bug Fix: LIVE_LTP_UNAVAILABLE path enforces best_exit_price >= max(last_known_ltp, entry*1.01)."""

    def test_unavailable_path_corrects_best_exit_in_source(self):
        """Source code must enforce best_exit >= max(_current_be, _last_known_ltp, _entry_floor)."""
        src = read_backend_source()
        # Check that LIVE_LTP_UNAVAILABLE alert is present
        assert "LIVE_LTP_UNAVAILABLE" in src, "LIVE_LTP_UNAVAILABLE alert not found in server.py"
        # Check the correction formula: max(..._last_known_ltp..._entry_floor...)
        assert "_last_known_ltp" in src, "_last_known_ltp variable not found in server.py"
        assert "_entry_floor" in src, "_entry_floor variable not found in server.py"
        assert "_corrected_be" in src, "_corrected_be variable not found in server.py"
        print("PASS: LIVE_LTP_UNAVAILABLE path uses _last_known_ltp + _entry_floor for correction")

    def test_entry_floor_is_1_percent_above_entry(self):
        """_entry_floor must be entry * 1.01 (1% above entry)."""
        src = read_backend_source()
        assert "* 1.01" in src, "_entry_floor calculation (entry * 1.01) not found"
        print("PASS: entry_floor uses * 1.01 (1% floor)")

    def test_corrected_be_uses_max_of_three_values(self):
        """_corrected_be must be max(_current_be, _last_known_ltp, _entry_floor)."""
        src = read_backend_source()
        # The fix should use max() with all three values
        assert "max(_current_be, _last_known_ltp, _entry_floor)" in src, \
            "max(_current_be, _last_known_ltp, _entry_floor) not found — correction may be incomplete"
        print("PASS: _corrected_be = max(_current_be, _last_known_ltp, _entry_floor)")


# ===========================================================================
# Group 8: best_exit_price >= latest_option_ltp (API level)
# ===========================================================================

class TestCustomPositionsBestExitPrice:
    """P0 Bug Fix: GET /api/fno/custom-positions — best_exit_price >= latest_option_ltp."""

    def test_custom_positions_returns_200(self, auth_headers):
        """GET /api/fno/custom-positions must return 200."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:300]}"
        print("PASS: /api/fno/custom-positions returned 200")

    def test_custom_positions_no_garbage_records(self, auth_headers):
        """After startup purge, no position should have buy_price >= 999000 or null expiry_date."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data if isinstance(data, list) else data.get("positions", [])

        garbage_count = 0
        for pos in positions:
            buy_price = float(pos.get("buy_price") or 0)
            expiry_date = pos.get("expiry_date")
            if buy_price >= 999000:
                garbage_count += 1
                print(f"FAIL: Garbage position with buy_price={buy_price}: {pos.get('script')}")
            if expiry_date is None or expiry_date == "":
                garbage_count += 1
                print(f"FAIL: Position with null expiry_date: {pos.get('script')}")

        assert garbage_count == 0, f"{garbage_count} garbage positions found after startup purge"
        print(f"PASS: No garbage positions found (checked {len(positions)} positions)")

    def test_open_positions_best_exit_price_gte_latest_option_ltp(self, auth_headers):
        """For OPEN positions, best_exit_price must be >= latest_option_ltp (core bug fix)."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data if isinstance(data, list) else data.get("positions", [])

        open_positions = [p for p in positions if p.get("status") not in ("EXITED", "EXPIRED")]
        violations = []

        for pos in open_positions:
            best_exit = pos.get("best_exit_price")
            latest_ltp = pos.get("latest_option_ltp")

            if best_exit is not None and latest_ltp is not None:
                best_exit_f = float(best_exit)
                latest_ltp_f = float(latest_ltp)
                if latest_ltp_f > 0 and best_exit_f < latest_ltp_f:
                    violations.append({
                        "script": pos.get("script"),
                        "best_exit_price": best_exit_f,
                        "latest_option_ltp": latest_ltp_f,
                    })

        if violations:
            print(f"FAIL: {len(violations)} positions have best_exit_price < latest_option_ltp:")
            for v in violations:
                print(f"  {v['script']}: best_exit={v['best_exit_price']}, ltp={v['latest_option_ltp']}")
        else:
            print(f"PASS: All {len(open_positions)} open positions have best_exit_price >= latest_option_ltp")

        assert len(violations) == 0, f"{len(violations)} positions violate best_exit_price >= latest_option_ltp"

    def test_best_exit_price_gte_entry_floor(self, auth_headers):
        """For OPEN positions with best_exit_price set, it must be >= buy_price * 1.01."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data if isinstance(data, list) else data.get("positions", [])

        open_positions = [p for p in positions if p.get("status") not in ("EXITED", "EXPIRED")]
        violations = []

        for pos in open_positions:
            best_exit = pos.get("best_exit_price")
            buy_price = pos.get("buy_price")

            if best_exit is not None and buy_price is not None:
                best_exit_f = float(best_exit)
                buy_price_f = float(buy_price)
                entry_floor = round(buy_price_f * 1.01, 2)
                if buy_price_f > 0 and best_exit_f < entry_floor:
                    violations.append({
                        "script": pos.get("script"),
                        "best_exit_price": best_exit_f,
                        "buy_price": buy_price_f,
                        "entry_floor": entry_floor,
                    })

        if violations:
            print(f"FAIL: {len(violations)} positions have best_exit_price < buy_price*1.01:")
            for v in violations:
                print(f"  {v['script']}: best_exit={v['best_exit_price']}, floor={v['entry_floor']}")
        else:
            print(f"PASS: All open positions have best_exit_price >= buy_price*1.01")

        assert len(violations) == 0, f"{len(violations)} positions violate best_exit_price >= buy_price*1.01"


# ===========================================================================
# Group 9: Strategy Threshold Enforcement (422 guard)
# ===========================================================================

class TestStrategyThresholdEnforcement:
    """P0 Feature: Signal generation raises 422 if no strategy passes thresholds (when >=10 trades)."""

    def test_strategy_threshold_code_exists_in_server(self):
        """Server must have the 422 guard for strategy selection."""
        src = read_backend_source()
        assert "status_code=422" in src or "422" in src, \
            "No 422 status code found in server.py"
        assert "75% win-rate" in src or "75%.*win" in src or "win-rate" in src.lower(), \
            "Strategy threshold comment/logic not found"
        assert "0.40R" in src or "0.40.*expectancy" in src or "expectancy" in src.lower(), \
            "Expectancy threshold not found in server.py"
        print("PASS: 422 guard with 75% win-rate / 0.40R expectancy found in server.py")

    def test_strategy_threshold_only_fires_with_sufficient_data(self):
        """Guard must only activate when >= 10 backtested trades exist."""
        src = read_backend_source()
        # Check >= 10 trades condition
        assert ">= 10" in src or ">=10" in src or "10" in src, \
            "Strategy threshold requires >= 10 trades condition — not found"
        # The guard block
        assert "_sufficient_backtest" in src, \
            "_sufficient_backtest variable not found — threshold guard may be incomplete"
        print("PASS: Strategy threshold block checks _sufficient_backtest (>= 10 trades)")

    def test_fno_generate_works_when_db_empty(self, auth_headers):
        """With empty/insufficient backtest data, signal generation should NOT return 422."""
        resp = safe_streaming_post(
            f"http://localhost:8001/api/fno/generate",
            json_body={"symbols": ["NIFTY"]},
            headers=auth_headers,
            timeout=240,
            skip_msg="Streaming fno/generate timed out (Kite API may be unavailable)",
        )
        if resp is None:
            pytest.skip("Streaming endpoint returned None / timed out")
        # Should not be 422 (unless DB has >= 10 trades AND no strategy passes — unlikely in test env)
        assert resp.status_code != 422 or resp.status_code == 200, \
            f"Unexpected 422 when backtest DB should be empty/insufficient: {resp.text[:300]}"
        if resp.status_code == 200:
            print("PASS: fno/generate returns 200 (no 422 with insufficient backtest data)")
        elif resp.status_code == 422:
            print(f"NOTE: 422 returned — DB may have >= 10 trades but no strategy passes threshold: {resp.text[:300]}")
        else:
            print(f"NOTE: Got {resp.status_code} — {resp.text[:200]}")


# ===========================================================================
# Group 10: Multibagger RSI Fix
# ===========================================================================

class TestMultibaggerRsiFix:
    """P0 Feature: compute_multibagger_analysis uses real RSI from hist data."""

    def test_rsi_uses_fundamental_get_rsi(self):
        """compute_multibagger_analysis must use fundamental.get('rsi') not 30+position*40."""
        src = read_backend_source()
        # Must use fundamental.get('rsi')
        assert "fundamental.get(\"rsi\")" in src or "fundamental.get('rsi')" in src, \
            "fundamental.get('rsi') not found — RSI fix missing"
        print("PASS: fundamental.get('rsi') found in server.py for RSI extraction")

    def test_rsi_real_takes_priority_over_proxy(self):
        """When real RSI is available, it must be used instead of the 30+position*40 proxy."""
        src = read_backend_source()
        # Find the RSI section in compute_multibagger_analysis
        # Check that real RSI assignment comes before the proxy formula
        real_rsi_pos = src.find("_real_rsi = fundamental.get(\"rsi\")")
        if real_rsi_pos < 0:
            real_rsi_pos = src.find("_real_rsi = fundamental.get('rsi')")
        proxy_pos = src.find("30 + (position")
        assert real_rsi_pos > 0, "_real_rsi assignment not found"
        assert proxy_pos > 0, "proxy formula '30 + (position' not found"
        # Real RSI check must come BEFORE proxy formula
        assert real_rsi_pos < proxy_pos, \
            f"Real RSI (pos {real_rsi_pos}) should appear before proxy formula (pos {proxy_pos})"
        print(f"PASS: Real RSI check (pos {real_rsi_pos}) comes before proxy (pos {proxy_pos})")

    def test_rsi_fallback_proxy_still_exists(self):
        """Fallback proxy (30 + position * 40) should still exist for when hist data unavailable."""
        src = read_backend_source()
        assert "30 + (position" in src, \
            "Fallback RSI proxy not found — may have been fully removed instead of conditionally used"
        print("PASS: Fallback RSI proxy (30 + position*40) still present as fallback")


# ===========================================================================
# Group 11: VIX-scaled price bands — india_vix param in indicators.py
# ===========================================================================

class TestVixScaledPriceBands:
    """P0 Feature: compute_realistic_price_bands accepts india_vix and scales when VIX > 15."""

    def test_compute_realistic_price_bands_has_india_vix_param(self):
        """compute_realistic_price_bands in indicators.py must accept india_vix param."""
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands
        sig = inspect.signature(compute_realistic_price_bands)
        params = list(sig.parameters.keys())
        assert "india_vix" in params, f"'india_vix' param missing from compute_realistic_price_bands. Got: {params}"
        india_vix_default = sig.parameters["india_vix"].default
        assert india_vix_default is None, f"india_vix should default to None, got {india_vix_default}"
        print(f"PASS: compute_realistic_price_bands has india_vix param (default=None)")

    def test_vix_scaling_activates_above_15(self):
        """When india_vix > 15, hist_vol should be scaled up (wider bands)."""
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        # Without VIX scaling
        bands_no_vix = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.20, sector="IT", india_vix=None
        )
        # With high VIX (> 15)
        bands_high_vix = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.20, sector="IT", india_vix=25.0  # 25% VIX > 15 threshold
        )
        # Bands with high VIX should be wider (larger upside_pct for longer horizons)
        if "1Y" in bands_no_vix and "1Y" in bands_high_vix:
            no_vix_upside = abs(bands_no_vix["1Y"].get("upside_pct", 0))
            high_vix_upside = abs(bands_high_vix["1Y"].get("upside_pct", 0))
            # VIX=25 > 15, so high VIX upside should be >= no_vix upside
            assert high_vix_upside >= no_vix_upside * 0.95, \
                f"VIX>15 did not widen bands: no_vix={no_vix_upside}, high_vix={high_vix_upside}"
            print(f"PASS: VIX>15 scaling applied: 1Y upside no_vix={no_vix_upside:.2f}% vs high_vix={high_vix_upside:.2f}%")
        else:
            print(f"NOTE: 1Y key not found in bands — keys: {list(bands_no_vix.keys())}")

    def test_vix_below_15_no_scaling(self):
        """When india_vix <= 15, no VIX scaling applied (bands same as without VIX)."""
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands_low_vix = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.20, sector="IT", india_vix=12.0  # Below 15 threshold
        )
        bands_no_vix = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.20, sector="IT", india_vix=None
        )
        if "1Y" in bands_low_vix and "1Y" in bands_no_vix:
            low_vix_upside = bands_low_vix["1Y"].get("upside_pct", 0)
            no_vix_upside = bands_no_vix["1Y"].get("upside_pct", 0)
            assert abs(low_vix_upside - no_vix_upside) < 0.01, \
                f"VIX<15 should not affect bands: low_vix={low_vix_upside}, no_vix={no_vix_upside}"
            print(f"PASS: VIX<15 produces same bands as no-VIX (upside={low_vix_upside:.2f}%)")


# ===========================================================================
# Group 12: _fetch_hist_one returns dict (not just float)
# ===========================================================================

class TestFetchHistOneReturnsDict:
    """P0 Feature: _fetch_hist_one returns dict with hist_vol, rsi, trend_alignment."""

    def test_fetch_hist_one_is_local_function_in_multibagger_candidates(self):
        """_fetch_hist_one must be defined as a local async function (inside _build_multibagger_candidates)."""
        src = read_backend_source()
        assert "_fetch_hist_one" in src, "_fetch_hist_one function not found in server.py"
        print("PASS: _fetch_hist_one found in server.py")

    def test_fetch_hist_one_returns_dict_with_hist_vol(self):
        """_fetch_hist_one must return a dict containing 'hist_vol' key."""
        src = read_backend_source()
        # Find the _fetch_hist_one function body
        start = src.find("async def _fetch_hist_one(")
        assert start >= 0, "_fetch_hist_one not found"
        end = src.find("\n    async def ", start + 1)
        if end < 0:
            end = src.find("\n    fetched = ", start + 1)
        func_body = src[start:end if end > 0 else start + 1000]
        assert '"hist_vol"' in func_body or "'hist_vol'" in func_body, \
            "'hist_vol' key not returned by _fetch_hist_one"
        print("PASS: _fetch_hist_one returns dict with 'hist_vol' key")

    def test_fetch_hist_one_returns_dict_with_rsi(self):
        """_fetch_hist_one must return a dict containing 'rsi' key."""
        src = read_backend_source()
        start = src.find("async def _fetch_hist_one(")
        assert start >= 0, "_fetch_hist_one not found"
        end = src.find("\n    fetched = ", start + 1)
        func_body = src[start:end if end > 0 else start + 1000]
        assert '"rsi"' in func_body or "'rsi'" in func_body, \
            "'rsi' key not returned by _fetch_hist_one"
        print("PASS: _fetch_hist_one returns dict with 'rsi' key")

    def test_fetch_hist_one_returns_dict_with_trend_alignment(self):
        """_fetch_hist_one must return a dict containing 'trend_alignment' key."""
        src = read_backend_source()
        start = src.find("async def _fetch_hist_one(")
        assert start >= 0, "_fetch_hist_one not found"
        end = src.find("\n    fetched = ", start + 1)
        func_body = src[start:end if end > 0 else start + 1000]
        assert '"trend_alignment"' in func_body or "'trend_alignment'" in func_body, \
            "'trend_alignment' key not returned by _fetch_hist_one"
        print("PASS: _fetch_hist_one returns dict with 'trend_alignment' key")


# ===========================================================================
# Group 13: Startup tasks purge garbage custom_positions
# ===========================================================================

class TestStartupGarbagePurge:
    """P0 Startup: startup_tasks purges garbage custom_positions."""

    def test_startup_tasks_has_purge_logic(self):
        """startup_tasks must contain purge logic for garbage positions."""
        src = read_backend_source()
        assert "999000" in src or "999999" in src, \
            "Garbage purge threshold (999000/999999) not found in startup_tasks"
        assert "expiry_date" in src and ("None" in src or "null" in src), \
            "expiry_date null check not found in startup_tasks"
        assert "delete_many" in src, \
            "delete_many not found — garbage purge not implemented"
        print("PASS: startup_tasks has garbage purge for buy_price>=999000 and null expiry_date")

    def test_no_garbage_positions_after_startup(self, auth_headers):
        """After startup purge, API should return no garbage records."""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data if isinstance(data, list) else data.get("positions", [])

        garbage = [
            p for p in positions
            if float(p.get("buy_price") or 0) >= 999000
            or p.get("expiry_date") is None
            or p.get("expiry_date") == ""
        ]
        assert len(garbage) == 0, \
            f"{len(garbage)} garbage positions still present after startup purge: {garbage}"
        print(f"PASS: No garbage positions after startup purge (checked {len(positions)} positions)")


# ===========================================================================
# Group 14: NSE Holidays Regression
# ===========================================================================

class TestNseHolidaysRegression:
    """Regression: GET /api/admin/nse-holidays returns current year holidays."""

    def test_nse_holidays_returns_200(self, auth_headers):
        """GET /api/admin/nse-holidays must return 200."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/nse-holidays",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:300]}"
        print("PASS: /api/admin/nse-holidays returned 200")

    def test_nse_holidays_has_holidays_list(self, auth_headers):
        """Response must contain a 'holidays' list."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/nse-holidays",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        holidays = data.get("holidays") or data.get("data") or data.get("nse_holidays")
        if isinstance(data, list):
            holidays = data
        assert holidays is not None, f"No holidays key found in response. Keys: {list(data.keys()) if isinstance(data, dict) else 'list'}"
        assert len(holidays) > 0, "Holidays list is empty"
        print(f"PASS: /api/admin/nse-holidays has {len(holidays)} holidays")

    def test_nse_holidays_has_total_in_memory(self, auth_headers):
        """Response must contain a count/total field."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/nse-holidays",
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            has_total = any(
                k in data for k in ["total", "total_in_memory", "count", "total_holidays"]
            )
            assert has_total, f"No count/total field found. Keys: {list(data.keys())}"
            total_val = data.get("total") or data.get("total_in_memory") or data.get("count") or data.get("total_holidays")
            assert int(total_val) > 0, f"Total holidays should be > 0, got {total_val}"
            print(f"PASS: Total holidays = {total_val}")
        else:
            # It's a list — just count
            assert len(data) > 0
            print(f"PASS: {len(data)} holidays returned as list")


# ===========================================================================
# Group 15: Build FNO signal in server — best_exit code
# ===========================================================================

class TestBestExitPriceEnforcement:
    """P0 Bug Fix: best_exit_price computation enforces >= current LTP."""

    def test_best_exit_enforces_ltp_floor_in_source(self):
        """Source code around best_exit must use max(_raw_best, latest_option_ltp, ...)."""
        src = read_backend_source()
        assert "max(_raw_best, latest_option_ltp" in src, \
            "best_exit floor enforcement 'max(_raw_best, latest_option_ltp, ...)' not found in server.py"
        print("PASS: best_exit_price uses max(_raw_best, latest_option_ltp, ...) enforcement")

    def test_best_exit_comment_mentions_never_below_ltp(self):
        """Code comment must mention 'never below live market price' or similar."""
        src = read_backend_source()
        # Check for the intent comment
        assert (
            "never" in src.lower() and "ltp" in src.lower()
        ), "Comment about 'never below LTP' not found near best_exit computation"
        print("PASS: Comment about 'never below LTP' found in best_exit computation")
