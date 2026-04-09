"""
Strategic trading scheduler.

Two jobs:

  1. Assessment (hourly, market hours)
     Runs every hour on the :45 mark, from 09:45 through 15:45 ET, Mon–Fri.
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

A singleton PortfolioManager is kept alive for the lifetime of the process.
This preserves managed_positions, stop_order_ids, circuit-breaker counters,
and other in-memory state across scheduler runs. On every call the config is
re-read from env so that RISK_PROFILE and other settings take effect without
a restart. Positions are bootstrapped from Alpaca on first use via
load_from_broker(), then kept in sync on every subsequent assessment and
stop-check run.

Environment variables:
  STOP_CHECK_INTERVAL_MINUTES  Stop-loss check frequency (default: 15)
  SCAN_UNIVERSE_LIMIT          Max symbols per assessment cycle (default: 150)
  DRY_RUN                      "true" to observe only (default: "true")
  MAX_SHARE_PRICE_USD          Skip stocks above this price per share (default: 25.0)
  RISK_PROFILE                 Risk profile for the scheduler (default: "moderate")
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

# ---------------------------------------------------------------------------
# Singleton PortfolioManager
# ---------------------------------------------------------------------------

_pm = None  # type: ignore[var-annotated]  # PortfolioManager | None


def _get_or_create_pm():
    """Return the singleton PortfolioManager, creating it on first call.

    Config is re-read on every call so that RISK_PROFILE and other env
    changes take effect without a server restart.  The position list and all
    in-memory state are preserved across calls.
    """
    global _pm

    from monaimetrics.config import load_config_from_env
    from monaimetrics.data_input import AlpacaClients
    from monaimetrics.portfolio_manager import PortfolioManager

    config = load_config_from_env()
    clients = AlpacaClients(config.api)

    if _pm is None:
        _pm = PortfolioManager(config, clients)
        _pm.load_from_broker()
        log.info(
            "Scheduler: singleton PortfolioManager created — %d position(s) "
            "bootstrapped from broker (profile=%s, dry_run=%s)",
            len(_pm.managed_positions),
            config.profile.value,
            config.dry_run,
        )
    else:
        # Refresh config and clients so any env changes (e.g. RISK_PROFILE)
        # are picked up without rebuilding the full PM.
        _pm.config = config
        _pm.clients = clients

    return _pm


# ---------------------------------------------------------------------------
# Market hours helper
# ---------------------------------------------------------------------------

def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_time  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now < close_time


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

def run_assessment_job() -> None:
    """Full strategic assessment — evaluates the live universe and executes signals."""
    if not _is_market_open():
        log.debug("Scheduler: market closed, skipping assessment")
        return

    from monaimetrics.data_input import get_tradeable_assets

    try:
        pm = _get_or_create_pm()
        config = pm.config
        mode = "DRY RUN" if config.dry_run else "LIVE"

        universe = get_tradeable_assets(pm.clients, limit=SCAN_UNIVERSE_LIMIT)
        log.info(
            "Scheduler [%s]: assessment starting — %d symbols in universe (profile=%s, "
            "tracking %d position(s))",
            mode, len(universe), config.profile.value, len(pm.managed_positions),
        )

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

    try:
        pm = _get_or_create_pm()
        records = pm.run_stop_check()

        if records:
            mode = "DRY RUN" if pm.config.dry_run else "LIVE"
            log.info(
                "Scheduler [%s]: stop check — %d stop(s) triggered",
                mode, len(records),
            )

    except Exception:
        log.exception("Scheduler: stop check job failed")


# ---------------------------------------------------------------------------
# Scheduler startup
# ---------------------------------------------------------------------------

def start(run_assessment: bool = True, run_stops: bool = True) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BackgroundScheduler(timezone=ET)

    if run_assessment:
        # Hourly assessment: every hour at :45, from 09:45 through 15:45 ET (Mon–Fri)
        scheduler.add_job(
            run_assessment_job,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour="9-15",
                minute=45,
                timezone=ET,
            ),
            id="assessment_hourly",
            name="Assessment (hourly :45 ET, 09:45–15:45)",
            replace_existing=True,
            misfire_grace_time=300,
        )
        log.info("Scheduler: hourly assessment registered at :45 ET (09:45–15:45, Mon–Fri)")

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
        "Scheduler: running — hourly assessments (:45 ET, 09:45–15:45), stop checks every %dm, universe cap %d",
        STOP_CHECK_INTERVAL, SCAN_UNIVERSE_LIMIT,
    )
