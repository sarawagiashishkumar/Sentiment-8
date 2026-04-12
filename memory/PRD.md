# PRD — Trading Signals & F&O Platform (Master Spec v2.0)

## Core Product
AI-driven trading research platform for NSE F&O markets.

## Architecture
- Backend: FastAPI (Python), Frontend: React + Shadcn UI, DB: MongoDB, Data: Kite Connect API v3

## Latest: Phase 35 — P0/P1 Feature Sprint (2026-04-13)
### News & Sentiment Engine (P0)
- `GET /api/news/forecast` — Pre/post-market forecast for NIFTY, BANKNIFTY, top 10 F&O stocks. Combines RSS sentiment (VADER) with technical context (RSI, trend, regime) from equity_master_cache
- `GET /api/news/market-summary` — Market-wide bullish/bearish/neutral counts
- `GET /api/news/symbol/{symbol}` — Per-symbol headlines and sentiment
- NewsSentimentPanel on Home Dashboard showing index forecasts, stock sentiments, symbol search
- Background monitor runs every 120s refreshing RSS cache

### QR Upload + Razorpay Toggle (P1)
- Payment config: `razorpay_enabled`, `offline_enabled` toggles + `qr_image_base64` upload
- `GET /payments/qr-image` returns uploaded QR
- Admin Payments: Checkboxes for online/offline mode, file upload for custom QR, status shows all toggles

### Custom API Endpoints CRUD (P1)
- `POST/GET/DELETE /admin/custom-apis` — Full CRUD for custom API endpoints
- `POST /admin/custom-apis/{name}/test` — Test any custom API from admin panel
- Admin Advanced Controls: "Add API" button, inline form, list with test/delete buttons

### Price Band Engine (Pre-existing, Verified)
- `equity_master_cache.py`: 524 lines, full schema per user spec
- `price_band_engine.py`: 289 lines, 6 horizons (1W/1M/3M/6M/9M/12M), 3 scenarios, regime multipliers, fundamental scalar
- Already integrated into multibagger_engine and portfolio_engine

### Phase 34: Bug Fixes (2026-04-12)
- Heartbeat: 30s ping, 30min buffer. Tab changes = activity
- AI markdown cleanup. LiveHelp single mic + voice toggle
- Multibagger badge contrast. Heatmap neutral gray

### Phase 33: Clean Desk + 7 Items (2026-04-12)
### Phase 32: Superadmin CRUD (2026-04-12)
### Phase 31: Component Splitting (2026-04-12)

## Navigation: 9 main tabs, 10 admin sub-tabs, 6 F&O sub-tabs

## Remaining Backlog
- P2: Type hints on models/__init__.py
- P2: Security review of dynamic imports in test files
- P3: Multi-currency payment support
- P3: Advanced analytics dashboard with usage graphs
