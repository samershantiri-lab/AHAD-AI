import os
import requests

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)


# TOKEN FROM RENDER ENVIRONMENT
BOT_TOKEN = os.getenv("BOT_TOKEN")


# START COMMAND
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🚀 AHAD AI v1.1 ONLINE\n\n"
        "اكتب /scan لبدء فحص السوق 🔥"
    )


# SCANNER
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🔍 AHAD AI scanning all coins...\nانتظر قليلاً 🚀"
    )

    try:

        url = "https://api.binance.com/api/v3/ticker/24hr"

        response = requests.get(
            url,
            timeout=15
        )

        data = response.json()


        opportunities = []


        for coin in data:

            symbol = coin.get("symbol", "")

            if symbol.endswith("USDT"):

                change = float(
                    coin.get("priceChangePercent", 0)
                )

                volume = float(
                    coin.get("quoteVolume", 0)
                )


                # LONG FILTER
                if change > 0 and volume > 1000000:

                    strength = (
                        change +
                        (volume / 100000000)
                    )


                    opportunities.append({
                        "symbol": symbol,
                        "change": change,
                        "strength": strength
                    })



        opportunities = sorted(
            opportunities,
            key=lambda x: x["strength"],
            reverse=True
        )


        top3 = opportunities[:3]


        if not top3:

            await update.message.reply_text(
                "❌ لا توجد فرص قوية الآن"
            )

            return



        message = """
🚀 AHAD AI SMART SIGNALS

TOP 3 OPPORTUNITIES

"""


        number = 1


        for c in top3:

            message += f"""
{number}️⃣ {c['symbol']}

🟢 SIGNAL: LONG

🔥 Strength:
{round(c['strength'],2)}

📈 Move:
{c['change']} %

🎯 TP1: +3%
🎯 TP2: +6%

🛑 SL: -2%

-----------------

"""

            number += 1



        await update.message.reply_text(message)



    except Exception as e:

        await update.message.reply_text(
            f"ERROR ❌\n{e}"
        )



# RUN BOT
def main():

    print("Starting AHAD AI v1.1...")
    print("AHAD AI Bot is running 🚀")


    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    app.add_handler(
        CommandHandler(
            "scan",
            scan
        )
    )


    app.run_polling(
        drop_pending_updates=True
    )



if __name__ == "__main__":

    main()
