# PRD — Trading Research Platform (Multibagger Engine)

## Original Problem Statement
Build a minimalist full-stack web app for stock analysis using FastAPI, React, and MongoDB. Core purpose: Generate high-quality, profitable F&O (Futures and Options) trading signals based on a detailed "Master Spec."

## Key Product Requirements (Master Spec)
1. **Global Architecture**: ALL calculations (backtests, indicators, targets, P&L, probabilities, Greeks, valuations, scoring, risk metrics) computed strictly in backend Python using live/historical data. NO HALLUCINATION. No frontend UI changes permitted. Minimum 78% Confluence Score for F&O signals.
2. **Market Universe**: Restricted to NIFTY 500, NIFTY 50, BANKNIFTY, BSE 500. Liquid stock price ≥ ₹50. Not under NCLT/DRT. Debt < 30% of market cap. Net profit positive in at least 1 of the last 3 quarters.
3. **Time/Expiry**: 09:15 to 15:30 IST strict session. Remaining trading days exclude weekends and NSE holidays.
4. **Shared Pipeline**: Master stock snapshot, Complete technicals, Forensic audit, Macro/Geopolitical context.
5. **F&O Signals**: Index-level weighted views, realistic data-driven T1/T2 based on intraday behavior, expiry-aware Best Exit based on VIX-theta decay.
6. **Multibagger & Portfolio**: Forensic/quality filters, realistic multi-horizon price bands, portfolio risk metrics (Beta, Sharpe, VaR, max drawdown).

## User Personas
- Primary: Admin/Owner (role: "owner") — manages users, triggers signals
- Secondary: Sub-users (role: "user") — consume signals, analyze portfolios

## Tech Stack
- **Frontend**: React (App.js now modular)
- **Backend**: FastAPI (server.py with modular services)
- **Database**: MongoDB
- **Live Data**: Kite Connect API v3 (primary), `yfinance` (fallback)
- **Auth**: JWT-based (username + PIN)

---

## Architecture (Current State — Post Refactoring)

```
/app
├── backend/
│   ├── models/
│   │   └── __init__.py         ← All 31 Pydantic models (428 lines)
│   ├── services/
│   │   ├── research_engine.py  ← Thin orchestrator (137 lines, re-exports all batches)
│   │   ├── indicators.py       ← Basic indicators: RSI, MACD, BB, ATR, etc. (516 lines)
│   │   ├── advanced_indicators.py ← Batch 1: Williams %R, Ichimoku, Fibonacci... (607 lines)
│   │   ├── technical_core.py   ← Full snapshot, confluence, portfolio verdict (555 lines)
│   │   ├── forensic_audit.py   ← Batch 2: Altman Z, Piotroski, Beneish (435 lines)
│   │   ├── macro_context.py    ← Batch 3: Regime, SECTOR_MACRO_IMPACT_MAP (339 lines)
│   │   ├── portfolio_risk.py   ← Batch 4: Correlation, Stress Tests, Diversification (483 lines)
│   │   ├── strategy_library.py ← Batch 5: 13 strategies, State Machine, Weights (601 lines)
│   │   ├── market_data.py
│   │   ├── data_verifier.py
│   │   └── holiday_manager.py  ← MongoDB NSE holiday storage + background auto-fetcher
│   ├── tests/
│   ├── .env
│   ├── requirements.txt
│   └── server.py               ← Main API routes (6654 lines, models extracted)
└── frontend/
    ├── src/
    │   ├── utils/
    │   │   ├── formatters.js   ← Format utilities (72 lines)
    │   │   └── exportUtils.js  ← F&O export (CSV/XLS/JPG) (136 lines)
    │   ├── components/
    │   │   ├── shared/
    │   │   │   └── LiveInfoBox.jsx ← Live option LTP display component
    │   │   └── ui/             ← shadcn components
    │   ├── App.js              ← Main component (2521 lines, down from 2770)
    │   ├── App.css
    │   └── index.js
```

---

## Key API Endpoints
- `POST /api/auth/access` — Login
- `GET /api/fno/generate` (POST) — Generate F&O signals
- `GET /api/multibagger` — Multibagger screener
- `POST /api/portfolio/analyze` — Portfolio analysis
- `GET /api/admin/nse-holidays` — NSE holiday list
- `POST /api/admin/nse-holidays/refresh` — Refresh holidays from NSE
- `GET /api/admin/strategy-stats` — 13-strategy backtest stats

## Key DB Schema
- **users**: `{username, role, credits, created_at}`
- **custom_positions**: `{user_id, script, buy_price, quantity_lots, status, signal_state}`
- **kite_option_master**: `{underlying, expiry, strike, option_type, tradingsymbol, instrument_token, lot_size}`
- **fundamental_cache**: `{symbol, ltp, pe_ratio, eps, total_debt_to_equity, recent_profit_positive, altman_z_score, earnings_quality, roic, fcf_yield}`
- **strategy_stats**: `{strategy_id, win_rate, expectancy, total_trades, disabled}`
- **nse_holidays**: `{date (YYYY-MM-DD), description, source, year}`

---

## What's Been Implemented (Changelog)

### 2025 Q1 — Initial Build
- JWT authentication (owner + sub-user roles)
- Kite Connect API v3 integration
- Basic F&O signal generation

### 2025 Q2-Q3 — Master Spec Implementation
- **Batch 1**: Advanced Technical Analysis (Ichimoku, Fibonacci, Candlestick Patterns, RSI Divergence, Multi-timeframe Trend)
- **Batch 2**: Forensic Financial Audit (Altman Z-Score, Beneish M-Score, Piotroski F-Score, ROIC vs WACC)
- **Batch 3**: Macro & Regime Context (8-regime classifier, SECTOR_MACRO_IMPACT_MAP with 15 events)
- **Batch 4**: Portfolio Risk Analytics (Correlation Matrix, 5 Stress Scenarios, Diversification Audit)
- **Batch 5**: Strategy Library (13 strategies, Signal State Machine, Constituent-weighted NIFTY/BANKNIFTY bias)
- NSE Holiday Management (MongoDB-backed, background auto-fetcher for FY 2026-2027)

### 2026 Feb — Codebase Refactoring
- **research_engine.py** (3682 lines) → 8 modular files (avg ~500 lines each)
- **server.py models** → extracted to `backend/models/__init__.py` (384 lines saved)
- **App.js utilities** → extracted to `src/utils/formatters.js`, `src/utils/exportUtils.js`, `src/components/shared/LiveInfoBox.jsx` (250 lines saved)
- All tests pass: 40/40 regression tests (Iteration 21)

---

## Prioritized Backlog (ROADMAP)

### P0 (Must Have — Next Sprint)
- **server.py Route Extraction**: Move 49 route handlers from server.py to `routes/` directory. Need to create `core/database.py` (db connection) and move helpers to `core/` modules.

### P1 (High Value)
- **Position Sizing Calculator**: Based on risk %, lot size, and ATR.
- **Multi-horizon Price Bands**: Compute realistic 1W/1M/3M/6M/9M/1Y price bands for Multibagger and Portfolio views.

### P2 (Future)
- **Sector Momentum Dashboard**: Track sector-wise momentum scores.
- **server.py helper extraction**: Move business logic helpers to `core/kite_helpers.py`, `core/fno_helpers.py`, etc.
- **Frontend page components**: Extract FNO page, Multibagger page, Portfolio page, Admin page to separate React component files.

---

## Known Constraints
- Strict: ALL analytical metrics MUST be calculated mathematically in Python. No LLM estimation.
- No UI changes: Frontend appearance must be preserved exactly.
- Kite Connect API key required for live data; yfinance is the fallback.
- NSE Holiday list auto-refreshes 1 week before April 1st each year.
