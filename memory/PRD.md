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
- [x] Signal Log Auto-Capture (logs every generated signal + IV term structure during F&O projection)
- [x] NDJSONStreamConsumer memory leak fix (AbortController + signal cleanup on unmount)
- [x] server.py modular extraction: date_utils.py (118 lines), utils.py (69 lines) — server.py 4019→3890 lines

## Testing Status
- Iterations 44-50: 97 tests, all green (0 failures, 0 errors)

## Code Architecture
```
backend/
├── server.py           (3890 lines — auth, startup, Kite client, domain mgmt)
├── services/
│   ├── utils.py         (NEW: clamp, sanitize_float, utc_now_iso, safe_ratio, etc.)
│   ├── date_utils.py    (NEW: today_ist, trading days, expiry risk, calendar days)
│   ├── iv_analytics.py  (IV cone, term structure)
│   ├── multiframe_analysis.py  (Multi-TF daily/weekly/monthly)
│   └── ... (25+ service modules)
└── routes/
    └── fno.py           (721 lines — all F&O endpoints)
```

## DB Collections
sticky_fno_cards, fno_popup_events, fno_signal_history, fno_signal_log,
mfe_library, theta_curves, fwd_mfe, iv_history, iv_term_structure,
regime_history, index_constituents

## Backlog
All planned features complete. No remaining P0/P1 items.
