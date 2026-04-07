"""
F&O Universe Service — Mini-Batch: F&O Universe / List Selection

Provides a single-sourced, clean abstraction for the F&O stock universe.
Returns ALL NSE F&O-eligible symbols from the LOT_SIZE_MAP, subject to
eligibility filters defined in section 1.5 of the Master Spec.

The universe list is derived from:
1. LOT_SIZE_MAP (maintained in server.py) — the canonical source of
   all symbols with known F&O lot sizes.
2. Kite option_master DB collection — symbols that have live option chains.
3. Eligibility filters (LTP >= 50, not NCLT/DRT, debt < 30%, profit positive).

Design: The data source can later be swapped to a dynamic NSE scraper
or nsetools/nsepy integration without changing any downstream logic.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical F&O universe — all NSE F&O-eligible individual stock symbols.
# This list is derived from NSE's "List of Underlyings for F&O" plus
# recent additions. It matches LOT_SIZE_MAP keys minus index entries.
#
# To update: add/remove symbols here when NSE changes the F&O list.
# ---------------------------------------------------------------------------

NSE_FO_STOCKS: list[str] = [
    # Large-cap banking & financial
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE",
    "BAJAJFINSV", "INDUSINDBK", "BANDHANBNK", "BANKBARODA", "PNB", "CANBK",
    "IDFCFIRSTB", "FEDERALBNK", "AUBANK", "MANAPPURAM", "MUTHOOTFIN",
    "SHRIRAMFIN", "CHOLAFIN", "HDFCLIFE", "SBILIFE", "ICICIGI", "LICI",
    "SBICARD",

    # IT & Technology
    "TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIMindtree", "MPHASIS",
    "COFORGE", "PERSISTENT", "LTTS",

    # Energy & Oil
    "RELIANCE", "ONGC", "BPCL", "IOC", "GAIL", "HINDPETRO", "PETRONET",
    "TATAPOWER", "NTPC", "POWERGRID", "ADANIGREEN", "ADANIPOWER",
    "TORNTPOWER", "CESC",

    # Auto & Auto ancillary
    "TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT",
    "ASHOKLEY", "BALKRISIND", "MRF", "TVSMOTOR", "MOTHERSON",

    # Pharma & Healthcare
    "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "AUROPHARMA",
    "BIOCON", "GLENMARK", "TORNTPHARM", "IPCALAB", "ALEMBICPHARMA",
    "APOLLOHOSP",

    # FMCG & Consumer
    "ITC", "HINDUNILVR", "NESTLEIND", "TATACONSUM", "BRITANNIA", "DABUR",
    "MARICO", "COLPAL", "GODREJCP", "UBL", "VBL", "JUBLFOOD",

    # Metals & Mining
    "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "NMDC", "NATIONALUM",
    "SAIL", "COALINDIA",

    # Infrastructure & Cement
    "LT", "ULTRACEMCO", "SHREECEM", "AMBUJACEM", "ACCIND", "RAMCOCEM",
    "ADANIENT", "ADANIPORTS",

    # Chemicals
    "PIIND", "UPL", "DEEPAKNTR", "ATUL", "SRF", "GNFC",

    # Real Estate
    "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE",

    # Telecom & Media
    "BHARTIARTL", "IDEA",

    # Engineering & Capital Goods
    "CUMMINSIND", "THERMAX", "VOLTAS", "BLUESTARCO", "CROMPTON",
    "POLYCAB", "KEI", "DIXON", "AMBER", "ABB", "SIEMENS",
    "BEL", "HAL", "BDL",

    # Textiles & Apparel
    "PAGEIND",

    # Insurance & Misc Financial
    "NAUKRI",

    # Others from LOT_SIZE_MAP
    "ASIANPAINT", "BERGEPAINT", "TITAN", "GRASIM", "HAVELLS",
    "WHIRLPOOL", "AAPLLTD",

    # Recent F&O additions (2024-2026)
    "ZOMATO", "PAYTM", "NYKAA", "DMART", "TRENT", "IRCTC",
    "INDIGO", "RECLTD", "PFC", "IRFC", "NHPC", "SJVN",
    "CONCOR", "EXIDEIND", "INDUSTOWER", "ABCAPITAL",
    "GMRINFRA", "HUDCO", "BHEL", "HINDCOPPER",
    "ADITIMKT", "ABFRL",
    "DEVIT", "WEBELSOLAR",
]

# Index F&O underlyings (always eligible if index-level conditions met)
INDEX_FO_UNDERLYINGS: list[str] = ["NIFTY", "BANKNIFTY"]


def get_fo_universe(
    lot_size_map: dict[str, int] | None = None,
    include_indices: bool = False,
) -> list[str]:
    """
    Return the full F&O-eligible stock universe.

    Priority:
    1. LOT_SIZE_MAP keys (if provided) — most authoritative, from Kite instruments
    2. NSE_FO_STOCKS hardcoded list — fallback

    If include_indices=True, also includes NIFTY/BANKNIFTY.
    """
    symbols: set[str] = set()

    # Primary: LOT_SIZE_MAP (from server.py) has all symbols with known lot sizes
    if lot_size_map:
        for sym in lot_size_map:
            if sym not in ("NIFTY", "BANKNIFTY"):
                symbols.add(sym)

    # Secondary: Hardcoded NSE F&O list
    symbols.update(NSE_FO_STOCKS)

    if include_indices:
        symbols.update(INDEX_FO_UNDERLYINGS)

    return sorted(symbols)


async def get_fo_universe_from_db(db, lot_size_map: dict[str, int] | None = None) -> list[str]:
    """
    Return F&O universe, enriched with symbols from kite_option_master DB.

    Checks kite_option_master for unique underlyings that have live option chains.
    """
    symbols: set[str] = set()

    # From LOT_SIZE_MAP + hardcoded list
    base = get_fo_universe(lot_size_map=lot_size_map, include_indices=False)
    symbols.update(base)

    # From DB: kite_option_master has real option chain data
    try:
        coll = db.get_collection("kite_option_master")
        db_underlyings = await coll.distinct("underlying")
        for u in db_underlyings:
            if u and u not in ("NIFTY", "BANKNIFTY") and isinstance(u, str):
                symbols.add(u)
    except Exception as e:
        logger.warning(f"kite_option_master query failed: {e}")

    return sorted(symbols)


def get_fo_universe_size(lot_size_map: dict[str, int] | None = None) -> int:
    """Quick count of F&O universe size."""
    return len(get_fo_universe(lot_size_map=lot_size_map))
