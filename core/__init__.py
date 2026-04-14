# core/__init__.py
# Trade Pulse Quants — Event-Driven Live Trading Core Package
#
# Event Flow:
#   DataFeed → MarketEvent
#   Strategy → SignalEvent
#   RiskManager → OrderEvent
#   OMS (submit)
#   Execution → FillEvent
#   Portfolio (update)
#   Storage (persist)

from core.data_feed import DataFeed, MarketEvent
from core.strategy import Strategy, SignalEvent
from core.risk_manager import RiskManager, OrderEvent
from core.oms import OMS
from core.execution import ExecutionEngine, FillEvent
from core.portfolio import Portfolio
from core.storage import Storage

__all__ = [
    "DataFeed", "MarketEvent",
    "Strategy", "SignalEvent",
    "RiskManager", "OrderEvent",
    "OMS",
    "ExecutionEngine", "FillEvent",
    "Portfolio",
    "Storage",
]
