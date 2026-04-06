"""Tests for market intelligence module."""

import pytest
from monaimetrics.market_intelligence import (
    vix_to_cycle_score,
    compute_market_breadth,
    compute_cycle_score,
)


class TestVixToCycleScore:
    def test_extreme_complacency(self):
        assert vix_to_cycle_score(10.0) == 2

    def test_low_fear(self):
        assert vix_to_cycle_score(14.0) == 1

    def test_normal(self):
        assert vix_to_cycle_score(18.0) == 0

    def test_elevated_fear(self):
        assert vix_to_cycle_score(25.0) == -1

    def test_extreme_fear(self):
        assert vix_to_cycle_score(35.0) == -2

    def test_boundary_12(self):
        assert vix_to_cycle_score(12.0) == 1

    def test_boundary_16(self):
        assert vix_to_cycle_score(16.0) == 0

    def test_boundary_22(self):
        assert vix_to_cycle_score(22.0) == -1

    def test_boundary_30(self):
        assert vix_to_cycle_score(30.0) == -2


class TestMarketBreadth:
    def test_bullish(self):
        result = compute_market_breadth({1: 5, 2: 70, 3: 15, 4: 10})
        assert result["signal"] == "bullish"
        assert result["advancing_pct"] == 0.7

    def test_bearish(self):
        result = compute_market_breadth({1: 5, 2: 10, 3: 15, 4: 70})
        assert result["signal"] == "bearish"
        assert result["declining_pct"] == 0.7

    def test_neutral(self):
        result = compute_market_breadth({1: 25, 2: 25, 3: 25, 4: 25})
        assert result["signal"] == "neutral"

    def test_cautious(self):
        result = compute_market_breadth({1: 10, 2: 20, 3: 25, 4: 45})
        assert result["signal"] == "cautious"

    def test_empty(self):
        result = compute_market_breadth({})
        assert result["signal"] == "neutral"
        assert result["total_stocks"] == 0


class TestComputeCycleScore:
    def test_vix_only(self):
        assert compute_cycle_score(vix=10.0) == 2
        assert compute_cycle_score(vix=35.0) == -2

    def test_no_data(self):
        assert compute_cycle_score() == 0

    def test_breadth_override_bearish(self):
        # VIX says contrarian buy (-2), but breadth is bearish → force cautious
        breadth = {"signal": "bearish"}
        score = compute_cycle_score(vix=35.0, breadth=breadth)
        assert score == 1  # max(−2, 1) = 1

    def test_breadth_override_normal_vix(self):
        breadth = {"signal": "bearish"}
        score = compute_cycle_score(vix=18.0, breadth=breadth)
        assert score == 1  # max(0, 1) = 1

    def test_clamped_range(self):
        assert compute_cycle_score(vix=5.0) == 2
        assert compute_cycle_score(vix=100.0) == -2
