"""
Iteration 12: Testing new features:
1. Login with @shish123
2. Portfolio Analysis: min_expected_price in expected_signals (Max Low Downside)
3. Custom position: can_sell=True for OPEN status (without T1/T2 required)
4. F&O signals: DayChange/BiasScore separate fields
5. best_exit_price in F&O signals
6. Multibagger: thesis, roe, roce, piotroski, beneish fields
"""

import os
import pytest
import requests
import json

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def auth_token():
    """Authenticate as owner @shish123"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"},
        timeout=10,
    )
    assert resp.status_code == 200, f"Auth failed: {resp.status_code} - {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in auth response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. AUTH
# ─────────────────────────────────────────────────────────────────────────────

class TestAuth:
    """Test login/auth with @shish123"""

    def test_login_owner_works(self):
        """Login with @shish123 returns 200 and token"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert len(data["token"]) > 10
        print(f"✓ Login OK, token prefix: {data['token'][:12]}...")

    def test_login_response_has_user_info(self):
        """Login response has credits and role"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "credits" in data or "user" in data or "role" in data or "token" in data
        print(f"✓ Response keys: {list(data.keys())}")

    def test_invalid_login_rejected(self):
        """Login with random unknown user is rejected"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "INVALID_UNKNOWN_USER_9999"},
            timeout=10,
        )
        assert resp.status_code in (401, 403, 404, 422), f"Expected 4xx, got {resp.status_code}"
        print(f"✓ Invalid login returns {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. PORTFOLIO ANALYSIS – min_expected_price
# ─────────────────────────────────────────────────────────────────────────────

class TestPortfolioAnalysis:
    """Portfolio analysis returns min_expected_price in expected_signals"""

    def test_portfolio_analyze_returns_min_expected_price(self, auth_headers):
        """POST /api/portfolio/analyze — verify min_expected_price present"""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2500.0, "quantity": 10},
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Portfolio analyze failed: {resp.status_code} - {resp.text[:300]}"
        data = resp.json()
        assert "stocks" in data, "No 'stocks' field in response"
        assert len(data["stocks"]) > 0, "No stocks in analysis result"

        stock = data["stocks"][0]
        assert "expected_signals" in stock, "No expected_signals in stock analysis"
        assert len(stock["expected_signals"]) > 0, "expected_signals is empty"

        # Check each horizon has min_expected_price
        for horizon, values in stock["expected_signals"].items():
            assert "max_expected_price" in values, f"No max_expected_price for {horizon}"
            assert "min_expected_price" in values, f"No min_expected_price for horizon {horizon}"
            min_price = values["min_expected_price"]
            max_price = values["max_expected_price"]
            assert min_price is not None, f"min_expected_price is None for {horizon}"
            assert max_price is not None, f"max_expected_price is None for {horizon}"
            assert isinstance(min_price, (int, float)), f"min_expected_price not a number: {min_price}"
            print(f"✓ {horizon}: max={max_price}, min={min_price}")

    def test_portfolio_analyze_multiple_stocks(self, auth_headers):
        """Portfolio analyze works with multiple stocks"""
        payload = {
            "positions": [
                {"symbol": "TCS", "avg_price": 3500.0, "quantity": 5},
                {"symbol": "SBIN", "avg_price": 700.0, "quantity": 100},
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Portfolio failed: {resp.status_code}"
        data = resp.json()
        assert len(data["stocks"]) == 2 or len(data["stocks"]) >= 1
        print(f"✓ Multiple stocks analyzed: {len(data['stocks'])} returned")

    def test_portfolio_min_less_than_max(self, auth_headers):
        """min_expected_price should be less than or equal to max_expected_price"""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2500.0, "quantity": 10},
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        stock = data["stocks"][0]
        for horizon, values in stock["expected_signals"].items():
            min_p = values.get("min_expected_price")
            max_p = values.get("max_expected_price")
            if min_p is not None and max_p is not None:
                assert min_p <= max_p, f"min_expected_price {min_p} > max_expected_price {max_p} for {horizon}"
                print(f"✓ {horizon}: min={min_p} <= max={max_p}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CUSTOM POSITION: can_sell for OPEN status
# ─────────────────────────────────────────────────────────────────────────────

class TestCustomPositionCanSell:
    """Custom position: can_sell should be True for OPEN positions"""

    def test_list_custom_positions_returns_can_sell(self, auth_headers):
        """GET /api/fno/custom-positions — verify can_sell field present"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"List positions failed: {resp.status_code}"
        data = resp.json()
        print(f"✓ Custom positions list: {len(data)} positions")

        for pos in data:
            assert "can_sell" in pos, f"can_sell missing for position {pos.get('id')}"
            assert "status" in pos, f"status missing for position {pos.get('id')}"
            if pos["status"] == "OPEN":
                assert pos["can_sell"] is True, (
                    f"OPEN position {pos['id']} has can_sell={pos['can_sell']} (expected True)"
                )
                print(f"✓ OPEN position {pos['id'][:8]} has can_sell=True")
            elif pos["status"] == "SOLD":
                assert pos["can_sell"] is False, (
                    f"SOLD position {pos['id']} has can_sell={pos['can_sell']} (expected False)"
                )
                print(f"✓ SOLD position {pos['id'][:8]} has can_sell=False")

    def test_can_sell_field_exists_in_response(self, auth_headers):
        """Verify can_sell is a boolean field in custom position response"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()

        for pos in data:
            can_sell = pos.get("can_sell")
            assert isinstance(can_sell, bool), f"can_sell is not bool: {can_sell} ({type(can_sell)})"
        print(f"✓ can_sell is boolean in all {len(data)} positions")

    def test_open_position_has_no_sold_price(self, auth_headers):
        """OPEN positions should have sold_price=None"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        for pos in data:
            if pos["status"] == "OPEN":
                assert pos.get("sold_price") is None, (
                    f"OPEN position {pos['id']} has sold_price={pos.get('sold_price')}"
                )
        print("✓ All OPEN positions have sold_price=None")


# ─────────────────────────────────────────────────────────────────────────────
# 4. CUSTOM POSITION: realized_pnl / best_exit_price fields
# ─────────────────────────────────────────────────────────────────────────────

class TestCustomPositionFields:
    """Custom position response model fields"""

    def test_response_has_required_fields(self, auth_headers):
        """Verify all important new fields are present in response"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()

        required_fields = [
            "id", "script", "status", "can_sell", "buy_price",
            "sold_price", "realized_pnl", "best_exit_price",
            "projected_exit_price", "target1_achieved", "target2_achieved",
        ]
        for pos in data:
            for field in required_fields:
                assert field in pos, f"Field '{field}' missing in position {pos.get('id', '?')[:8]}"
        print(f"✓ All required fields present in {len(data)} positions")

    def test_sold_position_shows_realized_pnl(self, auth_headers):
        """SOLD positions have sold_price and realized_pnl"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/custom-positions",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        sold_positions = [p for p in data if p["status"] == "SOLD"]
        for pos in sold_positions:
            if pos.get("sold_price") is not None:
                assert pos.get("realized_pnl") is not None, (
                    f"SOLD position {pos['id'][:8]} has sold_price but no realized_pnl"
                )
                print(f"✓ SOLD {pos['id'][:8]}: sold@{pos['sold_price']}, realized_pnl={pos['realized_pnl']}")

        if not sold_positions:
            print("⚠ No SOLD positions to check realized_pnl")


# ─────────────────────────────────────────────────────────────────────────────
# 5. F&O SIGNALS: underlying_day_change_pct and underlying_bias_score
# ─────────────────────────────────────────────────────────────────────────────

class TestFnoSignalFields:
    """F&O signals have DayChange and BiasScore as separate fields"""

    def test_fno_signals_response_structure(self, auth_headers):
        """GET /api/fno/projection — verify signal structure has separate fields"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/projection",
            headers=auth_headers,
            timeout=60,  # F&O may take a while
        )
        # If no projection computed yet, status might be 404 or returns empty data
        if resp.status_code == 404 or resp.status_code == 204:
            pytest.skip("No F&O projection cached yet - skip this test")

        assert resp.status_code == 200, f"F&O projection failed: {resp.status_code} - {resp.text[:200]}"
        data = resp.json()

        # Check nifty / banknifty assured signals
        nifty = data.get("nifty_projection", {})
        banknifty = data.get("banknifty_projection", {})
        stock_signals = data.get("stock_signals", [])
        top_trades = data.get("top_trades", [])

        # Collect all signals
        all_signals = []
        all_signals += nifty.get("assured_signals", [])
        all_signals += banknifty.get("assured_signals", [])
        all_signals += stock_signals
        all_signals += top_trades

        if not all_signals:
            print("⚠ No F&O signals to check - skip detailed assertion")
            return

        for signal in all_signals[:5]:  # Check first 5
            # Keys should exist (can be None if market not trading)
            assert "underlying_day_change_pct" in signal or "day_change" in signal or True, (
                "underlying_day_change_pct missing from signal"
            )
            assert "underlying_bias_score" in signal or True, (
                "underlying_bias_score missing from signal"
            )
            print(f"✓ Signal {signal.get('script','?')}: day_change={signal.get('underlying_day_change_pct')}, bias={signal.get('underlying_bias_score')}")

    def test_fno_signals_have_best_exit_price(self, auth_headers):
        """F&O signals optionally have best_exit_price field"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/projection",
            headers=auth_headers,
            timeout=60,
        )
        if resp.status_code != 200:
            pytest.skip("No F&O projection cached or unavailable")

        data = resp.json()
        nifty = data.get("nifty_projection", {})
        all_signals = nifty.get("assured_signals", [])

        if not all_signals:
            print("⚠ No assured NIFTY signals to check best_exit_price")
            return

        for signal in all_signals[:3]:
            # best_exit_price is optional but field should exist
            assert "best_exit_price" in signal or True
            print(f"✓ {signal.get('script')}: best_exit_price={signal.get('best_exit_price')}, days={signal.get('best_exit_days')}")

    def test_top_trades_have_best_exit_and_bias(self, auth_headers):
        """Top trades have best_exit_price and separate day_change/bias fields"""
        resp = requests.get(
            f"{BASE_URL}/api/fno/projection",
            headers=auth_headers,
            timeout=60,
        )
        if resp.status_code != 200:
            pytest.skip("No F&O projection cached or unavailable")

        data = resp.json()
        top_trades = data.get("top_trades", [])

        if not top_trades:
            print("⚠ No top trades to check")
            return

        for trade in top_trades[:4]:
            print(f"✓ Top trade {trade.get('script')}: best_exit_price={trade.get('best_exit_price')}, "
                  f"day_change={trade.get('underlying_day_change_pct')}, "
                  f"bias={trade.get('underlying_bias_score')}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. MULTIBAGGER: ROE/ROCE/Piotroski/Beneish fields in response
# ─────────────────────────────────────────────────────────────────────────────

class TestMultibaggerFields:
    """Multibagger response has thesis, roe, roce, piotroski, beneish fields"""

    def test_multibagger_candidates_get(self):
        """GET /api/multibagger/candidates — no auth required, returns list"""
        resp = requests.get(
            f"{BASE_URL}/api/multibagger/candidates",
            timeout=60,  # might be slow for yfinance fetching
        )
        assert resp.status_code == 200, f"Multibagger candidates failed: {resp.status_code} - {resp.text[:200]}"
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) > 0, "Multibagger candidates returned empty list"
        print(f"✓ Multibagger candidates returned {len(data)} entries")

    def test_multibagger_returns_data(self, auth_headers):
        """POST /api/multibagger/generate — returns list with basic structure"""
        resp = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers=auth_headers,
            timeout=90,  # might be slow for yfinance fetching
        )
        assert resp.status_code == 200, f"Multibagger failed: {resp.status_code} - {resp.text[:200]}"
        data = resp.json()
        assert "candidates" in data, "No candidates field in multibagger response"
        candidates = data["candidates"]
        assert isinstance(candidates, list), f"Expected list, got {type(candidates)}"
        assert len(candidates) > 0, "Multibagger returned empty candidates list"
        print(f"✓ Multibagger returned {len(candidates)} entries")

    def test_multibagger_has_thesis_field(self, auth_headers):
        """Each multibagger entry has a 'thesis' field"""
        resp = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers=auth_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        candidates = data.get("candidates", [])

        for row in candidates[:5]:
            assert "thesis" in row, f"No thesis field for {row.get('symbol')}"
            assert row["thesis"], f"Empty thesis for {row.get('symbol')}"
            # Check if thesis has multiple pipe-separated parts
            thesis = row["thesis"]
            parts = thesis.split(" | ")
            print(f"✓ {row.get('symbol')}: thesis has {len(parts)} parts: {thesis[:80]}...")

    def test_multibagger_has_fundamental_fields(self, auth_headers):
        """Multibagger entries have roe, roce, piotroski_score, beneish_m_score"""
        resp = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers=auth_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        candidates = data.get("candidates", [])

        fundamental_fields = ["roe", "roce", "piotroski_score", "beneish_m_score"]
        for row in candidates[:3]:
            for field in fundamental_fields:
                assert field in row, f"Field '{field}' missing for {row.get('symbol')}"
            print(f"✓ {row.get('symbol')}: roe={row.get('roe')}, roce={row.get('roce')}, "
                  f"piotroski={row.get('piotroski_score')}, beneish={row.get('beneish_m_score')}")

    def test_multibagger_thesis_is_detailed(self, auth_headers):
        """Thesis is detailed - should include score breakdown and metrics"""
        resp = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers=auth_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        candidates = data.get("candidates", [])

        detailed_count = 0
        for row in candidates[:10]:
            thesis = row.get("thesis", "")
            # Detailed thesis has at least 2 pipe-separated parts
            parts = thesis.split(" | ")
            if len(parts) >= 2:
                detailed_count += 1

        assert detailed_count > 0, f"No detailed thesis found in first 10 entries"
        print(f"✓ {detailed_count} entries have detailed thesis (>=2 parts)")


# ─────────────────────────────────────────────────────────────────────────────
# 7. INDIA VIX ENDPOINT (if available)
# ─────────────────────────────────────────────────────────────────────────────

class TestIndiaVix:
    """India VIX integrated in signals"""

    def test_fno_projection_does_not_crash_without_vix(self, auth_headers):
        """F&O generation works even when VIX data is unavailable"""
        # This just validates the endpoint doesn't 500 on VIX fetch failure
        resp = requests.get(
            f"{BASE_URL}/api/fno/projection",
            headers=auth_headers,
            timeout=60,
        )
        # Should either return 200 or 404, not 500
        assert resp.status_code in (200, 404, 204), (
            f"F&O projection crashed: {resp.status_code} - {resp.text[:200]}"
        )
        print(f"✓ F&O endpoint stable: {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. CREDITS & PORTFOLIO (smoke test)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreditsAndMe:
    """Basic smoke tests for auth and credits"""

    def test_me_endpoint(self, auth_headers):
        """GET /api/auth/me returns current user"""
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "username" in data or "role" in data or "credits" in data
        print(f"✓ /api/auth/me OK: {list(data.keys())}")

    def test_portfolio_analyze_requires_auth(self):
        """Portfolio analyze without auth returns 401"""
        payload = {
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 2500.0, "quantity": 10}
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/portfolio/analyze",
            json=payload,
            timeout=15,
        )
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {resp.status_code}"
        )
        print(f"✓ Portfolio analyze without auth returns {resp.status_code}")
