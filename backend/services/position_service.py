"""
Position Service — Custom position helpers (refresh, response building, monitoring).

Extracted from server.py for modularity. Uses lazy `import server as _srv`
for accessing server.py globals (db, caches, config) to avoid circular imports.
"""
from __future__ import annotations

import math
import logging
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from models import CustomPositionResponse, FNOContract, MonitoringEvent
from services.utils import to_float as _to_float, utc_now_iso as _utc_now_iso
from services.date_utils import (
    get_minutes_to_expiry,
    get_remaining_trading_days,
    get_nth_trading_day_from_today,
    get_calendar_days_to_date as _get_calendar_days_to_date,
    get_calendar_days_for_nth_trading_day as _get_calendar_days_for_nth_trading_day,
)
from services.data_verifier import (
    compute_vix_theta_decay,
    compute_dynamic_target_revision,
)
from services.position_monitor import check_urgent_exit
from services.research_engine import (
    classify_regime_enhanced,
    generate_position_alerts as generate_monitoring_alerts,
    get_symbol_sentiment,
    transition_signal_state,
)
from services.multibagger_engine import _MONITORING_EVENT_COMMON_KEYS
from services.kite_client import (
    _fetch_live_option_ltp,
    _resolve_verified_lot_size,
)
from services.fno_signal_engine import (
    _compute_initial_option_targets,
    _compute_initial_option_sl,
)

logger = logging.getLogger(__name__)


def _srv():
    """Lazy import server module to avoid circular imports."""
    import server
    return server


def _build_monitoring_events(raw_events: list[dict]) -> list[MonitoringEvent]:
    """Convert raw monitoring event dicts (from MongoDB) to MonitoringEvent models."""
    result: list[MonitoringEvent] = []
    for evt in raw_events:
        details = {k: v for k, v in evt.items() if k not in _MONITORING_EVENT_COMMON_KEYS}
        result.append(MonitoringEvent(
            type=evt.get("type", ""),
            symbol=evt.get("symbol", ""),
            underlying=evt.get("underlying", ""),
            script=evt.get("script", ""),
            direction=evt.get("direction", ""),
            timestamp=evt.get("timestamp", ""),
            severity=evt.get("severity", "MEDIUM"),
            reason=evt.get("reason", ""),
            details=details,
        ))
    return result


def _position_to_response(position: dict) -> CustomPositionResponse:
    lot_size = int(position.get("lot_size", 1))
    quantity_lots = max(1, int(position.get("quantity_lots", 1)))
    units = max(1, lot_size * quantity_lots)
    buy_price = float(position["buy_price"])
    latest_option_ltp = _to_float(position.get("latest_option_ltp"))
    target1 = _to_float(position.get("target1"))
    target2 = _to_float(position.get("target2"))

    target1_achieved = bool(latest_option_ltp is not None and target1 is not None and latest_option_ltp >= target1)
    target2_achieved = bool(latest_option_ltp is not None and target2 is not None and latest_option_ltp >= target2)

    buy_to_ltp_diff = round(float(latest_option_ltp) - buy_price, 2) if latest_option_ltp is not None else None
    buy_to_ltp_pct = round((buy_to_ltp_diff / buy_price) * 100, 2) if (buy_to_ltp_diff is not None and buy_price > 0) else None
    floating_pnl_amount = round((float(latest_option_ltp) - buy_price) * units, 2) if latest_option_ltp is not None else None
    floating_pnl_pct = buy_to_ltp_pct
    ltp_to_t1_diff = round(max(float(target1) - float(latest_option_ltp), 0.0), 2) if (target1 is not None and latest_option_ltp is not None) else None
    ltp_to_t2_diff = round(max(float(target2) - float(latest_option_ltp), 0.0), 2) if (target2 is not None and latest_option_ltp is not None) else None

    sold_price = _to_float(position.get("sold_price"))
    realized_pnl = _to_float(position.get("realized_pnl"))
    if realized_pnl is None and sold_price is not None:
        realized_pnl = round((sold_price - buy_price) * units, 2)

    can_sell = position.get("status") == "OPEN"

    return CustomPositionResponse(
        id=position["id"],
        script=position["script"],
        underlying=position["underlying"],
        expiry_date=position["expiry_date"],
        expiry_time_ist=position.get("expiry_time_ist", "15:30"),
        lot_size=lot_size,
        quantity_lots=quantity_lots,
        units=units,
        buy_price=buy_price,
        created_at=position["created_at"],
        last_update=position["last_update"],
        status=position["status"],
        alert=position.get("alert"),
        latest_option_ltp=latest_option_ltp,
        target1=target1,
        target2=target2,
        buy_to_ltp_diff=buy_to_ltp_diff,
        buy_to_ltp_pct=buy_to_ltp_pct,
        floating_pnl_amount=floating_pnl_amount,
        floating_pnl_pct=floating_pnl_pct,
        ltp_to_t1_diff=ltp_to_t1_diff,
        ltp_to_t2_diff=ltp_to_t2_diff,
        target1_achieved=target1_achieved,
        target2_achieved=target2_achieved,
        can_sell=can_sell,
        sold_price=sold_price,
        realized_pnl=realized_pnl,
        projected_exit_price=position.get("projected_exit_price"),
        best_exit_price=position.get("best_exit_price"),
        best_exit_days=position.get("best_exit_days"),
        best_exit_date_str=position.get("best_exit_date_str"),
        remaining_trading_days=int(position.get("remaining_trading_days") or 0),
        recovery_potential=position.get("recovery_potential"),
        minutes_to_expiry=int(position.get("minutes_to_expiry", 0)),
        revised_exit_plan=position.get("revised_exit_plan", ""),
        monitoring_events=_build_monitoring_events(position.get("monitoring_events", [])),
    )


async def _refresh_open_position(position: dict) -> dict:
    _s = _srv()
    db = _s.db
    IST = _s.IST
    _get_india_vix = _s._get_india_vix
    _get_stock_core_cached = _s._get_stock_core_cached

    corrected_lot_size = int(position.get("lot_size") or 1)
    if corrected_lot_size <= 1:
        corrected_lot_size = await _resolve_verified_lot_size(
            str(position.get("underlying", "")),
            str(position.get("script", "")),
        )

    contract_dict = {
        "script": position["script"],
        "underlying": position["underlying"],
        "expiry": position["expiry_date"],
        "expiry_time_ist": position.get("expiry_time_ist", "15:30"),
        "strike": position["strike"],
        "option_type": position["option_type"],
        "exchange": "NFO",
        "lot_size": corrected_lot_size,
    }
    contract = FNOContract(**contract_dict)
    minutes_to_expiry = get_minutes_to_expiry(contract)

    if minutes_to_expiry <= 0:
        updated = await db.custom_positions.find_one_and_update(
            {"id": position["id"]},
            {
                "$set": {
                    "status": "EXPIRED",
                    "alert": "EXPIRED",
                    "minutes_to_expiry": minutes_to_expiry,
                    "last_update": _utc_now_iso(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return updated

    try:
        latest_option_ltp = await _fetch_live_option_ltp(contract)
    except Exception:
        _last_known_ltp  = float(position.get("latest_option_ltp") or 0)
        _current_be      = float(position.get("best_exit_price") or 0)
        _entry_floor     = round(float(position.get("buy_price") or 0) * 1.01, 2)
        _corrected_be    = max(_current_be, _last_known_ltp, _entry_floor) if _last_known_ltp > 0 else _current_be
        _unavail_update: dict = {
            "alert": "LIVE_LTP_UNAVAILABLE",
            "lot_size": corrected_lot_size,
            "minutes_to_expiry": minutes_to_expiry,
            "last_update": _utc_now_iso(),
            "revised_exit_plan": "Live option feed unavailable; showing last confirmed option LTP.",
        }
        if _corrected_be > _current_be:
            _unavail_update["best_exit_price"] = _corrected_be
        updated = await db.custom_positions.find_one_and_update(
            {"id": position["id"]},
            {"$set": _unavail_update},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return updated

    buy_price = float(position["buy_price"])
    pnl_pct = ((latest_option_ltp - buy_price) / buy_price) if buy_price > 0 else 0.0
    revised_target1 = round(float(position.get("target1") or _compute_initial_option_targets(buy_price)["target1"]), 2)
    revised_target2 = round(float(position.get("target2") or (buy_price * 1.5)), 2)
    projected_exit_price = None
    raw_recovery_potential = ((revised_target1 - latest_option_ltp) / max(latest_option_ltp, 0.01)) if latest_option_ltp > 0 else 0.0
    if minutes_to_expiry <= 120:
        max_recoverable_pct = 0.08
    elif minutes_to_expiry <= 360:
        max_recoverable_pct = 0.10
    else:
        max_recoverable_pct = 0.14
    recovery_potential = max(0.0, min(raw_recovery_potential, max_recoverable_pct))
    best_exit_price = None
    best_exit_days: int | None = None
    best_exit_date_str: str | None = None

    remaining_trading_days = get_remaining_trading_days(position["expiry_date"])

    _today_ist_str = datetime.now(IST).strftime("%Y-%m-%d")
    _exp_raw = position.get("expiry_date") or position.get("expiry") or ""
    try:
        _exp_norm = datetime.strptime(str(_exp_raw), "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        _exp_norm = ""
    _expiry_is_today = (_exp_norm == _today_ist_str)

    if _expiry_is_today:
        best_exit_days = 0
        best_exit_date_str = "Today (Exit Before 3:30 PM)"
        try:
            _pos_entry_sd = float(position.get("buy_price") or 0)
            _pos_vix_sd = await _get_india_vix() if _pos_entry_sd > 0 else 15.0
            if _pos_entry_sd > 0:
                _und_sym_sd = (position.get("underlying") or
                               position.get("script", "").split("2")[0][:10])
                _und_ltp_sd = 0.0
                if _und_sym_sd:
                    try:
                        _und_core_sd = await _get_stock_core_cached(_und_sym_sd.upper())
                        _und_ltp_sd = float(_und_core_sd.get("ltp") or 0)
                    except Exception:
                        pass
                _now_sd = datetime.now(IST)
                _mkt_close_sd = _now_sd.replace(hour=15, minute=30, second=0, microsecond=0)
                _rem_sd = max(1, int((_mkt_close_sd - _now_sd).total_seconds() / 60)) if _now_sd < _mkt_close_sd else 1
                _frac_sd = min(_rem_sd / 375.0, 1.0)
                _vf_sd = 1.3 if _pos_vix_sd > 25 else (1.15 if _pos_vix_sd > 20 else (0.85 if _pos_vix_sd < 12 else 1.0))
                _atr_sd = max(_und_ltp_sd * 0.012, _pos_entry_sd * 0.05) if _und_ltp_sd > 0 else _pos_entry_sd * 0.05
                _ss_sd = _atr_sd * math.sqrt(_frac_sd) * _vf_sd
                _strike_sd = float(position.get("strike") or _pos_entry_sd)
                _type_sd = "CE" if "CE" in position.get("script", "").upper() else "PE"
                _delta_sd = 0.45
                if _und_ltp_sd > 0 and _strike_sd > 0:
                    _m_sd = _und_ltp_sd / _strike_sd if _type_sd == "CE" else _strike_sd / _und_ltp_sd
                    if _m_sd >= 1.08:   _delta_sd = 0.80
                    elif _m_sd >= 1.04: _delta_sd = 0.65
                    elif _m_sd >= 0.97: _delta_sd = 0.45
                    elif _m_sd >= 0.93: _delta_sd = 0.28
                    else:               _delta_sd = 0.15
                _theta_sd = (_pos_entry_sd * _vf_sd * 0.25 / math.sqrt(max(_frac_sd, 0.01))) * _frac_sd
                _peak_sd = _ss_sd * 1.5 * _delta_sd - _theta_sd * 0.5
                _peak_sd = max(_peak_sd, _pos_entry_sd * 0.02)
                _t2_sd = float(position.get("target2") or (_pos_entry_sd * 1.5))
                _raw_sd_exit = round(min(
                    _pos_entry_sd + _peak_sd,
                    _t2_sd * 1.10,
                    _pos_entry_sd * 2.0,
                ), 2)
                _ltp_floor = latest_option_ltp if (latest_option_ltp and latest_option_ltp > 0) else round(_pos_entry_sd * 1.01, 2)
                best_exit_price = max(_raw_sd_exit, _ltp_floor)
            elif latest_option_ltp and latest_option_ltp > 0:
                best_exit_price = latest_option_ltp
        except Exception:
            if latest_option_ltp and latest_option_ltp > 0:
                best_exit_price = latest_option_ltp
    elif remaining_trading_days >= 14:
        best_exit_days = max(1, min(int(remaining_trading_days * 0.6), remaining_trading_days - 1))
    elif remaining_trading_days >= 7:
        best_exit_days = max(1, min(int(remaining_trading_days * 0.7), remaining_trading_days - 1))
    elif remaining_trading_days >= 3:
        best_exit_days = 2
    else:
        best_exit_days = min(1, remaining_trading_days) if remaining_trading_days > 0 else 0

    if best_exit_days and best_exit_days > 0:
        best_exit_date_obj = get_nth_trading_day_from_today(best_exit_days)
        best_exit_date_str = best_exit_date_obj.strftime("%d %b %Y")
        try:
            _pos_entry = float(position.get("buy_price") or 0)
            _pos_vix = await _get_india_vix()
            if _pos_entry > 0:
                _und_sym = (position.get("underlying") or
                            position.get("script", "").split("2")[0][:10])
                _und_ltp = 0.0
                if _und_sym:
                    try:
                        _und_core = await _get_stock_core_cached(_und_sym.upper())
                        _und_ltp = float(_und_core.get("ltp") or 0)
                    except Exception:
                        pass

                _pos_atr_proxy = (
                    max(_und_ltp * 0.012, _pos_entry * 0.05)
                    if _und_ltp > 0 else _pos_entry * 0.05
                )
                _pos_max_move = _pos_atr_proxy * math.sqrt(max(best_exit_days, 1)) * 2.0

                _pos_strike = float(position.get("strike") or _pos_entry)
                _pos_opt_type = "CE" if "CE" in position.get("script", "").upper() else "PE"
                _pos_be_delta = 0.45
                if _und_ltp > 0 and _pos_strike > 0:
                    _pos_mono = (
                        _und_ltp / _pos_strike if _pos_opt_type == "CE"
                        else _pos_strike / _und_ltp
                    )
                    if _pos_mono >= 1.08:   _pos_be_delta = 0.80
                    elif _pos_mono >= 1.04: _pos_be_delta = 0.65
                    elif _pos_mono >= 0.97: _pos_be_delta = 0.45
                    elif _pos_mono >= 0.93: _pos_be_delta = 0.28
                    else:                   _pos_be_delta = 0.15

                _pos_max_gain = _pos_max_move * _pos_be_delta * 1.2
                _pos_target2  = float(position.get("target2") or (_pos_entry * 1.5))
                max_ltp_projection = round(min(
                    _pos_entry + _pos_max_gain,
                    _pos_entry * 3.0,
                    _pos_target2 * 1.20,
                ), 2)

                _cal_to_expiry = (
                    _get_calendar_days_to_date(position["expiry"])
                    if position.get("expiry") else max(remaining_trading_days, 1)
                )
                _cal_to_best_exit = _get_calendar_days_for_nth_trading_day(best_exit_days)
                _pos_theta, _ = compute_vix_theta_decay(
                    entry_price=_pos_entry,
                    remaining_trading_days=remaining_trading_days,
                    best_exit_days=best_exit_days,
                    india_vix=_pos_vix,
                    calendar_days_to_expiry=_cal_to_expiry,
                    calendar_best_exit_days=_cal_to_best_exit,
                )
                _raw_best = round(max_ltp_projection - _pos_theta, 2)
                best_exit_price = max(_raw_best, latest_option_ltp, round(_pos_entry * 1.01, 2))
        except Exception:
            pass

    # Dynamic target revision
    dynamic_revision_note: str | None = None
    revised_exit_plan: str = "Hold with trailing stop once target1 hits"
    try:
        now_ist = datetime.now(IST)
        session_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        mins_to_close = max(0, int((session_close - now_ist).total_seconds() / 60))
        india_vix_for_pos = await _get_india_vix()
        underlying_sym = position.get("underlying") or position.get("script", "").split("2")[0][:10]
        underlying_core = None
        if underlying_sym:
            try:
                underlying_core = await _get_stock_core_cached(underlying_sym.upper())
            except Exception:
                pass
        underlying_ltp_val = float(underlying_core.get("ltp", 0) or 0) if underlying_core else 0.0
        underlying_entry_val = float(position.get("underlying_entry_price", underlying_ltp_val) or underlying_ltp_val)
        option_type_pos = "CE" if "CE" in position.get("script", "").upper() else "PE"
        dir_pos = "BULLISH" if option_type_pos == "CE" else "BEARISH"
        rev_t1, rev_t2, dynamic_revision_note = compute_dynamic_target_revision(
            entry_price=buy_price,
            current_ltp=latest_option_ltp,
            current_t1=revised_target1,
            current_t2=revised_target2,
            underlying_ltp=underlying_ltp_val,
            underlying_entry=underlying_entry_val,
            india_vix=india_vix_for_pos,
            minutes_to_session_close=mins_to_close,
            remaining_trading_days=remaining_trading_days,
            direction=dir_pos,
            original_t1=float(position.get("original_target1") or 0),
            original_t2=float(position.get("original_target2") or 0),
        )
        if rev_t1 > revised_target1:
            revised_target1 = rev_t1
        if rev_t2 > revised_target2:
            revised_target2 = rev_t2
        if dynamic_revision_note:
            revised_exit_plan = dynamic_revision_note
    except Exception as exc:
        logger.warning("Dynamic target revision failed: %s", exc)

    alert = None

    # Compute realistic 60-second optimal advised price
    if latest_option_ltp < 15:
        _increment_60s = 0.20
    elif latest_option_ltp < 30:
        _increment_60s = 0.50
    elif latest_option_ltp < 60:
        _increment_60s = 1.00
    elif latest_option_ltp < 120:
        _increment_60s = 1.50
    elif latest_option_ltp < 200:
        _increment_60s = 2.00
    else:
        _increment_60s = round(latest_option_ltp * 0.007, 1)
    optimal_advised_price = round(latest_option_ltp + _increment_60s, 2)

    if pnl_pct <= -0.35 and recovery_potential <= 0.14:
        alert = "EXIT_NOW_HIGH_LOSS"
        best_exit_price = optimal_advised_price
        revised_exit_plan = (
            f"URGENT EXIT: Loss >35% and recovery potential is weak "
            f"({recovery_potential * 100:.1f}%). Optimal exit near \u20b9{optimal_advised_price} "
            f"(max expected price in next 60 sec)."
        )
    elif minutes_to_expiry <= 15:
        alert = "EXIT_URGENT_TIME"
        best_exit_price = optimal_advised_price
        revised_exit_plan = (
            f"URGENT EXIT: <15 min to expiry. "
            f"Optimal liquidation price: \u20b9{optimal_advised_price} (60-sec window)."
        )
    elif pnl_pct <= -0.12:
        alert = "EXIT_URGENT_LOSS"
        best_exit_price = optimal_advised_price
        revised_exit_plan = (
            f"URGENT EXIT: Loss exceeded 12% from entry. "
            f"Exit now near \u20b9{optimal_advised_price}."
        )
    elif minutes_to_expiry < 60 and ((position["target1"] - latest_option_ltp) / max(latest_option_ltp, 0.01)) > 0.12:
        alert = "RISKY_PREMIUM"
        revised_exit_plan = "High premium-risk near expiry; consider reducing exposure"

    # Research Engine: Enhanced urgent exit detection
    if alert is None:
        now_ist = datetime.now(IST)
        session_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        mins_to_close = max(0, int((session_close - now_ist).total_seconds() / 60))
        urgent_info = check_urgent_exit(
            position={
                "buy_price": position.get("buy_price", 0),
                "remaining_trading_days": remaining_trading_days,
            },
            current_ltp=latest_option_ltp,
            minutes_to_session_close=mins_to_close,
        )
        if urgent_info.get("urgent_exit"):
            alert = "URGENT_EXIT_ENGINE"
            revised_exit_plan = urgent_info["reason"]
            if urgent_info.get("best_price_hint"):
                best_exit_price = urgent_info["best_price_hint"]

    # Batch 5: Signal Lifecycle State Machine
    current_signal_state = position.get("signal_state", "ACTIVE")
    _stored_sl = position.get("stop_loss")
    if _stored_sl and float(_stored_sl) > 0:
        _stop_loss_price = float(_stored_sl)
    else:
        _stop_loss_price = round(float(buy_price) * 0.88, 2)
    option_type_sm = "CE" if "CE" in position.get("script", "").upper() else "PE"
    direction_sm = "BULLISH" if option_type_sm == "CE" else "BEARISH"
    sm_result = transition_signal_state(
        current_state=current_signal_state,
        ltp=latest_option_ltp,
        entry_price=buy_price,
        sl_price=_stop_loss_price,
        t1_price=revised_target1,
        t2_price=revised_target2,
        direction=direction_sm,
        minutes_to_expiry=minutes_to_expiry,
    )
    new_signal_state = sm_result["new_state"]
    if sm_result.get("urgent_exit") and alert is None:
        alert = "URGENT_EXIT_SM"
        revised_exit_plan = sm_result.get("reason", revised_exit_plan)
    if new_signal_state in ("EXPIRED", "CLOSED_LOSS", "CLOSED_WIN", "CANCELLED") and position.get("status") == "OPEN":
        if new_signal_state == "EXPIRED" and alert is None:
            alert = "EXPIRED"
    if new_signal_state in ("WATCHING_SL", "CLOSED_LOSS") and alert is None:
        alert = "SL_WATCH"

    # Batch 4: Position Monitoring & Alerts (Section 8)
    import os
    _monitoring_events: list[dict] = []
    _mon_state_snapshot: dict = {}
    try:
        _mon_underlying = position.get("underlying", "")
        _mon_vix = await _get_india_vix() or 15.0
        _mon_und_ltp = 0.0
        if _mon_underlying:
            try:
                _mon_core = await _get_stock_core_cached(_mon_underlying.upper())
                _mon_und_ltp = float(_mon_core.get("ltp") or 0)
            except Exception:
                pass

        _mon_regime = classify_regime_enhanced(
            india_vix=_mon_vix, realized_vol=None, adx=None,
        )

        _mon_news: dict = {}
        if _mon_underlying:
            try:
                _mon_news = get_symbol_sentiment(_mon_underlying)
            except Exception:
                pass

        _mon_flow_band = "NeutralFlow"

        _mon_prev_regime = position.get("_mon_previous_regime")
        _mon_prev_news_flag = position.get("_mon_previous_news_flag", "NEUTRAL")
        _mon_orig_p_t1 = position.get("_mon_original_p_hit_t1")
        _mon_orig_p_t2 = position.get("_mon_original_p_hit_t2")

        _mon_p_t1 = recovery_potential if recovery_potential is not None else None
        _mon_p_t2 = round(recovery_potential * 0.6, 4) if recovery_potential else None

        _mon_now = datetime.now(IST)
        _mon_close = _mon_now.replace(hour=15, minute=30, second=0, microsecond=0)
        _mon_mins = max(0, int((_mon_close - _mon_now).total_seconds() / 60))

        _mon_p_rec = None
        if pnl_pct < 0 and recovery_potential is not None:
            _mon_p_rec = min(recovery_potential * 2.0, 0.95) if recovery_potential > 0 else 0.05

        _monitoring_events = generate_monitoring_alerts(
            position=position,
            current_ltp=latest_option_ltp,
            entry_price=buy_price,
            stop_loss=_stop_loss_price,
            minutes_remaining=_mon_mins,
            news_sentiment=_mon_news,
            previous_news_flag=_mon_prev_news_flag,
            current_regime=_mon_regime,
            previous_regime=_mon_prev_regime,
            current_p_hit_t1=_mon_p_t1,
            original_p_hit_t1=_mon_orig_p_t1,
            current_p_hit_t2=_mon_p_t2,
            original_p_hit_t2=_mon_orig_p_t2,
            p_recovery=_mon_p_rec,
            flow_band=_mon_flow_band,
        )

        _mon_state_snapshot = {
            "_mon_previous_regime": _mon_regime.get("regime"),
            "_mon_previous_news_flag": _mon_news.get("news_flag", "NEUTRAL"),
        }
        if _mon_orig_p_t1 is None and _mon_p_t1 is not None:
            _mon_state_snapshot["_mon_original_p_hit_t1"] = _mon_p_t1
        if _mon_orig_p_t2 is None and _mon_p_t2 is not None:
            _mon_state_snapshot["_mon_original_p_hit_t2"] = _mon_p_t2

        if _monitoring_events and os.environ.get("MONITORING_LOG_VERBOSE", "1") == "1":
            for _mevt in _monitoring_events:
                logger.info(
                    "MONITOR [%s] %s %s | Sev=%s | %s",
                    _mevt.get("type"), _mevt.get("symbol"), _mevt.get("direction"),
                    _mevt.get("severity"), _mevt.get("reason", "")[:120],
                )
    except Exception as _mon_err:
        logger.debug("Position monitoring failed for %s: %s", position.get("id"), _mon_err)

    updated = await db.custom_positions.find_one_and_update(
        {"id": position["id"]},
        {
            "$set": {
                "latest_option_ltp": round(float(latest_option_ltp), 2),
                "lot_size": corrected_lot_size,
                "target1": revised_target1,
                "target2": revised_target2,
                "stop_loss": _stop_loss_price,
                "signal_state": new_signal_state,
                "signal_state_reason": sm_result.get("reason"),
                "minutes_to_expiry": minutes_to_expiry,
                "alert": alert,
                "projected_exit_price": projected_exit_price,
                "best_exit_price": best_exit_price,
                "best_exit_days": best_exit_days,
                "best_exit_date_str": best_exit_date_str,
                "remaining_trading_days": remaining_trading_days,
                "recovery_potential": round(recovery_potential, 4),
                "last_update": _utc_now_iso(),
                "revised_exit_plan": revised_exit_plan,
                "monitoring_events": _monitoring_events,
                **_mon_state_snapshot,
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return updated
