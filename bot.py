import os
import asyncio
import requests

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 AHAD AI v1.1 is online\n\n"
        "Send /scan to hunt opportunities 🔥"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🔎 AHAD AI scanning market...\nPlease wait 🚀"
    )

    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        data = requests.get(url, timeout=10).json()

        coins = []

        for coin in data:
            symbol = coin.get("symbol", "")

            if symbol.endswith("USDT"):

                change = float(coin["priceChangePercent"])
                volume = float(coin["quoteVolume"])

                # فلتر فرص LONG
                if change > 0 and volume > 1000000:

                    strength = change + (volume / 100000000)

                    coins.append({
                        "symbol": symbol,
                        "change": change,
                        "volume": volume,
                        "strength": strength
                    })

        coins = sorted(
            coins,
            key=lambda x: x["strength"],
            reverse=True
        )[:3]


        if not coins:
            await update.message.reply_text(
                "❌ No strong opportunities now"
            )
            return


        message = "🚀 AHAD AI SMART SIGNALS\n\n"

        number = 1

        for c in coins:
            message += (
                f"{number}️⃣ {c['symbol']}\n"
                f"🟢 LONG\n"
                f"🔥 Strength: {round(c['strength'],2)}\n"
                f"📈 Move: {c['change']}%\n\n"
                f"🎯 TP1: +3%\n"
                f"🎯 TP2: +6%\n"
                f"🛑 SL: -2%\n\n"
            )

            number += 1


        await update.message.reply_text(message)


    except Exception as e:
        await update.message.reply_text(
            f"Error: {e}"
        )


async def main():

    print("Starting AHAD AI v1.1...")
    print("AHAD AI Bot is running 🚀")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("scan", scan)
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
