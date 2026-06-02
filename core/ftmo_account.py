"""
core/ftmo_account.py — FTMO account metrics and daily reset (single source of truth).

FTMO uses two balances:
  - challenge_balance (initial_balance pref): max drawdown limit base (10%).
  - sod_balance (ftmo_sod_balance pref): start-of-day snapshot at Prague reset (5% daily loss).

Daily loss for FTMO = equity below today's SOD (closed + floating), not MT5 profit field.
Max drawdown = equity below challenge initial balance.

Daily reset: once per Prague calendar day after daily_reset_time, including after long sleeps.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("FtmoAccount")

PRAGUE_TZ = ZoneInfo("Europe/Prague")
DEFAULT_RESET_STATE = Path(__file__).resolve().parent.parent / "data" / "daily_reset_date.txt"


@dataclass(frozen=True)
class FtmoMetrics:
    """Computed FTMO risk numbers for guards and UI."""

    equity: float
    balance: float
    floating_pnl: float
    sod_balance: float
    challenge_balance: float
    daily_loss: float
    daily_loss_limit: float
    daily_loss_pct: float
    daily_remaining: float
    max_drawdown: float
    max_drawdown_limit: float
    max_drawdown_pct: float
    dd_remaining: float

    @property
    def daily_pnl(self) -> float:
        """Signed P&L vs SOD (negative = loss). Matches FTMO dashboard intuition."""
        return self.equity - self.sod_balance


def compute_ftmo_metrics(
    equity: float,
    sod_balance: float,
    challenge_balance: float,
    *,
    daily_loss_limit_pct: float = 0.05,
    max_drawdown_pct: float = 0.10,
    balance: float = 0.0,
    floating_pnl: float = 0.0,
) -> FtmoMetrics:
    """
    FTMO-aligned loss math.

    daily_loss     = max(0, sod - equity)   — loss since Prague day start
    max_drawdown   = max(0, challenge - equity) — loss since challenge start
    """
    sod = max(sod_balance, 0.01)
    challenge = max(challenge_balance, 0.01)
    eq = float(equity)

    daily_loss = max(0.0, sod - eq)
    daily_limit = challenge * daily_loss_limit_pct
    daily_pct = (daily_loss / challenge) * 100.0
    daily_rem = max(0.0, daily_limit - daily_loss)

    max_dd = max(0.0, challenge - eq)
    max_dd_limit = challenge * max_drawdown_pct
    max_dd_pct = (max_dd / challenge) * 100.0
    dd_rem = max(0.0, max_dd_limit - max_dd)

    return FtmoMetrics(
        equity=eq,
        balance=float(balance or eq),
        floating_pnl=float(floating_pnl),
        sod_balance=sod,
        challenge_balance=challenge,
        daily_loss=daily_loss,
        daily_loss_limit=daily_limit,
        daily_loss_pct=daily_pct,
        daily_remaining=daily_rem,
        max_drawdown=max_dd,
        max_drawdown_limit=max_dd_limit,
        max_drawdown_pct=max_dd_pct,
        dd_remaining=dd_rem,
    )


def snapshot_from_mt5_account(
    acc: Any,
    sod_balance: float,
    challenge_balance: float,
    **kwargs: Any,
) -> FtmoMetrics:
    """Build metrics from MetaTrader5 account_info() struct."""
    equity = float(acc.equity)
    balance = float(acc.balance)
    floating = float(getattr(acc, "profit", 0.0) or 0.0)
    return compute_ftmo_metrics(
        equity=equity,
        sod_balance=sod_balance,
        challenge_balance=challenge_balance,
        balance=balance,
        floating_pnl=floating,
        **kwargs,
    )


# ── Daily reset (Prague calendar day) ─────────────────────────────────────────

def prague_today() -> date:
    return datetime.now(PRAGUE_TZ).date()


def _parse_reset_time(reset_time: str) -> tuple[int, int]:
    parts = (reset_time or "00:00").strip().split(":")
    hh = int(parts[0]) if parts else 0
    mm = int(parts[1]) if len(parts) > 1 else 0
    return hh, mm


def last_reset_prague_date(state_path: Path = DEFAULT_RESET_STATE) -> Optional[date]:
    try:
        if state_path.exists():
            raw = state_path.read_text(encoding="utf-8").strip()
            if raw:
                return date.fromisoformat(raw)
    except Exception:
        pass
    return None


def mark_daily_reset_done(state_path: Path = DEFAULT_RESET_STATE) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(prague_today().isoformat(), encoding="utf-8")


def should_run_daily_reset(
    reset_time: str = "00:00",
    state_path: Path = DEFAULT_RESET_STATE,
) -> bool:
    """
    True when a Prague-day reset is due.

    Runs on the first daemon wake *after* daily_reset_time on a new Prague date.
    Survives multi-hour sleeps (no HH:MM polling required).
    """
    today = prague_today()
    if last_reset_prague_date(state_path) == today:
        return False

    now = datetime.now(PRAGUE_TZ)
    hh, mm = _parse_reset_time(reset_time)
    reset_dt = datetime(today.year, today.month, today.day, hh, mm, tzinfo=PRAGUE_TZ)
    return now >= reset_dt


def persist_sod_balance(prefs_path: Path, sod_balance: float) -> dict:
    """Write ftmo_sod_balance into user_prefs.json; return updated prefs dict."""
    prefs: dict = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
        except Exception:
            prefs = {}
    prefs["ftmo_sod_balance"] = float(sod_balance)
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    return prefs
