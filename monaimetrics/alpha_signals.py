"""
Alpha signals overlay: external data feeds that influence trade scoring.
Fetches, normalizes, and routes external signals to trade types via YAML config.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
import yaml

from monaimetrics import calculators

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class SignalEffect:
    """One way a signal influences a specific set of trade types."""
    name: str
    polarity: str           # "bull" or "bear"
    trade_types: list[str]  # ["energy", "oil"] or ["all"]
    weight: float
    max_adjustment: float
    apply_to: str           # "buy", "sell", or "both"


@dataclass
class NormalizationConfig:
    method: str             # "range", "zscore", or "threshold"
    min_value: float = 0.0
    max_value: float = 100.0
    mean: float = 0.0
    std: float = 1.0
    threshold: float = 0.0
    invert: bool = False


@dataclass
class SignalSource:
    type: str               # "rest_api"
    url_template: str
    auth_env_var: str
    response_path: str


@dataclass
class SignalDefinition:
    """One external data source with its normalization and list of effects."""
    id: str
    name: str
    source: SignalSource
    normalization: NormalizationConfig
    ttl_minutes: int
    effects: list[SignalEffect]


@dataclass
class CachedSignalValue:
    """A fetched and normalized signal value with timestamp."""
    signal_id: str
    normalized_value: float
    fetched_at: datetime

    def is_stale(self, ttl_minutes: int) -> bool:
        age = (datetime.now(timezone.utc) - self.fetched_at).total_seconds()
        return age > ttl_minutes * 60


class SignalCache:
    """Holds cached signal values, handles TTL expiry."""

    def __init__(self):
        self._cache: dict[str, CachedSignalValue] = {}

    def get(self, signal_id: str) -> CachedSignalValue | None:
        return self._cache.get(signal_id)

    def put(self, value: CachedSignalValue):
        self._cache[value.signal_id] = value

    def is_stale(self, signal_id: str, ttl_minutes: int) -> bool:
        cached = self._cache.get(signal_id)
        if cached is None:
            return True
        return cached.is_stale(ttl_minutes)

    def all_values(self) -> dict[str, CachedSignalValue]:
        return dict(self._cache)


class TradeTypeResolver:
    """Resolves symbol → set of trade types (Alpaca auto-detect + YAML overrides)."""

    def __init__(
        self,
        overrides: dict[str, list[str]] | None = None,
        alpaca_trading_client=None,
    ):
        self._overrides: dict[str, set[str]] = {
            sym: set(types) for sym, types in (overrides or {}).items()
        }
        self._alpaca_cache: dict[str, set[str]] = {}
        self._alpaca_client = alpaca_trading_client
        self._alpaca_loaded = False

    def resolve(self, symbol: str) -> set[str]:
        """Returns all trade types for a symbol."""
        result: set[str] = set()

        # Check manual overrides
        if symbol in self._overrides:
            result.update(self._overrides[symbol])

        # Check Alpaca cache
        if symbol in self._alpaca_cache:
            result.update(self._alpaca_cache[symbol])
        elif not self._alpaca_loaded and self._alpaca_client is not None:
            self._load_from_alpaca()
            if symbol in self._alpaca_cache:
                result.update(self._alpaca_cache[symbol])

        return result

    def _load_from_alpaca(self):
        """Load sector/industry classifications from Alpaca for all known symbols."""
        if self._alpaca_loaded or self._alpaca_client is None:
            return
        self._alpaca_loaded = True
        try:
            assets = self._alpaca_client.get_all_assets()
            for asset in assets:
                if not asset.tradable:
                    continue
                types: set[str] = set()
                # Alpaca asset objects may have sector/industry attributes
                sector = getattr(asset, "sector", None)
                industry = getattr(asset, "industry", None)
                if sector:
                    types.add(sector.lower())
                if industry:
                    types.add(industry.lower())
                if types:
                    self._alpaca_cache[asset.symbol] = types
        except Exception as e:
            log.warning("Failed to load trade types from Alpaca: %s", e)

    def preload(self, symbols: list[str]):
        """Trigger Alpaca loading if not done yet."""
        if not self._alpaca_loaded and self._alpaca_client is not None:
            self._load_from_alpaca()


# ---------------------------------------------------------------------------
# YAML Loading
# ---------------------------------------------------------------------------

def load_signal_definitions(
    path: str,
) -> tuple[list[SignalDefinition], dict[str, list[str]]]:
    """Parse alpha_signals.yaml into signal definitions and trade type overrides."""
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return [], {}

    definitions: list[SignalDefinition] = []
    for sig in raw.get("signals", []):
        source_raw = sig.get("source", {})
        source = SignalSource(
            type=source_raw.get("type", "rest_api"),
            url_template=source_raw.get("url_template", ""),
            auth_env_var=source_raw.get("auth_env_var", ""),
            response_path=source_raw.get("response_path", ""),
        )

        norm_raw = sig.get("normalization", {})
        normalization = NormalizationConfig(
            method=norm_raw.get("method", "range"),
            min_value=norm_raw.get("min_value", 0.0),
            max_value=norm_raw.get("max_value", 100.0),
            mean=norm_raw.get("mean", 0.0),
            std=norm_raw.get("std", 1.0),
            threshold=norm_raw.get("threshold", 0.0),
            invert=norm_raw.get("invert", False),
        )

        effects: list[SignalEffect] = []
        for eff in sig.get("effects", []):
            effects.append(SignalEffect(
                name=eff.get("name", ""),
                polarity=eff.get("polarity", "bull"),
                trade_types=eff.get("trade_types", ["all"]),
                weight=eff.get("weight", 1.0),
                max_adjustment=eff.get("max_adjustment", 10.0),
                apply_to=eff.get("apply_to", "both"),
            ))

        definitions.append(SignalDefinition(
            id=sig.get("id", ""),
            name=sig.get("name", ""),
            source=source,
            normalization=normalization,
            ttl_minutes=sig.get("ttl_minutes", 60),
            effects=effects,
        ))

    trade_types: dict[str, list[str]] = raw.get("trade_types", {}) or {}

    return definitions, trade_types


# ---------------------------------------------------------------------------
# Signal Fetching & Normalization
# ---------------------------------------------------------------------------

def _extract_nested(data: dict, path: str):
    """Extract a value from a nested dict using dot-separated path."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def fetch_signal_value(signal: SignalDefinition, context: dict | None = None) -> float | None:
    """Fetch raw value from a REST API signal source."""
    if signal.source.type != "rest_api":
        log.warning("Unsupported signal source type: %s", signal.source.type)
        return None

    url = signal.source.url_template
    if context:
        for key, val in context.items():
            url = url.replace(f"{{{key}}}", str(val))

    # Resolve auth
    headers = {}
    if signal.source.auth_env_var:
        api_key = os.environ.get(signal.source.auth_env_var, "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        raw = _extract_nested(data, signal.source.response_path)
        if raw is None:
            log.warning("Signal %s: path '%s' returned None", signal.id, signal.source.response_path)
            return None
        return float(raw)
    except Exception as e:
        log.warning("Signal %s fetch failed: %s", signal.id, e)
        return None


def normalize_signal(value: float, config: NormalizationConfig) -> float:
    """Dispatch to the appropriate normalization calculator."""
    if config.method == "range":
        return calculators.normalize_range(
            value, config.min_value, config.max_value, config.invert,
        )
    elif config.method == "zscore":
        return calculators.normalize_zscore(
            value, config.mean, config.std, config.invert,
        )
    elif config.method == "threshold":
        return calculators.normalize_threshold(
            value, config.threshold, config.invert,
        )
    else:
        log.warning("Unknown normalization method: %s", config.method)
        return 0.0


def refresh_signals(
    definitions: list[SignalDefinition],
    cache: SignalCache,
    context: dict | None = None,
):
    """Fetch each signal once, normalize, cache. Skips if not stale."""
    for sig_def in definitions:
        if not cache.is_stale(sig_def.id, sig_def.ttl_minutes):
            continue

        raw = fetch_signal_value(sig_def, context)
        if raw is None:
            continue

        normalized = normalize_signal(raw, sig_def.normalization)
        cache.put(CachedSignalValue(
            signal_id=sig_def.id,
            normalized_value=normalized,
            fetched_at=datetime.now(timezone.utc),
        ))
        log.debug("Signal %s refreshed: raw=%.2f, normalized=%.3f", sig_def.id, raw, normalized)


# ---------------------------------------------------------------------------
# Effect Application
# ---------------------------------------------------------------------------

def effect_applies(
    effect: SignalEffect,
    symbol_types: set[str],
    side: str,
) -> bool:
    """Does this effect match the given symbol types and trade side?"""
    # Check side
    if effect.apply_to != "both" and effect.apply_to != side:
        return False

    # Check trade types
    if "all" in effect.trade_types:
        return True

    return bool(symbol_types & set(effect.trade_types))


def compute_alpha_adjustment(
    definitions: list[SignalDefinition],
    cache: SignalCache,
    *,
    symbol_types: set[str],
    side: str,
    global_max: float,
) -> float:
    """
    Walk all signals and their effects, aggregate into a single points adjustment.
    Returns a float in [-global_max, +global_max].
    """
    effect_tuples: list[tuple[float, float, float]] = []

    for sig_def in definitions:
        cached = cache.get(sig_def.id)
        if cached is None:
            continue

        for effect in sig_def.effects:
            if not effect_applies(effect, symbol_types, side):
                continue

            # Apply polarity
            signal_value = cached.normalized_value
            if effect.polarity == "bear":
                signal_value = -signal_value

            effect_tuples.append((signal_value, effect.weight, effect.max_adjustment))

    if not effect_tuples:
        return 0.0

    return calculators.aggregate_alpha_adjustment(effect_tuples, global_max)
