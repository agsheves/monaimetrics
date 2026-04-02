"""
Load non-secret configuration from user_config.yaml.

The file uses KEY=VALUE format with # comments, for example:

    ALPACA_PAPER=true   # use paper trading
    DRY_RUN=true        # no live orders
    MAX_SHARE_PRICE_USD=25.0

Values are applied with lower priority than actual environment variables, so
the load order is:

    Replit secrets  >  user_config.yaml  >  code defaults

Confidential values (API keys, passwords) live in Replit app secrets and are
never in this file. Only shareable non-secret settings belong here.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _ROOT / "user_config.yaml"


def load_user_config(path: str | Path | None = None) -> dict[str, str]:
    """
    Parse user_config.yaml and inject values into os.environ where the key
    is not already set (environment and .env values take priority).

    Args:
        path: Path to the config file. Defaults to user_config.yaml in the
              project root.

    Returns:
        Dict of all key/value pairs found in the file (regardless of whether
        they were injected into os.environ).
    """
    config_path = Path(path) if path else _DEFAULT_PATH
    if not config_path.exists():
        return {}

    loaded: dict[str, str] = {}
    with open(config_path, encoding="utf-8") as fh:
        for raw_line in fh:
            # Strip inline comments and surrounding whitespace
            line = raw_line.split("#")[0].strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            loaded[key] = value
            # Only set if not already present — env vars and .env win
            if key not in os.environ:
                os.environ[key] = value

    return loaded
