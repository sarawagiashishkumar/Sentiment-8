# PRD — Final Trading Dashboard (Structured Upgrade)

## Latest User Request Implemented
A) Global text/hover visibility rules with separate heading/result color roles.
B) Expanded dynamic “Profitable F&O Signals – Individual Stocks” universe (not hard-capped).
C) New Portfolio Analysis module with:
- File upload (.txt/.csv/.xls/.xlsx/.pdf/.jpg/.jpeg/.bmp)
- Manual dynamic row entry (+/- rows)
- Deep per-stock analysis output with horizons and recommendation/comments.

## What Was Built
### 1) Text & Hover Visibility (Global)
- Added distinct text roles:
  - `headingTextColor` (fixed headings/labels)
  - `resultTextColor` (dynamic values/numbers/scores)
- Applied safe contrast rules across Multibagger, F&O, Portfolio, Admin.
- Added explicit hover-safe text color for result rows/cards/tables to avoid invisible text.

### 2) F&O Individual Stock Signals (Expanded & Dynamic)
- Extended stock F&O universe to liquid names (10–20 set).
- Stock-only opportunities now use the same confluence/risk/expiry-aware filters.
- UI renders all qualifying stock signals returned by backend (no forced limit to 3).

### 3) Portfolio Analysis
#### Backend
- `POST /api/portfolio/analyze`
  - Manual JSON input: `positions[{symbol, avg_price, quantity}]`
- `POST /api/portfolio/analyze-upload`
  - Upload parser for txt/csv/xls/xlsx/pdf/jpg/jpeg/bmp
  - Flexible header alias detection for symbol/avg price/quantity
  - OCR/PDF text heuristic extraction support where parser data is available
- Deep per-stock output includes:
  - live/fundamental fields
  - position metrics (`pnl_pct`, `allocation_pct`)
  - `value_flag`, `price_zone`, `momentum_proxy`, `quality_proxy`
  - `expected_ranges` for 1W/1M/3M/6M/9M/1Y with GREEN/RED flags
  - `recommendation`, `comments`

#### Frontend
- New Portfolio page in persistent navigation and landing module.
- Left: upload flow.
- Right: manual dynamic table with + / - row controls and submit.
- Results render per-stock cards + mini horizon table + recommendation/comments.

## Existing Capabilities Preserved
- Username login with RBAC (owner/sub_admin/user)
- Owner CRUD + sub-admin quotas
- Admin credit exemption
- Expiry-aware F&O logic and custom sticky projections in MongoDB
- Top 4 Best Trade sticky panel
- SEBI educational/personal testing disclaimers

## Validation Status
- Regression via testing agent iteration_7: PASS
- Backend tests executed by testing agent: 15 passed for requested scope
- Frontend browser automation validated:
  - F&O generate (dual panes + top4 + stock cards)
  - Portfolio upload/manual flows
  - hover contrast visibility
- No API flow mocked

## Next Tasks (P0/P1/P2)
### P0
- Add robust OCR fallback package detection messaging for unsupported image/PDF environments.
- Add file-level parse diagnostics (which rows parsed/skipped).

### P1
- Add downloadable portfolio analysis report (CSV/PDF).
- Add per-horizon confidence score visualization.

### P2
- Split large `server.py` into modules (`auth`, `fno`, `portfolio`, `admin`, `parsers`) for maintainability.
