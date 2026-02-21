# Monaimetrics

## Overview
Monaimetrics is a Python CLI trading dashboard that connects to Alpaca's trading API. It provides portfolio management, activity reporting, growth tracking, and trade planning capabilities.

## Project Architecture
- **Language**: Python 3.12
- **Package Manager**: uv (pyproject.toml)
- **Type**: CLI application (no frontend/web UI)

### Directory Structure
- `monaimetrics/` - Main application package
  - `cli.py` - Interactive CLI dashboard (entry point: `python -m monaimetrics.cli`)
  - `config.py` - Configuration, enums, and system settings
  - `data_input.py` - Alpaca API data adapter layer
  - `calculators.py` - Technical analysis calculations
  - `strategy.py` - Trading strategy logic
  - `portfolio_manager.py` - Portfolio management
  - `trading_interface.py` - Order execution via Alpaca
  - `reporting.py` - Trade/performance reporting
  - `audit_qa.py` - Retrospective analysis
- `tests/` - Test suite
- `_developer/` - Developer documentation and planning

### Key Dependencies
- `alpaca-py` - Alpaca trading/data SDK
- `python-dotenv` - Environment variable loading
- `pytz` - Timezone support

### Environment Variables
The app requires Alpaca API credentials (loaded from `.env` or environment):
- `ALPACA_API_KEY` - Alpaca API key
- `ALPACA_SECRET_KEY` - Alpaca secret key
- `ALPACA_PAPER` - Set to "true" for paper trading (default behavior is dry run)

## Running
- Workflow: `python -m monaimetrics.cli`
- Tests: `python -m pytest tests/`
