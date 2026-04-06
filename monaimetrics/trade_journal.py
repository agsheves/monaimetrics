"""
Append-only trade journal.

Every signal evaluation, execution, stop trigger, circuit breaker event,
and system event is recorded as a timestamped JSON Lines entry in
data/journal.jsonl. Survives restarts, searchable, human-readable.

Event types:
    SIGNAL          Strategy generated a signal
    EXECUTION       Trade was executed (or rejected)
    STOP_TRIGGERED  Stop-loss or trailing stop fired
    CIRCUIT_BREAKER Circuit breaker activated/deactivated
    ASSESSMENT      Full assessment cycle completed
    SYSTEM          System-level events (startup, pause, resume)
    DIGEST          Daily summary
    WEIGHT_ADJUST   Framework weight changed
    RECONCILIATION  Broker/system state mismatch resolved
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

JOURNAL_DIR = Path(__file__).resolve().parent.parent / "data"
JOURNAL_PATH = JOURNAL_DIR / "journal.jsonl"
_lock = Lock()


def _ensure_dir():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def log_event(
    event_type: str,
    symbol: str = "",
    action: str = "",
    data: dict | None = None,
    reasons: list[str] | None = None,
    confidence: int = 0,
    price: float = 0.0,
    qty: int = 0,
    value: float = 0.0,
    outcome: str = "",
    framework_scores: dict | None = None,
) -> dict:
    """Append a single event to the journal. Returns the event dict."""
    _ensure_dir()
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "price": round(price, 2),
        "qty": qty,
        "value": round(value, 2),
        "outcome": outcome,
        "reasons": reasons or [],
        "framework_scores": framework_scores or {},
        "data": data or {},
    }

    with _lock:
        try:
            with open(JOURNAL_PATH, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            log.warning("Journal write failed: %s", e)

    return event


def read_events(
    event_type: str | None = None,
    symbol: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[dict]:
    """Read events from journal with optional filters."""
    if not JOURNAL_PATH.exists():
        return []

    events = []
    try:
        with open(JOURNAL_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event_type and event.get("type") != event_type:
                    continue
                if symbol and event.get("symbol") != symbol:
                    continue
                if since:
                    try:
                        ts = datetime.fromisoformat(event["ts"])
                        if ts < since:
                            continue
                    except Exception:
                        continue

                events.append(event)
    except Exception as e:
        log.warning("Journal read failed: %s", e)

    return events[-limit:]


def recent_trades(n: int = 20) -> list[dict]:
    """Recent trade executions."""
    return read_events(event_type="EXECUTION", limit=n)


def trades_for_symbol(symbol: str, limit: int = 50) -> list[dict]:
    """All trades for a specific symbol."""
    return read_events(symbol=symbol, event_type="EXECUTION", limit=limit)


def daily_summary(date: str | None = None) -> dict:
    """Summary of activity for a given date (default: today)."""
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    since = datetime.fromisoformat(f"{date}T00:00:00+00:00")
    events = read_events(since=since, limit=10000)

    buys = [e for e in events if e.get("type") == "EXECUTION" and e.get("action") == "BUY"]
    sells = [e for e in events if e.get("type") == "EXECUTION" and e.get("action") == "SELL"]
    stops = [e for e in events if e.get("type") == "STOP_TRIGGERED"]
    assessments = [e for e in events if e.get("type") == "ASSESSMENT"]

    return {
        "date": date,
        "total_events": len(events),
        "buys": len(buys),
        "sells": len(sells),
        "stops_triggered": len(stops),
        "assessments": len(assessments),
        "buy_value": sum(e.get("value", 0) for e in buys),
        "sell_value": sum(e.get("value", 0) for e in sells),
        "symbols_traded": list(set(
            e.get("symbol") for e in buys + sells if e.get("symbol")
        )),
    }


def recent_activity(n: int = 50) -> list[dict]:
    """Most recent events of any type, formatted for display."""
    return read_events(limit=n)
