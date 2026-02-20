"""
Tests for trading_interface. Dry-run tests need no API.
Integration tests hit Alpaca paper trading.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

from monaimetrics.config import load_config, RiskProfile
from monaimetrics.data_input import AlpacaClients, reset_clients
from monaimetrics.trading_interface import (
    OrderRequest,
    OrderResult,
    submit_order,
    place_stop_order,
    get_order,
    get_open_orders,
    cancel_order,
    cancel_all_orders,
    _check_position_size,
    _check_slippage,
)


# ---------------------------------------------------------------------------
# Dry-Run Tests (no API needed)
# ---------------------------------------------------------------------------

class TestDryRun:
    def setup_method(self):
        self.cfg = load_config()
        assert self.cfg.dry_run is True

    def test_buy_returns_dry_run(self):
        req = OrderRequest(symbol="AAPL", side="buy", qty=10)
        result = submit_order(req, self.cfg)
        assert result.status == "dry_run"
        assert result.order_id == "dry_run"
        assert result.symbol == "AAPL"
        assert result.qty == 10

    def test_sell_returns_dry_run(self):
        req = OrderRequest(symbol="AAPL", side="sell", qty=5)
        result = submit_order(req, self.cfg)
        assert result.status == "dry_run"

    def test_stop_order_dry_run(self):
        result = place_stop_order("AAPL", 10, 140.0, self.cfg)
        assert result.status == "dry_run"

    def test_cancel_dry_run(self):
        assert cancel_order("fake-id", self.cfg) is True

    def test_cancel_all_dry_run(self):
        assert cancel_all_orders(self.cfg) == 0


class TestSafetyChecks:
    def setup_method(self):
        self.cfg = load_config()

    def test_slippage_ok(self):
        req = OrderRequest(symbol="AAPL", side="buy", qty=10, limit_price=150.0)
        assert _check_slippage(req, 151.0) is None

    def test_slippage_flagged(self):
        req = OrderRequest(symbol="AAPL", side="buy", qty=10, limit_price=150.0)
        msg = _check_slippage(req, 165.0)
        assert msg is not None
        assert "slippage" in msg.lower()

    def test_slippage_not_checked_for_limit_orders(self):
        req = OrderRequest(symbol="AAPL", side="buy", qty=10, order_type="limit", limit_price=150.0)
        assert _check_slippage(req, 165.0) is None

    def test_sell_skips_position_check(self):
        req = OrderRequest(symbol="AAPL", side="sell", qty=10000)
        assert _check_position_size(req, 150.0, self.cfg) is None


class TestOrderRequest:
    def test_defaults(self):
        req = OrderRequest(symbol="AAPL", side="buy", qty=10)
        assert req.order_type == "market"
        assert req.time_in_force == "day"
        assert req.limit_price is None
        assert req.stop_price is None


# ---------------------------------------------------------------------------
# Integration Tests (Alpaca paper trading)
# ---------------------------------------------------------------------------

needs_api = pytest.mark.skipif(
    not os.environ.get("ALPACA_API_KEY"),
    reason="No Alpaca API key",
)


@pytest.fixture(scope="module")
def live_cfg():
    cfg = load_config()
    # Override dry_run for live tests
    object.__setattr__(cfg, "dry_run", False)
    return cfg


@pytest.fixture(scope="module")
def clients():
    cfg = load_config()
    reset_clients()
    return AlpacaClients(cfg.api)


@needs_api
class TestLiveOrders:
    def test_buy_and_cancel(self, live_cfg, clients):
        """Submit a buy, verify accepted, then cancel."""
        req = OrderRequest(symbol="AAPL", side="buy", qty=1)
        result = submit_order(req, live_cfg, clients)

        assert result.status in ("accepted", "filled")
        assert result.order_id != ""
        assert result.symbol == "AAPL"

        if result.status == "accepted":
            success = cancel_order(result.order_id, clients=clients)
            assert success is True

    def test_list_open_orders(self, live_cfg, clients):
        orders = get_open_orders(clients)
        assert isinstance(orders, list)

    def test_invalid_symbol_rejected(self, live_cfg, clients):
        req = OrderRequest(symbol="ZZZNOTREAL123", side="buy", qty=1)
        result = submit_order(req, live_cfg, clients)
        assert result.status == "rejected"

    def test_stop_order(self, live_cfg, clients):
        """Place a stop sell — will be rejected since we hold no MSFT."""
        result = place_stop_order("MSFT", 1, 100.0, live_cfg, clients=clients)
        # Rejected because we don't hold the position, which is fine
        assert result.status in ("accepted", "rejected")

    def test_cancel_all(self, live_cfg, clients):
        cancel_all_orders(clients=clients)
        orders = get_open_orders(clients)
        assert len(orders) == 0
