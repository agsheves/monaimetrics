# Optimum Trading Bot -- Workplan

## Ralph Wiggum Rules: one thing at a time, keep it simple, don't be clever

---

## Design Philosophy

This system is a **slower-tempo retail adaptation of the Renaissance Capital approach**: be agnostic about any individual stock, scan for temporary mispricings driven by fundamentals or news, buy in, take the statistical edge, cash out, repeat. The edge comes from **many small, uncorrelated bets** -- not from picking winners.

If a stock continues to meet entry criteria after we sell, we buy it again as a completely new trade through the full pipeline. No memory, no attachment, no "thesis" that keeps us in a losing position.

**KISS is the organising principle.** One engine. One pipeline. Clear rules. Complex systems have many ways to go wrong. We add complexity only after the simple version is making money.

### Seven Optimisation Principles

These are baked into the design at every level, not bolted on as afterthoughts:

1. **The scan IS the edge.** Don't scan 150 random stocks and hope. Dynamically build today's universe from where the edge is right now: earnings, news, volume spikes, oversold Stage 2 names.
2. **Rank, don't just pass/fail.** Every passing candidate gets ranked by conviction. Only buy the top N needed to fill the portfolio. Always hold the best available opportunities, not "good enough" ones.
3. **No price cap.** Alpaca supports fractional shares. Excluding stocks above $25 kills the universe. AAPL, NVDA, MSFT are the most liquid, most news-responsive names in the market. Include everything.
4. **Tighter ratchets for tighter targets.** 5% ratchet steps are too wide for a system targeting 3-6% gains. Use 3% steps so a stock at 4% gain already has its stop at breakeven.
5. **Size for gap risk.** We can't trade after hours. Stocks that routinely gap 3% overnight are more dangerous than ones that gap 0.5%. Position sizing should reflect this.
6. **Use pre-market data.** Alpaca provides pre-market quotes. A stock that gapped down 4% pre-market shouldn't get a buy signal based on yesterday's close.
7. **Earnings calendar as timing tool.** Don't just trade AFTER earnings (PEAD). Position BEFORE known earnings when technicals are already favorable -- the volatility expansion creates the movement we need.

---

## Constraints

| Constraint | Detail |
|---|---|
| Broker | Alpaca (margin account only) |
| PDT rule | 3 same-day round-trips per rolling 5 business days (account under $25k) |
| Trading hours | 09:30-16:00 ET, Mon-Fri. No after-hours execution |
| Weekend gap risk | No ability to exit positions after Friday close until Monday 09:30 |
| Data sources | Alpaca (bars, quotes, news), AlphaVantage (fundamentals, earnings, news), Decis (newsfeed) |
| Compute | Replit -- no GPU cluster, no HFT infrastructure |
| Options | Alpaca Level 1-3 (covered calls, long calls/puts, vertical spreads). No calendar spreads as multi-leg |
| Account size | Under $25k initially |

---

## Return Expectations

5% weekly = 1,164% annualised. Renaissance Medallion, the most successful quant fund in history (150 PhDs, 20x leverage, 150,000 trades/day), averages ~66% gross annually. They do not hit 5% weekly sustained.

**Target: 1-2% weekly average (50-100% annualised).** Some weeks will be 5%+. Some will be negative. The edge is statistical over months, not any single week. Designing for a realistic target produces a better system than designing for a fantasy one -- chasing 5%/week forces concentration and risk that blows up accounts.

---

## APIs & Data Feeds Required

### Trading & Market Data

| API | Provider | What It Provides | Used For | Auth | Status |
|---|---|---|---|---|---|
| **Trading API** | Alpaca | Order submission, position management, account info | All trade execution, portfolio sync | `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` | Working |
| **Market Data API** | Alpaca | Daily OHLCV bars, snapshots, pre-market quotes | Technical indicators, stage analysis, RSI, gap risk scoring, pre-market filter | Same as trading | Working |
| **News API** | Alpaca | Headlines + summaries for traded symbols | Negative filter (Gate 3), conviction modifier, accelerated exit trigger | Same as trading | Available, not yet wired |
| **Asset List API** | Alpaca | Universe of tradeable US equities with sector/industry | Volume spike scanning, universe construction | Same as trading | Working |

### Fundamental & Earnings Data

| API | Provider | What It Provides | Used For | Auth | Status |
|---|---|---|---|---|---|
| **Earnings Calendar** | AlphaVantage | Upcoming and recent earnings report dates | Dynamic universe builder, earnings proximity scoring, PEAD timing | `ALPHAVANTAGE_API_KEY` | Key exists, not yet wired |
| **Earnings Surprise** | AlphaVantage | Actual vs estimated EPS, surprise magnitude | PEAD conviction boost (post-earnings drift) | Same as above | Key exists, not yet wired |
| **Company Overview** | AlphaVantage | Sector, industry, market cap | Sector concentration tracking, sector momentum | Same as above | Key exists, not yet wired |

### News & Geopolitical

| API | Provider | What It Provides | Used For | Auth | Status |
|---|---|---|---|---|---|
| **Decis Country Info** | Decis | Geopolitical stability indices, sector news | Sector-level catalyst detection, alpha signals | `DECIS_API_KEY` + `DECIS_BASE_URL` | Configured, keys needed |
| **Groq LLM** | Groq (Llama) | Fast text classification | News sentiment classification (POSITIVE/NEGATIVE/NOISE) | `GROQ_API_KEY` | Working |

### Optional / Future

| API | Provider | What It Provides | Used For | Auth | Status |
|---|---|---|---|---|---|
| **Claude API** | Anthropic | Advanced reasoning | Audit QA analysis, complex event interpretation | `ANTHROPIC_API_KEY` | Configured, not active |
| **Kalshi** | Kalshi | Prediction market data | Separate arbitrage system (not part of this bot) | `KALSHI_API_KEY` | Working (separate system) |
| **Sentiment API** | TBD | News sentiment scoring | Could replace Groq classification if dedicated service preferred | `SENTIMENT_API_KEY` | Placeholder only |

### API Rate Limits & Caching Strategy

| API | Rate Limit | Caching |
|---|---|---|
| Alpaca Market Data | 200 requests/minute (free tier, IEX feed) | Bar data cached per cycle; snapshots refreshed each 15-min cycle |
| Alpaca News | Included in data plan | Cached with 60-minute TTL per symbol |
| AlphaVantage | 25 requests/day (free), 75/min (premium) | Earnings calendar cached daily; surprise data cached per symbol per day |
| Decis | TBD (depends on plan) | Cached with 60-minute TTL |
| Groq | 30 requests/minute (free tier) | Classification results cached with 60-minute TTL per symbol |

**Note on AlphaVantage:** The free tier (25 calls/day) is tight for a system scanning 50-100 symbols. Premium ($50/month for 75 calls/min) is strongly recommended. Alternatively, earnings calendar data can be fetched once daily (1 call) and earnings surprise data fetched only for stocks in the dynamic universe (10-20 calls/day), which fits within free tier limits if managed carefully.

---

## Architecture: One Engine, Three Inputs

```
┌────────────────────────────────────────────┐
│              SIGNAL INPUTS                  │
│                                            │
│  Stock Data ────┐                          │
│  (primary,      │                          │
│   proven)       ├──► CONVICTION SCORE      │
│                 │    (0-100)               │
│  News ──────────┤                          │
│  (filter +      │                          │
│   modifier)     │                          │
│                 │                          │
│  Earnings ──────┘                          │
│  (boost for                                │
│   PEAD)                                    │
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│              ENTRY GATES                    │
│                                            │
│  1. Stage 2?                               │
│  2. Volume >= 2x average?                  │
│  3. No negative catalyst?                  │
│  4. Minimum conviction?                    │
│  5. RSI(2) context (mean-reversion boost)  │
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│              EXECUTION                      │
│                                            │
│  Kelly sizing ──► Bracket order            │
│  (auto-calibrated   (entry + GTC stop)     │
│   from real data)                          │
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│              EXIT RULES                     │
│                                            │
│  3% hard stop (immediate)                  │
│  Ratcheting stop at 3% milestones          │
│  Non-performance (5 days, <2% gain)        │
│  Thursday lock-in (>=5% gain)              │
│  Friday close-out (everything, no exceptions)│
│  10 calendar day max hold                  │
│  Negative news catalyst (accelerated exit) │
│  Stage 4 decline (emergency)               │
└────────────────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│              QA/QC FEEDBACK                 │
│                                            │
│  Track every trade                         │
│  Weekly performance analysis               │
│  Auto-calibrate Kelly inputs from results  │
│  Surface recommendations for human review  │
└────────────────────────────────────────────┘
```

---

## Dynamic Universe Builder

The old system scanned a static list of ~150 liquid stocks under $25/share. This is wrong. The universe should be **dynamically constructed each cycle** based on where the edge is today. No price cap -- Alpaca supports fractional shares.

### Universe Sources (Run Each Cycle)

| Source | What It Surfaces | Why |
|---|---|---|
| **Earnings calendar** (AlphaVantage) | Stocks reporting this week + stocks that reported in last 5 trading days | PEAD is strongest 1-10 days post-earnings. Pre-earnings positioning captures volatility expansion |
| **News feed** (Alpaca + Decis) | Stocks with breaking catalysts today | Event-driven moves happen now, not on a stale watchlist |
| **RSI(2) screener** | Stage 2 stocks where RSI(2) just dropped below 25 | Mean-reversion setups are time-sensitive -- today's oversold is tomorrow's bounce |
| **Volume spike scanner** | Stocks with 3x+ average volume today | Unusual volume precedes or accompanies institutional moves |
| **Recent winners** | Stocks we profitably traded last week that still meet Stage 2 | Re-entry on proven setups (stock-agnostic but pattern-aware) |
| **Sector momentum** | Top 3 sectors by weekly performance | Simple bias toward where money is flowing |

### Universe Construction

```
Each 15-minute cycle:
  1. Fetch earnings calendar → add to universe
  2. Fetch news headlines → extract mentioned symbols → add to universe
  3. Scan Alpaca asset list for volume spikes (3x+) → add to universe
  4. Compute RSI(2) for existing watchlist → add oversold Stage 2 names
  5. Add symbols from last week's profitable trades that are still Stage 2
  6. Deduplicate
  7. Fetch technical data for combined universe
  8. Run entry pipeline on all candidates
  9. Rank by conviction, buy top N
```

The universe will vary in size day to day. During earnings season, it could be 50+ names. On a quiet Tuesday, maybe 20. That's fine -- we only need 8-15 positions, and quality > quantity.

### No Price Cap

The old `max_share_price_usd = 25.0` is removed. With fractional shares and Kelly sizing, a $20k portfolio can buy $1,600 of NVDA at $800 just as easily as $1,600 of a $15 stock. The price cap excluded the most liquid, most news-responsive, most analyst-covered stocks in the market. Including them dramatically expands the opportunity set.

---

## Entry Decision (Single Pipeline)

Every candidate passes through the same sequence. No tiers, no separate engines.

### Gate 0: Pre-Market Sanity Check

Before evaluating any candidate at the first cycle of the day, check pre-market price movement via Alpaca pre-market quotes. If a stock has gapped down > 2% from prior close in pre-market, skip it for this cycle -- the technical data from yesterday's close is stale and the setup may be invalidated. Re-evaluate on the next cycle when intraday data is available.

This is a simple guard that prevents entering positions based on yesterday's data when overnight conditions have materially changed.

### Gate 1: Stage 2 Required

Stock must be in Weinstein Stage 2 (advancing) -- price above rising 150-day MA. This is the existing filter and it works. Stage 1 = watch, Stage 3/4 = skip.

### Gate 2: Volume Confirmation

Current volume must be >= 2x 50-day average volume. Confirms institutional participation. Already computed from Alpaca bar data.

### Gate 3: No Negative Catalyst

Check news feeds (Alpaca News API, Decis) for the symbol and its sector. If there's a negative catalyst (earnings miss, regulatory action, fraud, downgrade), block entry. Simple positive/negative/noise classification via Groq LLM.

This is the **safety filter**, not a signal source. It prevents buying into oversold stocks that are oversold for good reason.

### Gate 4: Conviction Scoring

Combine available signals into a single 0-100 score:

| Input | What It Measures | Weight |
|---|---|---|
| Technical score | Stage strength, momentum, volume ratio | 40% (base, proven) |
| RSI(2) context | Mean-reversion opportunity if oversold | 20% |
| News sentiment | Positive catalyst present | 15% |
| Earnings context | Recent beat OR upcoming report | 15% |
| Earnings calendar proximity | Known catalyst approaching | 10% |

Minimum conviction to enter: 40/100 (configurable).

**On RSI(2) mean reversion:** When RSI(2) < 25 on a Stage 2 stock, this is an oversold dip in an uptrend -- the highest-probability mean-reversion setup. Backtested at 73% win rate across 146,000+ parameter combinations. This boosts conviction significantly. When RSI(2) is neutral (25-75), this component scores 50 (no boost, no penalty). This is not a separate engine -- it is an input to the same scoring pipeline.

**On news as a conviction modifier:** A positive catalyst (earnings beat, contract win, sector tailwind) adds up to 15 points to the conviction score. No positive news = no boost, no penalty. The stock-data signal must be there first; news just strengthens it.

**On earnings (PEAD):** A stock that beat earnings estimates within the past 10 trading days gets a conviction boost proportional to the surprise magnitude. This exploits post-earnings announcement drift -- one of the most persistent market anomalies for small/mid-cap stocks. Sourced from AlphaVantage earnings data.

**On earnings calendar look-ahead:** A stock that already meets technical criteria (Stage 2, volume confirming) AND has earnings scheduled within 1-3 trading days gets a conviction boost. This is NOT earnings gambling -- we still have the 3% stop. We are buying a stock that already passes our filters, with a known volatility catalyst approaching. The implied volatility expansion around earnings creates exactly the kind of price movement this system harvests. If earnings disappoint, the 3% stop limits damage. If they beat, we capture the PEAD drift for the rest of the week.

Scoring for earnings calendar proximity:
- Earnings in 1-3 trading days + Stage 2 + volume: +10 points (volatility catalyst approaching)
- Earnings in 4-5 trading days: +5 points (positioning early)
- No upcoming earnings: 0 (neutral, no penalty)
- Do NOT enter the day of or day before earnings unless conviction is >= 60 (the gap risk is real)

### Gate 5: Position Sizing (Kelly + Gap Risk)

If conviction passes the minimum threshold:

```
kelly_f = win_prob - ((1 - win_prob) / win_loss_ratio)
base_size = kelly_f * 0.25 * available_capital
gap_adjusted_max = max_position * gap_risk_factor
position_size = min(base_size, gap_adjusted_max * portfolio_value)
```

Where:
- `win_prob` = confidence / 100 (initially estimated, later calibrated from actual trade data)
- `win_loss_ratio` = avg_win / avg_loss (initially 0.05 / 0.03 = 1.67, later calibrated)
- `0.25` = quarter-Kelly fraction (conservative, captures ~75% of optimal growth with ~50% less drawdown)
- `gap_risk_factor` = scaling factor based on historical overnight gap volatility (see below)

If Kelly sizes to zero or negative, the edge isn't there. Skip.

**Gap risk adjustment:** We cannot trade after hours. A stock that routinely gaps 3% overnight is more dangerous than one that gaps 0.5%, because our stop-loss cannot fire during the gap. The system computes a gap risk score from the last 30 trading days:

```
avg_abs_gap = mean(abs(open[i] - close[i-1]) / close[i-1] for i in last 30 days)

gap_risk_factor:
  avg_abs_gap < 0.5%  → 1.00 (full position size allowed)
  avg_abs_gap 0.5-1.0% → 0.85
  avg_abs_gap 1.0-2.0% → 0.70
  avg_abs_gap 2.0-3.0% → 0.55
  avg_abs_gap > 3.0%   → 0.40 (high-gap stocks get 40% of normal max size)
```

This is computed from existing daily bar data (no new API calls). A stock like NVDA with large overnight gaps gets smaller positions. A stable utility stock gets larger positions. The 3% stop still applies, but the position is sized so that a gap-through-stop event causes proportionally less portfolio damage.

---

## Exit Rules (Complete, Priority Order)

| # | Rule | Trigger | Priority | Notes |
|---|---|---|---|---|
| 1 | Stage 4 decline | Price below falling 150-day MA | EMERGENCY | Hardest rule, no exceptions |
| 2 | Hard stop | 3% below entry (closing price) | EMERGENCY | Broker-side GTC order, survives system downtime |
| 3 | Ratcheting stop | Price drops below locked milestone | IMMEDIATE | 3% milestones: entry*1.03^n. Stop ratchets up, never down |
| 4 | Negative news | Material negative catalyst on held position | ELEVATED | LLM classification, accelerated exit |
| 5 | Non-performance | Held 5+ calendar days with < 2% gain | STANDARD | Capital isn't working, redeploy elsewhere |
| 6 | Thursday lock-in | Thursday close, position >= 5% gain | STANDARD | Sell to lock in, or tighten ratchet stop to protect gains into Friday |
| 7 | Friday close-out | Friday 15:30 ET | STANDARD | Sell everything. No exceptions. Zero weekend exposure |
| 8 | Max hold | 10 calendar days | STANDARD | Position has had its chance, move on |
| 9 | Concentration | Position > 8% of portfolio | STANDARD | Trim excess to restore sizing limits |

### Thursday/Friday Logic Detail

- **Thursday close**: Positions at >= 5% gain are evaluated. Either sell to lock in the profit, or tighten the ratcheting stop to a close level (e.g., 1.5% below current instead of the standard 3% milestone) to protect gains while allowing a Friday continuation. This decision can be rule-based: if the gain is 5-7%, tighten and hold; if the gain is > 7%, lock in.
- **Friday**: All positions sold by 15:30 ET. Any stragglers get market orders at 15:55 ET. The system enters the weekend **flat with zero exposure**. This eliminates weekend gap risk entirely and forces capital recycling.

### Why No Fixed Profit Target

The original design used limit orders at the profit target (15% moderate, none for high-risk). The new system removes this entirely. Reasons:
- A fixed target caps upside on the best trades (a stock that jumps 10% in a week should capture all of that, not sell at 5%)
- The ratcheting stop locks in gains dynamically as the position runs
- The Friday close-out provides the hard deadline
- This means winners run intraweek while losers are cut at 3%

The 5% number is not a sell target -- it is the **minimum acceptable return threshold** for the Thursday decision and the QA/QC performance measurement.

---

## Portfolio Structure

| Parameter | Value |
|---|---|
| Max single position | 8% of portfolio |
| Target open positions | 8-15 at any time |
| Max concurrent positions | 20 |
| Capital deployment | 85-90% actively deployed |
| Dry powder reserve | 10-15% for immediate deployment on high-conviction setups |
| Position sizing | Kelly (quarter-fraction) * conviction * available capital |

**No tiers.** Every position follows the same rules. The old moderate/high-risk distinction is removed. Risk is managed through position sizing (Kelly naturally sizes smaller when the edge is less certain), gap-risk adjustment, and the universal 3% stop.

**Ranking, not pass/fail.** When multiple candidates pass all gates, they are ranked by conviction score and only the top N needed to fill the portfolio are bought. If we have 10 open positions and want 12-15, we buy the top 2-5 candidates from the ranked list, not every stock that clears the 40-point minimum. This ensures the portfolio always holds the best available opportunities.

---

## Execution Rhythm

### Monday-Thursday (Every 15 Minutes, 09:30-16:00 ET)

```
1. Sync positions from broker (current prices, quantities, stop order status)
2. Pre-market check (first cycle of the day only):
   a. Fetch pre-market quotes for all held positions + watchlist
   b. Flag any held positions that gapped down > 2% for priority review
   c. Exclude candidates that gapped down > 2% from entry consideration this cycle
3. Check stops:
   a. Hard stop: 3% below entry → SELL EMERGENCY
   b. Ratcheting stop: update if price hit new 3% milestone
   c. Verify broker-side GTC stop orders exist for every position
      (re-place if missing -- fixes Issue #10)
4. Check time-based exits:
   a. Non-performance: held 5+ days, <2% gain → SELL
   b. Max hold: 10 calendar days → SELL
5. Check news:
   a. Fetch recent news for held positions
   b. Negative catalyst on held position → SELL ELEVATED
6. Build dynamic universe:
   a. Earnings calendar: stocks reporting this week + reported last 5 days
   b. News feed: extract symbols from Alpaca + Decis headlines
   c. Volume spikes: scan for 3x+ average volume today
   d. RSI(2) screener: Stage 2 stocks with RSI(2) < 25
   e. Recent winners: last week's profitable exits still in Stage 2
   f. Deduplicate all sources into candidate list
7. Evaluate + rank candidates:
   a. Fetch technical data for universe
   b. Run entry pipeline (gates 0-5) on all candidates
   c. Rank passing candidates by conviction score
   d. Buy top N needed to fill portfolio (target 8-15 positions)
   e. Apply gap-risk adjustment to position sizes
8. Track PDT usage (decrement slots on same-day round-trips)
9. Log everything
```

### Thursday Close (15:45-16:00 ET)

```
For each position with >= 5% gain:
  - If gain 5-7%: tighten ratcheting stop to 1.5% below current (tighter than normal 3% step)
  - If gain > 7%: sell to lock in profits
For each position with < 2% gain held 4+ days:
  - Sell (early non-performance exit before Friday)
```

### Friday (Full Day + Close-Out)

```
Morning (09:30-14:00):
  - Normal 15-minute cycles, but buy only on ultra-high conviction
  - More conservative: require conviction >= 60 (vs 40 normal) for Friday entries
  
Close-out (15:30 ET):
  - Sell all remaining positions at market
  
Stragglers (15:55 ET):
  - Market orders on anything still open
  
End state: FLAT. Zero exposure over the weekend.
```

### Saturday (Automated, Off-Market)

```
1. QA/QC engine runs weekly analysis
2. Update Kelly inputs from actual trade performance
3. Generate human-readable performance report
4. Build Monday universe:
   a. Fetch next week's earnings calendar (AlphaVantage)
   b. Identify stocks reporting Mon-Wed (prime PEAD + look-ahead candidates)
   c. Scan for Stage 2 stocks with RSI(2) < 30 on Friday close
   d. Compute gap-risk scores for all watchlist candidates
   e. Flag recent profitable exits that are still Stage 2 (re-entry candidates)
5. Build news/event queue for next week (known catalysts, sector events)
```

---

## PDT Management

Alpaca is margin-only. Under $25k = 3 same-day round-trips per rolling 5 business days.

### How 15-25 Trades/Week Works With PDT

PDT only restricts **same-day** round-trips. The weekly cycle is inherently multi-day:

- Monday buys sold Tuesday+ = NOT a day trade
- Tuesday buys sold Wednesday+ = NOT a day trade
- Thursday close-outs on positions held since Monday-Wednesday = NOT day trades
- Friday close-out on anything held 1+ days = NOT day trades

**PDT slots are consumed only when**: a position is opened and closed on the same calendar day. This happens when:
- A stock gaps up on open, hits 5%+ immediately, and we want to capture it same-day
- A stock hits the 3% stop on the same day we bought it

### PDT Tracking

```
PDT_SLOTS_MAX = 3
pdt_rolling_window = 5 business days

On each potential same-day exit:
  if slots_used_in_window >= PDT_SLOTS_MAX:
    → hold overnight, sell next trading day
  else:
    → execute same-day exit, increment counter
```

Reserve PDT slots for highest-conviction same-day exits. Everything else holds overnight minimum.

---

## News Integration

News serves three roles, in order of priority:

### Role 1: Negative Filter (Safety)

Before entering any position, check news for the symbol and sector. Block entry on material negative catalysts. This prevents buying oversold stocks that are oversold for legitimate reasons.

Implementation:
- Fetch headlines from Alpaca News API + Decis feed for the candidate symbol
- Pass through Groq LLM with a simple prompt: classify as POSITIVE / NEGATIVE / NOISE
- NEGATIVE → block entry, add to exclusion list for the current cycle
- Use cached classifications with 60-minute TTL to avoid redundant API calls

### Role 2: Conviction Modifier (Entry)

Positive news boosts the conviction score by up to 15 points. A stock with strong technicals AND a positive catalyst is more likely to move in our direction within the week.

Implementation:
- Same classification pipeline as Role 1
- POSITIVE → add configurable boost (default: +10 points, max +15) to conviction score
- The technical signal must be there first; news amplifies, it does not create the signal

### Role 3: Accelerated Exit (Held Positions)

If negative news breaks on a held position, accelerate the exit to ELEVATED priority regardless of current P&L.

Implementation:
- On each 15-minute cycle, check news for all held positions
- New NEGATIVE classification since last check → generate SELL signal with ELEVATED urgency
- This catches situations where the stop-loss hasn't triggered yet but the thesis is broken

### News Sources

| Source | Data Available | Primary Use |
|---|---|---|
| Alpaca News API | Headlines + summaries for traded symbols | Per-symbol catalyst detection |
| AlphaVantage | Earnings calendars, earnings surprise data | PEAD conviction boost |
| Decis | Geopolitical/sector news feed | Sector-level catalyst detection |

---

## Risk Management

### Position Level

| Control | Value |
|---|---|
| Hard stop-loss | 3% below entry (GTC broker-side order) |
| Ratcheting stop | 3% gain milestones, stop only moves up |
| Max position size | 8% of portfolio (adjusted down by gap-risk factor) |
| Max hold period | 10 calendar days |
| Friday close-out | Everything sold, zero weekend exposure |

### Portfolio Level

| Control | Threshold | Action |
|---|---|---|
| Weekly drawdown | 5% in a rolling week | Halt new entries, close weakest positions |
| Monthly drawdown | 12% in a rolling month | All activity paused, emergency sells only |
| Rapid loss | 3+ stops hit in single day | 48-hour new-entry pause |
| Sector concentration | > 3 positions in same sector | Block new entries in that sector |
| Total position count | > 20 open positions | Block new entries |
| Data staleness | > 60 minutes without update | Pause until data restored |
| Stage 4 detection | Any held position enters Stage 4 | Immediate sell, no exceptions |

### Circuit Breaker Recovery

When a portfolio-level circuit breaker fires:
- Emergency sells (stop-loss, Stage 4) still execute
- New buys blocked until condition clears
- Weekly drawdown: resumes next Monday (fresh week)
- Monthly drawdown: requires positive week before resuming
- Rapid loss: automatic 48-hour cooldown

---

## QA/QC Engine

### What It Records (Every Trade)

```
{
  symbol: str
  entry_date: datetime
  exit_date: datetime
  hold_days: int
  entry_price: float
  exit_price: float
  gain_loss_pct: float
  entry_conviction: int
  conviction_rank: int            # where this candidate ranked among all passing candidates
  entry_signal_source: str        # "technical", "technical+news", "technical+earnings"
  universe_source: str            # "earnings_calendar", "news_feed", "rsi_screener",
                                  #  "volume_spike", "recent_winner", "watchlist"
  exit_reason: str                # "stop", "ratchet", "friday_close", "non_performance",
                                  #  "max_hold", "news_exit", "stage4", "thursday_lockin"
  position_size_usd: float
  position_pct_of_portfolio: float
  gap_risk_factor: float          # the gap-risk adjustment applied at entry
  sector: str
  pdt_slot_used: bool
  had_earnings_in_hold_period: bool
}
```

Stored as JSONL in `data/trade_log.jsonl`. One line per completed trade. Append-only.

### Weekly Analysis (Saturday Automated Run)

Computed over the trailing 30 completed trades (minimum sample for any auto-adjustment):

| Metric | Purpose |
|---|---|
| Win rate (overall) | Is the edge real? |
| Win rate by signal source | Are news/earnings inputs helping? |
| Win rate by universe source | Which scan sources produce the best trades? |
| Average win % vs average loss % | Is asymmetry correct? |
| Win rate by exit reason | Which exits are capturing gains vs cutting winners? |
| Win rate by day of entry | Are certain days better for entries? |
| Win rate by sector | Should we avoid certain sectors? |
| Win rate by conviction rank | Are top-ranked candidates actually better? |
| Friday close-out P&L impact | How much value does the weekly cycle add/lose? |
| Average hold duration (winners vs losers) | Are we holding losers too long? |
| Conviction accuracy | Do higher-conviction trades actually win more? |
| Portfolio heat (avg % of capital at risk) | Are we over/under-deployed? |
| Gap risk accuracy | Do gap-adjusted positions actually lose less on gaps? |
| Earnings calendar impact | Do pre-earnings entries outperform? |

### Auto-Adjustments (Mathematical, No Human Needed)

These use actual trade data to replace estimated parameters. Minimum 30 trades before any auto-adjustment activates.

**1. Kelly inputs calibration:**
```
win_prob = rolling_wins / rolling_total_trades  (30-trade window)
avg_win = rolling_average_gain_on_wins          (30-trade window)
avg_loss = rolling_average_loss_on_losses        (30-trade window)
```
This replaces the initial estimates (win_prob from confidence/100, avg_win 0.05, avg_loss 0.03) with real numbers. If performance degrades, Kelly automatically sizes positions smaller. If it improves, sizes increase. Self-correcting.

**2. Signal source weighting:**
If trades with news-boost have a significantly different win rate than technicals-only (>10% difference sustained over 30+ trades), adjust the conviction weight for the news component accordingly. Rebalance monthly.

**3. Position size caps:**
If the weekly drawdown circuit breaker fires more than once in 4 weeks, auto-reduce max_position by 1% (e.g., 8% -> 7%). Restore after 4 clean weeks.

### Human Review Recommendations (Surfaced, Not Auto-Applied)

The system generates but does not implement:

- "Stop-loss data suggests 4% performs better than 3% over last 60 trades. Consider adjusting."
- "Sector X has 25% win rate over 12 trades. Consider temporary exclusion."
- "Friday close-out is costing an average of 0.8% per position. Weekend gap risk is averaging 1.2% on the few positions tested. Friday rule is net positive."
- "Conviction scores below 50 have a 38% win rate. Consider raising minimum conviction to 50."

Surfaced in the Django dashboard and in the Saturday report. Human decides.

### Anomaly Alerts

- Win rate drops below 45% over 20+ trades → "Edge may have degraded. Review market conditions."
- Average loss exceeds 4% (above the 3% stop) → "Stops may not be executing properly. Check broker orders."
- More than 50% of exits are Friday close-outs → "Too many positions are not reaching targets. Review entry criteria."

---

## What Changes From Current Codebase

### config.py

**Remove:**
- `Tier` enum (MODERATE/HIGH) -- replaced by single-tier model
- `ModerateTierConfig` and `HighRiskTierConfig` dataclasses
- `TierAllocation` and `ALLOCATION_TABLES` -- no tier allocation needed
- `FRAMEWORK_WEIGHTS` by tier
- `RebalanceConfig` -- no tier rebalancing
- `HoldAuditConfig` -- replaced by continuous 15-minute monitoring
- `max_share_price_usd` -- no price cap, fractional shares handle any price

**Add:**
- `PositionConfig` dataclass (single set of parameters):
  - `stop_loss: float = 0.03`
  - `ratchet_step_pct: float = 0.03`
  - `non_perf_days: int = 5`
  - `non_perf_gain_threshold: float = 0.02`
  - `max_hold_days: int = 10`
  - `max_position: float = 0.08`
  - `kelly_fraction: float = 0.25`
  - `min_conviction: int = 40`
  - `friday_min_conviction: int = 60`
  - `thursday_lockin_threshold: float = 0.05`
  - `thursday_tighten_vs_sell: float = 0.07` (above this, sell; below, tighten)
  - `premarket_gap_skip_threshold: float = 0.02` (skip if gapped down > 2% pre-market)
  - `earnings_lookahead_days: int = 3` (boost conviction if earnings within N days)
  - `earnings_day_min_conviction: int = 60` (higher bar for day-of/day-before earnings entry)
- `PortfolioConfig` dataclass:
  - `max_positions: int = 20`
  - `target_positions_min: int = 8`
  - `target_positions_max: int = 15`
  - `dry_powder_reserve: float = 0.12`
  - `sector_concentration_max: int = 3`
- `GapRiskConfig` dataclass:
  - `lookback_days: int = 30`
  - `thresholds: list = [0.005, 0.01, 0.02, 0.03]` (gap % breakpoints)
  - `factors: list = [1.0, 0.85, 0.70, 0.55, 0.40]` (corresponding size multipliers)
- `UniverseConfig` dataclass:
  - `earnings_lookback_days: int = 5` (include stocks that reported within N days)
  - `earnings_lookahead_days: int = 5` (include stocks reporting within N days)
  - `volume_spike_multiple: float = 3.0` (include stocks with Nx average volume)
  - `rsi_oversold_threshold: float = 25.0` (include Stage 2 stocks below this RSI)
  - `include_recent_winners: bool = True`
  - `max_universe_size: int = 100` (cap to prevent excessive API calls)
- `ConvictionWeights` dataclass:
  - `technical: float = 0.40`
  - `rsi_context: float = 0.20`
  - `news_sentiment: float = 0.15`
  - `earnings_surprise: float = 0.15`
  - `earnings_proximity: float = 0.10`
- `NewsConfig` dataclass:
  - `enabled: bool = True`
  - `negative_filter: bool = True`
  - `conviction_boost_max: float = 15.0`
  - `cache_ttl_minutes: int = 60`
- `QAConfig` dataclass:
  - `min_trades_for_calibration: int = 30`
  - `rolling_window: int = 30`
  - `max_position_reduction_step: float = 0.01`
- Updated `CircuitBreakerConfig`:
  - `weekly_drawdown: float = 0.05` (replaces single max_drawdown)
  - `monthly_drawdown: float = 0.12`
  - Keep `rapid_loss_count: int = 3` and `rapid_loss_pause_hours: int = 48`

### calculators.py

**Add:**
- `rsi(closes: list[float], period: int = 2) -> float` -- RSI calculation from closing prices
- `days_held(entry_date: datetime, current_date: datetime) -> int` -- calendar day counting (replaces weeks_held)
- `is_non_performing_days(days_held: int, current_gain: float, review_days: int, threshold: float) -> bool`
- `friday_closeout_needed(current_weekday: int, current_time: time) -> bool`
- `thursday_lockin_action(gain_pct: float, threshold: float, tighten_vs_sell: float) -> str` -- returns "sell", "tighten", or "hold"
- `gap_risk_score(bars: list, lookback: int = 30) -> float` -- average absolute overnight gap from daily bars
- `gap_risk_factor(gap_score: float, config: GapRiskConfig) -> float` -- maps gap score to position size multiplier
- `earnings_proximity_score(days_to_earnings: int | None, config: PositionConfig) -> float` -- conviction boost for upcoming earnings

**Keep unchanged:**
- `kelly_position_size()` -- same formula, different inputs
- `ratchet_stop_level()` -- same logic, primary profit mechanism
- `stop_loss_price()` -- same formula, different percentage
- `composite_score()` -- same weighted average, different weights
- `normalise_score()`, `gain_pct()`, `asymmetry_score()`
- Stage classification helpers

**Remove:**
- `profit_target_price()` -- no fixed profit targets
- `atr_stop_loss_price()` -- single stop method (fixed %, not ATR-based)
- `is_non_performing()` -- replaced by days-based version
- Week-based calculation helpers

### strategy.py

**Rewrite `evaluate_opportunity()`:**
- Remove tier parameter -- single path for all candidates
- Add Gate 0: pre-market gap check (skip if gapped down > 2%)
- Add RSI(2) scoring to conviction calculation
- Add news sentiment check (gate 3: negative filter)
- Add earnings surprise boost (if available)
- Add earnings calendar proximity boost (upcoming earnings within 1-3 days)
- Use new `ConvictionWeights` for scoring (5 inputs including earnings proximity)
- Use single `PositionConfig` for sizing and stops
- Apply gap-risk factor to position sizing (reduce max_position for high-gap stocks)
- Remove asymmetry gate (was high-risk tier only)
- Remove price cap gate (no max_share_price_usd)
- Add sector concentration check before entry

**Rewrite `review_position()`:**
- Replace `_check_profit_target()` with ratcheting stop as primary mechanism
- Replace `_check_non_performance()` with days-based version (5 days, <2%)
- Replace `_check_max_hold()` with days-based version (10 calendar days)
- Add `_check_negative_news()` -- accelerated exit on bad news
- Add `_check_thursday_lockin()` -- Thursday gain evaluation
- Add `_check_friday_closeout()` -- unconditional Friday sell
- Remove tier-specific logic throughout

**Rewrite `generate_plan()`:**
- Remove tier iteration for opportunity scanning
- Add position count limit check before generating buy signals
- Add sector concentration check
- Remove tier_values accounting
- **Add candidate ranking**: sort all passing BUY signals by conviction score descending, then take only the top N needed to reach target_positions_max. This replaces the old "buy everything that passes" approach with "buy the best available"
- Track `conviction_rank` on each signal for QA/QC attribution

**Update `ManagedPosition`:**
- Remove `tier` field
- Remove `target_price` field (no fixed targets)
- Change `weeks_held` to `days_held: int` or compute from `entry_date`
- Add `sector: str`
- Add `entry_conviction: int`
- Add `entry_signal_source: str`

**Update `Signal`:**
- Remove `tier` field
- Remove `target_price` field

### portfolio_manager.py

**Change:**
- Remove all tier accounting (tier_values, tier allocation, tier iteration)
- Change assessment frequency from hourly to every 15 minutes
- Add PDT tracking: `pdt_slots_used` counter, rolling 5-day window, check before same-day exits
- Add Friday close-out job: scheduled at 15:30 ET Friday, sells everything
- Add Thursday evaluation job: scheduled at 15:45 ET Thursday, runs lock-in logic
- Fix Issue #9: ensure `user_config.yaml` is created with `DRY_RUN=false` and `ALPACA_PAPER=false`
- Fix Issue #10: place all stop orders as GTC; on each cycle, verify every held position has a broker-side stop order, re-place if missing
- Add news fetching to assessment cycle
- Add sector tracking for concentration limits
- Update circuit breakers: weekly + monthly drawdown (replacing single 18% max_drawdown)

**Add:**
- `run_friday_closeout()` -- sells all positions at market
- `run_thursday_evaluation()` -- evaluates lock-in vs tighten vs hold
- `check_pdt_available() -> bool` -- can we do a same-day exit?
- `record_completed_trade()` -- writes to trade_log.jsonl with full metadata
- `verify_stop_orders()` -- ensure every position has GTC stop at broker

### scheduler.py

**Change:**
- Assessment job: every 15 minutes during market hours (was hourly at :45)
- Stop check job: keep every 15 minutes (merge with assessment job since they're now same frequency)
- Add: Thursday evaluation job (15:45 ET Thursday)
- Add: Friday close-out job (15:30 ET Friday, backstop at 15:55 ET)
- Add: Saturday QA/QC job (runs weekly analysis)

### data_input.py

**Add:**
- `get_news(symbol: str) -> list[NewsItem]` -- fetch from Alpaca News API
- `get_decis_news(sector: str) -> list[NewsItem]` -- fetch from Decis feed
- `get_earnings_surprise(symbol: str) -> EarningsSurprise | None` -- from AlphaVantage
- `get_earnings_calendar(lookahead_days: int = 5) -> list[EarningsEvent]` -- upcoming earnings from AlphaVantage
- `get_rsi(closes: list[float], period: int = 2) -> float` -- compute from existing bar data
- `classify_news(headlines: list[str]) -> str` -- Groq LLM classification (POSITIVE/NEGATIVE/NOISE)
- `get_premarket_quote(symbol: str) -> float | None` -- pre-market price from Alpaca snapshot
- `get_gap_risk_data(symbol: str, bars: list) -> float` -- compute avg absolute overnight gap from bar data
- `build_dynamic_universe(config: UniverseConfig) -> list[str]` -- construct today's scan universe from all sources (earnings calendar + news + volume spikes + RSI screener + recent winners)
- `get_volume_spike_symbols(multiple: float = 3.0) -> list[str]` -- scan for unusual volume today

**Change:**
- Remove `max_share_price_usd` filter from `get_tradeable_assets()` -- no price cap

**Keep unchanged:**
- All Alpaca market data fetching (bars, quotes, positions, account)
- Technical indicator computation (MA, ATR, volume ratio, stage)
- Client initialisation and caching

### reporting.py

**Add:**
- `record_completed_trade(trade_record: dict)` -- append to `data/trade_log.jsonl`
- `load_trade_history() -> list[dict]` -- read trade log
- Weekly analysis functions (win rate, by-source, by-exit-reason, etc.)
- Performance report generation for dashboard + Saturday email

### audit_qa.py

**Rewrite to become the QA/QC engine:**
- `compute_rolling_metrics(trades: list, window: int = 30) -> dict` -- all weekly metrics
- `calibrate_kelly_inputs(trades: list, window: int = 30) -> dict` -- returns updated win_prob, avg_win, avg_loss
- `calibrate_signal_weights(trades: list) -> dict` -- returns updated conviction weights
- `generate_recommendations(metrics: dict) -> list[str]` -- human-readable suggestions
- `detect_anomalies(metrics: dict) -> list[str]` -- alerts for degraded performance
- `should_reduce_position_size(drawdown_history: list) -> bool` -- auto-cap adjustment

### Web Dashboard (Django)

**Update:**
- Remove tier displays (moderate/high)
- Show single portfolio view with all positions
- Add QA/QC section: weekly metrics, trade log, recommendations
- Add PDT status display (slots used / remaining)
- Show Friday close-out status
- Settings page: remove tier-related settings, add new parameters

---

## Build Phases

### Phase 0: Fix Safety Bugs (Issues 9 & 10)

Non-negotiable. Before any strategy changes.

**Issue 9 -- DRY_RUN persistence:**
- Create `user_config.yaml` at project root with `DRY_RUN=false` and `ALPACA_PAPER=false`
- Verify `load_user_config()` reads it correctly
- Optionally: add Settings page toggles

**Issue 10 -- Stop order persistence:**
- Change all stop orders from DAY to GTC time-in-force
- Add `verify_stop_orders()` to the assessment cycle: for each held position, check if a GTC stop exists at broker; if not, place one
- Fix bracket order submission so stop legs persist, OR abandon brackets in favour of separate market buy + GTC stop (simpler, more reliable)
- Test: verify stops survive overnight by checking broker orders next morning

**Tests:** Verify stop orders exist after market close for all held positions. Verify DRY_RUN=false results in actual order submission.

---

### Phase 1: Re-parameterise + Core Improvements (Single Tier, New Targets, Ranking, Gap Risk)

Transform config.py and strategy.py for the new model. Includes the core optimisation principles that don't require new external data sources: ranking, gap-risk sizing, tighter ratchets, price cap removal, and pre-market checks.

**config.py:**
- Add new dataclasses (`PositionConfig`, `PortfolioConfig`, `ConvictionWeights`, `GapRiskConfig`, `UniverseConfig`)
- Remove tier-specific configs and `max_share_price_usd`
- Set `ratchet_step_pct` to 0.03 (not 0.05)
- Update `SystemConfig` to use new structures
- Update `load_config()` and `load_config_from_env()`

**calculators.py:**
- Add `days_held()`, `is_non_performing_days()`, `friday_closeout_needed()`, `thursday_lockin_action()`
- Add `gap_risk_score()` and `gap_risk_factor()` -- computed from existing bar data, no new API calls
- Add `rsi(closes, period=2)` -- computed from existing bar data
- Update `ratchet_stop_level()` to use 0.03 step
- Keep existing Kelly, stop-loss, composite score functions

**strategy.py:**
- Remove tier logic from `evaluate_opportunity()` and `review_position()`
- Remove price cap gate
- Add pre-market gap check (Gate 0)
- Add RSI(2) to conviction scoring
- Apply gap-risk factor to position sizing
- Add candidate ranking in `generate_plan()` -- sort by conviction, buy top N only
- Update `ManagedPosition` and `Signal` dataclasses (add sector, conviction_rank, gap_risk_factor)
- Implement new exit rules (days-based non-performance, Thursday lock-in, Friday close-out)

**data_input.py:**
- Remove `max_share_price_usd` filter from `get_tradeable_assets()`
- Add `get_premarket_quote()` via Alpaca snapshot
- Add RSI computation from existing bar data
- Add gap-risk computation from existing bar data (no new API calls)

**portfolio_manager.py:**
- Remove tier accounting
- Change assessment to 15-minute cycles
- Add PDT tracking
- Add Friday close-out and Thursday evaluation jobs
- Add `verify_stop_orders()` to each cycle
- Add pre-market check to first cycle of day

**scheduler.py:**
- Update job frequencies
- Add Thursday and Friday special jobs
- Add Saturday QA/QC job (placeholder until Phase 4)

**Tests:** Full test suite update for new parameters. Verify entry gates, exit rules, position sizing, gap-risk adjustment, ranking logic, PDT tracking, RSI calculation.

---

### Phase 2: Dynamic Universe Builder

Replace the static watchlist with a dynamic universe constructed from multiple sources. This is the single biggest improvement to entry quality -- scanning where the edge is instead of scanning randomly.

**data_input.py:**
- Implement `get_earnings_calendar()` via AlphaVantage -- upcoming earnings for next 5 trading days
- Implement `get_volume_spike_symbols()` -- scan Alpaca assets for 3x+ average volume today
- Implement `build_dynamic_universe()` -- combine all sources, deduplicate, cap at max_universe_size
- Track which source surfaced each symbol (for QA/QC attribution)

**strategy.py:**
- Add earnings calendar proximity scoring to conviction calculation
- Boost conviction +10 for stocks with earnings in 1-3 days (if already Stage 2 + volume)
- Require conviction >= 60 for day-of/day-before earnings entries (higher bar due to gap risk)
- Track `universe_source` on each signal

**portfolio_manager.py:**
- Replace static watchlist with `build_dynamic_universe()` call each cycle
- Saturday job: pre-build Monday universe from earnings calendar + Friday's RSI screener
- Add recent winners tracking (symbols profitably exited last week)

**Tests:** Mock earnings calendar and volume data. Verify universe construction from multiple sources. Verify earnings proximity scoring. Verify source attribution tracking.

---

### Phase 3: Wire In News (Filter + Modifier)

Connect the three news sources as a filter and conviction modifier.

**data_input.py:**
- Implement `get_news()` via Alpaca News API
- Implement `get_decis_news()` via Decis API
- Implement `classify_news()` via Groq LLM (simple prompt, cache results with TTL)
- Implement `get_earnings_surprise()` via AlphaVantage

**strategy.py:**
- Gate 3: check news classification before entry; NEGATIVE → block
- Conviction modifier: POSITIVE news → boost score by configurable amount
- Earnings surprise: recent beat within 10 trading days → boost by up to 15 points
- Add `_check_negative_news()` to position review for accelerated exits
- News-mentioned symbols feed into dynamic universe builder

**config.py:**
- Add `NewsConfig` to `SystemConfig`

**Tests:** Mock API responses for all three sources. Verify negative filter blocks entry. Verify positive boost adjusts conviction correctly. Verify accelerated exit on negative news for held positions.

---

### Phase 4: QA/QC Engine

The self-correcting feedback loop. Requires trades to analyse, so this comes after the system is running.

**reporting.py:**
- Implement `record_completed_trade()` -- append structured records to `data/trade_log.jsonl`
- Wire into portfolio_manager so every completed trade (sell execution) is recorded

**audit_qa.py:**
- Rewrite with rolling metrics computation
- Kelly auto-calibration from real trade data
- Signal weight auto-calibration
- Position size cap auto-adjustment
- Recommendation generation
- Anomaly detection

**scheduler.py:**
- Wire Saturday QA/QC job to run full analysis

**Web dashboard:**
- Add QA/QC section showing metrics, recommendations, trade log

**Phase 1 dependency:** Enhanced trade recording should be added during Phase 1 (even before QA analysis exists) so data accumulates from day one. The analysis and auto-adjustment logic is Phase 4.

**Tests:** Feed synthetic trade histories with known characteristics. Verify metrics calculation, Kelly calibration, recommendation generation, anomaly detection.

---

### Phase 5: Dashboard & Polish

Update the Django web dashboard for the new single-tier model.

- Remove tier displays
- Show unified portfolio view
- Add PDT status (slots used / available / next refresh)
- Add Friday close-out countdown
- Add QA/QC metrics section
- Add news feed display for held positions
- Add trade log browser with filtering
- Update Settings page for new parameters

---

## What We Are NOT Building (Yet)

These are future enhancements, only considered after the base system is profitable:

- **Options trading** -- weekly calls as amplifiers, covered calls, CSPs on reserves
- **Correlation matrices** -- cross-position correlation monitoring
- **Graduated deleveraging** -- dynamic position sizing based on drawdown depth
- **Sector rotation** -- systematic sector timing
- **Multiple strategy engines** -- mean reversion, event-driven, and momentum as independent engines
- **Backtesting engine** -- historical strategy validation
- **ML-based signal optimisation** -- parameter tuning via machine learning
- **Short selling** -- market-neutral positioning
- **Futures** -- micro futures for index exposure
- **Multiple broker accounts** -- PDT slot multiplication

Each would be a separate workplan after this one is delivering.

---

## Files Affected (Summary)

| File | Change Type | Scope |
|---|---|---|
| `config.py` | Major rewrite | New dataclasses, remove tiers, remove price cap, add gap risk + universe + earnings configs |
| `calculators.py` | Additions + minor removals | RSI, gap risk scoring, day-counting, earnings proximity, Thursday/Friday helpers, 3% ratchet |
| `strategy.py` | Major rewrite | Single pipeline, ranking, gap-risk sizing, pre-market gate, new exit rules, news integration |
| `portfolio_manager.py` | Major rewrite | Remove tiers, dynamic universe, add PDT/Friday/Thursday, fix stops, pre-market checks |
| `scheduler.py` | Moderate changes | 15-min cycles, new scheduled jobs, Saturday universe prep |
| `data_input.py` | Major additions | Dynamic universe builder, news, earnings calendar, pre-market quotes, gap risk data, volume spike scanner |
| `reporting.py` | Additions | Trade recording with universe source + gap risk + conviction rank, weekly analysis |
| `audit_qa.py` | Major rewrite | QA/QC engine with auto-calibration, universe source attribution, gap risk analysis |
| `trading_interface.py` | Minor changes | GTC stop orders, verify stop existence, fractional share support |
| `web/` (Django) | Moderate updates | Remove tiers, add QA/QC, add PDT display, universe source display |
| `tests/` | Full rewrite | All test files updated for new model |
| `user_config.yaml` | Create new | DRY_RUN=false, ALPACA_PAPER=false |
| `alpha_signals.yaml` | Minor updates | Adjust for single-tier model |

---

## Success Criteria

| Metric | Threshold | Timeframe |
|---|---|---|
| System executes trades autonomously | Yes/No | Phase 1 complete |
| All positions have GTC stops at broker | 100% compliance | Phase 0 complete |
| 15-minute assessment cycles running | Yes/No | Phase 1 complete |
| Friday close-out executing | Zero weekend exposure | Phase 1 complete |
| Candidate ranking active | Top-N selection, not pass/fail | Phase 1 complete |
| Gap-risk sizing active | High-gap stocks get smaller positions | Phase 1 complete |
| Pre-market filter active | Skip gapped-down candidates at open | Phase 1 complete |
| Dynamic universe builder active | Universe from earnings + news + volume + RSI | Phase 2 complete |
| Earnings calendar positioning active | Conviction boost for upcoming earnings | Phase 2 complete |
| Win rate (30-trade rolling) | > 50% | After 4-6 weeks of trading |
| Average weekly return | > 0.5% (26%+ annualised) | After 8 weeks of trading |
| Maximum weekly drawdown | < 5% | Ongoing |
| Kelly auto-calibration active | Yes/No | Phase 4 complete + 30 trades |
| News filter blocking bad entries | Measurable via QA/QC | Phase 3 complete |
| Universe source attribution | Trackable per trade | Phase 2 complete |
| Gap-risk adjustment validated | High-gap positions lose less on gaps | After 8 weeks of trading |
