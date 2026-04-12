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

## Future/Backlog
- Wait for 30+ days iv_history accumulation for meaningful IV cone percentile bands
- Performance benchmarking during live market hours (timing data will populate during trading sessions)
- Further signal engine optimization based on profiling data
