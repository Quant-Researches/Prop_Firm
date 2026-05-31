"""
core/bar_selector.py
====================
Resolve which OHLCV bar to use for signal generation.

MT5 bar index = candle OPEN time (FTMO / Europe/Helsinki).
Scheduler fires at candle CLOSE time → target open = close - timeframe.

This avoids guessing iloc[-1] vs iloc[-2] when a new forming bar exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from core.candle_timer import TF_MINUTES
from core.ftmo_time import FTMO_TZ, now_ftmo


@dataclass
class BarSelection:
    index: int
    bar_open: datetime
    scheduled_close: datetime | None
    method: str


def _to_ftmo(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(FTMO_TZ)
    return t.tz_convert(FTMO_TZ)


def _normalize_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([_to_ftmo(t) for t in index])


def open_time_for_close(close_dt: datetime, timeframe: str) -> pd.Timestamp:
    """Bar open timestamp for the bar that closes at *close_dt*."""
    close_ts = _to_ftmo(close_dt).floor("min")
    step = TF_MINUTES.get(timeframe, 60)
    return (close_ts - pd.Timedelta(minutes=step)).floor("min")


def resolve_signal_bar(
    df: pd.DataFrame,
    timeframe: str,
    scheduled_close: datetime | None = None,
    now: datetime | None = None,
) -> BarSelection:
    """
    Pick the iloc index for signal evaluation.

    Scheduled ticks: match bar OPEN timestamp to (scheduled_close - TF).
    Manual ticks: use the last fully closed bar by wall-clock.
    """
    now_ts = _to_ftmo(now or now_ftmo())
    step = TF_MINUTES.get(timeframe, 60)
    n = len(df)
    if n == 0:
        raise ValueError("Cannot resolve signal bar on empty dataframe")

    idx_norm = _normalize_index(df.index)

    if scheduled_close is not None:
        close_ts = _to_ftmo(scheduled_close).floor("min")
        target_open = open_time_for_close(close_ts, timeframe)

        # 1) Exact open-time match (verified source of truth)
        for i in range(n - 1, -1, -1):
            if idx_norm[i].floor("min") == target_open:
                return BarSelection(
                    i,
                    idx_norm[i].to_pydatetime(),
                    close_ts.to_pydatetime(),
                    f"timestamp match open={target_open.strftime('%Y-%m-%d %H:%M')} FTMO",
                )

        # 2) New bar opened at close_ts → prior bar is the one that just closed
        if n >= 2 and idx_norm[-1].floor("min") == close_ts:
            i = n - 2
            if idx_norm[i].floor("min") == target_open:
                return BarSelection(
                    i,
                    idx_norm[i].to_pydatetime(),
                    close_ts.to_pydatetime(),
                    f"forming bar at {close_ts.strftime('%H:%M')}; closed bar open={target_open.strftime('%H:%M')} FTMO",
                )

        # 3) Broker lag: nearest open within one bar period
        best_i, best_delta = None, None
        for i in range(n):
            delta = abs((idx_norm[i].floor("min") - target_open).total_seconds())
            if delta <= step * 60 and (best_delta is None or delta < best_delta):
                best_i, best_delta = i, delta
        if best_i is not None:
            return BarSelection(
                best_i,
                idx_norm[best_i].to_pydatetime(),
                close_ts.to_pydatetime(),
                f"nearest open to {target_open.strftime('%H:%M')} FTMO (delta={int(best_delta)}s)",
            )

        # 4) Last bar whose close time <= scheduled close
        for i in range(n - 1, -1, -1):
            bar_end = idx_norm[i] + pd.Timedelta(minutes=step)
            if bar_end <= close_ts + pd.Timedelta(seconds=30):
                return BarSelection(
                    i,
                    idx_norm[i].to_pydatetime(),
                    close_ts.to_pydatetime(),
                    f"last completed bar before close {close_ts.strftime('%H:%M')} FTMO",
                )

    # Manual tick: last fully closed bar by current time
    for i in range(n - 1, -1, -1):
        bar_end = idx_norm[i] + pd.Timedelta(minutes=step)
        if now_ts >= bar_end:
            return BarSelection(
                i,
                idx_norm[i].to_pydatetime(),
                None,
                f"manual: last closed bar open={idx_norm[i].strftime('%Y-%m-%d %H:%M')} FTMO",
            )

    fallback = max(0, n - 2) if n >= 2 else 0
    return BarSelection(
        fallback,
        idx_norm[fallback].to_pydatetime(),
        None,
        "manual: fallback (only forming bar available)",
    )
