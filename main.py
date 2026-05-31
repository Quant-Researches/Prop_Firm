"""
main.py — Trade Pulse Quants background scheduler daemon.

Run from project root:
    python main.py

Requires: MT5 terminal open, config/user_prefs.json with credentials.

Architecture
------------
This daemon uses a SLEEP-TO-NEXT-CLOSE scheduler:
  1. Read symbol + timeframe from Settings (user_prefs.json).
  2. Call compute_next_candle_close() → exact seconds until next MT5 candle close.
  3. Sleep precisely that many seconds (chunked every 5 min for settings change detection).
  4. Wake up and immediately fire the pipeline in a daemon thread.
  5. Loop back to step 1.

There is NO polling, NO HH:MM string matching, NO schedules.json reading at runtime.
schedules.json is written by the Scheduler UI for display purposes only.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Always run relative to project root
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
    schedule_matches_now,      # kept for --check-schedule CLI
)
from core.candle_timer import compute_next_candle_close, session_info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("Daemon")

SCHEDULES_PATH   = ROOT / "schedules.json"
LAST_FIRED_PATH  = ROOT / "data" / "last_fired.json"
DAILY_RESET_PATH = ROOT / "data" / "daily_reset_date.txt"


# ── schedules.json helpers (display-only; not used for execution) ─────────────

_cached_schedules      = None
_last_schedules_mtime  = 0.0


def load_schedules() -> list[dict]:
    global _cached_schedules, _last_schedules_mtime
    if SCHEDULES_PATH.exists():
        try:
            mtime = os.path.getmtime(SCHEDULES_PATH)
            if _cached_schedules is not None and mtime == _last_schedules_mtime:
                return _cached_schedules
            _cached_schedules = json.loads(SCHEDULES_PATH.read_text(encoding="utf-8"))
            _last_schedules_mtime = mtime
            return _cached_schedules
        except Exception as e:
            logger.error("Failed to load schedules.json: %s", e)
    return []


def save_schedules(schedules: list[dict]) -> None:
    global _cached_schedules, _last_schedules_mtime
    SCHEDULES_PATH.write_text(json.dumps(schedules, indent=2), encoding="utf-8")
    _cached_schedules = schedules
    try:
        _last_schedules_mtime = os.path.getmtime(SCHEDULES_PATH)
    except Exception:
        pass


# ── Restart-safe last-fired guard ─────────────────────────────────────────────

def _load_last_fired() -> str | None:
    """Read the last-fired candle key (YYYY-MM-DD HH:MM) from disk."""
    try:
        if LAST_FIRED_PATH.exists():
            return json.loads(
                LAST_FIRED_PATH.read_text(encoding="utf-8")
            ).get("fired_key")
    except Exception:
        pass
    return None


def _save_last_fired(fired_key: str, close_dt: datetime) -> None:
    """Atomically persist the fired key so a mid-minute restart doesn't re-fire."""
    try:
        LAST_FIRED_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = LAST_FIRED_PATH.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({
                "fired_key": fired_key,
                "close_dt":  close_dt.isoformat(),
                "saved_at":  datetime.now().isoformat(),
            }),
            encoding="utf-8",
        )
        tmp.replace(LAST_FIRED_PATH)   # atomic rename — no partial-write corruption
    except Exception as e:
        logger.warning("Could not persist last_fired: %s", e)


# ── Daily reset guard ─────────────────────────────────────────────────────────

def _daily_reset_done_today() -> bool:
    try:
        if DAILY_RESET_PATH.exists():
            return DAILY_RESET_PATH.read_text().strip() == \
                   datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y-%m-%d")
    except Exception:
        pass
    return False


def _mark_daily_reset_done() -> None:
    try:
        DAILY_RESET_PATH.parent.mkdir(parents=True, exist_ok=True)
        DAILY_RESET_PATH.write_text(
            datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y-%m-%d")
        )
    except Exception as e:
        logger.warning("Could not persist daily_reset_date: %s", e)


# ── Chunked sleep ─────────────────────────────────────────────────────────────

def _chunked_sleep(total_sec: float, chunk_sec: int = 300) -> None:
    """
    Sleep in 5-minute chunks so a symbol/TF change in Settings takes effect
    within 5 minutes rather than waiting the full inter-candle sleep duration.
    """
    remaining = float(total_sec)
    while remaining > 0:
        time.sleep(min(remaining, float(chunk_sec)))
        remaining -= chunk_sec


# ── MT5 connection helper ─────────────────────────────────────────────────────

def ensure_mt5_connected(prefs: dict) -> None:
    import MetaTrader5 as mt5
    from core.mt5_connection import MT5Connection

    if not mt5.terminal_info():
        logger.warning("MT5 disconnected! Attempting auto-recovery…")
        if MT5Connection.connect(
            prefs.get("mt5_account", ""),
            prefs.get("mt5_password", ""),
            prefs.get("mt5_server", ""),
            prefs.get("mt5_path", ""),
        ):
            logger.info("MT5 auto-recovery successful.")
        else:
            logger.error("MT5 auto-recovery failed: %s", mt5.last_error())


# ── Non-blocking pipeline fire ────────────────────────────────────────────────

def _fire_pipeline(engine: TradingEngine, prefs: dict, close_dt: datetime) -> None:
    """
    Run one pipeline tick and dispatch notifications.
    Executed in a daemon thread — never blocks the scheduler loop.
    """
    from core.notifier import process_and_broadcast

    day      = ftmo_day_name(close_dt)
    time_str = ftmo_hhmm(close_dt)

    ensure_mt5_connected(prefs)
    engine.storage.log_event(
        "info",
        f"Candle close → pipeline: {day} {time_str} (FTMO)",
    )
    logger.info("🔥 Pipeline firing: %s %s FTMO", day, time_str)

    try:
        result = engine.run_pipeline_tick(is_manual=False)
        sig = (result or {}).get("signal", "HOLD")
        engine.storage.log_event(
            "info",
            f"Pipeline complete @ {day} {time_str} FTMO | signal={sig}",
        )
        logger.info("✅ Pipeline done — signal=%s", sig)

        if not result:
            result = {
                "symbol":  prefs.get("trading_symbol", "UNKNOWN"),
                "signal":  "HOLD",
                "phase":   "UNKNOWN",
                "error":   "Strategy returned no result",
            }

        # Notifications in a sub-thread so the pipeline thread returns immediately
        threading.Thread(
            target=process_and_broadcast,
            args=(result, prefs, "LTS_AUTOMATIC"),
            daemon=True,
            name=f"Notif-{time_str}",
        ).start()

    except Exception as exc:
        engine.storage.log_event("error", f"Pipeline crash: {exc}")
        logger.exception("Pipeline crash on %s %s", day, time_str)

        def _notify_crash() -> None:
            try:
                from core.notifier import broadcast_risk_alert
                broadcast_risk_alert(
                    alert_type="BLOCKED",
                    symbol=prefs.get("trading_symbol", "UNKNOWN"),
                    warnings=[f"PIPELINE CRASH at {day} {time_str}: {exc}"],
                    suggestions=[
                        "Last tick FAILED. Check data/events.jsonl.",
                        "Restart daemon after fixing the issue.",
                    ],
                    prefs=prefs,
                    block_reason=str(exc),
                )
            except Exception:
                pass

        threading.Thread(target=_notify_crash, daemon=True).start()


# ── Daily reset ───────────────────────────────────────────────────────────────

def run_daily_reset(engine: TradingEngine, prefs: dict, prefs_path: Path, reset_time: str) -> None:
    """Reconnect MT5 and snapshot start-of-day balance (Prague time)."""
    from core.mt5_connection import MT5Connection
    import MetaTrader5 as mt5

    acc  = prefs.get("mt5_account")
    pwd  = prefs.get("mt5_password")
    svr  = prefs.get("mt5_server")
    path = prefs.get("mt5_path", "")

    if not (acc and pwd and svr):
        engine.storage.log_event(
            "warning", "Daily reset skipped — MT5 credentials not configured."
        )
        return

    engine.storage.log_event(
        "info",
        f"Executing scheduled {reset_time} MT5 reconnect & SOD snapshot…",
    )
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


# ── Main loop — SLEEP-TO-NEXT-CLOSE ──────────────────────────────────────────

def main_loop() -> None:
    ensure_prefs_file()
    prefs      = load_prefs()
    prefs_path = ROOT / "config" / "user_prefs.json"
    engine     = TradingEngine(mode="live")

    from core.bot_lifecycle import log_bot_started
    log_bot_started(
        "daemon",
        mode="live",
        symbol=prefs.get("trading_symbol", ""),
        timeframe=prefs.get("timeframe", ""),
        extra={"mt5_configured": mt5_configured(prefs)},
    )

    print("=" * 66)
    print("  Trade Pulse Quants — Sleep-to-Close Scheduler STARTED")
    print(f"  Symbol    : {prefs.get('trading_symbol')}")
    print(f"  Timeframe : {prefs.get('timeframe')}")
    sess = session_info(prefs.get("trading_symbol", "XAUUSD"))
    print(f"  Session   : {sess['label']} FTMO (Europe/Helsinki)")
    print(f"  Root      : {ROOT}")
    print(f"  Logs      : data/events.jsonl | data/bot_lifecycle.log")
    print(f"  MT5 ready : {mt5_configured(prefs)}")
    print("  Press Ctrl+C to stop.")
    print("=" * 66)

    # Startup notification (non-blocking)
    from core.notifier import broadcast_daemon_started
    threading.Thread(
        target=broadcast_daemon_started,
        args=(prefs, 0),
        daemon=True,
    ).start()

    if not mt5_configured(prefs):
        logger.warning(
            "MT5 credentials missing in config/user_prefs.json — "
            "pipeline ticks will fail until Settings are saved."
        )

    # Restore last-fired key from disk (survives daemon restart mid-minute)
    last_fired_key: str | None = _load_last_fired()
    logger.info("Startup last_fired_key=%s", last_fired_key)

    # ── Scheduler loop ────────────────────────────────────────────────────────
    while True:
        # 1. Reload settings (Settings page may have changed symbol / TF)
        prefs  = load_prefs()
        symbol = prefs.get("trading_symbol", "XAUUSD")
        tf     = prefs.get("timeframe",      "1h")
        now    = now_ftmo()

        # 2. Daily reset (Prague midnight, once per calendar day, disk-guarded)
        reset_time  = prefs.get("daily_reset_time", "00:00")
        now_prg_str = datetime.now(ZoneInfo("Europe/Prague")).strftime("%H:%M")
        if now_prg_str == reset_time and not _daily_reset_done_today():
            try:
                run_daily_reset(engine, prefs, prefs_path, reset_time)
                _mark_daily_reset_done()
            except Exception as exc:
                engine.storage.log_event("error", f"Daily reset failed: {exc}")
                logger.exception("Daily reset failed")
                try:
                    from core.notifier import broadcast_risk_alert
                    broadcast_risk_alert(
                        alert_type="BLOCKED",
                        symbol=symbol,
                        warnings=[f"DAILY RESET / MT5 RECONNECT FAILED: {exc}"],
                        suggestions=["SOD balance NOT saved. Check MT5 and restart daemon."],
                        prefs=prefs,
                        block_reason=str(exc),
                    )
                except Exception:
                    pass

        # 3. Compute exact seconds to next candle close
        try:
            next_close_dt, sleep_sec = compute_next_candle_close(symbol, tf, now)
        except ValueError as ve:
            logger.error("Invalid TF/symbol config: %s — sleeping 60 s", ve)
            time.sleep(60)
            continue
        except Exception as exc:
            logger.exception("compute_next_candle_close failed — sleeping 60 s: %s", exc)
            time.sleep(60)
            continue

        logger.info(
            "⏱  Next %-3s close: %s FTMO  (sleep=%.0f s / %.1f min)",
            tf,
            next_close_dt.strftime("%A %d %b %H:%M"),
            sleep_sec,
            sleep_sec / 60,
        )

        # 4. Precise sleep — chunked every 5 min to detect settings changes
        _chunked_sleep(sleep_sec, chunk_sec=300)

        # 5. Post-sleep sanity checks
        wake_now = now_ftmo()

        if wake_now.weekday() >= 5:          # Saturday=5, Sunday=6
            logger.info(
                "Weekend (%s) — no pipeline tick. Sleeping to Monday.",
                wake_now.strftime("%A"),
            )
            continue

        # Reload prefs (settings may have changed during long sleep)
        prefs  = load_prefs()
        symbol = prefs.get("trading_symbol", "XAUUSD")
        tf     = prefs.get("timeframe", "1h")

        # 6. Restart-safety dedup guard (disk-persisted)
        fire_key = next_close_dt.strftime("%Y-%m-%d %H:%M")
        if last_fired_key == fire_key:
            logger.warning(
                "🔁 Restart guard: slot %s already fired — skipping double-fire.",
                fire_key,
            )
            continue

        # 7. Persist BEFORE launching (crash-safe: if crash after persist,
        #    restart correctly skips this slot instead of double-firing)
        last_fired_key = fire_key
        _save_last_fired(fire_key, next_close_dt)

        # 8. Fire pipeline in daemon thread — scheduler loop is never blocked
        threading.Thread(
            target=_fire_pipeline,
            args=(engine, prefs, next_close_dt),
            daemon=True,
            name=f"Pipeline-{fire_key}",
        ).start()

        # Loop immediately to compute the NEXT close
        # (pipeline runs in parallel; scheduler doesn't wait for it)


# ── CLI helpers ───────────────────────────────────────────────────────────────

def check_schedule_now() -> None:
    """Print whether any schedule slot matches current FTMO minute."""
    ensure_prefs_file()
    now    = now_ftmo()
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

    # Also show sleep-to-close calculation
    prefs  = load_prefs()
    symbol = prefs.get("trading_symbol", "XAUUSD")
    tf     = prefs.get("timeframe", "1h")
    try:
        nxt_close, secs = compute_next_candle_close(symbol, tf, now)
        print(
            f"\nSleep-to-close: next {tf} close = "
            f"{nxt_close.strftime('%A %H:%M')} FTMO  ({secs:.0f} s)"
        )
    except Exception as e:
        print(f"compute_next_candle_close error: {e}")


def run_once_now() -> None:
    """Run a single pipeline tick immediately (for testing)."""
    ensure_prefs_file()
    prefs  = load_prefs()
    engine = TradingEngine(mode="live")
    now_hel = now_ftmo()
    print(f"Manual tick — {ftmo_display(now_hel)}")
    _fire_pipeline(engine, prefs, now_hel)
    time.sleep(3)   # give notification thread time to start
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
