"""
Records everything that happens and presents it in useful formats.
Answers 'what happened?' — never 'was it good?' (that's audit_qa's job).
If it happened and wasn't logged, it didn't happen.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from monaimetrics.config import (
    NotificationPriority, Tier, SignalType, SystemConfig,
)
from monaimetrics.data_input import AccountInfo
from monaimetrics.strategy import ManagedPosition, Signal
from monaimetrics.trading_interface import OrderResult
from monaimetrics import calculators

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class PositionSnapshot:
    symbol: str
    tier: str
    qty: float
    entry_price: float
    current_price: float
    gain_pct: float
    weeks_held: int


@dataclass
class PortfolioSnapshot:
    timestamp: str
    portfolio_value: float
    cash: float
    positions: list[PositionSnapshot]
    tier_values: dict[str, float]
    allocation_pcts: dict[str, float]


@dataclass
class TradeRecord:
    timestamp: str
    symbol: str
    action: str
    side: str
    tier: str
    qty: float
    price: float | None
    gain_pct: float | None
    reasons: list[str]
    confidence: int
    order_id: str
    status: str


@dataclass
class Alert:
    timestamp: str
    priority: str
    message: str
    source: str


@dataclass
class PerformanceMetrics:
    period_days: int
    total_return_pct: float
    benchmark_return_pct: float | None
    alpha: float | None
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    best_trade_pct: float
    worst_trade_pct: float
    moderate_trades: int
    high_risk_trades: int


@dataclass
class TierPerformance:
    tier: str
    trades: int
    wins: int
    win_rate: float
    avg_gain_pct: float
    total_return_pct: float


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

class Reporter:
    """Accumulates all system events. Export to JSON. Query for metrics."""

    def __init__(self):
        self.trades: list[TradeRecord] = []
        self.snapshots: list[PortfolioSnapshot] = []
        self.alerts: list[Alert] = []

    # ----- Recording -----

    def record_trade(
        self,
        signal: Signal,
        order_result: OrderResult | None,
        entry_price: float | None = None,
        exit_gain_pct: float | None = None,
    ):
        price = None
        order_id = ""
        status = "no_order"

        if order_result:
            price = order_result.filled_avg_price
            order_id = order_result.order_id
            status = order_result.status

        self.trades.append(TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol=signal.symbol,
            action=signal.action.value,
            side="sell" if signal.action in (SignalType.SELL, SignalType.REDUCE) else "buy",
            tier=signal.tier.value,
            qty=order_result.qty if order_result else 0,
            price=price,
            gain_pct=exit_gain_pct,
            reasons=list(signal.reasons),
            confidence=signal.confidence,
            order_id=order_id,
            status=status,
        ))

    def take_snapshot(
        self,
        account: AccountInfo,
        managed_positions: list[ManagedPosition],
        tier_values: dict[Tier, float],
    ):
        total = account.portfolio_value if account.portfolio_value > 0 else 1.0

        positions = [
            PositionSnapshot(
                symbol=p.symbol,
                tier=p.tier.value,
                qty=p.qty,
                entry_price=p.entry_price,
                current_price=p.current_price,
                gain_pct=calculators.gain_pct(p.current_price, p.entry_price),
                weeks_held=p.weeks_held,
            )
            for p in managed_positions
        ]

        tv = {t.value: v for t, v in tier_values.items()}
        alloc = {t.value: v / total for t, v in tier_values.items()}
        alloc["cash"] = account.cash / total

        self.snapshots.append(PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            portfolio_value=account.portfolio_value,
            cash=account.cash,
            positions=positions,
            tier_values=tv,
            allocation_pcts=alloc,
        ))

    def record_alert(
        self,
        priority: NotificationPriority,
        message: str,
        source: str = "system",
    ):
        alert = Alert(
            timestamp=datetime.now(timezone.utc).isoformat(),
            priority=priority.value,
            message=message,
            source=source,
        )
        self.alerts.append(alert)
        if priority in (NotificationPriority.CRITICAL, NotificationPriority.HIGH):
            log.warning("ALERT [%s] %s: %s", priority.value, source, message)

    # ----- Queries -----

    def closed_trades(self) -> list[TradeRecord]:
        """All completed sell/reduce trades with gain_pct recorded."""
        return [t for t in self.trades if t.gain_pct is not None]

    def trades_in_period(self, days: int) -> list[TradeRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return [t for t in self.trades if t.timestamp >= cutoff]

    def calculate_performance(self, days: int = 30) -> PerformanceMetrics:
        closed = [t for t in self.closed_trades()
                  if t.timestamp >= (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()]

        wins = [t for t in closed if t.gain_pct is not None and t.gain_pct > 0]
        losses = [t for t in closed if t.gain_pct is not None and t.gain_pct <= 0]

        win_gains = [t.gain_pct for t in wins]
        loss_gains = [t.gain_pct for t in losses]

        total = len(closed)
        win_count = len(wins)
        loss_count = len(losses)

        # Portfolio return from snapshots
        period_snapshots = [
            s for s in self.snapshots
            if s.timestamp >= (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        ]
        total_return = 0.0
        if len(period_snapshots) >= 2:
            first = period_snapshots[0].portfolio_value
            last = period_snapshots[-1].portfolio_value
            if first > 0:
                total_return = (last - first) / first

        mod_trades = [t for t in closed if t.tier == "moderate"]
        high_trades = [t for t in closed if t.tier == "high"]

        return PerformanceMetrics(
            period_days=days,
            total_return_pct=total_return,
            benchmark_return_pct=None,
            alpha=None,
            total_trades=total,
            wins=win_count,
            losses=loss_count,
            win_rate=win_count / total if total > 0 else 0.0,
            avg_win_pct=sum(win_gains) / len(win_gains) if win_gains else 0.0,
            avg_loss_pct=sum(loss_gains) / len(loss_gains) if loss_gains else 0.0,
            best_trade_pct=max(win_gains) if win_gains else 0.0,
            worst_trade_pct=min(loss_gains) if loss_gains else 0.0,
            moderate_trades=len(mod_trades),
            high_risk_trades=len(high_trades),
        )

    def tier_performance(self) -> dict[str, TierPerformance]:
        result = {}
        for tier_name in ("moderate", "high"):
            closed = [t for t in self.closed_trades() if t.tier == tier_name]
            wins = [t for t in closed if t.gain_pct is not None and t.gain_pct > 0]
            gains = [t.gain_pct for t in closed if t.gain_pct is not None]

            result[tier_name] = TierPerformance(
                tier=tier_name,
                trades=len(closed),
                wins=len(wins),
                win_rate=len(wins) / len(closed) if closed else 0.0,
                avg_gain_pct=sum(gains) / len(gains) if gains else 0.0,
                total_return_pct=sum(gains) if gains else 0.0,
            )
        return result

    # ----- Alert Checks -----

    def check_alerts(
        self,
        account: AccountInfo,
        config: SystemConfig,
        peak_value: float,
        paused: bool,
        pause_reason: str,
    ) -> list[Alert]:
        """Generate alerts based on current state. Returns new alerts."""
        new_alerts = []

        if paused:
            self.record_alert(
                NotificationPriority.CRITICAL,
                f"System paused: {pause_reason}",
                "circuit_breaker",
            )
            new_alerts.append(self.alerts[-1])

        if peak_value > 0:
            drawdown = (peak_value - account.portfolio_value) / peak_value
            if drawdown >= config.circuit_breakers.max_drawdown * 0.8:
                self.record_alert(
                    NotificationPriority.HIGH,
                    f"Drawdown warning: {drawdown:.1%} approaching limit {config.circuit_breakers.max_drawdown:.1%}",
                    "risk",
                )
                new_alerts.append(self.alerts[-1])

        return new_alerts

    # ----- Export -----

    def _serialize(self, obj) -> dict:
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return str(obj)

    def export_json(self, filepath: str | Path):
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "trades": [asdict(t) for t in self.trades],
            "snapshots": [asdict(s) for s in self.snapshots],
            "alerts": [asdict(a) for a in self.alerts],
        }
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
        log.info("Exported report to %s", filepath)

    def trade_summary(self) -> str:
        """Human-readable trade summary."""
        perf = self.calculate_performance(days=9999)
        tier_perf = self.tier_performance()

        lines = [
            f"Total trades: {perf.total_trades}",
            f"Win rate: {perf.win_rate:.0%} ({perf.wins}W / {perf.losses}L)",
            f"Avg win: {perf.avg_win_pct:.1%}  Avg loss: {perf.avg_loss_pct:.1%}",
            f"Best: {perf.best_trade_pct:.1%}  Worst: {perf.worst_trade_pct:.1%}",
            "",
        ]
        for name, tp in tier_perf.items():
            lines.append(
                f"  {name}: {tp.trades} trades, "
                f"{tp.win_rate:.0%} win rate, "
                f"{tp.avg_gain_pct:.1%} avg gain"
            )
        return "\n".join(lines)
