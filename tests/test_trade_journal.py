"""Tests for the trade journal module."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Use a temp directory for tests
os.environ.setdefault("JOURNAL_TEST_MODE", "1")

from monaimetrics import trade_journal


@pytest.fixture(autouse=True)
def clean_journal(tmp_path, monkeypatch):
    """Use a temp journal file for each test."""
    journal_path = tmp_path / "journal.jsonl"
    monkeypatch.setattr(trade_journal, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(trade_journal, "JOURNAL_PATH", journal_path)
    yield journal_path


class TestLogEvent:
    def test_basic_event(self, clean_journal):
        event = trade_journal.log_event("SYSTEM", data={"msg": "startup"})
        assert event["type"] == "SYSTEM"
        assert "ts" in event
        assert clean_journal.exists()

    def test_trade_event(self, clean_journal):
        event = trade_journal.log_event(
            "EXECUTION",
            symbol="AAPL",
            action="BUY",
            confidence=78,
            price=175.50,
            qty=10,
            value=1755.00,
            reasons=["Stage 2 confirmed", "Confidence 78/100"],
            framework_scores={"canslim": 82.0, "greenblatt": 71.0, "technical": 68.0},
        )
        assert event["symbol"] == "AAPL"
        assert event["action"] == "BUY"
        assert event["confidence"] == 78
        assert event["price"] == 175.50
        assert len(event["reasons"]) == 2

    def test_multiple_events(self, clean_journal):
        for i in range(5):
            trade_journal.log_event("SYSTEM", data={"count": i})
        lines = clean_journal.read_text().strip().split("\n")
        assert len(lines) == 5


class TestReadEvents:
    def test_read_empty(self, clean_journal):
        events = trade_journal.read_events()
        assert events == []

    def test_read_with_type_filter(self, clean_journal):
        trade_journal.log_event("EXECUTION", symbol="AAPL")
        trade_journal.log_event("SYSTEM")
        trade_journal.log_event("EXECUTION", symbol="MSFT")

        execs = trade_journal.read_events(event_type="EXECUTION")
        assert len(execs) == 2
        assert execs[0]["symbol"] == "AAPL"

    def test_read_with_symbol_filter(self, clean_journal):
        trade_journal.log_event("EXECUTION", symbol="AAPL")
        trade_journal.log_event("EXECUTION", symbol="MSFT")

        aapl = trade_journal.read_events(symbol="AAPL")
        assert len(aapl) == 1

    def test_read_with_limit(self, clean_journal):
        for i in range(10):
            trade_journal.log_event("SYSTEM", data={"i": i})
        events = trade_journal.read_events(limit=3)
        assert len(events) == 3
        # Should be the last 3
        assert events[0]["data"]["i"] == 7

    def test_read_with_since(self, clean_journal):
        # Write a past event manually
        old_event = {
            "ts": "2020-01-01T00:00:00+00:00",
            "type": "SYSTEM",
            "symbol": "",
            "action": "",
            "confidence": 0,
            "price": 0,
            "qty": 0,
            "value": 0,
            "outcome": "",
            "reasons": [],
            "framework_scores": {},
            "data": {},
        }
        with open(clean_journal, "w") as f:
            f.write(json.dumps(old_event) + "\n")

        trade_journal.log_event("SYSTEM", data={"recent": True})

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = trade_journal.read_events(since=since)
        assert len(events) == 1
        assert events[0]["data"].get("recent") is True


class TestHelpers:
    def test_recent_trades(self, clean_journal):
        trade_journal.log_event("EXECUTION", symbol="AAPL", action="BUY")
        trade_journal.log_event("SYSTEM")
        trade_journal.log_event("EXECUTION", symbol="MSFT", action="SELL")

        trades = trade_journal.recent_trades()
        assert len(trades) == 2

    def test_trades_for_symbol(self, clean_journal):
        trade_journal.log_event("EXECUTION", symbol="AAPL")
        trade_journal.log_event("EXECUTION", symbol="MSFT")
        trade_journal.log_event("EXECUTION", symbol="AAPL")

        aapl = trade_journal.trades_for_symbol("AAPL")
        assert len(aapl) == 2

    def test_daily_summary(self, clean_journal):
        trade_journal.log_event("EXECUTION", symbol="AAPL", action="BUY", value=1000)
        trade_journal.log_event("EXECUTION", symbol="MSFT", action="SELL", value=2000)
        trade_journal.log_event("STOP_TRIGGERED", symbol="TSLA")
        trade_journal.log_event("ASSESSMENT")

        summary = trade_journal.daily_summary()
        assert summary["buys"] == 1
        assert summary["sells"] == 1
        assert summary["stops_triggered"] == 1
        assert summary["assessments"] == 1
        assert summary["buy_value"] == 1000
        assert summary["sell_value"] == 2000

    def test_recent_activity(self, clean_journal):
        trade_journal.log_event("SYSTEM")
        trade_journal.log_event("EXECUTION", symbol="AAPL")
        events = trade_journal.recent_activity()
        assert len(events) == 2
