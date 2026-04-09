# PRD — Trading Research Platform (F&O Signal Engine)

## Original Problem Statement
Full-stack web app for stock analysis (FastAPI, React, MongoDB) with:
- F&O Trading Signals with live Kite Connect data
- Multibagger Screener, Portfolio Analysis
- Strict "Kite Supremacy" — ALL calculations backend Python, NO yfinance

## Core Architecture
- **Backend:** FastAPI (Python 3.11) — Modularized into routes/ and services/
- **Frontend:** React with Shadcn/UI + Recharts — Componentized (App.js = 259 lines)
- **Database:** MongoDB (motor async driver)
- **Live Data:** Kite Connect API v3
- **Streaming:** NDJSON StreamingResponse

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/auth/access | POST | Login |
| /api/auth/me | GET | Current user with settings |
| /api/auth/settings | PATCH | Update fno_budget, account_risk_pct |
| /api/fno/generate | POST | F&O signal generation (NDJSON stream) |
| /api/fno/position-sizing | POST | Enhanced: lots_atr_method, lots_fixed_risk, max_risk_Rs |
| /api/fno/events | GET | Popup events |
| /api/fno/sticky-cards | GET | Active sticky cards |
| /api/fno/performance-stats | GET | Aggregated performance stats |
| /api/fno/signal-history | GET | Paginated closed trades |
| /api/fno/signal-log | GET | Signal generation log |
| /api/fno/iv-cone/{symbol} | GET | IV Cone with percentile bands |
| /api/fno/iv-term-structure/{symbol} | GET | IV term structure |
| /api/fno/multi-timeframe/{symbol} | GET | Multi-TF analysis (Daily/Weekly/Monthly) |

## Completed Features
- [x] Master Spec v2.0 Batches 1-4
- [x] P2-A: App.js componentization (3265 to 259 lines)
- [x] P2-B: Budget Entry Trigger Alert UI
- [x] P2-C: Position Sizing Calculator (ATR14, fixed-risk)
- [x] Test infrastructure fix (BASE_URL + asyncio)
- [x] Historical Signal Performance Tracking
- [x] IV Analytics: IV Cone + IV Term Structure (data pipeline + charts)
- [x] Multi-Timeframe Analysis Views (Daily/Weekly/Monthly with alignment scoring)
- [x] Signal Log Auto-Capture
- [x] NDJSONStreamConsumer memory leak fix (AbortController)
- [x] Architecture Hardening Phase 1: utils.py, date_utils.py, position_parser.py, fundamental_scoring.py (server.py 4019->3578)
- [x] Architecture Hardening Phase 2: kite_client.py, fundamental_data.py, user_service.py, validators.py (server.py 3578->2218)
- [x] Architecture Hardening Phase 3: script_master.py, india_vix.py, hist_data.py, position_service.py, routes/auth.py (server.py 2220->981)
- [x] Full pytest suite fix: 1281 passed, 0 failed, 23 skipped (100% green)

## Testing Status
- Full suite: 1281 passed, 0 failed, 23 skipped (100% green as of 2026-04-09)
- 47 test files across /app/backend/tests/
- Test helpers in tests/helpers/test_utils.py (safe_streaming_post, read_backend_source, get_base_url)

## Architecture (Post Phase 3 Extraction)
```
/app/backend/
├── server.py                        # 981 lines (core app + startup + residual endpoints)
├── routes/
│   ├── auth.py                      # NEW Phase 3: login, logout, me, settings
│   ├── fno.py                       # F&O signal endpoints
│   ├── admin.py                     # Admin panel endpoints
│   ├── market_data.py               # Market data endpoints
│   ├── portfolio.py                 # Portfolio endpoints
│   ├── multibagger.py               # Multibagger endpoints
│   └── batch_jobs.py                # Batch/cron endpoints
├── services/
│   ├── script_master.py             # NEW Phase 3: NSE/Angel/Kite/Dhan symbol sync
│   ├── india_vix.py                 # NEW Phase 3: India VIX via Kite
│   ├── hist_data.py                 # NEW Phase 3: Historical OHLCV cache
│   ├── position_service.py          # NEW Phase 3: Position refresh/monitoring/response
│   ├── kite_client.py               # Phase 2: Kite API interactions
│   ├── fundamental_data.py          # Phase 2: Piotroski/Beneish scoring
│   ├── user_service.py              # Phase 2: User CRUD
│   ├── validators.py                # Phase 2: Input validation
│   ├── utils.py                     # Phase 1: Utility functions
│   ├── date_utils.py                # Phase 1: Trading day calculations
│   ├── fno_signal_engine.py         # F&O signal generation
│   ├── research_engine.py           # Regime classification, sentiment
│   ├── position_monitor.py          # Monitoring alerts
│   └── ... (other services)
└── tests/
    ├── helpers/test_utils.py        # Shared test utilities
    └── test_*.py                    # 47 test files
```

## Backlog
- P2: Advanced IV analytics (IV cone + term structure chart — wait for iv_history 30+ days)
- P2: Historical signal performance tracking enhancements
