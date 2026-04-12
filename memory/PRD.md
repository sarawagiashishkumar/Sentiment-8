# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets.

## Architecture
- Backend: FastAPI (Python), Frontend: React + Shadcn UI, DB: MongoDB, Data: Kite Connect API v3

## Latest: Phase 36 — Type Hints & Security Review (2026-04-13)
- **models/__init__.py**: Fully type-hinted all 30+ Pydantic models. `dict` → `dict[str, Any]`, `List[str]` → `list[str]`, `model_validator` moved to module-level import, NaN sanitizer field set extracted to module constant. MeResponse/AdminUserView extended with `package`, `suspended` fields.
- **Security Review**: Replaced dangerous `exec_module(server)` in `test_structured_changes_portfolio_fno.py` with safe `read_backend_source()` source-file inspection. Verified `importlib.import_module` (module existence checks) and `subprocess.run(["tail",...])` (read-only log access) patterns are benign.
- **Restored /fno/scripts/search**: Endpoint accidentally lost during Phase 31 fno.py split — restored at line 585.
- Test: iteration 90 — 17/17 backend, 100% frontend.

## Phase 35: P0/P1 Feature Sprint (2026-04-13)
- News & Sentiment engine, QR upload + Razorpay toggle, Custom API CRUD, Price Band verification

## Phase 34: Bug Fixes (2026-04-12)
- Heartbeat, AI markdown, LiveHelp UI, badge contrast, heatmap neutral

## Phase 31-33: Component splitting, Superadmin CRUD, Clean Desk (2026-04-12)

## Navigation: 9 main tabs, 10 admin sub-tabs, 6 F&O sub-tabs

## Code Quality — COMPLETE
All items from the original Code Quality Report are now resolved:
- Circular imports, Auth/Alert/CRM complexity, component splitting, route extraction
- Type hints (app_state.py, models/__init__.py), security review, dynamic import audit
- No remaining backlog items from the original report

## Remaining Backlog
- P3: Multi-currency payment support
- P3: Advanced analytics dashboard with usage graphs
