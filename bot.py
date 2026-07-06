import os
import threading
import requests
from flask import Flask
import telebot


# ===== WEB SERVER FOR RENDER =====

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 AHAD AI is running"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web).start()


# ===== TELEGRAM BOT =====

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "🚀 AHAD AI v1.0 is online\n\nSend /scan"
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔍 AHAD AI scanning market..."
    )

    try:

        data = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            timeout=10
        ).json()


        coins = []

        for coin in data:

            if coin["symbol"].endswith("USDT"):

                change = float(
                    coin["priceChangePercent"]
                )

                volume = float(
                    coin["quoteVolume"]
                )


                if change > 3 and volume > 10000000:

                    coins.append(
                        (
                            coin["symbol"],
                            change,
                            volume
                        )
                    )


        coins = sorted(
            coins,
            key=lambda x: x[1],
            reverse=True
        )[:3]


        if not coins:

            bot.reply_to(
                message,
                "❌ No strong signals now"
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
                f"STRENGTH: {round(c[1],2)}\n"
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



print("Starting AHAD AI v1.0...")
print("AHAD AI Bot is running 🚀")


bot.infinity_polling()
