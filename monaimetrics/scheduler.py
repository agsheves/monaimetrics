"""
Strategic trading scheduler.

Two jobs:

  1. Assessment (twice daily, market hours)
     Runs at 09:45 ET (after open volatility settles) and 14:00 ET.
     Fetches the live Alpaca universe of tradeable US equities, evaluates
     every symbol through the full strategy stack (stage analysis, Kelly
     sizing, cycle positioning, risk tier allocation), then executes any
     signals that meet the rules (buy, sell, reduce).

  2. Stop check (every STOP_CHECK_INTERVAL_MINUTES, default 15)
     Lightweight price-only scan of current positions.
     Fires stop-loss and trailing-stop sells immediately — does not wait
     for the next full assessment.

Both jobs skip weekends and outside 09:30–16:00 ET.
Both respect DRY_RUN — no orders are submitted while dry run is active.

Environment variables:
  STOP_CHECK_INTERVAL_MINUTES  Stop-loss check frequency (default: 15)
  SCAN_UNIVERSE_LIMIT          Max symbols per assessment cycle (default: 150)
  DRY_RUN                      "true" to observe only (default: "true")
  MAX_POSITION_USD             Hard dollar cap per order (default: 2.0)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import pytz

log = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

STOP_CHECK_INTERVAL = int(os.environ.get("STOP_CHECK_INTERVAL_MINUTES", "15"))
SCAN_UNIVERSE_LIMIT = int(os.environ.get("SCAN_UNIVERSE_LIMIT", "150"))

# Twice-daily assessment times (ET)
ASSESSMENT_TIMES = [
    {"hour": 9,  "minute": 45},   # morning — after open volatility settles
    {"hour": 14, "minute": 0},    # afternoon — mid-session review
]


def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_time  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now < close_time


def run_assessment_job() -> None:
    """Full strategic assessment — evaluates the live universe and executes signals."""
    if not _is_market_open():
        log.debug("Scheduler: market closed, skipping assessment")
        return

    from monaimetrics.config import load_config, RiskProfile
    from monaimetrics.data_input import AlpacaClients, get_tradeable_assets
    from monaimetrics.portfolio_manager import PortfolioManager

    try:
        config = load_config(RiskProfile.MODERATE)
        clients = AlpacaClients(config.api)
        mode = "DRY RUN" if config.dry_run else "LIVE"

        universe = get_tradeable_assets(clients, limit=SCAN_UNIVERSE_LIMIT)
        log.info(
            "Scheduler [%s]: assessment starting — %d symbols in universe",
            mode, len(universe),
        )

        pm = PortfolioManager(config, clients)
        plan, records = pm.run_assessment(watchlist=universe)

        buys    = sum(1 for r in records if r.signal.action.value == "buy")
        sells   = sum(1 for r in records if r.signal.action.value == "sell")
        reduces = sum(1 for r in records if r.signal.action.value == "reduce")
        log.info(
            "Scheduler [%s]: assessment complete — %d signal(s): %d buy, %d sell, %d reduce",
            mode, len(records), buys, sells, reduces,
        )

    except Exception:
        log.exception("Scheduler: assessment job failed")


def run_stop_check_job() -> None:
    """Lightweight stop-loss check on current positions."""
    if not _is_market_open():
        return

    from monaimetrics.config import load_config, RiskProfile
    from monaimetrics.data_input import AlpacaClients
    from monaimetrics.portfolio_manager import PortfolioManager

    try:
        config = load_config(RiskProfile.MODERATE)
        clients = AlpacaClients(config.api)
        pm = PortfolioManager(config, clients)
        records = pm.run_stop_check()

        if records:
            mode = "DRY RUN" if config.dry_run else "LIVE"
            log.info(
                "Scheduler [%s]: stop check — %d stop(s) triggered",
                mode, len(records),
            )

    except Exception:
        log.exception("Scheduler: stop check job failed")


def start(run_assessment: bool = True, run_stops: bool = True) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BackgroundScheduler(timezone=ET)

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
        log.info("Scheduler: assessment registered at %s ET (Mon–Fri)", times_str)

    if run_stops:
        scheduler.add_job(
            run_stop_check_job,
            trigger=IntervalTrigger(minutes=STOP_CHECK_INTERVAL),
            id="stop_check",
            name=f"Stop check (every {STOP_CHECK_INTERVAL}m)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        log.info("Scheduler: stop check registered (every %dm, market hours only)", STOP_CHECK_INTERVAL)

    scheduler.start()
    log.info(
        "Scheduler: running — assessments 2×/day, stop checks every %dm, universe cap %d",
        STOP_CHECK_INTERVAL, SCAN_UNIVERSE_LIMIT,
    )
