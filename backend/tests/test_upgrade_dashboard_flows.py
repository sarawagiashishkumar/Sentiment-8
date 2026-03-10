import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Regression tests for upgraded trading dashboard flows: username auth, RBAC/quota, credits, multibagger and F&O generation
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


@pytest.fixture
def created_users():
    users = []
    yield users


@pytest.fixture(autouse=True)
def cleanup_created_users(api_client, api_base_url, created_users):
    yield
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    headers = _auth_headers(owner['token'])
    for user_key in reversed(created_users):
        try:
            api_client.delete(f'{api_base_url}/admin/users/{user_key}', headers=headers, timeout=30)
        except Exception:
            pass


def _auth_headers(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


def _login(client: requests.Session, api_base_url: str, username: str) -> dict:
    response = client.post(f'{api_base_url}/auth/access', json={'username': username}, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get('token'), str) and payload['token']
    return payload


def _create_user(client: requests.Session, api_base_url: str, owner_headers: dict, created_users: list[str], **kwargs) -> dict:
    response = client.post(f'{api_base_url}/admin/users', json=kwargs, headers=owner_headers, timeout=30)
    assert response.status_code == 200
    user = response.json()
    created_users.append(user['user_key'])
    return user


def test_login_username_owner_me_reflects_admin_exempt(api_client, api_base_url):
    login = _login(api_client, api_base_url, OWNER_USERNAME)
    me = api_client.get(f'{api_base_url}/auth/me', headers=_auth_headers(login['token']), timeout=30)
    assert me.status_code == 200
    data = me.json()
    assert data['username'] == OWNER_USERNAME
    assert data['role'] == 'owner'
    assert data['admin_exempt'] is True


def test_scripts_search_returns_suggestions_for_nifty(api_client, api_base_url):
    response = api_client.get(f'{api_base_url}/fno/scripts/search', params={'q': 'NIFTY10MAR'}, timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert data['query'] == 'NIFTY10MAR'
    assert isinstance(data['suggestions'], list)
    assert any(item.startswith('NIFTY10MAR') for item in data['suggestions'])


def test_multibagger_generate_has_rsi_gtt_and_duration_targets(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    response = api_client.post(
        f'{api_base_url}/multibagger/generate',
        json={},
        headers=_auth_headers(owner['token']),
        timeout=180,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data['candidates'], list) and len(data['candidates']) > 0

    first = data['candidates'][0]
    assert 'current_rsi_level' in first
    assert 'gtt_buy_price' in first
    assert isinstance(first['targeted_upside_price'], dict)
    assert isinstance(first['targeted_upside_profit_pct'], dict)
    for duration in ['1W', '1M', '3M', '6M', '9M', '1Y']:
        assert duration in first['targeted_upside_price']
        assert duration in first['targeted_upside_profit_pct']


def test_fno_generate_returns_dual_pane_reports_top4_and_stock_panel(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    response = api_client.post(
        f'{api_base_url}/fno/generate',
        json={},
        headers=_auth_headers(owner['token']),
        timeout=240,
    )
    assert response.status_code == 200
    data = response.json()

    assert 'nifty_projection' in data and 'banknifty_projection' in data
    nifty = data['nifty_projection']
    bank = data['banknifty_projection']

    assert nifty['index_name'] == 'NIFTY'
    assert bank['index_name'] == 'BANKNIFTY'
    assert nifty['strike_range_max'] - nifty['strike_range_min'] == 1000
    assert bank['strike_range_max'] - bank['strike_range_min'] == 1000

    assert 'with_consolidated_report' in nifty
    assert 'without_consolidated_report' in nifty
    assert 'with_consolidated_report' in bank
    assert 'without_consolidated_report' in bank

    assert isinstance(data['top_trades'], list)
    assert len(data['top_trades']) <= 4
    assert isinstance(data.get('stock_signals', []), list)
    assert all(row['underlying'] not in {'NIFTY', 'BANKNIFTY'} for row in data.get('stock_signals', []))


def test_custom_script_dynamic_parse_does_not_return_not_supported(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    script = 'NIFTY10MAR24050PE'
    response = api_client.post(
        f'{api_base_url}/fno/generate',
        json={'custom_script': script},
        headers=_auth_headers(owner['token']),
        timeout=240,
    )
    assert response.status_code == 200
    data = response.json()
    assert data['custom_signal'] is not None
    assert data['custom_signal']['script'] == script


def test_sub_admin_quota_enforced_for_user_creation(api_client, api_base_url, created_users):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner['token'])

    sub_username = f'sub{uuid.uuid4().hex[:7]}1'
    sub = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        created_users,
        username=sub_username,
        role='sub_admin',
        initial_credits=0,
        quota_limit=1,
    )

    sub_login = _login(api_client, api_base_url, sub['username'])
    sub_headers = _auth_headers(sub_login['token'])

    first_username = f'u{uuid.uuid4().hex[:8]}1'
    first = api_client.post(
        f'{api_base_url}/admin/users',
        json={'username': first_username, 'role': 'user', 'initial_credits': 1},
        headers=sub_headers,
        timeout=30,
    )
    assert first.status_code == 200
    created_users.append(first.json()['user_key'])

    second_username = f'u{uuid.uuid4().hex[:8]}2'
    second = api_client.post(
        f'{api_base_url}/admin/users',
        json={'username': second_username, 'role': 'user', 'initial_credits': 1},
        headers=sub_headers,
        timeout=30,
    )
    assert second.status_code == 403
    assert 'quota' in second.json().get('detail', '').lower()


def test_credits_deduct_for_basic_user_but_not_for_owner_or_sub_admin(api_client, api_base_url, created_users):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner['token'])

    basic_username = f'basic{uuid.uuid4().hex[:8]}1'
    sub_username = f'sub{uuid.uuid4().hex[:7]}2'

    basic_user = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        created_users,
        username=basic_username,
        role='user',
        initial_credits=3,
    )
    sub_user = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        created_users,
        username=sub_username,
        role='sub_admin',
        initial_credits=0,
        quota_limit=2,
    )

    basic_login = _login(api_client, api_base_url, basic_user['username'])
    sub_login = _login(api_client, api_base_url, sub_user['username'])

    basic_headers = _auth_headers(basic_login['token'])
    sub_headers = _auth_headers(sub_login['token'])

    basic_before = api_client.get(f'{api_base_url}/auth/me', headers=basic_headers, timeout=30).json()['credits']
    sub_before = api_client.get(f'{api_base_url}/auth/me', headers=sub_headers, timeout=30).json()['credits']

    mb_basic = api_client.post(f'{api_base_url}/multibagger/generate', json={}, headers=basic_headers, timeout=180)
    mb_sub = api_client.post(f'{api_base_url}/multibagger/generate', json={}, headers=sub_headers, timeout=180)
    assert mb_basic.status_code == 200
    assert mb_sub.status_code == 200

    basic_after = api_client.get(f'{api_base_url}/auth/me', headers=basic_headers, timeout=30).json()['credits']
    sub_after = api_client.get(f'{api_base_url}/auth/me', headers=sub_headers, timeout=30).json()['credits']

    assert basic_before - basic_after == 2
    assert sub_before == sub_after


def test_custom_position_create_list_close_and_alert_fields(api_client, api_base_url, created_users):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner['token'])

    username = f'pos{uuid.uuid4().hex[:8]}1'
    user = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        created_users,
        username=username,
        role='user',
        initial_credits=5,
    )

    login = _login(api_client, api_base_url, user['username'])
    user_headers = _auth_headers(login['token'])

    create = api_client.post(
        f'{api_base_url}/fno/custom-position',
        json={'script': 'NIFTY', 'buy_price': 120.5},
        headers=user_headers,
        timeout=120,
    )
    assert create.status_code == 200
    payload = create.json()
    assert payload['cost_charged'] == 1
    assert payload['position']['status'] == 'OPEN'
    assert payload['position']['minutes_to_expiry'] > 0
    position_id = payload['position']['id']

    listing = api_client.get(f'{api_base_url}/fno/custom-positions', headers=user_headers, timeout=120)
    assert listing.status_code == 200
    rows = listing.json()
    assert any(row['id'] == position_id for row in rows)

    close = api_client.post(
        f'{api_base_url}/fno/custom-position/{position_id}/close',
        json={},
        headers=user_headers,
        timeout=30,
    )
    assert close.status_code == 200
    assert close.json()['closed'] is True


def test_fno_signal_has_expiry_risk_and_minutes_to_expiry(api_client, api_base_url):
    response = api_client.get(f'{api_base_url}/fno/signal/NIFTY10MAR26500PE', timeout=120)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data['minutes_to_expiry'], int)
    assert data['expiry_risk'] in {'LOW', 'MEDIUM', 'HIGH'}


def test_portfolio_manual_analysis_returns_expected_ranges(api_client, api_base_url, created_users):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner['token'])

    username = f'port{uuid.uuid4().hex[:8]}1'
    user = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        created_users,
        username=username,
        role='user',
        initial_credits=5,
    )
    login = _login(api_client, api_base_url, user['username'])
    headers = _auth_headers(login['token'])

    response = api_client.post(
        f'{api_base_url}/portfolio/analyze',
        json={
            'positions': [
                {'symbol': 'RELIANCE', 'avg_price': 1200, 'quantity': 10},
                {'symbol': 'TCS', 'avg_price': 3000, 'quantity': 5},
            ]
        },
        headers=headers,
        timeout=180,
    )
    assert response.status_code == 200
    data = response.json()
    assert data['parsed_positions_count'] >= 1
    first = data['stocks'][0]
    assert 'expected_ranges' in first
    for horizon in ['1W', '1M', '3M', '6M', '9M', '1Y']:
        assert horizon in first['expected_ranges']


def test_portfolio_upload_csv_analysis(api_client, api_base_url, created_users):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    owner_headers = _auth_headers(owner['token'])

    username = f'port{uuid.uuid4().hex[:8]}2'
    user = _create_user(
        api_client,
        api_base_url,
        owner_headers,
        created_users,
        username=username,
        role='user',
        initial_credits=5,
    )
    login = _login(api_client, api_base_url, user['username'])
    headers = _auth_headers(login['token'])

    csv_content = 'Symbol,Average_Price,Quantity\nRELIANCE,1200,10\nINFY,1500,8\n'
    files = {'file': ('Holding(1).csv', csv_content, 'text/csv')}
    response = requests.post(
        f'{api_base_url}/portfolio/analyze-upload',
        files=files,
        headers={'Authorization': headers['Authorization']},
        timeout=180,
    )
    assert response.status_code == 200
    data = response.json()
    assert data['parsed_positions_count'] >= 1
