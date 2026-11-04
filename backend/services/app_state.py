"""
Centralized application state — breaks circular import chain.

server.py populates these at startup. Services and routes import from here
instead of doing lazy `import server` for basic state access.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

# ── Database ──────────────────────────────────────────────────────────────────
db: Optional[AsyncIOMotorDatabase] = None

# ── Timezone ──────────────────────────────────────────────────────────────────
IST: timezone = timezone(timedelta(hours=5, minutes=30))

# ── Kite Connect ──────────────────────────────────────────────────────────────
KITE_API_KEY: Optional[str] = None
KITE_API_SECRET: Optional[str] = None
KITE_REDIRECT_URL: Optional[str] = None
kite_access_token: Optional[str] = None

# ── Config Constants ──────────────────────────────────────────────────────────
CONFLUENCE_THRESHOLD_DISPLAY: int = 55

# ── Caches (populated at runtime) ─────────────────────────────────────────────
SECTOR_MOMENTUM_CACHE: dict[str, Any] = {}
SECTOR_MOMENTUM_CACHE_TTL_SECONDS: int = 1800

# ── Script Master Tracking ────────────────────────────────────────────────────
SCRIPT_MASTER_LAST_SYNC_DATE: Optional[str] = None
KITE_OPTION_MASTER_LAST_SYNC_DATE: Optional[str] = None
KITE_SCRIPT_MASTER_URL: str = "https://api.kite.trade/instruments"

# ── LOT_SIZE_MAP (populated from data/lot_sizes.py at startup) ────────────────
LOT_SIZE_MAP: dict[str, int] = {}

# ── Performance Tracking ──────────────────────────────────────────────────────
LAST_FNO_PERF: dict[str, Any] = {}
LAST_MB_PERF: dict[str, Any] = {}

# ── Session Store (shared between auth and routes) ────────────────────────────
SESSION_STORE: dict[str, dict[str, Any]] = {}

# ── Runtime Config (populated by server.py) ───────────────────────────────────
KITE_ALLOWED_DATA_ENDPOINTS: list[str] = []
KITE_READ_ONLY_MODE: bool = False
NSE_HOLIDAYS: set[str] = set()
OWNER_BOOTSTRAP_USERNAME: str = ""
LEGACY_OWNER_ALIAS: str = ""


def configure(
    database: AsyncIOMotorDatabase,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    redirect_url: Optional[str] = None,
    access_token: Optional[str] = None,
) -> None:
    """Called by server.py on startup to inject shared state."""
    global db, KITE_API_KEY, KITE_API_SECRET, KITE_REDIRECT_URL, kite_access_token
    db = database
    if api_key is not None:
        KITE_API_KEY = api_key
    if api_secret is not None:
        KITE_API_SECRET = api_secret
    if redirect_url is not None:
        KITE_REDIRECT_URL = redirect_url
    if access_token is not None:
        kite_access_token = access_token


def configure_runtime(
    session_store: Optional[dict] = None,
    allowed_endpoints: Optional[list[str]] = None,
    read_only: Optional[bool] = None,
    holidays: Optional[set] = None,
    owner_username: Optional[str] = None,
    legacy_alias: Optional[str] = None,
) -> None:
    """Called by server.py after full init to inject runtime config."""
    global SESSION_STORE, KITE_ALLOWED_DATA_ENDPOINTS, KITE_READ_ONLY_MODE
    global NSE_HOLIDAYS, OWNER_BOOTSTRAP_USERNAME, LEGACY_OWNER_ALIAS
    if session_store is not None:
        SESSION_STORE = session_store
    if allowed_endpoints is not None:
        KITE_ALLOWED_DATA_ENDPOINTS = allowed_endpoints
    if read_only is not None:
        KITE_READ_ONLY_MODE = read_only
    if holidays is not None:
        NSE_HOLIDAYS = holidays
    if owner_username is not None:
        OWNER_BOOTSTRAP_USERNAME = owner_username
    if legacy_alias is not None:
        LEGACY_OWNER_ALIAS = legacy_alias


def _utc_now_iso() -> str:
    """UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()
