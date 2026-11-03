from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deps
from routes import livehelp


class FakeSessions:
    def __init__(self, token_hash: str, user_key: str):
        self.token_hash = token_hash
        self.user_key = user_key
        self.query = None

    async def find_one(self, query, projection=None):
        self.query = query
        if query.get("token_hash") != self.token_hash:
            return None
        cutoff = query.get("expires_at", {}).get("$gt")
        if not isinstance(cutoff, datetime) or cutoff.tzinfo != timezone.utc:
            return None
        return {"user_key": self.user_key}


class FakeUsers:
    async def find_one(self, query, projection=None):
        if query.get("user_key") == "user-1":
            return {"user_key": "user-1", "username": "test-user", "role": "user"}
        return None


class FakeCrmMessages:
    def __init__(self):
        self.documents = []

    async def find_one(self, query, projection=None):
        cutoff = query.get("ts_epoch", {}).get("$gte", float("-inf"))
        return next(
            (
                doc for doc in self.documents
                if doc.get("type") == query.get("type")
                and doc.get("dedupe_key") == query.get("dedupe_key")
                and doc.get("ts_epoch", 0) >= cutoff
            ),
            None,
        )

    async def insert_one(self, document):
        self.documents.append(document)


class FakeDatabase:
    def __init__(self, token_hash: str | None = None):
        self.login_sessions = FakeSessions(token_hash or "", "user-1")
        self.app_users = FakeUsers()
        self.crm_messages = FakeCrmMessages()


def test_current_user_resolves_session_from_shared_database():
    token = "persisted-session-token"
    database = FakeDatabase(deps.hash_session_token(token))
    previous_db, previous_store = deps.db, deps.SESSION_STORE
    deps.configure(database, {})
    try:
        user = asyncio.run(deps.get_current_user(f"Bearer {token}"))
    finally:
        deps.configure(previous_db, previous_store)

    assert user["user_key"] == "user-1"
    assert token not in deps.SESSION_STORE
    assert database.login_sessions.query["token_hash"] == deps.hash_session_token(token)


def test_log_action_skips_auth_tickets_and_deduplicates_server_errors():
    database = FakeDatabase()
    previous_db = livehelp._state.db
    livehelp._state.db = database
    current_user = {"user_key": "user-1", "username": "test-user"}
    try:
        asyncio.run(livehelp.log_session_action(
            {"endpoint": "/livehelp/log-action", "status": "401", "error": "Invalid session"},
            current_user=current_user,
        ))
        assert database.crm_messages.documents == []

        action = {"endpoint": "/api/signals", "status": "500", "error": "Internal error"}
        asyncio.run(livehelp.log_session_action(action, current_user=current_user))
        asyncio.run(livehelp.log_session_action(action, current_user=current_user))
    finally:
        livehelp._state.db = previous_db

    assert len(database.crm_messages.documents) == 1
    assert database.crm_messages.documents[0]["type"] == "auto_bug_ticket"
