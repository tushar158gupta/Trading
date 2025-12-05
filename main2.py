
# TELEGRAM_TOKEN =     "8580237190:AAFMP7hYeJeLAoEDHPFm90uMW6gJr7dMKU0"   # CHANGE THIS (after revoking the old one!)
# CHAT_ID = "@Tushartradingupdates"                       # Your public channel username with @import requestsimport requestsimport requests
import time
from datetime import datetime, timedelta
import numpy as np
import json
import requests
import os
from dotenv import load_dotenv

# ---------------------------------------------------
# TELEGRAM CONFIG
# ---------------------------------------------------
BOT_TOKEN =  os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except:
        pass


# ---------------------------------------------------
# NSE FREE API CLIENT
# ---------------------------------------------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/"
})

def get_option_chain(symbol):
    # Step 1: warmup request to generate cookies
    try:
        session.get("https://www.nseindia.com", timeout=5)
    except:
        pass

    # Step 2: actual option chain request
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"

    try:
        resp = session.get(url, timeout=5)
        data = resp.json()
        return data["records"]["data"]
    except Exception as e:
        print("[NSE ERROR]", str(e))
        return None

# ---------------------------------------------------
# PATTERN DETECTION
# ---------------------------------------------------
def is_doji(o, h, l, c):
    body = abs(o - c)
    rng = h - l
    return rng > 0 and body / rng < 0.1

def is_hammer(o, h, l, c):
    body = abs(o - c)
    rng = h - l
    lower = min(o, c) - l
    upper = h - max(o, c)
    return rng > 0 and body / rng < 0.3 and lower > body * 2 and upper < body

def is_inverted_hammer(o, h, l, c):
    body = abs(o - c)
    rng = h - l
    lower = min(o, c) - l
    upper = h - max(o, c)
    return rng > 0 and body / rng < 0.3 and upper > body * 2 and lower < body


# ---------------------------------------------------
# CANDLE STORAGE
# ---------------------------------------------------
candles_1m = {}       # symbol -> minute -> {o,h,l,c}
candles_30m = {}      # 30 minute candles
candles_1h = {}       # hourly candles


# ---------------------------------------------------
# Candle Update Logic
# ---------------------------------------------------
def update_1m(symbol, ltp):
    now = datetime.now().strftime("%H:%M")
    if symbol not in candles_1m:
        candles_1m[symbol] = {}
    if now not in candles_1m[symbol]:
        candles_1m[symbol][now] = {"o": ltp, "h": ltp, "l": ltp, "c": ltp}
    else:
        c = candles_1m[symbol][now]
        c["h"] = max(c["h"], ltp)
        c["l"] = min(c["l"], ltp)
        c["c"] = ltp


def build_higher_timeframe(src, dst, period_minutes=30):
    """
    Build 30m or 1h candle from 1m candles.
    """
    for symbol, data in src.items():
        times = sorted(data.keys())
        if symbol not in dst:
            dst[symbol] = {}

        # Grouping logic
        for t in times:
            dt = datetime.strptime(t, "%H:%M")
            key_minute = (dt.minute // period_minutes) * period_minutes
            new_key = dt.replace(minute=key_minute).strftime("%H:%M")

            o, h, l, c = data[t]["o"], data[t]["h"], data[t]["l"], data[t]["c"]

            if new_key not in dst[symbol]:
                dst[symbol][new_key] = {"o": o, "h": h, "l": l, "c": c}
            else:
                dst[symbol][new_key]["h"] = max(dst[symbol][new_key]["h"], h)
                dst[symbol][new_key]["l"] = min(dst[symbol][new_key]["l"], l)
                dst[symbol][new_key]["c"] = c


# ---------------------------------------------------
# SWING LOW/HIGH & DEMAND ZONE
# ---------------------------------------------------
def find_last_swing_low(candle_list, lookback=10):
    if len(candle_list) < 3:
        return None
    lows = [c["l"] for c in candle_list]
    for i in range(1, len(lows)-1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            swing = lows[i]
    try:
        return swing
    except:
        return None


def is_in_demand_zone(price, swing_low, pct=0.005):
    if not swing_low:
        return False
    zone_low = swing_low * (1 - pct)
    zone_high = swing_low * (1 + pct)
    return zone_low <= price <= zone_high


# ---------------------------------------------------
# MULTI-SWING BREAKOUT
# ---------------------------------------------------
def is_breakout(candle_list, lookback=10):
    if len(candle_list) < lookback + 2:
        return False
    closes = [c["c"] for c in candle_list]
    highs = [c["h"] for c in candle_list]
    last_close = closes[-1]
    prev_high = max(highs[-(lookback+1):-1])
    return last_close > prev_high


# ---------------------------------------------------
# COMPRESSION DETECT (Equal highs/lows)
# ---------------------------------------------------
def is_compression(candle_list):
    if len(candle_list) < 2:
        return False
    c1, c2 = candle_list[-1], candle_list[-2]
    return abs(c1["h"] - c2["h"]) < 0.01 or abs(c1["l"] - c2["l"]) < 0.01


# ---------------------------------------------------
# STRIKES TO SCAN
# ---------------------------------------------------
STRIKES = [
    48000, 48200, 48500, 48800, 49000, 49200, 49500,
    # Add more...
]


# ---------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------
send_telegram("🚀 *Institutional Options Scanner Started*")

print("\n==============================")
print("  ADVANCED OPTIONS SCANNER    ")
print("==============================\n")

while True:
    print("\n--------------------------------------")
    print("SCAN:", datetime.now().strftime("%H:%M:%S"))
    print("--------------------------------------\n")

    data = get_option_chain("BANKNIFTY")
    if not data:
        print("[NSE] Error fetching data...")
        time.sleep(2)
        continue

    for item in data:
        for opt in [item.get("CE"), item.get("PE")]:
            if not opt:
                continue

            strike = opt.get("strikePrice")
            if strike not in STRIKES:
                continue

            opt_type = opt.get("optionType", ("CE" if "CE" in str(opt) else "PE"))
            symbol = f"{strike} {opt_type}"

            ltp = opt.get("lastPrice")
            if not ltp:
                continue

            update_1m(symbol, ltp)

            # Build 30m + 1h
            build_higher_timeframe(candles_1m, candles_30m, 30)
            build_higher_timeframe(candles_1m, candles_1h, 60)

            # Last 30m candle list
            tf_30 = list(candles_30m[symbol].values())
            tf_1h = list(candles_1h[symbol].values())

            # Process only 30m for now
            if len(tf_30) < 3:
                continue

            last = tf_30[-1]
            o, h, l, c = last["o"], last["h"], last["l"], last["c"]

            swing_low = find_last_swing_low(tf_30)
            demand_zone = is_in_demand_zone(c, swing_low)
            breakout = is_breakout(tf_30)
            compression = is_compression(tf_30)

            # Candle patterns
            doji = is_doji(o, h, l, c)
            hammer = is_hammer(o, h, l, c)
            inv_hammer = is_inverted_hammer(o, h, l, c)

            # Terminal output
            print(f"STRIKE: {symbol}")
            print(f"  LTP: {ltp}")
            print(f"  30m Candle: O={o}, H={h}, L={l}, C={c}")
            print(f"  Swing Low: {swing_low}")
            print(f"  Demand Zone: {demand_zone}")
            print(f"  Patterns: Doji={doji}, Hammer={hammer}, InvHammer={inv_hammer}")
            print(f"  Breakout: {breakout}, Compression: {compression}")
            print("------------------------------------------------------\n")

            # TRIGGER SETUP
            if demand_zone and (doji or hammer or inv_hammer or breakout or compression):
                
                entry = c
                sl = swing_low
                risk = entry - sl
                t1 = entry + 3 * risk
                t2 = entry + 4 * risk

                alert = {
                    "symbol": symbol,
                    "timeframe": "30m",
                    "entry": entry,
                    "stop_loss": sl,
                    "target_1_3": t1,
                    "target_1_4": t2,
                    "patterns": {
                        "doji": doji,
                        "hammer": hammer,
                        "inverted_hammer": inv_hammer,
                        "breakout": breakout,
                        "compression": compression
                    },
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                alert_json = json.dumps(alert, indent=4)

                print("🔥 SETUP FOUND 🔥")
                print(alert_json)
                print("\n")

                send_telegram(f"🚨 *Setup Found on {symbol}*\n```{alert_json}```")

    time.sleep(3)
