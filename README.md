# ⚡ Trade Pulse Quants

> **Event-Driven Live Trading Engine for FTMO Prop Firm Accounts**  
> Powered by MetaTrader 5 · Dow Theory Strategy · Real-Time Risk Guard · Multi-Channel Alerts

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Core Modules](#core-modules)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [FTMO Risk Guard](#ftmo-risk-guard)
- [Notification Channels](#notification-channels)
- [Scheduling Trades](#scheduling-trades)
- [UI Pages](#ui-pages)

---

## Overview

**Trade Pulse Quants** is a fully automated, event-driven algorithmic trading system built for FTMO Challenge and Funded accounts. It connects directly to MetaTrader 5, evaluates market signals using a Dow Theory EMA cross strategy, enforces FTMO-compliant risk rules, and executes live orders — all while broadcasting real-time alerts via Telegram and Email.

The system is split into two decoupled layers:

| Layer | Entry Point | Role |
|---|---|---|
| **Streamlit Dashboard (UI)** | `streamlit run app.py` | Configure, monitor, and manually trigger trades |
| **Background Daemon** | `python main.py` | Runs 24/7, fires the pipeline on schedule |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  STREAMLIT DASHBOARD                    │
│   app.py · Live Chart · Scheduler · Settings            │
│   (Configure rules, monitor equity, view event log)     │
└───────────────────┬─────────────────────────────────────┘
                    │  config/user_prefs.json
                    │  schedules.json
┌───────────────────▼─────────────────────────────────────┐
│               BACKGROUND DAEMON (main.py)               │
│   Runs infinite loop · Checks schedule every minute     │
│   Triggers pipeline on time match                        │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│             EXECUTION PIPELINE (engine.py)              │
│                                                         │
│  MT5 Data Feed  →  Strategy  →  FTMO Risk Guard         │
│       │               │               │                 │
│  OMS Submit  →  Execution  →  Portfolio MTM             │
│                                       │                 │
│                              Storage + Notifier         │
└─────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   Telegram       Email     Desktop Toast
```

---

## Project Structure

```
Prop_Firm/
│
├── app.py                   # Streamlit dashboard (Page 1: Bot Control)
├── main.py                  # Background trading daemon (scheduler loop)
├── requirements.txt         # Python dependencies
├── schedules.json           # Trading schedule (days + times)
├── .gitignore               # Git ignore rules
│
├── pages/
│   ├── 1_📈_Live_Chart.py   # Real-time MT5 chart with strategy signals
│   ├── 2_📅_Scheduler.py    # Schedule configuration UI
│   └── 3_⚙️_Settings.py     # MT5 credentials + strategy + alert settings
│
├── core/
│   ├── engine.py            # Main pipeline orchestrator
│   ├── strategy.py          # Dow Theory EMA cross signal generator
│   ├── risk_manager.py      # FTMO risk guard + ADR-based order sizing
│   ├── execution.py         # MT5 order execution (live / paper)
│   ├── oms.py               # Order Management System
│   ├── portfolio.py         # Portfolio mark-to-market tracking
│   ├── notifier.py          # Multi-channel alert broadcaster
│   ├── storage.py           # Event log + trade + PnL persistence
│   ├── signal_store.py      # Signal audit trail (data/signals.json)
│   ├── mt5_connection.py    # MT5 initialize + login helper
│   ├── mt5_data.py          # MT5 candle + LTP fetcher
│   └── chart_utils.py       # Plotly chart renderer
│
├── Utilities/
│   ├── ui_components.py     # Shared Streamlit CSS + sidebar components
│   └── technical_indicators.py  # ATR, volume helpers
│
├── config/
│   ├── config.py            # App-level constants
│   └── user_prefs.json      # ⚠️ Runtime config (gitignored — holds credentials)
│
└── data/                    # ⚠️ Runtime data (gitignored)
    ├── events.jsonl         # Live event log
    ├── trades.json          # Executed trade history
    ├── signals.json         # Signal audit trail
    └── pnl_history.json     # Equity snapshots
```

---

## Core Modules

### `core/engine.py` — Pipeline Orchestrator
Runs `run_pipeline_tick()` — the full sequence from data fetch to portfolio update. Called by both the scheduler (`main.py`) and the manual LTS button in the UI.

**Pipeline steps:**
1. Read `config/user_prefs.json` for live settings
2. Fetch OHLCV candles + LTP from MT5
3. Run Dow Theory strategy → `BUY` / `SELL` / `HOLD`
4. Evaluate all 6 FTMO risk rules
5. Build order (ADR-based SL, 1:2 R:R, leverage-validated lot size)
6. Execute via `mt5.order_send()`
7. Update portfolio MTM + persist to storage
8. Broadcast Telegram / Email / Desktop alert

---

### `core/strategy.py` — Signal Generator
Implements a **Dow Theory EMA Cross** strategy:
- Fast EMA / Slow EMA crossover for trend direction
- ATR filter to skip low-volatility environments
- Volume filter (optional)
- Market phase classification: **Bullish / Bearish / Sideways**

---

### `core/risk_manager.py` — FTMO Risk Guard + Order Sizing

**Part 1 — FTMO Rule Checks (6 checks before every trade):**

| Check | Rule |
|---|---|
| 1 | Daily loss limit (5% of starting balance) |
| 2 | Max overall drawdown (10%) |
| 3 | Daily budget vs trade risk |
| 4 | Max DD buffer vs trade risk |
| 5 | Max open positions (live `mt5.positions_total()`) |
| 6 | High-impact news blackout ±2 min (leverage > 1:30 only) |

**Part 2 — ADR-Based Order Sizing:**
- SL = 15% of 14-day Average Daily Range
- TP = SL × R:R ratio (default 1:2)
- Lot size = `risk_per_trade / (sl_ticks × tick_value)`
- Leverage constraint: scales lots down if margin needed > 30% of free margin

---

### `core/notifier.py` — Alert Broadcaster

Sends alerts across all enabled channels in background threads:

| Channel | Trigger |
|---|---|
| Telegram (text + chart image) | Every signal, risk block, and error |
| Email (Gmail SMTP) | Same events |
| Windows Desktop Toast | Same events |
| Sound (system beep) | Blocks and fills |

All critical failures (data fetch fail, MT5 disconnect, order send fail, pipeline crash) fire a Telegram alert — not just successful trades.

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- MetaTrader 5 terminal installed on Windows
- FTMO Demo or Funded account credentials

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd Prop_Firm
```

### 2. Create and activate virtual environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create your config file
```bash
copy config\user_prefs.json.example config\user_prefs.json
```
Then fill in your credentials (see [Configuration](#configuration)).

---

## Configuration

All settings are managed via **`config/user_prefs.json`** (gitignored). Configure them through the **Settings page** in the Streamlit UI, or edit the file directly:

```json
{
  "mt5_account":       "YOUR_ACCOUNT_NUMBER",
  "mt5_password":      "YOUR_PASSWORD",
  "mt5_server":        "FTMO-Demo",
  "mt5_path":          "",

  "trading_symbol":    "XAUUSD",
  "timeframe":         "1h",
  "bar_count":         350,

  "ema_fast":          5,
  "ema_slow":          8,
  "use_vol_filter":    false,
  "use_atr_filter":    true,

  "execution_mode":    "MetaTrader5",
  "daily_reset_time":  "00:00",
  "ftmo_sod_balance":  10000.0,

  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id":   "YOUR_CHAT_ID",
  "gmail_sender":       "you@gmail.com",
  "gmail_app_password": "YOUR_APP_PASSWORD",
  "gmail_receiver":     "alerts@yourdomain.com"
}
```

> ⚠️ **Never commit `user_prefs.json`** — it contains live credentials. It is already gitignored.

---

## Running the System

The system has **two independent processes** that should both be running during active trading hours:

### Terminal 1 — Streamlit Dashboard
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`

### Terminal 2 — Background Trading Daemon
```bash
python main.py
```
Runs the scheduler loop. Logs all events to `data/events.jsonl`.

> The dashboard reads from the same log file — so you see live events in the UI as the daemon executes trades.

---

## FTMO Risk Guard

The engine enforces FTMO rules **before every trade**. If any check fails, the trade is blocked and a Telegram alert fires immediately.

### Daily Reset
The SOD (Start-of-Day) balance snapshot is taken automatically at the configured `daily_reset_time` (default `00:00` Prague time = `03:30 IST`).

### News Blackout
For accounts with leverage **> 1:30**, trading is automatically blocked within **±2 minutes** of any HIGH-impact ForexFactory event affecting the traded currency. A warning is issued **3–15 minutes** before the blackout window.

Time zones handled:
- **FTMO Server Time**: `Europe/Helsinki` (GMT+3, matches MT5 chart)
- **Daily Reset**: `Europe/Prague` (CET/CEST)
- **Display**: Both FTMO and IST shown in all alerts

---

## Notification Channels

### Telegram Setup
1. Message `@BotFather` on Telegram → Create a new bot → Copy the token
2. Get your Chat ID from `@userinfobot`
3. Enter both in Settings page or `user_prefs.json`

### Gmail Setup
1. Enable 2FA on your Google account
2. Generate an **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Enter your Gmail address and the App Password in settings

---

## Scheduling Trades

Use the **Scheduler page** (`pages/2_📅_Scheduler.py`) to define when the bot is allowed to trade.

Schedules are stored in `schedules.json`:
```json
[
  { "day": "Monday",    "time": "09:30", "enabled": true },
  { "day": "Tuesday",   "time": "14:00", "enabled": true },
  { "day": "Wednesday", "time": "09:30", "enabled": false }
]
```
The daemon checks the schedule every minute and fires the pipeline only on exact day + time matches.

---

## UI Pages

| Page | File | Purpose |
|---|---|---|
| **Bot Control** | `app.py` | Start/stop bot, manual LTS trigger, live metrics, event log |
| **Live Chart** | `pages/1_📈_Live_Chart.py` | Real-time MT5 chart with EMA signals and trade markers |
| **Scheduler** | `pages/2_📅_Scheduler.py` | Add/remove/enable trading schedules |
| **Settings** | `pages/3_⚙️_Settings.py` | MT5 credentials, strategy params, alert config |

---

## ⚠️ Disclaimer

This software is for **educational and research purposes**. Trading financial instruments carries significant risk. The authors are not responsible for any financial losses incurred through use of this software. Always test thoroughly on a **demo account** before connecting to a live funded account.
