  
**ACTIVE TRADING SYSTEM**

Capabilities Specification

*System Architecture  |  Decision Frameworks  |  Operating Rules  |  Parameters*

**Build-Ready Reference Document**

Synthesised from Parts 1–3  |  No rationale  |  Implementation specification only

**DRAFT**

# **1\. System Overview**

An autonomous active trading system for capital growth. The system generates signals, sizes positions, executes trades via API, and manages exits without human intervention. The human owner configures preferences at setup, reviews monthly performance reports, and approves parameter adjustments. The human does not approve, modify, or delay individual trades.

## **1.1 Scope**

* Asset classes: equities and ETFs across global markets

* Two active tiers: Moderate Risk (harvesting engine) and High Risk (asymmetry engine)

* Low-risk allocation (ETF portfolio) is outside this system’s scope

* Execution: programmatic via trading API with low fees

* Monitoring: continuous, 24/7 for global markets

* Holding period: days to months (moderate), weeks to years (high-risk)

## **1.2 Six-Module Architecture**

| Module | Function | Outputs |
| :---- | :---- | :---- |
| News & Event Engine | Ingest, classify, and score news/events | Event classifications, impact scores, affected entity graph |
| Signal Generator | Convert events \+ metrics into trading signals | BUY/SELL/HOLD/WATCH/REDUCE/INCREASE signals with confidence 0–100 |
| Strategy Engine | Apply 7 theoretical frameworks, size positions, set stops/targets | Position sizes, stop-loss levels, profit targets, asymmetry scores |
| Portfolio Manager | Track positions, allocations, P\&L, drift | Portfolio state, rebalance instructions, hold audit results |
| Alert & Notification System | Deliver information to owner at correct priority | CRITICAL/HIGH/STANDARD/INFORMATIONAL notifications |
| Configuration Layer | Manage all adjustable parameters centrally | Parameter sets, risk profiles, audit logs |

# **2\. Decision Frameworks**

The system uses seven named frameworks in sequence. Each answers a different question in the signal generation pipeline.

| \# | Framework | Question Answered | Output |
| :---- | :---- | :---- | :---- |
| 1 | Cycle Positioning (Marks) | Is the market environment favourable? | Portfolio posture: tier allocation, buy threshold, cash reserve |
| 2 | Stage Analysis (Weinstein) | Is this stock in the right lifecycle phase? | Gate: only Stage 2 stocks may be bought; Stage 4 forces sell |
| 3 | Growth Quality (O’Neil CAN SLIM) | Does this stock have winning characteristics? | Composite score 0–100 for fundamental eligibility |
| 4 | Quality-Value (Greenblatt) | Is this stock both good and cheap? | Combined rank on Return on Capital \+ Earnings Yield |
| 5 | Event-News-Price Cascade | What happened and is the market reaction proportionate? | Event phase classification, over/underreaction detection |
| 6 | Asymmetric Opportunity (Thorp) | Is the risk/reward ratio exceptional? | Asymmetry Score (upside:downside ratio) |
| 7 | Conviction-Weighted Sizing (Kelly) | How much capital to commit? | Position size based on edge estimate and volatility |

## **2.1 Framework 1: Cycle Positioning**

Scores market conditions across four dimensions, each rated \-2 (despair) to \+2 (euphoria). Composite score determines portfolio posture.

| Dimension | Key Indicators |
| :---- | :---- |
| Economic cycle | GDP vs trend, unemployment trajectory, PMI, consumer confidence |
| Credit cycle | Credit spreads, lending standards, new debt issuance, default rates |
| Investor psychology | VIX, fund flows, IPO activity, margin debt, sentiment surveys |
| Valuation cycle | Aggregate P/E vs historical, CAPE ratio, equity risk premium, market cap/GDP |

### **Posture Adjustments**

| Score | Tier Shift | Buy Threshold | Cash Reserve |
| :---- | :---- | :---- | :---- |
| \-2 (despair) | Shift 10–15% toward high-risk | Lowered | Deploy to 3–5% |
| \-1 | Shift 5–10% toward high-risk | Slightly lowered | 5% |
| 0 (neutral) | Target as configured | Standard | 7% |
| \+1 | Shift 5–10% toward moderate | Slightly raised | 10% |
| \+2 (euphoria) | Shift 10–15% toward moderate | Raised | 12–15% |

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| Indicator weights | Equal (25% each) |
| Lookback window | 10 years |
| Assessment frequency | Weekly |
| Contrarian delay at extremes | 2 weeks |

## **2.2 Framework 2: Stage Analysis**

Classifies stocks into four lifecycle stages using the 30-week (150-day) simple moving average and volume patterns. Acts as a hard gate on entry/exit.

| Stage | MA Behaviour | System Action |
| :---- | :---- | :---- |
| 1 – Basing | Flattening after decline | Watchlist only. Buy signals suppressed. |
| 2 – Advancing | Slopes upward, breakout on volume | ONLY stage for buying. Hold existing. |
| 3 – Topping | Flattening, distribution volume | Tighten stops. No new buying. |
| 4 – Declining | Slopes downward | Immediate sell. No exceptions. |

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| MA period | 30 weeks (150 trading days) |
| Breakout volume threshold | 2× average weekly volume |
| Confirmation period | 2 weeks |
| Stage 4 action | Forced immediate sell (all tiers) |

## **2.3 Framework 3: Growth Quality Screening (CAN SLIM)**

Seven-factor scoring model. Stocks scored 0–100 composite. Minimum threshold required for buy eligibility.

| Factor | Implementation | Scoring |
| :---- | :---- | :---- |
| C – Current earnings | Quarterly EPS growth YoY | 0–100; 0 below 15%, 100 above 50% |
| A – Annual earnings | 3–5yr compound EPS growth | 0–100; 0 below 10%, 100 above 35% |
| N – New catalyst | Detected from News Engine | Binary flag |
| S – Supply/demand | Volume acceleration trend | 0–100 |
| L – Leader status | 52-week relative strength rank | Must exceed threshold (default 70\) |
| I – Institutional | Count, quality, net buying | 0–100 composite |
| M – Market direction | Handled by Cycle Positioning | Master gate, not scored individually |

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| Min composite score | 60/100 |
| Factor weights | C:25%, A:20%, N:10%, S:15%, L:20%, I:10% |
| Earnings acceleration | Preferred, not required |

## **2.4 Framework 4: Quality-Value Composite (Magic Formula)**

Ranks all stocks on two metrics: Return on Capital (EBIT / invested capital) and Earnings Yield (EBIT / enterprise value). Combined rank identifies quality businesses at bargain prices.

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| ROC minimum | 15% |
| Earnings yield minimum | Above market average |
| Sector exclusions | Financials, utilities |
| Reranking frequency | Monthly |
| Weight by tier | Moderate: 30%, High: 10% |

## **2.5 Framework 5: Event-News-Price Cascade**

Tracks five phases between event occurrence and full market pricing. System behaviour varies by phase.

| Phase | Timing | System Response |
| :---- | :---- | :---- |
| 1\. Event occurs | T+0 | Assess severity. Do not trade. |
| 2\. News breaks | T+min to T+hrs | Classify. Compare move to expected impact. Do not trade (except emergency sell). |
| 3\. Analysis | T+hrs to T+2d | Monitor for reversal. Flag overreaction if move \> 2× expected. |
| 4\. Consensus | T+2d to T+2wk | Generate signals if market pricing diverges from structural assessment. |
| 5\. Second-order | T+wk to T+months | Monitor knock-on effects via entity resolution graph. |

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| Reaction blackout | 4 hours |
| Overreaction threshold | 2× expected move |
| Underreaction threshold | 0.3× expected move |
| Structural monitoring window | 30 days |
| Entity propagation depth | 2 layers |

## **2.6 Framework 6: Asymmetric Opportunity Recognition**

Calculates Asymmetry Score \= (expected upside × probability) / (expected downside × probability). High scores indicate fat pitch opportunities.

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| Min asymmetry ratio | 3:1 |
| Dislocation scan trigger | Market/sector drawdown \> 15% |
| Speed premium | Can act at 70% normal conviction if ratio \> 5:1 |
| Floor value method | Lowest of: book value, 0.5× revenue, peer-group min EV/EBITDA |

## **2.7 Framework 7: Conviction-Weighted Position Sizing (Kelly)**

Position Size \= Kelly Fraction × Conviction Multiplier × Available Tier Capital. Uses fractional Kelly for safety margin.

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| Kelly fraction multiplier | Moderate: 0.25, High: 0.35 |
| Min conviction threshold | 40/100 |
| Max single position cap | Moderate: 10% of tier, High: 5% of tier |
| Volatility lookback | 30 days |
| Edge decay factor | 0.95 per day |

## **2.8 Framework Weighting by Tier**

| Framework | Moderate Risk | High Risk |
| :---- | :---- | :---- |
| Greenblatt (quality-value) | 30% | 10% |
| O’Neil (growth quality) | 40% | 40% |
| Weinstein (stage) | Hard gate | Hard gate |
| Event Cascade | Moderate impact | High impact |
| Thorp (asymmetry) | Moderate | Primary trigger |
| Kelly (sizing) | 0.25 multiplier | 0.35 multiplier |

## **2.9 Framework Conflict Resolution**

* Any single framework can trigger a sell. Most conservative (earliest) sell wins.

* Buy requires agreement from at least two frameworks (excluding gates).

* Stage 4 override: forces sell regardless of all other frameworks.

* O’Neil stop-loss: forces sell regardless of fundamentals.

# **3\. Portfolio Structure**

## **3.1 Tier Definitions**

| Tier | Role | Optimise For | Hold Period |
| :---- | :---- | :---- | :---- |
| Moderate Risk | Harvesting Engine – defined profit targets, bank gains, redeploy | Batting average \+ capital turnover | 2 weeks – 3 months |
| High Risk | Asymmetry Engine – trailing stops let winners run | Magnitude of winners | 1 week – 12+ months |

## **3.2 Default Allocation (Cycle-Adjusted)**

| Cycle Score | Moderate | High Risk | Cash Reserve |
| :---- | :---- | :---- | :---- |
| \-2 (despair) | 50% | 50% | 3–5% |
| \-1 | 55% | 45% | 5% |
| 0 (neutral) | 65% | 35% | 7% |
| \+1 | 70% | 30% | 10% |
| \+2 (euphoria) | 75–80% | 20–25% | 12–15% |

## **3.3 Risk Tolerance Profiles**

Owner selects a profile at setup. All downstream parameters set accordingly.

| Parameter | Conservative | Moderate (Default) | Aggressive |
| :---- | :---- | :---- | :---- |
| Mod/High split | 75/25 | 65/35 | 55/45 |
| Cash reserve | 10% | 7% | 5% |
| Moderate profit target | 20% | 25% | 30% |
| Moderate stop-loss | 6% | 8% | 10% |
| Kelly (Mod/High) | 0.15/0.25 | 0.25/0.35 | 0.30/0.40 |
| High-risk ATR multiple | 2.0× | 2.5× | 3.0× |
| Max position (Mod/High) | 8%/4% | 10%/5% | 12%/7% |
| Non-perf review (Mod/High) | 3wk/5wk | 4wk/6wk | 5wk/8wk |
| Max drawdown trigger | 12% | 18% | 25% |

# **4\. Signal Generation Pipeline**

## **4.1 Buy Signal Flow**

1. Cycle Positioning sets portfolio posture and buy threshold.

2. Stage Analysis gate: only Stage 2 stocks pass.

3. CAN SLIM \+ Greenblatt scoring (weighted by tier).

4. Event Cascade timing: phase assessment, over/underreaction check.

5. Asymmetry Score calculated for exceptional opportunities.

6. Kelly sizes the position based on composite conviction and volatility.

7. System executes via API if all gates pass and capital is available.

## **4.2 Sell Signal Triggers**

Any single trigger causes an automated sell. No human review.

| Trigger | Applies To | Timing |
| :---- | :---- | :---- |
| Stop-loss hit | Both tiers | Immediate |
| Trailing stop hit | High risk | Immediate |
| Profit target hit | Moderate | Immediate |
| Stage 4 detected | Both tiers | Immediate |
| Non-performance review failed | Both tiers | Next market open |
| Thesis expired (event-driven) | High risk | Next market open |
| Fundamental criteria degraded below entry threshold | Both tiers | Next hold audit |
| Original thesis invalidated | Both tiers | Immediate |
| Structural negative event | Both tiers | Immediate reassessment |
| Concentration breach (\>150% of cap via appreciation) | Both tiers | Auto-trim |

## **4.3 Signal Types**

| Signal | Meaning | Urgency Levels |
| :---- | :---- | :---- |
| BUY | Opportunity meeting all criteria | Standard / Elevated / Immediate |
| SELL | Exit position | Standard / Elevated / Emergency |
| HOLD | Criteria still met (default state) | N/A |
| WATCH | Conditions developing | Monitor |
| REDUCE | Partial position reduction | Standard / Elevated |
| INCREASE | Add to existing position | Standard / Elevated |

# **5\. Moderate Risk Tier Rules**

## **5.1 Entry Conditions (all must be met)**

* CAN SLIM composite score ≥ threshold (default 60\)

* Stage 2 confirmed

* Greenblatt top quartile OR strong CAN SLIM with earnings acceleration

* No active sell signals from any framework

* Kelly-sized within available tier capital and per-position cap

* Cycle posture permits (not extreme euphoria, or elevated threshold met)

## **5.2 Profit Target**

**ABSOLUTE: Sell automatically when gain reaches target. No exceptions.**

| Parameter | Default |
| :---- | :---- |
| Profit target | 25% gain from entry |
| Volatility adjustment | Target \= base \+ (0.5 × 30-day ATR as %) |
| Execution | Market order when closing price exceeds target |

## **5.3 Stop-Loss**

**ABSOLUTE: Sell automatically when loss reaches stop. No exceptions.**

| Parameter | Default |
| :---- | :---- |
| Stop-loss | 8% below entry |
| Trigger basis | Closing price |
| Gap-down | Sell at first available price |

## **5.4 Non-Performance**

**ABSOLUTE: Auto-assess stagnant positions. Auto-sell if criteria not met.**

| Parameter | Default |
| :---- | :---- |
| Review trigger | 4 weeks with \< 5% gain |
| Hold criteria | ALL entry criteria still met AND active buy/watch signal |
| Sell criteria | Any criterion failed OR no signal OR Stage 1/3 |
| Maximum hold | 12 weeks (unless actively hitting new highs) |

## **5.5 Re-Entry**

**ABSOLUTE: Any re-entry is a completely new trade. Full pipeline evaluation at current price. New stop-loss from new entry. No memory of previous trade.**

# **6\. High Risk Tier Rules**

## **6.1 Entry Conditions (all must be met)**

* Asymmetry Score ≥ 3:1

* At least one supporting framework confirms (Stage 2, CAN SLIM, or Greenblatt)

* No sector/geographic concentration breach

* Kelly-sized with high-risk multiplier within available capital

* Event-driven entries: Event Cascade past Phase 2

## **6.2 Initial Stop-Loss**

| Parameter | Default |
| :---- | :---- |
| Method | 2.5 × 14-day ATR below entry |
| Maximum | 15% below entry |
| Minimum | 5% below entry |

## **6.3 Trailing Stop – Milestone Ratcheting**

**ABSOLUTE: Trailing stops only move upward. Never downward.**

| Gain Reached | Stop Moves To | Effect |
| :---- | :---- | :---- |
| Entry | – 2.5× ATR | Max loss at initial stop |
| \+15% | Breakeven (entry price) | Loss now impossible |
| \+30% | Locks in \+15% | 15% gain guaranteed |
| \+50% | Locks in \+30% | 30% gain guaranteed |
| \>+50% | High minus 1.5–2.0× ATR (trailing) | Follows price upward |

### **Stage Interaction**

| Trigger | Action |
| :---- | :---- |
| Stage 2 → Stage 3 | Tighten stop to 1.0× ATR from highest price |
| Stage 4 detected | Immediate sell regardless of gain |

## **6.4 Non-Performance**

| Parameter | Default |
| :---- | :---- |
| Review trigger | 6 weeks with \< 8% gain |
| Max hold without new highs | 10 weeks |
| Thesis expiry (event-driven) | 8 weeks from entry |

## **6.5 Re-Entry**

**ABSOLUTE: Same as moderate tier. Completely new trade through full pipeline.**

# **7\. Continuous Hold Audit**

*Weekly automated audit on every open position. Test: would this stock generate a buy signal today if not already held?*

| Criterion | Pass | Fail Action |
| :---- | :---- | :---- |
| Stage | Stage 2 | Stage 3: tighten stops. Stage 4: immediate sell. |
| Fundamentals | Score above entry threshold | Below threshold: flag for exit. |
| Original thesis | Still valid | Invalidated: auto-sell. |
| Stop/trailing stop | Price above stop | Hit: immediate auto-sell. |
| Non-performance | Progressing toward target | Review trigger: auto-evaluate per tier rules. |
| Concentration | Within per-position cap | Exceeded: auto-trim to cap. |
| Event risk | No structural negative | Structural negative: immediate reassessment. |

# **8\. News & Event Engine**

## **8.1 Event Classification**

| Dimension | Categories |
| :---- | :---- |
| Scope | Global / Regional / Sector / Company |
| Severity | Normal / Positive Abnormal / Negative Abnormal |
| Duration | Transient / Short-term / Medium-term / Structural |
| Confidence | High / Medium / Low |

## **8.2 Event Types**

* Macro/Geopolitical: rate decisions, fiscal policy, sanctions, trade policy, natural disasters, currency moves

* Sector/Industry: regulation, commodity shocks, technology disruption, consolidation

* Company: earnings, management changes, M\&A, product launches, litigation, credit ratings, insider activity

## **8.3 Entity Resolution Graph**

Maps events to affected entities through relationship layers. Company X depends on supplier Y in country Z. Impact propagates through graph. Default: 2 layers deep.

## **8.4 Parameters**

| Parameter | Default |
| :---- | :---- |
| Source weighting | Equal; tuned over time based on accuracy |
| Event decay rate | Varies by duration classification |
| Corroboration for High confidence | 2 independent sources |
| Watchlist scope | Sector peers \+ configurable watchlist |

# **9\. Rebalancing**

## **9.1 Triggers**

| Trigger | Mechanism | Default |
| :---- | :---- | :---- |
| Drift threshold | Tier allocation deviates from target | 7 percentage points |
| Post-harvest | Check after every moderate tier profit harvest | Automatic |
| Cycle change | Cycle score changes, shifting targets | Any score change |
| Scheduled | Calendar review | Monthly |

## **9.2 Mechanism**

* Prefer directing new deployments to underweight tier over selling overweight positions.

* Severe drift (\>12pp): identify lowest-ranked positions in overweight tier for early exit.

* Rebalancing does not override emergency sell signals.

* Rebalancing does not force entry without a supporting buy signal.

# **10\. Human Governance Model**

## **10.1 Initial Setup Inputs**

| Input | Description |
| :---- | :---- |
| Total active capital | Amount allocated to this system |
| Risk tolerance profile | Conservative / Moderate / Aggressive |
| Market exclusions | Countries, sectors, companies to exclude |
| Currency preference | Base currency and allowed markets |
| Max drawdown tolerance | Portfolio drawdown triggering defensive posture |
| Notification preferences | Delivery channels and frequency |
| Capital addition schedule | Monthly / ad hoc / none |

## **10.2 Human Authority Matrix**

| Human CAN | Human CANNOT |
| :---- | :---- |
| Set risk tolerance and preferences | Override individual trade decisions |
| Add or withdraw capital | Delay stop-loss or profit target execution |
| Update market exclusions | Manually enter trades without system signal |
| Pause system (no new entries; open positions still managed) | Modify parameters of open positions |
| Emergency halt (close all positions, manual restart) | Apply parameter changes retroactively |
| Approve parameter adjustments at monthly review | Disable circuit breakers |
| Request formal structural review of frameworks | Change absolute rules without formal review |

## **10.3 Monthly Review**

System generates report containing: portfolio return vs benchmark, trade summary with win rates by tier, framework effectiveness scorecards, parameter performance analysis, recommended adjustments with supporting data, cycle assessment, and anomaly flags.

## **10.4 Parameter Adjustment Process**

1. System identifies improvement opportunity from rolling performance data.

2. Recommendation presented in monthly review with data and expected impact.

3. Human approves, modifies, rejects, or defers.

4. Approved changes logged, effective from next trade cycle only.

5. System tracks change impact in subsequent reviews.

## **10.5 Structural Changes**

Changes to absolute rules, frameworks, or architecture require: written proposal, backtesting against historical data, 2-week minimum review period, and explicit human approval.

# **11\. Safety Mechanisms**

## **11.1 Circuit Breakers**

| Breaker | Trigger | Response |
| :---- | :---- | :---- |
| Max drawdown | Portfolio at max drawdown from peak (default 18%) | Pause new entries. Existing managed by rules. CRITICAL alert. Resume at 10% recovery or manual unpause. |
| Rapid loss | 3+ stops triggered in single day | Pause new entries 48hrs. Existing continue. |
| Structural Divergence | Euphoria indicators high (+1.5 or above) AND fundamental indicators deteriorating simultaneously (see 11.2) | Accelerated preservation mode: halt new entries, drop profit targets to harvest current gains, tighten all trailing stops, let positions exit through accelerated normal mechanisms over configured window. Applies at portfolio level OR sector level independently. |
| API failure | Unavailable \>1hr during market hours | Queue trades, retry. CRITICAL alert. Broker-side stops maintained. |
| Data feed failure | Stale data beyond threshold | Pause new entries until restored. |
| Concentration breach | Position \>150% of cap via appreciation | Auto-trim to cap. |

## **11.2 Structural Divergence — Accelerated Defensive Exit**

Detects the rare condition where market sentiment/price is extremely elevated but underlying fundamentals are deteriorating. This is the pre-crash signature (e.g., 2000, 2008). Expected frequency: once or twice per decade. Operates at two levels: portfolio-wide (broad market) and sector-specific (individual sector divergence).

### **Detection Criteria (ALL must be met simultaneously)**

| Condition | Indicators | Threshold |
| :---- | :---- | :---- |
| Euphoria (sentiment/price) | Cycle composite ≥ \+1.5, CAPE ratio in top historical decile, margin debt at extremes, IPO/SPAC activity elevated, VIX compressed while leverage high | 3+ euphoria indicators at extreme |
| Fundamental deterioration | Earnings revisions trending negative (\>60% of index constituents), credit spreads widening while equities rise, insider selling accelerating across broad market, yield curve inversion or severe flattening, leading economic indicators declining for 3+ months | 3+ fundamental indicators deteriorating |
| Persistence | Both sides of divergence sustained continuously | 4 consecutive weeks minimum |

### **Sector-Level Detection**

Same divergence logic applied per sector independently. A sector can enter Structural Divergence while the broad market does not. Example: tech sector at extreme valuations with declining earnings revisions while broader market is healthy. Only positions in the affected sector enter accelerated exit.

### **Automated Response Sequence**

1. CRITICAL notification to owner: Structural Divergence detected at \[portfolio/sector\] level.

2. All new entries halted (portfolio-wide or sector-specific).

3. Moderate tier: profit targets reduced by configured amount (default: halved, e.g., 25% → 12.5%) to accelerate harvesting of current gains.

4. High risk tier: all trailing stops tightened to 1.0× ATR regardless of current milestone.

5. Hold audit frequency increased to daily. Lower threshold for hold confirmation.

6. Non-performance review periods halved: moderate 4wk → 2wk, high-risk 6wk → 3wk.

7. Positions currently in profit but below original target are harvested at reduced target as they hit it.

8. Positions at or near breakeven given configured window (default: 2 weeks) before stop tightens to breakeven.

9. Preservation mode continues until divergence resolves (both sides below threshold) or owner manually exits.

### **Parameters**

| Parameter | Default |
| :---- | :---- |
| Euphoria threshold | Cycle composite ≥ \+1.5 AND 3+ euphoria indicators at extreme |
| Deterioration threshold | 3+ fundamental indicators in simultaneous decline |
| Persistence requirement | 4 consecutive weeks |
| Reduced profit target (moderate) | Half of normal target |
| Trailing stop tightening (high-risk) | All stops to 1.0× ATR |
| Hold audit in preservation | Daily (up from weekly) |
| Non-perf review acceleration | Halved (mod: 2wk, high: 3wk) |
| Breakeven window for near-flat positions | 2 weeks |
| Sector-level detection | Enabled independently per sector |
| Resolution criteria | Both euphoria and deterioration indicators return below thresholds |

## **11.3 Broker-Side Stops**

All stop-loss orders placed persistently on broker side where API supports it. Protects against system downtime. If unavailable, system heartbeat check with immediate owner alert on failure.

## **11.4 Notification Priorities**

| Priority | Delivery | Examples |
| :---- | :---- | :---- |
| CRITICAL | Immediate push \+ email | Circuit breaker, Structural Divergence, API failure, system offline |
| HIGH | Push within 15min | Multiple stops, cycle change, significant event |
| STANDARD | Daily digest | Trades executed, rebalancing, non-perf exits |
| INFORMATIONAL | Monthly review only | Framework updates, parameter observations |

# **12\. Performance Tracking**

## **12.1 Tier Metrics**

| Metric | Moderate Target | High Risk Target |
| :---- | :---- | :---- |
| Win rate | \>55% | \>35% |
| Avg gain (winners) | 20–25% | 50%+ |
| Avg loss (losers) | \<8% | \<12% |
| Capital turnover | Higher \= efficient | Lower expected |
| Non-perf exit rate | \<20% | \<25% |
| Reward:risk ratio | \~3:1 | \>4:1 |

## **12.2 Portfolio Metrics**

* Total return vs benchmark (default: S\&P 500 total return)

* Return attribution by tier

* Cycle adjustment effectiveness vs static allocation

* Capital utilisation rate

* Framework effectiveness scorecards: per-framework signal accuracy, contribution, false signal rate

* Override impact (if any pauses/halts occurred)

## **12.3 System Health**

* API uptime and execution latency

* Data feed freshness and completeness

* Signal pipeline performance

* Circuit breaker activation frequency

## **12.4 Trade Attribution**

Every trade tagged with contributing frameworks. Enables: per-framework profitability tracking, false signal analysis, parameter sensitivity measurement, and quarterly effectiveness reporting.

# **13\. Absolute Rules (System-Enforced, No Override)**

1. Stop-loss execution is automatic and immediate when triggered.

2. Trailing stops never move downward.

3. Stage 4 \= immediate sell, no exceptions.

4. Re-entry after any exit \= completely new trade through full pipeline.

5. Every position audited weekly on hold criteria.

6. Moderate profit targets executed automatically when hit.

7. Positions auto-trimmed if exceeding per-position cap.

8. Non-performing positions auto-sold on failed review.

9. Human cannot delay, cancel, or modify individual trades.

10. Parameter changes apply to new trades only, never retroactively.

11. Structural Divergence triggers automatic preservation mode when detected. Cannot be suppressed.

# **14\. Complete Parameter Reference**

| Parameter | Moderate Default | High Risk Default |
| :---- | :---- | :---- |
| Profit target | 25% | N/A (trailing stop) |
| Initial stop-loss | 8% below entry | 2.5× ATR (max 15%, min 5%) |
| Non-perf review trigger | 4 weeks, \<5% gain | 6 weeks, \<8% gain |
| Max hold without new highs | 12 weeks | 10 weeks |
| Thesis expiry | N/A | 8 weeks |
| Kelly fraction | 0.25 | 0.35 |
| Max single position | 10% of tier | 5% of tier |
| Hold audit frequency | Weekly | Weekly |
| Breakeven ratchet | N/A | At \+15% gain |
| Lock-in ratchets | N/A | \+15% locked at \+30%, \+30% locked at \+50% |
| Trailing stop (mature) | N/A | 1.5–2.0× ATR from highest price |
| Stage 3 stop tightening | N/A | 1.0× ATR from highest price |
| Default tier allocation | 65% | 35% |
| Allocation range | 50–80% | 20–50% |
| Volatility adjustment (target) | Base \+ 0.5× ATR% | N/A |
| Rebalance drift threshold | 7 percentage points | 7 percentage points |
| Severe drift threshold | 12 percentage points | 12 percentage points |

# **15\. Position Lifecycle Summary**

## **15.1 Moderate Tier**

1. Signal: automated screening → Kelly sizes position.

2. Entry: API buy order. Broker-side stop at 8%. Target recorded. Clock starts.

3. Monitor: weekly audit. Non-perf review at 4wk if \<5% gain.

4. Exit: target hit → auto-sell OR stop hit → auto-sell OR non-perf failed → auto-sell OR framework violation → auto-sell.

5. Post-exit: capital to tier pool. Re-entry \= new trade only.

## **15.2 High Risk Tier**

1. Signal: asymmetry score \+ supporting framework. Kelly with high-risk multiplier.

2. Entry: API buy order. Broker-side stop at 2.5× ATR.

3. Monitor: weekly audit. Trailing ratchets at \+15%/+30%/+50%. Broker stops updated.

4. Stage watch: Stage 3 → tighten to 1.0× ATR. Stage 4 → immediate sell.

5. Exit: trail hit / initial stop / non-perf / thesis expiry / Stage 4 / emergency → auto-sell.

6. Post-exit: full fresh evaluation for any re-entry.