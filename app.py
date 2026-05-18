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
    """Read the latest PnL snapshot and event log from the background daemon (main.py)."""
    # 1. ALWAYS fetch real-time balance directly from MT5 broker
    import MetaTrader5 as mt5
    try:
        term = mt5.terminal_info()
        if term is not None:
            acc = mt5.account_info()
            if acc:
                st.session_state.account_balance = acc.equity
                st.session_state.daily_pnl       = acc.profit
                st.session_state.open_positions  = mt5.positions_total() or 0
    except Exception:
        pass

    # 2. Load PnL snapshot history as fallback / for trade count
    history = _storage.load_pnl_history()
    if history:
        last = history[-1]
        if st.session_state.account_balance == st.session_state.get("sod_balance", 100_000.0):
            # MT5 wasn't available — fall back to last saved snapshot
            st.session_state.account_balance = last.get("equity", st.session_state.account_balance)
            st.session_state.daily_pnl       = last.get("unrealised_pnl", 0.0)
            st.session_state.open_positions  = last.get("open_positions", 0)
        st.session_state.total_trades = last.get("total_trades", 0)
    else:
        st.session_state.total_trades = 0

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
    start_val = st.session_state.get("sod_balance", 100_000.0)
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
    st.markdown(f"""
    <div class="metric-card" style="--accent: linear-gradient(90deg,#6366f1,#8b5cf6); padding: 18px 20px;">
        <div style="display:grid; gap:10px; font-size:0.83rem;">
            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="color:#64748b;">Mode</span>
                <span class="mode-pill {MODE_COLORS.get(st.session_state.bot_mode,'mode-live')}">{st.session_state.bot_mode}</span>
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
                <span style="color:#64748b;">Live Equity</span>
                <span style="color:#34d399;font-weight:600;">${st.session_state.account_balance:,.2f}</span>
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


# ── Auto-refresh always (pulls live MT5 equity on each cycle) ─────────────────
time.sleep(3)
st.rerun()
