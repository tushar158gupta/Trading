import requests
import time
from datetime import datetime, timedelta
import json
import threading

# ============================================================
#  TELEGRAM CLIENT (Clean + Professional)
# ============================================================

class TelegramClient:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=5,
            )
            if r.status_code != 200:
                print("Telegram send failed:", r.text)
                return None
            return r.json().get("result", {}).get("message_id")
        except Exception as e:
            print("Telegram send Exception:", e)
            return None

    def edit(self, message_id, text):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/editMessageText",
                json={"chat_id": self.chat_id, "message_id": message_id, "text": text},
                timeout=5,
            )
            if r.status_code != 200:
                print("Telegram edit error:", r.text)
        except Exception as e:
            print("Telegram edit Exception:", e)
# ============================================================
#  NSE CLIENT (Stable JSON Fetch)
# ============================================================

class NSEClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/"
        })

    def warmup(self):
        try:
            self.session.get("https://www.nseindia.com", timeout=5)
        except:
            pass

    def get_option_chain(self, symbol="BANKNIFTY"):
        self.warmup()
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        try:
            r = self.session.get(url, timeout=5)
            if "application/json" not in r.headers.get("Content-Type", ""):
                return None
            return r.json()["records"]["data"]
        except Exception as e:
            print("Option chain error:", e)
            return None

    def get_index_price(self, symbol="BANKNIFTY"):
        try:
            url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
            r = self.session.get(url, timeout=5)
            j = r.json()
            return j.get("priceInfo", {}).get("lastPrice")
        except:
            return None
# ============================================================
#  CANDLE STRUCTURE (Clean Model)
# ============================================================

class Candle:
    def __init__(self, o, h, l, c):
        self.o = o
        self.h = h
        self.l = l
        self.c = c

    def update(self, price):
        self.h = max(self.h, price)
        self.l = min(self.l, price)
        self.c = price


# ============================================================
#  CANDLE BUILDER (Modular Multi-TF)
# ============================================================

class CandleBuilder:
    def __init__(self):
        self.candles_1m = {}
        self.candles_15m = {}
        self.candles_30m = {}
        self.index_1m = {}
        self.index_15m = {}
        self.index_30m = {}

    # ---------- Generic 1-minute update ----------
    def update_1m(self, store, key, price):
        now = datetime.now().strftime("%H:%M")
        if key not in store:
            store[key] = {}
        if now not in store[key]:
            store[key][now] = Candle(price, price, price, price)
        else:
            store[key][now].update(price)

    # ---------- Generic TF builder ----------
    def build_tf(self, src, dst, tf_minutes):
        for symbol in src:
            if symbol not in dst:
                dst[symbol] = {}

            for t in sorted(src[symbol].keys()):
                dt = datetime.strptime(t, "%H:%M")
                bucket_min = (dt.minute // tf_minutes) * tf_minutes
                key = dt.replace(minute=bucket_min).strftime("%H:%M")

                c = src[symbol][t]  # source candle

                if key not in dst[symbol]:
                    dst[symbol][key] = Candle(c.o, c.h, c.l, c.c)
                else:
                    dst[symbol][key].update(c.c)  # update with close
                    dst[symbol][key].h = max(dst[symbol][key].h, c.h)
                    dst[symbol][key].l = min(dst[symbol][key].l, c.l)

    # ---------- Public: Update option candle ----------
    def update_option_price(self, symbol, price):
        self.update_1m(self.candles_1m, symbol, price)
        self.build_tf(self.candles_1m, self.candles_15m, 15)
        self.build_tf(self.candles_1m, self.candles_30m, 30)

    # ---------- Public: Update INDEX candle ----------
    def update_index(self, price):
        self.update_1m(self.index_1m, "INDEX", price)
        self.build_tf(self.index_1m, self.index_15m, 15)
        self.build_tf(self.index_1m, self.index_30m, 30)
# ============================================================
#  PATTERN ENGINE (Clean + Modular)
# ============================================================

class PatternEngine:

    @staticmethod
    def is_doji(c):
        rng = c.h - c.l
        if rng <= 0:
            return False
        return abs(c.o - c.c) / rng < 0.1

    @staticmethod
    def is_hammer(c):
        body = abs(c.o - c.c)
        lower = min(c.o, c.c) - c.l
        upper = c.h - max(c.o, c.c)
        rng = c.h - c.l
        if rng <= 0:
            return False
        return body/rng < 0.3 and lower > body*2 and upper < body

    @staticmethod
    def is_inv_hammer(c):
        body = abs(c.o - c.c)
        upper = c.h - max(c.o, c.c)
        lower = min(c.o, c.c) - c.l
        rng = c.h - c.l
        if rng <= 0:
            return False
        return body/rng < 0.3 and upper > body*2 and lower < body

    @staticmethod
    def is_breakout(candles, lookback=10):
        if len(candles) < lookback + 2:
            return False
        prev_high = max(c.h for c in candles[-(lookback+1):-1])
        return candles[-1].c > prev_high

    @staticmethod
    def is_compression(candles):
        if len(candles) < 2:
            return False
        c1 = candles[-1]
        c2 = candles[-2]
        if c1.h == 0 or c2.l == 0:
            return False
        return (
            abs(c1.h - c2.h) / max(c1.h, c2.h) < 0.003 or
            abs(c1.l - c2.l) / max(c1.l, c2.l) < 0.003
        )

    @staticmethod
    def find_swing_low(candles):
        if len(candles) < 3:
            return None
        lows = [c.l for c in candles]
        for i in range(1, len(lows)-1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                return lows[i]
        return None

    @staticmethod
    def in_demand_zone(price, swing_low, pct=0.005):
        if swing_low is None:
            return False
        return swing_low*(1-pct) <= price <= swing_low*(1+pct)
# ============================================================
#  ALERT ENGINE (Clean + Prevent Duplicate Alerts)
# ============================================================

class AlertEngine:
    def __init__(self, telegram_client):
        self.telegram = telegram_client
        self.sent_alerts = set()  # avoid duplicate alerts

    def send_alert(self, symbol, timeframe, candle_key, entry, sl, t1, t2, patterns):
        key = f"{symbol}|{timeframe}|{candle_key}"
        if key in self.sent_alerts:
            return

        self.sent_alerts.add(key)

        alert_msg = json.dumps({
            "symbol": symbol,
            "timeframe": timeframe,
            "entry": entry,
            "stoploss": sl,
            "tgt_3R": t1,
            "tgt_4R": t2,
            "patterns": patterns,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, indent=4)

        self.telegram.send(f"🔥 Setup Found on {symbol} [{timeframe}]\n{alert_msg}")
        print("\n--- ALERT SENT ---")
        print(alert_msg)
        print("-------------------\n")
# ============================================================
#  SCANNER ENGINE (Runs Patterns on TF)
# ============================================================

class ScannerEngine:
    def __init__(self, candle_builder, pattern_engine, alert_engine):
        self.cb = candle_builder
        self.patterns = pattern_engine
        self.alerts = alert_engine

    def process_tf(self, candles_dict, symbol, timeframe):
        """
        Run pattern detection on 15m or 30m list for a symbol.
        """
        if symbol not in candles_dict:
            return

        c_list = list(candles_dict[symbol].values())
        if len(c_list) < 3:
            return

        last = c_list[-1]
        o, h, l, c = last.o, last.h, last.l, last.c

        # Swing + Demand
        swing_low = self.patterns.find_swing_low(c_list)
        demand = self.patterns.in_demand_zone(c, swing_low)

        # Patterns
        d = self.patterns.is_doji(last)
        hm = self.patterns.is_hammer(last)
        inv = self.patterns.is_inv_hammer(last)
        breakout = self.patterns.is_breakout(c_list)
        compress = self.patterns.is_compression(c_list)

        debug = (
            f"STRIKE: {symbol} | {timeframe}\n"
            f" O:{o} H:{h} L:{l} C:{c}\n"
            f" SwingLow: {swing_low}  Demand: {demand}\n"
            f" Patterns -> Doji:{d}, Hammer:{hm}, InvHam:{inv}\n"
            f" Breakout:{breakout}, Compression:{compress}\n"
        )
        print(debug)

        # Alert condition
        if demand and (d or hm or inv or breakout or compress):
            if swing_low is None:
                return

            entry = c
            sl = swing_low
            risk = entry - sl
            if risk <= 0:
                return

            t1 = entry + 3 * risk
            t2 = entry + 4 * risk

            # get the last TF candle key
            key = list(candles_dict[symbol].keys())[-1]

            self.alerts.send_alert(
                symbol=symbol,
                timeframe=timeframe,
                candle_key=key,
                entry=entry,
                sl=sl,
                t1=t1,
                t2=t2,
                patterns={
                    "doji": d,
                    "hammer": hm,
                    "inv_hammer": inv,
                    "breakout": breakout,
                    "compression": compress
                }
            )
# ============================================================
#  OPTION PROCESSOR (Handles Option Chain)
# ============================================================

class OptionProcessor:
    def __init__(self, nse_client, candle_builder, scanner):
        self.nse = nse_client
        self.cb = candle_builder
        self.scanner = scanner

    def process(self):
        data = self.nse.get_option_chain("BANKNIFTY")
        if not data:
            print("❌ Option chain fetch error.")
            return []

        processed_symbols = []

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

                # Update 1m + build TF
                self.cb.update_option_price(symbol, ltp)
                processed_symbols.append(symbol)

                # Run scanner on 15m/30m
                self.scanner.process_tf(self.cb.candles_15m, symbol, "15m")
                self.scanner.process_tf(self.cb.candles_30m, symbol, "30m")

        return sorted(list(set(processed_symbols)))
# ============================================================
#  CONFIG
# ============================================================

BOT_TOKEN = "8580237190:AAFMP7hYeJeLAoEDHPFm90uMW6gJr7dMKU0"          # <- put your bot token here
CHAT_ID   = "@tushartradingupdates"           # <- or your numeric chat id
INDEX_SYMBOL = "BANKNIFTY"
SLEEP_SECONDS = 2
MAX_DASHBOARD_SYMBOLS = 10


# ============================================================
#  DASHBOARD (Single Live-Updating Telegram Message)
# ============================================================

class Dashboard:
    def __init__(self, telegram_client, candle_builder):
        self.tg = telegram_client
        self.cb = candle_builder

        # create the initial message
        self.msg_id = self.tg.send("📊 Initializing BANKNIFTY scanner dashboard...")
        self.update_icons = ["⏳", "🔄", "⚡", "📈", "📊"]
        self.update_index = 0
        self.last_close = {}  # symbol -> last close for move arrow

    def _format_candle_line(self, tf_name, candle_obj):
        if candle_obj is None:
            return f"{tf_name}: O:- H:- L:- C:-"

        def fmt(x):
            try:
                return f"{float(x):.2f}"
            except:
                return str(x)

        return (
            f"{tf_name}: "
            f"O:{fmt(candle_obj.o)} "
            f"H:{fmt(candle_obj.h)} "
            f"L:{fmt(candle_obj.l)} "
            f"C:{fmt(candle_obj.c)}"
        )

    def _get_last_candle(self, store, key):
        """
        store: dict[symbol][time] = Candle
        key: symbol key like "INDEX" or option symbol
        """
        if key not in store or not store[key]:
            return None
        return list(store[key].values())[-1]

    def update(self, symbols):
        """
        Build and edit the Telegram dashboard message.
        `symbols` is list of option symbols processed in last scan.
        """
        if not self.msg_id:
            return

        self.update_index = (self.update_index + 1) % len(self.update_icons)
        icon = self.update_icons[self.update_index]

        lines = []
        lines.append(f"{icon} 📊 BANKNIFTY OPTIONS – LIVE OHLC (Auto-Update)")
        lines.append(f"⏱ Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # ========================================================
        # INDEX BLOCK AT TOP (1m / 15m / 30m)
        # ========================================================
        idx_1m = self._get_last_candle(self.cb.index_1m, "INDEX")
        idx_15m = self._get_last_candle(self.cb.index_15m, "INDEX")
        idx_30m = self._get_last_candle(self.cb.index_30m, "INDEX")

        lines.append(f"📌 {INDEX_SYMBOL} INDEX (LIVE)")
        lines.append(self._format_candle_line("1m ", idx_1m))
        lines.append(self._format_candle_line("15m", idx_15m))
        lines.append(self._format_candle_line("30m", idx_30m))
        lines.append("")

        # ========================================================
        # OPTIONS BLOCK
        # ========================================================
        if not symbols:
            # fallback to whatever has candles
            symbols = sorted(self.cb.candles_1m.keys())
        symbols = symbols[:MAX_DASHBOARD_SYMBOLS]

        lines.append(f"Tracking {len(symbols)} strikes (1m / 15m / 30m)")
        lines.append("")

        for sym in symbols:
            if sym not in self.cb.candles_1m or not self.cb.candles_1m[sym]:
                continue

            c1 = self._get_last_candle(self.cb.candles_1m, sym)
            c15 = self._get_last_candle(self.cb.candles_15m, sym)
            c30 = self._get_last_candle(self.cb.candles_30m, sym)

            # Movement arrow based on 1m close
            move_icon = "⏺"
            if c1 is not None:
                prev_close = self.last_close.get(sym)
                if prev_close is not None:
                    if c1.c > prev_close:
                        move_icon = "⬆️"
                    elif c1.c < prev_close:
                        move_icon = "⬇️"
                self.last_close[sym] = c1.c

            lines.append(f"{move_icon} {sym}")
            lines.append(self._format_candle_line("1m ", c1))
            lines.append(self._format_candle_line("15m", c15))
            lines.append(self._format_candle_line("30m", c30))
            lines.append("")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3990] + "\n...(truncated)..."

        self.tg.edit(self.msg_id, text)
# ============================================================
#  MAIN SCANNER APP
# ============================================================

class BankNiftyScannerApp:
    def __init__(self):
        # Core components
        self.telegram = TelegramClient(BOT_TOKEN, CHAT_ID)
        self.nse = NSEClient()
        self.candles = CandleBuilder()
        self.patterns = PatternEngine()
        self.alert_engine = AlertEngine(self.telegram)
        self.scanner = ScannerEngine(self.candles, self.patterns, self.alert_engine)
        self.option_processor = OptionProcessor(self.nse, self.candles, self.scanner)
        self.dashboard = Dashboard(self.telegram, self.candles)

    def run_once(self):
        # 1) Update Index candles
        idx_price = self.nse.get_index_price(INDEX_SYMBOL)
        if idx_price is not None:
            self.candles.update_index(idx_price)
        else:
            print("⚠️ Could not fetch index price.")

        # 2) Process option chain → update candles + run scanner
        symbols = self.option_processor.process()

        # 3) Update dashboard in Telegram
        self.dashboard.update(symbols)

    def run_forever(self):
        print("\n======================================")
        print("  BANKNIFTY AUTO STRIKE SCANNER v2.0")
        print("======================================\n")

        while True:
            try:
                print("\n--------------------------------------")
                print("SCAN:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                print("--------------------------------------\n")

                self.run_once()
            except Exception as e:
                print("❌ Error in main loop:", e)

            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    app = BankNiftyScannerApp()
    app.run_forever()
