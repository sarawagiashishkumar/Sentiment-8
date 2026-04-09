import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from tests.helpers.test_utils import get_ndjson_complete_data, safe_streaming_post

load_dotenv(Path("/app/frontend/.env"))
BASE_URL = "http://localhost:8001"

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


def _login(client: requests.Session, api_base_url: str, username: str) -> dict:
    response = client.post(f"{api_base_url}/auth/access", json={"username": username}, timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert "token" in data and isinstance(data["token"], str) and data["token"]
    return data


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_auth_me_reflects_owner_role_and_admin_exemption(api_client, api_base_url):
    login = _login(api_client, api_base_url, OWNER_USERNAME)
    me = api_client.get(f"{api_base_url}/auth/me", headers=_auth_headers(login["token"]), timeout=30)
    assert me.status_code == 200
    data = me.json()
    assert data["role"] == "owner"
    assert data["admin_exempt"] is True
    assert data["username"] == OWNER_USERNAME


def test_owner_generation_is_credit_exempt(api_client, api_base_url):
    login = _login(api_client, api_base_url, OWNER_USERNAME)
    headers = _auth_headers(login["token"])
    before = api_client.get(f"{api_base_url}/auth/me", headers=headers, timeout=30).json()["credits"]

    mb = safe_streaming_post(f"{api_base_url}/multibagger/generate", json_body={}, headers=headers)
    assert mb.status_code == 200
    mb_data = get_ndjson_complete_data(mb)
    assert mb_data["cost_charged"] == 0

    fno = safe_streaming_post(f"{api_base_url}/fno/generate", json_body={}, headers=headers)
    assert fno.status_code == 200
    fno_data = get_ndjson_complete_data(fno)
    assert fno_data["cost_charged"] == 0

    after = api_client.get(f"{api_base_url}/auth/me", headers=headers, timeout=30).json()["credits"]
    assert before == after


def test_admin_user_crud_create_update_delete_with_username(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner["token"])

    temp_username = f"user{uuid.uuid4().hex[:8]}1"
    create = api_client.post(
        f"{api_base_url}/admin/users",
        json={"username": temp_username, "role": "user", "initial_credits": 5},
        headers=owner_headers,
        timeout=30,
    )
    assert create.status_code == 200
    created = create.json()
    assert created["username"] == temp_username
    assert created["role"] == "user"
    assert created["credits"] == 5

    update = api_client.patch(
        f"{api_base_url}/admin/users/{created['user_key']}/credits",
        json={"credits": 9},
        headers=owner_headers,
        timeout=30,
    )
    assert update.status_code == 200
    assert update.json()["credits"] == 9

    user_login = _login(api_client, api_base_url, temp_username)
    user_me = api_client.get(
        f"{api_base_url}/auth/me",
        headers=_auth_headers(user_login["token"]),
        timeout=30,
    )
    assert user_me.status_code == 200
    assert user_me.json()["credits"] == 9

    delete = api_client.delete(
        f"{api_base_url}/admin/users/{created['user_key']}",
        headers=owner_headers,
        timeout=30,
    )
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True


def test_sub_admin_quota_enforcement(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner["token"])

    sub_username = f"sub{uuid.uuid4().hex[:7]}1"
    sub_create = api_client.post(
        f"{api_base_url}/admin/users",
        json={"username": sub_username, "role": "sub_admin", "initial_credits": 0, "quota_limit": 1},
        headers=owner_headers,
        timeout=30,
    )
    assert sub_create.status_code == 200
    sub_user_key = sub_create.json()["user_key"]

    try:
        sub_login = _login(api_client, api_base_url, sub_username)
        sub_headers = _auth_headers(sub_login["token"])

        first_user = f"u{uuid.uuid4().hex[:8]}1"
        first_create = api_client.post(
            f"{api_base_url}/admin/users",
            json={"username": first_user, "role": "user", "initial_credits": 1},
            headers=sub_headers,
            timeout=30,
        )
        assert first_create.status_code == 200

        second_user = f"u{uuid.uuid4().hex[:8]}2"
        second_create = api_client.post(
            f"{api_base_url}/admin/users",
            json={"username": second_user, "role": "user", "initial_credits": 1},
            headers=sub_headers,
            timeout=30,
        )
        assert second_create.status_code == 403
        assert "quota" in second_create.json().get("detail", "").lower()
    finally:
        api_client.delete(f"{api_base_url}/admin/users/{sub_user_key}", headers=owner_headers, timeout=30)


def test_basic_user_credit_deduction_and_insufficient_flow(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner["token"])

    username = f"basic{uuid.uuid4().hex[:8]}1"
    create = api_client.post(
        f"{api_base_url}/admin/users",
        json={"username": username, "role": "user", "initial_credits": 2},
        headers=owner_headers,
        timeout=30,
    )
    assert create.status_code == 200
    user_key = create.json()["user_key"]

    try:
        user_login = _login(api_client, api_base_url, username)
        user_headers = _auth_headers(user_login["token"])

        fno_ok = safe_streaming_post(f"{api_base_url}/fno/generate", json_body={}, headers=user_headers)
        assert fno_ok.status_code == 200
        fno_ok_data = get_ndjson_complete_data(fno_ok)
        assert fno_ok_data["cost_charged"] == 2
        assert fno_ok_data["credits_remaining"] == 0

        fno_fail = safe_streaming_post(f"{api_base_url}/fno/generate", json_body={}, headers=user_headers)
        assert fno_fail.status_code == 402
        assert "Insufficient credits" in fno_fail.json().get("detail", "")
    finally:
        api_client.delete(f"{api_base_url}/admin/users/{user_key}", headers=owner_headers, timeout=30)
