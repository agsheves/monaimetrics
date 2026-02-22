"""
The orchestrator. Owns 'when' and 'how', never 'what'.
Coordinates data_input, strategy, and trading_interface.
If you see a decision about whether a stock is a good buy here,
something has gone wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from math import floor

from monaimetrics.config import SignalType, SignalUrgency, Tier, SystemConfig
from monaimetrics.data_input import (
    AlpacaClients, get_clients, get_account, get_positions,
    get_technical_data, get_bulk_bars, get_latest_price, AccountInfo,
)
from monaimetrics.strategy import (
    ManagedPosition, Signal, TradingPlan,
    review_position, evaluate_opportunity, update_trailing_stop,
    generate_plan,
)
from monaimetrics.trading_interface import (
    OrderRequest, OrderResult,
    submit_order, place_stop_order, cancel_order, get_open_orders,
    cancel_all_orders,
)
from monaimetrics import calculators
from monaimetrics.alpha_signals import (
    SignalCache, TradeTypeResolver,
    load_signal_definitions, refresh_signals,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Execution Log Entry
# ---------------------------------------------------------------------------

@dataclass
class ExecutionRecord:
    timestamp: datetime
    signal: Signal
    order_result: OrderResult | None
    notes: str = ""


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------

class PortfolioManager:
    """
    Coordinates the trading cycle. Maintains managed position state.
    Call run_assessment() for a full cycle, or run_stop_check() for
    a lightweight price-only check.
    """

    def __init__(
        self,
        config: SystemConfig,
        clients: AlpacaClients | None = None,
    ):
        self.config = config
        self.clients = clients or get_clients(config.api)
        self.managed_positions: list[ManagedPosition] = []
        self.stop_order_ids: dict[str, str] = {}  # symbol → stop order id
        self.execution_log: list[ExecutionRecord] = []
        self.cycle_score: int = 0
        self.peak_value: float = 0.0
        self.stops_today: int = 0
        self.stops_today_date: datetime | None = None
        self.paused: bool = False
        self.pause_reason: str = ""
        self.pause_until: datetime | None = None

        # Alpha signals
        self.alpha_definitions = []
        self.alpha_cache = SignalCache()
        self.trade_type_resolver = TradeTypeResolver()
        if config.alpha_signals.enabled:
            try:
                defs, type_overrides = load_signal_definitions(
                    config.alpha_signals.config_path,
                )
                self.alpha_definitions = defs
                self.trade_type_resolver = TradeTypeResolver(
                    overrides=type_overrides,
                    alpaca_trading_client=self.clients.trading if self.clients else None,
                )
                log.info(
                    "Alpha signals loaded: %d signal(s), %d trade type override(s)",
                    len(defs), len(type_overrides),
                )
            except Exception as e:
                log.warning("Failed to load alpha signals: %s", e)

    # ----- Alpha Signals -----

    def refresh_alpha_signals(self, context: dict | None = None):
        """Refresh all alpha signal values (fetch + normalize + cache)."""
        if not self.alpha_definitions:
            return
        ctx = context or {}
        if self.config.api.decis_base_url:
            ctx.setdefault("base_url", self.config.api.decis_base_url)
        refresh_signals(self.alpha_definitions, self.alpha_cache, ctx)

    # ----- Tier Accounting -----

    def tier_values(self) -> dict[Tier, float]:
        values = {Tier.MODERATE: 0.0, Tier.HIGH: 0.0}
        for pos in self.managed_positions:
            values[pos.tier] += pos.qty * pos.current_price
        return values

    # ----- Position Sync -----

    def sync_positions(self):
        """Update current prices from broker. Add weeks_held increment."""
        for pos in self.managed_positions:
            try:
                price = get_latest_price(pos.symbol, self.clients)
                if price > 0:
                    pos.current_price = price
                    pos.highest_price = max(pos.highest_price, price)
            except Exception as e:
                log.warning("Price fetch failed for %s: %s", pos.symbol, e)

    def update_weeks_held(self):
        """Increment weeks_held based on entry_date."""
        now = datetime.now(timezone.utc)
        for pos in self.managed_positions:
            delta = now - pos.entry_date
            pos.weeks_held = delta.days // 7

    # ----- Circuit Breakers -----

    def check_circuit_breakers(self) -> bool:
        """
        Check all circuit breakers. Returns True if system should pause.
        Updates self.paused and self.pause_reason.
        """
        # Check if existing pause has expired
        if self.paused and self.pause_until:
            if datetime.now(timezone.utc) >= self.pause_until:
                log.info("Pause expired, resuming")
                self.paused = False
                self.pause_reason = ""
                self.pause_until = None

        try:
            account = get_account(self.clients)
        except Exception as e:
            self.paused = True
            self.pause_reason = f"API failure: {e}"
            log.error("Circuit breaker: API failure — %s", e)
            return True

        # Track peak
        if account.portfolio_value > self.peak_value:
            self.peak_value = account.portfolio_value

        # Max drawdown
        if self.peak_value > 0:
            drawdown = (self.peak_value - account.portfolio_value) / self.peak_value
            if drawdown >= self.config.circuit_breakers.max_drawdown:
                self.paused = True
                self.pause_reason = f"Max drawdown {drawdown:.1%} >= {self.config.circuit_breakers.max_drawdown:.1%}"
                log.warning("Circuit breaker: %s", self.pause_reason)
                return True

        # Rapid loss (3+ stops in one day)
        today = datetime.now(timezone.utc).date()
        if self.stops_today_date and self.stops_today_date != today:
            self.stops_today = 0
        self.stops_today_date = today

        if self.stops_today >= self.config.circuit_breakers.rapid_loss_count:
            self.paused = True
            self.pause_until = datetime.now(timezone.utc) + timedelta(
                hours=self.config.circuit_breakers.rapid_loss_pause_hours
            )
            self.pause_reason = f"Rapid loss: {self.stops_today} stops today"
            log.warning("Circuit breaker: %s", self.pause_reason)
            return True

        return self.paused

    # ----- Trailing Stop Maintenance -----

    def update_trailing_stops(self):
        """Recalculate trailing stops for all high-risk positions."""
        for pos in self.managed_positions:
            if pos.tier != Tier.HIGH:
                continue
            try:
                tech = get_technical_data(pos.symbol, days=30, clients=self.clients)
                new_stop = update_trailing_stop(pos, tech, self.config)
                if new_stop > pos.trailing_stop:
                    pos.trailing_stop = new_stop
                    old_id = self.stop_order_ids.get(pos.symbol, "")
                    if old_id and not self.config.dry_run:
                        cancel_order(old_id, self.config, self.clients)
                    result = place_stop_order(
                        pos.symbol, pos.qty, new_stop,
                        self.config, clients=self.clients,
                    )
                    if result.order_id:
                        self.stop_order_ids[pos.symbol] = result.order_id
                    log.info(
                        "Trailing stop updated %s: %.2f → %.2f",
                        pos.symbol, pos.trailing_stop, new_stop,
                    )
            except Exception as e:
                log.warning("Trailing stop update failed for %s: %s", pos.symbol, e)

    # ----- Execute Signals -----

    def _execute_buy(self, signal: Signal) -> OrderResult:
        if signal.position_size_usd <= 0:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="buy",
                qty=0, status="rejected", message="Zero position size",
            )

        price = get_latest_price(signal.symbol, self.clients)
        if price <= 0:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="buy",
                qty=0, status="rejected", message="Could not get price",
            )

        qty = floor(signal.position_size_usd / price)
        if qty < 1:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="buy",
                qty=0, status="rejected", message="Size below 1 share",
            )

        result = submit_order(
            OrderRequest(symbol=signal.symbol, side="buy", qty=qty),
            self.config, self.clients,
        )

        if result.status in ("accepted", "filled", "dry_run"):
            entry = result.filled_avg_price or price
            pos = ManagedPosition(
                symbol=signal.symbol,
                tier=signal.tier,
                qty=qty,
                entry_price=entry,
                entry_date=datetime.now(timezone.utc),
                stop_price=signal.stop_price,
                target_price=signal.target_price,
                trailing_stop=signal.stop_price if signal.tier == Tier.HIGH else 0.0,
                highest_price=entry,
                current_price=entry,
            )
            self.managed_positions.append(pos)

            # Place broker-side stop
            stop_result = place_stop_order(
                signal.symbol, qty, signal.stop_price,
                self.config, clients=self.clients,
            )
            if stop_result.order_id:
                self.stop_order_ids[signal.symbol] = stop_result.order_id

            log.info(
                "BUY %s %d shares @ %.2f (%s tier, stop=%.2f)",
                signal.symbol, qty, entry, signal.tier.value, signal.stop_price,
            )

        return result

    def _execute_sell(self, signal: Signal) -> OrderResult:
        pos = next(
            (p for p in self.managed_positions if p.symbol == signal.symbol),
            None,
        )
        if pos is None:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="sell",
                qty=0, status="rejected", message="No managed position found",
            )

        result = submit_order(
            OrderRequest(symbol=signal.symbol, side="sell", qty=pos.qty),
            self.config, self.clients,
        )

        if result.status in ("accepted", "filled", "dry_run"):
            # Cancel associated stop order
            stop_id = self.stop_order_ids.pop(signal.symbol, "")
            if stop_id:
                cancel_order(stop_id, self.config, self.clients)

            self.managed_positions = [
                p for p in self.managed_positions if p.symbol != signal.symbol
            ]

            # Track stops for circuit breaker
            if "stop" in " ".join(signal.reasons).lower():
                self.stops_today += 1

            gain = calculators.gain_pct(pos.current_price, pos.entry_price)
            log.info(
                "SELL %s %d shares (%.1f%% gain, reason: %s)",
                signal.symbol, int(pos.qty), gain * 100,
                signal.reasons[0] if signal.reasons else "unknown",
            )

        return result

    def _execute_reduce(self, signal: Signal) -> OrderResult:
        pos = next(
            (p for p in self.managed_positions if p.symbol == signal.symbol),
            None,
        )
        if pos is None:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="sell",
                qty=0, status="rejected", message="No managed position found",
            )

        # Calculate trim qty from concentration breach
        tv = self.tier_values()
        tier_val = tv.get(pos.tier, 0.0)
        max_pos = (self.config.moderate_tier.max_position if pos.tier == Tier.MODERATE
                   else self.config.high_risk_tier.max_position)
        target_value = max_pos * tier_val
        current_value = pos.qty * pos.current_price
        trim_value = current_value - target_value
        trim_qty = floor(trim_value / pos.current_price) if pos.current_price > 0 else 0

        if trim_qty < 1:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="sell",
                qty=0, status="rejected", message="Trim below 1 share",
            )

        result = submit_order(
            OrderRequest(symbol=signal.symbol, side="sell", qty=trim_qty),
            self.config, self.clients,
        )

        if result.status in ("accepted", "filled", "dry_run"):
            pos.qty -= trim_qty
            log.info("REDUCE %s by %d shares", signal.symbol, trim_qty)

        return result

    def execute_plan(self, plan: TradingPlan) -> list[ExecutionRecord]:
        """Execute all signals in priority order."""
        records = []

        for signal in plan.signals:
            if signal.action == SignalType.HOLD or signal.action == SignalType.WATCH:
                records.append(ExecutionRecord(
                    timestamp=datetime.now(timezone.utc),
                    signal=signal, order_result=None,
                    notes="No action required",
                ))
                continue

            # Pause check — still execute emergency sells
            is_emergency = signal.urgency in (SignalUrgency.EMERGENCY, SignalUrgency.IMMEDIATE)
            if self.paused and signal.action == SignalType.BUY:
                records.append(ExecutionRecord(
                    timestamp=datetime.now(timezone.utc),
                    signal=signal, order_result=None,
                    notes=f"Paused: {self.pause_reason}",
                ))
                continue

            if signal.action == SignalType.BUY:
                result = self._execute_buy(signal)
            elif signal.action in (SignalType.SELL,):
                result = self._execute_sell(signal)
            elif signal.action == SignalType.REDUCE:
                result = self._execute_reduce(signal)
            else:
                result = None

            records.append(ExecutionRecord(
                timestamp=datetime.now(timezone.utc),
                signal=signal, order_result=result,
            ))

        self.execution_log.extend(records)
        return records

    # ----- Full Assessment Cycle -----

    def run_assessment(
        self,
        watchlist: list[str] | None = None,
    ) -> tuple[TradingPlan, list[ExecutionRecord]]:
        """
        Full cycle: sync positions, get data, ask strategy, execute.
        Returns the plan and execution records.
        """
        log.info("Starting assessment cycle")

        # 1. Sync
        self.sync_positions()
        self.update_weeks_held()
        self.update_trailing_stops()

        # 2. Circuit breakers
        self.check_circuit_breakers()

        # 3. Get account state
        account = get_account(self.clients)
        tv = self.tier_values()

        # 4. Gather technical data
        all_symbols = list({p.symbol for p in self.managed_positions})
        if watchlist:
            all_symbols.extend(s for s in watchlist if s not in all_symbols)

        technicals = {}
        for sym in all_symbols:
            try:
                technicals[sym] = get_technical_data(sym, clients=self.clients)
            except Exception as e:
                log.warning("Tech data failed for %s: %s", sym, e)

        # 5. Refresh alpha signals
        if self.config.alpha_signals.enabled and self.config.alpha_signals.refresh_on_cycle:
            self.refresh_alpha_signals()
            self.trade_type_resolver.preload(all_symbols)

        # 6. Ask strategy
        alpha_kwargs = {}
        if self.config.alpha_signals.enabled and self.alpha_definitions:
            alpha_kwargs = dict(
                alpha_definitions=self.alpha_definitions,
                alpha_cache=self.alpha_cache,
                trade_type_resolver=self.trade_type_resolver,
            )

        plan = generate_plan(
            self.managed_positions, technicals,
            account, tv, self.config, self.cycle_score,
            **alpha_kwargs,
        )

        log.info(
            "Plan: %d signals (%d sells, %d buys, %d holds)",
            len(plan.signals),
            sum(1 for s in plan.signals if s.action == SignalType.SELL),
            sum(1 for s in plan.signals if s.action == SignalType.BUY),
            sum(1 for s in plan.signals if s.action == SignalType.HOLD),
        )

        # 7. Execute
        records = self.execute_plan(plan)

        return plan, records

    # ----- Lightweight Stop Check -----

    def run_stop_check(self) -> list[ExecutionRecord]:
        """
        Quick price-only check for stop-loss breaches.
        Runs more frequently than full assessment.
        """
        if not self.managed_positions:
            return []

        self.sync_positions()
        records = []

        for pos in list(self.managed_positions):
            # Fixed stop
            if pos.current_price <= pos.stop_price:
                signal = Signal(
                    symbol=pos.symbol,
                    action=SignalType.SELL,
                    urgency=SignalUrgency.EMERGENCY,
                    tier=pos.tier,
                    confidence=100,
                    reasons=[f"Stop-loss hit: {pos.current_price:.2f} <= {pos.stop_price:.2f}"],
                )
                result = self._execute_sell(signal)
                records.append(ExecutionRecord(
                    timestamp=datetime.now(timezone.utc),
                    signal=signal, order_result=result,
                ))
                continue

            # Trailing stop (high-risk)
            if pos.tier == Tier.HIGH and pos.trailing_stop > 0:
                if pos.current_price <= pos.trailing_stop:
                    signal = Signal(
                        symbol=pos.symbol,
                        action=SignalType.SELL,
                        urgency=SignalUrgency.EMERGENCY,
                        tier=pos.tier,
                        confidence=100,
                        reasons=[f"Trailing stop hit: {pos.current_price:.2f} <= {pos.trailing_stop:.2f}"],
                    )
                    result = self._execute_sell(signal)
                    records.append(ExecutionRecord(
                        timestamp=datetime.now(timezone.utc),
                        signal=signal, order_result=result,
                    ))
                    continue

            # Profit target (moderate)
            if pos.tier == Tier.MODERATE and pos.target_price > 0:
                if pos.current_price >= pos.target_price:
                    signal = Signal(
                        symbol=pos.symbol,
                        action=SignalType.SELL,
                        urgency=SignalUrgency.IMMEDIATE,
                        tier=pos.tier,
                        confidence=100,
                        reasons=[f"Profit target: {pos.current_price:.2f} >= {pos.target_price:.2f}"],
                    )
                    result = self._execute_sell(signal)
                    records.append(ExecutionRecord(
                        timestamp=datetime.now(timezone.utc),
                        signal=signal, order_result=result,
                    ))

        if records:
            self.execution_log.extend(records)
            self.check_circuit_breakers()

        return records

    # ----- Manual Override -----

    def manual_sell(self, symbol: str, reason: str = "Manual override") -> OrderResult | None:
        """Human-initiated sell. Logged as override, not strategy recommendation."""
        pos = next(
            (p for p in self.managed_positions if p.symbol == symbol),
            None,
        )
        if pos is None:
            log.warning("Manual sell: no position found for %s", symbol)
            return None

        signal = Signal(
            symbol=symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.IMMEDIATE,
            tier=pos.tier,
            confidence=100,
            reasons=[f"MANUAL: {reason}"],
        )
        result = self._execute_sell(signal)
        self.execution_log.append(ExecutionRecord(
            timestamp=datetime.now(timezone.utc),
            signal=signal, order_result=result,
            notes="Manual override — not a strategy recommendation",
        ))
        return result

    # ----- Emergency Halt -----

    def emergency_halt(self) -> list[OrderResult]:
        """Close all positions and cancel all orders. Manual restart required."""
        log.warning("EMERGENCY HALT initiated")
        self.paused = True
        self.pause_reason = "Emergency halt"

        cancel_all_orders(self.config, self.clients)

        results = []
        for pos in list(self.managed_positions):
            result = self._execute_sell(Signal(
                symbol=pos.symbol,
                action=SignalType.SELL,
                urgency=SignalUrgency.EMERGENCY,
                tier=pos.tier,
                confidence=100,
                reasons=["Emergency halt — closing all positions"],
            ))
            results.append(result)

        return results

    # ----- State Summary -----

    def summary(self) -> dict:
        """Quick snapshot of portfolio state."""
        tv = self.tier_values()
        try:
            account = get_account(self.clients)
            portfolio_value = account.portfolio_value
            cash = account.cash
        except Exception:
            portfolio_value = sum(tv.values())
            cash = 0.0

        return {
            "positions": len(self.managed_positions),
            "moderate_value": tv[Tier.MODERATE],
            "high_value": tv[Tier.HIGH],
            "portfolio_value": portfolio_value,
            "cash": cash,
            "peak_value": self.peak_value,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "cycle_score": self.cycle_score,
            "stops_today": self.stops_today,
            "dry_run": self.config.dry_run,
        }
