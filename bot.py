# ==============================
# 🚀 AHAD AI v8.3 - PART 1
# BYBIT + OKX DATA CORE
# ==============================

import requests
import time
import traceback
import threading

import pandas as pd
import numpy as np

from flask import Flask
import telebot

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from tradingview_ta import TA_Handler, Interval


# ==============================
# 🔑 TELEGRAM TOKEN
# ==============================

TOKEN = "8697535359:AAGlWi6GbtR1XQLlzhC_hoApLcfYiCxQWwg"

bot = telebot.TeleBot(TOKEN)


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v8.3 ONLINE"


def run_web():

    app.run(
        host="0.0.0.0",
        port=10000
    )


# ==============================
# 🟧 BYBIT SYMBOLS
# ==============================

def get_symbols():

    symbols = []

    try:

        url = (
        "https://api.bybit.com/v5/market/instruments-info"
        "?category=linear"
        )

        data = requests.get(
            url,
            timeout=10
        ).json()


        for x in data["result"]["list"]:

            if x["quoteCoin"] == "USDT":

                symbols.append(
                    x["symbol"]
                )


        print(
            "🟧 BYBIT MARKETS:",
            len(symbols)
        )


    except Exception as e:

        print(
            "❌ BYBIT ERROR",
            e
        )


    return symbols



# ==============================
# 🟧 BYBIT CANDLES
# ==============================

def get_candles(symbol, tf):

    try:

        convert = {

            "15m":"15",
            "1h":"60",
            "4h":"240",
            "1d":"D"

        }


        url = (
        "https://api.bybit.com/v5/market/kline"
        )


        params = {

            "category":"linear",
            "symbol":symbol,
            "interval":convert[tf],
            "limit":200

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()



        candles = data["result"]["list"]


        df = pd.DataFrame(
            candles
        )


        df = df.iloc[:,0:6]


        df.columns = [

            "time",
            "open",
            "high",
            "low",
            "close",
            "volume"

        ]


        for c in [

            "open",
            "high",
            "low",
            "close",
            "volume"

        ]:

            df[c] = pd.to_numeric(
                df[c]
            )


        df = df[::-1]


        return df



    except Exception as e:


        print(
            "❌ Candle Error:",
            symbol,
            e
        )


        return None



# ==============================
# ⬛ OKX CHECK ENGINE
# ==============================

def okx_check(symbol):

    try:

        okx_symbol = (
            symbol
            .replace("USDT","-USDT-SWAP")
        )


        url = (
        "https://www.okx.com/api/v5/market/ticker"
        )


        data = requests.get(

            url,

            params={
                "instId":okx_symbol
            },

            timeout=5

        ).json()



        if data["data"]:

            return True


        return False



    except:


        return False



# ==============================
# 📊 TRADINGVIEW ENGINE
# ==============================

def tradingview_score(symbol):

    try:

        handler = TA_Handler(

            symbol=symbol,
            screener="crypto",
            exchange="BYBIT",
            interval=Interval.INTERVAL_1_HOUR

        )


        tv = handler.get_analysis()


        if tv.summary["RECOMMENDATION"] == "BUY":

            return 15


        if tv.summary["RECOMMENDATION"] == "STRONG_BUY":

            return 25


        return 0



    except:

        return 0



# ==============================
# 🐋 START LOG
# ==============================

print("🚀 AHAD AI v8.3 STARTING")

print("🟧 BYBIT ENGINE ACTIVE")

print("⬛ OKX CONFIRM ACTIVE")

print("📊 TRADINGVIEW ACTIVE")

# ==============================
# 📊 TRADINGVIEW ENGINE
# ==============================

def tradingview_score(symbol):

    try:

        tv = TA_Handler(
            symbol=symbol,
            screener="crypto",
            exchange="BYBIT",
            interval=Interval.INTERVAL_1_HOUR
        )

        result = tv.get_analysis()

        signal = result.summary["RECOMMENDATION"]


        if signal == "STRONG_BUY":

            return 20


        if signal == "BUY":

            return 10


        return 0


    except Exception:

        return 0



# ==============================
# 🧠 AHAD AI BRAIN
# ==============================

def analyze(symbol):

    try:

        score = 0

        reasons = []

        frames = {}


        for tf in [
            "15m",
            "1h",
            "4h",
            "1d"
        ]:

            df = get_candles(
                symbol,
                tf
            )


            if df is None or len(df) < 100:

                return None


            frames[tf] = df



        weights = {

            "15m":40,
            "1h":30,
            "4h":20,
            "1d":10

        }



        for tf, df in frames.items():


            close = df["close"]

            price = close.iloc[-1]


            ema50 = EMAIndicator(
                close,
                window=50
            ).ema_indicator().iloc[-1]


            ema100 = EMAIndicator(
                close,
                window=100
            ).ema_indicator().iloc[-1]


            rsi = RSIIndicator(
                close,
                window=14
            ).rsi().iloc[-1]


            macd = MACD(close)


            macd_power = (
                macd.macd().iloc[-1]
                -
                macd.macd_signal().iloc[-1]
            )


            power = 0


            if price > ema50:

                power += 1


            if ema50 > ema100:

                power += 1


            if 35 <= rsi <= 70:

                power += 1


            if macd_power > 0:

                power += 1



            score += (
                power / 4
                *
                weights[tf]
            )


            if power >= 3:

                reasons.append(
                    tf + " BULLISH 🟢"
                )



        entry = frames["15m"]

        price = entry["close"].iloc[-1]


        atr = AverageTrueRange(
            entry["high"],
            entry["low"],
            entry["close"],
            window=14
        ).average_true_range().iloc[-1]



        whale = (
            entry["volume"].iloc[-1]
            /
            entry["volume"].tail(30).mean()
        )


        if whale >= 1.5:

            score += 20

            reasons.append(
                "Whale Volume 🐋"
            )



        # OKX
        if okx_check(symbol):

            score += 10

            reasons.append(
                "OKX Confirm ⬛"
            )



        # TradingView
        tv = tradingview_score(symbol)

        score += tv


        if tv:

            reasons.append(
                "TradingView 📊"
            )



        sl = price - atr * 1.5

        risk = price - sl



        return {

            "coin":symbol,
            "entry":price,
            "sl":sl,
            "tp1":price + risk*2,
            "tp2":price + risk*3,
            "score":round(score),
            "rsi":rsi,
            "whale":whale,
            "reasons":reasons

        }



    except Exception as e:

        print(
            "ANALYZE ERROR",
            symbol,
            e
        )

        return None



# ==============================
# 🤖 TELEGRAM
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v8.3 ONLINE 🐋

🟧 Bybit DATA
⬛ OKX Confirm
📊 TradingView

⏱ 15m | 1H | 4H | 1D

Send /scan
"""
    )



@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI v8.3 SCANNING..."
    )


    results = []


    for symbol in get_symbols()[:200]:


        x = analyze(symbol)


        if x:

            results.append(x)


        time.sleep(0.05)



    results = sorted(
        results,
        key=lambda x:x["score"],
        reverse=True
    )


    if not results:

        bot.send_message(
            message.chat.id,
            "⚠️ No market data"
        )

        return



    for s in results[:3]:

        bot.send_message(
            message.chat.id,
f"""
🚀 LONG HUNTER FOUND 🐋

🪙 {s['coin']}

🔥 SCORE:
{s['score']}

🎯 ENTRY:
{round(s['entry'],5)}

🛑 SL:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

📊 RSI:
{round(s['rsi'],2)}

🐋 Whale:
{round(s['whale'],2)}X

{chr(10).join(s['reasons'])}
"""
        )



# ==============================
# 🚀 RUN
# ==============================

threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=bot.infinity_polling,
    daemon=True
).start()


print("🔥 AHAD AI v8.3 FULL ONLINE")


while True:

    time.sleep(60)
