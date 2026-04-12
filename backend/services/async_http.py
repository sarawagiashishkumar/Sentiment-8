"""
Async HTTP Client — Non-blocking replacement for synchronous `requests` calls.
Eliminates event loop blocking in FastAPI async handlers.
"""
import asyncio
import logging
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

# Shared httpx async client (connection pooling, keep-alive)
_client: httpx.AsyncClient | None = None


def get_async_client() -> httpx.AsyncClient:
    """Get or create a shared httpx AsyncClient with connection pooling."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=True,
        )
    return _client


async def async_get(url: str, headers: dict | None = None, params: dict | None = None, timeout: float = 15.0) -> httpx.Response:
    """Non-blocking HTTP GET — drop-in replacement for requests.get()."""
    client = get_async_client()
    return await client.get(url, headers=headers, params=params, timeout=timeout)


async def async_post(url: str, headers: dict | None = None, data: dict | None = None, json: dict | None = None, timeout: float = 15.0) -> httpx.Response:
    """Non-blocking HTTP POST — drop-in replacement for requests.post()."""
    client = get_async_client()
    return await client.post(url, headers=headers, data=data, json=json, timeout=timeout)


async def async_get_text(url: str, headers: dict | None = None, timeout: float = 30.0) -> str:
    """Non-blocking GET that returns response text (for CSV/script master downloads)."""
    client = get_async_client()
    resp = await client.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


async def close_client():
    """Close the shared httpx client (call on shutdown)."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
