import os
import threading
import time
import requests
import pandas as pd
import ta
import telebot

from flask import Flask


# ==========================
# AHAD AI v4.0
# ==========================


TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)


# ==========================
# RENDER KEEP ALIVE
# ==========================


app = Flask(__name__)


@app.route("/")
def home():
    return "🚀 AHAD AI v4.0 ONLINE"


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


threading.Thread(
    target=run_web
).start()



# ==========================
# GET FUTURES SYMBOLS
# ==========================


def get_symbols():

    url = (
        "https://fapi.binance.com"
        "/fapi/v1/exchangeInfo"
    )

    data = requests.get(
        url,
        timeout=10
    ).json()


    symbols = []


    if "symbols" not in data:
        return symbols


    for s in data["symbols"]:

        if (
            s.get("quoteAsset") == "USDT"
            and
            s.get("status") == "TRADING"
        ):

            symbols.append(
                s["symbol"]
            )


    return symbols



# ==========================
# GET CANDLES
# ==========================


def get_chart(symbol):

    url = (
        "https://fapi.binance.com"
        "/fapi/v1/klines"
    )


    params = {
        "symbol": symbol,
        "interval": "15m",
        "limit": 200
    }


    data = requests.get(
        url,
        params=params,
        timeout=10
    ).json()


    if not isinstance(data, list):
        return None


    df = pd.DataFrame(data)


    df["close"] = df[4].astype(float)

    df["volume"] = df[5].astype(float)


    return df



# ==========================
# ANALYSIS ENGINE
# ==========================


def analyze(symbol):

    try:

        df = get_chart(symbol)


        if df is None:
            return None


        df["EMA50"] = (
            ta.trend
            .ema_indicator(
                df["close"],
                window=50
            )
        )


        df["EMA200"] = (
            ta.trend
            .ema_indicator(
                df["close"],
                window=200
            )
        )


        df["RSI"] = (
            ta.momentum
            .rsi(
                df["close"],
                window=14
            )
        )


        last = df.iloc[-1]


        score = 0


        reasons = []


        # TREND

        if (
            last["close"]
            >
            last["EMA50"]
        ):

            score += 30

            reasons.append(
                "EMA50 Bullish"
            )


        if (
            last["EMA50"]
            >
            last["EMA200"]
        ):

            score += 30

            reasons.append(
                "Trend UP"
            )


        # RSI

        if (
            last["RSI"] > 40
            and
            last["RSI"] < 65
        ):

            score += 20

            reasons.append(
                "RSI Healthy"
            )


        # VOLUME

        avg_volume = (
            df["volume"]
            .tail(30)
            .mean()
        )


        if (
            last["volume"]
            >
            avg_volume * 1.5
        ):

            score += 20

            reasons.append(
                "Volume Spike"
            )


        if score >= 70:

            return {

                "symbol": symbol,

                "price":
                round(
                    last["close"],
                    5
                ),

                "rsi":
                round(
                    last["RSI"],
                    2
                ),

                "score": score,

                "reasons": reasons
            }


    except:

        return None



# ==========================
# TELEGRAM
# ==========================


@bot.message_handler(
    commands=["start"]
)

def start(message):

    bot.reply_to(
        message,
        """
🚀 AHAD AI v4.0 ONLINE

🧠 Futures Quant Engine ACTIVE

⏱ Timeframe: 15M

Send /scan
"""
    )



@bot.message_handler(
    commands=["scan"]
)

def scan(message):


    bot.reply_to(
        message,
        "🔎 AHAD AI scanning market..."
    )


    results = []


    symbols = get_symbols()


    for symbol in symbols[:100]:

        signal = analyze(symbol)


        if signal:

            results.append(signal)


        time.sleep(0.05)



    results = sorted(
        results,
        key=lambda x:
        x["score"],
        reverse=True
    )[:3]



    if not results:

        bot.send_message(
            message.chat.id,
            "😴 No strong LONG signals now"
        )

        return



    text = (
        "🔥 AHAD AI TOP 3 LONG\n\n"
    )



    for r in results:


        text += f"""

🚀 {r['symbol']}

💰 Entry:
{r['price']}

📊 RSI:
{r['rsi']}

🧠 Strength:
{r['score']}%

🎯 TP1: +3%
🎯 TP2: +6%

🛑 SL: -2%

------------------

"""


    bot.send_message(
        message.chat.id,
        text
    )



# ==========================
# START
# ==========================


print(
    "🚀 AHAD AI v4.0 Started"
)


bot.remove_webhook()


bot.infinity_polling(
    skip_pending=True
)
