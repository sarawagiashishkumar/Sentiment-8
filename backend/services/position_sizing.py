"""
Position Sizing Calculator — Step 4 of the Master Spec.

Provides:
  1. Risk-based position sizing: given budget, premium, SL → lots_allowed
  2. Capital requirement calculation
  3. Budget gate: annotates signals as affordable / not_affordable

All calculations are pure Python. No LLM numeric work.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# ── Default Risk Parameters ───────────────────────────────────────────────

DEFAULT_MAX_RISK_PER_TRADE_PCT = 2.0  # 2% of portfolio per trade
DEFAULT_MAX_ALLOCATION_PCT = 10.0      # Max 10% of budget on a single trade


def compute_position_size(
    user_budget: float,
    option_premium: float,
    lot_size: int,
    sl_price: float | None = None,
    entry_price: float | None = None,
    max_risk_per_trade_pct: float = DEFAULT_MAX_RISK_PER_TRADE_PCT,
    max_allocation_pct: float = DEFAULT_MAX_ALLOCATION_PCT,
) -> dict[str, Any]:
    """
    Compute position sizing based on risk parameters.

    Inputs:
        user_budget: Total portfolio/capital available (in Rs)
        option_premium: Current premium per unit of the option
        lot_size: NSE lot size for the instrument
        sl_price: Stop-loss price per unit (optional)
        entry_price: Entry/buy price per unit (defaults to option_premium)
        max_risk_per_trade_pct: Max portfolio risk per trade (default 2%)
        max_allocation_pct: Max portfolio allocation for one trade (default 10%)

    Output:
        {
            lots_allowed: int,
            capital_required_per_lot: float,
            total_capital_required: float,
            risk_per_lot: float,
            total_risk_amount: float,
            risk_pct_of_portfolio: float,
            not_affordable: bool,
            sizing_reason: str,
        }
    """
    if user_budget <= 0 or option_premium <= 0 or lot_size <= 0:
        return {
            "lots_allowed": 0,
            "capital_required_per_lot": 0.0,
            "total_capital_required": 0.0,
            "risk_per_lot": 0.0,
            "total_risk_amount": 0.0,
            "risk_pct_of_portfolio": 0.0,
            "not_affordable": True,
            "sizing_reason": "Invalid inputs (zero budget, premium, or lot size)",
        }

    ep = entry_price if entry_price is not None else option_premium
    capital_per_lot = ep * lot_size

    # Max lots by allocation limit
    max_alloc = user_budget * (max_allocation_pct / 100)
    lots_by_allocation = max(0, int(max_alloc / capital_per_lot)) if capital_per_lot > 0 else 0

    # Max lots by risk limit (SL-based)
    sl_dist_per_unit = abs(ep - sl_price) if sl_price is not None and sl_price > 0 else ep * 0.15
    risk_per_lot = sl_dist_per_unit * lot_size
    max_risk = user_budget * (max_risk_per_trade_pct / 100)
    lots_by_risk = max(0, int(max_risk / risk_per_lot)) if risk_per_lot > 0 else 0

    # Final: minimum of the two constraints
    lots_allowed = min(lots_by_allocation, lots_by_risk)

    # Ensure at least 1 lot is checked for affordability
    total_capital = capital_per_lot * max(lots_allowed, 1)
    total_risk = risk_per_lot * max(lots_allowed, 1)
    risk_pct = (total_risk / user_budget * 100) if user_budget > 0 else 0.0

    not_affordable = capital_per_lot > user_budget
    if lots_allowed == 0 and not not_affordable:
        # Can afford 1 lot but risk constraint blocks it
        lots_allowed = 0
        sizing_reason = "Risk constraint limits to 0 lots; consider reducing risk per trade"
    elif not_affordable:
        lots_allowed = 0
        sizing_reason = "Capital required for 1 lot exceeds budget"
    else:
        sizing_reason = f"{lots_allowed} lot(s) within allocation and risk limits"

    return {
        "lots_allowed": lots_allowed,
        "capital_required_per_lot": round(capital_per_lot, 2),
        "total_capital_required": round(capital_per_lot * max(lots_allowed, 1), 2),
        "risk_per_lot": round(risk_per_lot, 2),
        "total_risk_amount": round(total_risk, 2),
        "risk_pct_of_portfolio": round(risk_pct, 2),
        "not_affordable": not_affordable,
        "sizing_reason": sizing_reason,
    }


def annotate_signal_affordability(
    signal: dict[str, Any],
    user_budget: float,
    max_risk_per_trade_pct: float = DEFAULT_MAX_RISK_PER_TRADE_PCT,
) -> dict[str, Any]:
    """
    Annotate an F&O signal dict with position sizing and affordability.

    Adds fields: sizing_info, not_affordable
    Does NOT block signal generation; only annotates.
    """
    premium = signal.get("current_premium") or signal.get("ltp") or signal.get("option_ltp") or 0
    lot_size = signal.get("lot_size", 1)
    sl = signal.get("stop_loss")
    entry = signal.get("best_budget_entry") or premium

    sizing = compute_position_size(
        user_budget=user_budget,
        option_premium=premium,
        lot_size=lot_size,
        sl_price=sl,
        entry_price=entry,
        max_risk_per_trade_pct=max_risk_per_trade_pct,
    )

    signal["sizing_info"] = sizing
    signal["not_affordable"] = sizing["not_affordable"]
    return signal
