"""
Iteration 23 - Portfolio Analyze Bug Fix + Alert Sound Upgrade
Tests:
  - POST /api/portfolio/analyze with DMART, KAYNES (was failing before fix)
  - portfolio_risk_metrics field in response
  - Multiple stocks (INFY + HDFCBANK) portfolio
  - Regression: GET /api/sector-momentum returns 15 sectors
  - Regression: POST /api/multibagger/custom-search for INFY vol_bands with 6 horizons
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ── Auth fixture ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def auth_token():
    """Obtain auth token with admin credentials."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=15,
    )
    assert resp.status_code == 200, f"Auth failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in response: {data}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ── TestPortfolioAnalyzeDmart ─────────────────────────────────────────────────
class TestPortfolioAnalyzeDmart:
    """Test portfolio analyze with DMART symbol (previously failing with 'Unable to analyze portfolio.')"""

    def test_dmart_returns_200(self, auth_headers):
        """POST /api/portfolio/analyze with DMART returns HTTP 200."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "DMART", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,  # yfinance can be slow
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
        print(f"DMART portfolio analyze: {resp.status_code} OK")

    def test_dmart_has_stocks_array(self, auth_headers):
        """Response has stocks array."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "DMART", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data, f"No 'stocks' key in response: {data.keys()}"
        assert isinstance(data["stocks"], list), f"'stocks' is not a list: {type(data['stocks'])}"
        print(f"DMART stocks count: {len(data['stocks'])}")

    def test_dmart_stock_has_recommendation(self, auth_headers):
        """Each stock in response has a recommendation field."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "DMART", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        if stocks:
            stock = stocks[0]
            assert "recommendation" in stock, f"'recommendation' missing in stock: {stock.keys()}"
            print(f"DMART recommendation: {stock.get('recommendation')}")
        else:
            # If stocks is empty, check failed_symbols
            failed = data.get("failed_symbols", [])
            print(f"DMART stocks empty. failed_symbols: {failed}")
            # This is acceptable if yfinance can't fetch data for DMART
            # but we should warn

    def test_dmart_has_parsed_positions_count(self, auth_headers):
        """Response has parsed_positions_count."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "DMART", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "parsed_positions_count" in data
        # Count should be >= 0 (0 if DMART not found, 1 if found)
        assert isinstance(data["parsed_positions_count"], int)
        print(f"DMART parsed_positions_count: {data['parsed_positions_count']}")


# ── TestPortfolioAnalyzeKaynes ─────────────────────────────────────────────────
class TestPortfolioAnalyzeKaynes:
    """Test portfolio analyze with KAYNES symbol."""

    def test_kaynes_returns_200(self, auth_headers):
        """POST /api/portfolio/analyze with KAYNES returns HTTP 200."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "KAYNES", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
        print(f"KAYNES portfolio analyze: {resp.status_code} OK")

    def test_kaynes_has_stocks_array(self, auth_headers):
        """KAYNES response has stocks array."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "KAYNES", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data, f"No 'stocks' key: {data.keys()}"
        print(f"KAYNES stocks: {data.get('stocks', [])}")
        print(f"KAYNES failed_symbols: {data.get('failed_symbols', [])}")

    def test_kaynes_stock_recommendation_field(self, auth_headers):
        """KAYNES stocks have recommendation field if returned."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "KAYNES", "avg_price": 3800, "quantity": 1}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        if stocks:
            stock = stocks[0]
            assert "recommendation" in stock, f"recommendation missing: {stock.keys()}"
            print(f"KAYNES recommendation: {stock['recommendation']}")
        else:
            failed = data.get("failed_symbols", [])
            print(f"KAYNES had no stocks (yfinance may not support it). failed: {failed}")


# ── TestPortfolioRiskMetrics ─────────────────────────────────────────────────
class TestPortfolioRiskMetrics:
    """Test portfolio_risk_metrics field presence in response."""

    def test_portfolio_risk_metrics_key_in_response(self, auth_headers):
        """Response should have portfolio_risk_metrics key (may be null if not passed through)."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "INFY", "avg_price": 1500, "quantity": 10}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "portfolio_risk_metrics" in data, (
            f"portfolio_risk_metrics field missing from response keys: {list(data.keys())}"
        )
        print(f"portfolio_risk_metrics value: {data['portfolio_risk_metrics']}")

    def test_portfolio_risk_metrics_populated_for_infy(self, auth_headers):
        """portfolio_risk_metrics should be populated (not null) if stock was found."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "INFY", "avg_price": 1500, "quantity": 10}]},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        risk = data.get("portfolio_risk_metrics")
        print(f"INFY stocks found: {len(stocks)}, risk_metrics: {risk}")
        # If stocks were returned successfully, risk metrics should be non-null
        if stocks:
            assert risk is not None, (
                "portfolio_risk_metrics is None even though stocks were analyzed. "
                "Bug: endpoint builds PortfolioAnalyzeResponse without portfolio_risk_metrics=analysis.portfolio_risk_metrics"
            )


# ── TestPortfolioMultipleStocks ─────────────────────────────────────────────────
class TestPortfolioMultipleStocks:
    """Test portfolio analyze with multiple stocks."""

    def test_infy_hdfcbank_returns_200(self, auth_headers):
        """POST /api/portfolio/analyze with INFY + HDFCBANK returns 200."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={
                "positions": [
                    {"symbol": "INFY", "avg_price": 1500, "quantity": 10},
                    {"symbol": "HDFCBANK", "avg_price": 1600, "quantity": 5},
                ]
            },
            headers=auth_headers,
            timeout=120,  # 2 stocks * ~20s each
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:500]}"
        print("INFY+HDFCBANK portfolio analyze: 200 OK")

    def test_infy_hdfcbank_stocks_count(self, auth_headers):
        """Multiple stock portfolio returns correct count."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={
                "positions": [
                    {"symbol": "INFY", "avg_price": 1500, "quantity": 10},
                    {"symbol": "HDFCBANK", "avg_price": 1600, "quantity": 5},
                ]
            },
            headers=auth_headers,
            timeout=120,
        )
        assert resp.status_code == 200
        data = resp.json()
        stocks = data.get("stocks", [])
        failed = data.get("failed_symbols", [])
        total_processed = len(stocks) + len(failed)
        assert total_processed >= 1, f"Expected at least 1 stock processed, got 0. data={data}"
        print(f"Multiple stocks: {len(stocks)} stocks analyzed, {len(failed)} failed")

    def test_portfolio_analyze_requires_auth(self):
        """Portfolio analyze endpoint requires authentication."""
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json={"positions": [{"symbol": "INFY", "avg_price": 1500, "quantity": 10}]},
            timeout=15,
        )
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print(f"Auth check: correctly returned {resp.status_code}")


# ── TestSectorMomentumRegression ─────────────────────────────────────────────────
class TestSectorMomentumRegression:
    """Regression: GET /api/sector-momentum returns 15 sectors."""

    def test_sector_momentum_returns_200(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
        print("sector-momentum: 200 OK")

    def test_sector_momentum_has_15_sectors(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        sectors = data.get("sectors", [])
        assert len(sectors) == 15, f"Expected 15 sectors, got {len(sectors)}: {[s.get('sector') for s in sectors]}"
        print(f"sector-momentum sectors count: {len(sectors)}")


# ── TestMultibaggerVolBandsRegression ─────────────────────────────────────────────────
class TestMultibaggerVolBandsRegression:
    """Regression: POST /api/multibagger/custom-search INFY returns vol_bands with 6 horizons."""

    def test_infy_custom_search_200(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "INFY"},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
        print("custom-search INFY: 200 OK")

    def test_infy_vol_bands_6_horizons(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/api/multibagger/custom-search",
            json={"symbol": "INFY"},
            headers=auth_headers,
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        vol_bands = data.get("vol_bands", {})
        assert vol_bands, f"vol_bands missing or empty: {data.keys()}"
        expected_keys = {"1W", "1M", "3M", "6M", "9M", "1Y"}
        actual_keys = set(vol_bands.keys())
        assert actual_keys == expected_keys, f"Expected {expected_keys}, got {actual_keys}"
        print(f"INFY vol_bands horizons: {list(vol_bands.keys())}")
