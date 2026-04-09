"""
India VIX — Kite Connect only, with 5-minute cache.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import requests

from services.kite_client import _get_kite_access_token

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


async def _get_india_vix() -> float | None:
    """Fetch India VIX — Kite Connect only, with 5-minute cache."""
    _s = _srv()
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _s.INDIA_VIX_CACHE.get("value")
    cached_ts = _s.INDIA_VIX_CACHE.get("ts", 0.0)
    if cached is not None and (now_ts - cached_ts) < _s.INDIA_VIX_CACHE_TTL_SECONDS:
        return float(cached)

    vix = None

    # PRIMARY (and sole source): Kite quote for India VIX
    access_token = await _get_kite_access_token()
    if access_token and _s.KITE_API_KEY:
        def _fetch_vix_kite() -> float | None:
            try:
                vix_tokens = ["NSE:INDIA VIX", "NSE:INDIAVIX"]
                for sym in vix_tokens:
                    resp = requests.get(
                        "https://api.kite.trade/quote/ltp",
                        params={"i": sym},
                        headers={
                            "X-Kite-Version": "3",
                            "Authorization": f"token {_s.KITE_API_KEY}:{access_token}",
                        },
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        for key, val in data.items():
                            ltp = val.get("last_price")
                            if ltp and float(ltp) > 0:
                                return float(ltp)
                return None
            except Exception as exc:
                logger.debug("Kite VIX fetch failed: %s", exc)
                return None

        try:
            vix = await asyncio.wait_for(asyncio.to_thread(_fetch_vix_kite), timeout=8.0)
            if vix:
                logger.debug(f"India VIX from Kite: {vix:.1f}")
        except Exception:
            pass

    # No third-party fallback — Kite is the sole VIX source

    if vix is not None:
        _s.INDIA_VIX_CACHE["value"] = vix
        _s.INDIA_VIX_CACHE["ts"] = now_ts
    return vix
