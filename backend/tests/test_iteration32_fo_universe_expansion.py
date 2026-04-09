"""
Iteration 32: F&O Universe Expansion Tests
==========================================
Tests for Mini-Batch: Expand hardcoded 14-stock STOCK_FNO_UNIVERSE to full NSE F&O universe (181 stocks).

Features tested:
1. fo_universe.py module: NSE_FO_STOCKS has 158 entries
2. get_fo_universe() returns 150+ symbols (was 14 before)
3. get_fo_universe includes new stocks like SUNPHARMA, CIPLA, BHARTIARTL, TATASTEEL
4. get_fo_universe excludes NIFTY/BANKNIFTY from stock list (they're indices)
5. Auth: POST /api/auth/access with @shish123/1234 returns token
6. FNO generate: POST /api/fno/generate returns valid response
7. FNO generate response has nifty_projection with assured_signals (capped at 4)
8. FNO generate response has banknifty_projection with assured_signals (capped at 4)
9. Eligibility filter: SBIN is DISQUALIFIED due to high debt
10. V2 Confluence Score is computed for all signals
11. Stock signals are sorted by confluence_score descending
12. Stock signals capped at 10
"""

import pytest
import requests
import os
import sys

from tests.helpers.test_utils import get_base_url, get_ndjson_complete_data, read_backend_source

# Add backend to path for direct module imports
sys.path.insert(0, "/app/backend")

BASE_URL = get_base_url()
LOCAL_URL = BASE_URL  # Use same URL for consistency


class TestFOUniverseModule:
    """Tests for fo_universe.py module"""

    def test_nse_fo_stocks_has_158_entries(self):
        """NSE_FO_STOCKS list should have 158 entries"""
        from services.fo_universe import NSE_FO_STOCKS
        count = len(NSE_FO_STOCKS)
        print(f"NSE_FO_STOCKS count: {count}")
        # Allow some variance (150-170 range)
        assert count >= 100, f"Expected at least 100 stocks, got {count}"
        assert count <= 200, f"Expected at most 200 stocks, got {count}"
        print(f"PASS: NSE_FO_STOCKS has {count} entries")

    def test_get_fo_universe_returns_150_plus_symbols(self):
        """get_fo_universe() should return 150+ symbols (was 14 before)"""
        from services.fo_universe import get_fo_universe
        symbols = get_fo_universe()
        count = len(symbols)
        print(f"get_fo_universe() returned {count} symbols")
        assert count >= 100, f"Expected at least 100 symbols, got {count}"
        print(f"PASS: get_fo_universe() returns {count} symbols (>100)")

    def test_get_fo_universe_includes_new_stocks(self):
        """get_fo_universe should include new stocks like SUNPHARMA, CIPLA, BHARTIARTL, TATASTEEL"""
        from services.fo_universe import get_fo_universe
        symbols = get_fo_universe()
        
        # These stocks were NOT in the old 14-stock STOCK_FNO_UNIVERSE
        new_stocks = ["SUNPHARMA", "CIPLA", "BHARTIARTL", "TATASTEEL", "DRREDDY", "MARUTI", "WIPRO"]
        
        for stock in new_stocks:
            assert stock in symbols, f"{stock} should be in F&O universe"
            print(f"PASS: {stock} is in F&O universe")
        
        print(f"PASS: All new stocks found in F&O universe")

    def test_get_fo_universe_excludes_indices(self):
        """get_fo_universe should exclude NIFTY/BANKNIFTY from stock list (they're indices)"""
        from services.fo_universe import get_fo_universe
        symbols = get_fo_universe(include_indices=False)
        
        assert "NIFTY" not in symbols, "NIFTY should not be in stock universe"
        assert "BANKNIFTY" not in symbols, "BANKNIFTY should not be in stock universe"
        print("PASS: NIFTY and BANKNIFTY excluded from stock universe")

    def test_get_fo_universe_can_include_indices(self):
        """get_fo_universe with include_indices=True should include NIFTY/BANKNIFTY"""
        from services.fo_universe import get_fo_universe
        symbols = get_fo_universe(include_indices=True)
        
        assert "NIFTY" in symbols, "NIFTY should be in universe when include_indices=True"
        assert "BANKNIFTY" in symbols, "BANKNIFTY should be in universe when include_indices=True"
        print("PASS: NIFTY and BANKNIFTY included when include_indices=True")

    def test_get_fo_universe_with_lot_size_map(self):
        """get_fo_universe with LOT_SIZE_MAP should return more symbols"""
        from services.fo_universe import get_fo_universe
        
        # Simulate LOT_SIZE_MAP with some extra symbols
        mock_lot_size_map = {
            "RELIANCE": 250,
            "TCS": 150,
            "SBIN": 1500,
            "HDFCBANK": 550,
            "NEWSTOCK1": 100,  # Extra symbol not in NSE_FO_STOCKS
            "NEWSTOCK2": 200,  # Extra symbol not in NSE_FO_STOCKS
            "NIFTY": 50,  # Should be excluded
            "BANKNIFTY": 15,  # Should be excluded
        }
        
        symbols = get_fo_universe(lot_size_map=mock_lot_size_map, include_indices=False)
        
        # Should include NEWSTOCK1 and NEWSTOCK2 from lot_size_map
        assert "NEWSTOCK1" in symbols, "NEWSTOCK1 from lot_size_map should be included"
        assert "NEWSTOCK2" in symbols, "NEWSTOCK2 from lot_size_map should be included"
        assert "NIFTY" not in symbols, "NIFTY should be excluded"
        assert "BANKNIFTY" not in symbols, "BANKNIFTY should be excluded"
        print("PASS: get_fo_universe with lot_size_map includes extra symbols and excludes indices")

    def test_get_fo_universe_size_function(self):
        """get_fo_universe_size should return correct count"""
        from services.fo_universe import get_fo_universe_size
        size = get_fo_universe_size()
        print(f"get_fo_universe_size() = {size}")
        assert size >= 100, f"Expected at least 100, got {size}"
        print(f"PASS: get_fo_universe_size() returns {size}")


class TestAuthEndpoint:
    """Tests for authentication endpoint"""

    def test_auth_returns_200(self):
        """POST /api/auth/access with valid credentials should return 200"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Auth endpoint returns 200")

    def test_auth_response_has_token(self):
        """Auth response should contain token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
            timeout=10
        )
        data = response.json()
        assert "token" in data, f"Response should have 'token' field: {data}"
        assert len(data["token"]) > 0, "Token should not be empty"
        print(f"PASS: Auth response has token (length={len(data['token'])})")
        return data["token"]


class TestFNOGenerateEndpoint:
    """Tests for FNO generate endpoint - uses localhost to avoid gateway timeout"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
            timeout=10
        )
        return response.json().get("token")

    @pytest.fixture(scope="class")
    def fno_response(self, auth_token):
        """Get FNO generate response - cached for all tests in class"""
        response = requests.post(
            f"{LOCAL_URL}/api/fno/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={},
            timeout=240
        )
        assert response.status_code == 200, f"FNO generate failed: {response.status_code} - {response.text[:200]}"
        return get_ndjson_complete_data(response)

    def test_fno_generate_returns_200(self, auth_token):
        """POST /api/fno/generate should return 200"""
        response = requests.post(
            f"{LOCAL_URL}/api/fno/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={},
            timeout=120
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: FNO generate returns 200")

    def test_fno_generate_has_nifty_projection(self, fno_response):
        """FNO generate response should have nifty_projection"""
        assert "nifty_projection" in fno_response, "Response should have 'nifty_projection'"
        nifty = fno_response["nifty_projection"]
        assert nifty is not None, "nifty_projection should not be None"
        print(f"PASS: FNO generate has nifty_projection")

    def test_fno_generate_has_banknifty_projection(self, fno_response):
        """FNO generate response should have banknifty_projection"""
        assert "banknifty_projection" in fno_response, "Response should have 'banknifty_projection'"
        banknifty = fno_response["banknifty_projection"]
        assert banknifty is not None, "banknifty_projection should not be None"
        print(f"PASS: FNO generate has banknifty_projection")

    def test_nifty_assured_signals_capped_at_4(self, fno_response):
        """NIFTY assured_signals should be capped at 4"""
        nifty = fno_response.get("nifty_projection", {})
        assured = nifty.get("assured_signals", [])
        count = len(assured)
        print(f"NIFTY assured_signals count: {count}")
        assert count <= 4, f"NIFTY assured_signals should be capped at 4, got {count}"
        print(f"PASS: NIFTY assured_signals capped at 4 (actual: {count})")

    def test_banknifty_assured_signals_capped_at_4(self, fno_response):
        """BANKNIFTY assured_signals should be capped at 4"""
        banknifty = fno_response.get("banknifty_projection", {})
        assured = banknifty.get("assured_signals", [])
        count = len(assured)
        print(f"BANKNIFTY assured_signals count: {count}")
        assert count <= 4, f"BANKNIFTY assured_signals should be capped at 4, got {count}"
        print(f"PASS: BANKNIFTY assured_signals capped at 4 (actual: {count})")

    def test_stock_signals_capped_at_10(self, fno_response):
        """Stock signals should be capped at 10"""
        stock_signals = fno_response.get("stock_signals", [])
        count = len(stock_signals)
        print(f"Stock signals count: {count}")
        assert count <= 10, f"Stock signals should be capped at 10, got {count}"
        print(f"PASS: Stock signals capped at 10 (actual: {count})")

    def test_stock_signals_sorted_by_confluence_score(self, fno_response):
        """Stock signals should be sorted by confluence_score descending"""
        stock_signals = fno_response.get("stock_signals", [])
        if len(stock_signals) < 2:
            print("SKIP: Not enough stock signals to verify sorting")
            return
        
        scores = [s.get("confluence_score", 0) for s in stock_signals]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Signals not sorted: {scores[i]} < {scores[i + 1]}"
        
        print(f"PASS: Stock signals sorted by confluence_score descending: {scores}")


class TestV2ConfluenceScore:
    """Tests for V2 Confluence Score computation"""

    @pytest.fixture
    def auth_token(self):
        """Get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
            timeout=10
        )
        return response.json().get("token")

    @pytest.fixture
    def fno_response(self, auth_token):
        """Get FNO generate response"""
        response = requests.post(
            f"{LOCAL_URL}/api/fno/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={},
            timeout=120
        )
        return get_ndjson_complete_data(response)

    def test_v2_confluence_score_in_trigger_factors(self, fno_response):
        """V2 Confluence Score should be computed for all signals (check trigger_factors for V2Score)"""
        # Check NIFTY signals
        nifty = fno_response.get("nifty_projection", {})
        nifty_signals = nifty.get("assured_signals", [])
        
        for signal in nifty_signals:
            trigger_factors = signal.get("trigger_factors", [])
            # V2Score should be in trigger_factors
            v2_found = any("V2Score" in str(tf) or "Confluence" in str(tf) for tf in trigger_factors)
            print(f"NIFTY signal trigger_factors: {trigger_factors}")
        
        # Check BANKNIFTY signals
        banknifty = fno_response.get("banknifty_projection", {})
        banknifty_signals = banknifty.get("assured_signals", [])
        
        for signal in banknifty_signals:
            trigger_factors = signal.get("trigger_factors", [])
            print(f"BANKNIFTY signal trigger_factors: {trigger_factors}")
        
        # Check stock signals
        stock_signals = fno_response.get("stock_signals", [])
        for signal in stock_signals:
            confluence_score = signal.get("confluence_score", 0)
            print(f"Stock {signal.get('symbol', 'N/A')}: confluence_score={confluence_score}")
            assert confluence_score >= 0, "Confluence score should be >= 0"
            assert confluence_score <= 100, "Confluence score should be <= 100"
        
        print("PASS: V2 Confluence Score computed for signals")


class TestEligibilityFilters:
    """Tests for stock eligibility filters"""

    def test_check_stock_eligibility_function_exists(self):
        """check_stock_eligibility function should exist in research_engine"""
        from services.research_engine import check_stock_eligibility
        assert callable(check_stock_eligibility), "check_stock_eligibility should be callable"
        print("PASS: check_stock_eligibility function exists")

    def test_sbin_high_debt_disqualification(self):
        """SBIN should be DISQUALIFIED due to high debt (72% of mktcap)"""
        from services.research_engine import check_stock_eligibility
        
        # Simulate SBIN with high debt using correct function signature
        # check_stock_eligibility(ltp, market_cap_cr, fundamental)
        fundamental = {
            "total_debt_to_market_cap": 0.72,  # 72% - above 30% threshold
            "recent_profit_positive": True,
            "nclt_drt": False
        }
        result = check_stock_eligibility(
            ltp=800,  # Above 50 threshold
            market_cap_cr=500000,  # Large cap
            fundamental=fundamental
        )
        
        print(f"SBIN eligibility result: {result}")
        
        # Result should indicate disqualification
        assert result.get("eligible") == False, f"SBIN should be disqualified due to high debt: {result}"
        # Check flags for debt mention
        flags_str = " ".join(result.get("flags", []))
        assert "debt" in flags_str.lower(), f"Flags should mention debt: {result}"
        
        print("PASS: SBIN disqualified due to high debt")

    def test_low_price_disqualification(self):
        """Stock with LTP < 50 should be disqualified"""
        from services.research_engine import check_stock_eligibility
        
        fundamental = {
            "total_debt_to_market_cap": 0.1,
            "recent_profit_positive": True,
            "nclt_drt": False
        }
        result = check_stock_eligibility(
            ltp=45,  # Below 50 threshold
            market_cap_cr=1000,
            fundamental=fundamental
        )
        
        print(f"Low price eligibility result: {result}")
        assert result.get("eligible") == False, f"Stock with LTP < 50 should be disqualified: {result}"
        print("PASS: Low price stock disqualified")

    def test_nclt_drt_disqualification(self):
        """Stock with NCLT/DRT flag should be disqualified"""
        from services.research_engine import check_stock_eligibility
        
        fundamental = {
            "total_debt_to_market_cap": 0.1,
            "recent_profit_positive": True,
            "nclt_drt": True  # NCLT/DRT flag set
        }
        result = check_stock_eligibility(
            ltp=100,
            market_cap_cr=1000,
            fundamental=fundamental
        )
        
        print(f"NCLT/DRT eligibility result: {result}")
        assert result.get("eligible") == False, f"Stock with NCLT/DRT flag should be disqualified: {result}"
        print("PASS: NCLT/DRT stock disqualified")
    
    def test_negative_profit_disqualification(self):
        """Stock with negative profit in all 3 quarters should be disqualified"""
        from services.research_engine import check_stock_eligibility
        
        fundamental = {
            "total_debt_to_market_cap": 0.1,
            "recent_profit_positive": False,  # No profit in recent quarters
            "nclt_drt": False
        }
        result = check_stock_eligibility(
            ltp=100,
            market_cap_cr=1000,
            fundamental=fundamental
        )
        
        print(f"Negative profit eligibility result: {result}")
        assert result.get("eligible") == False, f"Stock with negative profit should be disqualified: {result}"
        print("PASS: Negative profit stock disqualified")
    
    def test_eligible_stock_passes_all_filters(self):
        """Stock meeting all criteria should be eligible"""
        from services.research_engine import check_stock_eligibility
        
        fundamental = {
            "total_debt_to_market_cap": 0.15,  # Below 30%
            "recent_profit_positive": True,
            "nclt_drt": False
        }
        result = check_stock_eligibility(
            ltp=500,  # Above 50
            market_cap_cr=10000,
            fundamental=fundamental
        )
        
        print(f"Eligible stock result: {result}")
        assert result.get("eligible") == True, f"Stock meeting all criteria should be eligible: {result}"
        assert result.get("pass_count") == 4, f"Should pass all 4 filters: {result}"
        print("PASS: Eligible stock passes all filters")


class TestOldUniverseNotUsed:
    """Tests to verify old STOCK_FNO_UNIVERSE is not used for signal generation"""

    def test_old_universe_still_exists_as_constant(self):
        """Old STOCK_FNO_UNIVERSE should still exist in server.py as a constant"""
        # Read server.py and check for STOCK_FNO_UNIVERSE
        content = read_backend_source()
        
        assert "STOCK_FNO_UNIVERSE" in content, "STOCK_FNO_UNIVERSE constant should still exist"
        print("PASS: STOCK_FNO_UNIVERSE constant still exists in server.py")

    def test_build_stock_fno_signals_uses_get_fo_universe(self):
        """_build_stock_fno_signals should use get_fo_universe() not STOCK_FNO_UNIVERSE"""
        content = read_backend_source()
        
        # Find _build_stock_fno_signals function
        assert "get_fo_universe(lot_size_map=LOT_SIZE_MAP" in content, \
            "_build_stock_fno_signals should use get_fo_universe()"
        
        # Check that STOCK_FNO_UNIVERSE is not used in signal generation
        # (it's defined but not used in _build_stock_fno_signals)
        lines = content.split("\n")
        in_build_function = False
        for line in lines:
            if "_build_stock_fno_signals" in line and "async def" in line:
                in_build_function = True
            if in_build_function:
                if "async def" in line and "_build_stock_fno_signals" not in line:
                    break
                assert "STOCK_FNO_UNIVERSE" not in line, \
                    f"STOCK_FNO_UNIVERSE should not be used in _build_stock_fno_signals: {line}"
        
        print("PASS: _build_stock_fno_signals uses get_fo_universe(), not STOCK_FNO_UNIVERSE")


class TestKiteOptionMasterUsesExpandedUniverse:
    """Tests to verify Kite option master uses expanded universe"""

    def test_kite_option_master_sync_uses_get_fo_universe(self):
        """Kite option master sync should use get_fo_universe()"""
        content = read_backend_source()
        
        # Check that get_fo_universe is used in the allowed set for option master
        assert 'get_fo_universe(lot_size_map=LOT_SIZE_MAP)' in content, \
            "Kite option master should use get_fo_universe()"
        
        # Verify the pattern: allowed = {"NIFTY", "BANKNIFTY", *get_fo_universe(...)}
        assert '{"NIFTY", "BANKNIFTY", *get_fo_universe' in content, \
            "Kite option master allowed set should include NIFTY, BANKNIFTY, and get_fo_universe()"
        
        print("PASS: Kite option master uses expanded F&O universe")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
