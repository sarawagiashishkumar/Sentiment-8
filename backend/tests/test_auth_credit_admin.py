import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Auth, credit consumption, and admin CRUD regression tests for protected dashboard flows
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


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


def _login(client: requests.Session, api_base_url: str, password: str) -> dict:
    response = client.post(f"{api_base_url}/auth/access", json={"password": password}, timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert "token" in data and isinstance(data["token"], str) and data["token"]
    return data


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_auth_me_reflects_admin_role_and_credits(api_client, api_base_url):
    login = _login(api_client, api_base_url, "owner123")

    me = api_client.get(f"{api_base_url}/auth/me", headers=_auth_headers(login["token"]), timeout=30)
    assert me.status_code == 200

    data = me.json()
    assert data["role"] == "admin"
    assert isinstance(data["credits"], int)
    assert data["credits"] >= 0
    assert data["user_key"] == login["user_key"]


def test_auth_me_reflects_sample_user_role_and_credits(api_client, api_base_url):
    login = _login(api_client, api_base_url, "userabc1")

    me = api_client.get(f"{api_base_url}/auth/me", headers=_auth_headers(login["token"]), timeout=30)
    assert me.status_code == 200

    data = me.json()
    assert data["role"] == "user"
    assert isinstance(data["credits"], int)
    assert data["credits"] >= 0
    assert data["user_key"] == login["user_key"]


def test_multibagger_generate_charges_one_credit(api_client, api_base_url):
    login = _login(api_client, api_base_url, "owner123")
    headers = _auth_headers(login["token"])

    me_before = api_client.get(f"{api_base_url}/auth/me", headers=headers, timeout=30)
    assert me_before.status_code == 200
    credits_before = me_before.json()["credits"]

    response = api_client.post(f"{api_base_url}/multibagger/generate", json={}, headers=headers, timeout=120)
    assert response.status_code == 200

    data = response.json()
    assert data["cost_charged"] == 1
    assert data["credits_remaining"] == credits_before - 1
    assert isinstance(data["candidates"], list)
    assert isinstance(data["potential_count"], int)


def test_fno_generate_charges_two_credits_and_top4(api_client, api_base_url):
    login = _login(api_client, api_base_url, "owner123")
    headers = _auth_headers(login["token"])

    me_before = api_client.get(f"{api_base_url}/auth/me", headers=headers, timeout=30)
    assert me_before.status_code == 200
    credits_before = me_before.json()["credits"]

    response = api_client.post(f"{api_base_url}/fno/generate", json={}, headers=headers, timeout=150)
    assert response.status_code == 200

    data = response.json()
    assert data["cost_charged"] == 2
    assert data["credits_remaining"] == credits_before - 2
    assert isinstance(data["signals"], list)
    assert isinstance(data["top_trades"], list)
    assert len(data["top_trades"]) <= 4


def test_admin_user_crud_create_list_update_delete(api_client, api_base_url):
    admin = _login(api_client, api_base_url, "owner123")
    admin_headers = _auth_headers(admin["token"])

    temp_password = f"T{uuid.uuid4().hex[:9]}"
    create = api_client.post(
        f"{api_base_url}/admin/users",
        json={"password": temp_password, "initial_credits": 3},
        headers=admin_headers,
        timeout=30,
    )
    assert create.status_code == 200
    created = create.json()
    assert created["role"] == "user"
    assert created["credits"] == 3
    user_key = created["user_key"]

    listed = api_client.get(f"{api_base_url}/admin/users", headers=admin_headers, timeout=30)
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["user_key"] == user_key for row in rows)

    updated = api_client.patch(
        f"{api_base_url}/admin/users/{user_key}/credits",
        json={"credits": 7},
        headers=admin_headers,
        timeout=30,
    )
    assert updated.status_code == 200
    updated_data = updated.json()
    assert updated_data["user_key"] == user_key
    assert updated_data["credits"] == 7

    user_login = _login(api_client, api_base_url, temp_password)
    me = api_client.get(
        f"{api_base_url}/auth/me",
        headers=_auth_headers(user_login["token"]),
        timeout=30,
    )
    assert me.status_code == 200
    assert me.json()["credits"] == 7

    deleted = api_client.delete(f"{api_base_url}/admin/users/{user_key}", headers=admin_headers, timeout=30)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    listed_after = api_client.get(f"{api_base_url}/admin/users", headers=admin_headers, timeout=30)
    assert listed_after.status_code == 200
    assert all(row["user_key"] != user_key for row in listed_after.json())


def test_insufficient_credit_flow_returns_402(api_client, api_base_url):
    admin = _login(api_client, api_base_url, "owner123")
    admin_headers = _auth_headers(admin["token"])

    temp_password = f"T{uuid.uuid4().hex[:9]}"
    create = api_client.post(
        f"{api_base_url}/admin/users",
        json={"password": temp_password, "initial_credits": 1},
        headers=admin_headers,
        timeout=30,
    )
    assert create.status_code == 200
    user_key = create.json()["user_key"]

    try:
        user = _login(api_client, api_base_url, temp_password)
        fail_generate = api_client.post(
            f"{api_base_url}/fno/generate",
            json={},
            headers=_auth_headers(user["token"]),
            timeout=120,
        )
        assert fail_generate.status_code == 402
        detail = fail_generate.json().get("detail", "")
        assert "Insufficient credits" in detail
    finally:
        api_client.delete(f"{api_base_url}/admin/users/{user_key}", headers=admin_headers, timeout=30)
