# Trading Signals & F&O Platform — Complete Project Briefing

## Original Problem Statement
Build an AI-driven trading research platform for Indian NSE F&O (Futures & Options) markets. The platform serves a single owner (@shish123) and their sub-admin/user clients. It provides real-time signal generation for NIFTY/BANKNIFTY options, multibagger stock screening, portfolio analysis with price band projections, sector momentum heatmaps, and a full admin control panel for user management, payments, and CRM.

## Architecture

```
/app
├── backend/                    # FastAPI (Python 3.11)
│   ├── server.py               # Main app (1050 lines) — WebSocket endpoints, startup tasks
│   ├── routes/                 # 18 route files (6489 lines total)
│   │   ├── fno.py              # Core F&O signal generation (715 lines)
│   │   ├── fno_backtest.py     # Strategy backtester (202 lines)
│   │   ├── fno_iv.py           # IV analytics (124 lines)
│   │   ├── fno_cards.py        # Sticky cards & events (149 lines)
│   │   ├── admin.py            # User/package/permission CRUD (1175 lines)
│   │   ├── admin_domains.py    # Domain mapping CRUD (223 lines)
│   │   ├── market_data.py      # Heatmaps, sector momentum (784 lines)
│   │   ├── payments.py         # Razorpay + offline QR (373 lines)
│   │   ├── auth.py, alerts.py, crm.py, fraud.py, livehelp.py,
│   │   │   journal.py, multibagger.py, news.py, notifications.py,
│   │   │   portfolio.py, reports.py, risk.py, watchlist.py, batch_jobs.py
│   ├── services/               # 40+ service files (21420 lines total)
│   │   ├── app_state.py        # Shared state (breaks circular imports)
│   │   ├── equity_master_cache.py  # Single source of truth for equity data (524 lines)
│   │   ├── price_band_engine.py    # 6-horizon price band calculator (289 lines)
│   │   ├── fno_signal_engine.py    # Signal generation core
│   │   ├── fno_signal_builder.py   # Signal construction (1201 lines)
│   │   ├── multibagger_engine.py   # Screener with forensic gates (754 lines)
│   │   ├── portfolio_engine.py     # Holdings analysis + verdict (539 lines)
│   │   ├── kite_client.py          # Kite Connect API wrapper (897 lines)
│   │   ├── news_sentiment.py       # RSS + VADER sentiment (639 lines)
│   │   ├── confluence_score_v2.py  # Signal scoring model
│   │   ├── mfe_mae_engine.py       # Max Favorable/Adverse Excursion
│   │   ├── sticky_card_engine.py   # Position monitoring cards
│   │   └── ... (indicators, regime, forensic, IV, etc.)
│   ├── models/__init__.py      # 30+ Pydantic models (fully type-hinted)
│   ├── tests/                  # 91 test iterations
│   └── .env                    # MONGO_URL, DB_NAME, KITE_API_*, EMERGENT_LLM_KEY
├── frontend/                   # React 18 + Shadcn UI
│   ├── src/
│   │   ├── App.js              # Main orchestrator (9 tabs, heartbeat, auth)
│   │   ├── components/         # 113 JSX files across 16 directories
│   │   │   ├── Admin/          # 10 sub-tab panels (Users, Permissions, Payments, CRM, Fraud, Controls, Macro, Perf, API, CSV)
│   │   │   ├── FNO/            # 6 sub-tabs (Signals, Alerts, Journal, Backtester, Performance, IV Analytics)
│   │   │   ├── MarketHeatmap/  # 3 sub-tabs (Sector, Stocks, Options) — split into sub-components
│   │   │   ├── Multibagger/    # Screener dashboard with price bands
│   │   │   ├── Portfolio/      # Analysis + Risk Dashboard
│   │   │   ├── News/           # Sentiment panel on Home
│   │   │   ├── Shared/         # LiveHelpModule (AI voice agent), PlanComparison, Skeletons, etc.
│   │   │   └── ... (Auth, Home, Layout, Reports, Watchlist, Sectors)
│   │   ├── hooks/              # useAuth, useFNOGeneration, useLivePrices, useAlertEngine, use-toast
│   │   └── utils/              # formatters, apiDedup, logger
│   └── .env                    # REACT_APP_BACKEND_URL
└── memory/                     # PRD.md, CHANGELOG.md, ROADMAP.md, test_credentials.md
```

## 3rd Party Integrations
- **Kite Connect API v3** — Universal data source for live prices, OHLCV, option chains (requires user API key)
- **Razorpay** — Online payment processing (requires user API key, configurable via admin panel)
- **Offline QR/UPI** — QR code generation + admin-uploaded QR images for offline payments
- **Emergent LLM Key** — Powers AI Support Agent chat (GPT via emergentintegrations library)
- **WebRTC** — Native browser APIs for voice calls + screen sharing in live help
- **SpeechSynthesis** — Native TTS for AI voice responses in 11 languages
- **RSS + VADER** — News sentiment engine using RSS feeds + VADER NLP scoring

## Key Features (All Implemented & Tested)

### Signal Generation (F&O)
- NDJSON streaming F&O signal generation for NIFTY/BANKNIFTY + Top 15 stocks
- Confluence V2 scoring model (CONFLUENCE_THRESHOLD=40) with 4 sub-buckets
- MFE/MAE engine for optimal exit timing, ATR-based targets, BBE (Best Budget Entry)
- Strategy library (momentum, spreads, straddle, iron condor, butterfly, calendar)
- Real-time BBE zone alerts (`/fno/bbe-alerts`)
- Custom position tracking (CRUD) with monitoring events
- IV analytics: IV Cone, IV Term Structure, background IV collection
- Multi-timeframe analysis (daily/weekly/monthly trend alignment)
- Signal history, performance stats, generation timings

### Multibagger Screener
- equity_master_cache (524 lines) — single source of truth with 60+ fields per symbol
- price_band_engine (289 lines) — 6 horizons (1W/1M/3M/6M/9M/12M), 3 scenarios (conservative/expected/optimistic)
- Regime-aware volatility bands, fundamental scalar, structural floor/ceiling anchoring
- Forensic quality gates (Beneish M-Score, Piotroski F-Score, Altman Z-Score)
- SF2 high-conviction tagging

### Portfolio Analysis
- Upload holdings (CSV or manual entry), per-stock analysis with price bands
- Holding verdict engine: EXIT_IMMEDIATELY, PARTIAL_EXIT, WAIT_AND_WATCH, BUY_MORE_NOW, ACCUMULATE_ON_DIPS, STRONG_HOLD
- Risk dashboard with portfolio-level metrics

### Market Intelligence
- Sector momentum (18 NSE Index Sectors, 30s auto-refresh)
- Stock heatmap (NIFTY50/BANKNIFTY/ALL F&O, treemap + list views)
- Options heatmap (chain view + treemap, OI filter, expiry selection)
- News & Sentiment engine: Pre/post-market forecasts for NIFTY/BANKNIFTY + top 10 stocks
- Background RSS monitor (120s cycle)

### Admin Platform (Superadmin)
- **User Management**: Create/delete users, suspend/unsuspend, credit topup, bulk credit adjustment, CSV export, role assignment
- **Permissions & Packages**: Dynamic package CRUD (MongoDB-backed with fallback defaults), per-user usage limits, feature costs, feature restrictions (block/allow per feature)
- **Global Fee Management**: Set credit costs for all 9 features globally
- **Payments**: Razorpay + offline QR, enable/disable toggles, QR image upload, pending verification queue, payment history with pagination
- **CRM**: Admin→user messaging, inbox/sent views
- **Fraud Detection**: Geospatial "impossible travel" detection, summary cards, filter tabs (All/Pending/Resolved)
- **Advanced Controls**: API toggles (Kite/secondary/strict-live), Custom API endpoints CRUD (add/edit/delete/test)
- **Domain Mappings**: Full DNS/Nginx config management
- **Macro Events**: Market event notes
- **Generation Performance**: FNO/Multibagger phase timing history

### AI Support Agent (WebRTC + Voice)
- LLM-powered chat via Emergent LLM Key
- Single mic in text input + voice/chat mode toggle
- SpeechSynthesis TTS in 11 languages
- WebRTC voice calls + screen sharing with admin
- Markdown cleanup (strips `**`, `***`, `#`, backticks from responses)

### Plan Comparison
- User-facing `/plans` page with tier cards
- Low-credits modal auto-triggers when credits < 5

### Other
- Custom alert rule engine, trading journal (auto-logged), watchlist with price alerts
- Strategy backtester (7 strategies), daily/weekly report summaries
- Push notifications (browser), notification center with analytics
- Heartbeat: 30s ping, 30min inactivity buffer, tab changes count as activity

## Critical Architecture Rules (MUST FOLLOW)
1. **NO `import server` in services/** — Use `services/app_state.py` for shared state (db, IST, LOT_SIZE_MAP, etc.)
2. **NO synchronous HTTP calls** — All `requests.get/post` wrapped in `asyncio.to_thread` or use `services/async_http.py`
3. **NO `React.lazy()`** for standard components — causes Webpack chunk hash breaks on hot reload
4. **NO default percentage fallbacks** in price bands — always read from equity_master_cache or return error
5. **Exclude `_id`** from all MongoDB responses
6. **All API routes prefixed with `/api`** (Kubernetes ingress routing)
7. **Frontend uses `REACT_APP_BACKEND_URL`** for all API calls

## Test Credentials
- **Owner**: `POST /api/auth/access` with `{"username": "@shish123"}`
- **User**: `POST /api/auth/access` with `{"username": "Manas@2005"}`

## Testing Status
- **91 test iterations** completed (iterations 85-91 all 100% pass)
- Latest: iteration 91 — 21/21 backend, 100% frontend
- All 9 nav tabs, 10 admin sub-tabs, 6 F&O sub-tabs verified

## Remaining Backlog
- P3: Multi-currency payment support
- P3: Advanced analytics dashboard with usage graphs
- P3: SessionStorage → httpOnly cookie migration (major auth rewrite)

## Latest Change (2026-04-12 — Phase 34: Deep Code Review & Bug Fixes)
- Fixed dead/unreachable code in server.py WebSocket handler (duplicate except block)
- Fixed `check_usage_limit` to use DB-backed packages instead of hardcoded PACKAGES dict
- Fixed `search_users` to return sanitized user views via `_map_user_view`
- Parallelized `get_data_stats` queries using `asyncio.gather` (10x faster)
- Fixed N+1 queries in payments.py `list_pending_payments` and `get_payment_history` (batch $in)
- Fixed N+1 queries in fraud.py `list_fraud_incidents` (batch $in)
- Added session cleanup background task (30-min intervals, 24h TTL) to prevent SESSION_STORE memory leak
- Added _help_rooms stale cleanup background task (10-min intervals)
- Added `_session_logs` memory cap (100 entries/user, 500 users max) to prevent unbounded growth
- Fixed duplicate index conflict on `fno_signal_log` collection
- Test: iteration 92 — 16/16 backend (100%), frontend verified

## Key MongoDB Collections
- `app_users` — User accounts with roles, credits, packages, permissions
- `equity_master_cache` — 60+ field equity data cache per symbol
- `fno_signal_log` — Generated signal history
- `custom_positions` — User position tracking
- `system_meta` — Config store (packages, feature_costs, razorpay_config)
- `payments`, `crm_messages`, `fraud_incidents`, `notifications`, `trading_journal`
- `iv_history`, `generation_perf_history`, `strategy_backtests`
- `domain_mappings`, `custom_apis`, `usage_tracking`

## File Reference Quick Index
| Purpose | File |
|---------|------|
| Main backend | `/app/backend/server.py` (1050 lines) |
| Shared state | `/app/backend/services/app_state.py` |
| Price bands | `/app/backend/services/price_band_engine.py` |
| Equity cache | `/app/backend/services/equity_master_cache.py` |
| All models | `/app/backend/models/__init__.py` (30+ Pydantic models) |
| Main frontend | `/app/frontend/src/App.js` |
| Auth hook | `/app/frontend/src/hooks/useAuth.js` |
| Sidebar nav | `/app/frontend/src/components/Layout/AppSidebar.jsx` |
| AI agent | `/app/frontend/src/components/Shared/LiveHelpModule.jsx` |
| Test creds | `/app/memory/test_credentials.md` |
