# Session notes

Hand-off log between sessions and machines, newest entry first. Read the top entry before starting work; add one before you stop.

Non-negotiable: an entry is 150 words or fewer. Short and clear, or it defeats the purpose.

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
