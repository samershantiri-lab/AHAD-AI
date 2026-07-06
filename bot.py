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


# =============================
# AHAD AI v5.8 AUTO FUTURES PRO
# =============================


TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


# =============================
# RENDER KEEP ALIVE
# =============================

@app.route("/")
def home():
    return "🚀 AHAD AI v5.8 ONLINE"


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


# =============================
# BINANCE FUTURES SYMBOLS
# =============================


def get_symbols():

    try:

        url = (
            "https://fapi.binance.com"
            "/fapi/v1/exchangeInfo"
        )

        data = requests.get(
            url,
            timeout=10
        ).json()


        coins = []


        for s in data["symbols"]:

            if (
                s["quoteAsset"] == "USDT"
                and
                s["status"] == "TRADING"
            ):

                coins.append(
                    s["symbol"]
                )


        return coins[:150]


    except Exception as e:

        print(
            "Symbol error:",
            e
        )

        return [
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT"
        ]


# =============================
# GET 15M DATA
# =============================


def get_data(symbol):

    try:

        url = (
            "https://fapi.binance.com"
            "/fapi/v1/klines"
        )


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
                "a",
                "b",
                "c",
                "d",
                "e",
                "f"
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
            "Data error:",
            e
        )

        return None



# =============================
# ANALYSIS ENGINE
# =============================


def analyze(symbol):

    df = get_data(symbol)


    if df is None:

        return None


    try:

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


        volume_now = (
            df["volume"]
            .iloc[-1]
        )


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


        score = 0

        reasons = []


        if price > ema50:

            score += 30

            reasons.append(
                "Trend Bullish"
            )
if 40 <= rsi <= 65:

            score += 20

            reasons.append(
                "RSI Healthy"
            )


        if macd_power > 0:

            score += 20

            reasons.append(
                "MACD Bullish"
            )


        if whale >= 1.3:

            score += 30

            reasons.append(
                "Whale Volume"
            )


        stop_loss = (
            price -
            (atr * 1.5)
        )


        risk = (
            price -
            stop_loss
        )


        tp1 = (
            price +
            risk * 2
        )


        tp2 = (
            price +
            risk * 3
        )


        result = {

            "coin": symbol,
            "price": price,
            "entry": price,
            "sl": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "score": score,
            "rsi": rsi,
            "whale": whale,
            "reasons": reasons

        }


        return result


    except Exception as e:

        print(
            "Analyze error:",
            e
        )

        return None



# =============================
# TELEGRAM COMMANDS
# =============================


@bot.message_handler(
    commands=["start"]
)

def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v5.8 ONLINE

🐋 Auto Futures Scanner
🎯 Smart Entry Engine
🛑 ATR Stop Loss
🧠 Score System

Send /scan
"""
    )



@bot.message_handler(
    commands=["scan"]
)

def scan(message):

    bot.reply_to(
        message,
        "🐋 Scanning Futures Market..."
    )


    results = []


    for coin in get_symbols():

        data = analyze(coin)


        if data:

            results.append(data)


        time.sleep(0.03)



    results = sorted(
        results,
        key=lambda x:
        x["score"],
        reverse=True
    )


    signals = [
        x for x in results
        if x["score"] >= 80
    ][:3]


    if signals:


        for s in signals:


            text = f"""
🐋 AHAD AI v5.8 SIGNAL

🟢 LONG

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

🐋 Whale:
{round(s['whale'],2)}X

🔥 AHAD SCORE:
{s['score']}/100

✅
{chr(10).join(s['reasons'])}
"""


            bot.send_message(
                message.chat.id,
                text
            )


    else:


        watch = results[:3]


        msg = "👀 AHAD WATCHLIST\n\n"


        for w in watch:


            msg += f"""
🪙 {w['coin']}

Score:
{w['score']}/100

Waiting confirmation...
━━━━━━━━━━
"""


        bot.send_message(
            message.chat.id,
            msg
        )



# =============================
# TELEGRAM AUTO RESTART
# =============================


def telegram_engine():

    while True:

        try:

            print(
                "🤖 Telegram Engine ACTIVE"
            )


            bot.infinity_polling(
                skip_pending=True,
                timeout=60
            )


        except Exception as e:


            print(e)

            print(
                "Restarting Telegram..."
            )

            time.sleep(5)



# =============================
# START SYSTEM
# =============================


print(
    "🚀 AHAD AI v5.8 STARTED"
)


threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=telegram_engine,
    daemon=True
).start()


while True:

    time.sleep(60)
