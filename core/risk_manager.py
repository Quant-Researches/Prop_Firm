"""
core/risk_manager.py
Two-Part Risk Manager for FTMO Challenge accounts.
Part 1: FTMO Rule Guardian (daily loss, max DD, position limits, news blackout).
Part 2: ADR-based SL, 1:2 R:R, leverage-aware lot sizing.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import logging
import requests
import pytz
from core.strategy import SignalEvent

# ---------------------------------------------------------------------------
# FTMO uses TWO separate timezones:
#
#   1. MT5 CHART TIME (what you see on MetaTrader candles/history)
#      = GMT+3 (fixed in summer via EEST, matches standard broker convention)
#      = Europe/Helsinki in summer (EEST = UTC+3)
#      IST - GMT+3 = 2h30m  (always in summer)
#
#   2. DAILY RESET / ACCOUNT DASHBOARD (Prague headquarter time)
#      = CE(S)T = Europe/Prague
#      = GMT+2 in summer (CEST)  |  GMT+1 in winter (CET)
#      Daily Loss resets at 00:00 Prague (CEST) = 01:00 MT5 chart = 03:30 IST
#
# ForexFactory events are in US Eastern Time (ET/EDT) -> converted to UTC
# All comparisons are done in UTC; pytz handles DST automatically
# ---------------------------------------------------------------------------
_FTMO_TZ   = pytz.timezone("Europe/Helsinki")  # MT5 chart time (GMT+3 summer)
_PRAGUE_TZ = pytz.timezone("Europe/Prague")    # Daily reset / account dashboard
_ET_TZ     = pytz.timezone("America/New_York") # ForexFactory event times
_IST_TZ    = pytz.timezone("Asia/Kolkata")     # Indian Standard Time (UTC+5:30)

# Module-level cache: refreshed once per FTMO calendar day
_NEWS_CACHE: dict = {"events": [], "fetched_date": None, "error": False}

# Symbol -> currencies affected by news
_SYMBOL_CURRENCIES: dict = {
    "EURUSD": ["EUR","USD"], "GBPUSD": ["GBP","USD"],
    "USDJPY": ["USD","JPY"], "USDCHF": ["USD","CHF"],
    "AUDUSD": ["AUD","USD"], "NZDUSD": ["NZD","USD"],
    "USDCAD": ["USD","CAD"], "EURGBP": ["EUR","GBP"],
    "EURJPY": ["EUR","JPY"], "EURCHF": ["EUR","CHF"],
    "EURAUD": ["EUR","AUD"], "EURCAD": ["EUR","CAD"],
    "EURNZD": ["EUR","NZD"], "GBPJPY": ["GBP","JPY"],
    "GBPCHF": ["GBP","CHF"], "GBPAUD": ["GBP","AUD"],
    "GBPCAD": ["GBP","CAD"], "GBPNZD": ["GBP","NZD"],
    "AUDJPY": ["AUD","JPY"], "AUDCAD": ["AUD","CAD"],
    "AUDCHF": ["AUD","CHF"], "CADJPY": ["CAD","JPY"],
    "CHFJPY": ["CHF","JPY"], "NZDCAD": ["NZD","CAD"],
    "NZDCHF": ["NZD","CHF"], "NZDJPY": ["NZD","JPY"],
    "XAUUSD": ["USD"], "XAGUSD": ["USD"],
    "US30": ["USD"], "US500": ["USD"], "USTEC": ["USD"],
    "US30.CASH": ["USD"], "US500.CASH": ["USD"], "USTEC.CASH": ["USD"],
    "NAS100": ["USD"], "SPX500": ["USD"],
    "GER40": ["EUR"], "FRA40": ["EUR"], "UK100": ["GBP"],
    "XTIUSD": ["USD"], "XBRUSD": ["USD"],
}

logger = logging.getLogger("RiskManager")


# ---------------------------------------------------------------------------
# OrderEvent
# ---------------------------------------------------------------------------

@dataclass
class OrderEvent:
    symbol: str
    side: str
    qty: float
    order_type: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    signal_ref: Optional[SignalEvent] = None
    order_id: Optional[str] = None
    tag: str = ""
    est_loss_usd: float = 0.0
    est_profit_usd: float = 0.0

    @property
    def sl_distance(self) -> float:
        if self.limit_price and self.stop_loss:
            return abs(self.limit_price - self.stop_loss)
        return 0.0

    @property
    def tp_distance(self) -> float:
        if self.limit_price and self.take_profit:
            return abs(self.limit_price - self.take_profit)
        return 0.0

    @property
    def rr_ratio(self) -> float:
        if self.sl_distance > 0:
            return round(self.tp_distance / self.sl_distance, 2)
        return 0.0

    def __repr__(self) -> str:
        sl = str(round(self.stop_loss, 4)) if self.stop_loss else "N/A"
        tp = str(round(self.take_profit, 4)) if self.take_profit else "N/A"
        return (
            "OrderEvent(" + self.symbol + " | " + self.side
            + " " + str(round(self.qty, 2)) + "L"
            + " | SL=" + sl + " TP=" + tp
            + " | R:R=1:" + str(self.rr_ratio) + ")"
        )


# ---------------------------------------------------------------------------
# RiskEvaluation
# ---------------------------------------------------------------------------

@dataclass
class RiskEvaluation:
    approved: bool
    warnings: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    daily_loss_pct: float = 0.0
    total_drawdown_pct: float = 0.0
    daily_loss_remaining: float = 0.0
    max_dd_remaining: float = 0.0
    block_reason: str = ""


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

class RiskManager:
    """
    Two-part risk manager for FTMO Challenge / Funded accounts.

    Part 1 - evaluate_ftmo_rules():
        Checks daily loss (5%), max drawdown (10%), open position limit,
        pre-trade budget, and news blackout (leverage > 1:30).

    Part 2 - build_order():
        ADR-based SL (15% of daily range), 1:2 R:R,
        leverage/margin-validated lot sizing.
    """

    def __init__(
        self,
        starting_balance: float = 10_000.0,
        daily_loss_limit_pct: float = 0.05,
        max_drawdown_pct: float = 0.10,
        risk_per_trade: float = 100.0,
        rr_ratio: float = 2.0,
        max_positions: int = 1,
    ):
        self.starting_balance = starting_balance
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.risk_per_trade = risk_per_trade
        self.rr_ratio = rr_ratio
        self.max_positions = max_positions
        self._open_positions: int = 0

    # -------------------------------------------------------------------------
    # PART 1: FTMO Risk Guardian
    # -------------------------------------------------------------------------

    def evaluate_ftmo_rules(
        self,
        current_balance: float,
        daily_pnl: float,
        sod_balance: Optional[float] = None,
        leverage: int = 0,
        symbol: str = "",
        open_positions: int = -1,
    ) -> RiskEvaluation:
        """
        Evaluates ALL FTMO rules before a trade is placed.

        current_balance : live equity (mt5.account_info().equity)
        daily_pnl       : today P&L (mt5.account_info().profit)
        sod_balance     : start-of-day balance snapshot
        leverage        : mt5.account_info().leverage (e.g. 100 = 1:100)
        symbol          : MT5 symbol being traded (e.g. XAUUSD)
        open_positions  : live position count from mt5.positions_total().
                          Pass -1 to fall back to the internal counter
                          (not recommended for live trading).

        Check 6 (news blackout) only activates when leverage > 30.
        All times in UTC internally; display in FTMO time (Europe/Prague).
        """
        warnings = []
        suggestions = []
        approved = True
        block_reason = ""

        daily_loss_limit = self.starting_balance * self.daily_loss_limit_pct
        max_dd_limit     = self.starting_balance * self.max_drawdown_pct

        daily_loss_amount   = max(0.0, -daily_pnl)
        total_drawdown      = max(0.0, self.starting_balance - current_balance)
        daily_loss_pct_used = (daily_loss_amount / self.starting_balance) * 100
        total_drawdown_pct  = (total_drawdown / self.starting_balance) * 100
        daily_remaining     = max(0.0, daily_loss_limit - daily_loss_amount)
        dd_remaining        = max(0.0, max_dd_limit - total_drawdown)

        lim_pct = self.daily_loss_limit_pct * 100
        dd_pct  = self.max_drawdown_pct * 100
        bal     = self.starting_balance

        # Check 1: Daily Loss Limit (5%)
        if daily_loss_amount >= daily_loss_limit:
            approved = False
            block_reason = ("Daily loss limit reached: "
                + str(round(daily_loss_amount, 2)) + " / " + str(round(daily_loss_limit, 2)))
            warnings.append("DAILY LOSS LIMIT HIT: Lost " + str(round(daily_loss_amount, 2))
                + " today (limit=" + str(round(daily_loss_limit, 2))
                + " / " + str(round(lim_pct, 0)) + "% of " + str(round(bal, 0)) + ")")
            suggestions.append("STOP trading for today. Any further loss will breach the account.")
        elif daily_loss_amount >= daily_loss_limit * 0.80:
            warnings.append("WARNING: Approaching daily limit. " + str(round(daily_loss_amount, 2))
                + " used (" + str(round(daily_loss_pct_used, 1)) + "%). Only "
                + str(round(daily_remaining, 2)) + " left today.")
            suggestions.append("Reduce position size. Budget remaining: " + str(round(daily_remaining, 2)))
        elif daily_loss_amount >= daily_loss_limit * 0.50:
            warnings.append("INFO: Daily loss at " + str(round(daily_loss_pct_used, 1))
                + "%: " + str(round(daily_loss_amount, 2)) + " used.")

        # Check 2: Max Overall Drawdown (10%)
        if total_drawdown >= max_dd_limit:
            approved = False
            block_reason = ("Max drawdown breached: "
                + str(round(total_drawdown, 2)) + " / " + str(round(max_dd_limit, 2)))
            warnings.append("MAX DRAWDOWN BREACHED: Account down " + str(round(total_drawdown, 2))
                + " (limit=" + str(round(max_dd_limit, 2))
                + " / " + str(round(dd_pct, 0)) + "% of " + str(round(bal, 0)) + ")")
            suggestions.append("ACCOUNT AT SUSPENSION RISK. Do NOT place any trades.")
        elif total_drawdown >= max_dd_limit * 0.80:
            warnings.append("WARNING: Approaching max drawdown. " + str(round(total_drawdown, 2))
                + " used (" + str(round(total_drawdown_pct, 1)) + "%). Buffer: "
                + str(round(dd_remaining, 2)))
            suggestions.append("Trade with extreme caution. One bad trade of >"
                + str(round(dd_remaining, 0)) + " could breach.")
        elif total_drawdown >= max_dd_limit * 0.50:
            warnings.append("INFO: Overall drawdown at " + str(round(total_drawdown_pct, 1))
                + "%: " + str(round(total_drawdown, 2)) + " used.")

        # Check 3: Daily budget vs trade risk
        if approved and daily_remaining < self.risk_per_trade:
            approved = False
            block_reason = ("Daily room " + str(round(daily_remaining, 2))
                + " < trade risk " + str(round(self.risk_per_trade, 2)))
            warnings.append("TRADE BLOCKED: Only " + str(round(daily_remaining, 2))
                + " daily budget left, but trade risks " + str(round(self.risk_per_trade, 2)) + ".")
            suggestions.append("Reduce risk per trade or pause for today.")

        # Check 4: Max DD buffer vs trade risk
        if approved and dd_remaining < self.risk_per_trade:
            approved = False
            block_reason = ("DD room " + str(round(dd_remaining, 2))
                + " < trade risk " + str(round(self.risk_per_trade, 2)))
            warnings.append("TRADE BLOCKED: Only " + str(round(dd_remaining, 2))
                + " max-DD buffer left, but trade risks " + str(round(self.risk_per_trade, 2)) + ".")
            suggestions.append("No trades today. Protect the account.")

        # Check 5: Max open positions (from live MT5 count — not internal counter)
        # open_positions is mt5.positions_total() passed in from the engine.
        # This handles bot restarts and positions closed directly in MT5 terminal.
        live_pos = open_positions if open_positions >= 0 else self._open_positions
        if approved and live_pos >= self.max_positions:
            approved = False
            block_reason = "Max positions (" + str(self.max_positions) + ") already open"
            source = "MT5 live" if open_positions >= 0 else "internal counter (MT5 unavailable)"
            warnings.append("TRADE BLOCKED: " + str(live_pos)
                + " open positions in MT5 [" + source + "]. Max = " + str(self.max_positions) + ".")
            suggestions.append("Close an existing position in MT5 before opening a new one.")

        # Check 6: News Blackout (FTMO rule for leverage > 1:30 only)
        if approved and leverage > 30 and symbol:
            blocked, reason, warn, suggest = self._check_news_blackout(symbol, leverage)
            if blocked:
                approved = False
                block_reason = reason
            if warn:
                warnings.append(warn)
            if suggest:
                suggestions.append(suggest)

        if approved and not warnings:
            suggestions.append(
                "All FTMO rules OK"
                + " | Daily used: " + str(round(daily_loss_pct_used, 1)) + "%"
                + " | Max DD used: " + str(round(total_drawdown_pct, 1)) + "%"
                + " | Daily room: " + str(round(daily_remaining, 2))
                + " | DD room: " + str(round(dd_remaining, 2))
                + (" | Leverage=1:" + str(leverage) if leverage > 0 else "")
            )

        return RiskEvaluation(
            approved=approved,
            warnings=warnings,
            suggestions=suggestions,
            daily_loss_pct=daily_loss_pct_used,
            total_drawdown_pct=total_drawdown_pct,
            daily_loss_remaining=daily_remaining,
            max_dd_remaining=dd_remaining,
            block_reason=block_reason,
        )

    # -------------------------------------------------------------------------
    # News Blackout Helpers (used by Check 6)
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_symbol_currencies(symbol: str) -> list:
        """Returns the currency codes affected by news for a given symbol."""
        sym = symbol.upper().replace(".CASH","").replace(".PRO","").replace("_","")
        if sym in _SYMBOL_CURRENCIES:
            return _SYMBOL_CURRENCIES[sym]
        if len(sym) == 6 and sym.isalpha():
            return [sym[:3], sym[3:]]
        if "USD" in sym:
            return ["USD"]
        return []

    @staticmethod
    def _fetch_news_calendar() -> list:
        """
        Fetches HIGH-impact events from ForexFactory for the current week.
        Cache key = FTMO calendar date (Europe/Prague). Refreshes at midnight Prague time.
        ForexFactory event times are in US Eastern Time -> stored as UTC.
        """
        global _NEWS_CACHE
        today_key = datetime.now(_FTMO_TZ).date()
        if _NEWS_CACHE["fetched_date"] == today_key and _NEWS_CACHE["events"]:
            return _NEWS_CACHE["events"]
        try:
            resp = requests.get(
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                timeout=8, headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            events = []
            for ev in resp.json():
                if ev.get("impact", "").lower() != "high":
                    continue
                date_str = ev.get("date", "")
                time_str = ev.get("time", "")
                if not date_str or not time_str or time_str.lower() in ("", "all day", "tentative"):
                    continue
                try:
                    dt_et = _ET_TZ.localize(
                        datetime.strptime(date_str + " " + time_str, "%m-%d-%Y %I:%M%p")
                    )
                    events.append({
                        "time_utc": dt_et.astimezone(pytz.utc),
                        "currency": ev.get("currency", "").upper(),
                        "title":    ev.get("title", ""),
                    })
                except Exception:
                    continue
            _NEWS_CACHE.update({"events": events, "fetched_date": today_key, "error": False})
            logger.info("NewsGuard: cached " + str(len(events)) + " HIGH-impact events for FTMO date " + str(today_key))
            return events
        except Exception as e:
            _NEWS_CACHE["error"] = True
            logger.error("NewsGuard: calendar fetch failed: " + str(e))
            return _NEWS_CACHE.get("events", [])

    def _check_news_blackout(self, symbol: str, leverage: int) -> tuple:
        """
        Returns (blocked, block_reason, warning_msg, suggestion_msg).

        FTMO rule for leverage > 1:30:
          HARD BLOCK  : within +-2 min of HIGH-impact event for this symbol
          EARLY WARN  : 3-15 min before event (trade allowed, warning issued)

        All time comparisons are in UTC.
        Display strings show both FTMO time (CET/CEST) and IST for easy reading.
        IST = FTMO time + 2h30m (summer/CEST) or + 3h30m (winter/CET).
        """
        BLOCK_MIN = 2
        WARN_MIN  = 15
        currencies = self._get_symbol_currencies(symbol)
        if not currencies:
            return False, "", "", ""
        now_utc = datetime.now(pytz.utc)
        for ev in self._fetch_news_calendar():
            if ev["currency"] not in currencies:
                continue
            ev_utc = ev["time_utc"]
            mins   = (ev_utc - now_utc).total_seconds() / 60

            # Time strings in both FTMO and IST
            ev_ftmo    = ev_utc.astimezone(_FTMO_TZ).strftime("%H:%M CET/CEST")
            ev_ist     = ev_utc.astimezone(_IST_TZ).strftime("%H:%M IST")
            clear_ftmo = (ev_utc + timedelta(minutes=BLOCK_MIN)).astimezone(_FTMO_TZ).strftime("%H:%M")
            clear_ist  = (ev_utc + timedelta(minutes=BLOCK_MIN)).astimezone(_IST_TZ).strftime("%H:%M")
            block_ftmo = (ev_utc - timedelta(minutes=BLOCK_MIN)).astimezone(_FTMO_TZ).strftime("%H:%M")
            block_ist  = (ev_utc - timedelta(minutes=BLOCK_MIN)).astimezone(_IST_TZ).strftime("%H:%M")

            label = ev["title"] + " [" + ev["currency"] + "] @ " + ev_ftmo + " / " + ev_ist

            if -BLOCK_MIN <= mins <= BLOCK_MIN:
                direction = ("in " + str(round(abs(mins), 1)) + " min"
                             if mins >= 0 else str(round(abs(mins), 1)) + " min ago")
                return (
                    True,
                    "NEWS BLACKOUT (1:" + str(leverage) + " > 1:30): " + label + " | " + direction,
                    "NEWS BLACKOUT ACTIVE: " + label
                    + " | No trading 2 min before/after high-impact news.",
                    "Resume after " + clear_ftmo + " (FTMO) / " + clear_ist + " (IST).",
                )
            if BLOCK_MIN < mins <= WARN_MIN:
                return (
                    False, "",
                    "NEWS WARNING: " + label + " in " + str(round(mins, 0)) + " min."
                    + " Blackout starts at " + block_ftmo + " (FTMO) / " + block_ist + " (IST).",
                    "No new trades from " + block_ftmo + " (FTMO) / " + block_ist + " (IST).",
                )
        return False, "", "", ""

    # -------------------------------------------------------------------------
    # PART 2: Order Builder (ADR-based SL + Leverage Check)
    # -------------------------------------------------------------------------

    def _classify_volatility(self, atr_percentile: float) -> float:
        """Returns the ATR multiplier based on volatility regime."""
        if atr_percentile < 0.30:
            return 1.2  # Low volatility
        elif atr_percentile <= 0.70:
            return 1.5  # Normal volatility
        else:
            return 1.8  # High volatility

    def build_order(
        self,
        signal: str,
        symbol: str,
        close_price: float,
        atr: float,
        atr_percentile: float,
        last_high: float,
        last_low: float,
        live_spread: float,
        tick_size: float,
        tick_value: float,
        leverage: int = 100,
        free_margin: float = 0.0,
        contract_size: float = 100_000.0,
    ) -> Optional[OrderEvent]:
        """
        Builds a fully sized OrderEvent using quantitative ATR logic.
        Enforces EXACTLY $100 risk and 1:2 R:R ($200 target).
        """
        if signal not in ("BUY", "SELL"):
            logger.error(f"build_order: invalid signal {repr(signal)}")
            return None
        if atr <= 0 or tick_size <= 0 or tick_value <= 0:
            logger.error(f"build_order: invalid data atr={atr} tick_size={tick_size} tick_value={tick_value}")
            return None

        # --- Professional Validation Filters ---
        # 1. Spread Sanity Check
        max_allowed_spread = atr * 0.10
        if live_spread > max_allowed_spread:
            logger.warning(f"TRADE BLOCKED: Spread ({live_spread:.5f}) too high for current ATR ({atr:.5f}). Max allowed: {max_allowed_spread:.5f}")
            return None

        # --- Volatility Regime Logic ---
        atr_multiplier = self._classify_volatility(atr_percentile)
        atr_stop_distance = atr * atr_multiplier

        # --- Structure-Aware SL Validator ---
        structure_stop_distance = 0.0
        if signal == "BUY" and last_low and last_low > 0:
            structure_stop_distance = max(0.0, close_price - last_low)
        elif signal == "SELL" and last_high and last_high > 0:
            structure_stop_distance = max(0.0, last_high - close_price)

        final_sl_distance = max(atr_stop_distance, structure_stop_distance)

        # 2. Minimum/Maximum SL Bounds
        min_sl = tick_size * 5
        max_sl = close_price * 0.05  # Sanity check: don't allow a 5% stop loss
        if final_sl_distance < min_sl:
            final_sl_distance = min_sl
            logger.warning(f"build_order: SL below 5-tick floor. Adjusted to {min_sl}")
        if final_sl_distance > max_sl:
            logger.warning(f"TRADE BLOCKED: SL distance ({final_sl_distance:.5f}) exceeds extreme maximum ({max_sl:.5f}).")
            return None

        # --- Take Profit Engine ---
        # Fixed 1:2 R:R
        tp_distance = final_sl_distance * self.rr_ratio

        # --- Price Levels ---
        if signal == "BUY":
            sl = close_price - final_sl_distance
            tp = close_price + tp_distance
        else:
            sl = close_price + final_sl_distance
            tp = close_price - tp_distance

        # --- Position Sizing Engine ---
        sl_ticks = final_sl_distance / tick_size
        tp_ticks = tp_distance / tick_size
        risk_per_lot = sl_ticks * tick_value
        
        if risk_per_lot <= 0:
            logger.error(f"build_order: invalid risk_per_lot={risk_per_lot}")
            return None

        # position_size = risk_amount / (stop_loss_pips * pip_value)
        lots = self.risk_per_trade / risk_per_lot
        lots = max(0.01, round(lots, 2))
        
        # --- Leverage Protection ---
        if free_margin > 0 and leverage > 0 and contract_size > 0:
            margin_needed = (lots * contract_size * close_price) / leverage
            margin_cap = free_margin * 0.30
            if margin_needed > margin_cap:
                max_lots = (margin_cap * leverage) / (contract_size * close_price)
                max_lots = max(0.01, round(max_lots, 2))
                if max_lots < lots:
                    logger.warning(
                        f"LEVERAGE CONSTRAINT {symbol}: margin needed {margin_needed:.2f} "
                        f"> cap {margin_cap:.2f}. Lots reduced: {lots} -> {max_lots}"
                    )
                    lots = max_lots

        # --- Verification ---
        est_loss = round(lots * sl_ticks * tick_value, 2)
        est_profit = round(lots * tp_ticks * tick_value, 2)

        logger.info(
            f"Order built: {signal} {symbol} | Entry~{close_price:.5f} "
            f"| SL={sl:.5f} (dist={final_sl_distance:.5f}, ATRx{atr_multiplier}) "
            f"| TP={tp:.5f} (dist={tp_distance:.5f}) "
            f"| R:R=1:{self.rr_ratio} | Lots={lots} "
            f"| Est.Loss=${est_loss} | Est.Profit=${est_profit} "
            f"| Spread={live_spread:.5f}"
        )

        return OrderEvent(
            symbol=symbol, side=signal, qty=lots,
            order_type="MARKET", limit_price=close_price,
            stop_loss=sl, take_profit=tp,
            est_loss_usd=est_loss, est_profit_usd=est_profit,
        )

    # -------------------------------------------------------------------------
    # Position Tracking
    # -------------------------------------------------------------------------

    def increment_positions(self) -> None:
        self._open_positions += 1

    def decrement_positions(self) -> None:
        self._open_positions = max(0, self._open_positions - 1)

    def update_starting_balance(self, balance: float) -> None:
        self.starting_balance = balance

    @property
    def open_positions(self) -> int:
        return self._open_positions

    def __repr__(self) -> str:
        return ("RiskManager(start=" + str(round(self.starting_balance, 0))
            + ", risk=" + str(self.risk_per_trade) + "/trade"
            + ", RR=1:" + str(self.rr_ratio)
            + ", daily_limit=" + str(round(self.daily_loss_limit_pct * 100, 0)) + "pct"
            + ", max_dd=" + str(round(self.max_drawdown_pct * 100, 0)) + "pct"
            + ", open_pos=" + str(self._open_positions) + "/" + str(self.max_positions) + ")")
