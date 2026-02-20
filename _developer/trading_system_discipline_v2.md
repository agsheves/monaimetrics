  
**ACTIVE TRADING SYSTEM**

Part 3: Operating Discipline & Autonomous Execution

*Automated Rules  |  Exit Philosophies  |  Human Governance*

**DRAFT — For System Development Scoping**

Version 2.0 — Supersedes Part 3 v1.0

# **1\. Introduction: The Autonomous Discipline Layer**

The first document in this series defined the system’s architecture. The second defined the theoretical frameworks that drive decisions. This third document defines the operating discipline: the specific rules, the autonomous execution model, and the governance framework that allows a non-expert human owner to benefit from proven investment methodologies without managing individual trades.

## **1.1 The Automation Principle**

*The system executes trades autonomously based on rules derived from proven investment methodologies. The human owner’s role is governance, not operation. They set the parameters, review performance, and approve structural changes. They do not approve, modify, or delay individual trades.*

This design is supported by every theoretical framework the system is built on. The Elm Wealth Crystal Ball study proved that even finance professionals with tomorrow’s newspaper destroyed value through poor judgment on individual trades. Every practitioner referenced in the frameworks document — Thorp, O’Neil, Weinstein, Greenblatt, Marks — emphasises that the greatest source of loss is human judgment overriding systematic rules. O’Neil’s 8% stop-loss works precisely because it is executed without deliberation. Weinstein’s Stage 4 rule works because there is no exception.

The human owner is not expected to be a market expert. The expertise is embedded in the system through the theoretical frameworks. The human’s advantage is access to a system that codifies decades of proven methodology from Oaktree, Elm Wealth, and the other practitioners whose track records are documented in Part 2\.

## **1.2 Execution Model**

The system connects to a trading API with low transaction fees, enabling fully programmatic trade execution. This eliminates the gap where emotion could intervene between signal and execution.

| Function | Performed By | Rationale |
| :---- | :---- | :---- |
| Initial setup: risk tolerance, exclusions, capital | Human owner | Personal preferences only the owner can define. |
| Signal generation, sizing, entry/exit | System (automated) | Rules-based. Human judgment adds no value here. |
| Trade execution | System via trading API | Programmatic execution eliminates the emotion gap. |
| Monitoring and alerting | System, with notifications to human | Owner informed but not required to act on routine operations. |
| Periodic performance review | Human, using system reports | Owner reviews whether parameters need adjustment. |
| Parameter adjustments | Human, via configuration interface | Deliberate, logged, effective from next trade cycle. |
| Structural changes | Human, formal review process | Architectural decisions requiring understanding of implications. |

# **2\. Human Owner Setup and Configuration**

Before the system begins operating, the human owner completes an initial configuration. This is the primary point at which the human shapes the system’s behaviour. Once configured, the system operates autonomously within these parameters.

## **2.1 Initial Configuration Inputs**

| Input | Description | Example Values |
| :---- | :---- | :---- |
| Total active capital | Amount allocated to this active portfolio (separate from ETF allocation) | £50,000 / $100,000 |
| Risk tolerance profile | Named profile that sets default parameter values | Moderate Growth (default), Aggressive Growth, Conservative Growth |
| Market exclusions | Countries, sectors, or companies to exclude | Exclude: tobacco, weapons, Russia |
| Currency preference | Base currency and allowed markets | GBP base, allow USD and EUR |
| Maximum drawdown tolerance | Portfolio drawdown that triggers defensive posture | 15% from peak |
| Notification preferences | What to be informed about and how | Daily digest, push for emergencies only |
| Capital addition schedule | New capital frequency | Monthly / ad hoc / none |

## **2.2 Risk Tolerance Profiles**

Profiles set multiple parameters simultaneously, providing a coherent starting point.

| Parameter | Conservative | Moderate (Default) | Aggressive |
| :---- | :---- | :---- | :---- |
| Mod / High split | 75% / 25% | 65% / 35% | 55% / 45% |
| Cash reserve | 10% | 7% | 5% |
| Moderate profit target | 20% | 25% | 30% |
| Moderate stop-loss | 6% | 8% | 10% |
| Kelly fraction (Mod/High) | 0.15 / 0.25 | 0.25 / 0.35 | 0.30 / 0.40 |
| High-risk ATR multiple | 2.0× | 2.5× | 3.0× |
| Max single position | Mod 8%, High 4% | Mod 10%, High 5% | Mod 12%, High 7% |
| Non-perf review (Mod/High) | 3wk / 5wk | 4wk / 6wk | 5wk / 8wk |
| Max drawdown trigger | 12% | 18% | 25% |

## **2.3 Post-Setup Role**

After setup, the owner’s role is limited to: reviewing the periodic performance report (default: monthly), approving or rejecting parameter adjustments recommended by the system, adding or withdrawing capital, and updating personal constraints. The owner does not review individual trade decisions.

# **3\. Portfolio Structure**

## **3.1 Two-Tier Active Portfolio**

Low-risk allocation is handled separately through an ETF portfolio, outside this system’s scope.

| Tier | Role | Philosophy | Hold Period |
| :---- | :---- | :---- | :---- |
| Moderate Risk | Harvesting Engine | Ride to defined profit target, bank gains, redeploy. Optimise for batting average and capital turnover. | 2wk – 3mo |
| High Risk | Asymmetry Engine | Winners allowed to run via trailing stops. Optimise for magnitude of winners. | 1wk – 12+mo |

## **3.2 Cycle-Adjusted Allocation**

Allocation adjusts automatically based on Howard Marks’ Cycle Positioning framework.

| Cycle Position | Moderate | High Risk | Rationale |
| :---- | :---- | :---- | :---- |
| Extreme despair (-2) | 50% | 50% | Maximum opportunity for asymmetric winners. |
| Pessimism (-1) | 55% | 45% | Good conditions for high-risk. |
| Neutral (0) | 65% | 35% | Default. Majority in harvesting engine. |
| Optimism (+1) | 70% | 30% | Fewer asymmetric opportunities. |
| Extreme euphoria (+2) | 75–80% | 20–25% | Protect capital through consistent harvesting. |

## **3.3 Cash Reserve**

Adjusts automatically: 5% in despair, 7% at neutral, up to 15% in euphoria. Not manually deployable.

# **4\. Moderate Risk Tier: The Harvesting Engine**

## **4.1 Philosophy**

Growth through consistent, disciplined harvesting. A series of 20–25% gains, reliably harvested and redeployed, compounds more aggressively and with less variance than chasing larger but unpredictable returns. Directly supported by O’Neil’s research on winners from 1953–2001.

## **4.2 Automated Entry**

System enters automatically when: CAN SLIM score above threshold, Stage 2 confirmed, Greenblatt top quartile or strong CAN SLIM with earnings acceleration, no sell signals, Kelly-sized within available capital, market direction permits.

## **4.3 Automated Profit Harvest**

**ABSOLUTE RULE: When a moderate-tier position reaches the profit target (default: 25%), the system sells automatically. No delay, no review, no exception.**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Profit target | Gain from entry triggering harvest | 25% |
| Volatility adjustment | Wider target for volatile stocks | Base \+ (0.5 × 30-day ATR as %) |
| Execution | Order type at target | Market order when close exceeds target |

## **4.4 Automated Stop-Loss**

**ABSOLUTE RULE: If position falls to stop-loss (default: 8% below entry), system sells automatically at next available price.**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Max loss | Loss from entry triggering exit | 8% |
| Trigger basis | Intraday or closing price | Closing price |
| Gap-down | If stock gaps below stop at open | Sell at first available price |

## **4.5 Non-Performing Position Rules**

**ABSOLUTE RULE: Positions not progressing toward target are automatically assessed. If criteria no longer met, system sells without human intervention.**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Review trigger | Weeks with \<min move | 4 weeks |
| Min expected move | Gain to avoid review | 5% |
| Auto hold criteria | To survive: ALL entry criteria still met AND active buy/watch signal | Full re-evaluation |
| Auto sell criteria | Any criterion failed OR no signal OR Stage 1/3 | System sells |
| Max hold | Absolute cap unless hitting new highs | 12 weeks |

## **4.6 Re-Entry**

**ABSOLUTE RULE: Re-buying after any exit is a completely new trade. Full pipeline evaluation at current price. New stop-loss from new entry. No shortcuts, no memory of previous trade.**

# **5\. High Risk Tier: The Asymmetry Engine**

## **5.1 Philosophy**

Higher rate of individual losses, offset by outsized winners via trailing stops. System enters asymmetric risk/reward positions, applies strict initial stops, and lets the trailing mechanism identify winners automatically. Derived from Thorp’s fat pitch approach and Weinstein’s Stage 2 trend-riding.

## **5.2 Automated Entry**

System enters automatically when: Asymmetry Score meets threshold (default 3:1), at least one supporting framework confirms, no concentration breach, Kelly-sized with high-risk multiplier, event cascade past Phase 2 for event-driven entries.

## **5.3 Initial Stop-Loss**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Method | ATR-based below entry | 2.5 × 14-day ATR |
| Max initial stop | Hard cap | 15% below entry |
| Min initial stop | Floor | 5% below entry |

## **5.4 Trailing Stop: Milestone Ratcheting**

**ABSOLUTE RULE: Trailing stops only move upward. System executes automatically.**

| Gain | Stop Moves To | Effect |
| :---- | :---- | :---- |
| Entry | ATR-based | Max loss at initial stop |
| \+15% | Breakeven | Loss now impossible |
| \+30% | Locks \+15% | 15% gain guaranteed |
| \+50% | Locks \+30% | 30% gain guaranteed |
| \>+50% | Trail: high minus 1.5–2.0×ATR | Stop follows price up |

### **5.4.1 Stage Interaction**

Stage 2 → Stage 3 transition: stop auto-tightens to 1.0 × ATR. Stage 4 detected: immediate auto-sell. Broker-side stop orders updated at each ratchet.

## **5.5 Non-Performing Positions**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Review trigger | Weeks with \<min move | 6 weeks |
| Min expected move | Gain to avoid review | 8% |
| Max hold without new highs | Stagnant position cap | 10 weeks |
| Thesis expiry | Event-driven catalyst window | 8 weeks |

# **6\. The Continuous Hold Audit**

*Every position must continuously earn its place. The system runs this audit automatically. Positions that fail are exited. The human is notified but not consulted.*

## **6.1 Automated Assessment**

Weekly, for every position: given current price, fundamentals, stage, and cycle, would this stock generate a buy signal if not already held? Yes → hold confirmed. No → flagged for exit.

| Criterion | Pass | Fail Action |
| :---- | :---- | :---- |
| Stage Analysis | Stage 2 | Stage 3: tighten. Stage 4: auto-sell. |
| Fundamentals | Above entry threshold | Below: flag for exit. |
| Original thesis | Still valid | Invalidated: auto-sell. |
| Stop/trailing stop | Price above stop | Hit: immediate auto-sell. |
| Non-performance | Progressing | Review trigger: auto-evaluate. |
| Concentration | Within limits | Exceeded: auto-trim. |
| Event risk | No structural negative | Structural negative: auto-reassess. |

# **7\. Governance Model**

## **7.1 Govern, Don’t Operate**

The human governs like a board of directors: set strategy, review performance, approve structural changes. No day-to-day operational decisions.

## **7.2 What the Human Cannot Do**

**The human cannot: delay or cancel a system trade, override a stop-loss or profit target, manually enter a trade without a system signal, apply parameter changes retroactively to open positions.**

## **7.3 What the Human Can Do**

| Action | When | Effect |
| :---- | :---- | :---- |
| Adjust risk profile | Any time | New trades use updated params. Open positions unchanged. |
| Add/withdraw capital | Any time | System adjusts. No forced selling unless withdrawal requires it. |
| Update exclusions | Any time | No new entries in excluded areas. Existing flagged for natural exit. |
| Pause system | Any time \+ confirm | No new entries. Open positions still managed. |
| Emergency halt | Any time \+ double confirm | All positions closed. Manual restart required. |
| Approve param changes | Monthly review | System recommends, human approves. Next cycle. |
| Request structural review | Ad hoc | Formal process, not immediate change. |

## **7.4 The Periodic Review**

Monthly (default). System generates report containing: portfolio performance vs benchmark, trade summary with win rates, framework effectiveness scorecards, parameter performance analysis, recommended adjustments with rationale, cycle assessment, and anomaly flags.

## **7.5 Parameter Adjustment Process**

1. System identifies improvement based on rolling data (e.g., profit target consistently reached in 2 weeks suggesting it could rise).

2. Recommendation presented in periodic review with data and expected impact.

3. Human reviews: approve, modify, reject, or defer.

4. Approved changes logged and effective from next trade cycle. Open positions unaffected.

5. System tracks change impact and reports in subsequent reviews.

## **7.6 Structural Changes**

Changes to absolute rules, frameworks, or architecture require: written proposal, backtesting against historical data, 2-week minimum review period, and explicit human approval. System cannot initiate these autonomously.

# **8\. Safety Mechanisms and Circuit Breakers**

## **8.1 Structural Divergence: The Preservation Circuit Breaker**

*The rarest and most consequential safety mechanism. Triggers when the market shows extreme euphoria on sentiment and valuation indicators while fundamental indicators are simultaneously deteriorating. Expected frequency: once or twice per decade. This is not a normal correction — it is the system detecting that the foundations are cracking beneath a rising market.*

Historical examples of this pattern include the period preceding the 2000 dot-com crash (extreme valuations, deteriorating earnings breadth, speculative IPO activity) and 2007–2008 (extreme credit euphoria, deteriorating lending quality, rising default indicators). In both cases, the market continued rising for months after the divergence became measurable, then fell catastrophically.

The system does not attempt to time the top. Instead, it progressively accelerates the portfolio toward cash through the existing exit mechanisms, tightened and accelerated. The result is that when the crash arrives, the portfolio is substantially in cash. If the crash does not arrive and the market continues climbing, the system has banked significant profits through accelerated harvesting and can re-enter when signals normalise.

### **8.1.1 Trigger Conditions**

Structural Divergence is detected when euphoria indicators and fundamental indicators move in opposite directions beyond defined thresholds simultaneously. All of the following must be true:

* Cycle composite score at \+1.5 or above (strong optimism to euphoria), driven primarily by investor psychology and valuation dimensions

* AND at least three of the following fundamental deterioration signals present: aggregate earnings revisions trending negative over 8+ weeks, credit spreads widening while equity prices rise, corporate insider selling at elevated levels (2× or more above 12-month average), new debt issuance quality declining (higher proportion of speculative-grade), IPO/SPAC activity at extremes with poor post-listing performance, market breadth narrowing (fewer stocks driving index gains)

* AND the divergence has persisted for at least 4 weeks (prevents triggering on transient data)

### **8.1.2 Graduated Response**

Structural Divergence does not trigger a single panic sell. It activates a preservation mode that progressively reduces exposure through existing mechanisms, accelerated.

| Action | Normal Mode | Preservation Mode |
| :---- | :---- | :---- |
| New entries | Active | Halted completely. No new positions opened. |
| Moderate tier profit targets | 25% (default) | Reduced to half of configured target (e.g., 12.5%). Harvest gains faster. |
| High-risk trailing stops | 1.5–2.0× ATR | Tightened to 1.0× ATR across all positions. |
| Hold audit threshold | Standard weekly | Daily assessment. Lower threshold for hold confirmation. |
| Non-performance review | 4wk (mod) / 6wk (high) | Halved: 2wk (mod) / 3wk (high). Release capital from stagnant positions faster. |
| Cash reserve target | Cycle-adjusted (7–15%) | No target — cash accumulates as positions exit through tightened rules. |

### **8.1.3 Exit from Preservation Mode**

Preservation mode continues until either: the divergence resolves (cycle indicators return below \+1.0 OR fundamental deterioration signals reduce to fewer than two), or the owner manually exits preservation mode. When preservation mode ends, parameters revert to their normal configured values and the system resumes normal entry and management operations. Positions that were exited during preservation are eligible for re-entry as new trades through the standard pipeline.

### **8.1.4 Parameters**

| Parameter | Default |
| :---- | :---- |
| Cycle score threshold | Composite ≥ \+1.5 |
| Min fundamental deterioration signals | 3 of 6 |
| Persistence requirement | 4 consecutive weeks |
| Profit target reduction (moderate) | Halved |
| Trailing stop tightening (high-risk) | 1.0× ATR |
| Hold audit frequency in preservation | Daily |
| Non-performance review acceleration | Halved |

## **8.2 Operational Circuit Breakers**

| Breaker | Trigger | Response |
| :---- | :---- | :---- |
| Max drawdown | Portfolio at max drawdown from peak (default 18%) | Pause new entries. Existing managed by rules. CRITICAL alert. Resume at 10% recovery or manual unpause. |
| Rapid loss | 3+ stops triggered in single day | Pause new entries 48hrs. Existing continue under their rules. |
| API failure | Unavailable \>1hr during market hours | Queue trades, retry. CRITICAL alert. Broker-side stops maintained. |
| Data feed failure | Stale data beyond threshold | Pause new entries until restored. Existing continue. |
| Concentration breach | Position \>150% of cap via appreciation | Auto-trim to cap. |

## **8.3 Broker-Side Stops**

All stop-loss orders placed persistently on broker side where API supports it. Protects against system downtime. If unavailable, system maintains heartbeat check with immediate owner alert on failure.

## **8.4 Notifications**

| Priority | Delivery | Examples |
| :---- | :---- | :---- |
| CRITICAL | Immediate push \+ email | Structural Divergence activated, circuit breaker, API failure, system offline |
| HIGH | Push within 15min | Multiple stops, cycle change, significant event |
| STANDARD | Daily digest | Trades executed, rebalancing, non-perf exits |
| INFORMATIONAL | Monthly review only | Framework effectiveness, parameter observations |

# **9\. Position Lifecycle: Automated Flow**

## **9.1 Moderate Tier**

1. Signal: Automated screening passes. Kelly calculates size.

2. Entry: API buy order. Broker-side stop at 8%. Target recorded. Clock starts. Owner notified (STANDARD).

3. Monitoring: Weekly audit. Non-perf review at 4wk if \<5% gain.

4. Exit: (a) Target hit → auto-sell. (b) Stop hit → auto-sell. (c) Non-perf failed → auto-sell. (d) Framework violation → auto-sell.

5. Post-exit: Capital to pool. Re-entry only as new trade through full pipeline.

## **9.2 High Risk Tier**

1. Signal: Asymmetry score \+ supporting framework. Kelly with high-risk multiplier.

2. Entry: API buy order. Broker-side stop at 2.5× ATR. Owner notified (STANDARD).

3. Monitoring: Weekly audit. Trailing ratchets: \+15%→breakeven, \+30%→lock 15%, \+50%→lock 30%, then trailing ATR. Broker stops updated.

4. Stage watch: Stage 3 → tighten to 1.0× ATR. Stage 4 → immediate sell.

5. Exit: (a) Trail hit → auto-sell (gain guaranteed post-breakeven). (b) Initial stop → auto-sell. (c) Non-perf → auto-sell. (d) Thesis expiry → auto-sell. (e) Stage 4/emergency → auto-sell.

6. Post-exit: Full fresh evaluation for any re-entry.

# **10\. Performance Tracking**

## **10.1 Tier Metrics**

| Metric | Moderate Target | High Risk Target |
| :---- | :---- | :---- |
| Win rate | \>55% | \>35% |
| Avg gain (winners) | 20–25% | 50%+ |
| Avg loss (losers) | \<8% | \<12% |
| Capital turnover | Higher \= efficient | Lower expected |
| Non-perf exit rate | \<20% | \<25% |
| Reward:risk | \~3:1 | \>4:1 |

## **10.2 Portfolio Metrics**

* Total return vs benchmark

* Return attribution by tier

* Cycle adjustment effectiveness

* Capital utilisation rate

* Framework effectiveness scorecards

## **10.3 System Health**

* API uptime and execution latency

* Data feed freshness

* Signal pipeline performance

* Circuit breaker activation frequency

# **11\. Appendix: Complete Rules Reference**

## **11.1 Absolute Rules (No Override)**

1. Stop-loss execution is automatic and immediate.

2. Trailing stops never move downward.

3. Stage 4 \= immediate sell.

4. Re-entry \= completely new trade.

5. Every position audited on cycle.

6. Moderate profit targets executed when hit.

7. Positions auto-trimmed if exceeding cap.

8. Non-performing positions auto-sold on failed review.

9. Human cannot delay/cancel/modify individual trades.

10. Parameter changes apply to new trades only.

11. Structural Divergence preservation mode activates automatically when trigger conditions are met.

## **11.2 Parameters Summary**

| Parameter | Moderate Default | High Risk Default |
| :---- | :---- | :---- |
| Profit target | 25% | N/A (trailing) |
| Initial stop | 8% | 2.5× ATR (max 15%) |
| Non-perf review | 4 weeks | 6 weeks |
| Min move at review | 5% | 8% |
| Max hold (no new highs) | 12 weeks | 10 weeks |
| Thesis expiry | N/A | 8 weeks |
| Kelly fraction | 0.25 | 0.35 |
| Audit frequency | Weekly | Weekly |
| Breakeven ratchet | N/A | At \+15% |
| Lock-in ratchets | N/A | \+15% at \+30%, \+30% at \+50% |
| Trailing (mature) | N/A | 1.5–2.0× ATR |
| Stage 3 tighten | N/A | 1.0× ATR |
| Allocation | 65% | 35% |
| Range | 50–80% | 20–50% |

## **11.3 Human Authority**

| Can Do | Cannot Do |
| :---- | :---- |
| Set risk tolerance and preferences | Override individual trades |
| Add/withdraw capital | Delay stop-loss execution |
| Update market exclusions | Enter trades without system signal |
| Pause system | Modify open position parameters |
| Emergency halt | Change absolute rules without formal review |
| Approve param changes at review | Apply changes retroactively |
| Request structural review | Disable circuit breakers |

