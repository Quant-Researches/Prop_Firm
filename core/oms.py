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
from pathlib import Path
from typing import Optional
import json
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
    On startup, syncs with live MT5 positions so that post-restart duplicate
    checks and position counters reflect reality.

    Lifecycle:
        submit()        -> SUBMITTED
        update_status() -> FILLED | REJECTED | CANCELLED
        cancel()        -> CANCELLED  (only if PENDING or SUBMITTED)
    """

    def __init__(self, mode: str = "live"):
        self.mode = mode
        self._orders: dict[str, ManagedOrder] = {}   # order_id -> ManagedOrder
        self._sync_with_mt5()   # pre-populate from any open MT5 positions

    @staticmethod
    def _load_mt5_prefs() -> dict:
        prefs_path = Path(__file__).resolve().parent.parent / "config" / "user_prefs.json"
        if prefs_path.exists():
            try:
                return json.loads(prefs_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _sync_with_mt5(self) -> None:
        """
        Query mt5.positions_get() on startup and create synthetic FILLED
        ManagedOrder entries for each open position.
        This prevents the OMS from allowing a second trade in the same
        direction after a bot restart when a position is already live in MT5.
        """
        try:
            import MetaTrader5 as mt5
            from core.mt5_connection import MT5Connection

            prefs = self._load_mt5_prefs()
            if prefs.get("mt5_account") and prefs.get("mt5_password") and prefs.get("mt5_server"):
                MT5Connection.connect(
                    prefs.get("mt5_account", ""),
                    prefs.get("mt5_password", ""),
                    prefs.get("mt5_server", ""),
                    prefs.get("mt5_path", ""),
                )

            positions = mt5.positions_get()
            if not positions:
                return
            for pos in positions:
                side  = "BUY" if pos.type == 0 else "SELL"  # 0=BUY, 1=SELL in MT5
                order_id = f"MT5-{pos.ticket}"
                synth_order = OrderEvent(
                    symbol=pos.symbol,
                    side=side,
                    qty=pos.volume,
                    order_type="MARKET",
                    limit_price=pos.price_open,
                    stop_loss=pos.sl if pos.sl else None,
                    take_profit=pos.tp if pos.tp else None,
                )
                managed = ManagedOrder(
                    order_id=order_id,
                    order=synth_order,
                    status="FILLED",
                    broker_order_id=str(pos.ticket),
                )
                self._orders[order_id] = managed
                logger.info(
                    f"OMS startup sync: imported MT5 position {pos.ticket} "
                    f"| {side} {pos.volume}L {pos.symbol} @ {pos.price_open} as FILLED."
                )
        except Exception as e:
            logger.warning(f"OMS startup sync failed (MT5 not ready): {e}")

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
        # --- Duplicate check (includes FILLED from MT5 startup sync) ---
        for managed in self._orders.values():
            if (
                managed.status in ("PENDING", "SUBMITTED", "FILLED")
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
        """Returns True if there is already a PENDING/SUBMITTED/FILLED order for this symbol+side.
        Checks both OMS book AND live MT5 positions to handle any sync gaps.
        """
        # 1. Check OMS book (covers PENDING/SUBMITTED)
        oms_open = any(
            o.order.symbol == symbol and o.order.side == side
            for o in self.get_open_orders()
        )
        if oms_open:
            return True
        # 2. Check live MT5 positions (handles restarts and manual closes)
        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get(symbol=symbol)
            if positions:
                mt5_side_map = {0: "BUY", 1: "SELL"}
                for p in positions:
                    if mt5_side_map.get(p.type) == side:
                        return True
        except Exception:
            pass
        return False

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
