import os
import threading
import requests
from flask import Flask
import telebot


# ========== WEB SERVER FOR RENDER ==========

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 AHAD AI is running"


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
        "🚀 AHAD AI v1.1 ONLINE\n\nSend /scan"
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔍 AHAD AI scanning market..."
    )


    try:

        response = requests.get(
            "https://api.binance.us/api/v3/ticker/24hr",
            timeout=15
        )


        data = response.json()


        if not isinstance(data, list):

            bot.reply_to(
                message,
                f"API ERROR ⚠️\n\n{data}"
            )

            return


        coins = []


        for coin in data:


            symbol = coin.get("symbol", "")


            if symbol.endswith("USDT"):


                change = float(
                    coin.get(
                        "priceChangePercent",
                        0
                    )
                )


                volume = float(
                    coin.get(
                        "quoteVolume",
                        0
                    )
                )


                strength = change + (volume / 10000000)


                if change > 2 and volume > 1000000:


                    coins.append(
                        (
                            symbol,
                            change,
                            volume,
                            strength
                        )
                    )



        coins = sorted(
            coins,
            key=lambda x: x[3],
            reverse=True
        )[:3]



        if len(coins) == 0:

            bot.reply_to(
                message,
                "😴 No strong LONG signals now"
            )

            return



        text = "🚀 AHAD AI TOP 3 SIGNALS\n\n"


        for c in coins:

            text += (
                "----------------\n"
                f"🪙 COIN: {c[0]}\n"
                "TYPE: LONG 📈\n\n"
                "ENTRY: Market Zone\n"
                "SL: -2%\n"
                "TP1: +3%\n"
                "TP2: +6%\n\n"
                f"CHANGE: {round(c[1],2)}%\n"
                f"STRENGTH: {round(c[3],2)}\n\n"
            )


        bot.reply_to(
            message,
            text
        )



    except Exception as e:


        bot.reply_to(
            message,
            f"Scanner error ⚠️\n\n{e}"
        )


        print(e)




print("🚀 Starting AHAD AI v1.1")
print("🤖 Bot running...")


bot.infinity_polling()
