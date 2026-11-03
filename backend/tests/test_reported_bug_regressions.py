import asyncio
from unittest.mock import AsyncMock, Mock, patch

from models import FNOContract, StockCoreNormalized
from services import kite_client
from services.multibagger_engine import compute_multibagger_analysis


def test_option_quote_uses_kite_exchange_symbol_instead_of_numeric_token():
    contract = FNOContract(
        script="NIFTY26DEC25000CE",
        underlying="NIFTY",
        expiry="2026-12-31",
        strike=25000,
        option_type="CE",
        exchange="NFO",
        lot_size=65,
    )
    response = Mock(status_code=200)
    response.json.return_value = {
        "data": {"NFO:NIFTY26DEC25000CE": {"last_price": 123.45, "ohlc": {"high": 130, "low": 110}}}
    }

    with (
        patch.object(kite_client, "_get_kite_access_token", new=AsyncMock(return_value="access-token")),
        patch.object(kite_client._state, "KITE_API_KEY", "test-api-key"),
        patch.object(kite_client.requests, "get", return_value=response) as get,
    ):
        result = asyncio.run(kite_client._fetch_option_snapshot_from_kite(contract))

    assert result["ltp"] == 123.45
    assert result["day_high"] == 130
    assert result["day_low"] == 110
    assert get.call_args.kwargs["params"] == {"i": "NFO:NIFTY26DEC25000CE"}


def test_multibagger_score_uses_stock_specific_fundamentals():
    stock = StockCoreNormalized(
        symbol="TEST",
        company_name="Test Company",
        ltp=100,
        open=99,
        prev_close=98,
        volume=200000,
        market_cap=2000,
        pe_ratio=20,
        book_value=50,
        eps=5,
        year_high=120,
        year_low=80,
        sector="Technology",
    )

    weaker = compute_multibagger_analysis(
        stock,
        fundamental={"roe": 5, "roce": 6, "eps_growth_pct": 2, "piotroski_score": 3},
    )
    stronger = compute_multibagger_analysis(
        stock,
        fundamental={"roe": 25, "roce": 24, "eps_growth_pct": 40, "piotroski_score": 8},
    )

    assert stronger["multibagger_score"] > weaker["multibagger_score"]
