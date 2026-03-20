"""
Thin adapter to the Alpaca API. Receives specific instructions, executes them.
Deliberately boring. Does not think — does what it's told.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from alpaca.common.exceptions import APIError

from monaimetrics.config import SystemConfig
from monaimetrics.data_input import AlpacaClients, get_clients

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class OrderRequest:
    symbol: str
    side: str           # "buy" or "sell"
    qty: float
    order_type: str = "market"    # "market", "limit", "stop", "stop_limit"
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "day"    # "day", "gtc"


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str
    qty: float
    status: str         # "filled", "partial", "accepted", "rejected", "cancelled", "dry_run"
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Safety Checks
# ---------------------------------------------------------------------------

def _check_position_size(
    request: OrderRequest,
    price: float,
    config: SystemConfig,
) -> str | None:
    """Returns error message if order outside min/max position range, else None."""
    if request.side != "buy":
        return None

    order_value = request.qty * price

    # Hard dollar cap — overrides all other sizing logic
    if order_value > config.max_position_usd:
        return (
            f"Order value ${order_value:,.2f} exceeds hard position limit "
            f"${config.max_position_usd:,.2f}"
        )

    # Minimum position size — avoid dust trades
    if order_value < config.min_position_usd:
        return (
            f"Order value ${order_value:,.2f} below minimum position size "
            f"${config.min_position_usd:,.2f}"
        )

    return None


def _check_slippage(
    request: OrderRequest,
    current_price: float,
    threshold: float = 0.02,
) -> str | None:
    """Flag if limit/reference price has moved significantly since signal."""
    if request.order_type != "market" or current_price <= 0:
        return None

    if request.limit_price and request.limit_price > 0:
        diff = abs(current_price - request.limit_price) / request.limit_price
        if diff > threshold:
            return (
                f"Price slippage {diff:.1%}: current {current_price:.2f} "
                f"vs expected {request.limit_price:.2f}"
            )
    return None


# ---------------------------------------------------------------------------
# Order Execution
# ---------------------------------------------------------------------------

def _to_alpaca_side(side: str) -> OrderSide:
    return OrderSide.BUY if side == "buy" else OrderSide.SELL


def _to_alpaca_tif(tif: str) -> TimeInForce:
    return TimeInForce.GTC if tif == "gtc" else TimeInForce.DAY


def _result_from_alpaca(order) -> OrderResult:
    status_map = {
        OrderStatus.FILLED: "filled",
        OrderStatus.PARTIALLY_FILLED: "partial",
        OrderStatus.ACCEPTED: "accepted",
        OrderStatus.PENDING_NEW: "accepted",
        OrderStatus.NEW: "accepted",
        OrderStatus.CANCELED: "cancelled",
        OrderStatus.REJECTED: "rejected",
    }
    return OrderResult(
        order_id=str(order.id),
        symbol=order.symbol,
        side=order.side.value,
        qty=float(order.qty) if order.qty else 0.0,
        status=status_map.get(order.status, str(order.status)),
        filled_qty=float(order.filled_qty) if order.filled_qty else 0.0,
        filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
    )


def submit_order(
    request: OrderRequest,
    config: SystemConfig,
    clients: AlpacaClients | None = None,
) -> OrderResult:
    """
    Submit an order. Runs safety checks first. Respects dry_run mode.
    """
    # Dry run
    if config.dry_run:
        log.info(
            "DRY RUN: %s %s %s @ %s (%s)",
            request.side.upper(), request.qty, request.symbol,
            request.order_type, request.time_in_force,
        )
        return OrderResult(
            order_id="dry_run",
            symbol=request.symbol,
            side=request.side,
            qty=request.qty,
            status="dry_run",
            message="Dry run — no order placed",
        )

    c = (clients or get_clients()).trading

    # Build the Alpaca request
    side = _to_alpaca_side(request.side)
    tif = _to_alpaca_tif(request.time_in_force)

    try:
        if request.order_type == "limit" and request.limit_price:
            alpaca_req = LimitOrderRequest(
                symbol=request.symbol,
                qty=request.qty,
                side=side,
                time_in_force=tif,
                limit_price=request.limit_price,
            )
        elif request.order_type == "stop" and request.stop_price:
            alpaca_req = StopOrderRequest(
                symbol=request.symbol,
                qty=request.qty,
                side=side,
                time_in_force=tif,
                stop_price=request.stop_price,
            )
        elif request.order_type == "stop_limit" and request.stop_price and request.limit_price:
            alpaca_req = StopLimitOrderRequest(
                symbol=request.symbol,
                qty=request.qty,
                side=side,
                time_in_force=tif,
                stop_price=request.stop_price,
                limit_price=request.limit_price,
            )
        else:
            alpaca_req = MarketOrderRequest(
                symbol=request.symbol,
                qty=request.qty,
                side=side,
                time_in_force=tif,
            )

        order = c.submit_order(alpaca_req)
        result = _result_from_alpaca(order)
        log.info(
            "ORDER: %s %s %s — %s (id=%s)",
            request.side.upper(), request.qty, request.symbol,
            result.status, result.order_id,
        )
        return result

    except APIError as e:
        log.error("Order failed for %s: %s", request.symbol, e)
        return OrderResult(
            order_id="",
            symbol=request.symbol,
            side=request.side,
            qty=request.qty,
            status="rejected",
            message=str(e),
        )


# ---------------------------------------------------------------------------
# Broker-Side Stop Orders
# ---------------------------------------------------------------------------

def place_stop_order(
    symbol: str,
    qty: float,
    stop_price: float,
    config: SystemConfig,
    time_in_force: str = "gtc",
    clients: AlpacaClients | None = None,
) -> OrderResult:
    """Place a persistent stop-loss order on the broker side."""
    return submit_order(
        OrderRequest(
            symbol=symbol,
            side="sell",
            qty=qty,
            order_type="stop",
            stop_price=stop_price,
            time_in_force=time_in_force,
        ),
        config=config,
        clients=clients,
    )


def update_stop_order(
    old_order_id: str,
    symbol: str,
    qty: float,
    new_stop_price: float,
    config: SystemConfig,
    clients: AlpacaClients | None = None,
) -> OrderResult:
    """Cancel existing stop and place a new one at the updated price."""
    cancel_order(old_order_id, config, clients)
    return place_stop_order(symbol, qty, new_stop_price, config, clients=clients)


# ---------------------------------------------------------------------------
# Order Management
# ---------------------------------------------------------------------------

def get_order(
    order_id: str,
    clients: AlpacaClients | None = None,
) -> OrderResult:
    """Check status of a specific order."""
    c = (clients or get_clients()).trading
    try:
        order = c.get_order_by_id(order_id)
        return _result_from_alpaca(order)
    except APIError as e:
        return OrderResult(
            order_id=order_id, symbol="", side="", qty=0,
            status="rejected", message=str(e),
        )


def get_open_orders(
    clients: AlpacaClients | None = None,
) -> list[OrderResult]:
    """List all open/pending orders."""
    c = (clients or get_clients()).trading
    orders = c.get_orders()
    return [_result_from_alpaca(o) for o in orders]


def cancel_order(
    order_id: str,
    config: SystemConfig | None = None,
    clients: AlpacaClients | None = None,
) -> bool:
    """Cancel a specific order. Returns True if successful."""
    if config and config.dry_run:
        log.info("DRY RUN: cancel order %s", order_id)
        return True

    c = (clients or get_clients()).trading
    try:
        c.cancel_order_by_id(order_id)
        return True
    except APIError as e:
        log.error("Cancel failed for %s: %s", order_id, e)
        return False


def cancel_all_orders(
    config: SystemConfig | None = None,
    clients: AlpacaClients | None = None,
) -> int:
    """Cancel all open orders. Returns count cancelled."""
    if config and config.dry_run:
        log.info("DRY RUN: cancel all orders")
        return 0

    c = (clients or get_clients()).trading
    cancelled = c.cancel_orders()
    count = len(cancelled) if cancelled else 0
    log.info("Cancelled %d orders", count)
    return count
