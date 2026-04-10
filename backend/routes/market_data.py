"""
Market data route handlers.

Endpoints: /script-master/*, /sector-momentum, /kite/*
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from deps import get_current_user, get_owner_user

logger = logging.getLogger(__name__)

market_data_router = APIRouter()


# ── Script Master ─────────────────────────────────────────────────────────────

@market_data_router.get("/script-master/lookup")
async def script_master_lookup(q: str = Query(default="")):
    import server as _srv

    query = q.strip()
    if not query:
        return {"query": query, "matches": []}

    await _srv._sync_script_master_daily()
    resolved = await _srv._resolve_symbol_input(query)
    row = await _srv.db.script_master.find_one(
        {"canonical_symbol": resolved},
        {"_id": 0, "canonical_symbol": 1, "display_name": 1, "aliases": 1},
    )
    if not row:
        return {"query": query, "matches": []}
    return {
        "query": query,
        "matches": [
            {
                "symbol": row.get("canonical_symbol"),
                "display_name": row.get("display_name"),
                "aliases": row.get("aliases", []),
            }
        ],
    }


@market_data_router.post("/script-master/refresh")
async def script_master_refresh(owner_user: dict = Depends(get_owner_user)):
    """Stream script-master refresh progress as NDJSON."""
    import json
    import server as _srv
    from datetime import datetime
    from typing import AsyncGenerator
    from fastapi.responses import StreamingResponse

    _ = owner_user

    async def _stream() -> AsyncGenerator[str, None]:
        yield json.dumps({"type": "progress", "phase": "start", "message": "Syncing script master..."}) + "\n"
        _srv.SCRIPT_MASTER_LAST_SYNC_DATE = None
        await _srv._sync_script_master_daily(force=True)
        result = {"refreshed": True, "date": datetime.now(_srv.IST).date().isoformat()}
        yield json.dumps({"type": "complete", "data": result}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


# ── Sector Momentum ───────────────────────────────────────────────────────────

@market_data_router.get("/sector-momentum")
async def get_sector_momentum(
    force_refresh: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """
    Compute or return cached sector momentum dashboard.
    Returns momentum scores, 1W/1M/3M returns, RSI, ADX for 15 NSE sectors.
    Results cached for 30 minutes. Use ?force_refresh=true to bypass cache.
    """
    import server as _srv
    from datetime import datetime, timezone
    from services.sector_momentum import compute_sector_momentum_dashboard

    _ = current_user
    now_ts = datetime.now(timezone.utc).timestamp()

    # In-memory cache check
    if not force_refresh and _srv.SECTOR_MOMENTUM_CACHE:
        cached_ts = _srv.SECTOR_MOMENTUM_CACHE.get("_ts", 0)
        if (now_ts - cached_ts) < _srv.SECTOR_MOMENTUM_CACHE_TTL_SECONDS:
            data = {k: v for k, v in _srv.SECTOR_MOMENTUM_CACHE.items() if not k.startswith("_")}
            data["from_cache"] = True
            return data

    # MongoDB cache check
    if not force_refresh:
        try:
            cached_doc = await _srv.db.sector_momentum_cache.find_one(
                {"_key": "sector_momentum"}, {"_id": 0}
            )
            if cached_doc and (now_ts - float(cached_doc.get("cached_at_ts", 0))) < _srv.SECTOR_MOMENTUM_CACHE_TTL_SECONDS:
                payload = {k: v for k, v in cached_doc.items() if k not in ("_key", "cached_at_ts")}
                _srv.SECTOR_MOMENTUM_CACHE.update({**payload, "_ts": now_ts})
                payload["from_cache"] = True
                return payload
        except Exception:
            pass

    # Compute fresh
    try:
        result = await compute_sector_momentum_dashboard(db=_srv.db)
    except Exception as exc:
        logger.error("Sector momentum computation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sector momentum computation failed: {exc}")

    # Store in caches
    _srv.SECTOR_MOMENTUM_CACHE.update({**result, "_ts": now_ts})
    try:
        await _srv.db.sector_momentum_cache.update_one(
            {"_key": "sector_momentum"},
            {"$set": {"_key": "sector_momentum", "cached_at_ts": now_ts, **result}},
            upsert=True,
        )
    except Exception:
        pass

    result["from_cache"] = False
    return result


# ── Kite Connect Integration ─────────────────────────────────────────────────

@market_data_router.get("/kite/auth-url")
async def get_kite_auth_url(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    if not _srv.KITE_API_KEY or not _srv.KITE_API_SECRET or not _srv.KITE_REDIRECT_URL:
        raise HTTPException(status_code=400, detail="Kite credentials not configured")
    return {
        "auth_url": f"https://kite.zerodha.com/connect/login?v=3&api_key={_srv.KITE_API_KEY}",
        "redirect_url": _srv.KITE_REDIRECT_URL,
    }


@market_data_router.get("/kite/callback")
async def kite_callback(request_token: str = Query(...), status: str | None = Query(default=None)):
    import asyncio
    import server as _srv
    import requests

    _ = status
    if not _srv.KITE_API_KEY or not _srv.KITE_API_SECRET:
        raise HTTPException(status_code=400, detail="Kite credentials not configured")

    checksum = hashlib.sha256(
        f"{_srv.KITE_API_KEY}{request_token}{_srv.KITE_API_SECRET}".encode()
    ).hexdigest()

    def _create_session() -> dict:
        response = requests.post(
            "https://api.kite.trade/session/token",
            data={
                "api_key": _srv.KITE_API_KEY,
                "request_token": request_token,
                "checksum": checksum,
            },
            headers={"X-Kite-Version": "3"},
            timeout=15,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Kite session exchange failed")
        payload = response.json()
        if payload.get("status") != "success":
            raise HTTPException(status_code=502, detail="Kite session exchange failed")
        return payload.get("data", {})

    session_data = await asyncio.to_thread(_create_session)
    access_token = str(session_data.get("access_token", "")).strip()
    if not access_token:
        raise HTTPException(status_code=502, detail="Kite access token missing")

    today = _srv._today_ist()
    await _srv.db.system_meta.update_one(
        {"key": "kite_session"},
        {
            "$set": {
                "key": "kite_session",
                "date": today,
                "api_key": _srv.KITE_API_KEY,
                "access_token": access_token,
                "public_token": session_data.get("public_token"),
                "user_id": session_data.get("user_id"),
                "user_name": session_data.get("user_name"),
                "updated_at": _srv._utc_now_iso(),
            }
        },
        upsert=True,
    )

    await _srv._sync_kite_option_master_daily(force=True)
    return {
        "connected": True,
        "user_id": session_data.get("user_id"),
        "updated_at": _srv._utc_now_iso(),
    }


@market_data_router.get("/kite/status")
async def kite_status(current_user: dict = Depends(get_owner_user)):
    import asyncio
    import requests
    import server as _srv

    _ = current_user
    row = await _srv.db.system_meta.find_one({"key": "kite_session"}, {"_id": 0})
    if not row:
        return {"connected": False, "reason": "no_session"}

    # Date check first — if session is from a different day, it's definitely expired
    if row.get("date") != _srv._today_ist():
        return {
            "connected": False,
            "reason": "session_expired_date_mismatch",
            "date": row.get("date"),
            "user_id": row.get("user_id"),
            "updated_at": row.get("updated_at"),
        }

    # Live token validation: actually hit Kite API to confirm token works
    access_token = str(row.get("access_token", "")).strip()
    if not access_token:
        return {"connected": False, "reason": "no_access_token"}

    def _validate_token() -> bool:
        try:
            resp = requests.get(
                "https://api.kite.trade/user/profile",
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {_srv.KITE_API_KEY}:{access_token}",
                },
                timeout=8,
            )
            return resp.status_code == 200
        except Exception:
            return False

    try:
        token_valid = await asyncio.to_thread(_validate_token)
    except Exception:
        token_valid = False

    if not token_valid:
        return {
            "connected": False,
            "reason": "token_invalid_or_expired",
            "date": row.get("date"),
            "user_id": row.get("user_id"),
            "updated_at": row.get("updated_at"),
        }

    return {
        "connected": True,
        "date": row.get("date"),
        "user_id": row.get("user_id"),
        "updated_at": row.get("updated_at"),
    }


@market_data_router.post("/kite/refresh-option-master")
async def kite_refresh_option_master(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    await _srv._sync_kite_option_master_daily(force=True)
    meta = await _srv.db.system_meta.find_one({"key": "kite_option_master_sync"}, {"_id": 0})
    return {"refreshed": True, "meta": meta or {}}


@market_data_router.post("/kite/postback")
async def kite_postback(payload: dict):
    _ = payload
    return {"received": True}


@market_data_router.get("/kite/policy")
async def kite_policy(current_user: dict = Depends(get_owner_user)):
    import server as _srv

    _ = current_user
    return {
        "read_only_mode": _srv.KITE_READ_ONLY_MODE,
        "trading_enabled": False,
        "allowed_data_endpoints": _srv.KITE_ALLOWED_DATA_ENDPOINTS,
        "blocked_categories": ["orders", "gtt", "positions-write", "basket-orders"],
    }


# ── Market Heatmap Endpoints ──────────────────────────────────────────────────

@market_data_router.get("/market/sector-stocks")
async def sector_stocks(
    sector: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    """Return constituent stocks for a given sector with basic price data."""
    import server as _srv

    sector = sector.strip()
    if not sector:
        raise HTTPException(400, "sector query parameter required")

    # Look up sector constituents from the fno_universe or script master
    all_stocks = await _srv.db.script_master.find(
        {"segment": "NSE", "instrument_type": {"$in": ["EQ", "BE"]}},
        {"_id": 0, "tradingsymbol": 1, "name": 1},
    ).to_list(5000)

    # Filter stocks that belong to the sector (best-effort mapping)
    # Use cached sector→stock mapping if available
    sector_mapping = await _srv.db.sector_stock_mapping.find_one(
        {"sector": sector}, {"_id": 0}
    )
    if sector_mapping and sector_mapping.get("stocks"):
        symbols = sector_mapping["stocks"]
    else:
        # Fallback: return top traded stocks as placeholder
        symbols = [s["tradingsymbol"] for s in all_stocks[:20]]

    # Fetch latest LTP/change data from cache
    stock_data = []
    for sym in symbols[:30]:
        cached = await _srv.db.stock_ltp_cache.find_one(
            {"symbol": sym}, {"_id": 0}
        )
        ltp = cached.get("ltp", 0) if cached else 0
        prev_close = cached.get("prev_close", 0) if cached else 0
        change_pct = ((ltp - prev_close) / prev_close * 100) if prev_close else 0
        stock_data.append({
            "symbol": sym,
            "ltp": round(ltp, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": round(change_pct, 2),
        })

    stock_data.sort(key=lambda x: x["change_pct"], reverse=True)
    return {"sector": sector, "stocks": stock_data}


@market_data_router.get("/market/stock-heatmap")
async def stock_heatmap(
    filter: str = Query(default="fno"),
    current_user: dict = Depends(get_current_user),
):
    """Return stock heatmap data for the given filter universe."""
    import server as _srv

    # Get FNO universe
    fno_stocks = []
    async for doc in _srv.db.fno_universe.find({}, {"_id": 0, "symbol": 1, "lot_size": 1}):
        fno_stocks.append(doc.get("symbol", ""))

    if not fno_stocks:
        # Fallback: grab from data/lot_sizes.py if fno_universe is empty
        try:
            from data.lot_sizes import LOT_SIZE_MAP
            fno_stocks = list(LOT_SIZE_MAP.keys())
        except Exception:
            fno_stocks = []

    # Build the universe based on filter
    universe = set()
    nifty50 = {"RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "SBIN",
               "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE",
               "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND",
               "WIPRO", "HCLTECH", "TATAMOTORS", "NTPC", "POWERGRID", "M&M",
               "ONGC", "ADANIPORTS", "JSWSTEEL", "TATASTEEL", "COALINDIA",
               "BAJAJFINSV", "TECHM", "INDUSINDBK", "GRASIM", "CIPLA",
               "DRREDDY", "SBILIFE", "APOLLOHOSP", "HEROMOTOCO", "DIVISLAB",
               "EICHERMOT", "BRITANNIA", "BPCL", "TRENT", "HINDALCO",
               "SHRIRAMFIN", "BAJAJ-AUTO", "HDFCLIFE", "TATACONSUM", "BEL"}

    banknifty = {"HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
                 "INDUSINDBK", "BANKBARODA", "FEDERALBNK", "PNB", "IDFCFIRSTB",
                 "AUBANK", "BANDHANBNK"}

    if filter == "nifty50":
        universe = nifty50
    elif filter == "banknifty":
        universe = banknifty
    elif filter == "fno":
        universe = set(fno_stocks) if fno_stocks else nifty50
    else:
        universe = set(fno_stocks) if fno_stocks else nifty50

    # Fetch LTP data
    stocks = []
    for sym in universe:
        cached = await _srv.db.stock_ltp_cache.find_one({"symbol": sym}, {"_id": 0})
        ltp = cached.get("ltp", 0) if cached else 0
        prev_close = cached.get("prev_close", 0) if cached else 0
        change_pct = ((ltp - prev_close) / prev_close * 100) if prev_close else 0
        stocks.append({
            "symbol": sym,
            "ltp": round(ltp, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": round(change_pct, 2),
        })

    # Apply additional filters
    if filter == "plus5":
        stocks = [s for s in stocks if s["change_pct"] >= 5]
    elif filter == "plus3":
        stocks = [s for s in stocks if s["change_pct"] >= 3]
    elif filter == "minus3":
        stocks = [s for s in stocks if s["change_pct"] <= -3]
    elif filter == "minus5":
        stocks = [s for s in stocks if s["change_pct"] <= -5]

    stocks.sort(key=lambda x: x["change_pct"], reverse=True)
    return {"filter": filter, "count": len(stocks), "stocks": stocks}


@market_data_router.get("/market/options-heatmap")
async def options_heatmap(
    filter: str = Query(default="nifty"),
    current_user: dict = Depends(get_current_user),
):
    """Return options chain heatmap data from Kite option chain cache."""
    import server as _srv

    chains = []

    if filter in ("nifty", "banknifty"):
        symbol = "NIFTY" if filter == "nifty" else "BANKNIFTY"
        cached = await _srv.db.option_chain_cache.find_one(
            {"symbol": symbol}, {"_id": 0}
        )
        if cached and cached.get("chain"):
            strikes = []
            for row in cached["chain"][:20]:  # Top 20 strikes around ATM
                strikes.append({
                    "strike": row.get("strike", 0),
                    "ce_ltp": row.get("ce_ltp"),
                    "ce_oi": row.get("ce_oi"),
                    "ce_iv": row.get("ce_iv"),
                    "pe_ltp": row.get("pe_ltp"),
                    "pe_oi": row.get("pe_oi"),
                    "pe_iv": row.get("pe_iv"),
                })
            chains.append({
                "symbol": symbol,
                "spot": cached.get("spot", 0),
                "step": 50 if symbol == "NIFTY" else 100,
                "strikes": strikes,
            })
        summary = {}
        if cached:
            summary = {
                "max_pain": cached.get("max_pain"),
                "pcr": cached.get("pcr"),
                "iv_rank": cached.get("iv_rank"),
                "oi_buildup": cached.get("oi_buildup"),
            }
        return {"filter": filter, "chains": chains, "summary": summary}

    elif filter == "stocks":
        # Stock options: pull from option_chain_cache for stock symbols
        async for doc in _srv.db.option_chain_cache.find(
            {"symbol": {"$nin": ["NIFTY", "BANKNIFTY"]}}, {"_id": 0}
        ).sort("symbol", 1).limit(10):
            strikes = []
            for row in (doc.get("chain") or [])[:10]:
                strikes.append({
                    "strike": row.get("strike", 0),
                    "ce_ltp": row.get("ce_ltp"),
                    "ce_oi": row.get("ce_oi"),
                    "ce_iv": row.get("ce_iv"),
                    "pe_ltp": row.get("pe_ltp"),
                    "pe_oi": row.get("pe_oi"),
                    "pe_iv": row.get("pe_iv"),
                })
            chains.append({
                "symbol": doc.get("symbol"),
                "spot": doc.get("spot", 0),
                "step": 50,
                "strikes": strikes,
            })
        return {"filter": filter, "chains": chains, "summary": {}}

    return {"filter": filter, "chains": [], "summary": {}}
