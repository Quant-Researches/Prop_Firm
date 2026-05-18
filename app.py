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
from Utilities.ui_components import load_css, init_session_state, render_sidebar
load_css()


# ── Session State Initialisation ───────────────────────────────────────────────
init_session_state()


# ── Helpers ────────────────────────────────────────────────────────────────────
PIPELINE_STEPS = ["Data Feed", "Strategy", "Risk Mgr", "OMS", "Execution", "Portfolio", "Storage"]

MODE_COLORS = {"Live": "mode-live", "Backtest": "mode-backtest"}

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
_storage = Storage(execution_mode="MetaTrader5")

def _load_live_state():
    """Fetch live MT5 account state + event log from background daemon."""
    import MetaTrader5 as mt5

    # -- Pull credentials from saved prefs --
    prefs = {}
    if _PREFS_FILE.exists():
        try:
            prefs = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    acc_no  = prefs.get("mt5_account", "")
    pwd     = prefs.get("mt5_password", "")
    svr     = prefs.get("mt5_server", "")
    path    = prefs.get("mt5_path", "")

    # -- Initialize MT5 in this Streamlit process --
    mt5_ok = False
    try:
        init_kwargs = {}
        if path:
            init_kwargs["path"] = path
        if acc_no and pwd and svr:
            init_kwargs["login"]    = int(acc_no)
            init_kwargs["password"] = pwd
            init_kwargs["server"]   = svr
        mt5_ok = mt5.initialize(**init_kwargs)
    except Exception:
        mt5_ok = False

    if mt5_ok:
        acc = mt5.account_info()
        if acc:
            st.session_state.account_balance = acc.equity
            st.session_state.daily_pnl       = acc.profit
            st.session_state.open_positions  = mt5.positions_total() or 0
            st.session_state._mt5_server     = acc.server
            st.session_state._mt5_login      = acc.login
            st.session_state._mt5_leverage   = acc.leverage
            st.session_state._mt5_currency   = acc.currency
            st.session_state._mt5_connected  = True
        else:
            st.session_state._mt5_connected = False
    else:
        st.session_state._mt5_connected = False
        # Fallback: use last PnL snapshot from daemon
        history = _storage.load_pnl_history()
        if history:
            last = history[-1]
            st.session_state.account_balance = last.get("equity", st.session_state.account_balance)
            st.session_state.daily_pnl       = last.get("unrealised_pnl", 0.0)
            st.session_state.open_positions  = last.get("open_positions", 0)
            st.session_state.total_trades    = last.get("total_trades", 0)

    # -- Load trade count from snapshot history --
    history = _storage.load_pnl_history()
    if history:
        st.session_state.total_trades = history[-1].get("total_trades", 0)

    # -- Load event log from daemon's events.jsonl --
    log_lines = []
    if _storage.events_path.exists():
        try:
            all_lines = [ln for ln in _storage.events_path.open("r", encoding="utf-8") if ln.strip()]
            for line in reversed(all_lines[-60:]):
                evt  = json.loads(line)
                ts   = evt.get("timestamp", "").split("T")[1][:8] if "T" in evt.get("timestamp","") else ""
                kind = evt.get("kind", "info")
                msg  = evt.get("msg", "")
                icon, cls, label = EVENT_TEMPLATES.get(kind, ("·", "ev-info", "INFO"))
                log_lines.append(f'<span class="ev-info">[{ts}]</span> {icon} <span class="{cls}">[{label}]</span> {msg}')
        except Exception as e:
            log_lines.append(f'<span class="ev-info">Error reading logs: {e}</span>')
    st.session_state.event_log = log_lines




# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — 5 logical sections
# ─────────────────────────────────────────────────────────────────────────────
render_sidebar()

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
    function pad(n) { return String(n).padStart(2, '0'); }
    var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

    function tick() {
        try {
            var el = window.parent.document.getElementById('tpq-live-clock');
            if (!el) return;
            var now = new Date();
            var localStr = pad(now.getDate()) + ' ' + MONTHS[now.getMonth()] + ' ' + now.getFullYear() + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
            
            var ftmoFormatter = new Intl.DateTimeFormat('en-GB', {
                timeZone: 'Europe/Helsinki',
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
            });
            var ftmoParts = ftmoFormatter.formatToParts(now);
            var ftmoMap = {};
            ftmoParts.forEach(function(p){ ftmoMap[p.type] = p.value; });
            var ftmoStr = ftmoMap.day + ' ' + ftmoMap.month + ' ' + ftmoMap.year + ' ' + ftmoMap.hour + ':' + ftmoMap.minute + ':' + ftmoMap.second;
            
            el.innerHTML = '<span style="color:#94a3b8;">Local:</span> ' + localStr + ' <span style="color:#64748b;margin:0 8px;">|</span> <span style="color:#94a3b8;">FTMO MT5:</span> ' + ftmoStr;
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
                test_engine = TradingEngine(mode="live") 
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
        mc = MODE_COLORS.get(st.session_state.bot_mode, "mode-live")
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


# ── Metric Cards ── always refresh from MT5 on every page load ────────────────
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
        <div class="metric-label">Floating PnL</div>
        <div class="metric-value">${pnl_sign}{st.session_state.daily_pnl:,.2f}</div>
        <div class="metric-delta {pnl_color}">{pnl_icon} {pnl_sign}${pnl_abs:,.2f} open</div>
    </div>""", unsafe_allow_html=True)

with m4:
    _init_bal = float(_PREFS_FILE.exists() and json.loads(_PREFS_FILE.read_text()).get("initial_balance", 10_000.0) or 10_000.0)
    start_val = st.session_state.get("sod_balance", _init_bal)
    bal_delta = st.session_state.account_balance - start_val
    bd_color  = "delta-pos" if bal_delta >= 0 else "delta-neg"
    bd_sign   = "+" if bal_delta >= 0 else ""
    st.markdown(f"""
    <div class="metric-card" style="--accent: linear-gradient(90deg,#38bdf8,#0ea5e9);">
        <div class="metric-label">Live Equity (MT5)</div>
        <div class="metric-value">${st.session_state.account_balance:,.2f}</div>
        <div class="metric-delta {bd_color}">{bd_sign}${bal_delta:,.2f} vs SOD</div>
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

    # Resolve live values from prefs + MT5 session state
    _prefs = {}
    if _PREFS_FILE.exists():
        try:
            _prefs = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    _sym      = _prefs.get("trading_symbol", st.session_state.get("trading_symbol", "—"))
    _tf       = _prefs.get("timeframe",       st.session_state.get("timeframe", "—")).upper()
    _ema_f    = _prefs.get("ema_fast",        st.session_state.get("ema_fast", "—"))
    _ema_s    = _prefs.get("ema_slow",        st.session_state.get("ema_slow", "—"))
    _server   = st.session_state.get("_mt5_server",   _prefs.get("mt5_server", "—"))
    _login    = st.session_state.get("_mt5_login",    _prefs.get("mt5_account", "—"))
    _leverage = st.session_state.get("_mt5_leverage", "—")
    _currency = st.session_state.get("_mt5_currency", "USD")
    _connected = st.session_state.get("_mt5_connected", False)
    _conn_pill = '<span style="color:#10b981;font-weight:700;">● LIVE</span>' if _connected else '<span style="color:#ef4444;font-weight:700;">● OFFLINE</span>'

    _eq   = st.session_state.account_balance
    _pnl  = st.session_state.daily_pnl
    _init = float(_prefs.get("initial_balance", 10_000.0))
    _sod  = st.session_state.get("sod_balance", float(_prefs.get("ftmo_sod_balance", _init)))
    _dd   = ((_sod - _eq) / _sod * 100) if _sod > 0 else 0.0
    _dd_color = "#ef4444" if _dd > 3 else "#fbbf24" if _dd > 1 else "#10b981"

    _reset = _prefs.get("daily_reset_time", "00:00")
    _bar_count = _prefs.get("bar_count", 300)
    _risk_pct  = _prefs.get("ftmo_risk_pct", 5.0)
    _vol_filter = "ON" if _prefs.get("use_vol_filter", False) else "OFF"
    _atr_filter = "ON" if _prefs.get("use_atr_filter", True)  else "OFF"

    def _row(label, val, color="#f1f5f9", border=True):
        br = "border-bottom:1px solid #1e293b;padding-bottom:8px;" if border else ""
        return f'<div style="display:flex;justify-content:space-between;{br}margin-bottom:8px;"><span style="color:#64748b;">{label}</span><span style="color:{color};font-weight:600;">{val}</span></div>'

    st.markdown(f"""
    <div class="metric-card" style="--accent: linear-gradient(90deg,#6366f1,#8b5cf6); padding: 18px 20px;">
        <div style="display:grid; gap:2px; font-size:0.82rem;">
            {_row("MT5 Status", _conn_pill, border=True)}
            {_row("Server", _server)}
            {_row("Login", str(_login))}
            {_row("Leverage", f"1:{_leverage}" if _leverage != "—" else "—")}
            {_row("Currency", _currency)}
            {_row("Symbol", _sym, "#38bdf8")}
            {_row("Timeframe", _tf, "#818cf8")}
            {_row("EMA Fast / Slow", f"{_ema_f} / {_ema_s}")}
            {_row("Vol Filter", _vol_filter, "#fbbf24" if _vol_filter=="ON" else "#64748b")}
            {_row("ATR Filter", _atr_filter, "#fbbf24" if _atr_filter=="ON" else "#64748b")}
            {_row("Bar Count", str(_bar_count))}
            {_row("Daily Reset", f"{_reset} Prague")}
            {_row("SOD Balance", f"${_sod:,.2f}", "#94a3b8")}
            {_row("Live Equity", f"${_eq:,.2f}", "#34d399")}
            {_row("Float PnL", f"${_pnl:+,.2f}", "#10b981" if _pnl >= 0 else "#ef4444")}
            {_row("Drawdown", f"{_dd:.2f}%", _dd_color, border=False)}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Auto-refresh always (pulls live MT5 equity on each cycle) ─────────────────
time.sleep(3)
st.rerun()

