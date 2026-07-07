# ==============================
# 🚀 AHAD AI v6.1 STABLE
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

if TOKEN is None:
    raise Exception("BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)

print("🚀 Starting AHAD AI v6.1")
print("🤖 Telegram Engine ACTIVE")


# ==============================
# RENDER KEEP ALIVE
# ==============================

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 AHAD AI v6.1 ONLINE 🐋"


def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# ==============================
# BINANCE FUTURES LIST
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
                and
                s["status"] == "TRADING"
            ):

                symbols.append(
                    s["symbol"]
                )


        return symbols


    except Exception as e:

        print(
            "Symbol Error:",
            e
        )

        return []


# ==============================
# GET 15M CANDLES
# ==============================

def get_candles(symbol):

    try:

        url = "https://fapi.binance.com/fapi/v1/klines"


        params = {
            "symbol": symbol,
            "interval": "15m",
            "limit": 200
        }


        data = requests.get(
            url,
            params=params,
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
                "x1",
                "x2",
                "x3",
                "x4",
                "x5",
                "x6"
            ]
        )


        df = df[
            [
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        ]


        return df.astype(float)


    except Exception as e:

        print(
            "Candle Error:",
            e
        )

        return None
# ==============================
# 🧠 AHAD AI ANALYSIS ENGINE v6.2
# ==============================

def analyze(symbol):

    try:

        df = get_candles(symbol)

        if df is None:
            return None


        close = df["close"]

        price = close.iloc[-1]


        # ==================
        # EMA TREND
        # ==================

        ema50 = EMAIndicator(
            close,
            window=50
        ).ema_indicator().iloc[-1]


        ema200 = EMAIndicator(
            close,
            window=100
        ).ema_indicator().iloc[-1]


        # ==================
        # RSI
        # ==================

        rsi = RSIIndicator(
            close,
            window=14
        ).rsi().iloc[-1]


        # ==================
        # MACD
        # ==================

        macd = MACD(close)

        macd_power = (
            macd.macd().iloc[-1]
            -
            macd.macd_signal().iloc[-1]
        )


        # ==================
        # ATR
        # ==================

        atr = AverageTrueRange(
            df["high"],
            df["low"],
            close,
            window=14
        ).average_true_range().iloc[-1]


        # ==================
        # WHALE ENGINE
        # ==================

        volume_now = df["volume"].iloc[-1]

        volume_avg = (
            df["volume"]
            .tail(30)
            .mean()
        )


        whale_power = (
            volume_now /
            volume_avg
        )


        # ==================
        # AHAD SCORE v6.2
        # ==================

        score = 0

        reasons = []


        if price > ema50:

            score += 25

            reasons.append(
                "Trend Above EMA50 ✅"
            )


        if ema50 > ema200:

            score += 20

            reasons.append(
                "Bullish Structure 🐂"
            )


        if 35 <= rsi <= 68:

            score += 20

            reasons.append(
                "RSI Entry Zone 🎯"
            )


        if macd_power > 0:

            score += 20

            reasons.append(
                "MACD Momentum 🔥"
            )


        # WHALE CONFIRMATION

        if whale_power >= 1.5:

            score += 15

            reasons.append(
                "Whale Entered 🐋"
            )


        elif whale_power >= 1.1:

            score += 8

            reasons.append(
                "Pre Whale Activity 👀"
            )


        # ==================
        # SMART ENTRY
        # ==================

        entry = price


        stop_loss = (
            price -
            (atr * 1.5)
        )


        risk = (
            entry -
            stop_loss
        )


        tp1 = (
            entry +
            risk * 2
        )


        tp2 = (
            entry +
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
# 🤖 TELEGRAM COMMANDS v6.2
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v6.2 PRE-WHALE HUNTER

🐋 Whale Engine ACTIVE
📊 Auto Futures Scanner ACTIVE
🟢 LONG Hunter ACTIVE
⏱ 15m Timeframe ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Stop Loss ACTIVE
👀 Pre-Whale Watchlist ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI v6.2 scanning market..."
    )


    results = []


    symbols = get_futures_symbols()


    for symbol in symbols[:200]:

        try:

            result = analyze(symbol)


            if result:

                results.append(result)


            time.sleep(0.03)


        except Exception as e:

            print(
                "Scan Error:",
                symbol,
                e
            )



    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )


    sniper = [
        x for x in results
        if x["score"] >= 75
    ][:3]


    pre_whale = [
        x for x in results
        if 60 <= x["score"] < 75
    ][:5]


    watch = [
        x for x in results
        if 45 <= x["score"] < 60
    ][:5]



    # ==================
    # 🔥 SNIPER SIGNAL
    # ==================

    if sniper:


        for s in sniper:


            bot.send_message(
                message.chat.id,
f"""
🐋 AHAD AI v6.2 SIGNAL

🟢 SNIPER LONG

🪙 Coin:
{s['coin']}

🎯 Entry:
{round(s['entry'],5)}

🛑 Stop Loss:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

📊 RSI:
{round(s['rsi'],2)}

🐋 Whale:
{round(s['whale'],2)}X

🔥 SCORE:
{s['score']}/100

✅ Confirmations:
{chr(10).join(s['reasons'])}
"""
            )



    # ==================
    # 🟡 PRE WHALE
    # ==================

    elif pre_whale:


        text = """
🟡 PRE-WHALE WATCHLIST 🐋

Potential moves forming:
"""


        for p in pre_whale:


            text += f"""

🪙 {p['coin']}

🔥 Score:
{p['score']}/100

📊 RSI:
{round(p['rsi'],2)}

🐋 Whale:
{round(p['whale'],2)}X

👀 Waiting confirmation

━━━━━━━━━━
"""


        bot.send_message(
            message.chat.id,
            text
        )



    # ==================
    # 👀 WATCH ONLY
    # ==================

    elif watch:


        text = """
👀 AHAD WATCH MODE

Early setups:
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



    else:


        bot.send_message(
            message.chat.id,
"""
😴 Market quiet now 🛡

No clean LONG structure.

🐋 Waiting for better setup...
"""
        )



# ==============================
# 🛡 AUTO RECOVERY
# ==============================

def telegram_engine():

    while True:

        try:

            print(
                "🤖 Telegram Running"
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
                "🔄 Restarting..."
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
    "🔥 AHAD AI v6.2 FULL ONLINE"
)


while True:

    time.sleep(60)
