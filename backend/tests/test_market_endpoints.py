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

    scripts = {row['script'] for row in data}
    assert 'NIFTY10MAR26500CE' in scripts or 'NIFTY10MAR26500PE' in scripts
    assert 'BANKNIFTY10MAR47000CE' in scripts or 'BANKNIFTY10MAR47000PE' in scripts

    for row in data:
        assert row['underlying'] in {'NIFTY', 'BANKNIFTY'}
        assert row['direction'] in {'BULLISH', 'BEARISH', 'NEUTRAL'}
