import time
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from core.engine import TradingEngine

def load_schedules():
    p = Path("schedules.json")
    if p.exists():
        try:
            return json.loads(p.read_text())
        except:
            pass
    return []

# Initialize the shared engine
engine = TradingEngine(mode="live")

def main_loop():
    print("Trade Pulse Quants: Background Execution Engine (Live Mode)")
    print("Press Ctrl+C to exit. Logs are written to data/events.jsonl")
    engine.storage.log_event("info", "Background Execution Engine Started (Live Mode).")
    
    last_run_minute = None
    
    while True:
        # Dual-Core Time tracking for absolute alignment with FTMO
        # We use Europe/Helsinki (EET/EEST) for schedules & chart alignment,
        # and Europe/Prague (CET/CEST) strictly for daily drawdown reset tracking!
        now_hel = datetime.now(ZoneInfo("Europe/Helsinki"))
        now_prg = datetime.now(ZoneInfo("Europe/Prague"))
        
        current_day_hel  = now_hel.strftime("%A")
        current_time_hel = now_hel.strftime("%H:%M")
        current_minute   = now_hel.strftime("%Y-%m-%d %H:%M")
        
        current_time_prg = now_prg.strftime("%H:%M")
        
        # Only check once per minute
        if last_run_minute != current_minute:
            
            # --- Auto MT5 Reconnection & Snapshot at Configured Reset Time ---
            p = Path("config/user_prefs.json")
            prefs = {}
            if p.exists():
                try:
                    prefs = json.loads(p.read_text(encoding="utf-8"))
                except:
                    pass
            
            reset_time = prefs.get("daily_reset_time", "00:00")
            
            # Daily reset triggers strictly on Prague Time (CE(S)T) as configured in the settings!
            if current_time_prg == reset_time:
                try:
                    from core.mt5_connection import MT5Connection
                    acc = prefs.get("mt5_account")
                    pwd = prefs.get("mt5_password")
                    svr = prefs.get("mt5_server")
                    if acc and pwd and svr:
                        engine.storage.log_event("info", f"Executing scheduled {reset_time} MT5 Reconnection & Snapshot...")
                        if MT5Connection.connect(int(acc), pwd, svr):
                            import MetaTrader5 as mt5
                            acc_info = mt5.account_info()
                            if acc_info:
                                prefs["ftmo_sod_balance"] = float(acc_info.balance)
                                p.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
                                engine.storage.log_event(
                                    "info",
                                    f"SOD Snapshot: Balance={acc_info.balance} "
                                    f"| Prague Time={now_prg.strftime('%H:%M')} (reset time) "
                                    f"| Helsinki Time={now_hel.strftime('%H:%M')} "
                                    f"| IST={datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%H:%M')}"
                                )
                except Exception as e:
                    engine.storage.log_event("error", f"Scheduled MT5 task failed: {e}")
                    print(f"Error in scheduled MT5 task: {e}")
                    try:
                        from core.notifier import broadcast_risk_alert
                        broadcast_risk_alert(
                            alert_type="BLOCKED",
                            symbol=prefs.get("trading_symbol", "UNKNOWN"),
                            warnings=[f"DAILY RESET / MT5 RECONNECT FAILED: {e}"],
                            suggestions=["SOD balance snapshot was NOT saved. Check MT5 credentials and restart the bot."],
                            prefs=prefs,
                            block_reason=str(e),
                        )
                    except Exception:
                        pass
            # --------------------------------------------------

            scheds = load_schedules()
            should_run = False
            
            for s in scheds:
                # Schedules are checked strictly against Helsinki broker time
                if s.get("enabled", True) and s.get("day") == current_day_hel and s.get("time") == current_time_hel:
                    should_run = True
                    break
                    
            if should_run:
                try:
                    result = engine.run_pipeline_tick(is_manual=False)
                    if result:
                        engine.storage.log_event("info", f"Scheduler execution complete: {result.get('signal', 'HOLD')}")
                        
                        # Load prefs payload for the Broadcaster
                        p = Path("config/user_prefs.json")
                        prefs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
                        
                        import threading
                        from core.notifier import process_and_broadcast
                        bg_thread = threading.Thread(
                            target=process_and_broadcast,
                            args=(result, prefs, "LTS_AUTOMATIC")
                        )
                        bg_thread.start()

                except Exception as e:
                    engine.storage.log_event("error", f"Pipeline crash: {str(e)}")
                    print(f"Error in pipeline tick: {e}")
                    try:
                        from core.notifier import broadcast_risk_alert
                        _crash_prefs = json.loads(Path("config/user_prefs.json").read_text(encoding="utf-8")) if Path("config/user_prefs.json").exists() else {}
                        broadcast_risk_alert(
                            alert_type="BLOCKED",
                            symbol=_crash_prefs.get("trading_symbol", "UNKNOWN"),
                            warnings=[f"SCHEDULER PIPELINE CRASH: {str(e)}"],
                            suggestions=["Last scheduled tick FAILED. Bot is still running but trade was not executed. Check logs."],
                            prefs=_crash_prefs,
                            block_reason=str(e),
                        )
                    except Exception:
                        pass
                finally:
                    last_run_minute = current_minute
                    
        time.sleep(10)

if __name__ == "__main__":
    main_loop()
