"""
Centralized application state — breaks circular import chain.

server.py populates these at startup. Services import from here
instead of doing lazy `import server` for basic state access.
"""
from datetime import timezone, timedelta

# ── Database ──────────────────────────────────────────────────────────────────
db = None  # Set by server.py on startup (AsyncIOMotorDatabase)

# ── Timezone ──────────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))

# ── Kite Connect ──────────────────────────────────────────────────────────────
KITE_API_KEY = None       # Set from env
KITE_API_SECRET = None    # Set from env
KITE_REDIRECT_URL = None  # Set from env
kite_access_token = None  # Set via admin endpoint

# ── Config Constants ──────────────────────────────────────────────────────────
CONFLUENCE_THRESHOLD_DISPLAY = 40

# ── Caches (populated at runtime) ─────────────────────────────────────────────
SECTOR_MOMENTUM_CACHE = {}
SECTOR_MOMENTUM_CACHE_TTL_SECONDS = 1800  # 30 minutes

# ── Script Master Tracking ────────────────────────────────────────────────────
SCRIPT_MASTER_LAST_SYNC_DATE = None
KITE_OPTION_MASTER_LAST_SYNC_DATE = None
KITE_SCRIPT_MASTER_URL = "https://api.kite.trade/instruments"

# ── LOT_SIZE_MAP (populated from data/lot_sizes.py at startup) ────────────────
LOT_SIZE_MAP = {}

# ── Performance Tracking ──────────────────────────────────────────────────────
LAST_FNO_PERF = {}   # Last F&O generation phase timings
LAST_MB_PERF = {}    # Last Multibagger generation timings


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
