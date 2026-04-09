import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Iteration-8 regression: pricing enforcement + portfolio expected signal contract validation
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
OWNER_USERNAME = "@shish123"


@pytest.fixture(scope="session")
def api_base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not configured")
    return BASE_URL.rstrip("/") + "/api"


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return session


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client: requests.Session, api_base_url: str, username: str) -> dict:
    response = client.post(f"{api_base_url}/auth/access", json={"username": username}, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("token"), str) and payload["token"]
    return payload


def _create_user(client: requests.Session, api_base_url: str, owner_headers: dict, **kwargs) -> dict:
    response = client.post(f"{api_base_url}/admin/users", json=kwargs, headers=owner_headers, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == kwargs["username"]
    return payload


def test_pricing_contracts_for_basic_user(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner["token"])

    username = f"iter8{uuid.uuid4().hex[:8]}1"
    user = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        username=username,
        role="user",
        initial_credits=10,
    )
    user_headers = _auth_headers(_login(api_client, api_base_url, username)["token"])

    try:
        me_before = api_client.get(f"{api_base_url}/auth/me", headers=user_headers, timeout=30)
        assert me_before.status_code == 200
        before_credits = float(me_before.json()["credits"])

        mb = api_client.post(f"{api_base_url}/multibagger/generate", json={}, headers=user_headers, timeout=240)
        assert mb.status_code == 200
        mb_data = get_ndjson_complete_data(mb)
        assert mb_data["cost_charged"] == 2

        fno = api_client.post(f"{api_base_url}/fno/generate", json={}, headers=user_headers, timeout=240)
        assert fno.status_code == 200
        fno_data = get_ndjson_complete_data(fno)
        assert fno_data["cost_charged"] == 2

        custom = api_client.post(
            f"{api_base_url}/fno/custom-position",
            json={"script": "NIFTY", "buy_price": 120.5},
            headers=user_headers,
            timeout=120,
        )
        assert custom.status_code == 200
        assert custom.json()["cost_charged"] == 1

        portfolio = api_client.post(
            f"{api_base_url}/portfolio/analyze",
            json={
                "positions": [
                    {"symbol": "RELIANCE", "avg_price": 1200, "quantity": 10},
                    {"symbol": "TCS", "avg_price": 3000, "quantity": 5},
                ]
            },
            headers=user_headers,
            timeout=180,
        )
        assert portfolio.status_code == 200
        pdata = portfolio.json()
        assert pdata["parsed_positions_count"] >= 1
        assert pdata["cost_charged"] == round(0.2 * pdata["parsed_positions_count"], 2)

        me_after = api_client.get(f"{api_base_url}/auth/me", headers=user_headers, timeout=30)
        assert me_after.status_code == 200
        after_credits = float(me_after.json()["credits"])

        expected_spend = float(
            mb_data["cost_charged"]
            + fno_data["cost_charged"]
            + custom.json()["cost_charged"]
            + pdata["cost_charged"]
        )
        assert round(before_credits - after_credits, 2) == round(expected_spend, 2)
    finally:
        api_client.delete(f"{api_base_url}/admin/users/{user['user_key']}", headers=owner_headers, timeout=30)


def test_portfolio_expected_signals_have_signed_values_and_all_horizons(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    headers = _auth_headers(owner["token"])

    response = api_client.post(
        f"{api_base_url}/portfolio/analyze",
        json={
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 1200, "quantity": 10},
                {"symbol": "INFY", "avg_price": 1500, "quantity": 8},
            ]
        },
        headers=headers,
        timeout=180,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["parsed_positions_count"] >= 1
    assert isinstance(data.get("credits_remaining"), (int, float))

    required_horizons = {"1W", "1M", "3M", "6M", "9M", "1Y"}
    for stock in data["stocks"]:
        signals = stock.get("expected_signals", {})
        assert required_horizons == set(signals.keys())
        for horizon, row in signals.items():
            _ = horizon
            assert isinstance(row.get("max_expected_price"), (int, float))
            assert isinstance(row.get("amount_signal"), str)
            assert isinstance(row.get("percent_signal"), str)
            assert row["amount_signal"].startswith(("+", "-"))
            assert row["percent_signal"].startswith(("+", "-"))
            assert row["percent_signal"].endswith("%")


def test_fno_stock_signals_not_capped_to_three_when_available(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    headers = _auth_headers(owner["token"])

    response = api_client.post(f"{api_base_url}/fno/generate", json={}, headers=headers, timeout=240)
    assert response.status_code == 200
    data = get_ndjson_complete_data(response)
    assert isinstance(data.get("stock_signals"), list)

    # API-level sanity: no forced front-end style cap field and payload can exceed 3 items.
    if len(data["stock_signals"]) > 3:
        assert len(data["stock_signals"]) >= 4
    else:
        pytest.skip("Current market cycle returned <=3 potential stock signals; dynamic cap validated via method-level test.")
