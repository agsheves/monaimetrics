# Monaimetrics

## Overview
Monaimetrics is a Python trading platform that connects to Alpaca's trading API. It automatically evaluates US equities through multiple investment frameworks and executes trades that fit the investment thesis. It provides portfolio management, activity reporting, growth tracking, trade planning, and strategy research through both a CLI and a Django web UI.

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
  - `strategy.py` - Trading strategy logic (6 framework scoring system)
  - `portfolio_manager.py` - Portfolio orchestration
  - `trading_interface.py` - Order execution via Alpaca
  - `scheduler.py` - Automated trading scheduler (assessments + stop checks)
  - `runtime_settings.py` - Persistent user-adjustable settings (JSON file)
  - `review_queue.py` - Human-in-the-loop trade approval queue
  - `reporting.py` - Trade/performance reporting
  - `audit_qa.py` - Retrospective analysis
  - `fundamental_data.py` - Alpha Vantage fundamental data adapter with file-based caching
  - `backtest.py` - Historical backtest engine (simulates strategy over cached price data)
  - `alpha_signals.py` - External data feed overlay system
- `web/` - Django web application
  - `settings.py` - Django settings (ALLOWED_HOSTS=*, session cookies, CSRF)
  - `urls.py` - Root URL config
  - `wsgi.py` - WSGI application
  - `dashboard/` - Main app (views, URLs, template tags)
  - `templates/dashboard/` - HTML templates (base, login, dashboard, settings, lookup, scan, research)
  - `static/css/` - Dark theme CSS
- `_developer/` - Reference documents (used by research panel)
- `tests/` - Test suite
- `manage.py` - Django management script

### Key Dependencies
- `django` - Web framework
- `alpaca-py` - Alpaca trading/data SDK
- `apscheduler` - Background task scheduling
- `groq` - Groq API client (LLM for research panel)
- `gunicorn` - Production WSGI server
- `python-dotenv` - Environment variable loading

### Environment Variables / Secrets
- `APP_USERNAME` - Login username (default: "admin")
- `APP_PASSWORD` - Login password (secret)
- `GROQ_API_KEY` - Groq API key for research panel (secret)
- `ALPACA_API_KEY` - Alpaca API key
- `ALPACA_SECRET_KEY` - Alpaca secret key
- `ALPACA_PAPER` - Use Alpaca paper trading (default: "false")
- `ALPHA_VANTAGE_API_KEY` - Alpha Vantage API key (75 calls/min premium plan)

### Pages
1. **Login** (`/login/`) - Simple username/password auth
2. **Portfolio** (`/`) - Portfolio value, cash, positions, allocation bar, pending trade reviews
3. **Symbol Lookup** (`/lookup/`) - Stock lookup with price, technicals, trading signals
4. **Scan** (`/scan/`) - Opportunity scan across the full Alpaca universe; buy candidates ranked by confidence
5. **Backtest** (`/backtest/`) - Simulate the strategy over historical data with equity curve, trade log, win/loss stats
6. **Research** (`/research/`) - Ask questions about trading strategies via Groq LLM, with suggested quick questions and markdown rendering
7. **Settings** (`/settings/`) - Risk profile selector, position size min/max, universe limit, dry run toggle, human review toggle

### Automatic Trading Scheduler
- Boots via Django's `AppConfig.ready()` hook in `web/dashboard/apps.py`
- Implemented in `monaimetrics/scheduler.py`
- **Assessment job**: runs twice daily (09:45 ET and 14:00 ET, Mon-Fri). Fetches the live Alpaca universe of tradeable US equities, evaluates every symbol through the full strategy stack. If human review is enabled, signals are queued for approval. Otherwise, trades execute immediately.
- **Stop check job**: lightweight price-only scan every 15 minutes during market hours. Fires stop-loss and trailing-stop sells immediately (always, even when human review is enabled).
- **Approved trades job**: checks the review queue every 2 minutes and executes approved signals.
- Market hours: 09:30-16:00 ET, Monday-Friday only
- All jobs respect the dry run setting

### Runtime Settings
- Persisted to `runtime_settings.json` (not in git)
- Adjustable via the Settings page: risk profile, position size min/max, universe limit, dry run, human review
- The scheduler reads these on every job run

### Safety Controls
- Position size min/max enforced in `trading_interface._check_position_size` before any order is submitted
- Dry run mode: signals are logged but no real orders are placed (default: enabled)
- Human review mode: trades are queued for manual approval before execution (default: enabled)
- Stop-losses always execute immediately regardless of review mode
- Circuit breakers: max drawdown, rapid loss pause, concentration limits

## Running
- **Web UI**: `python manage.py runserver 0.0.0.0:5000`
- **CLI**: `python -m monaimetrics.cli`
- **Tests**: `python -m pytest tests/`
- **Production**: `gunicorn --bind=0.0.0.0:5000 --workers=2 web.wsgi:application`
