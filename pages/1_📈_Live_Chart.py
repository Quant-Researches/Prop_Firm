"""
pages/1_📈_Live_Chart.py — Trade Pulse Quants
==============================================
Live Chart page: fetches ≥300 candles via Dhan API (or yfinance fallback),
runs RealTimeSignalGenerator (strategy.py — UNCHANGED logic), and renders
a Plotly candlestick chart with EMA overlays and BUY/SELL signal markers.

Run with:  streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import json
from pathlib import Path

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Live Chart — Trade Pulse Quants",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #0a0e1a; color: #e2e8f0; }

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080d1c 0%, #0d1225 60%, #111827 100%);
    border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p { color: #94a3b8 !important; }

/* Header */
.chart-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid #312e81;
    border-radius: 16px;
    padding: 18px 28px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 0 40px rgba(99,102,241,0.12);
}
.chart-title {
    font-size: 1.5rem;
    font-weight: 800;
    background: linear-gradient(90deg, #818cf8, #c084fc, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.chart-sub { font-size: 0.8rem; color: #64748b; margin-top: 3px; }

/* Signal card */
.signal-card {
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
    border: 1px solid;
    transition: all 0.3s;
}
.signal-buy   { background: rgba(16,185,129,0.1);  border-color: rgba(16,185,129,0.4); }
.signal-sell  { background: rgba(239,68,68,0.1);   border-color: rgba(239,68,68,0.4);  }
.signal-hold  { background: rgba(100,116,139,0.1); border-color: rgba(100,116,139,0.3);}
.signal-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1.5px; color: #64748b; margin-bottom: 4px; }
.signal-value { font-size: 1.4rem; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
.signal-value.buy  { color: #10b981; }
.signal-value.sell { color: #ef4444; }
.signal-value.hold { color: #94a3b8; }

/* Phase badges */
.phase-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.phase-bullish { background: rgba(16,185,129,0.15);  color: #10b981; border: 1px solid #10b981; }
.phase-bearish { background: rgba(239,68,68,0.15);   color: #ef4444; border: 1px solid #ef4444; }
.phase-sideways{ background: rgba(251,191,36,0.15);  color: #fbbf24; border: 1px solid #fbbf24; }

/* Metric row */
.metric-row {
    display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap;
}
.mini-card {
    flex: 1;
    min-width: 120px;
    background: rgba(255,255,255,0.025);
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 12px 16px;
}
.mini-label { font-size: 0.65rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.mini-value { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; font-family: 'JetBrains Mono', monospace; margin-top: 3px; }

/* Source badge */
.source-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 0.68rem; font-weight: 600;
}
.source-dhan { background: rgba(99,102,241,0.15); color: #818cf8; border: 1px solid #4f46e5; }
.source-yf   { background: rgba(251,191,36,0.12); color: #fbbf24; border: 1px solid #d97706; }

header[data-testid="stHeader"] { background-color: #0a0e1a !important; border-bottom: 1px solid #1e293b !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.stMainBlockContainer { padding-top: 2rem !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0e1a; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ── Prefs Bootstrap ───────────────────────────────────────────────────────────
PREFS_FILE = Path(__file__).parent.parent / "config" / "user_prefs.json"

DEFAULT_PREFS = {
    "dhan_client_id":     "",
    "dhan_api_key":       "",
    "trading_symbol":     "Gold Petal (1g)",
    "security_id":        "626",
    "exchange_segment":   "MCX_COMM",
    "instrument_type":    "FUTCOM",
    "timeframe":          "5m",
    "ema_fast":           3,
    "ema_slow":           8,
    "use_vol_filter":     True,
    "trade_volume":       1,
    "bar_count":          300,
    "yf_fallback_symbol": "GC=F",
}

if "_prefs_loaded" not in st.session_state:
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE) as f:
                saved = json.load(f)
            for k, v in {**DEFAULT_PREFS, **saved}.items():
                st.session_state[k] = v
        except Exception:
            for k, v in DEFAULT_PREFS.items():
                st.session_state.setdefault(k, v)
    else:
        for k, v in DEFAULT_PREFS.items():
            st.session_state.setdefault(k, v)
    st.session_state["_prefs_loaded"] = True


# ── Read active settings ──────────────────────────────────────────────────────
def _pref(key):
    return st.session_state.get(key, DEFAULT_PREFS.get(key))

selected_asset_name  = _pref("trading_symbol")
security_id          = _pref("security_id")
exchange_segment     = _pref("exchange_segment")
instrument_type      = _pref("instrument_type")
selected_timeframe   = _pref("timeframe")
ema_fast             = int(_pref("ema_fast"))
ema_slow             = int(_pref("ema_slow"))
use_vol_filter       = bool(_pref("use_vol_filter"))
bar_count            = int(_pref("bar_count"))
dhan_client_id       = _pref("dhan_client_id")
dhan_api_key         = _pref("dhan_api_key")
yf_fallback_symbol   = _pref("yf_fallback_symbol")
active_data_source   = _pref("data_source")


# ── Page Header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="chart-header">
    <div>
        <div class="chart-title">📈 {selected_asset_name}</div>
        <div class="chart-sub">Candlestick Chart — Dow Theory Strategy | {selected_timeframe} | EMA {ema_fast}/{ema_slow}</div>
    </div>
    <div id="chart-live-clock" style="font-family:'JetBrains Mono',monospace;font-size:0.95rem;color:#38bdf8;
         background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.2);border-radius:8px;padding:8px 14px;">
        🕐 <span id="chart-clock-text">loading...</span>
    </div>
</div>
""", unsafe_allow_html=True)

components.html("""
<script>
(function(){
    function pad(n){return String(n).padStart(2,'0');}
    var MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    function tick(){
        try{
            var el=window.parent.document.getElementById('chart-clock-text');
            if(!el) return;
            var now=new Date();
            el.textContent=pad(now.getDate())+' '+MONTHS[now.getMonth()]+' '+now.getFullYear()
                +'  '+pad(now.getHours())+':'+pad(now.getMinutes())+':'+pad(now.getSeconds());
        }catch(e){}
    }
    tick(); setInterval(tick,1000);
})();
</script>
""", height=0)


# ── Sidebar Quick Controls ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 12px 12px; border-bottom:1px solid #1e293b; margin-bottom:8px;">
        <div style="font-size:1.0rem;font-weight:800;background:linear-gradient(90deg,#818cf8,#c084fc);
             -webkit-background-clip:text;-webkit-text-fill-color:transparent;">⚡ Trade Pulse Quants</div>
        <div style="font-size:0.68rem;color:#475569;margin-top:2px;">LIVE CHART</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Quick Config**")
    st.info(f"Symbol: **{selected_asset_name}**\nEMA: **{ema_fast}/{ema_slow}** | TF: **{selected_timeframe}**\nVol Filter: **{'ON' if use_vol_filter else 'OFF'}**\nCandles: **{bar_count}**")
    st.caption("⚙️ Change settings on the **Settings** page.")

    auto_refresh = st.toggle("🔄 Auto-Refresh", value=st.session_state.get("chart_auto_refresh", False), key="chart_auto_refresh")
    refresh_interval = st.slider("Refresh interval (sec)", 10, 300, 60, step=10, disabled=not auto_refresh)

    refresh_btn = st.button("↺ Refresh Now", use_container_width=True)


# ── Data Fetch ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=55, show_spinner=False)
def _load_data(security_id, exchange_segment, instrument_type, interval,
               client_id, access_token, bar_count, yf_symbol, active_data_source,
               ema_fast, ema_slow, use_vol_filter, use_atr_filter, _cache_bust=0):
    """Cached data fetch + strategy analysis."""
    from core.dhan_data import fetch_candles
    from core.strategy import RealTimeSignalGenerator

    df, source, dhan_error = fetch_candles(
        security_id=security_id,
        exchange_segment=exchange_segment,
        instrument_type=instrument_type,
        interval=interval,
        client_id=client_id,
        access_token=access_token,
        bar_count=bar_count,
        fallback_symbol=yf_symbol,
        data_source=active_data_source,
    )

    if df is None or df.empty:
        return None, None, source, dhan_error

    gen = RealTimeSignalGenerator(
        stock_symbol=security_id,
        sec_id=security_id,
        interval=interval,
        use_vol_filter=use_vol_filter,
        use_atr_filter=use_atr_filter,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
    )
    gen.update_data(df)
    result = gen.run_analysis()

    return result, gen.data, source, dhan_error


# Cache-bust key (incremented on manual refresh)
if "chart_cache_bust" not in st.session_state:
    st.session_state.chart_cache_bust = 0
if refresh_btn:
    st.session_state.chart_cache_bust += 1
    st.cache_data.clear()

with st.spinner("📡 Fetching market data..."):
    result, df_chart, data_source, _dhan_err = _load_data(
        security_id=security_id,
        exchange_segment=exchange_segment,
        instrument_type=instrument_type,
        interval=selected_timeframe,
        client_id=dhan_client_id,
        access_token=dhan_api_key,
        bar_count=bar_count,
        yf_symbol=yf_fallback_symbol,
        active_data_source=active_data_source,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        use_vol_filter=use_vol_filter,
        use_atr_filter=st.session_state.get("use_atr_filter", True),
        _cache_bust=st.session_state.chart_cache_bust,
    )


# ── Data Source Banner ──────────────────────────────────────────────────────────────────────────────
if data_source == "yfinance":
    st.warning("⚠️ **Using yfinance fallback** — Data is delayed / not MCX live feed. Configure Dhan API credentials in ⚙️ Settings for live data.")
    if _dhan_err:
        with st.expander("🔍 Why did Dhan API fail? (click to expand)", expanded=True):
            st.error(f"🚨 **Dhan API Error:**  \n```\n{_dhan_err}\n```")
            st.markdown("""
**Common fixes:**
- 🔑 **Token expired** — Dhan access tokens expire daily. Generate a new one at [Dhan Developer Portal](https://developer.dhan.co) and update in ⚙️ Settings.
- 📍 **Wrong Security ID** — Go to ⚙️ Settings, pick a symbol from the live dropdown, and click Save.
- 📶 **Weekend/holiday** — MCX is closed; Dhan returns empty data. The yfinance fallback is expected.
            """)
elif data_source == "dhan":
    st.markdown('<span class="source-badge source-dhan">🟢 Dhan API — Live MCX Feed</span>', unsafe_allow_html=True)


# ── No Data Guard ─────────────────────────────────────────────────────────────
if result is None or df_chart is None or df_chart.empty:
    st.error("❌ Could not fetch market data. Please check your Settings (API credentials or internet connection).")
    st.info("**Tip:** Go to ⚙️ Settings, leave Dhan credentials blank, and ensure your yfinance fallback symbol is correct (e.g. `GC=F` for Gold).")
    st.stop()


# ── Signal Summary Cards ──────────────────────────────────────────────────────
signal   = result.get("signal", "HOLD")
phase    = result.get("phase", "SIDEWAYS")
price    = result.get("price", 0.0)
last_high = result.get("last_high", np.nan)
last_low  = result.get("last_low", np.nan)
fast_ema  = result.get("fast_ema", np.nan)
slow_ema  = result.get("slow_ema", np.nan)
reason   = result.get("reason", "")

sig_class = {"BUY": "signal-buy", "SELL": "signal-sell"}.get(signal, "signal-hold")
sig_val_class = {"BUY": "buy", "SELL": "sell"}.get(signal, "hold")
phase_cls = {"BULLISH": "phase-bullish", "BEARISH": "phase-bearish"}.get(phase, "phase-sideways")
sig_icon  = {"BUY": "▲", "SELL": "▼"}.get(signal, "—")

s1, s2, s3, s4, s5 = st.columns(5)

with s1:
    st.markdown(f"""
    <div class="signal-card {sig_class}">
        <div class="signal-label">Latest Signal</div>
        <div class="signal-value {sig_val_class}">{sig_icon} {signal}</div>
    </div>""", unsafe_allow_html=True)

with s2:
    st.markdown(f"""
    <div class="signal-card signal-hold">
        <div class="signal-label">Market Phase</div>
        <div style="margin-top:6px;"><span class="phase-pill {phase_cls}">{phase}</span></div>
    </div>""", unsafe_allow_html=True)

with s3:
    st.markdown(f"""
    <div class="signal-card signal-hold">
        <div class="signal-label">CMP</div>
        <div class="signal-value hold">₹{price:,.2f}</div>
    </div>""", unsafe_allow_html=True)

with s4:
    st.markdown(f"""
    <div class="signal-card signal-hold">
        <div class="signal-label">Fractal High / Low</div>
        <div class="signal-value" style="font-size:0.95rem;color:#e2e8f0;">
            <span style="color:#10b981">{last_high:,.2f}</span> /
            <span style="color:#ef4444">{last_low:,.2f}</span>
        </div>
    </div>""", unsafe_allow_html=True)

with s5:
    st.markdown(f"""
    <div class="signal-card signal-hold">
        <div class="signal-label">EMA {ema_fast} / {ema_slow}</div>
        <div class="signal-value" style="font-size:0.95rem;color:#e2e8f0;">
            <span style="color:#c084fc">{fast_ema:,.2f}</span> /
            <span style="color:#38bdf8">{slow_ema:,.2f}</span>
        </div>
    </div>""", unsafe_allow_html=True)

if reason:
    st.markdown(f"""
    <div style="margin:8px 0 14px; padding:8px 14px; background:rgba(99,102,241,0.08);
         border:1px solid rgba(99,102,241,0.2); border-radius:8px;
         font-size:0.8rem; color:#94a3b8;">
        📝 Signal Reason: <span style="color:#a5b4fc;">{reason}</span>
    </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CANDLESTICK CHART — Centralized Graph Generation
# ══════════════════════════════════════════════════════════════════════════════
from core.chart_utils import generate_trade_chart
import numpy as np

fig_merge = generate_trade_chart(
    df_chart=df_chart,
    selected_asset_name=selected_asset_name,
    selected_timeframe=selected_timeframe,
    ema_fast=ema_fast,
    ema_slow=ema_slow,
    last_high=last_high,
    last_low=last_low,
    dark_mode=False
)

st.plotly_chart(fig_merge, use_container_width=True, config={'scrollZoom': True})


# ── Recent Signals Table ──────────────────────────────────────────────────────
with st.expander("📋 Recent Signals Table", expanded=False):
    if 'Signal_Vis' in df_chart.columns:
        sig_df = df_chart[df_chart['Signal_Vis'].isin(['BUY', 'SELL'])][
            ['Open', 'High', 'Low', 'Close', 'Volume', 'Signal_Vis', 'Signal_Reason', 'Phase', 'fast_ema', 'slow_ema']
        ].tail(20).copy()
        sig_df.index = sig_df.index.strftime('%Y-%m-%d %H:%M')
        sig_df.columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Signal', 'Reason', 'Phase', f'EMA{ema_fast}', f'EMA{ema_slow}']

        def _color_signal(val):
            if val == 'BUY':
                return 'color: #10b981; font-weight: 700'
            elif val == 'SELL':
                return 'color: #ef4444; font-weight: 700'
            return ''

        styled = sig_df.style.applymap(_color_signal, subset=['Signal'])
        st.dataframe(styled, use_container_width=True)
    else:
        st.info("No signal data available.")


# ── Auto Refresh ───────────────────────────────────────────────────────────────
if auto_refresh:
    import time
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()
