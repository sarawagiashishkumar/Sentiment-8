# CHANGELOG — Trading Signals & F&O Platform

## 2026-04-12 — Phase 34: Deep Code Review & Bug Fixes
- Fixed dead/unreachable code in server.py WebSocket handler
- Fixed check_usage_limit to use DB packages, search_users to sanitize output
- Parallelized get_data_stats with asyncio.gather (10x faster)
- Fixed N+1 queries in payments.py and fraud.py (batch $in usernames)
- Added session cleanup (30m/24h TTL), help room cleanup (10m), session logs memory cap
- Fixed duplicate fno_signal_log index conflict
- Test: iteration 92 — 16/16 backend, 100% frontend

## 2026-04-12 — Phase 33: Clean Desk Protocol + 7 Items
- Plan Comparison Page: New /plans nav tab with 4 tier cards, feature comparison, low-credits modal
- admin.py domain extraction: 5 endpoints moved to admin_domains.py (1317→1107 lines)
- Type hints: services/app_state.py fully annotated
- Payment history: GET /admin/payments/history with Pending/History tabs in admin UI
- Fraud dashboard: Summary cards (Total/Pending/Resolved) + filter tabs
- Live data isolation: Audit confirmed clean (WebSocket, apiDedup, silent refresh)
- Test: iteration 87 — 26/26 backend, 100% frontend

## 2026-04-12 — Phase 32: Superadmin CRUD Expansion & Dynamic Plans
- User suspend/unsuspend, credit top-up, bulk credit adjustment, CSV export
- Dynamic package CRUD (MongoDB-backed), global feature fee management
- Test: iteration 86 — 25/25 backend, 100% frontend

## 2026-04-12 — Phase 31: Component & Route Splitting
- FNODashboard → FNOExportTable + useFNOGeneration (62% reduction)
- OptionsHeatmap → 4 sub-components (62% reduction)
- routes/fno.py → fno_backtest, fno_iv, fno_cards (44% reduction)
- Test: iteration 85 — 26/26 backend, 100% frontend

## 2026-04-12 — Phase 28-30: Code Quality Report Fixes
## 2026-04-12 — Phase 22-27: Razorpay, WebRTC, Voice AI, Mobile, Permissions
## 2026-04-12 — Phase 19-21: Charts, Reports, Watchlist, Backtester, Alerts, CRM, Fraud
## 2026-04-12 — Phase 1-18: Core features through notification center
