# Session notes

Hand-off log between coding sessions, newest entry first. Read the top entry before starting work; add one before you stop.

Rules:
- Stamp every entry with the real clock: `date -u +"%Y-%m-%dT%H:%MZ"` and `hostname -s`. Never guess the time.
- Compare the top stamp with `git log -1 --format=%cI` and with any entries you remember writing. Newer stamps mean other sessions have happened since; read them all before acting.
- Keep an entry to about ten lines: done, hand-off state (tests, uncommitted work, running services), next steps, open questions.
- When the log passes 20 entries, fold the oldest into one paragraph under `## Earlier`.

Entry format:

```
## <UTC stamp> · <machine> · <tool>
Done: ...
State: ...
Next: ...
Open: ...
```

---

## 2026-09-13T13:56Z · Deep-Thought · Claude Code
Done: session notes started (rolled out from dev_toolkit).
State: no code changes.
Next: read the top entry at the start of each session; add one before stopping.
