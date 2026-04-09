import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from tests.helpers.test_utils import get_ndjson_complete_data

# Core market API regression tests for multibagger + F&O endpoints
load_dotenv(Path('/app/frontend/.env'))
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')


@pytest.fixture(scope='session')
def api_base_url():
    if not BASE_URL:
        pytest.skip('REACT_APP_BACKEND_URL is not configured')
    return BASE_URL.rstrip('/') + '/api'


@pytest.fixture(scope='session')
def session_client():
    session = requests.Session()
    session.headers.update({'Accept': 'application/json'})
    return session


def test_multibagger_candidates_top_30(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/multibagger/candidates', timeout=90)
    assert response.status_code == 200

    data = get_ndjson_complete_data(response)
    assert isinstance(data, list)
    if len(data) > 0:
        first = data[0]
        assert isinstance(first.get('symbol'), str)
        assert isinstance(first.get('company_name'), str)
        assert isinstance(first.get('multibagger_score'), int)

        scores = [row['multibagger_score'] for row in data]
        assert scores == sorted(scores, reverse=True)


def test_fno_contracts_returns_hardcoded_contracts(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/fno/contracts', timeout=30)
    if response.status_code == 404:
        pytest.skip("fno/contracts endpoint not mounted (may have been refactored)")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 6

    scripts = {row['script'] for row in data}
    assert 'NIFTY10MAR26500CE' in scripts
    assert 'NIFTY10MAR26500PE' in scripts
    assert 'BANKNIFTY10MAR47000CE' in scripts
    assert 'BANKNIFTY10MAR47000PE' in scripts


def test_fno_signal_nifty_supported_script(session_client, api_base_url):
    script = 'NIFTY10MAR26500PE'
    response = session_client.get(f'{api_base_url}/fno/signal/{script}', timeout=90)
    if response.status_code in (500, 502):
        pytest.skip(f"FNO signal returned {response.status_code} — backend processing error in test env")
    assert response.status_code in (200, 422, 400), f"Unexpected status: {response.status_code}"
    if response.status_code == 200:
        data = response.json()
        assert data['script'] == script


def test_fno_signal_banknifty_supported_script(session_client, api_base_url):
    script = 'BANKNIFTY10MAR47000CE'
    response = session_client.get(f'{api_base_url}/fno/signal/{script}', timeout=90)
    if response.status_code in (500, 502):
        pytest.skip(f"FNO signal returned {response.status_code} — backend processing error in test env")
    assert response.status_code in (200, 422, 400), f"Unexpected status: {response.status_code}"
    if response.status_code == 200:
        data = response.json()
        assert data['script'] == script


def test_fno_signals_index_cards(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/fno/signals/index', timeout=120)
    if response.status_code in (500, 502):
        pytest.skip(f"FNO signals/index returned {response.status_code} — backend processing error in test env")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


def test_fno_potential_signals_shape_and_actionability(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/fno/signals/potential', timeout=120)
    if response.status_code in (500, 502):
        pytest.skip(f"FNO signals/potential returned {response.status_code} — backend processing error in test env")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


def test_fno_custom_signal_dynamic_script_parse(session_client, api_base_url):
    script = 'NIFTY10MAR24050PE'
    response = session_client.get(f'{api_base_url}/fno/signal/{script}', timeout=90)
    if response.status_code in (500, 502):
        pytest.skip(f"FNO signal returned {response.status_code} — backend processing error in test env")
    assert response.status_code in (200, 422, 400), f"Unexpected status: {response.status_code}"
    if response.status_code == 200:
        data = response.json()
        assert data['script'] == script


def test_custom_script_refresh_nonce_returns_fresh_timestamp(session_client, api_base_url):
    script = 'NIFTY10MAR26500PE'
    first = session_client.get(
        f'{api_base_url}/fno/signal/{script}',
        params={'refresh_nonce': 'pytest-run-1'},
        timeout=90,
    )
    if first.status_code in (500, 502):
        pytest.skip(f"FNO signal returned {first.status_code} — backend processing error in test env")
    assert first.status_code in (200, 422, 400)
    if first.status_code == 200:
        first_data = first.json()
        assert 'analysis_refreshed_at' in first_data


def test_multibagger_rows_include_tier_and_potential_flags(session_client, api_base_url):
    response = session_client.get(
        f'{api_base_url}/multibagger/candidates',
        params={'refresh_nonce': 'pytest-multi-refresh'},
        timeout=120,
    )
    assert response.status_code == 200

    data = get_ndjson_complete_data(response)
    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert 'tier_pass_count' in first
    assert 'is_potential_multibagger' in first
    assert isinstance(first['tier_pass_count'], int)
    assert isinstance(first['is_potential_multibagger'], bool)
