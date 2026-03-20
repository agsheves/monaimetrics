"""
Notification system for trade events.

Two delivery mechanisms:
1. File-backed queue (data/notifications.jsonl) — read by dashboard
2. Webhook (optional URL in runtime settings) — POST JSON to any endpoint

Notification types:
    TRADE_EXECUTED      A buy/sell was executed
    STOP_TRIGGERED      Stop-loss or trailing stop fired
    SYSTEM_PAUSED       Circuit breaker activated
    SYSTEM_RESUMED      Circuit breaker cleared
    ASSESSMENT_COMPLETE Assessment cycle finished
    DAILY_DIGEST        End-of-day summary
    WEIGHT_ADJUSTED     Strategy framework weights changed
    RECONCILIATION      Broker/system state mismatch
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import requests

log = logging.getLogger(__name__)

NOTIFICATION_DIR = Path(__file__).resolve().parent.parent / "data"
NOTIFICATION_PATH = NOTIFICATION_DIR / "notifications.jsonl"
READ_TRACKER_PATH = NOTIFICATION_DIR / "notifications_read.json"
_lock = Lock()


def _ensure_dir():
    NOTIFICATION_DIR.mkdir(parents=True, exist_ok=True)


def notify(
    event_type: str,
    title: str,
    message: str,
    symbol: str = "",
    data: dict | None = None,
    priority: str = "standard",
) -> dict:
    """
    Create a notification. Writes to file and optionally sends webhook.
    Priority: critical, high, standard, info
    Returns the notification dict.
    """
    _ensure_dir()

    notification = {
        "id": uuid.uuid4().hex[:12],
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "title": title,
        "message": message,
        "symbol": symbol,
        "priority": priority,
        "data": data or {},
    }

    with _lock:
        try:
            with open(NOTIFICATION_PATH, "a") as f:
                f.write(json.dumps(notification) + "\n")
        except Exception as e:
            log.warning("Notification write failed: %s", e)

    webhook_url = os.environ.get("NOTIFICATION_WEBHOOK_URL", "")
    if not webhook_url:
        try:
            from monaimetrics import runtime_settings
            rt = runtime_settings.load()
            webhook_url = rt.webhook_url
        except Exception:
            pass
    if webhook_url:
        _send_webhook(webhook_url, notification)

    return notification


def _send_webhook(url: str, notification: dict) -> None:
    """POST notification to webhook URL. Fire-and-forget."""
    try:
        requests.post(url, json=notification, timeout=5)
    except Exception as e:
        log.debug("Webhook delivery failed: %s", e)


def get_notifications(
    limit: int = 50,
    since: datetime | None = None,
    unread_only: bool = False,
) -> list[dict]:
    """Read notifications from file."""
    if not NOTIFICATION_PATH.exists():
        return []

    read_ids = _get_read_ids() if unread_only else set()

    notifications = []
    try:
        with open(NOTIFICATION_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    n = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if since:
                    try:
                        ts = datetime.fromisoformat(n["ts"])
                        if ts < since:
                            continue
                    except Exception:
                        continue

                if unread_only and n.get("id") in read_ids:
                    continue

                notifications.append(n)
    except Exception as e:
        log.warning("Notification read failed: %s", e)

    return notifications[-limit:]


def mark_read(notification_ids: list[str]) -> None:
    """Mark notifications as read."""
    _ensure_dir()
    read_ids = _get_read_ids()
    read_ids.update(notification_ids)

    with _lock:
        try:
            READ_TRACKER_PATH.write_text(json.dumps(list(read_ids)))
        except Exception as e:
            log.warning("Read tracker write failed: %s", e)


def mark_all_read() -> None:
    """Mark all current notifications as read."""
    all_notifs = get_notifications(limit=10000)
    ids = [n["id"] for n in all_notifs if "id" in n]
    mark_read(ids)


def unread_count() -> int:
    """Count of unread notifications."""
    return len(get_notifications(unread_only=True, limit=10000))


def _get_read_ids() -> set:
    """Load the set of read notification IDs."""
    if not READ_TRACKER_PATH.exists():
        return set()
    try:
        return set(json.loads(READ_TRACKER_PATH.read_text()))
    except Exception:
        return set()
