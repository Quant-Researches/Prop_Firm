import time
import json
from datetime import datetime
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
engine = TradingEngine(mode="paper")

def main_loop():
    print("Trade Pulse Quants: Background Execution Engine (Paper Mode)")
    print("Press Ctrl+C to exit. Logs are written to data/events.jsonl")
    engine.storage.log_event("info", "Background Execution Engine Started (Paper Mode).")
    
    last_run_minute = None
    
    while True:
        now = datetime.now()
        current_day = now.strftime("%A")
        current_time = now.strftime("%H:%M")
        current_minute = now.strftime("%Y-%m-%d %H:%M")
        
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
            
            if current_time == reset_time:
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
                                engine.storage.log_event("info", f"✅ Snapshot: Updated Start of Day Balance to {acc_info.balance}")
                except Exception as e:
                    engine.storage.log_event("error", f"Scheduled MT5 task failed: {e}")
                    print(f"Error in scheduled MT5 task: {e}")
            # --------------------------------------------------

            scheds = load_schedules()
            should_run = False
            
            for s in scheds:
                if s.get("enabled", True) and s.get("day") == current_day and s.get("time") == current_time:
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
                    engine.storage.log_event("info", f"Pipeline crash: {str(e)}")
                    print(f"Error in pipeline tick: {e}")
                finally:
                    last_run_minute = current_minute
                    
        time.sleep(10)

if __name__ == "__main__":
    main_loop()
