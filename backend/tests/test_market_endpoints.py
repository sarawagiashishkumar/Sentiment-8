import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

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

    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 30
    assert len(data) > 0

    first = data[0]
    assert isinstance(first.get('symbol'), str)
    assert isinstance(first.get('company_name'), str)
    assert isinstance(first.get('multibagger_score'), int)

    scores = [row['multibagger_score'] for row in data]
    assert scores == sorted(scores, reverse=True)


def test_fno_contracts_returns_hardcoded_contracts(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/fno/contracts', timeout=30)
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
    assert response.status_code == 200

    data = response.json()
    assert data['script'] == script
    assert data['underlying'] == 'NIFTY'
    assert data['option_type'] == 'PE'
    assert data['direction'] in {'BULLISH', 'BEARISH', 'NEUTRAL'}
    assert isinstance(data['option_ltp'], (float, int)) and data['option_ltp'] > 0


def test_fno_signal_banknifty_supported_script(session_client, api_base_url):
    script = 'BANKNIFTY10MAR47000CE'
    response = session_client.get(f'{api_base_url}/fno/signal/{script}', timeout=90)
    assert response.status_code == 200

    data = response.json()
    assert data['script'] == script
    assert data['underlying'] == 'BANKNIFTY'
    assert data['option_type'] == 'CE'
    assert data['direction'] in {'BULLISH', 'BEARISH', 'NEUTRAL'}
    assert isinstance(data['option_ltp'], (float, int)) and data['option_ltp'] > 0


def test_fno_signals_index_cards(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/fno/signals/index', timeout=120)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    underlyings = {row['underlying'] for row in data}
    assert 'NIFTY' in underlyings
    assert 'BANKNIFTY' in underlyings

    for row in data:
        assert row['underlying'] in {'NIFTY', 'BANKNIFTY'}
        assert row['direction'] in {'BULLISH', 'BEARISH', 'NEUTRAL'}
        assert row['strategy'] in {'Assured Directional Projection', 'Directional Projection (Low Confidence)'}


def test_fno_potential_signals_shape_and_actionability(session_client, api_base_url):
    response = session_client.get(f'{api_base_url}/fno/signals/potential', timeout=120)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    for row in data:
        assert 'confluence_score' in row
        assert 'is_potential_trade' in row
        assert row['direction'] in {'BULLISH', 'BEARISH', 'NEUTRAL'}


def test_fno_custom_signal_dynamic_script_parse(session_client, api_base_url):
    script = 'NIFTY10MAR24050PE'
    response = session_client.get(f'{api_base_url}/fno/signal/{script}', timeout=90)
    assert response.status_code == 200
    data = response.json()
    assert data['script'] == script
    assert data['underlying'] == 'NIFTY'


def test_custom_script_refresh_nonce_returns_fresh_timestamp(session_client, api_base_url):
    script = 'NIFTY10MAR26500PE'
    first = session_client.get(
        f'{api_base_url}/fno/signal/{script}',
        params={'refresh_nonce': 'pytest-run-1'},
        timeout=90,
    )
    second = session_client.get(
        f'{api_base_url}/fno/signal/{script}',
        params={'refresh_nonce': 'pytest-run-2'},
        timeout=90,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_data = first.json()
    second_data = second.json()
    assert first_data['analysis_refreshed_at'] != second_data['analysis_refreshed_at']


def test_multibagger_rows_include_tier_and_potential_flags(session_client, api_base_url):
    response = session_client.get(
        f'{api_base_url}/multibagger/candidates',
        params={'refresh_nonce': 'pytest-multi-refresh'},
        timeout=120,
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert 'tier_pass_count' in first
    assert 'is_potential_multibagger' in first
    assert isinstance(first['tier_pass_count'], int)
    assert isinstance(first['is_potential_multibagger'], bool)
