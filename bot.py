import os
import time
import telebot
import requests
import pandas as pd
from flask import Flask
from threading import Thread
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange


# ======================
# AHAD AI v5.7 FIXED
# ======================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


@app.route("/")
def home():
    return "🚀 AHAD AI v5.7 ONLINE"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


def keep_alive():
    Thread(target=run_web).start()



# ======================
# DATA ENGINE
# ======================

def get_data(symbol):

    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": "15m",
        "limit": 120
    }

    try:

        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()

        df = pd.DataFrame(
            data,
            columns=[
                "time","open","high",
                "low","close","volume",
                "x1","x2","x3",
                "x4","x5","x6"
            ]
        )

        df = df[
            [
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        ]

        return df.astype(float)

    except Exception as e:

        print(e)

        return None



# ======================
# SMART ANALYSIS
# ======================

def analyze(symbol):

    df = get_data(symbol)

    if df is None:
        return None


    close = df["close"]

    price = close.iloc[-1]


    rsi = RSIIndicator(
        close
    ).rsi().iloc[-1]


    ema = EMAIndicator(
        close,
        window=50
    ).ema_indicator().iloc[-1]


    macd = MACD(close)

    macd_power = (
        macd.macd().iloc[-1]
        -
        macd.macd_signal().iloc[-1]
    )


    atr = AverageTrueRange(
        df["high"],
        df["low"],
        df["close"]
    ).average_true_range().iloc[-1]


    volume_now = df["volume"].iloc[-1]

    volume_avg = df["volume"].tail(30).mean()


    score = 0


    if price > ema:
        score += 30


    if 40 <= rsi <= 65:
        score += 25


    if macd_power > 0:
        score += 20


    whale = volume_now / volume_avg


    if whale > 1.2:
        score += 25


    if score < 75:
        return None


    stop = price - (atr * 1.5)

    risk = price - stop


    return {

        "coin": symbol,
        "entry": price,
        "sl": stop,
        "tp1": price + risk * 2,
        "tp2": price + risk * 3,
        "rsi": rsi,
        "score": score,
        "whale": whale

    }



# ======================
# TELEGRAM
# ======================


@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v5.7 ONLINE

🐋 Whale Engine ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Stop Loss ACTIVE

Send /scan
"""
    )



@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔍 Searching sniper setups..."
    )


    coins = [

        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT"

    ]


    found = []


    for c in coins:

        x = analyze(c)

        if x:
            found.append(x)



    if not found:

        bot.send_message(
            message.chat.id,
            "😴 No sniper LONG setup now 🛡"
        )

        return



    for s in found:

        bot.send_message(
            message.chat.id,
f"""
🟢 AHAD LONG SIGNAL

🪙 {s['coin']}

🎯 Entry:
{round(s['entry'],5)}

🛑 Stop Loss:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

📊 RSI:
{round(s['rsi'],2)}

🐋 Whale:
{round(s['whale'],2)}X

🔥 SCORE:
{s['score']}/100
"""
        )



# ======================
# START
# ======================


def telegram():

    while True:

        try:

            bot.infinity_polling(
                skip_pending=True
            )

        except Exception as e:

            print(e)

            time.sleep(5)



print("🚀 AHAD AI v5.7 STARTING")


keep_alive()


Thread(
    target=telegram
).start()
