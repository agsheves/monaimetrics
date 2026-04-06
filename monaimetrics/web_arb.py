from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def get_arb_dashboard_data() -> dict:
    from monaimetrics.prediction_trading_arb import (
        load_arb_config,
        KalshiClient,
        ArbLedger,
        scan_and_evaluate,
        check_settlements,
    )

    config = load_arb_config()

    if not config.kalshi_api_key:
        return {
            "connected": False,
            "error":
            "Kalshi API key not configured. Add KALSHI_API_KEY to your environment.",
            "config": _config_summary(config),
        }

    if not config.kalshi_private_key_path and not config.kalshi_private_key_pem:
        pem_env = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
        if pem_env:
            config.kalshi_private_key_pem = pem_env
        else:
            return {
                "connected": False,
                "error":
                "Kalshi private key not configured. Add KALSHI_PRIVATE_KEY_PEM to your environment.",
                "config": _config_summary(config),
            }

    try:
        client = KalshiClient(config)
        balance_cents = client.get_balance()
        positions = client.get_positions()
        connected = True
    except Exception as e:
        log.warning("Could not connect to Kalshi: %s", e)
        return {
            "connected": False,
            "error": str(e),
            "config": _config_summary(config),
        }

    ledger = ArbLedger(
        starting_balance_cents=balance_cents,
        current_balance_cents=balance_cents,
    )

    opportunities = []
    try:
        opportunities = scan_and_evaluate(client, config)
    except Exception as e:
        log.warning("Arb scan error: %s", e)

    opps_data = []
    for opp in opportunities[:10]:
        opps_data.append({
            "event_ticker": opp.event_ticker,
            "side": opp.side.value.upper(),
            "markets": [m.title for m in opp.markets],
            "prices_cents": opp.prices_cents,
            "combined_cost_cents": opp.combined_cost_cents,
            "net_profit_cents": opp.net_profit_cents,
            "net_profit_pct": round(opp.net_profit_pct * 100, 2),
            "contracts": opp.contracts,
            "total_fee_cents": opp.total_fee_cents,
        })

    return {
        "connected": connected,
        "error": None,
        "balance_usd": balance_cents / 100,
        "positions": positions,
        "positions_count": len(positions),
        "opportunities": opps_data,
        "opportunities_count": len(opportunities),
        "ledger": ledger.summary(),
        "config": _config_summary(config),
    }


def _config_summary(config) -> dict:
    return {
        "mode": "Demo" if config.use_demo else "Live",
        "dry_run": config.dry_run,
        "scan_categories": list(config.scan_categories),
        "min_profit_pct": config.min_profit_pct * 100,
        "max_contracts_per_leg": config.max_contracts_per_leg,
        "max_open_arbs": config.max_open_arbs,
        "max_daily_trades": config.max_daily_trades,
        "max_capital_deployed_usd": config.max_capital_deployed_cents / 100,
    }
