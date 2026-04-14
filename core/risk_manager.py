"""
core/risk_manager.py
====================
Risk Manager — validates SignalEvents and produces OrderEvents.

Architecture Position:
    [Strategy] → SignalEvent → [Risk Manager] → OrderEvent → [OMS]

Responsibilities:
    - Position sizing (fixed qty, % risk, Kelly, volatility-adjusted)
    - Max drawdown / max open positions guard
    - Signal filter (min strength threshold, cooldown between trades)
    - SL/TP distance checks

TODO: Implement evaluate() with real risk rules and position sizing formulas.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.strategy import SignalEvent
import requests
import logging

logger = logging.getLogger("RiskManager")


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass
class OrderEvent:
    """
    Carries a validated order ready to be submitted to OMS.
    """
    symbol: str
    side: str                   # "BUY" | "SELL"
    qty: float                  # number of units / lots
    order_type: str             # "MARKET" | "LIMIT" | "SL_MARKET" | "SL_LIMIT"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    signal_ref: Optional[SignalEvent] = None   # back-reference to originating signal
    tag: str = ""               # label / strategy tag for reporting

    def __repr__(self) -> str:
        return (
            f"OrderEvent({self.symbol} | {self.side} {self.qty} "
            f"@ {self.order_type} | SL={self.stop_loss} TP={self.take_profit})"
        )


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class RiskManager:
    """
    Evaluates signals against risk constraints and returns sized orders.

    Parameters
    ----------
    capital         : total account capital (₹ or $)
    risk_pct        : fraction of capital to risk per trade (0.01 = 1%)
    max_positions   : maximum concurrent open positions
    min_strength    : minimum signal strength to pass through (0.0–1.0)
    """

    def __init__(
        self,
        capital: float = 100_000.0,
        risk_pct: float = 0.01,
        max_positions: int = 5,
        min_strength: float = 0.5,
    ):
        self.capital = capital
        self.risk_pct = risk_pct
        self.max_positions = max_positions
        self.min_strength = min_strength
        self._open_positions: int = 0

    # ------------------------------------------------------------------
    # Core Interface — implement this
    # ------------------------------------------------------------------

    def evaluate(self, signal: SignalEvent) -> Optional[OrderEvent]:
        """
        Validate signal and compute position size.
        Returns an OrderEvent on approval, None if signal is rejected.

        Rejection reasons (implement checks):
          - signal.strength < self.min_strength
          - self._open_positions >= self.max_positions
          - insufficient margin / capital
          - symbol already has open position in same direction
        """
        raise NotImplementedError("RiskManager.evaluate() — implement risk rules")

    # ------------------------------------------------------------------
    # Data Fetching
    # ------------------------------------------------------------------

    @staticmethod
    def fetch_fund_limits(client_id: str, access_token: str) -> dict:
        """
        Queries Dhan's GET /v2/fundlimit endpoint.
        Returns available balance and margin details for the trading account.

        Returns
        -------
        dict: containing keys like "availabelBalance", "utilizedAmount",
              "sodLimit", "collateralAmount", etc. Empty dict on failure.
        """
        if not client_id or not access_token:
            logger.warning("Missing API keys for fund limits.")
            return {}

        headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
            "client-id": client_id,
        }

        try:
            res = requests.get(
                "https://api.dhan.co/v2/fundlimit",
                headers=headers,
                timeout=10
            )
            if res.status_code == 200:
                data = res.json()
                logger.info(f"Fund Limits: Available={data.get('availabelBalance')}, Utilized={data.get('utilizedAmount')}")
                return data
            else:
                logger.error(f"Dhan Fund Limits error: HTTP {res.status_code} - {res.text[:200]}")
                return {}
        except Exception as e:
            logger.error(f"Failed to fetch fund limits: {e}")
            return {}

    @staticmethod
    def fetch_live_margin_info(
        client_id: str,
        access_token: str,
        security_id: str,
        exchange_segment: str,
        transaction_type: str = "BUY",
        quantity: int = 1,
        price: float = 0.0
    ) -> dict:
        """
        Queries Dhan's live Margin Calculator API.
        Useful for determining leverage allowed and pre-trade margin requirements.
        
        Returns
        -------
        dict: containing keys like "totalMargin", "leverage", "spanMargin", etc.
              Returns empty dict on failure.
        """
        if not client_id or not access_token:
            logger.warning("Missing API keys for margin calculation.")
            return {}

        headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
            "client-id": client_id,
        }
        
        # Dhan margin calculator format
        payload = {
            "dhanClientId": client_id,
            "exchangeSegment": exchange_segment,
            "transactionType": transaction_type.upper(),
            "quantity": quantity,
            "productType": "MARGIN",
            "securityId": str(security_id),
            "price": price
        }

        try:
            endpoint = "https://api.dhan.co/v2/margincalculator"
            res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                logger.debug(f"Margin Info for {security_id}: Margin={data.get('totalMargin')}, Lev={data.get('leverage')}")
                return data
            else:
                logger.error(f"Dhan Margin API error: HTTP {res.status_code} - {res.text[:200]}")
                return {}
        except Exception as e:
            logger.error(f"Failed to fetch margin info: {e}")
            return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def update_capital(self, new_capital: float) -> None:
        """Called by Portfolio after each fill to keep capital in sync."""
        self.capital = new_capital

    def increment_positions(self) -> None:
        self._open_positions += 1

    def decrement_positions(self) -> None:
        self._open_positions = max(0, self._open_positions - 1)

    @property
    def open_positions(self) -> int:
        return self._open_positions

    def __repr__(self) -> str:
        return (
            f"RiskManager(capital={self.capital:.2f}, risk_pct={self.risk_pct}, "
            f"max_pos={self.max_positions}, open={self._open_positions})"
        )
