"""
core/dhan_instruments.py
========================
Fetches the Dhan instrument master CSV and returns MCX FUTCOM futures
as a dict suitable for the Settings page dropdown.

The result is cached in config/instrument_cache.json (refreshed every 24 h).
Falls back to a small hardcoded list if the download fails.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger("DhanInstruments")

# ── Public CSV endpoint (no auth required) ─────────────────────────────────────
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# ── Cache location (next to user_prefs.json) ──────────────────────────────────
_REPO_ROOT    = Path(__file__).parent.parent
CACHE_FILE    = _REPO_ROOT / "config" / "instrument_cache.json"
CACHE_MAX_AGE = timedelta(hours=24)

# ── Hardcoded fallback (used when download fails) ─────────────────────────────
FALLBACK_INSTRUMENTS: dict[str, dict] = {
    "Gold Petal (1g)":  {"security_id": "626",   "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Gold M (10g)":     {"security_id": "1333",  "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Gold (1kg)":       {"security_id": "694",   "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Silver (30kg)":    {"security_id": "796",   "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
    "Crude Oil":        {"security_id": "10599", "exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
}


# ── Column names in the Dhan scrip master CSV ─────────────────────────────────
_COL_SECURITY_ID   = "SEM_SMST_SECURITY_ID"
_COL_TRADING_SYM   = "SEM_TRADING_SYMBOL"
_COL_CUSTOM_SYM    = "SEM_CUSTOM_SYMBOL"
_COL_EXCH_ID       = "SEM_EXM_EXCH_ID"
_COL_INSTRUMENT    = "SEM_INSTRUMENT_NAME"
_COL_EXPIRY        = "SEM_EXPIRY_DATE"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_mcx_instruments(force_refresh: bool = False) -> tuple[dict[str, dict], str]:
    """
    Return MCX FUTCOM instruments as:
        {display_name: {security_id, exchange_segment, instrument_type}}

    Also returns a source string: "live" | "cache" | "fallback"
    """
    # 1. Try cache (unless force_refresh is requested)
    if not force_refresh:
        cached = _load_cache()
        if cached is not None:
            return cached, "cache"

    # 2. Try live download
    try:
        instruments = _download_and_filter()
        if instruments:
            _save_cache(instruments)
            return instruments, "live"
    except Exception as e:
        logger.warning(f"Instrument master download failed: {e}")

    # 3. Stale cache is still better than hardcoded list
    cached = _load_cache(ignore_age=True)
    if cached:
        return cached, "cache"

    # 4. Last resort — hardcoded fallback
    return FALLBACK_INSTRUMENTS, "fallback"


def get_cache_info() -> dict:
    """Return metadata about the current cache (age, count, source)."""
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            saved_at = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
            age_h = (datetime.now() - saved_at).total_seconds() / 3600
            return {
                "exists": True,
                "saved_at": saved_at.strftime("%Y-%m-%d %H:%M"),
                "age_hours": round(age_h, 1),
                "count": len(data.get("instruments", {})),
            }
        except Exception:
            pass
    return {"exists": False}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _download_and_filter() -> dict[str, dict]:
    """Download the scrip master CSV and extract MCX FUTCOM futures."""
    resp = requests.get(SCRIP_MASTER_URL, timeout=30)
    resp.raise_for_status()

    # The CSV is large (~5 MB). Read only the columns we need.
    needed_cols = [
        _COL_SECURITY_ID,
        _COL_TRADING_SYM,
        _COL_CUSTOM_SYM,
        _COL_EXCH_ID,
        _COL_INSTRUMENT,
        _COL_EXPIRY,
    ]

    df = pd.read_csv(
        StringIO(resp.text),
        usecols=lambda c: c in needed_cols,
        dtype=str,
        low_memory=False,
    )

    # Filter: MCX exchange, FUTCOM instrument
    mask = (
        (df[_COL_EXCH_ID].str.strip().str.upper() == "MCX")
        & (df[_COL_INSTRUMENT].str.strip().str.upper() == "FUTCOM")
    )
    mcx = df[mask].copy()

    if mcx.empty:
        logger.warning("No MCX FUTCOM rows found in scrip master — check column names.")
        return {}

    # Build { display_name: {...} }
    instruments: dict[str, dict] = {}
    for _, row in mcx.iterrows():
        sec_id = str(row.get(_COL_SECURITY_ID, "")).strip()
        # Prefer custom symbol, fall back to trading symbol
        sym = str(row.get(_COL_CUSTOM_SYM, "") or row.get(_COL_TRADING_SYM, "")).strip()
        expiry = str(row.get(_COL_EXPIRY, "")).strip()

        if not sec_id or not sym:
            continue

        # Make a human-readable label: "GOLDPETAL-26Mar25"
        label = _make_label(sym, expiry)
        instruments[label] = {
            "security_id":      sec_id,
            "exchange_segment": "MCX_COMM",
            "instrument_type":  "FUTCOM",
        }

    # Sort alphabetically for a clean dropdown
    return dict(sorted(instruments.items()))


def _make_label(symbol: str, expiry: str) -> str:
    """Create a tidy display label like 'GOLDPETAL-26Mar25'."""
    exp_str = ""
    if expiry and expiry not in ("nan", "NaT", ""):
        try:
            dt = pd.to_datetime(expiry, errors="coerce")
            if pd.notna(dt):
                exp_str = "-" + dt.strftime("%d%b%y")
        except Exception:
            pass
    return f"{symbol}{exp_str}"


def _load_cache(ignore_age: bool = False) -> dict | None:
    """Load instruments from cache file if it exists and is fresh enough."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(data["saved_at"])
        if not ignore_age and (datetime.now() - saved_at) > CACHE_MAX_AGE:
            return None
        instruments = data.get("instruments", {})
        return instruments if instruments else None
    except Exception as e:
        logger.debug(f"Cache read error: {e}")
        return None


def _save_cache(instruments: dict[str, dict]):
    """Save instruments to the cache file."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": datetime.now().isoformat(),
        "instruments": instruments,
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"Instrument cache saved: {len(instruments)} MCX FUTCOM symbols.")
