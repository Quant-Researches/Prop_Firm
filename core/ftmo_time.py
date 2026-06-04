"""
core/ftmo_time.py — civil FTMO timezone helpers (Europe/Helsinki).

FTMO chart time = Europe/Helsinki (EET/EEST, GMT+2 / GMT+3 with DST).
Trading scheduler, candles, and bar picker use core.broker_clock (MT5-calibrated).

Daily account reset uses Europe/Prague (see main.py) — NOT for schedule slots.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# MT5 candle / schedule timezone (matches app.py FTMO clock)
FTMO_TZ = ZoneInfo("Europe/Helsinki")

# English day names — never use strftime("%A") (breaks on non-English Windows locales)
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

WEEKDAY_IDX = {name: i for i, name in enumerate(WEEKDAYS)}


def now_ftmo() -> datetime:
    """Civil FTMO time from OS clock. For trading, prefer broker_clock.broker_now()."""
    return datetime.now(FTMO_TZ)


def ftmo_day_name(dt: datetime | None = None) -> str:
    """English weekday name for FTMO time (matches schedules.json 'day' field)."""
    dt = dt or now_ftmo()
    return WEEKDAYS[dt.weekday()]


def ftmo_hhmm(dt: datetime | None = None) -> str:
    """HH:MM in FTMO time — matches schedules.json 'time' field."""
    dt = dt or now_ftmo()
    return dt.strftime("%H:%M")


def ftmo_date(dt: datetime | None = None) -> date:
    dt = dt or now_ftmo()
    return dt.date()


def ftmo_display(dt: datetime | None = None) -> str:
    """Human-readable FTMO timestamp for logs/UI."""
    dt = dt or now_ftmo()
    return dt.strftime("%A %d %b %Y %H:%M:%S") + " (FTMO / Helsinki)"


def parse_schedule_datetime(day_name: str, time_str: str, after: datetime | None = None) -> datetime:
    """
    Next occurrence of schedule slot (day + HH:MM) in FTMO timezone, >= after.
    """
    after = after or now_ftmo()
    if after.tzinfo is None:
        after = after.replace(tzinfo=FTMO_TZ)
    else:
        after = after.astimezone(FTMO_TZ)

    hh, mm = map(int, time_str.split(":"))
    target_wd = WEEKDAY_IDX[day_name]
    days_ahead = (target_wd - after.weekday()) % 7
    candidate = datetime(
        after.year,
        after.month,
        after.day,
        hh,
        mm,
        59,          # second=59 keeps the "⚡ NEXT" badge visible the full 60-second window.
        tzinfo=FTMO_TZ,
    ) + timedelta(days=days_ahead)

    if candidate < after:
        candidate += timedelta(days=7)
    return candidate


def find_next_schedule(
    schedules: list[dict],
    *,
    enabled_only: bool = True,
) -> tuple[dict | None, datetime | None]:
    """
    Return (schedule_dict, next_ftmo_datetime) for the soonest enabled slot.
    All comparisons use FTMO time — not local PC clock.
    """
    now = now_ftmo()
    best: dict | None = None
    best_dt: datetime | None = None

    for s in schedules:
        if enabled_only and not s.get("enabled", True):
            continue
        day = s.get("day")
        t = s.get("time")
        if not day or not t or day not in WEEKDAY_IDX:
            continue
        try:
            nxt = parse_schedule_datetime(day, t, now)
        except (ValueError, KeyError):
            continue
        if best_dt is None or nxt < best_dt:
            best_dt = nxt
            best = s

    return best, best_dt


def schedule_matches_now(schedule: dict, dt: datetime | None = None) -> bool:
    """True if this slot should fire on the given FTMO minute."""
    dt = dt or now_ftmo()
    return (
        schedule.get("enabled", True)
        and schedule.get("day") == ftmo_day_name(dt)
        and schedule.get("time") == ftmo_hhmm(dt)
    )
