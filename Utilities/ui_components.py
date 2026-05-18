import streamlit as st
import json
from pathlib import Path

# Paths
_PREFS_FILE = Path(__file__).parent.parent / "config" / "user_prefs.json"

def load_css():
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
[data-testid="stSidebar"] * { color: #cbd5e1 !important; }

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

def init_session_state():
    """Initialize standard session state variables based on user preferences."""
    user_prefs = {}
    if _PREFS_FILE.exists():
        try:
            with open(_PREFS_FILE) as f:
                user_prefs = json.load(f)
        except Exception:
            pass

    # Attempt to read live equity from MT5 on first load
    _init_bal = float(user_prefs.get("initial_balance", user_prefs.get("ftmo_sod_balance", 10_000.0)))
    _live_balance = _init_bal
    try:
        import MetaTrader5 as _mt5
        if _mt5.terminal_info() is not None:
            _acc = _mt5.account_info()
            if _acc:
                _live_balance = _acc.equity
    except Exception:
        pass

    defaults = {
        "bot_running": False,
        "bot_mode": "Live",
        "start_time": None,
        "event_log": [],
        "total_trades": 0,
        "open_positions": 0,
        "daily_pnl": 0.0,
        "account_balance": _live_balance,
        "symbols": ["GOLD", "SILVER"],
        "timeframe": user_prefs.get("timeframe", "5m"),
        "trailing_sl_pct": 1.0,
        "target_pct": 2.5,
        "active_pipeline_step": -1,
        "ema_fast":        user_prefs.get("ema_fast", 3),
        "ema_slow":        user_prefs.get("ema_slow", 8),
        "use_vol_filter":  user_prefs.get("use_vol_filter", True),
        "use_atr_filter":  user_prefs.get("use_atr_filter", True),
        "trade_volume":    user_prefs.get("trade_volume", 0.01),
        "initial_balance": float(user_prefs.get("initial_balance", 10_000.0)),
        "trading_symbol":  user_prefs.get("trading_symbol", "XAUUSD"),
        "mt5_account":     user_prefs.get("mt5_account", ""),
        "mt5_password":    user_prefs.get("mt5_password", ""),
        "mt5_server":      user_prefs.get("mt5_server", "FTMO-Demo"),
        "mt5_path":        user_prefs.get("mt5_path", ""),
        "bar_count":       user_prefs.get("bar_count", 300),
        "sod_balance":     float(user_prefs.get("ftmo_sod_balance", user_prefs.get("initial_balance", 10_000.0))),
        "telegram_bot_token": user_prefs.get("telegram_bot_token", ""),
        "telegram_chat_id":  user_prefs.get("telegram_chat_id", ""),
        "gmail_sender":      user_prefs.get("gmail_sender", ""),
        "gmail_app_password": user_prefs.get("gmail_app_password", ""),
        "gmail_receiver":    user_prefs.get("gmail_receiver", ""),
        "alert_telegram":  bool(user_prefs.get("alert_telegram", True)),
        "alert_email":     bool(user_prefs.get("alert_email", True)),
        "alert_sound":     bool(user_prefs.get("alert_sound", True)),
        "alert_desktop":   bool(user_prefs.get("alert_desktop", True)),
        "execution_mode":  "MetaTrader5",
        "daily_reset_time": user_prefs.get("daily_reset_time", "00:00"),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
            
def render_sidebar():
    """Renders the common sidebar across all pages."""
    with st.sidebar:
        st.markdown("""
        <div class="sb-brand">
            <div class="sb-brand-title">⚡ Trade Pulse Quants</div>
            <div class="sb-brand-sub">EVENT-DRIVEN TRADING SYSTEM</div>
            <span class="sb-version">v1.0.0 · Streamlit</span>
        </div>
        """, unsafe_allow_html=True)

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
        st.session_state.bot_mode = "Live"

        tf_display = str(st.session_state.get("timeframe", "5m")).upper()
        sym = st.session_state.get('trading_symbol', '—')
        ema_f = st.session_state.get('ema_fast', 3)
        ema_s = st.session_state.get('ema_slow', 8)
        st.markdown(f"""
        <div class="sb-card" style="margin-bottom:10px">
            <div class="sb-stat-row">
                <span class="sb-stat-key">⏱️ Bar Timeframe</span>
                <span class="sb-stat-val blue">{tf_display}</span>
            </div>
            <div class="sb-stat-row">
                <span class="sb-stat-key">📈 Symbol</span>
                <span class="sb-stat-val">{sym}</span>
            </div>
            <div class="sb-stat-row">
                <span class="sb-stat-key">EMA</span>
                <span class="sb-stat-val">{ema_f} / {ema_s}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="sb-section">
            <div class="sb-section-title">🛡️ Risk Management</div>
        </div>""", unsafe_allow_html=True)

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
            cur_prefs = {}
            if _PREFS_FILE.exists():
                with open(_PREFS_FILE, "r") as f:
                    cur_prefs = json.load(f)
                
            cur_prefs["alert_telegram"] = bool(st.session_state.alert_telegram)
            cur_prefs["alert_email"] = bool(st.session_state.alert_email)
            cur_prefs["alert_sound"] = bool(st.session_state.alert_sound)
            cur_prefs["alert_desktop"] = bool(st.session_state.alert_desktop)
            
            with open(_PREFS_FILE, "w") as f:
                json.dump(cur_prefs, f, indent=2)
        except Exception:
            pass

        st.markdown("""
        <div class="sb-footer">
            Trade Pulse Quants &nbsp;·&nbsp; v1.0.0<br>
            Built with Streamlit &nbsp;·&nbsp; Python<br>
            <span style="color:#1e293b">─────────────────</span><br>
            ⚠️ For educational use only
        </div>
        """, unsafe_allow_html=True)
