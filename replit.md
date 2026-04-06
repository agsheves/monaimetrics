# Monaimetrics

## Overview
Monaimetrics is a Python trading dashboard that connects to Alpaca's trading API. It provides portfolio management, activity reporting, growth tracking, trade planning, and strategy research capabilities through both a CLI and a Django web UI.

## Project Architecture
- **Language**: Python 3.12
- **Framework**: Django 6.0 (web UI)
- **Package Manager**: uv (pyproject.toml)
- **Type**: Web application with CLI fallback

### Directory Structure
- `monaimetrics/` - Core trading engine package
  - `cli.py` - Interactive CLI dashboard (entry point: `python -m monaimetrics.cli`)
  - `config.py` - Configuration, enums, risk profiles, allocation tables
  - `data_input.py` - Alpaca API data adapter layer
  - `calculators.py` - Technical analysis calculations
  - `strategy.py` - Trading strategy logic
  - `portfolio_manager.py` - Portfolio orchestration
  - `trading_interface.py` - Order execution via Alpaca
  - `reporting.py` - Trade/performance reporting
  - `audit_qa.py` - Retrospective analysis
  - `prediction_trading_arb.py` - Kalshi arb trading engine (separate config, accounting, execution)
- `web/` - Django web application
  - `settings.py` - Django settings (ALLOWED_HOSTS=*, session cookies, CSRF)
  - `urls.py` - Root URL config
  - `wsgi.py` - WSGI application
  - `dashboard/` - Main app (views, URLs, template tags)
  - (no services folder — all functional code lives in `monaimetrics/`)
  - `templates/dashboard/` - HTML templates (base, login, dashboard, settings, lookup, research, arb)
  - `static/css/` - Dark theme CSS
- `_developer/` - Reference documents (used by research panel)
- `tests/` - Test suite
- `manage.py` - Django management script

### Key Dependencies
- `django` - Web framework
- `alpaca-py` - Alpaca trading/data SDK
- `groq` - Groq API client (LLM for research panel)
- `gunicorn` - Production WSGI server
- `python-dotenv` - Environment variable loading
- `pytz` - Timezone support
- `cryptography` - RSA-PSS signing for Kalshi API auth

### Configuration — Two-source system

**Replit app secrets** — confidential credentials (set in Replit sidebar, never in code):
- `APP_PASSWORD` - Login password
- `APP_USERNAME` - Login username
- `GROQ_API_KEY` - Groq API key for research panel
- `ALPACA_API_KEY` - Alpaca API key (live or paper, matching the account you use)
- `ALPACA_SECRET_KEY` - Alpaca API secret key

**`user_config.yaml`** — shareable non-secret settings (committed to git):
- `ALPACA_PAPER` - `true` = paper trading endpoint, `false` = live (default: `false`)
- `DRY_RUN` - `true` = no real orders submitted (default: `false`)
- `MAX_SHARE_PRICE_USD` - Skip stocks above this price per share (default: `25.0`)
- `CASH_RESERVE_PCT` - Fraction of cash kept undeployed (default: `0.20`)
- `SCAN_UNIVERSE_LIMIT` - Max symbols scanned per assessment (default: `200`)
- `PROFIT_TARGET` - Profit target for moderate tier as decimal (default: `0.15` = 15%)
- `STOP_LOSS` - Stop-loss for moderate tier as decimal (default: `0.06` = 6%)
- `RISK_PROFILE` - Risk profile for the scheduler: `conservative`, `moderate`, or `aggressive` (default: `moderate`); also written by the Settings page

**Load order** (highest priority first): Replit secrets (already in os.environ) → `user_config.yaml` → code defaults.
Loader: `monaimetrics/user_config.py` — called from both `web/settings.py` and `monaimetrics/config.py`.
No `.env` file is used; all secrets live in Replit app secrets only.

### Pages
1. **Login** (`/login/`) - Simple username/password auth
2. **Portfolio** (`/`) - Portfolio value, cash, positions, allocation bar
3. **Symbol Lookup** (`/lookup/`) - Stock lookup with price, technicals, trading signals
4. **Scan** (`/scan/`) - Dry-run opportunity scan across a symbol universe; buy candidates ranked by confidence
5. **Research** (`/research/`) - Ask questions about trading strategies via Groq LLM
6. **Arb Trading** (`/arb/`) - Kalshi prediction market arbitrage dashboard (separate from stock portfolio)
7. **Settings** (`/settings/`) - Risk profile selector with allocation table preview

### Automatic Trading Scheduler
- Boots via Django's `AppConfig.ready()` hook in `web/dashboard/apps.py`
- Implemented in `monaimetrics/scheduler.py`
- **Assessment job**: runs **hourly at :45** from 09:45 through 15:45 ET (Mon–Fri). Fetches the live Alpaca universe of tradeable US equities (`SCAN_UNIVERSE_LIMIT`, default 200), evaluates every symbol through the full strategy stack (stage analysis, Kelly sizing, cycle positioning, risk tier allocation), executes buy/sell/reduce signals that meet the rules.
- **Stop check job**: lightweight price-only scan of current positions every `STOP_CHECK_INTERVAL_MINUTES` (default: 15) during market hours — fires stop-loss and trailing-stop sells immediately without waiting for the next assessment. Also applies **breakeven lock**: once a position is up 3%, stop is floored at `entry + $0.01`.
- Market hours: 09:30–16:00 ET, Monday–Friday only
- Both jobs read `RISK_PROFILE` from env/user_config.yaml (no longer hardcoded to MODERATE)
- Both jobs log activity and respect `DRY_RUN` — no orders are submitted in dry run mode
- Uses Django's `RUN_MAIN` env var guard to avoid double-starting under the StatReloader

### Order Execution
- **Bracket orders**: each buy submits a single bracket order (buy + stop-loss atomically) via Alpaca's bracket order API. This eliminates "potential wash trade" rejections. Falls back to plain buy + separate stop if bracket is rejected.
- Any existing stop-loss for a symbol is cancelled before re-buying to prevent conflicts.

### Safety Controls
- `MAX_SHARE_PRICE_USD` env var (default: `25.0`) — skips stocks priced above this per-share limit; allows multiple shares to be bought up to Kelly-sized amount
- `DRY_RUN` env var — skips actual order submission; **default is `true`** (safe mode). Set `DRY_RUN=false` to enable live execution.
- `ALPACA_PAPER=true` env var — switches Alpaca client to paper trading mode (default: live)
- 20% cash reserve enforced before every buy (`CASH_RESERVE_PCT`)

## Running
- **Web UI**: `python manage.py runserver 0.0.0.0:5000`
- **CLI**: `python -m monaimetrics.cli`
- **Tests**: `python -m pytest tests/`
- **Production**: `gunicorn --bind=0.0.0.0:5000 --workers=2 web.wsgi:application`

## User Preferences
- Clean dark theme UI
- Minimal additional languages (Python-focused)
- Personal tool, single-user auth via env vars
- Django for backend
- Groq (Llama Maverick) for research panel
