import io
import os
import asyncio
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest
import requests
from dotenv import load_dotenv


# Regression coverage for structured upgrade: portfolio manual/upload parsing + dynamic stock F&O result sizing
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


def test_portfolio_manual_has_all_required_horizons(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    headers = _auth_headers(owner["token"])

    response = api_client.post(
        f"{api_base_url}/portfolio/analyze",
        json={
            "positions": [
                {"symbol": "RELIANCE", "avg_price": 1200, "quantity": 10},
                {"symbol": "TCS", "avg_price": 3000, "quantity": 3},
            ]
        },
        headers=headers,
        timeout=180,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["parsed_positions_count"] >= 1
    expected_horizons = {"1W", "1M", "3M", "6M", "9M", "1Y"}
    for stock in data["stocks"]:
        assert expected_horizons == set(stock.get("expected_ranges", {}).keys())


def test_portfolio_upload_txt_with_flexible_headers(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    auth_header = {"Authorization": f"Bearer {owner['token']}"}

    txt_content = "stock,buy price,shares\nINFY,1500,8\nITC,400,20\n"
    files = {"file": ("portfolio.txt", txt_content, "text/plain")}
    response = requests.post(
        f"{api_base_url}/portfolio/analyze-upload",
        files=files,
        headers=auth_header,
        timeout=180,
    )
    assert response.status_code == 200

    data = response.json()
    symbols = {row["symbol"] for row in data["stocks"]}
    assert "INFY" in symbols
    assert "ITC" in symbols


def test_portfolio_upload_xlsx_with_alias_headers(api_client, api_base_url):
    owner = _login(api_client, api_base_url, OWNER_USERNAME)
    auth_header = {"Authorization": f"Bearer {owner['token']}"}

    frame = pd.DataFrame(
        [
            {"Instrument": "SBIN", "Buy Price": 650, "Units": 10},
            {"Instrument": "AXISBANK", "Buy Price": 1200, "Units": 4},
        ]
    )
    xlsx_stream = io.BytesIO()
    frame.to_excel(xlsx_stream, index=False)
    xlsx_stream.seek(0)

    files = {
        "file": (
            "holdings.xlsx",
            xlsx_stream.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = requests.post(
        f"{api_base_url}/portfolio/analyze-upload",
        files=files,
        headers=auth_header,
        timeout=180,
    )
    assert response.status_code == 200

    data = response.json()
    symbols = {row["symbol"] for row in data["stocks"]}
    assert "SBIN" in symbols
    assert "AXISBANK" in symbols


def test_stock_signal_builder_is_not_hard_capped_to_three(monkeypatch):
    if "/app/backend" not in sys.path:
        sys.path.append("/app/backend")
    spec = importlib.util.spec_from_file_location("server", "/app/backend/server.py")
    server = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(server)

    class DummySignal:
        def __init__(self, script: str, score: int):
            self.script = script
            self.confluence_score = score
            self.is_potential_trade = True

    async def fake_get_stock_core(symbol):
        return {
            "symbol": symbol,
            "company_name": symbol,
            "ltp": 1000,
            "open": 990,
            "high": 1010,
            "low": 970,
            "prev_close": 980,
            "year_high": 1200,
            "year_low": 800,
            "volume": 500000,
            "market_cap": 100000,
            "pe_ratio": 20,
            "book_value": 300,
            "eps": 50,
            "sector": "TEST",
        }

    async def fake_build_contract(symbol, strike, option_type):
        return {"symbol": symbol, "strike": strike, "option_type": option_type}

    async def fake_safe_signal(contract, refreshed_at, sem):
        return DummySignal(
            script=f"{contract['symbol']}-{contract['option_type']}",
            score=80,
        )

    monkeypatch.setattr(server, "STOCK_FNO_UNIVERSE", ["A", "B", "C", "D"])
    monkeypatch.setattr(server, "get_stock_core", fake_get_stock_core)
    monkeypatch.setattr(server, "_build_contract", fake_build_contract)
    monkeypatch.setattr(server, "_safe_signal", fake_safe_signal)

    rows = asyncio.run(server._build_stock_fno_signals("2026-02-01T00:00:00Z"))
    assert len(rows) == 8
