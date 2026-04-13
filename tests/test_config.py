import pytest
from monaimetrics.config import (
    RiskProfile,
    Tier,
    Stage,
    TierAllocation,
    ALLOCATION_TABLES,
    FRAMEWORK_WEIGHTS,
    SystemConfig,
    load_config,
)


class TestEnums:
    def test_stages_numbered_1_to_4(self):
        assert Stage.BASING.value == 1
        assert Stage.DECLINING.value == 4

    def test_risk_profiles(self):
        assert len(RiskProfile) == 3


class TestTierAllocation:
    def test_valid_allocation(self):
        a = TierAllocation(0.65, 0.28, 0.07)
        assert a.moderate == 0.65

    def test_invalid_allocation_raises(self):
        with pytest.raises(ValueError):
            TierAllocation(0.50, 0.50, 0.50)

    def test_all_tables_sum_to_one(self):
        for profile, table in ALLOCATION_TABLES.items():
            for score, alloc in table.items():
                total = alloc.moderate + alloc.high + alloc.cash
                assert abs(total - 1.0) <= 0.01, (
                    f"{profile.value} score={score}: sums to {total}"
                )

    def test_all_profiles_cover_all_scores(self):
        for profile in RiskProfile:
            assert set(ALLOCATION_TABLES[profile].keys()) == {-2, -1, 0, 1, 2}


class TestFrameworkWeights:
    def test_both_tiers_present(self):
        assert Tier.MODERATE in FRAMEWORK_WEIGHTS
        assert Tier.HIGH in FRAMEWORK_WEIGHTS

    def test_weights_sum_to_one(self):
        for tier, fw in FRAMEWORK_WEIGHTS.items():
            total = fw.greenblatt + fw.canslim + fw.event_cascade + fw.asymmetry
            assert abs(total - 1.0) < 0.01, f"{tier.value}: sums to {total}"


class TestLoadConfig:
    def test_default_is_moderate(self):
        cfg = load_config()
        assert cfg.profile == RiskProfile.MODERATE

    def test_dry_run_default_true(self):
        # Code-level default is True (safe). user_config.yaml overrides to False
        # for production. Test in isolation by removing the env var temporarily.
        import os
        prev = os.environ.pop("DRY_RUN", None)
        try:
            cfg = load_config()
            assert cfg.dry_run is True
        finally:
            if prev is not None:
                os.environ["DRY_RUN"] = prev

    def test_conservative_tighter_stops(self):
        # Conservative stop (0.04) must be tighter than moderate (0.06).
        # STOP_LOSS env var must NOT be set; user_config.yaml should not include it.
        import os
        os.environ.pop("STOP_LOSS", None)
        con = load_config(RiskProfile.CONSERVATIVE)
        mod = load_config(RiskProfile.MODERATE)
        assert con.moderate_tier.stop_loss < mod.moderate_tier.stop_loss

    def test_aggressive_wider_stops(self):
        # Aggressive stop (0.10) must be wider than moderate (0.06).
        import os
        os.environ.pop("STOP_LOSS", None)
        agg = load_config(RiskProfile.AGGRESSIVE)
        mod = load_config(RiskProfile.MODERATE)
        assert agg.moderate_tier.stop_loss > mod.moderate_tier.stop_loss

    def test_conservative_lower_drawdown(self):
        con = load_config(RiskProfile.CONSERVATIVE)
        mod = load_config(RiskProfile.MODERATE)
        assert con.circuit_breakers.max_drawdown < mod.circuit_breakers.max_drawdown

    def test_all_profiles_build_without_error(self):
        for profile in RiskProfile:
            cfg = load_config(profile)
            assert cfg.profile == profile

    def test_get_allocation_clamps(self):
        cfg = load_config()
        alloc = cfg.get_allocation(99)
        assert alloc == cfg.get_allocation(2)
        alloc_low = cfg.get_allocation(-99)
        assert alloc_low == cfg.get_allocation(-2)

    def test_get_framework_weights(self):
        cfg = load_config()
        w = cfg.get_framework_weights(Tier.MODERATE)
        assert w.canslim == 0.40

    def test_ratchet_step_default(self):
        cfg = load_config()
        assert cfg.ratchet_step_pct == pytest.approx(0.05)

    def test_ratchet_step_env_override(self, monkeypatch):
        monkeypatch.setenv("RATCHET_STEP", "0.10")
        cfg = load_config()
        assert cfg.ratchet_step_pct == pytest.approx(0.10)

    def test_kelly_fractions_increase_with_risk(self):
        con = load_config(RiskProfile.CONSERVATIVE)
        mod = load_config(RiskProfile.MODERATE)
        agg = load_config(RiskProfile.AGGRESSIVE)
        assert con.moderate_tier.kelly_fraction < mod.moderate_tier.kelly_fraction
        assert mod.moderate_tier.kelly_fraction < agg.moderate_tier.kelly_fraction
