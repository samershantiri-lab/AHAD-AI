import os
import time
import requests
import telebot
import pandas as pd
import ta

from flask import Flask
from threading import Thread


# =========================
# AHAD AI v5.6 SNIPER WHALE
# =========================

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)


# KEEP RENDER ONLINE

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v5.6 ONLINE"


def web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


Thread(target=web).start()


# =========================
# GET MARKET DATA
# =========================

def get_symbols():

    try:

        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        data = requests.get(
            url,
            timeout=10
        ).json()


        symbols = []

        for x in data["symbols"]:

            if (
                x["quoteAsset"] == "USDT"
                and
                x["status"] == "TRADING"
            ):
                symbols.append(x["symbol"])


        return symbols[:100]

    except Exception as e:

        print(e)

        return []



def get_candles(symbol):

    try:

        url = "https://fapi.binance.com/fapi/v1/klines"

        params = {
            "symbol": symbol,
            "interval": "15m",
            "limit": 220
        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        df = pd.DataFrame(data)


        df["high"] = df[2].astype(float)
        df["low"] = df[3].astype(float)
        df["close"] = df[4].astype(float)
        df["volume"] = df[5].astype(float)


        return df


    except:

        return None



# =========================
# AI ANALYSIS
# =========================


def analyze(symbol):

    df = get_candles(symbol)

    if df is None:
        return None


    try:

        df["ema50"] = ta.trend.ema_indicator(
            df["close"],
            50
        )


        df["ema200"] = ta.trend.ema_indicator(
            df["close"],
            200
        )


        df["rsi"] = ta.momentum.rsi(
            df["close"],
            14
        )


        macd = ta.trend.MACD(
            df["close"]
        )

        df["macd"] = macd.macd_diff()


        df["atr"] = ta.volatility.average_true_range(
            df["high"],
            df["low"],
            df["close"]
        )


        last = df.iloc[-1]


        score = 0


        if last.close > last.ema50:
            score += 20


        if last.ema50 > last.ema200:
            score += 20


        if 40 <= last.rsi <= 60:
            score += 20


        if last.macd > 0:
            score += 20


        vol_avg = df.volume.tail(30).mean()

        whale = last.volume / vol_avg


        if whale > 1.3:
            score += 20



        if score < 75:
            return None



        price = last.close

        atr = last.atr


        entry = price

        sl = price - (atr * 1.5)

        risk = entry - sl


        tp1 = entry + (risk * 2)

        tp2 = entry + (risk * 3)


        return {

            "coin":symbol,

            "entry":entry,

            "sl":sl,

            "tp1":tp1,

            "tp2":tp2,

            "rsi":last.rsi,

            "whale":whale,

            "score":score

        }


    except Exception as e:

        print(e)

        return None



# =========================
# TELEGRAM
# =========================


@bot.message_handler(commands=["start"])
def start(m):

    bot.reply_to(
        m,
"""🚀 AHAD AI v5.6 ONLINE

🐋 Whale Engine ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Stop Loss ACTIVE

Send /scan"""
    )



@bot.message_handler(commands=["scan"])
def scan(m):

    bot.reply_to(
        m,
        "🐋 Searching sniper setups..."
    )


    results=[]


    for s in get_symbols():

        r = analyze(s)

        if r:

            results.append(r)


        time.sleep(0.05)



    results = sorted(
        results,
        key=lambda x:x["score"],
        reverse=True
    )[:3]



    if len(results)==0:

        bot.send_message(
            m.chat.id,
            "😴 No sniper LONG setup now 🛡"
        )

        return



    for x in results:

        msg=f"""
🐋 WHALE LONG SIGNAL

🪙 {x['coin']}

📍 ENTRY:
{round(x['entry'],5)}

🎯 TP1:
{round(x['tp1'],5)}

🎯 TP2:
{round(x['tp2'],5)}

🛑 STOP LOSS:
{round(x['sl'],5)}

📊 RSI:
{round(x['rsi'],2)}

🐋 Whale:
{round(x['whale'],2)}X

🔥 AHAD SCORE:
{x['score']}/100
"""

        bot.send_message(
            m.chat.id,
            msg
        )



print("🐋 AHAD AI v5.6 STARTED")


bot.remove_webhook()


bot.infinity_polling(
    skip_pending=True,
    timeout=60
    )
