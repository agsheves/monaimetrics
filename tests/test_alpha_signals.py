"""
Tests for alpha signals module. All use constructed data — no API calls.
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
import yaml

from monaimetrics import calculators
from monaimetrics.alpha_signals import (
    SignalEffect,
    SignalDefinition,
    SignalSource,
    NormalizationConfig,
    CachedSignalValue,
    SignalCache,
    TradeTypeResolver,
    load_signal_definitions,
    normalize_signal,
    effect_applies,
    compute_alpha_adjustment,
)
from monaimetrics.config import load_config, Tier, SignalType, SignalUrgency
from monaimetrics.data_input import TechnicalData, AccountInfo
from monaimetrics.strategy import (
    ManagedPosition,
    evaluate_opportunity,
    review_position,
    generate_plan,
)


NOW = datetime.now(timezone.utc)
CFG = load_config()


# ---------------------------------------------------------------------------
# Calculator Normalization Tests
# ---------------------------------------------------------------------------

class TestNormalizeRange:
    def test_midpoint(self):
        assert calculators.normalize_range(50, 0, 100) == 0.0

    def test_min_value(self):
        assert calculators.normalize_range(0, 0, 100) == -1.0

    def test_max_value(self):
        assert calculators.normalize_range(100, 0, 100) == 1.0

    def test_below_min_clamped(self):
        assert calculators.normalize_range(-10, 0, 100) == -1.0

    def test_above_max_clamped(self):
        assert calculators.normalize_range(150, 0, 100) == 1.0

    def test_invert(self):
        assert calculators.normalize_range(100, 0, 100, invert=True) == -1.0
        assert calculators.normalize_range(0, 0, 100, invert=True) == 1.0

    def test_equal_min_max(self):
        assert calculators.normalize_range(50, 50, 50) == 0.0

    def test_custom_range(self):
        result = calculators.normalize_range(25, 10, 40)
        assert -1.0 <= result <= 1.0
        assert result == 0.0  # 25 is midpoint of 10-40


class TestNormalizeZscore:
    def test_at_mean(self):
        assert calculators.normalize_zscore(50, 50, 10) == 0.0

    def test_one_std_above(self):
        assert calculators.normalize_zscore(60, 50, 10) == pytest.approx(1.0)

    def test_one_std_below(self):
        assert calculators.normalize_zscore(40, 50, 10) == pytest.approx(-1.0)

    def test_clamped_high(self):
        assert calculators.normalize_zscore(100, 50, 10) == 1.0

    def test_clamped_low(self):
        assert calculators.normalize_zscore(0, 50, 10) == -1.0

    def test_zero_std(self):
        assert calculators.normalize_zscore(60, 50, 0) == 0.0

    def test_invert(self):
        assert calculators.normalize_zscore(60, 50, 10, invert=True) == pytest.approx(-1.0)


class TestNormalizeThreshold:
    def test_above(self):
        assert calculators.normalize_threshold(60, 50) == 1.0

    def test_below(self):
        assert calculators.normalize_threshold(40, 50) == -1.0

    def test_at_threshold(self):
        assert calculators.normalize_threshold(50, 50) == 1.0

    def test_invert(self):
        assert calculators.normalize_threshold(60, 50, invert=True) == -1.0


class TestAggregateAlphaAdjustment:
    def test_single_effect(self):
        result = calculators.aggregate_alpha_adjustment(
            [(1.0, 1.0, 10.0)], global_max=15.0,
        )
        assert result == 10.0

    def test_per_effect_cap(self):
        result = calculators.aggregate_alpha_adjustment(
            [(1.0, 2.0, 5.0)], global_max=15.0,
        )
        assert result == 5.0  # raw=10.0, capped at max_adj=5.0

    def test_global_cap(self):
        result = calculators.aggregate_alpha_adjustment(
            [(1.0, 1.0, 10.0), (1.0, 1.0, 10.0)], global_max=15.0,
        )
        assert result == 15.0  # 10+10=20, capped at 15

    def test_negative(self):
        result = calculators.aggregate_alpha_adjustment(
            [(-1.0, 1.0, 10.0)], global_max=15.0,
        )
        assert result == -10.0

    def test_empty(self):
        result = calculators.aggregate_alpha_adjustment([], global_max=15.0)
        assert result == 0.0

    def test_mixed_effects(self):
        result = calculators.aggregate_alpha_adjustment(
            [(1.0, 1.0, 5.0), (-1.0, 1.0, 3.0)], global_max=15.0,
        )
        assert result == 2.0  # 5.0 + (-3.0) = 2.0


# ---------------------------------------------------------------------------
# Signal Normalization Dispatch
# ---------------------------------------------------------------------------

class TestNormalizeSignal:
    def test_range_method(self):
        config = NormalizationConfig(method="range", min_value=0, max_value=100)
        assert normalize_signal(50.0, config) == 0.0

    def test_zscore_method(self):
        config = NormalizationConfig(method="zscore", mean=50, std=10)
        assert normalize_signal(60.0, config) == pytest.approx(1.0)

    def test_threshold_method(self):
        config = NormalizationConfig(method="threshold", threshold=50)
        assert normalize_signal(60.0, config) == 1.0

    def test_unknown_method(self):
        config = NormalizationConfig(method="unknown")
        assert normalize_signal(50.0, config) == 0.0

    def test_range_with_invert(self):
        config = NormalizationConfig(
            method="range", min_value=10, max_value=40, invert=True,
        )
        assert normalize_signal(40.0, config) == -1.0


# ---------------------------------------------------------------------------
# Signal Cache Tests
# ---------------------------------------------------------------------------

class TestSignalCache:
    def test_put_and_get(self):
        cache = SignalCache()
        val = CachedSignalValue("test", 0.5, NOW)
        cache.put(val)
        assert cache.get("test") is val

    def test_get_missing(self):
        cache = SignalCache()
        assert cache.get("missing") is None

    def test_stale_check(self):
        cache = SignalCache()
        old_time = NOW - timedelta(minutes=120)
        cache.put(CachedSignalValue("test", 0.5, old_time))
        assert cache.is_stale("test", ttl_minutes=60) is True

    def test_fresh_check(self):
        cache = SignalCache()
        cache.put(CachedSignalValue("test", 0.5, NOW))
        assert cache.is_stale("test", ttl_minutes=60) is False

    def test_missing_is_stale(self):
        cache = SignalCache()
        assert cache.is_stale("missing", ttl_minutes=60) is True

    def test_overwrite(self):
        cache = SignalCache()
        cache.put(CachedSignalValue("test", 0.5, NOW))
        cache.put(CachedSignalValue("test", 0.9, NOW))
        assert cache.get("test").normalized_value == 0.9


# ---------------------------------------------------------------------------
# Effect Application Tests
# ---------------------------------------------------------------------------

class TestEffectApplies:
    def test_all_trade_types(self):
        effect = SignalEffect("test", "bull", ["all"], 1.0, 10.0, "both")
        assert effect_applies(effect, {"energy"}, "buy") is True
        assert effect_applies(effect, {"financials"}, "sell") is True

    def test_matching_type(self):
        effect = SignalEffect("test", "bull", ["energy", "oil"], 1.0, 10.0, "both")
        assert effect_applies(effect, {"energy"}, "buy") is True

    def test_non_matching_type(self):
        effect = SignalEffect("test", "bull", ["energy"], 1.0, 10.0, "both")
        assert effect_applies(effect, {"financials"}, "buy") is False

    def test_side_filter_buy_only(self):
        effect = SignalEffect("test", "bull", ["all"], 1.0, 10.0, "buy")
        assert effect_applies(effect, {"energy"}, "buy") is True
        assert effect_applies(effect, {"energy"}, "sell") is False

    def test_side_filter_sell_only(self):
        effect = SignalEffect("test", "bull", ["all"], 1.0, 10.0, "sell")
        assert effect_applies(effect, {"energy"}, "sell") is True
        assert effect_applies(effect, {"energy"}, "buy") is False

    def test_side_both(self):
        effect = SignalEffect("test", "bull", ["all"], 1.0, 10.0, "both")
        assert effect_applies(effect, {"energy"}, "buy") is True
        assert effect_applies(effect, {"energy"}, "sell") is True

    def test_empty_symbol_types(self):
        effect = SignalEffect("test", "bull", ["energy"], 1.0, 10.0, "both")
        assert effect_applies(effect, set(), "buy") is False

    def test_empty_symbol_types_with_all(self):
        effect = SignalEffect("test", "bull", ["all"], 1.0, 10.0, "both")
        assert effect_applies(effect, set(), "buy") is True


# ---------------------------------------------------------------------------
# Polarity Tests
# ---------------------------------------------------------------------------

class TestPolarity:
    def _make_signal_def(self, polarity, trade_types=None):
        return SignalDefinition(
            id="test_sig",
            name="Test",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect(
                "effect1", polarity,
                trade_types or ["all"], 1.0, 10.0, "both",
            )],
        )

    def test_bull_keeps_sign(self):
        sig_def = self._make_signal_def("bull")
        cache = SignalCache()
        cache.put(CachedSignalValue("test_sig", 0.8, NOW))

        result = compute_alpha_adjustment(
            [sig_def], cache,
            symbol_types={"energy"}, side="buy", global_max=15.0,
        )
        assert result > 0  # positive signal, bull polarity -> positive adjustment

    def test_bear_flips_sign(self):
        sig_def = self._make_signal_def("bear")
        cache = SignalCache()
        cache.put(CachedSignalValue("test_sig", 0.8, NOW))

        result = compute_alpha_adjustment(
            [sig_def], cache,
            symbol_types={"energy"}, side="buy", global_max=15.0,
        )
        assert result < 0  # positive signal, bear polarity -> negative adjustment

    def test_negative_signal_bull(self):
        """Negative signal with bull polarity stays negative."""
        sig_def = self._make_signal_def("bull")
        cache = SignalCache()
        cache.put(CachedSignalValue("test_sig", -0.8, NOW))

        result = compute_alpha_adjustment(
            [sig_def], cache,
            symbol_types={"energy"}, side="buy", global_max=15.0,
        )
        assert result < 0

    def test_negative_signal_bear(self):
        """Negative signal with bear polarity flips to positive."""
        sig_def = self._make_signal_def("bear")
        cache = SignalCache()
        cache.put(CachedSignalValue("test_sig", -0.8, NOW))

        result = compute_alpha_adjustment(
            [sig_def], cache,
            symbol_types={"energy"}, side="buy", global_max=15.0,
        )
        assert result > 0


# ---------------------------------------------------------------------------
# Compute Alpha Adjustment Integration
# ---------------------------------------------------------------------------

class TestComputeAlphaAdjustment:
    def _make_definitions(self):
        """Create a mideast stability signal with divergent effects."""
        return [SignalDefinition(
            id="mideast",
            name="Middle East Stability",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[
                SignalEffect("equity_drag", "bull", ["financials"], 1.0, 8.0, "both"),
                SignalEffect("oil_boost", "bear", ["energy", "oil"], 1.0, 10.0, "both"),
                SignalEffect("shipping", "bear", ["shipping"], 0.6, 5.0, "buy"),
            ],
        )]

    def test_divergent_effects(self):
        """Same signal, opposite effects for different trade types."""
        defs = self._make_definitions()
        cache = SignalCache()
        # Low stability -> normalized to -1.0
        cache.put(CachedSignalValue("mideast", -1.0, NOW))

        # Financials (bull polarity): -1.0 kept -> negative adjustment
        fin_adj = compute_alpha_adjustment(
            defs, cache,
            symbol_types={"financials"}, side="buy", global_max=15.0,
        )
        assert fin_adj < 0

        # Energy (bear polarity): -1.0 flipped to +1.0 -> positive adjustment
        energy_adj = compute_alpha_adjustment(
            defs, cache,
            symbol_types={"energy"}, side="buy", global_max=15.0,
        )
        assert energy_adj > 0

    def test_no_matching_types(self):
        defs = self._make_definitions()
        cache = SignalCache()
        cache.put(CachedSignalValue("mideast", 0.5, NOW))

        result = compute_alpha_adjustment(
            defs, cache,
            symbol_types={"technology"}, side="buy", global_max=15.0,
        )
        assert result == 0.0

    def test_no_cached_value(self):
        defs = self._make_definitions()
        cache = SignalCache()  # empty

        result = compute_alpha_adjustment(
            defs, cache,
            symbol_types={"energy"}, side="buy", global_max=15.0,
        )
        assert result == 0.0

    def test_shipping_buy_only(self):
        defs = self._make_definitions()
        cache = SignalCache()
        cache.put(CachedSignalValue("mideast", -1.0, NOW))

        buy_adj = compute_alpha_adjustment(
            defs, cache,
            symbol_types={"shipping"}, side="buy", global_max=15.0,
        )
        sell_adj = compute_alpha_adjustment(
            defs, cache,
            symbol_types={"shipping"}, side="sell", global_max=15.0,
        )
        assert buy_adj != 0.0
        assert sell_adj == 0.0  # shipping effect is buy-only


# ---------------------------------------------------------------------------
# Trade Type Resolver Tests
# ---------------------------------------------------------------------------

class TestTradeTypeResolver:
    def test_manual_overrides(self):
        resolver = TradeTypeResolver(overrides={"XOM": ["energy", "oil"]})
        types = resolver.resolve("XOM")
        assert "energy" in types
        assert "oil" in types

    def test_unknown_symbol(self):
        resolver = TradeTypeResolver()
        types = resolver.resolve("UNKNOWN")
        assert types == set()

    def test_no_alpaca_client(self):
        resolver = TradeTypeResolver(overrides={"XOM": ["energy"]})
        types = resolver.resolve("AAPL")
        assert types == set()


# ---------------------------------------------------------------------------
# YAML Parsing Tests
# ---------------------------------------------------------------------------

class TestYAMLParsing:
    def test_full_yaml(self):
        yaml_content = {
            "signals": [
                {
                    "id": "test_sig",
                    "name": "Test Signal",
                    "source": {
                        "type": "rest_api",
                        "url_template": "http://example.com/api",
                        "auth_env_var": "TEST_KEY",
                        "response_path": "data.value",
                    },
                    "normalization": {
                        "method": "range",
                        "min_value": 0,
                        "max_value": 100,
                        "invert": False,
                    },
                    "ttl_minutes": 30,
                    "effects": [
                        {
                            "name": "Effect 1",
                            "polarity": "bull",
                            "trade_types": ["energy"],
                            "weight": 0.8,
                            "max_adjustment": 10.0,
                            "apply_to": "buy",
                        },
                    ],
                },
            ],
            "trade_types": {
                "XOM": ["energy", "oil"],
                "LMT": ["defense"],
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            yaml.dump(yaml_content, f)
            path = f.name

        try:
            defs, types = load_signal_definitions(path)
            assert len(defs) == 1
            assert defs[0].id == "test_sig"
            assert defs[0].ttl_minutes == 30
            assert len(defs[0].effects) == 1
            assert defs[0].effects[0].polarity == "bull"
            assert defs[0].effects[0].weight == 0.8
            assert defs[0].normalization.method == "range"
            assert defs[0].source.response_path == "data.value"

            assert "XOM" in types
            assert types["XOM"] == ["energy", "oil"]
            assert types["LMT"] == ["defense"]
        finally:
            os.unlink(path)

    def test_empty_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            f.write("")
            path = f.name

        try:
            defs, types = load_signal_definitions(path)
            assert defs == []
            assert types == {}
        finally:
            os.unlink(path)

    def test_signals_only(self):
        yaml_content = {
            "signals": [
                {
                    "id": "simple",
                    "name": "Simple",
                    "source": {"type": "rest_api", "url_template": "http://x"},
                    "normalization": {"method": "threshold", "threshold": 50},
                    "ttl_minutes": 15,
                    "effects": [
                        {
                            "name": "E1",
                            "polarity": "bear",
                            "trade_types": ["all"],
                            "weight": 1.0,
                            "max_adjustment": 5.0,
                            "apply_to": "both",
                        },
                    ],
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            yaml.dump(yaml_content, f)
            path = f.name

        try:
            defs, types = load_signal_definitions(path)
            assert len(defs) == 1
            assert types == {}
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Strategy Integration Tests (alpha params passed through)
# ---------------------------------------------------------------------------

def make_tech(
    symbol="AAPL", price=150.0, ma_150=140.0, ma_slope=0.005,
    atr_14=3.0, volume_ratio=1.5, stage=2,
) -> TechnicalData:
    return TechnicalData(
        symbol=symbol, price=price, ma_150=ma_150, ma_slope=ma_slope,
        atr_14=atr_14, volume_ratio=volume_ratio, stage=stage,
        timestamp=NOW,
    )


def make_position(
    symbol="AAPL", tier=Tier.MODERATE, entry_price=100.0,
    current_price=110.0, stop_price=92.0, target_price=125.0,
    trailing_stop=0.0, highest_price=110.0, weeks_held=2, qty=10.0,
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


class TestEvaluateWithAlpha:
    def _make_bullish_alpha(self):
        sig_def = SignalDefinition(
            id="bull_signal", name="Bullish",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect("boost", "bull", ["all"], 1.0, 15.0, "both")],
        )
        cache = SignalCache()
        cache.put(CachedSignalValue("bull_signal", 1.0, NOW))
        return [sig_def], cache

    def _make_bearish_alpha(self):
        sig_def = SignalDefinition(
            id="bear_signal", name="Bearish",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect("drag", "bull", ["all"], 1.0, 15.0, "both")],
        )
        cache = SignalCache()
        cache.put(CachedSignalValue("bear_signal", -1.0, NOW))
        return [sig_def], cache

    def test_no_alpha_unchanged(self):
        """Without alpha params, function works as before."""
        tech = make_tech(stage=2, volume_ratio=2.0, price=150, ma_150=140)
        sig = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        assert sig.action in (SignalType.BUY, SignalType.WATCH)

    def test_bullish_alpha_boosts_confidence(self):
        defs, cache = self._make_bullish_alpha()
        tech = make_tech(stage=2, volume_ratio=2.0, price=150, ma_150=140)
        sig_with = evaluate_opportunity(
            "AAPL", tech, Tier.MODERATE, 50000, CFG,
            symbol_types={"technology"}, alpha_definitions=defs, alpha_cache=cache,
        )
        sig_without = evaluate_opportunity("AAPL", tech, Tier.MODERATE, 50000, CFG)
        assert sig_with.confidence >= sig_without.confidence

    def test_alpha_reason_appended(self):
        defs, cache = self._make_bullish_alpha()
        tech = make_tech(stage=2, volume_ratio=2.0, price=150, ma_150=140)
        sig = evaluate_opportunity(
            "AAPL", tech, Tier.MODERATE, 50000, CFG,
            symbol_types={"technology"}, alpha_definitions=defs, alpha_cache=cache,
        )
        alpha_reasons = [r for r in sig.reasons if "Alpha signals" in r]
        assert len(alpha_reasons) > 0


class TestReviewWithAlpha:
    def test_strong_negative_triggers_sell(self):
        """Alpha adjustment <= -10 triggers a sell when no other sell signals."""
        sig_def = SignalDefinition(
            id="crisis", name="Crisis",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect("crash", "bull", ["all"], 1.0, 15.0, "both")],
        )
        cache = SignalCache()
        cache.put(CachedSignalValue("crisis", -1.0, NOW))

        pos = make_position(current_price=110.0)
        tech = make_tech(price=110.0, stage=2)

        sig = review_position(
            pos, tech, 50000, CFG,
            symbol_types={"technology"},
            alpha_definitions=[sig_def], alpha_cache=cache,
        )
        assert sig.action == SignalType.SELL
        assert "Alpha signals" in sig.reasons[0]

    def test_mild_negative_no_sell(self):
        """Alpha adjustment > -10 does not trigger sell on its own."""
        sig_def = SignalDefinition(
            id="mild", name="Mild",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect("small", "bull", ["all"], 1.0, 5.0, "both")],
        )
        cache = SignalCache()
        cache.put(CachedSignalValue("mild", -1.0, NOW))

        pos = make_position(current_price=110.0)
        tech = make_tech(price=110.0, stage=2)

        sig = review_position(
            pos, tech, 50000, CFG,
            symbol_types={"technology"},
            alpha_definitions=[sig_def], alpha_cache=cache,
        )
        assert sig.action == SignalType.HOLD

    def test_existing_sell_takes_priority(self):
        """When stop-loss is hit, alpha doesn't add another sell signal."""
        sig_def = SignalDefinition(
            id="crisis", name="Crisis",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect("crash", "bull", ["all"], 1.0, 15.0, "both")],
        )
        cache = SignalCache()
        cache.put(CachedSignalValue("crisis", -1.0, NOW))

        pos = make_position(current_price=91.0, stop_price=92.0)
        tech = make_tech(price=91.0, stage=2)

        sig = review_position(
            pos, tech, 50000, CFG,
            symbol_types={"technology"},
            alpha_definitions=[sig_def], alpha_cache=cache,
        )
        # Should be stop-loss emergency, not alpha standard sell
        assert sig.action == SignalType.SELL
        assert sig.urgency == SignalUrgency.EMERGENCY

    def test_no_alpha_unchanged(self):
        """Without alpha params, review_position works as before."""
        pos = make_position(current_price=110.0)
        tech = make_tech(price=110.0, stage=2)
        sig = review_position(pos, tech, 50000, CFG)
        assert sig.action == SignalType.HOLD


class TestGeneratePlanWithAlpha:
    def test_plan_without_alpha(self):
        """Existing generate_plan still works without alpha params."""
        plan = generate_plan([], {}, make_account(), {}, CFG)
        assert plan.signals == []

    def test_plan_passes_alpha_through(self):
        """Alpha params are passed to evaluate_opportunity and review_position."""
        sig_def = SignalDefinition(
            id="boost", name="Boost",
            source=SignalSource("rest_api", "", "", ""),
            normalization=NormalizationConfig("range"),
            ttl_minutes=60,
            effects=[SignalEffect("up", "bull", ["all"], 1.0, 15.0, "both")],
        )
        cache = SignalCache()
        cache.put(CachedSignalValue("boost", 1.0, NOW))
        resolver = TradeTypeResolver(overrides={"AAPL": ["technology"]})

        techs = {"AAPL": make_tech(symbol="AAPL", stage=2, volume_ratio=2.0, price=150, ma_150=140)}
        plan = generate_plan(
            [], techs, make_account(),
            {Tier.MODERATE: 0, Tier.HIGH: 0}, CFG,
            alpha_definitions=[sig_def],
            alpha_cache=cache,
            trade_type_resolver=resolver,
        )
        buy_signals = [s for s in plan.signals if s.action == SignalType.BUY]
        if buy_signals:
            alpha_reasons = [r for r in buy_signals[0].reasons if "Alpha" in r]
            assert len(alpha_reasons) > 0
