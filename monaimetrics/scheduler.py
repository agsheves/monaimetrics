"""
Automatic trading scheduler.

Runs two recurring jobs:
  - Full assessment cycle: evaluates positions, scans watchlist, executes signals
  - Stop check: lightweight price-only scan for stop-loss breaches

Both jobs respect market hours and the DRY_RUN flag.
Market hours: 09:30 – 16:00 ET, Monday – Friday.

Environment variables:
  ASSESSMENT_INTERVAL_MINUTES  How often to run the full cycle (default: 5)
  STOP_CHECK_INTERVAL_MINUTES  How often to check stop losses (default: 1)
  WATCHLIST_SYMBOLS            Comma-separated symbols to scan for new buys
                               (default: empty — only manages current positions)
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


def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_time <= now < close_time


def _get_watchlist() -> list[str]:
    raw = os.environ.get("WATCHLIST_SYMBOLS", "").strip()
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def run_assessment_job() -> None:
    if not _is_market_open():
        log.debug("Scheduler: market closed, skipping assessment")
        return

    from monaimetrics.config import load_config, RiskProfile
    from monaimetrics.data_input import AlpacaClients
    from monaimetrics.portfolio_manager import PortfolioManager

    try:
        config = load_config(RiskProfile.MODERATE)
        clients = AlpacaClients(config.api)
        pm = PortfolioManager(config, clients)

        watchlist = _get_watchlist()
        mode = "DRY RUN" if config.dry_run else "LIVE"
        log.info(
            "Scheduler: starting assessment [%s] watchlist=%s",
            mode, watchlist or "(positions only)",
        )

        plan, records = pm.run_assessment(watchlist=watchlist or None)

        buys  = sum(1 for r in records if r.signal.action.value == "buy")
        sells = sum(1 for r in records if r.signal.action.value == "sell")
        log.info(
            "Scheduler: assessment complete — %d signals (%d buys, %d sells) [%s]",
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
    log.info("Scheduler: started (assessment=%dm, stop_check=%dm)", ASSESSMENT_INTERVAL, STOP_CHECK_INTERVAL)
