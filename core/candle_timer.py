"""
core/candle_timer.py
====================
Precision sleep-timer for the scheduler daemon.

compute_next_candle_close(symbol, tf, now) → (next_close_dt, sleep_seconds)

Replaces the old 10-second polling + HH:MM string matching with a single,
exact arithmetic computation.  The daemon calls this, sleeps the returned
number of seconds, then fires the pipeline immediately upon waking.

Rules
-----
- All candle closes are aligned to FTMO (Europe/Helsinki) midnight 00:00,
  matching MT5 chart bar timestamps exactly.
- Only closes that fall within the instrument's configured session window
  are returned (Forex 00:05–23:55, Commodity 01:05–23:50).
- Weekends (Saturday / Sunday) are skipped — the computed target advances
  to Monday's first session close automatically.
- 1m special case: session open = candle OPEN, not CLOSE.  The first 1m
  close is therefore session_open + 1 minute.
- 1d: fires at session open each trading day (the D1 bar closed at 00:00;
  session open is the earliest opportunity to analyse the completed bar).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

# Lazy import to avoid circular imports at module load
# (ftmo_time imports nothing from candle_timer)
_FTMO_TZ = None


def _ftmo_tz():
    global _FTMO_TZ
    if _FTMO_TZ is None:
        from zoneinfo import ZoneInfo
        _FTMO_TZ = ZoneInfo("Europe/Helsinki")
    return _FTMO_TZ


def _now_ftmo() -> datetime:
    from core.ftmo_time import now_ftmo
    return now_ftmo()


# ── Supported timeframes (must match Settings page selectbox) ─────────────────
SUPPORTED_TF: frozenset[str] = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})

TF_MINUTES: dict[str, int] = {
    "1m":  1,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1h":  60,
    "4h":  240,
    "1d":  1440,
}


# ── Session windows (FTMO / Europe/Helsinki) ──────────────────────────────────
#
#   Commodity (XAUUSD, XAGUSD, metals, oil, major indices):
#       01:05 AM – 23:50  (start_min=65, end_min=1430)
#
#   Forex (all other pairs — DEFAULT):
#       00:05 AM – 23:55  (start_min=5,  end_min=1435)
#
# These are the user-confirmed FTMO session boundaries.
# end_min is the LAST minute at which a session close can fire:
#   e.g. end_min=1430 means the 23:50 bar-close is included, 23:51+ is not.

_COMMODITY_SYMBOLS = frozenset({
    "XAUUSD", "XAGUSD", "GOLD", "SILVER",
    "USOIL",  "UKOIL",  "WTIUSD", "BCOUSD",
    "US30",   "US100",  "US500",  "GER40",
    "UK100",  "FRA40",  "ESP35",  "JP225",
    "AUS200",
})

_BROKER_SUFFIXES = (
    ".cash", ".i", ".pro", ".m", ".ecn", ".raw",
    ".stp", ".std", ".ndd", ".lev", ".fix", ".zero",
    ".prime", ".mini", ".micro",
)

_SESSION_COMMODITY = {"start_min": 65,  "end_min": 1430, "label": "01:05–23:50"}
_SESSION_FOREX     = {"start_min": 5,   "end_min": 1435, "label": "00:05–23:55"}


def _session_for_symbol(symbol: str) -> dict:
    """Return the session dict for a given instrument symbol."""
    # Strip common broker suffixes (XAUUSD.pro → XAUUSD)
    key = symbol.upper()
    for sfx in _BROKER_SUFFIXES:
        if key.endswith(sfx.upper()):
            key = key[: -len(sfx)]
            break
    return _SESSION_COMMODITY if key in _COMMODITY_SYMBOLS else _SESSION_FOREX


# ── Public API ────────────────────────────────────────────────────────────────

def compute_next_candle_close(
    symbol: str,
    tf: str,
    now: datetime | None = None,
) -> tuple[datetime, float]:
    """
    Return *(next_close_dt, sleep_seconds)*.

    ``next_close_dt``
        Timezone-aware datetime (Europe/Helsinki) of the next MT5 candle close
        that falls **within** the instrument's trading session.  Always > *now*.

    ``sleep_seconds``
        Exact number of seconds from *now* until *next_close_dt*.  Minimum 0.5
        to prevent zero-sleep tight loops.

    Parameters
    ----------
    symbol : str
        Instrument symbol (e.g. ``"XAUUSD"``, ``"EURUSD"``, ``"XAUUSD.pro"``).
    tf : str
        Timeframe string — must be one of ``SUPPORTED_TF``.
    now : datetime, optional
        Reference time (tz-aware, Helsinki).  Defaults to ``now_ftmo()``.

    Raises
    ------
    ValueError
        If *tf* is not in ``SUPPORTED_TF``.
    """
    if tf not in SUPPORTED_TF:
        raise ValueError(
            f"Unsupported timeframe '{tf}'. "
            f"Supported: {sorted(SUPPORTED_TF)}"
        )

    now = now or _now_ftmo()
    step_min = TF_MINUTES[tf]
    step_sec = step_min * 60

    sess      = _session_for_symbol(symbol)
    start_sec = sess["start_min"] * 60   # e.g. 3900  (01:05) for commodity
    end_sec   = sess["end_min"]   * 60   # e.g. 85800 (23:50) for commodity

    # Seconds elapsed since FTMO midnight right now
    now_sec = now.hour * 3600 + now.minute * 60 + now.second

    # Midnight of the current FTMO day (tz-aware)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── D1: fire at session open — catches the bar that closed at 00:00 ──────
    if step_min >= 1440:
        if now_sec < start_sec:
            # Still before today's session open → fire today at session open
            candidate = today_midnight + timedelta(seconds=start_sec)
        else:
            # Already past today's session open → fire at tomorrow's session open
            candidate = today_midnight + timedelta(days=1, seconds=start_sec)
        candidate = _skip_weekend(candidate)
        return candidate, _sleep_sec(candidate, now)

    # ── Intraday: next midnight-aligned close that is within session ──────────
    #
    # +1 to now_sec ensures we don't re-fire if the loop wakes exactly on a
    # candle boundary (avoids the "just fired, compute next" ambiguity).
    raw_next = math.ceil((now_sec + 1) / step_sec) * step_sec

    # ── 1m special case: session open is a candle OPEN, not a CLOSE ──────────
    # For step==1, ceil(start_min/1)*1 = start_min exactly, but that minute
    # is when the first session candle OPENS.  Its close is start_min + 1.
    # Guard: if the computed first close equals the session open, advance one step.
    # (Verified by user: 5m/15m/30m/1h/4h do NOT need this adjustment.)
    if step_min == 1 and raw_next == start_sec:
        raw_next += step_sec   # 01:05 → 01:06  (commodity) | 00:05 → 00:06 (forex)

    if start_sec <= raw_next <= end_sec:
        # Happy path: within today's session
        candidate = today_midnight + timedelta(seconds=raw_next)

    elif raw_next < start_sec:
        # Before session opens today → jump to first session close today
        first_in_session = math.ceil(start_sec / step_sec) * step_sec
        if step_min == 1 and first_in_session == start_sec:
            first_in_session += step_sec
        candidate = today_midnight + timedelta(seconds=first_in_session)

    else:
        # Past session end today → jump to first session close tomorrow
        first_in_session = math.ceil(start_sec / step_sec) * step_sec
        if step_min == 1 and first_in_session == start_sec:
            first_in_session += step_sec
        candidate = today_midnight + timedelta(days=1, seconds=first_in_session)

    candidate = _skip_weekend(candidate)
    return candidate, _sleep_sec(candidate, now)


def session_info(symbol: str) -> dict:
    """Return the session window dict for *symbol* (label, start_min, end_min)."""
    return _session_for_symbol(symbol)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _skip_weekend(dt: datetime) -> datetime:
    """Advance Saturday → Monday (+2 days), Sunday → Monday (+1 day)."""
    wd = dt.weekday()
    if wd == 5:    # Saturday
        return dt + timedelta(days=2)
    if wd == 6:    # Sunday
        return dt + timedelta(days=1)
    return dt


def _sleep_sec(target: datetime, now: datetime) -> float:
    """Seconds from *now* to *target*; minimum 0.5 to prevent tight loops."""
    return max((target - now).total_seconds(), 0.5)
