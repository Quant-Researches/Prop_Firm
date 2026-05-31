"""
core/scheduler_helper.py
========================
Automatic schedule generator — FTMO server time (Europe/Helsinki).

Schedule slot times = MT5 candle CLOSE times (when a new bar opens and the
previous bar is complete).

Session windows (user-confirmed FTMO boundaries):
  Commodity (XAUUSD, XAGUSD, metals, oil, indices): Mon–Fri 01:05–23:50 FTMO
  Forex (all other pairs — DEFAULT):                 Mon–Fri 00:05–23:55 FTMO

Candle close alignment
-----------------------
All MT5 candles are midnight-aligned (multiples of the TF interval from 00:00).
Formula:  first_close = ceil(session_start / step) * step
          last_close  = floor(session_end   / step) * step

Special cases
-------------
1m : session_open is the candle OPEN (not CLOSE).
     first 1m close = session_open + 1 min.
1d : D1 bar closes at 00:00 FTMO midnight.  Pipeline fires at session open
     (01:05 commodity / 00:05 forex) — the earliest opportunity to act on the
     completed bar.  D1 slots are scheduled on Tue–Fri (Monday's bar closed
     Tue 00:00, etc.).
"""
from __future__ import annotations

import json
import logging
import math
import re
import uuid
from datetime import datetime
from pathlib import Path

from core.ftmo_time import now_ftmo

logger = logging.getLogger("SchedulerHelper")

SCHEDULES_FILE = Path("schedules.json")

# ── Supported timeframes (must match Settings page selectbox) ─────────────────
TF_MINUTES: dict[str, int] = {
    "1m":  1,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1h":  60,
    "4h":  240,
    "1d":  1440,
}

SUPPORTED_TIMEFRAMES: frozenset[str] = frozenset(TF_MINUTES)

# ── Session windows ───────────────────────────────────────────────────────────
#
#  start_min / end_min = minutes from FTMO midnight.
#  end_min is the LAST minute where a bar-close can fall inside the session.
#    Commodity: 01:05–23:50  → start=65,  end=1430
#    Forex:     00:05–23:55  → start=5,   end=1435

_SYMBOL_SESSION: dict[str, dict] = {
    # ── Precious metals ──────────────────────────────────────────────────────
    "XAUUSD": {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "XAGUSD": {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "GOLD":   {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "SILVER": {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    # ── Energy ───────────────────────────────────────────────────────────────
    "USOIL":  {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "UKOIL":  {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "WTIUSD": {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "BCOUSD": {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    # ── Major indices ─────────────────────────────────────────────────────────
    "US30":   {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "US100":  {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "US500":  {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "GER40":  {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    "UK100":  {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"},
    # ── Forex (all other pairs fall through to DEFAULT) ───────────────────────
    "DEFAULT": {"start_min": 5,  "end_min": 1435, "label": "00:05–23:55"},
}

# Regex for broker-appended suffixes: XAUUSD.pro → XAUUSD
_BROKER_SUFFIX_RE = re.compile(
    r"\.(cash|i|pro|m|ecn|raw|stp|std|ndd|lev|fix|zero|prime|mini|micro)$",
    re.IGNORECASE,
)


def _session_for_symbol(symbol: str) -> dict:
    """Return the session config dict for *symbol*, stripping broker suffixes."""
    key = _BROKER_SUFFIX_RE.sub("", symbol.upper())
    for sym_key, cfg in _SYMBOL_SESSION.items():
        if sym_key == "DEFAULT":
            continue
        if sym_key in key or key in sym_key:
            return cfg
    return _SYMBOL_SESSION["DEFAULT"]


def _min_to_hhmm(total_min: int) -> str:
    return f"{total_min // 60:02d}:{total_min % 60:02d}"


# ── Core calculation ──────────────────────────────────────────────────────────

def candle_close_times_ftmo(symbol: str, timeframe_str: str) -> list[str]:
    """
    Return sorted list of HH:MM strings (FTMO Helsinki) when MT5 candles CLOSE
    for this symbol and timeframe, within the instrument's session window.

    All closes are midnight-aligned (standard MT5 behaviour):
        first_close = ceil(session_start / step) * step
        last_close  = floor(session_end   / step) * step

    Special handling
    ----------------
    1m  : first close = session_start + 1  (session_start is a candle OPEN)
    1d  : returns [session_open_time] — analysis trigger, not a bar-close time
    4h  : uses midnight anchor (00:00, 04:00, 08:00 …) — corrected from old 02:00
    1h  : first close computed by formula, not hardcoded to 02:00

    Raises
    ------
    ValueError
        If *timeframe_str* is not in SUPPORTED_TIMEFRAMES.
    """
    if timeframe_str not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe '{timeframe_str}'. "
            f"Supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )

    step      = TF_MINUTES[timeframe_str]
    sess      = _session_for_symbol(symbol)
    start_min = sess["start_min"]
    end_min   = sess["end_min"]
    times: list[str] = []

    # ── D1 ────────────────────────────────────────────────────────────────────
    # The D1 bar closes at 00:00 FTMO midnight.  We fire at session open, which
    # is the first opportunity to analyse the completed bar each trading day.
    # This is an analysis TRIGGER time, not a literal bar-close time.
    if step >= 1440:
        times.append(_min_to_hhmm(start_min))   # 01:05 (commodity) | 00:05 (forex)
        return times

    # ── Intraday: unified midnight-aligned ceil formula ───────────────────────
    #
    # first_close = ceil(start_min / step) * step
    #
    # 1m guard: when start_min is an exact multiple of step (it always is for
    #   step==1), ceil gives start_min itself.  But start_min is the candle OPEN,
    #   not its CLOSE.  Advance one step so we report the first genuine close.
    first = math.ceil(start_min / step) * step
    if step == 1 and first == start_min:
        first += step   # 65 → 66 = 01:06 (XAUUSD) | 5 → 6 = 00:06 (forex)

    last  = (end_min // step) * step     # floor → last complete close in session

    tmin = first
    while tmin <= last:
        times.append(_min_to_hhmm(tmin))
        tmin += step

    return times


def generate_ftmo_schedule(symbol: str, timeframe_str: str) -> list[dict]:
    """
    Build Mon–Fri (or Tue–Fri for D1) schedule rows: one row per candle close.
    """
    step     = TF_MINUTES.get(timeframe_str, 60)
    is_daily = step >= 1440

    # D1: Monday's bar closes Tuesday 00:00 → schedule Tue–Fri.
    # (Friday's bar closes Saturday 00:00; omit Saturday weekend firing.)
    active_days = (
        ["Tuesday", "Wednesday", "Thursday", "Friday"]
        if is_daily
        else ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    )

    close_times  = candle_close_times_ftmo(symbol, timeframe_str)
    sess         = _session_for_symbol(symbol)
    new_schedules: list[dict] = []
    created = now_ftmo().isoformat()

    for day in active_days:
        for time_str in close_times:
            new_schedules.append({
                "id":             f"SCH_{day}_{time_str.replace(':', '')}_{uuid.uuid4().hex[:6].upper()}",
                "day":            day,
                "time":           time_str,
                "enabled":        True,
                "created_at":     created,
                "last_run":       None,
                "pipeline_status": "pending",
                "symbol":         symbol.upper(),
                "timeframe":      timeframe_str,
                "candle_close_ftmo": True,
            })

    return new_schedules


def update_and_save_schedule(
    symbol: str,
    timeframe_str: str,
    prefs: dict | None = None,
) -> tuple[int, str]:
    """
    Replace schedules.json with FTMO-aligned candle-close slots.

    Returns
    -------
    (count, message)
        count   — number of slots written (0 on error)
        message — human-readable summary or error string
    """
    if timeframe_str not in SUPPORTED_TIMEFRAMES:
        err = f"Unknown timeframe '{timeframe_str}' — no schedule written."
        logger.error(err)
        return 0, err

    new_scheds = generate_ftmo_schedule(symbol, timeframe_str)
    sess       = _session_for_symbol(symbol)
    sample     = candle_close_times_ftmo(symbol, timeframe_str)
    preview    = ", ".join(sample[:4]) + ("…" if len(sample) > 4 else "")

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
        logger.warning("Could not log schedule event: %s", ex)

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
                    "Daemon uses sleep-to-next-close — schedules.json is for display only.",
                ],
                suggestions=[
                    "Confirm times match MT5 chart candle closes.",
                    "Keep python main.py running 24/5 during trading.",
                ],
                prefs=prefs,
                block_reason="Schedule update",
            )
        except Exception as notif_err:
            logger.warning("Schedule notification failed: %s", notif_err)

    return len(new_scheds), msg
