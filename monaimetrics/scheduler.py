"""
Automatic trading scheduler.

Runs two recurring jobs:
  - Full assessment cycle: fetches the live universe of tradeable US equities
    from Alpaca, evaluates every symbol against the full strategy ruleset,
    and executes any signals that fire (buy, sell, reduce, stop).
  - Stop check: lightweight price-only scan every minute for stop-loss breaches
    on current positions — acts immediately without waiting for the next cycle.

Both jobs respect market hours and the DRY_RUN flag.
Market hours: 09:30 – 16:00 ET, Monday – Friday.

Environment variables:
  ASSESSMENT_INTERVAL_MINUTES  How often to run the full cycle (default: 5)
  STOP_CHECK_INTERVAL_MINUTES  How often to check stop losses (default: 1)
  SCAN_UNIVERSE_LIMIT          Max symbols to evaluate per cycle (default: 150)
  DRY_RUN                      "true" to log without executing (default: "true")
  MAX_POSITION_USD             Hard cap per order in dollars (default: 2.0)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import pytz

log = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

ASSESSMENT_INTERVAL = int(os.environ.get("ASSESSMENT_INTERVAL_MINUTES", "5"))
STOP_CHECK_INTERVAL = int(os.environ.get("STOP_CHECK_INTERVAL_MINUTES", "1"))
SCAN_UNIVERSE_LIMIT = int(os.environ.get("SCAN_UNIVERSE_LIMIT", "150"))


def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_time <= now < close_time


def run_assessment_job() -> None:
    if not _is_market_open():
        log.debug("Scheduler: market closed, skipping assessment")
        return

    from monaimetrics.config import load_config, RiskProfile
    from monaimetrics.data_input import AlpacaClients, get_tradeable_assets
    from monaimetrics.portfolio_manager import PortfolioManager

    try:
        config = load_config(RiskProfile.MODERATE)
        clients = AlpacaClients(config.api)

        universe = get_tradeable_assets(clients, limit=SCAN_UNIVERSE_LIMIT)
        mode = "DRY RUN" if config.dry_run else "LIVE"

        log.info(
            "Scheduler: starting assessment [%s] — scanning %d symbols from live universe",
            mode, len(universe),
        )

        pm = PortfolioManager(config, clients)
        plan, records = pm.run_assessment(watchlist=universe)

        buys  = sum(1 for r in records if r.signal.action.value == "buy")
        sells = sum(1 for r in records if r.signal.action.value == "sell")
        log.info(
            "Scheduler: assessment complete — %d signal(s) (%d buys, %d sells) [%s]",
            len(records), buys, sells, mode,
        )

    except Exception:
        log.exception("Scheduler: assessment job failed")


def run_stop_check_job() -> None:
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
                "Scheduler: stop check fired %d signal(s) [%s]",
                len(records), mode,
            )

    except Exception:
        log.exception("Scheduler: stop check job failed")


def start(run_assessment: bool = True, run_stops: bool = True) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BackgroundScheduler(timezone=ET)

    if run_assessment:
        scheduler.add_job(
            run_assessment_job,
            trigger=IntervalTrigger(minutes=ASSESSMENT_INTERVAL),
            id="assessment",
            name=f"Full assessment (every {ASSESSMENT_INTERVAL}m)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        log.info("Scheduler: assessment job registered (every %dm)", ASSESSMENT_INTERVAL)

    if run_stops:
        scheduler.add_job(
            run_stop_check_job,
            trigger=IntervalTrigger(minutes=STOP_CHECK_INTERVAL),
            id="stop_check",
            name=f"Stop check (every {STOP_CHECK_INTERVAL}m)",
            replace_existing=True,
            misfire_grace_time=30,
        )
        log.info("Scheduler: stop check job registered (every %dm)", STOP_CHECK_INTERVAL)

    scheduler.start()
    log.info(
        "Scheduler: started — assessment every %dm, stop check every %dm, universe cap %d symbols",
        ASSESSMENT_INTERVAL, STOP_CHECK_INTERVAL, SCAN_UNIVERSE_LIMIT,
    )
