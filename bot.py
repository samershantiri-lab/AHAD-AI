import os
import telebot
import requests
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange


# =========================
# AHAD AI v5.7
# SMART MONEY EDITION
# =========================


TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


# =========================
# KEEP RENDER ONLINE
# =========================

@app.route("/")
def home():
    return "🚀 AHAD AI v5.7 SMART MONEY ONLINE"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


def keep_alive():
    t = Thread(target=run_web)
    t.start()


# =========================
# MARKET DATA
# =========================

def get_data(symbol):

    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": "15m",
        "limit": 120
    }

    try:
        r = requests.get(
            url,
            params=params,
            timeout=10
        )

        data = r.json()

        df = pd.DataFrame(
            data,
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "x1",
                "x2",
                "x3",
                "x4",
                "x5",
                "x6"
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

        df = df.astype(float)

        return df

    except:
        return None


# =========================
# INDICATORS ENGINE
# =========================

def analyze(symbol):

    df = get_data(symbol)

    if df is None:
        return None

    close = df["close"]

    rsi = RSIIndicator(close).rsi().iloc[-1]

    ema50 = EMAIndicator(
        close,
        window=50
    ).ema_indicator().iloc[-1]

    macd = MACD(close)

    macd_value = (
        macd.macd().iloc[-1]
        -
        macd.macd_signal().iloc[-1]
    )

    atr = AverageTrueRange(
        df["high"],
        df["low"],
        df["close"]
    ).average_true_range().iloc[-1]
price = close.iloc[-1]

    volume_now = df["volume"].iloc[-1]
    volume_avg = df["volume"].tail(30).mean()

    score = 0
    reasons = []


    # =================
    # TREND
    # =================

    if price > ema50:
        score += 25
        reasons.append("Trend Bullish ✅")


    # =================
    # RSI
    # =================

    if 40 <= rsi <= 65:
        score += 20
        reasons.append("RSI Healthy ✅")


    # =================
    # MACD
    # =================

    if macd_value > 0:
        score += 20
        reasons.append("MACD Positive ✅")


    # =================
    # WHALE VOLUME
    # =================

    whale_power = volume_now / volume_avg

    if whale_power >= 1.3:
        score += 25
        reasons.append("Whale Volume 🐋")


    # =================
    # SMART ENTRY ENGINE
    # =================

    entry = price

    stop_loss = (
        price -
        (atr * 1.5)
    )

    risk = (
        entry -
        stop_loss
    )


    tp1 = (
        entry +
        (risk * 2)
    )


    tp2 = (
        entry +
        (risk * 3)
    )


    if score < 75:
        return None


    return {

        "coin": symbol,

        "entry": entry,

        "sl": stop_loss,

        "tp1": tp1,

        "tp2": tp2,

        "score": score,

        "rsi": rsi,

        "whale": whale_power,

        "reasons": reasons

    }



# =========================
# SCANNER
# =========================

COINS = [

    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "SUIUSDT"

]


@bot.message_handler(
    commands=["start"]
)

def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v5.7 ONLINE

🧠 Smart Money Engine
🐋 Whale Detector
🎯 Smart Entry
🛑 ATR Stop Loss

Send /scan
"""
    )



@bot.message_handler(
    commands=["scan"]
)

def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI scanning..."
    )


    signals = []


    for coin in COINS:

        result = analyze(coin)


        if result:

            signals.append(result)



    signals = sorted(
        signals,
        key=lambda x:
        x["score"],
        reverse=True
    )[:3]



    if not signals:

        bot.send_message(
            message.chat.id,
            "😴 No sniper setup now 🛡"
        )

        return



    for s in signals:

        text = f"""

🐋 AHAD AI SIGNAL

🟢 LONG

🪙 Coin:
{s['coin']}

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

🔥 AHAD SCORE:
{s['score']}/100


{chr(10).join(s['reasons'])}

"""

        bot.send_message(
            message.chat.id,
            text
        )



# =========================
# START SYSTEM
# =========================


def telegram_engine():

    while True:

        try:

            print(
                "🤖 Telegram Engine Running"
            )

            bot.infinity_polling(
                skip_pending=True,
                timeout=60
            )


        except Exception as e:

            print(e)

            import time
            time.sleep(5)



print(
    "🚀 AHAD AI v5.7 STARTING"
)


keep_alive()


Thread(
    target=telegram_engine
).start()
