from __future__ import annotations

import logging
from monaimetrics.config import load_config, RiskProfile, ALLOCATION_TABLES
from monaimetrics.data_input import (
    AlpacaClients, get_account, get_positions, get_technical_data,
)
from monaimetrics.portfolio_manager import PortfolioManager
from monaimetrics.strategy import evaluate_opportunity, generate_plan, ManagedPosition

log = logging.getLogger(__name__)


def get_portfolio_data(risk_profile: str = "moderate") -> dict:
    try:
        profile = RiskProfile(risk_profile)
    except ValueError:
        profile = RiskProfile.MODERATE

    config = load_config(profile)
    clients = AlpacaClients(config.api)

    try:
        account = get_account(clients)
        positions = get_positions(clients)
        connected = True
    except Exception as e:
        log.warning("Could not connect to Alpaca: %s", e)
        return {
            "connected": False,
            "error": str(e),
            "account": None,
            "positions": [],
            "allocation": None,
            "profile": profile.value,
        }

    allocation = config.get_allocation(0)

    total = account.portfolio_value if account.portfolio_value > 0 else 1
    moderate_value = sum(p.market_value for p in positions) * allocation.moderate
    high_value = sum(p.market_value for p in positions) * allocation.high

    return {
        "connected": connected,
        "error": None,
        "account": {
            "portfolio_value": account.portfolio_value,
            "cash": account.cash,
            "buying_power": account.buying_power,
            "status": account.status,
        },
        "positions": [
            {
                "symbol": p.symbol,
                "qty": p.qty,
                "avg_entry_price": p.avg_entry_price,
                "current_price": p.current_price,
                "market_value": p.market_value,
                "unrealized_pl": p.unrealized_pl,
                "unrealized_pl_pct": p.unrealized_pl_pct,
            }
            for p in positions
        ],
        "allocation": {
            "moderate": allocation.moderate,
            "high": allocation.high,
            "cash": allocation.cash,
        },
        "profile": profile.value,
    }


def get_symbol_data(symbol: str, risk_profile: str = "moderate") -> dict:
    try:
        profile = RiskProfile(risk_profile)
    except ValueError:
        profile = RiskProfile.MODERATE

    config = load_config(profile)
    clients = AlpacaClients(config.api)

    try:
        tech = get_technical_data(symbol, clients=clients)
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

    from monaimetrics.data_input import get_bars
    try:
        bars = get_bars(symbol, days=30, clients=clients)
        recent_bars = [
            {
                "date": b.timestamp.strftime("%Y-%m-%d"),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": int(b.volume),
            }
            for b in bars[-10:]
        ]
    except Exception:
        recent_bars = []

    stage_labels = {1: "Basing", 2: "Advancing", 3: "Topping", 4: "Declining"}

    signal = None
    try:
        pm = PortfolioManager(config, clients)
        account = get_account(clients)
        pm.peak_value = account.portfolio_value
        plan, _ = pm.run_assessment(watchlist=[symbol])
        if plan.signals:
            sig = plan.signals[0]
            signal = {
                "action": sig.action.value.upper(),
                "tier": sig.tier.value,
                "confidence": sig.confidence,
                "urgency": sig.urgency.value,
                "reasons": sig.reasons,
                "position_size_usd": sig.position_size_usd,
                "stop_price": sig.stop_price,
                "target_price": sig.target_price,
            }
    except Exception as e:
        log.warning("Could not generate signal for %s: %s", symbol, e)

    return {
        "error": None,
        "symbol": symbol,
        "price": tech.price,
        "ma_150": tech.ma_150,
        "ma_slope": tech.ma_slope,
        "atr_14": tech.atr_14,
        "volume_ratio": tech.volume_ratio,
        "stage": tech.stage,
        "stage_label": stage_labels.get(tech.stage, "Unknown"),
        "timestamp": tech.timestamp.strftime("%Y-%m-%d %H:%M"),
        "recent_bars": recent_bars,
        "signal": signal,
    }


def get_allocation_for_profile(profile_name: str) -> dict:
    try:
        profile = RiskProfile(profile_name)
    except ValueError:
        profile = RiskProfile.MODERATE

    table = ALLOCATION_TABLES[profile]
    result = {}
    for score, alloc in sorted(table.items()):
        result[score] = {
            "moderate": alloc.moderate,
            "high": alloc.high,
            "cash": alloc.cash,
        }
    return result
