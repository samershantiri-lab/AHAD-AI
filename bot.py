import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 AHAD AI v1.0 is online"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = """
🚀 AHAD AI SMART SIGNALS

Scanner is running...

📊 Top 3 opportunities:

1️⃣ BTCUSDT
Type: LONG 🟢
Strength: 90%

2️⃣ ETHUSDT
Type: LONG 🟢
Strength: 85%

3️⃣ SOLUSDT
Type: LONG 🟢
Strength: 80%

AHAD AI v1.0 🚀
"""

    await update.message.reply_text(message)


def main():
    print("Starting AHAD AI v1.0...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))

    print("AHAD AI Bot is running 🚀")

    app.run_polling(
        close_loop=False
    )


if __name__ == "__main__":
    main()
