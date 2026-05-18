import json
from datetime import datetime
from pathlib import Path
import logging
import pandas as pd
import MetaTrader5 as mt5

from core.strategy import RealTimeSignalGenerator
from core.risk_manager import OrderEvent, RiskManager
from core.oms import OMS
from core.execution import ExecutionEngine
from core.portfolio import Portfolio
from core.storage import Storage
from core.signal_store import save_signal

logger = logging.getLogger("TradingEngine")

from core.mt5_data import fetch_mt5_candles, fetch_mt5_ltp

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
            sl_atr_mult=1.5,             # SL = 1.5x ATR
            max_positions=1,             # one trade at a time on FTMO
        )
        self.oms = OMS(mode=mode)
        self.execution = ExecutionEngine(mode=mode)
        self.portfolio = Portfolio()
        self.strategy = None
        
    def load_prefs(self):
        p = Path("config/user_prefs.json")
        if p.exists():
            try:
                return json.loads(p.read_text())
            except:
                pass
        return {}

    def run_pipeline_tick(self, is_manual=False):
        prefs = self.load_prefs()
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
                from core.notifier import broadcast_risk_alert
                broadcast_risk_alert(
                    alert_type="BLOCKED",
                    symbol=sym,
                    warnings=[f"DATA FETCH FAILED: {err}"],
                    suggestions=["Check MT5 connection and symbol visibility in MarketWatch."],
                    prefs=prefs,
                    block_reason=f"Data feed error: {err}",
                )
            except Exception as _ne:
                logger.warning(f"Notifier failed on data fetch error: {_ne}")
            return {"error": err}
            
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
        if not self.strategy:
            self.strategy = RealTimeSignalGenerator(
                stock_symbol=sym,
                sec_id=sym,
                interval=tf,
                use_vol_filter=prefs.get("use_vol_filter", False),
                use_atr_filter=prefs.get("use_atr_filter", True),
                ema_fast=prefs.get("ema_fast", 5),
                ema_slow=prefs.get("ema_slow", 8)
            )
        else:
            self.strategy.use_volume_filter = prefs.get("use_vol_filter", False)
            self.strategy.use_atr_filter = prefs.get("use_atr_filter", True)
            self.strategy.ema_short_period = prefs.get("ema_fast", 5)
            self.strategy.ema_long_period = prefs.get("ema_slow", 8)
            
        self.strategy.update_data(df)
        result = self.strategy.run_analysis()
        
        if not result:
            self.storage.log_event("error", "Strategy produced no result (insufficient indicator data or no candles). Tick skipped.")
            return None

        sig = result.get("Signal", "HOLD")
        phase = result.get("Market_Phase", "SIDEWAYS")
        action = result.get('Action', '')
        
        self.storage.log_event("signal", f"Phase: {phase} | Signal: {sig} | Reason: {action}")
        
        # 3. Signal Store
        if sig in ["BUY", "SELL"]:
            strategy_df = result.get("data")
            if strategy_df is not None and not strategy_df.empty:
                latest_row = strategy_df.iloc[-1]
                save_signal(
                    latest_row=latest_row,
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
        if sig in ["BUY", "SELL"] and execution_mode == "MetaTrader5":
            close_px = df['Close'].iloc[-1]
            atr      = df['ATR'].iloc[-1] if 'ATR' in df.columns else (close_px * 0.005)

            # ── Sync starting balance from SOD snapshot ────────────────────
            sod_balance = float(prefs.get("ftmo_sod_balance", 10_000.0))
            self.risk_manager.update_starting_balance(sod_balance)

            # Fetch live account state from MT5
            current_balance  = sod_balance  # fallback
            daily_pnl_live   = 0.0
            leverage_live    = 0
            mt5_positions    = -1  # -1 = unknown, falls back to internal counter
            try:
                acc = mt5.account_info()
                if acc:
                    current_balance = acc.equity
                    daily_pnl_live  = acc.profit
                    leverage_live   = acc.leverage
                # Live open position count — handles restarts & MT5-side closes
                mt5_positions = mt5.positions_total()
            except Exception as _e:
                logger.warning(f"Could not fetch MT5 account_info: {_e}")

            # PART 1: FTMO Risk Check (includes news blackout for leverage > 1:30)
            risk_eval = self.risk_manager.evaluate_ftmo_rules(
                current_balance=current_balance,
                daily_pnl=daily_pnl_live,
                sod_balance=sod_balance,
                leverage=leverage_live,
                symbol=sym,
                open_positions=mt5_positions,
            )

            # Log all warnings and smart suggestions
            for w in risk_eval.warnings:
                self.storage.log_event("risk", w)
            for s in risk_eval.suggestions:
                self.storage.log_event("info", s)

            # Broadcast risk alerts to all notification channels
            if risk_eval.warnings or not risk_eval.approved:
                try:
                    from core.notifier import broadcast_risk_alert
                    # Determine alert type from block reason content
                    if not risk_eval.approved:
                        atype = (
                            "NEWS_BLACKOUT"
                            if "NEWS BLACKOUT" in risk_eval.block_reason
                            else "BLOCKED"
                        )
                    else:
                        atype = (
                            "NEWS_BLACKOUT"
                            if any("NEWS" in w for w in risk_eval.warnings)
                            else "FTMO_WARNING"
                        )
                    broadcast_risk_alert(
                        alert_type=atype,
                        symbol=sym,
                        warnings=risk_eval.warnings,
                        suggestions=risk_eval.suggestions,
                        prefs=prefs,
                        block_reason=risk_eval.block_reason,
                    )
                except Exception as _ne:
                    logger.warning(f"Risk alert broadcast failed: {_ne}")

            if not risk_eval.approved:
                self.storage.log_event("risk",
                    f"Trade BLOCKED by FTMO Risk Guard: {risk_eval.block_reason}")
            else:
                # ── PART 2: Build Order via RiskManager ───────────────────
                # Every value here is fetched live from MT5. No imaginary defaults.

                # --- Fetch symbol info from MT5 ---
                sym_info = mt5.symbol_info(sym)
                if sym_info is None:
                    _sym_err = f"mt5.symbol_info({sym}) returned None — is the symbol visible in MarketWatch?"
                    self.storage.log_event("risk", f"Cannot build order: {_sym_err}")
                    try:
                        from core.notifier import broadcast_risk_alert
                        broadcast_risk_alert(
                            alert_type="BLOCKED",
                            symbol=sym,
                            warnings=[f"SYMBOL INFO UNAVAILABLE: {_sym_err}"],
                            suggestions=["Open MT5 terminal → MarketWatch → right-click → Show All → find and add the symbol."],
                            prefs=prefs,
                            block_reason=_sym_err,
                        )
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
                        self.storage.log_event("risk", f"Cannot build order: {_acc_err}")
                        try:
                            from core.notifier import broadcast_risk_alert
                            broadcast_risk_alert(
                                alert_type="BLOCKED",
                                symbol=sym,
                                warnings=[f"MT5 ACCOUNT INFO UNAVAILABLE: {_acc_err}"],
                                suggestions=["Re-check MT5 login credentials in Settings and restart the bot."],
                                prefs=prefs,
                                block_reason=_acc_err,
                            )
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

                        # --- Calculate ADR from the already-fetched OHLCV data ---
                        # Resample to daily candles — no extra API call needed.
                        adr = 0.0
                        try:
                            df_d = df.copy()
                            if not isinstance(df_d.index, pd.DatetimeIndex):
                                df_d.index = pd.to_datetime(df_d.index)
                            daily = df_d.resample("D").agg({"High": "max", "Low": "min"}).dropna()
                            if len(daily) >= 2:
                                adr = (daily["High"] - daily["Low"]).tail(14).mean()
                                self.storage.log_event(
                                    "info",
                                    f"ADR (14-day avg daily range): {adr:.5f}"
                                    f" | SL will be {adr * 0.15:.5f} (15% of ADR)"
                                )
                        except Exception as _e:
                            logger.warning(f"ADR resampling failed: {_e}")

                        if adr <= 0:
                            # Last resort: only possible if we have less than 2 daily candles
                            # in the entire dataset — extremely unlikely but handled.
                            _adr_err = "Cannot compute ADR — not enough daily data in fetched candles."
                            self.storage.log_event("risk", f"{_adr_err} Increase bar_count in settings (>100 bars recommended).")
                            try:
                                from core.notifier import broadcast_risk_alert
                                broadcast_risk_alert(
                                    alert_type="BLOCKED",
                                    symbol=sym,
                                    warnings=[f"ADR COMPUTATION FAILED: {_adr_err}"],
                                    suggestions=["Increase bar_count to >100 in Settings to ensure sufficient daily data."],
                                    prefs=prefs,
                                    block_reason=_adr_err,
                                )
                            except Exception as _ne:
                                logger.warning(f"Notifier failed on ADR error: {_ne}")
                        else:
                            # --- Build the order ---
                            order = self.risk_manager.build_order(
                                signal=sig,
                                symbol=sym,
                                close_price=close_px,
                                adr=adr,
                                tick_size=tick_size,
                                tick_value=tick_value,
                                leverage=leverage,
                                free_margin=free_margin,
                                contract_size=contract_size,
                                adr_fraction=0.15,
                            )

                            if order is None:
                                _order_err = f"RiskManager.build_order() returned None for {sig} {sym} — margin/leverage constraint or invalid tick data."
                                self.storage.log_event("risk", _order_err)
                                try:
                                    from core.notifier import broadcast_risk_alert
                                    broadcast_risk_alert(
                                        alert_type="BLOCKED",
                                        symbol=sym,
                                        warnings=[f"ORDER BUILD FAILED: {_order_err}"],
                                        suggestions=["Check free margin, leverage, and tick data in MT5. Signal was valid but position could not be sized."],
                                        prefs=prefs,
                                        block_reason=_order_err,
                                    )
                                except Exception as _ne:
                                    logger.warning(f"Notifier failed on order build error: {_ne}")
                            else:
                                self.storage.log_event(
                                    "order",
                                    f"OMS Submit: {sig} {order.qty:.2f}L {sym}"
                                    f" | Entry~{close_px:.4f}"
                                    f" | SL={order.stop_loss:.4f} TP={order.take_profit:.4f}"
                                    f" | R:R=1:{order.rr_ratio}"
                                    f" | ADR={adr:.4f} | Leverage=1:{leverage}"
                                    f" | Risk=${self.risk_manager.risk_per_trade:.0f}"
                                    f" | Target=${self.risk_manager.risk_per_trade * self.risk_manager.rr_ratio:.0f}"
                                )
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
                                    self.oms.update_status(order_id, "FAILED")
                                    _exec_msg = f"MT5 order_send FAILED: {_exec_err}"
                                    self.storage.log_event("error", _exec_msg)
                                    try:
                                        from core.notifier import broadcast_risk_alert
                                        broadcast_risk_alert(
                                            alert_type="BLOCKED",
                                            symbol=sym,
                                            warnings=[f"EXECUTION FAILURE: {_exec_msg}"],
                                            suggestions=["Check MT5 terminal immediately — order may NOT have been placed. Verify manually."],
                                            prefs=prefs,
                                            block_reason=_exec_msg,
                                        )
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
            "last_low": result.get('last_low', None) if result else None
        }
