"""
core/oms.py
===========
Order Management System — receives OrderEvents and routes them to Execution.

Architecture Position:
    [Risk Manager] → OrderEvent → [OMS] → [Execution Engine]

Responsibilities:
    - Order bookkeeping (pending, filled, cancelled, rejected)
    - Duplicate order prevention
    - Order modification / cancellation
    - Internal order ID generation

TODO: Implement submit(), cancel(), modify(), and status() with real broker OMS logic.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

from core.risk_manager import OrderEvent


# ---------------------------------------------------------------------------
# Internal models
# ---------------------------------------------------------------------------

@dataclass
class ManagedOrder:
    """Wraps an OrderEvent with OMS tracking metadata."""
    order_id: str
    order: OrderEvent
    status: str = "PENDING"     # PENDING | SUBMITTED | FILLED | CANCELLED | REJECTED
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    broker_order_id: Optional[str] = None
    rejection_reason: Optional[str] = None

    def __repr__(self) -> str:
        return f"ManagedOrder({self.order_id} | {self.order.symbol} | {self.status})"


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class OMS:
    """
    Order Management System.

    Stores all orders in memory during the bot session.
    Call submit() to enter an order into the lifecycle.

    Parameters
    ----------
    mode : "backtest" | "paper" | "live"
    """

    def __init__(self, mode: str = "live"):
        self.mode = mode
        self._orders: dict[str, ManagedOrder] = {}   # order_id → ManagedOrder

    # ------------------------------------------------------------------
    # Core Interface — implement these
    # ------------------------------------------------------------------

    def submit(self, order: OrderEvent) -> str:
        """
        Validate and submit an order to the OMS book.
        Returns the internal order_id.
        """
        order_id = self.new_order_id()
        self._orders[order_id] = ManagedOrder(
            order_id=order_id,
            order=order,
            status="SUBMITTED"
        )
        return order_id

    def update_status(self, order_id: str, status: str, broker_id: Optional[str] = None, reason: Optional[str] = None) -> None:
        """
        Update order state post-execution.
        """
        if order_id in self._orders:
            o = self._orders[order_id]
            o.status = status
            o.updated_at = datetime.utcnow()
            if broker_id: o.broker_order_id = broker_id
            if reason:    o.rejection_reason = reason

    def cancel(self, order_id: str) -> bool:
        """
        Cancel a pending/submitted order.
        """
        if order_id not in self._orders:
            return False
            
        o = self._orders[order_id]
        if o.status in ("PENDING", "SUBMITTED"):
            o.status = "CANCELLED"
            o.updated_at = datetime.utcnow()
            return True
        return False

    def modify(self, order_id: str, **kwargs) -> bool:
        """
        Modify price/qty of a pending order.
        """
        if order_id not in self._orders:
            return False
            
        o = self._orders[order_id]
        if o.status in ("PENDING", "SUBMITTED"):
            # Update the underlying order event
            for k, v in kwargs.items():
                if hasattr(o.order, k):
                    setattr(o.order, k, v)
            o.updated_at = datetime.utcnow()
            return True
        return False

    def status(self, order_id: str) -> Optional[str]:
        """Return the current status string for a given order_id."""
        return self._orders[order_id].status if order_id in self._orders else None


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_all_orders(self) -> list[ManagedOrder]:
        return list(self._orders.values())

    def get_open_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values() if o.status in ("PENDING", "SUBMITTED")]

    def get_filled_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values() if o.status == "FILLED"]

    @staticmethod
    def new_order_id() -> str:
        return str(uuid.uuid4())[:8].upper()

    def __repr__(self) -> str:
        return (
            f"OMS(mode={self.mode}, total={len(self._orders)}, "
            f"open={len(self.get_open_orders())})"
        )
