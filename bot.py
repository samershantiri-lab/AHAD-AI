# =====================================
# 🚀 AHAD AI v11.4
# SMART ENTRY EDITION
# =====================================

import os
import time
import threading
import traceback
import requests
import urllib.request

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
        "🐋 AHAD AI v11.4 "
        "SMART ENTRY ONLINE 🚀"
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
# 🏦 SECTOR DATABASE v11.4
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
# ⬛ OKX FUTURES CRYPTO ONLY
# =====================================

def get_symbols():

    try:

        url = (
            "https://www.okx.com"
            "/api/v5/public/instruments"
        )


        params = {

            "instType": "SWAP"

        }


        data = requests.get(

            url,

            params=params,

            timeout=15

        ).json()



        blocked = [

            # STOCKS
            "TSLA",
            "AMZN",
            "AAPL",
            "NVDA",
            "META",
            "GOOGL",
            "MSFT",
            "NFLX",
            "AMD",
            "COIN",
            "MSTR",
            "BABA",
            "PLTR",
            "HOOD",

            # GOLD / FOREX
            "XAU",
            "EUR",
            "GBP",
            "JPY",

            # INDEX
            "SPX",
            "NASDAQ",
            "DOW"

        ]



        result = []



        for x in data["data"]:


            symbol = x["instId"]


            if (

                x["settleCcy"] == "USDT"

                and

                x["state"] == "live"

                and

                x.get("ctType") == "linear"

                and

                "USD" not in x["instId"].replace("USDT", "")

                and

                not any(
                    b in symbol
                    for b in blocked
                )

            ):


                result.append(
                    symbol
                )



        print(

            "🐋 MARKETS FOUND:",

            len(result)

        )


        return result



    except Exception as e:


        print(

            "SYMBOL ERROR:",

            e

        )


        return []



# =====================================
# 🐋 TOP FLOW SCANNER v12
# Find hot money before AI scan
# =====================================

def top_flow_scanner(symbols):

    results = []

    for symbol in symbols:

        try:

            c15 = get_candles(symbol, "15m")

            if len(c15) < 50:
                continue


            volumes = [
                x["volume"]
                for x in c15
            ]

            closes = [
                x["close"]
                for x in c15
            ]


            vol_now = sum(volumes[-5:])

            vol_avg = (
                sum(volumes[-40:])
                /
                40
            )


            if vol_avg == 0:
                continue


            flow = vol_now / vol_avg


            move = (
                (closes[-1] - closes[-20])
                /
                closes[-20]
            ) * 100


            # لا نريد عملة طارت كثير
            if move > 10:
                continue


            if flow >= 1.15:

                results.append({

                    "coin": symbol,

                    "flow": flow

                })


        except:

            pass


        time.sleep(0.01)

        if len(results) >= 80:
            break


    results = sorted(
        results,
        key=lambda x: x["flow"],
        reverse=True
    )


    return [
        x["coin"]
        for x in results[:100]
    ]



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
    "🔥 AHAD AI v11.4 CORE READY 🐋"
)

# =====================================
# 📊 INDICATORS ENGINE v11.4
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
# 📊 ADX INDICATOR v11.4
# =====================================

def adx(candles, period=14):
    """
    حساب مؤشر ADX لقياس قوة الاتجاه
    """
    try:
        highs = [x["high"] for x in candles]
        lows = [x["low"] for x in candles]
        closes = [x["close"] for x in candles]
        
        if len(closes) < period + 1:
            return 20
        
        # True Range
        tr = []
        for i in range(1, len(closes)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i-1]
            
            tr.append(max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            ))
        
        # Directional Movement
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(closes)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)
                
            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)
        
        # Smooth
        tr_smooth = sum(tr[-period:]) / period
        plus_smooth = sum(plus_dm[-period:]) / period
        minus_smooth = sum(minus_dm[-period:]) / period
        
        if tr_smooth == 0:
            return 20
        
        plus_di = (plus_smooth / tr_smooth) * 100
        minus_di = (minus_smooth / tr_smooth) * 100
        
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        
        # ADX = متوسط DX لآخر period
        return round(dx, 2)
        
    except:
        return 20


# =====================================
# 📊 CCI INDICATOR v11.4
# =====================================

def cci(candles, period=20):
    """
    حساب مؤشر CCI لقياس التشبع
    """
    try:
        typical_prices = [(x["high"] + x["low"] + x["close"]) / 3 for x in candles[-period-1:]]
        
        if len(typical_prices) < period:
            return 0
        
        current_tp = typical_prices[-1]
        mean_tp = sum(typical_prices) / len(typical_prices)
        
        # Mean deviation
        deviation = sum([abs(tp - mean_tp) for tp in typical_prices]) / len(typical_prices)
        
        if deviation == 0:
            return 0
        
        cci_value = (current_tp - mean_tp) / (0.015 * deviation)
        return round(cci_value, 2)
        
    except:
        return 0
        
# =====================================
# 🐋 SMART MONEY ENGINE v11.4
# =====================================

def smart_money(candles):

    try:

        closes = [
            x["close"]
            for x in candles
        ]


        volumes = [
            x["volume"]
            for x in candles
        ]


        volume_now = sum(
            volumes[-5:]
        )


        volume_avg = (
            sum(volumes[-50:])
            /
            10
        )


        if volume_avg == 0:

            flow = 0

        else:

            flow = (
                volume_now
                /
                volume_avg
            )


        move = (
            (
                closes[-1]
                -
                closes[-24]
            )
            /
            closes[-24]
        ) * 100



        if (
            flow >= 1.5
            and
            abs(move) < 8
        ):

            status = (
                "🐋 SMART ACCUMULATION"
            )


        elif (
            flow >= 1.5
            and
            move > 8
        ):

            status = (
                "🚨 WHALE EXIT"
            )


        else:

            status = "NORMAL"



        return {

            "flow": round(flow, 2),

            "status": status

        }



    except Exception as e:

        print(
            "SMART MONEY ERROR:",
            e
        )


        return {

            "flow": 0,

            "status": "ERROR"

        }



# =====================================
# 🐋 PRE PUMP ACCUMULATION ENGINE v11.4
# Detect whales before breakout
# =====================================

def pre_pump_engine(candles):

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


        volume_now = sum(
            volumes[-5:]
        )


        volume_avg = (
            sum(volumes[-50:])
            /
            50
        )


        if volume_avg == 0:

            return {

                "status":"NORMAL",

                "score":0

            }


        flow = (
            volume_now
            /
            volume_avg
        )


        move = (
            (price - closes[-30])
            /
            closes[-30]
        ) * 100


        current_rsi = rsi(
            closes
        )


        # 🐋 Quiet accumulation before pump

        if (
            flow >= 1.15
            and
            abs(move) < 5
            and
            35 <= current_rsi <= 65
        ):

            return {

                "status":"🐋 WHALE LOADING",

                "score":25

            }


        return {

            "status":"NORMAL",

            "score":0

        }


    except Exception as e:

        print(
            "PRE PUMP ERROR:",
            e
        )


        return {

            "status":"ERROR",

            "score":0

        }



# =====================================
# 📊 MULTI TIMEFRAME ENGINE v11.4
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

            closes = [
                x["close"]
                for x in candles
            ]


            value = rsi(
                closes
            )


            data[name] = round(
                value,
                2
            )


            if 50 <= value <= 70:

                score += 10


            elif value > 75:

                score -= 10


            elif value < 35:

                score += 5



        data["score"] = score


        return data



    except Exception as e:

        print(
            "MULTI RSI ERROR:",
            e
        )


        return {

            "15m":50,
            "1h":50,
            "4h":50,
            "1d":50,
            "score":0

        }



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

        "near_support":
        ((price-support)/price)*100,

        "near_resistance":
        ((resistance-price)/price)*100

    }



# =====================================
# 🛡 ANTI LATE ENTRY v11.4
# =====================================

def fomo_filter(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    price = closes[-1]


    move = (

        (price - closes[-96])

        /

        closes[-96]

    ) * 100



    current_rsi = rsi(
        closes
    )


    # Avoid late momentum entry

    if (
        move > 5
        and
        current_rsi > 65
    ):

        return (

            False,

            "⏳ WAIT PULLBACK"

        )



    if move > 8:

        return (

            False,

            "🚫 MOVE DONE - WAIT RETEST"

        )



    if current_rsi > 75:

        return (

            False,

            "🚫 RSI HOT"

        )



    return (

        True,

        "🐋 EARLY ENTRY AREA"

    )



# =====================================
# 🪤 TRAP DETECTOR v11.4
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


    if (
        price >= max(highs[-50:]) * 0.98
        and
        r > 70
    ):

        return "🪤 BULL TRAP"



    if (
        price <= min(lows[-50:]) * 1.02
        and
        r < 35
    ):

        return "🪤 BEAR TRAP"



    return "✅ NO TRAP"



# =====================================
# 🧠 AI BRAIN ENGINE v11.4
# =====================================

def ai_brain(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    price = closes[-1]


    e20 = ema(
        closes,
        20
    )


    e50 = ema(
        closes,
        50
    )


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
# 📊 BREAKOUT DETECTOR v11.4
# =====================================

def breakout_detector(candles, volume_avg):
    """
    اكتشاف الاختراقات الحقيقية
    - اختراق مقاومة سابقة مع حجم تداول مرتفع
    """
    try:
        if len(candles) < 30:
            return {"breakout": False, "type": "NONE"}
        
        price = candles[-1]["close"]
        resistance = max([x["high"] for x in candles[-20:]])
        volume_now = candles[-1]["volume"]
        
        # اختراق مقاومة مع حجم أعلى من المتوسط
        if price > resistance and volume_now > volume_avg * 1.5:
            return {
                "breakout": True,
                "type": "🚀 BREAKOUT",
                "level": round(resistance, 6)
            }
        
        return {"breakout": False, "type": "NONE"}
        
    except:
        return {"breakout": False, "type": "NONE"}


# =====================================
# 📊 REVERSAL DETECTOR v11.4
# =====================================

def reversal_detector(candles):
    """
    اكتشاف الانعكاسات من الدعم مع أنماط الشموع
    """
    try:
        if len(candles) < 5:
            return {"reversal": False, "type": "NONE"}
        
        price = candles[-1]["close"]
        support = min([x["low"] for x in candles[-20:]])
        patterns = []
        
        # Hammer
        last = candles[-1]
        body = abs(last["close"] - last["open"])
        lower_shadow = min(last["open"], last["close"]) - last["low"]
        upper_shadow = last["high"] - max(last["open"], last["close"])
        
        if lower_shadow > body * 2 and upper_shadow < body * 0.5:
            patterns.append("HAMMER")
        
        # Bullish Engulfing
        if len(candles) >= 2:
            c1 = candles[-2]
            c2 = candles[-1]
            if (c1["close"] < c1["open"] and 
                c2["close"] > c2["open"] and 
                c2["open"] < c1["close"] and 
                c2["close"] > c1["open"]):
                patterns.append("BULLISH ENGULFING")
        
        # Doji at support
        if body < (last["high"] - last["low"]) * 0.1:
            patterns.append("DOJI")
        
        near_support = ((price - support) / price) * 100
        
        if near_support < 3 and patterns:
            return {
                "reversal": True,
                "type": "🔄 REVERSAL",
                "pattern": ", ".join(patterns),
                "support": round(support, 6)
            }
        
        return {"reversal": False, "type": "NONE"}
        
    except:
        return {"reversal": False, "type": "NONE"}
        
# =====================================
# 🚀 FINAL ANALYZE ENGINE v11.4
# =====================================

def analyze(symbol, sector):

    try:

        c15 = get_candles(symbol,"15m")
        c1h = get_candles(symbol,"1h")
        c4h = get_candles(symbol,"4h")
        c1d = get_candles(symbol,"1d")


        if (
            len(c15)<60
            or len(c1h)<60
            or len(c4h)<60
            or len(c1d)<60
        ):

            return None



        price = c15[-1]["close"]


        # =====================================
        # 📊 CALCULATE INDICATORS
        # =====================================

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

        # =====================================
        # 📊 NEW INDICATORS v11.4
        # =====================================

        adx_value = adx(c1h)
        cci_value = cci(c15)

        # =====================================
        # 📊 BREAKOUT & REVERSAL DETECTION
        # =====================================

        volume_avg = sum([x["volume"] for x in c15[-50:]]) / 50 if len(c15) >= 50 else 0
        breakout = breakout_detector(c15, volume_avg)
        reversal = reversal_detector(c15)

        # =====================================
        # 🔥 SMART SCORE v11.4 (Weighted)
        # =====================================

        score = 0

        # 1. ADX + TREND (25)
        if adx_value > 25:
            score += 15
        if adx_value > 40:
            score += 10

        # 2. MOMENTUM (RSI + CCI) (20)
        closes1h = [x["close"] for x in c1h]
        rsi_1h = rsi(closes1h)
        if 45 <= rsi_1h <= 65:
            score += 10
        if -100 < cci_value < 100:
            score += 5
        if cci_value > 0:
            score += 5

        # 3. SMART MONEY (20)
        if money["status"] == "🐋 SMART ACCUMULATION":
            score += 15
        if pre["status"] == "🐋 WHALE LOADING":
            score += 5

        # 4. VOLUME (15)
        flow = money["flow"]
        if flow >= 2.0:
            score += 15
        elif flow >= 1.5:
            score += 10
        elif flow >= 1.2:
            score += 5

        # 5. SUPPORT / RESISTANCE (10)
        if sr["near_support"] < 3:
            score += 10
        elif sr["near_support"] < 5:
            score += 5

        # 6. BREAKOUT / REVERSAL BONUS (10)
        if breakout["breakout"]:
            score += 10
        if reversal["reversal"]:
            score += 10

        # 7. MULTI RSI (10)
        score += multi["score"] // 2

        # 8. TRAP PENALTY
        if trap != "✅ NO TRAP":
            score -= 20

        # 9. RSI DAILY PENALTY
        closes1d = [x["close"] for x in c1d]
        rsi_1d = rsi(closes1d)
        if rsi_1d > 70:
            score -= 15
        elif rsi_1d > 65:
            score -= 5

        # 10. RESISTANCE PENALTY
        if sr["near_resistance"] < 3:
            score -= 10

        # =====================================
        # ⭐ QUALITY LEVEL
        # =====================================

        if score >= 85 and breakout["breakout"]:
            quality = "🚀 BREAKOUT"
        elif score >= 80 and money["status"] == "🐋 SMART ACCUMULATION":
            quality = "🐋 SMART MONEY"
        elif score >= 75 and reversal["reversal"]:
            quality = "🔄 REVERSAL"
        elif score >= 70:
            quality = "👀 WATCH"
        else:
            quality = "⏳ LATE MOVE"

        # =====================================
        # 🎯 ENTRY ZONE
        # =====================================

        move = atr(c15)

        if breakout["breakout"]:
            # Breakout Entry: فوق المقاومة مباشرة
            entry_low = breakout["level"] * 0.998
            entry_high = breakout["level"] * 1.002
        elif reversal["reversal"]:
            # Reversal Entry: عند الدعم مع أنماط
            entry_low = reversal["support"] * 0.998
            entry_high = reversal["support"] * 1.002
        else:
            # Normal Entry
            entry_low = price * 0.995
            entry_high = price * 1.005

        # =====================================
        # 🎯 TARGETS
        # =====================================

        if brain["direction"] == "🟢 LONG":
            sl = sr["support"] * 0.995
            tp1 = price + move * 2
            tp2 = price + move * 3
        else:
            sl = sr["resistance"] * 1.005
            tp1 = price - move * 2
            tp2 = price - move * 3

        # =====================================
        # 📊 QUALITY TYPE FOR DISPLAY
        # =====================================

        if breakout["breakout"]:
            signal_type = "🚀 BREAKOUT"
        elif reversal["reversal"]:
            signal_type = f"🔄 REVERSAL ({reversal['pattern']})"
        elif money["status"] == "🐋 SMART ACCUMULATION":
            signal_type = "🐋 SMART MONEY"
        else:
            signal_type = "📈 MOMENTUM"

        return {

            "coin": symbol,
            "sector": sector,
            "direction": brain["direction"],
            "score": round(score),
            "quality": quality,
            "signal_type": signal_type,
            "entry_low": round(entry_low, 6),
            "entry_high": round(entry_high, 6),
            "sl": round(sl, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "money": money["status"],
            "liquidity": money["flow"],
            "pre_pump": pre["status"],
            "multi": multi,
            "trap": trap,
            "warning": warning,
            "adx": adx_value,
            "cci": cci_value

        }


    except Exception as e:

        print(
            "ANALYZE ERROR:",
            e
        )

        return None
        
# =====================================
# 🤖 TELEGRAM ENGINE v11.4
# =====================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
        """
🐋 AHAD AI v11.4 ONLINE 🚀

🧠 Smart Entry Engine ACTIVE
📊 ADX + CCI Indicators ACTIVE
🚀 Breakout Detector ACTIVE
🔄 Reversal Detector ACTIVE
🐋 Smart Money ACTIVE
🪤 Trap Detector ACTIVE

🎯 Goal:
High quality entries (Breakout / Reversal / Smart Money)

Send /scan
        """
    )



# =====================================
# 🔎 SMART SCANNER v11.4
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        """
🐋 AHAD AI v11.4 SCANNING...

📊 ADX + CCI Analysis
🚀 Hunting Breakouts
🔄 Finding Reversals
🐋 Tracking Smart Money

Please wait ⏳
        """
    )


    long_results = []


    all_symbols = get_symbols()

    symbols = top_flow_scanner(all_symbols)


    flow = sector_flow(
        all_symbols
    )


    hot_sector = flow["sector"]


    bot.send_message(
        message.chat.id,
        f"""
🔥 MARKET FLOW

🏦 Hot Sector:
{hot_sector}

🐋 Flow Power:
{flow['power']}
        """
    )


    # TOP FLOW PRIORITY

    if len(symbols) < 20:

        symbols = all_symbols


    bot.send_message(
        message.chat.id,
        f"💎 Smart Money Watchlist: {len(symbols)} coins"
    )



    for symbol in symbols:


        result = analyze(
            symbol,
            hot_sector
        )


        if result:


            if result["score"] > 100:

                result["score"] = 100



            if result["direction"] == "🟢 LONG":

                # تصفية أقوى: فقط Breakout أو Reversal أو Smart Money مع سكور عالي
                if (
                    result["score"] >= 70
                    and (
                        "BREAKOUT" in result["signal_type"]
                        or "REVERSAL" in result["signal_type"]
                        or result["money"] == "🐋 SMART ACCUMULATION"
                    )
                ):

                    long_results.append(result)



        time.sleep(
            0.03
        )


    # =====================================
    # 📊 SORT: Breakout → Reversal → Smart Money → Score
    # =====================================

    def sort_key(x):
        priority = 0
        if "BREAKOUT" in x["signal_type"]:
            priority = 100
        elif "REVERSAL" in x["signal_type"]:
            priority = 80
        elif x["money"] == "🐋 SMART ACCUMULATION":
            priority = 60
        return (priority, x["score"], x["liquidity"])

    results = sorted(
        long_results,
        key=sort_key,
        reverse=True
    )[:3]


    if not results:


        bot.send_message(
            message.chat.id,
            """
👀 No strong setups now

🚀 No Breakouts detected
🔄 No Reversals found
🐋 Smart Money not ready
⏳ Try again later
            """
        )


        return



    for s in results:


        msg = f"""
🚨 AHAD AI v11.4 🐋

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

{s['quality']}
📊 Type: {s['signal_type']}

🔥 Score: {s['score']}/100 | 💧Flow: {s['liquidity']}X
📊 ADX: {s['adx']} | CCI: {s['cci']}
🐋 Money: {s['money']}
🪤 Trap: {s['trap']}

🎯 Entry: {round(s['entry_low'],6)} - {round(s['entry_high'],6)}
🛑 SL: {round(s['sl'],6)}

🥇 TP1: {round(s['tp1'],6)}
🥈 TP2: {round(s['tp2'],6)}

📊 RSI:
15m:{s['multi']['15m']} | 1H:{s['multi']['1h']}
4H:{s['multi']['4h']} | 1D:{s['multi']['1d']}

⚠️ {s['warning']}

🧠 AHAD: HIGH QUALITY 🚀
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

            print(
                "KEEP ALIVE ERROR:",
                e
            )


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
    "🔥 AHAD AI v11.4 SMART ENTRY ONLINE 🐋"
)



while True:

    time.sleep(
        60
    )
