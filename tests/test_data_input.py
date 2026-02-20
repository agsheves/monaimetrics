"""
Integration tests for data_input against Alpaca paper trading.
These hit the real API — requires valid keys in .env.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

from monaimetrics.config import load_config
from monaimetrics.data_input import (
    AlpacaClients,
    get_account,
    get_positions,
    get_bars,
    get_latest_price,
    get_bulk_bars,
    get_technical_data,
    check_alpaca_health,
    reset_clients,
)


pytestmark = pytest.mark.skipif(
    not os.environ.get("ALPACA_API_KEY"),
    reason="No Alpaca API key — skipping integration tests",
)


@pytest.fixture(scope="module")
def clients():
    cfg = load_config()
    reset_clients()
    return AlpacaClients(cfg.api)


class TestAccount:
    def test_get_account(self, clients):
        acct = get_account(clients)
        assert acct.status == "AccountStatus.ACTIVE"
        assert acct.cash > 0
        assert acct.portfolio_value > 0

    def test_get_positions_returns_list(self, clients):
        positions = get_positions(clients)
        assert isinstance(positions, list)


class TestBars:
    def test_get_bars_aapl(self, clients):
        bars = get_bars("AAPL", days=30, clients=clients)
        assert len(bars) > 0
        assert bars[0].close > 0
        assert bars[0].volume > 0

    def test_bars_ordered_oldest_first(self, clients):
        bars = get_bars("AAPL", days=30, clients=clients)
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_get_latest_price(self, clients):
        price = get_latest_price("AAPL", clients=clients)
        assert price > 100  # AAPL should be well above $100

    def test_get_bulk_bars(self, clients):
        result = get_bulk_bars(["AAPL", "MSFT"], days=30, clients=clients)
        assert "AAPL" in result
        assert "MSFT" in result
        assert len(result["AAPL"]) > 0


class TestTechnicalData:
    def test_aapl_technical(self, clients):
        tech = get_technical_data("AAPL", days=200, clients=clients)
        assert tech.symbol == "AAPL"
        assert tech.price > 0
        assert tech.ma_150 > 0
        assert tech.atr_14 > 0
        assert tech.volume_ratio > 0
        assert tech.stage in (1, 2, 3, 4)

    def test_stage_is_reasonable(self, clients):
        tech = get_technical_data("AAPL", days=200, clients=clients)
        assert tech.stage == 2 or tech.stage in (1, 2, 3, 4)


class TestHealth:
    def test_health_ok(self, clients):
        health = check_alpaca_health(clients)
        assert health.status == "ok"
        assert health.source == "alpaca"
