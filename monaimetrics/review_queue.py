"""
In-memory review queue for human-in-the-loop trade approval.

When human_review is enabled, the scheduler stores proposed signals here
instead of executing them immediately. The web UI presents them for
approval or rejection.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from monaimetrics.config import SignalType, Tier

log = logging.getLogger(__name__)

_lock = Lock()


@dataclass
class PendingSignal:
    """A proposed trade awaiting human review."""
    id: str
    symbol: str
    action: str          # BUY, SELL, REDUCE
    tier: str            # moderate, high
    confidence: int
    position_size_usd: float
    stop_price: float
    target_price: float
    reasons: list[str]
    price_at_signal: float
    created_at: datetime
    status: str = "pending"  # pending, approved, rejected, expired


# Module-level queue
_pending: list[PendingSignal] = []


def add_signals(signals: list[dict]) -> int:
    """Add proposed signals to the review queue. Returns count added."""
    count = 0
    with _lock:
        for sig in signals:
            action = sig.get("action", "")
            if action not in ("BUY", "SELL", "REDUCE"):
                continue
            _pending.append(PendingSignal(
                id=uuid.uuid4().hex[:12],
                symbol=sig["symbol"],
                action=action,
                tier=sig.get("tier", "moderate"),
                confidence=sig.get("confidence", 0),
                position_size_usd=sig.get("position_size_usd", 0),
                stop_price=sig.get("stop_price", 0),
                target_price=sig.get("target_price", 0),
                reasons=sig.get("reasons", []),
                price_at_signal=sig.get("price", 0),
                created_at=datetime.now(timezone.utc),
            ))
            count += 1
    log.info("Review queue: added %d signal(s), total pending: %d", count, len(get_pending()))
    return count


def get_pending() -> list[PendingSignal]:
    """Return all pending signals (newest first)."""
    with _lock:
        return [s for s in _pending if s.status == "pending"]


def get_all() -> list[PendingSignal]:
    """Return all signals including resolved ones."""
    with _lock:
        return list(_pending)


def approve(signal_id: str) -> PendingSignal | None:
    """Mark a signal as approved. Returns the signal or None."""
    with _lock:
        for sig in _pending:
            if sig.id == signal_id and sig.status == "pending":
                sig.status = "approved"
                log.info("Review queue: approved %s %s", sig.action, sig.symbol)
                return sig
    return None


def reject(signal_id: str) -> PendingSignal | None:
    """Mark a signal as rejected."""
    with _lock:
        for sig in _pending:
            if sig.id == signal_id and sig.status == "pending":
                sig.status = "rejected"
                log.info("Review queue: rejected %s %s", sig.action, sig.symbol)
                return sig
    return None


def approve_all() -> int:
    """Approve all pending signals. Returns count approved."""
    with _lock:
        count = 0
        for sig in _pending:
            if sig.status == "pending":
                sig.status = "approved"
                count += 1
    log.info("Review queue: approved all (%d)", count)
    return count


def reject_all() -> int:
    """Reject all pending signals. Returns count rejected."""
    with _lock:
        count = 0
        for sig in _pending:
            if sig.status == "pending":
                sig.status = "rejected"
                count += 1
    return count


def clear_resolved() -> int:
    """Remove non-pending signals from the queue."""
    global _pending
    with _lock:
        before = len(_pending)
        _pending = [s for s in _pending if s.status == "pending"]
        return before - len(_pending)


def get_approved() -> list[PendingSignal]:
    """Return and consume approved signals (marks them as consumed)."""
    with _lock:
        approved = [s for s in _pending if s.status == "approved"]
        # Remove consumed approved signals
        _pending[:] = [s for s in _pending if s.status != "approved"]
        return approved
