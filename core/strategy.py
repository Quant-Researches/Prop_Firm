"""
core/strategy.py
================
Strategy — consumes MarketEvents and produces SignalEvents.

Architecture Position:
    [Data Feed] → MarketEvent → [Strategy] → SignalEvent → [Risk Manager]

Built-in strategy slots:
    - on_market_event() : called on every new bar
    - on_signal()       : optional hook after signal is generated

TODO: Subclass Strategy and implement on_market_event() with your logic.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.data_feed import MarketEvent


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass
class SignalEvent:
    """
    Carries a directional signal produced by a Strategy.
    """
    symbol: str
    direction: str              # "BUY" | "SELL" | "EXIT_LONG" | "EXIT_SHORT"
    strength: float             # 0.0 – 1.0  (confidence / signal quality)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    strategy_name: str = "BaseStrategy"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"SignalEvent({self.strategy_name} | {self.symbol} | "
            f"{self.direction} | strength={self.strength:.2f})"
        )


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class Strategy:
    """
    Base class for all trading strategies.

    Lifecycle
    ---------
    1. Bot starts → __init__() called once
    2. Per bar    → on_market_event(event) called → returns SignalEvent or None
    3. Per signal → on_signal(signal) hook fires (optional override)
    4. Bot stops  → teardown() called once

    Parameters
    ----------
    name        : human-readable strategy identifier
    params      : dict of strategy hyperparameters (EMA periods, RSI level, etc.)
    """

    def __init__(self, name: str = "BaseStrategy", params: Optional[dict] = None):
        self.name = name
        self.params = params or {}
        self._bar_count = 0

    # ------------------------------------------------------------------
    # Core Interface — implement these
    # ------------------------------------------------------------------

    def on_market_event(self, event: MarketEvent) -> Optional[SignalEvent]:
        """
        Called on every new MarketEvent (bar close).
        Return a SignalEvent to trigger an order, or None to wait.
        """
        raise NotImplementedError(f"{self.name}.on_market_event() — implement signal logic")

    # ------------------------------------------------------------------
    # Optional Hooks — override as needed
    # ------------------------------------------------------------------

    def on_signal(self, signal: SignalEvent) -> None:
        """Called immediately after a signal is emitted. Use for logging."""
        pass

    def teardown(self) -> None:
        """Called when the bot is stopped. Release indicators, close files, etc."""
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def bar_count(self) -> int:
        return self._bar_count

    def __repr__(self) -> str:
        return f"Strategy(name={self.name}, params={self.params})"
        
from pprint import pprint
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor
import logging
import json
import os
import pytz
import requests
import subprocess
from config.config import config
from Utilities.technical_indicators import calculate_ema, calculate_rsi, calculate_atr

# --- Logger Setup ---
def setup_logger(name="DowTheoryFutures"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = setup_logger()

class RealTimeSignalGenerator:
    """
    Generates signals for a single stock using Dow Theory on candles.
    Adapted for Futures (Gold) 5min strategy.
    """
    def __init__(self, stock_symbol, sec_id=None, interval="5m",
                 use_vol_filter=True, ema_fast=3, ema_slow=8, use_atr_filter=True, atr_period=14):
        self.symbol = stock_symbol
        self.sec_id = sec_id  # MT5 Symbol (Optional for scanner)
        self.interval = interval
        self.data = pd.DataFrame()
        
        # EMA periods — configurable via UI (defaults: fast=3, slow=8)
        self.ema_short_period = ema_fast
        self.ema_long_period = ema_slow
        self.vol_ma_period = 21
        
        self.last_signal = "HOLD"
        self.market_phase = "SIDEWAYS"
        
        # Risk Management
        self.stop_loss_pct = 0.002
        self.take_profit_pct = 0.0045
        
        # Tracking
        self.last_processed_candle_time = None


        # Swing Logic Attributes
        self.highs = []
        self.lows = []
        
        # Filter toggles
        self.use_volume_filter = use_vol_filter
        self.use_atr_filter    = use_atr_filter
        self.atr_period        = atr_period

    def update_data(self, df):
        """Updates the data from an external source (Bulk Fetch)."""
        if df is not None and not df.empty:
            self.data = df.copy()
            # Ensure index is datetime
            if not isinstance(self.data.index, pd.DatetimeIndex):
                self.data.index = pd.to_datetime(self.data.index)

    def calculate_indicators(self):
        """Calculates EMAs, Volume MA, ATR and ATR Slope."""
        if self.data.empty or len(self.data) < self.ema_long_period:
            return

        df = self.data.copy()
        # EMA
        df['fast_ema'] = calculate_ema(df['Close'], self.ema_short_period)
        df['slow_ema'] = calculate_ema(df['Close'], self.ema_long_period)
        df['EMA_Fast'] = df['fast_ema']
        df['EMA_Slow'] = df['slow_ema']
        
        # Volume Moving Average
        if 'Volume' in df.columns:
            df['Vol_MA'] = df['Volume'].rolling(window=self.vol_ma_period).mean()
        
        # ATR & ATR Slope
        df['ATR'] = calculate_atr(df['High'], df['Low'], df['Close'], period=self.atr_period)
        # Slope = difference between current and previous ATR bar
        # Positive  → volatility is expanding (breakout energy growing)
        # Negative  → volatility is contracting (choppy / exhaustion move)
        df['ATR_Slope'] = df['ATR'].diff()
        
        # ATR Percentile (200 periods) to classify volatility regimes (0.0 to 1.0)
        df['ATR_Percentile'] = df['ATR'].rolling(window=200, min_periods=20).apply(lambda x: (x <= x[-1]).mean(), raw=True)
        
        self.data = df

    def _find_and_set_swings_fractal(self):
        """Find Highs and Lows using strict Fractal logic (Simplified)."""
        try:
            high = self.data['High']
            low = self.data['Low']
            
            # Initialize columns
            self.data['SwingType'] = 'NA'
            self.data['Last_High'] = np.nan
            self.data['Last_Low'] = np.nan
            
            if len(self.data) < 5:
                return

            # 1. Identify Fractal Candidates
            candidates = [] 
            
            for i in range(2, len(self.data) - 2):
                # Fractal High (5 candles)
                if (high.iloc[i] > high.iloc[i-1] and 
                    high.iloc[i] > high.iloc[i-2] and
                    high.iloc[i] > high.iloc[i+1] and 
                    high.iloc[i] > high.iloc[i+2]):
                    candidates.append({'idx': i, 'type': 'High', 'val': high.iloc[i]})
                    
                # Fractal Low (5 candles)
                if (low.iloc[i] < low.iloc[i-1] and 
                    low.iloc[i] < low.iloc[i-2] and 
                    low.iloc[i] < low.iloc[i+1] and 
                    low.iloc[i] < low.iloc[i+2]):
                    candidates.append({'idx': i, 'type': 'Low', 'val': low.iloc[i]})
            
            if not candidates:
                return

            # 2. Filter for Alternating Swings
            confirmed_swings = []
            pending = candidates[0]
            
            for i in range(1, len(candidates)):
                curr = candidates[i]
                if pending['type'] == curr['type']:
                    # Keep better one
                    if pending['type'] == 'High':
                        if curr['val'] > pending['val']:
                            pending = curr
                    else: # Low
                        if curr['val'] < pending['val']:
                            pending = curr
                else:
                    # Switch
                    confirmed_swings.append(pending)
                    pending = curr
            confirmed_swings.append(pending)
            
            # 3. Update DataFrame (Simple High/Low)
            active_high = np.nan
            active_low = np.nan
            
            swing_types = ['NA'] * len(self.data)
            last_high_arr = [np.nan] * len(self.data)
            last_low_arr = [np.nan] * len(self.data)
            
            swings_by_idx = {x['idx']: x for x in confirmed_swings}
            
            self.highs = []
            self.lows = []
            
            for i in range(len(self.data)):
                # If swing at this index
                if i in swings_by_idx:
                    swing = swings_by_idx[i]
                    sType = 'NA'
                    
                    if swing['type'] == 'High':
                        sType = 'High'
                        self.highs.append(swing['val'])
                        active_high = swing['val']
                        # Do not clear active_low (User wants "previous conditions", usually entails keeping support)
                        # Actually, strictly, if we make a High, the Low is the support.
                        # For signal generation "Close > High", we just need the last High.
                        
                    elif swing['type'] == 'Low':
                        sType = 'Low'
                        self.lows.append(swing['val'])
                        active_low = swing['val']
                    
                    swing_types[i] = sType
                
                last_high_arr[i] = active_high
                last_low_arr[i] = active_low

            self.data['SwingType'] = swing_types
            self.data['Last_High'] = last_high_arr
            self.data['Last_Low'] = last_low_arr

        except Exception as e:
            logger.error(f"SWING ERROR: {e}")


    def determine_phase(self, row):
        """Updates market phase based on EMA and swings."""
        if 'EMA_Fast' not in row or 'EMA_Slow' not in row:
             return "SIDEWAYS"
             
        close = row['Close']
        fast = row['EMA_Fast']
        slow = row['EMA_Slow']
        
        if pd.isna(fast) or pd.isna(slow):
            return "SIDEWAYS"
        
        if close > fast and fast > slow:
            return "BULLISH"
        elif close < fast and fast < slow:
            return "BEARISH"
        else:
            return "SIDEWAYS"

    def _generate_core_signal(self, latest_row):
        """Generates core BUY/SELL signal with Volume and ATR slope confirmation."""
        close_price = latest_row['Close']
        last_high = latest_row.get('Last_High', np.nan)
        last_low  = latest_row.get('Last_Low',  np.nan)
        
        signal = "HOLD"
        reason = ""
        
        # ── Volume Filter ──────────────────────────────────────────────────────
        vol_passed = True
        if self.use_volume_filter and 'Volume' in latest_row and 'Vol_MA' in latest_row:
            vol = latest_row['Volume']
            ma  = latest_row['Vol_MA']
            if pd.notna(vol) and pd.notna(ma) and vol < ma:
                vol_passed = False

        # ── ATR Slope Filter ──────────────────────────────────────────────────
        # Positive ATR slope → volatility is expanding → breakout has energy
        # We require this for BOTH buy and sell breakouts (momentum confirmation)
        atr_passed = True
        if self.use_atr_filter and 'ATR_Slope' in latest_row:
            atr_slope = latest_row['ATR_Slope']
            if pd.notna(atr_slope) and atr_slope <= 0:
                atr_passed = False

        if self.market_phase == "BULLISH":
            if pd.notna(last_high) and close_price > last_high:
                if vol_passed and atr_passed:
                    signal = "BUY"
                    reason = (f"Breakout > High ({last_high:.2f}) + Phase BULLISH"
                              + (" + Vol OK" if self.use_volume_filter else "")
                              + (" + ATR ↑" if self.use_atr_filter else ""))
                else:
                    filters_failed = []
                    if not vol_passed:  filters_failed.append("Vol Low")
                    if not atr_passed: filters_failed.append("ATR Slope ≤ 0")
                    reason = f"Breakout > High but filtered: {', '.join(filters_failed)}"
            
        elif self.market_phase == "BEARISH":
            if pd.notna(last_low) and close_price < last_low:
                if vol_passed and atr_passed:
                    signal = "SELL"
                    reason = (f"Breakdown < Low ({last_low:.2f}) + Phase BEARISH"
                              + (" + Vol OK" if self.use_volume_filter else "")
                              + (" + ATR ↑" if self.use_atr_filter else ""))
                else:
                    filters_failed = []
                    if not vol_passed:  filters_failed.append("Vol Low")
                    if not atr_passed: filters_failed.append("ATR Slope ≤ 0")
                    reason = f"Breakdown < Low but filtered: {', '.join(filters_failed)}"
        
        return signal, reason
        
    def generate_historical_signals(self):
        """
        Backfills 'Signal' column in self.data for visualization.
        """
        if self.data.empty:
            return

        signals = []
        phases = []
        
        # Iterate through data to simulate real-time analysis
        # Note: This is a simplified backtest, strictly following the logic at each step
        
        last_acted_high = None
        last_acted_low = None
        
        current_signal = "HOLD"
        reasons = []

        for i in range(len(self.data)):
            row = self.data.iloc[i].copy()
            phase = self.determine_phase(row)
            phases.append(phase)
            
            # Determine signal
            self.market_phase = phase
            sig, reason = self._generate_core_signal(row)
            
            # Allow signals if direction changes OR if it's a new breakout level (Pyramiding)
            entry_signal = np.nan
            entry_reason = np.nan
            
            if sig == "BUY":
                curr_high = row.get('Last_High')
                if current_signal != "BUY" or (pd.notna(curr_high) and curr_high != last_acted_high):
                    entry_signal = "BUY"
                    current_signal = "BUY"
                    last_acted_high = curr_high
                    entry_reason = reason

            elif sig == "SELL":
                curr_low = row.get('Last_Low')
                if current_signal != "SELL" or (pd.notna(curr_low) and curr_low != last_acted_low):
                    entry_signal = "SELL"
                    current_signal = "SELL"
                    last_acted_low = curr_low
                    entry_reason = reason
            
            signals.append(entry_signal)
            reasons.append(entry_reason)
                
        self.data['Phase'] = phases
        self.data['Signal_Vis'] = signals
        self.data['Signal_Reason'] = reasons

    def run_analysis(self, scheduled_close=None, is_manual=False):
        """
        Runs full analysis and returns signal for the verified signal bar.

        scheduled_close: candle CLOSE time from scheduler (FTMO/Helsinki).
        is_manual: if True, pick last closed bar by wall-clock instead.
        """
        if self.data.empty:
            return None

        # 1. Calculate Indicators
        self.calculate_indicators()
        
        if 'EMA_Fast' not in self.data.columns:
            return None

        # 2. Find Swings (Using FRACTAL logic)
        self._find_and_set_swings_fractal()
        
        # 3. Generate Historical Signals for Visualization
        self.generate_historical_signals()
        
        # 4. Resolve signal bar by timestamp (not blind iloc[-1])
        from core.bar_selector import resolve_signal_bar
        from core.broker_clock import broker_now

        close_for_lookup = None if is_manual else scheduled_close
        selection = resolve_signal_bar(
            self.data,
            self.interval,
            scheduled_close=close_for_lookup,
            now=broker_now(self.symbol),
        )
        signal_row = self.data.iloc[selection.index]
        
        self.market_phase = self.determine_phase(signal_row)
        
        raw_signal, raw_reason = self._generate_core_signal(signal_row)
        
        clean_signal = signal_row.get('Signal_Vis', 'HOLD')
        if pd.isna(clean_signal):
            clean_signal = "HOLD"
            
        clean_reason = signal_row.get('Signal_Reason', raw_reason)
        if pd.isna(clean_reason):
            clean_reason = raw_reason
        
        return {
            "symbol": self.symbol,
            "time": signal_row.name,
            "price": signal_row['Close'],
            "phase": self.market_phase,
            "Signal": clean_signal,
            "Market_Phase": self.market_phase,
            "Action": clean_reason,
            "raw_signal": raw_signal,
            "data": self.data,
            "last_high": signal_row.get('Last_High', np.nan),
            "last_low": signal_row.get('Last_Low', np.nan),
            "fast_ema": signal_row['fast_ema'],
            "slow_ema": signal_row['slow_ema'],
            "atr": signal_row.get('ATR', np.nan),
            "atr_percentile": signal_row.get('ATR_Percentile', np.nan),
            "signal_bar_index": selection.index,
            "signal_bar_open": selection.bar_open,
            "scheduled_close": selection.scheduled_close,
            "bar_selection": selection.method,
        }
