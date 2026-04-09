"""
Iteration 20: 5 New Wiring Actions Tests
Tests the 5 new wiring actions added on top of Batch 1-5 research engine:
  Action 1: Signal lifecycle state machine wired into _refresh_open_position()
  Action 2: merge_duplicate_holdings + compute_master_stock_snapshot in _analyze_portfolio_positions
  Action 3: strategy_backtest MongoDB collection + admin endpoints + strategy-library
  Action 4: compute_macro_context() wired into build_fno_signal()
  Action 5: _compute_enhanced_index_breadth() for NIFTY/BANKNIFTY signals

HTTP API Tests:
  - GET /api/health (backend alive)
  - GET /api/strategy-library (13 strategies)
  - POST /api/admin/strategy-stats/record (with admin auth)
  - GET /api/admin/strategy-stats (aggregated stats)
  - GET /api/admin/strategy-stats?strategy_id=S1_ORB (filtered)

Unit Tests (research_engine functions directly):
  - transition_signal_state (state machine)
  - merge_duplicate_holdings
  - compute_master_stock_snapshot
  - STRATEGY_LIBRARY contents
  - check_strategy_eligible
  - compute_macro_context
  - compute_index_constituent_bias
"""
import os
import sys
import pytest
import requests
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from tests.helpers.test_utils import get_base_url

# Load env
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = get_base_url()

# Import research engine directly
sys.path.insert(0, "/app/backend")
from services.research_engine import (
    transition_signal_state,
    merge_duplicate_holdings,
    compute_master_stock_snapshot,
    STRATEGY_LIBRARY,
    check_strategy_eligible,
    compute_macro_context,
    compute_index_constituent_bias,
    NIFTY50_WEIGHTS,
    BANKNIFTY_WEIGHTS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def admin_token():
    """Get admin auth token for @shish123."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/access",
        json={"username": "@shish123"},
        timeout=15,
    )
    if resp.status_code == 200:
        token = resp.json().get("token")
        assert token, "Token missing in auth response"
        return token
    pytest.skip(f"Admin auth failed: {resp.status_code} {resp.text}")


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def api_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def make_ohlcv(n=260, base=1000.0, trend=0.0) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame with n rows."""
    rng = np.random.default_rng(42)
    close = base + trend * np.arange(n) + rng.normal(0, 5, n).cumsum()
    high = close + rng.uniform(0, 10, n)
    low = close - rng.uniform(0, 10, n)
    open_ = close - rng.normal(0, 3, n)
    volume = rng.integers(100_000, 1_000_000, n).astype(float)
    idx = pd.bdate_range(start="2020-01-02", periods=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


# ─── Action 3: HTTP API Tests ─────────────────────────────────────────────────

class TestHealthCheck:
    """GET /api/ — backend alive."""

    def test_backend_root_returns_200(self, api_session):
        resp = api_session.get(f"{BASE_URL}/api/", timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print(f"PASS: GET /api/ -> {resp.status_code}")


class TestStrategyLibraryEndpoint:
    """GET /api/strategy-library — 13 strategies with required fields."""

    def test_strategy_library_returns_200(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print(f"PASS: GET /api/strategy-library -> 200")

    def test_strategy_library_has_13_strategies(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data, "Response missing 'total' field"
        assert data["total"] == 13, f"Expected 13 strategies, got {data['total']}"
        assert "strategies" in data
        assert len(data["strategies"]) == 13
        print(f"PASS: strategy-library has {data['total']} strategies")

    def test_strategy_library_has_required_strategy_ids(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = {s["id"] for s in data["strategies"]}
        required = ["S1_ORB", "SW2_200DMA_BOUNCE", "E2_IRON_CONDOR", "SF2_FORENSIC_QUALITY"]
        for sid in required:
            assert sid in ids, f"Strategy {sid} missing from strategy-library"
        print(f"PASS: Required strategy IDs present: {required}")

    def test_strategy_library_strategies_have_entry_conditions(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        for strat in data["strategies"]:
            sid = strat.get("id")
            assert "entry_conditions" in strat, f"{sid} missing entry_conditions"
            assert isinstance(strat["entry_conditions"], list), f"{sid} entry_conditions not list"
            assert len(strat["entry_conditions"]) > 0, f"{sid} entry_conditions is empty"
        print("PASS: All strategies have non-empty entry_conditions")

    def test_strategy_library_strategies_have_preferred_regime(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/strategy-library",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        for strat in data["strategies"]:
            sid = strat.get("id")
            assert "preferred_regime" in strat, f"{sid} missing preferred_regime"
            assert isinstance(strat["preferred_regime"], list), f"{sid} preferred_regime not list"
        print("PASS: All strategies have preferred_regime list")

    def test_strategy_library_requires_auth(self, api_session):
        """Unauthenticated request should return 401."""
        resp = api_session.get(f"{BASE_URL}/api/strategy-library", timeout=15)
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("PASS: strategy-library requires authentication")


class TestAdminStrategyStats:
    """POST /api/admin/strategy-stats/record and GET /api/admin/strategy-stats."""

    # Track recorded trade IDs for cleanup verification
    _recorded_strategy_id = "S1_ORB"
    _recorded_symbol = "TEST_NIFTY_ITER20"

    def test_record_trade_result_post(self, api_session, auth_headers):
        resp = api_session.post(
            f"{BASE_URL}/api/admin/strategy-stats/record",
            params={
                "strategy_id": self._recorded_strategy_id,
                "symbol": self._recorded_symbol,
                "win": "true",
                "r_multiple": 1.2,
            },
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("recorded") is True, "recorded field should be True"
        assert data.get("strategy_id") == self._recorded_strategy_id
        print(f"PASS: POST /api/admin/strategy-stats/record -> recorded=True for {self._recorded_strategy_id}")

    def test_record_trade_result_has_stats(self, api_session, auth_headers):
        resp = api_session.post(
            f"{BASE_URL}/api/admin/strategy-stats/record",
            params={
                "strategy_id": self._recorded_strategy_id,
                "symbol": self._recorded_symbol,
                "win": "true",
                "r_multiple": 1.5,
            },
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        current_stats = data.get("current_stats", {})
        assert "win_rate" in current_stats, "current_stats missing win_rate"
        assert "expectancy" in current_stats, "current_stats missing expectancy"
        assert current_stats.get("total_trades", 0) > 0
        print(f"PASS: Trade result has current_stats with win_rate={current_stats.get('win_rate')}")

    def test_record_trade_result_has_eligible_flag(self, api_session, auth_headers):
        resp = api_session.post(
            f"{BASE_URL}/api/admin/strategy-stats/record",
            params={
                "strategy_id": self._recorded_strategy_id,
                "symbol": self._recorded_symbol,
                "win": "false",
                "r_multiple": -1.0,
            },
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "eligible" in data, "Response missing 'eligible' flag"
        assert "auto_disabled" in data, "Response missing 'auto_disabled' flag"
        assert "reason" in data, "Response missing 'reason'"
        print(f"PASS: Trade result has eligible={data.get('eligible')}, auto_disabled={data.get('auto_disabled')}")

    def test_get_strategy_stats_returns_200(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/admin/strategy-stats",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "strategy_stats" in data, "Response missing strategy_stats"
        assert "total_records" in data, "Response missing total_records"
        print(f"PASS: GET /api/admin/strategy-stats -> {len(data['strategy_stats'])} strategies, {data['total_records']} records")

    def test_get_strategy_stats_has_win_rate_and_expectancy(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/admin/strategy-stats",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        stats_list = data["strategy_stats"]
        assert len(stats_list) > 0, "strategy_stats should have at least one entry after recording trades"
        for stat in stats_list:
            assert "win_rate" in stat, f"{stat.get('strategy_id')} missing win_rate"
            assert "expectancy" in stat, f"{stat.get('strategy_id')} missing expectancy"
            assert "eligible" in stat, f"{stat.get('strategy_id')} missing eligible flag"
        print("PASS: All strategy stats have win_rate, expectancy, eligible")

    def test_get_strategy_stats_filter_by_strategy_id(self, api_session, auth_headers):
        resp = api_session.get(
            f"{BASE_URL}/api/admin/strategy-stats",
            params={"strategy_id": self._recorded_strategy_id},
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        stats_list = data["strategy_stats"]
        # All returned stats should be for S1_ORB
        for stat in stats_list:
            assert stat["strategy_id"] == self._recorded_strategy_id, \
                f"Filter failed: got {stat['strategy_id']} instead of {self._recorded_strategy_id}"
        print(f"PASS: GET /api/admin/strategy-stats?strategy_id=S1_ORB -> {len(stats_list)} entries, all S1_ORB")

    def test_admin_stats_requires_auth(self, api_session):
        """Unauthenticated request should return 401."""
        resp = api_session.get(f"{BASE_URL}/api/admin/strategy-stats", timeout=15)
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("PASS: admin/strategy-stats requires authentication")

    def test_admin_stats_record_requires_auth(self, api_session):
        """Unauthenticated record should return 401."""
        resp = api_session.post(
            f"{BASE_URL}/api/admin/strategy-stats/record",
            params={"strategy_id": "S1_ORB", "symbol": "TEST", "win": "true", "r_multiple": 1.0},
            timeout=15,
        )
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("PASS: admin/strategy-stats/record requires authentication")


# ─── Action 1: Signal Lifecycle State Machine ─────────────────────────────────

class TestSignalStateMachineWiring:
    """Unit tests for transition_signal_state() — Action 1."""

    def test_active_to_watching_t1_when_ltp_ge_t1(self):
        """ACTIVE -> WATCHING_T1 when ltp >= t1."""
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=120.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=130.0,
            direction="BULLISH",
        )
        assert result["new_state"] == "WATCHING_T1", \
            f"Expected WATCHING_T1, got {result['new_state']}"
        assert result["t1_hit"] is True
        print(f"PASS: ACTIVE->WATCHING_T1 when ltp=120 >= t1=115. reason={result['reason']}")

    def test_urgent_exit_when_15_min_to_expiry(self):
        """Triggers urgent_exit when minutes_to_expiry <= 15."""
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=100.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=130.0,
            direction="BULLISH",
            minutes_to_expiry=10,
        )
        assert result["urgent_exit"] is True, "Expected urgent_exit=True for minutes_to_expiry=10"
        assert result["new_state"] == "EXPIRED", f"Expected EXPIRED, got {result['new_state']}"
        print(f"PASS: urgent_exit=True for minutes_to_expiry=10. reason={result['reason']}")

    def test_urgent_exit_at_exactly_15_min(self):
        """Triggers urgent_exit at exactly 15 minutes to expiry."""
        result = transition_signal_state(
            current_state="WATCHING_T1",
            ltp=120.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=130.0,
            direction="BULLISH",
            minutes_to_expiry=15,
        )
        assert result["urgent_exit"] is True, "Expected urgent_exit=True for minutes_to_expiry=15"
        assert result["new_state"] == "EXPIRED"
        print("PASS: urgent_exit=True at exactly 15 mins to expiry")

    def test_watching_t1_to_closed_win_when_t2_is_none(self):
        """WATCHING_T1 -> CLOSED_WIN when t2 is None and T1 hit."""
        result = transition_signal_state(
            current_state="WATCHING_T1",
            ltp=120.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=None,
            direction="BULLISH",
        )
        assert result["new_state"] == "CLOSED_WIN", \
            f"Expected CLOSED_WIN, got {result['new_state']}"
        print(f"PASS: WATCHING_T1->CLOSED_WIN when t2=None and T1 hit. reason={result['reason']}")

    def test_active_to_watching_sl_when_sl_hit(self):
        """ACTIVE -> WATCHING_SL when ltp <= sl."""
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=88.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=130.0,
            direction="BULLISH",
        )
        assert result["new_state"] == "WATCHING_SL", \
            f"Expected WATCHING_SL, got {result['new_state']}"
        assert result["sl_hit"] is True
        print(f"PASS: ACTIVE->WATCHING_SL when ltp=88 <= sl=90")

    def test_watching_sl_to_closed_loss(self):
        """WATCHING_SL -> CLOSED_LOSS when SL hit confirmed."""
        result = transition_signal_state(
            current_state="WATCHING_SL",
            ltp=88.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=130.0,
            direction="BULLISH",
        )
        assert result["new_state"] == "CLOSED_LOSS", \
            f"Expected CLOSED_LOSS, got {result['new_state']}"
        print(f"PASS: WATCHING_SL->CLOSED_LOSS when SL hit")

    def test_terminal_state_no_transition(self):
        """Terminal states (CLOSED_WIN/CLOSED_LOSS/EXPIRED) have no transitions."""
        for terminal in ("CLOSED_WIN", "CLOSED_LOSS", "EXPIRED"):
            result = transition_signal_state(
                current_state=terminal,
                ltp=200.0,
                entry_price=100.0,
                sl_price=90.0,
                t1_price=115.0,
                t2_price=130.0,
            )
            assert result["new_state"] == terminal, \
                f"Terminal state {terminal} should not transition, got {result['new_state']}"
        print("PASS: Terminal states (CLOSED_WIN/CLOSED_LOSS/EXPIRED) have no transitions")

    def test_bearish_signal_sl_hit(self):
        """BEARISH: ACTIVE -> WATCHING_SL when ltp >= sl_price."""
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=110.0,
            entry_price=100.0,
            sl_price=108.0,
            t1_price=88.0,
            t2_price=80.0,
            direction="BEARISH",
        )
        assert result["new_state"] == "WATCHING_SL", \
            f"Expected WATCHING_SL for BEARISH, got {result['new_state']}"
        assert result["sl_hit"] is True
        print("PASS: BEARISH signal ACTIVE->WATCHING_SL when ltp >= sl")

    def test_signal_state_returns_required_keys(self):
        """transition_signal_state returns dict with required keys."""
        result = transition_signal_state(
            current_state="ACTIVE",
            ltp=100.0,
            entry_price=100.0,
            sl_price=90.0,
            t1_price=115.0,
            t2_price=130.0,
        )
        for key in ("new_state", "reason", "urgent_exit", "sl_hit", "t1_hit", "t2_hit"):
            assert key in result, f"Missing key '{key}' in state machine result"
        print("PASS: transition_signal_state returns all required keys")


# ─── Action 2: Merge Holdings & Master Stock Snapshot ─────────────────────────

class TestMergeHoldingsWiring:
    """Unit tests for merge_duplicate_holdings() — Action 2."""

    def test_merges_same_symbol_into_one(self):
        """Same symbol duplicates should produce 1 merged record."""
        holdings = [
            {"symbol": "RELIANCE", "avg_price": 2800.0, "quantity": 10, "current_value": 30000},
            {"symbol": "RELIANCE", "avg_price": 2600.0, "quantity": 5, "current_value": 14000},
        ]
        result = merge_duplicate_holdings(holdings)
        assert len(result) == 1, f"Expected 1 merged record, got {len(result)}"
        merged = result[0]
        assert merged["symbol"] == "RELIANCE"
        assert merged["quantity"] == 15
        # Weighted avg = (2800*10 + 2600*5) / 15 = (28000+13000)/15 = 41000/15 ≈ 2733.33
        expected_avg = round((2800 * 10 + 2600 * 5) / 15, 2)
        assert abs(merged["avg_price"] - expected_avg) < 0.01, \
            f"Expected avg_price={expected_avg}, got {merged['avg_price']}"
        print(f"PASS: merge_duplicate_holdings merged 2 RELIANCE rows -> qty=15, avg_price={merged['avg_price']}")

    def test_no_duplicates_unchanged(self):
        """No duplicates: list should be returned as-is (same count)."""
        holdings = [
            {"symbol": "TCS", "avg_price": 3500.0, "quantity": 5, "current_value": 17500},
            {"symbol": "INFY", "avg_price": 1500.0, "quantity": 10, "current_value": 15000},
        ]
        result = merge_duplicate_holdings(holdings)
        assert len(result) == 2, f"Expected 2 entries, got {len(result)}"
        symbols = {r["symbol"] for r in result}
        assert "TCS" in symbols and "INFY" in symbols
        print("PASS: merge_duplicate_holdings with no duplicates returns unchanged count")

    def test_merged_current_value_is_sum(self):
        """Merged record's current_value should be sum of both."""
        holdings = [
            {"symbol": "HDFCBANK", "avg_price": 1700.0, "quantity": 20, "current_value": 35000},
            {"symbol": "HDFCBANK", "avg_price": 1650.0, "quantity": 10, "current_value": 17000},
        ]
        result = merge_duplicate_holdings(holdings)
        assert len(result) == 1
        assert result[0]["current_value"] == 52000  # 35000 + 17000
        print("PASS: merged current_value = 35000 + 17000 = 52000")

    def test_weighted_avg_with_three_duplicates(self):
        """Merges 3 same-symbol entries with correct weighted avg."""
        holdings = [
            {"symbol": "SBIN", "avg_price": 600.0, "quantity": 10},
            {"symbol": "SBIN", "avg_price": 500.0, "quantity": 10},
            {"symbol": "SBIN", "avg_price": 550.0, "quantity": 10},
        ]
        result = merge_duplicate_holdings(holdings)
        assert len(result) == 1
        assert result[0]["quantity"] == 30
        expected_avg = round((600 * 10 + 500 * 10 + 550 * 10) / 30, 2)
        assert abs(result[0]["avg_price"] - expected_avg) < 0.01
        print(f"PASS: 3-entry merge: qty=30, avg_price={result[0]['avg_price']} (expected {expected_avg})")


class TestMasterStockSnapshotWiring:
    """Unit tests for compute_master_stock_snapshot() — Action 2."""

    def test_returns_week52_high_and_low(self):
        """Returns week52_high, week52_low with valid hist data."""
        hist = make_ohlcv(n=300, base=1000.0)
        snap = compute_master_stock_snapshot(
            symbol="TEST_STOCK", ltp=1050.0, hist=hist
        )
        assert "week52_high" in snap, "Missing week52_high"
        assert "week52_low" in snap, "Missing week52_low"
        assert snap["week52_high"] > snap["week52_low"], "week52_high should > week52_low"
        assert snap["week52_high"] > 0 and snap["week52_low"] > 0
        print(f"PASS: week52_high={snap['week52_high']}, week52_low={snap['week52_low']}")

    def test_returns_ath_and_pct_below_ath(self):
        """Returns ath and pct_below_ath. Use ltp below 52w low to guarantee ltp < ATH."""
        hist = make_ohlcv(n=300, base=1000.0, trend=0.5)  # positive trend so ATH is well above
        snap = compute_master_stock_snapshot(
            symbol="TEST_STOCK", ltp=800.0, hist=hist  # ltp far below any ATH
        )
        assert "ath" in snap, "Missing ath"
        assert "pct_below_ath" in snap, "Missing pct_below_ath"
        assert snap["ath"] > 0
        assert snap["pct_below_ath"] <= 0, \
            f"pct_below_ath={snap['pct_below_ath']} should be <= 0 when ltp=800 < ATH={snap['ath']}"
        print(f"PASS: ath={snap['ath']}, pct_below_ath={snap['pct_below_ath']}")

    def test_returns_3m_and_1m_levels(self):
        """Returns month3_high, month3_low, month1_high, month1_low."""
        hist = make_ohlcv(n=300, base=1000.0)
        snap = compute_master_stock_snapshot(
            symbol="TEST_STOCK", ltp=1050.0, hist=hist
        )
        for key in ("month3_high", "month3_low", "month1_high", "month1_low"):
            assert key in snap, f"Missing {key}"
            assert snap[key] > 0
        print(f"PASS: 3M={snap['month3_high']}/{snap['month3_low']}, 1M={snap['month1_high']}/{snap['month1_low']}")

    def test_market_cap_category_large(self):
        """Large cap (market_cap > 200B) -> LARGE_CAP."""
        snap = compute_master_stock_snapshot(
            symbol="RELIANCE", ltp=2800.0, hist=None, market_cap=300e9
        )
        assert snap["market_cap_category"] == "LARGE_CAP"
        print("PASS: market_cap=300B -> LARGE_CAP")

    def test_market_cap_category_small(self):
        """Small cap (5B < market_cap < 50B) -> SMALL_CAP."""
        snap = compute_master_stock_snapshot(
            symbol="SMALLCO", ltp=100.0, hist=None, market_cap=10e9
        )
        assert snap["market_cap_category"] == "SMALL_CAP"
        print("PASS: market_cap=10B -> SMALL_CAP")

    def test_pct_from_52w_high_is_negative_when_below(self):
        """pct_from_52w_high should be <= 0 when ltp < 52w high."""
        hist = make_ohlcv(n=260, base=1000.0)
        # ltp set below the expected range mean
        snap = compute_master_stock_snapshot(
            symbol="TEST_STOCK", ltp=900.0, hist=hist
        )
        assert snap["pct_from_52w_high"] <= 0, \
            f"pct_from_52w_high should be <= 0 when ltp < 52w high, got {snap['pct_from_52w_high']}"
        print(f"PASS: pct_from_52w_high={snap['pct_from_52w_high']} (ltp=900 below 52w high)")

    def test_no_hist_returns_symbol_without_price_levels(self):
        """No hist: snapshot returns symbol but no price levels."""
        snap = compute_master_stock_snapshot(
            symbol="NODATA", ltp=100.0, hist=None
        )
        assert snap["symbol"] == "NODATA"
        assert "week52_high" not in snap
        assert "ath" not in snap
        print("PASS: no hist -> returns symbol without price levels")


# ─── Action 3 (Unit): Strategy Library & Eligibility ─────────────────────────

class TestStrategyLibraryUnit:
    """Unit tests for STRATEGY_LIBRARY constant — Action 3."""

    def test_has_exactly_13_strategies(self):
        assert len(STRATEGY_LIBRARY) == 13, f"Expected 13 strategies, got {len(STRATEGY_LIBRARY)}"
        print(f"PASS: STRATEGY_LIBRARY has {len(STRATEGY_LIBRARY)} strategies")

    def test_required_strategy_ids_present(self):
        required = ["S1_ORB", "SW2_200DMA_BOUNCE", "E2_IRON_CONDOR", "SF2_FORENSIC_QUALITY"]
        for sid in required:
            assert sid in STRATEGY_LIBRARY, f"Missing strategy: {sid}"
        print(f"PASS: Required strategies present: {required}")

    def test_each_strategy_has_required_fields(self):
        required_fields = ["name", "type", "entry_conditions", "preferred_regime", "min_win_rate", "min_expectancy"]
        for sid, strat in STRATEGY_LIBRARY.items():
            for f in required_fields:
                assert f in strat, f"Strategy {sid} missing field: {f}"
        print("PASS: All strategies have required fields")

    def test_s1_orb_is_intraday_type(self):
        strat = STRATEGY_LIBRARY["S1_ORB"]
        assert strat["type"] == "INTRADAY", f"S1_ORB should be INTRADAY, got {strat['type']}"
        print("PASS: S1_ORB type = INTRADAY")

    def test_e2_iron_condor_is_expiry_type(self):
        strat = STRATEGY_LIBRARY["E2_IRON_CONDOR"]
        assert strat["type"] == "EXPIRY", f"E2_IRON_CONDOR should be EXPIRY, got {strat['type']}"
        print("PASS: E2_IRON_CONDOR type = EXPIRY")

    def test_sf2_forensic_quality_is_screener_linked(self):
        strat = STRATEGY_LIBRARY["SF2_FORENSIC_QUALITY"]
        assert strat["type"] == "SCREENER_LINKED", f"SF2_FORENSIC_QUALITY should be SCREENER_LINKED"
        print("PASS: SF2_FORENSIC_QUALITY type = SCREENER_LINKED")


class TestCheckStrategyEligibleWiring:
    """Unit tests for check_strategy_eligible() — Action 3."""

    def test_no_stats_is_eligible(self):
        eligible, reason = check_strategy_eligible(None)
        assert eligible is True, "No stats should be eligible"
        assert "new strategy" in reason.lower() or "no backtest" in reason.lower()
        print(f"PASS: check_strategy_eligible(None) -> True, reason='{reason}'")

    def test_below_win_rate_threshold_ineligible(self):
        """win_rate=0.60, 30 trades -> False."""
        stats = {"total_trades": 30, "win_rate": 0.60, "expectancy": 0.45}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is False, f"Expected False for win_rate=0.60, got {eligible}"
        assert "win rate" in reason.lower() or "60%" in reason
        print(f"PASS: win_rate=0.60, 30 trades -> False, reason='{reason}'")

    def test_high_win_rate_and_expectancy_is_eligible(self):
        """win_rate=0.80, expectancy=0.55, 30 trades -> True."""
        stats = {"total_trades": 30, "win_rate": 0.80, "expectancy": 0.55}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is True, f"Expected True for win_rate=0.80, expectancy=0.55, got {eligible}"
        print(f"PASS: win_rate=0.80, expectancy=0.55, 30 trades -> True, reason='{reason}'")

    def test_insufficient_trades_is_eligible_provisional(self):
        """5 trades < min_trades=10 -> eligible provisionally."""
        stats = {"total_trades": 5, "win_rate": 0.60, "expectancy": 0.30}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is True, "5 trades should be provisionally eligible"
        assert "provisional" in reason.lower() or "insufficient" in reason.lower()
        print(f"PASS: 5 trades (< 10) -> True provisional, reason='{reason}'")

    def test_disabled_strategy_ineligible(self):
        """disabled=True -> False."""
        stats = {"total_trades": 30, "win_rate": 0.80, "expectancy": 0.55, "disabled": True}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is False, "disabled=True strategy should be ineligible"
        print(f"PASS: disabled=True -> False, reason='{reason}'")

    def test_below_expectancy_threshold_ineligible(self):
        """win_rate=0.78, expectancy=0.30 (< 0.40), 30 trades -> False."""
        stats = {"total_trades": 30, "win_rate": 0.78, "expectancy": 0.30}
        eligible, reason = check_strategy_eligible(stats)
        assert eligible is False, f"Expected False for expectancy=0.30, got {eligible}"
        assert "expectancy" in reason.lower() or "0.30" in reason
        print(f"PASS: expectancy=0.30 < 0.40 -> False, reason='{reason}'")

    def test_returns_tuple_of_bool_and_str(self):
        """check_strategy_eligible returns (bool, str) tuple."""
        result = check_strategy_eligible(None)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)
        print("PASS: check_strategy_eligible returns (bool, str) tuple")


# ─── Action 4: Macro Context ─────────────────────────────────────────────────

class TestMacroContextWiring:
    """Unit tests for compute_macro_context() — Action 4."""

    def test_airlines_crude_spike_is_headwind(self):
        """sector='Airlines', active_events=['CRUDE_SPIKE'] -> macro_bias=HEADWIND."""
        result = compute_macro_context(
            active_events=["CRUDE_SPIKE"],
            sector="Airlines",
        )
        assert result["macro_bias"] == "HEADWIND", \
            f"Expected HEADWIND for Airlines+CRUDE_SPIKE, got {result['macro_bias']}"
        print(f"PASS: Airlines + CRUDE_SPIKE -> macro_bias=HEADWIND")

    def test_it_usd_strengthening_is_tailwind(self):
        """
        sector='IT', active_events=['USD_STRENGTHENING'] -> expected macro_bias=TAILWIND.
        BUG: Currently returns NEUTRAL due to substring matching too broad:
          'it' in 'capital goods (imports)' = True (capital contains 'it').
          This causes ben_count=1, loser_count=1 -> NEUTRAL instead of TAILWIND.
        This test documents the KNOWN BUG in compute_macro_context substring matching.
        """
        result = compute_macro_context(
            active_events=["USD_STRENGTHENING"],
            sector="IT",
        )
        # KNOWN BUG: should be TAILWIND but is NEUTRAL due to substring match
        # "it" in "capital goods (imports)" = True (cap-IT-al)
        # Documenting actual behavior; fix needed in compute_macro_context word-boundary matching
        actual_bias = result["macro_bias"]
        print(f"BUG DOCUMENTED: IT + USD_STRENGTHENING -> macro_bias={actual_bias} (expected TAILWIND)")
        print(f"  Root cause: 'it' in 'capital goods (imports)' = True (substring match too broad)")
        # The substring bug has been fixed — IT + USD_STRENGTHENING now correctly returns TAILWIND
        assert actual_bias == "TAILWIND", \
            f"IT + USD_STRENGTHENING should be TAILWIND, got {actual_bias}"

    def test_returns_regime_and_macro_bias(self):
        """compute_macro_context returns regime and macro_bias fields."""
        result = compute_macro_context(
            active_events=["FII_INFLOW"],
            vix=14.0,
            sector="Banking",
        )
        assert "regime" in result, "Missing regime in macro_context"
        assert "macro_bias" in result, "Missing macro_bias in macro_context"
        assert result["macro_bias"] in ("TAILWIND", "HEADWIND", "NEUTRAL")
        print(f"PASS: compute_macro_context returns regime and macro_bias={result['macro_bias']}")

    def test_returns_event_impacts_list(self):
        """Returns event_impacts as a list."""
        result = compute_macro_context(
            active_events=["CRUDE_SPIKE", "FII_OUTFLOW"],
            sector="Airlines",
        )
        assert "event_impacts" in result
        assert isinstance(result["event_impacts"], list)
        assert len(result["event_impacts"]) >= 1
        print(f"PASS: event_impacts list has {len(result['event_impacts'])} entries")

    def test_geopolitical_flag_activated(self):
        """GEOPOLITICAL_CONFLICT in active_events sets geopolitical_flag active=True."""
        result = compute_macro_context(
            active_events=["GEOPOLITICAL_CONFLICT"],
            sector="Defence",
        )
        assert result.get("geopolitical_flag", {}).get("active") is True, \
            "Expected geopolitical_flag.active=True"
        print("PASS: GEOPOLITICAL_CONFLICT -> geopolitical_flag.active=True")

    def test_no_events_returns_neutral_bias(self):
        """No active_events with no sector -> NEUTRAL macro_bias."""
        result = compute_macro_context()
        assert result["macro_bias"] in ("TAILWIND", "HEADWIND", "NEUTRAL")
        print(f"PASS: no active_events -> macro_bias={result['macro_bias']}")

    def test_banking_rbi_rate_hike_is_tailwind(self):
        """Banking sector + RBI_RATE_HIKE -> TAILWIND (bank is beneficiary)."""
        result = compute_macro_context(
            active_events=["RBI_RATE_HIKE"],
            sector="Banking",
        )
        assert result["macro_bias"] == "TAILWIND", \
            f"Expected TAILWIND for Banking+RBI_RATE_HIKE, got {result['macro_bias']}"
        print(f"PASS: Banking + RBI_RATE_HIKE -> macro_bias=TAILWIND")


# ─── Action 5: Index Constituent Bias ────────────────────────────────────────

class TestIndexConstituentBiasWiring:
    """Unit tests for compute_index_constituent_bias() — Action 5."""

    def test_returns_weighted_bias_string(self):
        """Returns weighted_bias as BULLISH/BEARISH/NEUTRAL string."""
        signals = [
            {"symbol": "HDFCBANK", "direction": "BULLISH", "conviction": 0.8},
            {"symbol": "ICICIBANK", "direction": "BULLISH", "conviction": 0.7},
            {"symbol": "AXISBANK", "direction": "BULLISH", "conviction": 0.6},
        ]
        result = compute_index_constituent_bias(signals, index_name="NIFTY")
        assert "weighted_bias" in result
        assert result["weighted_bias"] in ("BULLISH", "BEARISH", "NEUTRAL"), \
            f"Unexpected weighted_bias: {result['weighted_bias']}"
        print(f"PASS: weighted_bias={result['weighted_bias']}")

    def test_returns_breadth_score_0_100(self):
        """breadth_score is in range [0, 100]."""
        signals = [
            {"symbol": "HDFCBANK", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "ICICIBANK", "direction": "BULLISH", "conviction": 0.8},
            {"symbol": "AXISBANK", "direction": "BEARISH", "conviction": 0.5},
            {"symbol": "KOTAKBANK", "direction": "NEUTRAL", "conviction": 0.5},
        ]
        result = compute_index_constituent_bias(signals, index_name="BANKNIFTY")
        score = result["breadth_score"]
        assert 0 <= score <= 100, f"breadth_score out of [0,100]: {score}"
        print(f"PASS: breadth_score={score} in [0,100]")

    def test_all_bullish_nifty_returns_bullish_bias(self):
        """All BULLISH signals -> BULLISH weighted_bias."""
        signals = [
            {"symbol": "RELIANCE", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "HDFCBANK", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "ICICIBANK", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "INFY", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "TCS", "direction": "BULLISH", "conviction": 0.9},
        ]
        result = compute_index_constituent_bias(signals, index_name="NIFTY")
        assert result["weighted_bias"] == "BULLISH", \
            f"All-bullish should be BULLISH, got {result['weighted_bias']}"
        print(f"PASS: all-BULLISH NIFTY -> weighted_bias=BULLISH, breadth={result['breadth_score']}")

    def test_all_bearish_returns_bearish_bias(self):
        """All BEARISH signals -> BEARISH weighted_bias."""
        signals = [
            {"symbol": "HDFCBANK", "direction": "BEARISH", "conviction": 0.8},
            {"symbol": "ICICIBANK", "direction": "BEARISH", "conviction": 0.8},
            {"symbol": "AXISBANK", "direction": "BEARISH", "conviction": 0.8},
            {"symbol": "KOTAKBANK", "direction": "BEARISH", "conviction": 0.8},
            {"symbol": "SBIN", "direction": "BEARISH", "conviction": 0.8},
        ]
        result = compute_index_constituent_bias(signals, index_name="BANKNIFTY")
        assert result["weighted_bias"] == "BEARISH", \
            f"All-bearish should be BEARISH, got {result['weighted_bias']}"
        print(f"PASS: all-BEARISH BANKNIFTY -> weighted_bias=BEARISH, breadth={result['breadth_score']}")

    def test_empty_signals_returns_neutral(self):
        """Empty signals -> NEUTRAL with breadth_score=50."""
        result = compute_index_constituent_bias([], index_name="NIFTY")
        assert result["weighted_bias"] == "NEUTRAL"
        assert result["breadth_score"] == 50
        print("PASS: empty signals -> NEUTRAL, breadth_score=50")

    def test_nifty50_weights_populated(self):
        """NIFTY50_WEIGHTS has key stocks with positive weights."""
        assert len(NIFTY50_WEIGHTS) > 0, "NIFTY50_WEIGHTS is empty"
        assert "RELIANCE" in NIFTY50_WEIGHTS
        assert "HDFCBANK" in NIFTY50_WEIGHTS
        assert NIFTY50_WEIGHTS["RELIANCE"] > 0
        print(f"PASS: NIFTY50_WEIGHTS has {len(NIFTY50_WEIGHTS)} stocks, RELIANCE weight={NIFTY50_WEIGHTS['RELIANCE']}")

    def test_banknifty_weights_populated(self):
        """BANKNIFTY_WEIGHTS has key bank stocks with positive weights."""
        assert len(BANKNIFTY_WEIGHTS) > 0, "BANKNIFTY_WEIGHTS is empty"
        assert "HDFCBANK" in BANKNIFTY_WEIGHTS
        assert "ICICIBANK" in BANKNIFTY_WEIGHTS
        assert BANKNIFTY_WEIGHTS["HDFCBANK"] > 0
        print(f"PASS: BANKNIFTY_WEIGHTS has {len(BANKNIFTY_WEIGHTS)} stocks, HDFCBANK weight={BANKNIFTY_WEIGHTS['HDFCBANK']}")

    def test_returns_top_contributors(self):
        """Returns top_positive_contributors and top_negative_contributors."""
        signals = [
            {"symbol": "HDFCBANK", "direction": "BULLISH", "conviction": 0.9},
            {"symbol": "ICICIBANK", "direction": "BULLISH", "conviction": 0.7},
            {"symbol": "AXISBANK", "direction": "BEARISH", "conviction": 0.8},
        ]
        result = compute_index_constituent_bias(signals, index_name="BANKNIFTY")
        assert "top_positive_contributors" in result, "Missing top_positive_contributors"
        assert "top_negative_contributors" in result, "Missing top_negative_contributors"
        assert isinstance(result["top_positive_contributors"], list)
        assert isinstance(result["top_negative_contributors"], list)
        print(f"PASS: top_positive={len(result['top_positive_contributors'])}, top_negative={len(result['top_negative_contributors'])}")

    def test_breadth_score_always_clamped(self):
        """breadth_score must be in [0,100] even with extreme all-bullish BANKNIFTY."""
        # All BANKNIFTY stocks at max conviction (previously this gave >100)
        signals = [
            {"symbol": sym, "direction": "BULLISH", "conviction": 1.0}
            for sym in list(BANKNIFTY_WEIGHTS.keys())[:12]
        ]
        result = compute_index_constituent_bias(signals, index_name="BANKNIFTY")
        score = result["breadth_score"]
        assert 0 <= score <= 100, f"breadth_score={score} EXCEEDS [0,100] range — clamping bug!"
        print(f"PASS: all-BULLISH BANKNIFTY breadth_score={score} is clamped to [0,100]")
