import os
import sys
import logging

from django.apps import AppConfig

log = logging.getLogger(__name__)


class DashboardConfig(AppConfig):
    name = "web.dashboard"
    verbose_name = "Dashboard"

    def ready(self) -> None:
        # Decide whether this process should own the scheduler.
        #
        # Django dev server (manage.py runserver):
        #   - Spawns a file-watcher process (RUN_MAIN not set) — skip.
        #   - Spawns the actual worker (RUN_MAIN='true') — start scheduler.
        #
        # Gunicorn (production):
        #   - RUN_MAIN is never set, but 'gunicorn' appears in sys.argv.
        #   - We run with --workers=1 so there is only one worker process.
        #   - Start scheduler here.
        #
        # Any other runner (e.g. pytest, shell): skip.

        is_dev_worker = os.environ.get("RUN_MAIN") == "true"
        is_gunicorn = any("gunicorn" in arg for arg in sys.argv)

        if not (is_dev_worker or is_gunicorn):
            return

        from monaimetrics import scheduler
        try:
            scheduler.start()
        except Exception:
            log.exception("Failed to start trading scheduler")
