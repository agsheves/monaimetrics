"""
Scenario-based tests for strategy. All use constructed data, no API calls.
"""

import pytest
from datetime import datetime, timezone, timedelta

from monaimetrics.config import (
    SignalType, SignalUrgency, Stage, Tier, load_config,
)
from monaimetrics.data_input import TechnicalData, AccountInfo
from monaimetrics.strategy import (
    ManagedPosition,
    Signal,
    assess_stage,
    score_technical,
    score_asymmetry,
    compute_composite_confidence,
    review_position,
    update_trailing_stop,
    evaluate_opportunity,
    generate_plan,
)


NOW = datetime.now(timezone.utc)
CFG = load_config()


def make_tech(
    symbol="AAPL",
    price=150.0,
    ma_150=140.0,
    ma_slope=0.005,
    atr_14=3.0,
    volume_ratio=1.5,
    stage=2,
) -> TechnicalData:
    return TechnicalData(
        symbol=symbol, price=price, ma_150=ma_150, ma_slope=ma_slope,
        atr_14=atr_14, volume_ratio=volume_ratio, stage=stage,
        timestamp=NOW,
    )


def make_position(
    symbol="AAPL",
    tier=Tier.MODERATE,
    entry_price=100.0,
    current_price=110.0,
    stop_price=92.0,
    target_price=125.0,
    trailing_stop=0.0,
    highest_price=110.0,
    weeks_held=2,
    qty=10.0,
) -> ManagedPosition:
    return ManagedPosition(
        symbol=symbol, tier=tier, qty=qty, entry_price=entry_price,
        entry_date=NOW - timedelta(weeks=weeks_held),
        stop_price=stop_price, target_price=target_price,
        trailing_stop=trailing_stop, highest_price=highest_price,
        current_price=current_price, weeks_held=weeks_held,
    )


def make_account(cash=50000.0, portfolio_value=100000.0) -> AccountInfo:
    return AccountInfo(
        cash=cash, portfolio_value=portfolio_value,
        buying_power=cash * 2, status="active",
    )


# ---------------------------------------------------------------------------
# Framework Tests
# ---------------------------------------------------------------------------

class TestAssessStage:
    def test_stage_passthrough(self):
        tech = make_tech(stage=2)
        assert assess_stage(tech) == 2

    def test_all_stages(self):
        for s in (1, 2, 3, 4):
            assert assess_stage(make_tech(stage=s)) == s


class TestScoreTechnical:
    def test_stage2_high_score(self):
        tech = make_tech(stage=2, volume_ratio=2.0, price=160, ma_150=140)
        score = score_technical(tech, CFG)
        assert score > 60

    def test_stage4_low_score(self):
        tech = make_tech(stage=4, volume_ratio=0.5, price=90, ma_150=100)
        score = score_technical(tech, CFG)
        assert score < 30

    def test_score_bounded(self):
        for stage in (1, 2, 3, 4):
            score = score_technical(make_tech(stage=stage), CFG)
            assert 0 <= score <= 100


class TestScoreAsymmetry:
    def test_returns_positive(self):
        tech = make_tech(atr_14=3.0)
        score = score_asymmetry(tech, CFG)
        assert score > 0

    def test_zero_price(self):
        tech = make_tech(price=0.0)
        assert score_asymmetry(tech, CFG) == 0.0


class TestCompositeConfidence:
    def test_range(self):
        conf = compute_composite_confidence(70, 60, 50, Tier.MODERATE, CFG)
        assert 0 <= conf <= 100

    def test_higher_scores_higher_confidence(self):
        low = compute_composite_confidence(30, 30, 30, Tier.MODERATE, CFG)
        high = compute_composite_confidence(90, 90, 90, Tier.MODERATE, CFG)
        assert high > low


# ---------------------------------------------------------------------------
# Position Review (Sell-Side) Tests
# ---------------------------------------------------------------------------

class TestStopLoss:
    def test_stop_triggered(self):
        pos = make_position(current_price=91.0, stop_price=92.0)
        tech = make_tech(price=91.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.SELL
        assert sig.urgency == SignalUrgency.EMERGENCY

    def test_stop_not_triggered(self):
        pos = make_position(current_price=95.0, stop_price=92.0)
        tech = make_tech(price=95.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.HOLD


class TestTrailingStop:
    def test_trailing_triggered(self):
        pos = make_position(
            tier=Tier.HIGH, current_price=108.0,
            trailing_stop=110.0, stop_price=85.0,
        )
        tech = make_tech(price=108.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.SELL
        assert sig.urgency == SignalUrgency.EMERGENCY

    def test_trailing_not_triggered(self):
        pos = make_position(
            tier=Tier.HIGH, current_price=115.0,
            trailing_stop=110.0, stop_price=85.0,
        )
        tech = make_tech(price=115.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.HOLD


class TestProfitTarget:
    def test_target_hit(self):
        pos = make_position(current_price=126.0, target_price=125.0)
        tech = make_tech(price=126.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.SELL
        assert sig.urgency == SignalUrgency.IMMEDIATE

    def test_target_not_hit(self):
        pos = make_position(current_price=120.0, target_price=125.0)
        tech = make_tech(price=120.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.HOLD


class TestStage4Override:
    def test_stage4_forces_sell(self):
        pos = make_position(current_price=110.0)
        tech = make_tech(price=110.0, stage=4)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.SELL
        assert sig.urgency == SignalUrgency.EMERGENCY
        assert "Stage 4" in sig.reasons[0]

    def test_stage4_overrides_profit(self):
        """Even if in profit, Stage 4 forces sell."""
        pos = make_position(current_price=130.0, target_price=125.0)
        tech = make_tech(price=130.0, stage=4)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.SELL
        assert sig.urgency == SignalUrgency.EMERGENCY


class TestNonPerformance:
    def test_non_performing_moderate(self):
        pos = make_position(
            current_price=102.0, entry_price=100.0, weeks_held=5,
        )
        tech = make_tech(price=102.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.SELL
        assert "Not delivering" in sig.reasons[0]

    def test_performing_ok(self):
        pos = make_position(
            current_price=108.0, entry_price=100.0, weeks_held=5,
        )
        tech = make_tech(price=108.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.HOLD


class TestConcentration:
    def test_breach_triggers_reduce(self):
        # High-risk tier with no profit target, so concentration is the trigger
        pos = make_position(
            tier=Tier.HIGH, entry_price=100.0, current_price=110.0,
            stop_price=85.0, target_price=0.0, trailing_stop=95.0,
            highest_price=110.0, qty=100,
        )
        tech = make_tech(price=110.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.REDUCE

    def test_within_cap(self):
        pos = make_position(current_price=100.0, qty=1)
        tech = make_tech(price=100.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.HOLD


class TestConflictResolution:
    def test_most_urgent_wins(self):
        """Stage 4 (emergency) beats non-performance (standard)."""
        pos = make_position(
            current_price=102.0, entry_price=100.0, weeks_held=5,
        )
        tech = make_tech(price=102.0, stage=4)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.urgency == SignalUrgency.EMERGENCY
        assert "Stage 4" in sig.reasons[0]


# ---------------------------------------------------------------------------
# Trailing Stop Update Tests
# ---------------------------------------------------------------------------

class TestUpdateTrailingStop:
    def test_moves_up(self):
        pos = make_position(
            tier=Tier.HIGH, entry_price=100.0, current_price=120.0,
            highest_price=120.0, trailing_stop=95.0,
        )
        tech = make_tech(price=120.0, atr_14=3.0, stage=2)
        new_stop = update_trailing_stop(pos, tech, CFG)
        assert new_stop >= 100.0

    def test_never_moves_down(self):
        pos = make_position(
            tier=Tier.HIGH, entry_price=100.0, current_price=105.0,
            highest_price=120.0, trailing_stop=115.0,
        )
        tech = make_tech(price=105.0, atr_14=3.0, stage=2)
        new_stop = update_trailing_stop(pos, tech, CFG)
        assert new_stop >= 115.0

    def test_stage3_tightens(self):
        pos = make_position(
            tier=Tier.HIGH, entry_price=100.0, current_price=160.0,
            highest_price=160.0, trailing_stop=130.0,
        )
        tech_s2 = make_tech(price=160.0, atr_14=3.0, stage=2)
        tech_s3 = make_tech(price=160.0, atr_14=3.0, stage=3)
        stop_s2 = update_trailing_stop(pos, tech_s2, CFG)
        stop_s3 = update_trailing_stop(pos, tech_s3, CFG)
        assert stop_s3 >= stop_s2

    def test_moderate_tier_unchanged(self):
        pos = make_position(tier=Tier.MODERATE, trailing_stop=95.0)
        tech = make_tech(price=110.0, stage=2)
        assert update_trailing_stop(pos, tech, CFG) == 95.0


# ---------------------------------------------------------------------------
# Opportunity Scan (Buy-Side) Tests
# ---------------------------------------------------------------------------

class TestEvaluateOpportunity:
    def test_stage2_can_buy(self):
        tech = make_tech(stage=2, volume_ratio=2.0, price=150, ma_150=140)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        assert sig.action in (SignalType.BUY, SignalType.WATCH)

    def test_stage1_blocked(self):
        tech = make_tech(stage=1)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        assert sig.action == SignalType.WATCH

    def test_stage4_blocked(self):
        tech = make_tech(stage=4)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        assert sig.action != SignalType.BUY

    def test_stage3_blocked(self):
        tech = make_tech(stage=3)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        assert sig.action != SignalType.BUY

    def test_zero_capital_no_buy(self):
        tech = make_tech(stage=2, volume_ratio=2.0)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 0, CFG)
        assert sig.action != SignalType.BUY

    def test_buy_has_stop_and_target(self):
        tech = make_tech(stage=2, volume_ratio=2.0, price=150, ma_150=140)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        if sig.action == SignalType.BUY:
            assert sig.stop_price > 0
            assert sig.target_price > 0
            assert sig.position_size_usd > 0


# ---------------------------------------------------------------------------
# Plan Generation Tests
# ---------------------------------------------------------------------------

class TestGeneratePlan:
    def test_empty_portfolio_and_watchlist(self):
        plan = generate_plan([], {}, make_account(), {}, CFG)
        assert plan.signals == []
        assert plan.cycle_score == 0

    def test_sell_before_buy(self):
        pos = make_position(current_price=91.0, stop_price=92.0)
        techs = {
            "AAPL": make_tech(symbol="AAPL", price=91.0, stage=2),
            "MSFT": make_tech(symbol="MSFT", stage=2, volume_ratio=2.0, price=300, ma_150=280),
        }
        plan = generate_plan(
            [pos], techs, make_account(),
            {Tier.MODERATE: 50000, Tier.HIGH: 30000}, CFG,
        )
        sells = [s for s in plan.signals if s.action == SignalType.SELL]
        buys = [s for s in plan.signals if s.action == SignalType.BUY]
        if sells and buys:
            sell_idx = plan.signals.index(sells[0])
            buy_idx = plan.signals.index(buys[0])
            assert sell_idx < buy_idx

    def test_held_symbols_not_rescanned(self):
        pos = make_position(symbol="AAPL", current_price=110.0)
        techs = {"AAPL": make_tech(symbol="AAPL", price=110.0, stage=2)}
        plan = generate_plan(
            [pos], techs, make_account(),
            {Tier.MODERATE: 50000}, CFG,
        )
        buy_signals = [s for s in plan.signals if s.action == SignalType.BUY and s.symbol == "AAPL"]
        assert len(buy_signals) == 0

    def test_plan_has_timestamp(self):
        plan = generate_plan([], {}, make_account(), {}, CFG)
        assert plan.timestamp is not None
