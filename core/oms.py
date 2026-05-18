"""
core/oms.py
===========
Order Management System - receives OrderEvents and routes them to Execution.

Architecture Position:
    [Risk Manager] -> OrderEvent -> [OMS] -> [Execution Engine]

Responsibilities:
    - Order bookkeeping (pending, submitted, filled, cancelled, rejected)
    - Duplicate order prevention (same symbol + side already open)
    - Order modification and cancellation
    - Internal order ID generation (8-char UUID)
    - Session-level order history (in-memory, reset on restart)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid
import logging

from core.risk_manager import OrderEvent

logger = logging.getLogger("OMS")


# ---------------------------------------------------------------------------
# ManagedOrder - wraps OrderEvent with OMS lifecycle metadata
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
        return (
            "ManagedOrder("
            + self.order_id
            + " | " + self.order.symbol
            + " " + self.order.side
            + " | " + self.status + ")"
        )


# ---------------------------------------------------------------------------
# OMS
# ---------------------------------------------------------------------------

class OMS:
    """
    Order Management System.

    Stores all orders in-memory during the bot session.
    All orders are lost on restart (persistent storage is handled by Storage).

    Lifecycle:
        submit()        -> SUBMITTED
        update_status() -> FILLED | REJECTED | CANCELLED
        cancel()        -> CANCELLED  (only if PENDING or SUBMITTED)
    """

    def __init__(self, mode: str = "live"):
        self.mode = mode
        self._orders: dict[str, ManagedOrder] = {}   # order_id -> ManagedOrder

    # -------------------------------------------------------------------------
    # Core Interface
    # -------------------------------------------------------------------------

    def submit(self, order: OrderEvent) -> str:
        """
        Registers an order in the OMS book.

        Duplicate Prevention:
            If there is already an open (PENDING/SUBMITTED) order for the
            same symbol AND same side, the new order is rejected immediately
            to prevent double-exposure on the same instrument.

        Returns the internal order_id string.
        """
        # --- Duplicate check ---
        for managed in self._orders.values():
            if (
                managed.status in ("PENDING", "SUBMITTED")
                and managed.order.symbol == order.symbol
                and managed.order.side == order.side
            ):
                dup_id = managed.order_id
                logger.warning(
                    "OMS duplicate blocked: "
                    + order.side + " " + order.symbol
                    + " already open as order " + dup_id
                    + ". Skipping new submission."
                )
                # Return the existing order's ID so the caller can track it
                return dup_id

        order_id = self._new_order_id()
        self._orders[order_id] = ManagedOrder(
            order_id=order_id,
            order=order,
            status="SUBMITTED",
        )
        logger.info(
            "OMS submit: " + order_id
            + " | " + order.side + " " + str(round(order.qty, 2)) + "L " + order.symbol
            + " | SL=" + str(round(order.stop_loss, 4) if order.stop_loss else "N/A")
            + " TP=" + str(round(order.take_profit, 4) if order.take_profit else "N/A")
        )
        return order_id

    def update_status(
        self,
        order_id: str,
        status: str,
        broker_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Updates the lifecycle status of an order after execution.

        status options:
            FILLED    - MT5 confirmed execution
            REJECTED  - MT5 or broker rejected the order
            CANCELLED - manually or programmatically cancelled
        """
        if order_id not in self._orders:
            logger.warning("OMS update_status: order_id " + order_id + " not found.")
            return

        o = self._orders[order_id]
        prev_status = o.status
        o.status = status
        o.updated_at = datetime.utcnow()
        if broker_id:
            o.broker_order_id = broker_id
        if reason:
            o.rejection_reason = reason

        logger.info(
            "OMS status: " + order_id
            + " " + prev_status + " -> " + status
            + (" | broker_id=" + str(broker_id) if broker_id else "")
            + (" | reason=" + reason if reason else "")
        )

    def mark_rejected(self, order_id: str, reason: str) -> None:
        """
        Convenience method to mark an order as REJECTED with a reason.
        Called when MT5 returns an error on execution.
        """
        self.update_status(order_id, "REJECTED", reason=reason)
        logger.error(
            "OMS REJECTED: " + order_id + " | Reason: " + reason
        )

    def cancel(self, order_id: str) -> bool:
        """
        Cancels a PENDING or SUBMITTED order.
        Returns True if cancelled, False if already filled/rejected.
        """
        if order_id not in self._orders:
            return False

        o = self._orders[order_id]
        if o.status in ("PENDING", "SUBMITTED"):
            o.status = "CANCELLED"
            o.updated_at = datetime.utcnow()
            logger.info("OMS cancelled: " + order_id)
            return True

        logger.warning(
            "OMS cancel: order " + order_id
            + " is already " + o.status + " — cannot cancel."
        )
        return False

    def modify(self, order_id: str, **kwargs) -> bool:
        """
        Modifies fields of a PENDING or SUBMITTED order.
        Accepted kwargs: qty, stop_loss, take_profit, limit_price
        """
        if order_id not in self._orders:
            return False

        o = self._orders[order_id]
        if o.status not in ("PENDING", "SUBMITTED"):
            logger.warning(
                "OMS modify: order " + order_id
                + " is " + o.status + " — cannot modify."
            )
            return False

        for k, v in kwargs.items():
            if hasattr(o.order, k):
                setattr(o.order, k, v)
                logger.info("OMS modify: " + order_id + " set " + k + "=" + str(v))
            else:
                logger.warning("OMS modify: OrderEvent has no field '" + k + "' — skipped.")
        o.updated_at = datetime.utcnow()
        return True

    def get_status(self, order_id: str) -> Optional[str]:
        """Returns the current status string for an order_id, or None if not found."""
        return self._orders[order_id].status if order_id in self._orders else None

    # -------------------------------------------------------------------------
    # Query Helpers
    # -------------------------------------------------------------------------

    def get_all_orders(self) -> list[ManagedOrder]:
        return list(self._orders.values())

    def get_open_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values() if o.status in ("PENDING", "SUBMITTED")]

    def get_filled_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values() if o.status == "FILLED"]

    def get_rejected_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values() if o.status == "REJECTED"]

    def get_cancelled_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values() if o.status == "CANCELLED"]

    def has_open_position(self, symbol: str, side: str) -> bool:
        """Returns True if there is already a PENDING/SUBMITTED order for this symbol+side."""
        return any(
            o.order.symbol == symbol and o.order.side == side
            for o in self.get_open_orders()
        )

    def summary(self) -> dict:
        return {
            "total":     len(self._orders),
            "submitted": len([o for o in self._orders.values() if o.status == "SUBMITTED"]),
            "filled":    len(self.get_filled_orders()),
            "rejected":  len(self.get_rejected_orders()),
            "cancelled": len(self.get_cancelled_orders()),
        }

    @staticmethod
    def _new_order_id() -> str:
        return str(uuid.uuid4())[:8].upper()

    def __repr__(self) -> str:
        s = self.summary()
        return (
            "OMS(total=" + str(s["total"])
            + " | filled=" + str(s["filled"])
            + " | rejected=" + str(s["rejected"])
            + " | open=" + str(len(self.get_open_orders())) + ")"
        )
