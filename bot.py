import os
import time
import threading
import requests
import telebot
import pandas as pd

from flask import Flask

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange


# ==========================
# AHAD AI v5.8.1 FIX BUILD
# ==========================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


# ==========================
# KEEP RENDER ONLINE
# ==========================

@app.route("/")
def home():
    return "🚀 AHAD AI v5.8.1 ONLINE"


def web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


# ==========================
# GET FUTURES COINS AUTO
# ==========================

def get_symbols():

    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        data = requests.get(
            url,
            timeout=10
        ).json()

        symbols = []

        for item in data["symbols"]:

            if (
                item["quoteAsset"] == "USDT"
                and item["status"] == "TRADING"
            ):
                symbols.append(
                    item["symbol"]
                )

        return symbols[:200]

    except Exception as e:

        print("Symbol Error", e)

        return [
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT"
        ]


# ==========================
# 15M MARKET DATA
# ==========================

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

        print("Candle Error", e)

        return None


# ==========================
# AHAD ANALYSIS ENGINE
# ==========================

def analyze(symbol):

    try:

        df = get_candles(symbol)

        if df is None:
            return None


        close = df["close"]

        price = close.iloc[-1]


        rsi = RSIIndicator(
            close
        ).rsi().iloc[-1]


        ema50 = EMAIndicator(
            close,
            window=50
        ).ema_indicator().iloc[-1]


        macd = MACD(close)

        macd_power = (
            macd.macd().iloc[-1]
            -
            macd.macd_signal().iloc[-1]
        )
        atr = AverageTrueRange(
            df["high"],
            df["low"],
            df["close"]
        ).average_true_range().iloc[-1]


        volume_now = df["volume"].iloc[-1]
        volume_avg = df["volume"].tail(30).mean()

        whale = volume_now / volume_avg


        score = 0
        reasons = []


        # TREND
        if price > ema50:
            score += 30
            reasons.append("EMA Trend UP")


        # RSI
        if 40 <= rsi <= 65:
            score += 20
            reasons.append("RSI Healthy")


        # MACD
        if macd_power > 0:
            score += 20
            reasons.append("MACD Momentum")


        # WHALE VOLUME
        if whale >= 1.3:
            score += 30
            reasons.append("Whale Volume")


        # SMART ENTRY
        entry = price

        stop_loss = price - (atr * 1.5)

        risk = entry - stop_loss

        tp1 = entry + (risk * 2)
        tp2 = entry + (risk * 3)


        return {
            "coin": symbol,
            "entry": entry,
            "sl": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rsi": rsi,
            "score": score,
            "whale": whale,
            "reasons": reasons
        }


    except Exception as e:

        print(
            "Analyze Error:",
            e
        )

        return None



# ==========================
# TELEGRAM START
# ==========================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v5.8.1 ONLINE

🐋 Whale Engine ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Stop ACTIVE
📊 Futures Auto Scan

Send /scan
"""
    )



# ==========================
# SCAN COMMAND
# ==========================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI scanning market..."
    )


    results = []


    for coin in get_symbols():

        result = analyze(coin)

        if result:
            results.append(result)

        time.sleep(0.02)


    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )


    signals = [
        x for x in results
        if x["score"] >= 80
    ][:3]


    if signals:

        for s in signals:

            text = f"""
🟢 LONG SIGNAL

🪙 Coin: {s['coin']}

🎯 Entry:
{round(s['entry'],5)}

🛑 Stop Loss:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

💪 RSI:
{round(s['rsi'],2)}

🐋 Whale:
{round(s['whale'],2)}X

🔥 AHAD SCORE:
{s['score']}/100

✅ Confirmation:
{chr(10).join(s['reasons'])}
"""

            bot.send_message(
                message.chat.id,
                text
            )

    else:

        bot.send_message(
            message.chat.id,
            "😴 No perfect LONG setup now 🛡"
        )



# ==========================
# TELEGRAM ENGINE
# ==========================

def telegram():

    while True:

        try:

            print("🤖 Telegram ACTIVE")

            bot.infinity_polling(
                skip_pending=True,
                timeout=60
            )

        except Exception as e:

            print(e)

            time.sleep(5)



# ==========================
# START AHAD SYSTEM
# ==========================

print(
    "🚀 Starting AHAD AI v5.8.1"
)


threading.Thread(
    target=web_server,
    daemon=True
).start()


threading.Thread(
    target=telegram,
    daemon=True
).start()


while True:

    time.sleep(60)
