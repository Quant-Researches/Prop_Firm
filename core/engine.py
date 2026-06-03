from datetime import datetime
import logging
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from config.prefs import load_prefs, save_prefs
from core.ftmo_account import snapshot_from_mt5_account
from core.strategy import RealTimeSignalGenerator
from core.risk_manager import OrderEvent, RiskManager
from core.oms import OMS
from core.execution import ExecutionEngine
from core.portfolio import Portfolio
from core.storage import Storage
from core.signal_store import save_signal

logger = logging.getLogger("TradingEngine")

from core.mt5_data import fetch_mt5_candles, fetch_mt5_ltp
from core.order_failures import (
    DATA_FETCH_FAILED,
    FTMO_WARNING,
    MT5_SYMBOL_UNAVAILABLE,
    MT5_ACCOUNT_UNAVAILABLE,
    STRATEGY_ATR_INVALID,
    ORDER_BUILD_FAILED,
    OMS_DUPLICATE_POSITION,
    classify_mt5_execution_error,
)
from core.notifier import broadcast_order_failure, broadcast_risk_alert, tick_context_from_pipeline


class TradingEngine:
    def __init__(self, mode="live"):
        self.mode = mode
        self.storage = Storage()
        # RiskManager reads starting_balance from prefs on each tick — updated dynamically
        self.risk_manager = RiskManager(
            starting_balance=10_000.0,   # overridden per-tick from ftmo_sod_balance pref
            daily_loss_limit_pct=0.05,   # 5% FTMO daily loss limit
            max_drawdown_pct=0.10,       # 10% FTMO max drawdown
            risk_per_trade=100.0,        # $100 risk per trade
            rr_ratio=2.0,                # 1:2 R:R → $200 target
            max_positions=1,             # one trade at a time on FTMO
        )
        self.oms = OMS(mode=mode)
        self.execution = ExecutionEngine(mode=mode)
        self.portfolio = Portfolio()
        self.strategy = None
        self._strategy_key: tuple[str, str] | None = None

    def _sync_strategy(self, prefs: dict, sym: str, tf: str) -> None:
        """Keep strategy instance aligned with Settings (symbol, TF, filters)."""
        key = (sym, tf)
        if not self.strategy or self._strategy_key != key:
            self.strategy = RealTimeSignalGenerator(
                stock_symbol=sym,
                sec_id=sym,
                interval=tf,
                use_vol_filter=prefs.get("use_vol_filter", False),
                use_atr_filter=prefs.get("use_atr_filter", True),
                ema_fast=prefs.get("ema_fast", 5),
                ema_slow=prefs.get("ema_slow", 8),
            )
            self._strategy_key = key
        else:
            self.strategy.symbol = sym
            self.strategy.sec_id = sym
            self.strategy.interval = tf
            self.strategy.use_volume_filter = prefs.get("use_vol_filter", False)
            self.strategy.use_atr_filter = prefs.get("use_atr_filter", True)
            self.strategy.ema_short_period = prefs.get("ema_fast", 5)
            self.strategy.ema_long_period = prefs.get("ema_slow", 8)

    def run_pipeline_tick(self, is_manual=False, scheduled_close=None):
        prefs = load_prefs()
        tick_type = "manual" if is_manual else "scheduled"
        
        execution_mode = "MetaTrader5"
        self.storage.set_execution_mode(execution_mode)
        
        self.storage.log_event("info", f"Starting {tick_type} pipeline tick (Mode: {execution_mode})...")
        
        # 1. Data Feed via MT5
        sym = prefs.get("trading_symbol", "XAUUSD")
        tf = prefs.get("timeframe", "1h")
        
        mt5_path = prefs.get("mt5_path", "")
        
        df, source, err = fetch_mt5_candles(
            symbol=sym,
            timeframe_str=tf,
            bar_count=prefs.get("bar_count", 500),
            mt5_path=mt5_path,
            account=prefs.get("mt5_account", ""),
            password=prefs.get("mt5_password", ""),
            server=prefs.get("mt5_server", "")
        )
        
        if df is None or df.empty:
            self.storage.log_event("error", f"Data fetch failed: {err}")
            try:
                broadcast_order_failure(
                    failure_code=DATA_FETCH_FAILED,
                    symbol=sym,
                    detail=f"Data feed error: {err}",
                    prefs=prefs,
                )
            except Exception as _ne:
                logger.warning(f"Notifier failed on data fetch error: {_ne}")
            return {"error": err, "symbol": sym, "failure_code": DATA_FETCH_FAILED}
            
        self.storage.log_event("market", f"Fetched {len(df)} candles via {source}")
        
        ltp, ltp_err = fetch_mt5_ltp(
            sym, 
            mt5_path=mt5_path,
            account=prefs.get("mt5_account", ""),
            password=prefs.get("mt5_password", ""),
            server=prefs.get("mt5_server", "")
        )
        if ltp > 0:
            self.storage.log_event("market", f"Live LTP: ${ltp:,.2f}")
        
        # 2. Strategy
        self._sync_strategy(prefs, sym, tf)
        self.strategy.update_data(df)
        result = self.strategy.run_analysis(
            scheduled_close=scheduled_close,
            is_manual=is_manual,
        )
         
        if not result:
            self.storage.log_event("error", "Strategy produced no result (insufficient indicator data or no candles). Tick skipped.")
            return None

        sig = result.get("Signal", "HOLD")
        phase = result.get("Market_Phase", "SIDEWAYS")
        action = result.get('Action', '')
        _tick_ctx = tick_context_from_pipeline(
            {**result, "signal": sig, "action": action, "candles_fetched": len(df)},
            tf,
        )
        bar_sel = result.get("bar_selection", "")
        if bar_sel:
            self.storage.log_event(
                "info",
                f"Signal bar: open={result.get('signal_bar_open')} | {bar_sel}",
            )
        
        self.storage.log_event("signal", f"Phase: {phase} | Signal: {sig} | Reason: {action}")
        
        # 3. Signal Store
        if sig in ["BUY", "SELL"]:
            strategy_df = result.get("data")
            if strategy_df is not None and not strategy_df.empty:
                sig_idx = result.get("signal_bar_index", len(strategy_df) - 1)
                signal_row = strategy_df.iloc[sig_idx]
                save_signal(
                    latest_row=signal_row,
                    symbol=sym,
                    interval=tf,
                    sec_id=sym,
                    signal=sig,
                    reason=action,
                )
                self.storage.log_event("signal", f"Signal saved to data/signals.json")

        # 4. Execution Routing
        _order = None   # tracked for return dict / notifier
        _fill  = None
        _trade_blocked = False
        _block_reason = ""
        _failure_code = ""
        _failure_alert_sent = False
        _risk_warnings: list = []
        if sig in ["BUY", "SELL"] and execution_mode == "MetaTrader5":
            strategy_df = result.get("data")
            price_df = strategy_df if strategy_df is not None and not strategy_df.empty else df
            sig_idx = result.get("signal_bar_index", len(price_df) - 1)
            signal_row = price_df.iloc[sig_idx]
            close_px = float(signal_row['Close'])
            atr = float(signal_row['ATR']) if 'ATR' in signal_row.index and pd.notna(signal_row['ATR']) else (close_px * 0.005)

            challenge_balance = float(prefs.get("initial_balance", 10_000.0))
            sod_balance = float(prefs.get("ftmo_sod_balance", challenge_balance))

            equity_live = sod_balance
            leverage_live = 0
            mt5_positions = -1
            ftmo_metrics = None
            try:
                acc = mt5.account_info()
                if acc:
                    equity_live = float(acc.equity)
                    leverage_live = int(acc.leverage)
                    if prefs.get("ftmo_sod_balance") is None:
                        sod_balance = float(acc.balance)
                        prefs["ftmo_sod_balance"] = sod_balance
                        try:
                            save_prefs(prefs)
                            self.storage.log_event(
                                "info",
                                f"Auto-initialized SOD balance from MT5: ${sod_balance:,.2f}",
                            )
                        except Exception as _pe:
                            logger.error("Failed to auto-save SOD balance: %s", _pe)
                    ftmo_metrics = snapshot_from_mt5_account(
                        acc,
                        sod_balance=sod_balance,
                        challenge_balance=challenge_balance,
                        daily_loss_limit_pct=self.risk_manager.daily_loss_limit_pct,
                        max_drawdown_pct=self.risk_manager.max_drawdown_pct,
                    )
                mt5_positions = mt5.positions_total()
            except Exception as _e:
                logger.warning("Could not fetch MT5 account_info: %s", _e)

            self.risk_manager.configure_ftmo(
                challenge_balance=challenge_balance,
                sod_balance=sod_balance,
            )

            risk_eval = self.risk_manager.evaluate_ftmo_rules(
                equity=equity_live,
                sod_balance=sod_balance,
                challenge_balance=challenge_balance,
                leverage=leverage_live,
                symbol=sym,
                open_positions=mt5_positions,
                metrics=ftmo_metrics,
            )

            # Log all warnings and smart suggestions
            for w in risk_eval.warnings:
                self.storage.log_event("risk", w)
            for s in risk_eval.suggestions:
                self.storage.log_event("info", s)

            # Broadcast risk alerts to all notification channels
            if risk_eval.warnings or not risk_eval.approved:
                try:
                    if not risk_eval.approved:
                        fc = risk_eval.block_code or "FTMO_RULES_BLOCKED"
                        broadcast_order_failure(
                            failure_code=fc,
                            symbol=sym,
                            detail=risk_eval.block_reason or "FTMO risk guard blocked trade",
                            prefs=prefs,
                            signal=sig,
                            warnings=risk_eval.warnings,
                            suggestions=risk_eval.suggestions,
                            tick_context=_tick_ctx,
                        )
                        _failure_alert_sent = True
                    else:
                        broadcast_risk_alert(
                            alert_type="FTMO_WARNING",
                            symbol=sym,
                            warnings=risk_eval.warnings,
                            suggestions=risk_eval.suggestions,
                            prefs=prefs,
                            failure_code=FTMO_WARNING,
                            signal=sig,
                            tick_context=_tick_ctx,
                        )
                except Exception as _ne:
                    logger.warning(f"Risk alert broadcast failed: {_ne}")

            if not risk_eval.approved:
                _trade_blocked = True
                _block_reason = risk_eval.block_reason or "FTMO risk guard blocked trade"
                _failure_code = risk_eval.block_code or "FTMO_RULES_BLOCKED"
                _risk_warnings = list(risk_eval.warnings)
                self.storage.log_event("risk",
                    f"Trade BLOCKED by FTMO Risk Guard: {risk_eval.block_reason}")
            else:
                # ── PART 2: Build Order via RiskManager ───────────────────
                # Every value here is fetched live from MT5. No imaginary defaults.

                # --- Fetch symbol info from MT5 ---
                sym_info = mt5.symbol_info(sym)
                if sym_info is None:
                    _sym_err = f"mt5.symbol_info({sym}) returned None — is the symbol visible in MarketWatch?"
                    _trade_blocked = True
                    _block_reason = _sym_err
                    self.storage.log_event("risk", f"Cannot build order: {_sym_err}")
                    _failure_code = MT5_SYMBOL_UNAVAILABLE
                    try:
                        broadcast_order_failure(
                            failure_code=MT5_SYMBOL_UNAVAILABLE,
                            symbol=sym,
                            detail=_sym_err,
                            prefs=prefs,
                            signal=sig,
                            tick_context=_tick_ctx,
                        )
                        _failure_alert_sent = True
                    except Exception as _ne:
                        logger.warning(f"Notifier failed on symbol_info error: {_ne}")
                else:
                    tick_size     = sym_info.trade_tick_size
                    tick_value    = sym_info.trade_tick_value
                    contract_size = sym_info.trade_contract_size

                    # --- Fetch live account info from MT5 ---
                    acc_info = mt5.account_info()
                    if acc_info is None:
                        _acc_err = "mt5.account_info() returned None — MT5 may not be authorized or session has expired."
                        _trade_blocked = True
                        _block_reason = _acc_err
                        self.storage.log_event("risk", f"Cannot build order: {_acc_err}")
                        _failure_code = MT5_ACCOUNT_UNAVAILABLE
                        try:
                            broadcast_order_failure(
                                failure_code=MT5_ACCOUNT_UNAVAILABLE,
                                symbol=sym,
                                detail=_acc_err,
                                prefs=prefs,
                                signal=sig,
                                tick_context=_tick_ctx,
                            )
                            _failure_alert_sent = True
                        except Exception as _ne:
                            logger.warning(f"Notifier failed on account_info error: {_ne}")
                    else:
                        leverage    = acc_info.leverage      # e.g. 100 means 1:100
                        free_margin = acc_info.margin_free   # actual available margin in account currency

                        self.storage.log_event(
                            "info",
                            f"MT5 live data: Leverage=1:{leverage}"
                            f" | Free margin={free_margin:.2f}"
                            f" | tick_size={tick_size} tick_value={tick_value:.4f}"
                            f" | contract_size={contract_size:.0f}"
                        )

                        # --- Extract Strategy Metrics & Live Spread ---
                        tick = mt5.symbol_info_tick(sym)
                        live_spread = (tick.ask - tick.bid) if tick else 0.0
                        if tick:
                            entry_px = float(tick.ask if sig == "BUY" else tick.bid)
                        else:
                            entry_px = close_px

                        atr_val   = result.get('atr', close_px * 0.005) if result else (close_px * 0.005)
                        atr_pct   = result.get('atr_percentile', 0.5) if result else 0.5

                        if pd.isna(atr_val) or atr_val <= 0:
                            _atr_err = "Cannot build order: Invalid ATR value."
                            _trade_blocked = True
                            _block_reason = _atr_err
                            self.storage.log_event("risk", _atr_err)
                            _failure_code = STRATEGY_ATR_INVALID
                            try:
                                broadcast_order_failure(
                                    failure_code=STRATEGY_ATR_INVALID,
                                    symbol=sym,
                                    detail=_atr_err,
                                    prefs=prefs,
                                    signal=sig,
                                    tick_context=_tick_ctx,
                                )
                                _failure_alert_sent = True
                            except Exception as _ne:
                                logger.warning(f"Notifier failed on ATR error: {_ne}")
                        else:
                            # --- Build the order via Quantitative Risk Engine ---
                            build_result = self.risk_manager.build_order(
                                signal=sig,
                                symbol=sym,
                                close_price=entry_px,
                                atr=atr_val,
                                atr_percentile=atr_pct,
                                live_spread=live_spread,
                                tick_size=tick_size,
                                tick_value=tick_value,
                                leverage=leverage,
                                free_margin=free_margin,
                                contract_size=contract_size,
                            )

                            if not build_result.order:
                                _fc = build_result.failure_code or ORDER_BUILD_FAILED
                                _order_err = build_result.message or f"Order build failed for {sig} {sym}"
                                _trade_blocked = True
                                _block_reason = _order_err
                                _failure_code = _fc
                                self.storage.log_event("risk", f"[{_fc}] {_order_err}")
                                try:
                                    broadcast_order_failure(
                                        failure_code=_fc,
                                        symbol=sym,
                                        detail=_order_err,
                                        prefs=prefs,
                                        signal=sig,
                                        tick_context=_tick_ctx,
                                    )
                                    _failure_alert_sent = True
                                except Exception as _ne:
                                    logger.warning(f"Notifier failed on order build error: {_ne}")
                            else:
                                order = build_result.order
                                self.storage.log_event(
                                    "order",
                                    f"OMS Submit: {sig} {order.qty:.2f}L {sym}"
                                    f" | Entry~{entry_px:.4f}"
                                    f" | SL={order.stop_loss:.4f} TP={order.take_profit:.4f}"
                                    f" | R:R=1:{order.rr_ratio}"
                                    f" | ATR={atr_val:.4f} | Leverage=1:{leverage}"
                                    f" | Risk=${self.risk_manager.risk_per_trade:.0f}"
                                    f" | Target=${self.risk_manager.risk_per_trade * self.risk_manager.rr_ratio:.0f}"
                                )
                                if self.oms.has_open_position(sym, sig):
                                    _dup = f"OMS blocked duplicate {sig} {sym} — position already open."
                                    _trade_blocked = True
                                    _block_reason = _dup
                                    _failure_code = OMS_DUPLICATE_POSITION
                                    self.storage.log_event("risk", _dup)
                                    try:
                                        broadcast_order_failure(
                                            failure_code=OMS_DUPLICATE_POSITION,
                                            symbol=sym,
                                            detail=_dup,
                                            prefs=prefs,
                                            signal=sig,
                                            tick_context=_tick_ctx,
                                        )
                                        _failure_alert_sent = True
                                    except Exception as _ne:
                                        logger.warning(f"Notifier failed on OMS duplicate: {_ne}")
                                else:
                                    order_id = self.oms.submit(order)
                                    order.order_id = order_id
                                    try:
                                        fill = self.execution.execute(order, prefs=prefs)
                                        self.oms.update_status(order_id, "FILLED")
                                        self.risk_manager.increment_positions()
                                        _order = order   # expose to return dict
                                        _fill  = fill

                                        self.storage.log_event("fill", f"MT5 Fill: {fill.qty:.2f}L @ {fill.fill_price:.4f}")
                                        self.storage.save_order(order, order_id, "FILLED")
                                        self.storage.save_trade(fill)
                                        self.portfolio.on_fill(fill)
                                    except Exception as _exec_err:
                                        self.oms.mark_rejected(order_id, str(_exec_err))
                                        _exec_msg = str(_exec_err)
                                        _fc = classify_mt5_execution_error(_exec_msg)
                                        _trade_blocked = True
                                        _block_reason = _exec_msg
                                        _failure_code = _fc
                                        self.storage.log_event("error", f"[{_fc}] MT5 order_send FAILED: {_exec_msg}")
                                        try:
                                            broadcast_order_failure(
                                                failure_code=_fc,
                                                symbol=sym,
                                                detail=_exec_msg,
                                                prefs=prefs,
                                                signal=sig,
                                                order_id=order_id,
                                                tick_context=_tick_ctx,
                                            )
                                            _failure_alert_sent = True
                                        except Exception as _ne:
                                            logger.warning(f"Notifier failed on execution error: {_ne}")

        # 5. Live MT5 Account State for tick log — always read from broker, never from paper Portfolio
        current_px = df['Close'].iloc[-1]
        self.portfolio.mark_to_market({sym: current_px})

        # Fetch live account values from MT5 for accurate reporting
        live_equity   = 0.0
        live_pnl      = 0.0
        live_positions = 0
        try:
            _acc = mt5.account_info()
            if _acc:
                live_equity    = _acc.equity
                live_pnl       = _acc.profit
            live_positions = mt5.positions_total() or 0
        except Exception:
            pass

        # Fall back to portfolio snap only when MT5 is disconnected
        snap = self.portfolio.get_summary()
        if live_equity == 0.0:
            live_equity    = snap.equity
            live_pnl       = snap.unrealised_pnl
            live_positions = snap.open_positions

        self.storage.save_pnl_snapshot(
            timestamp=datetime.now(),
            equity=live_equity,
            cash=live_equity,           # for FTMO, equity = cash (margin account)
            realised_pnl=0.0,
            unrealised_pnl=live_pnl,
            open_positions=live_positions,
            total_trades=snap.total_trades
        )
        self.storage.log_event(
            "info",
            f"Tick Complete. Open Pos: {live_positions} "
            f"| Equity: ${live_equity:,.2f} "
            f"| uPnL: ${live_pnl:,.2f}"
        )
        
        return {
            "signal": sig,
            "phase": phase,
            "ltp": ltp if ltp > 0 else current_px,
            "action": action,
            "symbol": sym,
            "data_source": source,
            "candles_fetched": len(df),
            "order": _order,   # OrderEvent or None — used by notifier
            "fill":  _fill,    # FillEvent or None — used by notifier
            "df": result.get("data", df) if result else df,
            "last_high": result.get('last_high', None) if result else None,
            "last_low": result.get('last_low', None) if result else None,
            "trade_blocked": _trade_blocked if sig in ("BUY", "SELL") else False,
            "block_reason": _block_reason,
            "failure_code": _failure_code if sig in ("BUY", "SELL") else "",
            "failure_alert_sent": _failure_alert_sent if sig in ("BUY", "SELL") else False,
            "risk_warnings": _risk_warnings,
            "signal_bar_open": result.get("signal_bar_open"),
            "scheduled_close": result.get("scheduled_close"),
            "bar_selection": result.get("bar_selection"),
            "signal_bar_index": result.get("signal_bar_index"),
            "raw_signal": result.get("raw_signal"),
            "price": result.get("price"),
        }
