"""
The system's independent reviewer. Runs on a separate, less frequent
schedule. Looks at patterns — what's working, what isn't, and why.
Recommendations are always suggestions to a human, never automatic changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from statistics import mean, stdev

from monaimetrics.config import SystemConfig, Tier
from monaimetrics.reporting import Reporter, TradeRecord, TierPerformance
from monaimetrics.data_input import get_bars, AlpacaClients
from monaimetrics import calculators

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    category: str
    title: str
    detail: str
    confidence: str   # "high", "medium", "low"
    recommendation: str | None = None


@dataclass
class BenchmarkComparison:
    portfolio_return: float
    benchmark_return: float | None
    benchmark_symbol: str
    alpha: float | None
    outperformed: bool | None


@dataclass
class DecisionQuality:
    total_trades: int
    avg_confidence_winners: float
    avg_confidence_losers: float
    confidence_predictive: bool
    high_confidence_win_rate: float
    low_confidence_win_rate: float


@dataclass
class StopAnalysis:
    total_stops: int
    stops_that_recovered: int
    recovery_rate: float
    avg_stop_loss_pct: float
    suggestion: str


@dataclass
class TierAnalysis:
    tier: str
    performance: TierPerformance
    meets_target_win_rate: bool
    meets_target_reward_risk: bool
    notes: list[str]


@dataclass
class AuditReport:
    period_days: int
    generated_at: str
    benchmark: BenchmarkComparison
    decision_quality: DecisionQuality
    stop_analysis: StopAnalysis
    tier_analysis: dict[str, TierAnalysis]
    findings: list[Finding]
    recommendations: list[Finding]
    summary: str


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

class Auditor:
    """
    Runs periodic retrospective analysis. Reads from Reporter's accumulated
    data. Never calls strategy or executes trades.
    """

    def __init__(
        self,
        reporter: Reporter,
        config: SystemConfig,
        clients: AlpacaClients | None = None,
    ):
        self.reporter = reporter
        self.config = config
        self.clients = clients

    def run_audit(
        self,
        period_days: int = 30,
        benchmark_symbol: str = "SPY",
    ) -> AuditReport:
        log.info("Running audit for %d-day period", period_days)

        benchmark = self._analyze_benchmark(period_days, benchmark_symbol)
        decision_quality = self._analyze_decisions(period_days)
        stop_analysis = self._analyze_stops(period_days)
        tier_analysis = self._analyze_tiers(period_days)

        findings: list[Finding] = []
        recommendations: list[Finding] = []

        self._generate_benchmark_findings(benchmark, findings)
        self._generate_decision_findings(decision_quality, findings, recommendations)
        self._generate_stop_findings(stop_analysis, findings, recommendations)
        self._generate_tier_findings(tier_analysis, findings, recommendations)
        self._generate_config_recommendations(period_days, recommendations)

        summary = self._build_summary(benchmark, decision_quality, tier_analysis, findings)

        report = AuditReport(
            period_days=period_days,
            generated_at=datetime.now(timezone.utc).isoformat(),
            benchmark=benchmark,
            decision_quality=decision_quality,
            stop_analysis=stop_analysis,
            tier_analysis=tier_analysis,
            findings=findings,
            recommendations=recommendations,
            summary=summary,
        )

        log.info(
            "Audit complete: %d findings, %d recommendations",
            len(findings), len(recommendations),
        )
        return report

    # ----- Benchmark -----

    def _analyze_benchmark(
        self,
        period_days: int,
        benchmark_symbol: str,
    ) -> BenchmarkComparison:
        snapshots = self.reporter.snapshots
        portfolio_return = 0.0
        if len(snapshots) >= 2:
            first = snapshots[0].portfolio_value
            last = snapshots[-1].portfolio_value
            if first > 0:
                portfolio_return = (last - first) / first

        benchmark_return = None
        try:
            bars = get_bars(benchmark_symbol, days=period_days + 5, clients=self.clients)
            if len(bars) >= 2:
                benchmark_return = (bars[-1].close - bars[0].close) / bars[0].close
        except Exception as e:
            log.warning("Benchmark data unavailable: %s", e)

        alpha = None
        outperformed = None
        if benchmark_return is not None:
            alpha = portfolio_return - benchmark_return
            outperformed = alpha > 0

        return BenchmarkComparison(
            portfolio_return=portfolio_return,
            benchmark_return=benchmark_return,
            benchmark_symbol=benchmark_symbol,
            alpha=alpha,
            outperformed=outperformed,
        )

    # ----- Decision Quality -----

    def _analyze_decisions(self, period_days: int) -> DecisionQuality:
        closed = self.reporter.closed_trades()
        if not closed:
            return DecisionQuality(
                total_trades=0, avg_confidence_winners=0,
                avg_confidence_losers=0, confidence_predictive=False,
                high_confidence_win_rate=0, low_confidence_win_rate=0,
            )

        winners = [t for t in closed if t.gain_pct is not None and t.gain_pct > 0]
        losers = [t for t in closed if t.gain_pct is not None and t.gain_pct <= 0]

        avg_conf_win = mean([t.confidence for t in winners]) if winners else 0
        avg_conf_loss = mean([t.confidence for t in losers]) if losers else 0

        high_conf = [t for t in closed if t.confidence >= 70]
        low_conf = [t for t in closed if t.confidence < 70]

        high_conf_wins = [t for t in high_conf if t.gain_pct is not None and t.gain_pct > 0]
        low_conf_wins = [t for t in low_conf if t.gain_pct is not None and t.gain_pct > 0]

        high_wr = len(high_conf_wins) / len(high_conf) if high_conf else 0
        low_wr = len(low_conf_wins) / len(low_conf) if low_conf else 0

        return DecisionQuality(
            total_trades=len(closed),
            avg_confidence_winners=avg_conf_win,
            avg_confidence_losers=avg_conf_loss,
            confidence_predictive=avg_conf_win > avg_conf_loss,
            high_confidence_win_rate=high_wr,
            low_confidence_win_rate=low_wr,
        )

    # ----- Stop Analysis -----

    def _analyze_stops(self, period_days: int) -> StopAnalysis:
        closed = self.reporter.closed_trades()
        stop_trades = [
            t for t in closed
            if any("stop" in r.lower() for r in t.reasons)
        ]

        if not stop_trades:
            return StopAnalysis(
                total_stops=0, stops_that_recovered=0,
                recovery_rate=0, avg_stop_loss_pct=0,
                suggestion="No stop-loss exits in this period.",
            )

        losses = [t.gain_pct for t in stop_trades if t.gain_pct is not None]
        avg_loss = mean(losses) if losses else 0

        # Count how many stop exits had relatively small losses
        # (suggesting the stop may have been too tight)
        tight_stops = [t for t in stop_trades
                       if t.gain_pct is not None and t.gain_pct > -0.03]
        recovery_rate = len(tight_stops) / len(stop_trades) if stop_trades else 0

        suggestion = "Stop levels appear appropriate."
        if recovery_rate > 0.5:
            suggestion = (
                f"{recovery_rate:.0%} of stop exits had losses under 3%. "
                "Consider widening stops or using ATR-based stops."
            )

        return StopAnalysis(
            total_stops=len(stop_trades),
            stops_that_recovered=len(tight_stops),
            recovery_rate=recovery_rate,
            avg_stop_loss_pct=avg_loss,
            suggestion=suggestion,
        )

    # ----- Tier Analysis -----

    def _analyze_tiers(self, period_days: int) -> dict[str, TierAnalysis]:
        tier_perf = self.reporter.tier_performance()
        result = {}

        targets = {
            "moderate": {"win_rate": 0.55, "reward_risk": 3.0, "avg_gain": 0.20},
            "high": {"win_rate": 0.35, "reward_risk": 4.0, "avg_gain": 0.50},
        }

        for tier_name, perf in tier_perf.items():
            t = targets.get(tier_name, {})
            notes = []

            meets_wr = perf.win_rate >= t.get("win_rate", 0) if perf.trades > 0 else True
            meets_rr = True  # simplified — full reward:risk needs more data

            if perf.trades > 0 and not meets_wr:
                notes.append(
                    f"Win rate {perf.win_rate:.0%} below target {t.get('win_rate', 0):.0%}"
                )
            if perf.trades == 0:
                notes.append("No completed trades in this tier")

            result[tier_name] = TierAnalysis(
                tier=tier_name,
                performance=perf,
                meets_target_win_rate=meets_wr,
                meets_target_reward_risk=meets_rr,
                notes=notes,
            )

        return result

    # ----- Findings Generation -----

    def _generate_benchmark_findings(
        self, benchmark: BenchmarkComparison, findings: list[Finding],
    ):
        if benchmark.alpha is not None:
            if benchmark.alpha > 0:
                findings.append(Finding(
                    category="benchmark",
                    title=f"Outperforming {benchmark.benchmark_symbol}",
                    detail=(
                        f"Portfolio return {benchmark.portfolio_return:.1%} vs "
                        f"benchmark {benchmark.benchmark_return:.1%} "
                        f"(alpha: {benchmark.alpha:+.1%})"
                    ),
                    confidence="high" if abs(benchmark.alpha) > 0.02 else "medium",
                ))
            else:
                findings.append(Finding(
                    category="benchmark",
                    title=f"Underperforming {benchmark.benchmark_symbol}",
                    detail=(
                        f"Portfolio return {benchmark.portfolio_return:.1%} vs "
                        f"benchmark {benchmark.benchmark_return:.1%} "
                        f"(alpha: {benchmark.alpha:+.1%})"
                    ),
                    confidence="high" if abs(benchmark.alpha) > 0.02 else "medium",
                ))

    def _generate_decision_findings(
        self,
        dq: DecisionQuality,
        findings: list[Finding],
        recommendations: list[Finding],
    ):
        if dq.total_trades < 5:
            findings.append(Finding(
                category="decision_quality",
                title="Insufficient data",
                detail=f"Only {dq.total_trades} trades — too few for statistical analysis.",
                confidence="low",
            ))
            return

        if not dq.confidence_predictive:
            findings.append(Finding(
                category="decision_quality",
                title="Confidence scores not predictive",
                detail=(
                    f"Avg confidence on winners ({dq.avg_confidence_winners:.0f}) "
                    f"<= losers ({dq.avg_confidence_losers:.0f}). "
                    "Scoring model may need recalibration."
                ),
                confidence="medium",
            ))
            recommendations.append(Finding(
                category="scoring",
                title="Review composite scoring weights",
                detail="Confidence is not correlating with outcomes.",
                confidence="medium",
                recommendation=(
                    "Investigate which score dimensions are most predictive "
                    "and adjust weights in config."
                ),
            ))

        if dq.high_confidence_win_rate > 0 and dq.low_confidence_win_rate > 0:
            if dq.high_confidence_win_rate < dq.low_confidence_win_rate:
                recommendations.append(Finding(
                    category="scoring",
                    title="High-confidence trades underperforming",
                    detail=(
                        f"High-conf win rate {dq.high_confidence_win_rate:.0%} "
                        f"< low-conf {dq.low_confidence_win_rate:.0%}"
                    ),
                    confidence="medium",
                    recommendation="Consider raising the minimum conviction threshold.",
                ))

    def _generate_stop_findings(
        self,
        sa: StopAnalysis,
        findings: list[Finding],
        recommendations: list[Finding],
    ):
        if sa.total_stops == 0:
            return

        findings.append(Finding(
            category="stops",
            title=f"{sa.total_stops} stop-loss exits",
            detail=f"Avg loss on stops: {sa.avg_stop_loss_pct:.1%}. {sa.suggestion}",
            confidence="high" if sa.total_stops >= 5 else "medium",
        ))

        if sa.recovery_rate > 0.5 and sa.total_stops >= 3:
            recommendations.append(Finding(
                category="stops",
                title="Consider widening stop-loss",
                detail=(
                    f"{sa.recovery_rate:.0%} of stops triggered with losses under 3%. "
                    "Positions may be exiting prematurely."
                ),
                confidence="medium",
                recommendation=(
                    f"Current stop: {self.config.moderate_tier.stop_loss:.0%}. "
                    f"Consider testing {self.config.moderate_tier.stop_loss + 0.02:.0%} "
                    "or switching to ATR-based stops."
                ),
            ))

    def _generate_tier_findings(
        self,
        tier_analysis: dict[str, TierAnalysis],
        findings: list[Finding],
        recommendations: list[Finding],
    ):
        for name, ta in tier_analysis.items():
            if ta.notes:
                for note in ta.notes:
                    findings.append(Finding(
                        category=f"tier_{name}",
                        title=note,
                        detail=f"{name} tier: {ta.performance.trades} trades, {ta.performance.win_rate:.0%} win rate",
                        confidence="medium" if ta.performance.trades >= 5 else "low",
                    ))

            if ta.performance.trades >= 10 and not ta.meets_target_win_rate:
                recommendations.append(Finding(
                    category=f"tier_{name}",
                    title=f"Improve {name} tier win rate",
                    detail=f"Current {ta.performance.win_rate:.0%}, below target.",
                    confidence="high",
                    recommendation=f"Review entry criteria for {name} tier positions.",
                ))

    def _generate_config_recommendations(
        self,
        period_days: int,
        recommendations: list[Finding],
    ):
        closed = self.reporter.closed_trades()
        if len(closed) < 10:
            return

        # Non-performance exits
        non_perf = [t for t in closed if any("non-perform" in r.lower() for r in t.reasons)]
        non_perf_rate = len(non_perf) / len(closed) if closed else 0

        if non_perf_rate > 0.25:
            recommendations.append(Finding(
                category="config",
                title="High non-performance exit rate",
                detail=f"{non_perf_rate:.0%} of trades exited via non-performance review.",
                confidence="high",
                recommendation=(
                    "Entry criteria may be too loose, or the non-performance "
                    "window may be too short. Review CAN SLIM thresholds."
                ),
            ))

        # Profit target analysis (moderate tier)
        mod_wins = [
            t for t in closed if t.tier == "moderate"
            and t.gain_pct is not None and t.gain_pct > 0
        ]
        if len(mod_wins) >= 5:
            avg_gain = mean([t.gain_pct for t in mod_wins])
            target = self.config.moderate_tier.profit_target
            if avg_gain < target * 0.7:
                recommendations.append(Finding(
                    category="config",
                    title="Moderate tier rarely reaching full target",
                    detail=f"Avg winning gain {avg_gain:.1%} vs target {target:.1%}.",
                    confidence="medium",
                    recommendation=(
                        f"Consider lowering profit target from {target:.0%} "
                        f"to {avg_gain * 1.1:.0%} to capture more gains."
                    ),
                ))

    # ----- Summary -----

    def _build_summary(
        self,
        benchmark: BenchmarkComparison,
        dq: DecisionQuality,
        tier_analysis: dict[str, TierAnalysis],
        findings: list[Finding],
    ) -> str:
        lines = []

        if benchmark.alpha is not None:
            direction = "outperforming" if benchmark.alpha > 0 else "underperforming"
            lines.append(
                f"Portfolio is {direction} {benchmark.benchmark_symbol} "
                f"by {abs(benchmark.alpha):.1%}."
            )

        if dq.total_trades > 0:
            lines.append(
                f"{dq.total_trades} completed trades. "
                f"Overall win rate: high-conf {dq.high_confidence_win_rate:.0%}, "
                f"low-conf {dq.low_confidence_win_rate:.0%}."
            )

        for name, ta in tier_analysis.items():
            if ta.performance.trades > 0:
                lines.append(
                    f"{name.title()} tier: {ta.performance.trades} trades, "
                    f"{ta.performance.win_rate:.0%} win rate, "
                    f"{ta.performance.avg_gain_pct:.1%} avg gain."
                )

        high_findings = [f for f in findings if f.confidence == "high"]
        if high_findings:
            lines.append(f"{len(high_findings)} high-confidence finding(s) require attention.")

        return " ".join(lines) if lines else "Insufficient data for audit summary."
