"""
=== GLOBAL DATA POLICY — NON-NEGOTIABLE ===

Kite Connect is the sole source of truth for all production market data.
Data fetched from Kite Connect is authoritative and requires NO re-verification
from any third-party source (Yahoo Finance, yfinance, NSE scraper, etc.).
Cross-source comparison against delayed/external sources is PROHIBITED in production.

Hierarchy:
  1. Kite Connect API (primary — live/historical OHLCV, quotes, OI, IV)
  2. Verified CSV seed files (fallback — only when Kite is unavailable)
  3. yfinance (DISABLED — USE_YFINANCE=false — fundamentals stub only, offline research)

Applies to: F&O signals, Multibagger Screener, Portfolio Analysis,
            sector momentum, backtests, position monitoring, data verification.

No module may override this policy.
"""
from __future__ import annotations

import os

KITE_IS_SOURCE_OF_TRUTH: bool = True

USE_YFINANCE: bool = os.environ.get("USE_YFINANCE", "false").lower() in ("1", "true", "yes")
