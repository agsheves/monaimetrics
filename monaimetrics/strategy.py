"""
The only module with opinions about individual trades. Takes current state
of the world, produces a plan. Does NOT execute anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from monaimetrics.config import (
    SignalType, SignalUrgency, Stage, Tier, SystemConfig,
)
from monaimetrics.data_input import TechnicalData, AccountInfo, PositionInfo
from monaimetrics import calculators
from monaimetrics.fundamental_data import FundamentalData
from monaimetrics.alpha_signals import (
    SignalDefinition, SignalCache, compute_alpha_adjustment,
)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ManagedPosition:
    """Full state of a tracked position. Built by portfolio_manager."""
    symbol: str
    tier: Tier
    qty: float
    entry_price: float
    entry_date: datetime
    stop_price: float
    target_price: float
    trailing_stop: float
    highest_price: float
    current_price: float
    weeks_held: int = 0
    frameworks_at_entry: dict[str, float] = field(default_factory=dict)


@dataclass
class Signal:
    symbol: str
    action: SignalType
    urgency: SignalUrgency
    tier: Tier
    confidence: int
    position_size_usd: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class TradingPlan:
    signals: list[Signal]
    cycle_score: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# Framework Assessments
# ---------------------------------------------------------------------------

def assess_stage(tech: TechnicalData) -> int:
    """Framework 2: return stage 1-4 from technical data."""
    return tech.stage


def score_technical(tech: TechnicalData, config: SystemConfig) -> float:
    """
    Basic technical score from available data (0-100).
    Combines stage, volume, and momentum signals.
    """
    stage_scores = {1: 20, 2: 80, 3: 40, 4: 0}
    stage_score = stage_scores.get(tech.stage, 0)

    vol_score = min(100.0, tech.volume_ratio * 50.0)

    if tech.price > 0 and tech.ma_150 > 0:
        momentum = (tech.price - tech.ma_150) / tech.ma_150
        momentum_score = calculators.normalise_score(50 + momentum * 200)
    else:
        momentum_score = 50.0

    return calculators.composite_score(
        scores={"stage": stage_score, "volume": vol_score, "momentum": momentum_score},
        weights={"stage": 0.40, "volume": 0.25, "momentum": 0.35},
    )


def score_canslim(
    fund: FundamentalData | None,
    tech: TechnicalData,
    config: SystemConfig,
) -> float:
    """
    Framework 3: CANSLIM Growth Quality (O'Neil). Returns 0-100.
    Falls back to 50 (neutral) when no fundamental data is available.
    """
    if fund is None:
        return 50.0

    weights = config.canslim.weights

    # C — Current Quarterly Earnings Growth YoY
    cg = fund.quarterly_eps_growth_yoy
    if cg >= 0.50:
        c_score = 100.0
    elif cg >= 0.25:
        c_score = 70.0 + (cg - 0.25) / 0.25 * 30.0
    elif cg > 0:
        c_score = 40.0 + cg / 0.25 * 30.0
    else:
        c_score = max(0.0, 40.0 + cg * 100.0)

    # A — Annual Earnings Growth (3-year CAGR)
    ag = fund.annual_eps_growth_3yr
    if ag >= 0.25:
        a_score = 100.0
    elif ag >= 0.15:
        a_score = 70.0 + (ag - 0.15) / 0.10 * 30.0
    elif ag > 0:
        a_score = 40.0 + ag / 0.15 * 30.0
    else:
        a_score = max(0.0, 40.0 + ag * 100.0)

    # N — New High / Catalyst (proximity to 52-week high)
    n_score = 50.0
    if fund.fifty_two_week_high > 0 and tech.price > 0:
        pct = tech.price / fund.fifty_two_week_high
        if pct >= 0.95:
            n_score = 90.0 + min(10.0, (pct - 0.95) / 0.05 * 10.0)
        elif pct >= 0.80:
            n_score = 50.0 + (pct - 0.80) / 0.15 * 40.0
        else:
            n_score = max(0.0, pct / 0.80 * 50.0)

    # S — Supply & Demand (float tightness + volume)
    s_score = 50.0
    if fund.shares_float > 0 and fund.shares_outstanding > 0:
        float_pct = fund.shares_float / fund.shares_outstanding
        if float_pct < 0.50:
            s_score = 80.0
        elif float_pct < 0.70:
            s_score = 65.0
    if tech.volume_ratio > 1.5:
        s_score = min(100.0, s_score + 15.0)

    # L — Leader Status (position within 52-week range)
    l_score = 50.0
    if fund.fifty_two_week_high > 0 and fund.fifty_two_week_low > 0 and tech.price > 0:
        span = fund.fifty_two_week_high - fund.fifty_two_week_low
        if span > 0:
            l_score = ((tech.price - fund.fifty_two_week_low) / span) * 100.0

    # I — Institutional Sponsorship (30-70% is ideal)
    i_score = 50.0
    if fund.percent_institutions > 0:
        inst = fund.percent_institutions
        if 0.30 <= inst <= 0.70:
            i_score = 80.0 + (0.20 - abs(inst - 0.50)) / 0.20 * 20.0
        elif inst > 0.70:
            i_score = 60.0
        else:
            i_score = inst / 0.30 * 60.0

    return calculators.composite_score(
        scores={
            "current_earnings": c_score,
            "annual_earnings": a_score,
            "new_catalyst": n_score,
            "supply_demand": s_score,
            "leader_status": l_score,
            "institutional": i_score,
        },
        weights={
            "current_earnings": weights.current_earnings,
            "annual_earnings": weights.annual_earnings,
            "new_catalyst": weights.new_catalyst,
            "supply_demand": weights.supply_demand,
            "leader_status": weights.leader_status,
            "institutional": weights.institutional,
        },
    )


def score_greenblatt(
    fund: FundamentalData | None,
    config: SystemConfig,
) -> float:
    """
    Framework 4: Quality-Value Magic Formula (Greenblatt). Returns 0-100.
    Falls back to 50 (neutral) when no fundamental data is available.
    """
    if fund is None:
        return 50.0

    # Neutral for excluded sectors
    if fund.sector.lower() in config.greenblatt.sector_exclusions:
        return 50.0

    # Earnings yield score (higher = better value)
    ey = fund.earnings_yield
    if ey >= 0.15:
        ey_score = 100.0
    elif ey >= 0.10:
        ey_score = 70.0 + (ey - 0.10) / 0.05 * 30.0
    elif ey >= 0.05:
        ey_score = 40.0 + (ey - 0.05) / 0.05 * 30.0
    elif ey > 0:
        ey_score = ey / 0.05 * 40.0
    else:
        ey_score = 0.0

    # Return on capital score (higher = better quality)
    roc = fund.return_on_capital
    roc_min = config.greenblatt.roc_minimum_pct
    if roc >= roc_min * 3:
        roc_score = 100.0
    elif roc >= roc_min * 2:
        roc_score = 70.0 + (roc - roc_min * 2) / roc_min * 30.0
    elif roc >= roc_min:
        roc_score = 40.0 + (roc - roc_min) / roc_min * 30.0
    elif roc > 0:
        roc_score = roc / roc_min * 40.0
    else:
        roc_score = 0.0

    return calculators.composite_score(
        scores={"earnings_yield": ey_score, "return_on_capital": roc_score},
        weights={"earnings_yield": 0.50, "return_on_capital": 0.50},
    )


def assess_event_cascade_stub() -> int:
    """Framework 5: stub — returns phase 4 (consensus, safe to trade)."""
    return 4


def score_asymmetry(
    tech: TechnicalData,
    config: SystemConfig,
) -> float:
    """
    Framework 6: basic asymmetry score from technical data.
    Full version needs fundamental floor value — stubbed with ATR-based estimate.
    """
    if tech.price <= 0 or tech.atr_14 <= 0:
        return 0.0

    expected_upside = tech.atr_14 * 3.0
    expected_downside = tech.atr_14 * config.high_risk_tier.atr_stop_multiplier
    return calculators.asymmetry_score(
        expected_upside=expected_upside,
        prob_upside=0.5,
        expected_downside=expected_downside,
        prob_downside=0.5,
    )


def compute_composite_confidence(
    tech_score: float,
    canslim_score: float,
    greenblatt_score: float,
    tier: Tier,
    config: SystemConfig,
) -> int:
    """Combine framework scores into a single 0-100 confidence value."""
    weights = config.get_framework_weights(tier)
    scores = {
        "canslim": canslim_score,
        "greenblatt": greenblatt_score,
        "technical": tech_score,
    }
    fw_weights = {
        "canslim": weights.canslim,
        "greenblatt": weights.greenblatt,
        "technical": weights.event_cascade + weights.asymmetry,
    }
    return int(calculators.composite_score(scores, fw_weights))


# ---------------------------------------------------------------------------
# Position Review (sell-side)
# ---------------------------------------------------------------------------

def _check_stop_loss(pos: ManagedPosition) -> Signal | None:
    if pos.current_price <= pos.stop_price:
        return Signal(
            symbol=pos.symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.EMERGENCY,
            tier=pos.tier,
            confidence=100,
            reasons=[
                f"Stop-loss triggered: price ${pos.current_price:.2f} hit our "
                f"${pos.stop_price:.2f} exit level — selling to limit losses",
            ],
        )
    return None


def _check_trailing_stop(pos: ManagedPosition) -> Signal | None:
    if pos.tier != Tier.HIGH:
        return None
    if pos.trailing_stop > 0 and pos.current_price <= pos.trailing_stop:
        return Signal(
            symbol=pos.symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.EMERGENCY,
            tier=pos.tier,
            confidence=100,
            reasons=[
                f"Trailing stop triggered: price ${pos.current_price:.2f} "
                f"pulled back below our raised stop at ${pos.trailing_stop:.2f} "
                f"— locking in gains",
            ],
        )
    return None


def _check_profit_target(pos: ManagedPosition) -> Signal | None:
    if pos.tier != Tier.MODERATE:
        return None
    if pos.target_price > 0 and pos.current_price >= pos.target_price:
        return Signal(
            symbol=pos.symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.IMMEDIATE,
            tier=pos.tier,
            confidence=100,
            reasons=[
                f"Profit target reached: price ${pos.current_price:.2f} hit "
                f"our ${pos.target_price:.2f} goal — taking profits",
            ],
        )
    return None


def _check_stage4(pos: ManagedPosition, tech: TechnicalData) -> Signal | None:
    if tech.stage == Stage.DECLINING.value:
        return Signal(
            symbol=pos.symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.EMERGENCY,
            tier=pos.tier,
            confidence=100,
            reasons=[
                "Trend broken: stock entered Stage 4 (declining) — price is "
                "falling below a dropping moving average. This is our hardest "
                "rule: sell immediately, no exceptions",
            ],
        )
    return None


def _check_non_performance(pos: ManagedPosition, config: SystemConfig) -> Signal | None:
    if pos.tier == Tier.MODERATE:
        review_weeks = config.moderate_tier.non_perf_review_weeks
        threshold = config.moderate_tier.non_perf_gain_threshold
    else:
        review_weeks = config.high_risk_tier.non_perf_review_weeks
        threshold = config.high_risk_tier.non_perf_gain_threshold

    current_gain = calculators.gain_pct(pos.current_price, pos.entry_price)

    if calculators.is_non_performing(pos.weeks_held, current_gain, review_weeks, threshold):
        return Signal(
            symbol=pos.symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.STANDARD,
            tier=pos.tier,
            confidence=80,
            reasons=[
                f"Not delivering: held {pos.weeks_held} weeks with only "
                f"{current_gain:.1%} gain (need {threshold:.1%} by week "
                f"{review_weeks}) — cut and redeploy capital elsewhere",
            ],
        )
    return None


def _check_max_hold(pos: ManagedPosition, config: SystemConfig) -> Signal | None:
    if pos.tier == Tier.MODERATE:
        max_weeks = config.moderate_tier.max_hold_weeks
    else:
        max_weeks = config.high_risk_tier.max_hold_weeks

    if pos.weeks_held >= max_weeks:
        return Signal(
            symbol=pos.symbol,
            action=SignalType.SELL,
            urgency=SignalUrgency.STANDARD,
            tier=pos.tier,
            confidence=70,
            reasons=[
                f"Time limit reached: held {pos.weeks_held} weeks, past our "
                f"{max_weeks}-week maximum — sell to free capital for "
                f"fresh opportunities",
            ],
        )
    return None


def _check_concentration(
    pos: ManagedPosition,
    tier_value: float,
    config: SystemConfig,
) -> Signal | None:
    max_pos = (config.moderate_tier.max_position if pos.tier == Tier.MODERATE
               else config.high_risk_tier.max_position)
    position_value = pos.qty * pos.current_price
    trim = calculators.concentration_breach(
        position_value, tier_value, max_pos,
        config.circuit_breakers.concentration_breach_multiple,
    )
    if trim > 0:
        return Signal(
            symbol=pos.symbol,
            action=SignalType.REDUCE,
            urgency=SignalUrgency.STANDARD,
            tier=pos.tier,
            confidence=100,
            reasons=[
                f"Position too large: grown beyond safe concentration limits "
                f"— trim ${trim:,.0f} to restore proper sizing",
            ],
        )
    return None


def review_position(
    pos: ManagedPosition,
    tech: TechnicalData,
    tier_value: float,
    config: SystemConfig,
    *,
    symbol_types: set[str] | None = None,
    alpha_definitions: list[SignalDefinition] | None = None,
    alpha_cache: SignalCache | None = None,
) -> Signal:
    """
    Run all sell-side checks on a position. Returns the most urgent signal.
    Priority: emergency sells > immediate > standard > hold.
    """
    checks = [
        _check_stage4(pos, tech),
        _check_stop_loss(pos),
        _check_trailing_stop(pos),
        _check_profit_target(pos),
        _check_non_performance(pos, config),
        _check_max_hold(pos, config),
        _check_concentration(pos, tier_value, config),
    ]

    urgency_rank = {
        SignalUrgency.EMERGENCY: 0,
        SignalUrgency.IMMEDIATE: 1,
        SignalUrgency.ELEVATED: 2,
        SignalUrgency.STANDARD: 3,
    }

    sell_signals = [s for s in checks if s is not None]

    if not sell_signals:
        # Check alpha signals for strong negative adjustment
        if alpha_definitions and alpha_cache and symbol_types:
            alpha_adj = compute_alpha_adjustment(
                alpha_definitions, alpha_cache,
                symbol_types=symbol_types, side="sell",
                global_max=config.alpha_signals.global_max_adjustment,
            )
            if alpha_adj <= -10.0:
                return Signal(
                    symbol=pos.symbol,
                    action=SignalType.SELL,
                    urgency=SignalUrgency.STANDARD,
                    tier=pos.tier,
                    confidence=70,
                    reasons=[
                        f"Alpha signals strongly negative: {alpha_adj:+.1f} pts "
                        f"— external data suggests adverse conditions for this position",
                    ],
                )

        return Signal(
            symbol=pos.symbol,
            action=SignalType.HOLD,
            urgency=SignalUrgency.MONITOR,
            tier=pos.tier,
            confidence=50,
            reasons=["Position healthy — no sell triggers active, continue holding"],
        )

    sell_signals.sort(key=lambda s: urgency_rank.get(s.urgency, 99))
    winner = sell_signals[0]

    if len(sell_signals) > 1:
        winner.reasons.append(
            f"+ {len(sell_signals) - 1} other sell trigger(s)"
        )
    return winner


# ---------------------------------------------------------------------------
# Trailing Stop Maintenance
# ---------------------------------------------------------------------------

def update_trailing_stop(
    pos: ManagedPosition,
    tech: TechnicalData,
    config: SystemConfig,
) -> float:
    """Calculate updated trailing stop for a high-risk position."""
    if pos.tier != Tier.HIGH:
        return pos.trailing_stop

    hr = config.high_risk_tier
    milestones = [(m.gain_threshold, m.lock_gain) for m in hr.milestones]

    highest = max(pos.highest_price, pos.current_price)

    atr_mult = hr.mature_trail_atr_multiplier
    if tech.stage == Stage.TOPPING.value:
        atr_mult = hr.stage3_tighten_atr_multiplier

    return calculators.trailing_stop_update(
        current_stop=pos.trailing_stop,
        highest_price=highest,
        entry_price=pos.entry_price,
        milestones=milestones,
        atr=tech.atr_14,
        mature_atr_multiplier=atr_mult,
    )


# ---------------------------------------------------------------------------
# Opportunity Scan (buy-side)
# ---------------------------------------------------------------------------

_STAGE_EXPLANATIONS: dict[int, str] = {
    Stage.BASING.value: (
        "Not ready to buy: stock is in Stage 1 (basing) — price is "
        "consolidating with no clear trend. Waiting for a confirmed "
        "Stage 2 uptrend before entering"
    ),
    Stage.TOPPING.value: (
        "Not buying: stock is in Stage 3 (topping) — the uptrend is "
        "losing momentum and smart money may be selling. Too late for "
        "a safe entry"
    ),
    Stage.DECLINING.value: (
        "Not buying: stock is in Stage 4 (declining) — price is in a "
        "downtrend below a falling moving average. Wait for a new "
        "base to form"
    ),
}


def evaluate_opportunity(
    symbol: str,
    tech: TechnicalData,
    tier: Tier,
    available_capital: float,
    config: SystemConfig,
    *,
    fundamentals: FundamentalData | None = None,
    symbol_types: set[str] | None = None,
    alpha_definitions: list[SignalDefinition] | None = None,
    alpha_cache: SignalCache | None = None,
) -> Signal:
    """
    Evaluate a stock for a potential buy. Runs through framework gates and scoring.
    """
    reasons = []

    # Gate 1: Stage must be 2 (advancing)
    stage = assess_stage(tech)
    if stage != Stage.ADVANCING.value:
        reason = _STAGE_EXPLANATIONS.get(
            stage,
            f"Not buying: unrecognised stage ({stage})",
        )
        return Signal(
            symbol=symbol,
            action=SignalType.WATCH if stage == Stage.BASING.value else SignalType.HOLD,
            urgency=SignalUrgency.MONITOR,
            tier=tier,
            confidence=0,
            reasons=[reason],
        )

    reasons.append("Stage 2 (advancing) confirmed — price trending above rising 150-day MA")

    # Score frameworks
    tech_score = score_technical(tech, config)
    canslim = score_canslim(fundamentals, tech, config)
    greenblatt = score_greenblatt(fundamentals, config)
    asym = score_asymmetry(tech, config)
    event_phase = assess_event_cascade_stub()

    confidence = compute_composite_confidence(
        tech_score, canslim, greenblatt, tier, config,
    )

    # Alpha signals adjustment
    if alpha_definitions and alpha_cache and symbol_types:
        alpha_adj = compute_alpha_adjustment(
            alpha_definitions, alpha_cache,
            symbol_types=symbol_types, side="buy",
            global_max=config.alpha_signals.global_max_adjustment,
        )
        if alpha_adj != 0.0:
            confidence = max(0, min(100, confidence + int(round(alpha_adj))))
            reasons.append(f"Alpha signals: {alpha_adj:+.1f} pts")

    # Gate 2: Minimum conviction
    if confidence < config.kelly.min_conviction:
        return Signal(
            symbol=symbol,
            action=SignalType.WATCH,
            urgency=SignalUrgency.MONITOR,
            tier=tier,
            confidence=confidence,
            reasons=[
                f"Not enough conviction to buy: combined score is "
                f"{confidence}/100, need at least {config.kelly.min_conviction} "
                f"(technical:{tech_score:.0f}, growth:{canslim:.0f}, value:{greenblatt:.0f})",
            ],
        )

    reasons.append(
        f"Conviction {confidence}/100 "
        f"(technical:{tech_score:.0f}, growth:{canslim:.0f}, value:{greenblatt:.0f})"
    )

    # Gate 3: Event cascade must be past phase 2
    if event_phase <= 2:
        reasons.append(
            f"News/event cycle still early (phase {event_phase}/4) — "
            f"waiting for market to digest before trading"
        )
        return Signal(
            symbol=symbol,
            action=SignalType.WATCH,
            urgency=SignalUrgency.MONITOR,
            tier=tier,
            confidence=confidence,
            reasons=reasons,
        )

    # High-risk tier: check asymmetry
    if tier == Tier.HIGH and asym < config.asymmetry.min_ratio:
        return Signal(
            symbol=symbol,
            action=SignalType.WATCH,
            urgency=SignalUrgency.MONITOR,
            tier=tier,
            confidence=confidence,
            reasons=[
                f"Risk/reward not attractive enough: potential upside vs "
                f"downside is {asym:.1f}:1, need at least "
                f"{config.asymmetry.min_ratio}:1 for a high-risk position",
            ],
        )

    if tier == Tier.HIGH:
        reasons.append(f"Risk/reward ratio {asym:.1f}:1")

    # Size via Kelly
    kelly_frac = (config.moderate_tier.kelly_fraction if tier == Tier.MODERATE
                  else config.high_risk_tier.kelly_fraction)
    max_pos = (config.moderate_tier.max_position if tier == Tier.MODERATE
               else config.high_risk_tier.max_position)

    position_size = calculators.kelly_position_size(
        win_prob=confidence / 100.0,
        avg_win=0.25 if tier == Tier.MODERATE else 0.50,
        avg_loss=config.moderate_tier.stop_loss if tier == Tier.MODERATE else 0.12,
        fraction_multiplier=kelly_frac,
        available_capital=available_capital,
        max_position=max_pos,
    )

    if position_size <= 0:
        return Signal(
            symbol=symbol,
            action=SignalType.WATCH,
            urgency=SignalUrgency.MONITOR,
            tier=tier,
            confidence=confidence,
            reasons=[
                "Position sizes to zero: the statistical edge isn't strong "
                "enough to justify risking capital at this conviction level",
            ],
        )

    # Calculate stop and target
    if tier == Tier.MODERATE:
        stop = calculators.stop_loss_price(tech.price, config.moderate_tier.stop_loss)
        target = calculators.profit_target_price(
            tech.price, config.moderate_tier.profit_target,
            tech.atr_14, config.moderate_tier.vol_adjustment_factor,
        )
    else:
        stop = calculators.atr_stop_loss_price(
            tech.price, tech.atr_14,
            config.high_risk_tier.atr_stop_multiplier,
            config.high_risk_tier.max_stop,
            config.high_risk_tier.min_stop,
        )
        target = 0.0

    # Determine urgency
    urgency = SignalUrgency.STANDARD
    if asym >= config.asymmetry.speed_premium_ratio:
        urgency = SignalUrgency.ELEVATED
        reasons.append(
            f"Elevated urgency: risk/reward of {asym:.1f}:1 is exceptional "
            f"— act quickly before the window closes"
        )

    reasons.append(f"Position: ${position_size:,.0f}, stop-loss at ${stop:,.2f}")
    if target > 0:
        reasons.append(f"Profit target: ${target:,.2f}")

    return Signal(
        symbol=symbol,
        action=SignalType.BUY,
        urgency=urgency,
        tier=tier,
        confidence=confidence,
        position_size_usd=position_size,
        stop_price=stop,
        target_price=target,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Plan Generation
# ---------------------------------------------------------------------------

SIGNAL_PRIORITY = {
    (SignalType.SELL, SignalUrgency.EMERGENCY): 0,
    (SignalType.SELL, SignalUrgency.IMMEDIATE): 1,
    (SignalType.REDUCE, SignalUrgency.STANDARD): 2,
    (SignalType.SELL, SignalUrgency.STANDARD): 3,
    (SignalType.BUY, SignalUrgency.ELEVATED): 4,
    (SignalType.BUY, SignalUrgency.STANDARD): 5,
    (SignalType.WATCH, SignalUrgency.MONITOR): 6,
    (SignalType.HOLD, SignalUrgency.MONITOR): 7,
}


def generate_plan(
    managed_positions: list[ManagedPosition],
    watchlist_technicals: dict[str, TechnicalData],
    account: AccountInfo,
    tier_values: dict[Tier, float],
    config: SystemConfig,
    cycle_score: int = 0,
    *,
    fundamentals_map: dict[str, FundamentalData] | None = None,
    alpha_definitions: list[SignalDefinition] | None = None,
    alpha_cache: SignalCache | None = None,
    trade_type_resolver=None,
) -> TradingPlan:
    """
    Top-level plan generation. Reviews positions, scans opportunities,
    prioritises actions.
    """
    signals: list[Signal] = []
    held_symbols = {p.symbol for p in managed_positions}
    fund_map = fundamentals_map or {}

    def _resolve_types(symbol: str) -> set[str] | None:
        if trade_type_resolver is not None:
            return trade_type_resolver.resolve(symbol)
        return None

    # 1. Review all existing positions
    for pos in managed_positions:
        tech = watchlist_technicals.get(pos.symbol)
        if tech is None:
            signals.append(Signal(
                symbol=pos.symbol,
                action=SignalType.HOLD,
                urgency=SignalUrgency.MONITOR,
                tier=pos.tier,
                confidence=0,
                reasons=["No market data available for this symbol — holding until data returns"],
            ))
            continue

        tv = tier_values.get(pos.tier, account.portfolio_value * 0.5)
        signal = review_position(
            pos, tech, tv, config,
            symbol_types=_resolve_types(pos.symbol),
            alpha_definitions=alpha_definitions,
            alpha_cache=alpha_cache,
        )
        signals.append(signal)

    # 2. Scan opportunities (symbols not already held)
    allocation = config.get_allocation(cycle_score)
    for symbol, tech in watchlist_technicals.items():
        if symbol in held_symbols:
            continue

        for tier in (Tier.MODERATE, Tier.HIGH):
            tier_alloc = allocation.moderate if tier == Tier.MODERATE else allocation.high
            available = tier_alloc * account.portfolio_value
            current_tier_value = tier_values.get(tier, 0.0)
            remaining = max(0.0, available - current_tier_value)

            if remaining <= 0:
                continue

            signal = evaluate_opportunity(
                symbol, tech, tier, remaining, config,
                fundamentals=fund_map.get(symbol),
                symbol_types=_resolve_types(symbol),
                alpha_definitions=alpha_definitions,
                alpha_cache=alpha_cache,
            )

            if signal.action == SignalType.BUY:
                signals.append(signal)
                break
            elif signal.action == SignalType.WATCH:
                signals.append(signal)
                break

    # 3. Sort by priority
    signals.sort(
        key=lambda s: SIGNAL_PRIORITY.get((s.action, s.urgency), 99)
    )

    return TradingPlan(
        signals=signals,
        cycle_score=cycle_score,
        timestamp=datetime.now(timezone.utc),
    )
