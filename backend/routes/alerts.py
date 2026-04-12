"""
Custom Alert Rule Engine — Composable alert rules evaluated against live market data.
Rules like "NIFTY > 24000 AND VIX > 15" can be created, edited, and auto-evaluated.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

alerts_router = APIRouter()


class AlertCondition(BaseModel):
    field: str       # "symbol_ltp", "symbol_change_pct", "vix"
    symbol: str | None = None  # e.g. "NIFTY", "RELIANCE"
    operator: str    # "gt", "lt", "gte", "lte", "eq"
    value: float


class AlertRuleCreate(BaseModel):
    name: str
    conditions: list[AlertCondition]
    logic: str = "AND"  # "AND" or "OR"
    notify_type: str = "push"  # "push", "sound", "both"
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


@alerts_router.get("/alerts/rules")
async def list_alert_rules(current_user: dict = Depends(get_current_user)):
    """List all alert rules for the current user."""
    user_key = current_user.get("user_key", "")
    cursor = _state.db.alert_rules.find(
        {"user_key": user_key}, {"_id": 0}
    ).sort("created_at", -1).limit(50)
    rules = await cursor.to_list(50)
    return {"rules": rules, "count": len(rules)}


@alerts_router.post("/alerts/rules")
async def create_alert_rule(
    rule: AlertRuleCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new custom alert rule."""
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
async def update_alert_rule(
    rule_id: str,
    update: AlertRuleUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update an existing alert rule."""
    user_key = current_user.get("user_key", "")
    existing = await _state.db.alert_rules.find_one(
        {"rule_id": rule_id, "user_key": user_key}, {"_id": 0}
    )
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
        await _state.db.alert_rules.update_one(
            {"rule_id": rule_id, "user_key": user_key},
            {"$set": updates},
        )
    return {"updated": True, "rule_id": rule_id}


@alerts_router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete an alert rule."""
    user_key = current_user.get("user_key", "")
    result = await _state.db.alert_rules.delete_one(
        {"rule_id": rule_id, "user_key": user_key}
    )
    if result.deleted_count == 0:
        raise HTTPException(404, "Rule not found")
    return {"deleted": True, "rule_id": rule_id}


@alerts_router.post("/alerts/evaluate")
async def evaluate_alerts(current_user: dict = Depends(get_current_user)):
    """Evaluate all enabled alert rules for current user against live market data."""
    user_key = current_user.get("user_key", "")
    rules = await _state.db.alert_rules.find(
        {"user_key": user_key, "enabled": True}, {"_id": 0}
    ).to_list(50)

    if not rules:
        return {"triggered": [], "evaluated": 0}

    # Collect all symbols needed
    symbols_needed = set()
    needs_vix = False
    for rule in rules:
        for cond in rule.get("conditions", []):
            if cond.get("symbol"):
                symbols_needed.add(cond["symbol"].upper())
            if cond.get("field") == "vix":
                needs_vix = True

    # Fetch live quotes
    quote_data = {}
    if symbols_needed:
        try:
            from services.kite_client import fetch_kite_batch_quotes
            quotes = await fetch_kite_batch_quotes(list(symbols_needed))
            for sym, q in quotes.items():
                quote_data[sym] = {
                    "ltp": q.get("ltp", 0),
                    "change_pct": q.get("change_pct", 0),
                    "open": q.get("open", 0),
                    "high": q.get("high", 0),
                    "low": q.get("low", 0),
                    "volume": q.get("volume", 0),
                }
        except Exception as exc:
            logger.warning("Alert evaluation: quote fetch failed: %s", exc)

    # Fetch VIX if needed
    vix_value = 0
    if needs_vix:
        try:
            from services.india_vix import _get_india_vix
            vix_value = await _get_india_vix() or 0
        except Exception:
            pass

    # Evaluate each rule
    triggered = []
    now_ts = datetime.now(timezone.utc)

    for rule in rules:
        conditions = rule.get("conditions", [])
        logic = rule.get("logic", "AND")
        results = []

        for cond in conditions:
            field = cond.get("field", "")
            sym = (cond.get("symbol") or "").upper()
            op = cond.get("operator", "gt")
            threshold = float(cond.get("value", 0))
            op_fn = OPERATOR_MAP.get(op)
            if not op_fn:
                results.append(False)
                continue

            actual = 0
            if field == "vix":
                actual = vix_value
            elif field == "symbol_ltp" and sym in quote_data:
                actual = quote_data[sym]["ltp"]
            elif field == "symbol_change_pct" and sym in quote_data:
                actual = quote_data[sym]["change_pct"]
            elif field == "symbol_volume" and sym in quote_data:
                actual = quote_data[sym]["volume"]
            elif field == "symbol_high" and sym in quote_data:
                actual = quote_data[sym]["high"]
            elif field == "symbol_low" and sym in quote_data:
                actual = quote_data[sym]["low"]

            results.append(op_fn(actual, threshold))

        # Apply logic
        if logic == "AND":
            fired = all(results) if results else False
        else:
            fired = any(results) if results else False

        if fired:
            # Cooldown: don't re-trigger within 5 minutes
            last = rule.get("last_triggered")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if (now_ts - last_dt).total_seconds() < 300:
                        continue
                except (ValueError, TypeError):
                    pass

            # Record trigger
            await _state.db.alert_rules.update_one(
                {"rule_id": rule["rule_id"]},
                {"$set": {"last_triggered": now_ts.isoformat()}, "$inc": {"trigger_count": 1}},
            )

            # Push notification
            await _state.db.user_notifications.insert_one({
                "user_key": user_key,
                "category": "warning",
                "title": f"Alert: {rule['name']}",
                "message": f"Custom alert rule '{rule['name']}' triggered",
                "ts": now_ts.timestamp(),
                "read": False,
            })

            triggered.append({
                "rule_id": rule["rule_id"],
                "name": rule["name"],
                "triggered_at": now_ts.isoformat(),
            })

    return {"triggered": triggered, "evaluated": len(rules), "ts": now_ts.isoformat()}


async def run_alert_rule_monitor():
    """Background task: evaluate enabled alert rules every 30s during market hours."""
    while True:
        await asyncio.sleep(30)
        try:
            _now = datetime.now(_state.IST)
            if _now.weekday() >= 5:
                continue
            _mins = _now.hour * 60 + _now.minute
            if _mins < 555 or _mins > 930:
                continue

            # Get all users with enabled rules
            pipeline = [
                {"$match": {"enabled": True}},
                {"$group": {"_id": "$user_key"}},
            ]
            user_keys = [doc["_id"] async for doc in _state.db.alert_rules.aggregate(pipeline)]

            for user_key in user_keys:
                try:
                    rules = await _state.db.alert_rules.find(
                        {"user_key": user_key, "enabled": True}, {"_id": 0}
                    ).to_list(20)

                    symbols_needed = set()
                    for rule in rules:
                        for cond in rule.get("conditions", []):
                            if cond.get("symbol"):
                                symbols_needed.add(cond["symbol"].upper())

                    if not symbols_needed:
                        continue

                    from services.kite_client import fetch_kite_batch_quotes
                    quotes = await fetch_kite_batch_quotes(list(symbols_needed))
                    quote_data = {}
                    for sym, q in quotes.items():
                        quote_data[sym] = {"ltp": q.get("ltp", 0), "change_pct": q.get("change_pct", 0)}

                    now_ts = datetime.now(timezone.utc)
                    for rule in rules:
                        conditions = rule.get("conditions", [])
                        logic = rule.get("logic", "AND")
                        results = []
                        for cond in conditions:
                            sym = (cond.get("symbol") or "").upper()
                            op_fn = OPERATOR_MAP.get(cond.get("operator", "gt"))
                            threshold = float(cond.get("value", 0))
                            if not op_fn:
                                results.append(False)
                                continue
                            actual = 0
                            if cond.get("field") == "symbol_ltp" and sym in quote_data:
                                actual = quote_data[sym]["ltp"]
                            elif cond.get("field") == "symbol_change_pct" and sym in quote_data:
                                actual = quote_data[sym]["change_pct"]
                            results.append(op_fn(actual, threshold))

                        fired = (all(results) if logic == "AND" else any(results)) if results else False
                        if not fired:
                            continue

                        last = rule.get("last_triggered")
                        if last:
                            try:
                                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                                if (now_ts - last_dt).total_seconds() < 300:
                                    continue
                            except (ValueError, TypeError):
                                pass

                        await _state.db.alert_rules.update_one(
                            {"rule_id": rule["rule_id"]},
                            {"$set": {"last_triggered": now_ts.isoformat()}, "$inc": {"trigger_count": 1}},
                        )
                        await _state.db.user_notifications.insert_one({
                            "user_key": user_key,
                            "category": "warning",
                            "title": f"Alert: {rule['name']}",
                            "message": f"Custom alert rule '{rule['name']}' triggered",
                            "ts": now_ts.timestamp(),
                            "read": False,
                        })
                        logger.info("Alert rule triggered: %s for user %s", rule["name"], user_key[:8])
                except Exception as exc:
                    logger.debug("Alert monitor per-user failed: %s", exc)
        except Exception as exc:
            logger.debug("Alert rule monitor cycle failed: %s", exc)
