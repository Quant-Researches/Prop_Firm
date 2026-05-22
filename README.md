# ⚡ Trade Pulse Quants (Quant Risk & mplfinance Edition)

> **Event-Driven Live Trading Engine for FTMO Prop Firm Accounts**  
> Powered by MetaTrader 5 · Quantitative Volatility Regimes · Dow Theory Strategy · Ultra-Lightweight Charting

---

## 📋 Table of Contents

- [Branch Overview](#branch-overview)
- [New Features in this Branch](#new-features-in-this-branch)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Core Modules](#core-modules)
- [Setup & Installation](#setup--installation)
- [FTMO Risk Guard](#ftmo-risk-guard)
- [Notification Channels](#notification-channels)

---

## Branch Overview

**Branch:** `feature/quant_risk_mplfinance`

This branch represents a major architectural upgrade to the **Trade Pulse Quants** trading system. The core focus of this branch is the transition from a static risk model to a **Dynamic Volatility Regime Engine**, alongside a massive optimization of the background daemon utilizing an ultra-lightweight **mplfinance C-based rendering engine**. 

These upgrades make the daemon highly robust, mathematically rigorous, and 100% safe to run on low-resource environments like a 2GB AWS Lightsail VPS.

---

## New Features in this Branch

### 1. 📊 Quantitative Volatility Regime Engine
The static ADR (Average Daily Range) sizing logic has been completely replaced by a professional **ATR Percentile Engine**:
- **Rolling 200-Period ATR**: The system calculates the current Average True Range relative to the last 200 periods.
- **Regime Classification**: 
  - `Low Volatility` (Bottom 30%): Uses a tighter `1.2x` ATR multiplier.
  - `Normal Volatility` (Middle 40%): Uses a standard `1.5x` ATR multiplier.
  - `High Volatility` (Top 30%): Uses a wider `1.8x` ATR multiplier to prevent premature stop-outs in wild markets.
- **Structure-Aware Stop Loss**: Stop losses are dynamically placed based on `MAX(ATR_Distance, Structure_Distance)` to ensure technical logic is never overridden by pure math.

### 2. ⚡ Ultra-Lightweight Charting (`mplfinance`)
The heavy Plotly + Kaleido dependency (which silently ran Google Chrome in the background and spiked RAM usage) has been entirely removed from the background daemon.
- **Pure Memory Rendering**: Telegram/Email charts are now rendered entirely in-memory using Matplotlib's C-based `agg` backend.
- **Zero Browser Overhead**: CPU and RAM footprints during chart generation have been reduced by over 95%.
- **Premium Aesthetics**: The new static charts utilize a sleek, modern dark theme (`#0f172a` slate background), with vivid emerald/red candles, soft purple/cyan EMAs, and built-in "breathing room" (right-side padding) for a highly professional aesthetic.

### 3. 🛡️ Strict Fixed-Dollar Risk
Position sizing is strictly locked to an exact dollar amount (e.g., $100 per trade). The engine automatically converts the dynamic Stop Loss pip distance into the exact lot size required to risk exactly your chosen dollar amount, respecting all MT5 leverage constraints.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                  STREAMLIT DASHBOARD                    │
│   app.py · Live Chart · Scheduler · Settings            │
│   (Configure rules, monitor equity, view event log)     │
└───────────────────┬─────────────────────────────────────┘
                    │  config/user_prefs.json
┌───────────────────▼─────────────────────────────────────┐
│               BACKGROUND DAEMON (main.py)               │
│   Runs infinite loop · Checks schedule every minute     │
│   Triggers pipeline on time match                       │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│             EXECUTION PIPELINE (engine.py)              │
│                                                         │
│  MT5 Data Feed  →  Dow Strategy  →  Quant Risk Guard    │
│       │               │               │                 │
│  OMS Submit  →  Execution  →  mplfinance Image Gen      │
│                                       │                 │
│                              Storage + Notifier         │
└─────────────────────────────────────────────────────────┘
```

---

## Project Structure

```text
Prop_Firm/
├── app.py                   # Streamlit dashboard UI
├── main.py                  # Background trading daemon (scheduler loop)
├── schedules.json           # Trading schedule
│
├── core/
│   ├── engine.py            # Main pipeline orchestrator
│   ├── strategy.py          # Dow Theory EMA + ATR Percentile Engine
│   ├── risk_manager.py      # FTMO Risk Guard + Volatility Regime Sizing
│   ├── chart_utils.py       # mplfinance (Static) & Plotly (Live UI) renderers
│   ├── notifier.py          # Asynchronous Telegram / Email broadcaster
│   └── oms.py               # Order Management System
│
├── config/
│   └── user_prefs.json      # Runtime config (gitignored)
│
└── data/                    # Runtime data logs (gitignored)
```

---

## Core Modules

### `core/engine.py` — Pipeline Orchestrator
Executes the full automated trading sequence: Data Fetch → Strategy Check → Risk Evaluation → Order Sizing → MT5 Execution → Chart Generation → Broadcast.

### `core/strategy.py` & `core/risk_manager.py`
These files contain the new **Volatility Regime Engine**. The strategy calculates the 200-period ATR percentile, passes it to the risk manager, which dynamically scales the Stop Loss distance based on the mathematical regime (Low, Normal, High).

### `core/chart_utils.py`
Contains two rendering engines:
1. `generate_trade_chart()`: Plotly interactive graph used exclusively by the Streamlit UI.
2. `generate_static_trade_chart()`: The new ultra-lightweight `mplfinance` static image generator used by the background daemon for Telegram notifications.

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- MetaTrader 5 terminal
- `mplfinance` and `matplotlib` (Newly added in this branch)

### Installation
```bash
git clone <your-repo-url>
cd Prop_Firm
git checkout feature/quant_risk_mplfinance

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## FTMO Risk Guard

The engine evaluates **6 FTMO Rules** before executing any trade:
1. **Daily Loss Limit** (e.g., 5% of starting balance)
2. **Max Overall Drawdown** (e.g., 10%)
3. **Daily Budget Check** vs Trade Risk
4. **Drawdown Buffer Check** vs Trade Risk
5. **Max Open Positions**
6. **High-Impact News Blackout** (±2 minutes, for accounts with leverage > 1:30)

---

## Notification Channels

Alerts are broadcasted via background threads (non-blocking) to ensure the daemon never freezes:
- **Telegram**: Sends trade summaries alongside the new high-res `mplfinance` dark-theme chart.
- **Email**: Fallback text alerts via SMTP.
- **Windows Desktop Toast**: Native popups on the host machine.
- **Sound**: System beeps for immediate physical alerts.

> *Note: If a signal evaluates to `HOLD` on a scheduled daemon run, the system will silently skip the Telegram notification to prevent spamming your phone. Manual clicks of the "LTS" button in the UI will bypass this and ping you anyway.*
