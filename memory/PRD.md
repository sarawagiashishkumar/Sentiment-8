# PRD — Trading Signal Platform

## Original Problem Statement
Full-stack web app for stock analysis (FastAPI, React, MongoDB). Core features: F&O Trading Signals, Multibagger Screener, Portfolio Analysis.

## Core Requirements
1. **Global architecture**: ALL calculations in backend Python. NO LLM numeric work.
2. **Market universe**: NIFTY 500, NIFTY 50, BANKNIFTY, BSE 500.
3. **Mandatory Filtering**: Equity LTP >= 50. Not NCLT/DRT. Debt < 30% mcap. Profit positive 1/3 quarters.
4. **Time/Expiry**: 09:15-15:30 IST strict. Intraday targets mathematically assured.
5. **Entry Strategy**: Pullback Entry ("Best Budget Entry") instead of Momentum-based.
6. **No-Loss Guarantee**: Confluence Score optimized for zero loss-making signals.

## Architecture
```
/app/backend/
  server.py               (~8000+ lines — monolith, all F&O/Screener/Portfolio endpoints)
  services/
    indicators.py          — ATR, RSI, MACD, Bollinger, stock eligibility (4 filters incl NCLT)
    research_engine.py     — Re-exports all service modules
    strategy_library.py    — Strategy definitions, weights
    technical_core.py      — Full tech snapshot, divergence, patterns
    macro_engine.py        — Macro context, regime
    forensic_engine.py     — Piotroski, Altman, Beneish
    holiday_manager.py     — NSE holiday management
    market_data.py         — Kite/yfinance data fetching
    ### NEW (Batch 1-3):
    index_constituents.py  — NIFTY 50/BANKNIFTY weights, DB table, weighted breadth
    intraday_features.py   — Multi-TF EMAs, VWAP, order flow, regime classification
    options_features.py    — OI buildup, IV rank, bid-ask spread, depth
    news_sentiment.py      — RSS feeds (MC/ET/LiveMint), VADER scoring, NewsFlag
    mfe_mae_engine.py      — MFE/MAE library, probability tables, theta curves, best exit
    confluence_score_v2.py — 4-bucket scoring (A+B+C+D), threshold=78
  models/__init__.py       — Pydantic models
  tests/                   — Pytest test files

/app/frontend/
  src/App.js               (~3000 lines — monolith)
  src/utils/exportUtils.js — CSV/PDF export with Best Exit & Golden Star
```

## What's Been Implemented

### Phase 1 (Earlier Sessions)
- F&O Signal Engine with Kite Connect + yfinance
- Multibagger Screener with forensic analysis
- Portfolio Analysis with risk metrics
- JWT Authentication
- Macro context, strategy library, holiday manager
- Export (CSV/XLS/PDF) with Best Exit & Golden Star

### Phase 2 (Previous Session)
- Same-day expiry target bug fix
- F&O target math overhaul (session_sigma, delta, theta_session)
- Pullback entry strategy ("Best Budget Entry")
- UI "Wait for Budget Entry" advisory
- Lot size correction (NIFTY = 65)
- Export enhancements (Best Exit column)

### Phase 3 — F&O Master Spec Batches 1-3 (Current Session, 2026-04-07)

**Batch 1: Feature & Data Layer** — VERIFIED
- Index constituent weights (NIFTY 50: 50 stocks, BANKNIFTY: 12 banks) in DB
- Weighted breadth metrics (pct_uptrend, pct_above_vwap, breadth_score)
- Enhanced regime classification (6 labels: LowVolTrend, LowVolRange, HighVolTrend, HighVolCrash, PreEvent, PostEventIVCrush)
- News sentiment engine (RSS from MoneyControl, ET, LiveMint; VADER scoring; NewsFlag per symbol/sector)
- Intraday feature vector builder (RSI, MACD, Stochastic, VWAP distance, flow band)
- Options chain features (OI buildup classification, IV rank, bid-ask spread, moneyness)
- Order book imbalance & volume delta with flow bands (StrongBuyFlow...StrongSellFlow)

**Batch 2: MFE/MAE & Probability Models** — VERIFIED
- MFE/MAE library builder from historical OHLCV (simulated trade replay)
- Probability tables: P_hit and P_SL_first per target offset
- Probability-based T1/T2 selector (more conservative than ATR targets when data supports)
- Empirical theta curves (calibrated for Indian F&O: index/stock, weekly/monthly, ATM/ITM/OTM)
- Forward MFE to expiry with theta adjustment
- Best Exit online engine (forward MFE + theta + regime)
- No-chasing rule (blocks fresh entries when >75% of expected band achieved)
- 0DTE ATM long safety check (blocks after 14:30 IST cutoff)

**Batch 3: 4-Bucket Confluence Score** — VERIFIED
- Bucket A (Strategy & Backtest): win_rate, expectancy_R, trade_count scoring
- Bucket B (Direction & Structure): multi-TF alignment, RSI context, ADX, breadth, regime
- Bucket C (Options & Sentiment): OI buildup, IV rank, liquidity, flow band, news flag, PCR
- Bucket D (Trade Quality): R:R to T1/T2, P_hit probability, SL distance, concentration
- Final score: 0.30*A + 0.30*B + 0.25*C + 0.15*D
- Threshold: Score < 78 = suppress signal
- Old V1 scoring kept as fallback (feature flag pattern)

**Mandatory Filters Enhanced:**
- check_stock_eligibility now has 4 filters (added NCLT/DRT check)
- Trading session guard (logs warning outside 09:15-15:30 IST)

## Testing Status
- Iteration 31: 39/40 backend tests pass (97.5%), 1 flaky timeout
- 2 bugs fixed by testing agent (idxmax→argmax for DatetimeIndex)
- All 6 new modules import correctly
- F&O generate endpoint returns valid response
- Frontend loads without errors

## Prioritized Backlog

### P0 (Critical)
- None currently blocking

### P1 (Next)
- **Batch 4**: Sticky card monitoring & alerts (NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT events)
- **Position Sizing Calculator**: Risk-based lot sizing
- **Budget Entry Trigger Alert**: Live monitoring when pullback zone is hit
- **Strategy backtest data population**: Wire strategy_backtests collection for real Bucket A scores

### P2 (Future)
- server.py refactoring (~8000 lines → routes/ modules)
- App.js refactoring (~3000 lines → page components)
- Streaming response for /fno/generate
- 52-week IV data for proper IV Rank calculation
- Dynamic NIFTY 500/BSE 500 constituency parsing (currently NIFTY 50 + BANKNIFTY)
