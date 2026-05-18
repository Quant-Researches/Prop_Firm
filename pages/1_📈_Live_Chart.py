"""
pages/1_📈_Live_Chart.py — Trade Pulse Quants
==============================================
Live Chart page: fetches candles via MT5,
runs RealTimeSignalGenerator (strategy.py), and renders
a Plotly candlestick chart with EMA overlays and BUY/SELL signal markers.
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
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
from Utilities.ui_components import load_css, render_sidebar, init_session_state
load_css()
st.markdown("""
<style>
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
</style>
""", unsafe_allow_html=True)


# ── Prefs Bootstrap ───────────────────────────────────────────────────────────
init_session_state()

def _pref(key):
    return st.session_state.get(key)

selected_asset_name  = _pref("trading_symbol")
selected_timeframe   = _pref("timeframe")
ema_fast             = int(_pref("ema_fast"))
ema_slow             = int(_pref("ema_slow"))
use_vol_filter       = bool(_pref("use_vol_filter"))
use_atr_filter       = bool(_pref("use_atr_filter"))
bar_count            = int(_pref("bar_count"))
mt5_path             = _pref("mt5_path")


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

    function fmtTZ(now, tz){
        var fmt = new Intl.DateTimeFormat('en-GB', {
            timeZone: tz,
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
        });
        var parts = fmt.formatToParts(now);
        var m = {};
        parts.forEach(function(p){ m[p.type] = p.value; });
        return m.day + ' ' + m.month + ' ' + m.year + ' ' + m.hour + ':' + m.minute + ':' + m.second;
    }

    function tick(){
        try{
            var el = window.parent.document.getElementById('chart-clock-text');
            if(!el) return;
            var now = new Date();

            var istStr  = fmtTZ(now, 'Asia/Kolkata');
            var ftmoStr = fmtTZ(now, 'Europe/Helsinki');

            var sep = '<span style="color:#334155;margin:0 10px;">|</span>';
            el.innerHTML =
                '<span style="color:#64748b;font-size:0.8rem;">IST</span> '
                + '<span style="color:#f8fafc;">' + istStr + '</span>'
                + sep
                + '<span style="color:#64748b;font-size:0.8rem;">FTMO MT5 (GMT+3)</span> '
                + '<span style="color:#38bdf8;">' + ftmoStr + '</span>';
        }catch(e){}
    }
    tick(); setInterval(tick, 1000);
})();
</script>
""", height=0)


# ── Sidebar Quick Controls ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**Quick Config**")
    st.info(f"Symbol: **{selected_asset_name}**\nEMA: **{ema_fast}/{ema_slow}** | TF: **{selected_timeframe}**\nVol Filter: **{'ON' if use_vol_filter else 'OFF'}**\nCandles: **{bar_count}**")
    st.caption("⚙️ Change settings on the **Settings** page.")

    auto_refresh = st.toggle("🔄 Auto-Refresh", value=st.session_state.get("chart_auto_refresh", False), key="chart_auto_refresh")
    refresh_interval = st.slider("Refresh interval (sec)", 10, 300, 60, step=10, disabled=not auto_refresh)

    refresh_btn = st.button("↺ Refresh Now", use_container_width=True)


# ── Data Fetch ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=55, show_spinner=False)
def _load_data(symbol, interval, bar_count, ema_fast, ema_slow, use_vol_filter, use_atr_filter, mt5_path, account, password, server, _cache_bust=0):
    from core.mt5_data import fetch_mt5_candles
    from core.strategy import RealTimeSignalGenerator

    df, source, err = fetch_mt5_candles(symbol, interval, bar_count, mt5_path=mt5_path, account=account, password=password, server=server)

    if df is None or df.empty:
        return None, None, source, err

    gen = RealTimeSignalGenerator(
        stock_symbol=symbol,
        sec_id=symbol,
        interval=interval,
        use_vol_filter=use_vol_filter,
        use_atr_filter=use_atr_filter,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
    )
    gen.update_data(df)
    result = gen.run_analysis()

    return result, gen.data, source, err


# Cache-bust key (incremented on manual refresh)
if "chart_cache_bust" not in st.session_state:
    st.session_state.chart_cache_bust = 0
if refresh_btn:
    st.session_state.chart_cache_bust += 1
    st.cache_data.clear()

with st.spinner("📡 Fetching market data via MT5..."):
    result, df_chart, data_source, err = _load_data(
        symbol=selected_asset_name,
        interval=selected_timeframe,
        bar_count=bar_count,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        use_vol_filter=use_vol_filter,
        use_atr_filter=use_atr_filter,
        mt5_path=mt5_path,
        account=_pref("mt5_account"),
        password=_pref("mt5_password"),
        server=_pref("mt5_server"),
        _cache_bust=st.session_state.chart_cache_bust,
    )


# ── No Data Guard ─────────────────────────────────────────────────────────────
if result is None or df_chart is None or df_chart.empty:
    st.error(f"❌ Could not fetch market data. Error: {err}")
    st.info("**Tip:** Go to ⚙️ Settings and ensure your MT5 connection is active and symbol is valid.")
    st.stop()


# ── Signal Summary Cards ──────────────────────────────────────────────────────
signal   = result.get("Signal", "HOLD")
phase    = result.get("Market_Phase", "SIDEWAYS")
price    = result.get("price", 0.0)
last_high = result.get("last_high", np.nan)
last_low  = result.get("last_low", np.nan)
fast_ema  = result.get("fast_ema", np.nan)
slow_ema  = result.get("slow_ema", np.nan)
reason   = result.get("Action", "")

sig_class = {"BUY": "signal-buy", "SELL": "signal-sell"}.get(signal, "signal-hold")
sig_val_class = {"BUY": "buy", "SELL": "sell"}.get(signal, "hold")
phase_cls = {"BULLISH": "phase-bullish", "BEARISH": "phase-bearish"}.get(phase, "phase-sideways")
sig_icon  = {"BUY": "▲", "SELL": "▼"}.get(signal, "—")

s1, s2, s3, s4, s5 = st.columns(5)

with s1:
    st.markdown(f'''
    <div class="signal-card {sig_class}">
        <div class="signal-label">Latest Signal</div>
        <div class="signal-value {sig_val_class}">{sig_icon} {signal}</div>
    </div>''', unsafe_allow_html=True)

with s2:
    st.markdown(f'''
    <div class="signal-card signal-hold">
        <div class="signal-label">Market Phase</div>
        <div style="margin-top:6px;"><span class="phase-pill {phase_cls}">{phase}</span></div>
    </div>''', unsafe_allow_html=True)

with s3:
    st.markdown(f'''
    <div class="signal-card signal-hold">
        <div class="signal-label">CMP</div>
        <div class="signal-value hold">${price:,.2f}</div>
    </div>''', unsafe_allow_html=True)

with s4:
    st.markdown(f'''
    <div class="signal-card signal-hold">
        <div class="signal-label">Fractal High / Low</div>
        <div class="signal-value" style="font-size:0.95rem;color:#e2e8f0;">
            <span style="color:#10b981">{last_high:,.2f}</span> /
            <span style="color:#ef4444">{last_low:,.2f}</span>
        </div>
    </div>''', unsafe_allow_html=True)

with s5:
    st.markdown(f'''
    <div class="signal-card signal-hold">
        <div class="signal-label">EMA {ema_fast} / {ema_slow}</div>
        <div class="signal-value" style="font-size:0.95rem;color:#e2e8f0;">
            <span style="color:#c084fc">{fast_ema:,.2f}</span> /
            <span style="color:#38bdf8">{slow_ema:,.2f}</span>
        </div>
    </div>''', unsafe_allow_html=True)

if reason:
    st.markdown(f'''
    <div style="margin:8px 0 14px; padding:8px 14px; background:rgba(99,102,241,0.08);
         border:1px solid rgba(99,102,241,0.2); border-radius:8px;
         font-size:0.8rem; color:#94a3b8;">
        📝 Signal Reason: <span style="color:#a5b4fc;">{reason}</span>
    </div>''', unsafe_allow_html=True)


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
