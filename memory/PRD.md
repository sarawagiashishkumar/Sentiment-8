# PRD — Trading Signal Platform

## Original Problem Statement
Full-stack web app for stock analysis (FastAPI, React, MongoDB). Core features: F&O Trading Signals, Multibagger Screener, Portfolio Analysis.

## Core Requirements
1. **Global architecture**: ALL calculations in backend Python. NO LLM numeric work.
2. **Market universe**: NIFTY 500, NIFTY 50, BANKNIFTY, BSE 500.
3. **Mandatory Filtering**: Equity LTP >= 50. Not NCLT/DRT. Debt < 30% mcap. Profit positive 1/3 quarters.
4. **Time/Expiry**: 09:15-15:30 IST strict. Intraday targets mathematically assured.
5. **Entry Strategy**: Pullback Entry ("Best Budget Entry").
6. **Confluence Score V2**: 4-Bucket system (A: Strategy, B: Direction, C: Options/Flow, D: Trade Quality). Threshold >= 78.
7. **Dynamic Targets**: Probability-based T1/T2 using MFE/MAE + Theta decay.
8. **Alerts & Monitoring**: Real-time monitoring of sticky positions with NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT events.

## Architecture
```
/app/backend/
  server.py               (~8300 lines)
  services/
    indicators.py          — ATR, RSI, MACD, eligibility (4 filters incl NCLT)
    research_engine.py     — Re-exports all service modules
    strategy_library.py    — Strategy definitions, weights
    technical_core.py      — Full tech snapshot
    macro_engine.py        — Macro context, regime
    forensic_engine.py     — Piotroski, Altman, Beneish
    holiday_manager.py     — NSE holiday management
    market_data.py         — Kite/yfinance data fetching
    data_verifier.py       — Parallel verification
    index_constituents.py  — NIFTY 50/BANKNIFTY weights, weighted breadth
    intraday_features.py   — Multi-TF EMAs, VWAP, order flow, regime
    options_features.py    — OI buildup, IV rank, bid-ask, depth
    news_sentiment.py      — RSS feeds, VADER scoring, NewsFlag
    mfe_mae_engine.py      — MFE/MAE library, probability tables, theta, best exit
    confluence_score_v2.py — 4-bucket scoring (A+B+C+D), threshold=78
    fo_universe.py         — Full NSE F&O universe (158 stocks)
    position_monitor.py    — Batch 4: NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT alerts
  models/__init__.py       — Pydantic models (incl MonitoringEvent)
```

## Completed Work

### Phase 1-2 (Earlier Sessions)
- F&O Signal Engine, Multibagger Screener, Portfolio Analysis
- Pullback entry, lot size fix, export enhancements

### Phase 3 — Batches 1-3 (2026-04-07)
- Batch 1: Feature & data layer (constituents, features, news, flow)
- Batch 2: MFE/MAE backtests, probability models, theta curves
- Batch 3: 4-Bucket Confluence Score V2

### Mini-Batch: F&O Universe (2026-04-07)
- Expanded from 14 hardcoded to 158 NSE F&O stocks

### Step 1: Kite Connect Primary (2026-04-07)
- India VIX: Kite-first, yfinance fallback
- MFE/MAE enabled for ALL underlyings (NIFTY/BANKNIFTY included)

### Step 2: Batch 4 — Sticky Card Monitoring & Alerts (2026-04-07)
- position_monitor.py: NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT alert generators
- MonitoringEvent model with type, symbol, direction, severity, reason, details
- monitoring_events field added to CustomPositionResponse (additive, defaults empty)
- Wired into _refresh_open_position: recomputes regime, news, flow, probabilities per refresh
- Stores previous_regime, previous_news_flag, original_p_hit baselines for shift detection
- GET /api/fno/position-alerts: Aggregated alerts across OPEN positions, sorted by severity
- Direction detection bug fixed (endsWith instead of contains for CE/PE)
- Tests: Iteration 34 — 33/33 pass (100%)

## Testing Status
- Iteration 31: 39/40 (Batches 1-3)
- Iteration 32: 20/20 (Universe)
- Iteration 33: 27/27 (Kite-first + MFE for indices)
- Iteration 34: 33/33 (Batch 4 - Monitoring & Alerts)

## Prioritized Backlog

### P0 — Next Up
- **Step 3**: Strategy backtest data for Bucket A (replace mock defaults with real DB stats)
- **Step 4**: Position sizing calculator + Budget entry trigger

### P1
- server.py refactoring → routes/ modules
- Streaming response for /fno/generate
- 52-week IV data for IV Rank
- Dynamic NIFTY 500 constituency parsing

### P2
- App.js componentization
