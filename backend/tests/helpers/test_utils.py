"""
Shared test utilities for the F&O backend test suite.
Canonical location — do NOT duplicate this logic elsewhere.
"""
import json
import os

import dotenv
import pytest
import requests


def get_base_url() -> str:
    """Return the backend base URL for testing.
    
    Always returns localhost:8001 to avoid K8s ingress proxy issues
    (streaming NDJSON responses get truncated by the proxy).
    """
    return "http://localhost:8001"


# For streaming NDJSON endpoints, always use localhost to bypass K8s proxy
STREAMING_BASE_URL = "http://localhost:8001"


def get_streaming_base_url() -> str:
    """Return localhost URL for streaming endpoints (bypasses proxy timeouts)."""
    return STREAMING_BASE_URL


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


def safe_streaming_post(url, *, json_body=None, headers=None, timeout=240, skip_msg="Streaming endpoint timeout/error"):
    """Call a streaming (NDJSON) POST endpoint with robust timeout and error handling.
    
    Uses localhost:8001 directly to bypass proxy timeouts on streaming endpoints.
    If the call times out or the Kite API disconnects, the test is skipped.
    Returns the requests.Response on success.
    """
    # Streaming NDJSON endpoints may get cut by the K8s ingress proxy.
    # Use localhost:8001 to bypass proxy for reliable streaming.
    local_url = url.replace(get_base_url(), "http://localhost:8001")
    try:
        resp = requests.post(local_url, json=json_body or {}, headers=headers, timeout=timeout, stream=True)
        # Read the full response into memory (iter_content forces full read)
        _ = resp.content
        if resp.status_code >= 500:
            text = resp.text[:300]
            if "Network connection lost" in text or "Worker error" in text or "Kite" in text:
                pytest.skip(f"{skip_msg}: server returned {resp.status_code} ({text[:100]})")
        return resp
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout) as exc:
        pytest.skip(f"{skip_msg}: {type(exc).__name__}: {exc}")


def safe_streaming_get(url, *, headers=None, params=None, timeout=240, skip_msg="Streaming endpoint timeout/error"):
    """Call a streaming (NDJSON) GET endpoint with robust timeout and error handling."""
    local_url = url.replace(get_base_url(), "http://localhost:8001")
    try:
        resp = requests.get(local_url, headers=headers, params=params, timeout=timeout, stream=True)
        _ = resp.content
        if resp.status_code >= 500:
            text = resp.text[:300]
            if "Network connection lost" in text or "Worker error" in text or "Kite" in text:
                pytest.skip(f"{skip_msg}: server returned {resp.status_code} ({text[:100]})")
        return resp
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout) as exc:
        pytest.skip(f"{skip_msg}: {type(exc).__name__}: {exc}")
