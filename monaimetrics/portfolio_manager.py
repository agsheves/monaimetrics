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
    review_position, evaluate_opportunity,
    generate_plan,
)
from monaimetrics.trading_interface import (
    OrderRequest, OrderResult,
    submit_order, submit_bracket_buy, place_stop_order, cancel_order,
    get_open_orders, cancel_all_orders,
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

    def load_from_broker(self) -> set[str]:
        """Sync managed_positions with live Alpaca positions.

        - Adds positions present at broker but not yet tracked.
        - Removes tracked positions that no longer exist at broker (stop/target/
          manual close).
        - Updates qty and current_price for positions already tracked.
        - Populates stop_order_ids from open stop/stop_limit orders.

        In dry_run mode the app never submits real orders, so the broker holds
        no positions placed by this PM. The sync is skipped; simulated positions
        that were added via execute_plan() remain in managed_positions and their
        prices are updated via get_latest_price() in sync_positions().

        Returns the set of symbols successfully synced from the broker.
        """
        if self.config.dry_run:
            return set()

        try:
            broker_positions = get_positions(self.clients)
        except Exception as e:
            log.warning("load_from_broker: could not fetch positions: %s", e)
            return set()

        broker_symbols = {p.symbol for p in broker_positions}

        # Remove tracked positions that are no longer at the broker
        # (closed by bracket stop, take-profit, or manual action).
        if not self.config.dry_run:
            closed = [
                p.symbol for p in self.managed_positions
                if p.symbol not in broker_symbols
            ]
            if closed:
                log.info(
                    "load_from_broker: %d position(s) closed at broker: %s",
                    len(closed), closed,
                )
                self.managed_positions = [
                    p for p in self.managed_positions
                    if p.symbol in broker_symbols
                ]
                for sym in closed:
                    self.stop_order_ids.pop(sym, None)

        # Build stop order map: symbol → (stop_price, order_id).
        # Uses actual open orders so we always have the real current stop level.
        stop_map: dict[str, tuple[float, str]] = {}
        if not self.config.dry_run:
            try:
                for order in get_open_orders(self.clients):
                    if (
                        order.symbol
                        and order.side == "sell"
                        and order.order_type in ("stop", "stop_limit")
                        and order.stop_price is not None
                        and order.stop_price > 0
                        and order.order_id
                    ):
                        existing = stop_map.get(order.symbol)
                        if existing is None or order.stop_price > existing[0]:
                            stop_map[order.symbol] = (order.stop_price, order.order_id)
            except Exception as e:
                log.warning("load_from_broker: could not fetch open orders: %s", e)

        tracked_map = {p.symbol: p for p in self.managed_positions}
        added: list[str] = []

        for bp in broker_positions:
            if bp.symbol in tracked_map:
                # Refresh live data for existing tracked position
                pos = tracked_map[bp.symbol]
                pos.current_price = bp.current_price
                pos.qty = bp.qty
                # Populate stop_order_id if we have a fresher entry
                if bp.symbol in stop_map and not self.stop_order_ids.get(bp.symbol):
                    _, oid = stop_map[bp.symbol]
                    if oid:
                        self.stop_order_ids[bp.symbol] = oid
                continue

            # New position — bootstrap from broker data + open orders
            entry = bp.avg_entry_price
            stop_pct = self.config.moderate_tier.stop_loss
            profit_pct = self.config.moderate_tier.profit_target

            if bp.symbol in stop_map:
                stop_price, oid = stop_map[bp.symbol]
                if oid:
                    self.stop_order_ids[bp.symbol] = oid
            else:
                stop_price = round(entry * (1 - stop_pct), 4)

            target_price = round(entry * (1 + profit_pct), 4)

            pos = ManagedPosition(
                symbol=bp.symbol,
                tier=Tier.MODERATE,
                qty=bp.qty,
                entry_price=entry,
                entry_date=datetime.now(timezone.utc),
                stop_price=stop_price,
                target_price=target_price,
                current_price=bp.current_price,
                bracket_position=True,
            )
            self.managed_positions.append(pos)
            added.append(bp.symbol)

        if added:
            log.info(
                "load_from_broker: bootstrapped %d new position(s): %s",
                len(added), added,
            )

        return broker_symbols

    def sync_positions(self):
        """Sync managed_positions with the broker and update current prices."""
        synced = self.load_from_broker()
        # For any tracked positions not returned by the broker (e.g. dry_run
        # simulations that were never submitted), fall back to a direct price fetch.
        for pos in self.managed_positions:
            if pos.symbol in synced:
                continue
            try:
                price = get_latest_price(pos.symbol, self.clients)
                if price > 0:
                    pos.current_price = price
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

    # ----- Execute Signals -----

    def _execute_buy(self, signal: Signal) -> OrderResult:
        if signal.position_size_usd <= 0:
            return OrderResult(
                order_id="", symbol=signal.symbol, side="buy",
                qty=0, status="rejected", message="Zero position size",
            )

        # Cash reserve check — never deploy more than (1 - cash_reserve_pct) of cash
        try:
            account = get_account(self.clients)
            total_cash = float(account.cash)
            reserve = total_cash * self.config.cash_reserve_pct
            spendable = total_cash - reserve
            if spendable < signal.position_size_usd:
                return OrderResult(
                    order_id="", symbol=signal.symbol, side="buy",
                    qty=0, status="rejected",
                    message=(
                        f"Cash reserve: ${total_cash:.0f} total, "
                        f"${reserve:.0f} held in reserve, "
                        f"${spendable:.0f} spendable < ${signal.position_size_usd:.0f} needed"
                    ),
                )
        except Exception as e:
            log.warning("Could not check cash reserve for %s: %s", signal.symbol, e)

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

        # Cancel any existing stop order for this symbol before buying to avoid
        # "potential wash trade" rejections from Alpaca.
        old_stop_id = self.stop_order_ids.pop(signal.symbol, "")
        if old_stop_id and not self.config.dry_run:
            cancel_order(old_stop_id, self.config, self.clients)

        # Submit as a bracket order (buy + embedded stop-loss in one request).
        # Falls back to plain buy + separate stop if the bracket is rejected.
        target = signal.target_price if signal.target_price > 0 else None
        result, stop_order_id, bracket_used = submit_bracket_buy(
            signal.symbol, qty, signal.stop_price,
            config=self.config,
            target_price=target,
            clients=self.clients,
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
                current_price=entry,
                bracket_position=bracket_used,
            )
            self.managed_positions.append(pos)

            if stop_order_id:
                # Got the stop-loss leg ID from the bracket — track it for
                # later cancel/update (e.g. breakeven lock).
                self.stop_order_ids[signal.symbol] = stop_order_id
            elif not bracket_used:
                # Bracket was rejected and we fell back to a plain market buy;
                # place a separate stop-loss now.
                stop_result = place_stop_order(
                    signal.symbol, qty, signal.stop_price,
                    self.config, clients=self.clients,
                )
                if stop_result.order_id:
                    self.stop_order_ids[signal.symbol] = stop_result.order_id
            # else: bracket accepted but no leg ID yet (pending fill) — the
            # stop is broker-managed; do NOT create a second stop order.

            log.info(
                "BUY %s %d shares @ %.2f (%s tier, stop=%.2f, bracket=%s)",
                signal.symbol, qty, entry, signal.tier.value,
                signal.stop_price, bracket_used,
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
        # Always sync first — picks up new positions, removes broker-closed ones,
        # and refreshes prices (including dry_run simulations not in broker).
        # The early-return check comes AFTER the sync so that positions opened
        # since the last run are immediately tracked.
        self.sync_positions()

        if not self.managed_positions:
            return []

        records = []

        for pos in list(self.managed_positions):
            # Ratchet trailing stop: raise stop one 5% step for each 5% gain above entry.
            # Stateless — computed from entry_price and current_price only.
            # Updates both stop_price in memory and the broker-side stop order.
            if pos.entry_price > 0 and pos.current_price > pos.entry_price:
                ratchet_level = calculators.ratchet_stop_level(
                    pos.entry_price, pos.current_price, self.config.ratchet_step_pct
                )
                if ratchet_level is not None and ratchet_level > pos.stop_price:
                    old_id = self.stop_order_ids.get(pos.symbol, "")

                    # For bracket positions without a tracked stop ID, scan open
                    # orders to find and cancel the broker-side stop leg.
                    # Filter by order_type=="stop" or "stop_limit" to avoid
                    # accidentally cancelling a take-profit (limit) leg.
                    if not old_id and pos.bracket_position and not self.config.dry_run:
                        try:
                            for open_ord in get_open_orders(self.clients):
                                if (
                                    open_ord.symbol == pos.symbol
                                    and open_ord.side == "sell"
                                    and open_ord.order_id
                                    and open_ord.order_type in ("stop", "stop_limit")
                                ):
                                    old_id = open_ord.order_id
                                    break
                        except Exception as e:
                            log.warning(
                                "Ratchet: could not query open orders for %s: %s",
                                pos.symbol, e,
                            )

                    if old_id and not self.config.dry_run:
                        cancel_order(old_id, self.config, self.clients)
                        self.stop_order_ids.pop(pos.symbol, None)

                    stop_result = place_stop_order(
                        pos.symbol, pos.qty, ratchet_level,
                        self.config, clients=self.clients,
                    )
                    if stop_result.order_id:
                        self.stop_order_ids[pos.symbol] = stop_result.order_id
                    log.info(
                        "Ratchet: %s stop raised $%.4f → $%.4f (entry=$%.4f, step=%.0f%%)",
                        pos.symbol, pos.stop_price, ratchet_level, pos.entry_price,
                        self.config.ratchet_step_pct * 100,
                    )
                    pos.stop_price = ratchet_level

            # Fixed stop (covers ratcheted stop too — stop_price was updated above)
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
