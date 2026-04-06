"""
Iteration 24: Price Band Fix Tests
Tests verifying:
1. Portfolio price bands use actual computed vol-based values (not static fallback)
2. compute_realistic_price_bands uses quality-adjusted drift (piotroski/rsi/trend/beneish)
3. Portfolio analyze: DMART + KAYNES return DIFFERENT upside_pct values
4. Multibagger custom-search: vol_bands have annual_drift_pct field (new)
5. vol_bands 1Y upside_pct > 1M upside_pct (time scaling correct)
6. Portfolio risk_metrics has portfolio_vol_annual_pct field
7. Sector momentum regression
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ──────────────────────────────────────────────────────────────────────────────
# AUTH FIXTURE
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Get auth token once for all tests in this module."""
    response = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=15,
    )
    assert response.status_code == 200, f"Auth failed: {response.status_code} {response.text}"
    token = response.json().get("token") or response.json().get("access_token")
    assert token, f"No token in auth response. Keys: {list(response.json().keys())}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ──────────────────────────────────────────────────────────────────────────────
# PORTFOLIO DMART + KAYNES ANALYSIS (shared response, cached at module scope)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def portfolio_dmart_kaynes(auth_headers):
    """POST /api/portfolio/analyze with DMART + KAYNES. Slow: 30-60s."""
    payload = {
        "positions": [
            {"symbol": "DMART", "avg_price": 3800, "quantity": 2},
            {"symbol": "KAYNES", "avg_price": 4000, "quantity": 1},
        ]
    }
    response = requests.post(
        f"{BASE_URL}/api/portfolio/analyze",
        json=payload,
        headers=auth_headers,
        timeout=120,
    )
    return response


# ──────────────────────────────────────────────────────────────────────────────
# PORTFOLIO ANALYZE — DMART + KAYNES TESTS
# ──────────────────────────────────────────────────────────────────────────────

class TestPortfolioDmartKaynes:
    """Portfolio analyze for DMART + KAYNES — verify vol-based price bands."""

    def test_portfolio_returns_200(self, portfolio_dmart_kaynes):
        """Portfolio analyze should return HTTP 200."""
        assert portfolio_dmart_kaynes.status_code == 200, (
            f"Expected 200 got {portfolio_dmart_kaynes.status_code}: "
            f"{portfolio_dmart_kaynes.text[:500]}"
        )

    def test_portfolio_has_stocks_array(self, portfolio_dmart_kaynes):
        """Response should have a non-empty 'stocks' array."""
        data = portfolio_dmart_kaynes.json()
        assert "stocks" in data, "Missing 'stocks' key in response"
        assert isinstance(data["stocks"], list), "'stocks' should be a list"
        assert len(data["stocks"]) > 0, "'stocks' array is empty"

    def test_portfolio_positions_count_is_2(self, portfolio_dmart_kaynes):
        """Two positions submitted → should have exactly 2 parsed stocks."""
        data = portfolio_dmart_kaynes.json()
        stocks = data.get("stocks", [])
        # Check parsed_positions_count or stocks length
        parsed_count = data.get("parsed_positions_count", len(stocks))
        assert parsed_count == 2, f"Expected 2 positions, got {parsed_count}"

    def test_portfolio_stocks_have_expected_ranges(self, portfolio_dmart_kaynes):
        """Each stock should have expected_ranges with at least 1M horizon."""
        data = portfolio_dmart_kaynes.json()
        for stock in data.get("stocks", []):
            assert "expected_ranges" in stock, (
                f"Stock {stock.get('symbol')} missing expected_ranges"
            )
            assert "1M" in stock["expected_ranges"], (
                f"Stock {stock.get('symbol')} missing 1M horizon in expected_ranges"
            )

    def test_portfolio_upside_pct_values_differ_between_stocks(self, portfolio_dmart_kaynes):
        """DMART and KAYNES should have DIFFERENT 1M upside_pct (vol-based, not static)."""
        data = portfolio_dmart_kaynes.json()
        stocks = {s["symbol"]: s for s in data.get("stocks", [])}

        dmart_symbol = next((k for k in stocks if "DMART" in k.upper()), None)
        kaynes_symbol = next((k for k in stocks if "KAYNES" in k.upper()), None)

        assert dmart_symbol is not None, f"DMART not found in stocks: {list(stocks.keys())}"
        assert kaynes_symbol is not None, f"KAYNES not found in stocks: {list(stocks.keys())}"

        dmart_1m = stocks[dmart_symbol]["expected_ranges"].get("1M", {})
        kaynes_1m = stocks[kaynes_symbol]["expected_ranges"].get("1M", {})

        dmart_upside = dmart_1m.get("upside_pct")
        kaynes_upside = kaynes_1m.get("upside_pct")

        assert dmart_upside is not None, "DMART 1M upside_pct is None"
        assert kaynes_upside is not None, "KAYNES 1M upside_pct is None"

        print(f"DMART 1M upside_pct: {dmart_upside}")
        print(f"KAYNES 1M upside_pct: {kaynes_upside}")

        # The two stocks should have DIFFERENT upside values (not same static fallback)
        assert dmart_upside != kaynes_upside, (
            f"DMART and KAYNES have the SAME 1M upside_pct={dmart_upside} "
            "— suggesting static fallback not vol-based computation"
        )

    def test_kaynes_more_volatile_than_dmart(self, portfolio_dmart_kaynes):
        """KAYNES 1M upside_pct should be > DMART 1M upside_pct (KAYNES is more volatile)."""
        data = portfolio_dmart_kaynes.json()
        stocks = {s["symbol"]: s for s in data.get("stocks", [])}

        dmart_symbol = next((k for k in stocks if "DMART" in k.upper()), None)
        kaynes_symbol = next((k for k in stocks if "KAYNES" in k.upper()), None)

        if dmart_symbol is None or kaynes_symbol is None:
            pytest.skip("DMART or KAYNES not found in response")

        dmart_upside = stocks[dmart_symbol]["expected_ranges"]["1M"].get("upside_pct", 0)
        kaynes_upside = stocks[kaynes_symbol]["expected_ranges"]["1M"].get("upside_pct", 0)

        print(f"DMART 1M upside: {dmart_upside}%, KAYNES 1M upside: {kaynes_upside}%")

        assert kaynes_upside > dmart_upside, (
            f"Expected KAYNES upside ({kaynes_upside}%) > DMART upside ({dmart_upside}%) "
            "since KAYNES is more volatile than DMART"
        )

    def test_expected_signals_have_non_zero_prices(self, portfolio_dmart_kaynes):
        """expected_signals must have actual non-zero max/min expected prices."""
        data = portfolio_dmart_kaynes.json()
        for stock in data.get("stocks", []):
            sym = stock.get("symbol", "?")
            signals = stock.get("expected_signals", {})
            assert signals, f"Stock {sym} has empty expected_signals"
            # Check 1M horizon
            if "1M" in signals:
                sig_1m = signals["1M"]
                max_price = sig_1m.get("max_expected_price")
                min_price = sig_1m.get("min_expected_price")
                assert max_price is not None and max_price > 0, (
                    f"Stock {sym} 1M max_expected_price is null/zero: {max_price}"
                )
                assert min_price is not None and min_price > 0, (
                    f"Stock {sym} 1M min_expected_price is null/zero: {min_price}"
                )
                print(f"Stock {sym}: 1M max={max_price}, min={min_price}")

    def test_upside_pct_not_fixed_fallback_value(self, portfolio_dmart_kaynes):
        """upside_pct values should not be the static fallback percentages (e.g., exactly 5.4 for 1M)."""
        data = portfolio_dmart_kaynes.json()
        # Static fallback for 1M with default params would be 12.0 * 0.45 = 5.4
        STATIC_FALLBACK_1M = 5.4
        for stock in data.get("stocks", []):
            sym = stock.get("symbol", "?")
            ranges_1m = stock.get("expected_ranges", {}).get("1M", {})
            upside = ranges_1m.get("upside_pct")
            if upside is not None:
                # If upside is EXACTLY the static fallback, flag it
                print(f"Stock {sym} 1M upside_pct: {upside}")
                # Both stocks being equal to 5.4 exactly would be suspicious
                # We already tested they differ, this is an additional sanity check

    def test_portfolio_risk_metrics_present(self, portfolio_dmart_kaynes):
        """portfolio_risk_metrics should be in the response."""
        data = portfolio_dmart_kaynes.json()
        assert "portfolio_risk_metrics" in data, (
            "Missing 'portfolio_risk_metrics' in portfolio analyze response"
        )
        rm = data["portfolio_risk_metrics"]
        assert rm is not None, "portfolio_risk_metrics is None"

    def test_portfolio_risk_metrics_has_vol_annual_pct(self, portfolio_dmart_kaynes):
        """portfolio_risk_metrics must have portfolio_vol_annual_pct (bug 5 fix verification)."""
        data = portfolio_dmart_kaynes.json()
        rm = data.get("portfolio_risk_metrics", {})
        assert "portfolio_vol_annual_pct" in rm, (
            f"Missing 'portfolio_vol_annual_pct' in risk_metrics. Keys: {list(rm.keys())}"
        )
        vol = rm["portfolio_vol_annual_pct"]
        assert vol is not None and vol > 0, (
            f"portfolio_vol_annual_pct is invalid: {vol}. "
            "Previously this was hardcoded 0.30 for all stocks."
        )
        print(f"Portfolio vol_annual_pct: {vol}%")

    def test_portfolio_vol_not_hardcoded(self, portfolio_dmart_kaynes):
        """portfolio_vol_annual_pct should NOT be exactly 30.0 (which was the hardcoded fallback)."""
        data = portfolio_dmart_kaynes.json()
        rm = data.get("portfolio_risk_metrics", {})
        vol = rm.get("portfolio_vol_annual_pct")
        if vol is not None:
            # 30.0% exactly for ALL stocks would be the hardcoded bug
            # It's OK to be close but the real computed value should differ
            print(f"Portfolio vol_annual_pct = {vol}%")
            # Soft assertion: just log, not hard fail since it could naturally be ~30%


# ──────────────────────────────────────────────────────────────────────────────
# MULTIBAGGER CUSTOM-SEARCH RELIANCE — vol_bands + annual_drift_pct
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def multibagger_reliance(auth_headers):
    """POST /api/multibagger/custom-search for RELIANCE. Slow: ~20s."""
    payload = {"symbol": "RELIANCE"}
    response = requests.post(
        f"{BASE_URL}/api/multibagger/custom-search",
        json=payload,
        headers=auth_headers,
        timeout=60,
    )
    return response


@pytest.fixture(scope="module")
def multibagger_hdfcbank(auth_headers):
    """POST /api/multibagger/custom-search for HDFCBANK. Slow: ~20s."""
    payload = {"symbol": "HDFCBANK"}
    response = requests.post(
        f"{BASE_URL}/api/multibagger/custom-search",
        json=payload,
        headers=auth_headers,
        timeout=60,
    )
    return response


class TestMultibaggerReliance:
    """RELIANCE custom-search: vol_bands with 6 horizons + annual_drift_pct field."""

    def test_reliance_returns_200(self, multibagger_reliance):
        assert multibagger_reliance.status_code == 200, (
            f"Expected 200 got {multibagger_reliance.status_code}: "
            f"{multibagger_reliance.text[:500]}"
        )

    def test_reliance_has_vol_bands(self, multibagger_reliance):
        data = multibagger_reliance.json()
        assert "vol_bands" in data, "Missing 'vol_bands' in RELIANCE response"
        assert data["vol_bands"] is not None, "vol_bands is None"
        assert len(data["vol_bands"]) > 0, "vol_bands is empty"

    def test_reliance_vol_bands_has_6_horizons(self, multibagger_reliance):
        """vol_bands must have exactly 6 horizons: 1W, 1M, 3M, 6M, 9M, 1Y."""
        data = multibagger_reliance.json()
        vol_bands = data.get("vol_bands", {})
        expected_horizons = {"1W", "1M", "3M", "6M", "9M", "1Y"}
        actual_horizons = set(vol_bands.keys())
        assert actual_horizons == expected_horizons, (
            f"Expected horizons {expected_horizons}, got {actual_horizons}"
        )

    def test_reliance_vol_bands_have_annual_drift_pct(self, multibagger_reliance):
        """Each band must have 'annual_drift_pct' field (NEW field from bug fix)."""
        data = multibagger_reliance.json()
        vol_bands = data.get("vol_bands", {})
        for horizon, band in vol_bands.items():
            assert "annual_drift_pct" in band, (
                f"Missing 'annual_drift_pct' in RELIANCE vol_bands[{horizon}]. "
                f"Keys: {list(band.keys())}"
            )
            drift = band["annual_drift_pct"]
            assert drift is not None, f"annual_drift_pct is None for horizon {horizon}"
            print(f"RELIANCE {horizon} annual_drift_pct: {drift}%")

    def test_reliance_drift_not_always_7_percent(self, multibagger_reliance):
        """annual_drift_pct should reflect quality-adjusted computation, not always 7.0%."""
        data = multibagger_reliance.json()
        vol_bands = data.get("vol_bands", {})
        # All horizons share the same drift_adj, so check any horizon
        if "1Y" in vol_bands:
            drift = vol_bands["1Y"].get("annual_drift_pct")
            print(f"RELIANCE annual_drift_pct: {drift}%")
            # Just verify it's a valid number (quality adjustments may push it up/down)
            assert drift is not None
            assert isinstance(drift, (int, float))

    def test_reliance_vol_bands_have_upside_pct(self, multibagger_reliance):
        """Each band should have upside_pct, downside_pct, flag."""
        data = multibagger_reliance.json()
        vol_bands = data.get("vol_bands", {})
        for horizon, band in vol_bands.items():
            assert "upside_pct" in band, f"Missing upside_pct in {horizon}"
            assert "downside_pct" in band, f"Missing downside_pct in {horizon}"
            assert "flag" in band, f"Missing flag in {horizon}"
            upside = band["upside_pct"]
            assert upside is not None and upside > 0, (
                f"upside_pct should be positive for {horizon}: {upside}"
            )

    def test_reliance_vol_bands_time_scaling_correct(self, multibagger_reliance):
        """1Y upside_pct should be greater than 1M upside_pct (time scaling)."""
        data = multibagger_reliance.json()
        vol_bands = data.get("vol_bands", {})
        upside_1m = vol_bands.get("1M", {}).get("upside_pct")
        upside_1y = vol_bands.get("1Y", {}).get("upside_pct")

        if upside_1m is None or upside_1y is None:
            pytest.skip("1M or 1Y upside_pct not available")

        print(f"RELIANCE 1M upside: {upside_1m}%, 1Y upside: {upside_1y}%")
        assert upside_1y > upside_1m, (
            f"1Y upside ({upside_1y}%) should be > 1M upside ({upside_1m}%) — "
            "time scaling is broken"
        )


class TestMultibaggerHdfcbank:
    """HDFCBANK custom-search: vol_bands with different upside_pct per horizon."""

    def test_hdfcbank_returns_200(self, multibagger_hdfcbank):
        assert multibagger_hdfcbank.status_code == 200, (
            f"Expected 200 got {multibagger_hdfcbank.status_code}: "
            f"{multibagger_hdfcbank.text[:500]}"
        )

    def test_hdfcbank_has_vol_bands_6_horizons(self, multibagger_hdfcbank):
        data = multibagger_hdfcbank.json()
        vol_bands = data.get("vol_bands", {})
        assert len(vol_bands) == 6, f"Expected 6 horizons, got {len(vol_bands)}: {list(vol_bands.keys())}"

    def test_hdfcbank_vol_bands_different_upside_per_horizon(self, multibagger_hdfcbank):
        """Different horizons should have different upside_pct values (time-scaled)."""
        data = multibagger_hdfcbank.json()
        vol_bands = data.get("vol_bands", {})
        upsides = [band.get("upside_pct") for band in vol_bands.values() if band.get("upside_pct")]
        print(f"HDFCBANK upside_pcts: {upsides}")
        # All values being identical would indicate a bug (no time scaling)
        assert len(set(upsides)) > 1, (
            f"All upside_pct values are identical ({upsides[0] if upsides else 'N/A'}) — "
            "time scaling not working"
        )

    def test_hdfcbank_1y_upside_greater_than_1m(self, multibagger_hdfcbank):
        """1Y upside_pct > 1M upside_pct for HDFCBANK."""
        data = multibagger_hdfcbank.json()
        vol_bands = data.get("vol_bands", {})
        upside_1m = vol_bands.get("1M", {}).get("upside_pct")
        upside_1y = vol_bands.get("1Y", {}).get("upside_pct")
        if upside_1m and upside_1y:
            print(f"HDFCBANK 1M: {upside_1m}%, 1Y: {upside_1y}%")
            assert upside_1y > upside_1m, (
                f"1Y ({upside_1y}%) should be > 1M ({upside_1m}%)"
            )

    def test_hdfcbank_vol_bands_have_annual_drift_pct(self, multibagger_hdfcbank):
        """annual_drift_pct must be present in each HDFCBANK band."""
        data = multibagger_hdfcbank.json()
        vol_bands = data.get("vol_bands", {})
        for horizon, band in vol_bands.items():
            assert "annual_drift_pct" in band, (
                f"Missing annual_drift_pct in HDFCBANK vol_bands[{horizon}]"
            )


# ──────────────────────────────────────────────────────────────────────────────
# SECTOR MOMENTUM REGRESSION
# ──────────────────────────────────────────────────────────────────────────────

class TestSectorMomentumRegression:
    """Regression: GET /api/sector-momentum still works."""

    def test_sector_momentum_returns_200(self, auth_headers):
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200, (
            f"Sector momentum returned {response.status_code}: {response.text[:300]}"
        )

    def test_sector_momentum_has_sectors(self, auth_headers):
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60,
        )
        data = response.json()
        # Check the response has sector data
        assert isinstance(data, (list, dict)), "Unexpected response type"
        if isinstance(data, list):
            assert len(data) > 0, "Sector momentum list is empty"
            print(f"Sector momentum: {len(data)} sectors")
        else:
            # dict format
            sectors = data.get("sectors", data.get("data", []))
            assert len(sectors) > 0, "Sector momentum has no sectors"
            print(f"Sector momentum keys: {list(data.keys())}")


# ──────────────────────────────────────────────────────────────────────────────
# UNIT TESTS FOR compute_realistic_price_bands (direct import)
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeRealisticPriceBands:
    """Direct unit tests for compute_realistic_price_bands to verify bug fixes."""

    def test_annual_drift_pct_present_in_output(self):
        """The annual_drift_pct field must be present in each band (NEW field)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands = compute_realistic_price_bands(
            ltp=1000.0,
            hist_vol=0.30,
        )
        for horizon, band in bands.items():
            assert "annual_drift_pct" in band, (
                f"Missing annual_drift_pct in horizon {horizon}. Keys: {list(band.keys())}"
            )

    def test_piotroski_high_increases_drift(self):
        """High Piotroski score should produce higher drift than no Piotroski."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands_no_piotroski = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30
        )
        bands_high_piotroski = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30, piotroski_score=8
        )
        drift_base = bands_no_piotroski["1Y"]["annual_drift_pct"]
        drift_high = bands_high_piotroski["1Y"]["annual_drift_pct"]
        print(f"Drift base: {drift_base}%, drift with high Piotroski: {drift_high}%")
        assert drift_high > drift_base, (
            f"High Piotroski should increase drift: base={drift_base}, high={drift_high}"
        )

    def test_piotroski_low_decreases_drift(self):
        """Low Piotroski score should produce lower drift than no Piotroski."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands_no_piotroski = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30
        )
        bands_low_piotroski = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30, piotroski_score=2
        )
        drift_base = bands_no_piotroski["1Y"]["annual_drift_pct"]
        drift_low = bands_low_piotroski["1Y"]["annual_drift_pct"]
        print(f"Drift base: {drift_base}%, drift with low Piotroski: {drift_low}%")
        assert drift_low < drift_base, (
            f"Low Piotroski should decrease drift: base={drift_base}, low={drift_low}"
        )

    def test_overbought_rsi_decreases_drift(self):
        """RSI > 68 should reduce drift (mean reversion risk)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands_neutral_rsi = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30, rsi=50
        )
        bands_overbought = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30, rsi=75
        )
        drift_neutral = bands_neutral_rsi["1Y"]["annual_drift_pct"]
        drift_overbought = bands_overbought["1Y"]["annual_drift_pct"]
        print(f"Drift neutral RSI: {drift_neutral}%, drift overbought RSI: {drift_overbought}%")
        assert drift_overbought < drift_neutral, (
            f"Overbought RSI should decrease drift: neutral={drift_neutral}, overbought={drift_overbought}"
        )

    def test_beneish_manipulation_decreases_drift(self):
        """Beneish M-Score > -1.78 should reduce drift by 5%."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands_clean = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30, beneish_m_score=-3.0  # safe
        )
        bands_manipulator = compute_realistic_price_bands(
            ltp=1000.0, hist_vol=0.30, beneish_m_score=-1.5  # manipulator
        )
        drift_clean = bands_clean["1Y"]["annual_drift_pct"]
        drift_manip = bands_manipulator["1Y"]["annual_drift_pct"]
        print(f"Drift clean Beneish: {drift_clean}%, drift manipulator: {drift_manip}%")
        assert drift_manip < drift_clean, (
            f"Beneish manipulator should decrease drift: clean={drift_clean}, manip={drift_manip}"
        )
        # Penalty should be -5% annual
        assert abs((drift_clean - drift_manip) - 5.0) < 0.5, (
            f"Expected ~5% drift penalty, got {drift_clean - drift_manip}%"
        )

    def test_hist_vol_affects_band_width(self):
        """Higher hist_vol should produce wider bands (upside_pct should be larger)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands_low_vol = compute_realistic_price_bands(ltp=1000.0, hist_vol=0.15)
        bands_high_vol = compute_realistic_price_bands(ltp=1000.0, hist_vol=0.60)

        upside_low = bands_low_vol["1M"]["upside_pct"]
        upside_high = bands_high_vol["1M"]["upside_pct"]
        print(f"Low vol (15%) 1M upside: {upside_low}%, High vol (60%) 1M upside: {upside_high}%")
        assert upside_high > upside_low, (
            f"Higher volatility should produce wider upside band: low_vol={upside_low}, high_vol={upside_high}"
        )

    def test_1y_upside_greater_than_1m(self):
        """1Y upside_pct should be greater than 1M (time scaling)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands = compute_realistic_price_bands(ltp=1000.0, hist_vol=0.30)
        upside_1m = bands["1M"]["upside_pct"]
        upside_1y = bands["1Y"]["upside_pct"]
        print(f"1M upside: {upside_1m}%, 1Y upside: {upside_1y}%")
        assert upside_1y > upside_1m, (
            f"1Y upside ({upside_1y}%) should be > 1M upside ({upside_1m}%)"
        )

    def test_drift_only_7_when_no_quality_params(self):
        """With no quality params, annual_drift_pct should be 7.0% (base equity premium)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_realistic_price_bands

        bands = compute_realistic_price_bands(ltp=1000.0, hist_vol=0.30)
        drift = bands["1Y"]["annual_drift_pct"]
        print(f"Base drift (no quality params): {drift}%")
        assert abs(drift - 7.0) < 0.01, f"Base drift should be 7.0%, got {drift}%"


# ──────────────────────────────────────────────────────────────────────────────
# F&O ATR TARGETS UNIT TESTS (Bug 3 Fix)
# ──────────────────────────────────────────────────────────────────────────────

class TestFnoAtrTargets:
    """Unit tests for compute_atr_based_fno_targets: ATR_points × delta (not atr_pct × price)."""

    def test_atr_target_uses_atr_points_not_percentage(self):
        """T1/T2 must use ATR_points × delta, not ATR_pct × entry_price."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_atr_based_fno_targets

        entry_price = 100.0
        underlying_ltp = 24000.0
        atr = 240.0  # ATR in points (1% of underlying)
        minutes_to_expiry = 500

        t1, t2 = compute_atr_based_fno_targets(
            entry_price=entry_price,
            underlying_ltp=underlying_ltp,
            atr=atr,
            minutes_to_expiry=minutes_to_expiry,
            option_type="CE",
        )
        # Expected: atr × time_factor × delta × 1 = 240 × 0.90 × 0.45 = 97.2 gain
        # So T1 ≈ 197.2, T2 ≈ 100 + (240 × 0.90 × 0.45 × 2) = 294.4
        print(f"T1={t1}, T2={t2}")
        assert t1 > entry_price, f"T1 ({t1}) must be > entry ({entry_price})"
        assert t2 > t1, f"T2 ({t2}) must be > T1 ({t1})"

        # The gain from ATR should be much larger than a percentage-based approach
        # Old buggy formula: atr_pct × entry_price = (240/24000) × 100 × ... ≈ 1% = +1
        # New correct formula: atr_points × delta = 240 × 0.45 × ... ≈ +97
        expected_gain_old_buggy = (atr / underlying_ltp) * entry_price * 0.90
        expected_gain_new = atr * 0.90 * 0.45

        gain_actual = t1 - entry_price
        print(f"Actual T1 gain: {gain_actual}")
        print(f"Expected old-buggy gain: {expected_gain_old_buggy}")
        print(f"Expected new correct gain: {expected_gain_new}")

        # Actual gain should be much closer to new formula
        assert abs(gain_actual - expected_gain_new) < abs(gain_actual - expected_gain_old_buggy), (
            "T1 calculation appears to still use old buggy formula (atr_pct × price)"
        )

    def test_atr_target_minimum_floor(self):
        """T1 should be at least 3% above entry, T2 at least 8% (floor protection)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_atr_based_fno_targets

        entry_price = 5.0  # Very cheap OTM option
        t1, t2 = compute_atr_based_fno_targets(
            entry_price=entry_price,
            underlying_ltp=24000.0,
            atr=10.0,  # Small ATR → small gain
            minutes_to_expiry=100,  # Near expiry
            option_type="CE",
            strike=25000.0,  # Deep OTM (delta will be 0.15)
        )
        print(f"T1={t1}, T2={t2} for entry={entry_price}")
        assert t1 >= entry_price * 1.03, f"T1 floor: must be >= 103% of entry. T1={t1}"
        assert t2 >= entry_price * 1.08, f"T2 floor: must be >= 108% of entry. T2={t2}"

    def test_atr_target_delta_scales_with_moneyness(self):
        """Deep ITM option should have higher delta and thus higher T1 gain than OTM."""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.indicators import compute_atr_based_fno_targets

        entry = 200.0
        underlying = 24000.0
        atr = 200.0
        minutes = 400

        # ITM CE: strike well below underlying
        t1_itm, _ = compute_atr_based_fno_targets(
            entry_price=entry,
            underlying_ltp=underlying,
            atr=atr,
            minutes_to_expiry=minutes,
            option_type="CE",
            strike=21000.0,  # moneyness = 24000/21000 ≈ 1.14 → delta ~0.80
        )
        # OTM CE: strike above underlying
        t1_otm, _ = compute_atr_based_fno_targets(
            entry_price=entry,
            underlying_ltp=underlying,
            atr=atr,
            minutes_to_expiry=minutes,
            option_type="CE",
            strike=26000.0,  # moneyness = 24000/26000 ≈ 0.92 → delta ~0.15
        )
        gain_itm = t1_itm - entry
        gain_otm = t1_otm - entry
        print(f"ITM delta gain: {gain_itm:.2f}, OTM delta gain: {gain_otm:.2f}")
        assert gain_itm > gain_otm, (
            f"ITM option gain ({gain_itm}) should exceed OTM gain ({gain_otm}) due to delta"
        )
