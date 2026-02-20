"""
Tests for reporting. All unit tests, no API needed.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from monaimetrics.config import (
    NotificationPriority, Tier, SignalType, SignalUrgency, load_config,
)
from monaimetrics.data_input import AccountInfo
from monaimetrics.strategy import ManagedPosition, Signal
from monaimetrics.trading_interface import OrderResult
from monaimetrics.reporting import (
    Reporter, TradeRecord, PortfolioSnapshot, Alert,
    PerformanceMetrics, TierPerformance,
)


NOW = datetime.now(timezone.utc)
CFG = load_config()


def make_signal(
    symbol="AAPL",
    action=SignalType.SELL,
    tier=Tier.MODERATE,
    confidence=80,
    reasons=None,
) -> Signal:
    return Signal(
        symbol=symbol, action=action,
        urgency=SignalUrgency.STANDARD, tier=tier,
        confidence=confidence,
        reasons=reasons or ["Test reason"],
    )


def make_order_result(
    symbol="AAPL",
    side="sell",
    qty=10,
    filled_price=155.0,
    status="filled",
) -> OrderResult:
    return OrderResult(
        order_id="test-123", symbol=symbol, side=side,
        qty=qty, status=status, filled_qty=qty,
        filled_avg_price=filled_price,
    )


def make_position(
    symbol="AAPL",
    tier=Tier.MODERATE,
    entry_price=100.0,
    current_price=110.0,
    weeks_held=3,
) -> ManagedPosition:
    return ManagedPosition(
        symbol=symbol, tier=tier, qty=10,
        entry_price=entry_price,
        entry_date=NOW - timedelta(weeks=weeks_held),
        stop_price=92.0, target_price=125.0,
        trailing_stop=0.0, highest_price=current_price,
        current_price=current_price, weeks_held=weeks_held,
    )


def make_account(pv=100000, cash=30000) -> AccountInfo:
    return AccountInfo(
        cash=cash, portfolio_value=pv,
        buying_power=cash * 2, status="active",
    )


# ---------------------------------------------------------------------------
# Trade Recording
# ---------------------------------------------------------------------------

class TestRecordTrade:
    def test_records_sell(self):
        r = Reporter()
        r.record_trade(
            make_signal(), make_order_result(),
            exit_gain_pct=0.10,
        )
        assert len(r.trades) == 1
        assert r.trades[0].action == "sell"
        assert r.trades[0].gain_pct == 0.10
        assert r.trades[0].symbol == "AAPL"

    def test_records_buy(self):
        r = Reporter()
        r.record_trade(
            make_signal(action=SignalType.BUY),
            make_order_result(side="buy"),
        )
        assert r.trades[0].side == "buy"

    def test_no_order_result(self):
        r = Reporter()
        r.record_trade(make_signal(), None)
        assert r.trades[0].status == "no_order"
        assert r.trades[0].order_id == ""

    def test_accumulates(self):
        r = Reporter()
        r.record_trade(make_signal(symbol="AAPL"), make_order_result(symbol="AAPL"), exit_gain_pct=0.10)
        r.record_trade(make_signal(symbol="MSFT"), make_order_result(symbol="MSFT"), exit_gain_pct=-0.05)
        assert len(r.trades) == 2


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

class TestSnapshots:
    def test_take_snapshot(self):
        r = Reporter()
        r.take_snapshot(
            make_account(),
            [make_position()],
            {Tier.MODERATE: 50000, Tier.HIGH: 20000},
        )
        assert len(r.snapshots) == 1
        snap = r.snapshots[0]
        assert snap.portfolio_value == 100000
        assert snap.cash == 30000
        assert len(snap.positions) == 1
        assert snap.positions[0].symbol == "AAPL"

    def test_allocation_pcts(self):
        r = Reporter()
        r.take_snapshot(
            make_account(pv=100000, cash=30000),
            [],
            {Tier.MODERATE: 50000, Tier.HIGH: 20000},
        )
        alloc = r.snapshots[0].allocation_pcts
        assert alloc["moderate"] == pytest.approx(0.50)
        assert alloc["high"] == pytest.approx(0.20)
        assert alloc["cash"] == pytest.approx(0.30)

    def test_position_gain_calculated(self):
        r = Reporter()
        r.take_snapshot(
            make_account(),
            [make_position(entry_price=100, current_price=115)],
            {Tier.MODERATE: 50000, Tier.HIGH: 0},
        )
        assert r.snapshots[0].positions[0].gain_pct == pytest.approx(0.15)

    def test_multiple_snapshots(self):
        r = Reporter()
        r.take_snapshot(make_account(pv=100000), [], {Tier.MODERATE: 0, Tier.HIGH: 0})
        r.take_snapshot(make_account(pv=105000), [], {Tier.MODERATE: 0, Tier.HIGH: 0})
        assert len(r.snapshots) == 2


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_record_alert(self):
        r = Reporter()
        r.record_alert(NotificationPriority.HIGH, "Test alert", "test")
        assert len(r.alerts) == 1
        assert r.alerts[0].priority == "high"

    def test_check_alerts_paused(self):
        r = Reporter()
        alerts = r.check_alerts(
            make_account(), CFG,
            peak_value=100000, paused=True, pause_reason="Drawdown",
        )
        assert any("paused" in a.message.lower() for a in alerts)

    def test_check_alerts_drawdown_warning(self):
        r = Reporter()
        # Portfolio at 86k, peak 100k = 14% drawdown, limit is 18%
        # 80% of limit = 14.4%, so 14% should trigger warning
        alerts = r.check_alerts(
            make_account(pv=85000), CFG,
            peak_value=100000, paused=False, pause_reason="",
        )
        assert any("drawdown" in a.message.lower() for a in alerts)

    def test_check_alerts_no_issues(self):
        r = Reporter()
        alerts = r.check_alerts(
            make_account(pv=100000), CFG,
            peak_value=100000, paused=False, pause_reason="",
        )
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Performance Metrics
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_empty(self):
        r = Reporter()
        perf = r.calculate_performance()
        assert perf.total_trades == 0
        assert perf.win_rate == 0.0

    def test_with_trades(self):
        r = Reporter()
        r.record_trade(make_signal(symbol="A"), make_order_result(symbol="A"), exit_gain_pct=0.20)
        r.record_trade(make_signal(symbol="B"), make_order_result(symbol="B"), exit_gain_pct=0.15)
        r.record_trade(make_signal(symbol="C"), make_order_result(symbol="C"), exit_gain_pct=-0.08)

        perf = r.calculate_performance(days=9999)
        assert perf.total_trades == 3
        assert perf.wins == 2
        assert perf.losses == 1
        assert perf.win_rate == pytest.approx(2 / 3)
        assert perf.avg_win_pct == pytest.approx(0.175)
        assert perf.avg_loss_pct == pytest.approx(-0.08)
        assert perf.best_trade_pct == pytest.approx(0.20)
        assert perf.worst_trade_pct == pytest.approx(-0.08)

    def test_tier_breakdown(self):
        r = Reporter()
        r.record_trade(
            make_signal(symbol="A", tier=Tier.MODERATE),
            make_order_result(symbol="A"), exit_gain_pct=0.20,
        )
        r.record_trade(
            make_signal(symbol="B", tier=Tier.HIGH),
            make_order_result(symbol="B"), exit_gain_pct=0.50,
        )

        tp = r.tier_performance()
        assert tp["moderate"].trades == 1
        assert tp["high"].trades == 1
        assert tp["high"].avg_gain_pct == pytest.approx(0.50)

    def test_all_losses(self):
        r = Reporter()
        r.record_trade(make_signal(), make_order_result(), exit_gain_pct=-0.05)
        r.record_trade(make_signal(symbol="B"), make_order_result(symbol="B"), exit_gain_pct=-0.08)
        perf = r.calculate_performance(days=9999)
        assert perf.win_rate == 0.0
        assert perf.avg_win_pct == 0.0

    def test_portfolio_return_from_snapshots(self):
        r = Reporter()
        r.take_snapshot(make_account(pv=100000), [], {Tier.MODERATE: 0, Tier.HIGH: 0})
        r.take_snapshot(make_account(pv=110000), [], {Tier.MODERATE: 0, Tier.HIGH: 0})
        perf = r.calculate_performance(days=9999)
        assert perf.total_return_pct == pytest.approx(0.10)


class TestClosedTrades:
    def test_only_with_gain(self):
        r = Reporter()
        r.record_trade(make_signal(), make_order_result(), exit_gain_pct=0.10)
        r.record_trade(make_signal(action=SignalType.BUY), make_order_result(side="buy"))
        assert len(r.closed_trades()) == 1


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_json(self, tmp_path):
        r = Reporter()
        r.record_trade(make_signal(), make_order_result(), exit_gain_pct=0.10)
        r.take_snapshot(make_account(), [], {Tier.MODERATE: 50000, Tier.HIGH: 20000})
        r.record_alert(NotificationPriority.HIGH, "Test", "test")

        filepath = tmp_path / "report.json"
        r.export_json(filepath)

        assert filepath.exists()
        data = json.loads(filepath.read_text())
        assert len(data["trades"]) == 1
        assert len(data["snapshots"]) == 1
        assert len(data["alerts"]) == 1
        assert "exported_at" in data

    def test_export_creates_dirs(self, tmp_path):
        r = Reporter()
        filepath = tmp_path / "subdir" / "nested" / "report.json"
        r.export_json(filepath)
        assert filepath.exists()


class TestTradeSummary:
    def test_summary_string(self):
        r = Reporter()
        r.record_trade(make_signal(), make_order_result(), exit_gain_pct=0.20)
        r.record_trade(make_signal(symbol="B"), make_order_result(symbol="B"), exit_gain_pct=-0.05)
        summary = r.trade_summary()
        assert "Total trades: 2" in summary
        assert "Win rate:" in summary
        assert "moderate:" in summary
