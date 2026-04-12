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

### Phase 4-9: Streaming, Alerts, Modularization, Code Quality (Details in CHANGELOG.md)

### Phase 10: Critical System Fixes & UI/UX Standardization
### Phase 11: NDJSON Streaming Latency Fix & Auto-Refresh
### Phase 12: Modularization & IV Analytics Enhancement
### Phase 13: Confluence Extraction, Performance Profiling & IV Collection
### Phase 14: App Polish & Hardening
### Phase 15: Notification Center, Final Modularization & Perf Thresholds
### Phase 16: Push Notifications, Persistence & Final Engine Modularization
### Phase 17: Trading Journal, Benchmarking, IV Collector & Analytics
### Phase 18: Code Quality Report Fixes
### Phase 19: TradingView Charts, Reports, Watchlist & Backtester
### Phase 20: Senior Code Audit — Bug Fixes, Performance & Enhancements
### Phase 21: Custom Alert Rule Engine, Admin Permissions, Fraud Detection & CRM
### Phase 22: Razorpay, Offline QR Payments, WebRTC Live Help & Senior Audit
### Phase 23: Screen Sharing + Senior Technical Audit — Zero-Lag Performance
### Phase 24: Deep Senior Audit — All-Tab Parity Check + Bug Fixes
### Phase 25: Critical Chunk Loading Fix + AI Support Agent
### Phase 26: Mobile Responsiveness + Permissions CRUD
### Phase 27: Voice-Enabled Multilingual AI Support Agent
### Phase 28-30: Code Quality Report Fixes (auth, alerts, CRM, hooks, models)

### Phase 31: Code Quality — Component & Route Splitting (2026-04-12)
- **FNODashboard Split**: Extracted `FNOExportTable.jsx` (56 lines) and `useFNOGeneration.js` hook (84 lines). Dashboard orchestrator reduced to 311 lines.
- **OptionsHeatmap Split**: Extracted `OptionsControls.jsx` (116 lines), `OptionsSymbolSearch.jsx` (87 lines), `OptionsTreemapView.jsx` (23 lines), `OptionsChainView.jsx` (60 lines). Orchestrator reduced from 407 → 156 lines (62% reduction).
- **Backend fno.py Split**: Extracted `fno_backtest.py` (202 lines), `fno_iv.py` (124 lines), `fno_cards.py` (149 lines). Core fno.py reduced from 1227 → 692 lines (44% reduction).
- **All 26 backend tests pass. Full frontend verification: 8 main tabs, 10 admin sub-tabs, 6 F&O sub-tabs, 3 heatmap sub-tabs all working.**
- **Mock data purge**: CRM, notifications, livehelp, fraud, sessions all cleaned from DB.

## Code Quality Completion Status
| Item | Status |
|------|--------|
| Circular import chain (server↔services) | FIXED |
| Auth function complexity | FIXED (15→5) |
| Alert system complexity | FIXED (34→<10) |
| App.js complexity | FIXED (68→~25) |
| AdminDashboard complexity | FIXED (96→~20) |
| CRM admin_send_message | FIXED |
| Empty catch blocks | FIXED |
| Hook dependencies | FIXED |
| Model nesting | FIXED |
| Console cleanup | DONE |
| FNODashboard split | DONE (Phase 31) |
| OptionsHeatmap split | DONE (Phase 31) |
| routes/fno.py split | DONE (Phase 31) |
| Type hint coverage | BACKLOG |
| admin.py complexity | BACKLOG |

## Key API Endpoints
- `/api/health` — Comprehensive health check
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/fno/bbe-alerts` — Real-time BBE zone monitoring
- `/api/fno/performance-stats` — Aggregated performance stats
- `/api/fno/signal-log` — Signal generation log
- `/api/fno/run-backtest` — Strategy backtester
- `/api/fno/iv-cone/{symbol}` — IV Cone percentile bands
- `/api/fno/iv-term-structure/{symbol}` — IV term structure
- `/api/fno/iv-collect-now` — One-shot IV snapshot
- `/api/fno/generation-timings` — Phase timing metrics
- `/api/fno/sticky-cards` — Sticky card management
- `/api/fno/custom-positions` — Custom position CRUD
- `/api/fno/multi-timeframe/{symbol}` — Multi-timeframe analysis
- `/api/ws/prices` — WebSocket live price streaming
- `/api/watchlist` — Watchlist CRUD with price alerts
- `/api/notifications` — Notification CRUD
- `/api/journal` — Trading journal CRUD
- `/api/reports/daily-summary` — Daily P&L report
- `/api/alerts/rules` — Custom Alert Rules CRUD
- `/api/admin/packages` — Package tiers
- `/api/admin/users/{ref}/permissions` — User permissions
- `/api/payments/*` — Razorpay + offline QR payments
- `/api/livehelp/*` — WebRTC live help + AI support
- `/api/crm/*` — CRM messaging

## Future/Backlog
- P1: Expand Superadmin CRUD capabilities (bulk user actions, export, delete)
- P1: Isolate live data fetching logic (WebSocket/API perf optimization)
- P2: `admin.py` complexity reduction (`admin_map_domain`, `get_user_permissions`)
- P2: Type hints on public APIs (models + services first)
- P2: Security review of dynamic imports in test files
- P3: Payment history accumulation as users reactivate
- P3: Fraud incidents accumulation tracking
