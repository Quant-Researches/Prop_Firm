---
name: trade-pulse-change
description: Safe change workflow for Trade Pulse Quants — pipeline, scheduler, risk, and deployment. Use when modifying core/, main.py, execution, risk, scheduler, or preparing changes for user review.
---

# Trade Pulse Quants — Safe Change Workflow

## Before editing

1. Identify pipeline step (1–9 in README / AGENTS.md)
2. Read the module + callers (engine imports risk → oms → execution)
3. Confirm timezone impact: Helsinki vs Prague
4. Confirm threading: scheduler must not block on pipeline or notifications

## Critical path files

| Area | Files |
|------|-------|
| Scheduler | `main.py`, `core/candle_timer.py` |
| Pipeline | `core/engine.py` |
| Risk | `core/risk_manager.py` |
| Execution | `core/execution.py`, `core/oms.py` |
| Config | `config/prefs.py`, `config/user_prefs.json` |
| Alerts | `core/notifier.py` |

## Test checklist (demo account unless user confirms live)

```
□ python main.py --check-schedule
□ python main.py --tick-now
□ Inspect data/events.jsonl for expected log lines
□ If risk/execution changed: verify BLOCKED path still fires alerts
□ If scheduler changed: confirm next close time in daemon stdout
```

## After completing work — commit recommendation (do NOT commit)

Unless the user explicitly says "commit", end with a **Commit Recommendation** block:

```markdown
## Commit Recommendation

**Ready to commit?** Review the diff, then tell me to commit if it looks good.

**Files changed:**
- path/to/file.py — one-line summary

**Summary:** What changed and why (1–2 sentences).

**Suggested commit message:**
fix: short description focused on why

**Not included / intentionally excluded:**
- config/user_prefs.json, data/* (runtime — never commit)
```

Wait for user approval before running any git commit.

## Deployment reminder

- MT5 terminal open, AutoTrading enabled
- Prague midnight SOD snapshot (`daily_reset_time` in prefs)
- Daemon and UI are separate processes — UI crash must not stop daemon
