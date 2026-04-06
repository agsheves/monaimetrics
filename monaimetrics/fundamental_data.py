"""
Alpha Vantage fundamental data adapter with file-based caching.
Cache persists in cache/fundamentals/ — Replit-friendly, no database needed.

Rate limiting: 75 calls/min on the premium plan. Each stock needs 4 API calls.
Cache TTL: 24 hours (fundamentals change quarterly, daily refresh is plenty).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "fundamentals"
CACHE_TTL_HOURS = int(os.environ.get("FUNDAMENTAL_CACHE_TTL_HOURS", "24"))
BASE_URL = "https://www.alphavantage.co/query"

# Rate limiting: 75 calls/min = 1 call per 0.8s
_last_call_time = 0.0
_MIN_CALL_INTERVAL = 0.85


def _get_api_key() -> str:
    return os.environ.get("ALPHA_VANTAGE_API_KEY", "") or os.environ.get("ALPHAVANTAGE_API_KEY", "")


def _rate_limit():
    global _last_call_time
    now = time.monotonic()
    elapsed = now - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)
    _last_call_time = time.monotonic()


def _fetch(function: str, symbol: str, api_key: str, **extra) -> dict:
    """Single Alpha Vantage API call with rate limiting."""
    _rate_limit()
    params = {"function": function, "symbol": symbol, "apikey": api_key, **extra}
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "Error Message" in data or "Note" in data:
        msg = data.get("Error Message") or data.get("Note", "")
        log.warning("Alpha Vantage %s/%s: %s", function, symbol, msg)
        return {}
    return data


# ---------------------------------------------------------------------------
# Data Structure
# ---------------------------------------------------------------------------

@dataclass
class FundamentalData:
    """Pre-extracted fundamental fields for scoring."""
    symbol: str

    # Company info
    sector: str = ""
    industry: str = ""
    market_cap: float = 0.0

    # Valuation
    pe_ratio: float = 0.0
    forward_pe: float = 0.0
    price_to_book: float = 0.0
    ev_to_ebitda: float = 0.0

    # Profitability
    eps_ttm: float = 0.0
    return_on_equity: float = 0.0
    return_on_assets: float = 0.0

    # CANSLIM fields
    quarterly_eps_growth_yoy: float = 0.0
    annual_eps_growth_3yr: float = 0.0
    percent_institutions: float = 0.0
    shares_outstanding: float = 0.0
    shares_float: float = 0.0
    fifty_two_week_high: float = 0.0
    fifty_two_week_low: float = 0.0

    # Greenblatt fields
    ebit_ttm: float = 0.0
    enterprise_value: float = 0.0
    net_working_capital: float = 0.0
    net_fixed_assets: float = 0.0
    earnings_yield: float = 0.0
    return_on_capital: float = 0.0

    # Historical EPS for backtest [(date_str, eps), ...]
    quarterly_eps: list = field(default_factory=list)
    annual_eps: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------

def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol.upper()}.json"


def _is_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        fetched = datetime.fromisoformat(data.get("fetched_at", ""))
        return datetime.now(timezone.utc) - fetched < timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return False


def _read_cache(symbol: str) -> dict | None:
    path = _cache_path(symbol)
    if not _is_cache_fresh(path):
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_cache(symbol: str, raw: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw["fetched_at"] = datetime.now(timezone.utc).isoformat()
    try:
        _cache_path(symbol).write_text(json.dumps(raw, indent=1))
    except Exception as e:
        log.warning("Cache write failed for %s: %s", symbol, e)


# ---------------------------------------------------------------------------
# Fetch & Parse
# ---------------------------------------------------------------------------

def _safe_float(val, default=0.0) -> float:
    if val is None or val == "" or val == "None" or val == "-":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _extract_fundamentals(symbol: str, raw: dict) -> FundamentalData:
    """Extract scoring fields from cached raw API responses."""
    ov = raw.get("overview", {})
    inc = raw.get("income_statement", {})
    bal = raw.get("balance_sheet", {})
    earn = raw.get("earnings", {})

    # --- Overview fields ---
    market_cap = _safe_float(ov.get("MarketCapitalization"))
    pe = _safe_float(ov.get("PERatio"))
    fwd_pe = _safe_float(ov.get("ForwardPE"))
    ptb = _safe_float(ov.get("PriceToBookRatio"))
    ev_ebitda = _safe_float(ov.get("EVToEBITDA"))
    eps = _safe_float(ov.get("EPS"))
    roe = _safe_float(ov.get("ReturnOnEquityTTM"))
    roa = _safe_float(ov.get("ReturnOnAssetsTTM"))
    q_growth = _safe_float(ov.get("QuarterlyEarningsGrowthYOY"))
    inst_pct = _safe_float(ov.get("PercentInstitutions"))
    shares_out = _safe_float(ov.get("SharesOutstanding"))
    shares_flt = _safe_float(ov.get("SharesFloat"))
    high_52 = _safe_float(ov.get("52WeekHigh"))
    low_52 = _safe_float(ov.get("52WeekLow"))

    # --- Quarterly EPS history ---
    quarterly_eps = []
    for q in earn.get("quarterlyEarnings", []):
        date_str = q.get("fiscalDateEnding", "")
        reported = _safe_float(q.get("reportedEPS"))
        if date_str:
            quarterly_eps.append((date_str, reported))

    # --- Annual EPS history ---
    annual_eps = []
    for a in earn.get("annualEarnings", []):
        date_str = a.get("fiscalDateEnding", "")
        reported = _safe_float(a.get("reportedEPS"))
        if date_str:
            annual_eps.append((date_str, reported))

    # --- Annual EPS growth (3-year) ---
    annual_eps_growth_3yr = 0.0
    if len(annual_eps) >= 4:
        recent = annual_eps[0][1]  # most recent year
        three_yrs_ago = annual_eps[3][1]  # 3 years back
        if three_yrs_ago > 0 and recent > 0:
            annual_eps_growth_3yr = (recent / three_yrs_ago) ** (1.0 / 3.0) - 1.0

    # --- EBIT TTM from income statement ---
    ebit_ttm = 0.0
    quarterly_reports = inc.get("quarterlyReports", [])
    if len(quarterly_reports) >= 4:
        ebit_ttm = sum(_safe_float(q.get("ebit")) for q in quarterly_reports[:4])
    elif inc.get("annualReports"):
        ebit_ttm = _safe_float(inc["annualReports"][0].get("ebit"))

    # --- Enterprise value ---
    ev = 0.0
    if bal.get("quarterlyReports"):
        latest_bal = bal["quarterlyReports"][0]
        total_debt = (
            _safe_float(latest_bal.get("shortTermDebt"))
            + _safe_float(latest_bal.get("longTermDebt"))
        )
        cash = _safe_float(latest_bal.get("cashAndCashEquivalentsAtCarryingValue"))
        ev = market_cap + total_debt - cash
    elif ev_ebitda > 0:
        ebitda_ov = _safe_float(ov.get("EBITDA"))
        if ebitda_ov > 0:
            ev = ev_ebitda * ebitda_ov

    # --- Net working capital & net fixed assets ---
    nwc = 0.0
    nfa = 0.0
    if bal.get("quarterlyReports"):
        latest_bal = bal["quarterlyReports"][0]
        current_assets = _safe_float(latest_bal.get("totalCurrentAssets"))
        current_liab = _safe_float(latest_bal.get("totalCurrentLiabilities"))
        nwc = current_assets - current_liab
        nfa = _safe_float(latest_bal.get("propertyPlantEquipment"))

    # --- Greenblatt metrics ---
    earnings_yield = ebit_ttm / ev if ev > 0 else 0.0
    invested = nwc + nfa
    return_on_capital = ebit_ttm / invested if invested > 0 else 0.0

    return FundamentalData(
        symbol=symbol,
        sector=ov.get("Sector", ""),
        industry=ov.get("Industry", ""),
        market_cap=market_cap,
        pe_ratio=pe,
        forward_pe=fwd_pe,
        price_to_book=ptb,
        ev_to_ebitda=ev_ebitda,
        eps_ttm=eps,
        return_on_equity=roe,
        return_on_assets=roa,
        quarterly_eps_growth_yoy=q_growth,
        annual_eps_growth_3yr=annual_eps_growth_3yr,
        percent_institutions=inst_pct,
        shares_outstanding=shares_out,
        shares_float=shares_flt,
        fifty_two_week_high=high_52,
        fifty_two_week_low=low_52,
        ebit_ttm=ebit_ttm,
        enterprise_value=ev,
        net_working_capital=nwc,
        net_fixed_assets=nfa,
        earnings_yield=earnings_yield,
        return_on_capital=return_on_capital,
        quarterly_eps=quarterly_eps,
        annual_eps=annual_eps,
    )


def fetch_fundamentals(symbol: str) -> FundamentalData | None:
    """Fetch fundamental data from Alpha Vantage (4 API calls). Returns None on failure."""
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        overview = _fetch("OVERVIEW", symbol, api_key)
        income = _fetch("INCOME_STATEMENT", symbol, api_key)
        balance = _fetch("BALANCE_SHEET", symbol, api_key)
        earnings = _fetch("EARNINGS", symbol, api_key)

        if not overview:
            return None

        raw = {
            "overview": overview,
            "income_statement": income,
            "balance_sheet": balance,
            "earnings": earnings,
        }
        _write_cache(symbol, raw)
        return _extract_fundamentals(symbol, raw)

    except Exception as e:
        log.warning("Fundamental fetch failed for %s: %s", symbol, e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_fundamentals(symbol: str) -> FundamentalData | None:
    """Get fundamental data — from cache if fresh, otherwise fetch."""
    cached = _read_cache(symbol)
    if cached:
        return _extract_fundamentals(symbol, cached)
    return fetch_fundamentals(symbol)


def get_fundamentals_cached_only(symbol: str) -> FundamentalData | None:
    """Get from cache only — no API calls. For backtesting."""
    cached = _read_cache(symbol)
    if cached:
        return _extract_fundamentals(symbol, cached)
    return None


def bulk_refresh(
    symbols: list[str],
    progress_callback=None,
) -> dict[str, FundamentalData]:
    """Refresh fundamentals for a list of symbols. Returns {symbol: data}."""
    results = {}
    for i, sym in enumerate(symbols):
        data = get_fundamentals(sym)
        if data:
            results[sym] = data
        if progress_callback:
            progress_callback(i + 1, len(symbols), sym)
    log.info("Bulk refresh: %d/%d symbols loaded", len(results), len(symbols))
    return results


def cache_stats() -> dict:
    """Return cache statistics."""
    if not CACHE_DIR.exists():
        return {"cached_symbols": 0, "cache_dir": str(CACHE_DIR)}
    files = list(CACHE_DIR.glob("*.json"))
    fresh = sum(1 for f in files if _is_cache_fresh(f))
    return {
        "cached_symbols": len(files),
        "fresh_symbols": fresh,
        "stale_symbols": len(files) - fresh,
        "cache_dir": str(CACHE_DIR),
    }


# ---------------------------------------------------------------------------
# Historical Daily Prices (for backtest)
# ---------------------------------------------------------------------------

PRICE_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "prices"
PRICE_CACHE_TTL_HOURS = int(os.environ.get("PRICE_CACHE_TTL_HOURS", "24"))


def _price_cache_path(symbol: str) -> Path:
    return PRICE_CACHE_DIR / f"{symbol.upper()}.json"


def _is_price_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        fetched = datetime.fromisoformat(data.get("fetched_at", ""))
        return datetime.now(timezone.utc) - fetched < timedelta(hours=PRICE_CACHE_TTL_HOURS)
    except Exception:
        return False


def fetch_daily_prices(symbol: str, outputsize: str = "full") -> list[dict]:
    """
    Fetch daily adjusted prices from Alpha Vantage.
    Returns list of {date, open, high, low, close, adjusted_close, volume}
    sorted oldest-first. Cached to cache/prices/.

    outputsize: "compact" (100 days) or "full" (20+ years).
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    # Check cache first
    path = _price_cache_path(symbol)
    if _is_price_cache_fresh(path):
        try:
            data = json.loads(path.read_text())
            return data.get("prices", [])
        except Exception:
            pass

    try:
        raw = _fetch(
            "TIME_SERIES_DAILY_ADJUSTED", symbol, api_key,
            outputsize=outputsize,
        )
        ts = raw.get("Time Series (Daily)", {})
        if not ts:
            return []

        prices = []
        for date_str, vals in sorted(ts.items()):
            prices.append({
                "date": date_str,
                "open": float(vals.get("1. open", 0)),
                "high": float(vals.get("2. high", 0)),
                "low": float(vals.get("3. low", 0)),
                "close": float(vals.get("4. close", 0)),
                "adjusted_close": float(vals.get("5. adjusted close", 0)),
                "volume": int(float(vals.get("6. volume", 0))),
            })

        # Cache
        PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "prices": prices,
        }
        try:
            path.write_text(json.dumps(cache_data))
        except Exception as e:
            log.warning("Price cache write failed for %s: %s", symbol, e)

        return prices

    except Exception as e:
        log.warning("Daily price fetch failed for %s: %s", symbol, e)
        return []


def get_daily_prices(symbol: str, outputsize: str = "full") -> list[dict]:
    """Get daily prices — from cache if fresh, otherwise fetch."""
    path = _price_cache_path(symbol)
    if _is_price_cache_fresh(path):
        try:
            data = json.loads(path.read_text())
            return data.get("prices", [])
        except Exception:
            pass
    return fetch_daily_prices(symbol, outputsize)


def fetch_delayed_quote(symbol: str) -> dict | None:
    """
    Fetch 15-minute delayed quote from Alpha Vantage.
    Returns {symbol, price, volume, latest_trading_day, change, change_percent}
    or None on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        raw = _fetch(
            "GLOBAL_QUOTE", symbol, api_key,
            entitlement="delayed",
        )
        quote = raw.get("Global Quote", {})
        if not quote:
            return None

        return {
            "symbol": quote.get("01. symbol", symbol),
            "price": _safe_float(quote.get("05. price")),
            "volume": int(_safe_float(quote.get("06. volume"))),
            "latest_trading_day": quote.get("07. latest trading day", ""),
            "change": _safe_float(quote.get("09. change")),
            "change_percent": quote.get("10. change percent", ""),
        }
    except Exception as e:
        log.warning("Delayed quote fetch failed for %s: %s", symbol, e)
        return None
