"""
Persistent portfolio manager state.

Saves managed positions, trailing stop state, circuit breaker counters,
and peak portfolio value between scheduler runs.

Storage: data/pm_state.json (overwritten each save)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_PATH = STATE_DIR / "pm_state.json"
_lock = Lock()


@dataclass
class PersistedPosition:
    symbol: str
    tier: str
    qty: float
    entry_price: float
    entry_date: str
    stop_price: float
    target_price: float
    trailing_stop: float
    highest_price: float
    current_price: float
    weeks_held: int = 0


@dataclass
class PMState:
    positions: list[PersistedPosition] = field(default_factory=list)
    stop_order_ids: dict[str, str] = field(default_factory=dict)
    peak_value: float = 0.0
    cycle_score: int = 0
    stops_today: int = 0
    stops_today_date: str = ""
    paused: bool = False
    pause_reason: str = ""
    pause_until: str = ""
    last_saved: str = ""


def save(state: PMState) -> None:
    """Save PM state to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state.last_saved = datetime.now(timezone.utc).isoformat()

    data = {
        "positions": [asdict(p) for p in state.positions],
        "stop_order_ids": state.stop_order_ids,
        "peak_value": state.peak_value,
        "cycle_score": state.cycle_score,
        "stops_today": state.stops_today,
        "stops_today_date": state.stops_today_date,
        "paused": state.paused,
        "pause_reason": state.pause_reason,
        "pause_until": state.pause_until,
        "last_saved": state.last_saved,
    }

    with _lock:
        try:
            STATE_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning("PM state save failed: %s", e)


def load() -> PMState:
    """Load PM state from disk. Returns fresh state if file doesn't exist."""
    if not STATE_PATH.exists():
        return PMState()

    try:
        with _lock:
            data = json.loads(STATE_PATH.read_text())

        positions = [
            PersistedPosition(**p) for p in data.get("positions", [])
        ]

        return PMState(
            positions=positions,
            stop_order_ids=data.get("stop_order_ids", {}),
            peak_value=data.get("peak_value", 0.0),
            cycle_score=data.get("cycle_score", 0),
            stops_today=data.get("stops_today", 0),
            stops_today_date=data.get("stops_today_date", ""),
            paused=data.get("paused", False),
            pause_reason=data.get("pause_reason", ""),
            pause_until=data.get("pause_until", ""),
            last_saved=data.get("last_saved", ""),
        )
    except Exception as e:
        log.warning("PM state load failed: %s — starting fresh", e)
        return PMState()
