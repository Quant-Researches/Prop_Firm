"""
core/broker_clock.py — MT5-aligned FTMO clock (host-agnostic).

MT5 Python API returns bar/tick epochs that may not match true UTC on every
host (Windows local, AWS Lightsail, EC2). Civil ``now_ftmo()`` uses the OS
clock; candles used raw epoch → Helsinki, which can disagree by hours.

This module calibrates once per session (and periodically):
    skew_sec = median(MT5_tick_epoch - system_UTC_epoch)

All MT5 epochs are converted with:
    true_utc = mt5_epoch - skew_sec
    ftmo_dt  = true_utc → Europe/Helsinki

Trading paths use ``broker_now(symbol)`` so scheduler, bar picker, and OHLCV
index share one timeline on any machine with correct NTP (standard on AWS).
"""
from __future__ import annotations

import logging
import statistics
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from core.ftmo_time import FTMO_TZ, now_ftmo

logger = logging.getLogger("BrokerClock")

# Warn / log when MT5 epoch disagrees with system UTC by more than this.
SKEW_WARN_SEC = 120
# Reject calibration if skew looks absurd (misconfigured terminal).
SKEW_REJECT_SEC = 18 * 3600
# Samples for median skew (reduces tick noise).
_CALIBRATION_SAMPLES = 5
_SAMPLE_GAP_SEC = 0.08
# Recalibrate after this many seconds (DST / terminal reconnect).
_RECALIBRATE_AGE_SEC = 3600

_skew_sec: float | None = None
_calibrated_at: float = 0.0
_calibrated_symbol: str = ""


def skew_seconds() -> float | None:
    """Measured MT5−UTC skew in seconds, or None if not calibrated."""
    return _skew_sec


def is_calibrated() -> bool:
    return _skew_sec is not None


def skew_status() -> dict[str, Any]:
    """Diagnostics for logs, UI, and alerts."""
    civil = now_ftmo()
    skew = _skew_sec
    age = time.time() - _calibrated_at if _calibrated_at else None
    return {
        "calibrated": skew is not None,
        "skew_sec": skew,
        "skew_human": _format_skew(skew),
        "symbol": _calibrated_symbol or None,
        "calibrated_age_sec": int(age) if age is not None else None,
        "civil_ftmo": civil.strftime("%Y-%m-%d %H:%M:%S %z"),
    }


def _format_skew(skew: float | None) -> str:
    if skew is None:
        return "not calibrated"
    sign = "+" if skew >= 0 else "−"
    s = abs(int(round(skew)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return sign + " ".join(parts)


def mt5_seconds_to_ftmo(epoch: float | int) -> pd.Timestamp:
    """
    Convert an MT5 bar/tick epoch to timezone-aware Europe/Helsinki.

    Applies calibrated skew when available; otherwise legacy UTC→Helsinki.
    """
    epoch = int(float(epoch))
    if _skew_sec is not None:
        epoch = epoch - int(round(_skew_sec))
    return pd.to_datetime(epoch, unit="s", utc=True).tz_convert(FTMO_TZ)


def mt5_series_to_ftmo(epochs: pd.Series) -> pd.Series:
    """Vectorized conversion for candle ``time`` columns."""
    e = epochs.astype("int64")
    if _skew_sec is not None:
        e = e - int(round(_skew_sec))
    return pd.to_datetime(e, unit="s", utc=True).dt.tz_convert(FTMO_TZ)


def broker_now(symbol: str | None = None) -> datetime:
    """
    Current FTMO trading time — aligned with corrected candle index.

    Prefer latest MT5 tick (same axis as bars). Fall back to corrected
    system UTC, then civil ``now_ftmo()``.
    """
    if _skew_sec is not None:
        if symbol:
            try:
                import MetaTrader5 as mt5

                tick = mt5.symbol_info_tick(symbol)
                if tick is not None and tick.time > 0:
                    return mt5_seconds_to_ftmo(tick.time).to_pydatetime()
            except Exception:
                pass
        return (
            pd.Timestamp(time.time(), unit="s", tz=timezone.utc)
            .tz_convert(FTMO_TZ)
            .to_pydatetime()
        )

    logger.debug("broker_now: skew not calibrated — using civil now_ftmo()")
    return now_ftmo()


def _needs_recalibration(symbol: str, force: bool) -> bool:
    if force or _skew_sec is None:
        return True
    if symbol and _calibrated_symbol and symbol.upper() != _calibrated_symbol.upper():
        return True
    if time.time() - _calibrated_at >= _RECALIBRATE_AGE_SEC:
        return True
    return False


def calibrate_broker_clock(
    symbol: str,
    *,
    account: str = "",
    password: str = "",
    server: str = "",
    mt5_path: str = "",
    force: bool = False,
) -> tuple[bool, str]:
    """
    Measure MT5 vs system UTC skew (median of several ticks).

    Returns (ok, message). Safe on local Windows and Linux AWS when NTP is on.
    """
    global _skew_sec, _calibrated_at, _calibrated_symbol

    sym = (symbol or "").strip()
    if not sym:
        return False, "symbol required for broker clock calibration"

    if not _needs_recalibration(sym, force):
        return True, f"skew {_format_skew(_skew_sec)} (cached)"

    from core.mt5_connection import MT5Connection
    import MetaTrader5 as mt5

    if not MT5Connection.connect(account, password, server, mt5_path):
        err = mt5.last_error()
        return False, f"MT5 connect failed: {err}"

    if not mt5.symbol_select(sym, True):
        return False, f"symbol_select failed for {sym}"

    deltas: list[float] = []
    for _ in range(_CALIBRATION_SAMPLES):
        tick = mt5.symbol_info_tick(sym)
        if tick is None or tick.time <= 0:
            time.sleep(_SAMPLE_GAP_SEC)
            continue
        deltas.append(float(tick.time) - time.time())
        time.sleep(_SAMPLE_GAP_SEC)

    if len(deltas) < 2:
        return False, "insufficient MT5 ticks for calibration"

    skew = float(statistics.median(deltas))
    if abs(skew) > SKEW_REJECT_SEC:
        return False, f"skew {skew:.0f}s rejected (>{SKEW_REJECT_SEC}s)"

    # Snap large offsets to whole minutes so 15m/1h bar opens stay on the grid.
    if abs(skew) >= 60:
        skew = round(skew / 60.0) * 60.0

    _skew_sec = skew
    _calibrated_at = time.time()
    _calibrated_symbol = sym.upper()

    msg = f"skew {_format_skew(skew)} (n={len(deltas)})"
    if abs(skew) >= SKEW_WARN_SEC:
        logger.warning(
            "MT5 epoch offset from system UTC: %s — candles corrected; "
            "ensure OS NTP is enabled on AWS/local.",
            msg,
        )
    else:
        logger.info("Broker clock calibrated: %s", msg)
    return True, msg


def ensure_calibrated(prefs: dict, *, force: bool = False) -> tuple[bool, str]:
    """Calibrate using credentials from user prefs."""
    sym = prefs.get("trading_symbol", "XAUUSD")
    return calibrate_broker_clock(
        sym,
        account=prefs.get("mt5_account", ""),
        password=prefs.get("mt5_password", ""),
        server=prefs.get("mt5_server", ""),
        mt5_path=prefs.get("mt5_path", ""),
        force=force,
    )


def validate_candle_timestamps(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> str | None:
    """
    Return a warning string if the latest bar open is far from broker_now.
    None if OK or cannot validate.
    """
    if df is None or df.empty or not is_calibrated():
        return None

    from core.candle_timer import TF_MINUTES

    step = TF_MINUTES.get(timeframe, 60)
    try:
        last_open = pd.Timestamp(df.index[-1])
        if last_open.tzinfo is None:
            last_open = last_open.tz_localize(FTMO_TZ)
        else:
            last_open = last_open.tz_convert(FTMO_TZ)
        now_ts = pd.Timestamp(broker_now(symbol))
        # Forming bar: open should be within one TF of now (plus small slack)
        delta_sec = abs((now_ts - last_open).total_seconds())
        limit = step * 60 * 2 + 90
        if delta_sec > limit:
            return (
                f"last bar open {last_open.strftime('%H:%M')} vs broker_now "
                f"{now_ts.strftime('%H:%M')} (delta {int(delta_sec)}s > {limit}s)"
            )
    except Exception as exc:
        return f"validation error: {exc}"
    return None
