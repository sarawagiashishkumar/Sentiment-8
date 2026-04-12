# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal sole source — no yfinance fallbacks)

## Implemented Features

### Phase 1-9: Core, Architecture, Heatmaps, Streaming, Alerts, Modularization, Code Quality
### Phase 10-20: UI/UX, NDJSON Streaming, IV Analytics, Notifications, TradingView, Reports, Watchlist, Backtester
### Phase 21-27: Alert Engine, Permissions, Fraud Detection, CRM, Razorpay, WebRTC, Voice AI Agent
### Phase 28-30: Code Quality Report Fixes (auth, alerts, CRM, hooks, models)

### Phase 31: Code Quality — Component & Route Splitting (2026-04-12)
- **FNODashboard Split**: `FNOExportTable.jsx` + `useFNOGeneration.js` hook extracted. Dashboard 311 lines.
- **OptionsHeatmap Split**: 4 sub-components extracted. Orchestrator 407→156 lines (62% reduction).
- **Backend fno.py Split**: 3 sub-modules extracted. Core fno.py 1227→692 lines (44% reduction).
- Test: iteration 85 — 26/26 backend, 100% frontend.

### Phase 32: Superadmin CRUD Expansion & Dynamic Plans (2026-04-12)
- **User Suspend/Unsuspend**: `POST /admin/users/{user_ref}/suspend` toggles suspended status. UI shows Active/SUSPENDED badges + Suspend/Unsuspend buttons per user row.
- **Credit Top-up**: `POST /admin/users/{user_ref}/topup` adds credits (positive only). Green "Top-up" button per user row opens inline form.
- **Bulk Credit Adjustment**: `POST /admin/users/bulk-credits` adjusts credits for multiple users. Checkboxes on each row, "Select All", bulk panel with +/- credit delta.
- **CSV Export**: `GET /admin/users/export` streams CSV with user_key, username, role, credits, package, suspended, created_by, created_at. "Export CSV" button in header.
- **Dynamic Package CRUD**: Packages now stored in MongoDB (`system_meta` collection) with fallback to hardcoded defaults. `POST /admin/packages` creates/updates tiers. `DELETE /admin/packages/{key}` deletes (protects "free" tier, blocks deletion if users assigned). UI: "+ New Plan" button, inline form with key/label/credits/limits, hover edit/delete on tier cards.
- **Global Feature Fee Management**: `PATCH /admin/feature-costs` updates global default credit costs per feature. UI: "Global Fees" button opens editor with all 9 features (fno_generate, multibagger, portfolio, etc.) with editable number inputs.
- Test: iteration 86 — 25/25 backend, 100% frontend.

## Code Quality Completion Status
| Item | Status |
|------|--------|
| Circular import chain | FIXED |
| Auth function complexity | FIXED (15→5) |
| Alert system complexity | FIXED (34→<10) |
| App.js complexity | FIXED (68→~25) |
| AdminDashboard complexity | FIXED (96→~20) |
| CRM admin_send_message | FIXED |
| Empty catch blocks | FIXED |
| Hook dependencies | FIXED |
| FNODashboard split | DONE (Phase 31) |
| OptionsHeatmap split | DONE (Phase 31) |
| routes/fno.py split | DONE (Phase 31) |
| Superadmin CRUD | DONE (Phase 32) |
| Dynamic Plans & Fees | DONE (Phase 32) |
| Type hint coverage | BACKLOG |
| admin.py complexity | BACKLOG |

## Key API Endpoints
- `/api/health` — Comprehensive health check
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/fno/bbe-alerts` — Real-time BBE zone monitoring
- `/api/fno/run-backtest` — Strategy backtester
- `/api/fno/iv-cone/{symbol}` — IV Cone percentile bands
- `/api/fno/generation-timings` — Phase timing metrics
- `/api/fno/custom-positions` — Custom position CRUD
- `/api/ws/prices` — WebSocket live price streaming
- `/api/watchlist` — Watchlist CRUD with price alerts
- `/api/notifications` — Notification CRUD
- `/api/journal` — Trading journal CRUD
- `/api/reports/daily-summary` — Daily P&L report
- `/api/alerts/rules` — Custom Alert Rules CRUD
- `/api/admin/packages` — Package tiers CRUD (GET/POST/DELETE)
- `/api/admin/feature-costs` — Global feature costs (PATCH)
- `/api/admin/users/{ref}/suspend` — Toggle suspend (POST)
- `/api/admin/users/{ref}/topup` — Credit topup (POST)
- `/api/admin/users/bulk-credits` — Bulk credit adjustment (POST)
- `/api/admin/users/export` — CSV export (GET)
- `/api/admin/users/{ref}/permissions` — User permission management
- `/api/payments/*` — Razorpay + offline QR payments
- `/api/livehelp/*` — WebRTC live help + AI support
- `/api/crm/*` — CRM messaging

## Future/Backlog
- P1: Isolate live data fetching logic (WebSocket/API perf optimization)
- P2: `admin.py` complexity reduction (`admin_map_domain`, `get_user_permissions`)
- P2: Type hints on public APIs (models + services first)
- P2: Security review of dynamic imports in test files
- P3: Payment history accumulation as users reactivate
- P3: Fraud incidents accumulation tracking
