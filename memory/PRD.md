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

## Code Structure
```
backend/
├── server.py                          # Core utilities, data access, auth, settings endpoints
├── routes/
│   ├── fno.py                         # F&O signal generation + sticky cards + events + position sizing
│   ├── admin.py                       # Admin/user management
│   ├── market_data.py                 # Sector momentum, script master
│   ├── portfolio.py                   # Portfolio analysis
│   ├── multibagger.py                 # Multibagger screening
│   └── batch_jobs.py                  # Offline MFE/Theta/FwdMFE builders
├── services/
│   ├── fno_signal_engine.py           # F&O signal building with contextvars for user budget
│   ├── position_sizing.py            # Enhanced: ATR14, fixed-risk, lots_atr_method, lots_fixed_risk, max_risk_Rs
│   ├── mfe_mae_engine.py             # MFE/MAE library + select_targets_v2 + DB persistence
│   ├── confluence_score_v2.py         # 4-bucket scoring (A/B/C/D) with hard vetoes
│   ├── news_sentiment.py             # Parallel-verified news, NEWS_AGGREGATE, continuous monitor
│   ├── sticky_card_engine.py         # State machine, popup events, MongoDB CRUD
│   └── ... (20+ total service modules)
├── models/__init__.py                 # Pydantic models (UserSettingsUpdate, enhanced MeResponse/AccessResponse)
└── deps.py                            # Shared auth dependencies

frontend/
└── src/
    ├── App.js                         # 259 lines — routing shell
    └── components/
        ├── FNO/                       # FNODashboard (settings panel), FNOSignalCard (not_affordable + sizing info)
        ├── Multibagger/
        ├── Portfolio/
        ├── Shared/
        ├── Layout/
        ├── Auth/
        ├── Admin/
        ├── Home/
        └── Sectors/
```

## Key Endpoints
| Endpoint | Method | Type | Description |
|---|---|---|---|
| /api/auth/access | POST | JSON | Login, returns fno_budget + account_risk_pct |
| /api/auth/me | GET | JSON | Current user with settings |
| /api/auth/settings | PATCH | JSON | Update fno_budget, account_risk_pct |
| /api/fno/generate | POST | NDJSON Stream | Full F&O signal generation |
| /api/fno/position-sizing | POST | JSON | Enhanced: lots_atr_method, lots_fixed_risk, max_risk_Rs |
| /api/fno/events | GET | JSON | Unacknowledged popup events |
| /api/fno/sticky-cards | GET | JSON | Active sticky cards |
| /api/batch/status | GET | JSON | Batch cache counts |

## Master Spec v2.0 — ALL BATCHES COMPLETE
| Batch | Description | Status | Tests |
|---|---|---|---|
| Batch 1 | Data Layer: Constituent Engine, Regime Engine, Liquidity/PCR | DONE | 28/28 |
| Batch 2 | MFE/MAE Library, Theta Curves, Forward MFE persistence | DONE | 23/23 |
| Batch 3 | Target Engine + Confluence Score overhaul (6 items) | DONE | 20/20 |
| Batch 4 | News Sentiment + Sticky Card Monitoring + Popup Events | DONE | 27/27 |

## P2 Implementation — COMPLETE
| Task | Description | Status | Tests |
|---|---|---|---|
| P2-A | App.js Componentization (3265→259 lines) | DONE | Visual + Compilation verified |
| P2-B | Budget Entry Trigger Alert UI (not_affordable wiring, fno_budget settings) | DONE | 8/8 + 11/11 |
| P2-C | Position Sizing Calculator (ATR14, fixed-risk, lots_atr_method, lots_fixed_risk, max_risk_Rs) | DONE | 8/8 + 11/11 |

## Completed Features (Comprehensive)
- [x] All Master Spec v2.0 Batches (1-4)
- [x] P2-A: App.js componentization — pure structural refactor, 259 lines
- [x] P2-B: not_affordable inline warning in FNOSignalCard, fno_budget user setting, PATCH /auth/settings
- [x] P2-C: ATR14-based sizing (lots_atr_method), fixed-risk sizing (lots_fixed_risk), max_risk_Rs, account_risk_pct
- [x] Settings panel in F&O dashboard (Account Size + Risk Per Trade %)
- [x] Position sizing info badges in signal cards (Lots, ATR, Risk, Max₹)

## Testing Status
- Iteration 48: 8/8 unit + 11/11 integration pass (P2-B/C verification, 100%)
- Iteration 47: 27/27 backend pass (Batch 4 verification, 100%)
- Iteration 46: 20/20 backend pass (Batch 3 verification, 100%)
- Iteration 45: 23/23 backend pass (Batch 2 verification, 100%)
- Iteration 44: 28/28 backend pass (Batch 1 verification, 100%)

## Backlog (Priority Order)
- **Future:** IV cone + IV term structure charts (wait for 30+ days iv_history data)
- **Future:** Historical signal performance tracking
- **Future:** Multi-timeframe analysis views
