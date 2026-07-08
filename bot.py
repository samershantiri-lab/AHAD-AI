# =====================================
# 🚀 AHAD AI v9.1 CLEAN BUILD
# PART 1 - OKX CORE
# =====================================

import os
import time
import threading
import traceback
import requests

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
# 🌐 RENDER KEEP ALIVE
# =====================================

app = Flask(__name__)


@app.route("/")
def home():

    return "🐋 AHAD AI v9.1 ONLINE"


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
# ⬛ OKX MARKET LIST
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


        symbols = []


        for coin in data["data"]:

            if (
                coin.get("settleCcy") == "USDT"
                and
                coin.get("state") == "live"
            ):

                symbols.append(
                    coin["instId"]
                )


        print(
            "⬛ OKX MARKETS:",
            len(symbols)
        )


        return symbols


    except Exception as e:

        print(
            "OKX SYMBOL ERROR:",
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

            "1h": "1H",

            "4h": "4H"

        }


        url = (
            "https://www.okx.com"
            "/api/v5/market/candles"
        )


        params = {

            "instId": symbol,

            "bar": frames[tf],

            "limit": 100

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        candles = data["data"]


        result = []


        for c in candles[::-1]:

            result.append({

                "open": float(c[1]),

                "high": float(c[2]),

                "low": float(c[3]),

                "close": float(c[4]),

                "volume": float(c[5])

            })


        return result


    except Exception as e:

        print(
            "CANDLE ERROR:",
            symbol,
            e
        )

        return []



# =====================================
# 📊 INDICATORS ENGINE
# =====================================

def ema(values, period):

    if len(values) < period:

        return values[-1]


    k = 2 / (period + 1)

    result = values[0]


    for price in values:

        result = (
            price * k
            +
            result * (1-k)
        )


    return result



def rsi(values, period=14):

    if len(values) < period + 1:

        return 50


    gains = 0

    losses = 0


    recent = values[-period:]


    for i in range(1, len(recent)):

        diff = (
            recent[i]
            -
            recent[i-1]
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
        (
            100 /
            (1 + rs)
        )
    )



def atr(candles, period=14):

    if len(candles) < period:

        return 0


    ranges = []


    for c in candles[-period:]:

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
    "🚀 AHAD AI v9.1 STARTING"
)

print(
    "⬛ OKX CORE ACTIVE"
)

# =====================================
# 🧠 AHAD AI v9.1
# PART 2 - LIQUIDITY BRAIN
# =====================================


def analyze(symbol):

    try:

        # =============================
        # LOAD DATA
        # =============================

        c15 = get_candles(symbol, "15m")
        c1h = get_candles(symbol, "1h")
        c4h = get_candles(symbol, "4h")


        if (
            len(c15) < 30
            or
            len(c1h) < 30
        ):

            return None



        closes15 = [
            x["close"]
            for x in c15
        ]


        closes1h = [
            x["close"]
            for x in c1h
        ]


        price = closes15[-1]



        # =============================
        # TREND ENGINE
        # =============================

        ema20 = ema(
            closes1h,
            20
        )


        ema50 = ema(
            closes1h,
            50
        )


        trend = 0


        if price > ema20:

            trend += 20


        if ema20 > ema50:

            trend += 20



        # =============================
        # MOMENTUM
        # =============================

        rsi_value = rsi(
            closes15
        )


        momentum = 0


        if 35 <= rsi_value <= 70:

            momentum += 20



        # =============================
        # 🐋 LIQUIDITY FLOW
        # =============================

        recent_volume = sum(

            [
                x["volume"]
                for x in c15[-5:]
            ]

        )


        old_volume = sum(

            [
                x["volume"]
                for x in c15[-30:]
            ]

        ) / 6



        if old_volume > 0:

            liquidity = (

                recent_volume
                /
                old_volume

            )

        else:

            liquidity = 0



        liquidity_score = 0


        if liquidity >= 1.5:

            liquidity_score = 30



        # =============================
        # 🐋 WHALE ACCUMULATION
        # =============================

        price_change = (

            (
                price
                -
                closes15[-10]
            )

            /
            closes15[-10]

        ) * 100



        whale = "NORMAL"


        if (

            liquidity >= 1.5

            and

            abs(price_change) < 3

        ):


            whale = "WHALES LOADING 🐋"



        # =============================
        # LONG / SHORT DECISION
        # =============================

        direction = "WAIT"


        if (

            trend >= 20

            and

            liquidity >= 1.2

            and

            rsi_value < 75

        ):


            direction = "🟢 LONG"



        elif (

            trend == 0

            and

            liquidity >= 1.2

            and

            rsi_value > 40

        ):


            direction = "🔴 SHORT"



        # =============================
        # FINAL SCORE
        # =============================

        score = (

            trend

            +

            momentum

            +

            liquidity_score

        )



        # =============================
        # TARGETS
        # =============================

        risk = atr(c15) * 1.5


        if direction == "🔴 SHORT":

            sl = price + risk

            tp1 = price - risk * 2

            tp2 = price - risk * 3


        else:

            sl = price - risk

            tp1 = price + risk * 2

            tp2 = price + risk * 3



        return {


            "coin": symbol,


            "direction": direction,


            "score": round(score),


            "entry": price,


            "sl": sl,


            "tp1": tp1,


            "tp2": tp2,


            "rsi": rsi_value,


            "liquidity": liquidity,


            "whale": whale


        }



    except Exception as e:


        print(
            "AI ERROR:",
            symbol,
            e
        )


        return None

# =====================================
# 🤖 AHAD AI v9.1
# PART 3 - TELEGRAM SCANNER
# =====================================


@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v9.1 ONLINE 🐋

⬛ OKX DATA CORE

🧠 AI Liquidity Brain
🐋 Whale Flow Detector
🟢 LONG Hunter
🔴 SHORT Hunter

🎯 Goal:
Catch the move BEFORE it happens

Send /scan
"""
    )



# =====================================
# 🔍 SCAN COMMAND
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v9.1 SCANNING...

⬛ Reading OKX Liquidity
🧠 Tracking Smart Money
🐋 Searching Whale Flow...

Please wait...
"""
    )


    results = []


    symbols = get_symbols()


    bot.send_message(
        message.chat.id,
        f"⬛ OKX Markets: {len(symbols)}"
    )



    for symbol in symbols[:250]:

        try:

            result = analyze(
                symbol
            )


            if (
                result
                and
                result["direction"] != "WAIT"
            ):

                results.append(
                    result
                )


            time.sleep(
                0.02
            )


        except Exception as e:

            print(
                "SCAN ERROR:",
                symbol,
                e
            )



    # =============================
    # SORT BEST LIQUIDITY
    # =============================

    results = sorted(

        results,

        key=lambda x: (

            x["score"],

            x["liquidity"]

        ),

        reverse=True

    )



    top = results[:3]



    if not top:


        bot.send_message(
            message.chat.id,
            """
👀 AHAD AI RADAR

No strong move loading now 🛡

Market checked successfully
"""
        )

        return



    for s in top:


        bot.send_message(

            message.chat.id,

f"""
🚨 AHAD AI v9.1 SIGNAL 🐋


{s['direction']}

🪙 COIN:
{s['coin']}


🔥 AI SCORE:
{s['score']}/90


🐋 LIQUIDITY FLOW:
{round(s['liquidity'],2)}X


🧲 SMART MONEY:
{s['whale']}


🎯 ENTRY:
{round(s['entry'],6)}


🛑 STOP:
{round(s['sl'],6)}


🎯 TP1:
{round(s['tp1'],6)}


🎯 TP2:
{round(s['tp2'],6)}


📊 RSI:
{round(s['rsi'],2)}
"""

        )



# =====================================
# 🛡 AUTO RECOVERY
# =====================================

def telegram_engine():


    while True:


        try:


            print(
                "🤖 TELEGRAM ACTIVE"
            )


            bot.infinity_polling(

                skip_pending=True,

                timeout=60

            )


        except Exception:


            print(

                traceback.format_exc()

            )


            print(

                "🔄 Restart Telegram"

            )


            time.sleep(5)




# =====================================
# 🚀 START SYSTEM
# =====================================


threading.Thread(

    target=run_web,

    daemon=True

).start()



threading.Thread(

    target=telegram_engine,

    daemon=True

).start()



print(
    "🔥 AHAD AI v9.1 LIQUIDITY HUNTER ONLINE 🐋"
)



while True:

    time.sleep(60)
