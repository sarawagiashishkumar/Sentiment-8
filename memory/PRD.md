# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal sole source)

## Implemented Features (Latest)

### Phase 33: Clean Desk Protocol + 7 Items (2026-04-12)
- **Plan Comparison Page**: New `/plans` nav tab (9th button). 4 tier cards (Free/Basic/Pro/Unlimited) showing credits, usage limits (7 categories), feature access (9 features with check/X marks), and credit costs. "CURRENT" badge on active plan. Contact-admin CTA.
- **Low-Credits Modal**: Auto-triggers when non-owner user credits drop below 5 (once per session). Shows current balance, upgrade options, dismiss button.
- **Live Data Fetch Isolation**: Audited — `useLivePrices.js` (WebSocket, non-blocking), `apiDedup.js` (request dedup), heatmap silent refresh all confirmed clean. No changes needed.
- **admin.py Domain Extraction**: Extracted domain mapping CRUD (5 endpoints, ~210 lines) into `routes/admin_domains.py`. admin.py reduced from 1317→1107 lines.
- **Type Hints**: `services/app_state.py` fully annotated with `Optional`, `dict`, `list`, `AsyncIOMotorDatabase`, return types.
- **Payment History**: New `GET /admin/payments/history` endpoint with pagination. AdminPaymentsPanel enhanced with Pending/History tabs + history table (User, Amount, Method, Status, Purpose, Date).
- **Fraud History Dashboard**: AdminFraudPanel enhanced with 3 summary cards (Total/Pending/Resolved), filter tabs (All/Pending/Resolved), enriched incident cards with detection type and resolved date.
- Test: iteration 87 — 26/26 backend, 100% frontend.

### Phase 32: Superadmin CRUD Expansion & Dynamic Plans (2026-04-12)
- User suspend/unsuspend, credit top-up, bulk credit adjustment, CSV export
- Dynamic package CRUD (MongoDB-backed), global feature fee management
- Test: iteration 86 — 25/25 backend, 100% frontend.

### Phase 31: Component & Route Splitting (2026-04-12)
- FNODashboard, OptionsHeatmap, routes/fno.py all split into sub-modules
- Test: iteration 85 — 26/26 backend, 100% frontend.

### Phase 28-30: Code Quality Report Fixes
### Phase 22-27: Razorpay, WebRTC, Voice AI, Mobile, Permissions
### Phase 19-21: Charts, Reports, Watchlist, Backtester, Alerts, CRM, Fraud
### Phase 1-18: Core features through notification center

## Navigation Structure
- **Main Nav (9 tabs)**: Home, Multibagger, F&O Projections, Portfolio, Market HeatMap, Reports, Watchlist, Plans, Admin
- **Admin Sub-tabs (10)**: User Management, Permissions & Packages, Payments, CRM, Fraud Detection, Advanced Controls, Macro Events, Gen Performance, API Connect, CSV Seeds
- **F&O Sub-tabs (6)**: Signals, Alert Rules, Trading Journal, Backtester, Performance, IV Analytics

## Code Quality Status
| Item | Status |
|------|--------|
| Circular imports | FIXED |
| Auth/Alert/CRM complexity | FIXED |
| FNODashboard/OptionsHeatmap split | DONE |
| routes/fno.py split | DONE |
| admin.py domain extraction | DONE |
| Superadmin CRUD | DONE |
| Dynamic Plans & Fees | DONE |
| Type hints (app_state.py) | DONE |
| Live data isolation audit | DONE (clean) |
| Plans comparison page | DONE |
| Payment/Fraud history | DONE |

## Future/Backlog
- P2: Type hints on models/__init__.py + remaining services
- P2: Security review of dynamic imports in test files
- P3: Multi-currency payment support
