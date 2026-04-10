# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal sole source for all spot/NFO data — no yfinance fallbacks)

## Implemented Features

### Phase 1: Core
- JWT-based auth with owner/sub_admin/free roles
- F&O Signal Engine with Confluence V2 scoring (CONFLUENCE_THRESHOLD=40)
- NIFTY/BANKNIFTY projections + Top 15 stock signals
- MFE/MAE engine, ATR-based targets, position sizing
- BBE (Best Budget Entry) with 3-source model (ATR pullback + MAE median + day_low support)

### Phase 2: Architecture Hardening
- Modularized server.py (3578 → 2218 lines)
- Extracted: kite_client.py, fundamental_data.py, user_service.py, validators.py
- 55+ test iterations passing

### Phase 3: Market Data, Heatmaps & Signal Fixes
- **Kite Universal Data Source**: Direct `NFO:tradingsymbol` via `/quote` API
- **F&O Signal Fix**: BucketD hard_veto lowered from 0.8 to 0.5
- **Kite API Circuit Breaker**: Consecutive timeout detection
- **Sector Momentum**: 18 NSE Index Sectors (auto-fetch, 30s auto-refresh with force_refresh)
- **Market Heatmap Dashboard** with 3 sub-tabs (Sector/Stocks/Options)
- **Kite Session Health Monitor**: 60s background polling, alarm + browser notification

### Phase 4: Streaming & Reliability (2026-04-10)
- **NDJSON Partial Chunk Streaming**: Progressive rendering (NIFTY first, then BANKNIFTY)
- **NDJSON Keep-alive Heartbeats**: 5s padding prevents K8s ingress idle timeout
- **3-Column Layout**: NIFTY (max 4) | BANKNIFTY (max 4) | Top 4 Best Individual Stock Trades
- **Keep-alive Heartbeat System**: `/api/heartbeat` + 60s frontend polling
- **Warning System**: CDN mp3 alarm (5s max volume), browser notifications, "API Authentication Failed"
- **Force-refresh Cache Busting**: Sector Heatmap + Sectors Dashboard with `force_refresh=true`

### Phase 5: BBE Alerts, Session Health & Performance Tracking (2026-04-10)
- **Session Health Monitor**: Green "Live" / Red "Offline" indicator button in header before Logout. Polls `/api/kite/status` every 60s. Click to force recheck.
- **Market Heatmap on Landing Dashboard**: Added as native card in Home grid alongside Multibagger, F&O, Portfolio, Sectors.
- **Real-Time BBE Alerts**: New `/api/fno/bbe-alerts` endpoint. Fetches live LTP from Kite for recent signals, compares against BBE zone. Frontend `BBEAlertMonitor` polls every 30s during market hours. Triggers "NOW BUY" alert with CDN alarm when LTP enters BBE zone.
- **Signal Performance Tracking**: Fully wired sub-tab in F&O dashboard with 3 views:
  - **Performance**: Win rate, avg P&L, best/worst trades, by-symbol breakdown
  - **Closed Trades**: Archived terminal cards with outcomes
  - **Signal Log**: All generated signals with direction, entry, score, timestamps
- **Kite Universal Data Source Verified**: No yfinance or external fallbacks in any production data path.

### Phase 6: Sector Drill-down (2026-04-10)
- **Click-to-expand drill-down**: Click any sector tile → inline panel shows constituent stocks with live Kite LTP, change %, color-coded gainers/losers
- Works in both **SectorsDashboard** (Sectors tab) and **SectorHeatmap** (Market Heatmap tab)
- **Reusable SectorDrillDown component** with close button, stock count, gainers/losers count, Live badge
- **Toggle behavior**: Click same sector again to close
- **Cyan ring highlight** on selected sector card

### UI/Navigation
- Main tabs: Home, Multibagger, F&O Projections, Portfolio, Sectors, Market Heatmap, Admin
- Sub-tabs for Market Heatmap: Sector Heatmap | Stocks Heatmap | Options Heatmap
- Sub-tabs for F&O: Custom Script & F&O Generation | Signal Performance Tracking | IV Analytics & Multi-Timeframe

## Key API Endpoints
- `/api/fno/generate` — NDJSON streaming F&O signals (keepalive + partial + complete)
- `/api/fno/bbe-alerts` — Real-time BBE zone monitoring with live Kite LTP
- `/api/fno/performance-stats` — Aggregated performance statistics
- `/api/fno/signal-history` — Archived terminal cards with outcomes
- `/api/fno/signal-log` — All generated signals log
- `/api/heartbeat` — Keep-alive ping
- `/api/kite/status` — Session health check
- `/api/sector-momentum` — 18 NSE index sectors
- `/api/market/stock-heatmap?filter=nifty50` — Stock heatmap data
- `/api/market/options-heatmap?filter=RELIANCE` — Stock-specific options chain
- `/api/market/industry-sectors` — 29 industry sectors

## Upcoming Tasks
- None remaining from current spec

## Future/Backlog
- Advanced IV analytics: IV cone + IV term structure (needs 30+ days iv_history data)
- fno_signal_engine.py refactoring (~2800 lines → modular strategy files)
