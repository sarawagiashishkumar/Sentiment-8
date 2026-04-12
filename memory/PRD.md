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
- Click-to-expand drill-down: Click any sector tile → full list view table with 7 columns
- Works in SectorHeatmap (Sector + Industry tiles)
- Toggle behavior + cyan ring highlight + close button

### Phase 7: Critical Bug Fixes (2026-04-10)
- AdminDashboard ReferenceError FIXED: Added missing UserCog import
- Unicode rendering FIXED: Removed all star emoji references
- Ghost user investigation: Verified database is clean — only 2 legitimate users

### Phase 8: Code Quality Refactoring (2026-04-11)
- Circular Import Broken: Created services/app_state.py as centralized state module
- Hardcoded Test Secrets Removed: Created tests/conftest_helpers.py
- Auth Token Security: Moved from localStorage to sessionStorage
- Weak Cryptography Fixed: Replaced MD5 with SHA-256 in news_sentiment.py
- Silent Error Handling Fixed: All empty catch blocks now log to console
- Array Index Keys Fixed: Replaced key={i} with stable identifiers
- fno.py Complexity Reduced: Extracted helper functions

### Phase 9: Code Quality Refactoring Part 2 (2026-04-11)
- Remaining Circular Imports Broken: market_data.py migrated to app_state
- app_state.py Expanded: Added KITE_API_SECRET, KITE_REDIRECT_URL, caches
- Dynamic Import Security Fixed: script_master.py static imports
- batch_jobs.py Complexity Reduced: Extracted helpers
- KiteLiveWarning Stale Closure Fixed: disconnectedRef
- FNOIVAnalytics Re-render Fix: Extracted inline style constants
- useAuth Hook Created: hooks/useAuth.js

### Phase 10: Critical System Fixes & UI/UX Standardization (2026-04-12)
- **Nav Cleanup**: Removed "Sectors" standalone tab and route. Sector analysis only via Market HeatMap > Sector Heatmap
- **Home Dashboard**: Reduced to 4 cards (Multibagger, F&O, Portfolio, Market Heatmap). No Sector Momentum card.
- **Kite White-labeling**: ALL "Kite" mentions in public-facing UI replaced with "Market Data API". Admin panel updated.
- **Heatmap Gradient Colors**: All heatmaps use intensity-based gradients (green for positive, red for negative, fading toward zero)
- **Heatmap Sorting**: All heatmaps sort Highest to Lowest by default
- **Sector Drill-down Full List**: Table view with 7 columns (Symbol, LTP, %Change, Open, High, Low, Volume)
- **Static 18 Stocks Bug FIXED**: sector-stocks endpoint now dynamically maps to INDUSTRY_SECTOR_MAPPING. No NIFTY50 fallback.
- **F&O Universe Expanded**: LOT_SIZE_MAP expanded from 149 to 225 stocks (Nov 2024 NSE additions included)
- **Stock Heatmap Search**: Instant zero-click symbol search with real-time filtering
- **Dynamic Slider**: Change % range slider dynamically adapts to actual data range (no fixed ±10% cap)
- **Options Filter Standardization**: NIFTY/BANKNIFTY tabs > ALL/CE/PE filter > Expiry dropdown > Top 3 F&O stocks + Custom search with auto-suggest
- **Centered Error Popup**: DataFetchErrorPopup is now a centered overlay with market-closed context detection
- **5-sec Audio Alarm**: Verified — fires on API failures via playAlarmSound() in KiteLiveWarning
- **Portfolio Multi-file Upload**: Drag-and-drop zone with simultaneous multi-file support. Backend accepts 'files' parameter.
- **Anti-Sleep Heartbeat**: 10-min inactivity buffer with hard reset on every user interaction (click, scroll, keypress, filter toggle). Auto-fetch counts as active engagement.
- **Stock Heatmap OHLCV**: API now returns open, high, low, volume fields alongside ltp/change_pct

### Phase 11: NDJSON Streaming Latency Fix & Auto-Refresh (2026-04-12)
- **NDJSON Keepalive Buffering Bug FIXED**: `_run_phase_with_keepalive()` was collecting keepalive lines into a list and returning them AFTER the task completed. This caused keepalives to arrive late and could lead to proxy/ingress idle timeout killing the connection. Fixed by inlining the keepalive loop directly in the async generator — `yield` now sends keepalives to the wire immediately during computation.
- **Multibagger Keepalive Added**: Multibagger generate endpoint now has inline keepalive loop during `_build_multibagger_candidates()` to prevent proxy timeout on slow scans.
- **Auto-Refresh Countdown Indicator**: New `RefreshCountdown` component (SVG ring + seconds countdown + manual refresh button) added to all 3 heatmap tabs (Sector, Stocks, Options). Shows real-time countdown to next auto-refresh.
- **Session Reset Triggers Comprehensive**: Axios response interceptor resets inactivity clock on EVERY API response (covers auto-fetch). Visibility change + focus events also reset. Auto-fetch = active engagement — server stays awake.

### Phase 12: Modularization & IV Analytics Enhancement (2026-04-12)
- **useAuth Hook Wired**: Extracted all inline auth logic (login, logout, hydrate, token, syncCredits) from App.js into `hooks/useAuth.js`. App.js reduced from 312 to 240 lines.
- **AdminDashboard Split**: Broke 462-line monolith into orchestrator + 3 sub-components: `AdminUsersTab` (User Management table), `AdminApiTab` (Market Data API integration), `AdminCsvTab` (CSV Seed Management). Controls & Macro tabs kept inline due to tight state coupling.
- **fno_signal_engine.py Modularized**: Extracted `_build_report`, `_compute_enhanced_index_breadth`, `_build_index_projection`, `_build_stock_fno_signals` into new `services/fno_builders.py` (679 lines). Engine reduced from 2787 to 2152 lines.
- **IV Analytics Enhanced**: Added 5 quick symbol presets (NIFTY, BANKNIFTY, RELIANCE, TCS, HDFCBANK) and data collection status indicator showing progress toward 30-day minimum for reliable percentile bands.

### Phase 13: Confluence Extraction, Performance Profiling & IV Collection (2026-04-12)
- **fno_confluence.py Extracted**: 394 lines of pure scoring functions (`_compute_initial_option_targets`, `_compute_initial_option_sl`, `_calculate_confluence_score_master_spec`, `_get_signal_quality`) extracted from fno_signal_engine.py. Engine now 1785 lines (down from original 2787 — 36% reduction across 3 extractions).
- **Performance Profiling**: Added `time.monotonic()` instrumentation to all F&O generation phases (nifty_ms, banknifty_ms, stocks_ms, assembly_ms, total_ms) and multibagger (scan_ms, total_ms). New `/api/fno/generation-timings` endpoint returns last run timings. Tracking vars `LAST_FNO_PERF` and `LAST_MB_PERF` in `app_state.py`.
- **Manual IV Collection**: New `/api/fno/iv-collect-now` POST endpoint does one-shot ATM IV snapshot for NIFTY/BANKNIFTY + term structure across all available expiries — without requiring full signal generation. Frontend "Collect IV Now" button in IV Analytics tab triggers collection and displays results.

## Key API Endpoints
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/fno/bbe-alerts` — Real-time BBE zone monitoring
- `/api/fno/performance-stats` — Aggregated performance statistics
- `/api/fno/signal-log` — All generated signals log
- `/api/heartbeat` — Keep-alive ping (now returns 'active' field)
- `/api/kite/status` — Session health check
- `/api/sector-momentum` — 18 NSE index sectors
- `/api/market/sector-stocks?sector=X` — Sector drill-down (7 columns: Symbol, LTP, %Change, Open, High, Low, Volume)
- `/api/market/stock-heatmap` — Stock heatmap data (now includes OHLCV fields)
- `/api/market/options-heatmap` — Options heatmap data
- `/api/market/industry-sectors` — Industry sector aggregation
- `/api/portfolio/analyze-upload` — Multi-file portfolio upload
- `/api/fno/generation-timings` — Last generation phase timings
- `/api/fno/iv-collect-now` — One-shot IV snapshot collection (POST)
- `/api/fno/iv-cone/{symbol}` — IV Cone percentile bands
- `/api/fno/iv-term-structure/{symbol}` — IV term structure across expiries
- `/api/admin/users` — User management

### Phase 14: App Polish & Hardening (2026-04-12)
- **Admin Performance Dashboard**: New 6th tab in Admin panel showing F&O generation phase timings as horizontal bar chart (NIFTY/BANKNIFTY/Stocks/Assembly) + Multibagger timing. Historical runs persisted to MongoDB `generation_perf_history` collection. Shows last 20 runs with type, timestamp, total, phase breakdown, and signal count.
- **Error Boundary**: React class component wrapping all main content sections. Catches rendering crashes gracefully with "Something went wrong" fallback + "Try Again" button instead of white screen.
- **Loading Skeleton States**: `HeatmapSkeleton` component replaces plain "Loading..." text in StocksHeatmap and OptionsHeatmap with animated pulse skeleton grid.
- **Mobile Responsiveness**: Header uses 2-col grid on mobile, 4-col on desktop. Sidebar buttons show abbreviated labels on small screens (MB, F&O, Port, Heat). Home dashboard cards use responsive 2→4 column grid. Cost note abbreviated for mobile.

### Phase 15: Notification Center, Final Modularization & Perf Thresholds (2026-04-12)
- **Persistent Notification Center**: Bell icon in header with unread count badge. Click opens slide-out panel from right. Categorized notifications: Critical (BBE NOW BUY, EXIT_URGENT, API Disconnect), Warning (premium decay, approaching SL), Success (target watching, closed win), Info (general). Auto-clears read notifications after 24h. Connected to BBE alert monitor and KiteLiveWarning API failure detection.
- **fno_utils.py Extracted**: 179 lines (`_format_script`, `_compute_report_from_rows`, `_infer_stock_option_type`, `_analyze_micro_dip_prediction`). Engine now 1632 lines — 41% total reduction from original 2787 across 4 extractions (fno_builders 684, fno_confluence 395, fno_utils 179).
- **Performance Threshold Alerts**: PhaseBar component shows red "SLOW" warning with pulse animation when timing exceeds configurable thresholds (NIFTY >10s, BANKNIFTY >10s, Stocks >30s, Assembly >5s, Total >60s, Multibagger Scan >30s).

### Phase 16: Push Notifications, Persistence & Final Engine Modularization (2026-04-12)
- **Service Worker Push Notifications**: `sw-notifications.js` registered for background push delivery. `PushNotifToggle` in header (BellRing=ON, BellOff=OFF). State persisted in sessionStorage. Push fires for Critical (EXIT_URGENT, NOW BUY, API Disconnect) and Warning (APPROACHING_SL, LOSS_WARNING) alerts even when tab is minimized/background. Respects ON/OFF toggle preference.
- **Notification Persistence to MongoDB**: `user_notifications` collection with CRUD via `/api/notifications` (GET/POST/PATCH read-all/DELETE). Frontend loads history on login, saves new alerts to backend, syncs clear-all and mark-all-read operations.
- **Final Engine Modularization**: `build_fno_signal` (~1180 lines) extracted into `fno_signal_builder.py`. Engine now **500 lines** (82% reduction from original 2787). 5 extracted modules total: fno_signal_builder (1184), fno_builders (683), fno_confluence (395), fno_utils (189).

### Phase 17: Trading Journal, Benchmarking, IV Collector & Analytics (2026-04-12)
- **Automated Trading Journal**: `/api/journal` CRUD endpoints. Auto-logs every signal generation from F&O pipeline (symbol, direction, entry price, targets, SL, confluence score, signal quality). Frontend "Trading Journal" sub-tab in F&O dashboard with 6 summary cards (Total Entries, Closed Trades, P&L, Wins, Losses, Win Rate) + filterable table (event type + symbol search). P&L calculation on closed trades with win rate computation.
- **Live Benchmarking**: Admin Performance tab now fetches notification analytics in parallel via `Promise.all`. Auto-refreshable with manual refresh button.
- **IV Background Collector**: Scheduled `asyncio.create_task` runs every 30 minutes during market hours (9:15-15:30 IST). Captures ATM IV for NIFTY/BANKNIFTY without requiring signal generation. Accelerates 30-day IV history accumulation.
- **Notification Analytics**: `/api/notifications/analytics` endpoint returns alert frequency (7-day by category), total 24h alerts, average response latency (time from alert to read), and read count. Admin Performance tab shows analytics section with 4 metric cards.
- **Signal Engine Profiling**: `build_fno_signal` in `fno_signal_builder.py` instrumented with `time.monotonic()` for per-function timing. Phase timings logged at DEBUG level.

### Phase 18: Code Quality Report Fixes (2026-04-12)
- **Circular Import Broken**: `kite_client.py` migrated from `_srv().db`/`_srv().KITE_API_KEY` to `_state.db`/`_state.KITE_API_KEY` directly. Only 1 `_srv()` call remains for complex server functions (`_get_api_controls`, `_get_stock_core_cached`). Added `KITE_OPTION_MASTER_LAST_SYNC_DATE`, `KITE_SCRIPT_MASTER_URL`, `LOT_SIZE_MAP` to `app_state.py`.
- **Hook Dependencies Fixed**: `useAuth.js` uses `useRef` for token/loginUsername to avoid stale closures. `PushNotifications.jsx` has proper `useCallback` dependencies. All empty catch blocks now log errors.
- **FNO Complexity Reduced**: Extracted `_post_generation_effects()` helper from `_stream_generate()` — handles perf tracking, signal logging, journal, and IV capture. Reduced nesting and local variable count.
- **Test Quality**: `random` → `secrets` module in test files. `is` → `==` comparison anti-patterns fixed across all test files.
- **Frontend Quality**: Stable keys in `Skeletons.jsx` (prefixed `skel-grid-`, `skel-th-`, `skel-row-`). Nested ternaries refactored to helper functions. Environment-aware `logger.js` utility created (silences debug/warn in production).

### Phase 19: TradingView Charts, Reports, Watchlist & Backtester (2026-04-12)
- **TradingView Lightweight Charts (v5.1)**: `TVChartWrapper.jsx` with candlestick, line, area, histogram series. `IVConeChart` for IV percentile bands. `MiniChartPopup` — click any stock heatmap tile for intraday candlestick popup. Backend `/api/market/stock-chart/{symbol}` returns historical OHLCV candles from Kite.
- **Aggregated Reports Engine**: `/api/reports/daily-summary` + `/api/reports/weekly-summary` aggregate from `trading_journal` + `generation_perf_history`. Frontend "Reports" nav tab with daily/weekly toggle, date picker, 6 summary cards (Signals, Closed, P&L, Wins, Losses, Win Rate), best/worst trade, top symbols, quality distribution, CSV export.
- **Watchlist with Price Alerts**: `/api/watchlist` CRUD (GET/POST/DELETE). Set `alert_above`/`alert_below` thresholds per symbol. Background monitor runs every 60s during market hours — pushes to notification center when price crosses threshold. Frontend "Watchlist" nav tab with add form + items list.
- **Strategy Backtester**: `/api/fno/run-backtest` POST endpoint with momentum simulation. Frontend "Strategy Backtester" sub-tab in F&O with strategy selector (Momentum CE/PE, Straddle, Iron Condor), date range, equity curve via TradingView area chart, trade-by-trade log, summary cards (Win Rate, P&L, Max Drawdown, Sharpe, Profit Factor).
- **Navigation**: Expanded to 8 buttons (added Reports, Watchlist). F&O now has 5 sub-tabs (added Strategy Backtester).

### Phase 20: Senior Code Audit — Bug Fixes, Performance & Enhancements (2026-04-12)
- **Bug Fix: BBE Alerts Duplicate Key**: `fno.py` MongoDB query had duplicate `best_budget_entry` keys (second overwrites first). Fixed to single `{"$gt": 0}` condition. Prevented missed BBE alerts.
- **Bug Fix: Watchlist Alert Cooldown**: Added 1-hour cooldown (`ALERT_COOLDOWN_SECS=3600`) in watchlist monitor. Checks `last_triggered` timestamp before re-firing. Eliminates notification spam for persistent price breaches.
- **Bug Fix: Adaptive Position Polling**: Custom positions polling changed from fixed 5s to adaptive: 5s during market hours (9:15-15:30 IST), 60s off-hours. Reduces unnecessary server load 24/7 by ~92% off-hours.
- **Bug Fix: WebSocket Reconnect Stale Closure**: `useLivePrices.js` reconnection timer now uses `reconnectTimerRef` and reads from `symbolsRef.current` instead of captured stale `symbols`. Prevents reconnection with outdated symbol list.
- **Performance: GZip Compression**: Added `GZipMiddleware(minimum_size=1000)` — compresses JSON responses >1KB. Measured 74.5% payload reduction (6179→1576 bytes) on stock heatmap endpoint.
- **Performance: X-Response-Time Header**: New HTTP middleware adds `X-Response-Time: Xms` header to every response for monitoring/diagnostics.
- **Performance: Frontend Lazy Loading**: 7 heavy dashboard components (`MultibaggerDashboard`, `FNODashboard`, `PortfolioDashboard`, `AdminDashboard`, `MarketHeatmapDashboard`, `ReportsDashboard`, `WatchlistPanel`) wrapped with `React.lazy()` + `Suspense`. Reduces initial bundle load.
- **Performance: Reports MongoDB Aggregation**: `_aggregate_report` in `reports.py` now uses `$group` pipeline for symbol counts, quality distribution, and perf averages instead of fetching all docs and computing in Python.
- **Performance: Options Heatmap Sync Removal**: Removed redundant `_sync_kite_option_master_daily()` call on every options heatmap request (already runs at startup, saves ~200ms/request).
- **Enhancement: Health Check Endpoint**: New `GET /api/health` returns comprehensive status: DB connectivity, Kite session status, background task health (IV collector, watchlist monitor, news monitor), and data metrics (user count, signals logged).
- **Enhancement: Request Deduplication**: New `utils/apiDedup.js` with `dedupGet()` function prevents concurrent identical API calls during fast navigation.
- **Enhancement: Stale Data Timer**: `StaleDataTimer` component in `KiteLiveWarning.jsx` shows live-updating elapsed time since disconnect ("Data stale: 2m 15s ago").

## Key API Endpoints
- `/api/health` — Comprehensive health check (DB, Kite, background tasks, data metrics)
- `/api/fno/generate` — NDJSON streaming F&O signals
- `/api/fno/bbe-alerts` — Real-time BBE zone monitoring
- `/api/fno/performance-stats` — Aggregated performance statistics
- `/api/fno/signal-log` — All generated signals log
- `/api/heartbeat` — Keep-alive ping (now returns 'active' field)
- `/api/kite/status` — Session health check
- `/api/sector-momentum` — 18 NSE index sectors
- `/api/market/sector-stocks?sector=X` — Sector drill-down (7 columns)
- `/api/market/stock-heatmap` — Stock heatmap data (OHLCV fields)
- `/api/market/options-heatmap` — Options heatmap data
- `/api/market/industry-sectors` — Industry sector aggregation
- `/api/portfolio/analyze-upload` — Multi-file portfolio upload
- `/api/fno/generation-timings` — Last generation phase timings
- `/api/fno/iv-collect-now` — One-shot IV snapshot collection (POST)
- `/api/fno/iv-cone/{symbol}` — IV Cone percentile bands
- `/api/fno/iv-term-structure/{symbol}` — IV term structure
- `/api/fno/run-backtest` — Strategy backtester
- `/api/ws/prices` — WebSocket live price streaming
- `/api/watchlist` — Watchlist CRUD with price alerts
- `/api/notifications` — Notification CRUD
- `/api/journal` — Trading journal CRUD
- `/api/reports/daily-summary` — Daily P&L report
- `/api/reports/weekly-summary` — Weekly P&L report
- `/api/risk/portfolio-summary` — Risk dashboard metrics
- `/api/alerts/rules` — Custom Alert Rules CRUD (GET/POST/PATCH/DELETE)
- `/api/alerts/evaluate` — Evaluate alert rules against live market data
- `/api/admin/packages` — Available package tiers (free/basic/pro/unlimited)
- `/api/admin/users/{ref}/permissions` — User permission management
- `/api/admin/fraud-incidents` — Fraud incident management
- `/api/admin/crm/inbox` — Admin CRM inbox
- `/api/admin/crm/send` — Admin send/broadcast messages
- `/api/crm/inbox` — User CRM inbox
- `/api/crm/contact` — User support contact
- `/api/account/reactivation-request` — Fraud reactivation request

### Phase 21: Custom Alert Rule Engine, Admin Permissions, Fraud Detection & CRM (2026-04-12)
- **Custom Alert Rule Engine**: Composable rules with AND/OR logic across market conditions (symbol LTP, change %, volume, VIX). CRUD via `/api/alerts/rules`. Background evaluator runs every 30s during market hours with 5-minute cooldown per rule. Auto-pushes notifications on trigger. Frontend "Alert Rules" sub-tab in F&O Dashboard with visual rule builder, condition editor, toggle, and delete.
- **Admin Permissions & Tiered Packages**: 4 package tiers — Free (10 credits, limited), Basic (100 credits), Pro (500 credits), Unlimited. Each tier defines daily/total usage limits for every feature (fno_generate, multibagger, portfolio, backtest, alert rules, watchlist). Per-user feature cost overrides and feature restriction lists. Frontend "Permissions & Packages" tab in Admin with user selector and package assignment. Usage tracking via `usage_tracking` MongoDB collection.
- **Geospatial Fraud Detection**: Login IP geolocation via ip-api.com. Haversine distance calculation between current and last session. Impossible travel detection (max 900 km/h air, 300 km/h rail, 120 km/h road). Auto-suspends non-admin accounts on fraud detection with INR 2,500 reactivation fee. Login page shows "Fraud Login Attempt Detected" notice with detailed travel info, reactivation fee, and contact form. Admin "Fraud Detection" tab shows incident list with Reactivate/Confirm actions.
- **CRM Module**: Two-way messaging system. Admin can compose targeted messages to specific users or broadcast to all non-admin users. User inbox with read/dismiss/reply actions. Support contact form feeds into admin inbox. Message categories: admin_message, broadcast, fraud_alert, reactivation_request, user_reply, support_request. Notifications auto-pushed to user dashboard. Admin "CRM Messages" tab with inbox/sent tabs and compose form.
- **Navigation**: Admin Dashboard expanded from 6 to 10 tabs (added Permissions & Packages, Payments, CRM Messages, Fraud Detection). F&O Dashboard expanded from 5 to 6 sub-tabs (added Alert Rules).

### Phase 22: Razorpay, Offline QR Payments, WebRTC Live Help & Senior Audit (2026-04-12)
- **Razorpay Payment Gateway**: Admin configures key_id/key_secret/upi_id via Admin Dashboard (stored in MongoDB `system_meta`, NOT .env). Create order, verify signature, auto-reactivate on payment. Frontend 3-tab payment flow: Razorpay online / UPI QR code / Offline screenshot upload.
- **Offline QR Payment**: UPI QR code generated via `qrcode` Python library. Users scan and upload payment proof screenshot (base64 stored in MongoDB, max 5MB). Admin verifies via Payments panel with proof viewer and approve/reject buttons. Auto-creates CRM ticket on upload.
- **Admin Payments Panel**: Configure Razorpay credentials, view config status (Razorpay/UPI), pending verifications list with proof viewer, approve/reject with auto-reactivation.
- **Native WebRTC Live Help Module**: Zero third-party recurring costs. WebSocket signaling at `/api/ws/livehelp/{session_id}`. 5 free Google STUN servers (stun.l.google.com:19302). Text chat with message persistence + voice support via WebRTC media streams. Seamless text/voice toggle. Bug report button auto-generates CRM tickets.
- **Session Log Analysis**: Frontend axios interceptor logs all API calls (status, errors). Backend rule-based troubleshooting engine (6 patterns: kite_disconnect, credit_exhausted, generation_timeout, no_signals, data_stale, upload_failed). Auto-generates CRM bug tickets on 500/502/503 errors. LiveHelp fetches session analysis hints on connect.
- **User CRM Inbox (Parity Fix)**: Frontend component displaying admin messages with dismiss, reply, and contact support. Wired into App.js above main content area.
- **Senior Technical Audit Findings & Fixes**:
  - Mathematical Logic: Haversine formula verified (R=6371km, correct radians conversion), confluence scoring (0-100 with 8 sub-scores correctly capped), position sizing (dual-constraint min(allocation, risk)), MFE/MAE engine (13 strategy profiles, 4 DTE bands, 4 IV regimes).
  - Frontend-Backend Parity: 119 backend endpoints, ~72 unique frontend API consumers. Gap fixed: User CRM inbox (GET/PATCH/POST /crm/*) now has frontend consumer.
  - Latency Optimizations: Non-blocking geo-lookup (asyncio.run_in_executor), 7 new MongoDB compound indexes, timeout reduced from 5s to 3s on geo API.

## Key API Endpoints
- `/api/payments/create-order` — Razorpay order creation
- `/api/payments/verify` — Razorpay signature verification + auto-reactivation
- `/api/payments/qr-code` — UPI QR code generation (base64 PNG)
- `/api/payments/offline-upload` — Payment proof screenshot upload
- `/api/admin/payments/configure` — Admin sets Razorpay credentials
- `/api/admin/payments/config-status` — Check Razorpay/UPI config
- `/api/admin/payments/pending` — List pending offline payments
- `/api/admin/payments/{id}/proof` — Get payment proof image
- `/api/admin/payments/{id}/verify` — Approve/reject payment
- `/api/livehelp/ice-servers` — WebRTC STUN server config
- `/api/livehelp/log-action` — Log session action for analysis
- `/api/livehelp/session-analysis` — Get troubleshooting suggestions
- `/api/livehelp/chat-history` — Get chat messages
- `/api/livehelp/active-sessions` — Admin list active help sessions
- `/api/ws/livehelp/{session_id}` — WebRTC signaling + chat WebSocket
- `/api/crm/inbox` — User CRM inbox (admin messages)
- `/api/crm/dismiss/{id}` — Dismiss admin message
- `/api/crm/reply/{id}` — Reply to admin message
- `/api/crm/contact` — User support contact form

## WebRTC Capabilities Unlocked by Native Framework
Implemented:
1. **Screen sharing** — Users share their screen with admin for real-time debugging (getDisplayMedia)

Future capabilities (zero additional cost):
2. Multi-party admin conferencing (mesh or SFU topology)
3. Video support (toggle camera alongside voice)
4. File transfer via RTCDataChannel (share screenshots, logs)
5. Real-time market data streaming via DataChannel (bypass HTTP overhead)
6. Co-browsing — admin sees user's dashboard in real-time
7. Recording — capture audio/video sessions for compliance
8. Push-to-talk walkie-talkie mode for trading floor communication

### Phase 23: Screen Sharing + Senior Technical Audit — Zero-Lag Performance (2026-04-12)
- **Screen Sharing Enhancement**: Users can share their screen with admin via WebRTC `getDisplayMedia`. Admin sees live remote video. Toggle via Monitor/MonitorOff icons. Browser stop button auto-terminates share. WebSocket forwards `screen-share-start/end` signals.
- **Senior Technical Audit Findings & Fixes**:
  - **22 synchronous `requests` calls audited**: All confirmed wrapped in `asyncio.to_thread()` — no event loop blocking.
  - **Signal generation parallelized**: `asyncio.gather()` now fetches strategy stats + macro events in parallel (was sequential — saves ~200ms per signal).
  - **httpx AsyncClient**: New `services/async_http.py` with connection pooling (50 max, 20 keepalive) for future migration of `requests` calls to fully async.
  - **Bug Fix — contract.expiry type mismatch**: `fno_signal_builder.py` line 612 subtracted `datetime.date` from a `str` type expiry. Fixed to use pre-computed `_dte_for_mfe` integer.
  - **Bug Fix — trigger_factors typo**: "VeryC heapCE" → "VeryCheapCE" (space in middle of word).
  - **Mathematical Logic Verified**: Haversine (R=6371km), confluence scoring (8 sub-scores 0-100), position sizing (dual-constraint min(allocation, risk)), MFE/MAE (13 strategies, 4 DTE bands, 4 IV regimes), ATR targets, VIX theta decay.
  - **7 MongoDB compound indexes**: fno_signal_log, trading_journal (2), user_notifications, custom_positions, payments, livehelp_messages.
  - **httpx shutdown handler**: Clean client close on app shutdown.

## Future/Backlog
- All remaining items are data-dependent and auto-resolve with live market usage
- Payment history accumulates as users reactivate accounts
- Fraud incidents accumulate as multi-device logins trigger impossible travel checks
