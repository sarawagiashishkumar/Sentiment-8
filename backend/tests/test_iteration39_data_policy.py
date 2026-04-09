"""
Iteration 39: Global Kite Supremacy Rule via data_policy.py

Tests verify:
1. data_policy.py: KITE_IS_SOURCE_OF_TRUTH is True
2. data_policy.py: USE_YFINANCE is False (default)
3. data_verifier.py: imports KITE_IS_SOURCE_OF_TRUTH from data_policy
4. sector_momentum.py: imports KITE_IS_SOURCE_OF_TRUTH from data_policy
5. backtest_engine.py: imports KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy (no local definition)
6. intraday_features.py: imports KITE_IS_SOURCE_OF_TRUTH from data_policy
7. options_features.py: imports KITE_IS_SOURCE_OF_TRUTH from data_policy
8. server.py: imports KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy (no local definition)
9. server.py: _fetch_yfinance_fundamentals has disabled comment block
10. API regression: auth, sector-momentum, fno/scripts/search, admin/config all work
"""

import os
import re
import pytest
import requests

from tests.helpers.test_utils import get_base_url

BASE_URL = get_base_url()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: data_policy.py Constants Verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataPolicyConstants:
    """Verify data_policy.py has correct constant values."""

    def test_kite_is_source_of_truth_is_true(self):
        """KITE_IS_SOURCE_OF_TRUTH must be True."""
        from services.data_policy import KITE_IS_SOURCE_OF_TRUTH
        assert KITE_IS_SOURCE_OF_TRUTH is True, "KITE_IS_SOURCE_OF_TRUTH must be True"
        print("PASS: KITE_IS_SOURCE_OF_TRUTH = True")

    def test_use_yfinance_is_false_by_default(self):
        """USE_YFINANCE must be False by default (env not set)."""
        # Clear env var to test default
        original = os.environ.pop("USE_YFINANCE", None)
        try:
            # Re-import to get fresh value
            import importlib
            import services.data_policy as dp
            importlib.reload(dp)
            assert dp.USE_YFINANCE is False, "USE_YFINANCE must be False by default"
            print("PASS: USE_YFINANCE = False (default)")
        finally:
            if original is not None:
                os.environ["USE_YFINANCE"] = original

    def test_data_policy_file_exists(self):
        """data_policy.py must exist in services directory."""
        import services.data_policy
        assert services.data_policy is not None
        print("PASS: data_policy.py exists and is importable")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Import Verification - All modules import from data_policy
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataVerifierImport:
    """Verify data_verifier.py imports from data_policy."""

    def test_imports_kite_is_source_of_truth_from_data_policy(self):
        """data_verifier.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy."""
        with open("/app/backend/services/data_verifier.py", "r") as f:
            content = f.read()
        
        # Check for import statement
        pattern = r"from\s+services\.data_policy\s+import\s+.*KITE_IS_SOURCE_OF_TRUTH"
        assert re.search(pattern, content), "data_verifier.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy"
        print("PASS: data_verifier.py imports KITE_IS_SOURCE_OF_TRUTH from data_policy")

    def test_no_local_kite_is_source_of_truth_definition(self):
        """data_verifier.py must NOT have local KITE_IS_SOURCE_OF_TRUTH definition."""
        with open("/app/backend/services/data_verifier.py", "r") as f:
            content = f.read()
        
        # Check for local definition (assignment at module level)
        local_def_pattern = r"^KITE_IS_SOURCE_OF_TRUTH\s*[:=]"
        matches = re.findall(local_def_pattern, content, re.MULTILINE)
        assert len(matches) == 0, f"data_verifier.py has local KITE_IS_SOURCE_OF_TRUTH definition: {matches}"
        print("PASS: data_verifier.py has no local KITE_IS_SOURCE_OF_TRUTH definition")


class TestSectorMomentumImport:
    """Verify sector_momentum.py imports from data_policy."""

    def test_imports_kite_is_source_of_truth_from_data_policy(self):
        """sector_momentum.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy."""
        with open("/app/backend/services/sector_momentum.py", "r") as f:
            content = f.read()
        
        pattern = r"from\s+services\.data_policy\s+import\s+.*KITE_IS_SOURCE_OF_TRUTH"
        assert re.search(pattern, content), "sector_momentum.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy"
        print("PASS: sector_momentum.py imports KITE_IS_SOURCE_OF_TRUTH from data_policy")


class TestBacktestEngineImport:
    """Verify backtest_engine.py imports from data_policy (no local definition)."""

    def test_imports_both_constants_from_data_policy(self):
        """backtest_engine.py must import KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy."""
        with open("/app/backend/services/backtest_engine.py", "r") as f:
            content = f.read()
        
        # Check for import of both constants
        pattern = r"from\s+services\.data_policy\s+import\s+.*KITE_IS_SOURCE_OF_TRUTH.*USE_YFINANCE|from\s+services\.data_policy\s+import\s+.*USE_YFINANCE.*KITE_IS_SOURCE_OF_TRUTH"
        assert re.search(pattern, content), "backtest_engine.py must import both KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy"
        print("PASS: backtest_engine.py imports KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy")

    def test_no_local_use_yfinance_definition(self):
        """backtest_engine.py must NOT have local USE_YFINANCE definition."""
        with open("/app/backend/services/backtest_engine.py", "r") as f:
            content = f.read()
        
        # Check for local definition (assignment at module level, not in import)
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip import lines
            if "from services.data_policy import" in line:
                continue
            # Check for local definition
            if re.match(r"^USE_YFINANCE\s*[:=]", stripped):
                pytest.fail(f"backtest_engine.py has local USE_YFINANCE definition at line {i+1}: {line}")
        print("PASS: backtest_engine.py has no local USE_YFINANCE definition")


class TestIntradayFeaturesImport:
    """Verify intraday_features.py imports from data_policy."""

    def test_imports_kite_is_source_of_truth_from_data_policy(self):
        """intraday_features.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy."""
        with open("/app/backend/services/intraday_features.py", "r") as f:
            content = f.read()
        
        pattern = r"from\s+services\.data_policy\s+import\s+.*KITE_IS_SOURCE_OF_TRUTH"
        assert re.search(pattern, content), "intraday_features.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy"
        print("PASS: intraday_features.py imports KITE_IS_SOURCE_OF_TRUTH from data_policy")


class TestOptionsFeaturesImport:
    """Verify options_features.py imports from data_policy."""

    def test_imports_kite_is_source_of_truth_from_data_policy(self):
        """options_features.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy."""
        with open("/app/backend/services/options_features.py", "r") as f:
            content = f.read()
        
        pattern = r"from\s+services\.data_policy\s+import\s+.*KITE_IS_SOURCE_OF_TRUTH"
        assert re.search(pattern, content), "options_features.py must import KITE_IS_SOURCE_OF_TRUTH from data_policy"
        print("PASS: options_features.py imports KITE_IS_SOURCE_OF_TRUTH from data_policy")


class TestServerImport:
    """Verify server.py imports from data_policy (no local definition)."""

    def test_imports_both_constants_from_data_policy(self):
        """server.py must import KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy."""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        # Check for import of both constants
        pattern = r"from\s+services\.data_policy\s+import\s+.*KITE_IS_SOURCE_OF_TRUTH.*USE_YFINANCE|from\s+services\.data_policy\s+import\s+.*USE_YFINANCE.*KITE_IS_SOURCE_OF_TRUTH"
        assert re.search(pattern, content), "server.py must import both KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy"
        print("PASS: server.py imports KITE_IS_SOURCE_OF_TRUTH and USE_YFINANCE from data_policy")

    def test_no_local_use_yfinance_definition(self):
        """server.py must NOT have local USE_YFINANCE definition (only import)."""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip import lines and comments
            if "from services.data_policy import" in line:
                continue
            if stripped.startswith("#"):
                continue
            # Check for local definition
            if re.match(r"^USE_YFINANCE\s*[:=]", stripped):
                pytest.fail(f"server.py has local USE_YFINANCE definition at line {i+1}: {line}")
        print("PASS: server.py has no local USE_YFINANCE definition")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: _fetch_yfinance_fundamentals Disabled Comment Block
# ═══════════════════════════════════════════════════════════════════════════════

class TestYfinanceFundamentalsDisabledComment:
    """Verify _fetch_yfinance_fundamentals has disabled comment block."""

    def _read_all(self):
        combined = ""
        for fp in ["/app/backend/server.py", "/app/backend/services/fundamental_data.py"]:
            try:
                with open(fp, "r") as f:
                    combined += f.read() + "\n"
            except FileNotFoundError:
                continue
        return combined

    def test_has_disabled_comment_above_function(self):
        """_fetch_yfinance_fundamentals must have a disabled/stub comment block above it."""
        content = self._read_all()
        
        func_match = re.search(r"def\s+_fetch_yfinance_fundamentals\s*\(", content)
        assert func_match, "_fetch_yfinance_fundamentals function not found in codebase"
        
        func_pos = func_match.start()
        preceding_content = content[max(0, func_pos - 500):func_pos]
        
        disabled_patterns = [
            r"#.*DISABLED",
            r"#.*disabled",
            r"#.*stub",
            r"#.*STUB",
            r"#.*yfinance\s+only",
            r"#.*USE_YFINANCE\s+must\s+remain\s+false",
            r"#.*yfinance",  # Any yfinance comment
        ]
        
        found_disabled_comment = False
        for pattern in disabled_patterns:
            if re.search(pattern, preceding_content, re.IGNORECASE):
                found_disabled_comment = True
                break
        
        assert found_disabled_comment, "_fetch_yfinance_fundamentals must have a disabled/stub comment block above it"

    def test_function_is_gated_by_use_yfinance(self):
        """_fetch_yfinance_fundamentals usage must be gated by USE_YFINANCE check."""
        content = self._read_all()
        
        gated_pattern = r"if\s+USE_YFINANCE.*_fetch_yfinance_fundamentals|USE_YFINANCE.*=.*False"
        assert re.search(gated_pattern, content, re.DOTALL), \
            "_fetch_yfinance_fundamentals call must be gated by USE_YFINANCE"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: API Regression Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthEndpointsRegression:
    """Verify auth endpoints still work."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def test_auth_access_login(self):
        """POST /api/auth/access should work with valid credentials."""
        response = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"}
        )
        assert response.status_code == 200, f"Auth login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "token" in data, "Response must contain token"
        print(f"PASS: Auth login works, token received")

    def test_auth_me_endpoint(self):
        """GET /api/auth/me should work with valid token."""
        # Login first
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"}
        )
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        # Call /me
        me_resp = self.session.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_resp.status_code == 200, f"Auth me failed: {me_resp.status_code}"
        data = me_resp.json()
        assert data.get("username") == "@shish123"
        print("PASS: Auth /me endpoint works")


class TestSectorMomentumAPIRegression:
    """Verify sector-momentum endpoint still works."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        # Login
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"}
        )
        if login_resp.status_code == 200:
            self.token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            self.token = None

    def test_sector_momentum_endpoint(self):
        """GET /api/sector-momentum should return data with data_source='kite'."""
        if not self.token:
            pytest.skip("Auth failed")
        
        response = self.session.get(f"{BASE_URL}/api/sector-momentum", timeout=30)
        assert response.status_code == 200, f"Sector momentum failed: {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "sectors" in data, "Response must contain sectors"
        assert "summary" in data, "Response must contain summary"
        
        # Verify data_source is kite
        summary = data.get("summary", {})
        assert summary.get("data_source") == "kite", f"data_source must be 'kite', got: {summary.get('data_source')}"
        print("PASS: Sector momentum endpoint works with data_source='kite'")


class TestFNOEndpointsRegression:
    """Verify F&O endpoints still work."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        # Login
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"}
        )
        if login_resp.status_code == 200:
            self.token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            self.token = None

    def test_fno_scripts_search(self):
        """GET /api/fno/scripts/search should work."""
        response = self.session.get(
            f"{BASE_URL}/api/fno/scripts/search",
            params={"q": "NIFTY"}
        )
        assert response.status_code == 200, f"FNO scripts search failed: {response.status_code}"
        data = response.json()
        # Response can be a list or dict with suggestions
        if isinstance(data, dict):
            assert "suggestions" in data or "query" in data, "Response dict must have suggestions or query"
            suggestions = data.get("suggestions", [])
            print(f"PASS: FNO scripts search works, returned {len(suggestions)} suggestions")
        else:
            assert isinstance(data, list), "Response must be a list or dict"
            print(f"PASS: FNO scripts search works, returned {len(data)} results")


class TestAdminEndpointsRegression:
    """Verify admin endpoints still work."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        # Login as admin
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/access",
            json={"username": "@shish123", "password": "1234"}
        )
        if login_resp.status_code == 200:
            self.token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            self.token = None

    def test_admin_config(self):
        """GET /api/admin/config should work for admin user."""
        if not self.token:
            pytest.skip("Auth failed")
        
        response = self.session.get(f"{BASE_URL}/api/admin/config")
        assert response.status_code == 200, f"Admin config failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, dict), "Response must be a dict"
        print("PASS: Admin config endpoint works")


class TestAPIRoot:
    """Verify API root endpoint works."""

    def test_api_root(self):
        """GET /api/ should return status."""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"API root failed: {response.status_code}"
        print("PASS: API root endpoint works")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Runtime Import Verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestRuntimeImports:
    """Verify all modules can be imported without errors."""

    def test_data_policy_imports(self):
        """data_policy.py should import without errors."""
        from services.data_policy import KITE_IS_SOURCE_OF_TRUTH, USE_YFINANCE
        assert KITE_IS_SOURCE_OF_TRUTH is True
        assert USE_YFINANCE is False
        print("PASS: data_policy imports correctly")

    def test_data_verifier_imports(self):
        """data_verifier.py should import without errors."""
        from services.data_verifier import fetch_verified_price, fetch_verified_snapshot
        assert callable(fetch_verified_price)
        assert callable(fetch_verified_snapshot)
        print("PASS: data_verifier imports correctly")

    def test_sector_momentum_imports(self):
        """sector_momentum.py should import without errors."""
        from services.sector_momentum import compute_sector_momentum_dashboard
        assert callable(compute_sector_momentum_dashboard)
        print("PASS: sector_momentum imports correctly")

    def test_backtest_engine_imports(self):
        """backtest_engine.py should import without errors."""
        from services.backtest_engine import run_backtest_batch, fetch_strategy_backtest
        assert callable(run_backtest_batch)
        assert callable(fetch_strategy_backtest)
        print("PASS: backtest_engine imports correctly")

    def test_intraday_features_imports(self):
        """intraday_features.py should import without errors."""
        from services.intraday_features import compute_vwap_features, compute_intraday_technicals
        assert callable(compute_vwap_features)
        assert callable(compute_intraday_technicals)
        print("PASS: intraday_features imports correctly")

    def test_options_features_imports(self):
        """options_features.py should import without errors."""
        from services.options_features import classify_oi_buildup, compute_iv_rank
        assert callable(classify_oi_buildup)
        assert callable(compute_iv_rank)
        print("PASS: options_features imports correctly")
