"""
Sticky Card Engine — Batch 4 Items 4 & 5.

Implements:
- Sticky card state machine (PENDING→ACTIVE→...→CLOSED)
- Refresh cycle for live position monitoring
- POPUP_EVENTS: NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT
- Event storage in MongoDB with de-duplication

MongoDB collections:
- sticky_fno_cards: Live signal cards with state machine
- fno_popup_events: Emitted alert events with acknowledged flag
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Literal

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------
COLL_STICKY_CARDS = "sticky_fno_cards"
COLL_POPUP_EVENTS = "fno_popup_events"

# De-duplication window (same event_type + signal_id)
EVENT_DEDUP_MINUTES = 5

# ---------------------------------------------------------------------------
# State Machine States
# ---------------------------------------------------------------------------
VALID_STATES = [
    "PENDING", "ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2",
    "CLOSED_WIN", "CLOSED_LOSS", "EXPIRED", "CANCELLED",
]
TERMINAL_STATES = {"CLOSED_WIN", "CLOSED_LOSS", "EXPIRED", "CANCELLED"}
ACTIVE_STATES = {"PENDING", "ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2"}


# ---------------------------------------------------------------------------
# Index creation
# ---------------------------------------------------------------------------

async def ensure_indexes(db) -> None:
    """Create indexes for sticky cards and popup events."""
    await db[COLL_STICKY_CARDS].create_index(
        [("signal_id", 1)], unique=True, name="sticky_signal_id_unique",
    )
    await db[COLL_STICKY_CARDS].create_index(
        [("signal_state", 1), ("symbol", 1)], name="sticky_state_symbol",
    )
    await db[COLL_POPUP_EVENTS].create_index(
        [("signal_id", 1), ("event_type", 1), ("emitted_at", -1)],
        name="event_signal_type_time",
    )
    await db[COLL_POPUP_EVENTS].create_index(
        [("acknowledged", 1)], name="event_acknowledged",
    )
    logger.info("Sticky card + popup event indexes ensured")


# ---------------------------------------------------------------------------
# Sticky Card CRUD
# ---------------------------------------------------------------------------

async def create_sticky_card(db, signal_data: dict) -> str:
    """
    Create a new sticky card from a signal response.
    Returns signal_id.
    """
    signal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    doc = {
        "signal_id": signal_id,
        "symbol": signal_data.get("underlying", ""),
        "option_symbol": signal_data.get("script", ""),
        "direction": "LONG" if signal_data.get("direction") == "BULLISH" else "SHORT",
        "strategy": signal_data.get("strategy_library_id", ""),
        "entry_price": signal_data.get("entry_price", 0),
        "entry_zone_low": signal_data.get("best_budget_entry") or signal_data.get("entry_price", 0) * 0.97,
        "entry_zone_high": signal_data.get("entry_price", 0) * 1.01,
        "sl": signal_data.get("stop_loss", 0),
        "T1": signal_data.get("target1"),
        "T2": signal_data.get("target2"),
        "best_exit_label": "MFE Best Exit",
        "best_exit_price": signal_data.get("best_exit_price"),
        "near_expiry": signal_data.get("near_expiry_badge", False),
        "signal_state": "PENDING",
        "confluence_score_v2": signal_data.get("confluence_score_v2") or signal_data.get("confluence_score", 0),
        "score_bucket_A": signal_data.get("score_bucket_A"),
        "score_bucket_B": signal_data.get("score_bucket_B"),
        "score_bucket_C": signal_data.get("score_bucket_C"),
        "score_bucket_D": signal_data.get("score_bucket_D"),
        "regime_label": signal_data.get("score_regime_label", ""),
        "flow_band": signal_data.get("score_flow_band", "NeutralFlow"),
        "news_flag": signal_data.get("score_news_flag", "NEUTRAL"),
        "last_p_hit_T1": None,
        "last_p_hit_T2": None,
        "last_p_recover_entry": None,
        "current_price": signal_data.get("option_ltp", 0),
        "theta_remaining": None,
        "last_refreshed_at": now,
        "created_at": now,
        "closed_at": None,
        "close_reason": None,
    }

    await db[COLL_STICKY_CARDS].insert_one(doc)
    return signal_id


async def get_active_cards(db) -> list[dict]:
    """Get all non-terminal sticky cards."""
    cursor = db[COLL_STICKY_CARDS].find(
        {"signal_state": {"$nin": list(TERMINAL_STATES)}},
        {"_id": 0},
    )
    return await cursor.to_list(length=500)


async def get_card_by_id(db, signal_id: str) -> dict | None:
    """Get a single sticky card by signal_id."""
    return await db[COLL_STICKY_CARDS].find_one(
        {"signal_id": signal_id}, {"_id": 0},
    )


async def get_watch_list_symbols(db) -> list[str]:
    """Get unique symbols from all active sticky cards."""
    cards = await get_active_cards(db)
    return list(set(c["symbol"] for c in cards if c.get("symbol")))


async def update_card(db, signal_id: str, updates: dict) -> bool:
    """Update specific fields on a sticky card."""
    updates["last_refreshed_at"] = datetime.now(timezone.utc)
    result = await db[COLL_STICKY_CARDS].update_one(
        {"signal_id": signal_id}, {"$set": updates},
    )
    return result.modified_count > 0


async def close_card(db, signal_id: str, state: str, reason: str) -> bool:
    """Transition card to a terminal state."""
    return await update_card(db, signal_id, {
        "signal_state": state,
        "closed_at": datetime.now(timezone.utc),
        "close_reason": reason,
    })


# ---------------------------------------------------------------------------
# State Machine Transitions (Item 4)
# ---------------------------------------------------------------------------

def evaluate_state_transition(
    card: dict,
    current_price: float,
    atr14: float = 0,
    is_expiry_day: bool = False,
    is_past_close: bool = False,
) -> tuple[str, str | None]:
    """
    Evaluate state machine transitions for a sticky card.

    Returns: (new_state, close_reason) — if state unchanged, returns (current_state, None)
    """
    state = card.get("signal_state", "PENDING")
    direction = card.get("direction", "LONG")
    sl = card.get("sl", 0)
    t1 = card.get("T1")
    t2 = card.get("T2")
    entry_low = card.get("entry_zone_low", 0)
    entry_high = card.get("entry_zone_high", 0)
    sl_proximity = atr14 * 0.5 if atr14 > 0 else abs(current_price * 0.02)

    # Terminal check: expiry at 15:30 on expiry day
    if is_expiry_day and is_past_close:
        return "EXPIRED", "expiry_day_session_close"

    # Universal SL check (any active state → CLOSED_LOSS)
    if state in ACTIVE_STATES - {"PENDING"}:
        if direction == "LONG" and current_price <= sl:
            return "CLOSED_LOSS", f"sl_hit_at_{current_price:.2f}"
        if direction == "SHORT" and current_price >= sl:
            return "CLOSED_LOSS", f"sl_hit_at_{current_price:.2f}"

    if state == "PENDING":
        # Fill detection
        if direction == "LONG" and current_price >= entry_low:
            return "ACTIVE", None
        if direction == "SHORT" and current_price <= entry_high:
            return "ACTIVE", None

    elif state == "ACTIVE":
        # Check SL proximity
        if direction == "LONG" and current_price <= sl + sl_proximity:
            return "WATCHING_SL", None
        if direction == "SHORT" and current_price >= sl - sl_proximity:
            return "WATCHING_SL", None
        # Check T1 hit
        if t1:
            if direction == "LONG" and current_price >= t1:
                return "WATCHING_T1", None
            if direction == "SHORT" and current_price <= t1:
                return "WATCHING_T1", None

    elif state == "WATCHING_SL":
        # Recovery: price moved away from SL
        if direction == "LONG" and current_price > sl + sl_proximity * 2:
            return "ACTIVE", None
        if direction == "SHORT" and current_price < sl - sl_proximity * 2:
            return "ACTIVE", None

    elif state == "WATCHING_T1":
        if t2 is not None:
            return "WATCHING_T2", None
        else:
            # No T2 → book profit at T1
            return "CLOSED_WIN", f"t1_hit_no_t2_at_{current_price:.2f}"

    elif state == "WATCHING_T2":
        if t2:
            if direction == "LONG" and current_price >= t2:
                return "CLOSED_WIN", f"t2_hit_at_{current_price:.2f}"
            if direction == "SHORT" and current_price <= t2:
                return "CLOSED_WIN", f"t2_hit_at_{current_price:.2f}"

    return state, None


# ---------------------------------------------------------------------------
# Refresh Cycle (Item 4)
# ---------------------------------------------------------------------------

async def refresh_sticky_cards(db, fetch_live_price_fn=None) -> dict:
    """
    Single refresh cycle for all active sticky cards.
    Fetches live prices, evaluates state transitions, updates MongoDB.

    Returns: {refreshed: int, state_changes: int, events: int}
    """
    cards = await get_active_cards(db)
    if not cards:
        return {"refreshed": 0, "state_changes": 0, "events": 0}

    now_ist = datetime.now(IST)
    is_past_close = now_ist.hour >= 15 and now_ist.minute >= 30
    refreshed = 0
    state_changes = 0

    for card in cards:
        try:
            # Fetch live price (via callback or use stored price)
            current_price = card.get("current_price", 0)
            if fetch_live_price_fn:
                try:
                    live = await fetch_live_price_fn(card["option_symbol"])
                    if live and live > 0:
                        current_price = live
                except Exception:
                    pass

            # Determine if expiry day
            is_expiry_day = card.get("near_expiry", False)

            # Evaluate state machine
            new_state, close_reason = evaluate_state_transition(
                card, current_price,
                is_expiry_day=is_expiry_day,
                is_past_close=is_past_close,
            )

            # Build update dict
            updates = {"current_price": current_price}

            if new_state != card["signal_state"]:
                updates["signal_state"] = new_state
                state_changes += 1
                if new_state in TERMINAL_STATES:
                    updates["closed_at"] = datetime.now(timezone.utc)
                    updates["close_reason"] = close_reason
                logger.info(
                    f"StickyCard {card['signal_id'][:8]}: "
                    f"{card['signal_state']} -> {new_state} "
                    f"(price={current_price}, reason={close_reason})"
                )

            await update_card(db, card["signal_id"], updates)
            refreshed += 1

        except Exception as e:
            logger.warning(f"Sticky card refresh failed for {card.get('signal_id', '?')}: {e}")

    return {"refreshed": refreshed, "state_changes": state_changes, "events": 0}


# ---------------------------------------------------------------------------
# POPUP_EVENTS (Item 5)
# ---------------------------------------------------------------------------

async def emit_event(db, event: dict) -> bool:
    """
    Emit a popup event with de-duplication.
    Returns True if event was stored (not a duplicate).
    """
    signal_id = event.get("signal_id", "")
    event_type = event.get("event_type", "")

    # De-duplication: check if same event_type for same signal_id within 5 minutes
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=EVENT_DEDUP_MINUTES)
    existing = await db[COLL_POPUP_EVENTS].find_one({
        "signal_id": signal_id,
        "event_type": event_type,
        "emitted_at": {"$gte": cutoff},
    })
    if existing:
        logger.debug(f"Event dedup: {event_type} for {signal_id[:8]} (within {EVENT_DEDUP_MINUTES}m)")
        return False

    doc = {
        "event_id": str(uuid.uuid4()),
        "signal_id": signal_id,
        "event_type": event_type,
        "payload": event,
        "emitted_at": datetime.now(timezone.utc),
        "acknowledged": False,
    }
    await db[COLL_POPUP_EVENTS].insert_one(doc)
    logger.info(f"Event emitted: {event_type} for signal {signal_id[:8]}")
    return True


async def emit_news_impact(
    db, card: dict, prev_flag: str, curr_flag: str, agg_result: dict,
) -> bool:
    """
    EVENT 1: NEWS_IMPACT — Adverse sentiment shift detected.

    Trigger: (LONG + new NEGATIVE) OR (SHORT + new POSITIVE)
    and signal_state is ACTIVE/WATCHING_*
    """
    direction = card.get("direction", "LONG")
    state = card.get("signal_state", "PENDING")

    if state not in {"ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2"}:
        return False

    should_trigger = False
    if direction == "LONG" and prev_flag != "NEGATIVE" and curr_flag == "NEGATIVE":
        should_trigger = True
    elif direction == "SHORT" and prev_flag != "POSITIVE" and curr_flag == "POSITIVE":
        should_trigger = True

    if not should_trigger:
        return False

    now_ist = datetime.now(IST)
    event = {
        "event_type": "NEWS_IMPACT",
        "signal_id": card["signal_id"],
        "symbol": card["symbol"],
        "option_symbol": card["option_symbol"],
        "direction": direction,
        "news_flag": curr_flag,
        "avg_sentiment": agg_result.get("avg_sentiment", 0.0),
        "timestamp": now_ist.isoformat(),
        "headline_summary": agg_result.get("headline_summary", ""),
        "display_text": (
            f"News Impact -- {card['symbol']}: Sentiment shifted to {curr_flag} "
            f"(Score: {agg_result.get('avg_sentiment', 0):+.2f}) at {now_ist.strftime('%H:%M')}. "
            f"Recent: {agg_result.get('headline_summary', '')[:120]}"
        ),
    }
    return await emit_event(db, event)


async def emit_regime_shift(
    db, card: dict, old_regime: str, new_regime: str,
    updated_p_hit_t1: float, updated_p_hit_t2: float | None, vix: float,
) -> bool:
    """
    EVENT 2: REGIME_SHIFT — Market regime changed to HighVolCrash/PostEventCrush
    with low T1 probability.
    """
    state = card.get("signal_state", "PENDING")
    if state not in {"ACTIVE", "WATCHING_SL", "WATCHING_T1", "WATCHING_T2"}:
        return False

    if new_regime not in ("HighVolCrash", "PostEventCrush"):
        return False
    if updated_p_hit_t1 >= 0.40:
        return False

    now_ist = datetime.now(IST)
    event = {
        "event_type": "REGIME_SHIFT",
        "signal_id": card["signal_id"],
        "symbol": card["symbol"],
        "option_symbol": card["option_symbol"],
        "old_regime": old_regime,
        "new_regime": new_regime,
        "updated_p_hit_T1": updated_p_hit_t1,
        "updated_p_hit_T2": updated_p_hit_t2,
        "vix_current": vix,
        "timestamp": now_ist.isoformat(),
        "display_text": (
            f"Regime Shift -- {card['symbol']}: Market regime changed from {old_regime} "
            f"to {new_regime} (VIX: {vix:.1f}). "
            f"T1 probability updated to {updated_p_hit_t1:.0%}."
        ),
    }
    return await emit_event(db, event)


async def emit_urgent_exit(
    db, card: dict, p_recover: float, trend_score: int,
    flow_band: str, best_price_60s: float, reason_codes: list[str],
) -> bool:
    """
    EVENT 3: URGENT_EXIT — All 4 conditions met simultaneously:
    - p_recover < 0.20
    - trend_alignment dropped by >= 2
    - flow_band flipped to opposite direction
    - remaining_mins >= 5 (not in final 5 minutes)
    """
    state = card.get("signal_state", "PENDING")
    if state not in {"ACTIVE", "WATCHING_SL"}:
        return False

    # Check not in final 5 minutes
    now_ist = datetime.now(IST)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    remaining_mins = (market_close - now_ist).total_seconds() / 60
    if remaining_mins < 5:
        return False

    now_ist = datetime.now(IST)
    event = {
        "event_type": "URGENT_EXIT",
        "signal_id": card["signal_id"],
        "symbol": card["symbol"],
        "option_symbol": card["option_symbol"],
        "direction": card.get("direction", "LONG"),
        "best_achievable_price_60s": best_price_60s,
        "p_recover_to_entry": p_recover,
        "trend_alignment_score": trend_score,
        "flow_band": flow_band,
        "timestamp": now_ist.isoformat(),
        "reason_codes": reason_codes,
        "display_text": (
            f"Trend Reversal Detected -- {card['symbol']} ({card['option_symbol']}): "
            f"Recovery probability: {p_recover:.0%}. "
            f"Best available price near Rs.{best_price_60s:.2f} "
            f"based on current order depth (as of {now_ist.strftime('%H:%M')})."
        ),
    }
    return await emit_event(db, event)


# ---------------------------------------------------------------------------
# Event Query API helpers
# ---------------------------------------------------------------------------

async def get_unacknowledged_events(db, limit: int = 50) -> list[dict]:
    """Get unacknowledged popup events (most recent first)."""
    cursor = db[COLL_POPUP_EVENTS].find(
        {"acknowledged": False},
        {"_id": 0},
    ).sort("emitted_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def acknowledge_event(db, event_id: str) -> bool:
    """Mark an event as acknowledged."""
    result = await db[COLL_POPUP_EVENTS].update_one(
        {"event_id": event_id},
        {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


async def acknowledge_all_events(db) -> int:
    """Mark all events as acknowledged."""
    result = await db[COLL_POPUP_EVENTS].update_many(
        {"acknowledged": False},
        {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count


async def get_all_cards(db, include_terminal: bool = False) -> list[dict]:
    """Get all sticky cards, optionally including terminal states."""
    query = {} if include_terminal else {"signal_state": {"$nin": list(TERMINAL_STATES)}}
    cursor = db[COLL_STICKY_CARDS].find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def cancel_card(db, signal_id: str) -> bool:
    """User-initiated cancel of a sticky card."""
    return await close_card(db, signal_id, "CANCELLED", "user_manual_cancel")
