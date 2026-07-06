# ==============================
# 🚀 AHAD AI v5.9 STABLE CORE
# ==============================

import os
import time
import threading
import traceback
import requests
import pandas as pd

from flask import Flask
import telebot

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange


# ==============================
# CONFIG
# ==============================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

print("🚀 Starting AHAD AI v5.9")
print("🤖 Telegram Engine ACTIVE")


# ==============================
# KEEP RENDER ALIVE
# ==============================

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 AHAD AI v5.9 STABLE ONLINE 🐋"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


# ==============================
# BINANCE FUTURES ENGINE
# ==============================

def get_futures_symbols():

    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        data = requests.get(
            url,
            timeout=10
        ).json()

        symbols = []

        for s in data["symbols"]:

            if (
                s["quoteAsset"] == "USDT"
                and s["status"] == "TRADING"
            ):
                symbols.append(
                    s["symbol"]
                )

        return symbols

    except Exception as e:
        print("Symbol Error:", e)
        return []


# ==============================
# CANDLE DATA
# ==============================

def get_candles(symbol):

    try:

        url = (
            "https://fapi.binance.com/fapi/v1/klines"
            f"?symbol={symbol}"
            "&interval=15m"
            "&limit=120"
        )

        data = requests.get(
            url,
            timeout=10
        ).json()

        df = pd.DataFrame(
            data,
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "qav",
                "trades",
                "tb",
                "tq",
                "ignore"
            ]
        )

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        return df

    except Exception as e:
        print("Candle Error:", e)
        return None
        # ==============================
# 🧠 AHAD ANALYSIS ENGINE
# ==============================

def analyze(symbol):

    try:

        df = get_candles(symbol)

        if df is None:
            return None


        close = df["close"]

        price = close.iloc[-1]


        # EMA TREND

        ema50 = EMAIndicator(
            close,
            window=50
        ).ema_indicator().iloc[-1]


        ema200 = EMAIndicator(
            close,
            window=100
        ).ema_indicator().iloc[-1]


        # RSI

        rsi = RSIIndicator(
            close,
            window=14
        ).rsi().iloc[-1]


        # MACD

        macd = MACD(close)

        macd_value = (
            macd.macd().iloc[-1]
            -
            macd.macd_signal().iloc[-1]
        )


        # ATR

        atr = AverageTrueRange(
            df["high"],
            df["low"],
            close,
            window=14
        ).average_true_range().iloc[-1]


        # VOLUME WHALE

        volume_now = df["volume"].iloc[-1]

        volume_avg = (
            df["volume"]
            .tail(30)
            .mean()
        )


        whale_power = (
            volume_now
            /
            volume_avg
        )


        # ==================
        # SCORE ENGINE
        # ==================

        score = 0

        reasons = []


        if price > ema50:

            score += 20
            reasons.append(
                "EMA50 Trend ✅"
            )


        if ema50 > ema200:

            score += 20
            reasons.append(
                "EMA Trend Bullish 🐂"
            )


        if 40 <= rsi <= 65:

            score += 20
            reasons.append(
                "RSI Healthy ✅"
            )


        if macd_value > 0:

            score += 20
            reasons.append(
                "MACD Momentum ✅"
            )


        if whale_power >= 1.3:

            score += 20
            reasons.append(
                "Whale Volume 🐋"
            )


        # ==================
        # SMART ENTRY
        # ==================

        entry = price

        stop_loss = (
            price
            -
            (atr * 1.5)
        )


        risk = (
            entry
            -
            stop_loss
        )


        tp1 = (
            entry
            +
            risk * 2
        )


        tp2 = (
            entry
            +
            risk * 3
        )


        return {

            "coin": symbol,

            "entry": entry,

            "sl": stop_loss,

            "tp1": tp1,

            "tp2": tp2,

            "score": score,

            "rsi": rsi,

            "whale": whale_power,

            "reasons": reasons

        }


    except Exception as e:

        print(
            "Analyze Error:",
            e
        )

        return None
        # ==============================
# 🤖 TELEGRAM COMMANDS
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v5.9 STABLE ONLINE

🐋 Whale Engine ACTIVE
📊 Auto Futures Scanner ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Risk Engine ACTIVE
👀 Watchlist ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI scanning futures market..."
    )


    results = []


    symbols = get_futures_symbols()


    for symbol in symbols[:150]:

        result = analyze(symbol)

        if result:

            results.append(result)

        time.sleep(0.03)



    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )


    signals = [
        x for x in results
        if x["score"] >= 80
    ][:3]


    # ==================
    # SEND SIGNALS
    # ==================

    if signals:

        for s in signals:

            msg = f"""
🐋 AHAD AI WHALE SIGNAL

🟢 LONG SETUP

🪙 Coin:
{s['coin']}

🎯 ENTRY:
{round(s['entry'],5)}

🛑 STOP LOSS:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

📊 RSI:
{round(s['rsi'],2)}

🐋 Whale Power:
{round(s['whale'],2)}X

🔥 AHAD SCORE:
{s['score']}/100


✅ Confirmation:
{chr(10).join(s['reasons'])}
"""

            bot.send_message(
                message.chat.id,
                msg
            )


    else:

        watch = results[:3]


        text = """
👀 AHAD WATCHLIST

No perfect entry yet 🛡

Closest setups:
"""


        for w in watch:

            text += f"""

🪙 {w['coin']}

🔥 Score:
{w['score']}/100

📊 RSI:
{round(w['rsi'],2)}

🐋 Whale:
{round(w['whale'],2)}X

━━━━━━━━━━
"""


        bot.send_message(
            message.chat.id,
            text
        )



# ==============================
# 🛡 TELEGRAM AUTO RECOVERY
# ==============================

def telegram_engine():

    while True:

        try:

            print(
                "🤖 Telegram Engine Running"
            )


            bot.infinity_polling(
                skip_pending=True,
                timeout=60
            )


        except Exception:

            print(
                traceback.format_exc()
            )

            print(
                "🔄 Restarting Telegram..."
            )

            time.sleep(5)



# ==============================
# 🚀 START SYSTEM
# ==============================

threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=telegram_engine,
    daemon=True
).start()


print(
    "🔥 AHAD AI v5.9 FULL ONLINE"
)


while True:

    time.sleep(60)
