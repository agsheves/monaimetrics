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


def update_user_config(key: str, value: str, path: str | Path | None = None) -> None:
    """
    Update (or insert) a KEY=VALUE line in user_config.yaml and apply the
    new value to os.environ immediately.

    Existing inline comments on the changed line are preserved.
    If the key is not present, the new line is appended at the end.
    """
    config_path = Path(path) if path else _DEFAULT_PATH
    os.environ[key] = value

    if not config_path.exists():
        with open(config_path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
        return

    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    found = False
    new_lines = []
    for raw_line in lines:
        stripped = raw_line.split("#")[0].strip()
        if "=" in stripped:
            k, _, _ = stripped.partition("=")
            if k.strip() == key:
                comment_part = ""
                if "#" in raw_line:
                    comment_part = "  " + raw_line[raw_line.index("#"):]
                new_lines.append(f"{key}={value}{comment_part}" if comment_part else f"{key}={value}\n")
                found = True
                continue
        new_lines.append(raw_line)

    if not found:
        nl = "" if new_lines and new_lines[-1].endswith("\n") else "\n"
        new_lines.append(f"{nl}{key}={value}\n")

    config_path.write_text("".join(new_lines), encoding="utf-8")
