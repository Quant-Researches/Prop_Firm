import subprocess
import logging
import json
import requests
import smtplib
from email.message import EmailMessage
import winsound
import threading

logger = logging.getLogger("Notifier")

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
        
    try:
        if chart_bytes:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            payload = {"chat_id": chat_id, "caption": formatted_msg, "parse_mode": "MarkdownV2"}
            files = {"photo": ("chart.png", chart_bytes, "image/png")}
            resp = requests.post(url, data=payload, files=files, timeout=10)
            
            # Fallback if caption is too long (Telegram max 1024 chars for captions)
            if resp.status_code != 200:
                logger.warning(f"Telegram sendPhoto failed: {resp.text}, splitting message and chart...")
                url_msg = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload_msg = {"chat_id": chat_id, "text": formatted_msg, "parse_mode": "MarkdownV2"}
                requests.post(url_msg, json=payload_msg, timeout=5)
                # Send photo without caption
                payload_photo = {"chat_id": chat_id}
                # Must recreate file pointer/bytes wrapping if reading from stream, but chart_bytes is in-memory
                files_photo = {"photo": ("chart.png", chart_bytes, "image/png")}
                requests.post(url, data=payload_photo, files=files_photo, timeout=10)
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": formatted_msg, "parse_mode": "MarkdownV2"}
            requests.post(url, json=payload, timeout=5)
            
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
        
    signal_icon = "🟢 BUY" if signal == "BUY" else "🔴 SELL" if signal == "SELL" else "⚪ " + str(signal)
    
    msg = f"🚀 *TRADE PULSE QUANTS* 🚀\n\n"
    msg += f"📊 *Symbol:* {escape_md(symbol)}\n"
    msg += f"⏱ *Timeframe:* {escape_md(tf)}\n"
    msg += f"🔔 *Signal:* {escape_md(signal_icon)}\n"
    msg += f"💰 *LTP:* ₹{escape_md(f'{ltp:,.2f}')}\n"
    msg += f"📉 *EMA Cross:* {escape_md(ema_fast)} \\/ {escape_md(ema_slow)}\n"
    msg += f"🔍 *Phase:* {escape_md(phase)}\n\n"
    
    if "order" in payload:
        order = payload["order"]
        qty = order.get('qty', 0)
        sl = order.get('stop_loss', 0)
        tgt = order.get('take_profit', 0)
        msg += f"🛡 *Order Details*\n"
        msg += f"👉 Qty: {escape_md(qty)}\n"
        msg += f"🛑 SL: ₹{escape_md(f'{sl:,.2f}')}\n"
        msg += f"🎯 Target: ₹{escape_md(f'{tgt:,.2f}')}\n\n"
        
    if "execution" in payload:
        exc = payload["execution"]
        price = exc.get('fill_price', exc.get('filled_price', 0))
        msg += f"✅ *Execution*\n"
        msg += f"👉 Avg Price: ₹{escape_md(f'{price:,.2f}')}\n\n"
        
    if payload.get("error"):
        err = payload.get("error")
        msg += f"🚨 *ERROR:* {escape_md(err)}\n"
        
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
        
    for t in threads:
        t.start()


def process_and_broadcast(result: dict, prefs: dict, trigger: str = "LTS_MANUAL"):
    """
    Takes the raw output from TradingEngine.run_pipeline_tick(), constructs the JSON payload,
    generates the static chart snapshot, and dispatches the multi-channel broadcast.
    """
    if not result:
        return
        
    sig = result.get('signal', 'HOLD')
    ltp = result.get('ltp', 0.0)
    phase = result.get('phase', 'UNKNOWN')
    sym = result.get('symbol', 'UNKNOWN')
    src = result.get('data_source', 'Unknown')
    order = result.get('order')
    fill = result.get('fill')
    warnings = result.get('risk_warnings', [])
    
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
        "source": src
    }
    if order:
        json_payload["order"] = {
            "qty": int(order.qty),
            "stop_loss": round(order.stop_loss, 2),
            "take_profit": round(order.take_profit, 2)
        }
    if fill:
        json_payload["execution"] = {
            "fill_price": round(fill.fill_price, 2),
            "commission": round(fill.commission, 2)
        }
    if warnings:
        json_payload["warnings"] = warnings
        
    # ── Generate static chart snapshot ──
    chart_bytes = None
    df_chart = result.get('df')
    if df_chart is not None and not df_chart.empty:
        try:
            import numpy as np
            from core.chart_utils import generate_trade_chart
            
            fig = generate_trade_chart(
                df_chart=df_chart,
                selected_asset_name=sym,
                selected_timeframe=prefs.get('timeframe', '5m'),
                ema_fast=prefs.get('ema_fast', 3),
                ema_slow=prefs.get('ema_slow', 8),
                last_high=result.get('last_high', np.nan),
                last_low=result.get('last_low', np.nan),
                dark_mode=True
            )
            chart_bytes = fig.to_image(format="png")
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
        
    # ── Dispatch ──
    broadcast_lts_signal(json_payload, prefs, chart_bytes)
