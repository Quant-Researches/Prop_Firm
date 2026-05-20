"""
core/bot_lifecycle.py — persistent start/stop logging for dashboard + scheduler daemon.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.storage import Storage

logger = logging.getLogger("BotLifecycle")

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "bot_state.json"
LIFECYCLE_LOG = ROOT / "data" / "bot_lifecycle.log"


def _ensure_data_dir() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    _ensure_data_dir()
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"dashboard": {}, "daemon": {}}


def _save_state(state: dict) -> None:
    _ensure_data_dir()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_lifecycle_log(line: str) -> None:
    _ensure_data_dir()
    with LIFECYCLE_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _format_uptime(started_at: Optional[str]) -> str:
    if not started_at:
        return "00:00:00"
    try:
        start = datetime.fromisoformat(started_at)
        delta = datetime.now() - start
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "00:00:00"


def log_bot_started(
    source: str,
    *,
    mode: str = "Live",
    symbol: str = "",
    timeframe: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log bot/daemon START.

    source: 'dashboard' | 'daemon'
    """
    now = datetime.now()
    now_iso = now.isoformat()
    pid = os.getpid()

    details = extra or {}
    parts = [
        f"source={source}",
        f"mode={mode}",
    ]
    if symbol:
        parts.append(f"symbol={symbol}")
    if timeframe:
        parts.append(f"timeframe={timeframe}")
    if source == "daemon":
        parts.append(f"pid={pid}")
    for k, v in details.items():
        parts.append(f"{k}={v}")

    msg = "BOT STARTED | " + " | ".join(parts)
    storage = Storage()
    storage.log_event("bot", msg)
    logger.info(msg)

    line = f"{now_iso} | START | {source.upper()} | {msg.replace('BOT STARTED | ', '')}"
    _append_lifecycle_log(line)

    state = _load_state()
    state[source] = {
        "running": True,
        "started_at": now_iso,
        "stopped_at": None,
        "mode": mode,
        "symbol": symbol,
        "timeframe": timeframe,
        "pid": pid if source == "daemon" else None,
    }
    _save_state(state)


def log_bot_stopped(
    source: str,
    *,
    reason: str = "user",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log bot/daemon STOP.

    source: 'dashboard' | 'daemon'
    reason: 'user' | 'keyboard_interrupt' | 'error' | ...
    """
    now = datetime.now()
    now_iso = now.isoformat()

    state = _load_state()
    entry = state.get(source, {})
    started_at = entry.get("started_at")
    uptime = _format_uptime(started_at)

    details = extra or {}
    parts = [
        f"source={source}",
        f"reason={reason}",
        f"uptime={uptime}",
    ]
    if started_at:
        parts.append(f"started_at={started_at}")
    for k, v in details.items():
        parts.append(f"{k}={v}")

    msg = "BOT STOPPED | " + " | ".join(parts)
    storage = Storage()
    storage.log_event("bot", msg)
    logger.info(msg)

    line = f"{now_iso} | STOP | {source.upper()} | " + " | ".join(parts)
    _append_lifecycle_log(line)

    state[source] = {
        "running": False,
        "started_at": started_at,
        "stopped_at": now_iso,
        "last_uptime": uptime,
        "last_stop_reason": reason,
        "mode": entry.get("mode"),
        "symbol": entry.get("symbol"),
        "timeframe": entry.get("timeframe"),
    }
    _save_state(state)


def get_bot_state() -> dict:
    """Return persisted dashboard + daemon run state."""
    return _load_state()
