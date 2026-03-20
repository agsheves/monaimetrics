"""
Historical backtest engine.

Simulates the trading strategy over historical daily prices using cached
Alpha Vantage data + fundamentals. Runs entirely from local cache files
(Replit-friendly, no database).

Usage:
    from monaimetrics.backtest import run_backtest, BacktestConfig
    result = run_backtest(BacktestConfig(
        symbols=["AAPL", "MSFT", "GOOGL"],
        start_date="2024-01-01",
        end_date="2024-12-31",
    ))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from monaimetrics.config import (
    SystemConfig, RiskProfile, Tier, SignalType, Stage,
    load_config,
)
from monaimetrics import calculators
from monaimetrics.fundamental_data import (
    FundamentalData, get_fundamentals_cached_only, get_daily_prices,
)

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    symbols: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 100_000.0
    risk_profile: str = "moderate"
    max_positions: int = 10


@dataclass
class BacktestTrade:
    symbol: str
    action: str
    date: str
    price: float
    qty: int
    value: float
    reason: str
    confidence: int = 0


@dataclass
class BacktestPosition:
    symbol: str
    qty: int
    entry_price: float
    entry_date: str
    stop_price: float
    target_price: float
    tier: Tier = Tier.MODERATE


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: list[BacktestTrade]
    final_value: float
    total_return: float
    total_return_pct: float
    win_count: int
    loss_count: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    max_drawdown: float
    equity_curve: list[dict]
    symbols_evaluated: int
    days_simulated: int
    error: str | None = None


def _build_technicals_from_bars(
    bars: list[dict],
    idx: int,
    period: int = 150,
) -> dict:
    """Build a minimal technical snapshot from bar history up to idx."""
    if idx < period:
        return {}

    closes = [b["close"] for b in bars[:idx + 1]]
    highs = [b["high"] for b in bars[:idx + 1]]
    lows = [b["low"] for b in bars[:idx + 1]]
    volumes = [b["volume"] for b in bars[:idx + 1]]

    price = closes[-1]
    ma_150 = calculators.simple_moving_average(closes, period)
    slope = calculators.ma_slope(closes, period, lookback=10)
    atr = calculators.average_true_range(highs, lows, closes, 14)

    avg_vol = calculators.simple_moving_average(
        [float(v) for v in volumes[-50:]], 50,
    ) if len(volumes) >= 50 else (sum(volumes) / len(volumes) if volumes else 1)
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

    stage = calculators.stage_from_ma(price, ma_150, slope, vol_ratio)

    return {
        "price": price,
        "ma_150": ma_150,
        "ma_slope": slope,
        "atr_14": atr,
        "volume_ratio": vol_ratio,
        "stage": stage,
    }


def _score_opportunity(
    tech: dict,
    fund: FundamentalData | None,
    config: SystemConfig,
) -> tuple[int, float, float]:
    """Score a stock and return (confidence, stop_price, target_price)."""
    from monaimetrics.strategy import (
        score_technical, score_canslim, score_greenblatt,
        compute_composite_confidence,
    )
    from monaimetrics.data_input import TechnicalData

    td = TechnicalData(
        symbol="",
        price=tech["price"],
        ma_150=tech["ma_150"],
        ma_slope=tech["ma_slope"],
        atr_14=tech["atr_14"],
        volume_ratio=tech["volume_ratio"],
        stage=tech["stage"],
        timestamp=datetime.now(),
    )

    tech_score = score_technical(td, config)
    canslim = score_canslim(fund, td, config)
    greenblatt = score_greenblatt(fund, config)
    confidence = compute_composite_confidence(
        tech_score, canslim, greenblatt, Tier.MODERATE, config,
    )

    stop = calculators.stop_loss_price(tech["price"], config.moderate_tier.stop_loss)
    target = calculators.profit_target_price(
        tech["price"], config.moderate_tier.profit_target,
        tech["atr_14"], config.moderate_tier.vol_adjustment_factor,
    )

    return confidence, stop, target


def run_backtest(bt_config: BacktestConfig) -> BacktestResult:
    """Run a historical backtest simulation."""
    try:
        profile = RiskProfile(bt_config.risk_profile)
    except ValueError:
        profile = RiskProfile.MODERATE

    config = load_config(profile)

    # Load price data for all symbols
    all_bars: dict[str, list[dict]] = {}
    fundamentals: dict[str, FundamentalData] = {}

    for sym in bt_config.symbols:
        bars = get_daily_prices(sym, outputsize="full")
        if bars:
            all_bars[sym] = bars
        fund = get_fundamentals_cached_only(sym)
        if fund:
            fundamentals[sym] = fund

    if not all_bars:
        return BacktestResult(
            config=bt_config, trades=[], final_value=bt_config.initial_capital,
            total_return=0, total_return_pct=0, win_count=0, loss_count=0,
            win_rate=0, avg_win_pct=0, avg_loss_pct=0, max_drawdown=0,
            equity_curve=[], symbols_evaluated=0, days_simulated=0,
            error="No price data available. Ensure symbols are cached via Alpha Vantage.",
        )

    # Filter bars to date range
    start = bt_config.start_date
    end = bt_config.end_date

    # Build a unified date list from the first symbol that has data
    all_dates = set()
    for bars in all_bars.values():
        for b in bars:
            if start <= b["date"] <= end:
                all_dates.add(b["date"])
    dates = sorted(all_dates)

    if not dates:
        return BacktestResult(
            config=bt_config, trades=[], final_value=bt_config.initial_capital,
            total_return=0, total_return_pct=0, win_count=0, loss_count=0,
            win_rate=0, avg_win_pct=0, avg_loss_pct=0, max_drawdown=0,
            equity_curve=[], symbols_evaluated=0, days_simulated=0,
            error=f"No trading days found between {start} and {end}.",
        )

    # Build date-indexed bar lookup for each symbol
    bar_by_date: dict[str, dict[str, dict]] = {}
    bar_idx: dict[str, dict[str, int]] = {}
    for sym, bars in all_bars.items():
        bar_by_date[sym] = {b["date"]: b for b in bars}
        bar_idx[sym] = {b["date"]: i for i, b in enumerate(bars)}

    # Simulation state
    cash = bt_config.initial_capital
    positions: dict[str, BacktestPosition] = {}
    trades: list[BacktestTrade] = []
    equity_curve: list[dict] = []
    peak_value = bt_config.initial_capital
    max_drawdown = 0.0
    wins: list[float] = []
    losses: list[float] = []

    for date in dates:
        # Update position values & check exits
        for sym in list(positions.keys()):
            if sym not in bar_by_date or date not in bar_by_date[sym]:
                continue

            bar = bar_by_date[sym][date]
            pos = positions[sym]
            price = bar["close"]

            # Stop-loss check
            if price <= pos.stop_price:
                value = pos.qty * price
                gain_pct = (price - pos.entry_price) / pos.entry_price
                cash += value
                trades.append(BacktestTrade(
                    symbol=sym, action="SELL", date=date, price=price,
                    qty=pos.qty, value=value,
                    reason=f"Stop-loss: ${price:.2f} <= ${pos.stop_price:.2f}",
                ))
                if gain_pct >= 0:
                    wins.append(gain_pct)
                else:
                    losses.append(gain_pct)
                del positions[sym]
                continue

            # Profit target check
            if pos.target_price > 0 and price >= pos.target_price:
                value = pos.qty * price
                gain_pct = (price - pos.entry_price) / pos.entry_price
                cash += value
                trades.append(BacktestTrade(
                    symbol=sym, action="SELL", date=date, price=price,
                    qty=pos.qty, value=value,
                    reason=f"Target hit: ${price:.2f} >= ${pos.target_price:.2f}",
                ))
                wins.append(gain_pct)
                del positions[sym]
                continue

        # Evaluate new opportunities (only if we have room)
        if len(positions) < bt_config.max_positions:
            for sym in bt_config.symbols:
                if sym in positions:
                    continue
                if sym not in all_bars or date not in bar_idx[sym]:
                    continue

                idx = bar_idx[sym][date]
                tech = _build_technicals_from_bars(all_bars[sym], idx)
                if not tech or tech["stage"] != Stage.ADVANCING.value:
                    continue

                fund = fundamentals.get(sym)
                confidence, stop, target = _score_opportunity(tech, fund, config)

                if confidence < config.kelly.min_conviction:
                    continue

                # Size via Kelly
                position_capital = cash * 0.95  # leave 5% buffer
                avail = min(position_capital, config.max_position_usd)
                kelly_size = calculators.kelly_position_size(
                    win_prob=confidence / 100.0,
                    avg_win=0.25,
                    avg_loss=config.moderate_tier.stop_loss,
                    fraction_multiplier=config.moderate_tier.kelly_fraction,
                    available_capital=avail,
                    max_position=config.moderate_tier.max_position,
                )

                price = tech["price"]
                if kelly_size < config.min_position_usd or price <= 0:
                    continue

                qty = int(kelly_size / price)
                if qty < 1:
                    continue

                cost = qty * price
                if cost > cash:
                    continue

                cash -= cost
                positions[sym] = BacktestPosition(
                    symbol=sym, qty=qty, entry_price=price,
                    entry_date=date, stop_price=stop, target_price=target,
                )
                trades.append(BacktestTrade(
                    symbol=sym, action="BUY", date=date, price=price,
                    qty=qty, value=cost,
                    reason=f"Confidence {confidence}/100, Stage 2",
                    confidence=confidence,
                ))

                if len(positions) >= bt_config.max_positions:
                    break

        # Calculate portfolio value
        port_value = cash
        for sym, pos in positions.items():
            if sym in bar_by_date and date in bar_by_date[sym]:
                port_value += pos.qty * bar_by_date[sym][date]["close"]
            else:
                port_value += pos.qty * pos.entry_price

        equity_curve.append({"date": date, "value": round(port_value, 2)})

        if port_value > peak_value:
            peak_value = port_value
        dd = (peak_value - port_value) / peak_value if peak_value > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    # Close remaining positions at last known price
    for sym, pos in list(positions.items()):
        last_bar = None
        for d in reversed(dates):
            if sym in bar_by_date and d in bar_by_date[sym]:
                last_bar = bar_by_date[sym][d]
                break
        if last_bar:
            price = last_bar["close"]
            value = pos.qty * price
            gain_pct = (price - pos.entry_price) / pos.entry_price
            cash += value
            trades.append(BacktestTrade(
                symbol=sym, action="SELL", date=dates[-1], price=price,
                qty=pos.qty, value=value,
                reason="End of backtest period",
            ))
            if gain_pct >= 0:
                wins.append(gain_pct)
            else:
                losses.append(gain_pct)

    final_value = cash
    total_return = final_value - bt_config.initial_capital
    total_return_pct = total_return / bt_config.initial_capital if bt_config.initial_capital > 0 else 0
    total_trades = len(wins) + len(losses)

    return BacktestResult(
        config=bt_config,
        trades=trades,
        final_value=round(final_value, 2),
        total_return=round(total_return, 2),
        total_return_pct=round(total_return_pct, 4),
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=round(len(wins) / total_trades, 4) if total_trades > 0 else 0,
        avg_win_pct=round(sum(wins) / len(wins), 4) if wins else 0,
        avg_loss_pct=round(sum(losses) / len(losses), 4) if losses else 0,
        max_drawdown=round(max_drawdown, 4),
        equity_curve=equity_curve,
        symbols_evaluated=len(all_bars),
        days_simulated=len(dates),
    )
