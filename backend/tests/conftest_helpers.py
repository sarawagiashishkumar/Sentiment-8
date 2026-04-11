"""
Shared test configuration — credentials from env vars, not hardcoded.
"""
import os
from pathlib import Path


def get_base_url() -> str:
    """Resolve BASE_URL from env or frontend .env file."""
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    env_path = Path(__file__).resolve().parent.parent.parent / "frontend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return "http://localhost:8001"


# Credentials from environment — fallback to known test defaults
OWNER_USERNAME = os.environ.get("TEST_OWNER_USERNAME", "@shish123")
USER_USERNAME = os.environ.get("TEST_USER_USERNAME", "Manas@2005")
