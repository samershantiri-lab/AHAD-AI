import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 AHAD AI v1.0 is online 🤖"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = """
🚀 AHAD AI SMART SIGNALS

Scanner is running...

📊 TOP 3 OPPORTUNITIES

🟢 LONG Scanner Active
⏱ Timeframe: 15m

1️⃣ Waiting for market data...
2️⃣ Waiting for Alpha Hunter...
3️⃣ Waiting for AI Signal...

🔥 AHAD AI v1.0
"""

    await update.message.reply_text(message)


def main():

    print("Starting AHAD AI v1.0...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))

    print("AHAD AI Bot is running 🚀")

    app.run_polling()


if __name__ == "__main__":
    main()
