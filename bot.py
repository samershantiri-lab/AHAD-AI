import telebot
import os
import time
from flask import Flask
from threading import Thread

from tradingview_ta import TA_Handler, Interval

# ==========================
# AHAD AI v3.0
# TradingView Quant Engine
# ==========================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


# ===== KEEP RENDER ALIVE =====

@app.route("/")
def home():
    return "🚀 AHAD AI v3.0 TradingView Engine ONLINE"


def run_web():
    app.run(host="0.0.0.0", port=10000)


Thread(target=run_web).start()


# ===== COINS LIST =====

COINS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "ARBUSDT",
    "OPUSDT",
    "PEPEUSDT",
    "WIFUSDT"
]


# ===== ANALYZE COIN =====

def analyze_coin(symbol):

    try:
        handler = TA_Handler(
            symbol=symbol,
            screener="crypto",
            exchange="BINANCE",
            interval=Interval.INTERVAL_15_MINUTES
        )

        data = handler.get_analysis()

        indicators = data.indicators

        rsi = indicators.get("RSI")
        macd = indicators.get("MACD.macd")
        macd_signal = indicators.get("MACD.signal")

        ema50 = indicators.get("EMA50")
        ema200 = indicators.get("EMA200")
        close = indicators.get("close")

        score = 0

        reasons = []


        # Trend
        if close and ema50 and ema200:
            if close > ema50 > ema200:
                score += 35
                reasons.append("EMA Bull Trend ✅")


        # RSI
        if rsi:
            if 40 < rsi < 65:
                score += 25
                reasons.append("RSI Healthy ✅")


        # MACD
        if macd and macd_signal:
            if macd > macd_signal:
                score += 25
                reasons.append("MACD Bullish ✅")


        # TradingView recommendation

        if data.summary["RECOMMENDATION"] in ["BUY", "STRONG_BUY"]:
            score += 15
            reasons.append("TV BUY Signal ✅")


        if score >= 70:

            entry = round(close, 5)

            sl = round(entry * 0.98, 5)
            tp1 = round(entry * 1.03, 5)
            tp2 = round(entry * 1.06, 5)

            return {
                "coin": symbol,
                "score": score,
                "entry": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "reasons": reasons
            }


    except Exception:
        return None


# ===== TELEGRAM =====

@bot.message_handler(commands=["start"])
def start(msg):

    bot.reply_to(
        msg,
        """
🚀 AHAD AI v3.0 ONLINE

🧠 TradingView Quant Engine ACTIVE

Timeframe: 15M

Send /scan
        """
    )


@bot.message_handler(commands=["scan"])
def scan(msg):

    bot.reply_to(
        msg,
        "🔎 AHAD AI scanning TradingView..."
    )

    results = []

    for coin in COINS:

        signal = analyze_coin(coin)

        if signal:
            results.append(signal)

        time.sleep(1)


    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )[:3]


    if not results:

        bot.send_message(
            msg.chat.id,
            "😴 No strong LONG signals now"
        )

        return


    for s in results:

        text = f"""
🚀 AHAD AI LONG SIGNAL 🟢

Coin:
{s['coin']}

Entry:
{s['entry']}

🎯 TP1:
{s['tp1']}

🎯 TP2:
{s['tp2']}

🛑 SL:
{s['sl']}

Strength:
{s['score']} / 100 🧠

Reasons:
{chr(10).join(s['reasons'])}

Timeframe:
15M
"""

        bot.send_message(
            msg.chat.id,
            text
        )


# ===== RUN BOT =====

print("Starting AHAD AI v3.0 🚀")

bot.infinity_polling(
    skip_pending=True
)
