# ==============================
# 🚀 AHAD AI v6.0 STABLE CORE
# ==============================

import os
import time
import threading
import traceback
import requests
import telebot

from flask import Flask


# ==============================
# ⚙️ CONFIG
# ==============================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)


print("🚀 Starting AHAD AI v6.0")
print("🤖 Telegram Engine ACTIVE")


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

app = Flask(__name__)


@app.route("/")
def home():
    return "🚀 AHAD AI v6.0 ONLINE 🐋"


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


# ==============================
# 📊 BINANCE FUTURES DATA
# ==============================

def get_futures_symbols():

    try:

        url = (
            "https://fapi.binance.com"
            "/fapi/v1/ticker/24hr"
        )

        data = requests.get(
            url,
            timeout=10
        ).json()


        coins = []

        for c in data:

            if (
                c["symbol"].endswith("USDT")
                and float(c["quoteVolume"]) > 10000000
            ):

                coins.append(
                    c["symbol"]
                )

        return coins


    except Exception as e:

        print(
            "Symbols error:",
            e
        )

        return []
# ==============================
# 🧠 AHAD AI ANALYSIS ENGINE
# ==============================

def analyze(symbol):

    try:

        url = (
            "https://fapi.binance.com"
            "/fapi/v1/klines"
        )

        params = {
            "symbol": symbol,
            "interval": "15m",
            "limit": 50
        }


        candles = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        closes = [
            float(x[4])
            for x in candles
        ]

        volumes = [
            float(x[5])
            for x in candles
        ]


        price = closes[-1]


        avg_volume = (
            sum(volumes[:-1])
            /
            len(volumes[:-1])
        )

        whale = (
            volumes[-1]
            /
            avg_volume
        )


        change = (
            (closes[-1] - closes[-5])
            /
            closes[-5]
        ) * 100


        score = 0


        # 🐋 Whale power
        if whale > 1.5:
            score += 40


        # 🟢 LONG momentum
        if change > 0:
            score += 30


        # 📊 Volume boost
        if volumes[-1] > avg_volume:
            score += 20


        # 🔥 Strong move
        if change > 1:
            score += 10


        if score >= 70:

            return {

                "coin": symbol,
                "price": price,
                "score": score,
                "whale": whale

            }


        return None


    except Exception as e:

        print(
            "Analyze error:",
            symbol,
            e
        )

        return None
# ==============================
# 🤖 TELEGRAM COMMANDS
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v6.0 ONLINE

🐋 Whale Engine ACTIVE
📊 Futures Scanner ACTIVE
🟢 LONG Priority ACTIVE
⏱ 15m Smart Entry ACTIVE
🎯 TP / SL Engine ACTIVE

Send /scan
"""
    )


# ==============================
# 🐋 SCAN COMMAND
# ==============================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI scanning market...\n⏱ Timeframe: 15m"
    )


    try:

        results = []

        symbols = get_futures_symbols()


        for symbol in symbols[:200]:

            signal = analyze(symbol)

            if signal:

                results.append(signal)


            time.sleep(0.05)


        results = sorted(
            results,
            key=lambda x: x["score"],
            reverse=True
        )


        text = """
🚀 AHAD AI v6 SIGNALS

🏆 TOP 3 SETUPS
"""


        if len(results) == 0:

            text += """

😴 No sniper LONG yet 🛡

Market quiet now...
Waiting for whale movement 🐋
"""


        else:

            for coin in results[:3]:

                entry = coin["price"]

                tp1 = entry * 1.03
                tp2 = entry * 1.06
                sl = entry * 0.98


                text += f"""

🟢 LONG {coin['coin']}

💰 Entry:
{round(entry,6)}

🎯 TP1:
{round(tp1,6)}

🎯 TP2:
{round(tp2,6)}

🛑 SL:
{round(sl,6)}

🔥 Strength:
{coin['score']}/100

🐋 Whale:
{round(coin['whale'],2)}X

────────────
"""


        bot.send_message(
            message.chat.id,
            text
        )


    except Exception as e:

        print(
            "SCAN ERROR:",
            e
        )

        bot.send_message(
            message.chat.id,
            "⚠️ Scanner temporary error"
        )


# ==============================
# 🛡 AUTO RECOVERY ENGINE
# ==============================

def telegram_engine():

    while True:

        try:

            print("🤖 Bot polling started")

            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60
            )


        except Exception:

            traceback.print_exc()

            print(
                "🔄 Restarting Telegram..."
            )

            time.sleep(5)



# ==============================
# 🚀 START SYSTEM
# ==============================

if __name__ == "__main__":

    threading.Thread(
        target=run_web
    ).start()


    telegram_engine()
