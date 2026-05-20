"""
core/storage.py
===============
Storage — persists trades, orders, and PnL to disk.

Architecture Position:
    [Portfolio] → [Storage] ← (reads) [UI / Reporting]

Supported Formats:
    - JSON  : simple human-readable, default for trades/orders
    - CSV   : for PnL timeseries, compatible with pandas/Excel

TODO: Implement save_trade(), save_order(), save_pnl_snapshot(), and load_history().
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import json
import csv

from core.execution import FillEvent
from core.risk_manager import OrderEvent


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_TRADES_FILE  = "data/trades.json"
DEFAULT_ORDERS_FILE  = "data/orders.json"
DEFAULT_PNL_FILE     = "data/pnl_history.csv"
DEFAULT_EVENTS_FILE  = "data/events.jsonl"


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class Storage:
    """
    Lightweight persistence layer for the trading session.

    All paths are relative to the project root unless absolute paths are given.

    Parameters
    ----------
    trades_file  : path for trade (fill) records
    orders_file  : path for order records
    pnl_file     : path for PnL timeseries (CSV)
    """

    def __init__(
        self,
        execution_mode: str = "MetaTrader5",
        trades_file: str = DEFAULT_TRADES_FILE,
        orders_file: str = DEFAULT_ORDERS_FILE,
        pnl_file: str = DEFAULT_PNL_FILE,
        events_file: str = DEFAULT_EVENTS_FILE,
    ):
        self.execution_mode = execution_mode
        self.base_dir = Path("data")

        self.events_path      = Path(events_file)
        self.trades_file_name = Path(trades_file).name
        self.orders_file_name = Path(orders_file).name
        self.pnl_file_name    = Path(pnl_file).name

        self.trades_path = self.base_dir / self.trades_file_name
        self.orders_path = self.base_dir / self.orders_file_name
        self.pnl_path    = self.base_dir / self.pnl_file_name
        self._ensure_dirs()

    def set_execution_mode(self, mode: str) -> None:
        """Update execution mode label (paths are always data/ for MT5 live trading)."""
        self.execution_mode = mode
        # Paths are fixed to data/ — Dhan routing removed
        self.trades_path = self.base_dir / self.trades_file_name
        self.orders_path = self.base_dir / self.orders_file_name
        self.pnl_path    = self.base_dir / self.pnl_file_name
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Core Interface — implement these
    # ------------------------------------------------------------------

    def log_event(self, kind: str, msg: str) -> None:
        """
        Append a structured log event to events.jsonl.
        Used heavily by main.py so app.py can stream live logs.
        """
        evt = {
            "timestamp": datetime.now().isoformat(),
            "kind": kind,
            "msg": msg
        }
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evt) + "\n")

    def save_trade(self, fill: FillEvent) -> None:
        """
        Append a FillEvent to the trades JSON file.
        """
        trades = self.load_trades()
        # Convert dataclass to dict, handle datetime serialization
        data = asdict(fill)
        data["timestamp"] = data["timestamp"].isoformat()
        trades.append(data)
        
        with self.trades_path.open("w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2)

    def save_order(self, order: OrderEvent, order_id: str, status: str) -> None:
        """
        Append or update an OrderEvent record in the orders JSON file.
        """
        orders = self.load_orders()
        
        # Check if updating an existing order
        found = False
        for o in orders:
            if o.get("order_id") == order_id:
                o["status"] = status
                o["updated_at"] = datetime.now().isoformat()
                found = True
                break
                
        if not found:
            data = asdict(order)
            rec = {
                "order_id": order_id,
                "status": status,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "order": data
            }
            # Handle datetime nested in order
            if "timestamp" in data and isinstance(data["timestamp"], datetime):
                data["timestamp"] = data["timestamp"].isoformat()
            orders.append(rec)
            
        with self.orders_path.open("w", encoding="utf-8") as f:
            json.dump(orders, f, indent=2)

    def save_pnl_snapshot(
        self, timestamp: datetime, equity: float, cash: float,
        realised_pnl: float, unrealised_pnl: float,
        open_positions: int = 0, total_trades: int = 0
    ) -> None:
        """
        Append one row to the PnL CSV timeseries.
        """
        file_exists = self.pnl_path.exists()
        with self.pnl_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "equity", "cash", "realised_pnl", "unrealised_pnl", "open_positions", "total_trades"])
            writer.writerow([
                timestamp.isoformat(),
                round(equity, 2),
                round(cash, 2),
                round(realised_pnl, 2),
                round(unrealised_pnl, 2),
                open_positions,
                total_trades
            ])

    def load_trades(self) -> list[dict]:
        """Load all trade records from disk."""
        if not self.trades_path.exists():
            return []
        try:
            with self.trades_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def load_orders(self) -> list[dict]:
        """Load all order records from disk."""
        if not self.orders_path.exists():
            return []
        try:
            with self.orders_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def load_pnl_history(self) -> list[dict]:
        """Load the PnL CSV as a list of row dicts."""
        if not self.pnl_path.exists():
            return []
        try:
            rows = []
            with self.pnl_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse numeric fields
                    for k in ["equity", "cash", "realised_pnl", "unrealised_pnl"]:
                        row[k] = float(row[k]) if row[k] else 0.0
                    for k in ["open_positions", "total_trades"]:
                        if k in row: row[k] = int(row[k]) if row[k] else 0
                    rows.append(row)
            return rows
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """Create parent directories if they don't exist."""
        for p in (self.trades_path, self.orders_path, self.pnl_path, self.events_path):
            p.parent.mkdir(parents=True, exist_ok=True)

    def clear_session(self) -> None:
        """
        Delete all data files (use carefully — typically only in test runs).
        """
        for p in (self.trades_path, self.orders_path, self.pnl_path, self.events_path):
            if p.exists():
                p.unlink()

    def file_sizes(self) -> dict[str, str]:
        """Return human-readable file sizes for each data file."""
        def _fmt(p: Path) -> str:
            if p.exists():
                size = p.stat().st_size
                return f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            return "not found"
        return {
            "trades":  _fmt(self.trades_path),
            "orders":  _fmt(self.orders_path),
            "pnl_csv": _fmt(self.pnl_path),
            "events":  _fmt(self.events_path),
        }

    def __repr__(self) -> str:
        return (
            f"Storage(trades={self.trades_path}, "
            f"orders={self.orders_path}, pnl={self.pnl_path}, events={self.events_path})"
        )
