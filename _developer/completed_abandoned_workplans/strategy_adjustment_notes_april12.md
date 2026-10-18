# Volatility Harvest Strategy — Build Adjustment

## What Changed

The system shifts from multi-week positions targeting 25% gains to short-term volatility harvesting targeting 4–6% gains over 1–10 days. The two-tier structure (moderate + high-risk) is replaced by a single engine that cycles capital rapidly through small, event-driven positions.

## Trade Structure

| Parameter | Value |
|---|---|
| Profit target | 5% gain from entry |
| Stop-loss | 3% below entry (closing price) |
| Max hold | 10 calendar days |
| Non-performance exit | 5 days with < 2% gain → sell |
| Weekly close-out | Exit all positions Friday close unless explicit thesis to hold |
| Position size | Kelly fraction (0.25) × conviction × available capital |
| Max single position | 8% of portfolio (equities), 3% (options) |
| Target open positions | 8–15 at any time |
| Review cycle | Every 15 minutes during market hours |

## Entry Signal

1. **News/event detected** — earnings, regulatory, geopolitical, sector catalyst
2. **Price hasn't fully reflected the event yet** — we're in the Phase 2–3 window (minutes to hours after news breaks)
3. **Volume confirms** — 2×+ average volume in the direction of the move
4. **No contradicting signals** — not in Stage 4 decline, no structural negative on the stock

Entry is automatic when all conditions met. No human approval.

## Options (Weekly Calls)

Used as amplifier and to work around PDT limits. Buy slightly OTM weekly calls expiring Friday. Target 50–100% premium gain (≈ 3–5% underlying move). Stop at 50% premium loss. Exit by Thursday — never hold to expiry. Max 3% of portfolio per option position.

## PDT Management

Account under $25k = 3 same-day round-trips per rolling 5 days. Structure:

- **Same-day exits** (use PDT slots): only for highest-conviction setups that hit target intraday
- **Multi-day holds** (no PDT impact): options bought Tuesday sold Thursday, stocks held 2+ days
- **System tracks PDT count** and blocks same-day exits when limit reached

## Portfolio Structure

- **85–90%** actively deployed in volatility harvest positions
- **10–15%** dry powder reserve for immediate deployment on high-conviction setups
- No separate high-risk tier. Asymmetric bets taken opportunistically from the same pool.
- Capital from exits returns to pool immediately for redeployment.

## Safety

| Trigger | Response |
|---|---|
| Position hits 3% stop | Immediate auto-sell |
| Portfolio down 8% in a week | Halt new entries, close weakest positions, resume next week |
| Structural Divergence detected | Preservation mode: halt entries, tighten stops, harvest at reduced targets |
| 3 PDT slots used | Multi-day holds only until slots refresh |

## What's Kept from Original System

- Kelly position sizing
- Weinstein Stage Analysis as entry gate (Stage 2 only)
- Event-News-Price Cascade for signal timing
- Structural Divergence circuit breaker
- Autonomous execution — human governs, doesn't operate
- Broker-side stop-losses

## What's Dropped or Changed

- ~~25% profit target~~ → 5%
- ~~4–12 week holds~~ → 1–10 days
- ~~Two-tier moderate/high-risk~~ → single engine
- ~~CAN SLIM / Greenblatt as primary screens~~ → news/event detection primary, fundamentals as negative filter only
- ~~Weekly hold audit~~ → 15-minute review cycle
- ~~8% stop-loss~~ → 3% (tighter stop, faster exit)
- ~~3:1 reward:risk~~ → 1.7:1 (compensated by higher win rate and faster cycling)