"""
config/config.py
================
Single source of truth for all project configuration.

Usage
-----
    from config.config import config

    config.load()                    # load from disk (call once at startup)
    val = config.dhan_api_key        # read a value
    config.dhan_api_key = "xyz"      # set a value
    config.save()                    # persist to disk
"""

from __future__ import annotations
import json
from pathlib import Path

# On-disk path — sits next to this file
_SAVE_PATH = Path(__file__).parent / "saved_config.json"


class _Config:
    """
    Project-level configuration.  All settings are plain attributes so they
    are easy to read and write anywhere in the app.  Call load() once at startup
    and save() whenever values change.
    """

    # ── Dhan API Credentials ─────────────────────────────────────────────
    dhan_client_id: str = ""
    dhan_api_key: str = ""

    # ── Dhan API ─────────────────────────────────────────────────────────
    dhan_base_url: str = "https://api.dhan.co/v2"

    # ── Instrument ───────────────────────────────────────────────────────
    trading_symbol: str = "Gold Petal (1g)"
    security_id: str = "626"
    exchange_segment: str = "MCX_COMM"
    instrument_type: str = "FUTCOM"
    yf_fallback_symbol: str = "GC=F"

    # ── Strategy ─────────────────────────────────────────────────────────
    timeframe: str = "5m"
    ema_fast: int = 3
    ema_slow: int = 8
    use_vol_filter: bool = True
    bar_count: int = 300

    # ── Risk ─────────────────────────────────────────────────────────────
    default_stop_loss_pct: float = 0.002
    default_take_profit_pct: float = 0.0045

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> "_Config":
        """Load values from saved_config.json (if it exists)."""
        if _SAVE_PATH.exists():
            try:
                data = json.loads(_SAVE_PATH.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(self, k):
                        setattr(self, k, v)
            except Exception:
                pass  # silently fall back to defaults
        return self

    def save(self) -> None:
        """Persist current values to saved_config.json."""
        _SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {k: getattr(self, k) for k in _SERIALISABLE_KEYS}
        _SAVE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def as_dict(self) -> dict:
        """Return a dict of all serialisable config values."""
        return {k: getattr(self, k) for k in _SERIALISABLE_KEYS}

    def update(self, d: dict) -> None:
        """Bulk-set values from a dict, then save."""
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.save()

    def __repr__(self) -> str:
        return f"<Config dhan_client_id={'*set*' if self.dhan_client_id else 'unset'}>"


# Keys that are persisted to disk (everything except internal/derived values)
_SERIALISABLE_KEYS = [
    "dhan_client_id",
    "dhan_api_key",
    "trading_symbol",
    "security_id",
    "exchange_segment",
    "instrument_type",
    "yf_fallback_symbol",
    "timeframe",
    "ema_fast",
    "ema_slow",
    "use_vol_filter",
    "bar_count",
    "default_stop_loss_pct",
    "default_take_profit_pct",
    "log_level",
]


# Singleton — import this everywhere
config = _Config()
