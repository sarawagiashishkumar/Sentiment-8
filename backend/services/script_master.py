"""
Script Master — NSE/Angel/Kite/Dhan symbol sync and resolution.

Extracted from server.py for modularity.
"""
from __future__ import annotations

import asyncio
import csv
import difflib
import io
import logging
import re
from datetime import datetime

import requests

from data.symbols import MULTIBAGGER_UNIVERSE
from services.market_data import market_data_client
from services.utils import (
    normalize_symbol_key as _normalize_symbol_key,
    utc_now_iso as _utc_now_iso,
)
from services.research_engine import get_fo_universe

logger = logging.getLogger(__name__)

NSE_SCRIPT_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
ANGEL_SCRIPT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
KITE_SCRIPT_MASTER_URL = "https://api.kite.trade/instruments"
DHAN_SCRIPT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


async def _sync_script_master_daily(force: bool = False) -> None:
    _s = _srv()
    IST = _s.IST
    db = _s.db
    client = _s.client
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP

    today = datetime.now(IST).date().isoformat()
    if not force and _s.SCRIPT_MASTER_LAST_SYNC_DATE == today:
        return

    meta = await db.system_meta.find_one({"key": "script_master_sync"}, {"_id": 0})
    if (not force) and meta and meta.get("date") == today and int(meta.get("updated_count", 0) or 0) >= 500:
        _s.SCRIPT_MASTER_LAST_SYNC_DATE = today
        return

    from data.fno_contracts import FNO_CONTRACTS

    seed_symbols = {
        *MULTIBAGGER_UNIVERSE,
        *get_fo_universe(lot_size_map=LOT_SIZE_MAP),
        *[row["underlying"] for row in FNO_CONTRACTS],
        "NIFTY",
        "BANKNIFTY",
    }

    def _clean_source_symbol(value: str) -> str:
        raw = str(value or "").upper().strip()
        raw = raw.replace("-EQ", "")
        raw = raw.replace(" EQ", "")
        raw = raw.replace(".EQ", "")
        return _normalize_symbol_key(raw)

    def _fetch_nse_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(
                NSE_SCRIPT_MASTER_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            if response.status_code != 200:
                return []
            reader = csv.DictReader(io.StringIO(response.text))
            rows: list[tuple[str, str]] = []
            for row in reader:
                symbol = _normalize_symbol_key(str(row.get("SYMBOL", "")).strip())
                name = str(row.get("NAME OF COMPANY", "")).strip()
                if symbol:
                    rows.append((symbol, name or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch NSE script master: %s", exc)
            return []

    def _fetch_angel_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(ANGEL_SCRIPT_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if response.status_code != 200:
                return []
            payload = response.json()
            rows: list[tuple[str, str]] = []
            for item in payload if isinstance(payload, list) else []:
                exch = str(item.get("exch_seg", "")).upper().strip()
                instrument_type = str(item.get("instrumenttype", "")).upper().strip()
                if exch not in {"NSE", "BSE"}:
                    continue
                if instrument_type and instrument_type not in {"EQ", "AMXIDX", "INDEX"}:
                    continue
                raw_symbol = str(item.get("symbol") or item.get("name") or "").strip()
                raw_name = str(item.get("name") or item.get("symbol") or "").strip()
                symbol = _clean_source_symbol(raw_symbol)
                if not symbol:
                    symbol = _clean_source_symbol(raw_name)
                if symbol.endswith(("FUT", "CE", "PE")):
                    continue
                if symbol:
                    rows.append((symbol, raw_name or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch Angel script master: %s", exc)
            return []

    def _fetch_kite_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(KITE_SCRIPT_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if response.status_code != 200:
                return []
            reader = csv.DictReader(io.StringIO(response.text))
            rows: list[tuple[str, str]] = []
            for item in reader:
                exchange = str(item.get("exchange", "")).upper().strip()
                segment = str(item.get("segment", "")).upper().strip()
                instrument_type = str(item.get("instrument_type", "")).upper().strip()
                if exchange not in {"NSE", "BSE"}:
                    continue
                if segment not in {"NSE", "BSE"}:
                    continue
                if instrument_type not in {"EQ", ""}:
                    continue
                raw_symbol = str(item.get("tradingsymbol", "")).strip()
                raw_name = str(item.get("name", "")).strip()
                symbol = _normalize_symbol_key(raw_symbol)
                if symbol:
                    rows.append((symbol, raw_name or raw_symbol or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch Kite script master: %s", exc)
            return []

    def _fetch_dhan_rows() -> list[tuple[str, str]]:
        try:
            response = requests.get(DHAN_SCRIPT_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if response.status_code != 200:
                return []
            reader = csv.DictReader(io.StringIO(response.text))
            rows: list[tuple[str, str]] = []
            for item in reader:
                exchange = str(item.get("SEM_EXM_EXCH_ID", "")).upper().strip()
                instrument_name = str(item.get("SEM_INSTRUMENT_NAME", "")).upper().strip()
                symbol_name = str(item.get("SM_SYMBOL_NAME", "")).strip()
                trading_symbol = str(item.get("SEM_TRADING_SYMBOL", "")).strip()
                custom_symbol = str(item.get("SEM_CUSTOM_SYMBOL", "")).strip()
                if exchange not in {"NSE", "BSE"}:
                    continue
                if instrument_name not in {"EQUITY", "INDEX"}:
                    continue
                raw_symbol = trading_symbol or symbol_name or custom_symbol
                raw_name = custom_symbol or symbol_name or trading_symbol
                symbol = _clean_source_symbol(raw_symbol)
                if symbol.endswith(("FUT", "CE", "PE")):
                    continue
                if symbol:
                    rows.append((symbol, raw_name or symbol))
            return rows
        except Exception as exc:
            logger.warning("Failed to fetch Dhan script master: %s", exc)
            return []

    nse_rows, angel_rows, kite_rows, dhan_rows = await asyncio.gather(
        asyncio.to_thread(_fetch_nse_rows),
        asyncio.to_thread(_fetch_angel_rows),
        asyncio.to_thread(_fetch_kite_rows),
        asyncio.to_thread(_fetch_dhan_rows),
    )

    nse_equity_symbols = {symbol for symbol, _ in nse_rows}
    allow_symbols = {_normalize_symbol_key(symbol) for symbol in seed_symbols}
    allow_symbols.update({"NIFTY", "BANKNIFTY"})

    source_rows = []
    for symbol, name in [*nse_rows, *angel_rows, *kite_rows, *dhan_rows]:
        canonical = _normalize_symbol_key(symbol)
        if not canonical:
            continue
        if canonical in allow_symbols or canonical in nse_equity_symbols:
            source_rows.append((canonical, name))
    script_records: dict[str, dict] = {}

    for symbol in seed_symbols:
        canonical = _normalize_symbol_key(symbol)
        if not canonical:
            continue
        script_records.setdefault(
            canonical,
            {
                "display_name": symbol,
                "aliases": {symbol, canonical},
            },
        )

    for symbol, name in source_rows:
        row = script_records.setdefault(
            symbol,
            {
                "display_name": name,
                "aliases": {symbol},
            },
        )
        row["display_name"] = row.get("display_name") or name
        row["aliases"].update({symbol, name, name.replace("LIMITED", "LTD")})

    for symbol in sorted(seed_symbols):
        canonical = _normalize_symbol_key(symbol)
        if not canonical:
            continue
        try:
            meta_symbol = await asyncio.to_thread(market_data_client.resolve_symbol_meta, canonical)
        except Exception:
            meta_symbol = None
        if not meta_symbol:
            continue

        row = script_records.setdefault(
            canonical,
            {
                "display_name": symbol,
                "aliases": {symbol, canonical},
            },
        )
        row["display_name"] = meta_symbol.get("name") or row.get("display_name") or symbol
        row["aliases"].update(
            {
                meta_symbol.get("name", ""),
                meta_symbol.get("id", ""),
                meta_symbol.get("did", ""),
                canonical,
            }
        )

    now_iso = _utc_now_iso()
    docs: list[dict] = []
    for canonical, data in sorted(script_records.items()):
        aliases = sorted({str(alias).strip() for alias in data["aliases"] if str(alias).strip()})
        normalized_aliases = sorted(
            {
                _normalize_symbol_key(alias)
                for alias in aliases
                if _normalize_symbol_key(alias)
            }
        )
        docs.append(
            {
                "canonical_symbol": canonical,
                "display_name": data.get("display_name") or canonical,
                "aliases": aliases,
                "normalized_aliases": normalized_aliases,
                "updated_at": now_iso,
            }
        )

    if len(docs) < 500:
        logger.warning("Script master refresh skipped: insufficient compiled rows (%s)", len(docs))
        return

    import os
    staging = db.script_master_staging
    await staging.drop()
    for start in range(0, len(docs), 5000):
        await staging.insert_many(docs[start : start + 5000], ordered=False)

    db_name = os.environ["DB_NAME"]
    try:
        await client.admin.command(
            "renameCollection",
            f"{db_name}.script_master_staging",
            to=f"{db_name}.script_master",
            dropTarget=True,
        )
    except Exception:
        await db.script_master.delete_many({})
        cursor = staging.find({}, {"_id": 0})
        batch: list[dict] = []
        async for row in cursor:
            batch.append(row)
            if len(batch) >= 5000:
                await db.script_master.insert_many(batch, ordered=False)
                batch = []
        if batch:
            await db.script_master.insert_many(batch, ordered=False)
        await staging.drop()

    await db.system_meta.update_one(
        {"key": "script_master_sync"},
        {
            "$set": {
                "key": "script_master_sync",
                "date": today,
                "updated_count": len(docs),
                "updated_at": _utc_now_iso(),
            }
        },
        upsert=True,
    )
    _s.SCRIPT_MASTER_LAST_SYNC_DATE = today


async def _resolve_symbol_input(value: str) -> str:
    await _sync_script_master_daily()
    _s = _srv()
    db = _s.db
    raw_query = str(value or "").strip()
    cleaned = _normalize_symbol_key(raw_query)
    if not cleaned:
        return cleaned

    normalized_variants = {cleaned}
    if cleaned.endswith("LTD"):
        normalized_variants.add(f"{cleaned[:-3]}LIMITED")
    if cleaned.endswith("LIMITED"):
        normalized_variants.add(f"{cleaned[:-7]}LTD")
    query_tokens = [
        _normalize_symbol_key(token)
        for token in re.split(r"\s+|[,&./()-]", raw_query)
        if _normalize_symbol_key(token) and len(_normalize_symbol_key(token)) >= 3
    ]

    row = await db.script_master.find_one(
        {
            "$or": [
                {"canonical_symbol": {"$in": list(normalized_variants)}},
                {"normalized_aliases": {"$in": list(normalized_variants)}},
            ]
        },
        {"_id": 0, "canonical_symbol": 1},
    )
    if row and row.get("canonical_symbol"):
        return row["canonical_symbol"]

    regex_candidates = await db.script_master.find(
        {
            "$or": [
                {
                    "normalized_aliases": {
                        "$regex": "|".join(
                            re.escape(item)
                            for item in [*normalized_variants, *query_tokens]
                        )
                    }
                },
                {"display_name": {"$regex": re.escape(raw_query), "$options": "i"}},
            ]
        },
        {"_id": 0, "canonical_symbol": 1, "display_name": 1, "normalized_aliases": 1},
    ).to_list(5000)
    if regex_candidates:
        def _candidate_sort_key(item: dict) -> tuple[int, int]:
            normalized_aliases = item.get("normalized_aliases", [])
            exact = 1 if any(candidate in normalized_aliases for candidate in normalized_variants) else 0
            starts_with = 1 if any(
                (str(alias).startswith(candidate) or candidate.startswith(str(alias)))
                for alias in normalized_aliases
                for candidate in normalized_variants
            ) else 0
            token_hits = sum(
                1 for token in query_tokens if any(token in str(alias) for alias in normalized_aliases)
            )
            score = (exact * 100) + (starts_with * 50)
            display = _normalize_symbol_key(str(item.get("display_name", "")))
            similarity = int(difflib.SequenceMatcher(None, cleaned, display).ratio() * 100)
            return (score, token_hits, similarity)

        best = sorted(regex_candidates, key=_candidate_sort_key, reverse=True)[0]
        candidate = best.get("canonical_symbol")
        if candidate:
            return candidate

    try:
        meta = await asyncio.to_thread(market_data_client.resolve_symbol_meta, raw_query.upper())
    except Exception:
        meta = None
    if meta:
        discovered = _normalize_symbol_key(meta.get("did") or meta.get("id") or cleaned)
        if discovered:
            aliases = {
                raw_query,
                cleaned,
                meta.get("name", ""),
                meta.get("id", ""),
                meta.get("did", ""),
            }
            aliases = {str(alias).strip() for alias in aliases if str(alias).strip()}
            normalized_aliases = sorted(
                {
                    _normalize_symbol_key(alias)
                    for alias in aliases
                    if _normalize_symbol_key(alias)
                }
            )
            await db.script_master.update_one(
                {"canonical_symbol": discovered},
                {
                    "$set": {
                        "canonical_symbol": discovered,
                        "display_name": meta.get("name") or discovered,
                        "aliases": sorted(aliases),
                        "normalized_aliases": normalized_aliases,
                        "updated_at": _utc_now_iso(),
                    }
                },
                upsert=True,
            )
            return discovered

    return cleaned
