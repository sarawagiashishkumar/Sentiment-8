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

## Code Structure
```
backend/
├── server.py                          # ~3,960 lines (core utilities, data access, auth)
├── routes/
│   ├── fno.py                         # F&O signal generation + sticky cards + events endpoints
│   ├── admin.py                       # Admin/user management
│   ├── market_data.py                 # Sector momentum, script master
│   ├── portfolio.py                   # Portfolio analysis
│   ├── multibagger.py                 # Multibagger screening
│   └── batch_jobs.py                  # Offline MFE/Theta/FwdMFE builders
├── services/
│   ├── fno_signal_engine.py           # F&O signal building (~2,700 lines)
│   ├── mfe_mae_engine.py             # MFE/MAE library + select_targets_v2 + DB persistence (~1,300 lines)
│   ├── confluence_score_v2.py         # 4-bucket scoring (A/B/C/D) with hard vetoes
│   ├── news_sentiment.py             # NEW: Parallel-verified news, NEWS_AGGREGATE, continuous monitor
│   ├── sticky_card_engine.py         # NEW: State machine, popup events, MongoDB CRUD
│   ├── constituent_engine.py          # Batch 1: Weighted breadth
│   ├── regime_engine.py              # Batch 1: 8-regime classifier
│   ├── iv_history.py                  # 52-week IV history & rank
│   ├── multibagger_engine.py          # Multibagger scoring
│   ├── portfolio_engine.py            # Portfolio analysis
│   ├── sector_momentum.py            # Sector index token mapping
│   ├── data_policy.py                # Kite Supremacy constants
│   └── ... (20+ total service modules)
├── models/__init__.py                 # Pydantic response models (with V2 scoring fields)
└── deps.py                            # Shared auth dependencies
```

## Key Endpoints
| Endpoint | Method | Type | Description |
|---|---|---|---|
| /api/fno/generate | POST | NDJSON Stream | Full F&O signal generation |
| /api/fno/signals/index | POST | NDJSON Stream | Index-specific signals |
| /api/fno/events | GET | JSON | Unacknowledged popup events |
| /api/fno/events/acknowledge | POST | JSON | Acknowledge single event |
| /api/fno/events/acknowledge-all | POST | JSON | Acknowledge all events |
| /api/fno/sticky-cards | GET | JSON | Active sticky cards |
| /api/fno/sticky-cards/{id}/cancel | POST | JSON | Cancel a sticky card |
| /api/fno/sticky-cards/refresh | POST | JSON | Trigger refresh cycle |
| /api/multibagger/candidates | GET | NDJSON Stream | Multibagger scan |
| /api/sector-momentum | GET | JSON | 8 NSE sector indices |
| /api/portfolio/analyze | POST | JSON | Portfolio analysis |
| /api/batch/status | GET | JSON | Batch cache counts |
| /api/batch/build-theta-curves | POST | JSON | Pre-compute theta curves |
| /api/batch/build-mfe-library | POST | JSON | Build MFE/MAE probability tables |
| /api/batch/build-forward-mfe | POST | JSON | Build forward MFE percentiles |

## MongoDB Collections
| Collection | Purpose | Key Index |
|---|---|---|
| sticky_fno_cards | Live signal cards with state machine | (signal_id) unique |
| fno_popup_events | Alert events with acknowledge flag | (signal_id, event_type, emitted_at) |
| mfe_library | Cached MFE/MAE probability tables | (symbol, strategy_id, dte_band, iv_regime) unique |
| theta_curves | Pre-computed empirical theta decay | (option_class, moneyness, iv_regime, dte) unique |
| fwd_mfe | Forward MFE-to-expiry percentiles | (symbol, dte_band, regime) unique |
| iv_history | 52-week ATM IV snapshots | (underlying, date) unique |
| regime_history | Market regime audit trail | (index_name, timestamp) |
| index_constituents | NIFTY/BANKNIFTY constituent weights | (index_name) |

## Master Spec v2.0 — ALL BATCHES COMPLETE
| Batch | Description | Status | Tests |
|---|---|---|---|
| Batch 1 | Data Layer: Constituent Engine, Regime Engine, Liquidity/PCR | DONE | 28/28 |
| Batch 2 | MFE/MAE Library, Theta Curves, Forward MFE persistence | DONE | 23/23 |
| Batch 3 | Target Engine + Confluence Score overhaul (6 items) | DONE | 20/20 |
| Batch 4 | News Sentiment + Sticky Card Monitoring + Popup Events | DONE | 27/27 |

## Completed Features (Comprehensive)
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
- [x] **Batch 1** — constituent_engine, regime_engine, LOG-ONLY breadth/PCR
- [x] **Batch 2** — MFE/MAE DB persistence, cache-first pipeline, batch job endpoints, 360 theta curves
- [x] **Batch 3** — USE_NEW_SCORING flag, real breadth in Bucket B, full MFE in Bucket D, select_targets_v2, should_suppress gating, 9 V2 response fields
- [x] **Batch 4** — Parallel-verified news (RSS cross-source), NEWS_AGGREGATE with recency weighting, continuous monitor (120s), sticky card state machine (9 states), 3 popup event types (NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT), de-duplication, event acknowledge API

## Testing Status
- Iteration 47: 27/27 backend pass (Batch 4 verification, 100%)
- Iteration 46: 20/20 backend pass (Batch 3 verification, 100%)
- Iteration 45: 23/23 backend pass (Batch 2 verification, 100%)
- Iteration 44: 28/28 backend pass (Batch 1 verification, 100%)

## Backlog (Priority Order)
- **P2-A:** App.js componentization (~3,237 lines) — pure structural refactor
- **P2-B:** Budget Entry Trigger Alert UI
- **P2-C:** Position Sizing Calculator enhancements
- **Future:** IV cone + IV term structure charts, historical signal performance tracking, multi-timeframe analysis
