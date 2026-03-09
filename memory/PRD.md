# PRD — AI Stock Research: Multibagger & F&O

## Original Problem Statement
Build a simple ultra-minimal full-stack app (FastAPI + React) for:
- Multibagger stock candidates
- F&O contracts and signals
- Custom script signal lookup
With backend-only analysis logic and frontend display.

## User Choices / Updates
- No API keys available.
- Use reliable live market data sources with fallback strategy.
- No dummy option LTP.
- Option LTP should use exact underlying+expiry+strike+CE/PE with nearest-expiry fallback (and robust fallback handling when exact strike is unavailable).

## Architecture Decisions
- **Backend**: FastAPI with typed Pydantic response models.
- **Data source strategy**:
  - Primary: Moneycontrol live endpoints (`priceapi` + `mcapi`) for stocks/index and option-chain parsing.
  - Secondary fallback: RapidAPI helper support kept in one place for future key wiring.
- **Core helpers**:
  - `get_stock_core(symbol)` normalizes stock/index data into one schema.
  - `get_option_ltp(script)` fetches live option LTP through a unified resolver.
- **Domain data**:
  - Hardcoded F&O universe in `data/fno_contracts.py`.
  - Hardcoded 50+ multibagger universe in `data/symbols.py`.
- **Frontend**: Single-page dashboard with 2 views via tabs (no routing complexity).

## What Has Been Implemented
- Backend endpoints:
  - `GET /api/multibagger/candidates` (top 30 sorted by score)
  - `GET /api/fno/contracts`
  - `GET /api/fno/signal/{script}`
  - `GET /api/fno/signals/index`
- Multibagger scoring engine (0–100) using market cap, PE, price zone, EPS, and range-position heuristics.
- Live F&O signal engine with entry/SL/targets, risk-reward, direction, and confluence score.
- Option LTP resolver improved with:
  - nearest-expiry fallback
  - nearest-valid-strike fallback when exact strike has no tradable LTP
- Frontend dashboard:
  - Header + KPI cards
  - Multibagger table + min-score slider
  - Index F&O signal cards
  - Custom script checker with error handling
- Added `data-testid` attributes across interactive and key user-facing elements.

## Testing Status
- Backend regression tests: `5 passed` (`/app/backend/tests/test_market_endpoints.py`).
- API spot checks via curl:
  - multibagger list ✅
  - single signal NIFTY ✅
  - single signal BANKNIFTY ✅
  - index signals list ✅
- Frontend Playwright screenshots captured for:
  - initial load
  - tab switching
  - slider interaction
  - custom BANKNIFTY signal render

## Prioritized Backlog
### P0
- Add caching/rate-limit guard for external provider calls to reduce latency/spikes.
- Add structured provider health/error telemetry endpoint for observability.

### P1
- Add server-side pagination/sorting controls for multibagger table.
- Add richer signal explanation blocks (why bullish/bearish/neutral).

### P2
- Add watchlist persistence and historical signal snapshots.
- Add downloadable CSV export for screened candidates/signals.

## Next Tasks
1. Introduce async caching layer (TTL) for `get_stock_core` and option-chain pages.
2. Add backend diagnostics metadata (provider used, fallback level) to responses.
3. Add table sort controls and lightweight skeleton loaders in frontend.
