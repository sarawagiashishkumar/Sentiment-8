"""
FNO IV Analytics route handlers.

IV Cone, Term Structure, and manual IV collection endpoints extracted from fno.py.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from deps import get_owner_user

logger = logging.getLogger(__name__)

fno_iv_router = APIRouter()


@fno_iv_router.get("/fno/iv-cone/{symbol}")
async def get_iv_cone(
    symbol: str,
    lookback_days: int = Query(default=365, ge=30, le=730),
    user=Depends(get_owner_user),
):
    """Get IV Cone data with percentile bands for a symbol."""
    import server as _srv
    from services.iv_analytics import compute_iv_cone
    return await compute_iv_cone(_srv.db, symbol.upper(), lookback_days)


@fno_iv_router.get("/fno/iv-term-structure/{symbol}")
async def get_iv_term_structure_endpoint(
    symbol: str,
    user=Depends(get_owner_user),
):
    """Get latest IV term structure for a symbol."""
    import server as _srv
    from services.iv_analytics import get_iv_term_structure
    return await get_iv_term_structure(_srv.db, symbol.upper())


@fno_iv_router.post("/fno/iv-collect-now")
async def collect_iv_now(user=Depends(get_owner_user)):
    """Manual one-shot IV snapshot collection for NIFTY and BANKNIFTY.
    Captures current ATM IV without requiring full signal generation."""
    from services.kite_client import fetch_kite_batch_quotes, fetch_kite_batch_option_quotes
    from services.iv_history import capture_atm_iv
    from services.iv_analytics import capture_iv_term_structure
    import services.app_state as _state

    results = {}
    for symbol in ["NIFTY", "BANKNIFTY"]:
        try:
            step = 50 if symbol == "NIFTY" else 100
            idx_quotes = await fetch_kite_batch_quotes(
                ["NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"], exchange="NSE"
            )
            spot = 0
            for v in idx_quotes.values():
                spot = v.get("ltp", 0)
            if spot <= 0:
                results[symbol] = {"captured": False, "reason": "spot_unavailable"}
                continue

            pipeline = [
                {"$match": {"underlying": symbol}},
                {"$group": {"_id": "$expiry"}},
                {"$sort": {"_id": 1}},
                {"$limit": 3},
            ]
            expiry_docs = await _state.db.kite_option_master.aggregate(pipeline).to_list(3)
            if not expiry_docs:
                results[symbol] = {"captured": False, "reason": "no_option_master"}
                continue

            nearest_expiry = expiry_docs[0]["_id"]
            atm_strike = round(spot / step) * step

            option_rows = await _state.db.kite_option_master.find(
                {"underlying": symbol, "expiry": nearest_expiry, "strike": float(atm_strike)},
                {"_id": 0, "tradingsymbol": 1, "option_type": 1},
            ).to_list(10)

            if option_rows:
                ts_list = [r["tradingsymbol"] for r in option_rows]
                quotes = await fetch_kite_batch_option_quotes(ts_list)
                atm_iv = None
                for ts, q in quotes.items():
                    iv = q.get("iv")
                    if iv and iv > 0:
                        atm_iv = iv / 100 if iv > 1 else iv
                        break

                if atm_iv and atm_iv > 0:
                    await capture_atm_iv(_state.db, symbol, atm_iv)

                    expiry_iv_map = {}
                    for exp_doc in expiry_docs:
                        exp = exp_doc["_id"]
                        exp_atm_rows = await _state.db.kite_option_master.find(
                            {"underlying": symbol, "expiry": exp, "strike": float(atm_strike)},
                            {"_id": 0, "tradingsymbol": 1},
                        ).to_list(5)
                        if exp_atm_rows:
                            exp_ts = [r["tradingsymbol"] for r in exp_atm_rows]
                            exp_quotes = await fetch_kite_batch_option_quotes(exp_ts)
                            for q in exp_quotes.values():
                                if q.get("iv") and q["iv"] > 0:
                                    expiry_iv_map[exp] = q["iv"] / 100 if q["iv"] > 1 else q["iv"]
                                    break

                    if expiry_iv_map:
                        await capture_iv_term_structure(_state.db, symbol, expiry_iv_map)

                    results[symbol] = {"captured": True, "atm_iv": round(atm_iv * 100, 2), "spot": spot, "strike": atm_strike, "expiry": nearest_expiry, "term_expiries": len(expiry_iv_map)}
                else:
                    results[symbol] = {"captured": False, "reason": "no_iv_in_quotes"}
            else:
                results[symbol] = {"captured": False, "reason": "no_atm_options"}
        except Exception as exc:
            logger.warning("IV collect-now failed for %s: %s", symbol, exc)
            results[symbol] = {"captured": False, "reason": str(exc)[:100]}

    return {"results": results}
