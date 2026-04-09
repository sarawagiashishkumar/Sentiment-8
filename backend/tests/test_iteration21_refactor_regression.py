"""
Iteration 21: Regression tests for codebase refactoring.
Tests verify that all refactored modules work correctly after:
1. research_engine.py split into 8 modular files
2. server.py models extracted to models/__init__.py
3. App.js utilities extracted to utils/formatters.js, utils/exportUtils.js, components/shared/LiveInfoBox.jsx
"""
import os
import sys
import pytest
import requests

from tests.helpers.test_utils import get_base_url, get_ndjson_complete_data

# Add backend dir to path for import tests
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND_DIR)

BASE_URL = get_base_url()


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def auth_token(api_client):
    """Get admin token using @shish123 / 1234"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "pin": "1234"},
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Auth failed with {response.status_code}: {response.text}")


@pytest.fixture(scope="session")
def auth_client(api_client, auth_token):
    """Authenticated requests session"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


# ── Health check ─────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Verify backend root endpoint is healthy"""

    def test_root_returns_200(self, api_client):
        """GET /api/ returns 200"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200

    def test_root_has_message_field(self, api_client):
        """GET /api/ response has message field"""
        response = api_client.get(f"{BASE_URL}/api/")
        data = response.json()
        assert "message" in data

    def test_root_message_is_string(self, api_client):
        """GET /api/ message is a non-empty string"""
        response = api_client.get(f"{BASE_URL}/api/")
        data = response.json()
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0


# ── Authentication ────────────────────────────────────────────────────────────

class TestAuthentication:
    """Auth endpoint tests"""

    def test_auth_access_returns_200(self, api_client):
        """POST /api/auth/access with valid credentials"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "pin": "1234"},
        )
        assert response.status_code == 200

    def test_auth_access_returns_token(self, api_client):
        """Token field present in auth response"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "pin": "1234"},
        )
        data = response.json()
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 10

    def test_auth_access_returns_role(self, api_client):
        """Role field present in auth response"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "pin": "1234"},
        )
        data = response.json()
        assert "role" in data
        assert data["role"] in ["owner", "sub_admin", "user"]

    def test_auth_access_returns_user_key(self, api_client):
        """user_key field present in auth response"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "pin": "1234"},
        )
        data = response.json()
        assert "user_key" in data

    def test_auth_access_invalid_user_returns_error(self, api_client):
        """Invalid credentials should return error (non-200)"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "NONEXISTENT_USER_XYZ", "pin": "0000"},
        )
        assert response.status_code != 200


@pytest.fixture(scope="session")
def fno_response(auth_client):
    """Single session-level FNO generate response to avoid multiple expensive calls"""
    response = auth_client.post(f"{BASE_URL}/api/fno/generate", json={}, timeout=150)
    return response


# ── FNO Signals ───────────────────────────────────────────────────────────────

class TestFnoSignals:
    """Tests for FNO signals endpoints.
    Note: The main FNO generation endpoint is POST /api/fno/generate (auth required).
    GET /api/fno/signals/index returns index signals (no auth).
    """

    def test_fno_generate_requires_auth(self, api_client):
        """POST /api/fno/generate without auth returns 401/403/422"""
        # Temporarily use empty auth header
        headers = {"Content-Type": "application/json", "Authorization": "Bearer INVALID"}
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            json={},
            headers=headers,
            timeout=30,
        )
        assert response.status_code in [401, 403, 422]

    def test_fno_generate_with_auth_returns_200(self, fno_response):
        """POST /api/fno/generate with auth returns 200"""
        assert fno_response.status_code == 200

    def test_fno_generate_has_nifty_projection(self, fno_response):
        """FNO generate response contains nifty_projection"""
        if fno_response.status_code != 200:
            pytest.skip(f"FNO generate returned {fno_response.status_code}")
        data = get_ndjson_complete_data(fno_response)
        assert "nifty_projection" in data

    def test_fno_generate_has_banknifty_projection(self, fno_response):
        """FNO generate response contains banknifty_projection"""
        if fno_response.status_code != 200:
            pytest.skip(f"FNO generate returned {fno_response.status_code}")
        data = get_ndjson_complete_data(fno_response)
        assert "banknifty_projection" in data

    def test_fno_generate_nifty_projection_is_dict(self, fno_response):
        """nifty_projection is a dict"""
        if fno_response.status_code != 200:
            pytest.skip(f"FNO generate returned {fno_response.status_code}")
        data = get_ndjson_complete_data(fno_response)
        nifty = data.get("nifty_projection")
        assert isinstance(nifty, dict)

    def test_fno_generate_banknifty_projection_is_dict(self, fno_response):
        """banknifty_projection is a dict"""
        if fno_response.status_code != 200:
            pytest.skip(f"FNO generate returned {fno_response.status_code}")
        data = get_ndjson_complete_data(fno_response)
        bnf = data.get("banknifty_projection")
        assert isinstance(bnf, dict)

    def test_fno_signals_index_returns_list(self, api_client):
        """GET /api/fno/signals/index returns a list"""
        response = api_client.get(f"{BASE_URL}/api/fno/signals/index", timeout=60)
        # Note: This endpoint does not require auth
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ── Multibagger ───────────────────────────────────────────────────────────────

class TestMultibagger:
    """Tests for multibagger endpoints.
    Note: POST /api/multibagger/generate requires auth.
    GET /api/multibagger/candidates does not require auth.
    """

    def test_multibagger_generate_requires_auth(self):
        """POST /api/multibagger/generate without auth returns 401/403"""
        headers = {"Content-Type": "application/json", "Authorization": "Bearer INVALID"}
        response = requests.post(
            f"{BASE_URL}/api/multibagger/generate",
            headers=headers,
        )
        assert response.status_code in [401, 403, 422]

    def test_multibagger_generate_with_auth_returns_200(self, auth_client):
        """POST /api/multibagger/generate with auth returns 200"""
        response = auth_client.post(f"{BASE_URL}/api/multibagger/generate")
        assert response.status_code == 200

    def test_multibagger_generate_has_candidates(self, auth_client):
        """POST /api/multibagger/generate response has candidates list"""
        response = auth_client.post(f"{BASE_URL}/api/multibagger/generate")
        if response.status_code == 200:
            data = get_ndjson_complete_data(response)
            assert "candidates" in data
            assert isinstance(data["candidates"], list)


# ── Portfolio Analyze ─────────────────────────────────────────────────────────

class TestPortfolioAnalyze:
    """Tests for portfolio analyze endpoint"""

    def test_portfolio_analyze_requires_auth(self, api_client):
        """POST /api/portfolio/analyze without auth returns error"""
        response = api_client.post(
            f"{BASE_URL}/api/portfolio/analyze",
            headers={"Authorization": ""},
            json={"positions": []},
        )
        assert response.status_code in [401, 403, 422]

    def test_portfolio_analyze_with_auth_returns_response(self, auth_client):
        """POST /api/portfolio/analyze with minimal valid payload"""
        payload = {
            "positions": [
                {
                    "symbol": "RELIANCE",
                    "qty": 10,
                    "avg_buy_price": 2500.0,
                    "current_price": 2600.0,
                }
            ],
            "portfolio_value": 26000.0,
        }
        response = auth_client.post(f"{BASE_URL}/api/portfolio/analyze", json=payload)
        # Should succeed (200) or return a meaningful error (not 500)
        assert response.status_code in [200, 400, 422]


# ── Admin endpoints ───────────────────────────────────────────────────────────

class TestAdminEndpoints:
    """Tests for admin endpoints"""

    def test_nse_holidays_requires_auth(self, api_client):
        """GET /api/admin/nse-holidays without auth returns error"""
        response = api_client.get(
            f"{BASE_URL}/api/admin/nse-holidays",
            headers={"Authorization": ""},
        )
        assert response.status_code in [401, 403, 422]

    def test_nse_holidays_with_auth_returns_200(self, auth_client):
        """GET /api/admin/nse-holidays with auth returns 200"""
        response = auth_client.get(f"{BASE_URL}/api/admin/nse-holidays")
        assert response.status_code == 200

    def test_nse_holidays_returns_list(self, auth_client):
        """NSE holidays response has holidays key with a list"""
        response = auth_client.get(f"{BASE_URL}/api/admin/nse-holidays")
        data = response.json()
        # Response is {"holidays": [...], "total_in_memory": N}
        assert "holidays" in data or isinstance(data, list)
        holidays = data.get("holidays", data) if isinstance(data, dict) else data
        assert isinstance(holidays, list)

    def test_strategy_stats_requires_auth(self, api_client):
        """GET /api/admin/strategy-stats without auth returns error"""
        response = api_client.get(
            f"{BASE_URL}/api/admin/strategy-stats",
            headers={"Authorization": ""},
        )
        assert response.status_code in [401, 403, 422]

    def test_strategy_stats_with_auth_returns_200(self, auth_client):
        """GET /api/admin/strategy-stats with auth returns 200"""
        response = auth_client.get(f"{BASE_URL}/api/admin/strategy-stats")
        assert response.status_code == 200


# ── Research Engine Import Tests ──────────────────────────────────────────────

class TestResearchEngineImports:
    """Tests that all key functions are accessible from services.research_engine"""

    def test_import_research_engine_module(self):
        """research_engine module imports without error"""
        from services import research_engine  # noqa
        assert research_engine is not None

    def test_indicators_accessible(self):
        """Core indicator functions accessible"""
        from services.research_engine import (
            compute_rsi, compute_macd, compute_bollinger,
            compute_atr, compute_adx, compute_obv,
            compute_sma, compute_ema, compute_stochastic,
            compute_historical_volatility,
        )
        assert callable(compute_rsi)
        assert callable(compute_macd)
        assert callable(compute_bollinger)

    def test_advanced_indicators_accessible(self):
        """Advanced indicator functions accessible"""
        from services.research_engine import (
            compute_williams_r, compute_cci, compute_vpt,
            compute_ichimoku, compute_fibonacci_levels,
            compute_pivot_points, compute_support_resistance,
            detect_rsi_divergence, detect_candlestick_patterns,
            compute_multiframe_trend, detect_chart_patterns,
        )
        assert callable(compute_williams_r)
        assert callable(detect_candlestick_patterns)

    def test_technical_core_accessible(self):
        """Technical core functions accessible"""
        from services.research_engine import (
            compute_full_technical_snapshot,
            check_urgent_exit,
            compute_technical_confluence_bonus,
            compute_portfolio_verdict,
        )
        assert callable(compute_full_technical_snapshot)
        assert callable(check_urgent_exit)

    def test_forensic_audit_accessible(self):
        """Forensic audit functions accessible"""
        from services.research_engine import (
            compute_altman_z_score,
            compute_earnings_quality,
            compute_forensic_red_flags,
            compute_roic_vs_wacc,
            compute_growth_quality,
            compute_forensic_audit,
        )
        assert callable(compute_forensic_audit)

    def test_macro_context_accessible(self):
        """Macro context functions accessible"""
        from services.research_engine import (
            classify_market_regime_enhanced,
            compute_macro_context,
            get_sector_macro_beneficiaries,
            get_all_macro_events,
            REGIME_STRATEGY_GRID,
            SECTOR_MACRO_IMPACT_MAP,
        )
        assert callable(compute_macro_context)
        assert isinstance(REGIME_STRATEGY_GRID, dict)
        assert isinstance(SECTOR_MACRO_IMPACT_MAP, dict)

    def test_portfolio_risk_accessible(self):
        """Portfolio risk functions accessible"""
        from services.research_engine import (
            compute_portfolio_correlation_matrix,
            compute_portfolio_stress_tests,
            compute_diversification_audit,
            compute_upcoming_catalysts,
            merge_duplicate_holdings,
            compute_master_stock_snapshot,
            STRESS_SCENARIOS,
        )
        assert callable(merge_duplicate_holdings)
        assert callable(compute_master_stock_snapshot)
        assert isinstance(STRESS_SCENARIOS, (dict, list))

    def test_strategy_library_accessible(self):
        """Strategy library functions and constants accessible"""
        from services.research_engine import (
            STRATEGY_LIBRARY,
            NIFTY50_WEIGHTS,
            BANKNIFTY_WEIGHTS,
            SIGNAL_STATES,
            SIGNAL_TRANSITIONS,
            get_strategy_by_id,
            get_eligible_strategies,
            select_strategy_for_signal,
            update_backtest_stats,
            check_strategy_eligible,
            transition_signal_state,
            compute_index_constituent_bias,
        )
        # STRATEGY_LIBRARY is a dict (strategy_id → strategy data)
        assert isinstance(STRATEGY_LIBRARY, dict)
        assert len(STRATEGY_LIBRARY) > 0
        assert isinstance(NIFTY50_WEIGHTS, dict)
        assert isinstance(BANKNIFTY_WEIGHTS, dict)
        assert callable(transition_signal_state)
        assert callable(compute_index_constituent_bias)

    def test_horizon_trading_days_accessible(self):
        """HORIZON_TRADING_DAYS constant accessible"""
        from services.research_engine import HORIZON_TRADING_DAYS
        assert isinstance(HORIZON_TRADING_DAYS, (int, float, dict))

    def test_all_models_importable(self):
        """All Pydantic models importable from models/__init__.py"""
        from models import (
            StatusCheck, StatusCheckCreate, AccessRequest, AccessResponse, MeResponse,
            AdminUserView, AdminCreateUserRequest, AdminSetCreditsRequest,
            AdminSetQuotaRequest, AdminUserProfileUpdateRequest,
            DomainMappingCreateRequest, DomainMappingStatusUpdateRequest,
            ApiControlUpdateRequest, StockCoreNormalized,
            MultibaggerCandidate, FNOContract, FNOSignalResponse,
            NonDirectionalStrategy, IndexAnalysisReport, IndexProjectionPane,
            MultibaggerGenerateResponse, FNOGenerateRequest, FNOGenerateResponse,
            PortfolioPositionInput, PortfolioAnalyzeRequest,
            PortfolioHorizonRange, PortfolioExpectedSignal, PortfolioStockAnalysis,
            PortfolioAnalyzeResponse, CustomPositionCreateRequest,
            CustomPositionSellRequest, CustomPositionResponse,
            CustomPositionCreateResponse, ScriptSearchResult,
        )
        # If we got here without exception, all models imported correctly
        assert True

    def test_classify_market_regime_accessible(self):
        """classify_market_regime accessible from research_engine"""
        from services.research_engine import classify_market_regime
        assert callable(classify_market_regime)

    def test_check_stock_eligibility_accessible(self):
        """check_stock_eligibility accessible from research_engine"""
        from services.research_engine import check_stock_eligibility
        assert callable(check_stock_eligibility)

    def test_compute_atr_based_fno_targets_accessible(self):
        """compute_atr_based_fno_targets accessible"""
        from services.research_engine import compute_atr_based_fno_targets
        assert callable(compute_atr_based_fno_targets)

    def test_compute_realistic_price_bands_accessible(self):
        """compute_realistic_price_bands accessible"""
        from services.research_engine import compute_realistic_price_bands
        assert callable(compute_realistic_price_bands)

    def test_compute_portfolio_risk_metrics_accessible(self):
        """compute_portfolio_risk_metrics accessible"""
        from services.research_engine import compute_portfolio_risk_metrics
        assert callable(compute_portfolio_risk_metrics)
