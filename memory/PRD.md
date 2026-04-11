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

### Phase 8: Code Quality Refactoring (2026-04-11)
- **Circular Import Broken**: Created `services/app_state.py` as centralized state module (db, IST, KITE_API_KEY, kite_access_token). Services import from app_state instead of lazy `import server`. server.py populates app_state on startup.
- **Hardcoded Test Secrets Removed**: Created `tests/conftest_helpers.py` with `os.environ.get()` for credentials. Updated 5 test files to use shared config.
- **Auth Token Security**: Moved from `localStorage` to `sessionStorage` — token clears on tab close, reducing XSS exposure.
- **Weak Cryptography Fixed**: Replaced MD5 with SHA-256 in `news_sentiment.py` headline hashing.
- **Silent Error Handling Fixed**: All empty catch blocks in NDJSONStreamConsumer, KiteLiveWarning, FNOSignalHistory, StocksHeatmap now log to console.
- **Array Index Keys Fixed**: Replaced `key={i}` with stable identifiers in MultibaggerCandidateCard, FNOSignalHistory, FNOIVAnalytics.
- **fno.py Complexity Reduced**: Extracted `_run_phase_with_keepalive()`, `_build_index_phase()`, `_build_stock_phase()`, `_build_no_signals_alert()` helper functions. Reduced nesting depth from 5 to 3.

### Phase 9: Code Quality Refactoring Part 2 (2026-04-11)
- **Remaining Circular Imports Broken**: `market_data.py` migrated 5 lazy `import server` calls to `import services.app_state as _state` for db, KITE_API_KEY, KITE_API_SECRET, KITE_REDIRECT_URL, SECTOR_MOMENTUM_CACHE, IST
- **app_state.py Expanded**: Added KITE_API_SECRET, KITE_REDIRECT_URL, SECTOR_MOMENTUM_CACHE, SECTOR_MOMENTUM_CACHE_TTL_SECONDS, SCRIPT_MASTER_LAST_SYNC_DATE
- **Dynamic Import Security Fixed**: `script_master.py` `__import__("datetime")` → static `from datetime import datetime`
- **batch_jobs.py Complexity Reduced**: Extracted `_build_mfe_for_symbol()` and `_build_fwd_mfe_for_symbol()` helpers, reducing nesting from 6 → 3
- **KiteLiveWarning Stale Closure Fixed**: `disconnected` state in `useCallback` dependency → `disconnectedRef` (useRef), eliminating infinite re-registration
- **FNOIVAnalytics Re-render Fix**: Extracted 10 inline chart style objects (CHART_TICK, TOOLTIP_STYLE, etc.) to module-level constants
- **useAuth Hook Created**: `hooks/useAuth.js` — reusable auth logic (for future App.js refactoring)

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
