"""Tests for PM state persistence, notifications, and strategy tracker."""

import json
from datetime import datetime, timezone

import pytest

from monaimetrics import pm_state, notifications, strategy_tracker


# --- PM State ---

@pytest.fixture
def clean_pm_state(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(pm_state, "STATE_PATH", tmp_path / "pm_state.json")
    yield tmp_path


class TestPMState:
    def test_load_empty(self, clean_pm_state):
        state = pm_state.load()
        assert state.positions == []
        assert state.peak_value == 0.0
        assert state.paused is False

    def test_save_and_load(self, clean_pm_state):
        state = pm_state.PMState(
            positions=[
                pm_state.PersistedPosition(
                    symbol="AAPL", tier="moderate", qty=10, entry_price=150.0,
                    entry_date="2024-01-15T10:00:00+00:00", stop_price=138.0,
                    target_price=187.0, trailing_stop=0.0, highest_price=155.0,
                    current_price=155.0, weeks_held=2,
                ),
            ],
            stop_order_ids={"AAPL": "order-123"},
            peak_value=105000.0,
            cycle_score=-1,
            stops_today=1,
            stops_today_date="2024-03-20",
            paused=False,
        )
        pm_state.save(state)

        loaded = pm_state.load()
        assert len(loaded.positions) == 1
        assert loaded.positions[0].symbol == "AAPL"
        assert loaded.positions[0].entry_price == 150.0
        assert loaded.stop_order_ids == {"AAPL": "order-123"}
        assert loaded.peak_value == 105000.0
        assert loaded.cycle_score == -1
        assert loaded.stops_today == 1

    def test_load_corrupted_file(self, clean_pm_state):
        (clean_pm_state / "pm_state.json").write_text("not json")
        state = pm_state.load()
        assert state.positions == []  # falls back to fresh state


# --- Notifications ---

@pytest.fixture
def clean_notifications(tmp_path, monkeypatch):
    monkeypatch.setattr(notifications, "NOTIFICATION_DIR", tmp_path)
    monkeypatch.setattr(notifications, "NOTIFICATION_PATH", tmp_path / "notifications.jsonl")
    monkeypatch.setattr(notifications, "READ_TRACKER_PATH", tmp_path / "notifications_read.json")
    yield tmp_path


class TestNotifications:
    def test_notify(self, clean_notifications):
        n = notifications.notify(
            "TRADE_EXECUTED",
            title="BUY AAPL",
            message="Bought 10 shares at $175.50",
            symbol="AAPL",
        )
        assert n["type"] == "TRADE_EXECUTED"
        assert "id" in n
        assert len(n["id"]) == 12

    def test_get_notifications(self, clean_notifications):
        notifications.notify("TRADE_EXECUTED", "Buy", "Test 1")
        notifications.notify("STOP_TRIGGERED", "Stop", "Test 2")

        all_notifs = notifications.get_notifications()
        assert len(all_notifs) == 2

    def test_unread_count(self, clean_notifications):
        notifications.notify("TRADE_EXECUTED", "Buy", "Test")
        notifications.notify("STOP_TRIGGERED", "Stop", "Test")

        assert notifications.unread_count() == 2

        all_notifs = notifications.get_notifications()
        notifications.mark_read([all_notifs[0]["id"]])
        assert notifications.unread_count() == 1

    def test_mark_all_read(self, clean_notifications):
        notifications.notify("TRADE_EXECUTED", "Buy", "Test 1")
        notifications.notify("TRADE_EXECUTED", "Buy", "Test 2")

        notifications.mark_all_read()
        assert notifications.unread_count() == 0

    def test_priority(self, clean_notifications):
        n = notifications.notify(
            "SYSTEM_PAUSED", "Paused", "Circuit breaker", priority="critical",
        )
        assert n["priority"] == "critical"


# --- Strategy Tracker ---

@pytest.fixture
def clean_tracker(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_tracker, "DATA_DIR", tmp_path)
    monkeypatch.setattr(strategy_tracker, "TRACKER_PATH", tmp_path / "strategy_performance.json")
    yield tmp_path


class TestStrategyTracker:
    def test_record_entry(self, clean_tracker):
        strategy_tracker.record_entry(
            "AAPL",
            {"canslim": 85.0, "greenblatt": 72.0, "technical": 68.0},
        )
        state = strategy_tracker._load_state()
        assert len(state.records) == 3  # one per framework

    def test_record_exit(self, clean_tracker):
        strategy_tracker.record_entry("AAPL", {"canslim": 85.0, "greenblatt": 72.0})
        strategy_tracker.record_exit("AAPL", gain_pct=0.12)

        state = strategy_tracker._load_state()
        for rec in state.records:
            assert rec["outcome"] == "win"
            assert rec["gain_pct"] == 0.12

    def test_record_exit_loss(self, clean_tracker):
        strategy_tracker.record_entry("TSLA", {"canslim": 45.0})
        strategy_tracker.record_exit("TSLA", gain_pct=-0.08)

        state = strategy_tracker._load_state()
        assert state.records[0]["outcome"] == "loss"

    def test_framework_accuracy(self, clean_tracker):
        # Record 3 wins and 1 loss for canslim
        for sym in ["AAPL", "MSFT", "GOOGL"]:
            strategy_tracker.record_entry(sym, {"canslim": 80.0})
            strategy_tracker.record_exit(sym, gain_pct=0.10)

        strategy_tracker.record_entry("TSLA", {"canslim": 55.0})
        strategy_tracker.record_exit("TSLA", gain_pct=-0.05)

        accuracy = strategy_tracker.framework_accuracy()
        assert accuracy["canslim"]["wins"] == 3
        assert accuracy["canslim"]["losses"] == 1
        assert accuracy["canslim"]["win_rate"] == 0.75

    def test_suggest_weight_adjustments(self, clean_tracker):
        # Create enough data
        for i in range(6):
            strategy_tracker.record_entry(f"SYM{i}", {"canslim": 80.0, "greenblatt": 60.0})
            if i < 5:
                strategy_tracker.record_exit(f"SYM{i}", gain_pct=0.10)  # 5 wins
            else:
                strategy_tracker.record_exit(f"SYM{i}", gain_pct=-0.05)  # 1 loss

        current = {"canslim": 0.40, "greenblatt": 0.30, "technical": 0.30}
        new_weights, reasons = strategy_tracker.suggest_weight_adjustments(current)
        assert isinstance(new_weights, dict)
        # canslim has >60% win rate with 6 trades → should get boost
        assert "canslim" in reasons

    def test_weight_adjustment_recording(self, clean_tracker):
        old = {"canslim": 0.40, "greenblatt": 0.30}
        new = {"canslim": 0.45, "greenblatt": 0.25}
        strategy_tracker.record_weight_adjustment(old, new, {"canslim": "+0.05"})

        history = strategy_tracker.get_weight_history()
        assert len(history) == 1
        assert history[0]["old_weights"]["canslim"] == 0.40
