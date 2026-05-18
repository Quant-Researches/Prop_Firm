"""
pages/3_⚙️_Settings.py — Trade Pulse Quants
============================================
User Preferences & Settings page.
All values are stored in st.session_state AND persisted to
config/user_prefs.json so they survive page reloads.
"""

import streamlit as st
import json
from pathlib import Path
import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.dhan_instruments import get_mcx_instruments, get_cache_info

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Settings — Trade Pulse Quants",
    page_icon="⚙️",
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

/* Section card */
.settings-card {
    background: rgba(255,255,255,0.025);
    border: 1px solid #1e293b;
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 20px;
}
.settings-card:hover { border-color: #2d3f5e; transition: border-color 0.2s; }
.card-title {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #475569;
    font-weight: 700;
    border-bottom: 1px solid #1a2235;
    padding-bottom: 10px;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Input styling */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    background: #0d1225 !important;
    border: 1px solid #1e293b !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
    font-family: 'JetBrains Mono', monospace !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
}
[data-testid="stSelectbox"] > div {
    background: #0d1225 !important;
    border-color: #1e293b !important;
    color: #e2e8f0 !important;
}

/* Save button */
.save-btn-container .stButton > button {
    background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
    border: 1px solid #4f46e5 !important;
    color: #fff !important;
    font-size: 0.95rem !important;
    padding: 12px 0 !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    transition: all 0.25s !important;
}
.save-btn-container .stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(99,102,241,0.4) !important;
}

/* Info badge */
.info-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(56,189,248,0.08);
    border: 1px solid rgba(56,189,248,0.2);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.72rem;
    color: #38bdf8;
    font-weight: 500;
}
.success-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(16,185,129,0.12);
    border: 1px solid rgba(16,185,129,0.35);
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 0.78rem;
    color: #10b981;
    font-weight: 600;
}

header[data-testid="stHeader"] {
    background-color: #0a0e1a !important;
    border-bottom: 1px solid #1e293b !important;
}
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.stMainBlockContainer { padding-top: 2rem !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0e1a; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ── Prefs file ────────────────────────────────────────────────────────────────
PREFS_DIR  = Path(__file__).parent.parent / "config"
PREFS_FILE = PREFS_DIR / "user_prefs.json"

DEFAULT_PREFS = {
    "data_source":       "Dhan",
    "execution_mode":    "JSON Only",
    "dhan_client_id":    "",
    "dhan_pin":          "",
    "totp_secret":       "",
    "dhan_api_key":      "",
    "trading_symbol":    "Gold Petal (1g)",
    "security_id":       "626",
    "exchange_segment":  "MCX_COMM",
    "instrument_type":   "FUTCOM",
    "timeframe":         "5m",
    "ema_fast":          3,
    "ema_slow":          8,
    "use_vol_filter":    True,
    "capital":           100000,
    "leverage":          1.0,
    "bar_count":         300,
    "yf_fallback_symbol": "GC=F",
}


def _load_prefs() -> dict:
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE) as f:
                saved = json.load(f)
            prefs = {**DEFAULT_PREFS, **saved}
            return prefs
        except Exception:
            pass
    return dict(DEFAULT_PREFS)


def _save_prefs(prefs: dict):
    PREFS_DIR.mkdir(parents=True, exist_ok=True)
    # Never write the API key to disk if user prefers in-memory only
    # But user explicitly wants persistence — write as-is
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


def _apply_to_session(prefs: dict):
    for k, v in prefs.items():
        st.session_state[k] = v


# ── Bootstrap session state on first load ────────────────────────────────────
if "_prefs_loaded" not in st.session_state:
    loaded = _load_prefs()
    _apply_to_session(loaded)
    st.session_state["_prefs_loaded"] = True


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <div class="page-title">⚙️ User Preferences & Settings</div>
    <div class="page-sub">Configure your Dhan API credentials, trading symbol, strategy parameters, and execution preferences.</div>
</div>
""", unsafe_allow_html=True)


# ── MCX Instrument helper ─────────────────────────────────────────────────────
# Load instruments: live CSV → local cache → hardcoded fallback
_force_refresh = st.session_state.pop("_instrument_refresh", False)
MCX_INSTRUMENTS_BASE, _instr_source = get_mcx_instruments(force_refresh=_force_refresh)

# Always append a "Custom" entry at the end
MCX_INSTRUMENTS = {**MCX_INSTRUMENTS_BASE, "Custom": {"security_id": "", "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"}}

EXCHANGE_SEGMENTS = ["MCX_COMM", "NSE_EQ", "NSE_FNO", "BSE_EQ", "BSE_FNO", "NSE_CURRENCY"]
INSTRUMENT_TYPES  = ["FUTCOM", "FUTIDX", "FUTSTK", "OPTSTK", "OPTIDX", "EQUITY"]
TIMEFRAMES        = ["1m", "3m", "5m", "15m", "25m", "30m", "1h", "1d"]


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Symbol Configuration (Dynamic, outside form)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="settings-card">', unsafe_allow_html=True)
st.markdown('<div class="card-title">📊 Symbol Selection & API Source</div>', unsafe_allow_html=True)

# ── Instrument source status + refresh button ─────────────────────────────────
_badge_col, _refresh_col = st.columns([4, 1])
with _badge_col:
    _cache_info = get_cache_info()
    if _instr_source in ("live", "cache"):
        _count = _cache_info.get("count", len(MCX_INSTRUMENTS_BASE))
        _age   = f" · cached {_cache_info.get('age_hours', 0):.0f}h ago" if _instr_source == "cache" else " · just fetched"
        st.markdown(
            f'<div class="info-badge">✅ Live from Dhan &nbsp;·&nbsp; <b>{_count}</b> MCX FUTCOM instruments{_age}</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div style="display:inline-flex;align-items:center;gap:6px;background:rgba(251,191,36,0.1);'
            'border:1px solid rgba(251,191,36,0.35);border-radius:20px;padding:4px 12px;'
            'font-size:0.72rem;color:#fbbf24;font-weight:500;">'
            '⚠️ Using fallback list — check internet connection and click Refresh</div>',
            unsafe_allow_html=True
        )
with _refresh_col:
    if st.button("🔄 Refresh List", key="btn_refresh_instruments", use_container_width=True):
        st.session_state["_instrument_refresh"] = True
        st.rerun()
st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

selected_preset = "Custom"
current_source = st.session_state.get("data_source", "Dhan")

def _on_source_change():
    st.session_state["data_source"] = st.session_state.input_data_source

st.radio(
    "Primary Data Source",
    options=["Dhan", "YFinance"],
    index=0 if current_source == "Dhan" else 1,
    horizontal=True,
    key="input_data_source",
    on_change=_on_source_change
)

st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

if current_source == "Dhan":
    preset_names = list(MCX_INSTRUMENTS.keys())
    current_preset = st.session_state.get("trading_symbol", "Gold Petal (1g)")
    if current_preset not in preset_names:
        current_preset = "Custom"

    def _on_preset_change():
        new_preset = st.session_state.input_preset
        if new_preset != "Custom" and new_preset in MCX_INSTRUMENTS:
            data = MCX_INSTRUMENTS[new_preset]
            st.session_state.input_security_id = data["security_id"]
            st.session_state.input_exchange_segment = data["exchange_segment"]
            st.session_state.input_instrument_type = data["instrument_type"]

    selected_preset = st.selectbox(
        "Quick Select (MCX Presets)",
        options=preset_names,
        index=preset_names.index(current_preset) if current_preset in preset_names else 0,
        key="input_preset",
        on_change=_on_preset_change
    )
else:
    st.text_input(
        "YFinance Symbol",
        value=st.session_state.get("yf_fallback_symbol", "GC=F"),
        placeholder="e.g. TSLA, AAPL, GC=F for Gold",
        help="Custom symbol for YFinance data feed",
        key="input_yf_fallback",
        on_change=lambda: None
    )

st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Global Settings Form
# ══════════════════════════════════════════════════════════════════════════════
with st.form("global_settings_form", border=False):
    
    if current_source == "Dhan":
        st.markdown('<div class="settings-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🔑 Dhan API Credentials</div>', unsafe_allow_html=True)
    
        cred_c1, cred_c2 = st.columns(2)
        with cred_c1:
            client_id = st.text_input(
                "Client ID",
                value=st.session_state.get("dhan_client_id", ""),
                placeholder="Your Dhan Client ID",
                help="Found in your Dhan account → Profile → API",
                key="input_client_id",
            )
            pin = st.text_input(
                "Dhan PIN",
                value=st.session_state.get("dhan_pin", ""),
                type="password",
                placeholder="6-digit Dhan PIN",
                key="input_dhan_pin",
            )
        with cred_c2:
            totp = st.text_input(
                "TOTP Secret",
                value=st.session_state.get("totp_secret", ""),
                type="password",
                placeholder="Your Base32 TOTP Secret",
                key="input_totp_secret",
            )
            api_key = st.text_input(
                "Access Token (API Key)",
                value=st.session_state.get("dhan_api_key", ""),
                type="password",
                placeholder="Auto-generated or Paste here",
                help="Generated via TOTP or Dhan Developer Portal",
                key="input_api_key",
            )

        st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
        gen_btn_clicked = st.form_submit_button("🔑 Generate Token - TOTP", use_container_width=True)
        if gen_btn_clicked:
            try:
                from core.dhan_auth import DhanAutoLogin
                c_id = st.session_state.input_client_id.strip()
                c_pin = st.session_state.input_dhan_pin.strip()
                c_totp = st.session_state.input_totp_secret.strip()
                if not (c_id and c_pin and c_totp):
                    st.error("⚠️ Please fill Client ID, Dhan PIN, and TOTP Secret to generate token.")
                else:
                    data = DhanAutoLogin.generate_and_save_token(c_id, c_pin, c_totp, str(PREFS_FILE))
                    st.session_state["dhan_api_key"] = data.get("accessToken", "")
                    st.session_state["dhan_client_id"] = c_id
                    st.session_state["dhan_pin"] = c_pin
                    st.session_state["totp_secret"] = c_totp
                    st.success("✅ Access Token generated and saved successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to generate token: {e}")
        st.markdown('</div>', unsafe_allow_html=True)
    
        st.markdown('<div class="settings-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">⚙️ Instrument Details</div>', unsafe_allow_html=True)
        
        # Auto-fill or allow custom override
        preset_data = MCX_INSTRUMENTS[selected_preset]
        st.markdown("**Instrument Details** (auto-filled from preset, editable for custom):")
    
        det_c1, det_c2, det_c3 = st.columns(3)
        with det_c1:
            security_id = st.text_input(
                "Security ID",
                value=preset_data["security_id"] if selected_preset != "Custom"
                      else st.session_state.get("security_id", ""),
                placeholder="e.g. 626",
                key="input_security_id",
            )
        with det_c2:
            seg_opts = EXCHANGE_SEGMENTS
            seg_default = preset_data["exchange_segment"]
            exchange_segment = st.selectbox(
                "Exchange Segment",
                options=seg_opts,
                index=seg_opts.index(seg_default) if seg_default in seg_opts else 0,
                key="input_exchange_segment",
            )
        with det_c3:
            inst_opts = INSTRUMENT_TYPES
            inst_default = preset_data["instrument_type"]
            instrument_type = st.selectbox(
                "Instrument Type",
                options=inst_opts,
                index=inst_opts.index(inst_default) if inst_default in inst_opts else 0,
                key="input_instrument_type",
            )
    
        st.markdown('</div>', unsafe_allow_html=True)


    # ══════════════════════════════════════════════════════════════════════════════
    # Section 3 — Strategy Parameters
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🧠 Strategy Parameters</div>', unsafe_allow_html=True)

    sp_c1, sp_c2, sp_c3, sp_c4 = st.columns(4)

    with sp_c1:
        tf_opts = TIMEFRAMES
        cur_tf = st.session_state.get("timeframe", "5m")
        timeframe = st.selectbox(
            "⏱️ Timeframe",
            options=tf_opts,
            index=tf_opts.index(cur_tf) if cur_tf in tf_opts else 2,
            help="Bar interval used to fetch data and generate signals",
            key="input_timeframe",
        )

    with sp_c2:
        ema_fast = st.number_input(
            "⚡ Fast EMA Period",
            min_value=1, max_value=50,
            value=int(st.session_state.get("ema_fast", 3)),
            step=1,
            help="Faster EMA — default 3",
            key="input_ema_fast",
        )

    with sp_c3:
        ema_slow = st.number_input(
            "🐢 Slow EMA Period",
            min_value=2, max_value=200,
            value=int(st.session_state.get("ema_slow", 8)),
            step=1,
            help="Slower EMA — default 8",
            key="input_ema_slow",
        )

    with sp_c4:
        bar_count = st.number_input(
            "📊 Candles to Fetch",
            min_value=100, max_value=1500,
            value=int(st.session_state.get("bar_count", 300)),
            step=50,
            help="Number of historical candles to load (min 300 recommended)",
            key="input_bar_count",
        )

    st.markdown("---")
    filt_c1, filt_c2, filt_c3, filt_c4 = st.columns([1, 2.5, 1, 2.5])
    with filt_c1:
        use_vol_filter = st.toggle(
            "Volume Filter",
            value=bool(st.session_state.get("use_vol_filter", True)),
            help="When ON, signals require volume > 21-period volume MA",
            key="input_vol_filter",
        )
    with filt_c2:
        st.markdown(
            '<div style="margin-top:8px; font-size:0.82rem; color:#64748b;">'
            'Require candle volume > 21-bar MA. '
            'Filters weak-volume breakouts.</div>',
            unsafe_allow_html=True
        )
    with filt_c3:
        use_atr_filter = st.toggle(
            "ATR Filter",
            value=bool(st.session_state.get("use_atr_filter", True)),
            help="When ON, signals require ATR slope > 0 (expanding volatility / breakout energy)",
            key="input_atr_filter",
        )
    with filt_c4:
        st.markdown(
            '<div style="margin-top:8px; font-size:0.82rem; color:#64748b;">'
            'Require ATR slope &gt; 0. Confirms expanding volatility on breakouts. '
            'Rejects false moves in choppy/exhausted markets.</div>',
            unsafe_allow_html=True
        )

    st.markdown('</div>', unsafe_allow_html=True)


    # ══════════════════════════════════════════════════════════════════════════════
    # Section 4 — Execution Settings
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🚀 Execution Settings</div>', unsafe_allow_html=True)

    exec_c1, exec_c2, exec_c3 = st.columns(3)
    
    # ── Auto-fetch from Dhan API if credentials exist ──
    auto_capital = int(st.session_state.get("capital", 100000))
    auto_leverage = float(st.session_state.get("leverage", 1.0))
    capital_source = "manual"
    leverage_source = "manual"
    
    if current_source == "Dhan":
        _cid = st.session_state.get("dhan_client_id", "")
        _tok = st.session_state.get("dhan_api_key", "")
        _sid = st.session_state.get("security_id", "")
        _exch = st.session_state.get("exchange_segment", "MCX_COMM")
        
        if _cid and _tok:
            from core.risk_manager import RiskManager
            
            # Fetch available balance
            if "dhan_live_capital" not in st.session_state:
                try:
                    fund_info = RiskManager.fetch_fund_limits(_cid, _tok)
                    if fund_info and fund_info.get("availabelBalance") is not None:
                        bal = str(fund_info["availabelBalance"]).upper().replace('X','').strip()
                        st.session_state["dhan_live_capital"] = int(float(bal))
                    else:
                        st.session_state["dhan_live_capital"] = None
                except Exception:
                    st.session_state["dhan_live_capital"] = None
            
            if st.session_state.get("dhan_live_capital") is not None:
                auto_capital = st.session_state["dhan_live_capital"]
                capital_source = "dhan"
            
            # Fetch leverage for this symbol
            if "dhan_live_leverage" not in st.session_state and _sid:
                try:
                    margin_info = RiskManager.fetch_live_margin_info(
                        client_id=_cid, access_token=_tok,
                        security_id=_sid, exchange_segment=_exch,
                        transaction_type="BUY", quantity=1, price=0.0
                    )
                    if margin_info and margin_info.get("leverage"):
                        lev_str = str(margin_info["leverage"]).upper().replace('X','').strip()
                        st.session_state["dhan_live_leverage"] = float(lev_str)
                    else:
                        st.session_state["dhan_live_leverage"] = None
                except Exception:
                    st.session_state["dhan_live_leverage"] = None
            
            if st.session_state.get("dhan_live_leverage") is not None:
                auto_leverage = st.session_state["dhan_live_leverage"]
                leverage_source = "dhan"
    
    with exec_c1:
        capital = st.number_input(
            "💰 Capital (₹)" + (" 🟢" if capital_source == "dhan" else ""),
            min_value=0, max_value=100_000_000,
            value=max(0, min(100_000_000, int(auto_capital))),
            step=10000,
            help="Auto-fetched from Dhan API" if capital_source == "dhan" else "Manual input — connect Dhan to auto-fetch",
            key="input_capital",
        )
    with exec_c2:
        leverage = st.number_input(
            "📈 Leverage" + (" 🟢" if leverage_source == "dhan" else ""),
            min_value=1.0, max_value=500.0,
            value=float(max(1.0, min(500.0, float(auto_leverage)))),
            step=0.1,
            format="%.1f",
            help="Auto-fetched from Dhan Margin API" if leverage_source == "dhan" else "Manual input — connect Dhan to auto-fetch",
            key="input_leverage",
        )
    with exec_c3:
        exec_mode_opts = ["Dhan Realtime", "MetaTrader5", "JSON Only"]
        cur_exec_mode = st.session_state.get("execution_mode", "JSON Only")
        execution_mode = st.selectbox(
            "⚡ Execution Mode",
            options=exec_mode_opts,
            index=exec_mode_opts.index(cur_exec_mode) if cur_exec_mode in exec_mode_opts else 2,
            help="Where to route trade orders after signal generation",
            key="input_execution_mode",
        )
    
    # Show live data badge
    if capital_source == "dhan" or leverage_source == "dhan":
        parts = []
        if capital_source == "dhan":
            parts.append(f"Capital: ₹{auto_capital:,}")
        if leverage_source == "dhan":
            parts.append(f"Leverage: {auto_leverage:.1f}x")
        st.markdown(f"""
        <div style="margin-top:8px; padding:8px 14px; background:rgba(34,197,94,0.08);
             border:1px solid rgba(34,197,94,0.25); border-radius:8px; font-size:0.78rem; color:#22c55e;">
        🟢 <b>LIVE FROM DHAN</b> — {' | '.join(parts)}
        </div>
        """, unsafe_allow_html=True)
    
    # Contextual warnings based on execution mode
    if execution_mode == "Dhan Realtime":
        st.markdown("""
        <div style="margin-top:12px; padding: 12px 16px; background:rgba(239,68,68,0.08);
             border:1px solid rgba(239,68,68,0.25); border-radius:10px; font-size:0.82rem; color:#f87171;">
        🔴 <b>DHAN REALTIME</b> — Real broker orders will be placed via Dhan API.
        Ensure your Dhan credentials and capital are correctly configured.
        </div>
        """, unsafe_allow_html=True)
    elif execution_mode == "MetaTrader5":
        st.markdown("""
        <div style="margin-top:12px; padding: 12px 16px; background:rgba(251,191,36,0.08);
             border:1px solid rgba(251,191,36,0.25); border-radius:10px; font-size:0.82rem; color:#fbbf24;">
        🟡 <b>METATRADER5</b> — Orders will be routed to MT5 bridge (requires MT5 setup).
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="margin-top:12px; padding: 12px 16px; background:rgba(56,189,248,0.08);
             border:1px solid rgba(56,189,248,0.25); border-radius:10px; font-size:0.82rem; color:#38bdf8;">
        📄 <b>JSON ONLY</b> — Signals saved to data/signals.json. No live orders placed.
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════════
    # Notification Settings
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="settings-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔔 Notification Channels</div>', unsafe_allow_html=True)
    st.markdown("<p style='font-size:0.85rem; color:#94a3b8; margin-top:-8px;'>Configure API keys and addresses for LTS broadcasts.</p>", unsafe_allow_html=True)
    
    notif_c1, notif_c2 = st.columns(2)
    with notif_c1:
        st.markdown("**Telegram (LTS Broadcast)**")
        telegram_bot_token = st.text_input(
            "Bot Token",
            value=st.session_state.get("telegram_bot_token", ""),
            type="password",
            key="input_telegram_bot_token"
        )
        telegram_chat_id = st.text_input(
            "Chat ID",
            value=st.session_state.get("telegram_chat_id", ""),
            key="input_telegram_chat_id"
        )
        
    with notif_c2:
        st.markdown("**Gmail SMTP (LTS Broadcast)**")
        gmail_sender = st.text_input(
            "Sender Email",
            value=st.session_state.get("gmail_sender", ""),
            key="input_gmail_sender"
        )
        gmail_app_password = st.text_input(
            "App Password",
            value=st.session_state.get("gmail_app_password", ""),
            type="password",
            help="Generate an App Password from your Google Account Security settings.",
            key="input_gmail_app_password"
        )
        gmail_receiver = st.text_input(
            "Receiver Email",
            value=st.session_state.get("gmail_receiver", ""),
            key="input_gmail_receiver"
        )
    st.markdown('</div>', unsafe_allow_html=True)


    # ══════════════════════════════════════════════════════════════════════════════
    # Save Button
    # ══════════════════════════════════════════════════════════════════════════════
    save_c1, save_c2, save_c3 = st.columns([1.5, 2, 1.5])
    with save_c2:
        st.markdown('<div class="save-btn-container">', unsafe_allow_html=True)
        save_clicked = st.form_submit_button("💾  Save Preferences", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if save_clicked:
        # Validate EMA ordering
        if st.session_state.input_ema_fast >= st.session_state.input_ema_slow:
            st.error("⚠️ Fast EMA period must be strictly less than Slow EMA period.")
        else:
            new_prefs = {
                "dhan_client_id":     st.session_state.input_client_id.strip() if current_source == "Dhan" else st.session_state.get("dhan_client_id", ""),
                "dhan_pin":           st.session_state.input_dhan_pin.strip() if current_source == "Dhan" else st.session_state.get("dhan_pin", ""),
                "totp_secret":        st.session_state.input_totp_secret.strip() if current_source == "Dhan" else st.session_state.get("totp_secret", ""),
                "dhan_api_key":       st.session_state.input_api_key.strip() if current_source == "Dhan" else st.session_state.get("dhan_api_key", ""),
                "trading_symbol":     st.session_state.input_preset if current_source == "Dhan" else st.session_state.input_yf_fallback.strip(),
                "security_id":        st.session_state.input_security_id.strip() if current_source == "Dhan" else "",
                "exchange_segment":   st.session_state.input_exchange_segment if current_source == "Dhan" else "",
                "instrument_type":    st.session_state.input_instrument_type if current_source == "Dhan" else "",
                "timeframe":          st.session_state.input_timeframe,
                "ema_fast":           int(st.session_state.input_ema_fast),
                "ema_slow":           int(st.session_state.input_ema_slow),
                "use_vol_filter":     bool(st.session_state.input_vol_filter),
                "use_atr_filter":     bool(st.session_state.input_atr_filter),
                "capital":            int(st.session_state.input_capital),
                "leverage":           int(st.session_state.input_leverage),
                "bar_count":          int(st.session_state.input_bar_count),
                "yf_fallback_symbol": st.session_state.input_yf_fallback.strip() if current_source == "YFinance" else st.session_state.get("yf_fallback_symbol", "GC=F"),
                "data_source":        current_source,
                "execution_mode":     st.session_state.input_execution_mode,
                "telegram_bot_token": st.session_state.input_telegram_bot_token.strip(),
                "telegram_chat_id":   st.session_state.input_telegram_chat_id.strip(),
                "gmail_sender":       st.session_state.input_gmail_sender.strip(),
                "gmail_app_password": st.session_state.input_gmail_app_password.strip(),
                "gmail_receiver":     st.session_state.input_gmail_receiver.strip(),
            }
            _apply_to_session(new_prefs)
            _save_prefs(new_prefs)

            st.markdown("""
            <div class="success-pill" style="margin:12px auto; display:flex; justify-content:center;">
                ✅ Preferences saved successfully
            </div>
            """, unsafe_allow_html=True)
            st.success("Settings saved! Navigate to 📈 Live Chart to see them in action.")


# ── Current config preview ────────────────────────────────────────────────────
with st.expander("👁️ Current Active Configuration", expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"""
| Setting | Value |
|---|---|
| Client ID | `{"*****" if st.session_state.get('dhan_client_id') else '(not set)'}` |
| API Key | `{"*****" + st.session_state.get('dhan_api_key','')[-4:] if st.session_state.get('dhan_api_key') else '(not set)'}` |
| Symbol | `{st.session_state.get('trading_symbol', '—')}` |
| Security ID | `{st.session_state.get('security_id', '—')}` |
| Exchange | `{st.session_state.get('exchange_segment', '—')}` |
""")
    with col_b:
        st.markdown(f"""
| Setting | Value |
|---|---|
| Timeframe | `{st.session_state.get('timeframe', '—')}` |
| Fast EMA | `{st.session_state.get('ema_fast', '—')}` |
| Slow EMA | `{st.session_state.get('ema_slow', '—')}` |
| Vol Filter | `{st.session_state.get('use_vol_filter', '—')}` |
| Trade Volume | `{st.session_state.get('trade_volume', '—')} lots` |
| Candles | `{st.session_state.get('bar_count', '—')}` |
""")