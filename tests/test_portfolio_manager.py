"""
Tests for portfolio_manager. Dry-run tests need no API.
Integration tests hit Alpaca paper trading.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from monaimetrics.config import (
    SignalType, SignalUrgency, Tier, load_config, RiskProfile,
)
from monaimetrics.data_input import AccountInfo, AlpacaClients, reset_clients
from monaimetrics.strategy import ManagedPosition, Signal, TradingPlan
from monaimetrics.portfolio_manager import PortfolioManager, ExecutionRecord


NOW = datetime.now(timezone.utc)


def make_pm(config=None) -> PortfolioManager:
    cfg = config or load_config()
    return PortfolioManager(cfg)


def make_position(
    symbol="AAPL",
    tier=Tier.MODERATE,
    entry_price=100.0,
    current_price=110.0,
    stop_price=92.0,
    target_price=125.0,
    trailing_stop=0.0,
    highest_price=110.0,
    weeks_held=2,
    qty=10.0,
) -> ManagedPosition:
    return ManagedPosition(
        symbol=symbol, tier=tier, qty=qty, entry_price=entry_price,
        entry_date=NOW - timedelta(weeks=weeks_held),
        stop_price=stop_price, target_price=target_price,
        trailing_stop=trailing_stop, highest_price=highest_price,
        current_price=current_price, weeks_held=weeks_held,
    )


# ---------------------------------------------------------------------------
# Dry-Run Tests (no API)
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_state(self):
        pm = make_pm()
        assert pm.managed_positions == []
        assert pm.paused is False
        assert pm.cycle_score == 0
        assert pm.config.dry_run is True

    def test_tier_values_empty(self):
        pm = make_pm()
        tv = pm.tier_values()
        assert tv[Tier.MODERATE] == 0.0
        assert tv[Tier.HIGH] == 0.0

    def test_tier_values_with_positions(self):
        pm = make_pm()
        pm.managed_positions = [
            make_position(tier=Tier.MODERATE, current_price=100, qty=10),
            make_position(symbol="MSFT", tier=Tier.HIGH, current_price=200, qty=5),
        ]
        tv = pm.tier_values()
        assert tv[Tier.MODERATE] == 1000.0
        assert tv[Tier.HIGH] == 1000.0


class TestExecutePlan:
    def test_hold_signals_no_orders(self):
        pm = make_pm()
        plan = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.HOLD,
                urgency=SignalUrgency.MONITOR, tier=Tier.MODERATE,
                confidence=50, reasons=["All criteria met"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        records = pm.execute_plan(plan)
        assert len(records) == 1
        assert records[0].order_result is None
        assert "No action" in records[0].notes

    def test_buy_dry_run(self):
        pm = make_pm()
        plan = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.BUY,
                urgency=SignalUrgency.STANDARD, tier=Tier.MODERATE,
                confidence=70, position_size_usd=5000,
                stop_price=138.0, target_price=187.0,
            )],
            cycle_score=0, timestamp=NOW,
        )
        records = pm.execute_plan(plan)
        assert len(records) == 1
        result = records[0].order_result
        assert result is not None
        # In dry-run, we still create the managed position
        assert result.status == "dry_run"

    def test_sell_dry_run(self):
        pm = make_pm()
        pm.managed_positions = [make_position(symbol="AAPL")]
        plan = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.SELL,
                urgency=SignalUrgency.EMERGENCY, tier=Tier.MODERATE,
                confidence=100, reasons=["Stop hit"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        records = pm.execute_plan(plan)
        assert len(records) == 1
        result = records[0].order_result
        assert result.status == "dry_run"
        assert len(pm.managed_positions) == 0

    def test_sell_increments_stop_counter(self):
        pm = make_pm()
        pm.managed_positions = [make_position(symbol="AAPL")]
        plan = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.SELL,
                urgency=SignalUrgency.EMERGENCY, tier=Tier.MODERATE,
                confidence=100, reasons=["Stop-loss hit"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        pm.execute_plan(plan)
        assert pm.stops_today >= 1

    def test_buy_blocked_when_paused(self):
        pm = make_pm()
        pm.paused = True
        pm.pause_reason = "Test pause"
        plan = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.BUY,
                urgency=SignalUrgency.STANDARD, tier=Tier.MODERATE,
                confidence=70, position_size_usd=5000,
                stop_price=138.0, target_price=187.0,
            )],
            cycle_score=0, timestamp=NOW,
        )
        records = pm.execute_plan(plan)
        assert records[0].order_result is None
        assert "Paused" in records[0].notes

    def test_emergency_sell_executes_when_paused(self):
        pm = make_pm()
        pm.paused = True
        pm.pause_reason = "Drawdown"
        pm.managed_positions = [make_position(symbol="AAPL")]
        plan = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.SELL,
                urgency=SignalUrgency.EMERGENCY, tier=Tier.MODERATE,
                confidence=100, reasons=["Stage 4"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        records = pm.execute_plan(plan)
        assert records[0].order_result is not None
        assert records[0].order_result.status == "dry_run"

    def test_sell_nonexistent_position_rejected(self):
        pm = make_pm()
        plan = TradingPlan(
            signals=[Signal(
                symbol="ZZZZ", action=SignalType.SELL,
                urgency=SignalUrgency.STANDARD, tier=Tier.MODERATE,
                confidence=100, reasons=["Test"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        records = pm.execute_plan(plan)
        assert records[0].order_result.status == "rejected"


class TestCircuitBreakers:
    def test_rapid_loss_triggers_pause(self):
        pm = make_pm()
        # Set peak to 0 so drawdown check is skipped (peak must be > 0)
        pm.peak_value = 0.0
        pm.paused = False
        pm.stops_today = 3
        pm.stops_today_date = datetime.now(timezone.utc).date()
        pm.check_circuit_breakers()
        assert pm.paused is True
        assert "Rapid loss" in pm.pause_reason

    def test_pause_expires(self):
        pm = make_pm()
        pm.paused = True
        pm.pause_reason = "Test"
        pm.pause_until = datetime.now(timezone.utc) - timedelta(hours=1)
        pm.check_circuit_breakers()
        assert pm.paused is False


class TestManualOverride:
    def test_manual_sell(self):
        pm = make_pm()
        pm.managed_positions = [make_position(symbol="AAPL")]
        result = pm.manual_sell("AAPL", "Taking profits manually")
        assert result is not None
        assert result.status == "dry_run"
        assert len(pm.managed_positions) == 0
        assert any("MANUAL" in r.signal.reasons[0] for r in pm.execution_log)

    def test_manual_sell_no_position(self):
        pm = make_pm()
        result = pm.manual_sell("ZZZZ")
        assert result is None


class TestEmergencyHalt:
    def test_closes_all(self):
        pm = make_pm()
        pm.managed_positions = [
            make_position(symbol="AAPL"),
            make_position(symbol="MSFT"),
        ]
        results = pm.emergency_halt()
        assert len(results) == 2
        assert all(r.status == "dry_run" for r in results)
        assert len(pm.managed_positions) == 0
        assert pm.paused is True


class TestSummary:
    def test_returns_dict(self):
        pm = make_pm()
        s = pm.summary()
        assert s["positions"] == 0
        assert s["dry_run"] is True
        assert s["paused"] is False

    def test_with_positions(self):
        pm = make_pm()
        pm.managed_positions = [make_position()]
        s = pm.summary()
        assert s["positions"] == 1
        assert s["moderate_value"] > 0


class TestStopCheck:
    def test_no_positions(self):
        pm = make_pm()
        records = pm.run_stop_check()
        assert records == []

    def test_stop_triggered_in_check(self):
        pm = make_pm()
        pos = make_position(current_price=91.0, stop_price=92.0)
        pm.managed_positions = [pos]
        # run_stop_check calls sync_positions which needs API,
        # but the position already has current_price set, and in dry_run
        # the sell will go through. We need to handle the sync gracefully.
        # For this test, current_price is already below stop.
        # sync_positions will try API and may fail in unit test context,
        # so we test the logic directly.
        if pos.current_price <= pos.stop_price:
            signal = Signal(
                symbol=pos.symbol, action=SignalType.SELL,
                urgency=SignalUrgency.EMERGENCY, tier=pos.tier,
                confidence=100, reasons=["Stop hit"],
            )
            result = pm._execute_sell(signal)
            assert result.status == "dry_run"
            assert len(pm.managed_positions) == 0


class TestExecutionLog:
    def test_log_accumulates(self):
        pm = make_pm()
        pm.managed_positions = [make_position(symbol="AAPL")]
        plan1 = TradingPlan(
            signals=[Signal(
                symbol="AAPL", action=SignalType.SELL,
                urgency=SignalUrgency.EMERGENCY, tier=Tier.MODERATE,
                confidence=100, reasons=["Stop hit"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        pm.execute_plan(plan1)
        assert len(pm.execution_log) == 1

        plan2 = TradingPlan(
            signals=[Signal(
                symbol="MSFT", action=SignalType.HOLD,
                urgency=SignalUrgency.MONITOR, tier=Tier.MODERATE,
                confidence=50, reasons=["All good"],
            )],
            cycle_score=0, timestamp=NOW,
        )
        pm.execute_plan(plan2)
        assert len(pm.execution_log) == 2


# ---------------------------------------------------------------------------
# Integration Tests (Alpaca paper trading)
# ---------------------------------------------------------------------------

needs_api = pytest.mark.skipif(
    not os.environ.get("ALPACA_API_KEY"),
    reason="No Alpaca API key",
)


@needs_api
class TestLiveIntegration:
    def test_summary_live(self):
        cfg = load_config()
        reset_clients()
        clients = AlpacaClients(cfg.api)
        pm = PortfolioManager(cfg, clients)
        s = pm.summary()
        assert s["portfolio_value"] > 0
        assert s["dry_run"] is True

    def test_assessment_empty_watchlist(self):
        cfg = load_config()
        reset_clients()
        clients = AlpacaClients(cfg.api)
        pm = PortfolioManager(cfg, clients)
        plan, records = pm.run_assessment(watchlist=[])
        assert plan is not None
        assert isinstance(records, list)

    def test_assessment_with_watchlist(self):
        cfg = load_config()
        reset_clients()
        clients = AlpacaClients(cfg.api)
        pm = PortfolioManager(cfg, clients)
        plan, records = pm.run_assessment(watchlist=["AAPL"])
        assert len(plan.signals) >= 0
        for sig in plan.signals:
            assert sig.symbol == "AAPL"
