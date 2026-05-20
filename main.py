"""
main.py — Trade Pulse Quants background scheduler daemon.

Run from project root:
    python main.py

Requires: MT5 terminal open, config/user_prefs.json with credentials.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Always run relative to project root (schedules.json, data/, config/)
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.prefs import ensure_prefs_file, load_prefs, mt5_configured
from core.engine import TradingEngine
from core.ftmo_time import (
    ftmo_day_name,
    ftmo_display,
    ftmo_hhmm,
    now_ftmo,
    schedule_matches_now,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("Daemon")

SCHEDULES_PATH = ROOT / "schedules.json"


def load_schedules() -> list[dict]:
    if SCHEDULES_PATH.exists():
        try:
            return json.loads(SCHEDULES_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load schedules.json: %s", e)
    return []


def save_schedules(schedules: list[dict]) -> None:
    SCHEDULES_PATH.write_text(json.dumps(schedules, indent=2), encoding="utf-8")


def mark_schedule_run(day: str, time_str: str) -> None:
    """Mark slot as completed after pipeline ran (resets on next week's same slot)."""
    scheds = load_schedules()
    updated = False
    now_iso = now_ftmo().isoformat()
    for s in scheds:
        if s.get("day") == day and s.get("time") == time_str:
            s["last_run"] = now_iso
            s["pipeline_status"] = "completed"
            updated = True
    if updated:
        save_schedules(scheds)


def run_scheduled_tick(engine: TradingEngine, prefs: dict, day: str, time_str: str) -> None:
    """Execute one pipeline tick and send notifications."""
    from core.notifier import process_and_broadcast

    logger.info("Scheduler firing: %s %s (FTMO candle close)", day, time_str)
    engine.storage.log_event(
        "info",
        f"Candle close → pipeline start: {day} {time_str} (FTMO)",
    )

    # Brief delay so MT5 has finished writing the closed bar to history
    time.sleep(3)

    try:
        result = engine.run_pipeline_tick(is_manual=False)
        mark_schedule_run(day, time_str)

        if result:
            sig = result.get("signal", "HOLD")
            engine.storage.log_event(
                "info",
                f"Pipeline complete @ {day} {time_str} FTMO | signal={sig} | status=Pipeline Already Run",
            )
            logger.info("Tick complete — signal=%s — slot marked completed", sig)
        else:
            engine.storage.log_event("warning", "Scheduler tick returned no result.")
            result = {
                "symbol": prefs.get("trading_symbol", "UNKNOWN"),
                "signal": "HOLD",
                "phase": "UNKNOWN",
                "error": "Strategy returned no result",
            }

        # Blocking call — waits for Telegram/email/desktop threads (see notifier._run_threads)
        process_and_broadcast(result, prefs, "LTS_AUTOMATIC")

    except Exception as e:
        engine.storage.log_event("error", f"Pipeline crash: {e}")
        logger.exception("Pipeline crash on scheduled tick")
        try:
            from core.notifier import broadcast_risk_alert
            broadcast_risk_alert(
                alert_type="BLOCKED",
                symbol=prefs.get("trading_symbol", "UNKNOWN"),
                warnings=[f"SCHEDULER PIPELINE CRASH: {e}"],
                suggestions=[
                    "Last scheduled tick FAILED.",
                    "Check data/events.jsonl and restart main.py after fixing MT5.",
                ],
                prefs=prefs,
                block_reason=str(e),
            )
        except Exception:
            logger.exception("Failed to send crash notification")


def run_daily_reset(engine: TradingEngine, prefs: dict, prefs_path: Path, reset_time: str) -> None:
    """Reconnect MT5 and snapshot start-of-day balance (Prague time)."""
    from core.mt5_connection import MT5Connection
    import MetaTrader5 as mt5

    acc = prefs.get("mt5_account")
    pwd = prefs.get("mt5_password")
    svr = prefs.get("mt5_server")
    path = prefs.get("mt5_path", "")

    if not (acc and pwd and svr):
        engine.storage.log_event("warning", "Daily reset skipped — MT5 credentials not configured.")
        return

    engine.storage.log_event("info", f"Executing scheduled {reset_time} MT5 reconnect & SOD snapshot...")
    if not MT5Connection.connect(acc, pwd, svr, path):
        raise RuntimeError(f"MT5 reconnect failed: {mt5.last_error()}")

    acc_info = mt5.account_info()
    if not acc_info:
        raise RuntimeError("mt5.account_info() returned None after reconnect")

    prefs["ftmo_sod_balance"] = float(acc_info.balance)
    prefs_path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    engine.risk_manager.update_starting_balance(float(acc_info.balance))

    now_prg = datetime.now(ZoneInfo("Europe/Prague"))
    now_hel = datetime.now(ZoneInfo("Europe/Helsinki"))
    engine.storage.log_event(
        "info",
        f"SOD Snapshot: Balance={acc_info.balance} "
        f"| Prague={now_prg.strftime('%H:%M')} "
        f"| Helsinki={now_hel.strftime('%H:%M')}",
    )

    from core.notifier import broadcast_risk_alert
    broadcast_risk_alert(
        alert_type="INFO",
        symbol=prefs.get("trading_symbol", "UNKNOWN"),
        warnings=[
            f"Daily SOD balance snapshot saved: ${acc_info.balance:,.2f}",
            f"Reset time (Prague): {reset_time}",
        ],
        suggestions=["Drawdown limits reset against this balance for the new FTMO day."],
        prefs=prefs,
        block_reason="Daily reset OK",
    )


def main_loop() -> None:
    ensure_prefs_file()
    prefs = load_prefs()
    prefs_path = ROOT / "config" / "user_prefs.json"

    engine = TradingEngine(mode="live")

    scheds = load_schedules()
    enabled_count = sum(1 for s in scheds if s.get("enabled", True))

    from core.bot_lifecycle import log_bot_started
    log_bot_started(
        "daemon",
        mode="live",
        symbol=prefs.get("trading_symbol", ""),
        timeframe=prefs.get("timeframe", ""),
        extra={"schedule_slots": enabled_count, "mt5_configured": mt5_configured(prefs)},
    )

    print("=" * 60)
    print("Trade Pulse Quants — Scheduler Daemon STARTED")
    print(f"Project root: {ROOT}")
    print(f"Symbol: {prefs.get('trading_symbol')} | TF: {prefs.get('timeframe')}")
    print(f"Schedule slots (enabled): {enabled_count}")
    print(f"MT5 configured: {mt5_configured(prefs)}")
    print("Logs → data/events.jsonl  |  data/bot_lifecycle.log")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    from core.notifier import broadcast_daemon_started
    broadcast_daemon_started(prefs, enabled_count)

    if not mt5_configured(prefs):
        logger.warning(
            "MT5 credentials missing in config/user_prefs.json — "
            "pipeline ticks will fail until Settings are saved."
        )

    last_run_minute = None

    while True:
        now_hel = now_ftmo()
        now_prg = datetime.now(ZoneInfo("Europe/Prague"))

        current_day_hel = ftmo_day_name(now_hel)
        current_time_hel = ftmo_hhmm(now_hel)
        current_minute = now_hel.strftime("%Y-%m-%d %H:%M")
        current_time_prg = now_prg.strftime("%H:%M")

        if last_run_minute != current_minute:
            logger.debug(
                "Tick check | FTMO %s | day=%s time=%s",
                ftmo_display(now_hel),
                current_day_hel,
                current_time_hel,
            )
            prefs = load_prefs()  # refresh each minute (UI may have saved new settings)
            reset_time = prefs.get("daily_reset_time", "00:00")

            if current_time_prg == reset_time:
                try:
                    run_daily_reset(engine, prefs, prefs_path, reset_time)
                except Exception as e:
                    engine.storage.log_event("error", f"Scheduled MT5 task failed: {e}")
                    logger.exception("Daily reset failed")
                    try:
                        from core.notifier import broadcast_risk_alert
                        broadcast_risk_alert(
                            alert_type="BLOCKED",
                            symbol=prefs.get("trading_symbol", "UNKNOWN"),
                            warnings=[f"DAILY RESET / MT5 RECONNECT FAILED: {e}"],
                            suggestions=["SOD balance was NOT saved. Check MT5 and restart daemon."],
                            prefs=prefs,
                            block_reason=str(e),
                        )
                    except Exception:
                        pass

            scheds = load_schedules()
            matched_slot = None
            for s in scheds:
                if schedule_matches_now(s, now_hel):
                    matched_slot = s
                    break

            last_run_minute = current_minute

            if matched_slot:
                logger.info(
                    "Schedule MATCH | %s %s (FTMO) | id=%s",
                    current_day_hel,
                    current_time_hel,
                    matched_slot.get("id", "?"),
                )
                run_scheduled_tick(engine, prefs, current_day_hel, current_time_hel)
            else:
                # Log once per minute at :00 seconds area — helps debug missed slots
                enabled_today = [
                    s["time"]
                    for s in scheds
                    if s.get("enabled", True) and s.get("day") == current_day_hel
                ]
                if enabled_today and current_time_hel.endswith(":00"):
                    logger.debug(
                        "No slot at %s %s | today has %d slots (e.g. %s)",
                        current_day_hel,
                        current_time_hel,
                        len(enabled_today),
                        ", ".join(sorted(enabled_today)[:5]),
                    )

        time.sleep(10)


def check_schedule_now() -> None:
    """Print whether any schedule slot matches current FTMO minute."""
    ensure_prefs_file()
    now = now_ftmo()
    scheds = load_schedules()
    print(ftmo_display(now))
    print(f"Day (EN): {ftmo_day_name(now)} | Time: {ftmo_hhmm(now)}")
    matches = [s for s in scheds if schedule_matches_now(s, now)]
    if matches:
        print(f"MATCH: {len(matches)} slot(s) — {matches[0].get('id')}")
    else:
        from core.ftmo_time import find_next_schedule
        nxt, nxt_dt = find_next_schedule(scheds)
        print("No match this minute.")
        if nxt and nxt_dt:
            print(f"Next slot: {nxt['day']} {nxt['time']} (FTMO) — in {nxt_dt - now}")


def run_once_now() -> None:
    """Run a single pipeline tick immediately (for testing scheduler + notifications)."""
    ensure_prefs_file()
    prefs = load_prefs()
    engine = TradingEngine(mode="live")
    now_hel = now_ftmo()
    print(f"Manual tick — {ftmo_display(now_hel)}")
    run_scheduled_tick(engine, prefs, ftmo_day_name(now_hel), ftmo_hhmm(now_hel))
    print("Done. Check Telegram / data/events.jsonl")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--tick-now", "--test"):
        run_once_now()
    elif len(sys.argv) > 1 and sys.argv[1] == "--check-schedule":
        check_schedule_now()
    else:
        try:
            main_loop()
        except KeyboardInterrupt:
            from core.bot_lifecycle import log_bot_stopped
            log_bot_stopped("daemon", reason="keyboard_interrupt")
            print("\nScheduler daemon STOPPED (Ctrl+C). See data/bot_lifecycle.log")
        except Exception as e:
            from core.bot_lifecycle import log_bot_stopped
            log_bot_stopped("daemon", reason="error", extra={"error": str(e)})
            logger.exception("Daemon exited with error")
            raise
