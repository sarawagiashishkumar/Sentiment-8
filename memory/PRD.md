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
- `/api/admin/users` — User management

## Future/Backlog
- Advanced IV analytics: IV cone + IV term structure (needs 30+ days iv_history data)
- fno_signal_engine.py refactoring (~2800 lines → modular strategy files)
- Extract useAuth hook into App.js (hook created but not wired)
- AdminDashboard.jsx split into sub-components (438 lines)
- NDJSON streaming audit: investigate data truncation and synchronous blocks
- Processing latency elimination: F&O Signal + Multibagger generation instant delivery
