# PRD — Trading Research Dashboard

## Original Problem Statement
Build a minimalist full-stack stock analysis web app using FastAPI (Python) backend, React + Vite frontend, and MongoDB. The app provides F&O signal generation, portfolio analysis, multibagger screening, custom position tracking, and admin management.

## Tech Stack
- **Frontend:** React, Tailwind CSS, Shadcn/UI components
- **Backend:** FastAPI (Python), MongoDB (Motor async driver)
- **Auth:** JWT-based sessions with RBAC (owner/sub_admin/user)
- **Data:** Kite Connect API v3 for live market data, yfinance for fundamental data
- **Deployed:** Kubernetes container, supervisor-managed

## Core User Personas
- **Owner/Trader:** Technical Indian equity trader tracking F&O positions, screening multibaggers, analyzing portfolio
- **Admin:** Manages user access, credits, Kite API connection

---

## What's Been Implemented (as of Mar 2026)

### Authentication & RBAC
- Username-only login (no password), JWT sessions in memory
- Owner/sub_admin/user role hierarchy
- Credit system with per-user quota limits and admin exemptions
- Owner bootstrap: `@shish123`

### F&O Signal Generation
- NIFTY/BANKNIFTY assured signals (index options)
- Stock F&O signals for 20+ liquid NSE stocks
- **Master Spec Confluence Scoring (0-100)** with:
  - Real India VIX via yfinance (`^NSEINDVIX`, 5-min cache)
  - Real PCR (Put-Call Ratio) computed from Kite option chain OI data
  - ORB (Opening Range Breakout) strategy detection
  - VWAP Reversion strategy detection
  - Technical alignment, volume, breadth, GEX, fundamental quality
- Multi-tier entry optimization ("SmartDipEntry") at predicted micro-dip
- Dynamic targets (T1, T2) and stop-loss based on volatility + time-to-expiry
- Minimum R:R ratio ≥ 1.2 enforced
- **BEST EXIT — Expiry-Aware with Theta Decay (NEW Mar 2026):**
  - `get_remaining_trading_days()` counts actual NSE trading days (excluding weekends + NSE_HOLIDAYS)
  - Theta decay: `daily_theta = (entry_price / (remaining_trading_days + 1)) * 0.15`; `best_exit_price = raw_target - (daily_theta × best_exit_days)`
  - `best_exit_date_str` displays as "DD MMM YYYY" (e.g., "26 Mar 2026")
  - ⚠ Near Expiry badge appears when `remaining_trading_days <= 2`
  - Best Exit format: "T+N Trading Days (DD MMM YYYY) @ ₹X"
- `trigger_factors` list with ORB/VWAP tags and market metadata
- Expiry risk bucketing (SAFE/CAUTION/DANGER/EXPIRED)

### Custom F&O Sticky Cards
- Create/track custom F&O positions (buy_price, lot_size, quantity_lots)
- Live refresh with LTP, floating P/L, T1/T2 achievement, alert system
- **Sell any OPEN position** (no T1/T2 requirement)
- Realized P/L shown when sold (replaces floating P/L — no duplicate)
- `best_exit_days` + `best_exit_date_str` + `remaining_trading_days` stored in DB
- BEST EXIT display with calendar date on each card

### Portfolio Analysis
- Manual entry or file upload (.txt/.csv/.xls/.xlsx/.pdf/.jpg)
- Per-stock analysis: LTP, P/L, value_flag, price_zone, momentum/quality proxy
- Horizon analysis: 1W/1M/3M/6M/9M/1Y
- **Max Low (Downside)** column showing `min_expected_price` for each horizon
- Recommendation + comments with risk flags

### Multibagger Screener
- 200+ stock universe screened with 8-tier scoring
- **Real fundamental data via yfinance** (24h MongoDB cache):
  - ROE, ROCE, EPS growth
  - **Piotroski F-score (0-9)** from financial statements
  - **Beneish M-score** for earnings manipulation detection
  - Debt/Equity, Current Ratio, Gross Margin
- **Detailed thesis** with score breakdown, tier pass list, per-metric commentary
- **Fundamentals row** in table showing ROE/ROCE/Piotroski/Beneish color-coded
- **Hover effect — entire 4-row block (NEW Mar 2026):** `tbody.multibagger-group` CSS wraps all 4 rows per stock; entire block turns white on hover
- **Custom Stock Search (NEW Mar 2026):** Search any NSE symbol via `/api/multibagger/custom-search`; results shown in same 4-row block with fundamentals + thesis
- GTT buy price, upside targets by horizon, PEG proxy

### UI/UX
- Dark theme with cyan/emerald/rose accent palette
- **DayChange** and **BiasScore** shown as separate colored badges (not combined)
- Portfolio: Max Low (Downside) column with rose-colored values
- Multibagger: fundamentals row + detailed pipe-separated thesis
- White/light bg hover effect on Portfolio and Multibagger blocks
- Connect Kite button with status indicator in Admin panel

### Admin Panel
- User management (create/edit/delete sub_admin and user accounts)
- Credit management with per-user quota
- **Connect Kite** section with live status indicator
- System meta display

---

## Key API Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/access` | POST | Login with username |
| `/api/fno/generate` | GET | Generate all F&O signals |
| `/api/fno/custom-position` | POST | Create custom position |
| `/api/fno/custom-position/{id}/sell` | POST | Sell (any OPEN position) |
| `/api/portfolio/analyze` | POST | Analyze portfolio positions |
| `/api/multibagger/candidates` | GET | Multibagger screener |
| `/api/kite/auth-url` | GET | Kite OAuth URL |
| `/api/admin/kite/status` | GET | Kite connection status |

---

## DB Collections
- `app_users`: user accounts with RBAC
- `custom_positions`: F&O sticky cards
- `system_meta`: Kite session, config
- `fundamental_cache`: yfinance fundamentals (24h TTL)

---

## Known Limitations / Blockers
- **Kite Historical API (403):** `kiteconnect.historical_data` blocked — requires higher subscription plan. ORB/VWAP logic uses proxy calculations instead.
- **yfinance speed:** First multibagger run is slow (~60s for 200 stocks). Subsequent runs use 24h cache.
- **Kite OAuth:** Must be refreshed daily via `/api/kite/auth-url`. F&O signals fall back to limited data when not connected.

---

## P0/P1/P2 Backlog
### P0 (Done)
- [x] can_sell without T1/T2 restriction
- [x] min_expected_price in portfolio (Max Low column)
- [x] DayChange/BiasScore separate badges
- [x] Detailed multibagger thesis
- [x] Piotroski + Beneish + ROE + ROCE in multibagger
- [x] Real PCR from option chain OI
- [x] India VIX from yfinance
- [x] ORB/VWAP strategy classification
- [x] BEST EXIT in all F&O cards + custom cards with best_exit_days
- [x] **Multibagger Hover Fix:** entire 4-row block highlights via tbody.multibagger-group (Mar 2026)
- [x] **Custom Stock Search in Multibagger:** POST /api/multibagger/custom-search (Mar 2026)
- [x] **Expiry-Aware Projections + Theta Decay:** get_remaining_trading_days(), best_exit_date_str, Near Expiry badge (Mar 2026)

### P1 (Upcoming)
- [ ] Historical API workaround (use cached 5-min data from Kite quotes)
- [ ] Better VWAP calculation (accumulate intraday price points in cache)
- [ ] Kite SSO for portfolio holdings sync
- [ ] Full "Master Spec" constituent breadth scoring (NIFTY50/BANKNIFTY analysis)

### P2 (Backlog)
- [ ] Position Sizing Calculator (capital/risk-based lot recommendation)
- [ ] Sector Momentum Heatmap
- [ ] Codebase refactor: split server.py → routes/, models/, services/
- [ ] Codebase refactor: split App.js → pages/ with lazy loading
- [ ] Mobile app / PWA
- [ ] Real-time WebSocket for live P/L updates
- [ ] Backtesting module for signals
- [ ] Email/SMS alerts for target hits

---

## CHANGELOG (Mar 20, 2026 - Session 2)

### Feature: F&O Export
- Export Results button (CSV/XLS/JPG) added to F&O page
- Columns: Script | Bias | Lot | Entry ₹ | Investment | SL | T1 | T1% | T1 Profit | T2 | T2% | T2 Profit | Conf
- JPG heading: white text on #1E3A5F dark background (html2canvas safe)
- LOT_SIZE_MAP expanded with 100+ NSE F&O stocks for correct Lot in all exports

### Fix: F&O HIGH Confidence Golden Star
- ⭐ appears next to Confidence score in all result cards when score ≥ 80
- Applied to: renderLiveInfoBox, stock signals, Top 4 trades, custom signal, JPG export

### Feature: Domain Mapping — Complete
- ADD: POST /api/admin/domain-mappings (saves to MongoDB, returns DNS instructions)
- VIEW: Listed in admin config with status badges (ACTIVE/PENDING/NGINX_CONFIG_GENERATED/FAILED)
- DELETE: DELETE /api/admin/domain-mappings/{domain} with confirm dialog in UI
- MAP: POST /api/admin/domain-mappings/{domain}/map — writes nginx reverse-proxy config, attempts reload, returns result in UI
- DNS Instructions toggle per domain in admin panel

### Fix: Portfolio & Multibagger Hover
- Portfolio card hover: background #FFFFFF, border-radius 8px, box-shadow, all text #1A1A1A
- Multibagger row hover: background #FFFFFF, all text #1A1A1A
- CSS specificity fixed to override conflicting generic rules

### Fix: Portfolio "No Live Data" Error
- _analyze_portfolio_positions now tries symbol variants (-EQ removal, uppercase trim) before failing
- Failed symbols collected in failed_symbols[] list — never block whole analysis
- PortfolioAnalyzeResponse includes failed_symbols field
- Frontend shows yellow warning badge per failed symbol (non-blocking)
- Server-side logging for all failed symbols
