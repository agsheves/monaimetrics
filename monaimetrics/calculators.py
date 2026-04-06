"""
Pure mathematical functions. No API calls, no state, no side effects.
Numbers in, numbers out. Every function testable with simple assertions.
All percentages as decimals (0.25 = 25%).
"""

from __future__ import annotations

import math


def normalise_score(value: float | None, floor: float = 0.0, ceiling: float = 100.0) -> float:
    """Clamp a value to the 0-100 score range. None returns 0."""
    if value is None:
        return 0.0
    return max(floor, min(ceiling, value))


def composite_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted average of named scores. Ignores keys present in only one dict."""
    shared_keys = set(scores) & set(weights)
    if not shared_keys:
        return 0.0
    total_weight = sum(weights[k] for k in shared_keys)
    if total_weight == 0:
        return 0.0
    return sum(scores[k] * weights[k] for k in shared_keys) / total_weight


def kelly_position_size(
    win_prob: float,
    avg_win: float,
    avg_loss: float,
    fraction_multiplier: float,
    available_capital: float,
    max_position: float,
) -> float:
    """
    Fractional Kelly position size in currency units.
    Returns 0 if edge is non-positive or inputs invalid.
    """
    if avg_loss <= 0 or win_prob <= 0 or win_prob >= 1:
        return 0.0

    win_loss_ratio = avg_win / avg_loss
    kelly_f = win_prob - ((1 - win_prob) / win_loss_ratio)

    if kelly_f <= 0:
        return 0.0

    sized = kelly_f * fraction_multiplier * available_capital
    cap = max_position * available_capital
    return min(sized, cap)


def stop_loss_price(entry_price: float, stop_pct: float) -> float:
    """Fixed percentage stop-loss. Returns the stop price."""
    return entry_price * (1 - stop_pct)


def ratchet_stop_level(
    entry_price: float,
    current_price: float,
    step: float = 0.05,
) -> float | None:
    """
    5%-ratchet trailing stop level (stateless, calculated from entry and current price only).

    Each time price clears a new milestone — entry × (1+step)^n — the stop is
    locked at the previous milestone: entry × (1+step)^(n-1).

    Example with step=0.05 and entry=$1.00:
      price=$1.05  → stop=$1.00  (entry × 1.05^0)
      price=$1.10  → stop=$1.00  (not yet at $1.1025)
      price=$1.1025 → stop=$1.05 (entry × 1.05^1)
      price=$1.1576 → stop=$1.05 (not yet at $1.1576...)
      price=$1.1577 → stop=$1.1025 (entry × 1.05^2)

    Returns the stop price to apply, or None if no milestone has been cleared
    yet (price has not risen by at least one full step above entry).
    """
    if entry_price <= 0 or step <= 0 or current_price <= entry_price:
        return None
    steps_cleared = int(math.log(current_price / entry_price) / math.log(1 + step))
    if steps_cleared < 1:
        return None
    return round(entry_price * (1 + step) ** (steps_cleared - 1), 4)


def atr_stop_loss_price(
    entry_price: float,
    atr: float,
    multiplier: float,
    max_stop_pct: float,
    min_stop_pct: float,
) -> float:
    """ATR-based stop-loss, clamped between min and max percentage."""
    atr_stop = entry_price - (atr * multiplier)
    pct_stop_low = entry_price * (1 - max_stop_pct)
    pct_stop_high = entry_price * (1 - min_stop_pct)
    return max(pct_stop_low, min(pct_stop_high, atr_stop))


def trailing_stop_update(
    current_stop: float,
    highest_price: float,
    entry_price: float,
    milestones: list[tuple[float, float]],
    atr: float,
    mature_atr_multiplier: float,
    mature_gain_threshold: float = 0.50,
) -> float:
    """
    Milestone-based trailing stop. Only moves up, never down.

    milestones: list of (gain_threshold, lock_gain) pairs.
    For gains above mature_gain_threshold, uses ATR-based trailing from highest price.
    """
    gain_pct = (highest_price - entry_price) / entry_price if entry_price > 0 else 0.0

    new_stop = current_stop

    for threshold, lock in sorted(milestones, key=lambda m: m[0]):
        if gain_pct >= threshold:
            milestone_stop = entry_price * (1 + lock)
            new_stop = max(new_stop, milestone_stop)

    if gain_pct > mature_gain_threshold:
        atr_trail = highest_price - (atr * mature_atr_multiplier)
        new_stop = max(new_stop, atr_trail)

    return max(new_stop, current_stop)


def profit_target_price(
    entry_price: float,
    base_target: float,
    atr: float,
    vol_adjustment_factor: float,
) -> float:
    """Volatility-adjusted profit target. Target = base + (factor × ATR as %)."""
    atr_pct = atr / entry_price if entry_price > 0 else 0.0
    adjusted_target = base_target + (vol_adjustment_factor * atr_pct)
    return entry_price * (1 + adjusted_target)


def portfolio_drift(
    current: dict[str, float],
    target: dict[str, float],
) -> dict[str, float]:
    """
    Per-key drift between current and target allocations.
    Positive = overweight, negative = underweight.
    """
    all_keys = set(current) | set(target)
    return {
        k: current.get(k, 0.0) - target.get(k, 0.0)
        for k in all_keys
    }


def max_drift(drifts: dict[str, float]) -> float:
    """Largest absolute drift across all keys."""
    if not drifts:
        return 0.0
    return max(abs(v) for v in drifts.values())


def rebalance_amounts(
    current_values: dict[str, float],
    target_pcts: dict[str, float],
    total_value: float,
) -> dict[str, float]:
    """
    Currency amounts to buy (positive) or sell (negative) per key
    to restore target allocation.
    """
    return {
        k: (target_pcts.get(k, 0.0) * total_value) - current_values.get(k, 0.0)
        for k in set(current_values) | set(target_pcts)
    }


def asymmetry_score(
    expected_upside: float,
    prob_upside: float,
    expected_downside: float,
    prob_downside: float,
) -> float:
    """Asymmetry Score = (upside × prob) / (downside × prob). Returns 0 if denominator is zero."""
    numerator = expected_upside * prob_upside
    denominator = expected_downside * prob_downside
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def stage_from_ma(
    current_price: float,
    ma_value: float,
    ma_slope: float,
    volume_ratio: float,
    breakout_volume_threshold: float = 2.0,
) -> int:
    """
    Classify stock stage (1-4) from moving average behaviour.
    ma_slope: positive = upward, negative = downward, near-zero = flat.
    volume_ratio: current volume / average volume.

    Returns stage number (1=basing, 2=advancing, 3=topping, 4=declining).
    """
    slope_flat_threshold = 0.001

    if ma_slope < -slope_flat_threshold:
        if current_price < ma_value:
            return 4  # declining
        return 1  # basing (price recovered but MA still falling)

    if abs(ma_slope) <= slope_flat_threshold:
        if current_price > ma_value and volume_ratio >= breakout_volume_threshold:
            return 2  # breakout from base
        if current_price < ma_value:
            return 1  # basing
        return 3  # topping (flat MA, price above but no volume breakout)

    # ma_slope > threshold (upward)
    if current_price > ma_value:
        return 2  # advancing
    return 4  # price dropped below rising MA — trend broken


# ---------------------------------------------------------------------------
# Technical Indicators (pure math over price/volume lists)
# ---------------------------------------------------------------------------

def simple_moving_average(values: list[float], period: int | None = None) -> float:
    """SMA over the last `period` values. Uses all values if period is None."""
    if not values:
        return 0.0
    window = values[-period:] if period else values
    return sum(window) / len(window)


def ma_slope(values: list[float], period: int, lookback: int = 10) -> float:
    """
    Slope of the SMA over the last `lookback` days.
    Returns the average daily change in MA value, normalised by current MA.
    Positive = upward, negative = downward, near-zero = flat.
    """
    if len(values) < period + lookback:
        return 0.0
    ma_now = simple_moving_average(values, period)
    ma_prev = simple_moving_average(values[:-lookback], period)
    if ma_prev == 0:
        return 0.0
    return (ma_now - ma_prev) / (ma_prev * lookback)


def true_range(high: float, low: float, prev_close: float) -> float:
    """Single-bar true range."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def average_true_range(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """ATR over the given period. Requires at least period+1 bars."""
    if len(highs) < period + 1:
        return 0.0
    trs = [
        true_range(highs[i], lows[i], closes[i - 1])
        for i in range(1, len(highs))
    ]
    return simple_moving_average(trs, period)


def volume_ratio(recent_volume: float, average_volume: float) -> float:
    """Current volume as a multiple of average. Returns 0 if no average."""
    if average_volume <= 0:
        return 0.0
    return recent_volume / average_volume


def relative_strength(
    stock_change: float,
    benchmark_change: float,
) -> float:
    """
    Simple relative strength: how much the stock outperformed the benchmark.
    Both inputs are percentage changes over the same period (as decimals).
    Returns a 0-100 score where 50 = matched benchmark.
    """
    diff = stock_change - benchmark_change
    score = 50.0 + (diff * 200.0)
    return max(0.0, min(100.0, score))


def concentration_breach(
    position_value: float,
    tier_value: float,
    max_position: float,
    breach_multiple: float = 1.5,
) -> float:
    """
    Returns the amount to trim if position exceeds breach_multiple × cap.
    Returns 0 if no breach.
    """
    cap = max_position * tier_value
    breach_level = cap * breach_multiple
    if position_value <= breach_level:
        return 0.0
    return position_value - cap


def gain_pct(current_price: float, entry_price: float) -> float:
    """Current gain/loss as a decimal fraction."""
    if entry_price <= 0:
        return 0.0
    return (current_price - entry_price) / entry_price


def is_non_performing(
    weeks_held: int,
    current_gain: float,
    review_weeks: int,
    gain_threshold: float,
) -> bool:
    """True if position has been held past review window without hitting gain threshold."""
    return weeks_held >= review_weeks and current_gain < gain_threshold


# ---------------------------------------------------------------------------
# Alpha Signal Normalization
# ---------------------------------------------------------------------------

def normalize_range(
    value: float,
    min_value: float,
    max_value: float,
    invert: bool = False,
) -> float:
    """Linear map to [-1.0, +1.0]. Clamps inputs outside [min, max]."""
    if max_value == min_value:
        return 0.0
    clamped = max(min_value, min(max_value, value))
    normalized = ((clamped - min_value) / (max_value - min_value)) * 2.0 - 1.0
    return -normalized if invert else normalized


def normalize_zscore(
    value: float,
    mean: float,
    std: float,
    invert: bool = False,
) -> float:
    """Z-score clamped to [-1.0, +1.0]. Returns 0 if std is zero."""
    if std <= 0:
        return 0.0
    z = (value - mean) / std
    clamped = max(-1.0, min(1.0, z))
    return -clamped if invert else clamped


def normalize_threshold(
    value: float,
    threshold: float,
    invert: bool = False,
) -> float:
    """Binary +1.0 / -1.0 based on whether value is above or below threshold."""
    result = 1.0 if value >= threshold else -1.0
    return -result if invert else result


def aggregate_alpha_adjustment(
    effects: list[tuple[float, float, float]],
    global_max: float,
) -> float:
    """
    Weighted sum of (signal_value, weight, max_adjustment) tuples,
    capped per-effect and globally.
    """
    total = 0.0
    for signal_value, weight, max_adj in effects:
        raw = signal_value * weight * max_adj
        capped = max(-max_adj, min(max_adj, raw))
        total += capped
    return max(-global_max, min(global_max, total))
