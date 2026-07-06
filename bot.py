import os
import telebot
import requests
import pandas as pd
import ta
from flask import Flask
import threading


# ========== WEB SERVER RENDER ==========

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 AHAD AI v2.0 is running"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web).start()


# ========== TELEGRAM BOT ==========

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "🚀 AHAD AI v2.0 QUANT ENGINE ONLINE\n\nSend /scan"
    )


# ========== INDICATORS ==========


def analyze(symbol):

    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval=15m&limit=100"
    )

    data = requests.get(url, timeout=10).json()

    df = pd.DataFrame(
        data,
        columns=[
            "time","open","high","low","close",
            "volume","x","x2","x3","x4","x5","x6"
        ]
    )

    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)


    # EMA

    df["ema50"] = ta.trend.ema_indicator(
        df["close"], window=50
    )

    df["ema200"] = ta.trend.ema_indicator(
        df["close"], window=100
    )


    # RSI

    rsi = ta.momentum.rsi(
        df["close"], window=14
    ).iloc[-1]


    # MACD

    macd = ta.trend.macd_diff(
        df["close"]
    ).iloc[-1]


    # VOLUME

    volume_now = df["volume"].iloc[-1]
    volume_avg = df["volume"].tail(20).mean()


    price = df["close"].iloc[-1]


    score = 0


    if price > df["ema50"].iloc[-1]:
        score += 25

    if price > df["ema200"].iloc[-1]:
        score += 20

    if 45 <= rsi <= 65:
        score += 20

    if macd > 0:
        score += 15

    if volume_now > volume_avg * 1.5:
        score += 20


    return {
        "coin": symbol,
        "price": price,
        "rsi": round(rsi,2),
        "score": score
    }



# ========== SCANNER ==========


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔍 AHAD AI v2.0 scanning market..."
    )

    try:

        coins_data = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            timeout=10
        ).json()


        results = []


        for c in coins_data:

            symbol = c["symbol"]

            if symbol.endswith("USDT"):

                try:

                    result = analyze(symbol)

                    if result["score"] >= 80:
                        results.append(result)

                except:
                    pass


        results = sorted(
            results,
            key=lambda x: x["score"],
            reverse=True
        )[:3]


        if not results:

            bot.reply_to(
                message,
                "😴 No strong LONG signals now"
            )

            return


        text = "🚀 AHAD AI TOP 3 LONG SIGNALS\n\n"


        for r in results:

            text += (
                f"🪙 COIN: {r['coin']}\n"
                f"🟢 TYPE: LONG\n\n"
                f"PRICE: {r['price']}\n"
                f"RSI: {r['rsi']} ✅\n"
                f"POWER: {r['score']}/100 🔥\n\n"
                f"ENTRY: Market Zone\n"
                f"TP1: +3%\n"
                f"TP2: +6%\n"
                f"SL: ATR Zone\n"
                "----------------\n"
            )


        bot.reply_to(message,text)


    except Exception as e:

        bot.reply_to(
            message,
            f"Scanner error ⚠️\n\n{e}"
        )



print("Starting AHAD AI v2.0...")
print("AHAD AI Bot running 🚀")


bot.infinity_polling()
