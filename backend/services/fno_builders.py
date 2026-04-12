"""
F&O Signal Builders — Index projections and stock signal batch generation.

Extracted from fno_signal_engine.py for modularity.
Contains: _build_report, _compute_enhanced_index_breadth,
          _build_index_projection, _build_stock_fno_signals
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Literal

from fastapi import HTTPException

from models import (
    FNOContract,
    FNOSignalResponse,
    IndexAnalysisReport,
    IndexProjectionPane,
    NonDirectionalStrategy,
    StockCoreNormalized,
)

from services.fno_signal_engine import (
    _srv,
    _compute_report_from_rows,
    _format_script,
    build_fno_signal,
    _build_signal_for_contract,
    _safe_signal,
    _get_nearest_expiry,
    compute_underlying_features,
    log_batch1_features,
    _calculate_confluence_score_master_spec,
)
from services.technical_core import compute_full_technical_snapshot
from services.iv_history import capture_atm_iv, get_iv_stats_52w
from services.confluence_score_v2 import CONFLUENCE_THRESHOLD

logger = logging.getLogger(__name__)

async def _build_report(index_name: Literal["NIFTY", "BANKNIFTY"], weighted: bool) -> IndexAnalysisReport:
    _s = _srv()
    NIFTY_WEIGHT_PROXY = _s.NIFTY_WEIGHT_PROXY
    BANKNIFTY_WEIGHT_PROXY = _s.BANKNIFTY_WEIGHT_PROXY
    get_stock_core = _s.get_stock_core
    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY
    symbols = [symbol for symbol, _ in weight_source]
    rows = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_rows = [StockCoreNormalized(**row) for row in rows]
    return _compute_report_from_rows(index_name, weight_source, normalized_rows, weighted)


async def _compute_enhanced_index_breadth(
    index_name: str,
    top_n: int = 12,
) -> dict:
    _s = _srv()
    _get_hist_ohlcv = _s._get_hist_ohlcv
    NIFTY50_WEIGHTS = _s.NIFTY50_WEIGHTS
    BANKNIFTY_WEIGHTS = _s.BANKNIFTY_WEIGHTS
    """
    Compute constituent-weighted index bias using tech snapshots for top N stocks.
    Uses NIFTY50_WEIGHTS / BANKNIFTY_WEIGHTS from research_engine.
    Returns compute_index_constituent_bias() result.
    """
    weights = NIFTY50_WEIGHTS if index_name == "NIFTY" else BANKNIFTY_WEIGHTS
    # Pick top N by weight
    top_symbols = sorted(weights.items(), key=lambda x: -x[1])[:top_n]

    constituent_signals: list[dict] = []

    async def _get_constituent_signal(sym: str, w: float) -> dict | None:
        try:
            hist = await _get_hist_ohlcv(sym, period="3mo")
            if hist is None or len(hist) < 20:
                return None
            ts = compute_full_technical_snapshot(sym, hist)
            return {
                "symbol": sym,
                "tech_bias": ts.get("technical_bias", "NEUTRAL"),
                "direction": ts.get("technical_bias", "NEUTRAL"),
                "conviction": min(
                    1.0,
                    abs(ts.get("bullish_signal_count", 0) - ts.get("bearish_signal_count", 0)) / 10
                ),
                "weight_override": w,
            }
        except Exception:
            return None

    results = await asyncio.gather(*[_get_constituent_signal(sym, w) for sym, w in top_symbols])
    constituent_signals = [r for r in results if r is not None]

    if not constituent_signals:
        return {"available": False, "weighted_bias": "NEUTRAL", "breadth_score": 50}

    bias_result = _srv().compute_index_constituent_bias(constituent_signals, index_name)
    bias_result["constituent_count_fetched"] = len(constituent_signals)
    bias_result["available"] = True

    # ── Batch 1 NEW: Compute enhanced weighted breadth (section 2.2) ─────
    # Convert constituent_signals to format expected by compute_weighted_breadth
    try:
        _breadth_data = []
        for sig in constituent_signals:
            _bias = sig.get("tech_bias", "NEUTRAL")
            _breadth_data.append({
                "symbol": sig["symbol"],
                "weight_pct": sig.get("weight_override", 1.0),
                "in_uptrend": _bias == "BULLISH",
                "above_vwap": _bias in ("BULLISH",),  # proxy when VWAP unavailable
                "intraday_return_pct": 0.0,  # will be enhanced with live data later
                "intraday_volatility": 0.0,
                "rsi": None,
                "macd_bullish": False,
            })
        _weighted_breadth = _srv().compute_weighted_breadth(_breadth_data, index_name)
        bias_result["weighted_breadth"] = _weighted_breadth
        logger.debug(f"{index_name} weighted breadth: {_weighted_breadth.get('breadth_score', 0)}")
    except Exception as _wb_err:
        logger.debug(f"Weighted breadth computation failed for {index_name}: {_wb_err}")

    return bias_result


async def _build_index_projection(index_name: Literal["NIFTY", "BANKNIFTY"], refreshed_at: str) -> IndexProjectionPane:
    _s = _srv()
    IST = _s.IST
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP
    db = _s.db
    _get_stock_core_cached = _s._get_stock_core_cached
    market_data_client = _s.market_data_client
    get_minutes_to_expiry = _s.get_minutes_to_expiry
    _fetch_option_snapshots_from_kite = _s._fetch_option_snapshots_from_kite
    compute_option_chain_analytics = _s.compute_option_chain_analytics
    _get_india_vix = _s._get_india_vix
    _get_hist_ohlcv = _s._get_hist_ohlcv
    _fetch_live_option_snapshot = _s._fetch_live_option_snapshot
    _to_float = _s._to_float
    get_stock_core = _s.get_stock_core
    NIFTY_WEIGHT_PROXY = _s.NIFTY_WEIGHT_PROXY
    BANKNIFTY_WEIGHT_PROXY = _s.BANKNIFTY_WEIGHT_PROXY
    clamp = _s.clamp
    try:
        stock = StockCoreNormalized(**(await _get_stock_core_cached(index_name)))
    except Exception:
        fallback_spot = await asyncio.to_thread(market_data_client.get_index_ltp, index_name)
        stock = StockCoreNormalized(
            symbol=index_name,
            sector="Index",
            ltp=fallback_spot,
            open=fallback_spot,
            high=fallback_spot,
            low=fallback_spot,
            prev_close=fallback_spot,
            volume=0.0,
            market_cap=None,
            pe_ratio=None,
            eps=None,
            book_value=None,
            year_high=fallback_spot,
            year_low=fallback_spot,
        )
    if stock.ltp is None:
        raise HTTPException(status_code=502, detail=f"{index_name} spot unavailable")

    # ── BATCH 1: LOG-ONLY feature audit ──────────────────────────────────
    try:
        _vix = await _get_india_vix()
        _adx_for_regime = None
        try:
            _hist = await _get_hist_ohlcv(index_name, interval="day", candles=30)
            if _hist and _hist.get("closes") and len(_hist["closes"]) >= 14:
                from services.indicators import compute_atr_based_fno_targets
                import pandas as pd
                _h_df = pd.DataFrame({"High": _hist["highs"], "Low": _hist["lows"], "Close": _hist["closes"]})
                _dx_series = pd.Series(dtype=float)
                for i in range(1, len(_h_df)):
                    _plus_dm = max(_h_df["High"].iloc[i] - _h_df["High"].iloc[i-1], 0)
                    _minus_dm = max(_h_df["Low"].iloc[i-1] - _h_df["Low"].iloc[i], 0)
                    _tr = max(_h_df["High"].iloc[i] - _h_df["Low"].iloc[i],
                             abs(_h_df["High"].iloc[i] - _h_df["Close"].iloc[i-1]),
                             abs(_h_df["Low"].iloc[i] - _h_df["Close"].iloc[i-1]))
                    _dx_series.loc[i] = abs(_plus_dm - _minus_dm) / max(_tr, 0.01) * 100
                if len(_dx_series) >= 14:
                    _adx_for_regime = float(_dx_series.rolling(14).mean().iloc[-1])
        except Exception:
            pass
        await log_batch1_features(index_name, db, vix=_vix, adx=_adx_for_regime)
    except Exception as exc:
        logger.debug(f"[BATCH1] Feature audit skipped: {exc}")

    step = 50 if index_name == "NIFTY" else 100
    atm = round(stock.ltp / step) * step
    strike_range_min = atm - 500
    strike_range_max = atm + 500
    expiry = await _get_nearest_expiry(index_name)

    strikes = list(range(int(strike_range_min), int(strike_range_max) + step, step))
    contracts: list[FNOContract] = []
    for strike in strikes:
        for option_type in ["CE", "PE"]:
            contract = FNOContract(
                script=_format_script(index_name, expiry, strike, option_type),
                underlying=index_name,
                expiry=expiry,
                expiry_time_ist="15:30",
                strike=float(strike),
                option_type=option_type,
                exchange="NFO",
                lot_size=LOT_SIZE_MAP.get(index_name, 1),
            )
            if get_minutes_to_expiry(contract) > 15:
                contracts.append(contract)

    rows: list[FNOSignalResponse] = []
    if contracts:
        kite_map = await _fetch_option_snapshots_from_kite(contracts)

        # ── Compute full option chain analytics (Max Pain, PCR, IV Rank, GEX, OI Buildup)
        # All analytics computed in pure Python from live Kite OI/IV/Gamma data (Master Spec).
        _chain_analytics = compute_option_chain_analytics(contracts, kite_map, stock.ltp, step)
        pcr         = _chain_analytics.get("pcr")
        _max_pain   = _chain_analytics.get("max_pain")
        _iv_rank    = _chain_analytics.get("iv_rank")
        _gex        = _chain_analytics.get("gex")
        _oi_buildup = _chain_analytics.get("oi_buildup")
        _atm_iv     = _chain_analytics.get("atm_iv")

        # ── 52-Week IV Rank enrichment ──────────────────────────────────────
        _iv_rank_52w = None
        if _atm_iv and _atm_iv > 0:
            try:
                await capture_atm_iv(db, index_name, _atm_iv)
                _iv_52w = await get_iv_stats_52w(db, index_name, _atm_iv)
                _iv_rank_52w = _iv_52w.get("iv_rank_52w")
            except Exception:
                pass  # Non-fatal: 52-week IV is enrichment only

        # ── Fetch India VIX ──────────────────────────────────────────────────
        india_vix = await _get_india_vix()

        # ── Fetch index historical OHLCV for tech snapshot ───────────────────
        index_tech_snap: dict = {}
        try:
            # Kite is the sole historical data source
            hist_index = await _get_hist_ohlcv(index_name.replace("^", ""), period="6mo")
            if hist_index is not None and not hist_index.empty:
                index_tech_snap = compute_full_technical_snapshot(index_name, hist_index, ltp=stock.ltp)
        except Exception as exc:
            logger.warning(f"Index tech snapshot failed for {index_name}: {exc}")

        for contract in contracts:
            minutes_to_expiry = get_minutes_to_expiry(contract)
            try:
                snapshot = kite_map.get(contract.script)
                if snapshot is None:
                    snapshot = await _fetch_live_option_snapshot(contract)
                option_ltp = float(snapshot.get("ltp"))
                signal = await build_fno_signal(
                    contract,
                    stock,
                    option_ltp,
                    refreshed_at,
                    minutes_to_expiry,
                    option_day_high=_to_float(snapshot.get("day_high")),
                    option_day_low=_to_float(snapshot.get("day_low")),
                    india_vix=india_vix,
                    pcr=pcr,
                    tech_snapshot=index_tech_snap,
                    fundamental={},  # Index has no individual fundamental data
                    max_pain=_max_pain,
                    iv_rank=_iv_rank,
                    iv_rank_52w=_iv_rank_52w,
                    atm_iv=_atm_iv,
                    oi_buildup=_oi_buildup,
                    gex=_gex,
                )
                rows.append(signal)
            except HTTPException:
                continue
            except Exception:
                continue

    directional_candidates = [
        item
        for item in rows
        if item is not None and item.direction != "NEUTRAL" and item.confluence_score >= CONFLUENCE_THRESHOLD and item.risk_reward_target2 >= 1.3
    ]
    by_strike: dict[float, list[FNOSignalResponse]] = defaultdict(list)
    for row in directional_candidates:
        by_strike[row.strike].append(row)

    paired_scripts = set()
    non_directional: list[NonDirectionalStrategy] = []
    for strike, entries in by_strike.items():
        ce = next((item for item in entries if item.option_type == "CE"), None)
        pe = next((item for item in entries if item.option_type == "PE"), None)
        if ce and pe:
            paired_scripts.add(ce.script)
            paired_scripts.add(pe.script)
            non_directional.append(
                NonDirectionalStrategy(
                    strike=strike,
                    strategy="Long Straddle (Non-Directional Strategy)",
                    ce_script=ce.script,
                    pe_script=pe.script,
                    combined_entry=round(ce.entry_price + pe.entry_price, 2),
                    rationale=(
                        "Both CE and PE at same strike passed profitability checks. "
                        "Classified as volatility strategy, not assured directional signal."
                    ),
                    confidence_score=int(round((ce.confluence_score + pe.confluence_score) / 2)),
                )
            )

    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY

    async def _safe_report_core(symbol: str) -> dict:
        try:
            return await _get_stock_core_cached(symbol)
        except Exception:
            return {
                "symbol": symbol,
                "sector": "Unknown",
                "ltp": None,
                "open": None,
                "high": None,
                "low": None,
                "prev_close": None,
                "volume": 0.0,
                "market_cap": None,
                "pe_ratio": None,
                "eps": None,
                "book_value": None,
                "year_high": None,
                "year_low": None,
            }

    report_rows = await asyncio.gather(*[_safe_report_core(symbol) for symbol, _ in weight_source])
    normalized_report_rows = [StockCoreNormalized(**row) for row in report_rows]
    with_report = _compute_report_from_rows(index_name, weight_source, normalized_report_rows, weighted=True)
    without_report = _compute_report_from_rows(index_name, weight_source, normalized_report_rows, weighted=False)

    expected_direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = with_report.bias

    # Filter out None items first (may occur if a signal build fails for an individual strike)
    rows = [r for r in rows if r is not None]

    assured_signals = [
        item
        for item in rows
        if item.script not in paired_scripts
        and strike_range_min <= item.strike <= strike_range_max
        and item.direction != "NEUTRAL"
        and expected_direction != "NEUTRAL"
        and item.direction == expected_direction
        and item.confluence_score >= 58
        and item.risk_reward_target2 >= 1.2
        and item.risk_reward_target1 >= 0.8
        and item.expiry_risk != "HIGH"
        and (item.target1 - item.entry_price) / max(item.entry_price, 0.01) <= 0.18
    ]
    assured_signals.sort(key=lambda row: row.confluence_score, reverse=True)

    watchlist_signals: list[FNOSignalResponse] = []

    if len(assured_signals) < 2:
        fallback_candidates = [
            item
            for item in rows
            if item.script not in paired_scripts
            and strike_range_min <= item.strike <= strike_range_max
            and item.expiry_risk != "HIGH"
            and item.direction != "NEUTRAL"
            and item.confluence_score >= 45
            and item.risk_reward_target2 >= 1.2
        ]
        fallback_candidates.sort(key=lambda row: row.confluence_score, reverse=True)
        
        existing_scripts = {s.script for s in assured_signals}
        for candidate in fallback_candidates:
            if candidate.script not in existing_scripts:
                assured_signals.append(
                    candidate.model_copy(update={
                        "strategy": f"{candidate.conviction_level} Conviction Trade (Neutral Market)"
                    })
                )
                if len(assured_signals) >= 2:
                    break
        
        if len(assured_signals) < 2 and len(rows) > 0:
            all_available = [
                item for item in rows
                if item.expiry_risk != "HIGH"
                and item.script not in paired_scripts
                and item.risk_reward_target2 >= 1.2
            ]
            all_available.sort(key=lambda row: row.confluence_score, reverse=True)
            
            existing_scripts = {s.script for s in assured_signals}
            for candidate in all_available:
                if candidate.script not in existing_scripts:
                    assured_signals.append(
                        candidate.model_copy(update={
                            "strategy": f"Best Available Trade (Score: {candidate.confluence_score})"
                        })
                    )
                    if len(assured_signals) >= 2:
                        break

    directional_count = len([item for item in rows if item.direction != "NEUTRAL"])
    high_conf_count = len([item for item in rows if item.confluence_score >= 80])
    medium_conf_count = len([item for item in rows if 70 <= item.confluence_score < 80])
    bias_aligned_count = (
        len([item for item in rows if item.direction == expected_direction])
        if expected_direction != "NEUTRAL"
        else 0
    )
    rejection_note = None
    if not assured_signals:
        if expected_direction == "NEUTRAL":
            rejection_note = (
                f"No trade: weighted {index_name} bias is NEUTRAL. "
                f"Directional contracts: {directional_count}/{len(rows)}."
            )
        else:
            rejection_note = (
                f"No trade: bias-aligned contracts {bias_aligned_count}/{len(rows)} did not pass strict gates. "
                f"High-confluence={high_conf_count}, Medium-confluence={medium_conf_count}."
            )

    return IndexProjectionPane(
        index_name=index_name,
        spot=round(stock.ltp, 2),
        strike_range_min=float(strike_range_min),
        strike_range_max=float(strike_range_max),
        assured_signals=assured_signals[:4],  # Cap: top 4 per index
        watchlist_signals=watchlist_signals[:8],
        non_directional_strategies=non_directional,
        rejection_note=rejection_note,
        with_consolidated_report=with_report,
        without_consolidated_report=without_report,
    )


async def _build_stock_fno_signals(refreshed_at: str) -> list[FNOSignalResponse]:
    _s = _srv()
    db = _s.db
    LOT_SIZE_MAP = _s.LOT_SIZE_MAP
    get_stock_core = _s.get_stock_core
    get_minutes_to_expiry = _s.get_minutes_to_expiry
    _get_india_vix = _s._get_india_vix
    _get_fundamental_data = _s._get_fundamental_data
    check_stock_eligibility = _s.check_stock_eligibility
    _get_hist_ohlcv = _s._get_hist_ohlcv
    _resolve_verified_lot_size = _s._resolve_verified_lot_size
    _fetch_option_snapshots_from_kite = _s._fetch_option_snapshots_from_kite
    compute_option_chain_analytics = _s.compute_option_chain_analytics
    _fetch_live_option_snapshot = _s._fetch_live_option_snapshot
    _to_float = _s._to_float
    from services.fo_universe import get_fo_universe
    # ── Mini-Batch: Use full F&O universe instead of hardcoded 14 stocks ──
    all_symbols = get_fo_universe(lot_size_map=LOT_SIZE_MAP, include_indices=False)
    logger.info(f"F&O universe: {len(all_symbols)} total symbols")

    # ── Pre-filter: Only process symbols that have lot sizes and option data ──
    # This avoids fetching data for 181 symbols when most won't have live chains.
    # First: Get symbols that exist in kite_option_master (have option chains)
    available_in_kite: set[str] = set()
    try:
        coll = db.get_collection("kite_option_master")
        db_underlyings = await coll.distinct("underlying")
        available_in_kite = {u for u in db_underlyings if u and u not in ("NIFTY", "BANKNIFTY")}
    except Exception:
        pass

    # If Kite data available, filter to those. Otherwise use LOT_SIZE_MAP stocks.
    if available_in_kite:
        symbols = sorted(available_in_kite & set(all_symbols))
    else:
        # Fallback: use all symbols that have lot sizes
        symbols = [s for s in all_symbols if s in LOT_SIZE_MAP]

    # Safety cap: process max 40 stocks to stay within gateway timeout
    MAX_SCAN = 40
    if len(symbols) > MAX_SCAN:
        # Prioritize: pick a diverse set — large-cap names first + random others
        _priority = [
            "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "LT",
            "BAJFINANCE", "ITC", "KOTAKBANK", "AXISBANK", "TATAMOTORS", "MARUTI",
            "SUNPHARMA", "BHARTIARTL", "HCLTECH", "WIPRO", "TITAN", "ADANIENT",
            "M&M", "NTPC", "TATASTEEL", "DRREDDY", "CIPLA", "HINDALCO",
        ]
        priority_set = [s for s in _priority if s in symbols]
        remaining = [s for s in symbols if s not in _priority]
        symbols = (priority_set + remaining)[:MAX_SCAN]

    logger.info(f"Building stock F&O signals for {len(symbols)} symbols (from {len(all_symbols)} universe)")
    cores = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])
    normalized_cores = [StockCoreNormalized(**row) for row in cores]
    semaphore = asyncio.Semaphore(8)  # Higher concurrency for speed

    # Fetch India VIX once for all stock signals
    india_vix = await _get_india_vix()

    async def _build_for_symbol(symbol: str, core: StockCoreNormalized) -> FNOSignalResponse | None:
        if core.ltp is None:
            logger.warning(f"{symbol}: No LTP available")
            return None

        # ── Eligibility filter ────────────────────────────────────────────
        fundamental = await _get_fundamental_data(symbol)
        eligibility = check_stock_eligibility(
            ltp=core.ltp,
            market_cap_cr=None,
            fundamental=fundamental,
        )
        if not eligibility["eligible"]:
            logger.info(f"{symbol}: DISQUALIFIED — {', '.join(eligibility['flags'])}")
            return None

        # ── Research engine: fetch historical OHLCV and compute technicals ─
        tech_snap: dict = {}
        try:
            hist_df = await _get_hist_ohlcv(symbol, period="6mo")
            if hist_df is not None and not hist_df.empty:
                tech_snap = compute_full_technical_snapshot(symbol, hist_df, ltp=core.ltp)
        except Exception as exc:
            logger.warning(f"{symbol}: tech snapshot failed: {exc}")

        step = 20 if core.ltp > 400 else 10
        strike = round(core.ltp / step) * step
        logger.info(f"{symbol}: LTP={core.ltp}, Strike={strike}, Eligible=True")

        async with semaphore:
            expiry = await _get_nearest_expiry(symbol, prefer_monthly=True)
            lot_size_val = await _resolve_verified_lot_size(symbol, None)

            # ── Option chain analytics: fetch ±5 strikes for PCR / Max Pain / GEX / OI Buildup ──
            _n_extra = 5
            _ana_contracts = [
                FNOContract(
                    script=_format_script(symbol, expiry, float(k), ot),
                    underlying=symbol,
                    expiry=expiry,
                    expiry_time_ist="15:30",
                    strike=float(k),
                    option_type=ot,
                    exchange="NFO",
                    lot_size=lot_size_val,
                )
                for k in range(
                    int(strike - _n_extra * step),
                    int(strike + _n_extra * step + step),
                    step,
                )
                for ot in ["CE", "PE"]
            ]
            _ana_kite_map: dict[str, dict] = {}
            try:
                _ana_kite_map = await _fetch_option_snapshots_from_kite(_ana_contracts)
            except Exception:
                pass
            _stock_analytics: dict = {}
            _stock_iv_rank_52w = None
            if _ana_kite_map:
                _stock_analytics = compute_option_chain_analytics(
                    _ana_contracts, _ana_kite_map, core.ltp, step
                )
                # ── 52-Week IV Rank for stock ────────────────────────
                _stock_atm_iv = _stock_analytics.get("atm_iv")
                if _stock_atm_iv and _stock_atm_iv > 0:
                    try:
                        await capture_atm_iv(db, symbol, _stock_atm_iv)
                        _iv_52 = await get_iv_stats_52w(db, symbol, _stock_atm_iv)
                        _stock_iv_rank_52w = _iv_52.get("iv_rank_52w")
                    except Exception:
                        pass

            symbol_rows: list[FNOSignalResponse] = []
            for option_type in ["CE", "PE"]:
                contract = FNOContract(
                    script=_format_script(symbol, expiry, strike, option_type),
                    underlying=symbol,
                    expiry=expiry,
                    expiry_time_ist="15:30",
                    strike=float(strike),
                    option_type=option_type,
                    exchange="NFO",
                    lot_size=lot_size_val,
                )
                minutes_to_expiry = get_minutes_to_expiry(contract)
                if minutes_to_expiry <= 15:
                    logger.warning(f"{symbol} {option_type}: Expiry too soon ({minutes_to_expiry}m)")
                    continue

                # Reuse snapshot from analytics map if available; else fetch individually
                snapshot = _ana_kite_map.get(contract.script)
                if snapshot is None:
                    try:
                        snapshot = await _fetch_live_option_snapshot(contract)
                    except Exception as exc:
                        logger.warning(f"{symbol} {option_type}: Failed to fetch snapshot: {exc}")
                        continue
                option_ltp = _to_float(snapshot.get("ltp"))
                if option_ltp is None or option_ltp <= 0:
                    logger.warning(f"{symbol} {option_type}: Invalid LTP: {option_ltp}")
                    continue

                try:
                    signal = await build_fno_signal(
                        contract,
                        core,
                        float(option_ltp),
                        refreshed_at,
                        minutes_to_expiry,
                        option_day_high=_to_float(snapshot.get("day_high")),
                        option_day_low=_to_float(snapshot.get("day_low")),
                        india_vix=india_vix,
                        tech_snapshot=tech_snap,
                        fundamental=fundamental,
                        max_pain=_stock_analytics.get("max_pain"),
                        iv_rank=_stock_analytics.get("iv_rank"),
                        iv_rank_52w=_stock_iv_rank_52w,
                        atm_iv=_stock_analytics.get("atm_iv"),
                        oi_buildup=_stock_analytics.get("oi_buildup"),
                        gex=_stock_analytics.get("gex"),
                    )
                    if signal is None:
                        logger.warning(f"{symbol} {option_type}: build_fno_signal returned None")
                        continue
                    logger.info(f"{symbol} {option_type}: Signal generated - Direction={signal.direction}, Confluence={signal.confluence_score}, Conviction={signal.conviction_level}")
                except HTTPException as exc:
                    logger.warning(f"{symbol} {option_type}: Signal generation failed: {exc.detail}")
                    continue

                if signal.direction != "NEUTRAL":
                    symbol_rows.append(signal)
                else:
                    logger.info(f"{symbol} {option_type}: Direction is NEUTRAL, skipping")

            if not symbol_rows:
                logger.info(f"{symbol}: No non-NEUTRAL signals")
                return None

            logger.info(f"{symbol}: {len(symbol_rows)} signals before filtering")
            
            # Enforce minimum confluence score per Master Spec requirement
            potential = [
                row
                for row in symbol_rows
                if row.confluence_score >= CONFLUENCE_THRESHOLD
                and row.risk_reward_target2 >= 1.2
                and row.expiry_risk != "HIGH"
            ]
            
            if potential:
                potential.sort(key=lambda row: row.confluence_score, reverse=True)
                logger.info(f"{symbol}: QUALIFIED - Confluence={potential[0].confluence_score}, Conviction={potential[0].conviction_level}")
                return potential[0]
            else:
                for row in symbol_rows:
                    reasons = []
                    if row.confluence_score < CONFLUENCE_THRESHOLD:
                        reasons.append(f"Confluence {row.confluence_score} < {CONFLUENCE_THRESHOLD} (minimum required)")
                    if row.risk_reward_target2 < 1.2:
                        reasons.append(f"R:R {row.risk_reward_target2:.2f} < 1.2")
                    if row.expiry_risk == "HIGH":
                        reasons.append("HIGH expiry risk")
                    if reasons:
                        logger.info(f"{symbol} {row.option_type}: {', '.join(reasons)}")
                return None

    built = await asyncio.gather(*[_build_for_symbol(symbol, normalized_cores[idx]) for idx, symbol in enumerate(symbols)])
    results = [item for item in built if item is not None]
    results.sort(key=lambda row: row.confluence_score, reverse=True)
    
    logger.info(f"Stock F&O signals: {len(results)} total from {len(symbols)}-symbol universe, returning top 10")
    return results[:10]

