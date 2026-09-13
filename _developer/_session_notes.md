# Session notes

Hand-off log between sessions and machines, newest entry first. Read the top entry before starting work; add one before you stop.

Non-negotiable: an entry is 150 words or fewer. Short and clear, or it defeats the purpose.
Shorthand is fine. Point at buildfiles, commits, or bloopers instead of repeating them. This is a quick recap of what was done, what was not, and where things stand, so the next agent can pick up fast.

Every entry must cover, as terse bullets:
- Activity: what was done.
- Decisions: what was chosen to do and not do, with the one-line reason.
- Issues: any major problem hit (also log it in `_bloopers.md`).
- Next: the immediate next step and hand-off state (uncommitted work, failing tests, running services).

Rules:
- Stamp from the real clock: `date -u +"%Y-%m-%dT%H:%MZ"` and `hostname -s`. Never guess the time.
- Compare the top stamp with `git log -1 --format=%cI` and with any entry you remember writing. Newer stamps mean other sessions have happened since; read them all before acting.
- Over 20 entries, fold the oldest into one paragraph under `## Earlier`.

```
## <UTC stamp> · <machine> · <tool>
Activity: ...
Decisions: ...
Issues: ...
Next: ...
```

---

## 2026-09-13T13:56Z · Deep-Thought · Claude Code
Activity: session notes started (rolled out from dev_toolkit).
Decisions: none.
Issues: none.
Next: read the top entry at the start of each session; add one before stopping.

## 2026-04-12T21:43Z · unknown · Claude Code (backfilled 2026-09-13)
Activity: diagnosed live-trading safety bugs; logged as Issues 9 & 10 in `_developer/build_plan.md` (only commit). Wrote `_developer/strategy_adjustment_notes_april12.md` (volatility-harvest pivot: 5% target, 3% stop, 1–10 day holds, single tier, Friday close-out) and drafted `_developer/workplan_optimum_trading_bot.md` (Phases 0–5). Neither committed.
Decisions: redesign moves to a separate repo — forked to `optimal_trading_bot` on 04-13 (memory `project_optimal_bot_split.md`); monaimetrics keeps the old two-tier strategy. Phase 0 (Issues 9/10) must precede any strategy change.
Issues: 9 — `user_config.yaml` never created, Replit secrets cleared, app silently on `DRY_RUN=true` (no orders since). 10 — stops/targets are DAY or cancelled each cycle, brackets show `legs=0`; positions unprotected overnight.
Next: branch `april-12`; uncommitted: `_developer/strategy_adjustment_notes_april12.md`, `_developer/workplan_optimum_trading_bot.md`, `cache/`, `data/notifications.jsonl`, `data/pm_state.json`, `data/strategy_performance.json` (only 09-13 docs commits since). Most useful: commit the two notes, then fix Issues 9/10 here (GTC stops, `user_config.yaml`) — this repo holds live positions.

## 2026-04-09T11:15Z · unknown · Claude Code (backfilled 2026-09-13)
Activity: Replit-agent style session ("Transitioned from Plan to Build mode"). Built Task #4 — portfolio state persistence and live stop management: `portfolio_manager.py` (+131), `scheduler.py`, `trading_interface.py`, `web_portfolio.py`, dashboard template. Follow-up commit refreshes stop order IDs on position tracking and guards against concurrent access in the scheduler.
Decisions: manage stops at the broker and persist portfolio state to disk rather than in memory; serialise scheduler access to position state.
Issues: none recorded in commits; the stop-order persistence problem surfaced later as Issue 10 (04-12), so this work did not fully solve overnight protection.
Next: branch `april-12` work continued 04-12 with the bug diagnosis above.

## 2026-04-06T13:02Z · unknown · Claude Code (backfilled 2026-09-13)
Activity: "Restore to working state (8ee622f) — trailing stop, risk profile, CSS fixes"; 58 files, +3514/−5308. Removed backtest, journal, notifications and plan templates; slimmed dashboard/settings; scan page tweaks. Merged as PR #5 (`april6`).
Decisions: roll back to a known-good commit rather than debug the March feature sprawl; keep trailing stop and risk-profile settings, drop backtest/journal/plan UI.
Issues: unknown what broke — the restore implies the 03-20/21 build was unstable.
Next: repo back on a working base; next session added state persistence and live stops (04-09).

## 2026-03-20T22:13Z · unknown · Claude Code (backfilled 2026-09-13)
Activity: after PR #3 (autonomous infrastructure, paper-trading default, position-size limits) — added `.env` loading in `web/settings.py`, daily trade planning page (`scheduler.py` +140, `plan.html`), manual full-report trigger incl. Sunday evenings, CSRF exemption on plan trigger and local dev origins.
Decisions: expose plan generation via web UI; allow localhost origins for dev.
Issues: none recorded.
Next: features later rolled back on 04-06 restore. Build plan at `_developer/build_plan.md` shows Phases 1–7 DONE with tests.
