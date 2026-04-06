import pytest
from monaimetrics.calculators import (
    normalise_score,
    composite_score,
    kelly_position_size,
    stop_loss_price,
    atr_stop_loss_price,
    trailing_stop_update,
    ratchet_stop_level,
    profit_target_price,
    portfolio_drift,
    max_drift,
    rebalance_amounts,
    asymmetry_score,
    stage_from_ma,
    concentration_breach,
    gain_pct,
    is_non_performing,
)


class TestNormaliseScore:
    def test_within_range(self):
        assert normalise_score(50.0) == 50.0

    def test_below_floor(self):
        assert normalise_score(-10.0) == 0.0

    def test_above_ceiling(self):
        assert normalise_score(150.0) == 100.0

    def test_none_returns_zero(self):
        assert normalise_score(None) == 0.0

    def test_boundaries(self):
        assert normalise_score(0.0) == 0.0
        assert normalise_score(100.0) == 100.0


class TestCompositeScore:
    def test_equal_weights(self):
        scores = {"a": 80, "b": 60}
        weights = {"a": 0.5, "b": 0.5}
        assert composite_score(scores, weights) == 70.0

    def test_unequal_weights(self):
        scores = {"a": 100, "b": 0}
        weights = {"a": 0.75, "b": 0.25}
        assert composite_score(scores, weights) == 75.0

    def test_missing_key_ignored(self):
        scores = {"a": 80, "b": 60}
        weights = {"a": 0.5, "c": 0.5}
        assert composite_score(scores, weights) == 80.0

    def test_empty_returns_zero(self):
        assert composite_score({}, {}) == 0.0


class TestKellyPositionSize:
    def test_positive_edge(self):
        size = kelly_position_size(
            win_prob=0.6, avg_win=1.5, avg_loss=1.0,
            fraction_multiplier=0.25, available_capital=100000,
            max_position=0.10,
        )
        assert size > 0
        assert size <= 10000  # max 10% of 100k

    def test_no_edge_returns_zero(self):
        size = kelly_position_size(
            win_prob=0.3, avg_win=0.5, avg_loss=1.0,
            fraction_multiplier=0.25, available_capital=100000,
            max_position=0.10,
        )
        assert size == 0.0

    def test_capped_at_max_position(self):
        size = kelly_position_size(
            win_prob=0.9, avg_win=10.0, avg_loss=1.0,
            fraction_multiplier=1.0, available_capital=100000,
            max_position=0.05,
        )
        assert size == 5000.0

    def test_zero_loss_returns_zero(self):
        assert kelly_position_size(0.6, 1.5, 0, 0.25, 100000, 0.10) == 0.0


class TestStopLossPrice:
    def test_eight_percent(self):
        assert stop_loss_price(100.0, 0.08) == pytest.approx(92.0)

    def test_zero_stop(self):
        assert stop_loss_price(100.0, 0.0) == 100.0


class TestATRStopLoss:
    def test_within_bounds(self):
        price = atr_stop_loss_price(
            entry_price=100.0, atr=3.0, multiplier=2.5,
            max_stop_pct=0.15, min_stop_pct=0.05,
        )
        assert price == pytest.approx(92.5)
        assert price >= 85.0   # max 15% below
        assert price <= 95.0   # min 5% below

    def test_clamped_to_max(self):
        # Large ATR would push stop too far — clamp to max
        price = atr_stop_loss_price(
            entry_price=100.0, atr=10.0, multiplier=2.5,
            max_stop_pct=0.15, min_stop_pct=0.05,
        )
        assert price == pytest.approx(85.0)

    def test_clamped_to_min(self):
        # Tiny ATR would push stop too tight — clamp to min
        price = atr_stop_loss_price(
            entry_price=100.0, atr=0.5, multiplier=2.5,
            max_stop_pct=0.15, min_stop_pct=0.05,
        )
        assert price == pytest.approx(95.0)


class TestRatchetStopLevel:
    def test_no_gain_returns_none(self):
        assert ratchet_stop_level(1.00, 1.00) is None

    def test_partial_gain_under_step_returns_none(self):
        assert ratchet_stop_level(1.00, 1.04) is None

    def test_first_milestone_exact_boundary(self):
        # price == entry × 1.05^1 exactly (floating-point safe with epsilon)
        result = ratchet_stop_level(1.00, 1.05)
        assert result == pytest.approx(1.00, rel=1e-4)

    def test_between_milestones_stays_at_previous(self):
        result = ratchet_stop_level(1.00, 1.08)
        assert result == pytest.approx(1.00, rel=1e-4)

    def test_second_milestone_exact_boundary(self):
        # price == entry × 1.05^2 = 1.1025 exactly (the classic float undercount case)
        result = ratchet_stop_level(1.00, 1.1025)
        assert result == pytest.approx(1.05, rel=1e-4)

    def test_second_milestone_above_boundary(self):
        result = ratchet_stop_level(1.00, 1.103)
        assert result == pytest.approx(1.05, rel=1e-4)

    def test_third_milestone_exact_boundary(self):
        # price == entry × 1.05^3 = 1.157625 exactly
        result = ratchet_stop_level(1.00, 1.157625)
        assert result == pytest.approx(1.1025, rel=1e-3)

    def test_custom_step(self):
        result = ratchet_stop_level(100.0, 110.0, step=0.10)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_below_entry_returns_none(self):
        assert ratchet_stop_level(1.00, 0.95) is None

    def test_stop_only_moves_up(self):
        low = ratchet_stop_level(1.00, 1.05)
        high = ratchet_stop_level(1.00, 1.1025)
        assert high > low


class TestTrailingStopUpdate:
    MILESTONES = [(0.15, 0.0), (0.30, 0.15), (0.50, 0.30)]

    def test_no_gain_stays_at_current(self):
        stop = trailing_stop_update(
            current_stop=92.0, highest_price=100.0, entry_price=100.0,
            milestones=self.MILESTONES, atr=3.0, mature_atr_multiplier=1.75,
        )
        assert stop == 92.0

    def test_breakeven_at_fifteen_pct(self):
        stop = trailing_stop_update(
            current_stop=92.0, highest_price=115.0, entry_price=100.0,
            milestones=self.MILESTONES, atr=3.0, mature_atr_multiplier=1.75,
        )
        assert stop >= 100.0

    def test_locks_fifteen_at_thirty_pct(self):
        stop = trailing_stop_update(
            current_stop=100.0, highest_price=130.0, entry_price=100.0,
            milestones=self.MILESTONES, atr=3.0, mature_atr_multiplier=1.75,
        )
        assert stop >= 114.99

    def test_never_moves_down(self):
        stop = trailing_stop_update(
            current_stop=120.0, highest_price=115.0, entry_price=100.0,
            milestones=self.MILESTONES, atr=3.0, mature_atr_multiplier=1.75,
        )
        assert stop == 120.0

    def test_mature_atr_trailing(self):
        stop = trailing_stop_update(
            current_stop=100.0, highest_price=160.0, entry_price=100.0,
            milestones=self.MILESTONES, atr=5.0, mature_atr_multiplier=1.75,
        )
        expected_atr_trail = 160.0 - (5.0 * 1.75)
        assert stop >= expected_atr_trail


class TestProfitTargetPrice:
    def test_no_vol_adjustment(self):
        target = profit_target_price(100.0, 0.25, 0.0, 0.5)
        assert target == pytest.approx(125.0)

    def test_with_vol_adjustment(self):
        target = profit_target_price(100.0, 0.25, 5.0, 0.5)
        assert target > 125.0

    def test_atr_effect(self):
        low_vol = profit_target_price(100.0, 0.25, 2.0, 0.5)
        high_vol = profit_target_price(100.0, 0.25, 8.0, 0.5)
        assert high_vol > low_vol


class TestPortfolioDrift:
    def test_no_drift(self):
        current = {"mod": 0.65, "high": 0.35}
        target = {"mod": 0.65, "high": 0.35}
        drifts = portfolio_drift(current, target)
        assert all(abs(v) < 0.001 for v in drifts.values())

    def test_overweight(self):
        current = {"mod": 0.75, "high": 0.25}
        target = {"mod": 0.65, "high": 0.35}
        drifts = portfolio_drift(current, target)
        assert drifts["mod"] == pytest.approx(0.10)
        assert drifts["high"] == pytest.approx(-0.10)

    def test_max_drift(self):
        drifts = {"mod": 0.08, "high": -0.08}
        assert max_drift(drifts) == pytest.approx(0.08)


class TestRebalanceAmounts:
    def test_balanced_no_action(self):
        amounts = rebalance_amounts(
            current_values={"mod": 65000, "high": 35000},
            target_pcts={"mod": 0.65, "high": 0.35},
            total_value=100000,
        )
        assert abs(amounts["mod"]) < 0.01
        assert abs(amounts["high"]) < 0.01

    def test_overweight_needs_selling(self):
        amounts = rebalance_amounts(
            current_values={"mod": 75000, "high": 25000},
            target_pcts={"mod": 0.65, "high": 0.35},
            total_value=100000,
        )
        assert amounts["mod"] < 0
        assert amounts["high"] > 0


class TestAsymmetryScore:
    def test_three_to_one(self):
        score = asymmetry_score(30, 0.5, 10, 0.5)
        assert score == pytest.approx(3.0)

    def test_zero_downside_returns_zero(self):
        assert asymmetry_score(30, 0.5, 0, 0.5) == 0.0

    def test_higher_upside_higher_score(self):
        low = asymmetry_score(20, 0.5, 10, 0.5)
        high = asymmetry_score(40, 0.5, 10, 0.5)
        assert high > low


class TestStageFromMA:
    def test_advancing(self):
        assert stage_from_ma(110, 100, 0.01, 1.5) == 2

    def test_declining(self):
        assert stage_from_ma(90, 100, -0.01, 1.0) == 4

    def test_breakout_from_base(self):
        assert stage_from_ma(105, 100, 0.0, 2.5, breakout_volume_threshold=2.0) == 2

    def test_basing_below_flat_ma(self):
        assert stage_from_ma(95, 100, 0.0, 1.0) == 1

    def test_topping(self):
        assert stage_from_ma(105, 100, 0.0, 1.0) == 3


class TestConcentrationBreach:
    def test_no_breach(self):
        assert concentration_breach(8000, 100000, 0.10) == 0.0

    def test_breach(self):
        trim = concentration_breach(20000, 100000, 0.10, 1.5)
        assert trim == pytest.approx(10000.0)

    def test_at_boundary(self):
        assert concentration_breach(15000, 100000, 0.10, 1.5) == 0.0


class TestGainPct:
    def test_positive(self):
        assert gain_pct(115.0, 100.0) == pytest.approx(0.15)

    def test_negative(self):
        assert gain_pct(92.0, 100.0) == pytest.approx(-0.08)

    def test_zero_entry(self):
        assert gain_pct(50.0, 0.0) == 0.0


class TestIsNonPerforming:
    def test_within_window(self):
        assert is_non_performing(2, 0.03, 4, 0.05) is False

    def test_past_window_below_threshold(self):
        assert is_non_performing(5, 0.03, 4, 0.05) is True

    def test_past_window_above_threshold(self):
        assert is_non_performing(5, 0.10, 4, 0.05) is False
