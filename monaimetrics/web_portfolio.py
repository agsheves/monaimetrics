from __future__ import annotations

import logging
from monaimetrics.config import load_config, RiskProfile, ALLOCATION_TABLES
from monaimetrics.data_input import (
    AlpacaClients, get_account, get_positions, get_technical_data,
    get_tradeable_assets,
)
from monaimetrics.strategy import evaluate_opportunity
from monaimetrics.trading_interface import get_open_orders
from monaimetrics import calculators

log = logging.getLogger(__name__)


def _build_stop_map(clients: AlpacaClients) -> dict[str, float]:
    """Scan open orders and return a map of symbol → current stop price."""
    stop_map: dict[str, float] = {}
    try:
        for order in get_open_orders(clients):
            if (
                order.symbol
                and order.side == "sell"
                and order.order_type in ("stop", "stop_limit")
                and order.stop_price is not None
                and order.stop_price > 0
            ):
                existing = stop_map.get(order.symbol)
                if existing is None or order.stop_price > existing:
                    stop_map[order.symbol] = order.stop_price
    except Exception as e:
        log.warning("Could not fetch open orders for stop visibility: %s", e)
    return stop_map


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

    stop_map = _build_stop_map(clients)
    stop_pct = config.moderate_tier.stop_loss
    profit_pct = config.moderate_tier.profit_target
    ratchet_step = config.ratchet_step_pct

    def _position_dict(p) -> dict:
        entry = p.avg_entry_price
        stop_price = round(stop_map.get(p.symbol, entry * (1 - stop_pct)), 2)
        target_price = round(entry * (1 + profit_pct), 2)
        ratchet_raw = calculators.ratchet_stop_level(entry, p.current_price, ratchet_step)
        ratchet_level = round(ratchet_raw, 2) if ratchet_raw is not None else None
        return {
            "symbol": p.symbol,
            "qty": p.qty,
            "avg_entry_price": entry,
            "current_price": p.current_price,
            "market_value": p.market_value,
            "unrealized_pl": p.unrealized_pl,
            "unrealized_pl_pct": p.unrealized_pl_pct,
            "stop_price": stop_price,
            "target_price": target_price,
            "ratchet_level": ratchet_level,
        }

    return {
        "connected": connected,
        "error": None,
        "account": {
            "portfolio_value": account.portfolio_value,
            "cash": account.cash,
            "buying_power": account.buying_power,
            "status": account.status,
        },
        "positions": [_position_dict(p) for p in positions],
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
                "change_pct": ((b.close - b.open) / b.open * 100) if b.open > 0 else 0,
            }
            for b in bars[-10:]
        ]
    except Exception:
        recent_bars = []

    stage_labels = {1: "Basing", 2: "Advancing", 3: "Topping", 4: "Declining"}

    signal = None
    try:
        from monaimetrics.config import Tier
        account = get_account(clients)
        available_capital = account.buying_power if account.buying_power > 0 else account.cash
        sig = evaluate_opportunity(
            symbol=symbol,
            tech=tech,
            tier=Tier.MODERATE,
            available_capital=available_capital,
            config=config,
        )
        signal = {
            "action": sig.action.value.upper(),
            "tier": sig.tier.value,
            "confidence": sig.confidence,
            "urgency": sig.urgency.value,
            "reasons": sig.reasons,
            "position_size_usd": round(sig.position_size_usd, 2),
            "stop_price": round(sig.stop_price, 2) if sig.stop_price else None,
            "target_price": round(sig.target_price, 2) if sig.target_price else None,
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


def scan_for_opportunities(
    risk_profile: str = "moderate",
    symbols: list[str] | None = None,
) -> dict:
    try:
        profile = RiskProfile(risk_profile)
    except ValueError:
        profile = RiskProfile.MODERATE

    config = load_config(profile)
    clients = AlpacaClients(config.api)

    try:
        account = get_account(clients)
    except Exception as e:
        return {"error": str(e), "buy_signals": [], "other_signals": [], "skipped_signals": [],
                "scan_errors": [], "scanned": [], "limit_usd": config.max_share_price_usd,
                "universe_size": 0, "profile": profile.value}

    if symbols:
        watchlist = symbols
        universe_size = len(symbols)
    else:
        watchlist = get_tradeable_assets(clients, limit=150)
        universe_size = len(watchlist)

    results = []
    errors = []

    from monaimetrics.data_input import get_technical_data
    from monaimetrics.strategy import evaluate_opportunity
    from monaimetrics.config import Tier

    available_capital = account.buying_power if account.buying_power > 0 else account.cash

    for sym in watchlist:
        try:
            tech = get_technical_data(sym, clients=clients)
            signal = evaluate_opportunity(
                symbol=sym,
                tech=tech,
                tier=Tier.MODERATE,
                available_capital=available_capital,
                config=config,
            )
            if signal is None:
                continue

            results.append({
                "symbol": sym,
                "action": signal.action.value.upper(),
                "tier": signal.tier.value,
                "confidence": signal.confidence,
                "urgency": signal.urgency.value,
                "reasons": signal.reasons,
                "position_size_usd": round(signal.position_size_usd, 2),
                "stop_price": round(signal.stop_price, 2) if signal.stop_price else None,
                "target_price": round(signal.target_price, 2) if signal.target_price else None,
                "price": round(tech.price, 2),
                "stage": tech.stage,
                "stage_label": {1: "Basing", 2: "Advancing", 3: "Topping", 4: "Declining"}.get(tech.stage, "Unknown"),
                "volume_ratio": round(tech.volume_ratio, 2) if tech.volume_ratio else None,
            })
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)})
            log.warning("Scan failed for %s: %s", sym, e)

    def _is_skipped(r: dict) -> bool:
        return any("— skipping" in reason for reason in r.get("reasons", []))

    buy_signals = [r for r in results if r["action"] == "BUY"]
    buy_signals.sort(key=lambda r: r["confidence"], reverse=True)
    non_buy = [r for r in results if r["action"] != "BUY"]
    other_signals = [r for r in non_buy if not _is_skipped(r)]
    skipped_signals = [r for r in non_buy if _is_skipped(r)]

    return {
        "error": None,
        "buy_signals": buy_signals,
        "other_signals": other_signals,
        "skipped_signals": skipped_signals,
        "scan_errors": errors,
        "scanned": watchlist,
        "universe_size": universe_size,
        "limit_usd": config.max_share_price_usd,
        "dry_run": config.dry_run,
        "profile": profile.value,
        "account": {
            "portfolio_value": account.portfolio_value,
            "cash": account.cash,
        },
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
