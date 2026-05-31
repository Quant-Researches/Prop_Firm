# Global Cursor User Rules — copy into Settings

**Where:** Cursor → Settings → Rules → **User Rules** → paste the block below.

These apply across all projects. Prop_Firm project rules in `.cursor/rules/` add detail when you work in that repo.

---

## Paste this into User Rules

```
## Trade Pulse Quants (Prop_Firm project)

When working in the Prop_Firm / Trade Pulse Quants repo:

- Never commit unless I explicitly say "commit" in that message
- After completing work, recommend a commit (files changed, summary, suggested message) and wait for my review
- Never push unless I explicitly ask
- Treat core/risk_manager.py and core/execution.py as critical path — ask before changing live trading behavior
- Trust code over README for scheduler (core/candle_timer.py sleep-to-close is authoritative)
- Config: use config/prefs.py and user_prefs.json — NOT config/config.py (legacy)
- Never commit config/user_prefs.json, data/*, or credentials
- Test on demo account: python main.py --tick-now

### Strategy-related files (read before editing)

When changing signals, indicators, or swing logic, read these files first:

- core/strategy.py — RealTimeSignalGenerator (Dow Theory EMA + fractal swings)
- Utilities/technical_indicators.py — EMA, ATR, RSI
- core/signal_store.py — signal audit trail
- core/data_feed.py — MarketEvent
- core/engine.py — how strategy output feeds risk_manager.build_order()

Strategy rules also live in .cursor/rules/strategy.mdc (auto-attaches when those files are open).

Do not weaken signal deduplication, phase detection, or breakout conditions without my explicit approval.
```

---

After pasting, save Settings. Project rules in `.cursor/rules/` still apply automatically when this repo is open.
