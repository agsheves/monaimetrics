  
**ACTIVE TRADING SYSTEM**

Part 2: Theoretical Frameworks & Strategy Paradigms

*Named Theories  |  Tunable Parameters  |  Measurable Effectiveness*

**DRAFT  —  For System Development Scoping**

Version 1.0  —  Companion to System Scope Document

# **1\. Introduction: Why Named Theories Matter**

The first document in this series defined what the system does. This document defines why it makes the decisions it makes. Every signal, every position size, every rebalancing decision must be traceable back to a named theoretical framework with tunable parameters and measurable outcomes.

This matters for three reasons. First, when a trade goes wrong, you need to understand which theory failed and whether the failure was in the theory itself or in its parameterisation. Second, when you want to adjust the system’s behaviour, you need to know which lever to pull. Third, when you review performance over time, you need to attribute returns and losses to specific frameworks so you can weight them appropriately.

Each framework in this document follows a consistent structure: the underlying principle (what do we believe and why), the practitioner evidence (who has proven this works and over what period), the system application (how it translates into parameters and signals), the tunable parameters (what the operator can adjust), and the effectiveness metrics (how we measure whether the theory is contributing to performance).

# **2\. Framework 1: Conviction-Weighted Position Sizing**

*Derived from: Kelly Criterion (1956), Elm Wealth Crystal Ball research (2024), Ed Thorp’s practical application at Princeton Newport Partners (1969–1988)*

## **2.1 The Underlying Principle**

Most investors focus almost entirely on what to buy and almost entirely neglect how much to buy. The Elm Wealth Crystal Ball experiment demonstrated this vividly: 118 finance-trained participants were given tomorrow’s front page of the Wall Street Journal and asked to trade stocks and bonds. Half of them lost money and one in six went bust, not because they couldn’t read the news, but because they sized their bets catastrophically. Meanwhile, five veteran macro traders given the same challenge all finished with gains, averaging 130% returns. The difference was almost entirely in bet sizing, not direction-picking.

The Kelly Criterion provides the mathematical foundation: the optimal fraction of capital to allocate to a bet is a function of your edge (expected return) divided by the variance of the outcome. Bet too much relative to your edge and you risk ruin; bet too little and you leave growth on the table. Edward Thorp applied this principle at Princeton Newport Partners, achieving 20% annualised returns over nearly 20 years without a single losing quarter. His core discipline was that no single trade should expose more than a controlled fraction of capital, and that position sizes should scale with conviction, not emotion.

## **2.2 System Application**

Every position the system recommends has an associated conviction score (derived from signal strength and confidence) and an estimated edge (expected return adjusted for probability). Position size is calculated using a modified Kelly formula:

*Position Size \= Kelly Fraction × Conviction Multiplier × Available Tier Capital*

Where the Kelly Fraction is derived from the signal’s expected return and the asset’s volatility, and the Conviction Multiplier is a scaling factor between 0 and 1 based on how many independent signals support the position.

Critically, the system uses Fractional Kelly, not full Kelly. Full Kelly maximises long-term geometric growth but produces extreme volatility along the way. Thorp himself advocated for fractions of Kelly (typically half-Kelly or quarter-Kelly) in practice, as the Kelly Criterion is extremely sensitive to errors in estimating your edge. Since our edge estimates are themselves uncertain, the fractional approach provides a margin of safety.

## **2.3 Tunable Parameters**

| Parameter | Description | Range | Default |
| :---- | :---- | :---- | :---- |
| Kelly fraction multiplier | Fraction of full Kelly to use (half-Kelly \= 0.5) | 0.1 – 1.0 | 0.25 (quarter-Kelly) |
| Minimum conviction threshold | Signal strength below which position size defaults to minimum | 0 – 100 | 40 |
| Maximum single-position cap | Hard cap regardless of Kelly output, per risk tier | 1% – 20% | Low: 15%, Mod: 10%, High: 5% |
| Volatility lookback period | Number of days used to estimate asset volatility for the Kelly calculation | 10 – 120 days | 30 days |
| Edge decay factor | How quickly the estimated edge diminishes as time passes since signal generation | 0.5 – 1.0 per day | 0.95 |

## **2.4 Effectiveness Metrics**

* Average position size relative to Kelly-optimal: are we consistently over- or under-sizing?

* Return contribution per unit of risk: are higher-conviction (larger) positions generating proportionally higher returns?

* Ruin proximity: maximum drawdown of any single position as a percentage of portfolio, and how often this approaches the tier cap

* Conviction calibration: do positions sized at high conviction actually outperform those at low conviction? If not, the conviction scoring needs recalibration, not the Kelly parameters

## **2.5 Key Insight for the System**

*The Crystal Ball study’s most important finding: even with perfect information about future news, bet sizing determined whether participants made or lost money. In our system, we will never have perfect information. This means bet sizing discipline is not just important — it is the primary determinant of whether the system generates capital growth or destroys it.*

# **3\. Framework 2: Cycle Positioning**

*Derived from: Howard Marks / Oaktree Capital — “Mastering the Market Cycle” (2018), “Navigating Cycles” memo series. Marks has co-managed \>$120B with this philosophy.*

## **3.1 The Underlying Principle**

Marks’ central thesis is that investors cannot predict the future but they can assess where they stand in the current cycle and adjust their posture accordingly. Markets swing like a pendulum between euphoria and despair, spending very little time at the rational midpoint. The key insight is that each phase of a cycle causes the next: excessive optimism leads to overvaluation, which leads to correction, which leads to excessive pessimism, which creates undervaluation, which leads to recovery.

Marks identifies several interlocking cycles: the economic cycle, the profit/earnings cycle, the credit cycle (which he considers the most powerful), and the investor psychology cycle. At market peaks, risk appears invisible and capital is readily available. At market troughs, opportunity abounds but fear paralyses action. The system’s role is to assess where we are in each of these cycles and adjust portfolio aggression accordingly.

## **3.2 System Application**

The system maintains a Cycle Position Assessment across four dimensions. Each dimension is scored on a scale that represents the pendulum position: strongly pessimistic (-2) through neutral (0) to strongly euphoric (+2). The composite score determines the system’s overall market posture.

| Cycle Dimension | Indicators Monitored | Pendulum Extremes |
| :---- | :---- | :---- |
| Economic cycle | GDP growth rate vs trend, unemployment trajectory, PMI/manufacturing data, consumer confidence | Euphoric: “Growth will continue forever” Despair: “Recession is permanent” |
| Credit cycle | Credit spreads, lending standards surveys, new debt issuance volume, default rates | Euphoric: Credit window wide open, any borrower gets funded Despair: Credit window slammed shut |
| Investor psychology | VIX / volatility indices, fund flow data, IPO activity, margin debt levels, sentiment surveys | Euphoric: “This time is different” Despair: “I’ll never trust the market again” |
| Valuation cycle | Aggregate P/E vs historical range, CAPE ratio, equity risk premium, market cap to GDP | Euphoric: Valuations detached from fundamentals Despair: Assets priced below liquidation value |

### **3.2.1 Posture Adjustment**

The composite cycle score maps to a portfolio posture that adjusts three things: the target allocation between risk tiers (shifting toward low-risk in euphoria, toward higher-risk in despair), the buy signal threshold (requiring higher conviction to buy in euphoric markets, lower conviction in despair), and the cash reserve target (higher in euphoria to preserve capital, lower in despair to deploy capital into opportunities).

| Composite Score | Market Posture | Risk Tier Shift | Buy Threshold | Cash Reserve |
| :---- | :---- | :---- | :---- | :---- |
| \-2 (extreme despair) | Maximum aggression | Shift 10–15% toward high-risk | Lowered (more willing to buy) | Deploy to minimum (e.g. 3%) |
| \-1 (pessimism) | Lean aggressive | Shift 5–10% toward high-risk | Slightly lowered | Reduce toward 5% |
| 0 (neutral) | Baseline | Target allocations as configured | Standard thresholds | Standard reserve (e.g. 7%) |
| \+1 (optimism) | Lean defensive | Shift 5–10% toward low-risk | Slightly raised | Increase toward 10% |
| \+2 (extreme euphoria) | Maximum defence | Shift 10–15% toward low-risk | Raised (more reluctant to buy) | Build to maximum (e.g. 15%) |

## **3.3 Tunable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Indicator weights | Relative importance of each cycle dimension in the composite score | Equal weight (25% each) |
| Lookback window | Historical period for comparing current indicators to their range | 10 years |
| Posture adjustment magnitude | How aggressively the portfolio shifts at each composite score level | As shown in table above |
| Cycle assessment frequency | How often the composite cycle score is recalculated | Weekly |
| Contrarian delay | Waiting period after an extreme reading before acting (to avoid catching falling knives) | 2 weeks at extremes |

## **3.4 Effectiveness Metrics**

* Cycle assessment accuracy: retrospectively, did the composite score correctly identify cycle extremes within a reasonable margin?

* Posture contribution to returns: did defensive postures during euphoric periods actually reduce losses in subsequent corrections? Did aggressive postures during despair capture recovery gains?

* Timing cost: how much return was sacrificed by the contrarian delay parameter?

# **4\. Framework 3: Stage Analysis for Entry and Exit Timing**

*Derived from: Stan Weinstein — “Secrets for Profiting in Bull and Bear Markets” (1988). One of the most enduring technical frameworks, still actively used by institutional traders.*

## **4.1 The Underlying Principle**

Weinstein observed that every stock moves through four predictable stages in its lifecycle. Stage 1 (Basing): the stock moves sideways after a decline, forming a horizontal base; the 30-week moving average flattens. Stage 2 (Advancing): the stock breaks out above resistance with increased volume; the 30-week MA slopes upward; this is the only stage where you should be buying. Stage 3 (Topping): price action becomes erratic, volume spikes on down days, the 30-week MA flattens again; smart money is distributing. Stage 4 (Declining): the stock breaks below support, the 30-week MA slopes downward; you should not be holding.

The power of this framework is its simplicity and its compatibility with any fundamental analysis. It does not tell you what to buy; it tells you when to buy and when to sell, based on the stock’s position in its own lifecycle. Weinstein’s core rule is absolute: only buy in Stage 2, never hold in Stage 4\.

## **4.2 System Application**

The system classifies every held and watchlisted security into one of the four stages using the 30-week (150-day) simple moving average and volume patterns. This classification acts as a gate on the Signal Generator’s output:

| Stage | System Behaviour | Signal Gate |
| :---- | :---- | :---- |
| Stage 1 (Basing) | Add to watchlist. Monitor for breakout. Do not buy yet. | Buy signals suppressed. Watch signals generated. |
| Stage 2 (Advancing) | This is the buy zone. Signals are active. Hold existing positions. | Buy signals active. Sell signals only from fundamentals or stop-loss. |
| Stage 2 Continuation | Pullback to rising 30-week MA within Stage 2\. Potential add-to-position point. | Increase signals active if fundamentals support. |
| Stage 3 (Topping) | Tighten stops. Prepare to exit. No new buying. | Buy signals suppressed. Sell/Reduce signals elevated priority. |
| Stage 4 (Declining) | Exit all positions. No exceptions. This is Weinstein’s “take the oath.” | Immediate sell signal if any position enters Stage 4\. |

## **4.3 Tunable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| MA period | The moving average period used for stage classification | 30 weeks (150 trading days) |
| Breakout volume threshold | Multiple of average volume required to confirm a Stage 2 breakout | 2x average weekly volume |
| Stage 4 override strictness | Whether Stage 4 detection forces immediate sell or flags for review | Forced sell for High-risk tier; flag for review for Low/Moderate |
| Confirmation period | Number of weeks a stock must remain in a new stage before reclassification is confirmed | 2 weeks |

## **4.4 Interaction with Other Frameworks**

Stage Analysis interacts with Cycle Positioning (Framework 2). During a market-wide cycle in extreme despair, Stage 1 basing patterns are more likely to resolve into Stage 2 breakouts. During euphoria, Stage 3 topping patterns are more common. The system uses the cycle composite score to adjust the probability weighting of stage transitions.

# **5\. Framework 4: Growth Quality Screening**

*Derived from: William O’Neil — CAN SLIM system. Named top-performing investment strategy 1998–2009 by AAII. O’Neil averaged \>40% annually on his investments.*

## **5.1 The Underlying Principle**

O’Neil studied every major stock market winner from 1953 to 2001 and identified seven characteristics they shared before their biggest price advances. The CAN SLIM acronym captures these: Current quarterly earnings growth (minimum 25% year-over-year), Annual earnings growth (minimum 25% over 3–5 years), New products/management/highs (a catalyst), Supply and demand dynamics (volume confirmation), Leader status (relative strength rank above 80), Institutional sponsorship (smart money ownership increasing), and Market direction (is the broad market in an uptrend).

For our system, O’Neil’s framework provides the fundamental screening criteria for identifying growth candidates before they enter the buy zone. His most important contribution beyond stock selection is his strict 7–8% stop-loss rule: if a stock falls 7–8% below your purchase price, you sell without exception. O’Neil found this discipline was as important as the selection criteria themselves.

## **5.2 System Application**

The system applies CAN SLIM criteria as a pre-filter for the Signal Generator. Only stocks that pass a configurable subset of these criteria are eligible for buy signals in the Moderate and High risk tiers. The criteria are scored, not binary, allowing the system to rank candidates.

| CAN SLIM Factor | System Implementation | Scoring |
| :---- | :---- | :---- |
| C – Current Earnings | Quarterly EPS growth rate vs same quarter prior year | 0–100 based on growth %, 0 below 15%, 100 above 50% |
| A – Annual Earnings | 3–5 year compound annual EPS growth rate | 0–100, 0 below 10%, 100 above 35% |
| N – New Catalyst | Detected from news engine: new product, new management, price at 52-week high | Binary flag weighted into composite score |
| S – Supply/Demand | Volume trend: is average volume increasing? | 0–100 based on volume acceleration |
| L – Leader | Relative strength rank vs broad market over 52 weeks | Must be above configurable threshold (default: 70\) |
| I – Institutional | Number and quality of institutional owners, and net buying vs selling | 0–100 composite of quantity, quality, and direction |
| M – Market Direction | Handled by Cycle Positioning framework (Framework 2\) | Not scored individually; acts as master gate |

## **5.3 Key Tunable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Minimum composite CAN SLIM score | Threshold for a stock to be eligible for buy signals | 60 out of 100 |
| Factor weights | Relative importance of each CAN SLIM factor in the composite | C: 25%, A: 20%, N: 10%, S: 15%, L: 20%, I: 10% |
| O’Neil stop-loss percentage | Maximum loss tolerated before automatic sell signal | 8% below purchase price |
| Earnings acceleration requirement | Whether quarterly earnings must show acceleration (increasing growth rate), not just growth | Preferred but not required |

# **6\. Framework 5: Quality-Value Composite Screening**

*Derived from: Joel Greenblatt — “Magic Formula”. Gotham Capital: 50% annualised return 1985–1994. Backtested at 23.8% CAGR vs 9.6% S\&P 500 (1988–2009). Validated across US, European, and Asian markets.*

## **6.1 The Underlying Principle**

Greenblatt’s insight is deceptively simple: buy good companies at cheap prices. “Good” is measured by Return on Capital (EBIT / invested capital), which identifies companies that efficiently convert capital into earnings. “Cheap” is measured by Earnings Yield (EBIT / enterprise value), which identifies companies whose price is low relative to their earnings power. By ranking all eligible stocks on both dimensions and selecting those that score well on both, you systematically find high-quality businesses trading at temporarily depressed valuations.

This framework complements CAN SLIM (Framework 4). While O’Neil focuses on momentum and earnings acceleration (growth stocks breaking out), Greenblatt focuses on quality and value (good businesses at bargain prices). Together, they cover the two primary edges available to an active growth investor: catching growth acceleration early, and buying quality when the market temporarily misprice it.

## **6.2 System Application**

The system calculates Return on Capital and Earnings Yield for all securities in the investable universe and produces a combined ranking. This ranking feeds into the Signal Generator as a “value quality score” that increases the signal strength of buy signals for highly-ranked stocks and decreases it for poorly-ranked ones.

For the Low-Risk tier specifically, the Greenblatt composite is the primary stock selection mechanism. Low-risk positions should be in high-quality, undervalued businesses rather than high-momentum growth stocks.

## **6.3 Key Tunable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| ROC minimum threshold | Minimum return on capital to be eligible | 15% |
| Earnings yield minimum | Minimum earnings yield for consideration | Above market average |
| Sector exclusions | Which sectors to exclude (Greenblatt excludes financials and utilities due to different accounting) | Financials, utilities excluded |
| Reranking frequency | How often the full universe is re-ranked | Monthly |
| Greenblatt weight by tier | How heavily the Greenblatt score influences signals per risk tier | Low: 60%, Mod: 30%, High: 10% |

# **7\. Framework 6: The Event-News-Price Cascade**

*Derived from: Elm Wealth Crystal Ball findings, Ed Thorp’s four sources of market inefficiency, behavioural finance research on information cascades.*

## **7.1 The Underlying Principle**

There is a measurable and exploitable gap between when an event occurs, when news about it reaches the market, how the market initially reacts, and what the actual impact turns out to be. This cascade has distinct phases, each creating different opportunities and risks.

The Elm Wealth study showed that even WSJ front pages from the future were surprisingly poor at predicting same-day market moves. Journalists interpret events through the lens of how markets have already reacted, creating a circular feedback loop. Lloyd Blankfein noted in response to the study that markets frequently don’t react to news as even seasoned experts expect. The implication for our system is that the value of news is not in predicting immediate price moves but in identifying structural shifts that the market has not yet fully priced in.

Thorp identified four sources of market inefficiency: information asymmetry (not everyone gets news at the same time or interprets it the same way), behavioural biases (investors overreact to dramatic news and underreact to slow-moving structural change), institutional constraints (some market participants are forced to sell or buy regardless of fundamentals), and liquidity mismatches (in thin markets, even modest selling pressure creates outsized price moves).

## **7.2 The Cascade Model**

| Phase | Timing | Market Behaviour | System Response |
| :---- | :---- | :---- | :---- |
| 1\. Event occurs | T+0 | No market reaction yet if after hours or if information is not yet public | If detected early: assess severity, prepare but do not act |
| 2\. News breaks | T+minutes to T+hours | Initial reaction, often driven by headlines and algorithms. Frequently an overreaction or underreaction. | Classify the event. Compare initial price move to expected impact. If divergence is large, flag as potential opportunity. |
| 3\. Analysis phase | T+hours to T+2 days | Analysts and institutional investors digest the news. Market may reverse initial reaction or extend it. | Monitor for reversal. If initial move was an overreaction (per our stability algorithms), generate contrarian watch signal. |
| 4\. Consensus forms | T+2 days to T+2 weeks | Market reaches a new consensus. Price stabilises at new level. | If consensus move is smaller than our structural assessment predicted, the market may have underpriced the event. Potential buy or sell signal. |
| 5\. Second-order effects | T+weeks to T+months | Knock-on effects materialise. Supply chain impacts, earnings revisions, competitive dynamics. | This is where structural events create the most value. Monitor for second-order impacts that the market has not yet priced. |

## **7.3 System Application**

For each event classified by the News Engine, the system tracks where in the cascade we are and what the expected behaviour should be at each phase. The key decisions are:

* Do not trade on Phase 1 or early Phase 2 unless the event is an emergency sell trigger. The initial reaction is unreliable and often reverses.

* In Phase 3, assess whether the initial move was proportionate to the event’s severity classification. Overreactions to transient events are potential buy opportunities; underreactions to structural events are potential sell signals.

* In Phase 4, if the market has stabilised but the system’s structural assessment disagrees with the new price, generate a signal with appropriate conviction based on the divergence.

* Phase 5 is where the system should be monitoring for second-order effects that other market participants have missed. The news engine’s entity resolution graph (company X depends on supplier Y, which is in country Z) is the key tool here.

## **7.4 Tunable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Reaction blackout period | Minimum time after news breaks before the system will generate a non-emergency signal | 4 hours |
| Overreaction threshold | Price move vs expected move ratio that triggers a contrarian watch signal | 2x expected move |
| Underreaction threshold | When price move is less than this fraction of expected, flag for structural mismatch | 0.3x expected move |
| Second-order monitoring window | How long the system actively monitors for cascade effects after an event | 30 days for structural events, 7 days for transient |
| Entity propagation depth | How many relationship layers the system follows when assessing indirect impacts | 2 layers (direct suppliers/customers and their dependencies) |

# **8\. Framework 7: Asymmetric Opportunity Recognition**

*Derived from: Ed Thorp’s “fat pitch” philosophy. Princeton Newport Partners: 20% annualised over 20 years, never a losing quarter. Ridgeline Partners: 18.2% annualised 1992–2002.*

## **8.1 The Underlying Principle**

Thorp’s career, from blackjack to Wall Street, was built on a single principle: only play when the odds are in your favour, and when they are, size your bet accordingly. He described the best opportunities as “fat pitches”: situations with asymmetric risk/reward where the downside is bounded but the upside is substantial. These are rare, they typically occur during crises, and they require fast action.

Thorp identified that fat pitches share common characteristics: they arise from market dislocations where forced sellers create artificial price depression, the downside is quantifiable and limited (e.g., the asset has a measurable floor value like scrap value, book value, or acquisition value), the upside is large because the market has temporarily priced in a worst-case scenario that is unlikely to materialise, and other traders will eventually find the opportunity, so speed matters.

## **8.2 System Application**

The system maintains an Asymmetry Score for potential positions, calculated as the ratio of expected upside to expected downside, weighted by probability. When the Asymmetry Score exceeds a configurable threshold and is supported by at least one other framework (e.g., the stock is in Stage 1/early Stage 2 per Weinstein, or is highly ranked by Greenblatt), the system generates an elevated buy signal.

The system also monitors for the conditions that create fat pitches: market-wide drawdowns exceeding a threshold, sector-specific dislocations, forced selling by institutional holders (detectable via unusual volume at depressed prices), and credit market stress creating refinancing fear in fundamentally sound companies.

## **8.3 Tunable Parameters**

| Parameter | Description | Default |
| :---- | :---- | :---- |
| Minimum asymmetry ratio | Ratio of expected upside to expected downside required to flag as a fat pitch | 3:1 |
| Dislocation threshold | Market or sector drawdown magnitude that triggers fat pitch scanning | 15% from recent peak |
| Speed premium | Allowance for executing above normal threshold confidence when asymmetry is very high | Signal can be generated at 70% of normal conviction threshold if asymmetry ratio exceeds 5:1 |
| Floor value methodology | How the system estimates the downside floor (book value, revenue multiple floor, peer floor) | Lowest of: book value, 0.5x revenue, peer-group minimum EV/EBITDA |

# **9\. Framework Integration: How the Theories Work Together**

These seven frameworks are not alternatives; they are layers of a single decision process. Each framework answers a different question:

| Question | Framework | Answer Type |
| :---- | :---- | :---- |
| Is the broad market environment favourable? | Cycle Positioning (Marks) | Portfolio posture: aggressive, neutral, or defensive |
| Is this stock in the right phase of its lifecycle? | Stage Analysis (Weinstein) | Entry/exit gate: should we be buying, holding, or selling? |
| Does this stock have the growth characteristics of a winner? | Growth Quality Screening (O’Neil) | Fundamental eligibility: is this a quality growth candidate? |
| Is this stock both good and cheap? | Quality-Value Composite (Greenblatt) | Value ranking: is quality being offered at a discount? |
| What just happened and what does it mean? | Event-News-Price Cascade | Event interpretation: is the market reaction proportionate? |
| Is there an asymmetric opportunity here? | Asymmetric Opportunity (Thorp) | Opportunity detection: is the risk/reward exceptional? |
| How much capital should we commit? | Conviction-Weighted Sizing (Kelly) | Position size: what bet size matches our edge? |

## **9.1 Signal Generation Flow**

A buy signal flows through the frameworks in sequence. First, the Cycle Positioning framework determines market posture and sets the baseline aggression level. Second, only stocks in Stage 2 (Weinstein) pass through. Third, passing stocks are scored by CAN SLIM (O’Neil) for growth quality and by the Magic Formula (Greenblatt) for quality-value, with weighting varying by risk tier. Fourth, any relevant events from the News Engine are processed through the Event-News-Price Cascade to assess timing. Fifth, the Asymmetry Score is calculated for exceptional opportunities. Finally, the Kelly framework sizes the position based on the composite conviction and estimated edge from all prior steps.

A sell signal follows a different path where any single framework can trigger an exit: Stage 4 entry (Weinstein) forces a sell, O’Neil’s stop-loss triggers a sell, a negative structural event (Cascade Phase 5\) triggers a sell, or Cycle Positioning in extreme euphoria triggers a portfolio-wide tightening. The system uses the most conservative (earliest) sell trigger.

## **9.2 Framework Weighting by Risk Tier**

| Framework | Low Risk Weight | Moderate Risk Weight | High Risk Weight |
| :---- | :---- | :---- | :---- |
| Greenblatt (quality-value) | Primary (60%) | Secondary (30%) | Low (10%) |
| O’Neil (growth quality) | Low (10%) | Primary (40%) | Primary (40%) |
| Weinstein (stage timing) | Applied as gate | Applied as gate | Applied as gate |
| Event Cascade (news) | Low impact | Moderate impact | High impact |
| Thorp (asymmetry) | Moderate | Moderate | Primary trigger |
| Kelly (position sizing) | Conservative (0.15 multiplier) | Standard (0.25 multiplier) | Aggressive (0.35 multiplier) |

# **10\. Measuring Theory Effectiveness Against Portfolio Performance**

## **10.1 Attribution Model**

Every completed trade (entry to exit) is tagged with the frameworks that contributed to the buy signal and the sell signal. Performance attribution then measures: which frameworks were involved in the most profitable trades, which frameworks generated the most false signals, and how parameter adjustments affect outcomes over rolling periods.

## **10.2 Framework Scorecards**

Each framework maintains a rolling scorecard that tracks:

* Signal accuracy: percentage of signals that resulted in profitable outcomes

* Signal contribution: average return of trades where this framework was a primary contributor

* False signal rate: percentage of signals that were acted upon but resulted in losses

* Opportunity cost: identifiable cases where the framework’s gate or threshold prevented a profitable trade

* Parameter sensitivity: how much outcomes changed when parameters were adjusted

## **10.3 Theory Refinement Process**

On a configurable schedule (e.g., quarterly), the system generates a Theory Effectiveness Report. This report identifies which frameworks are contributing most to returns, which are generating excessive false signals, and where parameter adjustments might improve performance. The human operator reviews this report and decides whether to adjust parameters, change framework weights, or leave the system as-is. All changes are logged and their subsequent impact tracked.

## **10.4 The Critical Rule**

*The system never adjusts its own parameters automatically. The human operator reviews effectiveness data and makes deliberate, logged adjustments. This prevents overfitting to recent conditions and ensures the operator understands why the system behaves as it does. The theories are fixed; the parameters are tunable; the weightings are adjustable; the decision to change any of these is human.*

# **11\. Additional Considerations Raised by These Frameworks**

## **11.1 Survivorship Bias Awareness**

All the systems referenced here (CAN SLIM, Magic Formula, Stage Analysis) have been backtested on historical data that includes survivorship bias. The system should track its own live performance against these theoretical backtested returns and expect some degradation. If live performance falls below a configurable fraction of backtested expectations (e.g., 60%), the relevant framework should be flagged for review.

## **11.2 Regime Detection**

These frameworks were developed and tested primarily in specific market regimes (mostly US equity markets in the late 20th and early 21st century). The system should maintain awareness of whether current market conditions are within or outside the regimes where these frameworks have proven track records. A prolonged zero-interest-rate environment, for example, fundamentally changes the credit cycle dynamics that Marks’ framework relies on.

## **11.3 Framework Conflicts**

The frameworks will sometimes disagree. Greenblatt might rank a stock highly (good and cheap), but Weinstein might show it in Stage 4 (declining). O’Neil might love its earnings growth, but the Event Cascade might show a structural negative event. The system’s resolution rule is: sell signals from any framework override buy signals from all other frameworks. In the absence of sell signals, the system requires agreement from at least two frameworks to generate a buy signal.

## **11.4 Structural Divergence: When Euphoria and Fundamentals Diverge**

The Cycle Positioning framework assesses the market pendulum between euphoria and despair, but there is a specific and rare condition that warrants separate treatment: when euphoria indicators are at extreme levels but fundamental indicators are simultaneously deteriorating. This is the pre-crash signature observed before major market collapses (2000, 2008\) where prices continued rising while the foundations were cracking underneath.

This divergence is detectable through the system’s existing frameworks: Cycle Positioning shows extreme euphoria on sentiment indicators while the CAN SLIM earnings screening shows deteriorating fundamentals across broad swathes of the market, credit spreads are widening even as equities rise, and insider selling is accelerating. When the system detects this divergence at sufficient magnitude, it triggers an accelerated preservation mode that systematically moves the portfolio toward cash through tightened stops and reduced profit targets, rather than a single panic sell-off.

This mechanism operates at both portfolio level (broad market divergence) and sector level (a specific sector may show divergence while the broader market does not). It is expected to trigger rarely — once or twice per decade — and is documented in detail in Part 3: Operating Discipline under Safety Mechanisms.

## **11.5 Emotional Discipline as a System Design Principle**

The recurring theme across all these practitioners is that emotional discipline matters more than analytical sophistication. The Crystal Ball study showed that information advantage without sizing discipline is worthless. Marks writes that the greatest profits come from buying when everyone else is fearful, which requires courage. Weinstein’s Stage 4 rule is an emotional discipline tool: sell, no exceptions. O’Neil’s 8% stop-loss is the same. The system is designed to enforce these disciplines mechanically, removing the emotional component from the human operator’s role as much as possible.