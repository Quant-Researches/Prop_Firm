"""
core/execution.py
=================
Execution Engine — fills orders and produces FillEvents.

Architecture Position:
    [OMS] → OrderEvent → [Execution Engine] → FillEvent → [Portfolio]

Supported Modes:
    - backtest : simulate fills using historical OHLCV bars (slippage model)
    - paper    : send real API requests but don't commit real capital
    - live     : execute real orders via broker API

TODO: Implement execute() for each mode with slippage models and broker calls.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import requests
import json

from core.risk_manager import OrderEvent


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass
class FillEvent:
    """
    Confirms that an order has been (partially) filled.
    """
    order_id: str
    symbol: str
    side: str                   # "BUY" | "SELL"
    qty: float                  # units filled
    fill_price: float           # average fill price
    timestamp: datetime = field(default_factory=datetime.utcnow)
    commission: float = 0.0     # transaction cost (brokerage + taxes)
    slippage: float = 0.0       # price slippage vs. requested price
    mode: str = "live"          # "backtest" | "paper" | "live"
    partial: bool = False       # True if only partly filled
    remaining_qty: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def gross_value(self) -> float:
        return self.qty * self.fill_price

    @property
    def net_value(self) -> float:
        return self.gross_value + self.commission

    def __repr__(self) -> str:
        return (
            f"FillEvent({self.order_id} | {self.symbol} | "
            f"{self.side} {self.qty} @ {self.fill_price:.2f} | "
            f"commission={self.commission:.2f})"
        )


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """
    Routes orders to the correct execution path based on mode.

    Parameters
    ----------
    mode             : "backtest" | "paper" | "live"
    slippage_pct     : % slippage applied in backtest/paper mode (e.g. 0.001 = 0.1%)
    commission_per_lot : flat commission per lot/unit (backtest simulation)
    """

    def __init__(
        self,
        mode: str = "live",
        slippage_pct: float = 0.001,
        commission_per_lot: float = 20.0,
    ):
        self.mode = mode
        self.slippage_pct = slippage_pct
        self.commission_per_lot = commission_per_lot
        self._fills: list[FillEvent] = []

    # ------------------------------------------------------------------
    # Core Interface — implement this
    # ------------------------------------------------------------------

    def execute(self, order: OrderEvent, prefs: dict = None) -> FillEvent:
        """
        Execute an order and return a FillEvent.
        Routes to MT5.
        """
        return self._execute_mt5(order, prefs)


    def _execute_mt5(self, order: OrderEvent, prefs: dict) -> FillEvent:
        import MetaTrader5 as mt5
        
        mt5_path = prefs.get("mt5_path", "")
        account = prefs.get("mt5_account", "")
        password = prefs.get("mt5_password", "")
        server = prefs.get("mt5_server", "")
        
        init_kwargs = {}
        if mt5_path:
            init_kwargs["path"] = mt5_path
            
        if not mt5.initialize(**init_kwargs):
            raise RuntimeError(f"MT5 API: Initialization failed. {mt5.last_error()}")
            
        if account and password and server:
            if not mt5.login(int(account), password=password, server=server):
                raise RuntimeError(f"MT5 API: Login failed. {mt5.last_error()}")
        
        # Determine lot size
        volume = float(order.qty)
        
        # MT5 Order Types
        order_type = mt5.ORDER_TYPE_BUY if order.side.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        
        # Tick for current price
        tick = mt5.symbol_info_tick(order.symbol)
        if not tick:
            raise RuntimeError(f"MT5 API: Could not get tick for {order.symbol}")
            
        price = tick.ask if order.side.upper() == "BUY" else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": float(order.stop_loss) if order.stop_loss else 0.0,
            "tp": float(order.take_profit) if order.take_profit else 0.0,
            "deviation": 20,
            "magic": 234000,
            "comment": "Trade Pulse",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            err = f"MT5 Order Send Failed, retcode: {result.retcode}, comment: {result.comment}"
            raise RuntimeError(err)
            
        fill = FillEvent(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            qty=result.volume,
            fill_price=result.price,
            commission=0.0, # MT5 doesn't easily return commission in order_send, can be queried from deals later
            slippage=abs(result.price - price),
            mode=self.mode,
            metadata={"mt5_order": result.order, "mt5_deal": result.deal, "comment": result.comment}
        )
        self._fills.append(fill)
        return fill

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_all_fills(self) -> list[FillEvent]:
        return list(self._fills)

    @property
    def fill_count(self) -> int:
        return len(self._fills)

    def set_mode(self, mode: str) -> None:
        """Hot-swap execution mode (e.g. paper → live)."""
        self.mode = mode

    def __repr__(self) -> str:
        return (
            f"ExecutionEngine(mode={self.mode}, fills={self.fill_count}, "
            f"slippage={self.slippage_pct*100:.2f}%)"
        )
