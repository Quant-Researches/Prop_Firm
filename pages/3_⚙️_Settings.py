"""
pages/3_⚙️_Settings.py — Trade Pulse Quants
"""

import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="Settings — Trade Pulse Quants", page_icon="⚙️", layout="wide")

from Utilities.ui_components import load_css, render_sidebar, init_session_state
load_css()
st.markdown("""
<style>
/* Page Header */
.page-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid #312e81;
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 28px;
    box-shadow: 0 0 40px rgba(99,102,241,0.12);
}
.page-title {
    font-size: 1.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, #818cf8, #c084fc, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.page-sub { font-size: 0.85rem; color: #64748b; margin-top: 4px; }

/* Settings Cards */
.settings-card {
    background: rgba(255,255,255,0.02);
    border: 1px solid #1e293b;
    border-radius: 16px;
    padding: 24px 28px;
    margin-bottom: 24px;
    transition: all 0.3s ease;
}
.settings-card:hover {
    border-color: #38bdf8;
    box-shadow: 0 8px 32px rgba(56, 189, 248, 0.05);
    transform: translateY(-2px);
}
.card-title {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #94a3b8;
    font-weight: 700;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 12px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.card-title span { font-size: 1.2rem; }

/* Inputs Customization */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    background: #0d1225 !important;
    border: 1px solid #1e293b !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    transition: all 0.2s;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: #38bdf8 !important;
    box-shadow: 0 0 0 2px rgba(56,189,248,0.2) !important;
}
[data-testid="stSelectbox"] > div {
    background: #0d1225 !important;
    border-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}

/* Save Button Customization */
.save-btn-container .stButton > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6, #d946ef) !important;
    background-size: 200% auto !important;
    border: none !important;
    color: white !important;
    font-size: 1rem !important;
    font-weight: 800 !important;
    padding: 12px 0 !important;
    border-radius: 12px !important;
    transition: all 0.4s ease !important;
    box-shadow: 0 4px 15px rgba(99,102,241,0.3) !important;
}
.save-btn-container .stButton > button:hover {
    background-position: right center !important;
    transform: translateY(-3px) !important;
    box-shadow: 0 8px 25px rgba(217,70,239,0.4) !important;
}
</style>
""", unsafe_allow_html=True)

PREFS_DIR  = Path(__file__).parent.parent / "config"
PREFS_FILE = PREFS_DIR / "user_prefs.json"

DEFAULT_PREFS = {
    "execution_mode":    "MetaTrader5",
    "trading_symbol":    "XAUUSD",
    "timeframe":         "5m",
    "ema_fast":          3,
    "ema_slow":          8,
    "use_vol_filter":    True,
    "use_atr_filter":    True,
    "trade_volume":      0.01,
    "bar_count":         300,
    "initial_balance":   10_000.0,
    "mt5_account":       "",
    "mt5_password":      "",
    "mt5_server":        "FTMO-Demo",
    "mt5_path":          "",
    "daily_reset_time":  "00:00",
    "telegram_bot_token":"",
    "telegram_chat_id":  "",
    "gmail_sender":      "",
    "gmail_app_password":"",
    "gmail_receiver":    "",
}

def _load_prefs() -> dict:
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE) as f:
                saved = json.load(f)
            return {**DEFAULT_PREFS, **saved}
        except Exception:
            pass
    return dict(DEFAULT_PREFS)

def _save_prefs(prefs: dict):
    PREFS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

if "_prefs_loaded" not in st.session_state:
    init_session_state()
    st.session_state["_prefs_loaded"] = True

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <div class="page-title">⚙️ Global Settings</div>
    <div class="page-sub">Configure your MetaTrader 5 credentials, trading instruments, and core strategy parameters for the automated bot.</div>
</div>
""", unsafe_allow_html=True)

with st.form("settings_form", border=False):
    
    # ── MT5 Credentials ──
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title"><span>🔑</span> MetaTrader 5 Connection</div>', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    mt5_account = c1.text_input("Account Number", value=str(st.session_state.get("mt5_account", "")), placeholder="e.g. 10101010")
    mt5_password = c2.text_input("Password", value=str(st.session_state.get("mt5_password", "")), type="password", placeholder="Master or Investor Password")
    mt5_server = c3.text_input("Server", value=str(st.session_state.get("mt5_server", "FTMO-Demo")), placeholder="e.g. FTMO-Demo")
    
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    mt5_path = st.text_input("Executable Path (Optional — Required for Prop Firms)", 
                             value=str(st.session_state.get("mt5_path", "")), 
                             placeholder="e.g. C:\\Program Files\\FTMO MetaTrader 5\\terminal64.exe",
                             help="Leave blank if using the default MetaTrader 5 installation path.")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Trading Config ──
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title"><span>📊</span> Instrument & Execution</div>', unsafe_allow_html=True)
    
    POPULAR_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "US30.cash", "US100.cash", "US500.cash", "USOIL.cash", "EURJPY", "Custom..."]
    c4, c5, c6 = st.columns(3)
    
    saved_sym = st.session_state.get("trading_symbol", "XAUUSD")
    sym_idx = POPULAR_SYMBOLS.index(saved_sym) if saved_sym in POPULAR_SYMBOLS else len(POPULAR_SYMBOLS) - 1
    
    selected_sym_dropdown = c4.selectbox("Trading Symbol", POPULAR_SYMBOLS, index=sym_idx, help="Select a popular MT5 instrument or choose 'Custom...' to type your own.")
    
    if selected_sym_dropdown == "Custom...":
        trading_symbol = c4.text_input("Custom Symbol", value=saved_sym if saved_sym not in POPULAR_SYMBOLS else "", placeholder="e.g. XAUUSD.i")
    else:
        trading_symbol = selected_sym_dropdown
    
    tf_opts = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    tf_val = st.session_state.get("timeframe", "5m")
    timeframe = c5.selectbox("Timeframe", tf_opts, index=tf_opts.index(tf_val) if tf_val in tf_opts else 1, help="Candle resolution used for strategy signals.")
    
    trade_volume = c6.number_input("Trade Volume (Lots)", value=float(st.session_state.get("trade_volume", 0.01)), step=0.01, format="%.2f", help="Lot size for automated trades.")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    cb1, cb2 = st.columns(2)
    initial_balance = cb1.number_input(
        "Initial Account Balance ($)",
        min_value=100.0,
        max_value=10_000_000.0,
        value=float(st.session_state.get("initial_balance", 10_000.0)),
        step=1000.0,
        format="%.2f",
        help="Your FTMO challenge or funded account starting balance. Used for drawdown calculations and SOD snapshots."
    )
    cb2.markdown(f"""
    <div style='margin-top:28px; padding:10px 16px; background:rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.2); border-radius:8px;'>
        <span style='color:#64748b; font-size:0.78rem;'>Configured Starting Balance:</span><br>
        <span style='color:#34d399; font-family:"JetBrains Mono",monospace; font-size:1.2rem; font-weight:800;'>${initial_balance:,.2f}</span>
    </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Strategy Params ──
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title"><span>🧠</span> Dow Theory Strategy</div>', unsafe_allow_html=True)
    
    c7, c8, c9 = st.columns(3)
    ema_fast = c7.number_input("Fast EMA Period", min_value=1, max_value=50, value=int(st.session_state.get("ema_fast", 3)), help="Used for short-term trend direction.")
    ema_slow = c8.number_input("Slow EMA Period", min_value=1, max_value=200, value=int(st.session_state.get("ema_slow", 8)), help="Used for long-term trend baseline.")
    bar_count = c9.number_input("Historical Candles", min_value=50, max_value=1000, value=int(st.session_state.get("bar_count", 300)), step=50, help="How much history to fetch for indicator calculations.")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    filt1, filt2 = st.columns(2)
    with filt1:
        use_vol_filter = st.toggle("Enable Volume Filter", value=st.session_state.get("use_vol_filter", True), help="Requires candle volume to be higher than the 21-period moving average.")
    with filt2:
        use_atr_filter = st.toggle("Enable ATR Filter", value=st.session_state.get("use_atr_filter", True), help="Requires expanding volatility (rising ATR) to confirm breakouts.")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Daily Reset & Maintenance ──
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title"><span>⏰</span> Daily Reset &amp; Maintenance (FTMO Time)</div>', unsafe_allow_html=True)

    saved_reset = st.session_state.get("daily_reset_time", "00:00")
    try:
        saved_reset_hh = int(saved_reset.split(":")[0])
        saved_reset_mm = int(saved_reset.split(":")[1])
    except Exception:
        saved_reset_hh, saved_reset_mm = 0, 0

    r1, r2, r3 = st.columns([1, 1, 2])
    reset_hh = r1.number_input("Reset Hour (HH)", min_value=0, max_value=23, value=saved_reset_hh, step=1,
                               help="Hour in FTMO time (CE(S)T / Europe/Prague) when the daily reset runs.")
    reset_mm = r2.number_input("Reset Minute (MM)", min_value=0, max_value=59, value=saved_reset_mm, step=5,
                               help="Minute for the daily reset.")
    daily_reset_time = f"{int(reset_hh):02d}:{int(reset_mm):02d}"
    r3.markdown(f"""
    <div style='margin-top:28px; padding:10px 16px; background:rgba(56,189,248,0.06); border:1px solid rgba(56,189,248,0.2); border-radius:8px; display:flex; align-items:center; gap:10px;'>
        <span style='color:#64748b; font-size:0.78rem; white-space:nowrap;'>Scheduled Reset Time (FTMO):</span>
        <span style='color:#38bdf8; font-family:"JetBrains Mono",monospace; font-size:1.1rem; font-weight:700;'>⏰ {daily_reset_time} CE(S)T</span>
    </div>""", unsafe_allow_html=True)

    st.caption("🔄 At this FTMO time each day, the background daemon will: (1) reconnect to MT5, (2) snapshot the start-of-day account balance for drawdown tracking.")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Notifications ──
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title"><span>🔔</span> Alerts & Notifications</div>', unsafe_allow_html=True)
    
    c10, c11 = st.columns(2)
    with c10:
        st.markdown("**Telegram Integration**")
        telegram_bot_token = st.text_input("Bot Token", value=str(st.session_state.get("telegram_bot_token", "")), type="password", placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
        telegram_chat_id = st.text_input("Chat ID", value=str(st.session_state.get("telegram_chat_id", "")), placeholder="-100123456789")
    with c11:
        st.markdown("**Email Integration (SMTP)**")
        gmail_sender = st.text_input("Sender Email", value=str(st.session_state.get("gmail_sender", "")), placeholder="bot@gmail.com")
        gmail_app_password = st.text_input("App Password", value=str(st.session_state.get("gmail_app_password", "")), type="password", placeholder="16-character app password")
        gmail_receiver = st.text_input("Receiver Email", value=str(st.session_state.get("gmail_receiver", "")), placeholder="you@gmail.com")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ── Save Button ──
    st.markdown('<div class="save-btn-container">', unsafe_allow_html=True)
    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        save_clicked = st.form_submit_button("💾 Save All Settings", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    if save_clicked:
        new_prefs = {
            "mt5_account": mt5_account.strip(),
            "mt5_password": mt5_password.strip(),
            "mt5_server": mt5_server.strip(),
            "mt5_path": mt5_path.strip(),
            "trading_symbol": trading_symbol.strip(),
            "timeframe": timeframe,
            "trade_volume": float(trade_volume),
            "initial_balance": float(initial_balance),
            "ema_fast": int(ema_fast),
            "ema_slow": int(ema_slow),
            "use_vol_filter": use_vol_filter,
            "use_atr_filter": use_atr_filter,
            "execution_mode": "MetaTrader5",
            "bar_count": int(bar_count),
            "daily_reset_time": daily_reset_time,
            "telegram_bot_token": telegram_bot_token.strip(),
            "telegram_chat_id": telegram_chat_id.strip(),
            "gmail_sender": gmail_sender.strip(),
            "gmail_app_password": gmail_app_password.strip(),
            "gmail_receiver": gmail_receiver.strip(),
        }
        # Preserve existing ftmo_sod_balance — only update initial_balance
        existing = _load_prefs()
        if "ftmo_sod_balance" in existing:
            new_prefs["ftmo_sod_balance"] = existing["ftmo_sod_balance"]
        for k, v in new_prefs.items():
            st.session_state[k] = v
        _save_prefs(new_prefs)

        # Auto schedule generation for XAUUSD matching FTMO hours
        if trading_symbol.strip().upper() == "XAUUSD":
            from core.scheduler_helper import update_and_save_schedule
            count, msg = update_and_save_schedule("XAUUSD", timeframe, prefs=new_prefs)
            if count > 0:
                st.success(f"✅ **Settings saved & XAUUSD Schedule Generated!** Created {count} active slots matching FTMO active hours. Old schedules were automatically purged.")
                # Sync session state schedules if present
                if "schedules" in st.session_state:
                    try:
                        p = Path("schedules.json")
                        if p.exists():
                            st.session_state.schedules = json.loads(p.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            else:
                st.error(f"❌ Failed to automatically generate schedule: {msg}")
        else:
            st.success("✅ **Settings saved successfully!** Changes will apply to your next scheduled run.")