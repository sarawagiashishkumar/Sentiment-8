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


# ── Market Heatmap Endpoints (Live Kite /quote — no cache dependency) ─────────

NIFTY50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "SBIN",
    "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND",
    "WIPRO", "HCLTECH", "TATAMOTORS", "NTPC", "POWERGRID", "M&M",
    "ONGC", "ADANIPORTS", "JSWSTEEL", "TATASTEEL", "COALINDIA",
    "BAJAJFINSV", "TECHM", "INDUSINDBK", "GRASIM", "CIPLA",
    "DRREDDY", "SBILIFE", "APOLLOHOSP", "HEROMOTOCO", "DIVISLAB",
    "EICHERMOT", "BRITANNIA", "BPCL", "TRENT", "HINDALCO",
    "SHRIRAMFIN", "BAJAJ-AUTO", "HDFCLIFE", "TATACONSUM", "BEL",
]

BANKNIFTY_STOCKS = [
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
    "INDUSINDBK", "BANKBARODA", "FEDERALBNK", "PNB", "IDFCFIRSTB",
    "AUBANK", "BANDHANBNK",
]


@market_data_router.get("/market/sector-stocks")
async def sector_stocks(
    sector: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    """Return constituent stocks for a given sector with live Kite quote data."""
    import server as _srv
    from services.kite_client import fetch_kite_batch_quotes

    sector = sector.strip()
    if not sector:
        raise HTTPException(400, "sector query parameter required")

    # Look up sector constituents from DB or use index constituents
    sector_mapping = await _srv.db.sector_stock_mapping.find_one(
        {"sector": sector}, {"_id": 0}
    )
    if sector_mapping and sector_mapping.get("stocks"):
        symbols = sector_mapping["stocks"]
    else:
        # Try index_constituents collection
        idx_map = await _srv.db.index_constituents.find_one(
            {"index_name": {"$regex": sector, "$options": "i"}}, {"_id": 0}
        )
        if idx_map and idx_map.get("symbols"):
            symbols = idx_map["symbols"]
        else:
            symbols = NIFTY50_STOCKS[:20]

    # Fetch live from Kite
    quotes = await fetch_kite_batch_quotes(symbols[:30])

    stock_data = []
    for sym in symbols[:30]:
        q = quotes.get(sym, {})
        stock_data.append({
            "symbol": sym,
            "ltp": round(q.get("ltp", 0), 2),
            "prev_close": round(q.get("prev_close", 0), 2),
            "change_pct": round(q.get("change_pct", 0), 2),
        })

    stock_data.sort(key=lambda x: x["change_pct"], reverse=True)
    kite_live = any(q.get("ltp", 0) > 0 for q in quotes.values())
    return {"sector": sector, "stocks": stock_data, "kite_live": kite_live}


@market_data_router.get("/market/stock-heatmap")
async def stock_heatmap(
    filter: str = Query(default="fno"),
    current_user: dict = Depends(get_current_user),
):
    """Return stock heatmap data with LIVE Kite quotes."""
    import server as _srv
    from services.kite_client import fetch_kite_batch_quotes

    # Get FNO universe from lot_sizes
    try:
        from data.lot_sizes import LOT_SIZE_MAP
        fno_stocks = [s for s in LOT_SIZE_MAP.keys()
                      if s not in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}]
    except Exception:
        fno_stocks = NIFTY50_STOCKS

    # Build universe based on filter
    if filter == "nifty50":
        universe = NIFTY50_STOCKS
    elif filter == "banknifty":
        universe = BANKNIFTY_STOCKS
    elif filter == "fno":
        universe = fno_stocks
    elif filter in ("plus5", "plus3", "minus3", "minus5"):
        universe = fno_stocks  # Fetch all, then filter by change
    else:
        universe = fno_stocks

    # Fetch live quotes from Kite /quote API
    quotes = await fetch_kite_batch_quotes(universe)

    stocks = []
    for sym in universe:
        q = quotes.get(sym, {})
        ltp = q.get("ltp", 0)
        prev_close = q.get("prev_close", 0)
        change_pct = q.get("change_pct", 0)
        stocks.append({
            "symbol": sym,
            "ltp": round(ltp, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": round(change_pct, 2),
        })

    # Apply percentage filters
    if filter == "plus5":
        stocks = [s for s in stocks if s["change_pct"] >= 5]
    elif filter == "plus3":
        stocks = [s for s in stocks if s["change_pct"] >= 3]
    elif filter == "minus3":
        stocks = [s for s in stocks if s["change_pct"] <= -3]
    elif filter == "minus5":
        stocks = [s for s in stocks if s["change_pct"] <= -5]

    stocks.sort(key=lambda x: x["change_pct"], reverse=True)
    kite_live = any(q.get("ltp", 0) > 0 for q in quotes.values())
    return {"filter": filter, "count": len(stocks), "stocks": stocks, "kite_live": kite_live}


@market_data_router.get("/market/options-heatmap")
async def options_heatmap(
    filter: str = Query(default="nifty"),
    current_user: dict = Depends(get_current_user),
):
    """Return options chain heatmap data LIVE from Kite /quote using NFO:tradingsymbol."""
    import server as _srv
    from services.kite_client import fetch_kite_batch_option_quotes, _get_kite_access_token

    access_token = await _get_kite_access_token()
    if not access_token:
        return {"filter": filter, "chains": [], "summary": {}, "kite_live": False,
                "warning": "Kite not connected. Please authenticate Kite in Admin panel."}

    chains = []

    if filter in ("nifty", "banknifty"):
        symbol = "NIFTY" if filter == "nifty" else "BANKNIFTY"
        step = 50 if symbol == "NIFTY" else 100

        # Get spot price from Kite
        from services.kite_client import fetch_kite_batch_quotes
        idx_quotes = await fetch_kite_batch_quotes(["NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"], exchange="NSE")
        spot = 0
        for v in idx_quotes.values():
            spot = v.get("ltp", 0)

        if spot <= 0:
            # Try from index quote
            import requests as _req
            try:
                resp = _req.get(
                    "https://api.kite.trade/quote/ltp",
                    params=[("i", f"NSE:{symbol}")],
                    headers={"X-Kite-Version": "3", "Authorization": f"token {_srv.KITE_API_KEY}:{access_token}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    for v in data.values():
                        spot = float(v.get("last_price", 0))
            except Exception:
                pass

        # Get nearest expiry option tradingsymbols from kite_option_master
        from services.kite_client import _sync_kite_option_master_daily
        await _sync_kite_option_master_daily()

        # Find nearest expiry
        from services.date_utils import today_ist as _tist
        pipeline = [
            {"$match": {"underlying": symbol}},
            {"$group": {"_id": "$expiry"}},
            {"$sort": {"_id": 1}},
            {"$limit": 1},
        ]
        expiry_docs = await _srv.db.kite_option_master.aggregate(pipeline).to_list(1)
        if not expiry_docs:
            return {"filter": filter, "chains": [], "summary": {}, "kite_live": True,
                    "warning": "No option master data. Run Kite instrument sync first."}

        nearest_expiry = expiry_docs[0]["_id"]

        # Get strikes around ATM
        atm_strike = round(spot / step) * step if spot > 0 else 0
        strike_range = list(range(int(atm_strike - step * 10), int(atm_strike + step * 11), step))

        # Get tradingsymbols for these strikes
        option_rows = await _srv.db.kite_option_master.find(
            {"underlying": symbol, "expiry": nearest_expiry, "strike": {"$in": [float(s) for s in strike_range]}},
            {"_id": 0, "tradingsymbol": 1, "strike": 1, "option_type": 1},
        ).to_list(200)

        if option_rows:
            ts_list = [r["tradingsymbol"] for r in option_rows]
            option_quotes = await fetch_kite_batch_option_quotes(ts_list)

            # Build strike table
            strike_data = {}
            for row in option_rows:
                s = float(row["strike"])
                ot = row["option_type"]
                ts = row["tradingsymbol"]
                q = option_quotes.get(ts, {})
                if s not in strike_data:
                    strike_data[s] = {"strike": s}
                prefix = "ce" if ot == "CE" else "pe"
                strike_data[s][f"{prefix}_ltp"] = q.get("ltp")
                strike_data[s][f"{prefix}_oi"] = q.get("oi")
                strike_data[s][f"{prefix}_iv"] = q.get("iv")

            sorted_strikes = sorted(strike_data.values(), key=lambda x: x["strike"])
            chains.append({
                "symbol": symbol,
                "spot": spot,
                "step": step,
                "expiry": nearest_expiry,
                "strikes": sorted_strikes,
            })

            # Compute summary
            total_ce_oi = sum((s.get("ce_oi") or 0) for s in sorted_strikes)
            total_pe_oi = sum((s.get("pe_oi") or 0) for s in sorted_strikes)
            pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else None

            return {"filter": filter, "chains": chains, "kite_live": True, "summary": {
                "pcr": pcr, "max_pain": None, "iv_rank": None,
                "oi_buildup": "SHORT_BUILDUP" if pcr and pcr < 0.7 else "LONG_BUILDUP" if pcr and pcr > 1.3 else None,
            }}

        return {"filter": filter, "chains": chains, "summary": {}, "kite_live": True}

    elif filter == "stocks":
        return {"filter": filter, "chains": [], "summary": {}, "kite_live": True,
                "warning": "Stock options heatmap: Select specific stock from F&O universe for chain view."}

    # Stock-specific option chains (e.g., filter=RELIANCE, TCS, HDFCBANK)
    else:
        # Try as stock symbol
        stock_symbol = filter.upper()
        step = 50  # default step for stock options
        from services.kite_client import fetch_kite_batch_quotes as _fbq2, fetch_kite_batch_option_quotes as _fboq2, _get_kite_access_token as _gkat2
        from services.date_utils import today_ist as _tist2

        access_token2 = await _gkat2()
        if not access_token2:
            return {"filter": filter, "chains": [], "summary": {}, "kite_live": False,
                    "warning": "API not connected."}

        # Get spot from Kite
        spot_quotes = await _fbq2([stock_symbol])
        spot = spot_quotes.get(stock_symbol, {}).get("ltp", 0)

        if spot <= 0:
            return {"filter": filter, "chains": [], "summary": {}, "kite_live": True,
                    "warning": f"No spot data for {stock_symbol}. Verify symbol is in F&O universe."}

        # Determine step based on price
        if spot > 5000:
            step = 100
        elif spot > 2000:
            step = 50
        elif spot > 500:
            step = 20
        elif spot > 100:
            step = 10
        else:
            step = 5

        # Find nearest expiry
        pipeline = [
            {"$match": {"underlying": stock_symbol}},
            {"$group": {"_id": "$expiry"}},
            {"$sort": {"_id": 1}},
            {"$limit": 3},
        ]
        expiry_docs = await _srv.db.kite_option_master.aggregate(pipeline).to_list(3)
        if not expiry_docs:
            return {"filter": filter, "chains": [], "summary": {}, "kite_live": True,
                    "warning": f"No option data for {stock_symbol}. Run Kite instrument sync."}

        nearest_expiry = expiry_docs[0]["_id"]
        available_expiries = [d["_id"] for d in expiry_docs]

        atm_strike = round(spot / step) * step
        strike_range = list(range(int(atm_strike - step * 10), int(atm_strike + step * 11), step))

        option_rows = await _srv.db.kite_option_master.find(
            {"underlying": stock_symbol, "expiry": nearest_expiry, "strike": {"$in": [float(s) for s in strike_range]}},
            {"_id": 0, "tradingsymbol": 1, "strike": 1, "option_type": 1},
        ).to_list(200)

        if option_rows:
            ts_list = [r["tradingsymbol"] for r in option_rows]
            option_quotes = await _fboq2(ts_list)

            strike_data = {}
            for row in option_rows:
                s = float(row["strike"])
                ot = row["option_type"]
                ts = row["tradingsymbol"]
                q = option_quotes.get(ts, {})
                if s not in strike_data:
                    strike_data[s] = {"strike": s}
                prefix = "ce" if ot == "CE" else "pe"
                strike_data[s][f"{prefix}_ltp"] = q.get("ltp")
                strike_data[s][f"{prefix}_oi"] = q.get("oi")
                strike_data[s][f"{prefix}_iv"] = q.get("iv")
                strike_data[s][f"{prefix}_ts"] = ts

            sorted_strikes = sorted(strike_data.values(), key=lambda x: x["strike"])
            chains.append({
                "symbol": stock_symbol,
                "spot": spot,
                "step": step,
                "expiry": nearest_expiry,
                "available_expiries": available_expiries,
                "strikes": sorted_strikes,
            })

            total_ce_oi = sum((s.get("ce_oi") or 0) for s in sorted_strikes)
            total_pe_oi = sum((s.get("pe_oi") or 0) for s in sorted_strikes)
            pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else None

            return {"filter": filter, "chains": chains, "kite_live": True, "summary": {
                "pcr": pcr, "oi_buildup": "SHORT_BUILDUP" if pcr and pcr < 0.7 else "LONG_BUILDUP" if pcr and pcr > 1.3 else None,
            }}

        return {"filter": filter, "chains": chains, "summary": {}, "kite_live": True,
                "warning": f"No option chain data for {stock_symbol} at expiry {nearest_expiry}."}




# ── Industry Sectors Heatmap ──────────────────────────────────────────────────

INDUSTRY_SECTOR_MAPPING = {
    "Agri": ["UPL", "PI", "DHANUKA", "RALLIS"],
    "Alcohol": ["MCDOWELL-N", "RADICO", "GLOBUSSPR"],
    "Automobile": ["TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "ASHOKLEY", "TVSMOTOR", "BALKRISIND"],
    "Aviation": ["INDIGO", "SPICEJET"],
    "Bank - Private": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "BANDHANBNK", "RBLBANK", "IDFC", "CUB", "MANAPPURAM"],
    "Bank - Public": ["SBIN", "BANKBARODA", "PNB", "CANBK", "INDIANB", "IOB", "CENTRALBK", "UNIONBANK", "MAHABANK", "BANKINDIA", "UCOBANK", "PSB"],
    "Cement": ["ULTRACEMCO", "SHREECEM", "AMBUJACEM", "ACC", "DALBHARAT", "RAMCOCEM", "JKCEMENT", "BIRLASOFT"],
    "Chemicals": ["PIDILITIND", "AARTI", "DEEPAKNTR", "NAVINFLUOR", "CLEAN", "ATUL", "SRF"],
    "Construction": ["LT", "NBCC", "NCC", "IRCON", "KEC"],
    "Consumer": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "MARICO", "DABUR", "GODREJCP", "TATACONSUM", "COLPAL", "EMAMILTD"],
    "Defence": ["HAL", "BEL", "BDL", "GRSE"],
    "Energy": ["RELIANCE", "ONGC", "BPCL", "IOC", "GAIL", "PETRONET", "NTPC", "POWERGRID", "TATAPOWER", "ADANIGREEN", "NHPC"],
    "Fertilizer": ["COROMANDEL", "CHAMBLFERT", "GNFC", "RCF"],
    "Financial": ["BAJFINANCE", "BAJAJFINSV", "SBILIFE", "HDFCLIFE", "ICICIPRULI", "MFSL", "CHOLAFIN", "SHRIRAMFIN", "M&MFIN", "PEL"],
    "Healthcare": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "LALPATHLAB", "METROPOLIS", "AUROPHARMA", "BIOCON", "LUPIN", "TORNTPHARM"],
    "IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "MPHASIS", "PERSISTENT", "COFORGE", "LTTS"],
    "Infrastructure": ["ADANIPORTS", "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "BRIGADE", "SOBHA", "PHOENIXLTD"],
    "Insurance": ["SBILIFE", "HDFCLIFE", "ICICIPRULI", "NIACL", "STAR"],
    "Logistics": ["CONCOR", "DELHIVERY", "BLUEDART"],
    "Media": ["ZEEL", "SUNTV", "PVRINOX", "NETWORK18"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "NATIONALUM", "NMDC", "COALINDIA", "SAIL", "JINDALSTEL"],
    "Oil & Gas": ["RELIANCE", "ONGC", "BPCL", "IOC", "GAIL", "PETRONET", "HINDPETRO", "MRPL", "GUJGASLTD"],
    "Power": ["NTPC", "POWERGRID", "TATAPOWER", "ADANIGREEN", "NHPC", "SJVN", "IREDA"],
    "Real Estate": ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "BRIGADE", "SOBHA", "PHOENIXLTD"],
    "Retail": ["TRENT", "DMART", "ABFRL", "SHOPERSTOP", "VMART"],
    "Steel": ["TATASTEEL", "JSWSTEEL", "SAIL", "JINDALSTEL", "APLAPOLLO"],
    "Sugar": ["BALRAMCHIN", "SHREERENUKA", "DWARIKESH", "TRIVENI"],
    "Telecom": ["BHARTIARTL", "IDEA", "TTML"],
    "Textile": ["PAGEIND", "RAYMOND", "ARVIND"],
}


@market_data_router.get("/market/industry-sectors")
async def industry_sectors(
    current_user: dict = Depends(get_current_user),
):
    """Return industry sector heatmap data with aggregated live Kite quotes."""
    from services.kite_client import fetch_kite_batch_quotes

    # Collect all unique symbols
    all_symbols = set()
    for stocks in INDUSTRY_SECTOR_MAPPING.values():
        all_symbols.update(stocks)

    # Fetch all quotes in batch
    quotes = await fetch_kite_batch_quotes(list(all_symbols))

    sectors = []
    for sector_name, stocks in sorted(INDUSTRY_SECTOR_MAPPING.items()):
        gainers = 0
        losers = 0
        total_change = 0
        live_count = 0

        for sym in stocks:
            q = quotes.get(sym, {})
            pct = q.get("change_pct", 0)
            if q.get("ltp", 0) > 0:
                live_count += 1
                total_change += pct
                if pct > 0:
                    gainers += 1
                elif pct < 0:
                    losers += 1

        avg_change = round(total_change / max(live_count, 1), 2)

        sectors.append({
            "sector": sector_name,
            "avg_change_pct": avg_change,
            "stock_count": len(stocks),
            "gainers": gainers,
            "losers": losers,
            "live_count": live_count,
        })

    sectors.sort(key=lambda x: x["avg_change_pct"], reverse=True)
    kite_live = any(q.get("ltp", 0) > 0 for q in quotes.values())
    return {"sectors": sectors, "count": len(sectors), "kite_live": kite_live}
