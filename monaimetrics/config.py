"""
Single source of truth for every tunable number in the system.
All percentages stored as decimals (0.25 = 25%).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os

from monaimetrics.user_config import load_user_config

# API keys come from Replit app secrets (already in os.environ).
# Non-secret settings (trading mode, position sizing, etc.) come from user_config.yaml.
load_user_config()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskProfile(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class Tier(Enum):
    MODERATE = "moderate"
    HIGH = "high"


class Stage(Enum):
    BASING = 1
    ADVANCING = 2
    TOPPING = 3
    DECLINING = 4


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"
    REDUCE = "reduce"
    INCREASE = "increase"


class SignalUrgency(Enum):
    STANDARD = "standard"
    ELEVATED = "elevated"
    IMMEDIATE = "immediate"
    EMERGENCY = "emergency"
    MONITOR = "monitor"


class NotificationPriority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    STANDARD = "standard"
    INFORMATIONAL = "informational"


class EventScope(Enum):
    GLOBAL = "global"
    REGIONAL = "regional"
    SECTOR = "sector"
    COMPANY = "company"


class EventSeverity(Enum):
    NORMAL = "normal"
    POSITIVE_ABNORMAL = "positive_abnormal"
    NEGATIVE_ABNORMAL = "negative_abnormal"


class EventDuration(Enum):
    TRANSIENT = "transient"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    STRUCTURAL = "structural"


class EventConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Framework Configs
# ---------------------------------------------------------------------------

@dataclass
class CycleConfig:
    """Framework 1: Cycle Positioning (Marks)"""
    indicator_weights: tuple[float, ...] = (0.25, 0.25, 0.25, 0.25)
    lookback_years: int = 10
    assessment_frequency_days: int = 7
    contrarian_delay_days: int = 14


@dataclass
class StageConfig:
    """Framework 2: Stage Analysis (Weinstein)"""
    ma_period_days: int = 150
    breakout_volume_multiple: float = 2.0
    confirmation_weeks: int = 2


@dataclass
class CANSLIMWeights:
    current_earnings: float = 0.25   # C
    annual_earnings: float = 0.20    # A
    new_catalyst: float = 0.10       # N
    supply_demand: float = 0.15      # S
    leader_status: float = 0.20      # L
    institutional: float = 0.10      # I


@dataclass
class CANSLIMConfig:
    """Framework 3: Growth Quality (O'Neil)"""
    min_composite_score: int = 60
    weights: CANSLIMWeights = field(default_factory=CANSLIMWeights)
    leader_rs_threshold: int = 70


@dataclass
class GreenblattConfig:
    """Framework 4: Quality-Value (Magic Formula)"""
    roc_minimum_pct: float = 0.15
    reranking_frequency_days: int = 30
    sector_exclusions: tuple[str, ...] = ("financials", "utilities")
    weight_moderate: float = 0.30
    weight_high: float = 0.10


@dataclass
class EventCascadeConfig:
    """Framework 5: Event-News-Price Cascade"""
    reaction_blackout_hours: int = 4
    overreaction_threshold: float = 2.0
    underreaction_threshold: float = 0.3
    structural_monitoring_days: int = 30
    entity_propagation_depth: int = 2


@dataclass
class AsymmetryConfig:
    """Framework 6: Asymmetric Opportunity (Thorp)"""
    min_ratio: float = 3.0
    dislocation_scan_drawdown: float = 0.15
    speed_premium_ratio: float = 5.0
    speed_premium_conviction_factor: float = 0.70


@dataclass
class KellyConfig:
    """Framework 7: Conviction-Weighted Sizing"""
    min_conviction: int = 40
    volatility_lookback_days: int = 30
    edge_decay_factor: float = 0.95


# ---------------------------------------------------------------------------
# Tier Configs
# ---------------------------------------------------------------------------

@dataclass
class ModerateTierConfig:
    profit_target: float = 0.25
    stop_loss: float = 0.08
    vol_adjustment_factor: float = 0.5
    non_perf_review_weeks: int = 4
    non_perf_gain_threshold: float = 0.05
    max_hold_weeks: int = 12
    max_position: float = 0.10
    kelly_fraction: float = 0.25


@dataclass
class TrailingStopMilestone:
    gain_threshold: float
    lock_gain: float


@dataclass
class HighRiskTierConfig:
    atr_stop_multiplier: float = 2.5
    atr_period_days: int = 14
    max_stop: float = 0.15
    min_stop: float = 0.05
    milestones: tuple[TrailingStopMilestone, ...] = (
        TrailingStopMilestone(0.15, 0.0),
        TrailingStopMilestone(0.30, 0.15),
        TrailingStopMilestone(0.50, 0.30),
    )
    mature_trail_atr_multiplier: float = 1.75
    stage3_tighten_atr_multiplier: float = 1.0
    non_perf_review_weeks: int = 6
    non_perf_gain_threshold: float = 0.08
    max_hold_weeks: int = 10
    thesis_expiry_weeks: int = 8
    max_position: float = 0.05
    kelly_fraction: float = 0.35


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

@dataclass
class TierAllocation:
    moderate: float
    high: float
    cash: float

    def __post_init__(self):
        total = self.moderate + self.high + self.cash
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Allocation must sum to 1.0, got {total}")


ALLOCATION_TABLES: dict[RiskProfile, dict[int, TierAllocation]] = {
    RiskProfile.CONSERVATIVE: {
        -2: TierAllocation(0.60, 0.36, 0.04),
        -1: TierAllocation(0.65, 0.30, 0.05),
         0: TierAllocation(0.75, 0.15, 0.10),
         1: TierAllocation(0.80, 0.10, 0.10),
         2: TierAllocation(0.82, 0.05, 0.13),
    },
    RiskProfile.MODERATE: {
        -2: TierAllocation(0.50, 0.46, 0.04),
        -1: TierAllocation(0.55, 0.40, 0.05),
         0: TierAllocation(0.65, 0.28, 0.07),
         1: TierAllocation(0.70, 0.20, 0.10),
         2: TierAllocation(0.77, 0.10, 0.13),
    },
    RiskProfile.AGGRESSIVE: {
        -2: TierAllocation(0.42, 0.55, 0.03),
        -1: TierAllocation(0.47, 0.48, 0.05),
         0: TierAllocation(0.55, 0.40, 0.05),
         1: TierAllocation(0.60, 0.30, 0.10),
         2: TierAllocation(0.65, 0.22, 0.13),
    },
}


# ---------------------------------------------------------------------------
# Safety / Circuit Breakers
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreakerConfig:
    max_drawdown: float = 0.18
    drawdown_recovery: float = 0.10
    rapid_loss_count: int = 3
    rapid_loss_pause_hours: int = 48
    concentration_breach_multiple: float = 1.5
    data_staleness_threshold_minutes: int = 60


@dataclass
class StructuralDivergenceConfig:
    euphoria_cycle_threshold: float = 1.5
    euphoria_indicators_required: int = 3
    deterioration_indicators_required: int = 3
    persistence_weeks: int = 4
    reduced_profit_target_factor: float = 0.5
    tightened_trail_atr_multiplier: float = 1.0
    hold_audit_frequency_days: int = 1
    non_perf_acceleration_factor: float = 0.5
    breakeven_window_weeks: int = 2


# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------

@dataclass
class RebalanceConfig:
    drift_threshold: float = 0.07
    severe_drift_threshold: float = 0.12
    scheduled_frequency_days: int = 30


# ---------------------------------------------------------------------------
# Hold Audit
# ---------------------------------------------------------------------------

@dataclass
class HoldAuditConfig:
    frequency_days: int = 7


# ---------------------------------------------------------------------------
# Framework Weighting by Tier
# ---------------------------------------------------------------------------

@dataclass
class FrameworkWeights:
    greenblatt: float
    canslim: float
    event_cascade: float
    asymmetry: float


FRAMEWORK_WEIGHTS: dict[Tier, FrameworkWeights] = {
    Tier.MODERATE: FrameworkWeights(
        greenblatt=0.30,
        canslim=0.40,
        event_cascade=0.15,
        asymmetry=0.15,
    ),
    Tier.HIGH: FrameworkWeights(
        greenblatt=0.10,
        canslim=0.40,
        event_cascade=0.25,
        asymmetry=0.25,
    ),
}


# ---------------------------------------------------------------------------
# API / External
# ---------------------------------------------------------------------------

@dataclass
class APIConfig:
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = False
    alpaca_base_url: str = "https://api.alpaca.markets/v2"
    financial_datasets_api_key: str = ""
    sentiment_api_url: str = ""
    sentiment_api_key: str = ""
    decis_api_key: str = ""
    decis_base_url: str = ""
    anthropic_api_key: str = ""


def _load_api_config() -> APIConfig:
    return APIConfig(
        alpaca_api_key=os.environ.get("ALPACA_API_KEY", ""),
        alpaca_secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
        alpaca_paper=os.environ.get("ALPACA_PAPER", "false").lower() == "true",
        alpaca_base_url=os.environ.get(
            "ALPACA_BASE_URL", "https://api.alpaca.markets/v2"
        ),
        financial_datasets_api_key=os.environ.get("FINANCIAL_DATASETS_API_KEY", ""),
        sentiment_api_url=os.environ.get("SENTIMENT_API_URL", ""),
        sentiment_api_key=os.environ.get("SENTIMENT_API_KEY", ""),
        decis_api_key=os.environ.get("DECIS_API_KEY", ""),
        decis_base_url=os.environ.get("DECIS_BASE_URL", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )


# ---------------------------------------------------------------------------
# Alpha Signals
# ---------------------------------------------------------------------------

@dataclass
class AlphaSignalsConfig:
    enabled: bool = False
    config_path: str = "alpha_signals.yaml"
    global_max_adjustment: float = 15.0
    refresh_on_cycle: bool = True
    log_signals: bool = True


# ---------------------------------------------------------------------------
# Main Config
# ---------------------------------------------------------------------------

@dataclass
class SystemConfig:
    profile: RiskProfile
    cycle: CycleConfig
    stage: StageConfig
    canslim: CANSLIMConfig
    greenblatt: GreenblattConfig
    event_cascade: EventCascadeConfig
    asymmetry: AsymmetryConfig
    kelly: KellyConfig
    moderate_tier: ModerateTierConfig
    high_risk_tier: HighRiskTierConfig
    circuit_breakers: CircuitBreakerConfig
    structural_divergence: StructuralDivergenceConfig
    rebalance: RebalanceConfig
    hold_audit: HoldAuditConfig
    api: APIConfig
    alpha_signals: AlphaSignalsConfig = field(default_factory=AlphaSignalsConfig)
    dry_run: bool = True
    max_share_price_usd: float = 25.0  # skip stocks above this price per share
    cash_reserve_pct: float = 0.20  # fraction of cash to keep undeployed

    def get_allocation(self, cycle_score: int) -> TierAllocation:
        clamped = max(-2, min(2, cycle_score))
        return ALLOCATION_TABLES[self.profile][clamped]

    def get_framework_weights(self, tier: Tier) -> FrameworkWeights:
        return FRAMEWORK_WEIGHTS[tier]


# ---------------------------------------------------------------------------
# Profile Factory
# ---------------------------------------------------------------------------

def load_config(
    profile: RiskProfile = RiskProfile.MODERATE,
) -> SystemConfig:
    """Build a full SystemConfig from a risk profile and environment variables."""

    tier_defaults: dict[RiskProfile, dict] = {
        RiskProfile.CONSERVATIVE: dict(
            moderate=dict(
                profit_target=0.20, stop_loss=0.06,
                kelly_fraction=0.15, max_position=0.08,
                non_perf_review_weeks=3,
            ),
            high=dict(
                kelly_fraction=0.25, max_position=0.04,
                atr_stop_multiplier=2.0, non_perf_review_weeks=5,
            ),
            circuit=dict(max_drawdown=0.12),
        ),
        RiskProfile.MODERATE: dict(
            moderate=dict(),
            high=dict(),
            circuit=dict(),
        ),
        RiskProfile.AGGRESSIVE: dict(
            moderate=dict(
                profit_target=0.30, stop_loss=0.10,
                kelly_fraction=0.30, max_position=0.12,
                non_perf_review_weeks=5,
            ),
            high=dict(
                kelly_fraction=0.40, max_position=0.07,
                atr_stop_multiplier=3.0, non_perf_review_weeks=8,
            ),
            circuit=dict(max_drawdown=0.25),
        ),
    }

    overrides = tier_defaults[profile]

    # PROFIT_TARGET and STOP_LOSS env vars override the profile default for the moderate tier
    mod_defaults = ModerateTierConfig()
    env_profit_target = os.environ.get("PROFIT_TARGET")
    env_stop_loss = os.environ.get("STOP_LOSS")
    if env_profit_target is not None:
        overrides["moderate"]["profit_target"] = float(env_profit_target)
    elif "profit_target" not in overrides["moderate"]:
        overrides["moderate"]["profit_target"] = mod_defaults.profit_target
    if env_stop_loss is not None:
        overrides["moderate"]["stop_loss"] = float(env_stop_loss)
    elif "stop_loss" not in overrides["moderate"]:
        overrides["moderate"]["stop_loss"] = mod_defaults.stop_loss

    return SystemConfig(
        profile=profile,
        cycle=CycleConfig(),
        stage=StageConfig(),
        canslim=CANSLIMConfig(),
        greenblatt=GreenblattConfig(),
        event_cascade=EventCascadeConfig(),
        asymmetry=AsymmetryConfig(),
        kelly=KellyConfig(),
        moderate_tier=ModerateTierConfig(**overrides["moderate"]),
        high_risk_tier=HighRiskTierConfig(**overrides["high"]),
        circuit_breakers=CircuitBreakerConfig(**overrides["circuit"]),
        structural_divergence=StructuralDivergenceConfig(),
        rebalance=RebalanceConfig(),
        hold_audit=HoldAuditConfig(),
        api=_load_api_config(),
        alpha_signals=AlphaSignalsConfig(),
        dry_run=os.environ.get("DRY_RUN", "true").lower() == "true",
        max_share_price_usd=float(os.environ.get("MAX_SHARE_PRICE_USD", "25.0")),
        cash_reserve_pct=float(os.environ.get("CASH_RESERVE_PCT", "0.20")),
    )


def load_config_from_env(default_profile: RiskProfile = RiskProfile.MODERATE) -> SystemConfig:
    """
    Like load_config() but reads the risk profile from the RISK_PROFILE environment
    variable (set via user_config.yaml or Replit secrets) instead of requiring a
    hard-coded enum value.  Falls back to *default_profile* if the env var is missing
    or unrecognised.
    """
    profile_map = {e.value: e for e in RiskProfile}
    profile_str = os.environ.get("RISK_PROFILE", default_profile.value).lower().strip()
    profile = profile_map.get(profile_str, default_profile)
    return load_config(profile)
