# AGENTS.md — Trade Pulse Quants

Guide for AI agents working in this repository.

## What this project is

Fully automated FTMO prop-firm trading bot: MetaTrader 5 + Python daemon + Streamlit dashboard. Real capital at risk — treat `core/risk_manager.py` and `core/execution.py` as critical path.

## Process architecture

```
Streamlit (app.py + pages/)     ←→  config/user_prefs.json, schedules.json (UI)
         │
main.py daemon                  ←→  sleep-to-close scheduler (candle_timer.py)
         │
core/engine.py pipeline       ←→  MT5 → strategy → risk → OMS → execute → notify
```

**Two processes, shared JSON config.** Crash isolation by design.

## Module map

| Module | Role |
|--------|------|
| `main.py` | Daemon loop, daily reset, pipeline fire |
| `core/candle_timer.py` | Next candle close arithmetic (authoritative scheduler) |
| `core/ftmo_time.py` | Helsinki time helpers |
| `core/engine.py` | Pipeline orchestrator |
| `core/strategy.py` | Dow Theory EMA cross signals (see `.cursor/rules/strategy.mdc`) |
| `Utilities/technical_indicators.py` | EMA, ATR, RSI |
| `core/signal_store.py` | Signal audit trail |
| `core/risk_manager.py` | FTMO guard + ATR order sizing |
| `core/oms.py` | Order lifecycle, duplicate prevention |
| `core/execution.py` | MT5 order_send |
| `core/notifier.py` | Telegram, email, desktop, sound |
| `config/prefs.py` | **Source of truth** for user settings |

**Ignore for MT5 settings:** `config/config.py` (legacy Dhan API).

## Timezones

- **Europe/Helsinki** — MT5 chart time, candle closes, scheduler
- **Europe/Prague** — FTMO daily reset, SOD balance snapshot

## Scheduler

**Runtime:** `main.py` + `core/candle_timer.py` (sleep-to-next-candle-close).  
**UI only:** `schedules.json` — weekly grid display, not execution timing.

## Safe commands

```bash
python main.py --check-schedule   # print schedule + next close
python main.py --tick-now         # one pipeline tick (demo unless user confirms live)
streamlit run app.py              # dashboard only
```

## Never without explicit user approval

- Weaken or skip FTMO risk checks
- Commit or push (recommend first — user reviews diff)
- Commit `config/user_prefs.json`, `data/*`, secrets
- Run live trading tests when user asked for demo only
- Add Kaleido/headless Chrome for charts

## Git workflow

1. Agent completes changes
2. Agent outputs **Commit Recommendation** (files, summary, suggested message)
3. User reviews diff
4. User explicitly says "commit" → then and only then run git commit

See `.cursor/rules/project-core.mdc`, `.cursor/rules/strategy.mdc`, and `.cursor/skills/trade-pulse-change/SKILL.md`.

Global User Rules paste block: `config/cursor-global-user-rules.md`.

## Logs to check after changes

- `data/events.jsonl` — pipeline events
- `data/bot_lifecycle.log` — daemon start/stop
- Daemon stdout — next close time, sleep duration
