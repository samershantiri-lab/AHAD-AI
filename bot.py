# =====================================
# 🚀 AHAD AI v11.3.3
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
        "🐋 AHAD AI v11.3.3 "
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
# 🏦 SECTOR DATABASE v11.3.3
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
    "🔥 AHAD AI v11.3.3 CORE READY 🐋"
)

# =====================================
# 📊 INDICATORS ENGINE v11.3.3
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
# 🏦 SECTOR FLOW ENGINE v11.3.3
# =====================================

def sector_flow(symbols):

    try:

        result = {}


        for sector, coins in SECTORS.items():

            power = 0


            for symbol in symbols:


                if any(
                    coin in symbol
                    for coin in coins
                ):

                    candles = get_candles(
                        symbol,
                        "1h"
                    )


                    if len(candles) > 50:


                        volumes = [
                            x["volume"]
                            for x in candles
                        ]


                        recent = sum(
                            volumes[-5:]
                        )


                        average = (
                            sum(
                                volumes[-50:]
                            )
                            /
                            10
                        )


                        if average > 0:

                            power += (
                                recent
                                /
                                average
                            )


            result[sector] = round(
                power,
                2
            )



        hot_sector = max(
            result,
            key=result.get
        )


        return {

            "sector": hot_sector,

            "power": result[hot_sector]

        }



    except Exception as e:

        print(
            "SECTOR ERROR:",
            e
        )


        return {

            "sector": "UNKNOWN",

            "power": 0

        }



# =====================================
# 🐋 SMART MONEY ENGINE v11.3.3
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
# 🐋 PRE PUMP ACCUMULATION ENGINE v11.3.3
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
# 📊 MULTI TIMEFRAME ENGINE v11.3.3
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
# 🛡 ANTI LATE ENTRY v11.3.3
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
# 🪤 TRAP DETECTOR v11.3.3
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
# 🧠 AI BRAIN ENGINE v11.3.3
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
# 📊 MACD INDICATOR v11.3.3
# =====================================

def macd(closes, fast=12, slow=26, signal=9):
    """
    حساب MACD و Histogram
    """
    try:
        if len(closes) < slow:
            return {"macd": 0, "signal": 0, "histogram": 0}
        
        # EMA Fast
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        
        macd_line = ema_fast - ema_slow
        
        # MACD Signal
        macd_signal = ema([macd_line], signal)
        
        histogram = macd_line - macd_signal
        
        return {
            "macd": macd_line,
            "signal": macd_signal,
            "histogram": histogram
        }
    except:
        return {"macd": 0, "signal": 0, "histogram": 0}


# =====================================
# 🔍 FAKE PUMP DETECTOR v11.3.3
# =====================================

def fake_pump_detector(candles):
    """
    اكتشاف الفخاخ السعرية:
    - شمعة كبيرة
    - حجم تداول ضخم
    - الشمعة التالية أغلقت أسفل منتصف الأولى
    """
    try:
        if len(candles) < 3:
            return {"is_fake": False, "trap": False}
        
        c1 = candles[-3]  # شمعة كبيرة محتملة
        c2 = candles[-2]  # الشمعة التالية
        c3 = candles[-1]  # الشمعة الحالية
        
        # حجم الشمعة الأولى
        body1 = abs(c1["close"] - c1["open"])
        avg_body = sum([abs(c["close"] - c["open"]) for c in candles[-20:]]) / 20
        
        # متوسط الحجم
        avg_volume = sum([c["volume"] for c in candles[-20:]]) / 20
        
        # شمعة كبيرة + حجم ضخم
        if body1 > avg_body * 2 and c1["volume"] > avg_volume * 2:
            mid = (c1["high"] + c1["low"]) / 2
            # الشمعة التالية أغلقت أسفل المنتصف
            if c2["close"] < mid:
                return {"is_fake": True, "trap": True}
        
        return {"is_fake": False, "trap": False}
        
    except:
        return {"is_fake": False, "trap": False}


# =====================================
# 🚀 FINAL ANALYZE ENGINE v11.3.3
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


        safe, warning = fomo_filter(c15)


        if not safe:

            return None


        brain = ai_brain(c1h)


        if brain["direction"] == "WAIT":

            return None


        sr = support_resistance(c15)

        money = smart_money(c15)

        pre = pre_pump_engine(c15)

        multi = multi_rsi_engine(
            c15,
            c1h,
            c4h,
            c1d
        )

        trap = trap_detector(c15)

        fake = fake_pump_detector(c15)

        # =====================================
        # 📊 CLOSES FOR INDICATORS
        # =====================================

        closes15 = [x["close"] for x in c15]
        closes1h = [x["close"] for x in c1h]
        closes4h = [x["close"] for x in c4h]
        closes1d = [x["close"] for x in c1d]

        rsi_15m = rsi(closes15)
        rsi_1h = rsi(closes1h)
        rsi_4h = rsi(closes4h)
        rsi_1d = rsi(closes1d)

        macd_data = macd(closes15)

        flow = money["flow"]


        # =====================================
        # 🔥 SMART RSI v11.3.3
        # =====================================

        rsi_score = 0
        if 45 <= rsi_15m <= 62:
            rsi_score = 10
        elif 62 < rsi_15m <= 70:
            rsi_score = 5
            warning = "⚠️ RSI WARNING"
        elif rsi_15m > 70 or rsi_15m < 35:
            return None


        # =====================================
        # 💧 DYNAMIC FLOW v11.3.3
        # =====================================

        flow_score = 0
        if flow < 0.8:
            return None
        elif flow >= 1.8:
            flow_score = 10
            flow_status = "🚀 WHALE FLOW"
        elif flow >= 1.2:
            flow_score = 5
            flow_status = "💧 HEALTHY FLOW"
        else:
            flow_status = "NORMAL"


        # =====================================
        # 📈 MACD MOMENTUM CHECK v11.3.3
        # =====================================

        if macd_data["histogram"] > 0:
            macd_score = 5
        else:
            macd_score = 0

        # التحقق من الزخم (آخر 3 أعمدة)
        hist_list = []
        for i in range(1, 4):
            if len(closes15) > i:
                temp_macd = macd(closes15[:-i])
                hist_list.append(temp_macd["histogram"])

        if len(hist_list) >= 3:
            if not (hist_list[0] > hist_list[1] > hist_list[2]):
                return None


        # =====================================
        # 🔥 MULTI TIMEFRAME VALIDATOR v11.3.3
        # =====================================

        tf_score = 0
        tf_alignment = True

        # 15m اتجاه صاعد
        ema20_15 = ema(closes15, 20)
        if price > ema20_15:
            tf_score += 5
        else:
            tf_alignment = False

        # 1H اتجاه صاعد
        ema20_1h = ema(closes1h, 20)
        if closes1h[-1] > ema20_1h:
            tf_score += 5
        else:
            tf_alignment = False

        # 4H ليس هابطاً بقوة
        ema20_4h = ema(closes4h, 20)
        if closes4h[-1] < ema20_4h * 0.97:
            tf_score -= 15


        # =====================================
        # 🔥 STRONG CANDLE CHECK v11.3.3
        # =====================================

        candle_score = 0
        last_candle = c15[-1]
        body = abs(last_candle["close"] - last_candle["open"])
        avg_body = sum([abs(c["close"] - c["open"]) for c in c15[-20:]]) / 20

        # Bullish candle
        if last_candle["close"] > last_candle["open"] and body > avg_body * 1.2:
            candle_score += 5
        # Doji
        elif body < (last_candle["high"] - last_candle["low"]) * 0.1:
            candle_score -= 5


        # =====================================
        # 📊 BETTER ENTRY v11.3.3
        # =====================================

        move = atr(c15)
        ema50_15 = ema(closes15, 50)

        if price > ema50_15 + (move * 0.5):
            early_text = "⏳ WAIT RETEST"
            return None
        else:
            early_text = "🐋 EARLY ENTRY AREA"
            
    # =====================================
    # 🔥 SCORE SYSTEM v11.3.3
    # =====================================

    score = 0

    # 🧠 AI Brain
    score += brain["confidence"]

    # 📊 Multi Timeframe
    score += multi["score"]

    # 🐋 Smart Money
    if money["status"] == "🐋 SMART ACCUMULATION":
        score += 20

    # ⚡ Pre Pump
    score += pre["score"]

    # 📊 RSI Score
    score += rsi_score

    # 💧 Flow Score
    score += flow_score

    # 📈 MACD Score
    score += macd_score

    # 📊 Multi Timeframe Score
    score += tf_score

    # 🔥 Candle Score
    score += candle_score


    # =====================================
    # 🔥 LATE ENTRY FILTER v11.3.3
    # =====================================

    late_penalty = 0
    if rsi_15m >= 68:
        late_penalty += 20
    score -= late_penalty
    score = max(score, 0)


    # =====================================
    # 🔥 MOMENTUM FILTER v11.3.3
    # =====================================

    if len(c15) >= 6:
        pump = c15[-1]["close"] / c15[-6]["close"]
        if pump > 1.05:
            score -= 15


    # =====================================
    # 🔥 BULL TRAP PENALTY v11.3.3
    # =====================================

    if trap == "🪤 BULL TRAP":
        score -= 15


    # =====================================
    # 🔥 FAKE PUMP DETECTOR v11.3.3
    # =====================================

    if fake["trap"]:
        return None


    # =====================================
    # 🔥 HEAT CONTROL v11.3.3
    # =====================================

    if multi["4h"] > 70:
        score -= 15

    if multi["1d"] > 70:
        score -= 20

    if multi["15m"] > 75:
        score -= 10


    # =====================================
    # 🔥 RESISTANCE FILTER v11.3.3
    # =====================================

    if sr["near_resistance"] < 3:
        score -= 10


    # =====================================
    # ⭐ CONFIDENCE ENGINE v11.3.3
    # =====================================

    confidence = 50

    # توافق الفريمات
    if tf_alignment:
        confidence += 15

    # Flow
    if flow >= 1.2:
        confidence += 10

    # RSI صحي
    if 45 <= rsi_15m <= 62:
        confidence += 10

    # MACD إيجابي
    if macd_data["histogram"] > 0:
        confidence += 10

    # Trend صاعد
    if price > ema(closes15, 50):
        confidence += 5

    confidence = min(confidence, 100)

    # إذا كانت الثقة أقل من 80% → لا ترسل الإشارة
    if confidence < 80:
        return None


    # =====================================
    # ⭐ QUALITY LEVEL v11.3.3
    # =====================================

    if trap == "🪤 BULL TRAP":
        quality = "⭐⭐ WATCHLIST"
    elif score >= 95:
        quality = "⭐⭐⭐⭐⭐ ELITE"
    elif score >= 85:
        quality = "⭐⭐⭐⭐ STRONG"
    elif score >= 75:
        quality = "⭐⭐⭐ GOOD"
    elif score >= 65:
        quality = "⭐⭐ WATCHLIST"
    else:
        quality = "⭐ LOW"


    # =====================================
    # 🐋 MONEY STATUS v11.3.3
    # =====================================

    if flow >= 3:
        money_status = "🚀 WHALE BUYING"
    elif flow >= 2:
        money_status = "🐋 SMART ACCUMULATION"
    elif flow >= 1.2:
        money_status = "💧 HEALTHY FLOW"
    else:
        money_status = "NORMAL"


    # =====================================
    # 🎯 FINAL VALIDATOR v11.3.3
    # =====================================

    # جميع الشروط يجب أن تتحقق قبل إرسال الإشارة
    if not (
        brain["direction"] == "🟢 LONG"
        and flow >= 0.8
        and 35 <= rsi_15m <= 70
        and macd_data["histogram"] > 0
        and confidence >= 80
        and trap != "🪤 BULL TRAP"
        and not fake["trap"]
    ):
        return None


    # =====================================
    # 🎯 ENTRY ZONE & TARGETS
    # =====================================

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

    # التأكد من أن TP1 أكبر من أعلى نقطة دخول
    if tp1 <= entry_high:
        tp1 = entry_high + move * 0.8


    return {

        "coin": symbol,
        "sector": sector,
        "direction": brain["direction"],
        "score": round(score),
        "quality": quality,
        "confidence": confidence,
        "money_status": money_status,
        "early_text": early_text,
        "entry_low": round(entry_low, 6),
        "entry_high": round(entry_high, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "liquidity": flow,
        "pre_pump": pre["status"],
        "multi": multi,
        "trap": trap,
        "warning": warning,
        "rsi_15m": round(rsi_15m, 2),
        "macd_hist": round(macd_data["histogram"], 6)

    }


except Exception as e:

    print(
        "ANALYZE ERROR:",
        e
    )

    return None
# =====================================
# 🤖 TELEGRAM ENGINE v11.3.3
# =====================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
        """
🐋 AHAD AI v11.3.3 ONLINE 🚀

🧠 AI Brain ACTIVE
🐋 Smart Money ACTIVE
📊 Multi TimeFrame ACTIVE
🪤 Trap Detector ACTIVE
⚡ Pre-Pump Detection ACTIVE
🔥 Heat Control ACTIVE
🎯 Early Entry Filter ACTIVE
📈 MACD Validator ACTIVE
🔍 Fake Pump Detector ACTIVE
⭐ Confidence Engine ACTIVE

🎯 Goal:
Best 3 quality LONG setups

Send /scan
        """
    )



# =====================================
# 🔎 SMART SCANNER v11.3.3
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        """
🐋 AHAD AI v11.3.3 SCANNING...

🔍 Checking Market Flow
🏦 Finding Hot Sector
🟢 Hunting TOP 3 LONG setups
🐋 Tracking Smart Money
⚡ Detecting Pre-Pump
🔥 Heat Control ACTIVE
📈 MACD Validator ACTIVE
⭐ Confidence Engine ACTIVE

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

                if (
                    result["score"] >= 65
                    and
                    (
                        result["liquidity"] >= 1.2
                        or
                        result["pre_pump"] == "🐋 WHALE LOADING"
                    )
                ):

                    long_results.append(result)



        time.sleep(
            0.03
        )



    results = sorted(

        long_results,

        key=lambda x: (
            x["score"],
            x["liquidity"],
            x["confidence"]
        ),

        reverse=True

    )[:3]



    if not results:


        bot.send_message(
            message.chat.id,
            """
👀 No sniper setup now

🐋 Smart Money not ready
⏳ Waiting next liquidity wave
💡 Confidence < 80% signals ignored
            """
        )


        return



    for s in results:


        msg = f"""
🚨 AHAD AI v11.3.3 🐋

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

{s['quality']}
⭐ Confidence: {s['confidence']}%

🔥 Score: {s['score']}/100 | 💧Flow: {s['liquidity']}X
🐋 Money: {s['money_status']}
🪤 Trap: {s['trap']}
📊 RSI 15m: {s['rsi_15m']}
📈 MACD Hist: {s['macd_hist']}

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
    "🔥 AHAD AI v11.3.3 SMART ENTRY ONLINE 🐋"
)



while True:

    time.sleep(
        60
    )
