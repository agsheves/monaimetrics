"""
Arbitrage trading on Kalshi prediction markets.
Functionally separate from stock trading — own config, own accounting,
own execution. Shares nothing with strategy.py or portfolio_manager.py.

Kalshi is CFTC-regulated and USD-settled. No crypto volatility.

Strategy: buy both sides of a binary event when combined prices < $1 minus
fees. One side always pays $1, locking in guaranteed profit.

Target: 1–2 % per trade, 3–4 trades per week, compounding.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArbSide(Enum):
    YES = "yes"
    NO = "no"


class ArbStatus(Enum):
    PENDING = "pending"
    OPEN = "open"          # both legs filled
    PARTIAL = "partial"    # one leg filled, risk state
    SETTLED = "settled"
    FAILED = "failed"


class LegStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ArbConfig:
    """Every tunable for arb trading. Separate from SystemConfig."""

    # Kalshi credentials
    kalshi_api_key: str = ""
    kalshi_private_key_path: str = ""   # file path to PEM
    kalshi_private_key_pem: str = ""    # or inline PEM content

    # Environment
    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    use_demo: bool = True  # start on demo by default

    # Scanning — Kalshi series tickers for sports game markets
    scan_categories: tuple[str, ...] = ("KXNBAGAME", "KXNHLGAME", "KXMLSGAME")
    min_outcomes: int = 2
    max_outcomes: int = 2  # strict binary for now

    # Thresholds (in cents — Kalshi operates in cents)
    min_profit_cents: int = 1         # minimum net profit per contract after fees
    min_profit_pct: float = 0.01      # 1 % minimum return per trade
    max_combined_price_cents: int = 99  # reject if combined > this before fees

    # Sizing
    max_contracts_per_leg: int = 100
    max_cost_per_trade_cents: int = 50_000  # $500 cap per arb trade
    min_cost_per_trade_cents: int = 5_000   # $50 minimum to bother

    # Execution
    use_fok: bool = True              # Fill-or-Kill for taker execution
    slippage_tolerance_cents: int = 1  # max price move between scan and execute

    # Risk
    max_open_arbs: int = 3
    max_daily_trades: int = 6
    max_capital_deployed_cents: int = 200_000  # $2,000 max at risk at once

    # Compounding
    reinvest_profits: bool = True
    compound_reserve_pct: float = 0.0  # keep 0 % in reserve (reinvest all)

    dry_run: bool = True

    @property
    def effective_base_url(self) -> str:
        if self.use_demo:
            return "https://demo-api.kalshi.co/trade-api/v2"
        return self.kalshi_base_url


def load_arb_config() -> ArbConfig:
    """Build ArbConfig from environment variables."""
    import os

    # KALSHI_PRIVATE_KEY_PATH can be a file path or inline PEM content.
    raw_key = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    if raw_key.strip().startswith("-----BEGIN"):
        key_path = ""
        key_pem = raw_key
    else:
        key_path = raw_key
        key_pem = ""

    return ArbConfig(
        kalshi_api_key=os.environ.get("KALSHI_API_KEY", ""),
        kalshi_private_key_path=key_path,
        kalshi_private_key_pem=key_pem,
        use_demo=os.environ.get("KALSHI_USE_DEMO", "true").lower() == "true",
        dry_run=os.environ.get("ARB_DRY_RUN", "true").lower() == "true",
    )


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class KalshiMarket:
    """A single Kalshi market (one outcome of an event)."""
    ticker: str
    event_ticker: str
    title: str
    status: str          # "open", "closed", "settled"
    yes_bid: int         # best bid for yes in cents
    yes_ask: int         # best ask for yes in cents
    no_bid: int          # best bid for no in cents
    no_ask: int          # best ask for no in cents
    volume: int
    result: str          # "" while open, "yes" or "no" when settled


@dataclass
class ArbOpportunity:
    """A detected arbitrage opportunity across an event's markets."""
    event_ticker: str
    side: ArbSide                    # buying YES or NO on both legs
    markets: list[KalshiMarket]
    prices_cents: list[int]          # ask price per contract on each leg
    combined_cost_cents: int         # sum of ask prices for 1 contract each
    fees_cents: list[int]            # taker fee per contract per leg
    total_fee_cents: int
    gross_profit_cents: int          # 100 - combined_cost
    net_profit_cents: int            # gross - total_fee
    net_profit_pct: float            # net / (combined_cost + total_fee)
    contracts: int                   # contracts to buy per leg
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ArbLeg:
    """One side of an arb trade."""
    market_ticker: str
    side: ArbSide
    action: str          # "buy"
    contracts: int
    price_cents: int
    fee_cents: int
    order_id: str = ""
    status: LegStatus = LegStatus.PENDING
    filled_price_cents: int = 0


@dataclass
class ArbTrade:
    """A complete arb trade with both legs and accounting."""
    trade_id: str
    event_ticker: str
    legs: list[ArbLeg]
    status: ArbStatus = ArbStatus.PENDING
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    settled_at: datetime | None = None
    total_cost_cents: int = 0
    total_fees_cents: int = 0
    payout_cents: int = 0
    net_profit_cents: int = 0


# ---------------------------------------------------------------------------
# Separate Accounting Ledger
# ---------------------------------------------------------------------------

@dataclass
class ArbLedger:
    """
    Standalone accounting for arb operations. Does not touch Alpaca balances.
    All values in cents for consistency with Kalshi.
    """
    starting_balance_cents: int = 0
    current_balance_cents: int = 0
    total_deployed_cents: int = 0
    total_profit_cents: int = 0
    total_fees_cents: int = 0
    trades_today: int = 0
    trades_this_week: int = 0
    last_trade_date: str = ""
    trade_history: list[dict] = field(default_factory=list)
    open_trades: list[ArbTrade] = field(default_factory=list)

    @property
    def available_cents(self) -> int:
        return self.current_balance_cents - self.total_deployed_cents

    @property
    def total_return_pct(self) -> float:
        if self.starting_balance_cents <= 0:
            return 0.0
        return self.total_profit_cents / self.starting_balance_cents

    def record_open(self, trade: ArbTrade) -> None:
        self.total_deployed_cents += trade.total_cost_cents
        self.total_fees_cents += trade.total_fees_cents
        self.current_balance_cents -= trade.total_cost_cents
        self.open_trades.append(trade)
        self.trades_today += 1
        self.trades_this_week += 1
        self.last_trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log.info(
            "ARB OPEN: %s — cost %d¢, fees %d¢, deployed %d¢",
            trade.trade_id, trade.total_cost_cents,
            trade.total_fees_cents, self.total_deployed_cents,
        )

    def record_settlement(self, trade: ArbTrade) -> None:
        self.total_deployed_cents -= (trade.total_cost_cents)
        self.total_profit_cents += trade.net_profit_cents
        self.current_balance_cents += trade.payout_cents
        self.open_trades = [
            t for t in self.open_trades if t.trade_id != trade.trade_id
        ]
        self.trade_history.append({
            "trade_id": trade.trade_id,
            "event": trade.event_ticker,
            "cost_cents": trade.total_cost_cents,
            "fees_cents": trade.total_fees_cents,
            "payout_cents": trade.payout_cents,
            "profit_cents": trade.net_profit_cents,
            "opened": trade.opened_at.isoformat(),
            "settled": (trade.settled_at or datetime.now(timezone.utc)).isoformat(),
        })
        log.info(
            "ARB SETTLED: %s — payout %d¢, profit %d¢, balance %d¢",
            trade.trade_id, trade.payout_cents,
            trade.net_profit_cents, self.current_balance_cents,
        )

    def reset_daily(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.last_trade_date != today:
            self.trades_today = 0

    def reset_weekly(self) -> None:
        self.trades_this_week = 0

    def summary(self) -> dict:
        return {
            "balance_usd": self.current_balance_cents / 100,
            "deployed_usd": self.total_deployed_cents / 100,
            "available_usd": self.available_cents / 100,
            "total_profit_usd": self.total_profit_cents / 100,
            "total_fees_usd": self.total_fees_cents / 100,
            "return_pct": round(self.total_return_pct * 100, 2),
            "open_trades": len(self.open_trades),
            "trades_today": self.trades_today,
            "trades_this_week": self.trades_this_week,
            "lifetime_trades": len(self.trade_history),
        }

    def export_json(self, path: Path) -> None:
        data = {"summary": self.summary(), "trade_history": self.trade_history}
        path.write_text(json.dumps(data, indent=2))
        log.info("Arb ledger exported to %s", path)


# ---------------------------------------------------------------------------
# Kalshi API Client
# ---------------------------------------------------------------------------

class KalshiClient:
    """
    Thin wrapper around the Kalshi REST API. Handles RSA-PSS signing.
    Deliberately minimal — does what it's told.
    """

    def __init__(self, config: ArbConfig):
        self._config = config
        self._base_url = config.effective_base_url
        self._api_key = config.kalshi_api_key
        self._private_key = self._load_private_key(
            config.kalshi_private_key_path,
            config.kalshi_private_key_pem,
        )
        self._session = requests.Session()

        # Extract the URL path prefix for request signing.
        # Kalshi requires signing the full path (e.g. /trade-api/v2/markets)
        # not just the relative path after the base URL.
        from urllib.parse import urlparse
        self._path_prefix = urlparse(self._base_url).path.rstrip("/")

    @staticmethod
    def _load_private_key(path: str, pem_inline: str = ""):
        """Load RSA key from file path or inline PEM string."""
        if pem_inline:
            pem_data = pem_inline.strip().encode()
        elif path:
            pem_data = Path(path).read_bytes()
        else:
            return None
        return serialization.load_pem_private_key(pem_data, password=None)

    def _sign_request(self, method: str, path: str) -> dict[str, str]:
        """Build auth headers with RSA-PSS signature."""
        if not self._private_key or not self._api_key:
            return {}

        timestamp_ms = str(int(time.time() * 1000))
        message = (timestamp_ms + method.upper() + path).encode()

        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256.digest_size,
            ),
            hashes.SHA256(),
        )

        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        sign_path = f"{self._path_prefix}{path}"
        headers = self._sign_request("GET", sign_path)
        resp = self._session.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}{path}"
        sign_path = f"{self._path_prefix}{path}"
        headers = self._sign_request("POST", sign_path)
        resp = self._session.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        sign_path = f"{self._path_prefix}{path}"
        headers = self._sign_request("DELETE", sign_path)
        resp = self._session.delete(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # -- Market Data -------------------------------------------------------

    def get_events(
        self,
        status: str = "open",
        series_ticker: str = "",
        cursor: str = "",
        limit: int = 200,
    ) -> tuple[list[dict], str]:
        """Fetch events. Returns (events, next_cursor)."""
        params: dict[str, Any] = {"status": status, "limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        data = self._get("/events", params)
        return data.get("events", []), data.get("cursor", "")

    def get_event(self, event_ticker: str) -> dict:
        params = {"with_nested_markets": "true"}
        return self._get(f"/events/{event_ticker}", params)

    def get_markets(
        self,
        event_ticker: str = "",
        series_ticker: str = "",
        status: str = "",
        cursor: str = "",
        limit: int = 200,
    ) -> tuple[list[dict], str]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        data = self._get("/markets", params)
        return data.get("markets", []), data.get("cursor", "")

    def get_orderbook(self, ticker: str) -> dict:
        return self._get(f"/markets/{ticker}/orderbook")

    def get_balance(self) -> int:
        """Account balance in cents."""
        data = self._get("/portfolio/balance")
        return data.get("balance", 0)

    def get_positions(self) -> list[dict]:
        data = self._get("/portfolio/positions")
        return data.get("market_positions", [])

    # -- Trading -----------------------------------------------------------

    def place_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        yes_price: int | None = None,
        no_price: int | None = None,
        time_in_force: str = "fill_or_kill",
    ) -> dict:
        """Place an order. Prices in cents (1–99)."""
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": "limit",
            "time_in_force": time_in_force,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        return self._post("/portfolio/orders", body)

    def cancel_order(self, order_id: str) -> dict:
        return self._delete(f"/portfolio/orders/{order_id}")


# ---------------------------------------------------------------------------
# Fee Calculation
# ---------------------------------------------------------------------------

def kalshi_taker_fee_cents(contracts: int, price_cents: int) -> int:
    """
    Kalshi taker fee: ceil(0.07 * C * P * (1 - P))
    P in dollars (price_cents / 100). Result in cents.
    Max 1.75 cents per contract.
    """
    p = price_cents / 100.0
    raw = 0.07 * contracts * p * (1.0 - p)
    fee_cents = math.ceil(raw)
    max_fee = math.ceil(1.75 * contracts)
    return min(fee_cents, max_fee)


def kalshi_maker_fee_cents(contracts: int, price_cents: int) -> int:
    """
    Kalshi maker fee: ceil(0.0175 * C * P * (1 - P))
    4x cheaper than taker.
    """
    p = price_cents / 100.0
    raw = 0.0175 * contracts * p * (1.0 - p)
    return math.ceil(raw)


# ---------------------------------------------------------------------------
# Market Parsing
# ---------------------------------------------------------------------------

def _parse_market(raw: dict) -> KalshiMarket:
    """Convert raw Kalshi API market dict to KalshiMarket."""
    return KalshiMarket(
        ticker=raw.get("ticker", ""),
        event_ticker=raw.get("event_ticker", ""),
        title=raw.get("title", ""),
        status=raw.get("status", ""),
        yes_bid=raw.get("yes_bid", 0) or 0,
        yes_ask=raw.get("yes_ask", 0) or 0,
        no_bid=raw.get("no_bid", 0) or 0,
        no_ask=raw.get("no_ask", 0) or 0,
        volume=raw.get("volume", 0) or 0,
        result=raw.get("result", ""),
    )


def _parse_event_markets(event_data: dict) -> list[KalshiMarket]:
    """Extract active markets from a nested event response."""
    raw_markets = event_data.get("markets", [])
    return [
        _parse_market(m) for m in raw_markets
        if m.get("status") in ("active", "open")
    ]


# ---------------------------------------------------------------------------
# Arb Detection
# ---------------------------------------------------------------------------

def detect_arb(
    markets: list[KalshiMarket],
    config: ArbConfig,
) -> ArbOpportunity | None:
    """
    Check if a set of markets from one event presents an arb.
    Returns opportunity if profitable after fees, else None.

    For binary events (2 outcomes that are mutually exclusive and exhaustive):
    one side must win. If combined ask prices for YES (or NO) on all
    outcomes < 100¢ minus fees, guaranteed profit exists.
    """
    if len(markets) < config.min_outcomes or len(markets) > config.max_outcomes:
        return None

    # Check both YES arb and NO arb
    for side in (ArbSide.YES, ArbSide.NO):
        if side == ArbSide.YES:
            prices = [m.yes_ask for m in markets]
        else:
            prices = [m.no_ask for m in markets]

        # No liquidity if any ask is missing
        if any(p <= 0 for p in prices):
            continue

        combined = sum(prices)

        # Quick reject
        if combined >= config.max_combined_price_cents:
            continue

        # Fees per leg (1 contract each)
        fees = [kalshi_taker_fee_cents(1, p) for p in prices]
        total_fee = sum(fees)

        gross_profit = 100 - combined
        net_profit = gross_profit - total_fee

        if net_profit < config.min_profit_cents:
            continue

        total_outlay = combined + total_fee
        net_pct = net_profit / total_outlay if total_outlay > 0 else 0.0
        if net_pct < config.min_profit_pct:
            continue

        # Size — how many contracts can we afford within limits?
        cost_per_set = total_outlay
        max_by_capital = (
            config.max_cost_per_trade_cents // cost_per_set
            if cost_per_set > 0 else 0
        )
        contracts = min(max_by_capital, config.max_contracts_per_leg)

        if contracts * cost_per_set < config.min_cost_per_trade_cents:
            continue

        return ArbOpportunity(
            event_ticker=markets[0].event_ticker,
            side=side,
            markets=markets,
            prices_cents=prices,
            combined_cost_cents=combined * contracts,
            fees_cents=[f * contracts for f in fees],
            total_fee_cents=total_fee * contracts,
            gross_profit_cents=gross_profit * contracts,
            net_profit_cents=net_profit * contracts,
            net_profit_pct=net_pct,
            contracts=contracts,
        )

    return None


# ---------------------------------------------------------------------------
# Arb Execution
# ---------------------------------------------------------------------------

def execute_arb(
    opp: ArbOpportunity,
    client: KalshiClient,
    config: ArbConfig,
    ledger: ArbLedger,
) -> ArbTrade | None:
    """
    Execute both legs of an arb. Uses FOK so partial fills don't leave
    us exposed on one side only.

    Returns ArbTrade if successful, None if blocked or failed.
    """
    # Pre-flight checks
    if ledger.trades_today >= config.max_daily_trades:
        log.warning("Daily trade limit reached (%d)", config.max_daily_trades)
        return None

    if len(ledger.open_trades) >= config.max_open_arbs:
        log.warning("Max open arbs reached (%d)", config.max_open_arbs)
        return None

    total_cost = opp.combined_cost_cents + opp.total_fee_cents
    if ledger.available_cents < total_cost:
        log.warning(
            "Insufficient balance: need %d¢, have %d¢",
            total_cost, ledger.available_cents,
        )
        return None

    if ledger.total_deployed_cents + total_cost > config.max_capital_deployed_cents:
        log.warning("Would exceed max deployed capital")
        return None

    # Build legs
    legs = []
    for i, market in enumerate(opp.markets):
        legs.append(ArbLeg(
            market_ticker=market.ticker,
            side=opp.side,
            action="buy",
            contracts=opp.contracts,
            price_cents=opp.prices_cents[i],
            fee_cents=opp.fees_cents[i],
        ))

    trade_id = f"arb_{opp.event_ticker}_{int(time.time())}"
    trade = ArbTrade(
        trade_id=trade_id,
        event_ticker=opp.event_ticker,
        legs=legs,
        total_cost_cents=total_cost,
        total_fees_cents=opp.total_fee_cents,
    )

    # Dry run
    if config.dry_run:
        log.info(
            "DRY RUN ARB: %s — %d contracts, cost %d¢, expected profit %d¢ (%.1f%%)",
            trade_id, opp.contracts, total_cost,
            opp.net_profit_cents, opp.net_profit_pct * 100,
        )
        for leg in legs:
            log.info(
                "  LEG: buy %s %s @ %d¢ × %d",
                leg.side.value, leg.market_ticker,
                leg.price_cents, leg.contracts,
            )
            leg.status = LegStatus.FILLED
            leg.filled_price_cents = leg.price_cents
        trade.status = ArbStatus.OPEN
        ledger.record_open(trade)
        return trade

    # Live execution — both legs with FOK
    tif = "fill_or_kill" if config.use_fok else "good_till_canceled"
    filled_legs: list[ArbLeg] = []

    for leg in legs:
        try:
            price_kwarg = (
                {"yes_price": leg.price_cents}
                if leg.side == ArbSide.YES
                else {"no_price": leg.price_cents}
            )
            result = client.place_order(
                ticker=leg.market_ticker,
                side=leg.side.value,
                action=leg.action,
                count=leg.contracts,
                time_in_force=tif,
                **price_kwarg,
            )
            order = result.get("order", {})
            leg.order_id = order.get("order_id", "")
            status = order.get("status", "")

            if status in ("resting", "executed"):
                leg.status = LegStatus.FILLED
                leg.filled_price_cents = leg.price_cents
                filled_legs.append(leg)
                log.info(
                    "LEG FILLED: %s %s @ %d¢ × %d (order %s)",
                    leg.side.value, leg.market_ticker,
                    leg.price_cents, leg.contracts, leg.order_id,
                )
            else:
                leg.status = LegStatus.REJECTED
                log.warning(
                    "LEG REJECTED: %s %s — status=%s",
                    leg.side.value, leg.market_ticker, status,
                )
        except Exception as e:
            leg.status = LegStatus.REJECTED
            log.error(
                "LEG ERROR: %s %s — %s", leg.side.value, leg.market_ticker, e,
            )

    # Both legs must fill for a valid arb
    if len(filled_legs) == len(legs):
        trade.status = ArbStatus.OPEN
        ledger.record_open(trade)
        log.info("ARB OPENED: %s — all %d legs filled", trade_id, len(legs))
        return trade

    # Partial fill — attempt to unwind. This is the danger zone.
    if filled_legs:
        trade.status = ArbStatus.PARTIAL
        log.error(
            "ARB PARTIAL: %s — %d of %d legs filled. Attempting unwind.",
            trade_id, len(filled_legs), len(legs),
        )
        for leg in filled_legs:
            if leg.order_id:
                try:
                    client.cancel_order(leg.order_id)
                except Exception as e:
                    log.error("Unwind failed for %s: %s", leg.order_id, e)
        trade.status = ArbStatus.FAILED
        return None

    trade.status = ArbStatus.FAILED
    log.warning("ARB FAILED: %s — no legs filled", trade_id)
    return None


# ---------------------------------------------------------------------------
# Settlement Check
# ---------------------------------------------------------------------------

def check_settlements(
    client: KalshiClient,
    ledger: ArbLedger,
) -> list[ArbTrade]:
    """
    Check open arb trades for settlement. When an event resolves,
    the winning leg pays $1 per contract, the losing leg pays $0.
    """
    settled: list[ArbTrade] = []

    for trade in list(ledger.open_trades):
        all_settled = True

        for leg in trade.legs:
            try:
                markets, _ = client.get_markets(
                    event_ticker=trade.event_ticker,
                    status="settled",
                )
                settled_tickers = {m["ticker"] for m in markets}

                if leg.market_ticker not in settled_tickers:
                    all_settled = False
                    break
            except Exception as e:
                log.error(
                    "Settlement check failed for %s: %s", leg.market_ticker, e,
                )
                all_settled = False
                break

        if not all_settled:
            continue

        # Payout: exactly one leg wins ($1 per contract), rest pay $0
        payout = 100 * trade.legs[0].contracts
        trade.payout_cents = payout
        trade.net_profit_cents = payout - trade.total_cost_cents
        trade.status = ArbStatus.SETTLED
        trade.settled_at = datetime.now(timezone.utc)

        ledger.record_settlement(trade)
        settled.append(trade)
        log.info(
            "SETTLED: %s — payout %d¢, net profit %d¢",
            trade.trade_id, payout, trade.net_profit_cents,
        )

    return settled


# ---------------------------------------------------------------------------
# Scanner — Main Loop Entry Point
# ---------------------------------------------------------------------------

def scan_and_evaluate(
    client: KalshiClient,
    config: ArbConfig,
) -> list[ArbOpportunity]:
    """
    Scan Kalshi for arb opportunities. Fetches markets by series,
    groups by event, and checks binary events for mispricing.
    Returns profitable opportunities sorted by net profit % (best first).
    """
    opportunities: list[ArbOpportunity] = []

    for series in config.scan_categories:
        cursor = ""
        while True:
            try:
                raw_markets, cursor = client.get_markets(
                    series_ticker=series,
                    cursor=cursor,
                    limit=200,
                )
            except Exception as e:
                log.error("Market scan failed for %s: %s", series, e)
                break

            # Group markets by event
            by_event: dict[str, list[dict]] = {}
            for m in raw_markets:
                et = m.get("event_ticker", "")
                by_event.setdefault(et, []).append(m)

            for event_ticker, event_markets in by_event.items():
                active = [
                    m for m in event_markets
                    if m.get("status") in ("active", "open")
                ]
                if len(active) < config.min_outcomes:
                    continue
                if len(active) > config.max_outcomes:
                    continue

                parsed = [_parse_market(m) for m in active]
                opp = detect_arb(parsed, config)
                if opp:
                    opportunities.append(opp)
                    log.info(
                        "ARB FOUND: %s — %s side, combined %d¢, net +%d¢ (%.1f%%)",
                        event_ticker, opp.side.value,
                        sum(opp.prices_cents), opp.net_profit_cents,
                        opp.net_profit_pct * 100,
                    )

            if not cursor:
                break

    opportunities.sort(key=lambda o: o.net_profit_pct, reverse=True)
    return opportunities


def run_arb_cycle(
    client: KalshiClient,
    config: ArbConfig,
    ledger: ArbLedger,
) -> dict:
    """
    Full arb cycle: check settlements, scan for new opportunities,
    execute best ones within limits. Returns cycle summary.
    """
    ledger.reset_daily()
    cycle_result: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "settlements": [],
        "opportunities_found": 0,
        "trades_executed": 0,
        "errors": [],
    }

    # 1. Check for settled trades
    try:
        settled = check_settlements(client, ledger)
        cycle_result["settlements"] = [t.trade_id for t in settled]
    except Exception as e:
        log.error("Settlement check error: %s", e)
        cycle_result["errors"].append(f"settlement: {e}")

    # 2. Scan for new opportunities
    opportunities = scan_and_evaluate(client, config)
    cycle_result["opportunities_found"] = len(opportunities)

    # 3. Execute best opportunities within limits
    for opp in opportunities:
        if ledger.trades_today >= config.max_daily_trades:
            break
        if len(ledger.open_trades) >= config.max_open_arbs:
            break

        trade = execute_arb(opp, client, config, ledger)
        if trade:
            cycle_result["trades_executed"] += 1

    return cycle_result


# ---------------------------------------------------------------------------
# Compounding Projection (for dashboard / planning)
# ---------------------------------------------------------------------------

def project_compound_growth(
    starting_balance_cents: int,
    profit_pct_per_trade: float,
    trades_per_week: int,
    weeks: int,
) -> list[dict]:
    """
    Project balance growth with compounding. For dashboard display.
    Returns weekly snapshots.
    """
    balance = starting_balance_cents
    snapshots = []

    for week in range(1, weeks + 1):
        for _ in range(trades_per_week):
            profit = int(balance * profit_pct_per_trade)
            balance += profit

        snapshots.append({
            "week": week,
            "balance_usd": balance / 100,
            "cumulative_return_pct": round(
                (balance - starting_balance_cents)
                / starting_balance_cents * 100, 1,
            ),
        })

    return snapshots
