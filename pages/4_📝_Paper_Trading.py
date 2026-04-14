"""
pages/4_📝_Paper_Trading.py — Trade Pulse Quants
================================================
Isolated dashboard for viewing Paper Trading performance.
This page reads from data/trades.json and data/pnl_history.csv
which are ONLY populated when execution_mode is 'JSON Only'.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import json

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Paper Trading — Trade Pulse Quants",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #0a0e1a; color: #e2e8f0; }

/* Sidebar shell */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080d1c 0%, #0d1225 60%, #111827 100%);
    border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p { color: #94a3b8 !important; }

/* Header */
.page-header {
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
    border: 1px solid #312e81;
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 0 40px rgba(139,92,246,0.12);
}
.page-title {
    font-size: 1.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, #c084fc, #e879f9, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.page-sub { font-size: 0.85rem; color: #94a3b8; margin-top: 4px; }

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #111827 0%, #1e293b 100%);
    border: 1px solid #1e293b;
    border-radius: 14px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
}
.metric-card:hover { border-color: #c084fc; }
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: var(--accent, linear-gradient(90deg, #c084fc, #e879f9));
}
.metric-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.metric-value { font-size: 1.9rem; font-weight: 700; margin: 6px 0; color: #f1f5f9; }
.metric-delta { font-size: 0.8rem; }
.delta-pos { color: #10b981; }
.delta-neg { color: #ef4444; }
.delta-neu { color: #64748b; }

/* DataFrame tables styling */
[data-testid="stDataFrame"] {
    background: #0f172a; border-radius: 12px; border: 1px solid #1e293b;
}

[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.stMainBlockContainer { padding-top: 2rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Paths ──────────────────────────────────────────────────────────────────────
TRADES_FILE = Path("data/trades.json")
PNL_FILE = Path("data/pnl_history.csv")

# ── Data Loading ───────────────────────────────────────────────────────────────
def load_paper_pnl():
    if not PNL_FILE.exists():
        return None
    try:
        df = pd.read_csv(PNL_FILE)
        if df.empty: return None
        return df.iloc[-1]
    except Exception:
        return None

def load_paper_trades():
    if not TRADES_FILE.exists():
        return []
    try:
        with open(TRADES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

# ── UI Layout ──────────────────────────────────────────────────────────────────

st.markdown("""
<div class="page-header">
    <div>
        <div class="page-title">📝 Paper Trading Dashboard</div>
        <div class="page-sub">Isolated simulation metrics (JSON Only execution mode)</div>
    </div>
    <div style="background:rgba(244,114,182,0.1); border:1px solid rgba(244,114,182,0.3); padding:8px 16px; border-radius:8px; color:#f472b6; font-size:0.85rem; font-weight:600; text-align:center;">
        SIMULATED EXECUTION
    </div>
</div>
""", unsafe_allow_html=True)

# ── 1. Metrics ─────────────────────────────────────────────────────────────────
pnl_data = load_paper_pnl()

if not pnl_data is None:
    m1, m2, m3, m4 = st.columns(4)
    
    total_trades = int(pnl_data.get("total_trades", 0))
    open_pos = int(pnl_data.get("open_positions", 0))
    daily_pnl = float(pnl_data.get("realised_pnl", 0)) + float(pnl_data.get("unrealised_pnl", 0))
    equity = float(pnl_data.get("equity", 100000))
    
    pnl_color = "delta-pos" if daily_pnl >= 0 else "delta-neg"
    pnl_sign = "+" if daily_pnl >= 0 else ""
    pnl_icon = "▲" if daily_pnl >= 0 else "▼"
    
    with m1:
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#9333ea,#c084fc);">
            <div class="metric-label">Simulated Trades</div>
            <div class="metric-value">{total_trades}</div>
            <div class="metric-delta delta-neu">Total lifetime</div>
        </div>""", unsafe_allow_html=True)

    with m2:
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#e879f9,#f472b6);">
            <div class="metric-label">Open Positions</div>
            <div class="metric-value">{open_pos}</div>
            <div class="metric-delta delta-neu">Active now</div>
        </div>""", unsafe_allow_html=True)

    with m3:
        pnl_abs = abs(daily_pnl)
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#10b981,#059669);">
            <div class="metric-label">Paper PnL</div>
            <div class="metric-value">₹{pnl_sign}{daily_pnl:,.0f}</div>
            <div class="metric-delta {pnl_color}">{pnl_icon} {pnl_sign}₹{pnl_abs:,.0f} total</div>
        </div>""", unsafe_allow_html=True)

    with m4:
        bal_delta = equity - 100_000
        bd_color = "delta-pos" if bal_delta >= 0 else "delta-neg"
        bd_sign = "+" if bal_delta >= 0 else ""
        st.markdown(f"""
        <div class="metric-card" style="--accent: linear-gradient(90deg,#38bdf8,#0ea5e9);">
            <div class="metric-label">Virtual Equity</div>
            <div class="metric-value">₹{equity:,.0f}</div>
            <div class="metric-delta {bd_color}">{bd_sign}₹{bal_delta:,.0f} vs base (₹100k)</div>
        </div>""", unsafe_allow_html=True)
else:
    st.info("No paper trading performance data found yet. Run the engine in 'JSON Only' mode to generate metrics.")

st.markdown("<br>", unsafe_allow_html=True)

# ── 2. Trade Ledger ────────────────────────────────────────────────────────────
st.markdown('<div style="font-size:1.1rem; font-weight:700; color:#e2e8f0; margin-bottom:12px;">📊 Paper Trade Ledger</div>', unsafe_allow_html=True)

trades = load_paper_trades()
if trades:
    # Reverse to show newest trades at the top
    trades.reverse()
    
    df = pd.DataFrame(trades)
    
    # Format and clean dataframe for display
    if 'timestamp' in df:
        df['Date/Time'] = pd.to_datetime(df['timestamp']).dt.strftime('%d-%b %H:%M:%S')
    else:
        df['Date/Time'] = "Unknown"
        
    df['Side'] = df['side'].apply(lambda x: '🟢 BUY' if x == 'BUY' else '🔴 SELL')
    df['Qty'] = df['qty'].astype(int)
    df['Fill Price'] = df['fill_price'].apply(lambda x: f"₹{x:,.2f}")
    df['Commission'] = df['commission'].apply(lambda x: f"₹{x:,.2f}")
    df['Order ID'] = df['order_id']
    df['Symbol'] = df['symbol']
    
    display_cols = ['Date/Time', 'Order ID', 'Symbol', 'Side', 'Qty', 'Fill Price', 'Commission']
    st.dataframe(df[display_cols], hide_index=True, use_container_width=True)
else:
    st.info("No paper trades recorded yet.")

# Refresh button
if st.button("🔄 Refresh Dash", key="refresh_paper"):
    st.rerun()

# ── Sidebar Warning ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="background:rgba(244,114,182,0.08); border:1px solid rgba(244,114,182,0.3); padding:12px; border-radius:10px; margin-top:20px;">
        <h4 style="color:#f472b6; margin-top:0; font-size:0.9rem;">ℹ️ About Paper Trading</h4>
        <p style="font-size:0.75rem; color:#cbd5e1; line-height:1.5; margin-bottom:0;">
            This isolated dashboard exclusively shows trades executed when the bot is set to <b>JSON Only</b> execution mode.<br><br>
            If you execute trades in <b>Dhan Realtime</b> mode, they will not appear here.
        </p>
    </div>
    """, unsafe_allow_html=True)