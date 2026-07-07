# ==============================
# 🚀 AHAD AI v8.2 CLEAN BUILD
# BYBIT + MEXC + TRADINGVIEW
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

from tradingview_ta import TA_Handler, Interval


# ==============================
# 🔑 CONFIG
# ==============================

TOKEN = os.environ.get("BOT_TOKEN")

if TOKEN is None:
    raise Exception("BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)


print("🚀 AHAD AI v8.2 STARTING")
print("🐋 CLEAN ENGINE LOADING")


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

app = Flask(__name__)


@app.route("/")
def home():

    return "🐋 AHAD AI v8.2 ONLINE"


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
# 🟧 BYBIT SYMBOLS
# ==============================

def bybit_symbols():

    try:

        url = (
            "https://api.bybit.com"
            "/v5/market/instruments-info"
        )

        params = {
            "category":"linear"
        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        coins = []


        for s in data["result"]["list"]:

            if s["symbol"].endswith("USDT"):

                coins.append(
                    s["symbol"]
                )


        print(
            "🟧 BYBIT:",
            len(coins)
        )


        return coins


    except Exception as e:

        print(
            "BYBIT ERROR:",
            e
        )

        return []



# ==============================
# 🟦 MEXC SYMBOLS
# ==============================

def mexc_symbols():

    try:

        url = (
            "https://contract.mexc.com"
            "/api/v1/contract/detail"
        )


        data = requests.get(
            url,
            timeout=10
        ).json()


        coins = []


        for s in data["data"]:

            if s["quoteCoin"] == "USDT":

                coins.append(
                    s["symbol"].replace("_","")
                )


        print(
            "🟦 MEXC:",
            len(coins)
        )


        return coins


    except Exception as e:

        print(
            "MEXC ERROR:",
            e
        )

        return []



# ==============================
# 🐋 MARKET ENGINE
# ==============================

def get_futures_symbols():

    coins = []

    coins += bybit_symbols()

    coins += mexc_symbols()


    coins = list(
        set(coins)
    )


    print(
        "🐋 TOTAL:",
        len(coins)
    )


    return coins



# ==============================
# 📊 BYBIT CANDLES
# ==============================

def get_candles(symbol, interval):

    try:

        frames = {
            "15m":"15",
            "1h":"60",
            "4h":"240",
            "1d":"D"
        }


        url = (
            "https://api.bybit.com"
            "/v5/market/kline"
        )


        params = {

            "category":"linear",

            "symbol":symbol,

            "interval":frames[interval],

            "limit":200

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        if data["retCode"] != 0:

            return None


        df = pd.DataFrame(
            data["result"]["list"]
        )


        df = df.iloc[:,1:6]


        df.columns = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]


        return df.astype(float)


    except Exception as e:

        print(
            "CANDLE ERROR:",
            symbol,
            e
        )

        return None
        # ==============================
# 📊 TRADINGVIEW SCORE
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


        signal = tv.summary["RECOMMENDATION"]


        if signal == "STRONG_BUY":

            return 30


        if signal == "BUY":

            return 15


        return 0


    except Exception as e:

        print(
            "TV ERROR:",
            symbol,
            e
        )

        return 0



# ==============================
# 🧠 ANALYSIS ENGINE
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


            if df is None or len(df) < 60:

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
                close
            ).rsi().iloc[-1]


            macd = MACD(close)

            macd_power = (
                macd.macd().iloc[-1]
                -
                macd.macd_signal().iloc[-1]
            )


            ok = 0


            if price > ema50:
                ok += 1


            if ema50 > ema100:
                ok += 1


            if 35 <= rsi <= 70:
                ok += 1


            if macd_power > 0:
                ok += 1



            score += (
                ok / 4
                *
                weights[tf]
            )


            if ok >= 3:

                reasons.append(
                    tf + " Bullish 🟢"
                )



        entry_df = frames["15m"]

        close = entry_df["close"]

        price = close.iloc[-1]


        atr = AverageTrueRange(
            entry_df["high"],
            entry_df["low"],
            close
        ).average_true_range().iloc[-1]


        whale = (
            entry_df["volume"].iloc[-1]
            /
            entry_df["volume"].tail(30).mean()
        )


        if whale >= 1.3:

            score += 20

            reasons.append(
                "Whale Volume 🐋"
            )



        tv_score = tradingview_score(symbol)

        score += tv_score


        if tv_score > 0:

            reasons.append(
                "TradingView Confirmed 📊"
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
            "ANALYZE ERROR:",
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
🚀 AHAD AI v8.2 ONLINE 🐋

🟧 Bybit Engine
🟦 MEXC Hunter
📊 TradingView Confirm

⏱ 15m | 1H | 4H | 1D

Send /scan
"""
    )



@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI scanning..."
    )


    results = []


    for symbol in get_futures_symbols()[:300]:

        result = analyze(symbol)


        if result:

            results.append(result)


        time.sleep(0.03)



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
🚀 AHAD AI SIGNAL 🐋

🪙 {s['coin']}

🔥 Score:
{s['score']}

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

✅
{chr(10).join(s['reasons'])}
"""
        )



# ==============================
# 🚀 START SYSTEM
# ==============================

threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=lambda:
    bot.infinity_polling(
        skip_pending=True
    ),
    daemon=True
).start()


print(
    "🔥 AHAD AI v8.2 FULL ONLINE"
)


while True:

    time.sleep(60)
