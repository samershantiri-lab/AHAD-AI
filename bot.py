# =====================================
# 🚀 AHAD AI v13.0
# ZERO-LAG ENTRY EDITION
# =====================================

import os
import time
import threading
import traceback
import requests
import urllib.request
from datetime import datetime, timedelta

from flask import Flask
import telebot


# =====================================
# 🔑 TELEGRAM TOKEN
# =====================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise Exception("❌ BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)


# =====================================
# 🌐 RENDER KEEP ALIVE SERVER
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v13.0 ZERO-LAG ENTRY ONLINE 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =====================================
# 🏦 SECTOR DATABASE v13.0
# =====================================

SECTORS = {
    "AI": ["FET", "TAO", "WLD", "ARKM", "AI", "RENDER"],
    "GAMING": ["APE", "SAND", "MANA", "GALA", "IMX", "AXS"],
    "DEFI": ["UNI", "AAVE", "LINK", "CRV", "MKR", "COMP"],
    "MEME": ["DOGE", "SHIB", "PEPE", "BONK", "FLOKI"],
    "LAYER1": ["SOL", "AVAX", "DOT", "NEAR", "ADA"],
    "RWA": ["ONDO", "PENDLE", "ENA"]
}


# =====================================
# 🐋 CACHE SYSTEM v13.0
# =====================================

cache = {
    "alpha": {"data": None, "timestamp": None},
    "futures": {"data": None, "timestamp": None},
    "okx": {"data": None, "timestamp": None}
}

def is_cache_valid(key):
    if cache[key]["timestamp"] is None:
        return False
    age = (datetime.now() - cache[key]["timestamp"]).total_seconds()
    return age < 120


def get_alpha_symbols():
    if is_cache_valid("alpha") and cache["alpha"]["data"] is not None:
        print("✅ Alpha: Using Cache")
        return cache["alpha"]["data"]

    try:
        print("🔄 Alpha: Fetching from API...")
        url = "https://www.binance.com/bapi/defi/v1/public/alpha-trade/tokens"
        response = requests.get(url, timeout=10)
        data = response.json()

        print("=" * 60)
        print("ALPHA RAW RESPONSE")
        print(data.get("data", [])[:5])
        print("=" * 60)

        alpha_symbols = []
        for token in data.get("data", []):
            alpha_symbols.append(token["symbol"].upper())

        cache["alpha"]["data"] = alpha_symbols
        cache["alpha"]["timestamp"] = datetime.now()
        print(f"✅ Alpha: {len(alpha_symbols)} symbols loaded")
        return alpha_symbols

    except Exception as e:
        print(f"⚠️ Alpha API Error: {e}")
        if cache["alpha"]["data"] is not None:
            print("🔄 Alpha: Using Fallback Cache")
            return cache["alpha"]["data"]
        return []


def get_binance_futures():
    print("🪙 ENTERED get_binance_futures()")

    if is_cache_valid("futures") and cache["futures"]["data"] is not None:
        print("✅ Futures: Using Cache")
        return cache["futures"]["data"]

    try:
        print("🔄 Futures: Fetching from API...")
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=10)

        print("=" * 60)
        print("STATUS:", response.status_code)
        print(response.text[:1000])
        print("=" * 60)

        data = response.json()
        print("Keys:", data.keys())
        print("First symbols:", data.get("symbols", [])[:5])

        symbols = []
        for s in data.get("symbols", []):
            if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
                symbols.append(s["symbol"])

        cache["futures"]["data"] = symbols
        cache["futures"]["timestamp"] = datetime.now()
        print(f"✅ Futures: {len(symbols)} symbols loaded")
        return symbols

    except Exception as e:
        print(f"⚠️ Futures API Error: {e}")
        if cache["futures"]["data"] is not None:
            print("🔄 Futures: Using Fallback Cache")
            return cache["futures"]["data"]
        return []


def get_okx_symbols():
    if is_cache_valid("okx") and cache["okx"]["data"] is not None:
        print("✅ OKX: Using Cache")
        return cache["okx"]["data"]

    try:
        print("🔄 OKX: Fetching from API...")
        url = "https://www.okx.com/api/v5/public/instruments"
        params = {"instType": "SWAP"}
        data = requests.get(url, params=params, timeout=15).json()

        symbols = []
        for x in data["data"]:
            if x["settleCcy"] == "USDT" and x["state"] == "live":
                symbols.append(x["instId"])

        cache["okx"]["data"] = symbols
        cache["okx"]["timestamp"] = datetime.now()
        print(f"✅ OKX: {len(symbols)} symbols loaded")
        return symbols

    except Exception as e:
        print(f"⚠️ OKX API Error: {e}")
        if cache["okx"]["data"] is not None:
            print("🔄 OKX: Using Fallback Cache")
            return cache["okx"]["data"]
        return []


# =====================================
# 🔧 NORMALIZE SYMBOL
# =====================================

def normalize_symbol(symbol):
    symbol = symbol.upper()
    symbol = symbol.replace("-USDT-SWAP", "")
    symbol = symbol.replace("-USDT", "")
    symbol = symbol.replace("USDT", "")
    return symbol


# =====================================
# 🛡️ HEALTH CHECK v13.0
# =====================================

health_status = {
    "alpha": "UNKNOWN",
    "futures": "UNKNOWN",
    "okx": "UNKNOWN"
}

def health_check():
    try:
        url = "https://www.binance.com/bapi/defi/v1/public/alpha-trade/tokens"
        requests.get(url, timeout=5)
        health_status["alpha"] = "ONLINE"
    except:
        health_status["alpha"] = "OFFLINE"

    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=5)
        data = response.json()
        if response.status_code == 200 and "symbols" in data and len(data["symbols"]) > 0:
            health_status["futures"] = "ONLINE"
        else:
            print("FUTURES HEALTH:", data)
            health_status["futures"] = "OFFLINE"
    except Exception as e:
        print("FUTURES HEALTH ERROR:", e)
        health_status["futures"] = "OFFLINE"

    try:
        url = "https://www.okx.com/api/v5/public/instruments"
        requests.get(url, params={"instType": "SWAP"}, timeout=5)
        health_status["okx"] = "ONLINE"
    except:
        health_status["okx"] = "OFFLINE"

    return health_status


def get_intersection_symbols():
    alpha = get_alpha_symbols()
    futures = get_binance_futures()
    alpha_set = {normalize_symbol(x) for x in alpha}
    future_set = {normalize_symbol(x) for x in futures}
    watchlist = list(alpha_set & future_set)

    print("=" * 60)
    print("ALPHA:", len(alpha))
    print(alpha[:10])
    print("FUTURES:", len(futures))
    print(futures[:10])
    print("WATCHLIST:", len(watchlist))
    print(watchlist[:20])
    print("=" * 60)
    return watchlist


# =====================================
# 📊 GET ALL TICKERS (BINANCE)
# =====================================

def get_all_tickers():
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()

        tickers = {}
        for item in data:
            symbol = item["symbol"]
            tickers[symbol] = {
                "priceChangePercent": float(item["priceChangePercent"]),
                "quoteVolume": float(item["quoteVolume"]),
                "highPrice": float(item["highPrice"])
            }
        return tickers
    except Exception as e:
        print("TICKERS ERROR:", e)
        return {}


# =====================================
# 📈 RELATIVE STRENGTH FILTER v13.0
# =====================================

def get_btc_eth_change():
    try:
        btc_url = "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT"
        eth_url = "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=ETHUSDT"

        btc = requests.get(btc_url, timeout=5).json()
        eth = requests.get(eth_url, timeout=5).json()

        return {
            "btc": float(btc["priceChangePercent"]),
            "eth": float(eth["priceChangePercent"])
        }
    except:
        return {"btc": 0, "eth": 0}


def relative_strength_filter(change_24h, btc_change, eth_change):
    if change_24h > btc_change + 2 and change_24h > eth_change + 2:
        return 15
    return 0


# =====================================
# 🕯 OKX CANDLES ENGINE
# =====================================

def get_candles(symbol, tf):
    try:
        frames = {
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }

        url = "https://www.okx.com/api/v5/market/candles"
        params = {
            "instId": symbol,
            "bar": frames[tf],
            "limit": 150
        }

        data = requests.get(url, params=params, timeout=10).json()
        candles = []

        for c in data["data"][::-1]:
            candles.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })

        return candles

    except Exception as e:
        print("CANDLE ERROR:", symbol, e)
        return []


print("🔥 AHAD AI v13.0 CORE READY 🐋")


# =====================================
# 📊 INDICATORS ENGINE v13.0
# =====================================

def ema(values, period):
    if len(values) < period:
        return values[-1]

    k = 2 / (period + 1)
    result = values[0]

    for v in values:
        result = v * k + result * (1 - k)

    return result


def rsi(values, period=14):
    gains = 0
    losses = 0

    for i in range(-period, -1):
        diff = values[i + 1] - values[i]
        if diff > 0:
            gains += diff
        else:
            losses -= diff

    if losses == 0:
        return 100

    rs = gains / losses
    return 100 - 100 / (1 + rs)


def atr(candles):
    ranges = []
    for c in candles[-14:]:
        ranges.append(c["high"] - c["low"])
    return sum(ranges) / len(ranges)


# =====================================
# 🔄 REVERSAL ZONE DETECTOR v13.0
# =====================================

def find_reversal_zone(candles):
    try:
        price = candles[-1]["close"]
        support = min([x["low"] for x in candles[-30:]])
        atr_val = atr(candles)

        reversal_zone = support + (atr_val * 0.3)
        distance = ((price - reversal_zone) / price) * 100

        if abs(distance) < 1.5:
            confidence = "HIGH ✅"
        elif abs(distance) < 3:
            confidence = "MEDIUM ⚠️"
        else:
            confidence = "LOW ❌"

        return {
            "reversal_price": round(reversal_zone, 6),
            "confidence": confidence,
            "distance": round(distance, 2)
        }

    except Exception as e:
        print("REVERSAL ERROR:", e)
        return {"reversal_price": 0, "confidence": "ERROR", "distance": 0}


# =====================================
# 📊 REVERSAL PATTERNS DETECTOR v13.0
# =====================================

def check_reversal_patterns(candles):
    try:
        patterns = []
        last_5 = candles[-5:]

        for i, c in enumerate(last_5):
            body = abs(c["close"] - c["open"])
            lower_shadow = min(c["open"], c["close"]) - c["low"]
            upper_shadow = c["high"] - max(c["open"], c["close"])

            if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                patterns.append("🔨 HAMMER")

        if len(candles) >= 2:
            c1 = candles[-2]
            c2 = candles[-1]
            if (c1["close"] < c1["open"] and
                c2["close"] > c2["open"] and
                c2["open"] < c1["close"] and
                c2["close"] > c1["open"]):
                patterns.append("📈 BULLISH ENGULFING")

        for c in last_5:
            body = abs(c["close"] - c["open"])
            if body < (c["high"] - c["low"]) * 0.1:
                patterns.append("⏸️ DOJI")

        return patterns

    except Exception as e:
        print("PATTERN ERROR:", e)
        return []


# =====================================
# 🎯 ZERO-LAG ENTRY ENGINE v13.0
# =====================================

def zero_lag_entry(candles, atr_val):
    try:
        price = candles[-1]["close"]
        recent_low = min([x["low"] for x in candles[-20:]])
        diff = price - recent_low

        if diff < atr_val * 0.3:
            entry = recent_low
            zone = "🚀 SNIPER"
        elif diff < atr_val * 0.8:
            entry = recent_low + (diff * 0.3)
            zone = "🎯 PRECISION"
        else:
            entry = recent_low + (atr_val * 0.3)
            zone = "👀 WATCH"

        return {"entry": round(entry, 6), "zone": zone}

    except Exception as e:
        print("ZERO-LAG ERROR:", e)
        return {"entry": 0, "zone": "ERROR"}
        
# =====================================
# 🐋 PRE PUMP ENGINE v13.0
# =====================================

def pre_pump_engine(candles, change_24h, rsi_1h):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            return {"status": "NORMAL", "score": 0, "flow": 0}

        flow = volume_now / volume_avg

        if flow >= 3.0:
            flow_score = 30
        elif flow >= 2.0:
            flow_score = 20
        elif flow >= 1.5:
            flow_score = 10
        elif flow >= 1.2:
            flow_score = 5
        else:
            flow_score = 0

        if flow >= 1.2 and abs(change_24h) < 5 and 35 <= rsi_1h <= 65:
            return {"status": "🐋 PRE PUMP DETECTED", "score": flow_score, "flow": round(flow, 2)}

        return {"status": "NORMAL", "score": flow_score, "flow": round(flow, 2)}

    except Exception as e:
        print("PRE PUMP ERROR:", e)
        return {"status": "ERROR", "score": 0, "flow": 0}


# =====================================
# 🧱 SUPPORT RESISTANCE ENGINE
# =====================================

def support_resistance(candles):
    highs = [x["high"] for x in candles[-80:]]
    lows = [x["low"] for x in candles[-80:]]
    price = candles[-1]["close"]

    support = min(lows)
    resistance = max(highs)

    return {
        "support": support,
        "resistance": resistance,
        "near_support": ((price - support) / price) * 100,
        "near_resistance": ((resistance - price) / price) * 100
    }


# =====================================
# 🛡️ ANTI LATE ENTRY v13.0
# =====================================

def fomo_filter(candles):
    closes = [x["close"] for x in candles]
    price = closes[-1]

    move = ((price - closes[-96]) / closes[-96]) * 100
    current_rsi = rsi(closes)

    if move < -3 or move > 5:
        return False, "⏳ OUT OF RANGE (-3% to +5%)"

    if current_rsi > 75:
        return False, "🚫 RSI HOT"

    return True, "🐋 EARLY ENTRY AREA"


# =====================================
# 🧠 AI BRAIN ENGINE v13.0
# =====================================

def ai_brain(candles):
    closes = [x["close"] for x in candles]
    price = closes[-1]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    score = 0

    if price > e20:
        score += 30
    else:
        score -= 30

    if e20 > e50:
        score += 30
    else:
        score -= 30

    if score >= 50:
        direction = "🟢 LONG"
    elif score <= -50:
        direction = "🔴 SHORT"
    else:
        direction = "WAIT"

    return {"direction": direction, "confidence": abs(score)}


# =====================================
# 🪤 TRAP DETECTOR v13.0
# =====================================

def trap_detector(candles):
    closes = [x["close"] for x in candles]
    highs = [x["high"] for x in candles]
    lows = [x["low"] for x in candles]

    price = closes[-1]
    r = rsi(closes)

    if price >= max(highs[-50:]) * 0.98 and r > 70:
        return "🪤 BULL TRAP"

    if price <= min(lows[-50:]) * 1.02 and r < 35:
        return "🪤 BEAR TRAP"

    return "✅ NO TRAP"


# =====================================
# 🐋 SMART MONEY ENGINE v13.0
# =====================================

def smart_money(candles, rsi_1h, change_24h):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 10

        if volume_avg == 0:
            return {"status": "NORMAL", "flow": 0}

        flow = volume_now / volume_avg

        if flow >= 2.0 and rsi_1h < 65 and abs(change_24h) < 5:
            return {"status": "🐋 WHALE LOADING", "flow": round(flow, 2)}

        return {"status": "NORMAL", "flow": round(flow, 2)}

    except Exception as e:
        print("SMART MONEY ERROR:", e)
        return {"status": "ERROR", "flow": 0}


# =====================================
# 📊 MULTI TIMEFRAME ENGINE v13.0
# =====================================

def multi_rsi_engine(c15, c1h, c4h, c1d):
    try:
        data = {}
        frames = {"15m": c15, "1h": c1h, "4h": c4h, "1d": c1d}
        score = 0

        for name, candles in frames.items():
            closes = [x["close"] for x in candles]
            value = rsi(closes)
            data[name] = round(value, 2)

            if 50 <= value <= 70:
                score += 10
            elif value > 75:
                score -= 10
            elif value < 35:
                score += 5

        data["score"] = score
        return data

    except Exception as e:
        print("MULTI RSI ERROR:", e)
        return {"15m": 50, "1h": 50, "4h": 50, "1d": 50, "score": 0}


# =====================================
# 🚀 FINAL ANALYZE ENGINE v13.0
# =====================================

def analyze(symbol, sector, tickers, btc_eth, alpha_symbols):
    try:
        okx_symbol = f"{symbol}-USDT-SWAP"
        okx_candles = get_candles(okx_symbol, "15m")

        if len(okx_candles) >= 60:
            c15 = okx_candles
            c1h = get_candles(okx_symbol, "1h")
            c4h = get_candles(okx_symbol, "4h")
            c1d = get_candles(okx_symbol, "1d")
        else:
            return None

        if len(c15) < 60 or len(c1h) < 60 or len(c4h) < 60 or len(c1d) < 60:
            return None

        price = c15[-1]["close"]

        ticker = tickers.get(symbol)
        if not ticker:
            return None

        change_24h = ticker["priceChangePercent"]
        volume_24h = ticker["quoteVolume"]

        if volume_24h < 1_000_000:
            return None

        closes1h = [x["close"] for x in c1h]
        closes4h = [x["close"] for x in c4h]

        rsi_1h = rsi(closes1h)
        rsi_4h = rsi(closes4h)

        safe, warning = fomo_filter(c15)
        if not safe:
            return None

        brain = ai_brain(c1h)
        if brain["direction"] == "WAIT":
            return None

        e20_1h = ema(closes1h, 20)
        e50_1h = ema(closes1h, 50)
        e20_4h = ema(closes4h, 20)
        e50_4h = ema(closes4h, 50)

        if not (e20_1h > e50_1h and e20_4h > e50_4h):
            return None

        sr = support_resistance(c15)

        if sr["near_resistance"] < 1:
            return None
        elif sr["near_resistance"] < 3:
            resistance_penalty = 10
        else:
            resistance_penalty = 0

        rs_score = relative_strength_filter(change_24h, btc_eth["btc"], btc_eth["eth"])

        money = smart_money(c15, rsi_1h, change_24h)
        pre = pre_pump_engine(c15, change_24h, rsi_1h)
        multi = multi_rsi_engine(c15, c1h, c4h, c1d)
        trap = trap_detector(c15)

        # =====================================
        # 🔄 REVERSAL & ZERO-LAG
        # =====================================

        move = atr(c15)

        reversal = find_reversal_zone(c15)
        patterns = check_reversal_patterns(c15)
        zero_entry = zero_lag_entry(c15, move)

        entry_price = zero_entry["entry"]
        entry_zone = zero_entry["zone"]

        # =====================================
        # 🔥 CONFIDENCE SCORE (100)
        # =====================================

        score = 0

        base = normalize_symbol(symbol)
        is_alpha = base in alpha_symbols

        if is_alpha:
            score += 10

        if pre["flow"] >= 3.0:
            score += 20
        elif pre["flow"] >= 2.0:
            score += 15
        elif pre["flow"] >= 1.5:
            score += 10
        elif pre["flow"] >= 1.2:
            score += 5

        if money["status"] == "🐋 WHALE LOADING":
            score += 20

        if e20_1h > e50_1h and e20_4h > e50_4h:
            score += 15

        if 40 <= rsi_1h <= 65:
            score += 10

        if volume_24h > 5_000_000:
            score += 10

        score += (10 - resistance_penalty)
        score += brain["confidence"] // 20
        score += rs_score

        # =====================================
        # ⭐ QUALITY LEVEL
        # =====================================

        if score >= 85 and pre["status"] == "🐋 PRE PUMP DETECTED":
            quality = "🐋 HIDDEN ACCUMULATION"
        elif score >= 75:
            quality = "🚀 BREAKOUT READY"
        elif score >= 60:
            quality = "👀 WATCH"
        else:
            quality = "⏳ LATE MOVE"

        # =====================================
        # 🎯 TARGETS
        # =====================================

        sl = sr["support"] * 0.995
        tp1 = price + move * 2
        tp2 = price + move * 3

        if is_alpha:
            alpha_status = "✅ ALPHA"
        else:
            alpha_status = "➖ FUTURES ONLY"

        return {
            "coin": symbol,
            "sector": sector,
            "direction": brain["direction"],
            "score": round(score),
            "quality": quality,
            "entry": entry_price,
            "entry_zone": entry_zone,
            "reversal_confidence": reversal["confidence"],
            "reversal_distance": reversal["distance"],
            "patterns": patterns,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "money": money["status"],
            "liquidity": money["flow"],
            "pre_pump": pre["status"],
            "change_24h": round(change_24h, 2),
            "multi": multi,
            "trap": trap,
            "warning": warning,
            "volume": round(volume_24h / 1_000_000, 2),
            "alpha_status": alpha_status
        }

    except Exception as e:
        print("ANALYZE ERROR:", e)
        return None
        
# =====================================
# 🤖 TELEGRAM ENGINE v13.0
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        """
🐋 AHAD AI v13.0 ONLINE 🚀

🧠 Alpha Hunter ACTIVE
🐋 Whale Loading ACTIVE
⚡ Pre-Pump Detection ACTIVE
🛡️ Health Check ACTIVE
📈 Relative Strength ACTIVE
🎯 Zero-Lag Entry ACTIVE

🎯 Goal:
Zero-Lag entries before pumps

Send /scan
        """
    )


@bot.message_handler(commands=["scan"])
def scan(message):
    bot.reply_to(
        message,
        """
🐋 AHAD AI v13.0 SCANNING...

🔍 Alpha Hunter Engine
📊 Futures Filter
⚡ Pre-Pump Detection
📈 Relative Strength Analysis
🎯 Zero-Lag Entry

Please wait ⏳
        """
    )

    health = health_check()

    health_msg = "🛡️ API STATUS:\n"
    for api, status in health.items():
        icon = "🟢" if status == "ONLINE" else "🔴"
        health_msg += f"{icon} {api.upper()}: {status}\n"

    bot.send_message(message.chat.id, health_msg)

    symbols = get_binance_futures()

    if not symbols:
        bot.send_message(message.chat.id, "⚠️ No futures symbols found")
        return

    bot.send_message(message.chat.id, f"📊 Futures Watchlist: {len(symbols)} coins")

    tickers = get_all_tickers()
    btc_eth = get_btc_eth_change()
    alpha_symbols = get_alpha_symbols()

    long_results = []

    for symbol in symbols:
        sector = "OTHER"
        for sec, coins in SECTORS.items():
            if any(coin in symbol for coin in coins):
                sector = sec
                break

        result = analyze(symbol, sector, tickers, btc_eth, alpha_symbols)

        if result:
            if result["score"] > 100:
                result["score"] = 100

            if result["direction"] == "🟢 LONG":
                if result["score"] >= 60 and result["liquidity"] >= 1.2:
                    long_results.append(result)

        time.sleep(0.03)

    def sort_key(x):
        whale_score = 10 if x["money"] == "🐋 WHALE LOADING" else 0
        return (whale_score, x["liquidity"], x["score"])

    results = sorted(long_results, key=sort_key, reverse=True)[:5]

    if not results:
        bot.send_message(
            message.chat.id,
            """
👀 No Alpha setups now

🐋 Waiting for Whale Loading
⚡ Pre-Pump not detected yet
⏳ Try again later
            """
        )
        return

    for s in results:
        patterns_text = " | ".join(s["patterns"]) if s["patterns"] else "✅ NO PATTERN"

        msg = f"""
🚨 AHAD AI v13.0 🐋

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

{s['quality']}

🏷 Source: {s['alpha_status']}

🔥 Score: {s['score']}/100
💧 Flow: {s['liquidity']}X
📈 24H: {s['change_24h']}%
💰 Volume: {s['volume']}M$

⚡ Pre-Pump: {s['pre_pump']}
🐋 Money: {s['money']}
🪤 Trap: {s['trap']}

🎯 Entry: {round(s['entry'], 6)}
📊 Reversal: {s['reversal_confidence']}
📈 Distance: {s['reversal_distance']}%
🎯 Zone: {s['entry_zone']}
🛑 SL: {round(s['sl'], 6)}

🥇 TP1: {round(s['tp1'], 6)}
🥈 TP2: {round(s['tp2'], 6)}

📊 RSI:
15m: {s['multi']['15m']} | 1H: {s['multi']['1h']}
4H: {s['multi']['4h']} | 1D: {s['multi']['1d']}

🕯️ Patterns: {patterns_text}

⚠️ {s['warning']}

⭐ Confidence: {s['score']}/100
        """

        bot.send_message(message.chat.id, msg)


# =====================================
# 🐋 KEEP ALIVE ENGINE
# =====================================

def keep_alive():
    while True:
        try:
            url = os.environ.get("RENDER_URL")
            if url:
                urllib.request.urlopen(url)
                print("🐋 KEEP ALIVE ACTIVE")
        except Exception as e:
            print("KEEP ALIVE ERROR:", e)
        time.sleep(300)
        
# =====================================
# 🚀 START SYSTEM
# =====================================

def telegram_engine():
    while True:
        try:
            print("🐋 TELEGRAM ENGINE STARTED")
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception:
            print("🚨 TELEGRAM ERROR")
            print(traceback.format_exc())
        print("🔄 Restarting Telegram...")
        time.sleep(5)


threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=telegram_engine, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

print("🔥 AHAD AI v13.0 ZERO-LAG ENTRY ONLINE 🐋")

while True:
    time.sleep(60)
