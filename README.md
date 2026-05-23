# ⚡ Trade Pulse Quants

> **Fully Automated, Event-Driven Algorithmic Trading Engine for FTMO Prop Firm Accounts**  
> Built with Python · MetaTrader 5 · Dow Theory · Quantitative Risk Engine · Real-Time Multi-Channel Alerts

---

## 📋 Table of Contents

1. [What is Trade Pulse Quants?](#1-what-is-trade-pulse-quants)
2. [Why This System Exists](#2-why-this-system-exists)
3. [System Architecture](#3-system-architecture)
4. [Project Structure](#4-project-structure)
5. [Trading Strategy — Dow Theory EMA Cross](#5-trading-strategy--dow-theory-ema-cross)
6. [Quantitative Risk Engine](#6-quantitative-risk-engine)
7. [FTMO Compliance Guard (6-Point Check)](#7-ftmo-compliance-guard-6-point-check)
8. [Order Management System (OMS)](#8-order-management-system-oms)
9. [Execution Engine](#9-execution-engine)
10. [Notification & Alert System](#10-notification--alert-system)
11. [Chart Rendering Engine](#11-chart-rendering-engine)
12. [Scheduling & Automation](#12-scheduling--automation)
13. [Timezone Handling](#13-timezone-handling)
14. [Streamlit Dashboard (UI)](#14-streamlit-dashboard-ui)
15. [Setup & Installation](#15-setup--installation)
16. [Configuration](#16-configuration)
17. [Running the System](#17-running-the-system)
18. [Deployment on AWS Lightsail](#18-deployment-on-aws-lightsail)
19. [Git Branch Strategy](#19-git-branch-strategy)
20. [Disclaimer](#20-disclaimer)

---

## 1. What is Trade Pulse Quants?

**Trade Pulse Quants** is a production-grade, fully automated algorithmic trading system purpose-built for **FTMO Prop Firm Challenge and Funded accounts**. It connects directly to **MetaTrader 5**, evaluates market conditions using a proprietary Dow Theory strategy, enforces all FTMO risk rules before every single trade, and executes live orders — all while broadcasting real-time alerts with professional charts to Telegram, Email, and Desktop.

The system is designed to run **24/7 on a cloud server** (AWS Lightsail) with zero human intervention during market hours.

### Key Highlights

| Feature | Description |
|---|---|
| **Fully Automated** | Runs autonomously on a schedule. No manual intervention required. |
| **FTMO Compliant** | Enforces all 6 FTMO risk rules before every trade automatically. |
| **Quantitative Risk** | Dynamic ATR-based volatility regime engine adapts to market conditions in real-time. |
| **Structure-Aware SL** | Stop losses respect actual market structure (swing highs/lows), not just math. |
| **Fixed Dollar Risk** | Every trade risks exactly $100 (configurable), regardless of market conditions. |
| **Multi-Channel Alerts** | Telegram (text + chart), Email, Windows Desktop Toast, Sound alerts. |
| **Ultra-Lightweight** | Runs safely on a 2GB RAM VPS. No heavy browser dependencies. |
| **Professional Dashboard** | Real-time Streamlit UI for monitoring, configuring, and manual testing. |

---

## 2. Why This System Exists

### The Problem
Prop firm traders face a unique challenge: they must generate consistent profits while **never** violating strict risk rules (5% daily loss limit, 10% max drawdown). Manual trading under these constraints is psychologically exhausting and error-prone. A single emotional trade can blow an entire funded account.

### The Solution
Trade Pulse Quants removes the human element from execution. The system:
- **Never trades emotionally** — it follows the strategy rules with mathematical precision.
- **Never violates risk limits** — the FTMO guard physically blocks any trade that would breach a rule.
- **Never misses a setup** — it monitors the market on schedule and executes instantly when conditions align.
- **Always notifies you** — every action (trade, block, error) is immediately sent to your phone via Telegram.

### Why Not Use Off-the-Shelf Bots?
Most commercial bots are black-box systems with hidden strategies and no FTMO-specific compliance. Trade Pulse Quants is:
- **Fully transparent** — every line of logic is visible and auditable.
- **FTMO-native** — built from the ground up around FTMO's specific timezone (Helsinki), daily reset rules, and leverage constraints.
- **Customizable** — every parameter (EMA periods, risk amount, R:R ratio, schedule) is configurable via the UI.

---

## 3. System Architecture

The system is split into **two independent processes** that communicate through shared configuration files:

```text
┌─────────────────────────────────────────────────────────────┐
│                    STREAMLIT DASHBOARD                       │
│   app.py · Live Chart · Scheduler · Settings                │
│   (Configure rules, monitor equity, view event log)         │
│                                                             │
│   ► Runs on: http://localhost:8501                           │
│   ► Purpose: Human interface for monitoring and control     │
└────────────────────────┬────────────────────────────────────┘
                         │  Shared Files:
                         │  ├── config/user_prefs.json
                         │  ├── schedules.json
                         │  └── data/events.jsonl
┌────────────────────────▼────────────────────────────────────┐
│                 BACKGROUND DAEMON (main.py)                  │
│   Infinite loop · Checks schedule every 60 seconds          │
│   Fires pipeline on exact day + time match (FTMO timezone)  │
│                                                             │
│   ► Runs in: Terminal / Windows Service                     │
│   ► Purpose: Autonomous trading execution                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│               EXECUTION PIPELINE (engine.py)                │
│                                                             │
│  Step 1: MT5 Data Feed (OHLCV candles + Live Price)         │
│  Step 2: Dow Theory Strategy (EMA cross + fractal swings)   │
│  Step 3: FTMO Risk Guard (6 compliance checks)              │
│  Step 4: Quantitative Order Builder (ATR sizing)            │
│  Step 5: OMS Submission (duplicate prevention)              │
│  Step 6: MT5 Order Execution (mt5.order_send)               │
│  Step 7: Portfolio Mark-to-Market Update                    │
│  Step 8: Chart Generation (mplfinance)                      │
│  Step 9: Multi-Channel Notification Broadcast               │
└─────────────────────────────────────────────────────────────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
        Telegram      Email     Desktop Toast
      (text+chart)   (SMTP)    (Windows Native)
```

### Why Two Separate Processes?

| Advantage | Explanation |
|---|---|
| **Crash Isolation** | If the UI crashes, the daemon continues trading. If the daemon crashes, the UI stays up for monitoring. |
| **Resource Efficiency** | On a 2GB VPS, you can stop the UI when not actively monitoring, saving ~150MB of RAM. |
| **Security** | The daemon runs headless with no web interface exposed to the internet. |

---

## 4. Project Structure

```text
Prop_Firm/
│
├── app.py                       # Streamlit dashboard (Page 1: Bot Control)
├── main.py                      # Background trading daemon (scheduler loop)
├── requirements.txt             # Python dependencies
├── schedules.json               # Trading schedule (days + times)
├── run_daemon.bat               # One-click daemon launcher (Windows)
├── run_dashboard.bat            # One-click dashboard launcher (Windows)
│
├── pages/                       # Streamlit multi-page UI
│   ├── 1_📈_Live_Chart.py       # Real-time MT5 candlestick chart with signals
│   ├── 2_📅_Scheduler.py        # Schedule configuration interface
│   └── 3_⚙️_Settings.py         # MT5 credentials + strategy + alert settings
│
├── core/                        # Core engine modules
│   ├── engine.py                # Pipeline orchestrator (the "brain")
│   ├── strategy.py              # Dow Theory EMA cross signal generator
│   ├── risk_manager.py          # FTMO guard + ATR order sizing
│   ├── oms.py                   # Order Management System
│   ├── execution.py             # MT5 order execution engine
│   ├── portfolio.py             # Portfolio mark-to-market tracking
│   ├── notifier.py              # Multi-channel alert broadcaster
│   ├── chart_utils.py           # Dual chart renderer (Plotly + mplfinance)
│   ├── storage.py               # Event log + trade + PnL persistence
│   ├── signal_store.py          # Signal audit trail
│   ├── mt5_connection.py        # MT5 initialize + login helper
│   ├── mt5_data.py              # MT5 candle + LTP fetcher
│   ├── ftmo_time.py             # FTMO timezone utilities
│   ├── scheduler_helper.py      # Schedule matching logic
│   ├── bot_lifecycle.py         # Start/stop logging for uptime tracking
│   ├── data_feed.py             # MarketEvent data class
│   └── prop_firm_risk.py        # Prop firm specific risk constants
│
├── Utilities/                   # Shared helpers
│   ├── ui_components.py         # Streamlit CSS + sidebar components
│   └── technical_indicators.py  # ATR, EMA, RSI calculation functions
│
├── config/
│   ├── config.py                # App-level constants
│   └── user_prefs.json          # ⚠️ Runtime config (gitignored — holds credentials)
│
└── data/                        # ⚠️ Runtime data (gitignored)
    ├── events.jsonl              # Live event log (JSON Lines format)
    ├── trades.json               # Executed trade history
    ├── signals.json              # Signal audit trail
    ├── pnl_history.json          # Equity snapshots
    ├── bot_state.json            # Daemon start/stop state
    └── bot_lifecycle.log         # Human-readable lifecycle log
```

---

## 5. Trading Strategy — Dow Theory EMA Cross

> **File:** `core/strategy.py` → Class: `RealTimeSignalGenerator`

The strategy is based on **Charles Dow's Market Theory**, which states that prices move in trends defined by successive higher highs and higher lows (uptrend) or lower highs and lower lows (downtrend).

### Step-by-Step Signal Generation

#### Step 1: Calculate Technical Indicators
When the daemon fires a pipeline tick, the engine fetches the latest OHLCV candles from MetaTrader 5 and calculates:
- **Fast EMA** (default: 5-period) — reacts quickly to recent price action.
- **Slow EMA** (default: 8-period) — smooths out noise and shows the underlying trend.
- **ATR** (14-period Average True Range) — measures current market volatility.
- **ATR Slope** — the rate of change of ATR (is volatility expanding or contracting?).
- **ATR Percentile** — where current ATR ranks relative to the last 200 periods (0.0 to 1.0).
- **Volume MA** (21-period) — average trading volume for volume confirmation.

> **Why EMA over SMA?** EMAs give more weight to recent prices, making them faster to react to trend changes. In intraday forex trading, speed of reaction is critical.

#### Step 2: Identify Market Phase
The system classifies the current market into one of three phases:

| Phase | Condition | Meaning |
|---|---|---|
| **BULLISH** | Close > Fast EMA > Slow EMA | Price is in an uptrend. Both EMAs are stacked bullishly. |
| **BEARISH** | Close < Fast EMA < Slow EMA | Price is in a downtrend. Both EMAs are stacked bearishly. |
| **SIDEWAYS** | Any other arrangement | No clear trend. The system will not trade. |

> **Why is SIDEWAYS important?** Trading in a sideways market leads to whipsaws (false signals). By requiring a clear phase alignment, the system avoids the majority of losing trades.

#### Step 3: Detect Fractal Swing Points
The strategy scans the historical candles and identifies **Swing Highs** (local peaks) and **Swing Lows** (local troughs) using a fractal detection algorithm. These are the key structural levels of the market:
- **Last High** — the price of the most recent confirmed swing high (resistance level).
- **Last Low** — the price of the most recent confirmed swing low (support level).

These levels are displayed as horizontal dashed lines on the Live Chart.

#### Step 4: Generate BUY/SELL Signal
A signal is generated only when ALL conditions align:

**BUY Signal:**
```
Market Phase = BULLISH
AND Close Price > Last Swing High  (breakout above resistance)
AND Volume > Volume MA             (volume confirmation — optional)
AND ATR Slope > 0                  (volatility is expanding — optional)
```

**SELL Signal:**
```
Market Phase = BEARISH
AND Close Price < Last Swing Low   (breakdown below support)
AND Volume > Volume MA             (volume confirmation — optional)
AND ATR Slope > 0                  (volatility is expanding — optional)
```

> **Why require a breakout?** A breakout above a swing high confirms that the market has made a new "higher high", which is the textbook definition of an uptrend continuation in Dow Theory. This dramatically reduces false signals compared to simple EMA crossovers.

#### Step 5: Deduplication
The system prevents firing the same signal twice on the same breakout level. If a BUY was already triggered at Swing High 1.1350, another BUY will not fire until a **new, different** Swing High is broken.

---

## 6. Quantitative Risk Engine

> **File:** `core/risk_manager.py` → Method: `build_order()`

Once a BUY or SELL signal is generated, the Risk Engine takes over to calculate the exact order parameters. This is the mathematical heart of the system.

### 6.1 Volatility Regime Classification

The system doesn't use a static stop loss distance. Instead, it dynamically adapts to the current market volatility using a **rolling ATR percentile**:

| ATR Percentile | Regime | ATR Multiplier | Meaning |
|---|---|---|---|
| Below 30th percentile | **Low Volatility** | 1.2× ATR | Market is quiet. Tighter stops are safe. |
| 30th – 70th percentile | **Normal Volatility** | 1.5× ATR | Standard market conditions. |
| Above 70th percentile | **High Volatility** | 1.8× ATR | Market is wild. Wider stops prevent premature stop-outs. |

> **Why use percentiles instead of fixed values?** A fixed ATR value (e.g., "use 15 pips") would fail when market conditions change. During holidays, ATR might be 8 pips; during NFP week, it might be 40 pips. The percentile ranking automatically adapts to the "new normal" of whatever the current regime is.

### 6.2 Structure-Aware Stop Loss

The system calculates two potential stop loss distances and picks the **larger** one:

```
ATR Stop Distance    = ATR × Volatility Multiplier (1.2, 1.5, or 1.8)
Structure Distance   = Distance from entry to nearest structural level
Final SL Distance    = MAX(ATR_Distance, Structure_Distance)
```

**For a BUY signal:**
- Structure Distance = `Entry Price - Last Swing Low` (distance down to support)

**For a SELL signal:**
- Structure Distance = `Last Swing High - Entry Price` (distance up to resistance)

> **Why use MAX instead of just ATR?** If the ATR says "place your stop 25 pips away" but the nearest support level is 40 pips below your entry, placing the stop at 25 pips would put it right inside the support zone — a high-probability area for a bounce. By using MAX, the stop is always placed beyond the structural level, giving the trade proper room to work.

### 6.3 Safety Bounds

Two guardrails prevent extreme stop loss values:
- **Minimum SL**: 5 × tick_size (prevents impossibly tight stops)
- **Maximum SL**: 5% of the entry price (prevents absurdly wide stops — trade is blocked entirely)

### 6.4 Take Profit Calculation

Take Profit is calculated using a fixed Risk-to-Reward ratio:

```
TP Distance = Final SL Distance × R:R Ratio (default: 2.0)
```

This means if you risk $100 on the stop loss, the take profit target is $200. Every trade has a mathematical edge: you only need to win 34% of the time to break even.

### 6.5 Fixed Dollar Position Sizing

The lot size is calculated to risk **exactly** the configured dollar amount (default: $100):

```
Risk Per Lot  = (SL Distance / Tick Size) × Tick Value
Lot Size      = $100 / Risk Per Lot
```

This ensures that regardless of how wide or tight the stop loss is, you always risk the same dollar amount.

### 6.6 Leverage Protection

Before the order is submitted, the system checks if you have enough margin:

```
Margin Needed = (Lots × Contract Size × Price) / Leverage
Margin Cap    = Free Margin × 30%
```

If the margin needed exceeds 30% of your free margin, the lot size is automatically scaled down. This prevents margin calls and ensures you always have buffer capital.

### 6.7 Spread Filter

Before any order is built, the system checks the live bid-ask spread:

```
Maximum Allowed Spread = ATR × 10%
```

If the current spread exceeds 10% of the ATR, the trade is **blocked entirely**. This prevents entering trades during illiquid periods (e.g., market open, news spikes) where slippage would destroy the risk-reward ratio.

---

## 7. FTMO Compliance Guard (6-Point Check)

> **File:** `core/risk_manager.py` → Method: `evaluate_risk()`

Before any trade is sent to MetaTrader 5, the system runs **6 mandatory compliance checks**. If ANY check fails, the trade is **blocked** and a Telegram alert is fired immediately explaining why.

| Check | Rule | What It Does |
|---|---|---|
| **1. Daily Loss Limit** | Max 5% of starting balance | Calculates today's realized + unrealized P&L. If adding this trade's risk would breach 5%, the trade is blocked. |
| **2. Max Overall Drawdown** | Max 10% from initial equity | Tracks the total drawdown from the FTMO starting balance. Blocks any trade that could push drawdown beyond 10%. |
| **3. Daily Budget Check** | Remaining daily budget > trade risk | Ensures you have enough "daily budget" left to absorb a potential loss on this trade. |
| **4. Drawdown Buffer Check** | Remaining DD buffer > trade risk | Ensures you have enough overall drawdown buffer remaining. |
| **5. Max Open Positions** | Default: 1 position at a time | Queries `mt5.positions_total()` to check how many trades are currently open. Blocks if at capacity. |
| **6. News Blackout** | ±2 min around HIGH-impact events | For accounts with leverage > 1:30, FTMO prohibits trading around major news events. The system fetches the ForexFactory calendar daily and automatically blocks trades within ±2 minutes of any HIGH-impact event affecting the traded currency. |

### News Blackout Detail

The news system has two modes:

| Mode | Time Window | Action |
|---|---|---|
| **HARD BLOCK** | Within ±2 minutes of event | Trade is completely blocked. Telegram alert sent. |
| **EARLY WARNING** | 3–15 minutes before event | Trade is allowed, but a warning is attached to the notification. |

> **Why is this critical?** FTMO specifically states that for accounts with leverage above 1:30, opening or closing trades during high-impact news events can result in account termination. This system eliminates that risk entirely by automating the blackout window.

---

## 8. Order Management System (OMS)

> **File:** `core/oms.py` → Class: `OMS`

The OMS acts as the intermediary between the Risk Manager and the Execution Engine. Its responsibilities:

1. **Order ID Generation**: Every order receives a unique 8-character UUID (e.g., `2DB3218F`).
2. **Lifecycle Tracking**: Each order moves through a state machine: `PENDING → SUBMITTED → FILLED / REJECTED / CANCELLED`.
3. **Duplicate Prevention**: If a trade for the same symbol and direction is already open, the OMS blocks the duplicate.
4. **Audit Trail**: All order state transitions are logged for compliance review.

### Order Lifecycle

```text
PENDING  →  Risk Guard approved the trade
    ↓
SUBMITTED  →  Sent to MT5 via mt5.order_send()
    ↓
FILLED  →  MT5 accepted and executed the order
    or
REJECTED  →  MT5 refused (insufficient margin, symbol not found, AutoTrading disabled, etc.)
```

---

## 9. Execution Engine

> **File:** `core/execution.py` → Class: `ExecutionEngine`

The Execution Engine is responsible for the physical act of sending orders to MetaTrader 5. It supports three modes:

| Mode | Description |
|---|---|
| **Live** | Sends real orders to MT5 via `mt5.order_send()`. Real money is at stake. |
| **Paper** | Simulates order execution without touching real capital. |
| **Backtest** | Historical simulation using OHLCV data with slippage models. |

When an order is executed in live mode, the engine:
1. Constructs the MT5 `TradeRequest` object with symbol, lot size, SL, TP, and order type.
2. Sends it via `mt5.order_send()`.
3. Parses the response code (`retcode`). If `10009` (success), it creates a `FillEvent`.
4. If rejected (e.g., `10027` — AutoTrading disabled), it logs the failure and triggers a Telegram alert.

---

## 10. Notification & Alert System

> **File:** `core/notifier.py`

The notification system broadcasts alerts across **4 channels simultaneously** using background threads, ensuring the daemon loop never freezes waiting for a slow network request.

### Channels

| Channel | Technology | What It Sends |
|---|---|---|
| **Telegram** | Bot API (HTTPS) | Formatted text message + high-res candlestick chart image |
| **Email** | Gmail SMTP (SSL) | HTML-formatted trade summary |
| **Windows Toast** | PowerShell + System.Windows.Forms | Native Windows desktop popup notification |
| **Sound** | `winsound` module | System beep alert for immediate physical attention |

### Alert Types

| Event | Telegram | Email | Desktop | Sound |
|---|---|---|---|---|
| BUY/SELL Signal | ✅ Text + Chart | ✅ | ✅ | ✅ |
| Trade Blocked (Risk) | ✅ | ✅ | ✅ | ✅ |
| Trade Rejected (MT5) | ✅ | ✅ | ✅ | ✅ |
| Data Fetch Failed | ✅ | ✅ | ✅ | — |
| MT5 Disconnected | ✅ | ✅ | ✅ | — |
| Pipeline Crash | ✅ | — | — | — |
| Daemon Started | ✅ | — | — | — |
| HOLD (Scheduled) | Silent by default | — | — | — |

### Smart Notification Logic

The system intelligently suppresses unnecessary notifications:
- **Scheduled ticks that result in HOLD**: Silent by default. The daemon runs every hour — if it pinged you "HOLD" every time, your phone would be flooded with 100+ messages per day.
- **Manual LTS button click**: Always sends a notification, even for HOLD. Because you physically clicked the button, you want confirmation.
- **Toggle**: You can override this behavior with the `notify_on_hold` setting in the UI.

### Non-Blocking Design

All alert threads are started as `daemon=True` threads. This means:
- The trading pipeline does not wait for Telegram to respond before moving to the next candle.
- If Telegram's servers are slow (or down), the trade still executes on time.
- The daemon loop is never blocked by a network timeout.

---

## 11. Chart Rendering Engine

> **File:** `core/chart_utils.py`

The system contains **two separate chart rendering engines**, each optimized for its specific use case:

### Engine 1: Plotly (Interactive — For the Web UI)

| Property | Value |
|---|---|
| **Used by** | Streamlit Live Chart page |
| **Rendering** | Client-side (user's browser GPU) |
| **Server Cost** | Zero — the server sends raw JSON, the browser does all the work |
| **Features** | Zoom, pan, hover tooltips, real-time updates |

### Engine 2: mplfinance (Static — For Background Notifications)

| Property | Value |
|---|---|
| **Used by** | Background daemon (Telegram/Email charts) |
| **Rendering** | Server-side using Matplotlib's C-based `agg` backend |
| **Server Cost** | ~1% CPU, ~5MB RAM |
| **Output** | 150 DPI PNG byte stream (in-memory, no temp files) |

> **Why two engines?** Plotly requires a full web browser (Kaleido/Chromium) to convert its JavaScript charts into static images. On a 2GB VPS, launching a hidden Chrome instance would spike RAM to 100% and crash the daemon. mplfinance renders natively in C with practically zero overhead.

### Chart Visual Elements

Both engines render the same visual elements for consistency:

| Element | Color | Description |
|---|---|---|
| Bullish Candles | Emerald Green (`#10b981`) | Price closed higher than it opened |
| Bearish Candles | Sharp Red (`#ef4444`) | Price closed lower than it opened |
| Fast EMA | Soft Purple (`#c084fc`) | 5-period Exponential Moving Average |
| Slow EMA | Soft Cyan (`#38bdf8`) | 8-period Exponential Moving Average |
| Last High Line | Green Dashed | Most recent swing high (resistance) |
| Last Low Line | Red Dashed | Most recent swing low (support) |
| BUY Markers | Green Triangle ▲ | Below the candle where a BUY signal fired |
| SELL Markers | Red Triangle ▼ | Above the candle where a SELL signal fired |
| Volume Bars | Dark Slate (`#1e293b`) | Trading volume sub-chart |
| Background | Deep Slate (`#0f172a`) | Premium dark theme |

---

## 12. Scheduling & Automation

> **Files:** `main.py`, `core/scheduler_helper.py`, `schedules.json`

### How the Scheduler Works

The background daemon (`main.py`) runs an infinite loop that checks the clock every **60 seconds**:

```text
while True:
    1. Get current time in FTMO timezone (Europe/Helsinki)
    2. Compare against all enabled schedule slots in schedules.json
    3. If day + time matches a slot → Fire the pipeline
    4. Mark the slot as "completed" for this minute (prevents double-firing)
    5. Sleep 60 seconds
    6. Repeat
```

### Schedule Format

Schedules are stored in `schedules.json`:
```json
[
  { "id": "SCH_Monday_0900_A1B2C3", "day": "Monday", "time": "09:00", "enabled": true },
  { "id": "SCH_Monday_1000_D4E5F6", "day": "Monday", "time": "10:00", "enabled": true },
  { "id": "SCH_Friday_1500_8256EF", "day": "Friday", "time": "15:00", "enabled": true }
]
```

All times are in **FTMO timezone (Europe/Helsinki, GMT+3)**. The system automatically converts to whatever timezone the server is running in.

### Manual Testing Commands

| Command | Description |
|---|---|
| `python main.py` | Start the daemon loop (runs forever until Ctrl+C) |
| `python main.py --tick-now` | Fire a single pipeline tick immediately (for testing) |
| `python main.py --check-schedule` | Print all enabled slots and show when the next one fires |

> **Why schedule-based instead of continuous?** Forex candles close at fixed intervals (e.g., every 1 hour). Running the strategy mid-candle would produce unreliable signals because the candle hasn't finished forming. By scheduling ticks at candle-close times, every signal is based on a fully confirmed, closed candle.

---

## 13. Timezone Handling

FTMO uses a specific set of timezones that differ from most brokers. The system handles all of them automatically:

| Context | Timezone | Why |
|---|---|---|
| **MT5 Server Charts** | `Europe/Helsinki` (GMT+3) | FTMO's MetaTrader 5 servers run on Helsinki time. All candle timestamps match this. |
| **FTMO Daily Reset** | `Europe/Prague` (CET/CEST) | FTMO calculates daily P&L and resets limits at midnight Prague time. |
| **Schedule Matching** | `Europe/Helsinki` | All schedule slots are matched against Helsinki time so they align with candle closes. |
| **User Display** | IST + FTMO time shown together | The UI and notifications always display both FTMO time and IST for easy reading. |

> **Why is this important?** If the system used the wrong timezone, it would fire the pipeline at the wrong time (e.g., mid-candle instead of candle-close), producing unreliable signals. Or worse, it would miscalculate the daily loss limit reset window, potentially leading to FTMO rule violations.

---

## 14. Streamlit Dashboard (UI)

The web-based dashboard provides a real-time monitoring and configuration interface.

### Page 1: Bot Control (`app.py`)

| Feature | Description |
|---|---|
| **Status Header** | Shows IST time, FTMO time, and bot uptime side by side |
| **CMP Widget** | Current Market Price (Last Traded Price from MT5) |
| **Fractal High/Low** | Latest structural swing high and swing low levels |
| **EMA Display** | Current Fast EMA and Slow EMA values |
| **LTS Button** | One-click manual pipeline trigger (fires a full tick and sends Telegram notification) |
| **Event Log** | Live-updating table of all daemon events (trades, blocks, errors) |

### Page 2: Live Chart (`pages/1_📈_Live_Chart.py`)

| Feature | Description |
|---|---|
| **Interactive Candlestick** | Plotly-powered chart with zoom, pan, and hover tooltips |
| **EMA Overlays** | Fast and Slow EMAs rendered directly on the price chart |
| **Signal Markers** | BUY (green ▲) and SELL (red ▼) markers at the exact candle where signals fired |
| **Structural Lines** | Horizontal dashed lines for Last High (green) and Last Low (red) |
| **Volume Sub-Chart** | Volume bars with a Volume MA overlay |
| **Auto-Refresh** | Configurable auto-refresh interval to keep the chart current |

### Page 3: Scheduler (`pages/2_📅_Scheduler.py`)

| Feature | Description |
|---|---|
| **Weekly Grid** | Visual grid of all 7 days × 24 hours showing active schedule slots |
| **Bulk Generator** | Automatically generate hourly slots for the entire trading week |
| **Enable/Disable** | Toggle individual slots on/off without deleting them |
| **Next Slot Preview** | Shows exactly when the next scheduled tick will fire |

### Page 4: Settings (`pages/3_⚙️_Settings.py`)

| Feature | Description |
|---|---|
| **MT5 Credentials** | Account number, password, server, terminal path |
| **Trading Symbol** | Which instrument to trade (e.g., EURUSD, XAUUSD) |
| **Timeframe** | Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, D1) |
| **EMA Periods** | Fast and Slow EMA period configuration |
| **Filters** | Toggle Volume Filter and ATR Filter on/off |
| **Alert Config** | Telegram Bot Token, Chat ID, Gmail credentials |
| **FTMO Balance** | Starting balance for daily loss calculations |

---

## 15. Setup & Installation

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Tested on 3.10, 3.11, 3.12 |
| MetaTrader 5 | Latest | Must be installed on the same Windows machine |
| Windows OS | 10/11/Server 2022 | Required for MT5 (MetaTrader 5 is Windows-only) |
| FTMO Account | Demo or Funded | MT5 credentials from FTMO |

### Step-by-Step Installation

#### Step 1: Clone the Repository
```bash
git clone https://github.com/Quant-Researches/Prop_Firm.git
cd Prop_Firm
git checkout feature/quant_risk_mplfinance
```

#### Step 2: Create Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate
```

#### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

#### Step 4: Configure Credentials
Open the Settings page in the Streamlit UI, or manually edit `config/user_prefs.json`:
```json
{
  "mt5_account":       "YOUR_ACCOUNT_NUMBER",
  "mt5_password":      "YOUR_PASSWORD",
  "mt5_server":        "FTMO-Demo",
  "mt5_path":          "C:\\Program Files\\MetaTrader 5\\terminal64.exe",

  "trading_symbol":    "EURUSD",
  "timeframe":         "1h",
  "bar_count":         350,

  "ema_fast":          5,
  "ema_slow":          8,

  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id":   "YOUR_CHAT_ID",
  "gmail_sender":       "you@gmail.com",
  "gmail_app_password": "YOUR_APP_PASSWORD",
  "gmail_receiver":     "alerts@yourdomain.com",

  "ftmo_sod_balance":  10000.0
}
```

> ⚠️ **Never commit `user_prefs.json`** — it contains live credentials. It is already gitignored.

#### Step 5: Configure Schedule
Use the Scheduler page in the UI, or manually edit `schedules.json` to define your trading hours.

#### Step 6: Verify Installation
```bash
python main.py --tick-now
```
If everything is configured correctly, this will run a single pipeline tick and send a Telegram notification.

---

## 16. Configuration

All runtime settings are managed via `config/user_prefs.json`. They can be edited through the **Settings page** in the Streamlit UI or directly in the file.

### Telegram Setup
1. Message `@BotFather` on Telegram → Create a new bot → Copy the **Bot Token**.
2. Message `@userinfobot` → Copy your **Chat ID**.
3. Enter both in the Settings page.

### Gmail Setup
1. Enable **2-Factor Authentication** on your Google account.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) and generate an **App Password**.
3. Enter your Gmail address and the App Password in the Settings page.

---

## 17. Running the System

### Production Setup (Two Terminals)

**Terminal 1 — Streamlit Dashboard:**
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`

**Terminal 2 — Background Daemon:**
```bash
python main.py
```
Runs the scheduler loop 24/7.

### Quick Launcher Scripts

| Script | Command |
|---|---|
| `run_dashboard.bat` | Double-click to launch the Streamlit UI |
| `run_daemon.bat` | Double-click to launch the background daemon |

> **Pro Tip:** The dashboard and daemon read from the same log files — so you see live events in the UI as the daemon executes trades in real-time.

---

## 18. Deployment on AWS Lightsail

The system is designed to run on an **AWS Lightsail 2GB Windows instance** ($20/month).

### Resource Estimates

| Component | RAM Usage |
|---|---|
| Windows Server 2022 | ~1.0 GB |
| MetaTrader 5 Terminal | ~150–300 MB |
| Python Daemon (`main.py`) | ~100 MB |
| Streamlit UI (`app.py`) | ~150 MB (optional) |
| **Total** | **~1.4–1.6 GB** |

### Optimization Tips

1. **Reduce MT5 Memory**: In MetaTrader 5, go to `Tools → Options → Charts` and set `Max bars in chart` to `5000` (default is 100,000+). This alone saves hundreds of MB.
2. **Stop the UI when not monitoring**: The daemon operates independently. You can close the Streamlit process to free ~150 MB.
3. **No web browsing**: Do not open Chrome/Edge on the server. Each browser tab consumes ~100–300 MB.
4. **Use `mplfinance`**: This branch already replaces the heavy Kaleido renderer with the ultra-lightweight mplfinance engine, saving ~500 MB of peak RAM during chart generation.

---

## 19. Git Branch Strategy

| Branch | Purpose | Status |
|---|---|---|
| `main` | Original codebase from initial development | Stable baseline |
| `prop_firm_Cursor` | Working state before the ATR risk engine overhaul | Safe backup |
| `feature/quant_risk_mplfinance` | **Current active branch** — Quantitative Risk Engine + mplfinance charts | Production ready |

### Switching Between Branches
```bash
# View all branches
git branch -a

# Switch to the backup branch
git checkout prop_firm_Cursor

# Switch back to the latest code
git checkout feature/quant_risk_mplfinance
```

---

## 20. Disclaimer

> ⚠️ **This software is for educational and research purposes only.**
> Trading financial instruments carries significant risk. Past performance does not guarantee future results. The authors are not responsible for any financial losses incurred through use of this software. Always test thoroughly on a **demo account** before connecting to a live funded account. Prop firm rules and risk parameters should be independently verified with your prop firm provider.
