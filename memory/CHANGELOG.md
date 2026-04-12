# CHANGELOG — Trading Signals & F&O Platform

## 2026-04-12 — Phase 32: Superadmin CRUD Expansion & Dynamic Plans
- User suspend/unsuspend toggle, credit top-up, bulk credit adjustment, CSV export
- Dynamic package CRUD (MongoDB-backed with hardcoded fallbacks)
- Global feature fee management (PATCH /admin/feature-costs)
- Test: iteration 86 — 25/25 backend, 100% frontend

## 2026-04-12 — Phase 31: Component & Route Splitting
- FNODashboard → FNOExportTable.jsx + useFNOGeneration.js hook (311 lines)
- OptionsHeatmap → 4 sub-components (407→156 lines, 62% reduction)
- routes/fno.py → fno_backtest.py, fno_iv.py, fno_cards.py (1227→692 lines, 44% reduction)
- Test: iteration 85 — 26/26 backend, 100% frontend

## 2026-04-12 — Phase 28-30: Code Quality Report Fixes
- Circular imports broken (app_state.py expanded, hist_data.py rewritten)
- Auth refactored (15→5 complexity), Alert system (34→<10), CRM split
- Empty catch blocks fixed, hook deps fixed, model nesting fixed

## 2026-04-12 — Phase 27: Voice-Enabled Multilingual AI Support Agent
- Text-to-speech via SpeechSynthesis, continuous voice mode, 11 languages

## 2026-04-12 — Phase 26: Mobile Responsiveness + Permissions CRUD
- White background fix, sub-tab scrolling, permissions panel rebuild

## 2026-04-12 — Phase 25: Chunk Loading Fix + AI Support Agent
- Removed React.lazy (chunk hash breaks), GPT-4o-mini AI support, voice input

## 2026-04-12 — Phase 22-24: Razorpay, WebRTC, Senior Audits
- Razorpay + offline QR payments, WebRTC live help, screen sharing
- 22 synchronous requests calls audited, signal gen parallelized
- Multiple bug fixes (null crash, cooldown types, script parser, stray chars)

## 2026-04-12 — Phase 19-21: Charts, Reports, Watchlist, Backtester, Alert Engine, CRM
- TradingView lightweight charts, aggregated reports, watchlist with price alerts
- Strategy backtester, custom alert rule engine, admin permissions & packages
- Geospatial fraud detection, CRM module, 4 new admin tabs

## 2026-04-12 — Phase 14-18: Polish, Notifications, Journal, IV Analytics
- Admin performance dashboard, error boundaries, loading skeletons
- Notification center, push notifications, trading journal
- IV background collector, notification analytics, engine profiling
- fno_signal_engine.py reduced 82% (2787→500 lines across 5 extractions)

## 2026-04-12 — Phase 10-13: System Fixes, Streaming, Modularization
- Nav cleanup, home dashboard, Kite white-labeling, heatmap gradients
- NDJSON keepalive fix, auto-refresh countdown, useAuth hook
- AdminDashboard split, fno_signal_engine modularized, confluence extracted
