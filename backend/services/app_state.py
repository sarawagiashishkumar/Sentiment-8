"""
Centralized application state — breaks circular import chain.

server.py populates these at startup. Services and routes import from here
instead of doing lazy `import server` for basic state access.
"""
from datetime import timezone, timedelta

# ── Database ──────────────────────────────────────────────────────────────────
db = None  # Set by server.py on startup (AsyncIOMotorDatabase)

# ── Timezone ──────────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))

# ── Kite Connect ──────────────────────────────────────────────────────────────
KITE_API_KEY = None
KITE_API_SECRET = None
KITE_REDIRECT_URL = None
kite_access_token = None

# ── Config Constants ──────────────────────────────────────────────────────────
CONFLUENCE_THRESHOLD_DISPLAY = 40

# ── Caches (populated at runtime) ─────────────────────────────────────────────
SECTOR_MOMENTUM_CACHE = {}
SECTOR_MOMENTUM_CACHE_TTL_SECONDS = 1800

# ── Script Master Tracking ────────────────────────────────────────────────────
SCRIPT_MASTER_LAST_SYNC_DATE = None
KITE_OPTION_MASTER_LAST_SYNC_DATE = None
KITE_SCRIPT_MASTER_URL = "https://api.kite.trade/instruments"

# ── LOT_SIZE_MAP (populated from data/lot_sizes.py at startup) ────────────────
LOT_SIZE_MAP = {}

# ── Performance Tracking ──────────────────────────────────────────────────────
LAST_FNO_PERF = {}
LAST_MB_PERF = {}

# ── Session Store (shared between auth and routes) ────────────────────────────
SESSION_STORE: dict = {}

# ── Runtime Config (populated by server.py) ───────────────────────────────────
KITE_ALLOWED_DATA_ENDPOINTS: list = []
KITE_READ_ONLY_MODE: bool = False
NSE_HOLIDAYS: set = set()
OWNER_BOOTSTRAP_USERNAME: str = ""
LEGACY_OWNER_ALIAS: str = ""


def configure(database, api_key=None, api_secret=None, redirect_url=None, access_token=None):
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


def configure_runtime(session_store=None, allowed_endpoints=None, read_only=None,
                      holidays=None, owner_username=None, legacy_alias=None):
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
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
