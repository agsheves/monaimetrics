"""
Market-wide intelligence: VIX, breadth, cycle scoring.

Computes cycle_score (-2 to +2) from VIX level and market breadth.
This drives the allocation tables in config.py that adjust equity/cash
split based on market conditions.

Score mapping (matches ALLOCATION_TABLES in config.py):
    -2  Extreme fear    → max equity exposure (contrarian buy)
    -1  Elevated fear   → slightly aggressive
     0  Normal          → balanced
    +1  Low volatility  → slightly cautious
    +2  Complacency     → defensive (raise cash)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "market"
VIX_CACHE_TTL_MINUTES = 30

_last_call_time = 0.0
_MIN_CALL_INTERVAL = 0.85


def _get_api_key() -> str:
    return (
        os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        or os.environ.get("ALPHAVANTAGE_API_KEY", "")
    )


def _rate_limit():
    global _last_call_time
    now = time.monotonic()
    elapsed = now - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)
    _last_call_time = time.monotonic()


def fetch_vix() -> float | None:
    """
    Fetch current VIX proxy level via Alpha Vantage.
    Uses VIXY (ProShares VIX Short-Term Futures ETF) as a readily available
    proxy. Returns estimated VIX level or None on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    cache_path = CACHE_DIR / "vix.json"
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            fetched = datetime.fromisoformat(data["fetched_at"])
            if datetime.now(timezone.utc) - fetched < timedelta(minutes=VIX_CACHE_TTL_MINUTES):
                return data.get("vix_level")
        except Exception:
            pass

    try:
        _rate_limit()
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": "VIXY",
            "entitlement": "delayed",
            "apikey": api_key,
        }
        resp = requests.get(
            "https://www.alphavantage.co/query", params=params, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        quote = data.get("Global Quote", {})
        price = float(quote.get("05. price", 0))

        if price <= 0:
            log.warning("VIX proxy: VIXY returned zero price")
            return None

        # VIXY tracks VIX short-term futures
        # Rough mapping: VIXY price correlates with VIX level
        vix_estimate = price * 0.75

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "vix_level": round(vix_estimate, 2),
            "proxy_price": price,
            "proxy_symbol": "VIXY",
        }
        cache_path.write_text(json.dumps(cache_data, indent=2))

        log.info("VIX proxy: VIXY=$%.2f → VIX≈%.1f", price, vix_estimate)
        return vix_estimate

    except Exception as e:
        log.warning("VIX fetch failed: %s", e)
        return None


def vix_to_cycle_score(vix: float) -> int:
    """
    Convert VIX level to cycle score (-2 to +2).

    Maps to ALLOCATION_TABLES in config.py:
    -2 has highest high-risk allocation (most aggressive)
    +2 has lowest high-risk allocation (most defensive)

    VIX < 12:  +2 (extreme complacency → be defensive)
    VIX 12-16: +1 (low fear → slightly cautious)
    VIX 16-22:  0 (normal range)
    VIX 22-30: -1 (elevated fear → contrarian opportunity)
    VIX > 30:  -2 (extreme fear → max contrarian)
    """
    if vix < 12:
        return 2
    elif vix < 16:
        return 1
    elif vix < 22:
        return 0
    elif vix < 30:
        return -1
    else:
        return -2


def compute_market_breadth(stage_counts: dict[int, int]) -> dict:
    """
    Compute market breadth from stage distribution.

    stage_counts: {1: count, 2: count, 3: count, 4: count}
    """
    total = sum(stage_counts.values())
    if total == 0:
        return {"advancing_pct": 0, "declining_pct": 0, "signal": "neutral", "total_stocks": 0}

    advancing = stage_counts.get(2, 0)
    declining = stage_counts.get(4, 0)
    adv_pct = advancing / total
    dec_pct = declining / total

    if dec_pct > 0.60:
        signal = "bearish"
    elif adv_pct > 0.60:
        signal = "bullish"
    elif dec_pct > 0.40:
        signal = "cautious"
    else:
        signal = "neutral"

    return {
        "advancing_pct": round(adv_pct, 3),
        "declining_pct": round(dec_pct, 3),
        "basing_pct": round(stage_counts.get(1, 0) / total, 3),
        "topping_pct": round(stage_counts.get(3, 0) / total, 3),
        "total_stocks": total,
        "signal": signal,
    }


def compute_cycle_score(
    vix: float | None = None,
    breadth: dict | None = None,
) -> int:
    """
    Compute cycle score from VIX and market breadth.
    VIX is the primary input; breadth can override in extreme cases.
    """
    if vix is not None:
        score = vix_to_cycle_score(vix)
    else:
        score = 0

    # Breadth override: if >60% declining, force caution regardless of VIX
    if breadth and breadth.get("signal") == "bearish":
        score = max(score, 1)

    return max(-2, min(2, score))
