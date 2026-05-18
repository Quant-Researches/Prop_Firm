import MetaTrader5 as mt5
import pandas as pd
from core.mt5_connection import MT5Connection

def fetch_mt5_candles(symbol, timeframe_str, bar_count=500, mt5_path="", account="", password="", server=""):
    """
    Fetches historical candles from MT5 for the given symbol and timeframe.
    Returns: df (DataFrame), source (str), error (str)
    """
    tf_map = {
        "1m": mt5.TIMEFRAME_M1,
        "5m": mt5.TIMEFRAME_M5,
        "15m": mt5.TIMEFRAME_M15,
        "30m": mt5.TIMEFRAME_M30,
        "1h": mt5.TIMEFRAME_H1,
        "4h": mt5.TIMEFRAME_H4,
        "1d": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe_str, mt5.TIMEFRAME_H1)
    
    if not MT5Connection.connect(account, password, server, mt5_path):
        err = mt5.last_error()
        return None, "MT5", f"Connection error: {err}"
        
    # Ensure symbol is active in Market Watch for real-time streaming
    if not mt5.symbol_select(symbol, True):
        return None, "MT5", f"Symbol '{symbol}' not found or subscription failed."
        
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bar_count)
    if rates is None or len(rates) == 0:
        return None, "MT5", f"No data for {symbol}"
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
    return df, "MT5", ""

def fetch_mt5_ltp(symbol, mt5_path="", account="", password="", server=""):
    """
    Fetches the Last Traded Price (LTP) or Ask price for the given symbol from MT5.
    Returns: ltp (float), error (str)
    """
    if not MT5Connection.connect(account, password, server, mt5_path):
        err = mt5.last_error()
        return 0.0, f"Connection error: {err}"
        
    # Ensure symbol is active in Market Watch for real-time tick streaming
    if not mt5.symbol_select(symbol, True):
        return 0.0, f"Symbol '{symbol}' not found or subscription failed."
        
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        return tick.last if tick.last > 0 else tick.ask, ""
    return 0.0, "Failed to fetch tick"
