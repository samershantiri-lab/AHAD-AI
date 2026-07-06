import os
import time
import requests
import telebot
import pandas as pd
import ta

from flask import Flask
from threading import Thread


# ==========================
# AHAD AI v5.5 WHALE ENGINE
# ==========================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)


# ==========================
# RENDER KEEP ALIVE
# ==========================

app = Flask(__name__)


@app.route("/")
def home():
    return "🐋 AHAD AI v5.5 WHALE ENGINE ONLINE"


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


Thread(
    target=run_web
).start()



# ==========================
# FUTURES SYMBOLS
# ==========================


def get_symbols():

    url = (
        "https://fapi.binance.com"
        "/fapi/v1/exchangeInfo"
    )

    try:

        data = requests.get(
            url,
            timeout=10
        ).json()


        symbols = []


        for s in data.get("symbols", []):

            if (
                s.get("quoteAsset") == "USDT"
                and
                s.get("status") == "TRADING"
            ):

                symbols.append(
                    s["symbol"]
                )


        return symbols[:120]


    except:

        return []



# ==========================
# GET 15M CANDLES
# ==========================


def get_chart(symbol):

    url = (
        "https://fapi.binance.com"
        "/fapi/v1/klines"
    )


    params = {

        "symbol": symbol,

        "interval": "15m",

        "limit": 200

    }


    try:

        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        if not isinstance(
            data,
            list
        ):

            return None


        df = pd.DataFrame(
            data
        )


        df["high"] = (
            df[2]
            .astype(float)
        )

        df["low"] = (
            df[3]
            .astype(float)
        )

        df["close"] = (
            df[4]
            .astype(float)
        )

        df["volume"] = (
            df[5]
            .astype(float)
        )


        return df


    except:

        return None



# ==========================
# ANALYSIS ENGINE
# ==========================


def analyze(symbol):

    try:

        df = get_chart(
            symbol
        )


        if df is None:

            return None


        # EMA TREND

        df["EMA50"] = (
            ta.trend
            .ema_indicator(
                df["close"],
                window=50
            )
        )


        df["EMA200"] = (
            ta.trend
            .ema_indicator(
                df["close"],
                window=200
            )
        )


        # RSI

        df["RSI"] = (
            ta.momentum
            .rsi(
                df["close"],
                window=14
            )
        )


        # MACD

        macd = (
            ta.trend.MACD(
                df["close"]
            )
        )


        df["MACD"] = (
            macd.macd_diff()
        )


        # ATR

        df["ATR"] = (
            ta.volatility
            .average_true_range(
                df["high"],
                df["low"],
                df["close"],
                window=14
            )
        ) 
last = df.iloc[-1]

        score = 0
        reasons = []


        # ==================
        # TREND SCORE
        # ==================

        if last["close"] > last["EMA50"]:
            score += 20
            reasons.append("Trend above EMA50 ✅")


        if last["EMA50"] > last["EMA200"]:
            score += 20
            reasons.append("EMA Bull Trend 🐂")


        # ==================
        # MOMENTUM
        # ==================

        if 40 < last["RSI"] < 65:
            score += 15
            reasons.append("RSI Healthy ✅")


        if last["MACD"] > 0:
            score += 15
            reasons.append("MACD Momentum ✅")


        # ==================
        # WHALE VOLUME
        # ==================

        avg_volume = (
            df["volume"]
            .tail(30)
            .mean()
        )


        volume_power = (
            last["volume"]
            /
            avg_volume
        )


        if volume_power > 1.5:

            score += 30

            reasons.append(
                "Whale Volume 🐋"
            )


        # ==================
        # ENTRY ENGINE
        # ==================

        price = last["close"]

        atr = last["ATR"]


        entry_low = (
            price -
            (atr * 0.3)
        )


        entry_high = (
            price +
            (atr * 0.2)
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


        if score >= 75:

            return {

                "symbol": symbol,

                "score": score,

                "price": price,

                "entry_low": entry_low,

                "entry_high": entry_high,

                "sl": stop_loss,

                "tp1": tp1,

                "tp2": tp2,

                "rsi": last["RSI"],

                "volume": volume_power,

                "reasons": reasons

            }


    except Exception as e:

        print(e)


    return None



# ==========================
# TELEGRAM
# ==========================


@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v5.5 ONLINE

🔥 WHALE ENGINE ACTIVE

⏱ Timeframe:
15 Minutes

Send /scan
"""
    )



@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI hunting whales..."
    )


    signals = []


    for symbol in get_symbols():


        result = analyze(symbol)


        if result:

            signals.append(
                result
            )


        time.sleep(0.05)



    signals = sorted(
        signals,
        key=lambda x:
        x["score"],
        reverse=True
    )[:3]



    if not signals:

        bot.send_message(
            message.chat.id,
            "😴 No whale LONG setup now 🛡️"
        )

        return



    for s in signals:


        text = f"""
🐋 AHAD AI WHALE SIGNAL

🟢 LONG

🪙 Coin:
{s['symbol']}

💰 Current:
{round(s['price'],5)}

🎯 ENTRY ZONE:
{round(s['entry_low'],5)}
-
{round(s['entry_high'],5)}

🛑 STOP LOSS:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

📊 RSI:
{round(s['rsi'],2)}

🐋 Volume Power:
{x:=.2f}

🔥 AHAD SCORE:
{s['score']}/100

Reasons:
{chr(10).join(s['reasons'])}
""".replace("{x:=.2f}", str(round(s["volume"],2)))


        bot.send_message(
            message.chat.id,
            text
        )



# ==========================
# START BOT
# ==========================


print(
    "🐋 AHAD AI v5.5 STARTED"
)


bot.remove_webhook()


bot.infinity_polling(
    skip_pending=True,
    timeout=60
)
