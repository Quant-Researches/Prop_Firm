"""
core/portfolio.py
=================
Portfolio — tracks positions, cash balance, and PnL after each fill.

Architecture Position:
    [Execution Engine] → FillEvent → [Portfolio]

Responsibilities:
    - Maintain open positions per symbol
    - Track realised and unrealised PnL
    - Update available cash / margin
    - Emit portfolio snapshots for UI and storage

TODO: Implement on_fill() and mark_to_market() with real PnL math.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.execution import FillEvent


# ---------------------------------------------------------------------------
# Internal models
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """Represents a single open position in a symbol."""
    symbol: str
    side: str                   # "LONG" | "SHORT"
    qty: float
    avg_price: float
    opened_at: datetime = field(default_factory=datetime.utcnow)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0

    def mark_to_market(self, current_price: float) -> float:
        """
        Update unrealised PnL using the latest market price.
        Returns the updated unrealised PnL value.
        """
        if self.side == "LONG":
            self.unrealised_pnl = (current_price - self.avg_price) * self.qty
        else:
            self.unrealised_pnl = (self.avg_price - current_price) * self.qty
        return self.unrealised_pnl

    def __repr__(self) -> str:
        return (
            f"Position({self.symbol} | {self.side} {self.qty} "
            f"@ {self.avg_price:.2f} | uPnL={self.unrealised_pnl:.2f})"
        )


@dataclass
class PortfolioSnapshot:
    """Point-in-time snapshot of the entire portfolio state."""
    timestamp: datetime
    cash: float
    equity: float               # cash + market value of all positions
    total_pnl: float
    realised_pnl: float
    unrealised_pnl: float
    open_positions: int
    total_trades: int


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class Portfolio:
    """
    Maintains the account state throughout the trading session.

    Parameters
    ----------
    initial_capital : starting cash balance
    """

    def __init__(self, initial_capital: float = 100_000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}   # symbol → Position
        self._trade_history: list[FillEvent] = []
        self._total_realised_pnl: float = 0.0

    # ------------------------------------------------------------------
    # Core Interface — implement these
    # ------------------------------------------------------------------

    def on_fill(self, fill: FillEvent) -> None:
        """
        Update portfolio state when an order is filled.
        """
        self._trade_history.append(fill)
        self.cash -= fill.commission

        fill_dir = 1 if fill.side == "BUY" else -1
        fill_qty = fill.qty

        if fill.symbol not in self.positions:
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                side="LONG" if fill_dir == 1 else "SHORT",
                qty=fill_qty,
                avg_price=fill.fill_price
            )
            return

        pos = self.positions[fill.symbol]
        pos_dir = 1 if pos.side == "LONG" else -1

        if pos_dir == fill_dir:
            # Adding
            new_qty = pos.qty + fill_qty
            pos.avg_price = ((pos.avg_price * pos.qty) + (fill.fill_price * fill_qty)) / new_qty
            pos.qty = new_qty
        else:
            # Reducing or Reversing
            if fill_qty <= pos.qty:
                rpnl = (fill.fill_price - pos.avg_price) * fill_qty if pos_dir == 1 else (pos.avg_price - fill.fill_price) * fill_qty
                pos.realised_pnl += rpnl
                self._total_realised_pnl += rpnl
                self.cash += rpnl
                
                pos.qty -= fill_qty
                if pos.qty == 0:
                    del self.positions[fill.symbol]
            else:
                # Reversing position
                close_qty = pos.qty
                rpnl = (fill.fill_price - pos.avg_price) * close_qty if pos_dir == 1 else (pos.avg_price - fill.fill_price) * close_qty
                self._total_realised_pnl += rpnl
                self.cash += rpnl
                
                new_qty = fill_qty - close_qty
                self.positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    side="LONG" if fill_dir == 1 else "SHORT",
                    qty=new_qty,
                    avg_price=fill.fill_price
                )

    def mark_to_market(self, prices: dict[str, float]) -> None:
        """
        Update unrealised PnL for all open positions.
        prices: {symbol → current_market_price}
        """
        for sym, pos in self.positions.items():
            if sym in prices:
                pos.mark_to_market(prices[sym])

    def get_summary(self) -> PortfolioSnapshot:
        """Return a PortfolioSnapshot with current account state."""
        return PortfolioSnapshot(
            timestamp=datetime.utcnow(),
            cash=self.cash,
            equity=self.equity,
            total_pnl=self.total_pnl,
            realised_pnl=self._total_realised_pnl,
            unrealised_pnl=sum(p.unrealised_pnl for p in self.positions.values()),
            open_positions=len(self.positions),
            total_trades=len(self._trade_history)
        )


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def equity(self) -> float:
        """Cash + unrealised PnL of all open positions."""
        return self.cash + sum(p.unrealised_pnl for p in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self._total_realised_pnl + sum(
            p.unrealised_pnl for p in self.positions.values()
        )

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    @property
    def trade_count(self) -> int:
        return len(self._trade_history)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def __repr__(self) -> str:
        return (
            f"Portfolio(cash={self.cash:.2f}, equity={self.equity:.2f}, "
            f"pnl={self.total_pnl:.2f}, positions={self.open_position_count})"
        )
