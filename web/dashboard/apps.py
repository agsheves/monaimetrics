import os
import logging

from django.apps import AppConfig

log = logging.getLogger(__name__)


class DashboardConfig(AppConfig):
    name = "web.dashboard"
    verbose_name = "Dashboard"

    def ready(self) -> None:
        # Django's StatReloader runs the app twice — once as the file-watcher
        # process and once as the main worker. RUN_MAIN='true' is only set in
        # the actual worker. We skip the scheduler in the watcher process to
        # avoid duplicate jobs.
        if os.environ.get("RUN_MAIN") != "true":
            return

        from monaimetrics import scheduler
        try:
            scheduler.start()
        except Exception:
            log.exception("Failed to start trading scheduler")
