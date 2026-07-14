# ================================================
# 🚀 AHAD AI v18.2
# MICRO MOMENTUM EDITION
# ================================================

import os
import time
import threading
import traceback
import requests
import urllib.request

from flask import Flask
import telebot


# ================================================
# 🔑 TELEGRAM TOKEN
# ================================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise Exception("❌ BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)


# ================================================
# 🌐 RENDER KEEP ALIVE SERVER
# ================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v18.2 MICRO MOMENTUM ONLINE 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ================================================
# 🏦 SECTOR DATABASE
# ================================================

SECTORS = {
    "AI": ["FET", "TAO", "WLD", "ARKM", "AI", "RENDER"],
    "GAMING": ["APE", "SAND", "MANA", "GALA", "IMX", "AXS"],
    "DEFI": ["UNI", "AAVE", "LINK", "CRV", "MKR", "COMP"],
    "MEME": ["DOGE", "SHIB", "PEPE", "BONK", "FLOKI"],
    "LAYER1": ["SOL", "AVAX", "DOT", "NEAR", "ADA"],
    "RWA": ["ONDO", "PENDLE", "ENA"],
    "L2": ["ARB", "OP", "MATIC", "BASE"],
    "ZK": ["ZK", "ZKSYNC"],
    "DEPIN": ["RENDER", "HNT", "AKT"]
}


# ================================================
# ⬛ OKX FUTURES CRYPTO ONLY
# ================================================

def get_symbols():
    try:
        url = "https://www.okx.com/api/v5/public/instruments"
        params = {"instType": "SWAP"}
        data = requests.get(url, params=params, timeout=15).json()

        blocked = [
            "TSLA", "AMZN", "AAPL", "NVDA", "META", "GOOGL", "MSFT", "NFLX",
            "AMD", "COIN", "MSTR", "BABA", "PLTR", "HOOD",
            "XAU", "EUR", "GBP", "JPY",
            "SPX", "NASDAQ", "DOW"
        ]

        result = []
        for x in data["data"]:
            symbol = x["instId"]
            if (
                x["settleCcy"] == "USDT"
                and x["state"] == "live"
                and x.get("ctType") == "linear"
                and "USD" not in x["instId"].replace("USDT", "")
                and not any(b in symbol for b in blocked)
            ):
                result.append(symbol)

        print("🐋 MARKETS FOUND:", len(result))
        return result

    except Exception as e:
        print("SYMBOL ERROR:", e)
        return []


# ================================================
# 🐋 TOP FLOW SCANNER
# ================================================

def top_flow_scanner(symbols):
    results = []
    for symbol in symbols:
        try:
            c15 = get_candles(symbol, "15m")
            if len(c15) < 50:
                continue

            volumes = [x["volume"] for x in c15]
            closes = [x["close"] for x in c15]

            vol_now = sum(volumes[-5:])
            vol_avg = sum(volumes[-40:]) / 40

            if vol_avg == 0:
                continue

            flow = vol_now / vol_avg
            move = ((closes[-1] - closes[-20]) / closes[-20]) * 100

            if move > 10:
                continue

            if flow >= 1.15:
                results.append({"coin": symbol, "flow": flow})

        except:
            pass

        time.sleep(0.01)
        if len(results) >= 80:
            break

    results = sorted(results, key=lambda x: x["flow"], reverse=True)
    return [x["coin"] for x in results[:100]]


# ================================================
# 🕯 OKX CANDLES ENGINE
# ================================================

def get_candles(symbol, tf):
    try:
        frames = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": symbol, "bar": frames[tf], "limit": 150}

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


print("🔥 AHAD AI v18.2 CORE READY 🐋")


# ================================================
# 📊 INDICATORS ENGINE
# ================================================

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


def macd_simple(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow:
        return 0
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    return ema_fast - ema_slow


# ================================================
# 📊 VWAP
# ================================================

def vwap(candles):
    try:
        total_value = 0
        total_volume = 0
        for c in candles:
            typical = (c["high"] + c["low"] + c["close"]) / 3
            total_value += typical * c["volume"]
            total_volume += c["volume"]
        if total_volume == 0:
            return 0
        return total_value / total_volume
    except:
        return 0


# ================================================
# 📊 OBV
# ================================================

def obv(candles):
    try:
        obv_value = 0
        for i in range(1, len(candles)):
            if candles[i]["close"] > candles[i-1]["close"]:
                obv_value += candles[i]["volume"]
            elif candles[i]["close"] < candles[i-1]["close"]:
                obv_value -= candles[i]["volume"]
        return obv_value
    except:
        return 0


# ================================================
# 📊 DONCHIAN CHANNELS
# ================================================

def donchian(candles, period=20):
    try:
        if len(candles) < period:
            return {"high": 0, "low": 0, "middle": 0}
        
        recent = candles[-period:]
        high = max([c["high"] for c in recent])
        low = min([c["low"] for c in recent])
        middle = (high + low) / 2
        
        return {"high": high, "low": low, "middle": middle}
    except:
        return {"high": 0, "low": 0, "middle": 0}


# ================================================
# 🧠 AI ENGINES
# ================================================

def sector_flow(symbols):
    try:
        result = {}
        for sector, coins in SECTORS.items():
            power = 0
            for symbol in symbols:
                if any(coin in symbol for coin in coins):
                    candles = get_candles(symbol, "1h")
                    if len(candles) > 50:
                        volumes = [x["volume"] for x in candles]
                        recent = sum(volumes[-5:])
                        average = sum(volumes[-50:]) / 10
                        if average > 0:
                            power += recent / average

            result[sector] = round(power, 2)

        hot_sector = max(result, key=result.get)
        return {"sector": hot_sector, "power": result[hot_sector]}

    except Exception as e:
        print("SECTOR ERROR:", e)
        return {"sector": "UNKNOWN", "power": 0}


def smart_money(candles):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 10

        if volume_avg == 0:
            flow = 0
        else:
            flow = volume_now / volume_avg

        move = ((closes[-1] - closes[-24]) / closes[-24]) * 100

        if flow >= 1.5 and abs(move) < 8:
            status = "🐋 SMART ACCUMULATION"
        elif flow >= 1.5 and move > 8:
            status = "🚨 WHALE EXIT"
        else:
            status = "NORMAL"

        return {"flow": round(flow, 2), "status": status}

    except Exception as e:
        print("SMART MONEY ERROR:", e)
        return {"flow": 0, "status": "ERROR"}


def pre_pump_engine(candles):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        price = closes[-1]
        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            return {"status": "NORMAL", "score": 0}

        flow = volume_now / volume_avg
        move = ((price - closes[-30]) / closes[-30]) * 100
        current_rsi = rsi(closes)

        if flow >= 1.15 and abs(move) < 5 and 35 <= current_rsi <= 65:
            return {"status": "🐋 WHALE LOADING", "score": 25}

        return {"status": "NORMAL", "score": 0}

    except Exception as e:
        print("PRE PUMP ERROR:", e)
        return {"status": "ERROR", "score": 0}


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


def fomo_filter(candles):
    closes = [x["close"] for x in candles]
    price = closes[-1]

    move = ((price - closes[-96]) / closes[-96]) * 100
    current_rsi = rsi(closes)

    if move > 5 and current_rsi > 65:
        return False, "⏳ WAIT PULLBACK"

    if move > 8:
        return False, "🚫 MOVE DONE - WAIT RETEST"

    if current_rsi > 75:
        return False, "🚫 RSI HOT"

    return True, "🐋 EARLY ENTRY AREA"


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
    
# ================================================
# 🎯 ANALYZE ENGINE (FLEX SCORE + MICRO MOMENTUM)
# ================================================

def analyze(symbol, sector):
    try:
        c15 = get_candles(symbol, "15m")
        c1h = get_candles(symbol, "1h")
        c4h = get_candles(symbol, "4h")
        c1d = get_candles(symbol, "1d")

        if len(c15) < 60 or len(c1h) < 60 or len(c4h) < 60 or len(c1d) < 60:
            return None

        price = c15[-1]["close"]

        safe, warning = fomo_filter(c15)
        if not safe:
            return None

        brain = ai_brain(c1h)
        if brain["direction"] == "WAIT":
            return None

        sr = support_resistance(c15)
        money = smart_money(c15)
        pre = pre_pump_engine(c15)
        multi = multi_rsi_engine(c15, c1h, c4h, c1d)
        trap = trap_detector(c15)

        closes15 = [x["close"] for x in c15]
        closes1h = [x["close"] for x in c1h]
        closes4h = [x["close"] for x in c4h]
        closes1d = [x["close"] for x in c1d]

        rsi_15m = rsi(closes15)
        rsi_1h = rsi(closes1h)
        rsi_4h = rsi(closes4h)
        rsi_1d = rsi(closes1d)

        flow = money["flow"]

        # ================================================
        # 📊 MICRO MOMENTUM (آخر ساعة)
        # ================================================

        if len(c1h) >= 2:
            micro_move = ((c1h[-1]["close"] - c1h[-2]["close"]) / c1h[-2]["close"]) * 100
        else:
            micro_move = 0

        if micro_move > 3:
            micro_score = 15
            micro_label = "🚀 MICRO MOMENTUM"
        elif micro_move > 1:
            micro_score = 10
            micro_label = "📈 MICRO MOMENTUM"
        elif micro_move > 0:
            micro_score = 5
            micro_label = "📊 MICRO MOMENTUM"
        else:
            micro_score = 0
            micro_label = "⏳ NO MICRO MOMENTUM"

        # ================================================
        # 📊 24H CHANGE & VOLUME (مرن)
        # ================================================

        ticker = requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
        ).json()

        change_24h = float(ticker["priceChangePercent"])
        volume_24h = float(ticker["quoteVolume"])

        # تصنيف الحجم (بدل الفلتر الصارم)
        if volume_24h > 10_000_000:
            volume_score = 15
            volume_label = "🐋 WHALE"
        elif volume_24h > 1_000_000:
            volume_score = 10
            volume_label = "🐬 DOLPHIN"
        elif volume_24h > 500_000:
            volume_score = 5
            volume_label = "🐟 FISH"
        else:
            volume_score = 3
            volume_label = "🦐 SHRIMP"

        # ================================================
        # 📊 NEW INDICATORS v18.2
        # ================================================

        vwap_value = vwap(c15)
        obv_value = obv(c15)
        donchian_data = donchian(c15, 20)
        macd_value = macd_simple(closes15)

        # ================================================
        # 🔥 FLEX SCORE SYSTEM (v18.2)
        # ================================================

        flex_score = 0
        breakout = False

        # 1. Donchian Breakout (20)
        if price > donchian_data["high"]:
            flex_score += 20
            breakout = True

        # 2. OBV اتجاه صاعد (15)
        if obv_value > 0:
            flex_score += 15

        # 3. VWAP (10)
        if price > vwap_value:
            flex_score += 10

        # 4. RSI (10)
        if 40 <= rsi_15m <= 65:
            flex_score += 10

        # 5. Volume Flow (10)
        if flow >= 1.5:
            flex_score += 10
        elif flow >= 1.2:
            flex_score += 5

        # 6. Smart Money (15)
        if money["status"] == "🐋 SMART ACCUMULATION":
            flex_score += 15

        # 7. Pre Pump (10)
        if pre["status"] == "🐋 WHALE LOADING":
            flex_score += 10

        # 8. MACD (5)
        if macd_value > 0:
            flex_score += 5

        # 9. Near Support (5)
        if sr["near_support"] < 3:
            flex_score += 5

        # 10. Quiet Accumulation (10)
        bb_width = (max([c["high"] for c in c15[-20:]]) - min([c["low"] for c in c15[-20:]])) / price
        if bb_width < 0.03 and flow > 1.2:
            flex_score += 10

        # 11. Micro Momentum (15)
        flex_score += micro_score

        # 12. Volume Score (15)
        flex_score += volume_score

        score = flex_score
        score = max(0, min(100, score))

        # ================================================
        # ⭐ SIGNAL TYPE (v18.2)
        # ================================================

        if breakout and score >= 70:
            signal_type = "🚀 BREAKOUT SNIPER"
        elif micro_score >= 15 and score >= 60:
            signal_type = "⚡ MICRO MOMENTUM"
        elif score >= 80 and money["status"] == "🐋 SMART ACCUMULATION":
            signal_type = "🐋 QUIET ACCUMULATION"
        elif score >= 70:
            signal_type = "📈 MOMENTUM"
        elif score >= 60:
            signal_type = "👀 WATCH"
        else:
            signal_type = "⏳ LATE"

        # ================================================
        # ⭐ QUALITY LEVEL (v18.2)
        # ================================================

        if trap == "🪤 BULL TRAP":
            quality = "MEDIUM QUALITY ⚠️"
        elif score >= 90:
            quality = "ELITE SIGNAL ✅"
        elif score >= 80:
            quality = "HIGH QUALITY ✅"
        elif score >= 70:
            quality = "GOOD QUALITY ✅"
        elif score >= 60:
            quality = "WATCHLIST 👀"
        else:
            quality = "LOW QUALITY ❌"

        # ================================================
        # 🐋 MONEY STATUS
        # ================================================

        if flow >= 3:
            money_status = "🚀 WHALE BUYING"
        elif flow >= 2:
            money_status = "🐋 SMART ACCUMULATION"
        elif flow >= 1.2:
            money_status = "💧 HEALTHY FLOW"
        else:
            money_status = "NORMAL"

        # ================================================
        # 🎯 EARLY ENTRY CHECK
        # ================================================

        if rsi_15m < 60 and flow > 1 and trap != "🪤 BULL TRAP":
            early_text = "🐋 EARLY ENTRY AREA"
        else:
            early_text = "⏳ WAIT FOR ENTRY"

        # ================================================
        # 🎯 ENTRY ZONE & TARGETS
        # ================================================

        move = atr(c15)

        entry_low = price * 0.995
        entry_high = price * 1.005

        if brain["direction"] == "🟢 LONG":
            sl = sr["support"] * 0.995
            tp1 = price + move * 2
            tp2 = price + move * 3
        else:
            sl = sr["resistance"] * 1.005
            tp1 = price - move * 2
            tp2 = price - move * 3

        if tp1 <= entry_high:
            tp1 = entry_high + move * 0.8

        return {
            "coin": symbol,
            "sector": sector,
            "direction": brain["direction"],
            "score": round(score),
            "quality": quality,
            "signal_type": signal_type,
            "money_status": money_status,
            "early_text": early_text,
            "entry_low": round(entry_low, 6),
            "entry_high": round(entry_high, 6),
            "sl": round(sl, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "liquidity": money["flow"],
            "pre_pump": pre["status"],
            "multi": multi,
            "trap": trap,
            "warning": warning,
            "vwap": round(vwap_value, 6),
            "obv": round(obv_value, 2),
            "donchian_high": round(donchian_data["high"], 6),
            "micro_score": micro_score,
            "micro_label": micro_label,
            "volume_label": volume_label,
            "change_24h": round(change_24h, 2)
        }

    except Exception as e:
        print("ANALYZE ERROR:", e)
        return None


# ================================================
# 🤖 TELEGRAM SCANNER (v18.2)
# ================================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, """
🐋 AHAD AI v18.2 ONLINE 🚀

🧠 Flex Score System ACTIVE
⚡ Micro Momentum ACTIVE
🚀 Breakout Sniper ACTIVE
🐋 Quiet Accumulation ACTIVE
📊 VWAP + OBV + Donchian ACTIVE
🐋 Smart Money ACTIVE
🪤 Trap Detector ACTIVE

🎯 Goal: Snipe breakouts & micro momentum

Send /scan
""")


@bot.message_handler(commands=["scan"])
def scan(message):
    bot.reply_to(message, """
🐋 AHAD AI v18.2 SCANNING...

🔍 Flex Score Analysis
⚡ Hunting Micro Momentum
🚀 Hunting Breakouts
🐋 Tracking Smart Money
📊 VWAP + OBV + Donchian

Please wait ⏳
""")

    long_results = []
    all_symbols = get_symbols()
    symbols = top_flow_scanner(all_symbols)

    flow = sector_flow(all_symbols)
    hot_sector = flow["sector"]

    bot.send_message(message.chat.id, f"""
🔥 MARKET FLOW

🏦 Hot Sector: {hot_sector}
🐋 Flow Power: {flow['power']}
""")

    if len(symbols) < 20:
        symbols = all_symbols

    bot.send_message(message.chat.id, f"💎 Smart Money Watchlist: {len(symbols)} coins")

    for symbol in symbols:
        result = analyze(symbol, hot_sector)
        if result:
            if result["score"] > 100:
                result["score"] = 100

            if result["direction"] == "🟢 LONG":
                # مرونة أعلى
                if (
                    result["score"] >= 45
                    or result["pre_pump"] == "🐋 WHALE LOADING"
                    or "BREAKOUT" in result["signal_type"]
                    or result.get("micro_score", 0) >= 10
                ):
                    long_results.append(result)

        time.sleep(0.03)

    # ترتيب حسب: الزخم → السكور → السيولة
    results = sorted(
        long_results,
        key=lambda x: (
            x.get("micro_score", 0),
            x["score"],
            x["liquidity"]
        ),
        reverse=True
    )[:5]

    if not results:
        bot.send_message(message.chat.id, """
👀 No sniper setups now

⚡ Waiting for Micro Momentum
🚀 Waiting for Breakout
⏳ Try again later
""")
        return

    for s in results:
        msg = f"""
🚨 AHAD AI v18.2 🐋

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

{s['quality']}
📊 Type: {s['signal_type']}
⚡ Micro: {s['micro_label']}

🔥 Flex Score: {s['score']}/100 | 💧Flow: {s['liquidity']}X
📈 24H: {s['change_24h']}%
💰 Volume: {s['volume_label']}
🐋 Money: {s['money_status']}
🪤 Trap: {s['trap']}

📊 VWAP: {s['vwap']}
📈 OBV: {s['obv']}
🚀 Donchian High: {s['donchian_high']}

🎯 Entry: {round(s['entry_low'],6)} - {round(s['entry_high'],6)}
🛑 SL: {round(s['sl'],6)}

🥇 TP1: {round(s['tp1'],6)}
🥈 TP2: {round(s['tp2'],6)}

📊 RSI:
15m:{s['multi']['15m']} | 1H:{s['multi']['1h']}
4H:{s['multi']['4h']} | 1D:{s['multi']['1d']}

⚠️ {s['warning']}
{s['early_text']}
"""
        bot.send_message(message.chat.id, msg)
        
# ================================================
# 🚀 SYSTEM
# ================================================

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

print("🔥 AHAD AI v18.2 MICRO MOMENTUM ONLINE 🐋")

while True:
    time.sleep(60)
