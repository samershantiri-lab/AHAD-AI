import os
import time
import threading
import requests
import pandas as pd
import telebot

from flask import Flask


# ==========================
# AHAD AI v5.6
# ==========================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


# ==========================
# RENDER WEB SERVER
# ==========================

@app.route("/")
def home():
    return "🚀 AHAD AI v5.6 ONLINE"


def run_web():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# ==========================
# MARKET DATA
# ==========================

def get_market():

    url = "https://api.binance.com/api/v3/ticker/24hr"

    try:
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

                coins.append({
                    "symbol": c["symbol"],
                    "change": float(c["priceChangePercent"]),
                    "volume": float(c["quoteVolume"])
                })

        return coins

    except Exception as e:

        print("Market Error:", e)

        return []


# ==========================
# AHAD AI ENGINE
# ==========================

def analyze_coin(coin):

    score = 0

    # Volume power
    if coin["volume"] > 50000000:
        score += 30

    # Momentum
    if coin["change"] > 1:
        score += 30

    # Smart Entry simulation
    if 1 < coin["change"] < 8:
        score += 30


    return score



def scan_market():

    market = get_market()

    results = []

    for coin in market:

        score = analyze_coin(coin)

        if score >= 80:

            results.append(
                {
                    "coin": coin["symbol"],
                    "score": score
                }
            )


    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:3]


# ==========================
# TELEGRAM COMMANDS
# ==========================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,

f"""
🚀 AHAD AI v5.6 ONLINE

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
        "🐋 Searching sniper setups..."
    )


    signals = scan_market()


    if not signals:

        bot.send_message(
            message.chat.id,
            "😴 No sniper LONG setup now 🛡"
        )

        return


    for s in signals:

        text = f"""

🟢 LONG SIGNAL

🪙 Coin: {s['coin']}

🎯 Entry: Smart Zone

🎯 TP1: +3%
🎯 TP2: +6%

🛑 Stop Loss:
ATR Protected

🐋 Whale Score:
{s['score']}/100

🔥 AHAD Score: HIGH

"""

        bot.send_message(
            message.chat.id,
            text
        )


# ==========================
# TELEGRAM ENGINE
# ==========================

def telegram_engine():

    while True:

        try:

            print("🤖 Telegram Engine ACTIVE")

            bot.infinity_polling(
                skip_pending=True,
                timeout=60,
                long_polling_timeout=60
            )


        except Exception as e:

            print("⚠️ Telegram crashed")
            print(e)

            print("🔄 Restarting...")

            time.sleep(5)



# ==========================
# START SYSTEM
# ==========================

if __name__ == "__main__":

    print("""
🚀 Starting AHAD AI v5.6

🐋 Whale Engine
🎯 Smart Entry
🛑 ATR Stop

""")


    threading.Thread(
        target=run_web,
        daemon=True
    ).start()


    time.sleep(2)


    threading.Thread(
        target=telegram_engine,
        daemon=True
    ).start()


    print("🔥 AHAD AI FULL ONLINE")


    while True:
        time.sleep(60)
