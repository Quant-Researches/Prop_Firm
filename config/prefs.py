"""
config/prefs.py — shared user preferences loader (daemon + UI + notifier).
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path

logger = logging.getLogger("Prefs")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREFS_FILE = PROJECT_ROOT / "config" / "user_prefs.json"
PREFS_EXAMPLE = PROJECT_ROOT / "config" / "user_prefs.json.example"

DEFAULT_PREFS: dict = {
    "execution_mode": "MetaTrader5",
    "trading_symbol": "XAUUSD",
    "timeframe": "5m",
    "ema_fast": 3,
    "ema_slow": 8,
    "use_vol_filter": True,
    "use_atr_filter": True,
    "bar_count": 300,
    "initial_balance": 10_000.0,
    "ftmo_sod_balance": 10_000.0,
    "mt5_account": "",
    "mt5_password": "",
    "mt5_server": "FTMO-Demo",
    "mt5_path": "",
    "daily_reset_time": "00:00",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "gmail_sender": "",
    "gmail_app_password": "",
    "gmail_receiver": "",
    "alert_telegram": True,
    "alert_email": True,
    "alert_sound": True,
    "alert_desktop": True,
    # Scheduler: notify every tick (incl. HOLD) vs signals/blocks/fills only
    "notify_on_hold": True,
    "notify_on_scheduler_start": True,
}


def load_prefs() -> dict:
    """Load prefs merged with defaults."""
    prefs = deepcopy(DEFAULT_PREFS)
    if PREFS_FILE.exists():
        try:
            saved = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                prefs.update(saved)
        except Exception as e:
            logger.warning("Could not read user_prefs.json: %s", e)
    return prefs


def save_prefs(prefs: dict) -> None:
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = {**DEFAULT_PREFS, **prefs}
    PREFS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def ensure_prefs_file() -> Path:
    """Create user_prefs.json from example or defaults if missing."""
    if PREFS_FILE.exists():
        return PREFS_FILE
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PREFS_EXAMPLE.exists():
        PREFS_FILE.write_text(PREFS_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Created config/user_prefs.json from example — fill in MT5 credentials.")
    else:
        save_prefs(DEFAULT_PREFS)
        logger.info("Created config/user_prefs.json with defaults — fill in MT5 credentials.")
    return PREFS_FILE


def mt5_configured(prefs: dict | None = None) -> bool:
    p = prefs or load_prefs()
    return bool(p.get("mt5_account") and p.get("mt5_password") and p.get("mt5_server"))
