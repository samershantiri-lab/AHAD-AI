# =====================================
# 🚀 AHAD AI v9.5 FINAL CLEAN
# PART 1 - CORE + OKX DATA
# =====================================

import os
import time
import threading
import traceback
import requests

from flask import Flask
import telebot


# =====================================
# 🔑 TELEGRAM
# =====================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise Exception("❌ BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)


# =====================================
# 🌐 RENDER SERVER
# =====================================

app = Flask(__name__)


@app.route("/")
def home():

    return "🐋 AHAD AI v9.5 ONLINE"


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
# ⬛ OKX CRYPTO SYMBOLS ONLY
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

            "TSLA",
            "AMZN",
            "AAPL",
            "NVDA",
            "META",
            "GOOGL",
            "MSFT",
            "NFLX"

        ]


        result = []


        for x in data["data"]:


            symbol = x["instId"]


            if (
                x["settleCcy"] == "USDT"
                and
                x["state"] == "live"
                and
                not any(
                    b in symbol
                    for b in blocked
                )
            ):

                result.append(symbol)



        print(
            "🐋 CRYPTO MARKETS:",
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
# 🕯 OKX CANDLES
# =====================================

def get_candles(symbol, tf):

    try:

        frames = {

            "15m": "15m",

            "1h": "1H"

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



# =====================================
# 📊 INDICATORS (NO LIBRARIES)
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
            result * (1-k)
        )


    return result



def rsi(values, period=14):

    gains = 0

    losses = 0


    for i in range(
        -period,
        -1
    ):


        diff = (
            values[i+1]
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
        100/(1+rs)
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



print(
    "🚀 AHAD AI v9.5 CORE READY 🐋"
)

# =====================================
# 🧱 SUPPORT / RESISTANCE ENGINE
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

        "near_support": (
            (price - support)
            /
            price
        ) * 100,

        "near_resistance": (
            (resistance - price)
            /
            price
        ) * 100

    }



# =====================================
# 🛡 ANTI FOMO ENGINE v9.6
# Catch move BEFORE explosion
# =====================================

def fomo_filter(candles):

    try:

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


        # آخر 24 ساعة تقريبا على 15m
        old_price = closes[-96]


        move_24h = (
            (price - old_price)
            /
            old_price
        ) * 100


        current_rsi = rsi(
            closes
        )


        support = min(
            lows[-80:]
        )


        distance_support = (
            (price - support)
            /
            price
        ) * 100


        # ==========================
        # 🚫 LONG TOO LATE
        # ==========================

        if (
            move_24h > 12
            and
            distance_support > 4
        ):

            return (
                False,
                "🚫 PUMPED - WAIT RETEST"
            )


        # ==========================
        # 🚫 RSI OVERHEAT
        # ==========================

        if current_rsi > 75:

            return (
                False,
                "🚫 RSI HOT - WAIT COOL"
            )


        # ==========================
        # 🚫 HUGE CANDLE
        # ==========================

        candle = (
            highs[-1]
            -
            lows[-1]
        )


        avg_candle = sum(
            [
                highs[i] - lows[i]
                for i in range(-30, -1)
            ]
        ) / 29


        if candle > avg_candle * 2.5:

            return (
                False,
                "🚫 BIG MOVE WAIT"
            )


        return (
            True,
            "🐋 EARLY AREA"
        )


    except Exception as e:

        print(
            "FOMO ERROR:",
            e
        )

        return (
            False,
            "FILTER ERROR"
        )



# =====================================
# 🐋 WHALE ACCUMULATION ENGINE v9.6
# Detect accumulation vs exit
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

            flow = 0

        else:

            flow = volume_now / volume_avg


        # حركة آخر 24 شمعة
        old_price = closes[-24]


        move = (
            (price - old_price)
            /
            old_price
        ) * 100


        # حركة السعر آخر 5 شمعات
        short_move = (
            (closes[-1] - closes[-5])
            /
            closes[-5]
        ) * 100


        # =====================
        # 🐋 TRUE ACCUMULATION
        # =====================

        if (
            flow >= 1.5
            and
            abs(move) < 8
            and
            abs(short_move) < 4
        ):

            status = "🐋 SMART ACCUMULATION"


        # =====================
        # 🚨 WHALE EXIT
        # =====================

        elif (
            flow >= 1.5
            and
            move > 8
        ):

            status = "🚨 WHALE DISTRIBUTION"


        else:

            status = "NORMAL"



        return {

            "flow": round(flow,2),

            "status": status

        }


    except Exception as e:

        print(
            "SMART MONEY ERROR:",
            e
        )

        return {

            "flow":0,

            "status":"ERROR"

        }



# =====================================
# 🧠 LORENTZIAN STYLE AI
# =====================================

def ai_brain(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    price = closes[-1]


    ema20 = ema(
        closes,
        20
    )


    ema50 = ema(
        closes,
        50
    )


    r = rsi(
        closes
    )


    score = 0


    if price > ema20:

        score += 30

    else:

        score -= 30



    if ema20 > ema50:

        score += 30

    else:

        score -= 30



    if r > 55:

        score += 20


    elif r < 45:

        score -= 20



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
# 🧠 FINAL ANALYZE ENGINE
# =====================================

def analyze(symbol):

    try:

        c15 = get_candles(symbol, "15m")
        c1h = get_candles(symbol, "1h")


        if len(c15) < 60 or len(c1h) < 60:

            return None



        price = c15[-1]["close"]


        sr = support_resistance(c15)

        safe, warning = fomo_filter(c15)

        money = smart_money(c15)

        brain = ai_brain(c1h)



        if brain["direction"] == "WAIT":

            return None



        # منع LONG قريب من المقاومة
        if (
            brain["direction"] == "🟢 LONG"
            and
            sr["near_resistance"] < 2
        ):

            return None



        score = brain["confidence"]



        if money["status"] == "🐋 SMART ACCUMULATION":

            score += 20



        if safe:

            score += 20



        if (
            brain["direction"] == "🟢 LONG"
            and
            sr["near_support"] < 3
        ):

            score += 20



        if (
            brain["direction"] == "🔴 SHORT"
            and
            sr["near_resistance"] < 3
        ):

            score += 20



        move = atr(c15)



        if brain["direction"] == "🟢 LONG":

            sl = sr["support"] * 0.995

            tp1 = price + move * 2

            tp2 = price + move * 3


        else:

            sl = sr["resistance"] * 1.005

            tp1 = price - move * 2

            tp2 = price - move * 3



        if not safe:

            status = "⏳ WAIT RETEST"


        elif (
            score >= 90
            and
            money["flow"] >= 1.5
            and
            money["status"] == "🐋 SMART ACCUMULATION"
        ):

            status = "🚀 SNIPER"


        else:

            status = "👀 WATCH"



        return {

            "coin": symbol,

            "direction": brain["direction"],

            "score": round(score),

            "entry": price,

            "sl": sl,

            "tp1": tp1,

            "tp2": tp2,

            "support": sr["support"],

            "resistance": sr["resistance"],

            "liquidity": money["flow"],

            "money": money["status"],

            "status": status,

            "warning": warning

        }



    except Exception as e:

        print(
            "ANALYZE ERROR:",
            symbol,
            e
        )

        return None



# =====================================
# 🤖 TELEGRAM
# =====================================


@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI v9.5 ONLINE\n\n"
        "🧠 AI Brain ACTIVE\n"
        "🐋 Smart Money ACTIVE\n"
        "📍 Support Resistance ACTIVE\n\n"
        "Send /scan"
    )



# =====================================
# 🔎 SCANNER
# BEST 2 LONG + BEST 1 SHORT
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI v9.5 SCANNING...\n\n"
        "🟢 Hunting LONG setups\n"
        "🔴 Hunting SHORT setups\n"
        "🧠 AI Brain running..."
    )


    long_results = []

    short_results = []


    symbols = get_symbols()


    bot.send_message(
        message.chat.id,
        f"🐋 Crypto Markets: {len(symbols)}"
    )


    for symbol in symbols:


        result = analyze(symbol)


        if result:


            # 🔥 MAX SCORE 100
            if result["score"] > 100:

                result["score"] = 100



            if (
                result["score"] >= 70
                and
                result["liquidity"] >= 1.3
            ):


                if result["direction"] == "🟢 LONG":

                    long_results.append(result)


                elif result["direction"] == "🔴 SHORT":

                    short_results.append(result)



        time.sleep(0.03)



    best_long = sorted(

        long_results,

        key=lambda x: x["score"],

        reverse=True

    )[:2]



    best_short = sorted(

        short_results,

        key=lambda x: x["score"],

        reverse=True

    )[:1]



    results = best_long + best_short



    if not results:

        bot.send_message(

            message.chat.id,

            "👀 No clean crypto setup now\n⏳ Waiting smart money..."

        )

        return



    for s in results:


        msg = f"""
🚨 AHAD AI v9.5 🐋

{s['direction']}
🪙 {s['coin']}

🔥 Score: {s['score']}/100

🐋 Flow: {s['liquidity']}X
🧲 {s['money']}

📍 Support:
{round(s['support'],6)}

🚧 Resistance:
{round(s['resistance'],6)}

🎯 Entry:
{round(s['entry'],6)}

🛑 SL:
{round(s['sl'],6)}

🥇 TP1:
{round(s['tp1'],6)}

🥈 TP2:
{round(s['tp2'],6)}

🧠 {s['status']}

⚠️ {s['warning']}
"""


        bot.send_message(
            message.chat.id,
            msg
        )



# =====================================
# 🚀 START SYSTEM
# =====================================


def telegram_engine():

    while True:

        try:

            bot.infinity_polling(
                skip_pending=True
            )


        except Exception:

            print(
                traceback.format_exc()
            )

            time.sleep(5)



threading.Thread(
    target=run_web,
    daemon=True
).start()



threading.Thread(
    target=telegram_engine,
    daemon=True
).start()



print(
    "🔥 AHAD AI v9.5 FULL ONLINE 🐋"
)



while True:

    time.sleep(60)
