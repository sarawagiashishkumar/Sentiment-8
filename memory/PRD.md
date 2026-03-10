# PRD — Final Trading Dashboard (Contrast + Expiry-Aware F&O + Sticky Custom Projections)

## What was upgraded in this iteration
1. **Global contrast/hover fix across all result areas**
   - Applied high-contrast text and hover inversion (light background + dark text) across Multibagger, F&O, Top-4, and Admin result components.
   - Added consistent result styling classes and hover-safe behavior.

2. **Expiry-aware and realistic F&O logic**
   - Added IST-based expiry-time logic (`15:30 IST`) and `minutes_to_expiry` computation.
   - Added hard guards:
     - expired contracts blocked
     - <=15 min to expiry blocked for safe projections
   - Added confidence downgrades when expiry is near.
   - Added response fields: `minutes_to_expiry`, `expiry_risk`.

3. **Sticky live custom projections (MongoDB per user)**
   - Added persistent custom positions endpoints:
     - `POST /api/fno/custom-position`
     - `GET /api/fno/custom-positions`
     - `POST /api/fno/custom-position/{id}/close`
   - Stored per logged-in user in MongoDB and refreshed in polling loop.
   - Added urgent alert conditions and revised exit-plan updates.
   - Frontend now renders sticky custom cards under custom input, above index projections.

## Existing major platform capabilities retained
- Username-based secure access with Owner/Sub-Admin/Basic User RBAC.
- Owner full CRUD + Sub-Admin quota controls.
- Admin exemption from credit billing.
- Multibagger button-driven generation only.
- F&O Projections dual-pane (NIFTY/BANKNIFTY), conflict separation for non-directional strategy.
- Top 4 Best Trade sticky panel.
- Personal testing + SEBI educational disclaimer.

## Testing status
- Backend regression tests: **25/25 passed**.
- Frontend sanity verified via screenshot automation for login, multibagger, F&O projections, custom sticky card, hover contrast.

## Rebuild Prompt Template (copy-paste)
"""
Build a full-stack trading dashboard using React + FastAPI + MongoDB with:

1) Secure username-only login (no public registration), RBAC roles: owner/sub_admin/user.
2) Owner full CRUD of users, sub-admin quota-based user creation, admin credit exemption.
3) Credit model for basic users: multibagger generation cost 1, F&O generation cost 2.
4) Landing dashboard with two primary modules: Multibagger and F&O Projections.
5) Persistent navigation across Home, Multibagger, F&O Projections, Admin.
6) Multibagger generation on button click only; no preloaded results.
7) Multibagger table must include:
   - Stock name, sector
   - RSI level
   - GTT buy price
   - Targeted upside prices for 1W/1M/3M/6M/9M/1Y
   - Corresponding % profit row for each duration.
8) F&O Projections generation on button click only; no preloaded results.
9) F&O dual-pane layout: NIFTY left, BANKNIFTY right with live spot headers.
10) Strike filter for projection candidates: within ±500 points of current spot.
11) Conflict rule: If same strike CE and PE both qualify, classify as non-directional strategy (straddle), not directional assured signals.
12) Provide two reports per index: with consolidated analysis and without consolidated analysis.
13) Add a full-width bottom panel for profitable individual stock F&O projections.
14) Add sticky Top 4 Best Trade panel with entry/SL/targets/confidence rationale.
15) Add custom sticky positions system (persist in MongoDB):
    - create custom position with script + buy price
    - list active positions with live updates every 5s
    - close position manually
    - include urgent red alert conditions.
16) Make F&O logic expiry-aware:
    - expiry date + expiry time IST
    - compute minutes_to_expiry
    - block expired and <=15 min cases
    - downgrade confidence near expiry.
17) Add strong UI contrast rules globally:
    - result text visible on dark background
    - hover state switches to light background + dark text.
18) Include personal testing + SEBI educational disclaimer on login and dashboard.
19) Keep all core market data fetchers centralized and reusable.
20) Include data-testid attributes for all interactive and critical display elements.
"""

## Next tasks
- Add unique username DB index migration + cleanup legacy rows.
- Add session TTL persistence (Redis) for hardening.
- Add richer invalidator cards for each custom projection.
