"""
Iteration 50: IV Cone + IV Term Structure + Multi-Timeframe Analysis Tests

Tests:
1. GET /api/fno/iv-cone/{symbol} - IV Cone with percentile bands
2. GET /api/fno/iv-term-structure/{symbol} - IV Term Structure
3. GET /api/fno/multi-timeframe/{symbol} - Multi-timeframe analysis with alignment
4. Regression: GET /api/fno/performance-stats - Still works
5. Regression: GET /api/fno/signal-history - Still works
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def auth_headers():
    """Get auth headers by logging in as owner."""
    resp = requests.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"})
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    token = resp.json().get("token")
    assert token, "No token returned"
    return {"Authorization": f"Bearer {token}"}


class TestIVConeEndpoint:
    """Tests for GET /api/fno/iv-cone/{symbol}"""

    def test_iv_cone_nifty_returns_valid_structure(self, auth_headers):
        """IV Cone for NIFTY returns valid structure with data_points, points, bands fields."""
        resp = requests.get(f"{BASE_URL}/api/fno/iv-cone/NIFTY", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Required fields
        assert "symbol" in data, "Missing 'symbol' field"
        assert data["symbol"] == "NIFTY", f"Expected symbol NIFTY, got {data['symbol']}"
        assert "data_points" in data, "Missing 'data_points' field"
        assert isinstance(data["data_points"], int), "data_points should be int"
        assert "points" in data, "Missing 'points' field"
        assert isinstance(data["points"], list), "points should be list"
        
        # bands can be None if no data
        assert "bands" in data, "Missing 'bands' field"
        
        # If no data, should have message
        if data["data_points"] == 0:
            assert "message" in data, "Should have message when no data"
            print(f"IV Cone NIFTY: No data yet - {data.get('message')}")
        else:
            # If data exists, bands should have percentile keys
            assert data["bands"] is not None, "bands should not be None when data exists"
            for key in ["p10", "p25", "p50", "p75", "p90", "min", "max", "mean"]:
                assert key in data["bands"], f"Missing band key: {key}"
            print(f"IV Cone NIFTY: {data['data_points']} data points, current_iv={data.get('current_iv')}")

    def test_iv_cone_reliance_returns_valid_structure(self, auth_headers):
        """IV Cone for RELIANCE returns valid structure."""
        resp = requests.get(f"{BASE_URL}/api/fno/iv-cone/RELIANCE", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["symbol"] == "RELIANCE"
        assert "data_points" in data
        assert "points" in data
        assert "bands" in data
        print(f"IV Cone RELIANCE: {data['data_points']} data points")


class TestIVTermStructureEndpoint:
    """Tests for GET /api/fno/iv-term-structure/{symbol}"""

    def test_iv_term_structure_nifty_returns_valid_structure(self, auth_headers):
        """IV Term Structure for NIFTY returns valid structure with term_points."""
        resp = requests.get(f"{BASE_URL}/api/fno/iv-term-structure/NIFTY", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Required fields
        assert "symbol" in data, "Missing 'symbol' field"
        assert data["symbol"] == "NIFTY"
        assert "data_points" in data, "Missing 'data_points' field"
        assert "term_points" in data, "Missing 'term_points' field"
        assert isinstance(data["term_points"], list), "term_points should be list"
        
        # If no data, should have message
        if data["data_points"] == 0:
            assert "message" in data, "Should have message when no data"
            print(f"IV Term Structure NIFTY: No data yet - {data.get('message')}")
        else:
            # If data exists, term_points should have expiry, dte, iv
            assert len(data["term_points"]) > 0
            for pt in data["term_points"]:
                assert "expiry" in pt, "Missing expiry in term_point"
                assert "dte" in pt, "Missing dte in term_point"
                assert "iv" in pt, "Missing iv in term_point"
            print(f"IV Term Structure NIFTY: {data['data_points']} term points")

    def test_iv_term_structure_reliance_returns_valid_structure(self, auth_headers):
        """IV Term Structure for RELIANCE returns valid structure."""
        resp = requests.get(f"{BASE_URL}/api/fno/iv-term-structure/RELIANCE", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["symbol"] == "RELIANCE"
        assert "data_points" in data
        assert "term_points" in data
        print(f"IV Term Structure RELIANCE: {data['data_points']} term points")


class TestMultiTimeframeEndpoint:
    """Tests for GET /api/fno/multi-timeframe/{symbol}"""

    def test_multi_timeframe_reliance_returns_frames_and_alignment(self, auth_headers):
        """Multi-timeframe for RELIANCE returns frames (daily/weekly/monthly) with indicators and alignment."""
        resp = requests.get(f"{BASE_URL}/api/fno/multi-timeframe/RELIANCE", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Required fields
        assert "symbol" in data, "Missing 'symbol' field"
        assert data["symbol"] == "RELIANCE"
        assert "data_available" in data, "Missing 'data_available' field"
        assert "frames" in data, "Missing 'frames' field"
        assert "alignment" in data, "Missing 'alignment' field"
        
        # Alignment should be one of expected values
        valid_alignments = ["STRONGLY_BULLISH", "BULLISH", "STRONGLY_BEARISH", "BEARISH", "MIXED", "INSUFFICIENT_DATA", "NO_DATA"]
        assert data["alignment"] in valid_alignments, f"Invalid alignment: {data['alignment']}"
        
        if data["data_available"]:
            # Should have daily, weekly, monthly frames
            frames = data["frames"]
            for tf in ["daily", "weekly", "monthly"]:
                assert tf in frames, f"Missing {tf} frame"
                frame = frames[tf]
                assert "label" in frame, f"Missing label in {tf} frame"
                assert "trend" in frame, f"Missing trend in {tf} frame"
                assert "indicators" in frame, f"Missing indicators in {tf} frame"
                
                # Check indicators
                ind = frame["indicators"]
                for key in ["rsi", "macd_direction", "bb_position_pct", "volume_trend", "price_change_pct"]:
                    assert key in ind, f"Missing {key} in {tf} indicators"
            
            print(f"Multi-TF RELIANCE: alignment={data['alignment']}, bullish={data.get('bullish_frames')}, bearish={data.get('bearish_frames')}")
        else:
            print(f"Multi-TF RELIANCE: No data - {data.get('message')}")

    def test_multi_timeframe_nifty_returns_structure(self, auth_headers):
        """Multi-timeframe for NIFTY (index) returns valid structure - may have NO_DATA."""
        resp = requests.get(f"{BASE_URL}/api/fno/multi-timeframe/NIFTY", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "symbol" in data
        assert data["symbol"] == "NIFTY"
        assert "alignment" in data
        assert "frames" in data
        print(f"Multi-TF NIFTY: alignment={data['alignment']}, data_available={data.get('data_available')}")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints."""

    def test_performance_stats_still_works(self, auth_headers):
        """GET /api/fno/performance-stats still returns valid structure."""
        resp = requests.get(f"{BASE_URL}/api/fno/performance-stats", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Required fields from iteration 49
        for key in ["total", "wins", "losses", "neutral", "win_rate", "avg_pnl_pct"]:
            assert key in data, f"Missing '{key}' in performance-stats"
        print(f"Performance Stats: total={data['total']}, win_rate={data['win_rate']}")

    def test_signal_history_still_works(self, auth_headers):
        """GET /api/fno/signal-history still returns paginated history."""
        resp = requests.get(f"{BASE_URL}/api/fno/signal-history", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "history" in data, "Missing 'history' field"
        assert "count" in data, "Missing 'count' field"
        assert isinstance(data["history"], list), "history should be list"
        print(f"Signal History: count={data['count']}")
