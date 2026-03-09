# PRD — AI Stock Research: Multibagger & F&O

## Original Problem Statement
Build a minimalist full-stack stock research app (FastAPI + React) for:
- Multibagger discovery
- F&O contract signals
- Custom script signal lookup
using live market data.

## User Choices / Latest Requests
- Keep reliable live data API intact (no dummy option LTP).
- Add one-click refresh UX:
  - **GET NEW MULTIBAGGERS**
  - **GET NEW SIGNALS**
- Improve signal quality to avoid weak neutral cards and surface potential profitable trades.
- Keep implementation lightweight, fast, and low-complexity infra.

## Architecture Decisions
- Backend remains FastAPI with in-memory lightweight processing (no heavy infra dependencies added).
- Live data flow preserved via existing reliable providers in `services/market_data.py`.
- Refresh is implemented via explicit `refresh_nonce` query params + fresh recomputation on demand.
- Added dedicated potential signals endpoint for trade-focused cards.

## Implemented (Current)
- **Backend APIs**
  - `GET /api/multibagger/candidates?refresh_nonce=...`
  - `GET /api/fno/signal/{script}?refresh_nonce=...`
  - `GET /api/fno/signals/index?refresh_nonce=...`
  - `GET /api/fno/signals/potential?refresh_nonce=...` (new)
- **Multibagger engine upgrades**
  - Tier-style analytics proxy logic, tier pass count, PB/PEG estimates, potential flag.
  - Candidate response now includes `tier_pass_count`, `is_potential_multibagger`, `analysis_refreshed_at`.
- **F&O signal engine upgrades**
  - Stronger live confluence/bias model to reduce low-quality neutral outputs.
  - Added `signal_quality`, `is_potential_trade`, `trigger_factors`, `analysis_refreshed_at`.
  - Potential endpoint returns high-conviction opportunities first.
- **Frontend UX upgrades**
  - Prominent buttons: **GET NEW MULTIBAGGERS** and **GET NEW SIGNALS**.
  - Refresh timestamps displayed in summary cards.
  - F&O section now focused on **Potential Profitable Trade Signals**.
  - Multibagger table now shows tier pass and potential tags.
  - Custom script lookup still supported with fresh live refresh.

## Validation / Testing
- API smoke tests via curl: passed for all updated endpoints.
- Pytest regression: **8 passed** (`/app/backend/tests/test_market_endpoints.py`).
- Browser automation checks: refresh buttons, tab flow, potential signal cards, custom script flow all verified.

## Prioritized Backlog
### P0
- Add short TTL in-memory caching + stale-while-refresh for faster repeated refresh bursts.
- Add structured fallback diagnostics in responses (provider and fallback level used).

### P1
- Add “Best Trade” ranking panel with top-1 rationale and invalidation conditions.
- Add richer multibagger explanation columns (which tiers failed/passed).

### P2
- Optional async worker scheduling for periodic snapshots (lightweight cron/apscheduler).
- Historical signal tracking and downloadable reports.

## Next Tasks
1. Introduce lightweight request-throttled cache for frequent refresh clicks.
2. Expose per-signal invalidators and confidence explanations in UI.
3. Add compact homepage route with CTA navigation to dashboard (if requested).
