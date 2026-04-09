"""
Shared test utilities for the F&O backend test suite.
Canonical location — do NOT duplicate this logic elsewhere.
"""
import json
import os

import dotenv


def get_base_url() -> str:
    """Return the backend base URL, falling back through multiple sources."""
    dotenv.load_dotenv("/app/frontend/.env", override=False)
    url = os.getenv("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if url:
        return url
    # Last-resort fallback
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    return "http://localhost:8001"


def parse_ndjson_response(response) -> list:
    """Parse an NDJSON (newline-delimited JSON) HTTP response into a list of dicts.

    Works with both ``requests.Response`` and ``httpx.Response`` objects.
    Skips blank lines. Raises ``AssertionError`` on malformed lines.
    """
    text = response.text if hasattr(response, "text") else response.content.decode()
    results = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Malformed NDJSON on line {i}: {exc}\nContent: {line[:200]}"
            ) from exc
    return results


def get_ndjson_complete_data(response) -> dict:
    """Return the ``data`` payload from the first NDJSON line whose ``type`` is
    ``"complete"``.  Falls back to returning the last parsed object if no
    ``type`` field is present (backward-compat with plain-JSON responses).
    """
    items = parse_ndjson_response(response)
    for item in items:
        if item.get("type") == "complete":
            return item.get("data", item)
    # Fallback: return last item (may be a plain dict from a non-streaming endpoint)
    if items:
        return items[-1]
    raise AssertionError("NDJSON response contained no parseable objects")


def get_first_ndjson_result(response) -> dict:
    """Alias kept for spec compliance — returns the complete data payload."""
    return get_ndjson_complete_data(response)


def read_backend_source() -> str:
    """Read and concatenate all relevant backend Python source files.
    
    Used by source-code inspection tests that need to search across server.py
    AND extracted modules in services/ and routes/.
    """
    import glob
    content = ""
    search_paths = [
        "/app/backend/server.py",
    ]
    for pattern in ["/app/backend/services/*.py", "/app/backend/routes/*.py"]:
        search_paths.extend(sorted(glob.glob(pattern)))
    for fp in search_paths:
        try:
            with open(fp, "r") as f:
                content += f"\n# === FILE: {fp} ===\n" + f.read()
        except FileNotFoundError:
            continue
    return content
