"""Web endpoint logic for the backtest page."""

from __future__ import annotations

import logging
from monaimetrics.backtest import BacktestConfig, run_backtest
from monaimetrics.fundamental_data import cache_stats, get_daily_prices

log = logging.getLogger(__name__)


def run_web_backtest(
    symbols: list[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100_000.0,
    risk_profile: str = "moderate",
    max_positions: int = 10,
) -> dict:
    """Run a backtest and return results formatted for the web UI."""
    config = BacktestConfig(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        risk_profile=risk_profile,
        max_positions=max_positions,
    )

    result = run_backtest(config)

    trades_data = [
        {
            "symbol": t.symbol,
            "action": t.action,
            "date": t.date,
            "price": round(t.price, 2),
            "qty": t.qty,
            "value": round(t.value, 2),
            "reason": t.reason,
            "confidence": t.confidence,
        }
        for t in result.trades
    ]

    return {
        "error": result.error,
        "config": {
            "symbols": config.symbols,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "initial_capital": config.initial_capital,
            "risk_profile": config.risk_profile,
            "max_positions": config.max_positions,
        },
        "trades": trades_data,
        "buy_count": sum(1 for t in trades_data if t["action"] == "BUY"),
        "sell_count": sum(1 for t in trades_data if t["action"] == "SELL"),
        "final_value": result.final_value,
        "total_return": result.total_return,
        "total_return_pct": result.total_return_pct,
        "win_count": result.win_count,
        "loss_count": result.loss_count,
        "win_rate": result.win_rate,
        "avg_win_pct": result.avg_win_pct,
        "avg_loss_pct": result.avg_loss_pct,
        "max_drawdown": result.max_drawdown,
        "equity_curve": result.equity_curve,
        "symbols_evaluated": result.symbols_evaluated,
        "days_simulated": result.days_simulated,
    }


def get_backtest_info() -> dict:
    """Return info about available cached data for backtesting."""
    stats = cache_stats()
    return {
        "cached_fundamentals": stats.get("cached_symbols", 0),
        "fresh_fundamentals": stats.get("fresh_symbols", 0),
    }
