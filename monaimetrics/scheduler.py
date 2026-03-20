"""
Strategic trading scheduler.

Jobs:
  1. Assessment (twice daily, market hours)
     Fetches VIX for cycle scoring, scans the live Alpaca universe,
     evaluates through the full strategy stack, executes or queues.

  2. Stop check (every 15 minutes)
     Lightweight price-only scan. Stop-loss sells fire immediately.

  3. Approved trade execution (every 2 minutes)
     Polls the review queue and executes approved signals.

  4. Daily digest (16:05 ET)
     Summarises the day's activity in the journal and sends notification.

All jobs skip weekends and outside 09:30-16:00 ET (except digest at close).
All respect DRY_RUN — no orders submitted while dry run is active.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import datetime

import pytz

log = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

STOP_CHECK_INTERVAL = int(os.environ.get("STOP_CHECK_INTERVAL_MINUTES", "15"))

ASSESSMENT_TIMES = [
    {"hour": 9,  "minute": 45},
    {"hour": 14, "minute": 0},
]

PLANNING_TIMES = [
    {"hour": 7,  "minute": 0,  "days": "mon-fri"},              # pre-market weekdays
    {"hour": 19, "minute": 0,  "days": "sun,mon,tue,wed,thu,fri"},  # evening + Sunday before Monday
]


def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_time  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now < close_time


def _load_runtime_config():
    """Load runtime settings and build config from them."""
    from monaimetrics import runtime_settings
    from monaimetrics.config import load_config, RiskProfile

    rt = runtime_settings.load()

    try:
        profile = RiskProfile(rt.risk_profile)
    except ValueError:
        profile = RiskProfile.MODERATE

    config = load_config(profile, runtime=asdict(rt))
    return config, rt


def run_assessment_job() -> None:
    """Full strategic assessment with VIX cycle scoring and market breadth."""
    if not _is_market_open():
        log.debug("Scheduler: market closed, skipping assessment")
        return

    from monaimetrics.data_input import AlpacaClients, get_tradeable_assets
    from monaimetrics.portfolio_manager import PortfolioManager
    from monaimetrics import review_queue
    from monaimetrics import trade_journal
    from monaimetrics import notifications
    from monaimetrics.market_intelligence import (
        fetch_vix, compute_cycle_score, compute_market_breadth,
    )

    try:
        config, rt = _load_runtime_config()
        clients = AlpacaClients(config.api)
        mode = "DRY RUN" if config.dry_run else "LIVE"

        # Fetch VIX and compute cycle score
        vix = fetch_vix()
        cycle_score = compute_cycle_score(vix=vix)

        universe = get_tradeable_assets(clients, limit=rt.scan_universe_limit)
        log.info(
            "Scheduler [%s]: assessment starting — %d symbols, VIX≈%s, cycle=%d",
            mode, len(universe),
            f"{vix:.1f}" if vix else "N/A",
            cycle_score,
        )

        pm = PortfolioManager(config, clients, restore_state=True)
        pm.cycle_score = cycle_score

        # Reconcile positions with broker on first run
        pm.reconcile_positions()

        plan, records = pm.run_assessment(
            watchlist=universe,
            execute=not rt.human_review,
        )

        buys    = sum(1 for s in plan.signals if s.action.value == "buy")
        sells   = sum(1 for s in plan.signals if s.action.value == "sell")
        reduces = sum(1 for s in plan.signals if s.action.value == "reduce")

        # Compute market breadth from scanned symbols
        from monaimetrics.data_input import get_technical_data
        stage_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for sig in plan.signals:
            try:
                tech = get_technical_data(sig.symbol, clients=clients)
                stage = tech.stage
                if stage in stage_counts:
                    stage_counts[stage] += 1
            except Exception:
                pass
        breadth = compute_market_breadth(stage_counts)

        # Log assessment to journal
        trade_journal.log_event(
            "ASSESSMENT",
            data={
                "universe_size": len(universe),
                "buys": buys, "sells": sells, "reduces": reduces,
                "cycle_score": cycle_score,
                "vix": vix,
                "breadth": breadth,
                "mode": mode,
                "human_review": rt.human_review,
            },
            reasons=[
                f"Assessed {len(universe)} symbols: "
                f"{buys} buy, {sells} sell, {reduces} reduce",
                f"VIX≈{vix:.1f}, cycle={cycle_score}" if vix else f"VIX=N/A, cycle={cycle_score}",
                f"Breadth: {breadth['signal']} ({breadth['advancing_pct']:.0%} advancing)",
            ],
        )

        if rt.human_review:
            actionable = []
            for sig in plan.signals:
                if sig.action.value in ("buy", "sell", "reduce"):
                    actionable.append({
                        "symbol": sig.symbol,
                        "action": sig.action.value.upper(),
                        "tier": sig.tier.value,
                        "confidence": sig.confidence,
                        "position_size_usd": sig.position_size_usd,
                        "stop_price": sig.stop_price,
                        "target_price": sig.target_price,
                        "reasons": sig.reasons,
                        "price": 0,
                    })
            if actionable:
                review_queue.add_signals(actionable)
                log.info(
                    "Scheduler [%s]: %d signal(s) queued for review "
                    "(%d buy, %d sell, %d reduce)",
                    mode, len(actionable), buys, sells, reduces,
                )
                notifications.notify(
                    "ASSESSMENT_COMPLETE",
                    f"Assessment: {len(actionable)} signal(s) awaiting review",
                    f"Scanned {len(universe)} symbols. "
                    f"{buys} buy, {sells} sell, {reduces} reduce. "
                    f"VIX≈{vix:.1f}, cycle={cycle_score}." if vix else
                    f"Scanned {len(universe)} symbols. "
                    f"{buys} buy, {sells} sell, {reduces} reduce.",
                )
        else:
            log.info(
                "Scheduler [%s]: assessment complete — %d signal(s): "
                "%d buy, %d sell, %d reduce",
                mode, len(records), buys, sells, reduces,
            )
            if buys + sells + reduces > 0:
                notifications.notify(
                    "ASSESSMENT_COMPLETE",
                    f"Assessment: {buys + sells + reduces} trade(s) executed",
                    f"Scanned {len(universe)} symbols. "
                    f"{buys} buy, {sells} sell, {reduces} reduce.",
                )

    except Exception:
        log.exception("Scheduler: assessment job failed")


def run_stop_check_job() -> None:
    """Lightweight stop-loss check with state restoration."""
    if not _is_market_open():
        return

    from monaimetrics.data_input import AlpacaClients
    from monaimetrics.portfolio_manager import PortfolioManager

    try:
        config, _rt = _load_runtime_config()
        clients = AlpacaClients(config.api)
        pm = PortfolioManager(config, clients, restore_state=True)
        records = pm.run_stop_check()

        if records:
            mode = "DRY RUN" if config.dry_run else "LIVE"
            log.info(
                "Scheduler [%s]: stop check — %d stop(s) triggered",
                mode, len(records),
            )

    except Exception:
        log.exception("Scheduler: stop check job failed")


def run_approved_trades_job() -> None:
    """Execute trades approved in the review queue."""
    if not _is_market_open():
        return

    from monaimetrics import review_queue
    from monaimetrics.config import SignalType, SignalUrgency, Tier
    from monaimetrics.data_input import AlpacaClients
    from monaimetrics.portfolio_manager import PortfolioManager
    from monaimetrics.strategy import Signal, TradingPlan

    approved = review_queue.get_approved()
    if not approved:
        return

    try:
        config, _rt = _load_runtime_config()
        clients = AlpacaClients(config.api)
        pm = PortfolioManager(config, clients, restore_state=True)
        mode = "DRY RUN" if config.dry_run else "LIVE"

        signals = []
        for pending in approved:
            action_map = {
                "BUY": SignalType.BUY,
                "SELL": SignalType.SELL,
                "REDUCE": SignalType.REDUCE,
            }
            tier_map = {
                "moderate": Tier.MODERATE,
                "high": Tier.HIGH,
            }
            signals.append(Signal(
                symbol=pending.symbol,
                action=action_map.get(pending.action, SignalType.HOLD),
                urgency=SignalUrgency.STANDARD,
                tier=tier_map.get(pending.tier, Tier.MODERATE),
                confidence=pending.confidence,
                position_size_usd=pending.position_size_usd,
                stop_price=pending.stop_price,
                target_price=pending.target_price,
                reasons=pending.reasons + ["Approved by human review"],
            ))

        from datetime import timezone
        plan = TradingPlan(
            signals=signals,
            cycle_score=pm.cycle_score,
            timestamp=datetime.now(timezone.utc),
        )
        records = pm.execute_plan(plan)

        log.info(
            "Scheduler [%s]: executed %d approved trade(s)",
            mode, len(records),
        )

    except Exception:
        log.exception("Scheduler: approved trades execution failed")


def run_planning_job() -> None:
    """Generate a forward-looking trade plan without executing anything.

    Runs at 07:00 ET (pre-market preview) and 19:00 ET (evening planning).
    Evaluates the full strategy stack in read-only mode, then saves the
    resulting signals to data/latest_plan.json for display in the UI.

    Plans are informational only — actual trades may differ when markets
    open due to live prices, volume, and changing conditions.
    """
    from monaimetrics.data_input import AlpacaClients, get_tradeable_assets
    from monaimetrics.portfolio_manager import PortfolioManager
    from monaimetrics import trade_journal
    from monaimetrics import notifications
    from monaimetrics.market_intelligence import fetch_vix, compute_cycle_score
    from datetime import timezone

    now = datetime.now(ET)
    if now.weekday() == 5:  # Saturday only — Sunday evening is valid for Monday prep
        log.debug("Planner: Saturday, skipping")
        return

    session = "pre-market" if now.hour < 12 else "evening"

    try:
        config, rt = _load_runtime_config()
        clients = AlpacaClients(config.api)

        vix = fetch_vix()
        cycle_score = compute_cycle_score(vix=vix)

        universe = get_tradeable_assets(clients, limit=rt.scan_universe_limit)
        log.info(
            "Planner [%s]: starting — %d symbols, VIX≈%s, cycle=%d",
            session, len(universe),
            f"{vix:.1f}" if vix else "N/A",
            cycle_score,
        )

        pm = PortfolioManager(config, clients, restore_state=True)
        pm.cycle_score = cycle_score
        pm.reconcile_positions()

        # Always read-only — never execute, never touch the review queue
        plan, _ = pm.run_assessment(watchlist=universe, execute=False)

        signals = []
        for sig in plan.signals:
            if sig.action.value in ("buy", "sell", "reduce"):
                signals.append({
                    "symbol": sig.symbol,
                    "action": sig.action.value.upper(),
                    "tier": sig.tier.value if hasattr(sig.tier, "value") else str(sig.tier),
                    "confidence": sig.confidence,
                    "position_size_usd": sig.position_size_usd,
                    "stop_price": sig.stop_price,
                    "target_price": sig.target_price,
                    "reasons": sig.reasons,
                })

        buys    = sum(1 for s in signals if s["action"] == "BUY")
        sells   = sum(1 for s in signals if s["action"] == "SELL")
        reduces = sum(1 for s in signals if s["action"] == "REDUCE")

        plan_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "session": session,
            "vix": round(vix, 2) if vix else None,
            "cycle_score": cycle_score,
            "universe_size": len(universe),
            "signal_count": len(signals),
            "buys": buys,
            "sells": sells,
            "reduces": reduces,
            "signals": signals,
            "disclaimer": (
                "These are planned trades based on current data. "
                "Actual trades may differ when markets open due to live prices, "
                "volume, and changing conditions."
            ),
        }

        trade_journal.save_plan(plan_data)

        trade_journal.log_event(
            "TRADE_PLAN",
            data={
                "session": session,
                "signal_count": len(signals),
                "universe_size": len(universe),
                "vix": vix,
                "cycle_score": cycle_score,
            },
            reasons=[
                f"{session.capitalize()} plan: {len(signals)} signal(s) across {len(universe)} symbols",
                f"VIX≈{vix:.1f}, cycle={cycle_score}" if vix else f"VIX=N/A, cycle={cycle_score}",
                f"{buys} buy, {sells} sell, {reduces} reduce",
            ],
        )

        notifications.notify(
            "TRADE_PLAN",
            f"Trade Plan ({session}): {len(signals)} signal(s)",
            f"{buys} buy, {sells} sell, {reduces} reduce planned. "
            f"Scanned {len(universe)} symbols. View full plan in the app.",
            priority="info",
        )

        log.info(
            "Planner [%s]: complete — %d signal(s): %d buy, %d sell, %d reduce",
            session, len(signals), buys, sells, reduces,
        )

    except Exception:
        log.exception("Scheduler: planning job failed")


def run_daily_digest_job() -> None:
    """End-of-day summary: log digest and send notification."""
    from monaimetrics import trade_journal
    from monaimetrics import notifications

    try:
        summary = trade_journal.daily_summary()

        trade_journal.log_event(
            "DIGEST",
            data=summary,
            reasons=[
                f"Day summary: {summary['buys']} buys, {summary['sells']} sells, "
                f"{summary['stops_triggered']} stops triggered",
            ],
        )

        if summary["total_events"] > 0:
            notifications.notify(
                "DAILY_DIGEST",
                f"Daily Digest: {summary['buys']}B / {summary['sells']}S",
                f"Today: {summary['buys']} buys (${summary['buy_value']:,.0f}), "
                f"{summary['sells']} sells (${summary['sell_value']:,.0f}), "
                f"{summary['stops_triggered']} stops. "
                f"Symbols: {', '.join(summary['symbols_traded']) or 'none'}.",
                priority="info",
            )

        log.info("Scheduler: daily digest — %d events", summary["total_events"])

    except Exception:
        log.exception("Scheduler: daily digest job failed")


def start(run_assessment: bool = True, run_stops: bool = True) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from monaimetrics import trade_journal

    scheduler = BackgroundScheduler(timezone=ET)

    # Log system startup
    trade_journal.log_event(
        "SYSTEM", action="STARTUP",
        reasons=["Trading scheduler started"],
    )

    # Trade planning jobs at 07:00 and 19:00 ET (Mon-Fri, read-only, no execution)
    for i, t in enumerate(PLANNING_TIMES):
        scheduler.add_job(
            run_planning_job,
            trigger=CronTrigger(
                day_of_week=t["days"],
                hour=t["hour"],
                minute=t["minute"],
                timezone=ET,
            ),
            id=f"planning_{i}",
            name=f"Trade plan at {t['hour']:02d}:{t['minute']:02d} ET ({t['days']})",
            replace_existing=True,
            misfire_grace_time=300,
        )
    log.info(
        "Scheduler: planning jobs registered — 07:00 Mon-Fri, 19:00 Sun-Fri (ET)"
    )

    if run_assessment:
        for i, t in enumerate(ASSESSMENT_TIMES):
            scheduler.add_job(
                run_assessment_job,
                trigger=CronTrigger(
                    day_of_week="mon-fri",
                    hour=t["hour"],
                    minute=t["minute"],
                    timezone=ET,
                ),
                id=f"assessment_{i}",
                name=f"Assessment at {t['hour']:02d}:{t['minute']:02d} ET",
                replace_existing=True,
                misfire_grace_time=300,
            )
        times_str = ", ".join(f"{t['hour']:02d}:{t['minute']:02d}" for t in ASSESSMENT_TIMES)
        log.info("Scheduler: assessment registered at %s ET (Mon-Fri)", times_str)

    if run_stops:
        scheduler.add_job(
            run_stop_check_job,
            trigger=IntervalTrigger(minutes=STOP_CHECK_INTERVAL),
            id="stop_check",
            name=f"Stop check (every {STOP_CHECK_INTERVAL}m)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        log.info("Scheduler: stop check registered (every %dm)", STOP_CHECK_INTERVAL)

    # Approved trades every 2 minutes
    scheduler.add_job(
        run_approved_trades_job,
        trigger=IntervalTrigger(minutes=2),
        id="approved_trades",
        name="Execute approved trades (every 2m)",
        replace_existing=True,
        misfire_grace_time=60,
    )
    log.info("Scheduler: approved trade execution registered (every 2m)")

    # Daily digest at 16:05 ET (just after market close)
    scheduler.add_job(
        run_daily_digest_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=16, minute=5,
            timezone=ET,
        ),
        id="daily_digest",
        name="Daily digest at 16:05 ET",
        replace_existing=True,
        misfire_grace_time=300,
    )
    log.info("Scheduler: daily digest registered at 16:05 ET")

    scheduler.start()
    log.info(
        "Scheduler: running — assessments 2x/day, stops every %dm, "
        "digest at close",
        STOP_CHECK_INTERVAL,
    )
