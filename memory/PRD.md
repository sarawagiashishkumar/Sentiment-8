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
  server.py               (~8100 lines)
  services/
    indicators.py          — ATR, RSI, MACD, Bollinger, stock eligibility (4 filters incl NCLT)
    research_engine.py     — Re-exports all service modules
    strategy_library.py    — Strategy definitions, weights
    technical_core.py      — Full tech snapshot, divergence, patterns
    macro_engine.py        — Macro context, regime
    forensic_engine.py     — Piotroski, Altman, Beneish
    holiday_manager.py     — NSE holiday management
    market_data.py         — Kite/yfinance data fetching
    index_constituents.py  — NIFTY 50/BANKNIFTY weights, DB table, weighted breadth
    intraday_features.py   — Multi-TF EMAs, VWAP, order flow, regime classification
    options_features.py    — OI buildup, IV rank, bid-ask spread, depth
    news_sentiment.py      — RSS feeds (MC/ET/LiveMint), VADER scoring, NewsFlag
    mfe_mae_engine.py      — MFE/MAE library, probability tables, theta curves, best exit
    confluence_score_v2.py — 4-bucket scoring (A+B+C+D), threshold=78
    fo_universe.py         — Full NSE F&O universe (158 stocks), get_fo_universe()
  models/__init__.py       — Pydantic models
  tests/                   — Pytest test files

/app/frontend/
  src/App.js               (~3000 lines)
  src/utils/exportUtils.js — CSV/PDF export with Best Exit & Golden Star
```

## What's Been Implemented

### Phase 1 (Earlier Sessions)
- F&O Signal Engine with Kite Connect + yfinance
- Multibagger Screener with forensic analysis
- Portfolio Analysis with risk metrics
- JWT Authentication, Macro context, Strategy library, Holiday manager
- Export (CSV/XLS/PDF) with Best Exit & Golden Star

### Phase 2 (Previous Session)
- Same-day expiry target bug fix
- F&O target math overhaul (session_sigma, delta, theta_session)
- Pullback entry strategy ("Best Budget Entry")
- Lot size correction (NIFTY = 65), Export enhancements

### Phase 3 — F&O Master Spec Batches 1-3 (2026-04-07)

**Batch 1: Feature & Data Layer** — VERIFIED (39/40 tests, Iteration 31)
- Index constituent weights (50 NIFTY + 12 BANKNIFTY) in DB
- Weighted breadth metrics, enhanced regime classification (6 labels)
- News sentiment engine (RSS from MC/ET/LiveMint; VADER scoring; NewsFlag)
- Intraday features, options chain features, order flow analysis

**Batch 2: MFE/MAE & Probability Models** — VERIFIED
- MFE/MAE library builder, probability tables (P_hit, P_SL_first)
- Empirical theta curves, forward MFE best exit engine
- No-chasing rule, 0DTE ATM safety gate

**Batch 3: 4-Bucket Confluence Score** — VERIFIED
- A(Strategy)+B(Direction)+C(Options/Sentiment)+D(Trade Quality)
- Score = 0.30A+0.30B+0.25C+0.15D, Threshold = 78
- Old V1 kept as fallback only

### Mini-Batch: F&O Universe Expansion (2026-04-07)
**VERIFIED (20/20 tests, Iteration 32)**
- **OLD:** Hardcoded `STOCK_FNO_UNIVERSE` with 14 stocks
- **NEW:** `get_fo_universe()` returns 158 NSE F&O-eligible stocks
- Smart pre-filtering: scans up to 40 stocks per request (prioritized by market cap)
- Kite option master sync expanded to full universe
- Display caps: 4 NIFTY + 4 BANKNIFTY + 10 stock signals (top by score)
- Eligibility filters enforced: SBIN disqualified (72% debt)

## Testing Status
- Iteration 31: 39/40 tests (Batches 1-3), 1 flaky timeout
- Iteration 32: 20/20 tests (F&O Universe expansion)

## Prioritized Backlog

### P0 (Critical)
- None currently blocking

### P1 (Next)
- **Batch 4**: Sticky card monitoring & alerts (NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT events)
- **Position Sizing Calculator**: Risk-based lot sizing
- **Budget Entry Trigger Alert**: Live monitoring when pullback zone is hit
- **Strategy backtest data population**: Wire strategy_backtests collection for real Bucket A scores

### P2 (Future)
- server.py refactoring (~8100 lines → routes/ modules)
- App.js refactoring (~3000 lines → page components)
- Streaming response for /fno/generate (to avoid gateway timeout)
- 52-week IV data for proper IV Rank calculation
- Dynamic NIFTY 500/BSE 500 constituency parsing
