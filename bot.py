import os
import requests
import telebot


BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "🚀 AHAD AI v1.1 ONLINE\n\nاكتب /scan للصيد 🔥"
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔍 AHAD AI scanning market...\nانتظر 🚀"
    )

    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"

        data = requests.get(
            url,
            timeout=10
        ).json()

        coins = []

        for c in data:

            symbol = c.get("symbol", "")

            if symbol.endswith("USDT"):

                change = float(
                    c.get("priceChangePercent", 0)
                )

                volume = float(
                    c.get("quoteVolume", 0)
                )

                if change > 0 and volume > 1000000:

                    strength = change + volume / 100000000

                    coins.append(
                        [
                            symbol,
                            change,
                            strength
                        ]
                    )


        coins.sort(
            key=lambda x: x[2],
            reverse=True
        )


        text = "🚀 AHAD AI TOP 3 SIGNALS\n\n"

        for i, c in enumerate(coins[:3], 1):

            text += f"""
{i}️⃣ {c[0]}

🟢 LONG
🔥 Strength: {round(c[2],2)}
📈 Move: {c[1]}%

🎯 TP1 +3%
🎯 TP2 +6%
🛑 SL -2%

-----------
"""


        bot.reply_to(message, text)


    except Exception as e:

        bot.reply_to(
            message,
            f"ERROR ❌ {e}"
        )


print("AHAD AI Bot is running 🚀")

bot.infinity_polling()
