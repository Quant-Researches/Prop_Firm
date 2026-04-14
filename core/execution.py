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
        Routes to Live Dhan API or Simulation based on mode.
        """
        if self.mode == "Dhan Realtime":
            return self._execute_dhan(order, prefs)
        return self._execute_sim(order)
        
    def _execute_sim(self, order: OrderEvent) -> FillEvent:
        # Simulated fill price
        base_price = order.limit_price if order.limit_price else 100.0  # fallback
        
        # Apply slippage
        if order.side == "BUY":
            fill_price = base_price * (1 + self.slippage_pct)
        else:
            fill_price = base_price * (1 - self.slippage_pct)
            
        commission = order.qty * self.commission_per_lot

        fill = FillEvent(
            order_id=order.order_id if hasattr(order, 'order_id') else "SIM_" + datetime.utcnow().strftime("%H%M%S"),
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            fill_price=fill_price,
            commission=commission,
            slippage=abs(fill_price - base_price),
            mode=self.mode
        )
        self._fills.append(fill)
        return fill


    def _execute_dhan(self, order: OrderEvent, prefs: dict) -> FillEvent:
        if not prefs:
            raise ValueError("Preferences containing API keys required for Dhan Realtime execution.")
            
        client_id = prefs.get("dhan_client_id")
        access_token = prefs.get("dhan_api_key")
        
        url = "https://api.dhan.co/v2/orders"
        headers = {
            "access-token": access_token,
            "client-id": client_id,
            "Content-Type": "application/json"
        }
        
        # Dhan payload configuration
        exchange_segment = prefs.get("exchange_segment", "MCX_COMM")
        security_id = prefs.get("security_id", "")
        
        payload = {
            "dhanClientId": client_id,
            "correlationId": order.order_id,
            "transactionType": order.side.upper(),
            "exchangeSegment": exchange_segment,
            "productType": "INTRADAY",
            "orderType": "MARKET",
            "validity": "DAY",
            "securityId": str(security_id),
            "quantity": int(order.qty),
            "disclosedQuantity": 0,
            "price": 0,
            "triggerPrice": 0,
            "afterMarketOrder": False,
            "boProfitValue": 0,
            "boStopLossValue": 0,
            "drvExpiryDate": None,
            "drvOptionType": None,
            "drvStrikePrice": 0
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            data = response.json()
            
            # Parse responses
            broker_order_id = data.get("orderId", "UNKNOWN_DHAN_ID")
            status = data.get("orderStatus", "SUBMITTED")
            
            # Simulated instant market fill parsing 
            fill = FillEvent(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                fill_price=order.limit_price if order.limit_price else 100.0, # Estimated fill until full websocket sync
                commission=order.qty * self.commission_per_lot,
                slippage=0.0,
                mode=self.mode,
                metadata={"dhan_order_id": broker_order_id, "api_response": data, "api_status": status}
            )
            self._fills.append(fill)
            return fill
            
        except Exception as e:
            raise RuntimeError(f"Dhan API Order Error: {e}")

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
