"""
Iteration 49: Signal History & Performance Tracking Tests

Tests:
1. /api/fno/performance-stats returns valid empty stats structure
2. /api/fno/signal-history returns paginated history
3. /api/fno/signal-log returns paginated log
4. close_card archives to fno_signal_history with outcome + pnl_pct
5. log_generated_signal inserts into fno_signal_log
6. get_performance_stats aggregates correctly with test data
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from datetime import datetime, timezone

def _resolve_base_url():
    url = os.environ.get('REACT_APP_BACKEND_URL', '').strip().rstrip('/')
    if url:
        return url
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip().rstrip('/')
    except FileNotFoundError:
        pass
    return 'https://backend-refactor-p2.preview.emergentagent.com'

BASE_URL = _resolve_base_url()


class TestPerformanceStatsEndpoint:
    def _get_token(self):
        r = httpx.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]

    def test_performance_stats_returns_valid_structure(self):
        token = self._get_token()
        r = httpx.get(f"{BASE_URL}/api/fno/performance-stats", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ["total", "wins", "losses", "neutral", "win_rate", "avg_pnl_pct", "best_trade_pnl", "worst_trade_pnl", "by_symbol"]:
            assert key in data, f"Missing key: {key}"
        assert isinstance(data["total"], int)
        assert isinstance(data["win_rate"], float)
        assert isinstance(data["by_symbol"], dict)


class TestSignalHistoryEndpoint:
    def _get_token(self):
        r = httpx.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]

    def test_signal_history_returns_paginated(self):
        token = self._get_token()
        r = httpx.get(f"{BASE_URL}/api/fno/signal-history?limit=10&skip=0", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "history" in data
        assert "count" in data
        assert isinstance(data["history"], list)


class TestSignalLogEndpoint:
    def _get_token(self):
        r = httpx.post(f"{BASE_URL}/api/auth/access", json={"username": "@shish123"}, timeout=15)
        return r.json()["token"]

    def test_signal_log_returns_paginated(self):
        token = self._get_token()
        r = httpx.get(f"{BASE_URL}/api/fno/signal-log?limit=10&skip=0", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "log" in data
        assert "count" in data
        assert isinstance(data["log"], list)


class TestCloseCardArchival:
    """Test that closing a sticky card archives it to signal history."""

    @pytest.mark.asyncio
    async def test_close_card_creates_history_entry(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["test_database"]

        from services.sticky_card_engine import (
            create_sticky_card, close_card, COLL_SIGNAL_HISTORY, COLL_STICKY_CARDS,
        )

        # Create a test signal
        test_signal = {
            "underlying": "TESTSTOCK",
            "script": "TESTSTOCK28APR1000CE",
            "direction": "BULLISH",
            "strategy_library_id": "test_strategy",
            "entry_price": 100.0,
            "stop_loss": 85.0,
            "target1": 120.0,
            "target2": 140.0,
            "best_exit_price": 130.0,
            "confluence_score": 85,
            "option_ltp": 105.0,
        }
        signal_id = await create_sticky_card(db, test_signal)
        assert signal_id

        # Update current_price to simulate price movement
        await db[COLL_STICKY_CARDS].update_one(
            {"signal_id": signal_id},
            {"$set": {"current_price": 120.0}},
        )

        # Close as win
        ok = await close_card(db, signal_id, "CLOSED_WIN", "t1_hit")
        assert ok

        # Verify history entry
        history_doc = await db[COLL_SIGNAL_HISTORY].find_one(
            {"signal_id": signal_id}, {"_id": 0},
        )
        assert history_doc is not None
        assert history_doc["outcome"] == "win"
        assert history_doc["pnl_pct"] == 20.0  # (120-100)/100 * 100
        assert history_doc["signal_state"] == "CLOSED_WIN"

        # Cleanup
        await db[COLL_STICKY_CARDS].delete_one({"signal_id": signal_id})
        await db[COLL_SIGNAL_HISTORY].delete_one({"signal_id": signal_id})
        client.close()


class TestLogGeneratedSignal:
    @pytest.mark.asyncio
    async def test_log_inserts_signal(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["test_database"]

        from services.sticky_card_engine import log_generated_signal, COLL_SIGNAL_LOG

        # Count before
        before = await db[COLL_SIGNAL_LOG].count_documents({})

        await log_generated_signal(db, {
            "underlying": "TESTSYM",
            "script": "TESTSYM28APR500CE",
            "direction": "BULLISH",
            "entry_price": 50.0,
            "stop_loss": 42.0,
            "target1": 60.0,
            "confluence_score": 75,
            "signal_quality": "GOOD",
        })

        after = await db[COLL_SIGNAL_LOG].count_documents({})
        assert after == before + 1

        # Cleanup
        await db[COLL_SIGNAL_LOG].delete_many({"symbol": "TESTSYM"})
        client.close()


class TestPerformanceStatsAggregation:
    @pytest.mark.asyncio
    async def test_aggregation_with_data(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["test_database"]

        from services.sticky_card_engine import get_performance_stats, COLL_SIGNAL_HISTORY

        # Insert test data
        test_docs = [
            {"signal_id": "test_agg_1", "symbol": "SYM_A", "outcome": "win", "pnl_pct": 15.0, "signal_state": "CLOSED_WIN"},
            {"signal_id": "test_agg_2", "symbol": "SYM_A", "outcome": "loss", "pnl_pct": -8.0, "signal_state": "CLOSED_LOSS"},
            {"signal_id": "test_agg_3", "symbol": "SYM_B", "outcome": "win", "pnl_pct": 22.0, "signal_state": "CLOSED_WIN"},
            {"signal_id": "test_agg_4", "symbol": "SYM_B", "outcome": "neutral", "pnl_pct": 0.0, "signal_state": "EXPIRED"},
        ]
        await db[COLL_SIGNAL_HISTORY].insert_many(test_docs)

        stats = await get_performance_stats(db)
        assert stats["total"] >= 4
        assert stats["wins"] >= 2
        assert stats["losses"] >= 1

        # Cleanup
        await db[COLL_SIGNAL_HISTORY].delete_many({"signal_id": {"$regex": "^test_agg_"}})
        client.close()
