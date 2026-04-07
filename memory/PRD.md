# PRD — Trading Signal Platform

## Original Problem Statement
Full-stack web app for stock analysis (FastAPI, React, MongoDB). Core features: F&O Trading Signals, Multibagger Screener, Portfolio Analysis.

## Core Requirements
1. **Global architecture**: ALL calculations in backend Python. NO LLM numeric work.
2. **Data source**: Kite Connect is the ONLY production OHLCV source. yfinance disabled by default (USE_YFINANCE=false).
3. **Mandatory Filtering**: LTP >= 50. Not NCLT/DRT. Debt < 30% mcap. Profit positive.
4. **Time/Expiry**: 09:15-15:30 IST strict.
5. **Confluence Score V2**: 4-Bucket system (A: Strategy, B: Direction, C: Options/Flow, D: Trade Quality). Threshold >= 78.
6. **Dynamic Targets**: Probability-based T1/T2 using MFE/MAE + Theta decay.
7. **Alerts & Monitoring**: NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT events (risk-focused, no imperative verbs).
8. **Strategy Backtests**: Real backtest stats gate Bucket A. Enable only if trade_count>=100, win_rate>=0.75, expectancy_R>=0.40.
9. **Position Sizing**: Risk-based sizing with not_affordable annotation.
10. **CSV Seed Fallback**: Verified offline OHLCV data for when Kite is unavailable.

## Architecture
```
/app/backend/
  server.py                  (~8500 lines)
  services/
    backtest_engine.py       — Kite OHLCV primary + CSV seed fallback (NO yfinance)
    position_monitor.py      — NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT alerts
    position_sizing.py       — Risk-based position sizing + budget gate
    confluence_score_v2.py   — 4-bucket scoring (A+B+C+D), threshold=78
    fo_universe.py           — Full NSE F&O universe (158 stocks)
    mfe_mae_engine.py        — MFE/MAE library, probability tables, theta, best exit
    intraday_features.py     — Multi-TF EMAs, VWAP, order flow, regime
    options_features.py      — OI buildup, IV rank, bid-ask, depth
    news_sentiment.py        — RSS feeds, VADER scoring, NewsFlag
    data_verifier.py         — Parallel verification (yfinance guarded)
    sector_momentum.py       — Sector analysis (yfinance guarded)
    [other services...]
  models/__init__.py         — Pydantic models
/app/data/ohlcv_seeds/       — Verified CSV seed files for offline OHLCV
```

## Data Source Policy
- **Primary**: Kite Connect Historical Data API (`get_ohlcv_from_kite`)
- **Fallback**: Verified CSV seed files (`get_ohlcv_from_csv_seed`)
- **DISABLED**: yfinance (USE_YFINANCE=false by default in all modules)
- **Admin Panel**: CSV seed upload/delete via /api/admin/csv-seeds endpoints

## Completed Work

### Phase 1-2 (Earlier Sessions)
- F&O Signal Engine, Multibagger Screener, Portfolio Analysis
- Pullback entry, lot size fix, export enhancements

### Phase 3 — Batches 1-3 (2026-04-07)
- Feature & data layer, MFE/MAE backtests, 4-Bucket Confluence Score V2

### Mini-Batch + Step 1 (2026-04-07)
- F&O Universe expanded to 158 stocks, Kite Connect primary

### Step 2: Batch 4 — Monitoring & Alerts (2026-04-07)
- position_monitor.py wired into _refresh_open_position
- MonitoringEvent model, GET /api/fno/position-alerts endpoint

### Section 2: URGENT_EXIT Wording Fix (2026-04-08)
- build_urgent_exit_reason(): no imperative verbs
- expected_best_price_next_60s replaces recommended_exit_price

### Step 3: strategy_backtests (2026-04-08)
- 5 trade simulators, batch job, Bucket A wiring
- Feature flag USE_BACKTEST_DB (default "0" = fallback)

### Step 4: Position Sizing (2026-04-08)
- compute_position_size, not_affordable annotation on signals

### HOTFIX: yfinance Removal (2026-04-08)
- backtest_engine.py rewritten: Kite → CSV seed → skip (zero yfinance)
- USE_YFINANCE=false default across server.py, data_verifier.py, sector_momentum.py
- CSV seed admin panel in frontend (upload, list, delete)
- GET/POST/DELETE /api/admin/csv-seeds endpoints
- Tests: Iteration 36 — 21/21 backend + 10/10 frontend pass

## Testing Status
- Iteration 34: 33/33 (Batch 4 Monitoring)
- Iteration 35: 32/32 (Sections 2-4)
- Iteration 36: 21/21 backend + 10/10 frontend (yfinance HOTFIX)
- Iteration 37: 23/23 backend + 13/13 frontend (Route Extraction Regression)

## Prioritized Backlog

### P1
- Extract remaining routes: market_data.py, portfolio.py, multibagger.py
- Streaming response for /fno/generate (prevent 504 gateway timeouts)
- 52-week IV data for IV Rank

### P2
- App.js componentization (~3000 lines)
- Budget Entry Trigger Alert

## Route Extraction Status (2026-04-08)
- `routes/fno.py` — DONE (11 endpoints + 3 backward-compat)
- `routes/admin.py` — DONE (22 endpoints)
- `deps.py` — DONE (shared auth dependencies)
- server.py reduced from ~8450 → ~7277 lines
