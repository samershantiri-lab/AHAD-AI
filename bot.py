import os
import threading
import requests
import telebot
import pandas as pd

from flask import Flask


# ======================
# RENDER WEB SERVER
# ======================

app = Flask(__name__)

@app.route("/")
def home():
    return "AHAD AI v2.1 QUANT ENGINE RUNNING 🚀"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web).start()


# ======================
# TELEGRAM
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        """
🚀 AHAD AI v2.1 ONLINE

QUANT ENGINE ACTIVE 🧠

Send /scan
        """
    )


# ======================
# INDICATORS
# ======================

def rsi(prices, period=14):

    delta = prices.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def analyze(symbol):

    url = (
        "https://fapi.binance.com/fapi/v1/klines"
        f"?symbol={symbol}&interval=15m&limit=100"
    )

    data = requests.get(
        url,
        timeout=10
    ).json()


    # حماية API
    if not isinstance(data, list):
        return None


    closes = []

    volumes = []


    for candle in data:

        if not isinstance(candle, list):
            return None

        closes.append(float(candle[4]))
        volumes.append(float(candle[5]))


    df = pd.DataFrame()

    df["close"] = closes
    df["volume"] = volumes


    df["ema50"] = df["close"].ewm(span=50).mean()

    df["rsi"] = rsi(df["close"])


    price = df["close"].iloc[-1]

    ema = df["ema50"].iloc[-1]

    last_rsi = df["rsi"].iloc[-1]

    volume_now = df["volume"].iloc[-1]

    volume_avg = df["volume"].mean()


    score = 0


    # Trend
    if price > ema:
        score += 40


    # RSI zone
    if 35 < last_rsi < 65:
        score += 30


    # Volume
    if volume_now > volume_avg:
        score += 30


    return score, price, round(last_rsi, 2)



# ======================
# SCANNER
# ======================


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔎 AHAD AI v2.1 scanning market..."
    )


    try:

        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"

        market = requests.get(
            url,
            timeout=10
        ).json()


        if not isinstance(market, list):

            bot.reply_to(
                message,
                "⚠️ Market API unavailable"
            )

            return



        results = []


        for coin in market:

            if not isinstance(coin, dict):
                continue


            symbol = coin.get("symbol")


            if symbol and symbol.endswith("USDT"):


                result = analyze(symbol)


                if result:

                    score, price, r = result


                    if score >= 60:

                        results.append(
                            {
                                "symbol":symbol,
                                "score":score,
                                "price":price,
                                "rsi":r
                            }
                        )


        results = sorted(
            results,
            key=lambda x:x["score"],
            reverse=True
        )[:3]



        if not results:

            bot.reply_to(
                message,
                "😴 No strong LONG signals now"
            )

            return



        text = "🚀 AHAD AI TOP 3 LONG\n\n"


        for c in results:

            text += f"""
🪙 {c['symbol']}

💪 Strength: {c['score']}%

💰 Entry: {c['price']}

📊 RSI: {c['rsi']}

🎯 TP1: +3%
🎯 TP2: +6%

🛑 SL: -2%

-----------------

"""


        bot.reply_to(
            message,
            text
        )


    except Exception as e:

        bot.reply_to(
            message,
            f"Scanner error ⚠️\n\n{e}"
        )



# ======================
# RUN BOT
# ======================


print("Starting AHAD AI v2.1 🚀")


bot.remove_webhook()

bot.infinity_polling(
    skip_pending=True
)
