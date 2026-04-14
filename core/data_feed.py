"""
core/data_feed.py
=================
Data Feed — produces MarketEvents from Historical or Live sources.

Architecture Position:
    [Data Feed] → MarketEvent → [Strategy]

Supported Modes:
    - historical : replay OHLCV CSV/parquet files
    - live       : subscribe to broker WebSocket / REST polling

TODO: Implement connect(), stream(), and disconnect() with real broker API.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass
class MarketEvent:
    """Carries OHLCV tick data for a single bar."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str = "1m"
    mode: str = "live"          # "historical" | "live"
    extra: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"MarketEvent({self.symbol} | {self.timestamp} | "
            f"O={self.open} H={self.high} L={self.low} C={self.close} V={self.volume})"
        )


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class DataFeed:
    """
    Abstract data feed that emits MarketEvents.

    Parameters
    ----------
    symbols   : list of trading symbols to subscribe to
    timeframe : bar size, e.g. "1m", "5m", "1h", "1d"
    mode      : "historical" | "paper" | "live"
    """

    def __init__(self, symbols: list[str], timeframe: str = "1m", mode: str = "live"):
        self.symbols = symbols
        self.timeframe = timeframe
        self.mode = mode
        self._connected = False

    # ------------------------------------------------------------------
    # Public Interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Establish connection to the data source.
        - Historical : open file handle / load dataframe
        - Live       : open WebSocket / authenticate REST session
        """
        raise NotImplementedError("DataFeed.connect() — implement broker connection")

    def stream(self) -> Iterator[MarketEvent]:
        """
        Yield MarketEvents one bar at a time.
        Blocks until a new bar arrives (live) or exhausts file (historical).
        """
        raise NotImplementedError("DataFeed.stream() — implement bar generator")

    def disconnect(self) -> None:
        """
        Gracefully close the data connection and release resources.
        """
        raise NotImplementedError("DataFeed.disconnect() — implement cleanup")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    def __repr__(self) -> str:
        return f"DataFeed(symbols={self.symbols}, tf={self.timeframe}, mode={self.mode})"
