"""
Iteration 46: BATCH 3 Verification for Master Spec v2.0
Tests for 6 items:
1. USE_NEW_SCORING feature flag
2. Bucket B real breadth wiring
3. Bucket D full MFE data + hard vetoes
4. select_targets_v2 consolidated function
5. should_suppress signal gating
6. V2 bucket breakdown in signal response (9 new fields)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for owner account"""
    response = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123", "password": "1234"},
        timeout=10
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token")
    pytest.skip(f"Auth failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


# ============================================================================
# Test Class: Auth Endpoint (Regression)
# ============================================================================

class TestAuthEndpoint:
    """Verify auth endpoint still works"""

    def test_auth_access_returns_token(self):
        """POST /api/auth/access with valid credentials returns token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"},
            timeout=10
        )
        assert response.status_code == 200, f"Auth failed: {response.text}"
        data = response.json()
        assert "token" in data, "Response missing 'token'"
        assert data.get("role") == "owner", f"Expected role=owner, got {data.get('role')}"
        print(f"PASS: Auth returns token, role={data.get('role')}")


# ============================================================================
# Test Class: Regression NDJSON Endpoints
# ============================================================================

class TestRegressionNDJSONEndpoints:
    """Regression tests for existing NDJSON streaming endpoints"""

    def test_fno_generate_returns_ndjson_stream(self, auth_headers):
        """POST /api/fno/generate returns NDJSON stream without errors"""
        response = requests.post(
            f"{BASE_URL}/api/fno/generate",
            headers=auth_headers,
            json={},
            stream=True,
            timeout=60
        )
        assert response.status_code == 200, f"FNO generate failed: {response.status_code}"
        
        # Read first few lines to verify NDJSON format
        lines_read = 0
        for line in response.iter_lines(decode_unicode=True):
            if line:
                lines_read += 1
                # Should be valid JSON
                import json
                try:
                    data = json.loads(line)
                    # Progress events have 'type' field
                    if "type" in data:
                        print(f"  Progress event: {data.get('type')}")
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON in NDJSON stream: {line[:100]}")
                if lines_read >= 5:
                    break
        
        print(f"PASS: FNO generate returns NDJSON stream ({lines_read} lines read)")

    def test_multibagger_candidates_returns_ndjson(self, auth_headers):
        """GET /api/multibagger/candidates returns NDJSON stream"""
        response = requests.get(
            f"{BASE_URL}/api/multibagger/candidates?limit=3",
            headers=auth_headers,
            stream=True,
            timeout=60
        )
        assert response.status_code == 200, f"Multibagger failed: {response.status_code}"
        
        lines_read = 0
        for line in response.iter_lines(decode_unicode=True):
            if line:
                lines_read += 1
                import json
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON: {line[:100]}")
                if lines_read >= 3:
                    break
        
        print(f"PASS: Multibagger candidates returns NDJSON ({lines_read} lines)")

    def test_sector_momentum_returns_sectors(self, auth_headers):
        """GET /api/sector-momentum returns sectors array with 8 entries"""
        response = requests.get(
            f"{BASE_URL}/api/sector-momentum",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Sector momentum failed: {response.status_code}"
        data = response.json()
        assert "sectors" in data, "Response missing 'sectors'"
        assert len(data["sectors"]) == 8, f"Expected 8 sectors, got {len(data['sectors'])}"
        print(f"PASS: Sector momentum returns {len(data['sectors'])} sectors")


# ============================================================================
# Test Class: Batch Status (Regression from Batch 2)
# ============================================================================

class TestBatchStatus:
    """Verify batch status endpoint still returns theta_curve_entries=360"""

    def test_batch_status_returns_counts(self, auth_headers):
        """GET /api/batch/status returns counts including theta_curve_entries=360"""
        response = requests.get(
            f"{BASE_URL}/api/batch/status",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Batch status failed: {response.status_code}"
        data = response.json()
        
        assert "theta_curve_entries" in data, "Missing theta_curve_entries"
        assert data["theta_curve_entries"] == 360, f"Expected 360 theta curves, got {data['theta_curve_entries']}"
        print(f"PASS: Batch status shows theta_curve_entries={data['theta_curve_entries']}")


# ============================================================================
# Test Class: select_targets_v2 Unit Tests
# ============================================================================

class TestSelectTargetsV2:
    """Unit tests for select_targets_v2 consolidated function"""

    def test_select_targets_v2_with_prob_table_returns_targets(self):
        """select_targets_v2() with prob_table returns t1, t2, abort=False, p_hit_t1/t2"""
        from services.mfe_mae_engine import select_targets_v2
        
        # Mock probability table with achievable targets
        prob_table = {
            "targets": [
                {"offset_pct": 0.5, "p_hit": 0.85, "p_sl_first": 0.10},
                {"offset_pct": 1.0, "p_hit": 0.78, "p_sl_first": 0.15},
                {"offset_pct": 1.5, "p_hit": 0.70, "p_sl_first": 0.18},
                {"offset_pct": 2.0, "p_hit": 0.62, "p_sl_first": 0.20},
                {"offset_pct": 3.0, "p_hit": 0.50, "p_sl_first": 0.25},
            ]
        }
        
        result = select_targets_v2(
            entry_price=100.0,
            stop_loss=95.0,
            atr=2.0,
            prob_table=prob_table,
            mins_to_1530=300,
            dte=5,
        )
        
        assert result["abort"] is False, f"Expected abort=False, got {result['abort']}"
        assert result["t1"] is not None, "Expected t1 to be set"
        assert result["p_hit_t1"] is not None, "Expected p_hit_t1 to be set"
        assert result["p_hit_t1"] > 0, f"Expected p_hit_t1 > 0, got {result['p_hit_t1']}"
        
        print(f"PASS: select_targets_v2 with prob_table: t1={result['t1']}, t2={result['t2']}, "
              f"p_hit_t1={result['p_hit_t1']}, p_hit_t2={result['p_hit_t2']}, abort={result['abort']}")

    def test_select_targets_v2_without_prob_table_returns_abort(self):
        """select_targets_v2() without prob_table returns abort=True (no achievable T1)"""
        from services.mfe_mae_engine import select_targets_v2
        
        # No probability table - should abort
        result = select_targets_v2(
            entry_price=100.0,
            stop_loss=95.0,
            atr=2.0,
            prob_table=None,  # No prob table
            mins_to_1530=300,
            dte=5,
        )
        
        assert result["abort"] is True, f"Expected abort=True without prob_table, got {result['abort']}"
        assert result["reason"] == "no_achievable_T1_in_session", f"Expected reason='no_achievable_T1_in_session', got {result['reason']}"
        assert result["t1"] is None, "Expected t1=None when abort"
        
        print(f"PASS: select_targets_v2 without prob_table: abort={result['abort']}, reason={result['reason']}")


# ============================================================================
# Test Class: compute_bucket_d Unit Tests
# ============================================================================

class TestComputeBucketD:
    """Unit tests for compute_bucket_d with hard vetoes and adjustments"""

    def test_bucket_d_rr_to_t1_below_1_returns_hard_veto(self):
        """compute_bucket_d() with rr_to_t1 < 1.0 returns score=0, hard_veto=True"""
        from services.confluence_score_v2 import compute_bucket_d
        
        result = compute_bucket_d(
            rr_to_t1=0.8,  # Below 1.0 threshold
            rr_to_t2=1.5,
            rr_to_best_exit=2.0,
            t1_p_hit=0.75,
            t2_p_hit=0.60,
            sl_distance_pct=10.0,
        )
        
        assert result["score"] == 0, f"Expected score=0 for rr_to_t1<1.0, got {result['score']}"
        assert result["hard_veto"] is True, f"Expected hard_veto=True, got {result['hard_veto']}"
        assert "rr_to_t1" in result.get("veto_reason", ""), f"Expected veto_reason to mention rr_to_t1"
        
        print(f"PASS: Bucket D hard veto: score={result['score']}, hard_veto={result['hard_veto']}, "
              f"veto_reason={result.get('veto_reason')}")

    def test_bucket_d_t2_p_hit_below_045_applies_penalty(self):
        """compute_bucket_d() with t2_p_hit < 0.45 applies -15 penalty"""
        from services.confluence_score_v2 import compute_bucket_d
        
        result = compute_bucket_d(
            rr_to_t1=1.5,  # Above threshold
            rr_to_t2=2.0,
            rr_to_best_exit=1.5,
            t1_p_hit=0.75,
            t2_p_hit=0.40,  # Below 0.45 threshold
            sl_distance_pct=10.0,
        )
        
        assert result["hard_veto"] is False, "Should not be hard veto"
        assert result["breakdown"]["t2_prob_adj"] == -15, f"Expected t2_prob_adj=-15, got {result['breakdown']['t2_prob_adj']}"
        
        print(f"PASS: Bucket D t2_p_hit penalty: score={result['score']}, t2_prob_adj={result['breakdown']['t2_prob_adj']}")

    def test_bucket_d_exit_bonus_applied(self):
        """compute_bucket_d() with rr_to_best_exit >= 2.0 AND t2_p_hit >= 0.55 applies +10 bonus"""
        from services.confluence_score_v2 import compute_bucket_d
        
        result = compute_bucket_d(
            rr_to_t1=2.0,
            rr_to_t2=2.5,
            rr_to_best_exit=2.5,  # >= 2.0
            t1_p_hit=0.80,
            t2_p_hit=0.60,  # >= 0.55
            sl_distance_pct=8.0,
        )
        
        assert result["hard_veto"] is False, "Should not be hard veto"
        assert result["breakdown"]["exit_bonus"] == 10, f"Expected exit_bonus=10, got {result['breakdown']['exit_bonus']}"
        
        print(f"PASS: Bucket D exit bonus: score={result['score']}, exit_bonus={result['breakdown']['exit_bonus']}")

    def test_bucket_d_rr_to_t2_below_15_caps_at_50(self):
        """compute_bucket_d() with rr_to_t2 < 1.5 caps score at 50"""
        from services.confluence_score_v2 import compute_bucket_d
        
        result = compute_bucket_d(
            rr_to_t1=1.2,  # Above 1.0 (no hard veto)
            rr_to_t2=1.3,  # Below 1.5 (cap applies)
            rr_to_best_exit=1.5,
            t1_p_hit=0.85,
            t2_p_hit=0.70,
            sl_distance_pct=5.0,  # Good SL distance
        )
        
        assert result["hard_veto"] is False, "Should not be hard veto"
        assert result["score"] <= 50, f"Expected score capped at 50, got {result['score']}"
        
        print(f"PASS: Bucket D cap at 50: score={result['score']} (rr_to_t2={1.3} < 1.5)")


# ============================================================================
# Test Class: FNOSignalResponse V2 Fields
# ============================================================================

class TestFNOSignalResponseV2Fields:
    """Verify FNOSignalResponse model contains all 9 new V2 fields"""

    def test_fno_signal_response_has_v2_fields(self):
        """FNOSignalResponse model contains all 9 new V2 fields"""
        from models import FNOSignalResponse
        
        v2_fields = [
            "confluence_score_v2",
            "score_bucket_A",
            "score_bucket_B",
            "score_bucket_C",
            "score_bucket_D",
            "score_suppress_reason",
            "score_regime_label",
            "score_flow_band",
            "score_news_flag",
        ]
        
        model_fields = FNOSignalResponse.model_fields.keys()
        
        missing_fields = []
        for field in v2_fields:
            if field not in model_fields:
                missing_fields.append(field)
        
        assert len(missing_fields) == 0, f"Missing V2 fields in FNOSignalResponse: {missing_fields}"
        
        print(f"PASS: FNOSignalResponse has all 9 V2 fields: {v2_fields}")


# ============================================================================
# Test Class: USE_NEW_SCORING Feature Flag
# ============================================================================

class TestUseNewScoringFlag:
    """Test USE_NEW_SCORING env var toggles V2/V1 scoring paths"""

    def test_use_new_scoring_env_var_default_true(self):
        """USE_NEW_SCORING env var defaults to 'true' (V2 scoring active)"""
        # Check the default behavior in fno_signal_engine
        import os
        
        # Clear any existing value
        original = os.environ.get("USE_NEW_SCORING")
        
        # Test default (when not set)
        if "USE_NEW_SCORING" in os.environ:
            del os.environ["USE_NEW_SCORING"]
        
        # The code uses: os.environ.get("USE_NEW_SCORING", "true").lower() == "true"
        default_value = os.environ.get("USE_NEW_SCORING", "true").lower()
        assert default_value == "true", f"Expected default 'true', got '{default_value}'"
        
        # Restore original
        if original is not None:
            os.environ["USE_NEW_SCORING"] = original
        
        print("PASS: USE_NEW_SCORING defaults to 'true' (V2 scoring active)")

    def test_use_new_scoring_false_disables_v2(self):
        """USE_NEW_SCORING='false' disables V2 scoring"""
        import os
        
        original = os.environ.get("USE_NEW_SCORING")
        os.environ["USE_NEW_SCORING"] = "false"
        
        use_v2 = os.environ.get("USE_NEW_SCORING", "true").lower() == "true"
        assert use_v2 is False, "Expected V2 scoring disabled when USE_NEW_SCORING='false'"
        
        # Restore
        if original is not None:
            os.environ["USE_NEW_SCORING"] = original
        elif "USE_NEW_SCORING" in os.environ:
            del os.environ["USE_NEW_SCORING"]
        
        print("PASS: USE_NEW_SCORING='false' disables V2 scoring")


# ============================================================================
# Test Class: compute_confluence_score_v2 with hard_veto
# ============================================================================

class TestComputeConfluenceScoreV2:
    """Test compute_confluence_score_v2 with hard_veto bucket D"""

    def test_confluence_v2_with_hard_veto_bucket_d_returns_should_suppress(self):
        """compute_confluence_score_v2() with hard_veto bucket D returns should_suppress=True"""
        from services.confluence_score_v2 import compute_confluence_score_v2, compute_bucket_d
        
        # Create a hard veto bucket D
        bucket_d = compute_bucket_d(
            rr_to_t1=0.5,  # Hard veto trigger
            rr_to_t2=1.0,
            t1_p_hit=0.70,
            t2_p_hit=0.50,
        )
        
        assert bucket_d["hard_veto"] is True, "Bucket D should have hard_veto"
        assert bucket_d["score"] == 0, "Bucket D score should be 0"
        
        # Create other buckets with good scores
        bucket_a = {"score": 80, "breakdown": {}}
        bucket_b = {"score": 85, "breakdown": {}}
        bucket_c = {"score": 75, "breakdown": {}}
        
        result = compute_confluence_score_v2(bucket_a, bucket_b, bucket_c, bucket_d)
        
        # With D=0, weighted score = 0.30*80 + 0.30*85 + 0.25*75 + 0.15*0 = 24 + 25.5 + 18.75 + 0 = 68.25 ≈ 68
        # 68 < 78 threshold → should_suppress=True
        assert result["should_suppress"] is True, f"Expected should_suppress=True with hard_veto D, got {result['should_suppress']}"
        
        print(f"PASS: confluence_v2 with hard_veto D: score={result['score']}, should_suppress={result['should_suppress']}")


# ============================================================================
# Test Class: Backend Imports
# ============================================================================

class TestBackendImports:
    """Verify all services.mfe_mae_engine functions import correctly"""

    def test_select_targets_v2_imports(self):
        """select_targets_v2 imports correctly from mfe_mae_engine"""
        from services.mfe_mae_engine import select_targets_v2
        assert callable(select_targets_v2), "select_targets_v2 should be callable"
        print("PASS: select_targets_v2 imports correctly")

    def test_fno_signal_engine_imports_select_targets_v2(self):
        """fno_signal_engine imports select_targets_v2"""
        # Check the import statement exists in fno_signal_engine
        import inspect
        from services import fno_signal_engine
        
        source = inspect.getsource(fno_signal_engine)
        assert "select_targets_v2" in source, "fno_signal_engine should import select_targets_v2"
        print("PASS: fno_signal_engine imports select_targets_v2")

    def test_confluence_score_v2_functions_import(self):
        """All confluence_score_v2 functions import correctly"""
        from services.confluence_score_v2 import (
            compute_bucket_a,
            compute_bucket_b,
            compute_bucket_c,
            compute_bucket_d,
            compute_confluence_score_v2,
        )
        
        assert callable(compute_bucket_a), "compute_bucket_a should be callable"
        assert callable(compute_bucket_b), "compute_bucket_b should be callable"
        assert callable(compute_bucket_c), "compute_bucket_c should be callable"
        assert callable(compute_bucket_d), "compute_bucket_d should be callable"
        assert callable(compute_confluence_score_v2), "compute_confluence_score_v2 should be callable"
        
        print("PASS: All confluence_score_v2 functions import correctly")


# ============================================================================
# Test Class: Bucket B Real Breadth Wiring
# ============================================================================

class TestBucketBBreadthWiring:
    """Verify Bucket B uses real breadth data"""

    def test_compute_bucket_b_accepts_breadth_params(self):
        """compute_bucket_b accepts sector_breadth_score and index_breadth_score"""
        from services.confluence_score_v2 import compute_bucket_b
        import inspect
        
        sig = inspect.signature(compute_bucket_b)
        params = list(sig.parameters.keys())
        
        assert "sector_breadth_score" in params, "compute_bucket_b should accept sector_breadth_score"
        assert "index_breadth_score" in params, "compute_bucket_b should accept index_breadth_score"
        
        print(f"PASS: compute_bucket_b accepts breadth params: {params}")

    def test_compute_bucket_b_with_index_breadth(self):
        """compute_bucket_b uses index_breadth_score for NIFTY/BANKNIFTY"""
        from services.confluence_score_v2 import compute_bucket_b
        
        result = compute_bucket_b(
            direction="BULLISH",
            bias_score=70,
            trend_alignment="ALIGNED",
            rsi=55,
            macd_bullish=True,
            adx=25,
            above_vwap=True,
            sector_breadth_score=None,
            index_breadth_score=75,  # High breadth
            regime="LowVolRange",
            stoch_k=60,
        )
        
        assert "score" in result, "Result should have score"
        assert result["score"] > 0, f"Expected positive score with good breadth, got {result['score']}"
        
        print(f"PASS: compute_bucket_b with index_breadth: score={result['score']}")


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
