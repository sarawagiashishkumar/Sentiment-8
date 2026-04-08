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
- [x] Architecture Hardening Phase 1: utils.py, date_utils.py, position_parser.py, fundamental_scoring.py (server.py 4019→3578)
- [x] Architecture Hardening Phase 2: kite_client.py, fundamental_data.py, user_service.py, validators.py (server.py 3578→2218)

## Testing Status
- Iterations 44-51: All green. 58 combined recent tests passing.
- Test file: test_iteration51_arch_extraction.py (25 tests for extraction validation)

## Code Architecture
```
backend/
├── server.py              (2218 lines — auth routes, startup, caching, domain mgmt)
├── services/
│   ├── kite_client.py      (NEW: All Kite Connect API interactions)
│   ├── fundamental_data.py (NEW: Piotroski, Beneish, yfinance fundamentals)
│   ├── user_service.py     (NEW: User CRUD, role helpers)
│   ├── validators.py       (NEW: Input validation pure functions)
│   ├── utils.py            (clamp, sanitize_float, utc_now_iso, safe_ratio, etc.)
│   ├── date_utils.py       (today_ist, trading days, expiry risk, calendar days)
│   ├── position_parser.py  (Position parsing helpers)
│   ├── fundamental_scoring.py  (Fund scoring helpers)
│   ├── iv_analytics.py     (IV cone, term structure)
│   ├── multiframe_analysis.py  (Multi-TF daily/weekly/monthly)
│   ├── fno_signal_engine.py (Core F&O signal logic)
│   ├── sticky_card_engine.py (State machine for live signals)
│   ├── news_sentiment.py   (RSS + VADER news scoring)
│   ├── confluence_score_v2.py (4-bucket scoring)
│   ├── mfe_mae_engine.py   (MFE/MAE/Theta persistence)
│   └── ... (25+ service modules)
└── routes/
    ├── fno.py              (721 lines — all F&O endpoints)
    ├── batch_jobs.py       (MFE library batch jobs)
    └── ...
```

## DB Collections
sticky_fno_cards, fno_popup_events, fno_signal_history, fno_signal_log,
mfe_library, theta_curves, fwd_mfe, iv_history, iv_term_structure,
regime_history, index_constituents, fundamental_cache

## Backlog (P2)
- Continue server.py modularization: Extract script_master, india_vix, hist_ohlcv, auth routes (target: <1500 lines)
- Advanced IV analytics: IV cone + IV term structure chart (wait for 30+ days of iv_history data)
- Historical signal performance tracking enhancements
- Multi-timeframe analysis views enhancements

## Kite Connect Postback URL
https://signal-backtester.preview.emergentagent.com/api/kite/postback
