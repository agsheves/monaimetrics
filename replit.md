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

### Environment Variables / Secrets
- `APP_USERNAME` - Login username (default: "admin")
- `APP_PASSWORD` - Login password (secret)
- `GROQ_API_KEY` - Groq API key for research panel (secret)
- `ALPACA_API_KEY` - Alpaca API key
- `ALPACA_SECRET_KEY` - Alpaca secret key
- `KALSHI_API_KEY` - Kalshi API key (for arb trading)
- `KALSHI_PRIVATE_KEY_PATH` - Kalshi RSA private key (file path OR inline PEM content starting with `-----BEGIN`)
- `KALSHI_PRIVATE_KEY_PEM` - Alternative: inline PEM content for Kalshi key
- `KALSHI_USE_DEMO` - Use Kalshi demo API (default: "true")
- `ARB_DRY_RUN` - Dry run mode for arb trades (default: "true")

### Pages
1. **Login** (`/login/`) - Simple username/password auth
2. **Portfolio** (`/`) - Portfolio value, cash, positions, allocation bar
3. **Symbol Lookup** (`/lookup/`) - Stock lookup with price, technicals, trading signals
4. **Research** (`/research/`) - Ask questions about trading strategies via Groq LLM
5. **Arb Trading** (`/arb/`) - Kalshi prediction market arbitrage dashboard (separate from stock portfolio)
6. **Settings** (`/settings/`) - Risk profile selector with allocation table preview

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
