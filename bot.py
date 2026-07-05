import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("8697535359:AAFmpR08Rc9WW0EH4sEW6Gcg6vVgZJC2XSI")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AHAD AI v1.0 is online 🚀"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 AHAD AI scanning market...\n\nPlease wait..."
    )


def main():
    print("Starting AHAD AI...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))

    app.run_polling()


if __name__ == "__main__":
    main()
