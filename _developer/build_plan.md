# Monaimetrics — Build Plan
## Ralph Wiggum Rules: one thing at a time, keep it simple, don't be clever

---

## Project Structure

```
monaimetrics/
├── _developer/              # specs, plans, notes (not shipped)
├── monaimetrics/            # package root
│   ├── __init__.py
│   ├── config.py            # all tunable numbers, zero logic
│   ├── calculators.py       # pure math, no side effects
│   ├── data_input.py        # external world → standardised scores
│   ├── strategy.py          # the only module with opinions
│   ├── portfolio_manager.py # orchestrator — when + how, never what
│   ├── trading_interface.py # thin broker adapter (Alpaca)
│   ├── reporting.py         # records everything, interprets nothing
│   └── audit_qa.py          # the system watching itself
├── tests/
│   ├── test_config.py
│   ├── test_calculators.py
│   ├── test_strategy.py
│   └── ...
├── pyproject.toml
└── README.md
```

---

## Build Phases

### Phase 1: Foundation (config + calculators)
The two modules with zero external dependencies. Everything else builds on these.

**config.py**
- Dataclass-based configuration (frozen where possible, explicit types)
- Risk tolerance profiles: Conservative / Moderate / Aggressive — each a named preset
- All 7 framework parameters from the capabilities spec (cycle, stage, CAN SLIM, Greenblatt, event cascade, asymmetry, Kelly)
- Tier allocation tables (cycle-score → moderate/high/cash splits)
- Stop-loss, trailing stop, profit target defaults per tier
- Non-performance review windows per tier
- Circuit breaker thresholds
- Notification priority definitions
- Validation on load — reject invalid combinations early

**calculators.py**
- Composite scoring: weighted average of 0–100 scores, configurable weights
- Kelly position sizing: fractional Kelly with conviction multiplier and tier caps
- Stop-loss price: fixed percentage and ATR-based methods
- Trailing stop update: milestone ratcheting logic (only moves up, never down)
- Profit target with volatility adjustment (base + 0.5 × ATR%)
- Portfolio drift calculation: current vs target, flag at threshold
- Rebalance amounts: what to buy/sell to restore targets
- Asymmetry score: (upside × prob) / (downside × prob)
- Stage classification helper: MA slope + volume pattern → stage 1/2/3/4
- Score normalisation: clamp to 0–100, handle nulls

Each function: numbers in, numbers out. Testable with simple assertions.

**Tests**: Unit tests for every calculator function with known inputs/outputs.

---

### Phase 2: Data Layer (data_input)
Bring the outside world in, clean it up, hand it off as standardised scores.

**data_input.py**
- Market data adapter (Alpaca): prices, volume, historical bars → technical scores
- Fundamental data adapter (Financial Datasets API): revenue growth, margins, valuation ratios → fundamental scores
- Portfolio state adapter (Alpaca): current holdings, cost basis, P&L — factual, not scored
- Benchmark data adapter: index/ETF prices for configured benchmarks
- Source health monitoring: flag stale or errored sources, don't pass bad data downstream
- Timestamp every score for staleness checks
- Stub/mock interfaces for sentiment and macro (not building those pipelines yet)

**Key decisions**:
- Each data source gets its own function returning a common score dict structure
- All API calls isolated here — rest of system never touches an external API
- Rate limiting and caching handled at this layer

**Tests**: Mock API responses, verify score structures and normalisation.

---

### Phase 3: Strategy Engine
Where the 7 frameworks live. The only module that has opinions.

**strategy.py**
- **Framework 1 — Cycle Positioning**: score 4 dimensions (−2 to +2), composite → portfolio posture
- **Framework 2 — Stage Analysis**: classify stock stage via 150-day MA + volume, hard gate on entry
- **Framework 3 — CAN SLIM scoring**: 7-factor composite, weighted per config
- **Framework 4 — Greenblatt Magic Formula**: ROC + earnings yield combined rank
- **Framework 5 — Event Cascade**: 5-phase timing (event → news → analysis → consensus → second-order)
- **Framework 6 — Asymmetry Recognition**: calculate asymmetry score, flag fat pitches
- **Framework 7 — Kelly Sizing**: size position from edge estimate + volatility

- **Signal generation pipeline**: run frameworks in sequence, apply gates, produce BUY/SELL/HOLD/WATCH/REDUCE/INCREASE signals
- **Position review**: for each holding — stop check, trail check, hold audit, non-performance review
- **Opportunity scan**: for universe/watchlist — score, gate, size candidates
- **Conflict resolution**: any framework can trigger sell (most conservative wins), buy needs 2+ agreement, Stage 4 overrides everything
- **Plan assembly**: prioritise actions (emergency sells → stop sells → rebalances → buys), attach reasoning

**Tests**: Scenario-based tests. "Given these scores and this portfolio state, strategy should recommend X."

---

### Phase 4: Trading Interface
Deliberately thin and boring. Easy to swap brokers.

**trading_interface.py**
- Order execution: buy/sell with market/limit/stop order types via Alpaca API
- Broker-side stop placement (persistent stops that survive system downtime)
- Safety checks before execution: position size cap, market hours check, price slippage check
- Order status tracking and partial fill handling
- Dry-run mode: log what would execute without placing orders (config flag)
- Return structured results: filled/partial/rejected with details

**Tests**: Mock Alpaca API, verify safety checks fire correctly.

---

### Phase 5: Portfolio Manager (Orchestrator)
Short and boring. Coordinates, never decides.

**portfolio_manager.py**
- **Scheduled assessment cycle**: refresh data → ask strategy → execute plan → log everything
- **Continuous monitoring loop**: price checks → stop-loss checks → emergency actions
- **Event-driven triggers**: major score changes → off-cycle assessment
- **Rebalancing**: drift detection, post-harvest checks, cycle-change adjustments
- **Circuit breakers**: max drawdown pause, rapid loss pause, structural divergence detection, API/data failure handling
- **Human override handling**: accept manual instructions, log as override not recommendation
- **Audit trigger**: on config schedule, kick off audit_qa cycle

**Tests**: Integration tests with mocked strategy + trading interface.

---

### Phase 6: Reporting
The system's memory. Write-heavy, captures everything.

**reporting.py**
- Decision log: every strategy recommendation with scores and reasoning
- Execution log: every order sent, fill price, slippage
- Portfolio snapshots: periodic full state capture
- Performance metrics: returns by period, benchmark comparison, tier attribution
- Alert generation: drawdown warnings, data source failures, circuit breaker activations
- Export formats: start with structured logs/JSON, dashboard later

**Tests**: Verify logs capture all required fields, alert thresholds fire correctly.

---

### Phase 7: Audit & QA
The slow loop. Runs weekly/monthly, looks at patterns.

**audit_qa.py**
- Benchmark comparison: portfolio returns vs configured benchmarks, alpha calculation
- Decision quality analysis: entry scores vs outcomes, stop-loss appropriateness
- Score effectiveness: per-dimension correlation with actual outcomes
- Pattern detection: recurring failure modes, sector/condition performance clusters
- Config recommendations: specific parameter change suggestions with evidence and confidence
- Risk regime assessment: does current config match current market environment?
- Output: structured findings report, prioritised recommendations, summary narrative

**Tests**: Feed known historical data, verify analysis outputs are sensible.

---

## Build Order Rationale

```
Phase 1: config + calculators     ← zero dependencies, testable immediately
Phase 2: data_input               ← needs config + calculators, brings real data in
Phase 3: strategy                 ← needs all of above, this is the brain
Phase 4: trading_interface        ← needs config only, but build after strategy so we have signals to execute
Phase 5: portfolio_manager        ← wires everything together, build last of the "fast loop"
Phase 6: reporting                ← can be built alongside phases 4-5, but formalised here
Phase 7: audit_qa                 ← the "slow loop", needs accumulated data from reporting
```

Each phase produces a working, testable module before moving on. No phase depends on a later phase. We can run the system in dry-run mode from Phase 5 onward.

---

## Things We're NOT Building Yet

These feed INTO data_input as external services — separate projects:
- NLP / sentiment analysis pipeline
- News aggregation and monitoring
- Event classification engine (scope, severity, duration)
- Entity resolution graph (company → supplier → country mapping)
- Web dashboard (reporting starts as structured logs)

We stub these with mock data so the core system is testable end-to-end.

---

## Key Conventions

- **Types over comments**: dataclasses and type hints so the code documents itself
- **Clean code**: readable, minimal comments, PEP 8 (per CLAUDE.md)
- **Config is the single source of truth**: no magic numbers anywhere else
- **Calculators are pure**: numbers in, numbers out, unit-testable in isolation
- **Strategy decides, portfolio_manager coordinates, trading_interface executes**: clear separation
- **Every decision logged**: if it happened and wasn't logged, it didn't happen
- **Dry-run first**: system runs in dry-run mode until explicitly switched to live
- **Secrets in env vars**: API keys (Alpaca, data providers) never in code or config files
- **Tests at root**: all tests live in `/tests/`, not inside the package
- **Fix completely then move on**: finish each phase's tests passing before starting the next

---

## Progress Tracker

One phase at a time. Don't start the next until the current one is done and tested.

| Phase | Module | Status | Tests | Notes |
|-------|--------|--------|-------|-------|
| 1a | config.py | DONE | 18/18 passing | All frameworks, tiers, profiles, allocation tables |
| 1b | calculators.py | DONE | 48/48 passing | All pure math functions, zero external deps |
| 2 | data_input.py | DONE | 9/9 passing (integration) | Alpaca market data via IEX feed |
| 3 | strategy.py | DONE | 36/36 passing | Frameworks, sell-side, buy-side, plan gen |
| 4 | trading_interface.py | DONE | 15/15 passing (5 live) | Dry-run, safety checks, live orders |
| 5 | portfolio_manager.py | DONE | 23/23 passing (3 live) | Orchestrator, circuit breakers, halt |
| 6 | reporting.py | DONE | 21/21 passing | Trades, snapshots, alerts, perf, JSON export |
| 7 | audit_qa.py | DONE | 30/30 passing | Benchmark, decisions, stops, tiers, findings, summary |

Status values: NOT STARTED → IN PROGRESS → TESTS PASSING → DONE

---

## Issues & Decisions Log

Track problems, decisions, and things we tried so we don't repeat ourselves.

| # | Date | Phase | Issue / Decision | Resolution | Status |
|---|------|-------|-----------------|------------|--------|
| 1 | 2026-02-19 | Setup | Python version + dependencies to confirm before Phase 1 | Python 3.14, venv with pytest | CLOSED |
| 2 | 2026-02-19 | Setup | Alpaca API: paper trading vs live — confirm account type | Paper trading, IEX feed (free tier) | CLOSED |
| 3 | — | 2 | Financial Datasets API: confirm provider and endpoints | — | OPEN |
| 4 | — | 2 | Sentiment/macro data sources: stub only for now | Decided: mock interfaces, build real adapters later | DECIDED |
| 5 | — | General | Entity resolution graph: out of scope for core system | Decided: external service, stubbed in data_input | DECIDED |
| 6 | 2026-02-19 | 2 | BarSet.__contains__ returns False even when key exists | Use barset.data for key checks | CLOSED |
| 7 | 2026-02-19 | 2 | Free Alpaca plan blocks SIP data feed | Switched to IEX feed (DataFeed.IEX) | CLOSED |
| 8 | 2026-02-19 | 2 | alpaca-py missing pytz dependency on Python 3.14 | pip install pytz | CLOSED |
