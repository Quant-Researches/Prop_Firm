"""
core/dhan_data.py
=================
Dhan API v2 Historical Data Fetcher

Fetches OHLCV data from Dhan API v2 for intraday and daily intervals.
Falls back to yfinance if Dhan credentials are not provided.

Dhan API Docs:
    POST https://api.dhan.co/v2/charts/historical  (intraday)
    POST https://api.dhan.co/v2/charts/historical  (daily)
"""

from __future__ import annotations
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("DhanData")

# ---------------------------------------------------------------------------
# Interval mappings
# ---------------------------------------------------------------------------
# Dhan intraday interval names
DHAN_INTRADAY_INTERVALS = {
    "1m":  "1",
    "3m":  "3",
    "5m":  "5",
    "15m": "15",
    "25m": "25",
    "60m": "60",
    "1h":  "60",
}

DHAN_DAILY_INTERVALS = {"1d", "1wk", "1mo"}

# yfinance fallback interval map
YF_INTERVAL_MAP = {
    "1m":  "1m",
    "3m":  "5m",   # yf doesn't have 3m natively, fall back to 5m
    "5m":  "5m",
    "15m": "15m",
    "25m": "30m",
    "60m": "60m",
    "1h":  "60m",
    "1d":  "1d",
    "1wk": "1wk",
}

# ---------------------------------------------------------------------------
# Main fetcher
# ---------------------------------------------------------------------------

def fetch_candles(
    security_id: str,
    exchange_segment: str,
    instrument_type: str,
    interval: str,
    client_id: str = "",
    access_token: str = "",
    bar_count: int = 300,
    fallback_symbol: str = "GC=F",     # yfinance symbol
    data_source: str = "Dhan",
) -> tuple[pd.DataFrame, str, str]:
    """
    Fetch OHLCV DataFrame strictly using the requested data_source, with NO fallbacks.

    Returns
    -------
    (df, source, error_detail)
      source       : "dhan" | "yfinance"
      error_detail : empty string on success, human-readable error on failure
    df has DatetimeIndex and columns: Open, High, Low, Close, Volume
    """
    if data_source != "Dhan":
        # Strict YFinance fetching
        df = _fetch_from_yfinance(symbol=fallback_symbol, interval=interval, bar_count=bar_count)
        if df is None or df.empty:
            return None, "yfinance", f"YFinance fetch failed for symbol '{fallback_symbol}'"
        return df, "yfinance", ""

    # Strict Dhan fetching
    if not access_token or not client_id:
        return None, "dhan", "No Dhan API credentials configured. Cannot execute Dhan feed."

    df, dhan_error = _fetch_from_dhan(
        security_id=security_id,
        exchange_segment=exchange_segment,
        instrument_type=instrument_type,
        interval=interval,
        client_id=client_id,
        access_token=access_token,
        bar_count=bar_count,
    )
    
    if df is not None and not df.empty:
        return df, "dhan", ""
        
    logger.error(f"Dhan fetch failed: {dhan_error}")
    return None, "dhan", f"Dhan API Error: {dhan_error}"


def fetch_ltp(
    security_id: str,
    exchange_segment: str,
    client_id: str,
    access_token: str
) -> tuple[float, str]:
    """
    Fetch the Last Traded Price (LTP) from Dhan Market Feed REST API.
    Returns (ltp, error_msg). ltp=0.0 on failure.
    """
    if not access_token or not client_id:
        return 0.0, "Missing API credentials"

    headers = {
        "Content-Type": "application/json",
        "access-token": access_token,
        "client-id": client_id,
    }
    
    # Dhan v2 LTP REST endpoint
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    payload = {
        "dhanClientId": client_id,
        "segmentId": exchange_segment,
        "data": [
            {
                "exchangeSegment": exchange_segment,
                "securityId": str(security_id)
            }
        ]
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            # Dhan returns a list in "data" key
            if "data" in data and len(data["data"]) > 0:
                ltp = data["data"][0].get("lastPrice", 0.0)
                return float(ltp), ""
            return 0.0, f"No LTP data in response: {res.text[:100]}"
        return 0.0, f"HTTP {res.status_code}: {res.text[:100]}"
    except Exception as e:
        return 0.0, str(e)


# ---------------------------------------------------------------------------
# Dhan API v2 implementation
# ---------------------------------------------------------------------------

def _fetch_from_dhan(
    security_id: str,
    exchange_segment: str,
    instrument_type: str,
    interval: str,
    client_id: str,
    access_token: str,
    bar_count: int,
) -> tuple[pd.DataFrame | None, str]:
    """Fetch historical candles from Dhan v2 API. Returns (df, error_detail)."""
    try:
        headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
            "client-id": client_id,
        }

        is_daily = interval in DHAN_DAILY_INTERVALS

        # Calculate date range
        today = datetime.now()
        if is_daily:
            # Go back enough weeks/months
            lookback_days = bar_count * 7 if interval == "1wk" else bar_count * 30 if interval == "1mo" else bar_count + 50
            from_dt = today - timedelta(days=lookback_days)
            endpoint = "https://api.dhan.co/v2/charts/historical"
        else:
            # For intraday, Dhan allows up to 90 days back for 1m, etc.
            # Request extra days to guarantee >= bar_count candles
            dhan_interval = DHAN_INTRADAY_INTERVALS.get(interval, "5")
            minutes_per_candle = int(dhan_interval)
            trading_minutes_per_day = 375  # NSE/MCX approx
            candles_per_day = trading_minutes_per_day // minutes_per_candle
            days_needed = max(7, (bar_count // candles_per_day) + 5)
            from_dt = today - timedelta(days=days_needed)
            endpoint = "https://api.dhan.co/v2/charts/intraday"

        from_date = from_dt.strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        chunk_size_days = 85
        all_dfs = []
        current_to_dt = today
        
        while current_to_dt > from_dt:
            current_from_dt = max(from_dt, current_to_dt - timedelta(days=chunk_size_days))
            
            c_from = current_from_dt.strftime("%Y-%m-%d")
            c_to = current_to_dt.strftime("%Y-%m-%d")

            if is_daily:
                payload = {
                    "securityId": str(security_id),
                    "exchangeSegment": exchange_segment,
                    "instrument": instrument_type,
                    "expiryCode": 0,
                    "oi_flag": "0",
                    "fromDate": c_from,
                    "toDate": c_to,
                }
            else:
                payload = {
                    "securityId": str(security_id),
                    "exchangeSegment": exchange_segment,
                    "instrument": instrument_type,
                    "interval": DHAN_INTRADAY_INTERVALS.get(interval, "5"),
                    "fromDate": c_from,
                    "toDate": c_to,
                }

            logger.info(f"Dhan API chunk: {c_from} to {c_to}")
            response = requests.post(endpoint, json=payload, headers=headers, timeout=15)

            if response.status_code != 200:
                err = f"HTTP {response.status_code}: {response.text[:300]}"
                logger.error(f"Dhan API error: {err}")
                if not all_dfs:
                    return None, err
                break  # Stop fetching older chunks but keep what we have

            data = response.json()

            if not data or "open" not in data:
                err_msg = data.get("message") or data.get("errorMessage") or str(data)[:200]
                if not all_dfs:
                    return None, f"Dhan API: {err_msg}"
                break

            timestamps = data.get("timestamp", [])
            if not timestamps:
                if not all_dfs:
                    return None, "Dhan API returned empty timestamp array."
                break

            chunk_df = pd.DataFrame({
                "Open":   data["open"],
                "High":   data["high"],
                "Low":    data["low"],
                "Close":  data["close"],
                "Volume": data["volume"],
            }, index=pd.to_datetime(timestamps, unit="s", utc=True))
            
            all_dfs.append(chunk_df)
            
            # Move backward one day before the current from_date
            current_to_dt = current_from_dt - timedelta(days=1)

        if not all_dfs:
            return None, "No data fetched across any chunks."

        # Combine all chunks
        df = pd.concat(all_dfs).drop_duplicates().sort_index()

        # Convert UTC → IST
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
        df.index.name = "Datetime"

        # Clean & tail to requested bar_count
        df = df.dropna().sort_index()
        df = df.tail(bar_count)
        return df, ""

    except requests.exceptions.Timeout:
        err = "Dhan API timed out (15s). Check your internet connection."
        logger.error(err)
        return None, err
    except Exception as e:
        err = f"Dhan API exception: {type(e).__name__}: {e}"
        logger.error(err)
        return None, err


# ---------------------------------------------------------------------------
# yfinance fallback
# ---------------------------------------------------------------------------

def _fetch_from_yfinance(symbol: str, interval: str, bar_count: int) -> pd.DataFrame:
    """Fallback: fetch from yfinance."""
    try:
        import yfinance as yf

        yf_interval = YF_INTERVAL_MAP.get(interval, "5m")

        # Determine period
        if yf_interval in ("1m",):
            period = "7d"
        elif yf_interval in ("5m", "15m", "30m"):
            period = "60d"
        elif yf_interval in ("60m", "1h"):
            period = "730d"
        else:
            period = "5y"

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=yf_interval, auto_adjust=True)

        if df.empty:
            return pd.DataFrame()

        # Normalise columns
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tzinfo is not None:
            df.index = df.index.tz_localize(None)
        df = df.dropna().sort_index()
        df = df.tail(bar_count)
        return df

    except Exception as e:
        logger.error(f"yfinance error: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Convenience: list of common MCX Gold instruments
# ---------------------------------------------------------------------------
MCX_INSTRUMENTS = {
    "Gold Petal (1g)":    {"security_id": "626",   "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Gold M (10g)":       {"security_id": "1333",  "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Gold (1kg)":         {"security_id": "694",   "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Silver (30kg)":      {"security_id": "796",   "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Crude Oil":          {"security_id": "10599", "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
}
