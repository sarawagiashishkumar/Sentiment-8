# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal sole source — no yfinance fallbacks)

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

### Phase 3: Market Data, Heatmaps & Signal Fixes
- Kite Universal Data Source: Direct NFO:tradingsymbol via /quote API
- F&O Signal Fix: BucketD hard_veto lowered from 0.8 to 0.5
- Kite API Circuit Breaker: Consecutive timeout detection
- Sector Momentum: 18 NSE Index Sectors (auto-fetch, 30s auto-refresh with force_refresh)
- Market Heatmap Dashboard with 3 sub-tabs (Sector/Stocks/Options)
- Kite Session Health Monitor: 60s background polling, alarm + browser notification

### Phase 4: Streaming & Reliability
- NDJSON Partial Chunk Streaming: Progressive rendering (NIFTY first, then BANKNIFTY)
- NDJSON Keep-alive Heartbeats: 5s padding prevents K8s ingress idle timeout
- 3-Column Layout: NIFTY (max 4) | BANKNIFTY (max 4) | Top 4 Best Individual Stock Trades
- Keep-alive Heartbeat System: /api/heartbeat + 60s frontend polling
- Warning System: CDN mp3 alarm (5s max volume), browser notifications, "API Authentication Failed"
- Force-refresh Cache Busting: Sector Heatmap + Sectors Dashboard with force_refresh=true

### Phase 5: BBE Alerts, Session Health & Performance Tracking
- Session Health Monitor: Green "Live" / Red "Offline" indicator in header before Logout
- Market Heatmap on Landing Dashboard: Native card in Home grid
- Real-Time BBE Alerts: /api/fno/bbe-alerts with live LTP monitoring + "NOW BUY" CDN alarm
- Signal Performance Tracking: Fully wired sub-tab (Performance/Closed Trades/Signal Log)

### Phase 6: Sector Drill-down
- Click-to-expand drill-down: Click any sector tile → inline panel with constituent stocks + live Kite data
- Works in both SectorsDashboard and SectorHeatmap
- Toggle behavior + cyan ring highlight + close button

### Phase 7: Critical Bug Fixes (2026-04-10)
- **AdminDashboard ReferenceError FIXED**: Added missing `UserCog` import from lucide-react — Admin panel was completely inaccessible
- **Unicode \u2b50 rendering FIXED**: Removed all `\u2b50` star emoji references that were rendering as literal text on mobile devices. Affected: FNOTargetPanel, FNOStickyCards, FNOSignalCard, FNODashboard
- **Ghost user investigation**: Verified database is clean — only 2 legitimate users (Manas@2005, @shish123). The "⭐ Before Best Exit" text user saw was the BEST EXIT feature label (now cleaned up)

## Key API Endpoints
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/fno/bbe-alerts` — Real-time BBE zone monitoring
- `/api/fno/performance-stats` — Aggregated performance statistics
- `/api/fno/signal-log` — All generated signals log
- `/api/heartbeat` — Keep-alive ping
- `/api/kite/status` — Session health check
- `/api/sector-momentum` — 18 NSE index sectors
- `/api/market/sector-stocks?sector=X` — Sector drill-down stocks
- `/api/market/stock-heatmap` — Stock heatmap data
- `/api/market/options-heatmap` — Options heatmap data
- `/api/admin/users` — User management

## Future/Backlog
- Advanced IV analytics: IV cone + IV term structure (needs 30+ days iv_history data)
- fno_signal_engine.py refactoring (~2800 lines → modular strategy files)
