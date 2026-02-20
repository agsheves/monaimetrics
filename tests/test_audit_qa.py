"""
Tests for audit_qa. All unit tests, no API needed.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from monaimetrics.config import (
    SignalType, SignalUrgency, Tier, load_config, NotificationPriority,
)
from monaimetrics.data_input import AccountInfo
from monaimetrics.strategy import ManagedPosition, Signal
from monaimetrics.trading_interface import OrderResult
from monaimetrics.reporting import (
    Reporter, TradeRecord, PortfolioSnapshot, TierPerformance,
)
from monaimetrics.audit_qa import (
    Auditor, AuditReport, Finding, BenchmarkComparison,
    DecisionQuality, StopAnalysis, TierAnalysis,
)


NOW = datetime.now(timezone.utc)
CFG = load_config()


def make_signal(
    symbol="AAPL",
    action=SignalType.SELL,
    tier=Tier.MODERATE,
    confidence=80,
    reasons=None,
) -> Signal:
    return Signal(
        symbol=symbol, action=action,
        urgency=SignalUrgency.STANDARD, tier=tier,
        confidence=confidence,
        reasons=reasons or ["Test reason"],
    )


def make_order_result(
    symbol="AAPL",
    side="sell",
    qty=10,
    filled_price=155.0,
    status="filled",
) -> OrderResult:
    return OrderResult(
        order_id="test-123", symbol=symbol, side=side,
        qty=qty, status=status, filled_qty=qty,
        filled_avg_price=filled_price,
    )


def make_reporter_with_trades(
    wins=3, losses=2,
    win_confidence=85, loss_confidence=60,
    win_gain=0.15, loss_gain=-0.05,
    tier=Tier.MODERATE,
    reasons=None,
) -> Reporter:
    r = Reporter()
    for i in range(wins):
        r.record_trade(
            make_signal(symbol=f"W{i}", confidence=win_confidence, tier=tier, reasons=reasons),
            make_order_result(symbol=f"W{i}"),
            exit_gain_pct=win_gain,
        )
    for i in range(losses):
        r.record_trade(
            make_signal(symbol=f"L{i}", confidence=loss_confidence, tier=tier, reasons=reasons),
            make_order_result(symbol=f"L{i}"),
            exit_gain_pct=loss_gain,
        )
    return r


def make_account(pv=100000, cash=30000) -> AccountInfo:
    return AccountInfo(
        cash=cash, portfolio_value=pv,
        buying_power=cash * 2, status="active",
    )


# ---------------------------------------------------------------------------
# Benchmark Analysis
# ---------------------------------------------------------------------------

class TestAnalyzeBenchmark:
    def test_no_snapshots(self):
        r = Reporter()
        auditor = Auditor(r, CFG)
        bm = auditor._analyze_benchmark(30, "SPY")
        assert bm.portfolio_return == 0.0
        assert bm.benchmark_symbol == "SPY"

    def test_portfolio_return_from_snapshots(self):
        r = Reporter()
        r.snapshots.append(PortfolioSnapshot(
            timestamp=NOW.isoformat(), portfolio_value=100000,
            cash=30000, positions=[], tier_values={}, allocation_pcts={},
        ))
        r.snapshots.append(PortfolioSnapshot(
            timestamp=NOW.isoformat(), portfolio_value=110000,
            cash=30000, positions=[], tier_values={}, allocation_pcts={},
        ))
        auditor = Auditor(r, CFG)
        bm = auditor._analyze_benchmark(30, "SPY")
        assert bm.portfolio_return == pytest.approx(0.10)

    def test_benchmark_unavailable(self):
        r = Reporter()
        auditor = Auditor(r, CFG)
        bm = auditor._analyze_benchmark(30, "INVALID_SYMBOL_XYZ")
        assert bm.benchmark_return is None
        assert bm.alpha is None
        assert bm.outperformed is None

    def test_alpha_calculation(self):
        r = Reporter()
        r.snapshots.append(PortfolioSnapshot(
            timestamp=NOW.isoformat(), portfolio_value=100000,
            cash=0, positions=[], tier_values={}, allocation_pcts={},
        ))
        r.snapshots.append(PortfolioSnapshot(
            timestamp=NOW.isoformat(), portfolio_value=115000,
            cash=0, positions=[], tier_values={}, allocation_pcts={},
        ))
        auditor = Auditor(r, CFG)
        # Mock benchmark to return known value
        with patch.object(auditor, '_analyze_benchmark') as mock:
            mock.return_value = BenchmarkComparison(
                portfolio_return=0.15, benchmark_return=0.10,
                benchmark_symbol="SPY", alpha=0.05, outperformed=True,
            )
            bm = auditor._analyze_benchmark(30, "SPY")
            assert bm.alpha == pytest.approx(0.05)
            assert bm.outperformed is True


# ---------------------------------------------------------------------------
# Decision Quality
# ---------------------------------------------------------------------------

class TestAnalyzeDecisions:
    def test_no_trades(self):
        r = Reporter()
        auditor = Auditor(r, CFG)
        dq = auditor._analyze_decisions(30)
        assert dq.total_trades == 0
        assert dq.confidence_predictive is False

    def test_confidence_predictive(self):
        r = make_reporter_with_trades(
            wins=5, losses=3,
            win_confidence=85, loss_confidence=60,
        )
        auditor = Auditor(r, CFG)
        dq = auditor._analyze_decisions(30)
        assert dq.total_trades == 8
        assert dq.avg_confidence_winners == pytest.approx(85)
        assert dq.avg_confidence_losers == pytest.approx(60)
        assert dq.confidence_predictive is True

    def test_confidence_not_predictive(self):
        r = make_reporter_with_trades(
            wins=3, losses=5,
            win_confidence=50, loss_confidence=80,
        )
        auditor = Auditor(r, CFG)
        dq = auditor._analyze_decisions(30)
        assert dq.confidence_predictive is False

    def test_high_vs_low_confidence_win_rates(self):
        r = Reporter()
        # High confidence winners
        for i in range(3):
            r.record_trade(
                make_signal(symbol=f"HW{i}", confidence=80),
                make_order_result(symbol=f"HW{i}"),
                exit_gain_pct=0.10,
            )
        # High confidence loser
        r.record_trade(
            make_signal(symbol="HL0", confidence=75),
            make_order_result(symbol="HL0"),
            exit_gain_pct=-0.05,
        )
        # Low confidence winner
        r.record_trade(
            make_signal(symbol="LW0", confidence=50),
            make_order_result(symbol="LW0"),
            exit_gain_pct=0.08,
        )
        # Low confidence loser
        r.record_trade(
            make_signal(symbol="LL0", confidence=40),
            make_order_result(symbol="LL0"),
            exit_gain_pct=-0.03,
        )

        auditor = Auditor(r, CFG)
        dq = auditor._analyze_decisions(30)
        assert dq.high_confidence_win_rate == pytest.approx(3 / 4)
        assert dq.low_confidence_win_rate == pytest.approx(1 / 2)


# ---------------------------------------------------------------------------
# Stop Analysis
# ---------------------------------------------------------------------------

class TestAnalyzeStops:
    def test_no_stops(self):
        r = make_reporter_with_trades(wins=3, losses=2)
        auditor = Auditor(r, CFG)
        sa = auditor._analyze_stops(30)
        assert sa.total_stops == 0
        assert "No stop-loss" in sa.suggestion

    def test_with_stops(self):
        r = Reporter()
        for i in range(4):
            r.record_trade(
                make_signal(symbol=f"S{i}", reasons=["Stop-loss hit"]),
                make_order_result(symbol=f"S{i}"),
                exit_gain_pct=-0.06,
            )
        auditor = Auditor(r, CFG)
        sa = auditor._analyze_stops(30)
        assert sa.total_stops == 4
        assert sa.avg_stop_loss_pct == pytest.approx(-0.06)

    def test_tight_stops_detected(self):
        r = Reporter()
        # Stops with small losses (under 3%) — tight stops
        for i in range(4):
            r.record_trade(
                make_signal(symbol=f"T{i}", reasons=["Stop triggered"]),
                make_order_result(symbol=f"T{i}"),
                exit_gain_pct=-0.02,
            )
        # One deeper loss
        r.record_trade(
            make_signal(symbol="D0", reasons=["Stop triggered"]),
            make_order_result(symbol="D0"),
            exit_gain_pct=-0.08,
        )
        auditor = Auditor(r, CFG)
        sa = auditor._analyze_stops(30)
        assert sa.total_stops == 5
        assert sa.recovery_rate == pytest.approx(4 / 5)
        assert "widening" in sa.suggestion.lower() or "ATR" in sa.suggestion

    def test_appropriate_stops(self):
        r = Reporter()
        # All stops with significant losses
        for i in range(5):
            r.record_trade(
                make_signal(symbol=f"S{i}", reasons=["Stop hit"]),
                make_order_result(symbol=f"S{i}"),
                exit_gain_pct=-0.08,
            )
        auditor = Auditor(r, CFG)
        sa = auditor._analyze_stops(30)
        assert sa.recovery_rate == 0.0
        assert "appropriate" in sa.suggestion.lower()


# ---------------------------------------------------------------------------
# Tier Analysis
# ---------------------------------------------------------------------------

class TestAnalyzeTiers:
    def test_empty_tiers(self):
        r = Reporter()
        auditor = Auditor(r, CFG)
        ta = auditor._analyze_tiers(30)
        for name, analysis in ta.items():
            assert analysis.performance.trades == 0
            assert "No completed trades" in analysis.notes[0]

    def test_moderate_meets_target(self):
        r = make_reporter_with_trades(
            wins=7, losses=3, tier=Tier.MODERATE,
        )
        auditor = Auditor(r, CFG)
        ta = auditor._analyze_tiers(30)
        assert ta["moderate"].meets_target_win_rate is True
        assert ta["moderate"].performance.win_rate == pytest.approx(0.70)

    def test_moderate_below_target(self):
        r = make_reporter_with_trades(
            wins=3, losses=7, tier=Tier.MODERATE,
        )
        auditor = Auditor(r, CFG)
        ta = auditor._analyze_tiers(30)
        assert ta["moderate"].meets_target_win_rate is False
        assert len(ta["moderate"].notes) > 0


# ---------------------------------------------------------------------------
# Finding Generators
# ---------------------------------------------------------------------------

class TestBenchmarkFindings:
    def test_outperforming(self):
        auditor = Auditor(Reporter(), CFG)
        findings = []
        bm = BenchmarkComparison(
            portfolio_return=0.15, benchmark_return=0.10,
            benchmark_symbol="SPY", alpha=0.05, outperformed=True,
        )
        auditor._generate_benchmark_findings(bm, findings)
        assert len(findings) == 1
        assert "Outperforming" in findings[0].title

    def test_underperforming(self):
        auditor = Auditor(Reporter(), CFG)
        findings = []
        bm = BenchmarkComparison(
            portfolio_return=0.05, benchmark_return=0.10,
            benchmark_symbol="SPY", alpha=-0.05, outperformed=False,
        )
        auditor._generate_benchmark_findings(bm, findings)
        assert len(findings) == 1
        assert "Underperforming" in findings[0].title

    def test_no_benchmark_data(self):
        auditor = Auditor(Reporter(), CFG)
        findings = []
        bm = BenchmarkComparison(
            portfolio_return=0.10, benchmark_return=None,
            benchmark_symbol="SPY", alpha=None, outperformed=None,
        )
        auditor._generate_benchmark_findings(bm, findings)
        assert len(findings) == 0


class TestDecisionFindings:
    def test_insufficient_data(self):
        auditor = Auditor(Reporter(), CFG)
        findings, recs = [], []
        dq = DecisionQuality(
            total_trades=3, avg_confidence_winners=0,
            avg_confidence_losers=0, confidence_predictive=False,
            high_confidence_win_rate=0, low_confidence_win_rate=0,
        )
        auditor._generate_decision_findings(dq, findings, recs)
        assert len(findings) == 1
        assert "Insufficient" in findings[0].title

    def test_not_predictive_generates_recommendation(self):
        auditor = Auditor(Reporter(), CFG)
        findings, recs = [], []
        dq = DecisionQuality(
            total_trades=10, avg_confidence_winners=60,
            avg_confidence_losers=70, confidence_predictive=False,
            high_confidence_win_rate=0.40, low_confidence_win_rate=0.50,
        )
        auditor._generate_decision_findings(dq, findings, recs)
        assert any("not predictive" in f.title.lower() for f in findings)
        assert any("scoring" in r.category for r in recs)

    def test_high_conf_underperforming(self):
        auditor = Auditor(Reporter(), CFG)
        findings, recs = [], []
        dq = DecisionQuality(
            total_trades=20, avg_confidence_winners=80,
            avg_confidence_losers=70, confidence_predictive=True,
            high_confidence_win_rate=0.30, low_confidence_win_rate=0.60,
        )
        auditor._generate_decision_findings(dq, findings, recs)
        assert any("underperforming" in r.title.lower() for r in recs)


class TestStopFindings:
    def test_no_stops(self):
        auditor = Auditor(Reporter(), CFG)
        findings, recs = [], []
        sa = StopAnalysis(
            total_stops=0, stops_that_recovered=0,
            recovery_rate=0, avg_stop_loss_pct=0,
            suggestion="No stops.",
        )
        auditor._generate_stop_findings(sa, findings, recs)
        assert len(findings) == 0

    def test_tight_stops_recommendation(self):
        auditor = Auditor(Reporter(), CFG)
        findings, recs = [], []
        sa = StopAnalysis(
            total_stops=5, stops_that_recovered=4,
            recovery_rate=0.80, avg_stop_loss_pct=-0.02,
            suggestion="Consider widening.",
        )
        auditor._generate_stop_findings(sa, findings, recs)
        assert len(findings) == 1
        assert len(recs) == 1
        assert "widening" in recs[0].title.lower()


class TestTierFindings:
    def test_below_target_generates_recommendation(self):
        auditor = Auditor(Reporter(), CFG)
        findings, recs = [], []
        ta = {
            "moderate": TierAnalysis(
                tier="moderate",
                performance=TierPerformance(
                    tier="moderate", trades=12, wins=4,
                    win_rate=0.33, avg_gain_pct=-0.02, total_return_pct=-0.24,
                ),
                meets_target_win_rate=False,
                meets_target_reward_risk=True,
                notes=["Win rate 33% below target 55%"],
            ),
        }
        auditor._generate_tier_findings(ta, findings, recs)
        assert any("tier" in r.category for r in recs)
        assert any("Improve" in r.title for r in recs)


class TestConfigRecommendations:
    def test_too_few_trades(self):
        r = make_reporter_with_trades(wins=3, losses=2)
        auditor = Auditor(r, CFG)
        recs = []
        auditor._generate_config_recommendations(30, recs)
        assert len(recs) == 0

    def test_high_non_performance_rate(self):
        r = Reporter()
        for i in range(8):
            r.record_trade(
                make_signal(symbol=f"NP{i}", reasons=["Non-performance review"]),
                make_order_result(symbol=f"NP{i}"),
                exit_gain_pct=-0.03,
            )
        for i in range(4):
            r.record_trade(
                make_signal(symbol=f"G{i}", reasons=["Profit target"]),
                make_order_result(symbol=f"G{i}"),
                exit_gain_pct=0.15,
            )
        auditor = Auditor(r, CFG)
        recs = []
        auditor._generate_config_recommendations(30, recs)
        assert any("non-performance" in r.title.lower() for r in recs)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestBuildSummary:
    def test_with_data(self):
        r = make_reporter_with_trades(wins=5, losses=3)
        auditor = Auditor(r, CFG)
        bm = BenchmarkComparison(
            portfolio_return=0.12, benchmark_return=0.08,
            benchmark_symbol="SPY", alpha=0.04, outperformed=True,
        )
        dq = auditor._analyze_decisions(30)
        ta = auditor._analyze_tiers(30)
        findings = [Finding("test", "Test", "Detail", "high")]
        summary = auditor._build_summary(bm, dq, ta, findings)
        assert "outperforming" in summary.lower()
        assert "trades" in summary.lower()
        assert "require attention" in summary.lower()

    def test_insufficient_data(self):
        r = Reporter()
        auditor = Auditor(r, CFG)
        bm = BenchmarkComparison(
            portfolio_return=0, benchmark_return=None,
            benchmark_symbol="SPY", alpha=None, outperformed=None,
        )
        dq = DecisionQuality(0, 0, 0, False, 0, 0)
        summary = auditor._build_summary(bm, dq, {}, [])
        assert "Insufficient" in summary


# ---------------------------------------------------------------------------
# Full Audit
# ---------------------------------------------------------------------------

class TestRunAudit:
    def test_full_audit_empty(self):
        r = Reporter()
        auditor = Auditor(r, CFG)
        report = auditor.run_audit(period_days=30)
        assert isinstance(report, AuditReport)
        assert report.period_days == 30
        assert report.generated_at is not None
        assert isinstance(report.findings, list)
        assert isinstance(report.recommendations, list)

    def test_full_audit_with_data(self):
        r = make_reporter_with_trades(wins=6, losses=4)
        r.snapshots.append(PortfolioSnapshot(
            timestamp=NOW.isoformat(), portfolio_value=100000,
            cash=30000, positions=[], tier_values={}, allocation_pcts={},
        ))
        r.snapshots.append(PortfolioSnapshot(
            timestamp=NOW.isoformat(), portfolio_value=108000,
            cash=30000, positions=[], tier_values={}, allocation_pcts={},
        ))
        auditor = Auditor(r, CFG)
        report = auditor.run_audit(period_days=30)
        assert report.decision_quality.total_trades == 10
        assert report.stop_analysis is not None
        assert len(report.summary) > 0
