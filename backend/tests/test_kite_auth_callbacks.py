import asyncio
import hashlib
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import services.app_state as app_state
from routes.market_data import get_kite_auth_url, kite_postback


class KiteAuthCallbackTests(unittest.TestCase):
    def test_auth_url_uses_server_api_key_without_redirect_env(self):
        with (
            patch.object(app_state, "KITE_API_KEY", "test-api-key"),
            patch.object(app_state, "KITE_API_SECRET", "test-api-secret"),
            patch.object(app_state, "KITE_REDIRECT_URL", None),
        ):
            result = asyncio.run(get_kite_auth_url({}))

        self.assertEqual(
            result["auth_url"],
            "https://kite.zerodha.com/connect/login?v=3&api_key=test-api-key",
        )
        self.assertIsNone(result["redirect_url"])
        self.assertNotIn("test-api-secret", result["auth_url"])

    def test_postback_accepts_valid_kite_checksum(self):
        secret = "test-api-secret"
        order_id = "220303000308932"
        order_timestamp = "2022-03-03 09:24:25"
        checksum = hashlib.sha256(f"{order_id}{order_timestamp}{secret}".encode()).hexdigest()
        payload = {
            "order_id": order_id,
            "order_timestamp": order_timestamp,
            "checksum": checksum,
        }

        with patch.object(app_state, "KITE_API_SECRET", secret):
            result = asyncio.run(kite_postback(payload))

        self.assertEqual(result, {"received": True})

    def test_postback_rejects_invalid_checksum(self):
        payload = {
            "order_id": "220303000308932",
            "order_timestamp": "2022-03-03 09:24:25",
            "checksum": "0" * 64,
        }

        with patch.object(app_state, "KITE_API_SECRET", "test-api-secret"):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(kite_postback(payload))

        self.assertEqual(error.exception.status_code, 401)

    def test_postback_rejects_missing_signature_fields(self):
        with patch.object(app_state, "KITE_API_SECRET", "test-api-secret"):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(kite_postback({"order_id": "220303000308932"}))

        self.assertEqual(error.exception.status_code, 400)

    def test_postback_requires_server_secret(self):
        with patch.object(app_state, "KITE_API_SECRET", None):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(kite_postback({}))

        self.assertEqual(error.exception.status_code, 503)


class StartupLifecycleTests(unittest.TestCase):
    def test_startup_does_not_wait_for_database_maintenance(self):
        import server

        async def verify():
            started = asyncio.Event()
            release = asyncio.Event()
            completed = asyncio.Event()

            async def blocked_maintenance():
                started.set()
                await release.wait()
                completed.set()

            with patch.object(server, "_run_startup_maintenance", blocked_maintenance):
                await server.startup_tasks()
                await asyncio.wait_for(started.wait(), timeout=1)
                self.assertFalse(release.is_set())
                release.set()
                await asyncio.wait_for(completed.wait(), timeout=1)

        asyncio.run(verify())


if __name__ == "__main__":
    unittest.main()
