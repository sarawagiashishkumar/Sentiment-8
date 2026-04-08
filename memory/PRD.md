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

## Testing Status
- Iteration 50: 8/8 pass (IV + Multi-TF, 100%)
- Iteration 49: 6/6 pass (Signal History, 100%)
- Iterations 44-48: 83/83 pass
- Total: 97 tests, all green

## DB Collections
sticky_fno_cards, fno_popup_events, fno_signal_history, fno_signal_log,
mfe_library, theta_curves, fwd_mfe, iv_history, iv_term_structure,
regime_history, index_constituents

## Backlog
All planned features complete. No remaining P0/P1 items.
