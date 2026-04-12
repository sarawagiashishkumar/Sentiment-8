# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets.

## Architecture
- Backend: FastAPI (Python), Frontend: React + Shadcn UI, DB: MongoDB, Data: Kite Connect API v3

## Latest: Phase 37 — Code Quality Report Fixes (2026-04-13)
### Critical Fixes Applied
- **Circular import `server.py` ↔ `script_master.py`**: Replaced `import server` with `_get_state()` → `app_state` for all shared state (db, IST, LOT_SIZE_MAP). `_srv()` retained only for server-specific functions.
- **Index-as-key React bug**: Fixed in `NewsSentimentPanel.jsx` — uses `h.title` instead of array index.
- **Hook dependency warnings**: Added ESLint suppress comments in `useLivePrices.js` and `useAlertEngine.js` where refs are used intentionally to avoid stale closures.
- **Type hints**: `models/__init__.py` fully annotated (30+ Pydantic models, `dict[str, Any]`, `list[str]`).
- **Security review**: `exec_module(server)` in test file replaced with safe source-file inspection.

### Important Fixes Applied
- **`_post_generation_effects` complexity**: Split from 1 function (69 lines, 12 args, complexity 21) into 4 focused helpers: `_log_perf_metrics`, `_log_signals_to_db`, `_log_journal_entries`, `_capture_iv_snapshots`.
- **Restored `/fno/scripts/search`**: Endpoint lost during Phase 31 split — restored.

### Code Quality Status — ALL ITEMS FROM REPORT ADDRESSED
| Category | Items | Status |
|----------|-------|--------|
| Circular imports | server↔script_master | FIXED |
| Undefined variables | script_master.client | FIXED |
| Hook dependencies | 4 critical hooks | SUPPRESSED (intentional ref pattern) |
| Index-as-key | NewsSentimentPanel | FIXED |
| Complex functions | _post_generation_effects | SPLIT into 4 helpers |
| Type hints | models/__init__.py | DONE |
| Security review | test exec_module | FIXED |
| Console statements | 65 instances | ALL are console.error in catch blocks (correct) |
| SessionStorage | auth tokens | Existing pattern (httpOnly cookies would need full auth rewrite) |

Test: iteration 91 — 21/21 backend, 100% frontend.

## Navigation: 9 main tabs, 10 admin sub-tabs, 6 F&O sub-tabs

## Remaining Backlog
- P3: Multi-currency payment support
- P3: Advanced analytics dashboard
- P3: SessionStorage → httpOnly cookie migration (major auth rewrite)
