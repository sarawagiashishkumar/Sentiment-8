# PRD — Trading Research Platform

## Original Problem Statement
Build a minimalist full-stack web app for stock analysis using FastAPI, React, and MongoDB.
Core: Generate high-quality, profitable F&O signals based on a Master Spec (Futures & Options),
plus Multibagger Screener and Portfolio Analysis for Indian equities.

## Users / Personas
- Primary: Admin owner (Rishaan/Shish) — uses all features
- Secondary: Invited users — view signals, analyze portfolio, run screener

## Architecture
- Frontend: React (App.js + Tailwind CSS + Shadcn UI), port 3000
- Backend: FastAPI monolith (server.py + services/), port 8001
- Database: MongoDB
- Auth: UUID token-based (no JWT), PIN login
- Live Data: Kite Connect v3 API + yfinance
- Research Engine: services/research_engine.py (new in session 2)

## Core Features Implemented

### Session 1 Completions
- JWT Auth (UUID tokens) + RBAC (admin/user)
- Credit system
- Kite API integration (live quotes, option master, PCR, OI)
- yfinance fundamentals (ROE, ROCE, Piotroski, Beneish)
- F&O Signal Generation (NIFTY, BANKNIFTY, 14 liquid stocks)
- Multibagger Screener (80+ stocks, tier scoring, thesis generation)
- Portfolio Analysis (CSV/paste input, horizon bands, recommendations)
- Admin Panel (user management, domain mapping)
- Custom F&O Position tracking
- Expiry-aware Best Exit + Theta Decay
- Multibagger Custom Search (POST /api/multibagger/custom-search)
- Multibagger hover UI (4-row block highlighting)

### Session 3 Completions (2026-04-06)
1. **Dual-Source Parallel Fetch + Verification** (`services/data_verifier.py`):
   - Primary: Kite Connect API (8s timeout, full OHLC+OI snapshot)
   - Fallback: yfinance NSE (free, no auth, parallel async.gather)
   - Cross-verify: If |kite - yf| > 2% → log discrepancy warning, use Kite as authoritative
   - `fetch_verified_price()` + `fetch_verified_snapshot()` used in F&O signal pipeline
   
2. **NSE Holidays Fix**: Removed `2026-04-06` (incorrectly listed, market was open).
   2026 holidays now correctly include: Jan 26, Feb 19, Mar 25, Apr 3, Apr 14, May 1, Aug 15, Oct 2, Oct 23, Nov 4, Nov 24

3. **VIX-Based Theta Decay** (`compute_vix_theta_decay` in data_verifier.py):
   - Replaces fixed 0.15 multiplier with Black-Scholes ATM theta approximation
   - Formula: Θ_daily = option_price × σ / (2 × √(T × 252))
   - σ = VIX/100 × scale_factor (1.25 for ≤7 days, 1.10 for ≤21 days, 1.0 otherwise)
   - Example: 100.0 entry, 14 days, exit in 7, VIX=16.5 → ₹16.97 theta (vs old ₹7 static)
   - ThetaModel tag added to trigger_factors for transparency

4. **Session-Time-Aware T1/T2 Targets**:
   - `get_minutes_to_session_close()` — returns exact minutes until 15:30 IST
   - T1/T2 now use `min(minutes_to_expiry, minutes_to_session_close)` for intraday realism
   - Market session status (`is_open`, `ist_time`, `status`) added to FNOGenerateResponse

5. **Dynamic Target Revision** for Custom F&O positions:
   - Trigger 1: LTP ≥ T1 → T2 revised up by 1.5× original T1-T2 gap
   - Trigger 2: Underlying moved > 0.5% favorably + VIX calm + 90+ min left → targets scaled up proportionally
   - Near-expiry cap: T2 capped at 1.35× entry when < 2 trading days + 120 min to close

6. **Market Session Status** in F&O responses:
   - `market_session` dict with `is_open`, `ist_time`, `minutes_to_close`, `status`
   - Pre-market/post-market signals include session context in no_signals_alert

7. **78% Confluence** (verified again): All stock_signals and top_trades consistently at ≥78%
   - Min observed: 78, Max observed: 92 across 12 stock signals

1. **Historical API Fix** — Kite option master now stores numeric `instrument_token` from CSV.
   `_resolve_kite_instrument_for_contract` returns numeric token. Historical API calls work (200 OK, 256 candles).

2. **Research Engine** (`/app/backend/services/research_engine.py`) — Pure Python computation:
   - RSI, MACD, Bollinger Bands, ATR, ADX, OBV, Stochastic, SMA/EMA
   - Historical Volatility (annualized)
   - Realistic Price Bands (volatility-based, 6 horizons: 1W/1M/3M/6M/9M/1Y)
   - Market Regime Classification (5 regimes, VIX+ADX+RSI)
   - Stock Eligibility Filters (price ≥ ₹50, debt < 30% mktcap, recent profit)
   - ATR-based F&O Targets (not fixed %)
   - Portfolio Risk Metrics (beta, Sharpe, max drawdown, VaR 95%)
   - Enhanced Portfolio Verdict (6-scale: STRONG HOLD → EXIT IMMEDIATELY)
   - Technical Confluence Bonus (RSI/MACD/trend/OBV/ADX/BB/Stoch)
   - Urgent Exit Detection (expiry, session close, loss threshold, crash regime)

3. **78% Minimum Confluence Enforcement** — F&O signals require confluence_score ≥ 78 (was 58)

4. **No-Signals Alert** — `no_signals_alert` field with specific reason when no signals qualify

5. **Market Regime in F&O Response** — `market_regime` dict (regime, vix, options_strategy, description)

6. **Enhanced Fundamental Data** — Added: `total_debt_to_market_cap`, `recent_profit_positive`,
   `revenue_cagr_3y`, `fcf_yield` to yfinance fetch + DB cache

7. **Eligibility Filters on Stock F&O + Multibagger** — Disqualifies stocks failing price/debt/profit checks

8. **Volatility-based Price Bands** — Multibagger + Portfolio now use historical vol, not static %

9. **Portfolio Risk Metrics** — `PortfolioAnalyzeResponse` now includes `portfolio_risk_metrics`
   with beta, Sharpe proxy, max drawdown, VaR 95%, sector breakdown, win rate

10. **Enhanced Portfolio Verdicts** — compute_portfolio_verdict() generates evidence-backed
    STRONG HOLD / BUY MORE NOW / ACCUMULATE ON DIPS / WAIT & WATCH / PARTIAL EXIT / EXIT IMMEDIATELY

11. **Urgent Exit for Custom Positions** — Enhanced _refresh_open_position uses check_urgent_exit()

12. **Historical OHLCV Cache** — _get_hist_ohlcv() with 6h in-memory + 12h MongoDB cache

### Session 4 Completions (2026-04-06)
1. **NSE Holiday Calendar FY 2026-2027** — Corrected the hardcoded holiday list (old list had wrong dates: Feb 19 Shivaratri, Mar 25 Holi, Oct 23 Diwali). Now uses official NSE 2026 calendar (16 base holidays). Live NSE API fetch returned 20 total including Mahashivratri, Id-Ul-Fitr, Bakri Id, Muharram, Ganesh Chaturthi, Dussehra, Diwali-Balipratipada.
2. **MongoDB-backed Holiday Storage** — `nse_holidays` collection stores holidays with fields: date, name, year, source, updated_at. Auto-seeds hardcoded defaults on first run.
3. **Background Auto-Fetch Task** — Daily coroutine at 02:00 IST. During March 25-31 window (one week before April 1st), auto-fetches upcoming FY's holidays from NSE API (primary) + Zerodha (fallback). Also fetches if current year has 0 holidays loaded.
4. **Admin Holiday Management Endpoints**:
   - GET /api/admin/nse-holidays — View all holidays with source tracking
   - POST /api/admin/nse-holidays/refresh?year=YYYY — Manual trigger for live fetch
5. **Live Holiday Set in Trading Day Calc** — `get_remaining_trading_days()` and `get_nth_trading_day_from_today()` now read from the dynamic holiday set (MongoDB-backed) instead of static hardcoded values.

## Key API Endpoints
- POST /api/auth/access — Login (username + pin)
- POST /api/fno/generate — F&O signal generation (now includes market_regime + no_signals_alert)
- POST /api/portfolio/analyze — Portfolio analysis (now includes portfolio_risk_metrics)
- GET /api/multibagger/candidates — Screener (now with eligibility filters + vol-based bands)
- POST /api/multibagger/custom-search — Custom search
- POST /api/kite/refresh-option-master — Force re-sync (now stores instrument_token)
- GET /api/kite/auth-url — Kite OAuth flow
- GET /api/admin/nse-holidays — View all NSE holidays (admin)
- POST /api/admin/nse-holidays/refresh?year=YYYY — Manual holiday refresh (admin)

## Key DB Schema
- **app_users**: {username, hashed_pin, role, credits, created_by}
- **custom_positions**: {user_id, script, buy_price, quantity_lots, status, best_exit_days, ...}
- **kite_option_master**: {underlying, expiry, strike, option_type, tradingsymbol, instrument, instrument_token (NEW), lot_size}
- **system_meta**: {key: "kite_session", value: {access_token, ...}}
- **fundamental_cache**: {symbol, roe, roce, piotroski_score, total_debt_to_market_cap (NEW), recent_profit_positive (NEW), revenue_cagr_3y (NEW), fcf_yield (NEW), ...}
- **hist_ohlcv_cache**: {symbol, period, records, cached_at_ts} (NEW)
- **nse_holidays**: {date (YYYY-MM-DD, unique index), name, year, source, updated_at} (NEW - Session 4)

## Architecture Files
- /app/backend/server.py — Monolith: ~6420 lines (NEEDS REFACTORING - P2)
- /app/backend/services/research_engine.py — Research engine
- /app/backend/services/data_verifier.py — Dual-source data verification
- /app/backend/services/holiday_manager.py — NSE holiday management + background auto-updater (NEW - Session 4)
- /app/backend/services/market_data.py — Market data helpers
- /app/frontend/src/App.js — Frontend monolith: ~2700 lines (NEEDS REFACTORING - P2)
- /app/frontend/src/App.css

## Backlog (Prioritized)

### P0 — Full Master Spec Implementation (Pending)
- Constituent-weighted NIFTY50/BANKNIFTY breadth scoring
- Strategy state machine (PENDING → ACTIVE → WATCHING_SL → etc.)
- Per-strategy backtest tracking (win rate, expectancy, auto-disable)
- Real intraday signal triggering (ORB 9:15-9:30, VWAP reversion)

### P1 — Blocked / Pending Resolution
- Kite Historical API for intraday candles (NOW FIXED — instrument_token resolved)

### P2 — Refactoring (Developer Experience)
- Split server.py into: routes/, services/, models/
- Split App.js into feature components

### P2 — Future Features
- Position Sizing Calculator
- Sector Momentum Dashboard (heatmap)
- Mobile App
- Kite SSO for Portfolio
- NIFTY 500 + BSE 500 universe scraping (currently ~80 stocks)

## Test Reports
- /app/test_reports/iteration_15.json — Session 1 final test (100% pass)
- /app/test_reports/iteration_16.json — Session 2 final test (49/50 pass, 1 skip)
- /app/test_reports/iteration_17.json — Session 3 final test (62/62 pass)
- /app/test_reports/iteration_18.json — Session 4: NSE Holiday Management (21/21 pass)
