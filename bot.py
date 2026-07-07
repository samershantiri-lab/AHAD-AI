# ==============================
# 🚀 AHAD AI v7.1
# MULTI SOURCE AI SCANNER
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
# 🤖 TELEGRAM CONFIG
# ==============================

TOKEN = os.environ.get("BOT_TOKEN")

if TOKEN is None:
    raise Exception("BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)

print("🚀 Starting AHAD AI v7.1")
print("🐋 Multi Source Engine ACTIVE")


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

app = Flask(__name__)

@app.route("/")
def home():

    return "🚀 AHAD AI v7.1 ONLINE 🐋"


def run_web():

    port = int(os.environ.get("PORT",10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# ==============================
# 🟨 BINANCE FUTURES
# ==============================

def binance_symbols():

    try:

        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        data = requests.get(
            url,
            timeout=10
        ).json()

        result = []

        for s in data.get("symbols", []):

            if (
                s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
            ):

                result.append(
                    {
                        "symbol":s["symbol"],
                        "source":"BINANCE"
                    }
                )


        print("🟨 Binance:",len(result))

        return result


    except Exception as e:

        print("Binance Error:",e)

        return []



# ==============================
# 🟧 BYBIT FUTURES
# ==============================

def bybit_symbols():

    try:

        url="https://api.bybit.com/v5/market/instruments-info"

        params={
            "category":"linear"
        }

        data=requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        result=[]


        for s in data["result"]["list"]:

            if s["quoteCoin"]=="USDT":

                result.append(
                    {
                        "symbol":s["symbol"],
                        "source":"BYBIT"
                    }
                )


        print("🟧 Bybit:",len(result))


        return result


    except Exception as e:

        print("Bybit Error:",e)

        return []



# ==============================
# 🟦 MEXC FUTURES
# ==============================

def mexc_symbols():

    try:

        url="https://contract.mexc.com/api/v1/contract/detail"


        data=requests.get(
            url,
            timeout=10
        ).json()


        result=[]


        for s in data["data"]:

            if s["quoteCoin"]=="USDT":

                result.append(
                    {
                        "symbol":s["symbol"].replace("_",""),
                        "source":"MEXC"
                    }
                )


        print("🟦 MEXC:",len(result))


        return result


    except Exception as e:

        print("MEXC Error:",e)

        return []



# ==============================
# 🐋 MERGE SOURCES
# ==============================

def get_futures_symbols():

    markets=[]

    markets += binance_symbols()
    markets += bybit_symbols()
    markets += mexc_symbols()


    clean={}


    for m in markets:

        clean[m["symbol"]] = m


    final=list(clean.values())


    print(
        "🐋 TOTAL MARKETS:",
        len(final)
    )


    return final
# ==============================
# 📊 GET CANDLES
# ==============================

def get_candles(market):

    try:

        symbol = market["symbol"]
        source = market["source"]


        if source == "BINANCE":

            url = "https://fapi.binance.com/fapi/v1/klines"

            params = {
                "symbol":symbol,
                "interval":"15m",
                "limit":150
            }

            data = requests.get(
                url,
                params=params,
                timeout=10
            ).json()


            candles = [
                [x[1],x[2],x[3],x[4],x[5]]
                for x in data
            ]


        elif source == "BYBIT":

            url = "https://api.bybit.com/v5/market/kline"

            params = {
                "category":"linear",
                "symbol":symbol,
                "interval":"15",
                "limit":150
            }

            data = requests.get(
                url,
                params=params,
                timeout=10
            ).json()


            candles = [
                [x[1],x[2],x[3],x[4],x[5]]
                for x in data["result"]["list"]
            ]


        else:

            return None



        df = pd.DataFrame(
            candles,
            columns=[
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )


        return df.astype(float)


    except Exception as e:

        print(
            "Candle Error:",
            e
        )

        return None



# ==============================
# 🧠 ANALYSIS ENGINE
# ==============================

def analyze(market):

    try:

        df = get_candles(market)

        if df is None or len(df) < 60:
            return None


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


        atr = AverageTrueRange(
            df["high"],
            df["low"],
            close,
            window=14
        ).average_true_range().iloc[-1]


        whale = (
            df["volume"].iloc[-1]
            /
            df["volume"].tail(30).mean()
        )


        score = 0
        reasons = []


        if price > ema50:
            score += 20
            reasons.append("EMA Bullish ✅")


        if ema50 > ema100:
            score += 20
            reasons.append("Trend UP 🟢")


        if 35 <= rsi <= 70:
            score += 20
            reasons.append("RSI Healthy 🎯")


        if macd_power > 0:
            score += 20
            reasons.append("MACD Power 📈")


        if whale >= 1:
            score += 20
            reasons.append("Whale Volume 🐋")


        sl = price - atr * 1.5

        risk = price - sl


        return {

            "coin":market["symbol"],
            "source":market["source"],

            "entry":price,

            "sl":sl,

            "tp1":price + risk*2,

            "tp2":price + risk*3,

            "score":score,

            "rsi":rsi,

            "whale":whale,

            "reasons":reasons

        }


    except Exception as e:

        print("Analyze Error:",e)

        return None
# ==============================
# 🤖 TELEGRAM COMMANDS
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v7.1 ONLINE 🐋

🟨 Binance
🟧 Bybit
🟦 MEXC

📊 Multi Source Scanner ACTIVE
🐋 Whale Engine ACTIVE
🟢 LONG Hunter ACTIVE
⏱ Timeframe: 15m
🎯 Smart Entry ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI scanning market...

Collecting data:
🟨 Binance
🟧 Bybit
🟦 MEXC
"""
    )


    results = []


    markets = get_futures_symbols()


    for market in markets[:300]:

        try:

            result = analyze(market)

            if result:

                results.append(result)


            time.sleep(0.03)


        except Exception as e:

            print(
                "Scan Error:",
                e
            )



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

            bot.send_message(
                message.chat.id,
f"""
🚨 AHAD AI SIGNAL 🐋

🟢 LONG SETUP

🪙 Coin:
{s['coin']}

📡 Source:
{s['source']}

🔥 Score:
{s['score']}/100

🎯 Entry:
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


✅ Reasons:
{chr(10).join(s['reasons'])}
"""
            )


    else:


        text = """
👀 AHAD AI RADAR

No perfect LONG yet 🛡

Closest setups:
"""


        for r in results[:5]:

            text += f"""

🪙 {r['coin']}

📡 Source:
{r['source']}

🔥 Score:
{r['score']}/100

📊 RSI:
{round(r['rsi'],2)}

🐋 Whale:
{round(r['whale'],2)}X

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
                "🤖 Telegram ACTIVE"
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
                "🔄 Restarting Telegram"
            )


            time.sleep(5)



# ==============================
# 🚀 START AHAD AI
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
    "🔥 AHAD AI v7.1 FULL ONLINE"
)


while True:

    time.sleep(60)
