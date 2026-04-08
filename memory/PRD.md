# PRD — Trading Research Platform (F&O Signal Engine)

## Original Problem Statement
Full-stack web app for stock analysis (FastAPI, React, MongoDB) with:
- F&O Trading Signals with live Kite Connect data
- Multibagger Screener
- Portfolio Analysis
- Strict "Kite Supremacy" — ALL calculations backend Python, NO yfinance in production

## Core Architecture
- **Backend:** FastAPI (Python 3.11) — Modularized into routes/ and services/
- **Frontend:** React with Shadcn/UI
- **Database:** MongoDB (motor async driver)
- **Live Data:** Kite Connect API v3
- **Streaming:** NDJSON StreamingResponse for heavy compute endpoints

## Code Structure (Post-Extraction)
```
backend/
├── server.py                          # 3,918 lines (core utilities, data access, auth)
├── routes/
│   ├── fno.py                         # F&O signal generation endpoints
│   ├── admin.py                       # Admin/user management
│   ├── market_data.py                 # Sector momentum, script master
│   ├── portfolio.py                   # Portfolio analysis
│   └── multibagger.py                 # Multibagger screening
├── services/
│   ├── fno_signal_engine.py           # F&O signal building (2,293 lines)
│   ├── multibagger_engine.py          # Multibagger scoring (657 lines)
│   ├── portfolio_engine.py            # Portfolio analysis (448 lines)
│   ├── iv_history.py                  # 52-week IV history & rank
│   ├── sector_momentum.py            # Sector index token mapping
│   ├── data_policy.py                # Kite Supremacy constants
│   ├── confluence_score_v2.py         # Signal scoring buckets
│   └── ... (14 total service modules)
├── models/__init__.py                 # Pydantic response models
└── deps.py                            # Shared auth dependencies
```

## Key Endpoints
| Endpoint | Method | Type | Description |
|---|---|---|---|
| /api/fno/generate | POST | NDJSON Stream | Full F&O signal generation |
| /api/fno/signals/index | POST | NDJSON Stream | Index-specific signals |
| /api/multibagger/candidates | GET | NDJSON Stream | Multibagger scan |
| /api/multibagger/generate | POST | NDJSON Stream | Multibagger analysis |
| /api/sector-momentum | GET | JSON | 8 NSE sector indices |
| /api/portfolio/analyze | POST | JSON | Portfolio analysis |
| /api/auth/access | POST | JSON | Authentication |

## Completed Features
- [x] Route extraction: fno.py, admin.py, market_data.py, portfolio.py, multibagger.py
- [x] Business logic extraction: fno_signal_engine.py, multibagger_engine.py, portfolio_engine.py
- [x] NDJSON streaming for all heavy compute endpoints (prevents 504 timeouts)
- [x] Kite Supremacy data policy (yfinance banned, data_policy.py enforced)
- [x] Sector momentum Kite rewrite with 8 NSE index tokens
- [x] 52-week IV Rank enrichment (iv_history.py, MongoDB collection)
- [x] FNOSignalResponse model updated with iv_rank_52w and atm_iv fields
- [x] Frontend IV Rank badges in signal cards
- [x] Export ATM IV and IV Rank 52W columns in CSV/PDF/Word
- [x] Same-day expiry target bug fix
- [x] Pullback entry strategy ("Best Budget Entry")
- [x] Lot size corrections (NIFTY=65)
- [x] Golden Star export indicators

## Testing Status
- Iteration 43: 31/31 backend pass, all frontend flows verified (100%)
- Previous: iterations 37-42 all passing

## Backlog (Priority Order)
- **P2:** App.js componentization (~3,237 lines)
- **P2:** Budget Entry Trigger Alert UI
- **P2:** Position Sizing Calculator enhancements
