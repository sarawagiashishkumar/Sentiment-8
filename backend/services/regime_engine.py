"""
Regime Engine — Section 3 of Master Spec v2.0.

Spec-exact 8-regime classifier using:
  - India VIX
  - Realized HV (20-day)
  - ADX(14)
  - Breadth metrics (from constituent_engine)

Labels (exactly one):
  LowVolTrend     vix<14 AND adx>25
  LowVolRange     vix<14 AND adx<=25
  NormalVolTrend   14<=vix<=20 AND adx>25
  NormalVolRange   14<=vix<=20 AND adx<=25
  HighVolTrend     vix>20 AND adx>25
  HighVolCrash     vix>25 AND adx>20 AND breadth downtrending
  PreEvent         major scheduled event within 24h (RBI, FOMC, earnings)
  PostEventCrush   within 6h after major event

Stores: regime_label, regime_timestamp in MongoDB for audit trail.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

# MongoDB collection for regime history
COLLECTION = "regime_history"

# Exact labels from the spec
RegimeLabel = Literal[
    "LowVolTrend",
    "LowVolRange",
    "NormalVolTrend",
    "NormalVolRange",
    "HighVolTrend",
    "HighVolCrash",
    "PreEvent",
    "PostEventCrush",
]

# Strategy grid per regime (from macro_context.py, aligned to new labels)
REGIME_STRATEGY: dict[str, dict[str, str]] = {
    "LowVolTrend": {
        "primary": "LONG_CALL / BULL_CALL_SPREAD",
        "avoid": "LONG_STRADDLE",
    },
    "LowVolRange": {
        "primary": "IRON_CONDOR / SHORT_STRADDLE",
        "avoid": "NAKED_DIRECTIONAL",
    },
    "NormalVolTrend": {
        "primary": "DEBIT_SPREAD / DIRECTIONAL",
        "avoid": "CONDORS_ON_TRENDING",
    },
    "NormalVolRange": {
        "primary": "IRON_CONDOR / CREDIT_SPREAD",
        "avoid": "STRADDLE",
    },
    "HighVolTrend": {
        "primary": "STRADDLE / STRANGLE",
        "avoid": "SHORT_NAKED_OPTIONS",
    },
    "HighVolCrash": {
        "primary": "PROTECTIVE_PUTS / BEAR_SPREAD",
        "avoid": "SHORT_PUTS / LONG_FUTURES",
    },
    "PreEvent": {
        "primary": "LONG_STRADDLE / LONG_STRANGLE",
        "avoid": "SHORT_OPTIONS",
    },
    "PostEventCrush": {
        "primary": "CREDIT_SPREAD / IRON_CONDOR",
        "avoid": "LONG_OPTIONS",
    },
}


def regime_classify(
    india_vix: float | None,
    realized_hv_20d: float | None = None,
    adx_14: float | None = None,
    breadth_metrics: dict[str, Any] | None = None,
    hours_to_event: float | None = None,
    hours_since_event: float | None = None,
) -> dict[str, Any]:
    """
    Classify market regime using the exact spec thresholds.

    Returns:
      regime_label: one of 8 labels
      vix_band: LOW / NORMAL / HIGH / PANIC
      trend_band: TRENDING / RANGE
      strategy: primary + avoid
      description: human-readable
      confidence: 0.0 - 1.0
    """
    vix = india_vix if india_vix is not None else 15.0
    adx = adx_14 if adx_14 is not None else 20.0
    breadth = breadth_metrics or {}
    breadth_score = breadth.get("breadth_score", 50.0)
    breadth_downtrend = breadth_score < 40.0

    # Event-based regimes take priority
    if hours_to_event is not None and 0 <= hours_to_event <= 24:
        label: RegimeLabel = "PreEvent"
        confidence = 0.80
        desc = f"Major event within {hours_to_event:.0f}h. Buy volatility before IV crush."
    elif hours_since_event is not None and hours_since_event <= 6:
        label = "PostEventCrush"
        confidence = 0.75
        desc = f"Post-event ({hours_since_event:.0f}h ago). IV crushing — sell overpriced options."
    elif vix > 25 and adx > 20 and breadth_downtrend:
        label = "HighVolCrash"
        confidence = 0.90
        desc = f"VIX {vix:.1f} (PANIC) + ADX {adx:.0f} + breadth declining. Capital protection mode."
    elif vix > 20 and adx > 25:
        label = "HighVolTrend"
        confidence = 0.80
        desc = f"VIX {vix:.1f} (HIGH) + strong trend ADX {adx:.0f}. Buy options on confirmation."
    elif vix > 20 and adx <= 25:
        # High vol but range-bound — spec doesn't define this explicitly
        # Treat as HighVolTrend (conservative)
        label = "HighVolTrend"
        confidence = 0.65
        desc = f"VIX {vix:.1f} (HIGH) + weak trend. Cautious directional."
    elif 14 <= vix <= 20 and adx > 25:
        label = "NormalVolTrend"
        confidence = 0.80
        desc = f"VIX {vix:.1f} (NORMAL) + trending ADX {adx:.0f}. Standard directional plays."
    elif 14 <= vix <= 20 and adx <= 25:
        label = "NormalVolRange"
        confidence = 0.75
        desc = f"VIX {vix:.1f} (NORMAL) + range ADX {adx:.0f}. Credit spreads."
    elif vix < 14 and adx > 25:
        label = "LowVolTrend"
        confidence = 0.85
        desc = f"VIX {vix:.1f} (LOW) + trend ADX {adx:.0f}. Cheap options — buy calls/puts."
    else:
        label = "LowVolRange"
        confidence = 0.70
        desc = f"VIX {vix:.1f} (LOW) + range ADX {adx:.0f}. Iron Condors / Short Straddles."

    # VIX band
    if vix < 14:
        vix_band = "LOW"
    elif vix <= 20:
        vix_band = "NORMAL"
    elif vix <= 25:
        vix_band = "HIGH"
    else:
        vix_band = "PANIC"

    trend_band = "TRENDING" if adx > 25 else "RANGE"

    strategy = REGIME_STRATEGY.get(label, REGIME_STRATEGY["NormalVolRange"])

    return {
        "regime_label": label,
        "vix_band": vix_band,
        "vix_value": round(vix, 1),
        "trend_band": trend_band,
        "adx_value": round(adx, 1),
        "realized_hv_20d": round(realized_hv_20d, 4) if realized_hv_20d else None,
        "breadth_score": round(breadth_score, 1),
        "strategy": strategy,
        "description": desc,
        "confidence": round(confidence, 2),
    }


async def store_regime(db, index_name: str, regime_data: dict[str, Any]) -> None:
    """Persist regime classification for audit trail."""
    doc = {
        "index_name": index_name,
        "regime_label": regime_data["regime_label"],
        "vix_value": regime_data.get("vix_value"),
        "adx_value": regime_data.get("adx_value"),
        "breadth_score": regime_data.get("breadth_score"),
        "confidence": regime_data.get("confidence"),
        "ts": datetime.now(timezone.utc),
    }
    try:
        await db[COLLECTION].insert_one(doc)
    except Exception as exc:
        logger.debug(f"Regime store failed: {exc}")


async def get_latest_regime(db, index_name: str) -> dict[str, Any] | None:
    """Retrieve the most recent regime classification for an index."""
    try:
        doc = await db[COLLECTION].find_one(
            {"index_name": index_name},
            {"_id": 0},
            sort=[("ts", -1)],
        )
        return doc
    except Exception:
        return None


async def ensure_indexes(db) -> None:
    """Create indexes for regime_history collection."""
    coll = db[COLLECTION]
    await coll.create_index(
        [("index_name", 1), ("ts", -1)],
        name="index_ts_desc",
    )
    logger.info("regime_history indexes ensured")
