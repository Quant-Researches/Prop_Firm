"""
core/signal_store.py
====================
Mandatory Signal Logger — writes every BUY/SELL signal to data/signals.json
in the user-specified format.

This module is called UNCONDITIONALLY on every signal, BEFORE any execution
routing (Dhan / MetaTrader5 / JSON-only). It is completely independent of
the OMS, Execution, and Portfolio pipelines to ensure zero coupling.

Architecture Position:
    [Strategy] → signal → [Signal Store] ← always writes
                        → [Engine routes to OMS/MT5/skip]
"""

from __future__ import annotations
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("SignalStore")

SIGNALS_FILE = Path("data/signals.json")


def _make_serializable(val):
    """Convert numpy/pandas types to native Python for JSON serialization."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating, np.float64)):
        return float(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, (pd.Timestamp,)):
        return str(val)
    if pd.isna(val):
        return None
    return val


def save_signal(
    latest_row: pd.Series,
    symbol: str,
    interval: str,
    sec_id: str,
    signal: str,
    reason: str,
) -> str:
    """
    Append a signal entry to data/signals.json in the exact user-specified format.

    Parameters
    ----------
    latest_row : pd.Series — the last row of the strategy DataFrame
    symbol     : trading symbol string (e.g. "GOLDPETAL")
    interval   : timeframe string (e.g. "1h")
    sec_id     : Dhan security ID string
    signal     : "BUY" or "SELL"
    reason     : human-readable signal reason string

    Returns
    -------
    str : the key used to store the signal (e.g. "2025-10-08 09:00:00_GOLDPETAL")
    """
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing signals
    existing = {}
    if SIGNALS_FILE.exists():
        try:
            existing = json.loads(SIGNALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    # Build the timestamp string from the row's index
    time_str = str(latest_row.name)
    key = f"{time_str}_{symbol}"

    # Calculate relative volume (rvol)
    vol = latest_row.get("Volume", 0)
    vol_ma = latest_row.get("Vol_MA", 0)
    rvol = float(vol / vol_ma) if vol_ma and not pd.isna(vol_ma) and vol_ma > 0 else 0.0

    # Build the exact user-specified JSON structure
    entry = {
        "Open":      _make_serializable(latest_row.get("Open", 0)),
        "High":      _make_serializable(latest_row.get("High", 0)),
        "Low":       _make_serializable(latest_row.get("Low", 0)),
        "Close":     _make_serializable(latest_row.get("Close", 0)),
        "Volume":    _make_serializable(latest_row.get("Volume", 0)),
        "EMA_Fast":  _make_serializable(latest_row.get("EMA_Fast", 0)),
        "EMA_Slow":  _make_serializable(latest_row.get("EMA_Slow", 0)),
        "Vol_MA":    _make_serializable(latest_row.get("Vol_MA", 0)),
        "Peak":      _make_serializable(latest_row.get("Peak", False)),
        "Trough":    _make_serializable(latest_row.get("Trough", False)),
        "SwingType": _make_serializable(latest_row.get("SwingType", "NA")),
        "Last_HH":   _make_serializable(latest_row.get("Last_High", None)),
        "Last_LL":   _make_serializable(latest_row.get("Last_Low", None)),
        "symbol":    symbol,
        "interval":  interval,
        "sec_id":    sec_id,
        "signal":    signal,
        "price":     _make_serializable(latest_row.get("Close", 0)),
        "time":      time_str,
        "reason":    reason,
        "rvol":      round(rvol, 6),
    }

    existing[key] = entry

    # Write back
    try:
        SIGNALS_FILE.write_text(
            json.dumps(existing, indent=4, default=str),
            encoding="utf-8"
        )
        logger.info(f"Signal saved: {key}")
    except Exception as e:
        logger.error(f"Failed to save signal: {e}")

    return key
