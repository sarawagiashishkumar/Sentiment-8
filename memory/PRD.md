# PRD — Trading Research Platform (F&O Application)

## Original Problem Statement
Build a professional F&O (Futures & Options) trading research application with:
- Kite Connect as the primary data source
- Strict backend-only calculations (no LLM hallucinations for numbers)
- Mandatory fundamental filters on NSE F&O universe
- Master Spec v2.0 multi-batch implementation

## Core Architecture Rules
1. ALL numeric calculations in backend Python only
2. Kite Connect is the authoritative data source
3. Strict fundamental filters on NSE F&O universe
4. NDJSON streaming for long-running endpoints

## Current State (April 2026)
- Backend: FastAPI, Python 3.11, `server.py` reduced to ~615 lines
- Frontend: React with Shadcn UI, Tailwind CSS
- Database: MongoDB (`test_database`)
- Test Suite: 119+ unit tests passing (100% green)
- Auth: Custom token-based via POST /api/auth/access

## What's Been Implemented

### Phase 1-5: Core Engine (DONE)
- F&O signal generation engine with 4-bucket confluence scoring (A/B/C/D)
- V2 confluence score with MFE/MAE probability targets
- Price Band Engine with mathematical audit
- Multibagger Screener
- Portfolio analysis
- Sector momentum dashboard (8 NSE sector indices)
- Admin dashboard with user/domain management
- Signal history tracking
- IV Analytics (cone + term structure)
- Multi-timeframe analysis

### Phase 6: Architecture Hardening (DONE)
- `server.py` modularized from 3578 → 615 lines
- Extracted: `kite_client.py`, `fundamental_data.py`, `user_service.py`, `validators.py`, `cache_helpers.py`, `lot_sizes.py`
- 100% test suite green (1385+ → 119 focused tests post-cleanup)

### Phase 7: P0 Fixes + P1 UI Overhaul (DONE — April 10, 2026)
**P0 Fixes:**
- Kite token validation: `/api/kite/status` now makes real API call to Kite profile endpoint (was falsely reporting "connected" based on date match alone)
- F&O signal suppression fix: `compute_bucket_d` no longer penalizes signals when MFE data is unavailable (t2_p_hit=None → neutral 0.50 default instead of 0.0 with -15 penalty)
- Sector momentum text: Removed hardcoded "15 sectors" from frontend

**P1 Features:**
- **Sub-Menu Navigation:** Added SubTabs component for F&O and Market HeatMap sections
- **F&O Sub-Tabs:** "Signals & Custom" | "Signal Performance" | "IV Analytics & Multi-TF"
- **F&O 3-Column Layout:** NIFTY (sticky) | BANKNIFTY | Top 4 Trades, with max 15 individual stock signals in 3-column grid below
- **Market HeatMap Section:** New nav tab with 3 sub-tabs:
  - Sector Heatmap (click sector → constituent stocks drill-down)
  - Stocks Heatmap with filters (Nifty50, BankNifty, FNO, +5%, +3%, -3%, -5%)
  - Options Heatmap with filters (NIFTY Options, BANKNIFTY Options, Stock Options)
- **Backend Endpoints Added:** `/api/market/stock-heatmap`, `/api/market/options-heatmap`, `/api/market/sector-stocks`

## Key API Endpoints
- `/api/auth/access` — Login
- `/api/auth/me` — Current user
- `/api/auth/settings` — User settings
- `/api/kite/status` — Kite connection status (with real token validation)
- `/api/fno/generate` — F&O signal generation (NDJSON stream)
- `/api/sector-momentum` — Sector momentum data
- `/api/market/stock-heatmap` — Stock heatmap data
- `/api/market/options-heatmap` — Options chain heatmap
- `/api/market/sector-stocks` — Sector constituent stocks
- `/api/fno/signal-history` — Historical signals
- `/api/fno/performance-stats` — Performance tracking

## Database Schema (test_database)
- `app_users`: User accounts, fno_budget, account_risk_pct
- `system_meta`: Kite session storage (key: "kite_session")
- `fno_signal_history`, `fno_signal_log`: Signal tracking
- `iv_history`: IV snapshots
- `fno_universe`: F&O tradeable stocks
- `script_master`: NSE instrument data
- `stock_ltp_cache`: Cached LTP/prev_close data
- `option_chain_cache`: Cached option chain data
- `sector_stock_mapping`: Sector→stocks mapping

## Upcoming Tasks
- P2: Historical signal performance tracking enhancements
- Advanced IV analytics (waiting for 30+ days of iv_history data)

## File Architecture
```
/app/backend/
├── server.py (615 lines)
├── routes/market_data.py (heatmap endpoints + kite status fix)
├── services/
│   ├── fno_signal_engine.py
│   ├── confluence_score_v2.py (bucket D fix)
│   ├── kite_client.py
│   ├── fundamental_data.py
│   ├── user_service.py
│   ├── validators.py
│   ├── cache_helpers.py
│   └── sector_momentum.py
├── data/lot_sizes.py
└── tests/
    ├── test_iteration51_arch_extraction.py
    ├── test_iteration52_phase6_audit.py
    └── test_iteration51_p0p1.py (NEW)

/app/frontend/src/
├── App.js
├── components/
│   ├── Layout/
│   │   ├── AppSidebar.jsx (nav-heatmap added)
│   │   └── SubTabs.jsx (NEW)
│   ├── FNO/
│   │   └── FNODashboard.jsx (sub-tabs + 3-col layout + IndexPane)
│   ├── MarketHeatmap/ (NEW)
│   │   ├── MarketHeatmapDashboard.jsx
│   │   ├── SectorHeatmap.jsx
│   │   ├── StocksHeatmap.jsx
│   │   └── OptionsHeatmap.jsx
│   └── ...
```
