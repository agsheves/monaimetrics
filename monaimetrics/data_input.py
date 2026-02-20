"""
Adapter layer for all external data. The rest of the system never touches
an API directly — everything comes through here in standardised structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient

from monaimetrics.config import APIConfig, load_config
from monaimetrics import calculators


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class BarRecord:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class AccountInfo:
    cash: float
    portfolio_value: float
    buying_power: float
    status: str


@dataclass
class PositionInfo:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float


@dataclass
class TechnicalData:
    symbol: str
    price: float
    ma_150: float
    ma_slope: float
    atr_14: float
    volume_ratio: float
    stage: int
    timestamp: datetime


@dataclass
class SourceHealth:
    source: str
    status: str  # "ok", "stale", "error"
    last_updated: datetime | None
    message: str = ""


# ---------------------------------------------------------------------------
# Client Management
# ---------------------------------------------------------------------------

class AlpacaClients:
    """Lazy-initialised Alpaca clients. One instance per data_input lifecycle."""

    def __init__(self, api_config: APIConfig):
        self._api_config = api_config
        self._trading: TradingClient | None = None
        self._data: StockHistoricalDataClient | None = None

    @property
    def trading(self) -> TradingClient:
        if self._trading is None:
            self._trading = TradingClient(
                self._api_config.alpaca_api_key,
                self._api_config.alpaca_secret_key,
                paper=True,
            )
        return self._trading

    @property
    def data(self) -> StockHistoricalDataClient:
        if self._data is None:
            self._data = StockHistoricalDataClient(
                self._api_config.alpaca_api_key,
                self._api_config.alpaca_secret_key,
            )
        return self._data


_clients: AlpacaClients | None = None


def get_clients(api_config: APIConfig | None = None) -> AlpacaClients:
    """Get or create the shared Alpaca client pair."""
    global _clients
    if _clients is None:
        if api_config is None:
            api_config = load_config().api
        _clients = AlpacaClients(api_config)
    return _clients


def reset_clients():
    """Reset clients (for testing or reconnection)."""
    global _clients
    _clients = None


# ---------------------------------------------------------------------------
# Account / Portfolio
# ---------------------------------------------------------------------------

def get_account(clients: AlpacaClients | None = None) -> AccountInfo:
    c = (clients or get_clients()).trading
    acct = c.get_account()
    return AccountInfo(
        cash=float(acct.cash),
        portfolio_value=float(acct.portfolio_value),
        buying_power=float(acct.buying_power),
        status=str(acct.status),
    )


def get_positions(clients: AlpacaClients | None = None) -> list[PositionInfo]:
    c = (clients or get_clients()).trading
    positions = c.get_all_positions()
    return [
        PositionInfo(
            symbol=p.symbol,
            qty=float(p.qty),
            avg_entry_price=float(p.avg_entry_price),
            current_price=float(p.current_price),
            market_value=float(p.market_value),
            unrealized_pl=float(p.unrealized_pl),
            unrealized_pl_pct=float(p.unrealized_plpc),
        )
        for p in positions
    ]


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

def get_bars(
    symbol: str,
    days: int = 200,
    clients: AlpacaClients | None = None,
) -> list[BarRecord]:
    """Fetch daily bars for a symbol. Returns oldest-first."""
    c = (clients or get_clients()).data
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    barset = c.get_stock_bars(request)
    bars = barset[symbol] if symbol in barset.data else []

    return [
        BarRecord(
            timestamp=b.timestamp,
            open=float(b.open),
            high=float(b.high),
            low=float(b.low),
            close=float(b.close),
            volume=float(b.volume),
        )
        for b in bars
    ]


def get_latest_price(
    symbol: str,
    clients: AlpacaClients | None = None,
) -> float:
    """Get the most recent closing price for a symbol."""
    bars = get_bars(symbol, days=5, clients=clients)
    if not bars:
        return 0.0
    return bars[-1].close


def get_bulk_bars(
    symbols: list[str],
    days: int = 200,
    clients: AlpacaClients | None = None,
) -> dict[str, list[BarRecord]]:
    """Fetch daily bars for multiple symbols in one call."""
    c = (clients or get_clients()).data
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    barset = c.get_stock_bars(request)

    result = {}
    for sym in symbols:
        bars = barset[sym] if sym in barset.data else []
        result[sym] = [
            BarRecord(
                timestamp=b.timestamp,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in bars
        ]
    return result


# ---------------------------------------------------------------------------
# Technical Data (raw bars → computed indicators via calculators)
# ---------------------------------------------------------------------------

def get_technical_data(
    symbol: str,
    days: int = 200,
    clients: AlpacaClients | None = None,
) -> TechnicalData:
    """Fetch bars and compute technical indicators for a single stock."""
    bars = get_bars(symbol, days=days, clients=clients)

    if not bars:
        return TechnicalData(
            symbol=symbol, price=0.0, ma_150=0.0, ma_slope=0.0,
            atr_14=0.0, volume_ratio=0.0, stage=1,
            timestamp=datetime.now(timezone.utc),
        )

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]

    price = closes[-1]
    ma_150 = calculators.simple_moving_average(closes, 150)
    slope = calculators.ma_slope(closes, 150, lookback=10)
    atr_14 = calculators.average_true_range(highs, lows, closes, 14)
    avg_vol = calculators.simple_moving_average(volumes, 50)
    vol_ratio = calculators.volume_ratio(volumes[-1], avg_vol)

    stage = calculators.stage_from_ma(
        current_price=price,
        ma_value=ma_150,
        ma_slope=slope,
        volume_ratio=vol_ratio,
    )

    return TechnicalData(
        symbol=symbol,
        price=price,
        ma_150=ma_150,
        ma_slope=slope,
        atr_14=atr_14,
        volume_ratio=vol_ratio,
        stage=stage,
        timestamp=bars[-1].timestamp,
    )


# ---------------------------------------------------------------------------
# Source Health
# ---------------------------------------------------------------------------

def check_alpaca_health(clients: AlpacaClients | None = None) -> SourceHealth:
    """Quick health check on Alpaca connectivity."""
    try:
        acct = get_account(clients)
        return SourceHealth(
            source="alpaca",
            status="ok",
            last_updated=datetime.now(timezone.utc),
        )
    except Exception as e:
        return SourceHealth(
            source="alpaca",
            status="error",
            last_updated=None,
            message=str(e),
        )
