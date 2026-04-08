# PRD — Trading Research Platform (F&O Signal Engine)

## Original Problem Statement
Full-stack web app for stock analysis (FastAPI, React, MongoDB) with:
- F&O Trading Signals with live Kite Connect data
- Multibagger Screener
- Portfolio Analysis
- Strict "Kite Supremacy" — ALL calculations backend Python, NO yfinance in production

## Core Architecture
- **Backend:** FastAPI (Python 3.11) — Modularized into routes/ and services/
- **Frontend:** React with Shadcn/UI — Componentized (App.js = 259 lines)
- **Database:** MongoDB (motor async driver)
- **Live Data:** Kite Connect API v3
- **Streaming:** NDJSON StreamingResponse for heavy compute endpoints

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/auth/access | POST | Login, returns fno_budget + account_risk_pct |
| /api/auth/me | GET | Current user with settings |
| /api/auth/settings | PATCH | Update fno_budget, account_risk_pct |
| /api/fno/generate | POST | Full F&O signal generation (NDJSON stream) |
| /api/fno/position-sizing | POST | Enhanced: lots_atr_method, lots_fixed_risk, max_risk_Rs |
| /api/fno/events | GET | Unacknowledged popup events |
| /api/fno/sticky-cards | GET | Active sticky cards |
| /api/fno/performance-stats | GET | Aggregated performance stats (win rate, avg P&L, by-symbol) |
| /api/fno/signal-history | GET | Paginated closed trades with outcomes |
| /api/fno/signal-log | GET | Paginated signal generation log |
| /api/batch/status | GET | Batch cache counts |

## Completed Features
- [x] Master Spec v2.0 Batches 1-4 (Data Layer, MFE/MAE, Target Engine, News Sentiment)
- [x] P2-A: App.js componentization (3265 to 259 lines)
- [x] P2-B: Budget Entry Trigger Alert UI (not_affordable wiring, fno_budget settings)
- [x] P2-C: Position Sizing Calculator (ATR14, fixed-risk methods)
- [x] Test infrastructure fix: BASE_URL resolution + asyncio.run() for Py3.11
- [x] Historical Signal Performance Tracking (close_card archival, P&L calculation, 3-tab UI)

## Testing Status
- Iteration 49: 6/6 pass (Signal History, 100%)
- Iterations 44-48: 83/83 pass (All previous features, 100%)
- Total: 89/89 all green

## DB Collections
- `sticky_fno_cards`, `fno_popup_events`
- `fno_signal_history` (archived terminal cards with outcome + pnl_pct)
- `fno_signal_log` (all generated signals)
- `mfe_library`, `theta_curves`, `fwd_mfe`
- `iv_history`, `regime_history`, `index_constituents`

## Backlog (Priority Order)
- **Future:** IV cone + IV term structure charts (wait for 30+ days iv_history data)
- **Future:** Multi-timeframe analysis views
