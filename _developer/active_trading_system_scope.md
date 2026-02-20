  
**ACTIVE TRADING SYSTEM**

System Scope & Architecture Definition

*Capital Growth Focus  |  Active Management  |  Human-Executed Trades*

**DRAFT  —  For System Development Scoping**

Version 1.0

# **1\. Executive Summary**

This document defines the full scope for an active trading system designed to generate capital growth through intelligent, event-driven portfolio management. The system integrates real-time news analysis, market metrics, and algorithmic stability assessments to produce actionable buy, sell, and hold signals for a human trader.

The system is not a day-trading platform. It operates on a medium-frequency active trading basis where positions may be held for extended periods when growth conditions are met, but trades can be executed quickly when conditions demand it, particularly in emergency scenarios. All trade execution is performed by a human operator; the system provides decision support, monitoring, and alerting.

# **2\. System Overview & Operating Principles**

## **2.1 Core Objectives**

1. Generate capital growth through active, informed position management

2. Identify buying opportunities driven by news events, market conditions, and fundamental analysis

3. Identify sell triggers and manage downside risk through structured loss management

4. Maintain a balanced portfolio across risk tiers with systematic rebalancing

5. Provide real-time portfolio monitoring and alerting to a human trader

## **2.2 Operating Model**

The system operates as a decision-support and monitoring layer. It does not execute trades. The human trader receives signals, alerts, and recommendations and retains full authority over execution. The system maintains a persistent view of the portfolio state and continuously evaluates positions against its criteria.

| Characteristic | Description |
| :---- | :---- |
| Trading frequency | Active but not day-trading. Positions held for days to months. Emergency exits executed within minutes. |
| Execution model | Human-executed. System generates signals and alerts; human approves and places trades. |
| Market hours | System monitors continuously. Alerts generated 24/7 for global markets; trade recommendations flagged for next available execution window. |
| Asset scope | Equities, ETFs, and index funds across global markets. Extensible to other asset classes. |
| Decision basis | Combination of news/event analysis, fundamental metrics, technical signals, and stability/volatility algorithms. |

# **3\. System Architecture**

The system comprises six interconnected modules. Each module operates with defined inputs and outputs, and communicates through a shared data layer.

## **3.1 Module Overview**

| Module | Function | Key Outputs |
| :---- | :---- | :---- |
| News & Event Engine | Ingests, categorises, and scores news and events | Event classifications, impact scores, affected entities |
| Signal Generator | Converts events and metrics into trading signals | Buy / sell / hold signals with confidence levels |
| Strategy Engine | Applies trading strategy rules and risk management | Position sizing, stop-loss levels, take-profit targets |
| Portfolio Manager | Tracks positions, allocations, and P\&L | Current state, drift analysis, rebalance instructions |
| Alert & Notification System | Delivers actionable information to the human trader | Prioritised alerts, dashboards, signal summaries |
| Configuration & Tuning Layer | Manages adjustable parameters across all modules | Parameter sets, strategy profiles, audit logs |

## **3.2 Data Flow**

The system follows a pipeline architecture: raw inputs (news feeds, market data, portfolio state) flow through processing stages to produce human-readable outputs (signals, alerts, rebalance recommendations). Each stage enriches the data with additional context and scoring. All decisions and their inputs are logged for auditability and strategy refinement.

# **4\. News & Event Engine**

## **4.1 Purpose**

This module is the primary input layer. It ingests news and event data from configured sources, classifies events by type and severity, and scores their potential impact on portfolio holdings and watchlist assets.

## **4.2 Event Classification Framework**

Every event is classified along three dimensions: scope, severity, and expected duration of impact.

| Classification | Categories | Description |
| :---- | :---- | :---- |
| Scope | Global / Regional / Sector / Company | The breadth of impact. A central bank rate decision is global; an earnings miss is company-level. |
| Severity | Normal / Positive Abnormal / Negative Abnormal | Assessed by the stability/volatility algorithms. Normal events are within expected parameters; abnormal events deviate significantly. |
| Duration | Transient / Short-term / Medium-term / Structural | Expected persistence of impact. A flash crash is transient; a regulatory change is structural. |
| Confidence | High / Medium / Low | The system’s confidence in its classification, based on data quality, source reliability, and corroboration. |

## **4.3 Event Types & Impact Mapping**

The engine maintains a taxonomy of event types and their expected impact patterns. This taxonomy is configurable and should be refined over time based on observed outcomes.

### **4.3.1 Macro / Geopolitical Events**

* Central bank rate decisions, monetary policy changes

* Government fiscal policy, tax changes, stimulus/austerity

* Geopolitical tensions, sanctions, trade policy shifts

* Natural disasters, pandemics, supply chain disruptions

* Currency movements, sovereign credit rating changes

### **4.3.2 Sector / Industry Events**

* Regulatory changes affecting specific industries

* Commodity price shocks (oil, metals, agricultural)

* Technology disruption or breakthrough announcements

* Industry consolidation or competitive shifts

### **4.3.3 Company-Specific Events**

* Earnings reports (beat/miss vs consensus)

* Management changes, M\&A activity, spin-offs

* Product launches, recalls, litigation outcomes

* Credit rating changes, debt issuance, buybacks

* Insider trading activity, institutional position changes

## **4.4 Entity Resolution**

The engine must map events to affected entities. An event about a trade war affects specific countries, sectors, and companies differently. The entity resolution layer maintains a graph of relationships (e.g., company X derives 40% of revenue from country Y) to propagate impact assessments through the portfolio.

## **4.5 Configurable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Source weighting | Reliability score per news source | Equal weight; tuned over time |
| Event decay rate | How quickly an event’s impact score diminishes | Varies by duration classification |
| Corroboration threshold | Number of independent sources required to increase confidence | 2 sources for High confidence |
| Watchlist scope | Which entities/sectors to monitor beyond current holdings | Sector peers \+ configurable watchlist |

# **5\. Signal Generator**

## **5.1 Purpose**

The Signal Generator translates classified events and market data into actionable buy, sell, and hold signals. It combines event-driven analysis with fundamental and technical indicators to produce signals with associated confidence levels and urgency ratings.

## **5.2 Signal Types**

| Signal | Meaning | Urgency Levels |
| :---- | :---- | :---- |
| BUY | An opportunity has been identified that meets buying criteria | Standard (next rebalance) / Elevated (within 24h) / Immediate |
| SELL | A position should be exited based on trigger criteria | Standard / Elevated / Emergency (execute ASAP) |
| HOLD | Current position continues to meet hold criteria | N/A — this is the default steady state |
| WATCH | Conditions are developing; not yet actionable | Monitor — may escalate to BUY or SELL |
| REDUCE | Partial position reduction recommended | Standard / Elevated |
| INCREASE | Add to existing position | Standard / Elevated |

## **5.3 Buy Signal Criteria**

A buy signal is generated when multiple conditions align. The system uses a weighted scoring model where each factor contributes to an overall buy score. A configurable threshold determines when the score triggers a signal.

### **5.3.1 Event-Driven Buy Triggers**

* Positive abnormal event affecting a target company or sector with high confidence

* Negative abnormal event creating an oversold condition in a fundamentally sound asset (contrarian opportunity)

* Structural positive shift (regulatory tailwind, market opening, technological advantage)

* Post-event stabilisation: volatility returning to normal after a negative event, indicating the market has absorbed the shock and the asset is undervalued

### **5.3.2 Fundamental Buy Triggers**

* Valuation below historical or peer-relative norms (P/E, P/B, EV/EBITDA) combined with stable or improving fundamentals

* Revenue/earnings growth trajectory above sector average

* Strong balance sheet metrics (low debt/equity, high interest coverage, strong free cash flow)

* Dividend yield above historical average with sustainable payout ratio (for income-generating positions)

### **5.3.3 Technical Buy Triggers**

* Price at or near established support levels with volume confirmation

* Momentum indicators signalling reversal from oversold conditions

* Moving average crossover patterns aligned with fundamental thesis

## **5.4 Sell Signal Criteria**

### **5.4.1 Protective Sell Triggers (Loss Management)**

* Stop-loss threshold breached (see Section 6 for calculation methodology)

* Trailing stop triggered after a position has appreciated

* Negative abnormal event with high confidence directly impacting a held position, where the event is classified as medium-term or structural

* Stability algorithm signals sustained deterioration in the country or market environment relevant to the holding

### **5.4.2 Strategic Sell Triggers**

* Take-profit target reached and no further growth catalyst identified

* Original investment thesis invalidated (e.g., competitive advantage eroded, regulatory environment changed)

* Fundamental deterioration: declining margins, rising debt, cash flow concerns

* Better opportunity identified requiring capital reallocation (opportunity cost trigger)

* Position size has grown beyond risk tier allocation limits due to appreciation

### **5.4.3 Emergency Sell Triggers**

These override normal processes and generate immediate alerts:

* Black swan events: sudden, severe, negative abnormal events with global or sector-wide impact

* Trading halt or suspension of a held security

* Fraud, accounting irregularity, or regulatory enforcement action against a held company

* Sovereign crisis affecting country exposure

## **5.5 Hold Criteria**

A position is held (default state) when the original investment thesis remains intact, growth trajectory is steady, no sell triggers have been activated, and the position remains within its risk tier allocation. The system continuously validates hold status; it is not passive. Each position is re-evaluated on every signal generation cycle.

## **5.6 Signal Scoring & Confidence**

Each signal carries a composite score (0–100) derived from weighted factors, and a confidence level based on data quality and corroboration. The human trader sees both the signal and its underlying reasoning. Thresholds for action are configurable per risk tier.

# **6\. Strategy Engine**

## **6.1 Purpose**

The Strategy Engine applies trading strategy rules to signals, determining position sizing, entry/exit parameters, and risk management mechanics. It enforces discipline and prevents emotional decision-making by providing structured, rules-based recommendations.

## **6.2 Portfolio Allocation Model**

### **6.2.1 Risk Tier Definitions**

| Risk Tier | Characteristics | Target Allocation | Max Single Position |
| :---- | :---- | :---- | :---- |
| Low Risk | Large-cap ETFs, index funds, blue-chip dividend stocks, bonds. Stable, established, low volatility. | Configurable (e.g., 40%) | Configurable (e.g., 15%) |
| Moderate Risk | Mid-cap growth stocks, sector ETFs, established companies with growth catalysts. | Configurable (e.g., 40%) | Configurable (e.g., 10%) |
| High Risk | Small-cap, emerging market, high-growth tech, turnaround plays, event-driven positions. | Configurable (e.g., 20%) | Configurable (e.g., 5%) |

### **6.2.2 Cash Reserve**

The system maintains a configurable cash reserve (e.g., 5–10% of portfolio value). This serves two purposes: liquidity for emergency exits (avoiding forced selling of other positions) and dry powder for immediate opportunity capture. The cash reserve is not counted within the risk tier allocations.

## **6.3 Position Sizing**

Position size is determined by the intersection of the signal’s risk tier, the portfolio’s current allocation state, and a per-position risk budget. The system recommends position sizes based on:

* Available capital within the relevant risk tier

* Maximum single-position limit for the tier

* Volatility-adjusted sizing: higher-volatility assets receive smaller positions to normalise risk contribution

* Conviction level: higher-confidence signals may warrant larger positions within limits

## **6.4 Stop-Loss Framework**

Every position entered must have a defined stop-loss. The system calculates and recommends stop-loss levels; the human trader confirms and sets them.

| Stop-Loss Type | Mechanism | Application |
| :---- | :---- | :---- |
| Initial Stop-Loss | Set at entry based on volatility (e.g., 2x ATR below entry price) or a fixed percentage (configurable per tier). | All new positions |
| Trailing Stop | Adjusts upward as the position appreciates. Never adjusts downward. Gap between price and stop is configurable (e.g., percentage or ATR-based). | Positions that have appreciated beyond a configurable threshold |
| Time-Based Stop | If a position has not moved toward its target within a configurable time window, it is flagged for review. | All positions; threshold configurable per risk tier |
| Event-Driven Override | A negative abnormal event can tighten the stop-loss or trigger immediate exit regardless of current stop level. | Triggered by Signal Generator emergency signals |

## **6.5 Take-Profit Framework**

Take-profit targets are set at entry and adjusted as conditions evolve.

* Initial target based on the investment thesis: expected return within expected timeframe

* Partial profit-taking: configurable rules to take partial profits at interim targets (e.g., sell 25% at 2x target, 25% at 3x, hold remainder with trailing stop)

* Reassessment on target approach: when price nears the take-profit target, the system re-evaluates fundamentals and news to determine whether to take profit or revise the target upward

## **6.6 Correlation & Concentration Risk**

The Strategy Engine monitors cross-position correlation to prevent hidden concentration risk. Holding five stocks in the same sector, even if individually within limits, creates sector concentration. The system tracks:

* Sector exposure as a percentage of portfolio

* Geographic/country exposure

* Correlation between positions (using rolling correlation of returns)

* Factor exposure (e.g., all positions sensitive to interest rate changes)

# **7\. Portfolio Manager**

## **7.1 Purpose**

The Portfolio Manager maintains the real-time state of the portfolio, tracks performance, monitors allocation drift, and generates rebalancing recommendations.

## **7.2 Portfolio State Tracking**

The system maintains a continuous, accurate record of: all current positions (entry price, current price, P\&L, weight, risk tier assignment), cash balance and reserve status, aggregate allocation by risk tier, total portfolio value and performance metrics (daily, weekly, monthly, YTD, since inception).

## **7.3 Rebalancing**

### **7.3.1 Rebalancing Triggers**

Rebalancing occurs on two bases: scheduled and threshold-triggered.

| Trigger | Mechanism | Configurable Parameter |
| :---- | :---- | :---- |
| Scheduled | Regular calendar-based review (e.g., weekly, bi-weekly, monthly) | Frequency |
| Drift threshold | Triggered when any risk tier’s actual allocation deviates from target by more than a configured amount (e.g., 5 percentage points) | Drift tolerance per tier |
| Event-driven | A major market event triggers an unscheduled rebalance review | Severity threshold for trigger |
| Post-trade | After any trade execution, the system recalculates allocations and flags if rebalancing is needed | Automatic |

### **7.3.2 Rebalancing Mechanism**

When a rebalance is triggered, the system generates a set of recommended trades to return the portfolio to target allocations. The recommendations consider: tax efficiency (preferring to add to underweight tiers rather than selling overweight positions where possible), transaction costs, minimum trade sizes, and current signal states (avoiding selling positions with active hold or buy signals unless the drift is severe).

### **7.3.3 Rebalancing Constraints**

* Rebalancing does not override active emergency sell signals

* Rebalancing does not force entry into positions without a supporting buy signal

* If the portfolio cannot be rebalanced to target without violating other rules, the system flags the situation for human review rather than forcing suboptimal trades

## **7.4 Performance Attribution**

The system tracks performance at multiple levels to enable strategy refinement: per-position return and contribution to portfolio, per-risk-tier performance, signal quality metrics (what percentage of buy signals resulted in profitable positions), and event classification accuracy (did the predicted impact materialise).

# **8\. Alert & Notification System**

## **8.1 Purpose**

This module ensures the human trader receives the right information at the right time with the right urgency. Information overload is as dangerous as information deficit.

## **8.2 Alert Priority Levels**

| Priority | Delivery | Examples |
| :---- | :---- | :---- |
| CRITICAL | Immediate push notification \+ audible alert | Emergency sell trigger, black swan event, stop-loss breach on large position |
| HIGH | Push notification within 5 minutes | New sell signal, new high-confidence buy signal, significant portfolio drift |
| STANDARD | Included in next scheduled digest | New moderate-confidence signals, rebalancing recommendations, position reviews due |
| INFORMATIONAL | Dashboard update only | News events classified as normal, routine metric updates, hold confirmations |

## **8.3 Digest Reports**

Scheduled digest reports provide a structured overview. Frequency is configurable (e.g., morning brief, end-of-day summary, weekly review). Each digest includes: portfolio snapshot (value, daily change, allocation status), active signals and their current state, upcoming events that may impact holdings (earnings dates, economic releases), positions approaching stop-loss or take-profit levels, and rebalancing status.

## **8.4 Alert Fatigue Management**

The system includes mechanisms to prevent alert fatigue: grouping related alerts (e.g., if an event affects five holdings, one grouped alert rather than five), suppression of repeated alerts for the same condition within a configurable cooldown period, and escalation if an alert is not acknowledged within a configurable window.

# **9\. Configuration & Tuning Layer**

## **9.1 Purpose**

All adjustable parameters are managed through a central configuration layer. This enables the human trader to tune the system’s behaviour without modifying code, and provides an audit trail of parameter changes.

## **9.2 Key Configurable Parameters**

| Category | Parameters |
| :---- | :---- |
| Risk tolerance | Risk tier allocation targets, maximum single-position sizes, cash reserve percentage |
| Stop-loss / take-profit | Stop-loss methodology (ATR-based, percentage-based), trailing stop gap, take-profit targets, partial profit-taking rules |
| Rebalancing | Scheduled frequency, drift tolerance thresholds, post-event trigger sensitivity |
| Signal generation | Buy/sell score thresholds, factor weightings, minimum confidence for action |
| News & events | Source weighting, event decay rates, corroboration requirements, watchlist scope |
| Alerts | Priority thresholds, delivery channels, digest frequency, cooldown periods, escalation windows |
| Strategy profiles | Pre-defined parameter sets (e.g., “Aggressive Growth”, “Conservative”, “Defensive”) that adjust multiple parameters simultaneously |

## **9.3 Strategy Profiles**

The system supports named strategy profiles that set multiple parameters simultaneously. A profile is a complete configuration snapshot. The trader can switch between profiles (e.g., from Growth to Defensive during market uncertainty) and can create custom profiles. Profile switches are logged and their performance impact tracked.

# **10\. Additional System Considerations**

Beyond the core trading logic, the following elements are essential for a robust, reliable system.

## **10.1 Data Management & Quality**

* Data source redundancy: no single point of failure for market data or news feeds

* Data validation: incoming data is checked for completeness, timeliness, and anomalies before processing

* Historical data storage: all inputs, signals, and decisions are stored for backtesting and audit

* Data freshness monitoring: alerts if data feeds are stale or delayed beyond configurable thresholds

## **10.2 Backtesting & Strategy Validation**

* Ability to replay historical data through the system to validate strategy changes before deploying them live

* Paper trading mode: run the system in parallel with live data but without generating actionable alerts, to validate new configurations

* Performance comparison: track how actual outcomes compare to what the system predicted at signal generation time

## **10.3 System Reliability & Failsafes**

* Graceful degradation: if a data source fails, the system continues operating with available data and flags the gap

* Stale signal handling: signals that have not been acted upon within a configurable window are auto-expired and re-evaluated

* Conflict resolution: if the system generates contradictory signals (e.g., buy from news engine and sell from technical analysis), it escalates to the human trader with full context rather than choosing one

* System health monitoring: the system monitors its own operational state and alerts on failures or anomalies

* Structural Divergence circuit breaker: when euphoria indicators are at extremes but fundamental indicators are simultaneously deteriorating (the pre-crash signature), the system enters an accelerated preservation mode that systematically reduces exposure through tightened stops and reduced profit targets. Operates at both portfolio and sector level. Expected frequency: once or twice per decade. See Part 3 for full specification.

## **10.4 Regulatory & Compliance Awareness**

* Trade frequency monitoring: flag if trading patterns could trigger pattern day trader rules or other regulatory thresholds

* Wash sale tracking: monitor for potential wash sale scenarios and alert before they occur

* Record keeping: maintain trade logs and decision rationale in a format suitable for tax reporting and potential audit

## **10.5 Tax Efficiency**

* Track cost basis and holding periods for all positions

* Factor tax implications into sell signal prioritisation (preferring long-term capital gains where possible)

* Tax-loss harvesting: identify opportunities to realise losses to offset gains, while maintaining portfolio exposure (respecting wash sale rules)

## **10.6 Benchmarking**

* Track portfolio performance against configurable benchmarks (e.g., S\&P 500, relevant sector indices)

* Attribution analysis: understand whether outperformance/underperformance is driven by stock selection, sector allocation, timing, or risk management

* Strategy component analysis: which signals and rules are contributing most to returns

## **10.7 Currency & Multi-Market Considerations**

* Currency exposure tracking for positions in non-base-currency markets

* Currency hedging recommendations when FX exposure exceeds configurable thresholds

* Market hours awareness: signal timing and urgency adjusted for when relevant markets are open

* Cross-market correlation monitoring (e.g., Asian markets overnight impact on European open)

## **10.8 Scalability & Extensibility**

* Modular design: new data sources, signal factors, or asset classes can be added without restructuring the system

* API-first architecture: all modules communicate via well-defined interfaces, enabling future automation or integration with broker APIs

* Plugin model for custom signal generators or analysis modules

## **10.9 Audit Trail & Decision Logging**

* Every signal, recommendation, parameter change, and human decision is logged with timestamp and full context

* Enables post-mortem analysis: for any trade, the system can reconstruct why the signal was generated and what information was available at the time

* Supports strategy refinement through pattern analysis of successful and unsuccessful signals

## **10.10 Human Override & Manual Input**

* The human trader can override any signal or recommendation, with the override logged

* Manual signal injection: the trader can manually add positions or signals for assets the system hasn’t flagged

* Feedback loop: the trader can mark signals as useful or not useful, feeding back into the system’s weighting over time

# **11\. Out of Scope (Current Version)**

* Automated trade execution (all trades are human-executed)

* Options and derivatives trading strategies

* Cryptocurrency markets (may be added as an extension)

* Social media sentiment analysis (may be added; currently limited to structured news sources)

* Machine learning model training within the system (the system uses pre-built stability/volatility algorithms)

* Multi-user or team-based portfolio management

# **12\. Development Approach**

This system should be built incrementally as a series of modular scripts and services. The recommended build order prioritises the modules that provide immediate value:

1. News & Event Engine: establish the data pipeline and event classification

2. Portfolio Manager: establish portfolio state tracking and monitoring

3. Signal Generator: connect events to buy/sell/hold signals

4. Strategy Engine: add position sizing, stop-loss, and risk management

5. Alert & Notification System: deliver signals to the human trader

6. Configuration & Tuning Layer: centralise parameter management

7. Backtesting framework: validate and refine the strategy

Each module should be developed with clear input/output contracts so that modules can be refined independently.