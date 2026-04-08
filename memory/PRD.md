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
├── server.py                          # ~3,920 lines (core utilities, data access, auth)
├── routes/
│   ├── fno.py                         # F&O signal generation endpoints
│   ├── admin.py                       # Admin/user management
│   ├── market_data.py                 # Sector momentum, script master
│   ├── portfolio.py                   # Portfolio analysis
│   ├── multibagger.py                 # Multibagger screening
│   └── batch_jobs.py                  # NEW: Offline MFE/Theta/FwdMFE builders
├── services/
│   ├── fno_signal_engine.py           # F&O signal building (~2,550 lines)
│   ├── mfe_mae_engine.py             # MFE/MAE library + DB persistence (~1,080 lines)
│   ├── constituent_engine.py          # Batch 1: Weighted breadth
│   ├── regime_engine.py              # Batch 1: 8-regime classifier
│   ├── confluence_score_v2.py         # 4-bucket scoring
│   ├── iv_history.py                  # 52-week IV history & rank
│   ├── multibagger_engine.py          # Multibagger scoring (657 lines)
│   ├── portfolio_engine.py            # Portfolio analysis (448 lines)
│   ├── sector_momentum.py            # Sector index token mapping
│   ├── data_policy.py                # Kite Supremacy constants
│   └── ... (18+ total service modules)
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
| /api/batch/status | GET | JSON | Batch cache counts |
| /api/batch/build-theta-curves | POST | JSON | Pre-compute theta curves |
| /api/batch/build-mfe-library | POST | JSON | Build MFE/MAE probability tables |
| /api/batch/build-forward-mfe | POST | JSON | Build forward MFE percentiles |

## MongoDB Collections
| Collection | Purpose | Key Index |
|---|---|---|
| mfe_library | Cached MFE/MAE probability tables | (symbol, strategy_id, dte_band, iv_regime) unique |
| theta_curves | Pre-computed empirical theta decay | (option_class, moneyness, iv_regime, dte) unique |
| fwd_mfe | Forward MFE-to-expiry percentiles | (symbol, dte_band, regime) unique |
| iv_history | 52-week ATM IV snapshots | (underlying, date) unique |
| regime_history | Market regime audit trail | (index_name, timestamp) |
| index_constituents | NIFTY/BANKNIFTY constituent weights | (index_name) |

## Completed Features
- [x] Route extraction: fno.py, admin.py, market_data.py, portfolio.py, multibagger.py, batch_jobs.py
- [x] Business logic extraction: fno_signal_engine.py, multibagger_engine.py, portfolio_engine.py
- [x] NDJSON streaming for all heavy compute endpoints
- [x] Kite Supremacy data policy (yfinance banned)
- [x] Sector momentum Kite rewrite with 8 NSE index tokens
- [x] 52-week IV Rank enrichment (iv_history.py)
- [x] Same-day expiry target bug fix
- [x] Pullback entry strategy ("Best Budget Entry")
- [x] Lot size corrections (NIFTY=65)
- [x] Golden Star export indicators
- [x] **Master Spec v2.0 BATCH 1** — Data & Feature Layer (constituent_engine, regime_engine, LOG-ONLY)
- [x] **Master Spec v2.0 BATCH 2** — MFE/MAE Library + Theta Curves + Forward MFE DB persistence, cache-first pipeline, batch job endpoints

## Master Spec v2.0 Implementation Progress
| Batch | Description | Status |
|---|---|---|
| Batch 1 | Data Layer: Constituent Engine, Regime Engine, Liquidity/PCR | DONE (28/28 tests) |
| Batch 2 | MFE/MAE Library, Theta Curves, Forward MFE persistence | DONE (23/23 tests) |
| Batch 3 | Target Engine + Confluence Score overhaul | NOT STARTED |
| Batch 4 | News Sentiment + Sticky Card Monitoring | NOT STARTED |

## Testing Status
- Iteration 45: 23/23 backend pass (Batch 2 verification, 100%)
- Iteration 44: 28/28 backend pass (Batch 1 verification, 100%)
- Previous: iterations 37-43 all passing

## Backlog (Priority Order)
- **P0:** Master Spec v2.0 Batch 3 (Target Engine + Confluence Score)
- **P0:** Master Spec v2.0 Batch 4 (News Sentiment + Monitoring)
- **P2:** App.js componentization (~3,237 lines)
- **P2:** Budget Entry Trigger Alert UI
- **P2:** Position Sizing Calculator enhancements
