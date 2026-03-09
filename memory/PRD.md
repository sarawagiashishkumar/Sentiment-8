# PRD — Trading Dashboard Upgrades & Conflict Resolution

## Original Request (Latest)
Upgrade the trading platform to include:
- Landing dashboard with two modules: Multibagger and F&O Projections
- Unified aesthetics aligned with login page + persistent navigation
- Username-based auth (no public registration), admin/sub-admin/basic RBAC
- Owner full CRUD, sub-admin limited user creation quota
- Admin exemption from credit billing
- F&O conflict logic fixes (directional vs non-directional), strike filter ±500
- Consolidated/without-consolidated analysis reports
- Custom script “Script not supported” issue fix
- Bottom stock F&O opportunities panel
- Multibagger table with RSI, GTT Buy, duration targets and ROI
- Top 4 Best Trade sticky panel and SEBI educational disclaimer

## Key User Choices Applied
- Owner username: `@shish123`
- Multibagger projections: model-based live projections enabled
- Sub-admin quota policy: fixed quota (default 10), editable by Owner

## Architecture Decisions
- Keep existing reliable live market ingestion in backend (`market_data.py`) intact.
- Keep stack lightweight: FastAPI + MongoDB + in-memory sessions.
- Introduced username-credential auth while preserving minimal legacy compatibility in API payload.
- Modularized F&O generation into index projections + conflict resolver + stock opportunity generator.

## Implemented Backend
### Auth / RBAC / Admin
- `POST /api/auth/access` (username login only for existing users; no public registration)
- `GET /api/auth/me`, `POST /api/auth/logout`
- Roles: `owner`, `sub_admin`, `user`
- Admin CRUD:
  - `GET /api/admin/users`
  - `POST /api/admin/users`
  - `PATCH /api/admin/users/{user_ref}/credits`
  - `PATCH /api/admin/users/{user_ref}/quota` (Owner only)
  - `DELETE /api/admin/users/{user_ref}`
- Sub-admin quota enforcement implemented.
- Owner/sub-admin credit exemption implemented.

### Multibagger
- On-demand endpoint: `POST /api/multibagger/generate` (cost 1 for basic user; 0 for exempt roles)
- Output includes:
  - Stock + sector
  - RSI proxy
  - GTT buy price
  - Targeted upside prices for 1W/1M/3M/6M/9M/1Y
  - Matching ROI (%) row data

### F&O Projections
- On-demand endpoint: `POST /api/fno/generate` (cost 2 for basic user; 0 for exempt roles)
- Dual index projections:
  - `nifty_projection` and `banknifty_projection`
  - Spot shown in headers
  - Strike filter hard-bounded within ±500 points
- Conflict resolution:
  - CE+PE profitable on same strike => moved to `non_directional_strategies` as straddle classification
  - Directional assured signals kept separate
- Reports:
  - `with_consolidated_report` (weighted constituent analysis)
  - `without_consolidated_report` (equal constituent analysis)
- Custom script support improved with dynamic parser (`/api/fno/signal/{script}` + generate custom input)
- Added script search endpoint: `GET /api/fno/scripts/search`
- Added stock opportunity panel signals (`RELIANCE`, `BDL`, `SBIN`, `TCS`)

### Compatibility Endpoints Retained
- `GET /api/multibagger/candidates`
- `GET /api/fno/contracts`
- `GET /api/fno/signal/{script}`
- `GET /api/fno/signals/index`
- `GET /api/fno/signals/potential`

## Implemented Frontend
- New dark/cyan aesthetic across login + internal screens (style unified)
- Persistent nav: Home / Multibagger / F&O Projections / Admin
- Home landing dashboard with two module cards (center-left and center-right)
- Username login page with registration-disabled messaging
- Multibagger page:
  - Empty state until button click
  - Generate button + slider + 2-row per stock projection table
- F&O page:
  - Empty state until button click
  - Dual pane NIFTY/BANKNIFTY with spot, assured + non-directional sections, reports
  - Full-width stock signals bottom panel
  - Sticky “Top 4 Best Trade Now” panel
  - Custom script projection runner
- Admin page:
  - User creation, role assignment, credit updates, quota updates, deletion controls
  - Credential display as `username as role`
- SEBI personal testing educational disclaimer shown prominently.

## Testing & Validation
- Backend test suite updated and passed: **21/21** (`pytest -q /app/backend/tests`)
- Playwright UI flows validated:
  - Login, landing modules, multibagger generation, F&O generation, admin panel
- Testing agent iteration completed with no blocking functional defects.

## Prioritized Backlog
### P0
- Persist session store with TTL backend (Redis) for stronger reliability across restarts.
- Add unique DB index on `username` with migration cleanup for historical legacy rows.

### P1
- Add pagination/virtualization for very large signal tables.
- Add explicit “strategy invalidators” section on each signal card.

### P2
- Add audit log timeline for user CRUD and credit changes.
- Add export/download for multibagger and F&O projection snapshots.

## Next Tasks
1. DB hardening: unique username index + migration script.
2. Session hardening: persistent token store with expiry.
3. Signal explainability enhancement (invalidators + concise rationale cards).
