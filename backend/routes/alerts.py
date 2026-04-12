"""
Custom Alert Rule Engine — Composable alert rules evaluated against live market data.
Refactored: evaluation logic split into focused sub-functions.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

alerts_router = APIRouter()

COOLDOWN_SECONDS = 300  # 5 min between re-triggers per rule


class AlertCondition(BaseModel):
    field: str
    symbol: str | None = None
    operator: str
    value: float


class AlertRuleCreate(BaseModel):
    name: str
    conditions: list[AlertCondition]
    logic: str = "AND"
    notify_type: str = "push"
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    conditions: list[AlertCondition] | None = None
    logic: str | None = None
    notify_type: str | None = None
    enabled: bool | None = None


OPERATOR_MAP = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: abs(a - b) < 0.01,
}

FIELD_EXTRACTORS = {
    "vix": lambda qd, sym, vix: vix,
    "symbol_ltp": lambda qd, sym, vix: qd.get(sym, {}).get("ltp", 0),
    "symbol_change_pct": lambda qd, sym, vix: qd.get(sym, {}).get("change_pct", 0),
    "symbol_volume": lambda qd, sym, vix: qd.get(sym, {}).get("volume", 0),
    "symbol_high": lambda qd, sym, vix: qd.get(sym, {}).get("high", 0),
    "symbol_low": lambda qd, sym, vix: qd.get(sym, {}).get("low", 0),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collect_symbols(rules: list[dict]) -> tuple[set[str], bool]:
    """Extract all needed symbols and whether VIX is needed from rules."""
    symbols = set()
    needs_vix = False
    for rule in rules:
        for cond in rule.get("conditions", []):
            if cond.get("symbol"):
                symbols.add(cond["symbol"].upper())
            if cond.get("field") == "vix":
                needs_vix = True
    return symbols, needs_vix


async def _fetch_market_data(symbols: set[str], needs_vix: bool) -> tuple[dict, float]:
    """Fetch live quotes and VIX in parallel."""
    quote_data = {}
    vix_value = 0.0

    async def _fetch_quotes():
        nonlocal quote_data
        if not symbols:
            return
        try:
            from services.kite_client import fetch_kite_batch_quotes
            raw = await fetch_kite_batch_quotes(list(symbols))
            for sym, q in raw.items():
                quote_data[sym] = {
                    "ltp": q.get("ltp", 0), "change_pct": q.get("change_pct", 0),
                    "open": q.get("open", 0), "high": q.get("high", 0),
                    "low": q.get("low", 0), "volume": q.get("volume", 0),
                }
        except Exception as exc:
            logger.warning("Alert quote fetch failed: %s", exc)

    async def _fetch_vix():
        nonlocal vix_value
        if not needs_vix:
            return
        try:
            from services.india_vix import _get_india_vix
            vix_value = await _get_india_vix() or 0
        except Exception:
            pass

    await asyncio.gather(_fetch_quotes(), _fetch_vix())
    return quote_data, vix_value


def _evaluate_condition(cond: dict, quote_data: dict, vix_value: float) -> bool:
    """Evaluate a single condition against market data."""
    field = cond.get("field", "")
    sym = (cond.get("symbol") or "").upper()
    op_fn = OPERATOR_MAP.get(cond.get("operator", ""))
    if not op_fn:
        return False
    threshold = float(cond.get("value", 0))
    extractor = FIELD_EXTRACTORS.get(field)
    actual = extractor(quote_data, sym, vix_value) if extractor else 0
    return op_fn(actual, threshold)


def _evaluate_rule(rule: dict, quote_data: dict, vix_value: float) -> bool:
    """Evaluate all conditions in a rule with AND/OR logic."""
    conditions = rule.get("conditions", [])
    if not conditions:
        return False
    results = [_evaluate_condition(c, quote_data, vix_value) for c in conditions]
    return all(results) if rule.get("logic", "AND") == "AND" else any(results)


def _is_in_cooldown(rule: dict, now: datetime) -> bool:
    """Check if rule was triggered recently (within cooldown)."""
    last = rule.get("last_triggered")
    if not last:
        return False
    try:
        if isinstance(last, str):
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        else:
            last_dt = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
        return (now - last_dt).total_seconds() < COOLDOWN_SECONDS
    except (ValueError, TypeError, AttributeError):
        return False


async def _trigger_rule(rule: dict, user_key: str, now: datetime):
    """Record trigger and push notification."""
    await _state.db.alert_rules.update_one(
        {"rule_id": rule["rule_id"]},
        {"$set": {"last_triggered": now.isoformat()}, "$inc": {"trigger_count": 1}},
    )
    await _state.db.user_notifications.insert_one({
        "user_key": user_key,
        "category": "warning",
        "title": f"Alert: {rule['name']}",
        "message": f"Custom alert rule '{rule['name']}' triggered",
        "ts": now.timestamp(),
        "read": False,
    })


# ── CRUD Routes ───────────────────────────────────────────────────────────────

@alerts_router.get("/alerts/rules")
async def list_alert_rules(current_user: dict = Depends(get_current_user)):
    user_key = current_user.get("user_key", "")
    cursor = _state.db.alert_rules.find(
        {"user_key": user_key}, {"_id": 0}
    ).sort("created_at", -1).limit(50)
    rules = await cursor.to_list(50)
    return {"rules": rules, "count": len(rules)}


@alerts_router.post("/alerts/rules")
async def create_alert_rule(rule: AlertRuleCreate, current_user: dict = Depends(get_current_user)):
    user_key = current_user.get("user_key", "")
    if not rule.name.strip():
        raise HTTPException(400, "Rule name required")
    if not rule.conditions:
        raise HTTPException(400, "At least one condition required")
    if rule.logic not in ("AND", "OR"):
        raise HTTPException(400, "Logic must be AND or OR")
    for cond in rule.conditions:
        if cond.operator not in OPERATOR_MAP:
            raise HTTPException(400, f"Invalid operator: {cond.operator}")

    doc = {
        "rule_id": str(uuid.uuid4()),
        "user_key": user_key,
        "name": rule.name.strip(),
        "conditions": [c.model_dump() for c in rule.conditions],
        "logic": rule.logic,
        "notify_type": rule.notify_type,
        "enabled": rule.enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
    }
    await _state.db.alert_rules.insert_one(doc)
    doc.pop("_id", None)
    return {"created": True, "rule": doc}


@alerts_router.patch("/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: str, update: AlertRuleUpdate, current_user: dict = Depends(get_current_user)):
    user_key = current_user.get("user_key", "")
    existing = await _state.db.alert_rules.find_one({"rule_id": rule_id, "user_key": user_key}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Rule not found")
    updates = {}
    if update.name is not None:
        updates["name"] = update.name.strip()
    if update.conditions is not None:
        updates["conditions"] = [c.model_dump() for c in update.conditions]
    if update.logic is not None:
        updates["logic"] = update.logic
    if update.notify_type is not None:
        updates["notify_type"] = update.notify_type
    if update.enabled is not None:
        updates["enabled"] = update.enabled
    if updates:
        await _state.db.alert_rules.update_one({"rule_id": rule_id, "user_key": user_key}, {"$set": updates})
    return {"updated": True, "rule_id": rule_id}


@alerts_router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, current_user: dict = Depends(get_current_user)):
    user_key = current_user.get("user_key", "")
    result = await _state.db.alert_rules.delete_one({"rule_id": rule_id, "user_key": user_key})
    if result.deleted_count == 0:
        raise HTTPException(404, "Rule not found")
    return {"deleted": True, "rule_id": rule_id}


# ── Evaluation Route ──────────────────────────────────────────────────────────

@alerts_router.post("/alerts/evaluate")
async def evaluate_alerts(current_user: dict = Depends(get_current_user)):
    """Evaluate all enabled alert rules against live market data."""
    user_key = current_user.get("user_key", "")
    rules = await _state.db.alert_rules.find(
        {"user_key": user_key, "enabled": True}, {"_id": 0}
    ).to_list(50)

    if not rules:
        return {"triggered": [], "evaluated": 0}

    symbols, needs_vix = _collect_symbols(rules)
    quote_data, vix_value = await _fetch_market_data(symbols, needs_vix)

    triggered = []
    now_ts = datetime.now(timezone.utc)

    for rule in rules:
        if not _evaluate_rule(rule, quote_data, vix_value):
            continue
        if _is_in_cooldown(rule, now_ts):
            continue
        await _trigger_rule(rule, user_key, now_ts)
        triggered.append({"rule_id": rule["rule_id"], "name": rule["name"], "triggered_at": now_ts.isoformat()})

    return {"triggered": triggered, "evaluated": len(rules), "ts": now_ts.isoformat()}


# ── Background Monitor ────────────────────────────────────────────────────────

def _is_market_hours() -> bool:
    """Check if current time is within NSE market hours."""
    _now = datetime.now(_state.IST)
    if _now.weekday() >= 5:
        return False
    _mins = _now.hour * 60 + _now.minute
    return 555 <= _mins <= 930


async def run_alert_rule_monitor():
    """Background task: evaluate enabled alert rules every 30s during market hours."""
    while True:
        await asyncio.sleep(30)
        if not _is_market_hours():
            continue
        try:
            pipeline = [{"$match": {"enabled": True}}, {"$group": {"_id": "$user_key"}}]
            user_keys = [doc["_id"] async for doc in _state.db.alert_rules.aggregate(pipeline)]

            for user_key in user_keys:
                await _evaluate_user_rules(user_key)
        except Exception as exc:
            logger.debug("Alert rule monitor cycle failed: %s", exc)


async def _evaluate_user_rules(user_key: str):
    """Evaluate all rules for a single user in the background monitor."""
    try:
        rules = await _state.db.alert_rules.find(
            {"user_key": user_key, "enabled": True}, {"_id": 0}
        ).to_list(20)

        symbols, needs_vix = _collect_symbols(rules)
        if not symbols and not needs_vix:
            return

        quote_data, vix_value = await _fetch_market_data(symbols, needs_vix)
        now_ts = datetime.now(timezone.utc)

        for rule in rules:
            if not _evaluate_rule(rule, quote_data, vix_value):
                continue
            if _is_in_cooldown(rule, now_ts):
                continue
            await _trigger_rule(rule, user_key, now_ts)
            logger.info("Alert rule triggered: %s for user %s", rule["name"], user_key[:8])
    except Exception as exc:
        logger.debug("Alert monitor per-user failed: %s", exc)
