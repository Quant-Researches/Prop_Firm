"""
core/scheduler_helper.py
========================
Automatic schedule generator — FTMO server time (Europe/Helsinki).

Schedule slot times = MT5 candle CLOSE times (when a new bar opens and the
previous bar is complete). The background daemon (main.py) fires the pipeline
when FTMO clock matches day + time exactly.

XAUUSD / metals (FTMO): Mon–Fri 01:05–23:59 FTMO
Forex (default):       Mon–Fri 00:05–23:55 FTMO
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from core.ftmo_time import now_ftmo

logger = logging.getLogger("SchedulerHelper")

SCHEDULES_FILE = Path("schedules.json")

# Session start in minutes from midnight (FTMO server clock)
_SYMBOL_SESSION: dict[str, dict] = {
    "XAUUSD": {"start_min": 65, "end_min": 1439, "label": "01:05–23:59"},   # 01:05 open
    "XAGUSD": {"start_min": 65, "end_min": 1439, "label": "01:05–23:59"},
    "GOLD":   {"start_min": 65, "end_min": 1439, "label": "01:05–23:59"},
    "DEFAULT": {"start_min": 5, "end_min": 1435, "label": "00:05–23:55"},  # FX typical
}

TF_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def _session_for_symbol(symbol: str) -> dict:
    key = symbol.upper().replace(".CASH", "").replace(".I", "")
    for sym_key, cfg in _SYMBOL_SESSION.items():
        if sym_key in key or key in sym_key:
            return cfg
    return _SYMBOL_SESSION["DEFAULT"]


def _min_to_hhmm(total_min: int) -> str:
    return f"{total_min // 60:02d}:{total_min % 60:02d}"


def candle_close_times_ftmo(symbol: str, timeframe_str: str) -> list[str]:
    """
    Return sorted list of HH:MM times (FTMO) when candles CLOSE for this symbol/TF.

    Logic:
    - Sub-hourly (1m–30m): first close after session open, then every TF step.
      e.g. XAUUSD 5m → 01:05, 01:10, 01:15 …
    - 1h: H1 bars close on the hour; first close after 01:05 open is 02:00, then 03:00…23:00.
    - 4h: 02:00, 06:00, 10:00, 14:00, 18:00, 22:00 (within session).
    - 1d: 23:00 (end of FTMO day before daily break).
    """
    step = TF_MINUTES.get(timeframe_str, 60)
    sess = _session_for_symbol(symbol)
    start_min = sess["start_min"]
    end_min = sess["end_min"]
    times: list[str] = []

    if step >= 1440:
        times.append("23:00")
        return times

    if step == 240:
        # 4H — align to 02:00 anchor then every 4 hours
        for hour in range(2, 24, 4):
            tmin = hour * 60
            if start_min <= tmin <= end_min:
                times.append(_min_to_hhmm(tmin))
        return sorted(set(times))

    if step == 60:
        # 1H — close at top of each hour; first H1 after 01:05 open completes at 02:00
        for hour in range(2, 24):
            tmin = hour * 60
            if start_min <= tmin <= end_min:
                times.append(_min_to_hhmm(tmin))
        return times

    if step == 30:
        # 30m — :00 and :30 within session (first close >= session start)
        tmin = ((start_min + 29) // 30) * 30
        while tmin <= end_min:
            times.append(_min_to_hhmm(tmin))
            tmin += 30
        return times

    # 1m, 5m, 15m — from session open, every `step` minutes
    tmin = start_min
    while tmin <= end_min:
        times.append(_min_to_hhmm(tmin))
        tmin += step
    return times


def generate_ftmo_schedule(symbol: str, timeframe_str: str) -> list[dict]:
    """
    Build Mon–Fri schedule rows: one row per candle CLOSE (FTMO time).
    """
    active_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    close_times = candle_close_times_ftmo(symbol, timeframe_str)
    sess = _session_for_symbol(symbol)
    new_schedules: list[dict] = []
    created = now_ftmo().isoformat()

    for day in active_days:
        for time_str in close_times:
            new_schedules.append({
                "id": f"SCH_{day}_{time_str.replace(':', '')}_{uuid.uuid4().hex[:6].upper()}",
                "day": day,
                "time": time_str,
                "enabled": True,
                "created_at": created,
                "last_run": None,
                "pipeline_status": "pending",  # pending | completed
                "symbol": symbol.upper(),
                "timeframe": timeframe_str,
                "candle_close_ftmo": True,
            })

    return new_schedules


def update_and_save_schedule(symbol: str, timeframe_str: str, prefs: dict = None) -> tuple[int, str]:
    """
    Replace schedules.json with FTMO-aligned candle-close slots.
    Returns: (count, message)
    """
    new_scheds = generate_ftmo_schedule(symbol, timeframe_str)
    sess = _session_for_symbol(symbol)
    sample = candle_close_times_ftmo(symbol, timeframe_str)
    preview = ", ".join(sample[:4]) + ("…" if len(sample) > 4 else "")

    try:
        SCHEDULES_FILE.write_text(json.dumps(new_scheds, indent=2), encoding="utf-8")
        msg = (
            f"FTMO schedule for {symbol} ({timeframe_str}): {len(new_scheds)} slots. "
            f"Session {sess['label']} FTMO. "
            f"Candle closes e.g. {preview}"
        )
        logger.info(msg)
    except Exception as e:
        err_msg = f"Failed to save schedule: {e}"
        logger.error(err_msg)
        return 0, err_msg

    try:
        from core.storage import Storage
        Storage().log_event("info", msg)
    except Exception as ex:
        logger.warning("Could not log event: %s", ex)

    if prefs:
        try:
            from core.notifier import broadcast_risk_alert
            broadcast_risk_alert(
                alert_type="INFO",
                symbol=symbol,
                warnings=[
                    "SCHEDULE REGENERATED (FTMO CANDLE CLOSE TIMES)",
                    f"Symbol: {symbol} | Timeframe: {timeframe_str}",
                    f"Slots: {len(new_scheds)} (Mon–Fri)",
                    f"Session: {sess['label']} (FTMO / Helsinki)",
                    f"Example closes: {preview}",
                    "Run: python main.py (daemon) — Start Bot in dashboard does NOT start the scheduler.",
                ],
                suggestions=[
                    "Confirm times match MT5 chart (H1 closes on the hour).",
                    "Keep python main.py running 24/5 during trading.",
                ],
                prefs=prefs,
                block_reason="Schedule update",
            )
        except Exception as notif_err:
            logger.warning("Schedule notification failed: %s", notif_err)

    return len(new_scheds), msg
