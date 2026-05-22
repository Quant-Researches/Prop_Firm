import subprocess
import logging
import json
import requests
import smtplib
from email.message import EmailMessage
import winsound
import threading

logger = logging.getLogger("Notifier")

_THREAD_JOIN_TIMEOUT = 45  # seconds — wait for alert delivery before scheduler continues


def _run_threads(threads: list) -> None:
    """Start alert threads and let them run in the background without blocking."""
    for t in threads:
        t.daemon = True
        t.start()

def send_windows_notification(title: str, message: str):
    """
    Sends a native Windows Toast notification using PowerShell.
    """
    msg = message.replace("'", "''")
    ttl = title.replace("'", "''")
    
    ps_command = f"""
    [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
    [reflection.assembly]::loadwithpartialname('System.Drawing') | Out-Null
    $notify = new-object system.windows.forms.notifyicon
    $notify.icon = [System.Drawing.Icon]::ExtractAssociatedIcon((Get-Process -id $pid).Path)
    $notify.visible = $true
    $notify.showballoontip(10000, '{ttl}', '{msg}', [system.windows.forms.tooltipicon]::Info)
    """
    try:
        subprocess.run(["powershell", "-Command", ps_command], capture_output=True, check=True)
    except Exception as e:
        logger.error(f"Failed to send Windows notification: {e}")

def play_alert_sound():
    try:
        # Standard Windows exclamation sound followed by a beep
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        winsound.Beep(1000, 500)
    except Exception as e:
        logger.error(f"Failed to play sound: {e}")

def send_telegram_alert(bot_token: str, chat_id: str, formatted_msg: str, chart_bytes: bytes = None):
    if not bot_token or not chat_id:
        return

    def _send_text(text: str, use_markdown: bool = True) -> bool:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text[:4096]}
        if use_markdown:
            payload["parse_mode"] = "MarkdownV2"
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200 and use_markdown:
            logger.warning("Telegram MarkdownV2 failed, retrying plain text: %s", resp.text[:200])
            return _send_text(text, use_markdown=False)
        return resp.status_code == 200

    try:
        if chart_bytes:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            payload = {"chat_id": chat_id, "caption": formatted_msg[:1024], "parse_mode": "MarkdownV2"}
            files = {"photo": ("chart.png", chart_bytes, "image/png")}
            resp = requests.post(url, data=payload, files=files, timeout=20)

            if resp.status_code != 200:
                logger.warning("Telegram sendPhoto failed: %s", resp.text[:200])
                _send_text(formatted_msg)
                payload_photo = {"chat_id": chat_id}
                files_photo = {"photo": ("chart.png", chart_bytes, "image/png")}
                requests.post(url, data=payload_photo, files=files_photo, timeout=20)
        else:
            _send_text(formatted_msg)

    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")

def send_email_alert(sender_email: str, app_password: str, receiver_email: str, subject: str, message: str, chart_bytes: bytes = None):
    if not sender_email or not app_password or not receiver_email:
        return
    try:
        msg = EmailMessage()
        msg.set_content(message)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email
        
        if chart_bytes:
            msg.add_attachment(chart_bytes, maintype='image', subtype='png', filename='chart.png')
            
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        logger.error(f"Email alert failed: {e}")

def _format_telegram_message(payload: dict, prefs: dict) -> str:
    """Formats the JSON payload into a pretty Telegram Markdown message."""
    trigger = payload.get("trigger", "ALERT")
    symbol = payload.get("symbol", "Unknown")
    signal = payload.get("signal", "NONE")
    ltp = payload.get("ltp", 0.0)
    phase = payload.get("phase", "")
    
    # Extract EMA from prefs
    ema_fast = prefs.get('ema_fast', '-')
    ema_slow = prefs.get('ema_slow', '-')
    tf = prefs.get('timeframe', '-')
    
    # Escaping MarkdownV2 characters
    def escape_md(text):
        if not isinstance(text, str):
             text = str(text)
        escape_chars = r"_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{char}" if char in escape_chars else char for char in text)
        
    signal_icon = "BUY" if signal == "BUY" else "SELL" if signal == "SELL" else str(signal)
    
    msg = "*TRADE PULSE QUANTS*\n\n"
    msg += "*Symbol:* " + escape_md(symbol) + "\n"
    msg += "*Timeframe:* " + escape_md(tf) + "\n"
    msg += "*Signal:* " + escape_md(signal_icon) + "\n"
    msg += "*LTP:* $" + escape_md(f"{ltp:,.4f}") + "\n"
    msg += "*EMA Cross:* " + escape_md(str(ema_fast)) + " / " + escape_md(str(ema_slow)) + "\n"
    msg += "*Phase:* " + escape_md(phase) + "\n\n"
    
    if "order" in payload and payload["order"]:
        order = payload["order"]
        qty        = order.get('qty', 0)
        sl         = order.get('stop_loss', 0)
        tgt        = order.get('take_profit', 0)
        rr         = order.get('rr_ratio', 0)
        est_loss   = order.get('est_loss_usd', 0)
        est_profit = order.get('est_profit_usd', 0)
        msg += "*Order Details*\n"
        msg += "Lots: " + escape_md(str(qty)) + "\n"
        msg += "SL: $" + escape_md(f"{sl:,.4f}") + "\n"
        msg += "Target: $" + escape_md(f"{tgt:,.4f}") + "\n"
        msg += "R:R: 1:" + escape_md(str(rr)) + "\n"
        msg += "Est\. Loss \(if SL hit\): \-$" + escape_md(f"{est_loss:,.2f}") + "\n"
        msg += "Est\. Profit \(if TP hit\): \+$" + escape_md(f"{est_profit:,.2f}") + "\n\n"
        
    if "execution" in payload and payload["execution"]:
        exc = payload["execution"]
        price = exc.get('fill_price', exc.get('filled_price', 0))
        msg += "*Execution*\n"
        msg += "Fill Price: $" + escape_md(f"{price:,.4f}") + "\n\n"
        
    if payload.get("error"):
        err = payload.get("error")
        msg += f"🚨 *ERROR:* {escape_md(err)}\n"

    if payload.get("trade_blocked"):
        msg += f"\n🚫 *Trade Blocked:* {escape_md(payload.get('block_reason', 'Risk guard'))}\n"
        for w in payload.get("risk_warnings") or []:
            msg += escape_md(w) + "\n"

    if payload.get("fill"):
        msg += "\n✅ *Order filled on MT5*\n"
        
    msg += f"⚡ _Trigger:_ {escape_md(trigger)}"
    
    return msg

def broadcast_lts_signal(json_payload: dict, prefs: dict, chart_bytes: bytes = None):
    """
    Broadcasts the raw JSON payload to all enabled channels concurrently using Background Threads.
    """
    message_str = json.dumps(json_payload, indent=2)
    
    threads = []
    
    # 1. Desktop Notification
    if prefs.get("alert_desktop", True):
        t = threading.Thread(target=send_windows_notification, args=("LTS Signal", message_str))
        threads.append(t)
        
    # 2. Sound
    if prefs.get("alert_sound", True):
        t = threading.Thread(target=play_alert_sound)
        threads.append(t)
        
    # 3. Telegram
    if prefs.get("alert_telegram", True):
        tg_msg = _format_telegram_message(json_payload, prefs)
        t = threading.Thread(target=send_telegram_alert, args=(
            prefs.get("telegram_bot_token", ""),
            prefs.get("telegram_chat_id", ""),
            tg_msg,
            chart_bytes
        ))
        threads.append(t)
        
    # 4. Email
    if prefs.get("alert_email", True):
        t = threading.Thread(target=send_email_alert, args=(
            prefs.get("gmail_sender", ""),
            prefs.get("gmail_app_password", ""),
            prefs.get("gmail_receiver", ""),
            "Trade Pulse Quants - LTS Match",
            message_str,
            chart_bytes
        ))
        threads.append(t)
        
    _run_threads(threads)


def broadcast_daemon_started(prefs: dict, schedule_count: int = 0) -> None:
    """Notify that the background scheduler daemon is online."""
    if not prefs.get("notify_on_scheduler_start", True):
        return
    sym = prefs.get("trading_symbol", "XAUUSD")
    tf = prefs.get("timeframe", "5m")
    warnings = [
        "Scheduler daemon STARTED",
        f"Symbol: {sym} | Timeframe: {tf}",
        f"Active schedule slots: {schedule_count}",
        "Timezone: Europe/Helsinki (FTMO chart time)",
    ]
    suggestions = ["Keep MT5 terminal open.", "Monitor data/events.jsonl for tick logs."]
    broadcast_risk_alert(
        alert_type="INFO",
        symbol=sym,
        warnings=warnings,
        suggestions=suggestions,
        prefs=prefs,
        block_reason="Daemon online",
    )


def _format_risk_telegram_message(alert_type: str, symbol: str, warnings: list,
                                   suggestions: list, block_reason: str = "") -> str:
    """
    Formats a risk/news alert into a MarkdownV2 Telegram message.
    alert_type: "BLOCKED" | "WARNING" | "NEWS_BLACKOUT" | "FTMO_WARNING"
    """
    def escape_md(text):
        if not isinstance(text, str):
            text = str(text)
        escape_chars = r"_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{c}" if c in escape_chars else c for c in text)

    icons = {
        "BLOCKED":       "TRADE BLOCKED",
        "NEWS_BLACKOUT": "NEWS BLACKOUT",
        "FTMO_WARNING":  "FTMO WARNING",
        "WARNING":       "RISK ALERT",
        "INFO":          "SYSTEM UPDATE",
    }
    header = icons.get(alert_type, "RISK ALERT")

    msg = "*TRADE PULSE QUANTS*\n"
    msg += "*" + escape_md(header) + "*\n\n"
    if symbol:
        msg += "*Symbol:* " + escape_md(symbol) + "\n"
    if block_reason:
        msg += "*Reason:* " + escape_md(block_reason) + "\n"
    if warnings:
        msg += "\n*Details:*\n"
        for w in warnings:
            msg += escape_md(w) + "\n"
    if suggestions:
        msg += "\n*Action:*\n"
        for s in suggestions:
            msg += escape_md(s) + "\n"
    return msg


def broadcast_risk_alert(
    alert_type: str,
    symbol: str,
    warnings: list,
    suggestions: list,
    prefs: dict,
    block_reason: str = "",
):
    """
    Broadcasts FTMO risk and news blackout alerts across all enabled channels.

    alert_type options:
        "BLOCKED"       - trade blocked by FTMO rules (daily loss, DD, max positions)
        "NEWS_BLACKOUT" - trade blocked by news window (leverage > 1:30)
        "FTMO_WARNING"  - approaching daily/DD limits but trade not yet blocked
        "WARNING"       - generic risk warning

    Channels: Desktop Toast, Sound, Telegram, Email (same prefs flags as trade alerts).
    """
    tg_msg    = _format_risk_telegram_message(alert_type, symbol, warnings, suggestions, block_reason)
    plain_msg = "\n".join(warnings + suggestions)
    title_map = {
        "BLOCKED":       "Trade BLOCKED - FTMO Guard",
        "NEWS_BLACKOUT": "NEWS BLACKOUT Active",
        "FTMO_WARNING":  "FTMO Risk Warning",
        "WARNING":       "Risk Alert",
    }
    title = title_map.get(alert_type, "Risk Alert")

    threads = []

    if prefs.get("alert_desktop", True):
        t = threading.Thread(target=send_windows_notification, args=(title, plain_msg[:256]))
        threads.append(t)

    # Sound: use exclamation for blocks, default beep for warnings
    if prefs.get("alert_sound", True):
        if alert_type in ("BLOCKED", "NEWS_BLACKOUT"):
            t = threading.Thread(target=play_alert_sound)
            threads.append(t)

    if prefs.get("alert_telegram", True):
        t = threading.Thread(target=send_telegram_alert, args=(
            prefs.get("telegram_bot_token", ""),
            prefs.get("telegram_chat_id", ""),
            tg_msg,
            None,
        ))
        threads.append(t)

    if prefs.get("alert_email", True):
        t = threading.Thread(target=send_email_alert, args=(
            prefs.get("gmail_sender", ""),
            prefs.get("gmail_app_password", ""),
            prefs.get("gmail_receiver", ""),
            "Trade Pulse Quants - " + title,
            plain_msg,
            None,
        ))
        threads.append(t)

    _run_threads(threads)


def process_and_broadcast(result: dict, prefs: dict, trigger: str = "LTS_MANUAL"):
    """
    Takes the raw output from TradingEngine.run_pipeline_tick(), constructs the JSON payload,
    generates the static chart snapshot, and dispatches the multi-channel broadcast.
    """
    prefs = prefs or {}
    sym = (result or {}).get("symbol", prefs.get("trading_symbol", "UNKNOWN"))

    if not result:
        broadcast_risk_alert(
            alert_type="WARNING",
            symbol=sym,
            warnings=["Pipeline returned no result (empty or insufficient data)."],
            suggestions=["Check MT5 connection and bar_count in Settings."],
            prefs=prefs,
            block_reason="Empty pipeline result",
        )
        return

    if result.get("error"):
        broadcast_risk_alert(
            alert_type="BLOCKED",
            symbol=sym,
            warnings=[f"DATA / PIPELINE ERROR: {result.get('error')}"],
            suggestions=["Verify MT5 is running and symbol is in MarketWatch."],
            prefs=prefs,
            block_reason=str(result.get("error")),
        )
        return
        
    sig = result.get('signal', 'HOLD')
    ltp = result.get('ltp', 0.0)
    phase = result.get('phase', 'UNKNOWN')
    src = result.get('data_source', 'Unknown')
    order = result.get('order')
    fill = result.get('fill')
    trade_blocked = bool(result.get("trade_blocked"))
    block_reason = result.get("block_reason", "")

    # Skip HOLD-only pings when user disabled them (signals/blocks/fills always notify)
    notify_on_hold = prefs.get("notify_on_hold", True)
    is_scheduled = trigger in ("LTS_AUTOMATIC", "SCHEDULER")
    if (
        sig == "HOLD"
        and not fill
        and not trade_blocked
        and is_scheduled
        and not notify_on_hold
    ):
        logger.info("Skipping HOLD notification (notify_on_hold=false).")
        return
    
    # ── Abort Check ──
    if result.get('aborted'):
        abort_reason = result.get('abort_reason', 'Unknown reason')
        json_payload = {
            "trigger": "LTS_ABORTED",
            "symbol": sym,
            "signal": sig,
            "phase": phase,
            "error": abort_reason
        }
        broadcast_lts_signal(json_payload, prefs)
        return

    # ── Build pure JSON payload ──
    json_payload = {
        "trigger": trigger,
        "symbol": sym,
        "signal": sig,
        "ltp": ltp,
        "phase": phase,
        "source": src,
        "trade_blocked": trade_blocked,
        "block_reason": block_reason,
        "risk_warnings": result.get("risk_warnings", []),
        "fill": bool(fill),
    }
    if order:
        order_event = order
        json_payload["order"] = {
            "qty": round(float(order_event.qty), 2),
            "stop_loss": round(float(order_event.stop_loss), 4) if order_event.stop_loss else 0,
            "take_profit": round(float(order_event.take_profit), 4) if order_event.take_profit else 0,
            "rr_ratio": order_event.rr_ratio,
            "est_loss_usd": order_event.est_loss_usd,
            "est_profit_usd": order_event.est_profit_usd,
        }
    if fill:
        fill_event = fill
        json_payload["execution"] = {
            "fill_price": round(float(fill_event.fill_price), 4),
            "commission": round(float(fill_event.commission), 2) if hasattr(fill_event, 'commission') else 0,
        }
    # risk_warnings removed — FTMO risk info is now logged in the event log, not the notifier
        
    # ── Generate static chart snapshot ──
    chart_bytes = None
    df_chart = result.get('df')
    if df_chart is not None and not df_chart.empty:
        try:
            import numpy as np
            from core.chart_utils import generate_static_trade_chart

            chart_bytes = generate_static_trade_chart(
                df_chart=df_chart,
                selected_asset_name=sym,
                selected_timeframe=prefs.get('timeframe', '5m'),
                ema_fast=prefs.get('ema_fast', 3),
                ema_slow=prefs.get('ema_slow', 8),
                last_high=result.get('last_high', np.nan),
                last_low=result.get('last_low', np.nan)
            )
        except Exception as e:
            logger.warning(f"Static chart generation failed: {e}")
        
    # ── Dispatch ──
    broadcast_lts_signal(json_payload, prefs, chart_bytes)
