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

### 2026 Apr — Master Spec Batches A, B, C Implementation (Iteration 25)
- **Batch A — Active Macro Events Management**: Replaced `active_events=[]` hardcoded empty in `build_fno_signal` and `compute_multibagger_analysis`. Added `_get_active_macro_events()` helper reading from MongoDB `macro_config` collection. Added admin endpoints `GET /api/admin/macro-events` (returns all 15 events + active flags) and `POST /api/admin/macro-events/update` (validates keys against SECTOR_MACRO_IMPACT_MAP, persists to DB). All 3 `build_fno_signal` callers updated to pass `fundamental` parameter (fixing pre-existing NameError). `compute_multibagger_analysis` now accepts `active_macro_events` param.
- **Batch B — Forensic Scores in Confluence Scoring**: `_calculate_confluence_score_master_spec` now accepts `piotroski_score`, `beneish_m_score`, `altman_z_zone` params. `fundamental_score` component now uses real forensic data (Piotroski ≥7→10pts, ≥5→7pts, ≥3→4pts, <3→2pts; Beneish manipulation -3; Altman DISTRESS -4, SAFE +2; cap 10). Falls back to 52W proxy when no forensic data. Also fixed pre-existing bug: Batch 1 tech vars (`ts`, `_cci`, `_ichimoku`, etc.) were undefined in function scope — fixed by adding `tech_snapshot: dict | None = None` param.
- **Batch C — Strategy Threshold Enforcement**: `_get_strategy_stats_for_selection()` now reads from `strategy_backtest` collection (same as admin endpoint) and aggregates win_rate/expectancy. Passed to `select_strategy_for_signal()` so strategies with <75% win rate / <0.40R expectancy are excluded from signal selection.
- All 37 tests pass (iteration 25).


- **Portfolio price bands**: Fixed broken update path — `expected_ranges` was always using static fallback due to wrong dict keys (`band.get("high")` → non-existent). Restructured `_analyze_portfolio_positions` to fetch hist_vol + Piotroski + RSI + trend FIRST, then compute `_portfolio_horizon_ranges()` in a single correct call.
- **Quality-adjusted drift**: `compute_realistic_price_bands()` now computes drift per-stock based on Piotroski F-Score (+3%/-4%), RSI (overbought/oversold ±2.5%), trend alignment (±2.5-4%), and Beneish M-Score (-5% penalty). Was fixed 7% for all stocks.
- **Multibagger custom-search**: Now fetches 1Y hist OHLCV to inject actual `hist_vol`, `rsi`, and `trend_alignment` into vol_bands (RELIANCE: 20.3% actual vol, 11% drift — was 30% fallback, 7% fixed).
- **F&O T1/T2 formula**: Fixed fundamental math error — was computing `ATR% × entry_price × delta` (wrong scale). Now correctly computes `ATR_points × delta → absolute option gain`. NIFTY ATM: T1=+61% / T2=+122% (was stuck at +4%/+10% floor). Removed hard % caps (1.15x, 1.65x).
- **F&O Best Exit**: Replaced fixed multipliers (1.4x/1.25x/1.15x) with `ATR × sqrt(days) × 2σ × delta` — dynamic projection per expiry and moneyness.
- **Portfolio risk hist_vol**: Was hardcoded 0.30 for all holdings. Now uses actual per-stock computed hist_vol.
- All 36 backend tests pass (Iteration 24).
- **Portfolio Analysis Fix**: Fixed `NameError: _get_fundamental_cached` → corrected to `_get_fundamental_data` in `_analyze_portfolio_positions`. Manual portfolio entry (DMART, KAYNES, etc.) now returns HTTP 200 with full analysis.
- **Custom F&O Alert Sound Upgrade**: Replaced single 0.5s beep with a rich 3-tier multi-tone engine: urgent exits → 3 rapid high-pitch square bursts; T1/T2 target hits → 3 ascending sine tones; warnings → 2 moderate triangle pulses. Now tracks ALL alert types (urgent, T1/T2 signal_state transitions, warnings) via separate refs.
- All 16 backend tests pass (Iteration 23).
- **Sector Momentum Dashboard**: New backend service `services/sector_momentum.py` — computes 1W/1M/3M returns, RSI(14), ADX(14), momentum score (0-100), direction for 15 NSE sectors using yfinance. 30-min dual-layer cache (in-memory + MongoDB). New API: `GET /api/sector-momentum`. New "Sectors" nav tab + sector grid UI.
- **Multi-horizon Price Bands**: Added `vol_bands` field to `MultibaggerCandidate` response model. Full Conservative/Expected/Optimistic price band table (6 horizons) now shown as expandable row in Multibagger page and Custom Stock Search panel. Based on historical volatility (σ-scaled).
- All 36 tests pass (Iteration 22).

---

## Prioritized Backlog (ROADMAP)

### P0 (Must Have — Next Sprint)
- **server.py Route Extraction**: Move 49+ route handlers from server.py to `routes/` directory. Need to create `core/database.py` (db connection) and move helpers to `core/` modules. File is ~6,960 lines.

### P1 (High Value)
- **Position Sizing Calculator**: Based on risk %, lot size, and ATR.

### P1 (High Value)
- **Position Sizing Calculator**: Based on risk %, lot size, and ATR.
- **Multi-horizon Price Bands**: ✅ DONE (Feb 2026)

### P2 (Future)
- **Sector Momentum Dashboard**: ✅ DONE (Feb 2026)
- **server.py helper extraction**: Move business logic helpers to `core/kite_helpers.py`, `core/fno_helpers.py`, etc.
- **Frontend page components**: Extract FNO page, Multibagger page, Portfolio page, Admin page to separate React component files.

---

## Known Constraints
- Strict: ALL analytical metrics MUST be calculated mathematically in Python. No LLM estimation.
- No UI changes: Frontend appearance must be preserved exactly.
- Kite Connect API key required for live data; yfinance is the fallback.
- NSE Holiday list auto-refreshes 1 week before April 1st each year.
