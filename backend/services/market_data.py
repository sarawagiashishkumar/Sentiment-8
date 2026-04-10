import asyncio
import logging
import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Any

import requests

from data.fno_contracts import get_fno_contract

logger = logging.getLogger(__name__)

MONEYCONTROL_API_BASE = "https://api.moneycontrol.com/mcapi"
MONEYCONTROL_PRICE_BASE = "https://priceapi.moneycontrol.com/pricefeed"
RAPIDAPI_BASE = "https://indian-stock-exchange-api2.p.rapidapi.com"

INDEX_BRIDGE_CODES = {
    "NIFTY": "in%3BNSX",
    "BANKNIFTY": "in%3Bnbx",
}


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "")
    if raw in {"", "-", "--", "NA", "N/A", "None", "null"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _safe_round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _normalize_symbol_match(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


class MarketDataClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
            }
        )
        self.rapidapi_key = os.environ.get("RAPIDAPI_KEY")
        self.rapidapi_host = os.environ.get(
            "RAPIDAPI_HOST", "indian-stock-exchange-api2.p.rapidapi.com"
        )

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        try:
            response = self.session.get(url, params=params, timeout=12)
            if response.status_code != 200:
                return None
            return response.json()
        except Exception as exc:
            logger.warning("Request failed for %s: %s", url, exc)
            return None

    @lru_cache(maxsize=1024)
    def resolve_symbol_meta(self, symbol: str) -> dict[str, str] | None:
        url = f"{MONEYCONTROL_API_BASE}/v1/fno/options/getFnoList"
        payload = self._get_json(url, params={"stk_txt": symbol})
        if not payload:
            return None

        fno_list = payload.get("data", {}).get("fno_list", [])
        if not fno_list:
            return None

        normalized_symbol = _normalize_symbol_match(symbol)

        def score(entry: dict[str, Any]) -> int:
            entry_id = _normalize_symbol_match(str(entry.get("id", "")))
            entry_did = _normalize_symbol_match(str(entry.get("did", "")))
            entry_name = _normalize_symbol_match(str(entry.get("stkname", "")))
            if entry_id == normalized_symbol or entry_did == normalized_symbol:
                return 100
            if entry_name == normalized_symbol:
                return 95
            if normalized_symbol in entry_name:
                return 70
            if normalized_symbol in entry_id or normalized_symbol in entry_did:
                return 60
            return 10

        best = sorted(fno_list, key=score, reverse=True)[0]
        return {
            "id": str(best.get("id", "")),
            "did": str(best.get("did", "")),
            "name": str(best.get("stkname", symbol)),
        }

    def fetch_stock_from_moneycontrol(self, symbol: str) -> dict[str, Any] | None:
        symbol_upper = symbol.upper()

        if symbol_upper in INDEX_BRIDGE_CODES:
            bridge = INDEX_BRIDGE_CODES[symbol_upper]
            index_url = f"{MONEYCONTROL_PRICE_BASE}/notapplicable/inidicesindia/{bridge}"
            payload = self._get_json(index_url)
            data = payload.get("data") if payload else None
            if not data:
                return None
            return {
                "symbol": symbol_upper,
                "company_name": data.get("company") or symbol_upper,
                "ltp": _parse_number(data.get("pricecurrent")),
                "open": _parse_number(data.get("OPEN")),
                "high": _parse_number(data.get("HIGH")),
                "low": _parse_number(data.get("LOW")),
                "prev_close": _parse_number(data.get("priceprevclose")),
                "year_high": _parse_number(data.get("52wkhi")),
                "year_low": _parse_number(data.get("52wklow")),
                "volume": int(_parse_number(data.get("VOL")) or 0),
                "market_cap": None,
                "pe_ratio": None,
                "book_value": None,
                "eps": None,
                "sector": "Index",
            }

        candidate_codes: list[str] = [symbol_upper]
        company_name = symbol_upper

        meta = self.resolve_symbol_meta(symbol_upper)
        if meta:
            candidate_codes.extend([meta["id"], meta["did"]])
            company_name = meta.get("name") or company_name

        # Preserve order, remove duplicates
        candidate_codes = list(dict.fromkeys(code for code in candidate_codes if code))

        for code in candidate_codes:
            if not code:
                continue
            eq_url = f"{MONEYCONTROL_PRICE_BASE}/nse/equitycash/{code}"
            payload = self._get_json(eq_url)
            if not payload or payload.get("code") != "200":
                continue

            data = payload.get("data") or {}
            ltp = _parse_number(data.get("pricecurrent")) or _parse_number(data.get("HP"))
            pe_ratio = _parse_number(data.get("PE"))
            eps = _parse_number(data.get("SC_TTM"))
            if eps is None and ltp and pe_ratio and pe_ratio > 0:
                eps = ltp / pe_ratio

            return {
                "symbol": symbol_upper,
                "company_name": data.get("SC_FULLNM") or company_name,
                "ltp": ltp,
                "open": _parse_number(data.get("OPN")),
                "high": _parse_number(data.get("DHI")) or _parse_number(data.get("HP")),
                "low": _parse_number(data.get("DLO")) or _parse_number(data.get("LP")),
                "prev_close": _parse_number(data.get("priceprevclose")),
                "year_high": _parse_number(data.get("52H")),
                "year_low": _parse_number(data.get("52L")),
                "volume": int(_parse_number(data.get("VOL")) or 0),
                "market_cap": _parse_number(data.get("MKTCAP")),
                "pe_ratio": pe_ratio,
                "book_value": _parse_number(data.get("BV")),
                "eps": eps,
                "sector": data.get("SC_SUBSEC") or "Unknown",
            }
        return None

    def fetch_stock_from_rapidapi(self, symbol: str) -> dict[str, Any] | None:
        if not self.rapidapi_key:
            return None
        headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": self.rapidapi_host,
        }
        try:
            response = self.session.get(
                f"{RAPIDAPI_BASE}/equities",
                params={"symbol": symbol},
                headers=headers,
                timeout=12,
            )
            if response.status_code != 200:
                return None
            payload = response.json()
        except Exception:
            return None

        return {
            "symbol": symbol.upper(),
            "company_name": payload.get("companyName") or symbol.upper(),
            "ltp": _parse_number(payload.get("ltp")),
            "open": _parse_number(payload.get("open")),
            "high": _parse_number(payload.get("high")),
            "low": _parse_number(payload.get("low")),
            "prev_close": _parse_number(payload.get("prevClose")),
            "year_high": _parse_number(payload.get("yearHigh")),
            "year_low": _parse_number(payload.get("yearLow")),
            "volume": int(_parse_number(payload.get("volume")) or 0),
            "market_cap": _parse_number(payload.get("marketCap")),
            "pe_ratio": _parse_number(payload.get("peRatio")),
            "book_value": _parse_number(payload.get("bookValue")),
            "eps": _parse_number(payload.get("eps")),
            "sector": payload.get("sector") or "Unknown",
        }

    def get_option_expiries(self, instrument_id: str) -> list[datetime]:
        url = f"{MONEYCONTROL_API_BASE}/v1/fno/options/getExpDts"
        payload = self._get_json(url, params={"id": instrument_id})
        if not payload:
            return []

        data = payload.get("data", {})
        expiries: list[datetime] = []
        iterable = data.values() if isinstance(data, dict) else data
        for item in iterable:
            value = item.get("fno_exp") if isinstance(item, dict) else None
            if not value:
                continue
            try:
                expiries.append(datetime.strptime(value, "%Y-%m-%d"))
            except ValueError:
                continue
        return sorted(expiries)

    def parse_option_chain_ltp(
        self,
        option_chain_html: str,
        strike: float,
        option_type: str,
    ) -> float | None:
        strike_map = {
            idx: _parse_number(val)
            for idx, val in re.findall(r'id="origin(\d+)"[^>]*>\s*([0-9,.]+)\s*<', option_chain_html)
        }
        call_map = {
            idx: _parse_number(val)
            for idx, val in re.findall(r'id="call_ltp(\d+)"[^>]*>\s*([0-9,.-]+)\s*<', option_chain_html)
        }
        put_map = {
            idx: _parse_number(val)
            for idx, val in re.findall(r'id="puts_ltp(\d+)"[^>]*>\s*([0-9,.-]+)\s*<', option_chain_html)
        }

        option_map = call_map if option_type.upper() == "CE" else put_map

        for idx, strike_value in strike_map.items():
            if strike_value is None:
                continue
            if abs(strike_value - float(strike)) > 0.01:
                continue
            exact_ltp = option_map.get(idx)
            if exact_ltp is not None and exact_ltp > 0:
                return exact_ltp

        nearest_candidates: list[tuple[float, float]] = []
        for idx, strike_value in strike_map.items():
            if strike_value is None:
                continue
            ltp_value = option_map.get(idx)
            if ltp_value is None or ltp_value <= 0:
                continue
            nearest_candidates.append((abs(strike_value - float(strike)), ltp_value))

        if nearest_candidates:
            nearest_candidates.sort(key=lambda item: item[0])
            return nearest_candidates[0][1]

        return None

    def fetch_option_ltp_for_contract(self, contract: dict[str, Any]) -> float:
        underlying = contract["underlying"].upper()
        meta = self.resolve_symbol_meta(underlying)
        instrument_id = ""
        did = underlying
        if meta:
            instrument_id = meta.get("id", "")
            did = meta.get("did") or did

        if underlying in INDEX_BRIDGE_CODES:
            did = underlying
            if not instrument_id:
                instrument_id = "9" if underlying == "NIFTY" else "23"
        if not instrument_id:
            instrument_id = did

        expiries = self.get_option_expiries(instrument_id)
        expiry_value = contract.get("expiry_date") or contract.get("expiry")
        target_expiry = datetime.strptime(expiry_value, "%Y-%m-%d")

        if expiries:
            chosen_expiry = min(expiries, key=lambda exp: abs((exp - target_expiry).days))
        else:
            chosen_expiry = target_expiry

        page = self.session.get(
            "https://www.moneycontrol.com/mc/optionchain",
            params={
                "sc_did": did,
                "sel_exp_date": chosen_expiry.strftime("%Y-%m-%d"),
                "classic": "true",
                "sec": "all",
            },
            timeout=15,
        )
        if page.status_code != 200:
            raise ValueError("Unable to fetch option chain")

        ltp = self.parse_option_chain_ltp(page.text, contract["strike"], contract["option_type"])
        if ltp is None:
            raise ValueError("Option LTP unavailable for requested strike")
        return float(ltp)


market_data_client = MarketDataClient()


async def get_stock_core(symbol: str) -> dict:
    """
    Single normalized stock/index fetch helper.
    PRIMARY: Kite Connect /quote API.
    FALLBACK: MoneyControl (only for index data or data Kite doesn't provide).
    """
    symbol_upper = symbol.upper().strip()

    # PRIMARY: Try Kite first (except for indices which Kite handles differently)
    if symbol_upper not in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}:
        try:
            from services.kite_client import _fetch_kite_equity_core
            kite_data = await _fetch_kite_equity_core(symbol_upper)
            if kite_data and kite_data.get("ltp"):
                return {
                    "symbol": kite_data.get("symbol", symbol_upper),
                    "company_name": kite_data.get("company_name", symbol_upper),
                    "ltp": _safe_round(_parse_number(kite_data.get("ltp"))),
                    "open": _safe_round(_parse_number(kite_data.get("open"))),
                    "high": _safe_round(_parse_number(kite_data.get("high"))),
                    "low": _safe_round(_parse_number(kite_data.get("low"))),
                    "prev_close": _safe_round(_parse_number(kite_data.get("prev_close"))),
                    "year_high": None,
                    "year_low": None,
                    "volume": int(_parse_number(kite_data.get("volume")) or 0),
                    "market_cap": None,
                    "pe_ratio": None,
                    "book_value": None,
                    "eps": None,
                    "sector": kite_data.get("sector") or "NSE",
                }
        except Exception as exc:
            logger.debug("Kite core fetch failed for %s: %s", symbol_upper, exc)

    # FALLBACK: MoneyControl (for indices or when Kite unavailable)
    data = await asyncio.to_thread(market_data_client.fetch_stock_from_moneycontrol, symbol_upper)
    if data is None:
        data = await asyncio.to_thread(market_data_client.fetch_stock_from_rapidapi, symbol_upper)

    if data is None:
        data = {
            "symbol": symbol_upper,
            "company_name": symbol_upper,
            "ltp": None, "open": None, "high": None, "low": None,
            "prev_close": None, "year_high": None, "year_low": None,
            "volume": 0, "market_cap": None, "pe_ratio": None,
            "book_value": None, "eps": None, "sector": "Unknown",
        }

    return {
        "symbol": data.get("symbol", symbol_upper),
        "company_name": data.get("company_name", symbol_upper),
        "ltp": _safe_round(_parse_number(data.get("ltp"))),
        "open": _safe_round(_parse_number(data.get("open"))),
        "high": _safe_round(_parse_number(data.get("high"))),
        "low": _safe_round(_parse_number(data.get("low"))),
        "prev_close": _safe_round(_parse_number(data.get("prev_close"))),
        "year_high": _safe_round(_parse_number(data.get("year_high"))),
        "year_low": _safe_round(_parse_number(data.get("year_low"))),
        "volume": int(_parse_number(data.get("volume")) or 0),
        "market_cap": _safe_round(_parse_number(data.get("market_cap"))),
        "pe_ratio": _safe_round(_parse_number(data.get("pe_ratio"))),
        "book_value": _safe_round(_parse_number(data.get("book_value"))),
        "eps": _safe_round(_parse_number(data.get("eps"))),
        "sector": data.get("sector") or "Unknown",
    }


async def get_option_ltp(script: str) -> float:
    """
    Fetches live option LTP from Moneycontrol option-chain using exact strike/type,
    with nearest expiry fallback.
    """
    contract = get_fno_contract(script)
    if not contract:
        raise ValueError("Script not supported")
    return await asyncio.to_thread(market_data_client.fetch_option_ltp_for_contract, contract)
