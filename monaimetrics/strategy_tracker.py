"""
Strategy performance tracker.

Tracks per-framework accuracy over time, identifies which frameworks
correlate with winning trades, and suggests weight adjustments.

Storage: data/strategy_performance.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_PATH = DATA_DIR / "strategy_performance.json"
_lock = Lock()


@dataclass
class TrackerState:
    records: list[dict] = field(default_factory=list)
    weight_adjustments: list[dict] = field(default_factory=list)
    last_adjustment: str = ""


def _load_state() -> TrackerState:
    if not TRACKER_PATH.exists():
        return TrackerState()
    try:
        with _lock:
            data = json.loads(TRACKER_PATH.read_text())
        return TrackerState(
            records=data.get("records", []),
            weight_adjustments=data.get("weight_adjustments", []),
            last_adjustment=data.get("last_adjustment", ""),
        )
    except Exception as e:
        log.warning("Tracker load failed: %s", e)
        return TrackerState()


def _save_state(state: TrackerState) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "records": state.records,
        "weight_adjustments": state.weight_adjustments,
        "last_adjustment": state.last_adjustment,
    }
    with _lock:
        try:
            TRACKER_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning("Tracker save failed: %s", e)


def record_entry(
    symbol: str,
    framework_scores: dict[str, float],
    action: str = "BUY",
) -> None:
    """Record framework scores at time of trade entry."""
    state = _load_state()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for fw, score in framework_scores.items():
        state.records.append({
            "symbol": symbol,
            "date": date,
            "framework": fw,
            "score": round(score, 1),
            "action": action,
            "outcome": "",
            "gain_pct": 0.0,
        })

    _save_state(state)


def record_exit(symbol: str, gain_pct: float) -> None:
    """Record outcome for all pending framework records for a symbol."""
    state = _load_state()
    outcome = "win" if gain_pct >= 0 else "loss"

    for rec in state.records:
        if rec["symbol"] == symbol and rec["outcome"] == "":
            rec["outcome"] = outcome
            rec["gain_pct"] = round(gain_pct, 4)

    _save_state(state)


def framework_accuracy(days: int = 90) -> dict[str, dict]:
    """
    Compute per-framework accuracy over the given period.
    Returns {framework: {wins, losses, total, win_rate, avg_score_win, avg_score_loss}}.
    """
    state = _load_state()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    stats: dict[str, dict] = {}

    for rec in state.records:
        if rec["outcome"] == "" or rec["date"] < cutoff:
            continue

        fw = rec["framework"]
        if fw not in stats:
            stats[fw] = {"wins": 0, "losses": 0, "win_scores": [], "loss_scores": []}

        if rec["outcome"] == "win":
            stats[fw]["wins"] += 1
            stats[fw]["win_scores"].append(rec["score"])
        else:
            stats[fw]["losses"] += 1
            stats[fw]["loss_scores"].append(rec["score"])

    result = {}
    for fw, s in stats.items():
        total = s["wins"] + s["losses"]
        result[fw] = {
            "wins": s["wins"],
            "losses": s["losses"],
            "total": total,
            "win_rate": round(s["wins"] / total, 3) if total > 0 else 0,
            "avg_score_win": round(
                sum(s["win_scores"]) / len(s["win_scores"]), 1,
            ) if s["win_scores"] else 0,
            "avg_score_loss": round(
                sum(s["loss_scores"]) / len(s["loss_scores"]), 1,
            ) if s["loss_scores"] else 0,
        }

    return result


def suggest_weight_adjustments(
    current_weights: dict[str, float],
    days: int = 90,
    max_delta: float = 0.05,
    min_weight: float = 0.05,
    max_weight: float = 0.50,
) -> tuple[dict[str, float], dict[str, str]]:
    """
    Suggest framework weight adjustments based on performance.
    Returns (new_weights, reasons_dict).
    """
    accuracy = framework_accuracy(days)

    if not accuracy:
        return dict(current_weights), {}

    new_weights = dict(current_weights)
    reasons = {}

    for fw in current_weights:
        if fw not in accuracy or accuracy[fw]["total"] < 5:
            continue

        win_rate = accuracy[fw]["win_rate"]
        current = current_weights[fw]

        if win_rate > 0.60:
            delta = min(max_delta, max_weight - current)
            new_weights[fw] = current + delta
            reasons[fw] = f"+{delta:.2f} (win rate {win_rate:.0%} over {accuracy[fw]['total']} trades)"
        elif win_rate < 0.35:
            delta = min(max_delta, current - min_weight)
            new_weights[fw] = current - delta
            reasons[fw] = f"-{delta:.2f} (win rate {win_rate:.0%} over {accuracy[fw]['total']} trades)"

    # Normalize to sum to 1.0
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 3) for k, v in new_weights.items()}

    return new_weights, reasons


def record_weight_adjustment(
    old_weights: dict[str, float],
    new_weights: dict[str, float],
    reasons: dict[str, str],
) -> None:
    """Log a weight adjustment event."""
    state = _load_state()
    state.weight_adjustments.append({
        "date": datetime.now(timezone.utc).isoformat(),
        "old_weights": old_weights,
        "new_weights": new_weights,
        "reasons": reasons,
    })
    state.last_adjustment = datetime.now(timezone.utc).isoformat()
    _save_state(state)


def get_weight_history(limit: int = 20) -> list[dict]:
    """Return recent weight adjustment history."""
    state = _load_state()
    return state.weight_adjustments[-limit:]
