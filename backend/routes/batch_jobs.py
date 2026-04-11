"""
Batch Jobs route handlers — Offline MFE/MAE Library, Theta Curves, Forward MFE builders.

All endpoints under /batch/* require owner auth.
Designed for manual or scheduled triggers to pre-compute and cache
probability tables and empirical curves into MongoDB.
"""
from __future__ import annotations

import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from deps import get_owner_user

from services.mfe_mae_engine import (
    build_and_store_mfe_library,
    build_and_store_theta_curves,
    build_and_store_forward_mfe,
    STRATEGY_PROFILES,
    DTE_BANDS,
    IV_REGIMES,
)

logger = logging.getLogger(__name__)

batch_router = APIRouter()


def _srv():
    import server
    return server


class BatchSymbolRequest(BaseModel):
    symbols: Optional[list[str]] = None


async def _build_mfe_for_symbol(db, s, symbol, strategies, dte_values):
    """Build MFE library entries for a single symbol. Returns (results, error)."""
    results = []
    hist_df = await s._get_hist_ohlcv(symbol, period="1y")
    if hist_df is None or hist_df.empty or len(hist_df) < 100:
        return results, {"symbol": symbol, "error": "insufficient_historical_data"}

    close_col = "Close" if "Close" in hist_df.columns else "close"
    closes = hist_df[close_col]
    atr = float(closes.pct_change().rolling(14).std().iloc[-1] * closes.iloc[-1]) if len(closes) > 20 else float(closes.iloc[-1] * 0.012)

    for strat in strategies:
        for dte in dte_values:
            for iv_regime_label, (iv_lo, iv_hi) in IV_REGIMES.items():
                iv_mid = (iv_lo + iv_hi) / 2 if iv_hi < 900 else 35.0
                result = await build_and_store_mfe_library(
                    db, symbol, hist_df, atr,
                    strategy_id=strat, dte=dte, iv=iv_mid,
                )
                if result.get("stored"):
                    results.append({
                        "symbol": symbol, "strategy": strat,
                        "dte": dte, "iv_regime": iv_regime_label,
                        "sample_size": result.get("sample_size", 0),
                    })
    return results, None


@batch_router.post("/build-mfe-library")
async def api_build_mfe_library(
    req: BatchSymbolRequest = BatchSymbolRequest(),
    user=Depends(get_owner_user),
):
    """
    Trigger offline MFE/MAE library build for specified symbols (or defaults).
    This is a heavy operation — run during off-market hours.
    """
    s = _srv()
    db = s.db

    symbols = req.symbols or ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    strategies = ["S1_ORB", "S3_SUPERTREND", "S4_MACD_ADX", "SW1_52W_BREAKOUT"]
    dte_values = [0, 2, 5, 10]

    all_results = []
    errors = []

    for symbol in symbols:
        try:
            sym_results, sym_error = await _build_mfe_for_symbol(db, s, symbol, strategies, dte_values)
            all_results.extend(sym_results)
            if sym_error:
                errors.append(sym_error)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
            logger.warning("MFE library build failed for %s: %s", symbol, exc)

    return {
        "status": "completed",
        "libraries_built": len(all_results),
        "errors": len(errors),
        "details": all_results[:20],
        "error_details": errors,
    }


@batch_router.post("/build-theta-curves")
async def api_build_theta_curves(user=Depends(get_owner_user)):
    """
    Pre-compute and store empirical theta decay curves for all
    (option_class × moneyness × IV regime × DTE) combinations.

    Lightweight operation — purely mathematical, no market data needed.
    """
    s = _srv()
    result = await build_and_store_theta_curves(s.db)
    return {
        "status": "completed",
        "stored_count": result.get("stored_count", 0),
        "total_combos": result.get("combos", 0),
    }


async def _build_fwd_mfe_for_symbol(db, s, symbol, dte_values, regimes):
    """Build forward MFE entries for a single symbol. Returns (results, error)."""
    results = []
    hist_df = await s._get_hist_ohlcv(symbol, period="1y")
    if hist_df is None or hist_df.empty or len(hist_df) < 100:
        return results, {"symbol": symbol, "error": "insufficient_historical_data"}

    close_col = "Close" if "Close" in hist_df.columns else "close"
    closes = hist_df[close_col]
    atr = float(closes.pct_change().rolling(14).std().iloc[-1] * closes.iloc[-1]) if len(closes) > 20 else float(closes.iloc[-1] * 0.012)
    opt_class = "index_weekly" if symbol in ("NIFTY", "BANKNIFTY") else "stock_monthly"

    for dte in dte_values:
        for regime in regimes:
            result = await build_and_store_forward_mfe(
                db, symbol, hist_df, atr,
                remaining_trading_days=dte, regime=regime, option_class=opt_class,
            )
            if result.get("stored"):
                results.append({
                    "symbol": symbol, "dte": dte, "regime": regime,
                    "reliable": result.get("reliable", False),
                    "sample_size": result.get("sample_size", 0),
                })
    return results, None


@batch_router.post("/build-forward-mfe")
async def api_build_forward_mfe(
    req: BatchSymbolRequest = BatchSymbolRequest(),
    user=Depends(get_owner_user),
):
    """Build forward MFE-to-expiry curves for specified symbols."""
    s = _srv()
    db = s.db

    symbols = req.symbols or ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    dte_values = [1, 2, 5, 10, 15]
    regimes = ["LowVolTrend", "LowVolRange", "NormalVolTrend", "HighVolTrend"]

    all_results = []
    errors = []

    for symbol in symbols:
        try:
            sym_results, sym_error = await _build_fwd_mfe_for_symbol(db, s, symbol, dte_values, regimes)
            all_results.extend(sym_results)
            if sym_error:
                errors.append(sym_error)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
            logger.warning("Forward MFE build failed for %s: %s", symbol, exc)

    return {
        "status": "completed",
        "fwd_mfe_built": len(all_results),
        "errors": len(errors),
        "details": all_results[:20],
        "error_details": errors,
    }


@batch_router.get("/status")
async def api_batch_status(user=Depends(get_owner_user)):
    """Get counts of cached MFE libraries, theta curves, and forward MFE entries."""
    s = _srv()
    db = s.db

    mfe_count = await db["mfe_library"].count_documents({})
    theta_count = await db["theta_curves"].count_documents({})
    fwd_count = await db["fwd_mfe"].count_documents({})

    return {
        "mfe_library_entries": mfe_count,
        "theta_curve_entries": theta_count,
        "fwd_mfe_entries": fwd_count,
    }


@batch_router.post("/refresh-equity-cache")
async def api_refresh_equity_cache(user=Depends(get_owner_user)):
    """Refresh equity_master_cache for the F&O + multibagger universe."""
    s = _srv()
    from services import equity_master_cache
    from data.symbols import MULTIBAGGER_UNIVERSE
    from services.research_engine import get_fo_universe

    symbols = list(set(
        list(MULTIBAGGER_UNIVERSE) +
        list(get_fo_universe(lot_size_map=s.LOT_SIZE_MAP))
    ))
    count = await equity_master_cache.refresh_universe(symbols, concurrency=3)
    return {"refreshed": count, "total": len(symbols)}

