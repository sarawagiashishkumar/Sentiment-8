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
9. **Strategy Backtests**: Real backtest stats gate Bucket A. Enable only if trade_count>=100, win_rate>=0.75, expectancy_R>=0.40.
10. **Position Sizing**: Risk-based sizing with not_affordable annotation. Does NOT block signals.

## Architecture
```
/app/backend/
  server.py                  (~8400 lines)
  services/
    indicators.py            — ATR, RSI, MACD, eligibility (4 filters incl NCLT)
    research_engine.py       — Re-exports all service modules
    strategy_library.py      — 13 strategy definitions
    technical_core.py        — Full tech snapshot
    macro_engine.py          — Macro context, regime
    forensic_engine.py       — Piotroski, Altman, Beneish
    holiday_manager.py       — NSE holiday management
    market_data.py           — Kite/yfinance data fetching
    data_verifier.py         — Parallel verification
    index_constituents.py    — NIFTY 50/BANKNIFTY weights, weighted breadth
    intraday_features.py     — Multi-TF EMAs, VWAP, order flow, regime
    options_features.py      — OI buildup, IV rank, bid-ask, depth
    news_sentiment.py        — RSS feeds, VADER scoring, NewsFlag
    mfe_mae_engine.py        — MFE/MAE library, probability tables, theta, best exit
    confluence_score_v2.py   — 4-bucket scoring (A+B+C+D), threshold=78
    fo_universe.py           — Full NSE F&O universe (158 stocks)
    position_monitor.py      — NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT alerts
    backtest_engine.py       — Strategy backtest simulators + batch job + DB reader
    position_sizing.py       — Risk-based position sizing + budget gate
  models/__init__.py         — Pydantic models (MonitoringEvent, sizing fields)
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
- MFE/MAE enabled for ALL underlyings

### Step 2: Batch 4 — Sticky Card Monitoring & Alerts (2026-04-07)
- position_monitor.py: NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT alert generators
- MonitoringEvent model, monitoring_events on CustomPositionResponse
- GET /api/fno/position-alerts endpoint
- Direction detection fix (endsWith)
- Tests: Iteration 34 — 33/33 pass

### Section 2: URGENT_EXIT Wording Fix (2026-04-08)
- Centralized build_urgent_exit_reason() — no imperative verbs
- Renamed recommended_exit_price → expected_best_price_next_60s
- Flow band described neutrally in reason text
- Tests: Iteration 35 — 32/32 pass

### Step 3: strategy_backtests Population (2026-04-08)
- backtest_engine.py: 5 trading simulators (ORB, VWAP, Supertrend, MACD, RSI)
- yfinance 12-month OHLCV fetcher (with MultiIndex fix)
- Batch job: POST /api/fno/backtest-batch (61 strategy×instrument combos)
- DB reader: fetch_strategy_backtest() for Bucket A
- Strict enable threshold: trade_count>=100 AND win_rate>=0.75 AND expectancy_R>=0.40
- Feature flag: USE_BACKTEST_DB (default "0" = fallback, "1" = strict)
- GET /api/fno/strategy-backtests endpoint
- Wired into Bucket A of confluence_score_v2.py
- Tests: Iteration 35 — 32/32 pass

### Step 4: Position Sizing + Budget Gate (2026-04-08)
- position_sizing.py: compute_position_size (lots_allowed, capital_required, risk_amount)
- annotate_signal_affordability for F&O signals
- not_affordable + sizing_info fields on FNOSignalResponse
- POST /api/fno/position-sizing endpoint
- Tests: Iteration 35 — 32/32 pass

## Testing Status
- Iteration 31: 39/40 (Batches 1-3)
- Iteration 32: 20/20 (Universe)
- Iteration 33: 27/27 (Kite-first + MFE for indices)
- Iteration 34: 33/33 (Batch 4 - Monitoring & Alerts)
- Iteration 35: 32/32 (Sections 2-4: Wording, Backtests, Sizing)

## Prioritized Backlog

### P0 — Done
- All P0 items completed: Monitoring, Backtests, Sizing

### P1
- server.py refactoring → routes/ modules (~8400 lines)
- Streaming response for /fno/generate
- 52-week IV data for IV Rank
- Dynamic NIFTY 500 constituency parsing

### P2
- App.js componentization (~3000 lines)
- Budget Entry Trigger Alert (monitor live LTP, alert when pullback zone hit)
