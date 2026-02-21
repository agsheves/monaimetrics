# Active Trading System — Framework Outline
## Version 0.2 — Structural Blueprint (No Code)

---

## System Structure

```
trading_system/
├── config.py
├── calculators.py
├── data_input.py
├── strategy.py
├── portfolio_manager.py
├── trading_interface.py
├── reporting.py
└── audit_qa.py
```

---

## 1. config.py

### What it does
Single file containing every tunable number in the system. Weights, thresholds,
allocation targets, risk limits, scheduling intervals. Nothing else in the system
contains magic numbers — everything references config.

### Contains
- Score weights (how much to weight fundamental vs technical vs sentiment vs macro)
- Thresholds (what composite score triggers a buy, a sell, a watch)
- Position limits (max single position as % of portfolio, max sector exposure)
- Risk parameters (stop-loss %, trailing stop gap, Kelly fraction)
- Allocation targets (% in low/moderate/high risk tiers, cash reserve floor)
- Scheduling (how often to run full assessment, how often to check stop-losses)
- Strategy profile presets (e.g. "aggressive" vs "defensive" as named bundles of the above)
- Benchmark definitions (which indices/ETFs to compare performance against)
- Audit schedule (how often audit_qa runs its analysis cycle)

### Dependencies
- None. This is a leaf node. Everything else reads from config, nothing writes to it
  programmatically (changes are manual and logged).

### Key principle
If you want to change how the system behaves, you open this file and only this file.

---

## 2. calculators.py

### What it does
A library of pure mathematical functions. No API calls, no state, no side effects.
You give it numbers, it returns numbers. Every function can be tested in isolation
with a simple "input X, expect Y" unit test.

### Contains
Functions for:
- **Composite scoring**: Combine multiple 0-100 scores using configurable weights
  into a single composite score. Supports both weighted-average and multiplicative
  (gate) modes.
- **Position sizing**: Given a composite score, portfolio value, and risk parameters
  from config, calculate how many shares/how much capital to allocate. Implements
  fractional Kelly.
- **Stop-loss calculation**: Given an entry price and config parameters, return the
  stop-loss price. Supports fixed percentage and ATR-based methods.
- **Trailing stop update**: Given current price and existing trailing stop level,
  return the new trailing stop (only moves up, never down).
- **Portfolio drift**: Given current allocations and target allocations from config,
  calculate how far each tier has drifted and whether it exceeds the rebalance
  threshold.
- **Rebalance amounts**: Given current positions, target allocations, and portfolio
  value, calculate what needs to be bought/sold to restore targets.
- **Risk-adjusted return**: Simple Sharpe-style calculations for performance tracking.
- **Score normalisation**: Ensure scores from different sources are on the same 0-100
  scale. Handles edge cases (nulls, out-of-range values).

### Dependencies
- config.py (reads weights, thresholds, risk parameters)

### Key principle
Every function is: numbers in, numbers out. If you can't describe what a function
does without mentioning an API, a ticker symbol, or a database, it doesn't belong
here.

---

## 3. data_input.py

### What it does
The adapter layer that brings all external information into the system in a
standardised format. Each data source has its own function, but they all return
the same structure: a dictionary of scores (0-100) keyed by category.

This module is where messy real-world data gets cleaned up into the simple numbers
that the rest of the system works with.

### Contains
Functions/connectors for:
- **Market data** (from Alpaca): Current prices, volume, historical bars. Translated
  into technical scores by calling calculators where needed.
- **Fundamental data** (from Financial Datasets API or similar): Revenue growth,
  margins, valuation ratios. Translated into fundamental scores.
- **News/sentiment scores** (from your external NLP/sentiment pipeline): These arrive
  as quantitative values already. This module just receives and standardises them.
- **Macro/geopolitical scores** (from Decis Country Info API or similar): Country
  stability ratings, directional assessments. Translated into macro scores.
- **Current portfolio state** (from Alpaca): What do we hold, at what cost basis,
  current P&L. This is factual data, not scored.
- **Benchmark data** (from Alpaca or other market data): Index/ETF prices for the
  benchmarks defined in config. Used by reporting and audit_qa for comparison.

### Also handles
- Source health monitoring: if a source is down or returning errors, flag it rather
  than passing bad data downstream.
- Staleness tracking: every score has a timestamp. The strategy module can decide
  whether a score is fresh enough to act on.

### Dependencies
- config.py (API endpoints, source configuration, refresh intervals)
- calculators.py (for translating raw data into normalised scores where needed)
- External APIs: Alpaca, Financial Datasets, your sentiment pipeline, Decis

### Key principle
The rest of the system never touches an external API directly. If you add a new data
source tomorrow, you add a function here and nothing else changes.

---

## 4. strategy.py

### What it does
The only module that has opinions about individual trades. It takes the current state
of the world (scores from data_input, current portfolio from data_input) and produces
a plan: a list of recommended actions with reasoning.

It assesses BOTH existing positions (should I hold, reduce, or exit?) AND potential
new positions (what should I buy, and how much?).

It does NOT execute anything. It returns a plan that the portfolio manager can act on.

### Contains
- **Position review**: For each current holding, check:
  - Has the stop-loss been breached? → recommend SELL (emergency)
  - Has the trailing stop been breached? → recommend SELL
  - Does it still pass the hold criteria? (the "would I buy this today?" test)
    → recommend HOLD or SELL
  - Has the score improved significantly? → recommend INCREASE
  - Has a take-profit target been hit? → recommend REDUCE or SELL
  (All the actual calculations are calls to calculators.py)

- **Opportunity scan**: For watchlist/universe stocks not currently held, check:
  - Does the composite score exceed the buy threshold? → candidate
  - Does adding this position breach any concentration limits? → check via calculators
  - What size should the position be? → call calculators for Kelly sizing
  - → recommend BUY with size, or WATCH if close but not there yet

- **Portfolio-level assessment**: Looking at the whole picture:
  - Is the portfolio drifting from tier allocation targets? → recommend rebalance
  - Is overall risk exposure within bounds? → flag if not
  - Are there correlation concerns? (multiple positions exposed to same risk)

- **Plan assembly**: Collect all recommendations, prioritise (emergency sells first,
  then stop-loss sells, then rebalances, then new buys), attach reasoning to each,
  and return the complete plan.

### Dependencies
- config.py (thresholds, allocation targets, strategy parameters)
- calculators.py (all the math — scoring, sizing, stop-loss checks, drift)
- data_input.py (current scores, current portfolio state)

### Does NOT depend on
- trading_interface.py (strategy never executes)
- reporting.py (strategy doesn't log — the portfolio manager logs the plan)
- audit_qa.py (strategy doesn't know it's being watched)

### Key principle
Strategy is where the theoretical frameworks live. When you add Cycle Positioning
or Event Velocity later, they become new assessment steps in this module that call
new functions in calculators. The structure doesn't change.

---

## 5. portfolio_manager.py

### What it does
The orchestrator. It owns the "when" and "how" but never the "what." It runs on a
schedule (or responds to triggers), coordinates the other modules, and ensures
everything happens in the right order.

Think of it as a very short script that says: get data, ask strategy what to do,
do it, record what happened.

### Contains
- **Scheduled run cycle**:
  1. Call data_input to refresh all scores and portfolio state
  2. Call strategy to assess positions and opportunities → receive plan
  3. Review plan (optional: flag anything unusual for human review)
  4. Send execution actions to trading_interface
  5. Send everything to reporting (the plan, the reasoning, the execution results)

- **Continuous monitoring loop** (runs more frequently than full assessment):
  1. Call data_input for latest prices only
  2. Call calculators to check stop-losses against current prices
  3. If any breach → call strategy for emergency assessment → execute immediately
  4. Log to reporting

- **Event-driven triggers**:
  - If data_input signals a major score change (e.g. macro score drops sharply),
    trigger an off-cycle strategy assessment
  - If trading_interface reports a failed order, handle retry or escalation

- **Human override handling**:
  - Accept manual instructions (e.g. "sell all AAPL regardless of strategy")
  - Log that it was a manual override, not a strategy recommendation

- **Audit cycle trigger**:
  - On the schedule defined in config (e.g. monthly), trigger audit_qa to run
    its analysis and route the findings to reporting/dashboard

### Dependencies
- config.py (scheduling intervals, trigger thresholds)
- data_input.py (calls to refresh data)
- strategy.py (calls to get recommendations)
- trading_interface.py (calls to execute)
- reporting.py (calls to log everything)
- audit_qa.py (triggers periodic analysis runs)

### Key principle
If you read portfolio_manager and see an if-statement about whether a stock is a
good buy, something has gone wrong. This module coordinates. It does not decide.

---

## 6. trading_interface.py

### What it does
Thin adapter to the Alpaca API (or any future broker). Receives specific instructions
from the portfolio manager ("buy 50 shares of AAPL at market") and executes them.
Also provides safety checks as a last line of defence.

### Contains
- **Order execution**: Buy, sell, with support for order types (market, limit, stop).
  Each function returns a result: filled, partial, rejected, with details.
- **Safety checks** (before executing):
  - Does this order exceed the maximum position size from config?
  - Is this a sell of the entire portfolio? (flag for confirmation)
  - Is the market open? (queue for next open if not)
  - Has the price moved significantly since the strategy made this recommendation?
- **Order status**: Check pending orders, handle partial fills.
- **Dry-run mode**: Log exactly what would be executed without placing any orders.
  Controlled by a flag in config.

### Dependencies
- config.py (position limits for safety checks, dry-run flag, API credentials)
- Alpaca API (external)

### Does NOT depend on
- strategy.py (the trading interface doesn't think — it does what it's told)
- data_input.py (it doesn't gather data — it receives instructions)
- calculators.py (no math here)

### Key principle
This module is deliberately thin and dumb. It's the easiest to swap out if you
change broker. It should be boring.

---

## 7. reporting.py

### What it does
Records everything that happens and presents it in useful formats. Written to by
nearly every other module. This is the system's memory — it captures the raw facts
of what was decided, what was executed, and what resulted.

Reporting answers "what happened?" It does NOT answer "was it good?" — that's
audit_qa's job.

### Contains
- **Decision log**: Every strategy recommendation with its reasoning, the scores
  that drove it, and whether it was executed, modified, or overridden.
- **Execution log**: Every order sent to Alpaca, its status, fill price, slippage
  from expected price.
- **Portfolio snapshot**: Periodic capture of full portfolio state — positions,
  allocations, P&L, tier distribution. Enables historical comparison.
- **Performance metrics**: Return calculations (daily, weekly, monthly, YTD),
  comparison to benchmarks, breakdown by strategy/framework.
- **Dashboard output**: Formats data for display. Initially this could be a simple
  console summary or CSV export; later a web dashboard. Also surfaces audit_qa
  findings when they are available.
- **Real-time alerts**: When reporting spots something that needs immediate attention
  (e.g. drawdown exceeding threshold, data source failure), it flags it for the
  portfolio manager.

### Dependencies
- config.py (reporting intervals, alert thresholds, output format preferences)

### Written to by
- portfolio_manager.py (logs the full cycle: plan + execution + results)
- trading_interface.py (logs order results directly for immediate capture)
- audit_qa.py (delivers periodic findings for inclusion in dashboard/reports)

### Key principle
If it happened and wasn't logged, it didn't happen. Every decision, every trade,
every override, every error. Reporting is factual and comprehensive. Interpretation
belongs to audit_qa.

---

## 8. audit_qa.py

### What it does
The system's independent reviewer. It runs on a separate, less frequent schedule
(e.g. monthly, or on-demand) and performs a retrospective analysis of the system's
performance, decisions, and behaviour over a defined review period. Its purpose is
to identify patterns — what's working, what isn't, and why — and to suggest
adjustments to config, strategy logic, or score weights.

This is the module most likely to use LLMs, because its job requires the kind of
interpretive, qualitative reasoning that goes beyond threshold checks: looking at
a month of trades and forming a view on whether the sentiment scoring is
contributing value, or whether the stop-loss percentage is too tight for the
current volatility regime.

It does NOT change the system automatically. It produces findings and
recommendations that a human reviews before any changes are made to config or
strategy.

### Contains

- **Benchmark comparison**:
  - Compare portfolio returns against configured benchmarks (e.g. S&P 500, sector
    ETFs, a simple 60/40 portfolio) over the review period.
  - Calculate alpha: is the system adding value beyond what a passive approach
    would deliver?
  - Track this over time: is alpha improving, declining, or volatile?

- **Decision quality analysis**:
  - Review all buy decisions in the period: what was the score at entry, what
    happened to the position afterward? Are high-conviction buys actually
    outperforming low-conviction ones? If not, the scoring model may be
    miscalibrated.
  - Review all sell decisions: were stop-losses triggered appropriately, or did
    positions recover immediately after being sold (suggesting stops are too
    tight)? Were take-profits captured, or did the system hold too long?
  - Review holds: did positions that strategy recommended holding actually
    continue to perform? Or are there patterns of slow bleed that the hold
    criteria aren't catching?

- **Score effectiveness analysis**:
  - For each score dimension (fundamental, technical, sentiment, macro), assess
    whether that score correlated with actual outcomes over the review period.
  - If sentiment scores are not predictive of price movement, the weight assigned
    to sentiment in config may need reducing.
  - If macro scores consistently flag risks that materialise, the weight may
    need increasing.
  - This is where an LLM is valuable: it can look at the correlation data AND
    the narrative context (what was the news, what was the market environment)
    to form a more nuanced view than a simple statistical test.

- **Pattern detection**:
  - Are there recurring situations where the system performs poorly? (e.g.
    consistently wrong on earnings plays, or bad at timing sector rotations)
  - Are there sectors, market conditions, or score ranges where performance
    is notably better or worse?
  - Has the system's behaviour changed over time in unintended ways? (e.g.
    gradually becoming more aggressive as trailing stops ratchet up)
  - An LLM can synthesise these patterns into a readable narrative rather
    than just presenting tables of numbers.

- **Config recommendation engine**:
  - Based on the above analysis, generate specific, testable recommendations:
    "Consider reducing sentiment weight from 0.25 to 0.15 based on low
    correlation over the past 3 months" or "The 8% stop-loss triggered on
    6 positions that recovered within 5 days — consider testing 10% or
    ATR-based stops."
  - Each recommendation includes the evidence that supports it and a
    suggested way to test it (e.g. backtest with the proposed change).
  - Recommendations are flagged with confidence: high (clear pattern with
    statistical support), medium (suggestive pattern, needs more data),
    low (worth investigating but inconclusive).

- **Risk regime assessment**:
  - Step back and assess whether the current market environment matches the
    assumptions embedded in the active config/strategy profile. If the system
    is running an "aggressive growth" profile but the macro environment has
    shifted to high volatility, the audit should flag this mismatch.
  - This is another area where LLM reasoning adds value: connecting macro
    conditions to strategy appropriateness is a judgment call, not a formula.

### Output format
- A structured findings report covering each area above, suitable for inclusion
  in the dashboard and/or export as a standalone document.
- A prioritised list of recommended config changes with evidence and confidence.
- A summary narrative (LLM-generated) that a human can read in 5 minutes to
  understand the system's health.

### Dependencies
- config.py (benchmark definitions, review period, audit schedule, current
  parameter values — so it can assess whether they're appropriate)
- reporting.py (reads the decision log, execution log, and portfolio snapshots
  that reporting has been accumulating — this is audit_qa's primary data source)
- data_input.py (for benchmark price data and current market context)
- calculators.py (for statistical calculations: correlation, alpha, Sharpe, etc.)
- LLM API (for interpretive analysis — the specific provider is configured in
  config)

### Does NOT depend on
- strategy.py (audit_qa reviews strategy's outputs via the logs in reporting,
  but never calls strategy directly — it's an independent observer)
- trading_interface.py (audit_qa never executes trades)
- portfolio_manager.py (audit_qa doesn't orchestrate anything — it's called BY
  the portfolio manager on a schedule, or run manually)

### Key principle
Audit_qa is the system watching itself. It operates at a different timescale
(weeks/months, not minutes/hours) and a different level of abstraction (patterns
and trends, not individual trades). It is the only module that asks "should we
change how the system works?" rather than "what should the system do right now?"

Its recommendations are always suggestions to a human, never automatic changes.
The human reviews, decides, and manually updates config. This keeps accountability
with a person and prevents feedback loops where the system optimises itself into
a corner.

---

## Data Flow Summary

```
                       External World
                            │
                       ┌────▼────┐
                       │  data   │  ◄── Alpaca, Sentiment Pipeline,
                       │  input  │      Decis, Financial Datasets
                       └────┬────┘
                            │ scores + portfolio state + benchmarks
                            ▼
       ┌─────────┐    ┌─────────────┐    ┌──────────────┐
       │  config │───►│  strategy   │◄───│ calculators   │
       │         │    │  (assess +  │    │ (pure math)   │
       │         │    │   plan)     │    │               │
       └────┬────┘    └──────┬──────┘    └──────┬────────┘
            │                │                   │
            │                │ plan              │
            │                ▼                   │
            │         ┌──────────────┐           │
            ├────────►│  portfolio   │           │
            │         │  manager     │           │
            │         │ (orchestrator)│          │
            │         └─┬──────┬──┬──┘           │
            │           │      │  │              │
            │           ▼      │  ▼              │
            │   ┌────────┐  │  ┌───────────┐    │
            ├──►│trading │  │  │ reporting │    │
            │   │interface│  │  │ (records) │    │
            │   └────┬───┘  │  └─────┬─────┘    │
            │        │      │        │           │
            │        ▼      │        │           │
            │   Alpaca API  │        │           │
            │               │        ▼           │
            │               │  ┌───────────┐    │
            │               └─►│ audit_qa  │◄───┘
            ├─────────────────►│(reviewer) │
            │                  └─────┬─────┘
            │                        │
            │                        ▼
            │              Findings & recommendations
            │              (to dashboard via reporting,
            │               to human for config decisions)
```

### Two operating rhythms

**Fast loop** (minutes to hours — portfolio_manager drives):
  data_input → strategy → portfolio_manager → trading_interface → reporting

**Slow loop** (weekly to monthly — portfolio_manager triggers, audit_qa runs):
  reporting (accumulated data) → audit_qa → findings → human review → config changes

The fast loop runs the portfolio. The slow loop improves the system.

---

## What This Does NOT Include (By Design)

These are handled by separate systems that feed INTO data_input:

- NLP / sentiment analysis pipeline
- News aggregation and monitoring
- Event classification (scope, severity, duration)
- Entity resolution (company → country → sector mapping)
- The Decis country stability engine

The trading system consumes the outputs of these systems as scores. It doesn't
need to know how they work.

---

## Adding Complexity Later

The structure supports incremental additions without reorganisation:

- **New data source**: Add a function in data_input. Add its weight in config.
- **New theoretical framework**: Add assessment logic in strategy that calls new
  functions in calculators.
- **New score dimension**: Add a field to the score structure, a weight in config,
  and it flows through automatically.
- **New safety rule**: Add a check in trading_interface.
- **New report type**: Add a function in reporting.
- **New audit analysis**: Add a function in audit_qa.
- **Change broker**: Rewrite trading_interface only.
- **Change LLM provider**: Update config only (audit_qa reads LLM config from there).

Nothing else changes in any of these cases.

---

## Module Dependency Summary

| Module             | Reads from                                      | Written to by / Called by         |
|--------------------|------------------------------------------------|-----------------------------------|
| config             | —                                              | Human (manual edits only)         |
| calculators        | config                                         | —                                 |
| data_input         | config, calculators, external APIs             | —                                 |
| strategy           | config, calculators, data_input                | —                                 |
| portfolio_manager  | config, data_input, strategy, trading_interface, reporting, audit_qa | Scheduler / triggers |
| trading_interface  | config, Alpaca API                             | portfolio_manager                 |
| reporting          | config                                         | portfolio_manager, trading_interface, audit_qa |
| audit_qa           | config, reporting, data_input, calculators, LLM API | portfolio_manager (triggers)  |
