# =====================================
# 🚀 AHAD AI v12.0
# ALPHA HUNTER EDITION
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

    raise Exception(
        "❌ BOT_TOKEN NOT FOUND"
    )


bot = telebot.TeleBot(
    TOKEN
)


# =====================================
# 🌐 RENDER KEEP ALIVE SERVER
# =====================================

app = Flask(
    __name__
)


@app.route("/")
def home():

    return (
        "🐋 AHAD AI v12.0 "
        "ALPHA HUNTER ONLINE 🚀"
    )


def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )


    app.run(

        host="0.0.0.0",

        port=port

    )



# =====================================
# 🏦 SECTOR DATABASE v12.0
# =====================================

SECTORS = {


    "AI": [

        "FET",
        "TAO",
        "WLD",
        "ARKM",
        "AI",
        "RENDER"

    ],


    "GAMING": [

        "APE",
        "SAND",
        "MANA",
        "GALA",
        "IMX",
        "AXS"

    ],


    "DEFI": [

        "UNI",
        "AAVE",
        "LINK",
        "CRV",
        "MKR",
        "COMP"

    ],


    "MEME": [

        "DOGE",
        "SHIB",
        "PEPE",
        "BONK",
        "FLOKI"

    ],


    "LAYER1": [

        "SOL",
        "AVAX",
        "DOT",
        "NEAR",
        "ADA"

    ],


    "RWA": [

        "ONDO",
        "PENDLE",
        "ENA"

    ]

}



# =====================================
# 🐋 CACHE SYSTEM v12.0
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
    return age < 120  # 120 ثانية


def get_alpha_symbols():
    """جلب قائمة العملات من Binance Alpha مع Cache و Fallback"""

    # 1. تحقق من Cache
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
            alpha_symbols.append(
                token["symbol"].upper()
            )

        # حفظ في Cache
        cache["alpha"]["data"] = alpha_symbols
        cache["alpha"]["timestamp"] = datetime.now()
        print(f"✅ Alpha: {len(alpha_symbols)} symbols loaded")
        return alpha_symbols

    except Exception as e:
        print(f"⚠️ Alpha API Error: {e}")

        # 2. Fallback: استخدم Cache القديم
        if cache["alpha"]["data"] is not None:
            print("🔄 Alpha: Using Fallback Cache")
            return cache["alpha"]["data"]

        # 3. Fallback: قائمة فارغة
        print("⚠️ Alpha: No fallback available, returning empty list")
        return []


def get_binance_futures():
    """جلب قائمة العقود الآجلة من Binance Futures مع Cache"""

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
    """جلب قائمة العملات من OKX مع Cache"""

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
            if (
                x["settleCcy"] == "USDT"
                and x["state"] == "live"
            ):
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
# 🛡️ HEALTH CHECK v12.0
# =====================================

health_status = {
    "alpha": "UNKNOWN",
    "futures": "UNKNOWN",
    "okx": "UNKNOWN"
}


def health_check():
    """فحص صحة جميع الـ APIs"""

    # اختبار Alpha
    try:
        url = "https://www.binance.com/bapi/defi/v1/public/alpha-trade/tokens"
        requests.get(url, timeout=5)
        health_status["alpha"] = "ONLINE"
    except:
        health_status["alpha"] = "OFFLINE"

    # اختبار Futures
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        requests.get(url, timeout=5)
        health_status["futures"] = "ONLINE"
    except:
        health_status["futures"] = "OFFLINE"

    # اختبار OKX
    try:
        url = "https://www.okx.com/api/v5/public/instruments"
        requests.get(url, params={"instType": "SWAP"}, timeout=5)
        health_status["okx"] = "ONLINE"
    except:
        health_status["okx"] = "OFFLINE"

    return health_status


def get_intersection_symbols():
    """تقاطع القوائم: Alpha + Futures (للتحقق فقط)"""
    
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
    """جلب جميع التيكرات من Binance Futures مرة واحدة"""
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
# 📈 RELATIVE STRENGTH FILTER v12.0
# =====================================

def get_btc_eth_change():
    """جلب تغير BTC و ETH خلال 24 ساعة"""
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
    """
    مقارنة أداء العملة مع BTC و ETH
    إذا كانت العملة أقوى من BTC و ETH → +15 نقطة
    """
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


        url = (

            "https://www.okx.com"

            "/api/v5/market/candles"

        )



        params = {


            "instId": symbol,


            "bar": frames[tf],


            "limit": 150

        }


        data = requests.get(

            url,

            params=params,

            timeout=10

        ).json()


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


        print(

            "CANDLE ERROR:",

            symbol,

            e

        )


        return []


print(
    "🔥 AHAD AI v12.0 CORE READY 🐋"
)

# =====================================
# 📊 INDICATORS ENGINE v12.0
# =====================================

def ema(values, period):

    if len(values) < period:

        return values[-1]


    k = 2 / (period + 1)

    result = values[0]


    for v in values:

        result = (
            v * k
            +
            result * (1 - k)
        )


    return result


def rsi(values, period=14):

    gains = 0
    losses = 0


    for i in range(-period, -1):

        diff = (
            values[i + 1]
            -
            values[i]
        )


        if diff > 0:

            gains += diff

        else:

            losses -= diff


    if losses == 0:

        return 100


    rs = gains / losses


    return (
        100
        -
        100 / (1 + rs)
    )


def atr(candles):

    ranges = []


    for c in candles[-14:]:

        ranges.append(
            c["high"]
            -
            c["low"]
        )


    return (
        sum(ranges)
        /
        len(ranges)
        )
    
# =====================================
# 🐋 PRE PUMP ENGINE v12.0
# =====================================

def pre_pump_engine(candles, change_24h, rsi_1h):
    """
    اكتشاف PRE-PUMP بناءً على:
    - Flow
    - Volume
    - RSI
    - Move < 5%
    """
    try:

        closes = [
            x["close"]
            for x in candles
        ]

        volumes = [
            x["volume"]
            for x in candles
        ]

        price = closes[-1]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            return {"status": "NORMAL", "score": 0}

        flow = volume_now / volume_avg

        # حساب النقاط حسب Flow
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

        # التحقق من PRE-PUMP
        if (
            flow >= 1.2
            and abs(change_24h) < 5
            and 35 <= rsi_1h <= 65
        ):
            return {
                "status": "🐋 PRE PUMP DETECTED",
                "score": flow_score,
                "flow": round(flow, 2)
            }

        return {
            "status": "NORMAL",
            "score": flow_score,
            "flow": round(flow, 2)
        }

    except Exception as e:
        print("PRE PUMP ERROR:", e)
        return {"status": "ERROR", "score": 0, "flow": 0}


# =====================================
# 🧱 SUPPORT RESISTANCE ENGINE
# =====================================

def support_resistance(candles):

    highs = [
        x["high"]
        for x in candles[-80:]
    ]

    lows = [
        x["low"]
        for x in candles[-80:]
    ]

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
# 🛡️ ANTI LATE ENTRY v12.0
# =====================================

def fomo_filter(candles):

    closes = [
        x["close"]
        for x in candles
    ]

    price = closes[-1]

    move = ((price - closes[-96]) / closes[-96]) * 100

    current_rsi = rsi(closes)

    # Early Move Filter: قبول فقط -3% إلى +5%
    if move < -3 or move > 5:
        return False, "⏳ OUT OF RANGE (-3% to +5%)"

    if current_rsi > 75:
        return False, "🚫 RSI HOT"

    return True, "🐋 EARLY ENTRY AREA"


# =====================================
# 🧠 AI BRAIN ENGINE v12.0
# =====================================

def ai_brain(candles):

    closes = [
        x["close"]
        for x in candles
    ]

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

    return {
        "direction": direction,
        "confidence": abs(score)
    }


# =====================================
# 🪤 TRAP DETECTOR v12.0
# =====================================

def trap_detector(candles):

    closes = [
        x["close"]
        for x in candles
    ]

    highs = [
        x["high"]
        for x in candles
    ]

    lows = [
        x["low"]
        for x in candles
    ]

    price = closes[-1]
    r = rsi(closes)

    if price >= max(highs[-50:]) * 0.98 and r > 70:
        return "🪤 BULL TRAP"

    if price <= min(lows[-50:]) * 1.02 and r < 35:
        return "🪤 BEAR TRAP"

    return "✅ NO TRAP"


# =====================================
# 🐋 SMART MONEY ENGINE v12.0
# =====================================

def smart_money(candles, rsi_1h, change_24h):
    """
    اكتشاف Whale Loading بناءً على:
    - Flow >= 2.0
    - RSI 1H < 65
    - 24H Change < 5%
    """
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 10

        if volume_avg == 0:
            return {"status": "NORMAL", "flow": 0}

        flow = volume_now / volume_avg

        # Whale Loading شروط
        if (
            flow >= 2.0
            and rsi_1h < 65
            and abs(change_24h) < 5
        ):
            return {
                "status": "🐋 WHALE LOADING",
                "flow": round(flow, 2)
            }

        return {
            "status": "NORMAL",
            "flow": round(flow, 2)
        }

    except Exception as e:
        print("SMART MONEY ERROR:", e)
        return {"status": "ERROR", "flow": 0}


# =====================================
# 📊 MULTI TIMEFRAME ENGINE v12.0
# =====================================

def multi_rsi_engine(c15, c1h, c4h, c1d):

    try:

        data = {}

        frames = {

            "15m": c15,
            "1h": c1h,
            "4h": c4h,
            "1d": c1d

        }

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
# 🚀 FINAL ANALYZE ENGINE v12.0
# =====================================

def analyze(symbol, sector, tickers, btc_eth, alpha_symbols):
    """
    تحليل عملة واحدة مع تمرير التيكرات وبيانات BTC/ETH و Alpha
    """
    try:

        # تحديد المصدر (OKX أو Binance)
        okx_symbol = f"{symbol}-USDT-SWAP"
        okx_candles = get_candles(okx_symbol, "15m")

        if len(okx_candles) >= 60:
            # استخدم OKX
            c15 = okx_candles
            c1h = get_candles(okx_symbol, "1h")
            c4h = get_candles(okx_symbol, "4h")
            c1d = get_candles(okx_symbol, "1d")
            symbol_okx = okx_symbol
        else:
            # استخدم Binance (OKX غير متوفر)
            return None

        if (
            len(c15) < 60
            or len(c1h) < 60
            or len(c4h) < 60
            or len(c1d) < 60
        ):
            return None

        price = c15[-1]["close"]

        # =====================================
        # 📈 24H CHANGE & VOLUME (من التيكرات)
        # =====================================

        ticker = tickers.get(symbol)
        if not ticker:
            return None

        change_24h = ticker["priceChangePercent"]
        volume_24h = ticker["quoteVolume"]

        # Volume Filter: أقل من 1M$ → تجاهل
        if volume_24h < 1_000_000:
            return None

        # =====================================
        # 📈 RSI 1H & 4H
        # =====================================

        closes1h = [x["close"] for x in c1h]
        closes4h = [x["close"] for x in c4h]

        rsi_1h = rsi(closes1h)
        rsi_4h = rsi(closes4h)

        # =====================================
        # 🛡️ FOMO FILTER
        # =====================================

        safe, warning = fomo_filter(c15)
        if not safe:
            return None

        # =====================================
        # 🧠 AI BRAIN
        # =====================================

        brain = ai_brain(c1h)
        if brain["direction"] == "WAIT":
            return None

        # =====================================
        # 📈 TREND FILTER (1H & 4H)
        # =====================================

        e20_1h = ema(closes1h, 20)
        e50_1h = ema(closes1h, 50)
        e20_4h = ema(closes4h, 20)
        e50_4h = ema(closes4h, 50)

        if not (e20_1h > e50_1h and e20_4h > e50_4h):
            return None

        # =====================================
        # 🧱 SUPPORT / RESISTANCE
        # =====================================

        sr = support_resistance(c15)

        # Resistance Filter
        if sr["near_resistance"] < 1:
            return None
        elif sr["near_resistance"] < 3:
            resistance_penalty = 10
        else:
            resistance_penalty = 0

        # =====================================
        # 📈 RELATIVE STRENGTH FILTER
        # =====================================

        rs_score = relative_strength_filter(change_24h, btc_eth["btc"], btc_eth["eth"])

        # =====================================
        # 🐋 SMART MONEY
        # =====================================

        money = smart_money(c15, rsi_1h, change_24h)

        # =====================================
        # ⚡ PRE PUMP ENGINE
        # =====================================

        pre = pre_pump_engine(c15, change_24h, rsi_1h)

        # =====================================
        # 📊 MULTI RSI
        # =====================================

        multi = multi_rsi_engine(c15, c1h, c4h, c1d)

        # =====================================
        # 🪤 TRAP DETECTOR
        # =====================================

        trap = trap_detector(c15)

        # =====================================
        # 🔥 CONFIDENCE SCORE (100)
        # =====================================

        score = 0

        # التحقق من Alpha
        base = normalize_symbol(symbol)
        is_alpha = base in alpha_symbols

        # Alpha Bonus (10)
        if is_alpha:
            score += 10

        # Flow (20)
        if pre["flow"] >= 3.0:
            score += 20
        elif pre["flow"] >= 2.0:
            score += 15
        elif pre["flow"] >= 1.5:
            score += 10
        elif pre["flow"] >= 1.2:
            score += 5

        # Whale (20)
        if money["status"] == "🐋 WHALE LOADING":
            score += 20

        # Trend (15)
        if e20_1h > e50_1h and e20_4h > e50_4h:
            score += 15

        # RSI (10)
        if 40 <= rsi_1h <= 65:
            score += 10

        # Volume (10)
        if volume_24h > 5_000_000:
            score += 10

        # Resistance (10)
        score += (10 - resistance_penalty)

        # AI Brain (5)
        score += brain["confidence"] // 20

        # Relative Strength (+15)
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

        move = atr(c15)

        entry_low = price * 0.995
        entry_high = price * 1.005

        sl = sr["support"] * 0.995
        tp1 = price + move * 2
        tp2 = price + move * 3

        # =====================================
        # 🏷️ SOURCE STATUS
        # =====================================

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
            "entry_low": entry_low,
            "entry_high": entry_high,
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
# 🤖 TELEGRAM ENGINE v12.0
# =====================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
        """
🐋 AHAD AI v12.0 ONLINE 🚀

🧠 Alpha Hunter ACTIVE
🐋 Whale Loading ACTIVE
⚡ Pre-Pump Detection ACTIVE
🛡️ Health Check ACTIVE
📈 Relative Strength ACTIVE

🎯 Goal:
Early entries before pumps

Send /scan
        """
    )



# =====================================
# 🔎 SMART SCANNER v12.0
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        """
🐋 AHAD AI v12.0 SCANNING...

🔍 Alpha Hunter Engine
📊 Futures Filter
⚡ Pre-Pump Detection
📈 Relative Strength Analysis

Please wait ⏳
        """
    )


    # =====================================
    # 🛡️ HEALTH CHECK
    # =====================================

    health = health_check()

    health_msg = "🛡️ API STATUS:\n"
    for api, status in health.items():
        icon = "🟢" if status == "ONLINE" else "🔴"
        health_msg += f"{icon} {api.upper()}: {status}\n"

    bot.send_message(
        message.chat.id,
        health_msg
    )


    # =====================================
    # 🎯 GET FUTURES SYMBOLS (Base List)
    # =====================================

    symbols = get_binance_futures()

    if not symbols:
        bot.send_message(
            message.chat.id,
            "⚠️ No futures symbols found"
        )
        return

    bot.send_message(
        message.chat.id,
        f"📊 Futures Watchlist: {len(symbols)} coins"
    )


    # =====================================
    # 📊 LOAD TICKERS, BTC/ETH & ALPHA ONCE
    # =====================================

    tickers = get_all_tickers()
    btc_eth = get_btc_eth_change()
    alpha_symbols = get_alpha_symbols()


    # =====================================
    # 🔍 ANALYZE
    # =====================================

    long_results = []

    for symbol in symbols:

        # تحديد القطاع
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

                if (
                    result["score"] >= 60
                    and result["liquidity"] >= 1.2
                ):

                    long_results.append(result)

        time.sleep(0.03)


    # =====================================
    # 📊 SORT: Whale Loading → Flow → Score
    # =====================================

    def sort_key(x):
        whale_score = 10 if x["money"] == "🐋 WHALE LOADING" else 0
        return (whale_score, x["liquidity"], x["score"])

    results = sorted(
        long_results,
        key=sort_key,
        reverse=True
    )[:5]


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


    # =====================================
    # 📨 SEND RESULTS
    # =====================================

    for s in results:

        msg = f"""
🚨 AHAD AI v12.0 🐋

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

🎯 Entry: {round(s['entry_low'],6)} - {round(s['entry_high'],6)}
🛑 SL: {round(s['sl'],6)}

🥇 TP1: {round(s['tp1'],6)}
🥈 TP2: {round(s['tp2'],6)}

📊 RSI:
15m: {s['multi']['15m']} | 1H: {s['multi']['1h']}
4H: {s['multi']['4h']} | 1D: {s['multi']['1d']}

⚠️ {s['warning']}

⭐ Confidence: {s['score']}/100
        """

        bot.send_message(
            message.chat.id,
            msg
        )



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

            print(
                "🐋 TELEGRAM ENGINE STARTED"
            )


            bot.infinity_polling(

                skip_pending=True,

                timeout=60,

                long_polling_timeout=60

            )


        except Exception:


            print(
                "🚨 TELEGRAM ERROR"
            )


            print(
                traceback.format_exc()
            )



        print(
            "🔄 Restarting Telegram..."
        )


        time.sleep(
            5
        )



threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=telegram_engine,
    daemon=True
).start()


threading.Thread(
    target=keep_alive,
    daemon=True
).start()


print(
    "🔥 AHAD AI v12.0 ALPHA HUNTER ONLINE 🐋"
)



while True:

    time.sleep(
        60
    )
