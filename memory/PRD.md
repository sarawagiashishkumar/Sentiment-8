# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal source for all spot/NFO data)

## Implemented Features

### Phase 1: Core
- JWT-based auth with owner/sub_admin/free roles
- F&O Signal Engine with Confluence V2 scoring (CONFLUENCE_THRESHOLD=40)
- NIFTY/BANKNIFTY projections + Top 15 stock signals
- MFE/MAE engine, ATR-based targets, position sizing
- BBE (Best Budget Entry) with historical MAE median

### Phase 2: Architecture Hardening
- Modularized server.py (3578 → 2218 lines)
- Extracted: kite_client.py, fundamental_data.py, user_service.py, validators.py
- 55+ test iterations passing

### Phase 3: Market Data, Heatmaps & Signal Fixes (Current - 2026-04-10)
- **Kite Universal Data Source**: Direct `NFO:tradingsymbol` via `/quote` API
- **F&O Signal Fix**: BucketD hard_veto lowered from 0.8 to 0.5, allowing CE signals with R:R 0.5-0.8 to pass. Signal quality labels recalibrated (≥75=HIGH, ≥55=MEDIUM, <55=LOW). Conviction levels adjusted for THRESHOLD=40.
- **Kite API Circuit Breaker**: Consecutive timeout detection skips remaining batches after 2 failures.
- **Sector Momentum**: 18 NSE Index Sectors (auto-fetch, 30s auto-refresh)
- **Market Heatmap Dashboard** with 3 sub-tabs (matching reference app design):
  - **Sector Heatmap**: NSE Index Sectors (18) + Industry Sectors (29). All tiles same teal gradient. No summary badges. No refresh button. Auto-fetch on mount.
  - **Stocks Heatmap**: 3 filters only (NIFTY50/BANKNIFTY/ALL). Full-width CSS grid treemap. Grid/List toggle + color range bar + stock count on same row. Auto-fetch + auto-reload on filter switch.
  - **Options Heatmap**: NIFTY/BANKNIFTY + stock-specific chains (RELIANCE/TCS/HDFCBANK). ALL/CE/PE filter tabs. Expiry dropdown. Custom Stock search. Min OI slider. CE tiles=teal, PE tiles=magenta. Treemap/Chain views.
- **Sub-tabs**: Plain text without icons, active tab = cyan pill (matching reference).
- **Kite Session Health Monitor**: 60s background polling, alarm sound + browser notification on disconnect.

### UI/Navigation
- Main tabs: Home, Multibagger, F&O Projections, Portfolio, Sectors, Market Heatmap, Admin
- Sub-tabs for Market Heatmap: Sector Heatmap | Stocks Heatmap | Options Heatmap

## Key API Endpoints
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/kite/status` — Session health check
- `/api/sector-momentum` — 18 NSE index sectors
- `/api/market/stock-heatmap?filter=nifty50` — Stock heatmap data
- `/api/market/options-heatmap?filter=RELIANCE` — Stock-specific options chain
- `/api/market/industry-sectors` — 29 industry sectors

## Upcoming Tasks
- P2: Sector Heatmap Drill-down (click sector → constituent stocks list)
- P2: Historical signal performance tracking (wire up existing sub-tab)

## Future/Backlog
- Advanced IV analytics: IV cone + IV term structure (needs 30+ days iv_history data)
