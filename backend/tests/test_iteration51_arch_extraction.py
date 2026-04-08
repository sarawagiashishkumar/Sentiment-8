"""
Iteration 51: Architecture Hardening Phase 2 — Service Extraction Validation

Tests that all extracted modules (kite_client, fundamental_data, user_service, validators)
are importable and that server.py re-exports them correctly.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                    break
    except FileNotFoundError:
        pass
OWNER_USERNAME = "@shish123"
OWNER_PIN = "1234"


def _login():
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": OWNER_USERNAME, "pin": OWNER_PIN}, timeout=30)
    assert resp.status_code == 200
    return resp.json()["token"]


class TestExtractedModuleImports:
    """Verify that extracted service modules can be imported independently."""

    def test_kite_client_import(self):
        from services.kite_client import (
            _get_kite_access_token,
            _fetch_kite_equity_core,
            _sync_kite_option_master_daily,
            _resolve_verified_lot_size,
            _fetch_option_snapshots_from_kite,
            compute_option_chain_analytics,
            _fetch_kite_hist_ohlcv_for_equity,
            _fetch_live_option_snapshot,
            _fetch_live_option_ltp,
            _fetch_historical_candles_from_kite,
        )
        assert callable(_get_kite_access_token)
        assert callable(compute_option_chain_analytics)
        assert callable(_fetch_live_option_ltp)

    def test_fundamental_data_import(self):
        from services.fundamental_data import (
            _compute_piotroski_score_from_data,
            _compute_beneish_m_score_from_data,
            _fetch_yfinance_fundamentals,
            _get_fundamental_data,
        )
        assert callable(_compute_piotroski_score_from_data)
        assert callable(_get_fundamental_data)

    def test_user_service_import(self):
        from services.user_service import (
            _ensure_owner_exists,
            _get_user_by_key,
            _get_user_by_username,
            _get_user_by_ref,
            _is_owner,
            _is_admin,
            _is_credit_exempt,
            _consume_credits,
            _map_user_view,
        )
        assert callable(_ensure_owner_exists)
        assert callable(_map_user_view)

    def test_validators_import(self):
        from services.validators import (
            _validate_expiry_guard,
            _validate_username,
            _validate_domain,
            _split_domain_root_and_host,
            _normalize_target_record,
            _resolve_ipv4,
        )
        assert callable(_validate_expiry_guard)
        assert callable(_resolve_ipv4)


class TestServerReExports:
    """Verify that server.py re-exports extracted functions for backward compat."""

    def test_server_reexports_kite_client(self):
        import server
        assert hasattr(server, '_get_kite_access_token')
        assert hasattr(server, '_fetch_kite_equity_core')
        assert hasattr(server, 'compute_option_chain_analytics')
        assert hasattr(server, '_fetch_live_option_ltp')
        assert hasattr(server, '_fetch_historical_candles_from_kite')

    def test_server_reexports_fundamental_data(self):
        import server
        assert hasattr(server, '_compute_piotroski_score_from_data')
        assert hasattr(server, '_get_fundamental_data')

    def test_server_reexports_user_service(self):
        import server
        assert hasattr(server, '_ensure_owner_exists')
        assert hasattr(server, '_get_user_by_key')
        assert hasattr(server, '_map_user_view')
        assert hasattr(server, '_consume_credits')
        assert hasattr(server, '_is_owner')
        assert hasattr(server, '_is_admin')

    def test_server_reexports_validators(self):
        import server
        assert hasattr(server, '_validate_expiry_guard')
        assert hasattr(server, '_validate_username')
        assert hasattr(server, '_validate_domain')
        assert hasattr(server, '_resolve_ipv4')


class TestValidatorLogic:
    """Test validator pure functions directly."""

    def test_validate_expiry_guard_expired(self):
        from services.validators import _validate_expiry_guard
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_expiry_guard(0)
        assert exc_info.value.status_code == 400

    def test_validate_expiry_guard_too_close(self):
        from services.validators import _validate_expiry_guard
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_expiry_guard(10)
        assert exc_info.value.status_code == 400

    def test_validate_expiry_guard_ok(self):
        from services.validators import _validate_expiry_guard
        _validate_expiry_guard(60)  # Should not raise

    def test_validate_username_valid(self):
        from services.validators import _validate_username
        result = _validate_username("@shish123")
        assert result == "@shish123"

    def test_validate_username_invalid(self):
        from services.validators import _validate_username
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_username("abc")  # Too short

    def test_split_domain(self):
        from services.validators import _split_domain_root_and_host
        root, host = _split_domain_root_and_host("sub.example.com")
        assert root == "example.com"
        assert host == "sub"

    def test_resolve_ipv4_direct(self):
        from services.validators import _resolve_ipv4
        assert _resolve_ipv4("1.2.3.4") == "1.2.3.4"


class TestOptionChainAnalyticsPure:
    """Test compute_option_chain_analytics pure computation."""

    def test_empty_input(self):
        from services.kite_client import compute_option_chain_analytics
        result = compute_option_chain_analytics([], {}, 20000.0)
        assert result["max_pain"] is None
        assert result["pcr"] is None

    def test_basic_computation(self):
        from services.kite_client import compute_option_chain_analytics
        from types import SimpleNamespace

        contracts = [
            SimpleNamespace(script="CE_20000", strike=20000, option_type="CE"),
            SimpleNamespace(script="PE_20000", strike=20000, option_type="PE"),
            SimpleNamespace(script="CE_20100", strike=20100, option_type="CE"),
            SimpleNamespace(script="PE_19900", strike=19900, option_type="PE"),
        ]
        kite_map = {
            "CE_20000": {"oi": 10000, "ltp": 150, "gamma": 0.001, "iv": 18.5, "oi_day_low": 9000, "day_open": 140},
            "PE_20000": {"oi": 12000, "ltp": 120, "gamma": 0.001, "iv": 19.0, "oi_day_low": 11000, "day_open": 110},
            "CE_20100": {"oi": 8000, "ltp": 100, "gamma": 0.0008, "iv": 17.5, "oi_day_low": 7500, "day_open": 95},
            "PE_19900": {"oi": 9000, "ltp": 130, "gamma": 0.0009, "iv": 20.0, "oi_day_low": 8500, "day_open": 125},
        }
        result = compute_option_chain_analytics(contracts, kite_map, 20000.0, step=100)
        assert result["max_pain"] is not None
        assert result["pcr"] is not None
        assert isinstance(result["pcr"], float)


class TestUserServicePure:
    """Test user service pure functions."""

    def test_is_owner(self):
        from services.user_service import _is_owner, _is_admin, _is_credit_exempt
        assert _is_owner({"role": "owner"}) is True
        assert _is_owner({"role": "user"}) is False
        assert _is_admin({"role": "owner"}) is True
        assert _is_admin({"role": "sub_admin"}) is True
        assert _is_admin({"role": "user"}) is False
        assert _is_credit_exempt({"role": "owner"}) is True
        assert _is_credit_exempt({"role": "user"}) is False


class TestAPIEndpointsAfterExtraction:
    """Verify key API endpoints still work after extraction."""

    def test_auth_access(self):
        resp = requests.post(f"{BASE_URL}/api/auth/access",
                             json={"username": OWNER_USERNAME, "pin": OWNER_PIN}, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data

    def test_auth_me(self):
        token = _login()
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == OWNER_USERNAME

    def test_auth_settings(self):
        token = _login()
        resp = requests.patch(
            f"{BASE_URL}/api/auth/settings",
            json={"fno_budget": 250000},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        assert resp.status_code == 200

    def test_fno_events(self):
        token = _login()
        resp = requests.get(
            f"{BASE_URL}/api/fno/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        assert resp.status_code == 200

    def test_fno_sticky_cards(self):
        token = _login()
        resp = requests.get(
            f"{BASE_URL}/api/fno/sticky-cards",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        assert resp.status_code == 200

    def test_fno_signal_history(self):
        token = _login()
        resp = requests.get(
            f"{BASE_URL}/api/fno/signal-history",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        assert resp.status_code == 200

    def test_server_line_count(self):
        """Verify server.py has been reduced by the extraction."""
        with open('/app/backend/server.py') as f:
            lines = len(f.readlines())
        assert lines < 2400, f"server.py should be < 2400 lines after extraction, got {lines}"
        assert lines > 1500, f"server.py should be > 1500 lines (not over-extracted), got {lines}"
