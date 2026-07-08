# =====================================
# 🚀 AHAD AI v9.4 FINAL CLEAN
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

    return "🐋 AHAD AI v9.4 ONLINE"


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
# ⬛ OKX SYMBOLS
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


        result = []


        for x in data["data"]:


            if (
                x["settleCcy"] == "USDT"
                and
                x["state"] == "live"
            ):

                result.append(
                    x["instId"]
                )


        print(
            "⬛ OKX:",
            len(result)
        )


        return result



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

            "1h": "1H"

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
    "🚀 AHAD AI v9.4 CORE READY 🐋"
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
# 🛡 FOMO KILLER
# =====================================

def fomo_filter(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    price = closes[-1]


    old = closes[-8]


    pump = (
        (price - old)
        /
        old
    ) * 100


    r = rsi(closes)


    if pump > 5:

        return False, "⏳ WAIT RETEST (PUMPED)"


    if r > 72:

        return False, "⏳ WAIT RSI COOL"


    return True, "✅ EARLY AREA"



# =====================================
# 🐋 SMART MONEY FLOW
# =====================================

def smart_money(candles):

    volumes = [
        x["volume"]
        for x in candles
    ]


    now = sum(
        volumes[-5:]
    )


    avg = (
        sum(
            volumes[-30:]
        )
        /
        6
    )


    if avg == 0:

        flow = 0


    else:

        flow = now / avg



    closes = [
        x["close"]
        for x in candles
    ]


    move = (
        (
            closes[-1]
            -
            closes[-10]
        )
        /
        closes[-10]
    ) * 100



    if (
        flow >= 1.5
        and
        abs(move) < 5
    ):

        status = "🐋 WHALES LOADING"


    elif (
        flow >= 1.5
        and
        move > 5
    ):

        status = "⚠️ POSSIBLE EXIT"


    else:

        status = "NORMAL"



    return {

        "flow": round(flow,2),

        "status": status

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



        score = brain["confidence"]



        if money["status"] == "🐋 WHALES LOADING":

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


        elif score >= 90:

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
        "🐋 AHAD AI v9.4 ONLINE\n\n"
        "🧠 AI Brain ACTIVE\n"
        "🐋 Smart Money ACTIVE\n"
        "📍 Support Resistance ACTIVE\n\n"
        "Send /scan"
    )



@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 Scanning OKX...\n"
        "Searching early liquidity ⏳"
    )


    results = []


    symbols = get_symbols()


    bot.send_message(
        message.chat.id,
        f"⬛ Markets: {len(symbols)}"
    )



    for symbol in symbols:

        result = analyze(symbol)


        if result and result["score"] >= 70:

            results.append(result)


        time.sleep(0.03)



    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )[:3]



    if not results:

        bot.send_message(
            message.chat.id,
            "👀 No clean setup now"
        )

        return



    for s in results:


        msg = (
f"""🚨 AHAD AI v9.4 🐋

{s['direction']} | {s['coin']}

🔥 Score: {s['score']}

🐋 Flow: {s['liquidity']}X
🧲 {s['money']}

📍 Support: {round(s['support'],6)}
🚧 Resistance: {round(s['resistance'],6)}

🎯 Entry: {round(s['entry'],6)}
🛑 SL: {round(s['sl'],6)}

🥇 TP1: {round(s['tp1'],6)}
🥈 TP2: {round(s['tp2'],6)}

🧠 {s['status']}
⚠️ {s['warning']}
"""
        )


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
    "🔥 AHAD AI v9.4 FULL ONLINE 🐋"
)



while True:

    time.sleep(60)
