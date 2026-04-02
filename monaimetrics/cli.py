"""
Simple text-only CLI dashboard. Run with: python -m monaimetrics.cli
"""

from __future__ import annotations

import sys
import logging
from datetime import datetime, timezone

from monaimetrics.config import load_config, Tier, SignalType
from monaimetrics.data_input import AlpacaClients, get_account
from monaimetrics.portfolio_manager import PortfolioManager
from monaimetrics.reporting import Reporter

logging.basicConfig(level=logging.WARNING)


BANNER = """
========================================
  MONAIMETRICS  —  Trading Dashboard
========================================
  Mode: {mode}
  Connected: {connected}
"""

MENU = """
  [1]  Portfolio Summary
  [2]  Activity Report
  [3]  Growth Report
  [4]  Plan Trades
  [Q]  Quit
"""


def divider(title: str = ""):
    if title:
        print(f"\n--- {title} {'-' * max(0, 35 - len(title))}")
    else:
        print("-" * 40)


def fmt_pct(value: float) -> str:
    if value >= 0:
        return f"+{value:.1%}"
    return f"{value:.1%}"


def fmt_usd(value: float) -> str:
    return f"${value:,.2f}"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def show_portfolio(pm: PortfolioManager, reporter: Reporter):
    divider("PORTFOLIO SUMMARY")

    s = pm.summary()
    print(f"  Portfolio Value:  {fmt_usd(s['portfolio_value'])}")
    print(f"  Cash:             {fmt_usd(s['cash'])}")
    print(f"  Peak Value:       {fmt_usd(s['peak_value'])}")
    print()
    print(f"  Moderate Tier:    {fmt_usd(s['moderate_value'])}")
    print(f"  High-Risk Tier:   {fmt_usd(s['high_value'])}")
    print(f"  Positions:        {s['positions']}")
    print()

    if s['paused']:
        print(f"  ** PAUSED: {s['pause_reason']} **")
        print()

    # Allocation
    total = s['portfolio_value'] if s['portfolio_value'] > 0 else 1
    cash_pct = s['cash'] / total
    mod_pct = s['moderate_value'] / total
    high_pct = s['high_value'] / total

    print("  Allocation:")
    print(f"    Moderate:  {mod_pct:.0%}")
    print(f"    High:      {high_pct:.0%}")
    print(f"    Cash:      {cash_pct:.0%}")
    print()

    # Positions detail
    if pm.managed_positions:
        print(f"  {'Symbol':<8} {'Tier':<10} {'Qty':>6} {'Entry':>10} {'Current':>10} {'Gain':>8} {'Weeks':>5}")
        print(f"  {'------':<8} {'----':<10} {'---':>6} {'-----':>10} {'-------':>10} {'----':>8} {'-----':>5}")
        for pos in pm.managed_positions:
            gain = (pos.current_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
            print(
                f"  {pos.symbol:<8} {pos.tier.value:<10} {pos.qty:>6.0f} "
                f"{fmt_usd(pos.entry_price):>10} {fmt_usd(pos.current_price):>10} "
                f"{fmt_pct(gain):>8} {pos.weeks_held:>5}"
            )
    else:
        print("  No managed positions.")
    print()


def show_activity(reporter: Reporter):
    divider("ACTIVITY REPORT")

    if not reporter.trades:
        print("  No trades recorded yet.")
        print()
        return

    print(reporter.trade_summary())
    print()

    # Recent trades (last 10)
    recent = reporter.trades[-10:]
    if recent:
        divider("Recent Trades")
        print(f"  {'Time':<20} {'Symbol':<8} {'Action':<6} {'Tier':<10} {'Price':>10} {'Gain':>8} {'Reason'}")
        print(f"  {'----':<20} {'------':<8} {'------':<6} {'----':<10} {'-----':>10} {'----':>8} {'------'}")
        for t in reversed(recent):
            ts = t.timestamp[:19].replace("T", " ")
            price_str = fmt_usd(t.price) if t.price else "—"
            gain_str = fmt_pct(t.gain_pct) if t.gain_pct is not None else "—"
            reason = t.reasons[0][:30] if t.reasons else ""
            print(
                f"  {ts:<20} {t.symbol:<8} {t.action:<6} {t.tier:<10} "
                f"{price_str:>10} {gain_str:>8} {reason}"
            )
    print()


def show_growth(reporter: Reporter):
    divider("GROWTH REPORT")

    perf = reporter.calculate_performance(days=9999)

    print(f"  Total Return:     {fmt_pct(perf.total_return_pct)}")
    print(f"  Total Trades:     {perf.total_trades}")
    print(f"  Win Rate:         {perf.win_rate:.0%} ({perf.wins}W / {perf.losses}L)")
    print()
    print(f"  Avg Win:          {fmt_pct(perf.avg_win_pct)}")
    print(f"  Avg Loss:         {fmt_pct(perf.avg_loss_pct)}")
    print(f"  Best Trade:       {fmt_pct(perf.best_trade_pct)}")
    print(f"  Worst Trade:      {fmt_pct(perf.worst_trade_pct)}")
    print()

    # Tier breakdown
    tier_perf = reporter.tier_performance()
    print("  Tier Breakdown:")
    for name, tp in tier_perf.items():
        if tp.trades > 0:
            print(
                f"    {name:<10} {tp.trades} trades, "
                f"{tp.win_rate:.0%} win rate, "
                f"{fmt_pct(tp.avg_gain_pct)} avg gain"
            )
        else:
            print(f"    {name:<10} No trades")
    print()

    # Snapshots summary
    if len(reporter.snapshots) >= 2:
        first = reporter.snapshots[0]
        last = reporter.snapshots[-1]
        print(f"  Snapshots:        {len(reporter.snapshots)}")
        print(f"  First:            {fmt_usd(first.portfolio_value)} ({first.timestamp[:10]})")
        print(f"  Latest:           {fmt_usd(last.portfolio_value)} ({last.timestamp[:10]})")
    else:
        print("  No portfolio snapshots yet.")
    print()


def plan_trades(pm: PortfolioManager, reporter: Reporter):
    divider("PLAN TRADES")

    symbols_input = input("  Enter symbols (comma-separated, or blank for AAPL): ").strip()
    if not symbols_input:
        watchlist = ["AAPL"]
    else:
        watchlist = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

    print(f"\n  Running assessment for: {', '.join(watchlist)}")
    print("  Fetching data and running strategy...")
    print()

    try:
        plan, records = pm.run_assessment(watchlist=watchlist)
    except Exception as e:
        print(f"  Error: {e}")
        print()
        return

    # Take a snapshot for the reporter
    try:
        account = get_account(pm.clients)
        tv = pm.tier_values()
        reporter.take_snapshot(account, pm.managed_positions, tv)
    except Exception:
        pass

    if not plan.signals:
        print("  No signals generated.")
        print()
        return

    print(f"  Cycle Score: {plan.cycle_score}")
    print(f"  Signals: {len(plan.signals)}")
    print()

    print(f"  {'Symbol':<8} {'Decision':<8} {'Urgency':<12} {'Tier':<10} {'Conf':>5} {'Size':>10} {'Stop':>10} {'Target':>10}")
    print(f"  {'------':<8} {'--------':<8} {'-------':<12} {'----':<10} {'----':>5} {'----':>10} {'----':>10} {'------':>10}")

    for sig in plan.signals:
        size_str = fmt_usd(sig.position_size_usd) if sig.position_size_usd > 0 else "—"
        stop_str = fmt_usd(sig.stop_price) if sig.stop_price > 0 else "—"
        target_str = fmt_usd(sig.target_price) if sig.target_price > 0 else "—"
        action_label = sig.action.value.upper()
        print(
            f"  {sig.symbol:<8} {action_label:<8} {sig.urgency.value:<12} "
            f"{sig.tier.value:<10} {sig.confidence:>5} "
            f"{size_str:>10} {stop_str:>10} {target_str:>10}"
        )
        for reason in sig.reasons:
            print(f"     Why:  {reason}")
    print()

    # Action legend
    actions_seen = {sig.action for sig in plan.signals}
    legend_items = []
    if SignalType.BUY in actions_seen:
        legend_items.append("BUY = open a new position")
    if SignalType.SELL in actions_seen:
        legend_items.append("SELL = close the position")
    if SignalType.WATCH in actions_seen:
        legend_items.append("WATCH = on radar, not ready to buy yet")
    if SignalType.HOLD in actions_seen:
        legend_items.append("HOLD = keep current position, no action needed")
    if SignalType.REDUCE in actions_seen:
        legend_items.append("REDUCE = trim position size")
    if legend_items:
        print("  " + "  |  ".join(legend_items))
        print()

    # Execution results
    divider("Execution Results")
    for rec in records:
        status = "—"
        if rec.order_result:
            status = rec.order_result.status
            if rec.order_result.message:
                status += f" ({rec.order_result.message})"
        elif rec.notes:
            status = rec.notes

        # Log to reporter
        gain = None
        if rec.signal.action in (SignalType.SELL, SignalType.REDUCE):
            pos = next(
                (p for p in pm.managed_positions if p.symbol == rec.signal.symbol),
                None,
            )
            if pos and pos.entry_price > 0:
                gain = (pos.current_price - pos.entry_price) / pos.entry_price
        reporter.record_trade(rec.signal, rec.order_result, exit_gain_pct=gain)

        print(f"  {rec.signal.symbol:<8} {rec.signal.action.value:<8} -> {status}")
    print()


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------

def main():
    print("\n  Connecting to Alpaca...")
    config = load_config()
    clients = AlpacaClients(config.api)
    pm = PortfolioManager(config, clients)
    reporter = Reporter()

    # Quick connection check
    try:
        account = get_account(clients)
        connected = True
        pm.peak_value = account.portfolio_value
    except Exception as e:
        print(f"  Warning: Could not connect to Alpaca: {e}")
        connected = False

    mode = "DRY RUN" if config.dry_run else "LIVE"
    print(BANNER.format(mode=mode, connected="Yes" if connected else "No"))

    while True:
        print(MENU)
        choice = input("  Choose [1-4, Q]: ").strip().lower()

        if choice == "1":
            show_portfolio(pm, reporter)
        elif choice == "2":
            show_activity(reporter)
        elif choice == "3":
            show_growth(reporter)
        elif choice == "4":
            plan_trades(pm, reporter)
        elif choice in ("q", "quit", "exit"):
            print("\n  Goodbye.\n")
            break
        else:
            print("  Invalid choice.")


if __name__ == "__main__":
    main()
