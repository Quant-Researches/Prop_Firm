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
            
            # --- Auto Token Generation via TOTP at Midnight ---
            if current_time == "00:00":
                try:
                    from core.dhan_auth import DhanAutoLogin
                    p = Path("config/user_prefs.json")
                    if p.exists():
                        prefs = json.loads(p.read_text(encoding="utf-8"))
                        c_id = prefs.get("dhan_client_id")
                        c_pin = prefs.get("dhan_pin")
                        c_totp = prefs.get("totp_secret")
                        
                        if c_id and c_pin and c_totp:
                            engine.storage.log_event("info", "Executing scheduled 00:00 Dhan API Token generation via TOTP...")
                            DhanAutoLogin.generate_and_save_token(c_id, c_pin, c_totp, str(p))
                            engine.storage.log_event("info", "Dhan access token generated and saved successfully.")
                except Exception as e:
                    engine.storage.log_event("error", f"Scheduled token generation failed: {e}")
                    print(f"Error in scheduled TOTP token generation: {e}")
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
