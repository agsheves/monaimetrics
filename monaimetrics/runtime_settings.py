"""
Persistent runtime settings stored as a JSON file.
These are the user-adjustable controls that survive restarts.
Separate from config.py (which holds framework tuning constants).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

_SETTINGS_PATH = Path(os.environ.get(
    "RUNTIME_SETTINGS_PATH",
    Path(__file__).resolve().parent.parent / "runtime_settings.json",
))

_lock = Lock()


@dataclass
class RuntimeSettings:
    # Risk
    risk_profile: str = "moderate"  # conservative, moderate, aggressive

    # Position sizing
    min_position_usd: float = 100.0
    max_position_usd: float = 5000.0

    # Execution control
    dry_run: bool = True
    human_review: bool = True  # require approval before executing trades

    # Universe
    scan_universe_limit: int = 200

    # Notifications
    webhook_url: str = ""


def load() -> RuntimeSettings:
    """Load settings from disk. Returns defaults if file doesn't exist."""
    with _lock:
        if not _SETTINGS_PATH.exists():
            return RuntimeSettings()
        try:
            data = json.loads(_SETTINGS_PATH.read_text())
            return RuntimeSettings(**{
                k: v for k, v in data.items()
                if k in RuntimeSettings.__dataclass_fields__
            })
        except Exception as e:
            log.warning("Failed to load runtime settings: %s", e)
            return RuntimeSettings()


def save(settings: RuntimeSettings) -> None:
    """Write settings to disk."""
    with _lock:
        try:
            _SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2))
        except Exception as e:
            log.error("Failed to save runtime settings: %s", e)


def update(**kwargs) -> RuntimeSettings:
    """Load, update specific fields, save, and return."""
    settings = load()
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    save(settings)
    return settings
