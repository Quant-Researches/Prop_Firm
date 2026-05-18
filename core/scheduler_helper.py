"""
core/scheduler_helper.py
========================
Automatic Schedule Generator for FTMO-compliant prop trading systems.
Automatically aligns schedules with standard FTMO active hours for XAUUSD (Gold).

Timezones:
- FTMO MT5 Server Time: Europe/Helsinki (EET/EEST = GMT+2/GMT+3)
- Scheduler Execution Time: Europe/Helsinki (EET/EEST = GMT+2/GMT+3)

Active hours for XAUUSD on FTMO:
- MT5 Broker Session: Monday 01:05 to Friday 23:59 (excluding daily breaks 23:59 to 01:05)
- General Tradeable hours per day: 01:05 to 23:59 FTMO Server Time (Europe/Helsinki).
"""

from __future__ import annotations
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("SchedulerHelper")

SCHEDULES_FILE = Path("schedules.json")

def generate_ftmo_schedule(symbol: str, timeframe_str: str) -> list[dict]:
    """
    Generates trading schedule slots matching standard FTMO active hours for XAUUSD
    and other instruments, aligned with the selected timeframe/interval.
    
    Active hours: Monday to Friday from 01:05 to 23:59 FTMO Time (Europe/Helsinki).
    Timeframe steps:
        - "1m": every 1 minute
        - "5m": every 5 minutes
        - "15m": every 15 minutes
        - "30m": every 30 minutes
        - "1h": every 60 minutes (1 hour)
        - "4h": every 240 minutes (4 hours)
        - "1d": daily reset or once per day
    """
    tf_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440
    }
    
    step = tf_minutes.get(timeframe_str, 5)
    active_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    new_schedules = []
    
    for day in active_days:
        # Tradeable window in FTMO Time minutes of day:
        # 01:05 is 65 minutes (1 * 60 + 5).
        # 23:59 is 1439 minutes (23 * 60 + 59).
        start_min = 65
        end_min = 1439
        
        # 1-day timeframe runs once per day, near daily close
        if step == 1440:
            new_schedules.append({
                "id": f"SCH_{day}_2300_{uuid.uuid4().hex[:6].upper()}",
                "day": day,
                "time": "23:00",
                "enabled": True,
                "created_at": datetime.now().isoformat(),
                "last_run": None
            })
            continue
            
        # Hour-aligned intervals (e.g. 02:00, 03:00...)
        if step >= 60:
            current_min = 120  # First standard close is 02:00 (120 min)
            while current_min <= 1380:  # 23:00
                if start_min <= current_min <= end_min:
                    hh = current_min // 60
                    mm = current_min % 60
                    time_str = f"{hh:02d}:{mm:02d}"
                    new_schedules.append({
                        "id": f"SCH_{day}_{hh:02d}{mm:02d}_{uuid.uuid4().hex[:6].upper()}",
                        "day": day,
                        "time": time_str,
                        "enabled": True,
                        "created_at": datetime.now().isoformat(),
                        "last_run": None
                    })
                current_min += step
        else:
            # Minute-aligned intervals starting at 01:05
            current_min = start_min
            while current_min <= end_min:
                hh = current_min // 60
                mm = current_min % 60
                time_str = f"{hh:02d}:{mm:02d}"
                new_schedules.append({
                    "id": f"SCH_{day}_{hh:02d}{mm:02d}_{uuid.uuid4().hex[:6].upper()}",
                    "day": day,
                    "time": time_str,
                    "enabled": True,
                    "created_at": datetime.now().isoformat(),
                    "last_run": None
                })
                current_min += step
                
    return new_schedules


def update_and_save_schedule(symbol: str, timeframe_str: str, prefs: dict = None) -> tuple[int, str]:
    """
    Clears existing schedules and writes newly auto-generated schedules for the symbol and timeframe.
    Sends Telegram / SMTP alerts if config is enabled.
    Returns: (count of schedules created, log_message)
    """
    new_scheds = generate_ftmo_schedule(symbol, timeframe_str)
    
    try:
        SCHEDULES_FILE.write_text(json.dumps(new_scheds, indent=2), encoding="utf-8")
        msg = f"Automatically regenerated FTMO-compliant schedule for {symbol} ({timeframe_str}): {len(new_scheds)} slots created."
        logger.info(msg)
    except Exception as e:
        err_msg = f"Failed to save auto-generated schedule to file: {e}"
        logger.error(err_msg)
        return 0, err_msg
        
    try:
        from core.storage import Storage
        storage = Storage()
        storage.log_event("info", msg)
    except Exception as ex:
        logger.warning(f"Could not log event to storage: {ex}")
        
    if prefs:
        try:
            from core.notifier import broadcast_risk_alert
            warnings = [
                f"SCHEDULE AUTOMATICALLY UPDATED (FTMO TIME)",
                f"Asset Symbol: {symbol}",
                f"Timeframe Interval: {timeframe_str}",
                f"Total Active Slots: {len(new_scheds)}",
                f"Active Window: Mon-Fri 01:05 to 23:59 (FTMO Server Time)",
                f"All previous custom schedules have been purged."
            ]
            suggestions = [
                "Verify the generated schedule table on the dashboard.",
                "Ensure background process (main.py) is active to handle the slots."
            ]
            broadcast_risk_alert(
                alert_type="INFO",
                symbol=symbol,
                warnings=warnings,
                suggestions=suggestions,
                prefs=prefs,
                block_reason="Automatic Schedule Update"
            )
        except Exception as notif_err:
            logger.warning(f"Failed to send schedule notification: {notif_err}")
            
    return len(new_scheds), msg
