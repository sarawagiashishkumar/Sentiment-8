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
kite_access_token = None  # Set via admin endpoint

# ── Config Constants ──────────────────────────────────────────────────────────
CONFLUENCE_THRESHOLD_DISPLAY = 40


def configure(database, api_key=None, access_token=None):
    """Called by server.py on startup to inject shared state."""
    global db, KITE_API_KEY, kite_access_token
    db = database
    if api_key is not None:
        KITE_API_KEY = api_key
    if access_token is not None:
        kite_access_token = access_token
