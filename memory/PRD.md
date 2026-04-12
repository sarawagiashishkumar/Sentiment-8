# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets. Real-time signal generation, sector momentum analysis, and market heatmaps.

## Architecture
- **Backend**: FastAPI (Python) — all numeric computations server-side
- **Frontend**: React + Shadcn UI + Recharts
- **Database**: MongoDB
- **Data Source**: Kite Connect API v3 (universal sole source)

## Latest: Phase 34 — Critical Bug Fixes (2026-04-13)
- **Heartbeat Fix**: Increased inactivity buffer 10min→30min, reduced ping 60s→30s. Prevents premature "Disconnected" warnings
- **Tab Activity Tracking**: Menu/tab navigation now counts as user activity via `handlePageChange` — resets heartbeat timer
- **AI Agent Markdown Cleanup**: Strips `**bold**`, `***italic***`, `#headings`, `` `code` `` from AI responses for professional plain-text display
- **LiveHelp UI Simplification**: Removed dual mic buttons. Single mic icon inside text input for speech-to-text in chat mode. Phone icon for voice/chat toggle
- **Multibagger Badge Contrast**: Score/WATCH badges now use `bg-slate-700 text-slate-200` for readability on dark backgrounds
- **Heatmap Neutral Colors**: Near-zero change values (<0.05%) show neutral gray instead of faint green/red
- Test: iteration 88 — 11/11 backend, 100% frontend

## Phase 33: Clean Desk + 7 Items (2026-04-12)
- Plan Comparison Page, Payment History, Fraud Dashboard, Domain Extraction, Type Hints

## Phase 32: Superadmin CRUD Expansion (2026-04-12)
- Suspend/Unsuspend, Topup, Bulk Credits, CSV Export, Dynamic Packages, Global Fees

## Phase 31: Component & Route Splitting (2026-04-12)
- FNODashboard, OptionsHeatmap, routes/fno.py split into sub-modules

## Navigation
- **Main Nav (9 tabs)**: Home, Multibagger, F&O, Portfolio, HeatMap, Reports, Watchlist, Plans, Admin
- **Admin Sub-tabs (10)**: Users, Permissions, Payments, CRM, Fraud, Controls, Macro, Perf, API, CSV
- **F&O Sub-tabs (6)**: Signals, Alerts, Journal, Backtester, Performance, IV Analytics

## Pending / Next Sprint
- P0: Price Band Upgrade (equity_master_cache + price_band_engine from user's specification)
- P0: News & Sentiment pre/post-market forecasts
- P1: QR image upload for offline payments + Razorpay enable/disable toggle
- P1: Advanced Controls — custom API add/edit/delete
- P2: Type hints on models/__init__.py
- P2: Security review of dynamic imports
