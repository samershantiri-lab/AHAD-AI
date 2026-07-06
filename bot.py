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
# 🧠 AHAD AI v6.1 ANALYSIS ENGINE
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

        macd_power = (
            macd.macd().iloc[-1]
            -
            macd.macd_signal().iloc[-1]
        )


        # ATR STOP ENGINE

        atr = AverageTrueRange(
            df["high"],
            df["low"],
            close,
            window=14
        ).average_true_range().iloc[-1]


        # WHALE VOLUME

        volume_now = df["volume"].iloc[-1]

        volume_avg = (
            df["volume"]
            .tail(30)
            .mean()
        )


        whale = (
            volume_now
            /
            volume_avg
        )


        # ==================
        # AHAD SCORE
        # ==================

        score = 0
        reasons = []


        if price > ema50:

            score += 25

            reasons.append(
                "EMA50 Bullish ✅"
            )


        if ema50 > ema200:

            score += 20

            reasons.append(
                "Trend Confirmed 🐂"
            )


        if 35 <= rsi <= 68:

            score += 20

            reasons.append(
                "RSI LONG Zone ✅"
            )


        if macd_power > 0:

            score += 20

            reasons.append(
                "MACD Momentum 🚀"
            )


        if whale >= 1.1:

            score += 15

            reasons.append(
                "Whale Activity 🐋"
            )


        # ENTRY + RISK

        entry = price

        stop_loss = (
            price -
            atr * 1.5
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


        if score >= 80:

            status = "🔥 SNIPER LONG"

        elif score >= 60:

            status = "🟡 ALMOST READY"

        else:

            status = "👀 WATCHING"



        return {

            "coin": symbol,
            "entry": entry,
            "sl": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "score": score,
            "rsi": rsi,
            "whale": whale,
            "status": status,
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
🚀 AHAD AI v6.1 ONLINE

🐋 Whale Engine ACTIVE
📊 Auto Futures Scanner ACTIVE
🟢 LONG Hunter ACTIVE
⏱ 15m Timeframe ACTIVE
🎯 Smart Entry + ATR SL ACTIVE
👀 Watchlist ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI v6.1 scanning market..."
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
        if x["score"] >= 80
    ][:3]


    almost = [
        x for x in results
        if 60 <= x["score"] < 80
    ][:5]



    if sniper:


        for s in sniper:


            bot.send_message(
                message.chat.id,
f"""
🐋 AHAD AI SNIPER SIGNAL

🟢 LONG

🪙 Coin:
{s['coin']}

{s['status']}

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

🔥 Score:
{s['score']}/100

✅ Reasons:
{chr(10).join(s['reasons'])}
"""
            )


    elif almost:


        text = """
🟡 AHAD WATCHLIST

Almost Ready Setups 👀
"""


        for a in almost:


            text += f"""

🪙 {a['coin']}

🔥 Score:
{a['score']}/100

📊 RSI:
{round(a['rsi'],2)}

🐋 Whale:
{round(a['whale'],2)}X

{a['status']}

━━━━━━━━━━
"""


        bot.send_message(
            message.chat.id,
            text
        )


    else:


        bot.send_message(
            message.chat.id,
            "😴 Market quiet now 🛡\n🐋 Waiting for whale movement..."
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
    "🔥 AHAD AI v6.1 FULL ONLINE"
)


while True:

    time.sleep(60)
