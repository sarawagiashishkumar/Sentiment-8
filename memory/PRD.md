# PRD — Trading Research Platform (F&O Application)

## Original Problem Statement
Build a professional F&O trading research application with:
- Kite Connect as the **absolute primary** data source (universal truth)
- Strict backend-only calculations (no LLM hallucinations for numbers)
- Mandatory fundamental filters on NSE F&O universe
- Master Spec v2.0 multi-batch implementation

## Core Architecture Rules
1. ALL numeric calculations in backend Python only
2. **Kite Connect is the universal data source** — use `/quote` with `exchange:tradingsymbol` format
3. Kite `/quote` API accepts `NSE:symbol` for equities, `NFO:tradingsymbol` for options — NO instrument token DB dependency
4. Strict fundamental filters on NSE F&O universe
5. NDJSON streaming for long-running endpoints
6. News/sentiment from RSS feeds (Kite has no news API) — only non-Kite exception
7. Fundamental data/Piotroski from dedicated service (Kite has no balance sheet data) — only non-Kite exception

## Current State (April 10, 2026)
- Backend: FastAPI, Python 3.11, `server.py` ~615 lines
- Frontend: React with Shadcn UI, Tailwind CSS
- Database: MongoDB (`test_database`)
- Test Suite: 133 unit tests passing (100% green)
- Auth: Custom token-based via POST /api/auth/access
- Kite: CONNECTED (validated via real API call to Kite profile endpoint)
- Users: 3 (admin, @shish123 owner, Manas@2005 user)

## What's Been Implemented

### Phase 1-5: Core Engine (DONE)
- F&O signal generation engine with 4-bucket confluence scoring (A/B/C/D)
- V2 confluence score with MFE/MAE probability targets
- Price Band Engine with mathematical audit
- Multibagger Screener
- Portfolio analysis
- Sector momentum dashboard (8 NSE sector indices)
- Signal history tracking, IV Analytics, Multi-timeframe analysis

### Phase 6: Architecture Hardening (DONE)
- `server.py` modularized from 3578 → 615 lines
- Extracted services: kite_client, fundamental_data, user_service, validators, cache_helpers, lot_sizes

### Phase 7: P0 Fixes + P1 UI Overhaul (DONE — April 10, 2026)

**P0 Fixes:**
- **Kite Token Validation**: `/api/kite/status` now makes real API call to Kite `/user/profile` — no more false-positive "connected" status
- **F&O Signal Suppression**: `compute_bucket_d` no longer penalizes with -15 when t2_p_hit=None (MFE data unavailable). Uses neutral 0.50 default
- **Kite Universal Data Source**: 
  - `get_stock_core()` uses Kite `/quote` as PRIMARY (MoneyControl only for indices fallback)
  - `_fetch_option_ltps_from_kite()` uses `NFO:tradingsymbol` directly — no `kite_option_master` dependency
  - `_fetch_option_snapshots_from_kite()` uses `NFO:tradingsymbol` directly
  - `_fetch_live_option_snapshot()` removed MoneyControl fallback — Kite only per user directive
  - New `fetch_kite_batch_quotes()` for bulk equity quotes (400/batch)
  - New `fetch_kite_batch_option_quotes()` for bulk option quotes
- **BBE Enhancement**: Best Budget Entry now uses 3-source model:
  1. MAE-based: Historical "lowest price before T1" from MFE library (median_mae_pct)
  2. Kite day_low: Session floor support (day_low * 1.02)
  3. ATR-adjusted pullback: Dynamic option ATR estimate (replaces fixed 12/15/20%)

**P1 Features:**
- **Sub-Menu Navigation**: SubTabs component used across F&O, Market HeatMap, Admin
- **F&O Sub-Tabs**: "Signals & Custom" | "Signal Performance" | "IV Analytics & Multi-TF"
- **F&O 3-Column Layout**: NIFTY (sticky) | BANKNIFTY | Top 4 Trades + max 15 stock signals
- **Market HeatMap Section**: New nav tab with 3 sub-tabs:
  - Sector Heatmap (click → constituent stocks drill-down)
  - Stocks Heatmap with filters (Nifty50, BankNifty, FNO, +5%, +3%, -3%, -5%) — **LIVE from Kite**
  - Options Heatmap with NIFTY/BANKNIFTY option chains — **LIVE from Kite** (21 strikes, PCR)
- **Admin Sub-Tabs**: User Management | API Controls & Domains | Macro Events | Kite Connect | CSV Seeds
- **"No Live Data" Warning**: KiteLiveWarning popup on all data-dependent pages when Kite disconnected
- **DB Cleanup**: Removed all testing agent users and duplicate owner accounts

## Key API Endpoints
- `/api/auth/access` — Login
- `/api/kite/status` — Real Kite token validation
- `/api/fno/generate` — F&O signal generation (NDJSON stream)
- `/api/sector-momentum` — Sector momentum data
- `/api/market/stock-heatmap` — **LIVE** stock heatmap from Kite /quote
- `/api/market/options-heatmap` — **LIVE** options chain from Kite /quote
- `/api/market/sector-stocks` — Sector constituent stocks

## Database Schema (test_database)
- `app_users`: 3 real users only
- `system_meta`: Kite session (validated via real API call)
- `fno_signal_history/log`: Signal tracking
- `iv_history`: IV snapshots
- `kite_option_master`: Used only for options heatmap strike lookup (instrument sync)
- `index_constituents`: Sector→stock mappings

## Upcoming Tasks
- P2: Historical signal performance tracking enhancements
- Advanced IV analytics (waiting for 30+ days of iv_history data)
- Real-time WebSocket price updates for heatmaps

## File Architecture
```
/app/backend/
├── server.py (615 lines)
├── routes/market_data.py (Kite-powered heatmap endpoints)
├── services/
│   ├── kite_client.py (batch quotes, NFO:tradingsymbol, no option master dep)
│   ├── fno_signal_engine.py (3-source BBE model)
│   ├── confluence_score_v2.py (Bucket D no-penalty fix)
│   ├── market_data.py (get_stock_core = Kite primary)
│   └── mfe_mae_engine.py (MAE library for BBE)
├── data/lot_sizes.py (149 F&O stocks)
└── tests/ (133 tests, 100% green)

/app/frontend/src/
├── App.js (KiteLiveWarning integration)
├── components/
│   ├── Layout/SubTabs.jsx (shared sub-tab component)
│   ├── FNO/FNODashboard.jsx (sub-tabs + 3-col + IndexPane)
│   ├── MarketHeatmap/ (Sector/Stocks/Options heatmaps)
│   ├── Admin/AdminDashboard.jsx (5 sub-tabs)
│   └── Shared/KiteLiveWarning.jsx
```
