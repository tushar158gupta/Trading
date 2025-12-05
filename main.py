
# TELEGRAM_TOKEN =     "8580237190:AAFMP7hYeJeLAoEDHPFm90uMW6gJr7dMKU0"   # CHANGE THIS (after revoking the old one!)
# CHAT_ID = "@Tushartradingupdates"                       # Your public channel username with @
import yfinance as yf
from datetime import datetime, time
import time as time_module
import requests
import os
from dotenv import load_dotenv


# ================== TELEGRAM CONFIG ==================

# 🔴 Replace this with your NEW bot token from @BotFather


BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_telegram_message(text: str):
    """
    Send a message to Telegram channel/user.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"  # for bold, code, etc.
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print("Telegram send error:", resp.text)
    except Exception as e:
        print("Telegram exception:", e)


# ================== NIFTY / PATTERN LOGIC ==================

# Nifty 50 index on Yahoo Finance
ticker = yf.Ticker("^NSEI")  # NIFTY 50 index symbol
market_close = time(15, 30)  # 3:30 PM IST


def is_doji(o, h, l, c, body_pct=0.1):
    """
    Doji: very small body compared to total range.
    body_pct is the max body/range ratio.
    """
    body = abs(o - c)
    rng = h - l
    if rng == 0:
        return False
    return body / rng < body_pct


def is_hammer(o, h, l, c, body_threshold=0.3, lower_wick_ratio=2):
    """
    Hammer: small body near top, long lower wick.
    """
    body = abs(o - c)
    rng = h - l
    if rng == 0:
        return False

    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    body_ratio = body / rng

    return (
        body_ratio < body_threshold and
        lower_wick > body * lower_wick_ratio and
        upper_wick < body
    )


def is_inverted_hammer(o, h, l, c, body_threshold=0.3, upper_wick_ratio=2):
    """
    Inverted (reverse) hammer: small body near bottom, long upper wick.
    """
    body = abs(o - c)
    rng = h - l
    if rng == 0:
        return False

    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    body_ratio = body / rng

    return (
        body_ratio < body_threshold and
        upper_wick > body * upper_wick_ratio and
        lower_wick < body
    )


print("Starting NIFTY 50 (^NSEI) scanner until 3:30 PM IST...")
print("Format: [Time] O:xxx H:xxx L:xxx C:xxx")

# Optional: notify Telegram when scanner starts
send_telegram_message("🚀 *NIFTY 50 scanner started!* I'll send 1m updates and pattern alerts until 3:30 PM IST.")

while True:
    now = datetime.now().time()
    if now > market_close:
        print("Market closed. Scanner stopped.")
        send_telegram_message("📢 *Market closed*. NIFTY 50 scanner stopped.")
        break

    try:
        df = ticker.history(period="1d", interval="1m")
    except Exception as e:
        print("Error fetching data from yfinance:", e)
        time_module.sleep(60)
        continue

    if df.empty:
        print("No data yet. Waiting...")
        time_module.sleep(60)
        continue

    latest = df.iloc[-1]
    o, h, l, c = latest["Open"], latest["High"], latest["Low"], latest["Close"]
    ts = df.index[-1].strftime("%H:%M")

    # Console log
    print(f"[{ts}] O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}")

    # ================== SEND OHLC EVERY MINUTE ==================
    ohlc_msg = (
        f"📊 *NIFTY 50 – 1m Update*\n"
        f"🕒 Time: *{ts}*\n\n"
        f"• 🟢 Open:  `{o:.2f}`\n"
        f"• 🔼 High:  `{h:.2f}`\n"
        f"• 🔽 Low:   `{l:.2f}`\n"
        f"• 🔵 Close: `{c:.2f}`\n"
        f"\n━━━━━━━━━━━━━━"
    )
    send_telegram_message(ohlc_msg)

    # ================== PATTERN DETECTION ==================
    pattern_names = []

    if is_doji(o, h, l, c):
        pattern_names.append("⚠️ *Doji Candle*")

    if is_hammer(o, h, l, c):
        pattern_names.append("🔨 *Hammer Candle*")

    if is_inverted_hammer(o, h, l, c):
        pattern_names.append("🔼 *Inverted (Reverse) Hammer*")

    if pattern_names:
        pattern_text = "\n".join(pattern_names)
        pattern_msg = (
            f"🚨 *Candle Pattern Detected!*\n"
            f"{pattern_text}\n\n"
            f"🕒 Time: *{ts}*\n"
            f"• 🟢 Open:  `{o:.2f}`\n"
            f"• 🔼 High:  `{h:.2f}`\n"
            f"• 🔽 Low:   `{l:.2f}`\n"
            f"• 🔵 Close: `{c:.2f}`\n"
            f"\n━━━━━━━━━━━━━━"
        )
        print(pattern_text.replace("*", ""))  # basic console print
        send_telegram_message(pattern_msg)

    # Wait 1 minute before next candle
    time_module.sleep(60)
