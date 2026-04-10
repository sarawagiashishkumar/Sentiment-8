# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal source for all spot/NFO data)

## Implemented Features (as of 2026-04-10)

### Phase 1: Core
- JWT-based auth with owner/sub_admin/free roles
- F&O Signal Engine with Confluence V2 scoring (CONFLUENCE_THRESHOLD=40)
- NIFTY/BANKNIFTY projections + Top 15 stock signals
- MFE/MAE engine, ATR-based targets, position sizing
- BBE (Best Budget Entry) with historical MAE median

### Phase 2: Architecture Hardening
- Modularized server.py (3578 → 2218 lines)
- Extracted: kite_client.py, fundamental_data.py, user_service.py, validators.py
- Full test suite: 53+ passing test iterations

### Phase 3: Market Data & Heatmaps (Current)
- **Kite Universal Data Source**: Direct `NFO:tradingsymbol` via `/quote` API
- **Sector Momentum**: 18 NSE Index Sectors (auto-fetch, 30s auto-refresh)
- **Market Heatmap Dashboard** with 3 sub-tabs:
  - **Sector Heatmap**: NSE Index Sectors (18) + Industry Sectors (29), auto-fetch on mount, drill-down to constituents
  - **Stocks Heatmap**: NIFTY50/BANKNIFTY/F&O Universe/ALL filters, Treemap/List views, auto-fetch & auto-refresh, filter switch auto-reload
  - **Options Heatmap**: NIFTY/BANKNIFTY + stock-specific chains (RELIANCE, TCS, HDFCBANK), CE/PE/ALL filters, custom stock search, Min OI slider, Treemap/Chain views
- **Kite Session Health Monitor**: 60s background polling of /api/kite/status, alarm sound + browser notification on disconnection (no "Kite" name in UI)
- **F&O Signal Quality Fix**: Signal quality labels recalibrated (≥75=HIGH, ≥55=MEDIUM, <55=LOW)
- **Conviction Levels**: Recalibrated for CONFLUENCE_THRESHOLD=40

### UI/Navigation
- Main tabs: Home, Multibagger, F&O Projections, Portfolio, Sectors, Market Heatmap, Admin
- Sub-tabs for Market Heatmap: Sector Heatmap | Stocks Heatmap | Options Heatmap
- Admin sub-menus for admin management

## Key API Endpoints
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/kite/status` — Session health check
- `/api/sector-momentum` — 18 NSE index sectors
- `/api/market/stock-heatmap?filter=nifty50` — Stock heatmap data
- `/api/market/options-heatmap?filter=RELIANCE` — Options chain
- `/api/market/industry-sectors` — 29 industry sectors
- `/api/market/sector-stocks?sector=SECTOR` — Sector constituent stocks

## Key DB Collections
- `app_users`: fno_budget, account_risk_pct
- `fno_signal_history`, `fno_signal_log`: Signal tracking
- `iv_history`: IV snapshots
- `index_constituents`: Nifty/BankNifty component stocks

## File Architecture
```
/app/backend/
├── server.py (~616 lines)
├── routes/
│   ├── fno.py
│   ├── market_data.py (industry-sectors, options-heatmap, stock-heatmap)
│   └── batch_jobs.py
├── services/
│   ├── kite_client.py (universal Kite /quote API)
│   ├── fno_signal_engine.py (signal quality fix)
│   ├── confluence_score_v2.py (THRESHOLD=40, conviction recalibrated)
│   ├── sector_momentum.py (18 NSE indices)
│   └── ...
├── tests/
│   ├── test_iteration54_market_heatmap_autofetch.py
│   ├── test_iteration53_major_update.py
│   └── test_iteration51_arch_extraction.py
/app/frontend/src/
├── components/
│   ├── MarketHeatmap/ (SectorHeatmap, StocksHeatmap, OptionsHeatmap, Dashboard)
│   ├── Sectors/SectorsDashboard.jsx
│   ├── Shared/KiteLiveWarning.jsx (health monitor + alarm)
│   ├── FNO/FNODashboard.jsx
│   └── Admin/AdminDashboard.jsx
└── App.js
```

## Upcoming Tasks
- P2: Verify Sector Heatmap Drill-down (click sector → constituent stocks list)
- P2: Historical signal performance tracking (wire up existing sub-tab)

## Future/Backlog
- Advanced IV analytics: IV cone + IV term structure (needs 30+ days iv_history)
