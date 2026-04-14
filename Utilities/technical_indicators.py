"""
Utilities/technical_indicators.py
===================================
Core technical indicator calculations used by strategy.py.
All functions accept pandas Series and return pandas Series.
"""

import pandas as pd
import numpy as np


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average.

    Parameters
    ----------
    series : pd.Series  — price series (e.g. Close)
    period : int        — EMA look-back window

    Returns
    -------
    pd.Series of EMA values (same index as input)
    """
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (Wilder's smoothing).

    Parameters
    ----------
    series : pd.Series — price series (e.g. Close)
    period : int       — RSI look-back window (default 14)

    Returns
    -------
    pd.Series of RSI values 0–100 (same index as input)
    """
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # fill NaN with neutral 50


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Average True Range (Wilder's smoothing).

    Parameters
    ----------
    high  : pd.Series — bar High prices
    low   : pd.Series — bar Low prices
    close : pd.Series — bar Close prices
    period : int      — ATR look-back window (default 14)

    Returns
    -------
    pd.Series of ATR values (same index as input)
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder's smoothing = EMA with alpha = 1/period
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return atr
