# BOT_TOKEN = "8580237190:AAFMP7hYeJeLAoEDHPFm90uMW6gJr7dMKU0"
import requests
import time
from datetime import datetime
import json

# ============================================================
# TELEGRAM CONFIG
# ============================================================

update_icons = ["⏳", "🔄", "⚡", "📈", "📊"]
update_index = 0
last_close = {}   # store previous close for change detection

BOT_TOKEN = "8580237190:AAFMP7hYeJeLAoEDHPFm90uMW6gJr7dMKU0"
CHAT_ID = "@tushartradingupdates"   # or your numeric chat id for testing

def telegram_send(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text  # NO parse_mode to avoid Markdown errors
            },
            timeout=5
        )
        print("TG send:", r.status_code, r.text)
        if r.status_code != 200:
            return None
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print("TG send error:", e)
        return None


def telegram_edit_message(message_id, text):
    if not message_id:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
            json={
                "chat_id": CHAT_ID,
                "message_id": message_id,
                "text": text
            },
            timeout=5
        )
        print("TG edit:", r.status_code, r.text)
    except Exception as e:
        print("TG edit error:", e)


# ============================================================
# NSE API CLIENT (very basic)
# ============================================================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/"
})

def get_option_chain(symbol):
    # Warmup
    try:
        session.get("https://www.nseindia.com", timeout=5)
    except Exception as e:
        print("Warmup error:", e)

    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    try:
        resp = session.get(url, timeout=5)
        print("NSE status:", resp.status_code, resp.headers.get("Content-Type"))
        if "application/json" not in resp.headers.get("Content-Type", ""):
            print("NSE not JSON, first 200 chars:", resp.text[:200])
            return None
        data = resp.json()
        return data["records"]["data"]
    except Exception as e:
        print("NSE error:", e)
        return None


# ============================================================
# PATTERNS
# ============================================================
def is_doji(o, h, l, c):
    rng = h - l
    return rng > 0 and abs(o - c) / rng < 0.1

def is_hammer(o, h, l, c):
    body = abs(o - c)
    lower = min(o, c) - l
    upper = h - max(o, c)
    rng = h - l
    return rng > 0 and body/rng < 0.3 and lower > body*2 and upper < body

def is_inverted_hammer(o, h, l, c):
    body = abs(o - c)
    upper = h - max(o, c)
    lower = min(o, c) - l
    rng = h - l
    return rng > 0 and body/rng < 0.3 and upper > body*2 and lower < body


# ============================================================
# CANDLE STORAGE
# ============================================================
candles_1m = {}
candles_15m = {}
candles_30m = {}
candles_1h = {}

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


def build_htf(src, dst, tf_minutes):
    """
    Build higher timeframe candles from lower timeframe (1m base).
    src: dict[symbol][HH:MM] = {o,h,l,c}
    dst: dict[symbol][HH:MM] = {o,h,l,c} aggregated into tf_minutes buckets.
    """
    for symbol in src:
        if symbol not in dst:
            dst[symbol] = {}

        for t in sorted(src[symbol].keys()):
            dt = datetime.strptime(t, "%H:%M")
            bucket_min = (dt.minute // tf_minutes) * tf_minutes
            key = dt.replace(minute=bucket_min).strftime("%H:%M")

            o = src[symbol][t]["o"]
            h = src[symbol][t]["h"]
            l = src[symbol][t]["l"]
            c = src[symbol][t]["c"]

            if key not in dst[symbol]:
                dst[symbol][key] = {"o": o, "h": h, "l": l, "c": c}
            else:
                dst[symbol][key]["h"] = max(dst[symbol][key]["h"], h)
                dst[symbol][key]["l"] = min(dst[symbol][key]["l"], l)
                dst[symbol][key]["c"] = c


# ============================================================
# SWING LOW + DEMAND ZONE
# ============================================================
def find_swing_low(candles):
    if len(candles) < 3:
        return None
    L = [c["l"] for c in candles]
    SL = None
    for i in range(1, len(L)-1):
        if L[i] < L[i-1] and L[i] < L[i+1]:
            SL = L[i]
    return SL

def in_demand_zone(price, swing_low, pct=0.005):
    if swing_low is None:
        return False
    return swing_low*(1-pct) <= price <= swing_low*(1+pct)


# ============================================================
# BREAKOUT + COMPRESSION
# ============================================================
def is_breakout(candles, lookback=10):
    if len(candles) < lookback+2:
        return False
    prev_high = max([c["h"] for c in candles[-(lookback+1):-1]])
    return candles[-1]["c"] > prev_high

def is_compression(candles, pct=0.3):
    if len(candles) < 2:
        return False
    c1, c2 = candles[-1], candles[-2]
    h_ref = max(c1["h"], c2["h"])
    l_ref = min(c1["l"], c2["l"])
    if h_ref == 0 or l_ref == 0:
        return False
    return (
        abs(c1["h"] - c2["h"]) / h_ref < pct/100
        or abs(c1["l"] - c2["l"]) / l_ref < pct/100
    )


# ============================================================
# TELEGRAM LIVE DASHBOARD
# ============================================================
# Single message that will be edited every scan with latest OHLC
dashboard_msg_id = telegram_send("📊 Initializing live OHLC dashboard...")

# To avoid repeating the same alert multiple times per candle
sent_alerts = set()  # keys like "symbol|timeframe|HH:MM"

MAX_DASHBOARD_SYMBOLS = 10  # limit to avoid Telegram 4096 char overflow


def format_candle_line(tf_name, candle):
    if not candle:
        return f"{tf_name}: O:- H:- L:- C:-"
    o = candle["o"]
    h = candle["h"]
    l = candle["l"]
    c = candle["c"]
    # round to 2 decimals if float
    def fmt(x):
        try:
            return f"{float(x):.2f}"
        except:
            return str(x)
    return f"{tf_name}: O:{fmt(o)} H:{fmt(h)} L:{fmt(l)} C:{fmt(c)}"


def update_dashboard():
    global update_index
    update_index = (update_index + 1) % len(update_icons)
    icon = update_icons[update_index]

    if not dashboard_msg_id:
        return

    symbols = sorted(candles_1m.keys())
    if not symbols:
        telegram_edit_message(dashboard_msg_id, f"{icon} Waiting for market ticks...")
        return

    symbols = symbols[:MAX_DASHBOARD_SYMBOLS]

    lines = []
    lines.append(f"{icon} 📊 BANKNIFTY OPTIONS – LIVE OHLC (Auto-Update)")
    lines.append(f"⏱ Updated: {datetime.now().strftime('%H:%M:%S')}")
    lines.append(f"Tracking {len(symbols)} symbols (1m / 15m / 30m)\n")

    for sym in symbols:
        # Latest 1m
        c1 = None
        if sym in candles_1m and candles_1m[sym]:
            c1 = list(candles_1m[sym].values())[-1]

        # Price Movement Indicator
        move_icon = ""
        if c1:
            last_c = last_close.get(sym)
            if last_c is not None:
                if c1["c"] > last_c:
                    move_icon = "⬆️"
                elif c1["c"] < last_c:
                    move_icon = "⬇️"
                else:
                    move_icon = "⏺"
            last_close[sym] = c1["c"]

        # Latest 15m
        c15 = None
        if sym in candles_15m and candles_15m[sym]:
            c15 = list(candles_15m[sym].values())[-1]

        # Latest 30m
        c30 = None
        if sym in candles_30m and candles_30m[sym]:
            c30 = list(candles_30m[sym].values())[-1]

        lines.append(f"{move_icon} {sym}")
        lines.append(format_candle_line("1m ", c1))
        lines.append(format_candle_line("15m", c15))
        lines.append(format_candle_line("30m", c30))
        lines.append("")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n...(truncated)..."

    telegram_edit_message(dashboard_msg_id, text)

# ============================================================
# MAIN LOOP
# ============================================================
print("\n==============================")
print(" ADVANCED AUTO-STRIKE SCANNER")
print("==============================\n")

while True:
    print("\n--------------------------------------")
    print("SCAN:", datetime.now().strftime("%H:%M:%S"))
    print("--------------------------------------\n")

    data = get_option_chain("BANKNIFTY")
    if not data:
        print("[NSE] Error fetching option chain...\n")
        time.sleep(2)
        continue

    available_strikes = sorted({d.get("strikePrice") for d in data})
    print("Available strikes:", available_strikes[:20], "...\n")

    for item in data:
        for opt in [item.get("CE"), item.get("PE")]:
            if not opt:
                continue

            strike = opt.get("strikePrice")
            opt_type = opt.get("optionType", "CE" if "CE" in str(opt) else "PE")
            symbol = f"{strike} {opt_type}"

            ltp = opt.get("lastPrice")
            if ltp is None:
                continue

            # Update 1m candles
            update_1m(symbol, ltp)

            # Build higher timeframes from 1m
            build_htf(candles_1m, candles_15m, 15)
            build_htf(candles_1m, candles_30m, 30)
            build_htf(candles_1m, candles_1h, 60)

            # --------------------------------------------------
            # PROCESS 15m AND 30m TIMEFRAMES
            # --------------------------------------------------
            # 15m
            tf15_list = list(candles_15m.get(symbol, {}).values())
            # 30m
            tf30_list = list(candles_30m.get(symbol, {}).values())

            # Helper to run same logic on any timeframe list
            def process_timeframe(tf_candles, timeframe_label):
                if len(tf_candles) < 3:
                    return

                last = tf_candles[-1]
                o, h, l, c = last["o"], last["h"], last["l"], last["c"]

                swing_low = find_swing_low(tf_candles)
                demand = in_demand_zone(c, swing_low)

                breakout = is_breakout(tf_candles)
                compress = is_compression(tf_candles)

                d = is_doji(o, h, l, c)
                hm = is_hammer(o, h, l, c)
                inv = is_inverted_hammer(o, h, l, c)

                # PRINT TO TERMINAL
                print(f"STRIKE: {symbol} | TF: {timeframe_label}")
                print(f"   LTP: {ltp}")
                print(f"   {timeframe_label} O:{o} H:{h} L:{l} C:{c}")
                print(f"   Swing Low: {swing_low}")
                print(f"   Demand Zone: {demand}")
                print(f"   Patterns → Doji:{d}, Hammer:{hm}, InvHammer:{inv}")
                print(f"   Breakout:{breakout}, Compression:{compress}")
                print("------------------------------------------------------\n")

                # Alert condition
                if demand and (d or hm or inv or breakout or compress):
                    entry = c
                    sl = swing_low
                    if sl is None:
                        return
                    risk = entry - sl
                    if risk <= 0:
                        return
                    t1 = entry + risk*3
                    t2 = entry + risk*4

                    # Avoid duplicate alerts on same candle
                    # Use last candle's time key from the dict
                    tf_dict = candles_15m if timeframe_label == "15m" else candles_30m
                    time_keys = sorted(tf_dict.get(symbol, {}).keys())
                    if not time_keys:
                        candle_key = "NA"
                    else:
                        candle_key = time_keys[-1]

                    alert_key = f"{symbol}|{timeframe_label}|{candle_key}"
                    if alert_key in sent_alerts:
                        return
                    sent_alerts.add(alert_key)

                    alert = {
                        "symbol": symbol,
                        "timeframe": timeframe_label,
                        "entry": entry,
                        "stoploss": sl,
                        "target_1_3": t1,
                        "target_1_4": t2,
                        "patterns": {
                            "doji": d,
                            "hammer": hm,
                            "inv_hammer": inv,
                            "breakout": breakout,
                            "compression": compress
                        },
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    alert_json = json.dumps(alert, indent=4)
                    print("🔥 SETUP FOUND 🔥")
                    print(alert_json, "\n")

                    # Plain text to avoid markdown issues
                    telegram_send(f"Setup Found on {symbol} [{timeframe_label}]\n{alert_json}")

            # Run for 15m and 30m
            process_timeframe(tf15_list, "15m")
            process_timeframe(tf30_list, "30m")

    # After finishing scan for all strikes, update Telegram dashboard
    update_dashboard()

    time.sleep(2)
