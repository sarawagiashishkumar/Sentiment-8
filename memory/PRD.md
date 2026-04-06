# PRD — Trading Research Platform

## Original Problem Statement
Build a minimalist full-stack web app for stock analysis using FastAPI, React, and MongoDB.
Core: Generate high-quality, profitable F&O signals based on a Master Spec (Futures & Options),
plus Multibagger Screener and Portfolio Analysis for Indian equities.

ALL calculations must be in backend Python — NEVER in LLM or frontend. No UI modifications.

## Users / Personas
- Primary: Admin owner (Rishaan/Shish) — uses all features
- Secondary: Invited users — view signals, analyze portfolio, run screener

## Architecture
- Frontend: React (App.js + Tailwind CSS + Shadcn UI), port 3000
- Backend: FastAPI monolith (server.py + services/), port 8001
- Database: MongoDB
- Auth: UUID token-based (no JWT), PIN login
- Live Data: Kite Connect v3 API + yfinance
- Research Engine: services/research_engine.py (3700+ lines, all batches)

## Core Features Implemented

### Session 1–3 Completions (Previous Sessions)
- JWT Auth (UUID tokens) + RBAC (admin/user) + credit system
- Kite API integration (live quotes, option master, PCR, OI)
- yfinance fundamentals (ROE, ROCE, Piotroski, Beneish)
- F&O Signal Generation (NIFTY, BANKNIFTY, 14 liquid stocks)
- Multibagger Screener (80+ stocks, tier scoring, thesis generation)
- Portfolio Analysis (CSV/paste input, horizon bands, recommendations)
- 78% Confluence enforcement, No-Signals Alert
- Expiry-aware Best Exit + VIX Theta Decay
- ATR-based F&O Targets (not fixed %)
- Session-time-aware T1/T2 (before 3:30 PM IST)
- Dynamic Target Revision + URGENT EXIT alerts
- Dual-source parallel fetch: Kite→yfinance fallback + cross-verification
- Portfolio Risk Metrics (beta, Sharpe, VaR, max drawdown)
- 6-scale Portfolio Verdict (STRONG HOLD → EXIT IMMEDIATELY)
- Market Regime Classification (5 regimes with VIX/ADX/RSI)
- Volatility-based Price Bands (6 horizons)
- Historical OHLCV Cache (6h in-memory + 12h MongoDB)

### Session 4 Completions (2026-04-06)
1. NSE Holiday Calendar FY 2026-2027 — MongoDB-backed, auto-refresh background task
2. Admin endpoints: GET/POST /api/admin/nse-holidays
3. 21/21 backend tests passing (iteration_18)

### Session 6 Completions — 5 Wiring Actions (2026-04-06)
ALL wired into active API flows. 64/64 tests passing (iteration_20). Bug fixed: macro_context sector match.

#### Action 1: Signal Lifecycle State Machine Wired
- `transition_signal_state()` called inside `_refresh_open_position()` on every position refresh
- States: PENDING→ACTIVE→WATCHING_SL→WATCHING_T1→WATCHING_T2→CLOSED_WIN|CLOSED_LOSS|EXPIRED|CANCELLED
- `signal_state` + `signal_state_reason` + `stop_loss` fields now persisted in `custom_positions` MongoDB
- URGENT_EXIT triggered when SL pressure + ≤60 min to expiry; EXPIRED triggered when ≤15 min to expiry

#### Action 2: merge_duplicate_holdings + compute_master_stock_snapshot Wired
- `merge_duplicate_holdings()` called at start of `_analyze_portfolio_positions()` — deduplicates same-symbol
- `compute_master_stock_snapshot()` called per-stock in portfolio analysis → adds 52W/3M/1M levels, ATH%, index memberships
- `compute_full_technical_snapshot()` used for live RSI/trend in portfolio verdicts (replaced placeholder None values)
- `PortfolioStockAnalysis` model now has: `master_snapshot`, `altman_z_zone`, `roic_wacc_spread`, `piotroski_score`, `beneish_m_score`
- Altman DISTRESS zone and ROIC<WACC appended to portfolio comments when detected

#### Action 3: Strategy Backtest MongoDB Persistence
- New collection: `strategy_backtest` — stores win/loss/r_multiple per strategy + symbol
- `GET /api/admin/strategy-stats` — aggregated per strategy_id with win_rate, expectancy, eligible, auto_disabled
- `POST /api/admin/strategy-stats/record` — record a trade result (admin only)
- `GET /api/strategy-library` — public (authenticated) endpoint returning all 13 strategy definitions
- `check_strategy_eligible()` auto-disables strategy if win_rate<75% or expectancy<0.40R after 10+ trades

#### Action 4: Macro Context Wired into Signals + Multibagger
- `compute_macro_context()` called inside `build_fno_signal()` for each F&O signal's sector
- Macro TAILWIND/HEADWIND added to `trigger_factors` list
- `FNOSignalResponse` now includes `macro_context` field (regime, sector bias, event impacts)
- Multibagger thesis_parts includes sector macro bias (TAILWIND/HEADWIND flagged)
- Bug fix: sector matching now uses word-boundary regex (fixes 'IT' matching 'capital' substring)

#### Action 5: Constituent-Weighted NIFTY/BANKNIFTY Index Breadth (LIVE)
- `_compute_enhanced_index_breadth()` async function: fetches tech snapshots for top 12 NIFTY/BANKNIFTY constituents
- Calls `compute_index_constituent_bias()` with weighted conviction scores
- For NIFTY/BANKNIFTY F&O signals: breadth_score and weighted_bias computed from live constituent data
- `FNOSignalResponse` now includes `index_breadth` field with breadth_score [0–100], top positive/negative contributors


ALL calculations pure Python backend. No UI changes. 120/120 tests passing (iteration_19).

#### Batch 1: Advanced Technical Analysis (research_engine.py)
- Williams %R (period 14, oversold < -80, overbought > -20)
- CCI — Commodity Channel Index (period 20, overbought/oversold flags)
- VPT — Volume Price Trend (cumulative, RISING/FALLING/FLAT trend)
- Accumulation/Distribution Line (CLV-weighted volume accumulation trend)
- Ichimoku Cloud (Tenkan 9, Kijun 26, Senkou A/B 26-period lead, Chikou, Kumo color, TK cross, Kumo twist, bullish/bearish signal flags)
- Fibonacci Retracements (23.6%, 38.2%, 50%, 61.8%, 78.6%) + Extensions (127.2%, 161.8%, 200%)
- Pivot Points — Classic (PP, S1/S2/S3, R1/R2/R3) + Camarilla (H3/H4, L3/L4)
- Support/Resistance — swing-based horizontal levels, clustered within 0.5%
- RSI Divergence Detection — Regular Bullish/Bearish + Hidden Bullish/Bearish
- Candlestick Patterns — Doji, Hammer, Inverted Hammer, Shooting Star, Bullish/Bearish Engulfing, Bullish/Bearish Harami, Morning Star, Evening Star
- Multi-timeframe Trend — Daily (20d), Weekly (~12w), Monthly (~6m) via daily OHLCV; alignment: STRONGLY_BULLISH → STRONGLY_BEARISH
- Chart Patterns — Bull Flag, Bear Flag, Bullish/Bearish Pennant with confidence levels
- Updated compute_full_technical_snapshot() — now includes all 12 new indicators
- Updated compute_technical_confluence_bonus() — cap raised 12→18, +15 new scoring conditions

#### Batch 2: Forensic Financial Audit (research_engine.py)
- Altman Z-Score (5-variable: working capital, retained earnings, EBIT, mkt cap/liabilities, asset turnover) — zones: SAFE >2.99, GREY 1.81–2.99, DISTRESS <1.81
- Earnings Quality — CFO/NI ratio (>1.0=HIGH, <0.5=LOW) + Balance-sheet accrual ratio
- Forensic Red Flags — Debtor days, Inventory days, Creditor days, CWIP/Assets, Goodwill/NetWorth, Share dilution%, Deferred tax growth, Promoter pledging%, Contingent liabilities
- ROIC vs WACC — NOPAT/InvestedCapital vs (Ke×E/V + Kd×D/V×(1-t)); spread = value creation/destruction
- Growth Quality — Revenue CAGR (multi-year), EBITDA margin trend (IMPROVING/STABLE/DETERIORATING), FCF yield
- compute_forensic_audit() — master function: composite score 0–100, overall_risk LOW/MEDIUM/HIGH, investable flag
- Wired into _fetch_yfinance_fundamentals() → fundamental_cache MongoDB (new fields: altman_z*, roic*, wacc*, cfo_ni_ratio, accrual_ratio, ebitda_margin*, growth_quality)
- Multibagger thesis now includes Altman Z, ROIC vs WACC, CFO/NI, EBITDA trend

#### Batch 3: Macro & Regime Context (research_engine.py)
- Enhanced Regime Classifier — 8 regimes: LOW_VOL_TREND_BULL, LOW_VOL_RANGE, NORMAL_VOL_TREND, NORMAL_VOL_RANGE, HIGH_VOL_TREND, HIGH_VOL_CRASH, PRE_EVENT, POST_EVENT_IV_CRUSH
- VIX buckets: <12=LOW, 12–18=NORMAL, 18–25=ELEVATED, 25+=PANIC
- Strategy selection grid (REGIME_STRATEGY_GRID) — each regime maps to primary/secondary/avoid F&O strategy
- Sector Impact Map (SECTOR_MACRO_IMPACT_MAP) — 15 macro events: RBI hike/cut, crude spike/fall, FII in/outflow, USD strengthen, INR weaken, India budget capex, PLI scheme, US Fed hike, China slowdown, Geopolitical conflict, EV adoption, Semiconductor shortage
- compute_macro_context() — returns regime + sector_impact + event_impacts + geopolitical_flag + strategy_suggestion
- F&O signal generation now uses classify_market_regime_enhanced() (ADX+RSI aware)

#### Batch 4: Portfolio-Level Risk Analytics (research_engine.py + server.py)
- Correlation Matrix — pairwise Pearson (Numpy corrcoef) on 90-day daily returns; flags high-corr pairs >0.70
- Stress Tests — 5 scenarios: NIFTY_CRASH_10PCT, CRUDE_SPIKE_30PCT, INR_WEAKENS_5PCT, US_RECESSION, RBI_RATE_HIKE_50BPS; per-holding impact using beta and sector overrides
- Diversification Audit — sector allocation%, market-cap split (Large/Mid/Small/Micro), cyclical vs defensive%, domestic vs export%, flags: over-concentration, micro-cap>25%, single stock>20%
- Upcoming Catalysts — RBI meeting calendar (11 dates FY25-26), Fed meeting calendar (10 dates); flags meetings within 15-day window
- merge_duplicate_holdings() — weighted-average price + aggregated quantities for same-symbol entries
- compute_master_stock_snapshot() — 52W/3M/1M high/low, ATH, % below ATH, IPO info if <5yr listed, index memberships, market-cap category
- PortfolioAnalyzeResponse now includes enhanced_analytics dict (stress, diversification, correlation, catalysts)

#### Batch 5: F&O Strategy Library & Signal State Machine (research_engine.py + server.py)
- Strategy Library (STRATEGY_LIBRARY) — 13 strategies:
  - Intraday: S1_ORB (Opening Range Breakout), S2_VWAP (VWAP Reversion), S3_SUPERTREND (Supertrend+EMA), S4_MACD_ADX (MACD+ADX), S5_RSI_REVERSION
  - Swing: SW1_52W_BREAKOUT, SW2_200DMA_BOUNCE, SW3_FLAG_BREAKOUT
  - Expiry/Options: E1_SHORT_STRADDLE, E2_IRON_CONDOR, E3_CALENDAR_SPREAD
  - Screener-linked: SF1_SCREENER_MOMENTUM, SF2_FORENSIC_QUALITY
- Backtest Stats Management — update_backtest_stats() + check_strategy_eligible(); auto-disable at win_rate<75% or expectancy<0.40R; provisional allow if <10 trades
- Signal Lifecycle State Machine — PENDING→ACTIVE→WATCHING_SL→WATCHING_T1→WATCHING_T2→CLOSED_WIN|CLOSED_LOSS|EXPIRED|CANCELLED; transition_signal_state() evaluates live price vs SL/T1/T2
- Constituent Weights — NIFTY50 (50 stocks with approx weights) + BANKNIFTY (12 stocks)
- compute_index_constituent_bias() — weighted aggregation of constituent signals → BULLISH/BEARISH/NEUTRAL with breadth_score [0–100], conviction, top contributors
- select_strategy_for_signal() auto-selects strategy from library given regime+direction
- FNOSignalResponse now includes strategy_library_id, strategy_library_name, market_regime fields

## Key API Endpoints
- POST /api/auth/access — Login (username + pin)
- POST /api/fno/generate — F&O signal generation (strategy_library_id, market_regime in response)
- POST /api/portfolio/analyze — Portfolio analysis (enhanced_analytics: stress/corr/diversification)
- GET /api/multibagger/candidates — Screener (Altman Z, ROIC, forensic fields in response)
- POST /api/multibagger/custom-search — Custom search
- POST /api/kite/refresh-option-master — Force re-sync
- GET /api/kite/auth-url — Kite OAuth flow
- GET /api/admin/nse-holidays — View NSE holidays
- POST /api/admin/nse-holidays/refresh?year=YYYY — Manual holiday refresh

## Key DB Schema
- **app_users**: {username, hashed_pin, role, credits, created_by}
- **custom_positions**: {user_id, script, buy_price, quantity_lots, status, best_exit_days, ...}
- **kite_option_master**: {underlying, expiry, strike, option_type, tradingsymbol, instrument_token, lot_size}
- **fundamental_cache**: {symbol, roe, roce, piotroski_score, beneish_m_score, altman_z_score, altman_z_zone, roic, wacc, roic_wacc_spread, cfo_ni_ratio, accrual_ratio, ebitda_margin_latest, ebitda_margin_trend, revenue_cagr_3y, fcf_yield, total_debt_to_market_cap, recent_profit_positive, ...}
- **hist_ohlcv_cache**: {symbol, period, records, cached_at_ts}
- **nse_holidays**: {date (YYYY-MM-DD, unique index), name, year, source, updated_at}

## Architecture Files
- /app/backend/server.py — Monolith: ~6710 lines
- /app/backend/services/research_engine.py — Research engine: 3700+ lines (all batches 1–5)
- /app/backend/services/data_verifier.py — Dual-source verification
- /app/backend/services/holiday_manager.py — NSE holiday management + background auto-updater
- /app/backend/services/market_data.py — Market data helpers
- /app/frontend/src/App.js — Frontend monolith: ~2700 lines (NO CHANGES IN SESSION 5)

## Backlog (Prioritized)

### P2 — Refactoring (Developer Experience)
- Split server.py into: routes/, services/, models/
- Split App.js into feature components
- Split research_engine.py into batch modules (3700 lines)

### P2 — Future Features
- Real-time constituent-weighted NIFTY breadth scoring (using live Kite data for all 50 stocks)
- Position Sizing Calculator
- Sector Momentum Dashboard (heatmap)
- Mobile App
- Kite SSO for Portfolio
- NIFTY 500 + BSE 500 universe expansion (currently ~80 stocks)
- Per-strategy backtest stats MongoDB persistence (strategy_backtest collection)
- Live intraday signal triggers: ORB 9:15-9:30 real-time detection

## Test Reports
- /app/test_reports/iteration_15.json — Session 1 final (100% pass)
- /app/test_reports/iteration_16.json — Session 2 final (49/50 pass)
- /app/test_reports/iteration_17.json — Session 3 final (62/62 pass)
- /app/test_reports/iteration_18.json — Session 4: NSE Holiday Management (21/21 pass)
- /app/test_reports/iteration_19.json — Session 5: Batch 1-5 Research Engine (120/120 pass)
