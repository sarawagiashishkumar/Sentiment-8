"""
P2-B/C Backend Tests — Budget Alert UI + Position Sizing Enhancements.

Tests:
1. compute_position_size returns enhanced fields (lots_atr_method, lots_fixed_risk, max_risk_Rs)
2. ATR-based sizing returns valid lots when ATR is provided
3. Fixed-risk sizing matches expected calculation
4. not_affordable flag triggers when capital exceeds budget
5. /auth/settings PATCH updates fno_budget and account_risk_pct
6. /auth/me returns fno_budget and account_risk_pct
7. /fno/position-sizing returns enhanced fields via API
"""
import pytest
import httpx

from tests.helpers.test_utils import get_base_url
from services.position_sizing import compute_position_size

BASE_URL = get_base_url() + "/api"


# ── Unit Tests ─────────────────────────────────────────────────────────────

class TestEnhancedPositionSizing:
    """Tests for compute_position_size with ATR14 and fixed-risk enhancements."""

    def test_returns_enhanced_fields(self):
        result = compute_position_size(
            user_budget=500000, option_premium=100, lot_size=50,
            sl_price=85, entry_price=100, atr14=50, account_risk_pct=2.0,
        )
        assert "lots_atr_method" in result
        assert "lots_fixed_risk" in result
        assert "max_risk_Rs" in result
        assert isinstance(result["lots_atr_method"], int)
        assert isinstance(result["lots_fixed_risk"], int)
        assert isinstance(result["max_risk_Rs"], float)

    def test_atr_method_valid_lots(self):
        result = compute_position_size(
            user_budget=1000000, option_premium=50, lot_size=75,
            sl_price=40, entry_price=50, atr14=30, account_risk_pct=2.0,
        )
        # max_risk_Rs = 1000000 * 2% = 20000
        # atr_risk_per_lot = 30 * 75 = 2250
        # lots_atr = floor(20000 / 2250) = 8
        assert result["lots_atr_method"] == 8
        assert result["max_risk_Rs"] == 20000.0

    def test_fixed_risk_sizing(self):
        result = compute_position_size(
            user_budget=500000, option_premium=200, lot_size=25,
            sl_price=180, entry_price=200, account_risk_pct=3.0,
        )
        # max_risk_Rs = 500000 * 3% = 15000
        # sl_dist = 200 - 180 = 20
        # risk_per_lot = 20 * 25 = 500
        # lots_fixed_risk = floor(15000 / 500) = 30
        assert result["lots_fixed_risk"] == 30
        assert result["max_risk_Rs"] == 15000.0

    def test_not_affordable_flag(self):
        result = compute_position_size(
            user_budget=1000, option_premium=500, lot_size=50,
            sl_price=450, entry_price=500,
        )
        # capital_per_lot = 500 * 50 = 25000 > 1000
        assert result["not_affordable"] is True
        assert result["lots_allowed"] == 0

    def test_zero_atr_returns_zero_atr_lots(self):
        result = compute_position_size(
            user_budget=500000, option_premium=100, lot_size=50,
            sl_price=85, entry_price=100, atr14=0,
        )
        assert result["lots_atr_method"] == 0


# ── Integration Tests ─────────────────────────────────────────────────────

class TestSettingsEndpoint:
    """Tests for /auth/settings PATCH endpoint."""

    def _get_token(self):
        r = httpx.post(f"{BASE_URL}/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]

    def test_update_fno_budget(self):
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.patch(f"{BASE_URL}/auth/settings", json={"fno_budget": 750000}, headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["fno_budget"] == 750000.0
        # Reset
        httpx.patch(f"{BASE_URL}/auth/settings", json={"fno_budget": 500000}, headers=headers, timeout=15)

    def test_me_returns_settings(self):
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.get(f"{BASE_URL}/auth/me", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "fno_budget" in data
        assert "account_risk_pct" in data
        assert isinstance(data["fno_budget"], float)
        assert isinstance(data["account_risk_pct"], float)


class TestPositionSizingAPI:
    """Tests for /fno/position-sizing endpoint with enhanced fields."""

    def _get_token(self):
        r = httpx.post(f"{BASE_URL}/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]

    def test_position_sizing_returns_enhanced_fields(self):
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.post(
            f"{BASE_URL}/fno/position-sizing?user_budget=500000&option_premium=100&lot_size=50&sl_price=85&atr14=50",
            headers=headers, timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert "lots_atr_method" in data
        assert "lots_fixed_risk" in data
        assert "max_risk_Rs" in data
        assert data["lots_atr_method"] >= 0
        assert data["lots_fixed_risk"] >= 0
        assert data["max_risk_Rs"] > 0
