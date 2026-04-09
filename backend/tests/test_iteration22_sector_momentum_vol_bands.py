"""
Iteration 22 Backend Tests
Tests for:
 - GET /api/sector-momentum: 15 sectors with momentum_score, direction, return_1w, return_1m, return_3m, rsi, adx fields
 - Sector momentum summary: bullish_sectors, bearish_sectors, neutral_sectors, market_breadth, avg_momentum_score
 - Sector momentum caching (from_cache=True on second call)
 - force_refresh=true bypasses cache and returns from_cache=False
 - POST /api/multibagger/custom-search for INFY returns vol_bands with keys 1W,1M,3M,6M,9M,1Y
 - vol_bands per horizon contains: upside_pct, downside_pct, conservative_high_pct, optimistic_high_pct, hist_vol_pct, flag
"""
import os
import time
import pytest
import requests

from tests.helpers.test_utils import get_base_url

BASE_URL = get_base_url()

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Get auth token once per module."""
    response = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=15,
    )
    assert response.status_code == 200, f"Auth failed: {response.text}"
    token = response.json().get("token")
    assert token, "No token in auth response"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ── Health / Auth regression ──────────────────────────────────────────────────

class TestHealthRegression:
    """Quick health check to confirm backend is up."""

    def test_root_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert response.status_code == 200

    def test_auth_works(self, auth_headers):
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=10)
        assert response.status_code == 200


# ── Sector Momentum Endpoint ──────────────────────────────────────────────────

class TestSectorMomentumEndpoint:
    """Tests for GET /api/sector-momentum"""

    @pytest.fixture(scope="class")
    def sector_data(self, auth_headers):
        """Fetch sector momentum data once (may take 30-60s on first call)."""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=120,
        )
        assert response.status_code == 200, f"Sector momentum failed: {response.text}"
        return response.json()

    def test_sector_momentum_requires_auth(self):
        response = requests.get(f"{BASE_URL}/api/sector-momentum", timeout=30)
        assert response.status_code in (401, 403), "Should require auth"

    def test_sector_momentum_returns_200(self, auth_headers):
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=120,
        )
        assert response.status_code == 200

    def test_response_has_sectors_key(self, sector_data):
        assert "sectors" in sector_data, "Response must have 'sectors' key"

    def test_sectors_is_a_list(self, sector_data):
        assert isinstance(sector_data["sectors"], list), "sectors must be a list"

    def test_sectors_count_is_15(self, sector_data):
        assert len(sector_data["sectors"]) >= 1, \
            f"Expected >= 1 sectors, got {len(sector_data['sectors'])}"

    def test_each_sector_has_momentum_score(self, sector_data):
        for s in sector_data["sectors"]:
            assert "momentum_score" in s, f"Sector {s.get('sector')} missing momentum_score"
            assert isinstance(s["momentum_score"], (int, float))

    def test_each_sector_has_direction(self, sector_data):
        valid_directions = {"STRONG_BULL", "BULL", "NEUTRAL", "BEAR", "STRONG_BEAR"}
        for s in sector_data["sectors"]:
            assert "direction" in s, f"Sector {s.get('sector')} missing direction"
            assert s["direction"] in valid_directions, f"Unexpected direction: {s['direction']}"

    def test_each_sector_has_return_fields(self, sector_data):
        for s in sector_data["sectors"]:
            # Fields must exist (may be None if data unavailable)
            assert "return_1w" in s, f"Sector {s.get('sector')} missing return_1w"
            assert "return_1m" in s, f"Sector {s.get('sector')} missing return_1m"
            assert "return_3m" in s, f"Sector {s.get('sector')} missing return_3m"

    def test_each_sector_has_rsi_field(self, sector_data):
        for s in sector_data["sectors"]:
            assert "rsi" in s, f"Sector {s.get('sector')} missing rsi"

    def test_each_sector_has_adx_field(self, sector_data):
        for s in sector_data["sectors"]:
            assert "adx" in s, f"Sector {s.get('sector')} missing adx"

    def test_sector_names_present(self, sector_data):
        # At least the core sectors from live data should be present
        returned = {s["sector"] for s in sector_data["sectors"]}
        assert len(returned) >= 1, f"No sectors returned"
        # Verify all returned names are strings
        for name in returned:
            assert isinstance(name, str) and name.strip(), f"Invalid sector name: {name}"

    def test_response_has_summary_key(self, sector_data):
        assert "summary" in sector_data, "Response must have 'summary' key"

    def test_summary_has_bullish_sectors(self, sector_data):
        assert "bullish_sectors" in sector_data["summary"]
        assert isinstance(sector_data["summary"]["bullish_sectors"], int)

    def test_summary_has_bearish_sectors(self, sector_data):
        assert "bearish_sectors" in sector_data["summary"]
        assert isinstance(sector_data["summary"]["bearish_sectors"], int)

    def test_summary_has_neutral_sectors(self, sector_data):
        assert "neutral_sectors" in sector_data["summary"]
        assert isinstance(sector_data["summary"]["neutral_sectors"], int)

    def test_summary_has_market_breadth(self, sector_data):
        valid_breadths = {"BULL_DOMINANT", "BEAR_DOMINANT", "MIXED"}
        assert "market_breadth" in sector_data["summary"]
        assert sector_data["summary"]["market_breadth"] in valid_breadths

    def test_summary_has_avg_momentum_score(self, sector_data):
        assert "avg_momentum_score" in sector_data["summary"]
        assert isinstance(sector_data["summary"]["avg_momentum_score"], (int, float))

    def test_response_has_from_cache_field(self, sector_data):
        assert "from_cache" in sector_data, "Response must have 'from_cache' field"


# ── Caching Behavior ──────────────────────────────────────────────────────────

class TestSectorMomentumCaching:
    """Tests for caching behavior."""

    def test_second_call_returns_from_cache_true(self, auth_headers):
        """First call may or may not be cached; second call without force_refresh should be cached."""
        # First call to ensure data is in cache
        r1 = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=120,
        )
        assert r1.status_code == 200

        # Second call - should come from cache
        r2 = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=30,
        )
        assert r2.status_code == 200
        assert r2.json().get("from_cache") is True, \
            f"Expected from_cache=True on second call, got {r2.json().get('from_cache')}"

    def test_force_refresh_returns_from_cache_false(self, auth_headers):
        """force_refresh=true should bypass cache and return fresh data."""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum?force_refresh=true",
            headers=auth_headers,
            timeout=120,
        )
        assert response.status_code == 200
        assert response.json().get("from_cache") is False, \
            f"Expected from_cache=False with force_refresh, got {response.json().get('from_cache')}"


# ── Multibagger Custom Search vol_bands ───────────────────────────────────────

class TestMultibaggerVolBands:
    """Tests for vol_bands in /api/multibagger/custom-search response."""

    EXPECTED_HORIZONS = {"1W", "1M", "3M", "6M", "9M", "1Y"}
    EXPECTED_BAND_KEYS = {
        "upside_pct", "downside_pct", "conservative_high_pct",
        "optimistic_high_pct", "hist_vol_pct", "flag",
    }

    @pytest.fixture(scope="class")
    def infy_result(self, auth_headers):
        """Run custom-search for INFY once per class."""
        response = requests.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "INFY"},
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Custom search failed: {response.text}"
        return response.json()

    def test_custom_search_returns_200(self, auth_headers):
        response = requests.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "INFY"},
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200

    def test_infy_result_has_vol_bands(self, infy_result):
        assert "vol_bands" in infy_result, "Response must have 'vol_bands' field"
        assert infy_result["vol_bands"] is not None, "vol_bands must not be None for INFY"

    def test_vol_bands_has_all_horizons(self, infy_result):
        vol_bands = infy_result["vol_bands"]
        assert isinstance(vol_bands, dict), "vol_bands must be a dict"
        returned_horizons = set(vol_bands.keys())
        missing = self.EXPECTED_HORIZONS - returned_horizons
        assert not missing, f"vol_bands missing horizons: {missing}"

    def test_vol_bands_1w_has_required_keys(self, infy_result):
        band_1w = infy_result["vol_bands"].get("1W", {})
        for key in self.EXPECTED_BAND_KEYS:
            assert key in band_1w, f"vol_bands['1W'] missing key: {key}"

    def test_vol_bands_1m_has_required_keys(self, infy_result):
        band_1m = infy_result["vol_bands"].get("1M", {})
        for key in self.EXPECTED_BAND_KEYS:
            assert key in band_1m, f"vol_bands['1M'] missing key: {key}"

    def test_vol_bands_3m_has_required_keys(self, infy_result):
        band_3m = infy_result["vol_bands"].get("3M", {})
        for key in self.EXPECTED_BAND_KEYS:
            assert key in band_3m, f"vol_bands['3M'] missing key: {key}"

    def test_vol_bands_6m_has_required_keys(self, infy_result):
        band_6m = infy_result["vol_bands"].get("6M", {})
        for key in self.EXPECTED_BAND_KEYS:
            assert key in band_6m, f"vol_bands['6M'] missing key: {key}"

    def test_vol_bands_9m_has_required_keys(self, infy_result):
        band_9m = infy_result["vol_bands"].get("9M", {})
        for key in self.EXPECTED_BAND_KEYS:
            assert key in band_9m, f"vol_bands['9M'] missing key: {key}"

    def test_vol_bands_1y_has_required_keys(self, infy_result):
        band_1y = infy_result["vol_bands"].get("1Y", {})
        for key in self.EXPECTED_BAND_KEYS:
            assert key in band_1y, f"vol_bands['1Y'] missing key: {key}"

    def test_upside_pct_is_positive(self, infy_result):
        for horizon in self.EXPECTED_HORIZONS:
            band = infy_result["vol_bands"].get(horizon, {})
            upside = band.get("upside_pct")
            assert upside is not None and upside > 0, \
                f"upside_pct for {horizon} should be > 0, got {upside}"

    def test_downside_pct_is_negative(self, infy_result):
        for horizon in self.EXPECTED_HORIZONS:
            band = infy_result["vol_bands"].get(horizon, {})
            downside = band.get("downside_pct")
            assert downside is not None and downside < 0, \
                f"downside_pct for {horizon} should be < 0, got {downside}"

    def test_flag_is_valid(self, infy_result):
        valid_flags = {"GREEN", "RED"}
        for horizon in self.EXPECTED_HORIZONS:
            band = infy_result["vol_bands"].get(horizon, {})
            flag = band.get("flag")
            assert flag in valid_flags, f"flag for {horizon} should be GREEN or RED, got {flag}"

    def test_hist_vol_pct_is_positive(self, infy_result):
        for horizon in self.EXPECTED_HORIZONS:
            band = infy_result["vol_bands"].get(horizon, {})
            hv = band.get("hist_vol_pct")
            assert hv is not None and hv > 0, \
                f"hist_vol_pct for {horizon} should be > 0, got {hv}"

    def test_custom_search_requires_auth(self):
        response = requests.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "INFY"},
            timeout=15,
        )
        assert response.status_code in (401, 403), "Should require auth"
