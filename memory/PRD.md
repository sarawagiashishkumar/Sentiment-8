# PRD — AI Stock Research Platform (Password + Credits + Admin)

## Original + Expanded Scope
Started as a lightweight stock research dashboard (Multibagger + F&O). Expanded to include:
- Landing page with password-only access
- Credit-based usage model
- Admin full CRUD for user credit control
- On-demand live generation only (no auto-population)
- SEBI-aligned educational disclaimer
- Top 4 Best Trade Now sticky panel

## User Requirements Implemented
1. **Page flow inspired by reference app** (simple landing + clear dashboard tabs).
2. **Conflict-free tab/action flow**: each section has its own generate action; no mixed-context trigger confusion.
3. **Password-based authentication (no username)**:
   - Password min 6 chars, letters+numbers only.
   - Same password maps to same user account.
4. **Credit economy**:
   - Multibagger generation = 1 credit
   - F&O generation = 2 credits
   - Proper insufficient-credit error handling.
5. **Admin owner rights (CRUD)**:
   - List users
   - Create users
   - Update user credits
   - Delete users (non-admin)
6. **Data generation behavior**:
   - Multibagger and F&O remain empty until user clicks generate.
   - Live analytics run at click time.
7. **Top 4 Best Trade Now** sticky panel with entry/SL/targets/confidence rationale.
8. **SEBI educational disclaimer + personal testing notice** on landing and dashboard.

## Architecture Decisions
- FastAPI + MongoDB retained for lightweight backend.
- In-memory session token store (simple, fast) with bearer auth.
- Live market data stack in `services/market_data.py` preserved intact.
- Added new generation endpoints while keeping legacy read endpoints for compatibility.

## Backend: Implemented APIs
### Auth
- `POST /api/auth/access`
- `GET /api/auth/me`
- `POST /api/auth/logout`

### Credit-charged generation
- `POST /api/multibagger/generate` (cost 1)
- `POST /api/fno/generate` (cost 2, optional custom script)

### Admin CRUD
- `GET /api/admin/users`
- `POST /api/admin/users`
- `PATCH /api/admin/users/{user_key}/credits`
- `DELETE /api/admin/users/{user_key}`

### Existing compatibility endpoints preserved
- `GET /api/multibagger/candidates`
- `GET /api/fno/contracts`
- `GET /api/fno/signal/{script}`
- `GET /api/fno/signals/index`
- `GET /api/fno/signals/potential`

## Frontend: Implemented Flows
- **Landing (protected)**: password input + disclaimer
- **Dashboard tabs**:
  - Multibagger Finder (button-driven generation)
  - F&O Signals (button-driven generation + custom script)
  - Admin Credits (admin-only CRUD panel)
- **Top 4 Best Trade Now** sticky panel in F&O view
- Credits summary + role + user key
- Compliance disclaimer in dashboard footer

## Testing & Validation
- Direct API validation with curl:
  - auth/session ✅
  - credit deduction ✅
  - insufficient credits ✅
  - admin CRUD ✅
  - generation endpoints ✅
- Playwright screenshots:
  - landing gate ✅
  - dashboard and tabs ✅
  - generated potential signals + top4 panel ✅
  - admin CRUD UI ✅
- Testing agent cycle complete:
  - `iteration_3.json`
  - pytest total: **14/14 passed**

## Prioritized Backlog
### P0
- Replace default admin fallback password with explicit secure runtime secret only.
- Move in-memory sessions to persistent TTL-backed store for stronger reliability.

### P1
- Add cooldown/debounce and tiny TTL cache for faster repeated generation clicks.
- Add explicit invalidators and richer rationale block per top trade.

### P2
- Add auditable credit transaction log (who consumed/got granted when).
- Add export/report for generated multibagger and F&O sessions.

## Next Tasks
1. Security hardening of admin bootstrap & session persistence.
2. Credit transaction history endpoint + UI.
3. Optional analytics explainability panel expansion.
