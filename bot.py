import os
import telebot
import requests
import pandas as pd
from flask import Flask
from threading import Thread
from tradingview_ta import TA_Handler, Interval

# =========================
# AHAD AI v4.1
# =========================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# =========================
# KEEP RENDER ONLINE
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 AHAD AI v4.1 ONLINE"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )

# =========================
# START COMMAND
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        """
🚀 AHAD AI v4.1 ONLINE

🧠 Quant Engine ACTIVE
📊 Source: TradingView
⏱ Timeframe: 15M

Send /scan
"""
    )


# =========================
# SCANNER
# =========================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🔎 AHAD AI scanning market..."
    )

    coins = [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "PEPEUSDT",
        "WIFUSDT",
        "ARBUSDT",
        "SUIUSDT"
    ]

    signals = []

    for coin in coins:

        try:

            symbol = coin.replace("USDT", "")

            handler = TA_Handler(
                symbol=symbol + "USDT",
                screener="crypto",
                exchange="BINANCE",
                interval=Interval.INTERVAL_15_MINUTES
            )

            data = handler.get_analysis()

            rsi = data.indicators["RSI"]
            rec = data.summary["RECOMMENDATION"]

            if (
                rec in ["BUY", "STRONG_BUY"]
                and rsi < 70
            ):

                signals.append(
f"""
🟢 LONG SIGNAL

🪙 Coin: {coin}

📊 Signal: {rec}
💪 RSI: {round(rsi,2)}

🎯 TP1: +3%
🎯 TP2: +6%
🛑 SL: -2%

🔥 AHAD Score: HIGH
"""
                )

        except Exception as e:
            print(e)


    if signals:

        for s in signals[:3]:
            bot.send_message(
                message.chat.id,
                s
            )

    else:

        bot.send_message(
            message.chat.id,
            "😴 No strong LONG signals now"
        )


# =========================
# RUN
# =========================

print("🚀 Starting AHAD AI v4.1")

Thread(target=run_web).start()

bot.infinity_polling(
    skip_pending=True,
    timeout=60
)
