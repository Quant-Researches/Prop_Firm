import json
from datetime import datetime
from pathlib import Path
import logging

from core.dhan_data import fetch_candles, fetch_ltp
from core.strategy import RealTimeSignalGenerator
from core.risk_manager import OrderEvent, RiskManager
from core.oms import OMS
from core.execution import ExecutionEngine
from core.portfolio import Portfolio
from core.storage import Storage
from core.signal_store import save_signal

logger = logging.getLogger("TradingEngine")

class TradingEngine:
    def __init__(self, mode="paper"):
        self.mode = mode
        self.storage = Storage()
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
        """
        Executes a single iteration of the trading pipeline.
        is_manual: True if triggered by the LTS button, False if by scheduler.
        """
        prefs = self.load_prefs()
        tick_type = "manual" if is_manual else "scheduled"
        
        # Ensure storage paths reflect the active execution mode
        execution_mode = prefs.get("execution_mode", "JSON Only")
        self.storage.set_execution_mode(execution_mode)
        
        self.storage.log_event("info", f"Starting {tick_type} pipeline tick (Mode: {execution_mode})...")
        
        # ── 1. Data Feed ──
        sec_id = prefs.get("security_id", "488798")
        exch = prefs.get("exchange_segment", "MCX_COMM")
        inst = prefs.get("instrument_type", "FUTCOM")
        tf = prefs.get("timeframe", "1h")
        client_id = prefs.get("dhan_client_id", "")
        token = prefs.get("dhan_api_key", "")
        data_source = prefs.get("data_source", "Dhan")
        
        df, source, err = fetch_candles(
            security_id=sec_id,
            exchange_segment=exch,
            instrument_type=inst,
            interval=tf,
            client_id=client_id,
            access_token=token,
            bar_count=prefs.get("bar_count", 500),
            fallback_symbol=prefs.get("yf_fallback_symbol", "GC=F"),
            data_source=data_source
        )
        
        if df is None or df.empty:
            self.storage.log_event("error", f"Data fetch failed: {err}")
            return {"error": err}
            
        self.storage.log_event("market", f"Fetched {len(df)} candles via {source}")
        
        # Fetch LTP for reporting if needed
        ltp, ltp_err = 0.0, ""
        if data_source == "Dhan":
            ltp, ltp_err = fetch_ltp(sec_id, exch, client_id, token)
            if ltp > 0:
                self.storage.log_event("market", f"Live LTP: ₹{ltp:,.2f}")
        
        # ── 2. Strategy ──
        sym = prefs.get("trading_symbol", "GOLD")
        if not self.strategy:
            self.strategy = RealTimeSignalGenerator(
                stock_symbol=sym,
                sec_id=sec_id,
                interval=tf,
                use_vol_filter=prefs.get("use_vol_filter", False),
                use_atr_filter=prefs.get("use_atr_filter", True),
                ema_fast=prefs.get("ema_fast", 5),
                ema_slow=prefs.get("ema_slow", 8)
            )
        else:
            # Hot-update dynamic settings
            self.strategy.use_volume_filter = prefs.get("use_vol_filter", False)
            self.strategy.use_atr_filter = prefs.get("use_atr_filter", True)
            self.strategy.ema_short_period = prefs.get("ema_fast", 5)
            self.strategy.ema_long_period = prefs.get("ema_slow", 8)
            
        self.strategy.update_data(df)
        result = self.strategy.run_analysis()
        
        if not result:
            return None

        sig = result.get("Signal", "HOLD")
        phase = result.get("Market_Phase", "SIDEWAYS")
        action = result.get('Action', '')
        
        self.storage.log_event("signal", f"Phase: {phase} | Signal: {sig} | Reason: {action}")
        
        # ── 3. Signal Store (MANDATORY — always runs, regardless of execution mode) ──
        if sig in ["BUY", "SELL"]:
            strategy_df = result.get("data")
            if strategy_df is not None and not strategy_df.empty:
                latest_row = strategy_df.iloc[-1]
                save_signal(
                    latest_row=latest_row,
                    symbol=sym,
                    interval=tf,
                    sec_id=sec_id,
                    signal=sig,
                    reason=action,
                )
                self.storage.log_event("signal", f"Signal saved to data/signals.json")

        # ── 4. Execution Routing (bifurcated by execution_mode) ──
        execution_mode = prefs.get("execution_mode", "JSON Only")
        
        if sig in ["BUY", "SELL"] and execution_mode == "Dhan Realtime":
            # ── 4a. Dhan Realtime: Full OMS → Execution pipeline (existing logic) ──
            close_px = df['Close'].iloc[-1]
            
            # Dynamic position sizing: fetch real capital & leverage from Dhan API
            capital = prefs.get("capital", 100000)   # fallback from settings
            leverage = prefs.get("leverage", 1.0)     # fallback from settings
            risk_warnings = []
            
            if data_source == "Dhan" and client_id and token:
                # Fetch live available balance
                fund_info = RiskManager.fetch_fund_limits(client_id, token)
                if fund_info and fund_info.get("availabelBalance") is not None:
                    bal_str = str(fund_info["availabelBalance"]).upper().replace('X','').strip()
                    capital = float(bal_str)
                    self.storage.log_event("risk", f"✅ Dhan Available Balance: ₹{capital:,.2f}")
                else:
                    err_msg = "❌ CRITICAL: Fund Limits API FAILED — cannot determine available capital. Trade ABORTED to prevent incorrect position sizing."
                    self.storage.log_event("error", err_msg)
                    risk_warnings.append(err_msg)
                    return {
                        "signal": sig, "phase": phase,
                        "ltp": ltp if ltp > 0 else close_px,
                        "action": action, "symbol": sym,
                        "data_source": source, "candles_fetched": len(df),
                        "order": None, "fill": None,
                        "risk_warnings": risk_warnings,
                        "aborted": True,
                        "abort_reason": "Fund Limits API failed — unable to fetch available capital from Dhan.",
                        "df": df
                    }
                
                # Fetch live margin/leverage for this symbol
                margin_info = RiskManager.fetch_live_margin_info(
                    client_id=client_id,
                    access_token=token,
                    security_id=sec_id,
                    exchange_segment=exch,
                    transaction_type=sig,
                    quantity=1,
                    price=close_px
                )
                if margin_info and margin_info.get("leverage"):
                    lev_str = str(margin_info["leverage"]).upper().replace('X','').strip()
                    leverage = float(lev_str)
                    self.storage.log_event("risk", f"✅ Dhan Leverage for {sym}: {leverage}x (margin: ₹{margin_info.get('totalMargin', 'N/A')})")
                else:
                    err_msg = f"❌ CRITICAL: Margin Calculator API FAILED for {sym} — cannot determine leverage. Trade ABORTED."
                    self.storage.log_event("error", err_msg)
                    risk_warnings.append(err_msg)
                    return {
                        "signal": sig, "phase": phase,
                        "ltp": ltp if ltp > 0 else close_px,
                        "action": action, "symbol": sym,
                        "data_source": source, "candles_fetched": len(df),
                        "order": None, "fill": None,
                        "risk_warnings": risk_warnings,
                        "aborted": True,
                        "abort_reason": f"Margin Calculator API failed — unable to fetch leverage for {sym}.",
                        "df": df
                    }
            else:
                warn = "⚠️ Non-Dhan source: using static Capital/Leverage from Settings."
                self.storage.log_event("risk", warn)
                risk_warnings.append(warn)
            
            qty = max(1, int((capital * leverage) // close_px))
            self.storage.log_event("risk", f"Position Size: qty={qty} (₹{capital:,.0f} × {leverage:.1f}x / ₹{close_px:,.2f})")
            
            atr = df['ATR'].iloc[-1] if 'ATR' in df.columns else (close_px * 0.005)
            
            if sig == "BUY":
                sl = close_px - (atr * 1.5)
                tp = close_px + (atr * 3.0)
            else:
                sl = close_px + (atr * 1.5)
                tp = close_px - (atr * 3.0)
            
            order = OrderEvent(
                symbol=sym,
                side=sig,
                qty=qty,
                order_type="MARKET",
                limit_price=close_px,
                stop_loss=sl,
                take_profit=tp
            )
            
            self.storage.log_event("order", f"OMS Submit: {sig} {qty}x {order.symbol} @ ~{close_px:.2f}")
            order_id = self.oms.submit(order)
            
            order.order_id = order_id
            fill = self.execution.execute(order, prefs=(prefs if execution_mode == "Dhan Realtime" else None))
            self.oms.update_status(order_id, "FILLED")
            
            self.storage.log_event("fill", f"{'Live' if execution_mode == 'Dhan Realtime' else 'Simulated'} Fill: {fill.qty}x @ {fill.fill_price:.2f} (comm: \u20b9{fill.commission})")
            self.storage.save_order(order, order_id, "FILLED")
            self.storage.save_trade(fill)
            self.portfolio.on_fill(fill)
            
        elif sig in ["BUY", "SELL"] and execution_mode == "MetaTrader5":
            # ── 4b. MetaTrader5: Placeholder stub ──
            self.storage.log_event("order", f"MT5 Bridge: {sig} signal routed to MetaTrader5 (not yet implemented)")
            logger.warning(f"MetaTrader5 execution not yet implemented. Signal: {sig}")
            
        elif sig in ["BUY", "SELL"] and execution_mode == "JSON Only":
            # ── 4c. JSON Only: Signal already saved above, skip OMS/Execution ──
            self.storage.log_event("info", f"JSON Only mode: {sig} signal saved, no order routed")
            
        # ── 4. Portfolio MTM ──
        current_px = df['Close'].iloc[-1]
        self.portfolio.mark_to_market({sym: current_px})
        
        snap = self.portfolio.get_summary()
        self.storage.save_pnl_snapshot(
            timestamp=datetime.now(),
            equity=snap.equity,
            cash=snap.cash,
            realised_pnl=snap.realised_pnl,
            unrealised_pnl=snap.unrealised_pnl,
            open_positions=snap.open_positions,
            total_trades=snap.total_trades
        )
        self.storage.log_event("info", f"Tick Complete. Open Pos: {snap.open_positions} | Equity: ₹{snap.equity:,.2f} | uPnL: ₹{snap.unrealised_pnl:,.2f}")
        
        return {
            "signal": sig,
            "phase": phase,
            "ltp": ltp if ltp > 0 else current_px,
            "action": action,
            "symbol": sym,
            "data_source": source,
            "candles_fetched": len(df),
            "order": order if 'order' in locals() else None,
            "fill": fill if 'fill' in locals() else None,
            "risk_warnings": risk_warnings if 'risk_warnings' in locals() else [],
            "df": result.get("data", df) if result else df,
            "last_high": result.get('last_high', None) if result else None,
            "last_low": result.get('last_low', None) if result else None
        }
