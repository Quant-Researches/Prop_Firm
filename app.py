"""
app.py — Trade Pulse Quants | Bot Control Dashboard (Page 1)
============================================================
Run with:  streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import time
from datetime import datetime, timedelta
import random
import json
from pathlib import Path

from core.engine import TradingEngine
from core.notifier import send_windows_notification

# ── Load persisted user prefs before session state init ────────────────────────
_PREFS_FILE = Path(__file__).parent / "config" / "user_prefs.json"
_USER_PREFS: dict = {}
if _PREFS_FILE.exists():
    try:
        with open(_PREFS_FILE) as _f:
            _USER_PREFS = json.load(_f)
    except Exception:
        pass

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trade Pulse Quants",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Global ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #0a0e1a; color: #e2e8f0; }

/* ── Sidebar shell ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080d1c 0%, #0d1225 60%, #111827 100%);
    border-right: 1px solid #1e293b;
    padding-bottom: 24px;
}

/* ── Sidebar brand header ── */
.sb-brand {
    padding: 20px 16px 16px;
    border-bottom: 1px solid #1e293b;
    margin-bottom: 4px;
}
.sb-brand-title {
    font-size: 1.05rem;
    font-weight: 800;
    background: linear-gradient(90deg, #818cf8, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.3px;
}
.sb-brand-sub {
    font-size: 0.7rem;
    color: #475569;
    margin-top: 3px;
    letter-spacing: 0.5px;
}
.sb-version {
    display: inline-block;
    margin-top: 10px;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.65rem;
    color: #818cf8;
    letter-spacing: 0.5px;
    font-weight: 600;
}

/* ── Sidebar section header ── */
.sb-section {
    margin: 14px 0 6px;
    padding: 0 4px;
}
.sb-section-title {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #334155;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #1a2235;
}

/* ── Sidebar card (groups related controls) ── */
.sb-card {
    background: rgba(255,255,255,0.025);
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 10px;
    transition: border-color 0.2s;
}
.sb-card:hover { border-color: #2d3f5e; }

/* ── Sidebar label ── */
.sb-label {
    font-size: 0.72rem;
    color: #64748b;
    font-weight: 500;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 5px;
}

/* ── Mode badges ── */
.sb-mode-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 4px;
}
.sb-badge {
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.2s;
    letter-spacing: 0.3px;
}
.sb-badge-backtest { background:rgba(99,102,241,0.15);  color:#818cf8; border-color:#4f46e5; }
.sb-badge-paper    { background:rgba(251,191,36,0.12);  color:#fbbf24; border-color:#d97706; }
.sb-badge-live     { background:rgba(239,68,68,0.12);   color:#f87171; border-color:#dc2626; }

/* ── Sidebar stat row ── */
.sb-stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    padding: 5px 0;
    border-bottom: 1px solid #1a2235;
}
.sb-stat-row:last-child { border-bottom: none; }
.sb-stat-key { color: #475569; }
.sb-stat-val { color: #e2e8f0; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
.sb-stat-val.green { color: #10b981; }
.sb-stat-val.yellow { color: #fbbf24; }
.sb-stat-val.red { color: #f87171; }
.sb-stat-val.blue { color: #38bdf8; }

/* ── Sidebar divider ── */
.sb-divider {
    border: none;
    border-top: 1px solid #1a2235;
    margin: 10px 0;
}

/* ── Sidebar footer ── */
.sb-footer {
    padding: 12px 4px 0;
    font-size: 0.65rem;
    color: #334155;
    text-align: center;
    border-top: 1px solid #1a2235;
    margin-top: 16px;
    line-height: 1.8;
}

/* Fix Streamlit widget label colours in sidebar */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span {
    color: #94a3b8 !important;
}
[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] { margin-top: 0 !important; }
[data-testid="stSidebar"] [data-testid="stNumberInput"] input { color: #e2e8f0 !important; background: #0d1225 !important; border-color: #1e293b !important; }

/* ── Header ── */
.tpq-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid #312e81;
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 0 40px rgba(99,102,241,0.15);
}
.tpq-title {
    font-size: 2rem;
    font-weight: 800;
    background: linear-gradient(90deg, #818cf8, #c084fc, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
}
.tpq-subtitle { font-size: 0.85rem; color: #64748b; margin-top: 4px; }
.tpq-clock {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.1rem;
    color: #38bdf8;
    background: rgba(56,189,248,0.08);
    border: 1px solid rgba(56,189,248,0.2);
    border-radius: 8px;
    padding: 10px 18px;
}

/* ── Status badge ── */
.status-running {
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(16,185,129,0.12);
    border: 1px solid rgba(16,185,129,0.4);
    color: #10b981;
    padding: 8px 18px; border-radius: 50px;
    font-weight: 600; font-size: 0.9rem;
    animation: pulse-green 2s infinite;
}
.status-stopped {
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(239,68,68,0.12);
    border: 1px solid rgba(239,68,68,0.4);
    color: #ef4444;
    padding: 8px 18px; border-radius: 50px;
    font-weight: 600; font-size: 0.9rem;
}
@keyframes pulse-green {
    0%, 100% { box-shadow: 0 0 0 0 rgba(16,185,129,0.4); }
    50%       { box-shadow: 0 0 0 6px rgba(16,185,129,0); }
}

/* ── Metric cards ── */
.metric-card {
    background: linear-gradient(135deg, #111827 0%, #1e293b 100%);
    border: 1px solid #1e293b;
    border-radius: 14px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
}
.metric-card:hover { border-color: #4f46e5; }
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--accent, linear-gradient(90deg, #818cf8, #c084fc));
    border-radius: 14px 14px 0 0;
}
.metric-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.metric-value { font-size: 1.9rem; font-weight: 700; margin: 6px 0; color: #f1f5f9; }
.metric-delta { font-size: 0.8rem; }
.delta-pos { color: #10b981; }
.delta-neg { color: #ef4444; }
.delta-neu { color: #64748b; }

/* ── Event log ── */
.event-log {
    background: #060b16;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    line-height: 1.8;
    max-height: 320px;
    overflow-y: auto;
}
.ev-market  { color: #38bdf8; }
.ev-signal  { color: #a78bfa; }
.ev-order   { color: #fbbf24; }
.ev-fill    { color: #34d399; }
.ev-error   { color: #f87171; }
.ev-info    { color: #94a3b8; }

/* ── Control buttons — dark themed for all ── */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    transition: all 0.25s !important;
    border: 1px solid #1e293b !important;
    background: linear-gradient(135deg, #1e293b, #0f172a) !important;
    color: #94a3b8 !important;
}
.stButton > button:hover {
    transform: translateY(-2px);
    background: linear-gradient(135deg, #273449, #182136) !important;
    border-color: #334155 !important;
    color: #e2e8f0 !important;
    box-shadow: 0 8px 20px rgba(0,0,0,0.5) !important;
}
/* Start Bot — green */
[data-testid="column"]:first-child .stButton > button {
    background: linear-gradient(135deg, #10b981, #059669) !important;
    border-color: #059669 !important;
    color: #fff !important;
}
/* Stop Bot — red */
[data-testid="column"]:nth-child(2) .stButton > button {
    background: linear-gradient(135deg, #ef4444, #dc2626) !important;
    border-color: #dc2626 !important;
    color: #fff !important;
}
/* Restart — amber */
[data-testid="column"]:nth-child(3) .stButton > button {
    background: linear-gradient(135deg, #f59e0b, #d97706) !important;
    border-color: #d97706 !important;
    color: #fff !important;
}

/* ── Mode pill ── */
.mode-pill {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.mode-live     { background: rgba(239,68,68,0.15);  color: #f87171; border: 1px solid #f87171; }
.mode-paper    { background: rgba(251,191,36,0.15); color: #fbbf24; border: 1px solid #fbbf24; }
.mode-backtest { background: rgba(99,102,241,0.15); color: #818cf8; border: 1px solid #818cf8; }

/* ── Section heading ── */
.section-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #475569;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #1e293b;
}

/* ── Uptime ── */
.uptime-widget {
    background: rgba(56,189,248,0.05);
    border: 1px solid rgba(56,189,248,0.15);
    border-radius: 10px;
    padding: 14px 18px;
    text-align: center;
}
.uptime-label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.uptime-value { font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; color: #38bdf8; font-weight: 600; margin-top: 4px; }

/* ── Pipeline diagram ── */
.pipeline {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    flex-wrap: nowrap;
    margin: 16px 0;
}
.pipe-node {
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 10px 16px;
    text-align: center;
    font-size: 0.75rem;
    font-weight: 600;
    color: #94a3b8;
    min-width: 90px;
    transition: all 0.3s;
}
.pipe-node.active { border-color: #6366f1; color: #a5b4fc; box-shadow: 0 0 12px rgba(99,102,241,0.3); }
.pipe-arrow { color: #334155; font-size: 1.2rem; padding: 0 4px; flex-shrink: 0; }
.pipe-arrow.active { color: #6366f1; }

/* ── Streamlit top header bar (default white toolbar) ── */
header[data-testid="stHeader"] {
    background-color: #0a0e1a !important;
    border-bottom: 1px solid #1e293b !important;
}
/* Hide the deploy/share button toolbar if present */
[data-testid="stToolbar"],
[data-testid="stDecoration"] {
    display: none !important;
}
/* Remove extra top padding left by hidden toolbar */
.stMainBlockContainer { padding-top: 2rem !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0e1a; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ── Session State Initialisation ───────────────────────────────────────────────
def _init_state():
    defaults = {
        "bot_running": False,
        "bot_mode": "Live",
        "start_time": None,
        "event_log": [],
        "total_trades": 0,
        "open_positions": 0,
        "daily_pnl": 0.0,
        "account_balance": 100_000.0,
        "symbols": ["GOLD", "SILVER"],
        "timeframe": _USER_PREFS.get("timeframe", "5m"),
        "trailing_sl_pct": 1.0,
        "target_pct": 2.5,
        "active_pipeline_step": -1,
        # Strategy prefs from user_prefs.json
        "ema_fast":        _USER_PREFS.get("ema_fast", 3),
        "ema_slow":        _USER_PREFS.get("ema_slow", 8),
        "use_vol_filter":  _USER_PREFS.get("use_vol_filter", True),
        "use_atr_filter":  _USER_PREFS.get("use_atr_filter", True),
        "trade_volume":    _USER_PREFS.get("trade_volume", 1),
        "trading_symbol":  _USER_PREFS.get("trading_symbol", "Gold Petal (1g)"),
        "security_id":     _USER_PREFS.get("security_id", "626"),
        "dhan_client_id":  _USER_PREFS.get("dhan_client_id", ""),
        "dhan_api_key":    _USER_PREFS.get("dhan_api_key", ""),
        "account_balance": float(_USER_PREFS.get("account_balance", 100_000.0)),
        "sod_balance":     float(_USER_PREFS.get("account_balance", 100_000.0)),
        "margin_cap":      int(_USER_PREFS.get("margin_cap", 80)),
        "alert_telegram":  bool(_USER_PREFS.get("alert_telegram", True)),
        "alert_email":     bool(_USER_PREFS.get("alert_email", True)),
        "alert_sound":     bool(_USER_PREFS.get("alert_sound", True)),
        "alert_desktop":   bool(_USER_PREFS.get("alert_desktop", True)),
        "execution_mode":  _USER_PREFS.get("execution_mode", "JSON Only"),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Helpers ────────────────────────────────────────────────────────────────────
PIPELINE_STEPS = ["Data Feed", "Strategy", "Risk Mgr", "OMS", "Execution", "Portfolio", "Storage"]

MODE_COLORS = {"Live": "mode-live", "Paper": "mode-paper", "Backtest": "mode-backtest"}

EVENT_TEMPLATES = {
    "market":  ("📡", "ev-market",  "MarketEvent"),
    "signal":  ("🎯", "ev-signal",  "SignalEvent"),
    "order":   ("📋", "ev-order",   "OrderEvent"),
    "fill":    ("✅", "ev-fill",    "FillEvent"),
    "info":    ("ℹ️", "ev-info",    "INFO"),
}

def _add_event(kind: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    icon, cls, label = EVENT_TEMPLATES.get(kind, ("·", "ev-info", "INFO"))
    entry = f'<span class="ev-info">[{ts}]</span> {icon} <span class="{cls}">[{label}]</span> {msg}'
    st.session_state.event_log.insert(0, entry)
    if len(st.session_state.event_log) > 60:
        st.session_state.event_log = st.session_state.event_log[:60]

def _format_uptime() -> str:
    if not st.session_state.bot_running or not st.session_state.start_time:
        return "00:00:00"
    delta = datetime.now() - st.session_state.start_time
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

from core.storage import Storage
_storage = Storage(execution_mode=_USER_PREFS.get("execution_mode", "JSON Only"))

def _load_live_state():
    """Read the latest PnL snapshot and event log from the background daemon (main.py)."""
    # 1. Load latest metrics
    history = _storage.load_pnl_history()
    if history:
        last = history[-1]
        st.session_state.account_balance = last.get("equity", 100_000.0)  # Use equity as the balanced tracking metric
        st.session_state.daily_pnl = last.get("realised_pnl", 0.0) + last.get("unrealised_pnl", 0.0)
        st.session_state.open_positions = last.get("open_positions", 0)
        st.session_state.total_trades = last.get("total_trades", 0)
    else:
        st.session_state.daily_pnl = 0.0
        st.session_state.open_positions = 0
        st.session_state.total_trades = 0

    # 1b. FETCH REAL-TIME BALANCE FROM DHAN (if active)
    _cid = st.session_state.get("dhan_client_id")
    _tok = st.session_state.get("dhan_api_key")
    if _cid and _tok and st.session_state.get("data_source") == "Dhan":
        from core.risk_manager import RiskManager
        f_data = RiskManager.fetch_fund_limits(_cid, _tok)
        if f_data:
            # Current available cash
            st.session_state.account_balance = float(f_data.get("availabelBalance", st.session_state.account_balance))
            # Start of Day limit for growth metric
            if "sodLimit" in f_data:
                st.session_state.sod_balance = float(f_data["sodLimit"])

    # 2. Load recent events (max 60 most recent)
    log_lines = []
    if _storage.events_path.exists():
        try:
            with _storage.events_path.open("r", encoding="utf-8") as f:
                # Read all lines, reverse them to get most recent first
                all_lines = [ln for ln in f if ln.strip()]
                for line in reversed(all_lines[-60:]):
                    evt = json.loads(line)
                    ts_full = evt.get("timestamp", "")
                    ts = ts_full.split("T")[1][:8] if "T" in ts_full else ts_full
                    kind = evt.get("kind", "info")
                    msg = evt.get("msg", "")
                    
                    icon, cls, label = EVENT_TEMPLATES.get(kind, ("·", "ev-info", "INFO"))
                    entry = f'<span class="ev-info">[{ts}]</span> {icon} <span class="{cls}">[{label}]</span> {msg}'
                    log_lines.append(entry)
        except Exception as e:
            log_lines.append(f'<span class="ev-info">Error reading logs: {e}</span>')
            
    st.session_state.event_log = log_lines



# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — 5 logical sections
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── 1. Branding ──────────────────────────────────────────────────────────
    st.markdown("""
    <div class="sb-brand">
        <div class="sb-brand-title">⚡ Trade Pulse Quants</div>
        <div class="sb-brand-sub">EVENT-DRIVEN TRADING SYSTEM</div>
        <span class="sb-version">v1.0.0 · Streamlit</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 2. Execution Settings ─────────────────────────────────────────────────
    st.markdown("""
    <div class="sb-section">
        <div class="sb-section-title">🚀 Execution Settings</div>
    </div>
    <div class="sb-card" style="margin-bottom:10px">
        <div class="sb-stat-row">
            <span class="sb-stat-key">Trading Mode</span>
            <span class="sb-stat-val red">🔴 LIVE</span>
        </div>
        <div class="sb-stat-row">
            <span class="sb-stat-key">Execution</span>
            <span class="sb-stat-val">Real broker orders</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    # mode is always Live
    st.session_state.bot_mode = "Live"

    # Timeframe comes from user prefs (set on Settings page)
    _tf_display = str(st.session_state.get("timeframe", "5m")).upper()
    st.markdown(f"""
    <div class="sb-card" style="margin-bottom:10px">
        <div class="sb-stat-row">
            <span class="sb-stat-key">⏱️ Bar Timeframe</span>
            <span class="sb-stat-val blue">{_tf_display}</span>
        </div>
        <div class="sb-stat-row">
            <span class="sb-stat-key">📈 Symbol</span>
            <span class="sb-stat-val">{st.session_state.get('trading_symbol', '—')}</span>
        </div>
        <div class="sb-stat-row">
            <span class="sb-stat-key">EMA</span>
            <span class="sb-stat-val">{st.session_state.get('ema_fast', 3)} / {st.session_state.get('ema_slow', 8)}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 4. Risk Management ────────────────────────────────────────────────────
    st.markdown("""
    <div class="sb-section">
        <div class="sb-section-title">🛡️ Risk Management</div>
    </div>""", unsafe_allow_html=True)

    # Fixed risk parameters
    st.session_state.trailing_sl_pct = 1.0
    st.session_state.target_pct = 2.5
    st.session_state.sl_type = "Trailing"

    st.markdown("""
    <div class="sb-card" style="margin-top:8px">
        <div class="sb-stat-row">
            <span class="sb-stat-key">Trailing SL</span>
            <span class="sb-stat-val red">1.00%</span>
        </div>
        <div class="sb-stat-row">
            <span class="sb-stat-key">Target</span>
            <span class="sb-stat-val green">2.50%</span>
        </div>
        <div class="sb-stat-row">
            <span class="sb-stat-key">SL Type</span>
            <span class="sb-stat-val">Trailing</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-label" style="margin-top:8px">🔔 Notification Channels</div>',
                unsafe_allow_html=True)
    notif_c1, notif_c2 = st.columns(2)
    with notif_c1:
        alert_telegram = st.toggle("Telegram", value=st.session_state.alert_telegram)
        st.session_state.alert_telegram = alert_telegram
        alert_email = st.toggle("Email",    value=st.session_state.alert_email)
        st.session_state.alert_email = alert_email
    with notif_c2:
        alert_sound = st.toggle("Sound",   value=st.session_state.alert_sound)
        st.session_state.alert_sound = alert_sound
        alert_desktop = st.toggle("Desktop", value=st.session_state.alert_desktop)
        st.session_state.alert_desktop = alert_desktop

    # Auto-save notification changes to user_prefs.json
    try:
        if _PREFS_FILE.exists():
            with open(_PREFS_FILE, "r") as f:
                cur_prefs = json.load(f)
        else:
            cur_prefs = {}
            
        cur_prefs["alert_telegram"] = bool(st.session_state.alert_telegram)
        cur_prefs["alert_email"] = bool(st.session_state.alert_email)
        cur_prefs["alert_sound"] = bool(st.session_state.alert_sound)
        cur_prefs["alert_desktop"] = bool(st.session_state.alert_desktop)
        
        with open(_PREFS_FILE, "w") as f:
            json.dump(cur_prefs, f, indent=2)
    except Exception:
        pass

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="sb-footer">
        Trade Pulse Quants &nbsp;·&nbsp; v1.0.0<br>
        Built with Streamlit &nbsp;·&nbsp; Python<br>
        <span style="color:#1e293b">─────────────────</span><br>
        ⚠️ For educational use only
    </div>
    """, unsafe_allow_html=True)



# ── Header (static shell — clock span filled by JS component below) ──────────
st.markdown("""
<div class="tpq-header">
    <div>
        <div class="tpq-title">⚡ Trade Pulse Quants</div>
        <div class="tpq-subtitle">Event-Driven Live Trading System</div>
    </div>
    <div class="tpq-clock" id="tpq-clock-wrapper">🕐 <span id="tpq-live-clock">loading...</span></div>
</div>
""", unsafe_allow_html=True)

# ── Live clock — injected via components.v1.html (scripts actually execute) ──
# Runs in a hidden 0-height iframe; accesses parent DOM via window.parent.
components.html("""
<script>
(function() {
    var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"];

    function pad(n) { return String(n).padStart(2, '0'); }

    function tick() {
        try {
            var el = window.parent.document.getElementById('tpq-live-clock');
            if (!el) return;
            var now = new Date();
            var day = pad(now.getDate());
            var mon = MONTHS[now.getMonth()];
            var yr  = now.getFullYear();
            var hh  = pad(now.getHours());
            var mm  = pad(now.getMinutes());
            var ss  = pad(now.getSeconds());
            el.textContent = day + ' ' + mon + ' ' + yr + '  ' + hh + ':' + mm + ':' + ss;
        } catch(e) {}
    }

    tick();
    setInterval(tick, 1000);
})();
</script>
""", height=0)


# ── Pipeline Diagram ──────────────────────────────────────────────────────────
st.markdown('<div class="section-label">📡 Event Pipeline</div>', unsafe_allow_html=True)
active = st.session_state.bot_running
pipeline_html = '<div class="pipeline">'
for i, step in enumerate(PIPELINE_STEPS):
    node_cls = "pipe-node active" if active else "pipe-node"
    pipeline_html += f'<div class="{node_cls}">{step}</div>'
    if i < len(PIPELINE_STEPS) - 1:
        arrow_cls = "pipe-arrow active" if active else "pipe-arrow"
        pipeline_html += f'<div class="{arrow_cls}">→</div>'
pipeline_html += '</div>'
st.markdown(pipeline_html, unsafe_allow_html=True)


# ── Control Panel ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">🎛️ Bot Controls</div>', unsafe_allow_html=True)

col_start, col_stop, col_restart, col_status, col_uptime = st.columns([1, 1, 1, 2, 1.5])

with col_start:
    if st.button("▶  Start Bot", use_container_width=True, disabled=st.session_state.bot_running):
        st.session_state.bot_running = True
        st.session_state.start_time  = datetime.now()
        _add_event("info", f"Bot STARTED · mode={st.session_state.bot_mode} · tf={st.session_state.timeframe}")
        st.rerun()

with col_stop:
    if st.button("⏹  Stop Bot", use_container_width=True, disabled=not st.session_state.bot_running):
        st.session_state.bot_running = False
        _add_event("info", "Bot STOPPED · all positions maintained")
        st.rerun()

with col_restart:
    if st.button("🔄  LTS", use_container_width=True, help="Last Trading Signal: Run manual pipeline test"):
        with st.spinner("Executing Manual Tick..."):
            try:
                # Initialize a temporary engine for the manual tick
                test_engine = TradingEngine(mode="paper") 
                result = test_engine.run_pipeline_tick(is_manual=True)
                
                if result:
                    if "error" in result:
                        st.error(f"LTS API Error: {result['error']}")
                    else:
                        # Delegate full chart rendering and broadcasting to core.notifier
                        import threading
                        from core.notifier import process_and_broadcast
                        
                        # Spin off into separate thread so the UI button doesn't freeze while Plotly generates
                        bg_thread = threading.Thread(
                            target=process_and_broadcast,
                            args=(result, _USER_PREFS, "LTS_MANUAL")
                        )
                        bg_thread.start()
                        
                        if result.get('aborted'):
                            abort_reason = result.get('abort_reason', 'Unknown reason')
                            st.error(f"🚨 TRADE ABORTED: {abort_reason}")
                            for w in result.get('risk_warnings', []):
                                st.warning(w)
                            for w in result.get('risk_warnings', []):
                                st.warning(w)
                            
                            st.toast(f"LTS Success: {sig} @ {ltp} ({src})", icon="🚀")
                else:
                    st.error("LTS Failed silently: Empty response or bad data format.")
            except Exception as e:
                st.error(f"LTS Error: {e}")


with col_status:
    if st.session_state.bot_running:
        mc = MODE_COLORS.get(st.session_state.bot_mode, "mode-paper")
        st.markdown(
            f'<div class="status-running">🟢 Running &nbsp;<span class="mode-pill {mc}">{st.session_state.bot_mode}</span></div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown('<div class="status-stopped">🔴 Stopped</div>', unsafe_allow_html=True)

with col_uptime:
    st.markdown(f"""
    <div class="uptime-widget">
        <div class="uptime-label">Uptime</div>
        <div class="uptime-value">{_format_uptime()}</div>
    </div>""", unsafe_allow_html=True)


st.markdown("<br>", unsafe_allow_html=True)


# ── Metric Cards ───────────────────────────────────────────────────────────────
if st.session_state.execution_mode == "JSON Only":
    st.markdown("""
    <div style="background:rgba(244,114,182,0.1); border:1px solid rgba(244,114,182,0.3); padding:20px; border-radius:12px; margin-bottom:20px;">
        <h3 style="color:#f472b6; margin-top:0; margin-bottom:10px;">📝 Paper Trading Mode Active</h3>
        <p style="color:#e2e8f0; font-size:1rem; margin-bottom:5px;">You are currently running in <b>JSON Only</b> execution mode.</p>
        <p style="color:#94a3b8; font-size:0.9rem; margin-bottom:0;">To view your simulated performance metrics, portfolio PnL, and trade history, please navigate to the <b>📝 Paper Trading</b> page using the sidebar.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    if st.session_state.bot_running:
        _load_live_state()
    
    st.markdown('<div class="section-label">📊 Live Metrics</div>', unsafe_allow_html=True)
    
    pnl_color = "delta-pos" if st.session_state.daily_pnl >= 0 else "delta-neg"
    pnl_sign  = "+" if st.session_state.daily_pnl >= 0 else ""
    pnl_icon  = "▲" if st.session_state.daily_pnl >= 0 else "▼"
    
    m1, m2, m3, m4 = st.columns(4)
    
    with m1:
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#818cf8,#6366f1);">
            <div class="metric-label">Total Trades</div>
            <div class="metric-value">{st.session_state.total_trades}</div>
            <div class="metric-delta delta-neu">Session total</div>
        </div>""", unsafe_allow_html=True)
    
    with m2:
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#f59e0b,#d97706);">
            <div class="metric-label">Open Positions</div>
            <div class="metric-value">{st.session_state.open_positions}</div>
            <div class="metric-delta delta-neu">Active now</div>
        </div>""", unsafe_allow_html=True)
    
    with m3:
        pnl_abs = abs(st.session_state.daily_pnl)
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#10b981,#059669);">
            <div class="metric-label">Daily PnL</div>
            <div class="metric-value">₹{pnl_sign}{st.session_state.daily_pnl:,.0f}</div>
            <div class="metric-delta {pnl_color}">{pnl_icon} {pnl_sign}₹{pnl_abs:,.0f} today</div>
        </div>""", unsafe_allow_html=True)
    
    with m4:
        start_val = st.session_state.get("sod_balance", 100_000.0)
        bal_delta = st.session_state.account_balance - start_val
        bd_color  = "delta-pos" if bal_delta >= 0 else "delta-neg"
        bd_sign   = "+" if bal_delta >= 0 else ""
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#38bdf8,#0ea5e9);">
            <div class="metric-label">Account Balance</div>
            <div class="metric-value">₹{st.session_state.account_balance:,.0f}</div>
            <div class="metric-delta {bd_color}">{bd_sign}₹{bal_delta:,.0f} vs start</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ── Event Log + Config Summary ─────────────────────────────────────────────────
log_col, cfg_col = st.columns([2, 1])

with log_col:
    st.markdown('<div class="section-label">📜 Live Event Stream</div>', unsafe_allow_html=True)

    # The event log is loaded inside _load_live_state() above

    if st.session_state.event_log:
        log_html = '<div class="event-log">' + "<br>".join(st.session_state.event_log) + '</div>'
    else:
        log_html = '<div class="event-log"><span class="ev-info">→ Start the bot to see live events...</span></div>'
    st.markdown(log_html, unsafe_allow_html=True)

    clear_col, spacer = st.columns([1, 4])
    with clear_col:
        if st.button("🗑 Clear Log"):
            _storage.events_path.write_text("")  # Hard clear the actual log file
            st.session_state.event_log = []
            st.rerun()

with cfg_col:
    st.markdown('<div class="section-label">⚙️ Active Config</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="metric-card" style="--accent: linear-gradient(90deg,#6366f1,#8b5cf6); padding: 18px 20px;">
        <div style="display:grid; gap:10px; font-size:0.83rem;">
            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="color:#64748b;">Mode</span>
                <span class="mode-pill {MODE_COLORS.get(st.session_state.bot_mode,'mode-paper')}">{st.session_state.bot_mode}</span>
            </div>
            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="color:#64748b;">Timeframe</span>
                <span style="color:#f1f5f9;font-weight:600;">{st.session_state.timeframe}</span>
            </div>
            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="color:#64748b;">Trailing SL</span>
                <span style="color:#f87171;font-weight:600;">1.00%</span>
            </div>
            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="color:#64748b;">Target</span>
                <span style="color:#10b981;font-weight:600;">2.50%</span>
            </div>
            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="color:#64748b;">Symbols</span>
                <span style="color:#f1f5f9;font-weight:600;">{len(st.session_state.symbols)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <span style="color:#64748b;">Capital</span>
                <span style="color:#34d399;font-weight:600;">₹{st.session_state.account_balance:,.0f}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">🔗 Architecture</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="metric-card" style="--accent: linear-gradient(90deg,#334155,#475569); font-size:0.75rem; line-height:2; font-family:'JetBrains Mono',monospace; color:#64748b;">
        <span style="color:#818cf8;">DataFeed</span> → MarketEvent<br>
        <span style="color:#a78bfa;">Strategy</span> → SignalEvent<br>
        <span style="color:#c084fc;">RiskMgr</span> → OrderEvent<br>
        <span style="color:#e879f9;">OMS</span> → submit()<br>
        <span style="color:#f472b6;">Execution</span> → FillEvent<br>
        <span style="color:#fb7185;">Portfolio</span> → on_fill()<br>
        <span style="color:#fda4af;">Storage</span> → persist()
    </div>
    """, unsafe_allow_html=True)


# ── Auto-refresh when running ──────────────────────────────────────────────────
if st.session_state.bot_running:
    time.sleep(2)
    st.rerun()
