"""
pages/2_📅_Scheduler.py — Trade Pulse Quants | Function Scheduler (Page 2)
===========================================================================
Enhanced scheduler:
  • Free-form time input (any HH:MM — no fixed slots)
  • Dynamic row management per day
  • Copy a full day's schedule to any other day(s)
Schedules persisted to schedules.json in the project root.
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime, timedelta, date
import random

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Scheduler — Trade Pulse Quants",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCHEDULES_FILE = Path(__file__).parent.parent / "schedules.json"

# ── CSS ────────────────────────────────────────────────────────────────────────
from Utilities.ui_components import load_css, render_sidebar, init_session_state
from core.ftmo_time import find_next_schedule, ftmo_date
load_css()
st.markdown("""
<style>
/* Day column card */
.day-card {
    background: linear-gradient(135deg, #0d1225, #111827);
    border: 1px solid #1e293b;
    border-radius: 14px; padding: 14px 12px; min-height: 200px;
    transition: border-color 0.25s;
}
.day-card:hover { border-color: #4f46e5; }
.day-header {
    font-size: 0.78rem; font-weight: 700; color: #818cf8;
    text-transform: uppercase; letter-spacing: 1.5px;
    margin-bottom: 10px; padding-bottom: 8px;
    border-bottom: 1px solid #1e293b;
    display: flex; justify-content: space-between; align-items: center;
}
.day-count {
    background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.3);
    border-radius: 12px; padding: 1px 8px; font-size: 0.65rem; color: #a5b4fc;
}

/* Chip inside day */
.sched-chip {
    background: linear-gradient(135deg, #1e1b4b, #1e293b);
    border: 1px solid #312e81;
    border-radius: 8px; padding: 6px 10px; margin-bottom: 6px;
    font-size: 0.72rem;
}
.chip-time { color: #38bdf8; font-family: 'JetBrains Mono',monospace; font-weight: 600; }
.chip-fn   { color: #c4b5fd; font-weight: 600; }
.chip-note { color: #475569; font-style: italic; }
.chip-enabled  { border-left: 3px solid #10b981; }
.chip-disabled { border-left: 3px solid #ef4444; opacity: 0.6; }
.chip-next {
    border: 1px solid #818cf8 !important;
    box-shadow: 0 0 15px rgba(129,140,248,0.25);
    background: linear-gradient(135deg, #1e1b4b, #2d2a70) !important;
    position: relative;
}
.next-badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background: #4f46e5;
    color: white;
    font-size: 0.55rem;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 6px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}

/* Copy panel */
.copy-panel {
    background: linear-gradient(135deg, #0f1629, #131f35);
    border: 1px solid #1e3a5f; border-radius: 14px; padding: 18px 20px;
}

/* Tag pills */
.tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; }
.tag-active   { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid #10b981; }
.tag-inactive { background: rgba(239,68,68,0.15);  color: #ef4444; border: 1px solid #ef4444; }
</style>
""", unsafe_allow_html=True)


# ── Data helpers ───────────────────────────────────────────────────────────────
def _load_schedules() -> list[dict]:
    if SCHEDULES_FILE.exists():
        try:
            raw = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
            # Deduplicate by ID — keeps last occurrence
            seen, deduped = set(), []
            for s in raw:
                if s.get("id") not in seen:
                    seen.add(s["id"])
                    deduped.append(s)
            return deduped
        except Exception:
            return []
    return []

def _save_schedules(schedules: list[dict]) -> None:
    SCHEDULES_FILE.write_text(json.dumps(schedules, indent=2), encoding="utf-8")

import uuid

def _new_id() -> str:
    return f"SCH_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

def _validate_time(hh: int, mm: int) -> tuple[bool, str]:
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return False, "Invalid time"
    return True, f"{hh:02d}:{mm:02d}"

def _get_next_schedule_id(schedules: list[dict]) -> str:
    """Find the ID of the next schedule to fire, using FTMO server time (Europe/Helsinki)."""
    nxt, _ = find_next_schedule(schedules, enabled_only=True)
    return nxt["id"] if nxt else None


# ── Available functions ────────────────────────────────────────────────────────
AVAILABLE_FUNCTIONS = {
    "data_feed":    ["data_feed.connect", "data_feed.disconnect", "data_feed.stream"],
    "strategy":     ["strategy.on_market_event"],
    "risk_manager": ["risk_manager.evaluate", "risk_manager.update_capital"],
    "oms":          ["oms.submit", "oms.cancel", "oms.modify", "oms.status"],
    "execution":    ["execution.execute", "execution.set_mode"],
    "portfolio":    ["portfolio.on_fill", "portfolio.mark_to_market", "portfolio.get_summary"],
    "storage":      ["storage.save_trade", "storage.save_order", "storage.save_pnl_snapshot",
                     "storage.load_trades", "storage.load_pnl_history"],
    "system":       ["system.start_bot", "system.stop_bot", "system.restart_bot",
                     "system.export_report", "system.send_alert"],
}
ALL_FUNCTIONS = [fn for fns in AVAILABLE_FUNCTIONS.values() for fn in fns]
DAYS      = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SHORT = ["Mon",    "Tue",     "Wed",       "Thu",      "Fri",    "Sat",       "Sun"]


# ── Session state init ─────────────────────────────────────────────────────────
if "schedules" not in st.session_state:
    st.session_state.schedules = _load_schedules()

# Get the soonest upcoming schedule ID
next_sched_id = _get_next_schedule_id(st.session_state.schedules)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📅 Scheduler")
    st.divider()

    total        = len(st.session_state.schedules)
    active_count = sum(1 for s in st.session_state.schedules if s.get("enabled", True))
    st.metric("Total Schedules", total)
    st.metric("Active", active_count)
    st.metric("Inactive", total - active_count)

    st.markdown("---")
    if st.button("🔄 Reload from file", use_container_width=True):
        st.session_state.schedules = _load_schedules()
        st.rerun()
    if st.button("💾 Save to file", use_container_width=True):
        _save_schedules(st.session_state.schedules)
        st.toast("✅ Schedules saved!", icon="💾")
    if st.button("🗑 Clear all schedules", use_container_width=True, type="secondary"):
        st.session_state.schedules = []
        _save_schedules([])
        st.rerun()

    st.markdown("---")
    st.caption("Trade Pulse Quants v1.0 · Scheduler")


# ── Header ─────────────────────────────────────────────────────────────────────
total        = len(st.session_state.schedules)
active_count = sum(1 for s in st.session_state.schedules if s.get("enabled", True))

st.markdown(f"""
<div class="tpq-header">
    <div>
        <div class="tpq-title">📅 Function Scheduler</div>
        <div class="tpq-subtitle">Free-form time entry · per-day rows · copy across days</div>
    </div>
    <div style="display:flex;gap:12px;">
        <div class="tpq-badge">
            <div class="tpq-badge-num">{total}</div>
            <div class="tpq-badge-lbl">Total</div>
        </div>
        <div class="tpq-badge">
            <div class="tpq-badge-num" style="color:#10b981">{active_count}</div>
            <div class="tpq-badge-lbl">Active</div>
        </div>
        <div class="tpq-badge">
            <div class="tpq-badge-num" style="color:#ef4444">{total - active_count}</div>
            <div class="tpq-badge-lbl">Paused</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Live Countdown Panel ───────────────────────────────────────────────────────
try:
    from core.candle_timer import compute_next_candle_close, session_info
    from core.ftmo_time import now_ftmo as _now_ftmo

    _symbol = st.session_state.get("trading_symbol", "XAUUSD")
    _tf     = st.session_state.get("timeframe", "1h")
    _now    = _now_ftmo()
    _sess   = session_info(_symbol)
    _next_dt, _sleep_sec = compute_next_candle_close(_symbol, _tf, _now)

    _hh  = int(_sleep_sec // 3600)
    _mm  = int((_sleep_sec % 3600) // 60)
    _ss  = int(_sleep_sec % 60)
    _day_label = _next_dt.strftime("%A")

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1e1b4b 0%,#0d1225 100%);
                border:1px solid #4f46e5;border-radius:16px;padding:20px 28px;
                margin-bottom:20px;display:flex;justify-content:space-between;
                align-items:center;gap:24px;flex-wrap:wrap;">
        <div>
            <div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;
                        letter-spacing:2px;margin-bottom:4px;">NEXT CANDLE CLOSE</div>
            <div style="font-size:1.5rem;font-weight:800;color:#38bdf8;
                        font-family:'JetBrains Mono',monospace;letter-spacing:1px;">
                {_day_label} {_next_dt.strftime('%H:%M')}
                <span style="font-size:0.85rem;color:#64748b;font-weight:400;">FTMO</span>
            </div>
        </div>
        <div style="text-align:center;">
            <div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;
                        letter-spacing:2px;margin-bottom:4px;">DAEMON SLEEPS FOR</div>
            <div style="font-size:1.5rem;font-weight:800;color:#a78bfa;
                        font-family:'JetBrains Mono',monospace;">
                {_hh:02d}h {_mm:02d}m {_ss:02d}s
            </div>
        </div>
        <div style="text-align:center;">
            <div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;
                        letter-spacing:2px;margin-bottom:4px;">INSTRUMENT · INTERVAL</div>
            <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;">
                {_symbol} · {_tf}
            </div>
            <div style="font-size:0.72rem;color:#475569;margin-top:2px;">
                Session: {_sess['label']} FTMO
            </div>
        </div>
        <div style="text-align:right;">
            <div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;
                        letter-spacing:2px;margin-bottom:4px;">SCHEDULER</div>
            <div style="font-size:0.9rem;font-weight:700;color:#34d399;">
                ● SLEEP-TO-CLOSE ACTIVE
            </div>
            <div style="font-size:0.65rem;color:#475569;margin-top:2px;">
                No polling · Zero CPU idle
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
except Exception:
    pass   # candle_timer not yet available — silently skip the panel

st.info("🕒 **TIMEZONE:** All times are **FTMO MT5 Server Time (Europe/Helsinki)**. "
        "The daemon sleeps **exactly** until each candle closes — no 10-second polling. "
        "Use the panel above to see when the next pipeline tick will fire.")




# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4.5 — AUTOMATIC FTMO ACTIVE HOURS GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">⚡ Automatic FTMO Active Hours Generator</div>', unsafe_allow_html=True)

with st.container():
    st.markdown("""
    <div style="background:linear-gradient(135deg, #1e1b4b 0%, #0d1225 100%); border:1px solid #4f46e5; border-radius:14px; padding:20px; margin-bottom:20px;">
        <div style="font-weight:700; color:#818cf8; font-size:1rem; margin-bottom:8px;">🔥 Active Hours Auto-Scheduler</div>
        <div style="font-size:0.8rem; color:#94a3b8; line-height:1.6; margin-bottom:16px;">
            Automatically configure the entire weekly schedule to align with standard <strong>FTMO trading session hours</strong> for your active trading instrument. 
            All other custom schedules will be completely removed, and a new optimal grid aligned with your settings will be loaded.
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col_g1, col_g2, col_g3 = st.columns([1.5, 1.5, 1.2])
    
    active_symbol = st.session_state.get("trading_symbol", "XAUUSD")
    active_timeframe = st.session_state.get("timeframe", "5m")
    
    with col_g1:
        st.markdown(f"<div style='font-size:0.75rem;color:#64748b;'>Trading Instrument</div><div style='font-weight:600;font-size:1.1rem;color:#f8fafc;padding:4px 0;'>💎 {active_symbol}</div>", unsafe_allow_html=True)
    with col_g2:
        st.markdown(f"<div style='font-size:0.75rem;color:#64748b;'>Selected Interval</div><div style='font-weight:600;font-size:1.1rem;color:#38bdf8;padding:4px 0;'>⏱️ {active_timeframe}</div>", unsafe_allow_html=True)
    with col_g3:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        generate_btn = st.button("🔥 Auto-Generate Grid", use_container_width=True, type="primary")
        
    if generate_btn:
        from core.scheduler_helper import update_and_save_schedule
        import json
        from pathlib import Path
        p_file = Path("config/user_prefs.json")
        prefs_payload = json.loads(p_file.read_text(encoding="utf-8")) if p_file.exists() else {}
        
        with st.spinner("⚡ Rebuilding FTMO schedule..."):
            count, msg = update_and_save_schedule(active_symbol, active_timeframe, prefs=prefs_payload)
            if count > 0:
                st.session_state.schedules = _load_schedules()
                st.toast(f"✅ Generated {count} active hours slots for {active_symbol}!", icon="⚡")
                st.success(f"🎉 **Success!** Automatically generated {count} FTMO-compliant trading slots aligned to standard market sessions. All previous schedules have been cleared.")
                st.rerun()
            else:
                st.error(f"❌ Failed to generate schedule: {msg}")

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — ADD NEW SCHEDULE (free-form time)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">➕ Add New Schedule</div>', unsafe_allow_html=True)

with st.container():
    a1, a2, a3, a4 = st.columns([1.6, 0.7, 0.7, 1.0])

    with a1:
        sel_day = st.selectbox("📆 Day", DAYS, key="add_day")

    with a2:
        hh = st.number_input("HH", min_value=0, max_value=23, value=9,
                             step=1, key="add_hh", label_visibility="visible")
    with a3:
        mm = st.number_input("MM", min_value=0, max_value=59, value=15,
                             step=5, key="add_mm", label_visibility="visible")

    with a4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        add_clicked = st.button("✅ Add Schedule", use_container_width=True, key="btn_add")

    if add_clicked:
        ok, time_str = _validate_time(int(hh), int(mm))
        if not ok:
            st.error("⚠️ Invalid time.")
        else:
            exists = any(
                s["day"] == sel_day and s["time"] == time_str
                for s in st.session_state.schedules
            )
            if exists:
                st.warning(f"⚠️ **{sel_day} {time_str}** already exists.")
            else:
                st.session_state.schedules.append({
                    "id":         _new_id(),
                    "day":        sel_day,
                    "time":       time_str,
                    "enabled":    True,
                    "created_at": datetime.now().isoformat(),
                    "last_run":   None,
                })
                _save_schedules(st.session_state.schedules)
                st.toast(f"✅ Added **{sel_day} {time_str}**", icon="📅")
                st.rerun()

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — COPY DAY PANEL
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">📋 Copy Day\'s Schedule</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="copy-panel">', unsafe_allow_html=True)

    # ── Row 1: FROM · preview · Copy Now (all on same baseline) ──────────────
    r1a, r1b, r1c = st.columns([1.3, 2.8, 1.1])

    with r1a:
        src_day = st.selectbox("📤 Copy FROM", DAYS, key="copy_src")

    src_scheds = [s for s in st.session_state.schedules if s["day"] == src_day]
    src_count  = len(src_scheds)

    with r1b:
        if src_scheds:
            preview = "  ·  ".join(
                s["time"]
                for s in sorted(src_scheds, key=lambda x: x["time"])[:10]
            )
            suffix = f"  …+{src_count - 10}" if src_count > 10 else ""
            st.markdown(
                f"<div style='background:#0d1829;border:1px solid #1e3a5f;border-radius:8px;"
                f"padding:9px 14px;font-size:0.75rem;font-family:JetBrains Mono,monospace;"
                f"color:#38bdf8;margin-top:26px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
                f"<span style='color:#475569;margin-right:8px'>{src_count} slot(s)</span>"
                f"{preview}{suffix}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='background:#0d1225;border:1px dashed #1e293b;border-radius:8px;"
                "padding:9px 14px;font-size:0.75rem;color:#334155;margin-top:26px'>"
                "No schedules on this day yet.</div>",
                unsafe_allow_html=True,
            )

    with r1c:
        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
        copy_clicked = st.button(
            "📋 Copy Now", use_container_width=True,
            key="btn_copy", disabled=not src_scheds,
        )

    # ── Row 2: TO multiselect (full width) ────────────────────────────────────
    target_days = st.multiselect(
        "📥 Copy TO — select target day(s)",
        [d for d in DAYS if d != src_day],
        key="copy_targets",
        placeholder="Pick one or more days…",
    )

    if copy_clicked and src_scheds and target_days:
        added = 0
        for tday in target_days:
            for s in src_scheds:
                already = any(
                    x["day"] == tday and x["time"] == s["time"]
                    for x in st.session_state.schedules
                )
                if not already:
                    st.session_state.schedules.append({
                        "id":         _new_id(),
                        "day":        tday,
                        "time":       s["time"],
                        "enabled":    s.get("enabled", True),
                        "created_at": datetime.now().isoformat(),
                        "last_run":   None,
                    })
                    added += 1
        _save_schedules(st.session_state.schedules)
        if added:
            st.toast(f"✅ Copied {added} slot(s) to {', '.join(target_days)}", icon="📋")
        else:
            st.toast("ℹ️ All slots already exist on target day(s).", icon="ℹ️")
        st.rerun()
    elif copy_clicked and not target_days:
        st.warning("⚠️ Please select at least one target day.")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PER-DAY CALENDAR (editable rows)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">🗓️ Weekly Schedule</div>', unsafe_allow_html=True)

# Compute the next upcoming date for each day name
from datetime import date, timedelta

def _next_date_for(day_name: str) -> date:
    """Return the soonest future date (today included) with the given weekday name, in FTMO timezone."""
    weekday_idx = {"Monday":0,"Tuesday":1,"Wednesday":2,"Thursday":3,
                   "Friday":4,"Saturday":5,"Sunday":6}
    today = ftmo_date()  # Use FTMO date, not local IST date
    target = weekday_idx[day_name]
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta)

day_dates = {day: _next_date_for(day) for day in DAYS}
today_name = date.today().strftime("%A")

day_cols = st.columns(7)

for col, day, short in zip(day_cols, DAYS, DAY_SHORT):
    day_scheds = sorted(
        [s for s in st.session_state.schedules if s["day"] == day],
        key=lambda x: x["time"],
    )
    d = day_dates[day]
    is_today   = (day == today_name)
    is_weekend = day in ("Saturday", "Sunday")

    # Header accent: purple for today, teal for weekend, default otherwise
    accent = "#6366f1" if is_today else ("#0891b2" if is_weekend else "#1e293b")
    lbl_color = "#a5b4fc" if is_today else ("#67e8f9" if is_weekend else "#818cf8")
    date_str = f"{d.day} {d.strftime('%b')}"  # Windows-safe (no %-d)

    today_badge = '<span style="font-size:0.6rem;color:#6366f1;margin-left:4px">TODAY</span>' if is_today else ""
    with col:
        st.markdown(
            f'<div class="day-header" style="border-bottom:2px solid {accent}">'
            f'<div>'
            f'<span style="color:{lbl_color};font-size:0.78rem;font-weight:700">{short}</span>'
            f'<span style="color:#64748b;font-size:0.68rem;margin-left:5px">{date_str}</span>'
            f'{today_badge}'
            f'</div>'
            f'<span class="day-count">{len(day_scheds)}</span></div>',
            unsafe_allow_html=True,
        )

        # ── Rows ──────────────────────────────────────────────────────────────
        for entry in day_scheds:
            enabled  = entry.get("enabled", True)
            is_next  = (entry["id"] == next_sched_id)
            
            chip_cls = "sched-chip chip-enabled" if enabled else "sched-chip chip-disabled"
            if is_next:
                chip_cls += " chip-next"
            
            next_badge = '<span class="next-badge">⚡ NEXT</span>' if is_next else ""

            st.markdown(
                f'<div class="{chip_cls}">'
                f'<span class="chip-time">{entry["time"]}</span>'
                f'{next_badge}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Inline action buttons (toggle | delete)
            ba, bb = st.columns(2)
            with ba:
                tog_lbl = "⏸" if enabled else "▶"
                if st.button(tog_lbl, key=f"cal_tog_{day}_{entry['id']}",
                             use_container_width=True, help="Pause / Resume"):
                    for s in st.session_state.schedules:
                        if s["id"] == entry["id"]:
                            s["enabled"] = not s.get("enabled", True)
                    _save_schedules(st.session_state.schedules)
                    st.rerun()
            with bb:
                if st.button("🗑", key=f"cal_del_{day}_{entry['id']}",
                             use_container_width=True, help="Delete"):
                    st.session_state.schedules = [
                        s for s in st.session_state.schedules if s["id"] != entry["id"]
                    ]
                    _save_schedules(st.session_state.schedules)
                    st.rerun()

        # ── Quick-add row inside the day column ───────────────────────────────
        with st.expander("＋ Add to this day", expanded=False):
            qhh = st.number_input("HH", 0, 23, 9,  step=1, key=f"qhh_{day}")
            qmm = st.number_input("MM", 0, 59, 15, step=5, key=f"qmm_{day}")
            if st.button("Add", key=f"qadd_{day}", use_container_width=True):
                ok, ts = _validate_time(int(qhh), int(qmm))
                if ok:
                    dup = any(
                        s["day"] == day and s["time"] == ts
                        for s in st.session_state.schedules
                    )
                    if not dup:
                        st.session_state.schedules.append({
                            "id":         _new_id(),
                            "day":        day,
                            "time":       ts,
                            "enabled":    True,
                            "created_at": datetime.now().isoformat(),
                            "last_run":   None,
                        })
                        _save_schedules(st.session_state.schedules)
                        st.rerun()
                    else:
                        st.warning("Already exists.")

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — FULL TABLE VIEW (sortable, all schedules)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">📋 All Scheduled Tasks</div>', unsafe_allow_html=True)

if not st.session_state.schedules:
    st.markdown("""
    <div style="background:#0d1225;border:1px dashed #1e293b;border-radius:12px;
                padding:40px;text-align:center;color:#475569;font-size:0.9rem;">
        📅 No schedules yet. Use the form above to add one.
    </div>
    """, unsafe_allow_html=True)
else:
    day_order = {d: i for i, d in enumerate(DAYS)}
    sorted_scheds = sorted(
        st.session_state.schedules,
        key=lambda s: (day_order.get(s["day"], 9), s["time"]),
    )

    hdr = st.columns([1.2, 1.0, 1.2, 0.8, 0.7, 0.7])
    labels = ["Day", "Time", "Created", "Status", "⏸/▶", "🗑"]
    for h, lbl in zip(hdr, labels):
        with h:
            st.markdown(
                f"<div style='font-size:0.68rem;text-transform:uppercase;letter-spacing:1.5px;"
                f"color:#334155;padding-bottom:6px;border-bottom:1px solid #1a2235;"
                f"font-weight:700'>{lbl}</div>",
                unsafe_allow_html=True,
            )

    for idx, entry in enumerate(sorted_scheds):
        c_day, c_time, c_created, c_stat, c_tog, c_del = st.columns(
            [1.2, 1.0, 1.2, 0.8, 0.7, 0.7]
        )
        enabled = entry.get("enabled", True)
        is_next = (entry["id"] == next_sched_id)
        
        row_style = "background:rgba(99,102,241,0.08);border-left:2px solid #818cf8;border-radius:6px;" if is_next else ""

        with c_day:
            st.markdown(
                f"<div style='padding:7px;font-weight:600;color:#818cf8;font-size:0.82rem;{row_style}'>"
                f"{entry['day'][:3]} {'⭐' if is_next else ''}</div>",
                unsafe_allow_html=True,
            )
        with c_time:
            st.markdown(
                f"<div style='padding:7px 0;font-family:JetBrains Mono,monospace;"
                f"color:#38bdf8;font-size:0.85rem;font-weight:600'>{entry['time']}</div>",
                unsafe_allow_html=True,
            )
        with c_created:
            created = entry.get("created_at", "")[:10] or "—"
            st.markdown(
                f"<div style='padding:7px 0;color:#475569;font-size:0.78rem'>{created}</div>",
                unsafe_allow_html=True,
            )
        with c_stat:
            tag_cls = "tag-active" if enabled else "tag-inactive"
            tag_txt = "Active" if enabled else "Off"
            st.markdown(
                f"<div style='padding:7px 0'><span class='tag {tag_cls}'>{tag_txt}</span></div>",
                unsafe_allow_html=True,
            )
        with c_tog:
            tog_icon = "⏸" if enabled else "▶"
            if st.button(tog_icon, key=f"tbl_tog_{entry['id']}", use_container_width=True,
                         help="Pause / Resume"):
                for s in st.session_state.schedules:
                    if s["id"] == entry["id"]:
                        s["enabled"] = not s.get("enabled", True)
                _save_schedules(st.session_state.schedules)
                st.rerun()
        with c_del:
            if st.button("🗑", key=f"tbl_del_{entry['id']}", use_container_width=True, help="Delete"):
                st.session_state.schedules = [
                    s for s in st.session_state.schedules if s["id"] != entry["id"]
                ]
                _save_schedules(st.session_state.schedules)
                st.rerun()

        if idx < len(sorted_scheds) - 1:
            st.markdown(
                "<hr style='border:none;border-top:1px solid #1a2235;margin:3px 0'>",
                unsafe_allow_html=True,
            )

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — QUICK PRESETS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">⚡ Quick Presets</div>', unsafe_allow_html=True)

PRESETS = {
    "🌅 Market Open": [
        {"day": d, "time": "09:15", "function": "data_feed.connect",        "note": "Connect at open"} for d in DAYS
    ] + [
        {"day": d, "time": "09:15", "function": "strategy.on_market_event", "note": "First signal"}    for d in DAYS
    ],
    "📊 Hourly Scan": [
        {"day": d, "time": t, "function": "strategy.on_market_event", "note": "Hourly"}
        for d in DAYS for t in ["10:00", "11:00", "12:00", "13:00", "14:00"]
    ],
    "💾 EOD Save": [
        {"day": d, "time": "15:30", "function": "storage.save_pnl_snapshot", "note": "End of day"} for d in DAYS
    ] + [
        {"day": d, "time": "15:30", "function": "data_feed.disconnect",      "note": "Disconnect"}    for d in DAYS
    ],
    "📧 Daily Report": [
        {"day": d, "time": "15:30", "function": "system.export_report", "note": "EOD report"} for d in DAYS
    ],
}

p_cols = st.columns(len(PRESETS))
for i, (label, entries) in enumerate(PRESETS.items()):
    with p_cols[i]:
        if st.button(label, use_container_width=True, key=f"preset_{i}"):
            added = 0
            for e in entries:
                already = any(
                    s["day"] == e["day"] and s["time"] == e["time"]
                    for s in st.session_state.schedules
                )
                if not already:
                    st.session_state.schedules.append({
                        "id":         _new_id(),
                        "day":        e["day"],
                        "time":       e["time"],
                        "enabled":    True,
                        "created_at": datetime.now().isoformat(),
                        "last_run":   None,
                    })
                    added += 1
            _save_schedules(st.session_state.schedules)
            if added:
                st.toast(f"✅ Added {added} slots from preset **{label}**", icon="⚡")
            else:
                st.toast("ℹ️ All preset slots already exist.", icon="ℹ️")
            st.rerun()

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — SUMMARY BY DAY
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.schedules:
    st.markdown('<div class="section-label">📈 Summary by Day</div>', unsafe_allow_html=True)
    s_cols = st.columns(7)
    for col, day, short in zip(s_cols, DAYS, DAY_SHORT):
        cnt = sum(1 for s in st.session_state.schedules if s["day"] == day and s.get("enabled", True))
        with col:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#111827,#1e293b);
                        border:1px solid #1e293b;border-radius:12px;
                        padding:16px;text-align:center;">
                <div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:1px">{short}</div>
                <div style="font-size:1.8rem;font-weight:700;color:#818cf8;margin:6px 0">{cnt}</div>
                <div style="font-size:0.72rem;color:#475569">active tasks</div>
            </div>
            """, unsafe_allow_html=True)
