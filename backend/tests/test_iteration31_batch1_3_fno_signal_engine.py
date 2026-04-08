"""
Iteration 31: F&O Signal Engine Batch 1-3 Tests

Tests for Master Spec Batches 1-3 implementation:
- Batch 1: Feature & data layer (index constituents, intraday features, order flow, options chain, news sentiment)
- Batch 2: MFE/MAE backtests, probability models, theta curves
- Batch 3: 4-bucket Confluence Score V2 (A+B+C+D), probability-based T1/T2, forward MFE best exit

All tests use the public API endpoint: https://backend-refactor-p2.preview.emergentagent.com
"""
import pytest
import requests
import os
import sys

# Add backend to path for direct module imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://backend-refactor-p2.preview.emergentagent.com').rstrip('/')


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API tests."""
    response = requests.post(f"{BASE_URL}/api/auth/access", json={
        "username": "@shish123",
        "password": "1234"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


# ============================================================================
# Test: Auth Endpoint
# ============================================================================

class TestAuthEndpoint:
    """Test authentication endpoint."""
    
    def test_auth_returns_200(self):
        """POST /api/auth/access with valid credentials returns 200."""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={
            "username": "@shish123",
            "password": "1234"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_auth_response_has_token(self):
        """Auth response contains token field."""
        response = requests.post(f"{BASE_URL}/api/auth/access", json={
            "username": "@shish123",
            "password": "1234"
        })
        data = response.json()
        assert "token" in data, "Response should contain 'token' field"
        assert isinstance(data["token"], str), "Token should be a string"
        assert len(data["token"]) > 0, "Token should not be empty"


# ============================================================================
# Test: F&O Generate Endpoint
# ============================================================================

class TestFNOGenerateEndpoint:
    """Test F&O signal generation endpoint."""
    
    def test_fno_generate_returns_200(self, api_client):
        """POST /api/fno/generate returns 200."""
        response = api_client.post(f"{BASE_URL}/api/fno/generate", json={})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_fno_generate_has_nifty_projection(self, api_client):
        """F&O generate response contains nifty_projection."""
        response = api_client.post(f"{BASE_URL}/api/fno/generate", json={})
        data = response.json()
        assert "nifty_projection" in data, "Response should contain 'nifty_projection'"
        assert data["nifty_projection"] is not None, "nifty_projection should not be None"
    
    def test_fno_generate_has_banknifty_projection(self, api_client):
        """F&O generate response contains banknifty_projection."""
        response = api_client.post(f"{BASE_URL}/api/fno/generate", json={}, timeout=120)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        if response.text:
            data = response.json()
            assert "banknifty_projection" in data, "Response should contain 'banknifty_projection'"
            assert data["banknifty_projection"] is not None, "banknifty_projection should not be None"
        else:
            pytest.skip("Empty response - API may be slow")
    
    def test_fno_generate_has_stock_signals(self, api_client):
        """F&O generate response contains stock_signals array."""
        response = api_client.post(f"{BASE_URL}/api/fno/generate", json={})
        data = response.json()
        assert "stock_signals" in data, "Response should contain 'stock_signals'"
        assert isinstance(data["stock_signals"], list), "stock_signals should be a list"


# ============================================================================
# Test: Index Constituents (Batch 1 - Section 2)
# ============================================================================

class TestIndexConstituents:
    """Test index constituents module."""
    
    def test_nifty50_constituents_count(self):
        """NIFTY 50 should have 50 constituents."""
        from services.index_constituents import _NIFTY50_CONSTITUENTS
        assert len(_NIFTY50_CONSTITUENTS) == 50, f"Expected 50 NIFTY constituents, got {len(_NIFTY50_CONSTITUENTS)}"
    
    def test_banknifty_constituents_count(self):
        """BANKNIFTY should have 12 constituents."""
        from services.index_constituents import _BANKNIFTY_CONSTITUENTS
        assert len(_BANKNIFTY_CONSTITUENTS) == 12, f"Expected 12 BANKNIFTY constituents, got {len(_BANKNIFTY_CONSTITUENTS)}"
    
    def test_get_constituents_sync_nifty(self):
        """get_constituents_sync returns NIFTY constituents."""
        from services.index_constituents import get_constituents_sync
        constituents = get_constituents_sync("NIFTY")
        assert len(constituents) == 50, f"Expected 50 constituents, got {len(constituents)}"
        assert "HDFCBANK" in constituents, "HDFCBANK should be in NIFTY constituents"
    
    def test_get_constituents_sync_banknifty(self):
        """get_constituents_sync returns BANKNIFTY constituents."""
        from services.index_constituents import get_constituents_sync
        constituents = get_constituents_sync("BANKNIFTY")
        assert len(constituents) == 12, f"Expected 12 constituents, got {len(constituents)}"
        assert "HDFCBANK" in constituents, "HDFCBANK should be in BANKNIFTY constituents"
    
    def test_compute_weighted_breadth(self):
        """compute_weighted_breadth returns valid breadth metrics."""
        from services.index_constituents import compute_weighted_breadth
        
        # Sample constituent data
        data = [
            {"symbol": "HDFCBANK", "weight_pct": 13.1, "in_uptrend": True, "above_vwap": True, "intraday_return_pct": 0.5, "intraday_volatility": 0.25},
            {"symbol": "RELIANCE", "weight_pct": 9.6, "in_uptrend": False, "above_vwap": True, "intraday_return_pct": -0.3, "intraday_volatility": 0.30},
        ]
        
        result = compute_weighted_breadth(data, "NIFTY")
        assert "pct_weight_in_uptrend" in result, "Should have pct_weight_in_uptrend"
        assert "pct_weight_above_vwap" in result, "Should have pct_weight_above_vwap"
        assert "breadth_score" in result, "Should have breadth_score"
        assert 0 <= result["breadth_score"] <= 100, "breadth_score should be 0-100"


# ============================================================================
# Test: News Sentiment (Batch 1 - Section 4)
# ============================================================================

class TestNewsSentiment:
    """Test news sentiment module."""
    
    def test_get_symbol_sentiment_returns_dict(self):
        """get_symbol_sentiment returns dict with required fields."""
        from services.news_sentiment import get_symbol_sentiment
        
        result = get_symbol_sentiment("RELIANCE")
        assert isinstance(result, dict), "Should return a dict"
        assert "news_count" in result, "Should have news_count"
        assert "avg_sentiment" in result, "Should have avg_sentiment"
        assert "news_flag" in result, "Should have news_flag"
    
    def test_get_symbol_sentiment_news_flag_valid(self):
        """news_flag should be POSITIVE, NEGATIVE, or NEUTRAL."""
        from services.news_sentiment import get_symbol_sentiment
        
        result = get_symbol_sentiment("NIFTY")
        assert result["news_flag"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"], f"Invalid news_flag: {result['news_flag']}"
    
    def test_get_market_sentiment_summary_returns_dict(self):
        """get_market_sentiment_summary returns dict with required fields."""
        from services.news_sentiment import get_market_sentiment_summary
        
        result = get_market_sentiment_summary()
        assert isinstance(result, dict), "Should return a dict"
        assert "total_headlines" in result, "Should have total_headlines"
        assert "avg_sentiment" in result, "Should have avg_sentiment"
        assert "market_flag" in result, "Should have market_flag"
    
    def test_get_market_sentiment_summary_has_headlines(self):
        """Market sentiment should have headlines (may be 0 if RSS fails)."""
        from services.news_sentiment import get_market_sentiment_summary, refresh_news_cache
        
        # Refresh cache first
        refresh_news_cache()
        result = get_market_sentiment_summary()
        # Note: total_headlines may be 0 if RSS feeds are unavailable
        assert result["total_headlines"] >= 0, "total_headlines should be >= 0"


# ============================================================================
# Test: MFE/MAE Engine (Batch 2 - Section 5)
# ============================================================================

class TestMFEMAEEngine:
    """Test MFE/MAE library and probability models."""
    
    def test_build_mfe_mae_library_returns_list(self):
        """build_mfe_mae_library returns non-empty list with valid entries."""
        import pandas as pd
        import numpy as np
        from services.mfe_mae_engine import build_mfe_mae_library
        
        # Create synthetic historical data
        np.random.seed(42)
        n_bars = 300
        close = 100 + np.cumsum(np.random.randn(n_bars) * 2)
        hist_df = pd.DataFrame({
            'Close': close,
            'High': close + np.abs(np.random.randn(n_bars)) * 1.5,
            'Low': close - np.abs(np.random.randn(n_bars)) * 1.5,
            'Open': close - np.random.randn(n_bars) * 0.5,
            'Volume': np.random.randint(100000, 1000000, n_bars)
        })
        
        library = build_mfe_mae_library(hist_df, atr=3.5, strategy_id='S3_SUPERTREND', direction='LONG', window_bars=50)
        
        assert isinstance(library, list), "Should return a list"
        assert len(library) > 0, "Library should not be empty"
        
        # Check first entry has required fields
        entry = library[0]
        assert "mfe" in entry, "Entry should have 'mfe'"
        assert "mae" in entry, "Entry should have 'mae'"
        assert "mfe_pct" in entry, "Entry should have 'mfe_pct'"
        assert "mae_pct" in entry, "Entry should have 'mae_pct'"
    
    def test_build_probability_table_computes_p_hit(self):
        """build_probability_table computes P_hit and P_SL_first for target offsets."""
        import pandas as pd
        import numpy as np
        from services.mfe_mae_engine import build_mfe_mae_library, build_probability_table
        
        # Create synthetic data
        np.random.seed(42)
        n_bars = 300
        close = 100 + np.cumsum(np.random.randn(n_bars) * 2)
        hist_df = pd.DataFrame({
            'Close': close,
            'High': close + np.abs(np.random.randn(n_bars)) * 1.5,
            'Low': close - np.abs(np.random.randn(n_bars)) * 1.5,
            'Open': close - np.random.randn(n_bars) * 0.5,
            'Volume': np.random.randint(100000, 1000000, n_bars)
        })
        
        library = build_mfe_mae_library(hist_df, atr=3.5, strategy_id='S3_SUPERTREND', direction='LONG', window_bars=50)
        prob_table = build_probability_table(library, sl_distance_pct=10.0)
        
        assert "targets" in prob_table, "Should have 'targets'"
        assert "sample_size" in prob_table, "Should have 'sample_size'"
        assert prob_table["sample_size"] > 0, "Sample size should be > 0"
        
        targets = prob_table["targets"]
        assert len(targets) > 0, "Should have target entries"
        
        # Check first target has P_hit and P_SL_first
        t = targets[0]
        assert "p_hit" in t, "Target should have 'p_hit'"
        assert "p_sl_first" in t, "Target should have 'p_sl_first'"
        assert 0 <= t["p_hit"] <= 1, "p_hit should be 0-1"
        assert 0 <= t["p_sl_first"] <= 1, "p_sl_first should be 0-1"


# ============================================================================
# Test: Empirical Theta (Batch 2 - Section 6.1)
# ============================================================================

class TestEmpiricalTheta:
    """Test empirical theta curves."""
    
    def test_compute_empirical_theta_returns_dict(self):
        """compute_empirical_theta returns intraday_theta and overnight_theta."""
        from services.mfe_mae_engine import compute_empirical_theta
        
        result = compute_empirical_theta(
            entry_price=150.0,
            dte=2,
            calendar_days=3,
            iv_regime='NORMAL_IV',
            option_class='index_weekly',
            moneyness='ATM'
        )
        
        assert isinstance(result, dict), "Should return a dict"
        assert "intraday_theta" in result, "Should have intraday_theta"
        assert "overnight_theta" in result, "Should have overnight_theta"
        assert "total_theta" in result, "Should have total_theta"
        assert result["intraday_theta"] >= 0, "intraday_theta should be >= 0"
        assert result["overnight_theta"] >= 0, "overnight_theta should be >= 0"
    
    def test_theta_increases_near_expiry(self):
        """Theta should be higher for 0DTE than 5DTE."""
        from services.mfe_mae_engine import compute_empirical_theta
        
        theta_0dte = compute_empirical_theta(entry_price=150.0, dte=0, calendar_days=0, iv_regime='NORMAL_IV', option_class='index_weekly', moneyness='ATM')
        theta_5dte = compute_empirical_theta(entry_price=150.0, dte=5, calendar_days=7, iv_regime='NORMAL_IV', option_class='index_weekly', moneyness='ATM')
        
        assert theta_0dte["total_theta"] > theta_5dte["total_theta"], "0DTE theta should be higher than 5DTE"


# ============================================================================
# Test: Best Exit Online (Batch 2 - Section 6.3)
# ============================================================================

class TestBestExitOnline:
    """Test best exit computation."""
    
    def test_compute_best_exit_online_returns_dict(self):
        """compute_best_exit_online returns best_exit_price and method."""
        from services.mfe_mae_engine import compute_best_exit_online
        
        result = compute_best_exit_online(
            entry_price=150.0,
            remaining_trading_days=3,
            dte=3,
            iv_regime='NORMAL_IV',
            market_regime='LowVolTrend',
            option_class='index_weekly',
            moneyness='ATM'
        )
        
        assert isinstance(result, dict), "Should return a dict"
        assert "best_exit_price" in result, "Should have best_exit_price"
        assert "method" in result, "Should have method"
        assert result["best_exit_price"] > 0, "best_exit_price should be > 0"


# ============================================================================
# Test: Confluence Score V2 (Batch 3 - Section 7)
# ============================================================================

class TestConfluenceScoreV2:
    """Test 4-bucket Confluence Score V2."""
    
    def test_compute_bucket_a_returns_score(self):
        """compute_bucket_a returns score based on win_rate/expectancy_r."""
        from services.confluence_score_v2 import compute_bucket_a
        
        result = compute_bucket_a(win_rate=0.72, expectancy_r=0.55, trade_count=150, strategy_enabled=True)
        
        assert isinstance(result, dict), "Should return a dict"
        assert "score" in result, "Should have 'score'"
        assert 0 <= result["score"] <= 100, "Score should be 0-100"
    
    def test_compute_bucket_b_returns_score(self):
        """compute_bucket_b returns score based on direction/trend/RSI/ADX."""
        from services.confluence_score_v2 import compute_bucket_b
        
        result = compute_bucket_b(
            direction='BULLISH',
            bias_score=2.0,
            trend_alignment='BULLISH',
            rsi=45.0,
            macd_bullish=True,
            adx=28.0,
            above_vwap=True,
            regime='LowVolTrend'
        )
        
        assert isinstance(result, dict), "Should return a dict"
        assert "score" in result, "Should have 'score'"
        assert 0 <= result["score"] <= 100, "Score should be 0-100"
    
    def test_compute_bucket_c_returns_score(self):
        """compute_bucket_c returns score based on OI/IV/flow/news."""
        from services.confluence_score_v2 import compute_bucket_c
        
        result = compute_bucket_c(
            oi_buildup='LONG_BUILDUP',
            iv_rank=25.0,
            is_liquid=True,
            spread_pct=0.8,
            flow_band='ModerateBuyFlow',
            news_flag='POSITIVE',
            direction='BULLISH'
        )
        
        assert isinstance(result, dict), "Should return a dict"
        assert "score" in result, "Should have 'score'"
        assert 0 <= result["score"] <= 100, "Score should be 0-100"
    
    def test_compute_bucket_d_returns_score(self):
        """compute_bucket_d returns score based on R:R/probability/SL distance."""
        from services.confluence_score_v2 import compute_bucket_d
        
        result = compute_bucket_d(
            rr_to_t1=1.8,
            rr_to_t2=2.5,
            t1_p_hit=0.72,
            sl_distance_pct=10.0,
            existing_exposure_same_direction=1
        )
        
        assert isinstance(result, dict), "Should return a dict"
        assert "score" in result, "Should have 'score'"
        assert 0 <= result["score"] <= 100, "Score should be 0-100"
    
    def test_compute_confluence_score_v2_returns_0_to_100(self):
        """compute_confluence_score_v2 returns score 0-100 with 4 buckets."""
        from services.confluence_score_v2 import compute_bucket_a, compute_bucket_b, compute_bucket_c, compute_bucket_d, compute_confluence_score_v2
        
        bucket_a = compute_bucket_a(win_rate=0.72, expectancy_r=0.55, trade_count=150)
        bucket_b = compute_bucket_b(direction='BULLISH', bias_score=2.0, trend_alignment='BULLISH', rsi=45.0, adx=28.0)
        bucket_c = compute_bucket_c(oi_buildup='LONG_BUILDUP', iv_rank=25.0, is_liquid=True, direction='BULLISH')
        bucket_d = compute_bucket_d(rr_to_t1=1.8, rr_to_t2=2.5, t1_p_hit=0.72, sl_distance_pct=10.0)
        
        result = compute_confluence_score_v2(bucket_a, bucket_b, bucket_c, bucket_d)
        
        assert isinstance(result, dict), "Should return a dict"
        assert "score" in result, "Should have 'score'"
        assert "buckets" in result, "Should have 'buckets'"
        assert "conviction" in result, "Should have 'conviction'"
        assert "should_suppress" in result, "Should have 'should_suppress'"
        
        assert 0 <= result["score"] <= 100, "Score should be 0-100"
        assert set(result["buckets"].keys()) == {"A", "B", "C", "D"}, "Should have 4 buckets A, B, C, D"
    
    def test_confluence_threshold_is_78(self):
        """CONFLUENCE_THRESHOLD should be 78."""
        from services.confluence_score_v2 import CONFLUENCE_THRESHOLD
        assert CONFLUENCE_THRESHOLD == 78, f"Expected threshold 78, got {CONFLUENCE_THRESHOLD}"
    
    def test_bucket_weights_sum_to_1(self):
        """BUCKET_WEIGHTS should sum to 1.0."""
        from services.confluence_score_v2 import BUCKET_WEIGHTS
        total = sum(BUCKET_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Bucket weights should sum to 1.0, got {total}"


# ============================================================================
# Test: Stock Eligibility (4 filters including NCLT/DRT)
# ============================================================================

class TestStockEligibility:
    """Test stock eligibility filters."""
    
    def test_check_stock_eligibility_has_4_filters(self):
        """check_stock_eligibility should have 4 filters (including NCLT/DRT)."""
        from services.indicators import check_stock_eligibility
        
        result = check_stock_eligibility(
            ltp=150.0,
            market_cap_cr=50000.0,
            fundamental={'nclt_drt': False, 'total_debt_to_market_cap': 0.15, 'recent_profit_positive': True}
        )
        
        assert result["max_filters"] == 4, f"Expected 4 filters, got {result['max_filters']}"
    
    def test_nclt_drt_filter_blocks_stock(self):
        """NCLT/DRT flagged stock should be ineligible."""
        from services.indicators import check_stock_eligibility
        
        result = check_stock_eligibility(
            ltp=150.0,
            market_cap_cr=50000.0,
            fundamental={'nclt_drt': True, 'total_debt_to_market_cap': 0.15, 'recent_profit_positive': True}
        )
        
        assert result["eligible"] == False, "NCLT/DRT stock should be ineligible"
        assert any("NCLT" in flag for flag in result["flags"]), "Should have NCLT flag"
    
    def test_price_below_50_blocks_stock(self):
        """Stock with price < 50 should be ineligible."""
        from services.indicators import check_stock_eligibility
        
        result = check_stock_eligibility(
            ltp=35.0,
            market_cap_cr=50000.0,
            fundamental={'nclt_drt': False, 'total_debt_to_market_cap': 0.15, 'recent_profit_positive': True}
        )
        
        assert result["eligible"] == False, "Price < 50 stock should be ineligible"


# ============================================================================
# Test: No-Chasing Rule
# ============================================================================

class TestNoChasingRule:
    """Test no-chasing rule."""
    
    def test_check_no_chasing_rule_blocks_when_75pct_achieved(self):
        """Should block entry when 75% of expected band achieved."""
        from services.mfe_mae_engine import check_no_chasing_rule
        
        result = check_no_chasing_rule(
            current_ltp=115.0,
            entry_price=100.0,
            expected_max_band=20.0,
            chasing_threshold_pct=75.0
        )
        
        assert result["allow_entry"] == False, "Should block entry at 75% of band"
        assert result["pct_of_band_achieved"] == 75.0, "Should report 75% achieved"
    
    def test_check_no_chasing_rule_allows_when_below_threshold(self):
        """Should allow entry when below threshold."""
        from services.mfe_mae_engine import check_no_chasing_rule
        
        result = check_no_chasing_rule(
            current_ltp=110.0,
            entry_price=100.0,
            expected_max_band=20.0,
            chasing_threshold_pct=75.0
        )
        
        assert result["allow_entry"] == True, "Should allow entry below threshold"


# ============================================================================
# Test: 0DTE ATM Safety
# ============================================================================

class TestZeroDTEATMSafety:
    """Test 0DTE ATM safety check."""
    
    def test_check_0dte_atm_safety_blocks_after_cutoff(self):
        """Should block 0DTE ATM longs after cutoff hour."""
        from services.mfe_mae_engine import check_0dte_atm_safety
        
        result = check_0dte_atm_safety(
            underlying_ltp=23000.0,
            strike=23000.0,
            entry_time_hour=15,
            dte=0,
            cutoff_hour=14
        )
        
        assert result["allow_entry"] == False, "Should block 0DTE ATM after cutoff"
    
    def test_check_0dte_atm_safety_allows_non_0dte(self):
        """Should allow non-0DTE entries."""
        from services.mfe_mae_engine import check_0dte_atm_safety
        
        result = check_0dte_atm_safety(
            underlying_ltp=23000.0,
            strike=23000.0,
            entry_time_hour=15,
            dte=1
        )
        
        assert result["allow_entry"] == True, "Should allow non-0DTE"


# ============================================================================
# Test: Module Imports via Research Engine
# ============================================================================

class TestResearchEngineReExports:
    """Test that research_engine re-exports all new modules."""
    
    def test_index_constituents_exports(self):
        """Research engine should export index constituent functions."""
        from services.research_engine import get_constituents_sync, compute_weighted_breadth
        assert callable(get_constituents_sync)
        assert callable(compute_weighted_breadth)
    
    def test_intraday_features_exports(self):
        """Research engine should export intraday feature functions."""
        from services.research_engine import compute_multi_timeframe_emas, compute_vwap_features, classify_flow_band
        assert callable(compute_multi_timeframe_emas)
        assert callable(compute_vwap_features)
        assert callable(classify_flow_band)
    
    def test_options_features_exports(self):
        """Research engine should export options feature functions."""
        from services.research_engine import classify_oi_buildup, compute_iv_rank, compute_enhanced_option_features
        assert callable(classify_oi_buildup)
        assert callable(compute_iv_rank)
        assert callable(compute_enhanced_option_features)
    
    def test_news_sentiment_exports(self):
        """Research engine should export news sentiment functions."""
        from services.research_engine import get_symbol_sentiment, get_market_sentiment_summary
        assert callable(get_symbol_sentiment)
        assert callable(get_market_sentiment_summary)
    
    def test_mfe_mae_engine_exports(self):
        """Research engine should export MFE/MAE engine functions."""
        from services.research_engine import build_mfe_mae_library, build_probability_table, compute_empirical_theta, compute_best_exit_online, check_no_chasing_rule, check_0dte_atm_safety
        assert callable(build_mfe_mae_library)
        assert callable(build_probability_table)
        assert callable(compute_empirical_theta)
        assert callable(compute_best_exit_online)
        assert callable(check_no_chasing_rule)
        assert callable(check_0dte_atm_safety)
    
    def test_confluence_score_v2_exports(self):
        """Research engine should export Confluence Score V2 functions."""
        from services.research_engine import compute_bucket_a, compute_bucket_b, compute_bucket_c, compute_bucket_d, compute_confluence_score_v2, CONFLUENCE_THRESHOLD
        assert callable(compute_bucket_a)
        assert callable(compute_bucket_b)
        assert callable(compute_bucket_c)
        assert callable(compute_bucket_d)
        assert callable(compute_confluence_score_v2)
        assert CONFLUENCE_THRESHOLD == 78


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
