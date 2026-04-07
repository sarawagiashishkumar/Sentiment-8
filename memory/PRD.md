# PRD — Trading Research Platform

## Original Problem Statement
Build a minimalist full-stack web app for stock analysis using FastAPI, React, and MongoDB. Core feature: generate high-quality, profitable F&O (Futures and Options) trading signals based on the "Master Spec." All calculations (backtests, indicators, targets, P&L, probabilities, Greeks, valuations, scoring, risk metrics) MUST be computed strictly in backend Python using live/historical data. NO hallucination, no frontend calculations, no LLM estimations.

## Core Requirements (User-Stated)
1. **All analytics in Python backend** — never in LLM or frontend
2. **Market universe**: NIFTY 500, NIFTY 50, BANKNIFTY, BSE 500 only
3. **Data policy**: Kite Connect API is the ONLY preferred/verified live source. yfinance is fallback only when Kite unavailable.
4. **F&O signals**: Include PCR, IV Rank, Max Pain, GEX, OI buildup classification
5. **Forensic filters**: Piotroski, Beneish, Altman scores for multibagger/portfolio
6. **NSE Holidays**: MongoDB-backed auto-fetch with background updater
7. **No frontend UI changes** unless explicitly requested

## Architecture
```
/app
├── backend/
│   ├── services/
│   │   ├── market_data.py          # Kite Connect integration
│   │   ├── research_engine.py      # Core analytics engine
│   │   ├── data_verifier.py        # ATR, theta, VIX computations
│   │   ├── indicators.py           # compute_realistic_price_bands (VIX-scaled)
│   │   ├── technical_core.py       # RSI, trend_alignment, full tech snapshot
│   │   ├── forensic_audit.py       # Piotroski, Beneish, Altman
│   │   ├── macro_context.py        # Macro/geopolitical context
│   │   ├── strategy_library.py     # Strategy thresholds (≥75% win, ≥0.40R)
│   │   └── holiday_manager.py      # NSE holiday auto-fetch
│   ├── tests/
│   │   └── test_iteration28_fno_analytics.py
│   └── server.py                   # MONOLITH: ~7580 lines
└── frontend/
    └── src/App.js                  # MONOLITH: ~2600 lines
```

## What's Been Implemented (Chronological)

### Session (Feb–Apr 2026)
- ✅ JWT Auth, User Management (Admin/User roles)
- ✅ Kite Connect API v3 integration (OAuth flow + access token mgmt)
- ✅ F&O Signal Generation (78% confluence minimum enforcement)
- ✅ NSE Holiday Management (MongoDB-backed, auto-fetch background task)
- ✅ Master Spec Batches A-C (Forensics, Macro Context, Confluence Scoring)
- ✅ Admin Macro Events Panel (toggle/manage active events)
- ✅ F&O Export (PDF + Word, 14-column standardized layout)
- ✅ F&O Target Generation Audit (removed hardcoded %, pure ATR/VIX/Theta math)
- ✅ Custom F&O Positions (create, refresh, sell, close, delete)
- ✅ Portfolio Analysis (Beta, Sharpe, VaR, max drawdown, correlation matrix)

### Apr 7 2026 — Bug Fixes (Expiry Awareness + Same-Day Targets)
- ✅ **Bug**: Best Exit showed "T+1 (08 Apr)" for same-day expiry position NIFTY07APR22850PE. Root cause: `best_exit_days = min(1, remaining_trading_days) = 1` always projected to next day. Fixed by checking if `expiry_date == today_IST` → sets `best_exit_date_str = "Today (Exit Before 3:30 PM)"` with `best_exit_days = 0`.
- ✅ **Bug**: T2 floating point display `426.84000000000003` — root cause: `entry_price * 3.0` without rounding. Fixed: `round(entry_price * 3.0, 2)`.
- ✅ **Enhancement**: Same-day expiry T1/T2 capped: T1 ≤ 50% gain, T2 ≤ 100% gain (was 150%/200% from full-day ATR which is unrealistic for intraday). Applies to both custom positions and signal generation.
- ✅ **P0 Bug Fix**: Custom F&O `best_exit_price` was showing BELOW current LTP (formula subtracted theta from current LTP instead of ATR-projected max). Fixed both the main path and the LIVE_LTP_UNAVAILABLE early-return path.
- ✅ **P0 Feature**: `compute_option_chain_analytics()` — pure Python computation of Max Pain, PCR, IV Rank, GEX, OI Buildup from live Kite OI/IV/Gamma data
- ✅ **P0 Feature**: `FNOSignalResponse` extended with `max_pain`, `iv_rank`, `oi_buildup`, `gex` fields
- ✅ **P0 Feature**: Index F&O signals now use `compute_option_chain_analytics` (full chain)
- ✅ **P0 Feature**: Individual stock F&O signals now fetch ±5-strike chain for analytics
- ✅ **P0 Feature**: Kite equity live data as primary source (`_fetch_kite_equity_core` via `NSE:SYMBOL` format)
- ✅ **P0 Feature**: Kite historical OHLCV as primary source (`_fetch_kite_hist_ohlcv_for_equity`), yfinance fallback
- ✅ **P0 Feature**: NSE equity instrument tokens stored in `kite_equity_master` MongoDB collection (via `_sync_kite_option_master_daily`)
- ✅ **P0 Feature**: `_get_hist_ohlcv` now tries Kite FIRST, then yfinance (Data Failover Policy)
- ✅ **P0 Feature**: F&O Strategy Thresholds strictly enforced — signals blocked (422) when backtest data shows no strategy passes ≥75% win-rate / ≥0.40R expectancy
- ✅ **P0 Feature**: Multibagger RSI fix — uses real RSI from historical data (`fundamental.get('rsi')`) instead of fake 52W-position-to-RSI proxy
- ✅ **P0 Feature**: VIX-scaled price bands — `compute_realistic_price_bands` now scales `hist_vol` when India VIX > 15
- ✅ **P0 Feature**: `_fetch_hist_one` now returns `{hist_vol, rsi, trend_alignment}` dict (was just float)
- ✅ **P0 Fix**: DB startup cleanup — purges garbage positions (`buy_price≥999000` or null `expiry_date`)

## Key DB Schema
- **users**: `{username, role, credits}`
- **custom_positions**: `{script, underlying, buy_price, quantity_lots, status, best_exit_price, target1, target2, remaining_trading_days, ...}`
- **macro_events**: Active toggled macro events
- **strategy_backtest**: Trade records for strategy win-rate/expectancy enforcement
- **kite_option_master**: F&O option contract tokens (daily sync from Kite)
- **kite_equity_master**: NSE equity instrument tokens (daily sync from Kite) ← NEW
- **nse_holidays**: `{date (YYYY-MM-DD), description, source, year}`
- **hist_ohlcv_cache**: 12h MongoDB cache for historical OHLCV

## Key API Endpoints
- `POST /api/fno/generate` — Generate F&O signals
- `GET /api/fno/signals/index` — NIFTY/BANKNIFTY constituent-weighted signals
- `GET /api/fno/custom-positions` — Open custom F&O positions
- `POST /api/fno/custom-position` — Create custom position
- `GET /api/multibagger/screen` — Multibagger candidates
- `GET /api/portfolio/analyze` — Portfolio risk analytics
- `GET /api/admin/nse-holidays` — View NSE holiday list
- `POST /api/admin/nse-holidays/refresh` — Force refresh holiday list
- `GET /api/admin/macro-events` — View/toggle macro events

## Testing Status
- **Iteration 28** (Apr 2026): 47/49 tests pass
  - 1 expected skip (Kite not authenticated → no signals)
  - 1 infrastructure note (502 timeout on heavy /fno/generate in preview env)
  - All P0 features confirmed via code inspection + API tests
- **Iteration 27**: 46/46 backend tests (F&O Target Generation Audit)

## Prioritized Backlog

### P1 — Next Priorities
- **Codebase refactoring**: Split server.py (~7580 lines) into `routes/` directory
  - `/app/backend/routes/fno.py`
  - `/app/backend/routes/multibagger.py`
  - `/app/backend/routes/portfolio.py`
  - `/app/backend/routes/auth.py`
  - `/app/backend/routes/admin.py`
- **Position Sizing Calculator**: Risk-based position sizing logic

### P2 — Future Tasks
- **App.js refactoring**: Split into separate page components
- **Sector Momentum Dashboard**: Sector rotation visualization
- **Streaming response for /fno/generate**: Avoid gateway timeouts in production (2.5min+ computation)
- **52-week historical IV data**: For proper IV Rank (currently uses within-chain proxy)

## Known Constraints
- Kite Connect API requires daily login (OAuth) for access token
- Without valid Kite session: option analytics (max_pain, iv_rank, gex, oi_buildup) return null
- Without valid Kite session: live equity prices fall back to Moneycontrol/RapidAPI
