# ROADMAP — Trading Signals & F&O Platform

## Active Sprint (Next)
- [ ] P1: Isolate live data fetching logic — ensure WebSocket/API calls don't block UI rendering
- [ ] P1: Plan Comparison Page — user-facing tier comparison for upsell (Free→Basic→Pro)
- [ ] P2: admin.py complexity reduction (admin_map_domain, get_user_permissions into service layer)
- [ ] P2: Type hints on public APIs (models/__init__.py, services/app_state.py first)

## Backlog
- [ ] P2: Security review of dynamic imports in test files
- [ ] P3: Payment history accumulation (track all Razorpay/offline payments over time)
- [ ] P3: Fraud incidents accumulation tracking (historical fraud dashboard)

## Code Quality Debt
| File | Lines | Issue | Priority |
|------|-------|-------|----------|
| admin.py | 1317 | admin_map_domain, get_user_permissions complexity | P2 |
| models/__init__.py | ~large | 0% type hint coverage | P2 |
| services/app_state.py | ~100 | 0% type hint coverage | P2 |
| tests/*.py | many | Dynamic imports in some test files | P2 |

## Completed (Latest)
- [x] Phase 32: Superadmin CRUD, Dynamic Plans, Global Fees
- [x] Phase 31: FNODashboard/OptionsHeatmap/fno.py splits
- [x] Phase 28-30: Code Quality Round 1+2
- [x] Phase 27: Voice AI Support Agent
- [x] Phase 22-26: Razorpay, WebRTC, Senior Audits, Mobile, Permissions
- [x] Phase 19-21: Charts, Reports, Watchlist, Backtester, Alerts, CRM, Fraud
- [x] Phase 1-18: All core features
