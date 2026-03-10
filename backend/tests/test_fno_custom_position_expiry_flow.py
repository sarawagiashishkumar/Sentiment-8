import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Regression tests for expiry-aware F&O responses and sticky custom-position lifecycle
load_dotenv(Path('/app/frontend/.env'))
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')
OWNER_USERNAME = '@shish123'


@pytest.fixture(scope='session')
def api_base_url():
    if not BASE_URL:
        pytest.skip('REACT_APP_BACKEND_URL is not configured')
    return BASE_URL.rstrip('/') + '/api'


@pytest.fixture(scope='session')
def api_client():
    session = requests.Session()
    session.headers.update({'Accept': 'application/json', 'Content-Type': 'application/json'})
    return session


def _auth_headers(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


def _login(client: requests.Session, api_base_url: str, username: str) -> dict:
    response = client.post(f'{api_base_url}/auth/access', json={'username': username}, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get('token'), str) and payload['token']
    return payload


def _create_basic_user(client: requests.Session, api_base_url: str, owner_headers: dict, initial_credits: int = 6):
    username = f'pos{uuid.uuid4().hex[:8]}1'
    response = client.post(
        f'{api_base_url}/admin/users',
        json={'username': username, 'role': 'user', 'initial_credits': initial_credits},
        headers=owner_headers,
        timeout=30,
    )
    assert response.status_code == 200
    return response.json()


def test_fno_generate_dynamic_script_parse_not_supported_regression(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    response = api_client.post(
        f'{api_base_url}/fno/generate',
        json={'custom_script': 'NIFTY10MAR24050PE'},
        headers=_auth_headers(owner['token']),
        timeout=240,
    )

    if response.status_code == 200:
        data = response.json()
        assert data['custom_signal'] is not None
        signal = data['custom_signal']
        assert isinstance(signal['minutes_to_expiry'], int)
        assert signal['expiry_risk'] in {'LOW', 'MEDIUM', 'HIGH'}
        assert isinstance(data['top_trades'], list)
        assert len(data['top_trades']) <= 4
        return

    assert response.status_code == 400
    detail = response.json().get('detail', '')
    assert 'Script not supported' not in detail
    assert 'expiry' in detail.lower() or 'time' in detail.lower()


def test_custom_position_create_list_close_credit_deduction_and_alerts(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner['token'])
    basic_user = _create_basic_user(api_client, api_base_url, owner_headers, initial_credits=6)
    basic_user_key = basic_user['user_key']

    try:
        basic_login = _login(api_client, api_base_url, basic_user['username'])
        user_headers = _auth_headers(basic_login['token'])

        before_credits = api_client.get(f'{api_base_url}/auth/me', headers=user_headers, timeout=30).json()['credits']

        create = api_client.post(
            f'{api_base_url}/fno/custom-position',
            json={'script': 'NIFTY', 'buy_price': 999999},
            headers=user_headers,
            timeout=120,
        )
        assert create.status_code == 200
        created = create.json()
        position_id = created['position']['id']
        assert created['cost_charged'] == 1
        assert created['position']['status'] == 'OPEN'
        assert isinstance(created['position']['minutes_to_expiry'], int)
        assert created['position']['minutes_to_expiry'] > 0

        after_credits = api_client.get(f'{api_base_url}/auth/me', headers=user_headers, timeout=30).json()['credits']
        assert before_credits - after_credits == 1

        # Poll list endpoint to validate sticky projection lifecycle + urgent alert behavior
        listed_row = None
        for _ in range(3):
            listing = api_client.get(f'{api_base_url}/fno/custom-positions', headers=user_headers, timeout=120)
            assert listing.status_code == 200
            rows = listing.json()
            listed_row = next((row for row in rows if row['id'] == position_id), None)
            if listed_row and listed_row.get('alert') == 'EXIT_URGENT_LOSS':
                break

        assert listed_row is not None
        assert isinstance(listed_row['minutes_to_expiry'], int)
        assert isinstance(listed_row['revised_exit_plan'], str)
        assert 'latest_option_ltp' in listed_row
        assert listed_row.get('alert') in {None, 'EXIT_URGENT_TIME', 'EXIT_URGENT_LOSS', 'RISKY_PREMIUM'}
        assert listed_row.get('alert') == 'EXIT_URGENT_LOSS'

        close = api_client.post(
            f'{api_base_url}/fno/custom-position/{position_id}/close',
            json={},
            headers=user_headers,
            timeout=30,
        )
        assert close.status_code == 200
        assert close.json()['closed'] is True

        final_listing = api_client.get(f'{api_base_url}/fno/custom-positions', headers=user_headers, timeout=120)
        assert final_listing.status_code == 200
        assert all(row['id'] != position_id for row in final_listing.json())
    finally:
        api_client.delete(f'{api_base_url}/admin/users/{basic_user_key}', headers=owner_headers, timeout=30)
