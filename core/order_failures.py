"""
core/order_failures.py
======================
Central registry for order / trade failure codes, headings, and suggestions.
Used by engine, risk_manager, OMS paths, and notifier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ── Failure codes ─────────────────────────────────────────────────────────────

# Pipeline / data
DATA_FETCH_FAILED = "DATA_FETCH_FAILED"
PIPELINE_EMPTY = "PIPELINE_EMPTY"
PIPELINE_CRASH = "PIPELINE_CRASH"

# FTMO risk guard
FTMO_DAILY_LOSS_LIMIT = "FTMO_DAILY_LOSS_LIMIT"
FTMO_MAX_DRAWDOWN = "FTMO_MAX_DRAWDOWN"
FTMO_DAILY_BUDGET = "FTMO_DAILY_BUDGET"
FTMO_DD_BUFFER = "FTMO_DD_BUFFER"
FTMO_MAX_POSITIONS = "FTMO_MAX_POSITIONS"
FTMO_NEWS_BLACKOUT = "FTMO_NEWS_BLACKOUT"
FTMO_RULES_BLOCKED = "FTMO_RULES_BLOCKED"  # generic fallback
FTMO_WARNING = "FTMO_WARNING"

# Pre-order MT5 / strategy data
MT5_SYMBOL_UNAVAILABLE = "MT5_SYMBOL_UNAVAILABLE"
MT5_ACCOUNT_UNAVAILABLE = "MT5_ACCOUNT_UNAVAILABLE"
STRATEGY_ATR_INVALID = "STRATEGY_ATR_INVALID"

# Order builder (RiskManager.build_order)
ORDER_SPREAD_TOO_HIGH = "ORDER_SPREAD_TOO_HIGH"
ORDER_SL_TOO_WIDE = "ORDER_SL_TOO_WIDE"
ORDER_INVALID_TICK_DATA = "ORDER_INVALID_TICK_DATA"
ORDER_INVALID_RISK_MATH = "ORDER_INVALID_RISK_MATH"
ORDER_INVALID_SIGNAL = "ORDER_INVALID_SIGNAL"
ORDER_BUILD_FAILED = "ORDER_BUILD_FAILED"  # unknown build failure

# OMS
OMS_DUPLICATE_POSITION = "OMS_DUPLICATE_POSITION"

# MT5 execution
MT5_CONNECTION_FAILED = "MT5_CONNECTION_FAILED"
MT5_SYMBOL_NOT_VISIBLE = "MT5_SYMBOL_NOT_VISIBLE"
MT5_TICK_UNAVAILABLE = "MT5_TICK_UNAVAILABLE"
MT5_ORDER_SEND_NULL = "MT5_ORDER_SEND_NULL"
MT5_AUTOTRADING_DISABLED = "MT5_AUTOTRADING_DISABLED"
MT5_FILLING_MODE = "MT5_FILLING_MODE"
MT5_INVALID_LOT = "MT5_INVALID_LOT"
MT5_INVALID_STOPS = "MT5_INVALID_STOPS"
MT5_INSUFFICIENT_MARGIN = "MT5_INSUFFICIENT_MARGIN"
MT5_MARKET_CLOSED = "MT5_MARKET_CLOSED"
MT5_EXECUTION_REJECTED = "MT5_EXECUTION_REJECTED"

# System
SYSTEM_INFO = "SYSTEM_INFO"
SYSTEM_WARNING = "SYSTEM_WARNING"
DAILY_RESET_FAILED = "DAILY_RESET_FAILED"


@dataclass
class FailureMeta:
    heading: str
    category: str
    suggestions: tuple[str, ...] = ()
    play_sound: bool = True


FAILURE_META: dict[str, FailureMeta] = {
    DATA_FETCH_FAILED: FailureMeta(
        "DATA FEED FAILED",
        "Pipeline",
        ("Verify MT5 is running and the symbol is in MarketWatch.", "Check internet and broker server status."),
    ),
    PIPELINE_EMPTY: FailureMeta(
        "PIPELINE EMPTY RESULT",
        "Pipeline",
        ("Check MT5 connection and bar_count in Settings.",),
    ),
    PIPELINE_CRASH: FailureMeta(
        "PIPELINE CRASH",
        "Pipeline",
        ("Check data/events.jsonl for the stack trace.", "Restart the daemon after fixing the error."),
    ),
    FTMO_DAILY_LOSS_LIMIT: FailureMeta(
        "FTMO BLOCK — DAILY LOSS LIMIT",
        "FTMO Risk Guard",
        ("Stop trading for today. Further loss may breach the account.",),
    ),
    FTMO_MAX_DRAWDOWN: FailureMeta(
        "FTMO BLOCK — MAX DRAWDOWN",
        "FTMO Risk Guard",
        ("Do not place new trades. Account is at suspension risk.",),
    ),
    FTMO_DAILY_BUDGET: FailureMeta(
        "FTMO BLOCK — DAILY BUDGET",
        "FTMO Risk Guard",
        ("Reduce risk per trade or pause until the next FTMO day.",),
    ),
    FTMO_DD_BUFFER: FailureMeta(
        "FTMO BLOCK — DRAWDOWN BUFFER",
        "FTMO Risk Guard",
        ("No new trades until drawdown buffer recovers.",),
    ),
    FTMO_MAX_POSITIONS: FailureMeta(
        "FTMO BLOCK — MAX POSITIONS",
        "FTMO Risk Guard",
        ("Close an existing position in MT5 before opening a new one.",),
    ),
    FTMO_NEWS_BLACKOUT: FailureMeta(
        "FTMO BLOCK — NEWS BLACKOUT",
        "FTMO Risk Guard",
        ("Wait until the news window clears (±2 min around HIGH-impact events).",),
    ),
    FTMO_RULES_BLOCKED: FailureMeta(
        "FTMO BLOCK — RISK GUARD",
        "FTMO Risk Guard",
        ("Review FTMO dashboard and data/events.jsonl.",),
    ),
    FTMO_WARNING: FailureMeta(
        "FTMO WARNING — APPROACHING LIMITS",
        "FTMO Risk Guard",
        ("Trade with caution; limits not yet breached.",),
        play_sound=False,
    ),
    MT5_SYMBOL_UNAVAILABLE: FailureMeta(
        "MT5 BLOCK — SYMBOL NOT FOUND",
        "Broker Data",
        ("Open MT5 → MarketWatch → Show All → add the symbol.",),
    ),
    MT5_ACCOUNT_UNAVAILABLE: FailureMeta(
        "MT5 BLOCK — ACCOUNT OFFLINE",
        "Broker Data",
        ("Re-check MT5 login in Settings and restart the daemon.",),
    ),
    STRATEGY_ATR_INVALID: FailureMeta(
        "STRATEGY BLOCK — INVALID ATR",
        "Strategy Data",
        ("Check indicator warm-up (bar_count) and candle history.",),
    ),
    ORDER_SPREAD_TOO_HIGH: FailureMeta(
        "ORDER BLOCKED — SPREAD TOO HIGH",
        "Order Builder",
        ("Spread exceeded 10% of ATR. Retry after liquidity improves (avoid news/open).",),
    ),
    ORDER_SL_TOO_WIDE: FailureMeta(
        "ORDER BLOCKED — STOP LOSS TOO WIDE",
        "Order Builder",
        ("Structure + ATR produced SL > 5% of price. Wait for tighter structure or lower volatility.",),
    ),
    ORDER_INVALID_TICK_DATA: FailureMeta(
        "ORDER BLOCKED — INVALID TICK DATA",
        "Order Builder",
        ("Check symbol tick_size and tick_value in MT5 symbol specification.",),
    ),
    ORDER_INVALID_RISK_MATH: FailureMeta(
        "ORDER BLOCKED — POSITION SIZING FAILED",
        "Order Builder",
        ("Risk per lot is zero or negative — verify tick data and stop distance.",),
    ),
    ORDER_INVALID_SIGNAL: FailureMeta(
        "ORDER BLOCKED — INVALID SIGNAL",
        "Order Builder",
        ("Internal error: signal was not BUY or SELL.",),
    ),
    ORDER_BUILD_FAILED: FailureMeta(
        "ORDER BLOCKED — BUILD FAILED",
        "Order Builder",
        ("See data/events.jsonl for the exact build_order log line.",),
    ),
    OMS_DUPLICATE_POSITION: FailureMeta(
        "OMS BLOCK — DUPLICATE POSITION",
        "Order Management",
        ("A position for this symbol and direction is already open.",),
    ),
    MT5_CONNECTION_FAILED: FailureMeta(
        "MT5 EXECUTION FAILED — NO CONNECTION",
        "MT5 Execution",
        ("Ensure MT5 terminal is open and logged in. Restart daemon.",),
    ),
    MT5_SYMBOL_NOT_VISIBLE: FailureMeta(
        "MT5 EXECUTION FAILED — SYMBOL",
        "MT5 Execution",
        ("Add symbol to MarketWatch before trading.",),
    ),
    MT5_TICK_UNAVAILABLE: FailureMeta(
        "MT5 EXECUTION FAILED — NO PRICE TICK",
        "MT5 Execution",
        ("Wait for live quotes; check symbol is tradable now.",),
    ),
    MT5_ORDER_SEND_NULL: FailureMeta(
        "MT5 EXECUTION FAILED — NO RESPONSE",
        "MT5 Execution",
        ("Connection may have dropped. Check MT5 and retry.",),
    ),
    MT5_AUTOTRADING_DISABLED: FailureMeta(
        "MT5 EXECUTION FAILED — AUTOTRADING OFF",
        "MT5 Execution",
        ("Enable AutoTrading (green robot icon) in the MT5 toolbar.",),
    ),
    MT5_FILLING_MODE: FailureMeta(
        "MT5 EXECUTION FAILED — FILLING MODE",
        "MT5 Execution",
        ("Broker rejected order filling type. Check symbol trade settings.",),
    ),
    MT5_INVALID_LOT: FailureMeta(
        "MT5 EXECUTION FAILED — INVALID LOT SIZE",
        "MT5 Execution",
        ("Adjust lot to symbol min/max/step in MT5.",),
    ),
    MT5_INVALID_STOPS: FailureMeta(
        "MT5 EXECUTION FAILED — INVALID SL/TP",
        "MT5 Execution",
        ("SL/TP may be too close to entry. Check broker stop level.",),
    ),
    MT5_INSUFFICIENT_MARGIN: FailureMeta(
        "MT5 EXECUTION FAILED — INSUFFICIENT MARGIN",
        "MT5 Execution",
        ("Reduce lot size or close other positions to free margin.",),
    ),
    MT5_MARKET_CLOSED: FailureMeta(
        "MT5 EXECUTION FAILED — MARKET CLOSED",
        "MT5 Execution",
        ("Wait for the trading session to open.",),
    ),
    MT5_EXECUTION_REJECTED: FailureMeta(
        "MT5 EXECUTION FAILED — BROKER REJECTED",
        "MT5 Execution",
        ("Check MT5 Experts/Journal tab for broker message.",),
    ),
    SYSTEM_INFO: FailureMeta(
        "SYSTEM UPDATE",
        "System",
        play_sound=False,
    ),
    SYSTEM_WARNING: FailureMeta(
        "SYSTEM WARNING",
        "System",
        play_sound=False,
    ),
    DAILY_RESET_FAILED: FailureMeta(
        "DAILY RESET FAILED",
        "System",
        ("SOD balance was NOT saved. Fix MT5 connection and restart daemon.",),
    ),
}


@dataclass
class OrderBuildResult:
    order: Optional[object] = None  # OrderEvent when success
    failure_code: str = ""
    message: str = ""


def meta_for(code: str) -> FailureMeta:
    return FAILURE_META.get(code, FAILURE_META[ORDER_BUILD_FAILED])


def classify_ftmo_block(block_reason: str) -> str:
    """Map evaluate_ftmo_rules block_reason to a specific failure code."""
    r = (block_reason or "").upper()
    if "NEWS BLACKOUT" in r or "NEWS_BLACKOUT" in r:
        return FTMO_NEWS_BLACKOUT
    if "DAILY LOSS" in r or "DAILY LOSS LIMIT" in r:
        return FTMO_DAILY_LOSS_LIMIT
    if "DRAWDOWN" in r and "BREACHED" in r:
        return FTMO_MAX_DRAWDOWN
    if "DD ROOM" in r or "MAX-DD" in r or "DD BUFFER" in r:
        return FTMO_DD_BUFFER
    if "DAILY ROOM" in r or "DAILY BUDGET" in r:
        return FTMO_DAILY_BUDGET
    if "MAX POSITION" in r or "POSITIONS" in r:
        return FTMO_MAX_POSITIONS
    return FTMO_RULES_BLOCKED


def classify_mt5_execution_error(error_message: str) -> str:
    """Map MT5 execution exception text to a specific failure code."""
    msg = error_message or ""
    m = re.search(r"retcode:\s*(\d+)", msg, re.I)
    if m:
        code = int(m.group(1))
        return {
            10027: MT5_AUTOTRADING_DISABLED,
            10030: MT5_FILLING_MODE,
            10006: MT5_EXECUTION_REJECTED,
            10014: MT5_INVALID_LOT,
            10016: MT5_INVALID_STOPS,
            10019: MT5_INSUFFICIENT_MARGIN,
            10018: MT5_MARKET_CLOSED,
        }.get(code, MT5_EXECUTION_REJECTED)
    low = msg.lower()
    if "connection failed" in low or "not authorized" in low:
        return MT5_CONNECTION_FAILED
    if "not found" in low or "not visible" in low or "marketwatch" in low:
        return MT5_SYMBOL_NOT_VISIBLE
    if "could not get tick" in low:
        return MT5_TICK_UNAVAILABLE
    if "returned none" in low:
        return MT5_ORDER_SEND_NULL
    return MT5_EXECUTION_REJECTED


def legacy_alert_type(failure_code: str) -> str:
    """Map failure code to legacy alert_type for sound/desktop title fallback."""
    if failure_code == FTMO_NEWS_BLACKOUT:
        return "NEWS_BLACKOUT"
    if failure_code == FTMO_WARNING:
        return "FTMO_WARNING"
    if failure_code in (SYSTEM_INFO,):
        return "INFO"
    if failure_code in (SYSTEM_WARNING, FTMO_WARNING):
        return "WARNING"
    if failure_code in FAILURE_META and not FAILURE_META[failure_code].play_sound:
        return "WARNING"
    return "BLOCKED"
