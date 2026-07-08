# =====================================
# 🚀 AHAD AI v8.4 - PART 1
# BYBIT CORE + OKX + TRADINGVIEW
# =====================================

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


# =====================================
# 🔑 TELEGRAM TOKEN
# =====================================

TOKEN = "8697535359:AAGlWi6GbtR1XQLlzhC_hoApLcfYiCxQWwg"

bot = telebot.TeleBot(TOKEN)



# =====================================
# 🌐 RENDER KEEP ALIVE
# =====================================

app = Flask(__name__)


@app.route("/")
def home():

    return "🐋 AHAD AI v8.4 ONLINE"


def run_web():

    app.run(
        host="0.0.0.0",
        port=10000
    )



# =====================================
# 🟧 BYBIT MARKET LIST
# =====================================

def get_symbols():

    try:

        url = (
            "https://api.bybit.com/v5/market/instruments-info"
        )


        params = {

            "category":"linear"

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        symbols = []


        for coin in data["result"]["list"]:

            if coin["quoteCoin"] == "USDT":

                symbols.append(
                    coin["symbol"]
                )


        print(
            "🟧 BYBIT MARKETS:",
            len(symbols)
        )


        return symbols


    except Exception as e:


        print(
            "❌ BYBIT SYMBOL ERROR:",
            e
        )


        return []



# =====================================
# 🟧 BYBIT CANDLES ENGINE
# =====================================

def get_candles(symbol, timeframe):

    try:

        tf = {

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

            "interval":tf[timeframe],

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



        for x in [

            "open",

            "high",

            "low",

            "close",

            "volume"

        ]:

            df[x] = pd.to_numeric(
                df[x]
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



# =====================================
# ⬛ OKX CONFIRM ENGINE
# =====================================

def okx_confirm(symbol):

    try:


        okx_symbol = (
            symbol.replace(
                "USDT",
                "-USDT-SWAP"
            )
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



        if len(data["data"]) > 0:

            return 10


        return 0



    except:


        return 0



# =====================================
# 📊 TRADINGVIEW ENGINE
# =====================================

def tradingview_score(symbol):

    try:


        total = 0


        frames = [

            Interval.INTERVAL_15_MINUTES,

            Interval.INTERVAL_1_HOUR,

            Interval.INTERVAL_4_HOURS,

            Interval.INTERVAL_1_DAY

        ]


        for frame in frames:


            handler = TA_Handler(

                symbol=symbol,

                screener="crypto",

                exchange="BYBIT",

                interval=frame

            )


            result = handler.get_analysis()


            signal = result.summary[
                "RECOMMENDATION"
            ]


            if signal == "BUY":

                total += 5


            if signal == "STRONG_BUY":

                total += 10



        return total



    except Exception as e:


        print(
            "TV ERROR:",
            symbol,
            e
        )


        return 0



# =====================================
# 🔗 OLD SYSTEM BRIDGE
# =====================================

def get_futures_symbols():

    return get_symbols()



def coinglass_score(symbol):

    return 0



# =====================================
# 🐋 START LOG
# =====================================

print("🚀 AHAD AI v8.4 STARTING")

print("🟧 BYBIT CORE ACTIVE")

print("⬛ OKX CONFIRM ACTIVE")

print("📊 TRADINGVIEW ACTIVE")

# =====================================
# 🧠 AHAD AI v8.4 BRAIN ENGINE
# =====================================

def analyze(symbol):

    try:

        frames = {}

        for tf in ["15m","1h","4h","1d"]:

            df = get_candles(symbol, tf)

            if df is None or len(df) < 100:
                return None

            frames[tf] = df


        score = 0
        reasons = []


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
            ) * weights[tf]


            if power >= 3:

                reasons.append(
                    tf + " Bullish 🟢"
                )



        # 🐋 WHALE ENGINE

        df = frames["15m"]

        volume_now = df["volume"].iloc[-1]

        volume_avg = (
            df["volume"]
            .tail(30)
            .mean()
        )


        whale = (
            volume_now / volume_avg
            if volume_avg > 0
            else 0
        )


        if whale >= 1.3:

            score += 20

            reasons.append(
                "Whale Volume 🐋"
            )



        # 📊 EXTERNAL CONFIRM

        score += tradingview_score(symbol)

        score += okx_confirm(symbol)



        # 🎯 ENTRY

        price = df["close"].iloc[-1]


        atr = AverageTrueRange(

            df["high"],
            df["low"],
            df["close"],
            window=14

        ).average_true_range().iloc[-1]


        sl = price - atr * 1.5

        risk = price - sl



        return {

            "coin":symbol,

            "entry":price,

            "sl":sl,

            "tp1":price + risk * 2,

            "tp2":price + risk * 3,

            "score":round(score),

            "rsi":rsi,

            "whale":whale,

            "reasons":reasons

        }


    except Exception as e:

        print(
            "Analyze Error:",
            symbol,
            e
        )

        return None

# =====================================
# 🤖 AHAD AI v8.4 TELEGRAM ENGINE
# =====================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v8.4 ONLINE 🐋

🟧 Bybit Core Engine
⬛ OKX Confirmation
📊 TradingView Multi-Timeframe

⏱ Timeframes:
🎯 15m Entry
📈 1H Trend
🐋 4H Power
👑 1D Macro

🧠 Smart Brain ACTIVE
🐋 Whale Scanner ACTIVE

Send /scan
"""
    )


# =====================================
# 🔍 SCANNER
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v8.4 SCANNING...

🟧 Loading Bybit Data
⬛ Checking OKX
📊 Reading TradingView
"""
    )


    results = []


    symbols = get_symbols()


    print(
        "🔍 SCANNING:",
        len(symbols)
    )


    for symbol in symbols[:200]:

        try:

            result = analyze(symbol)


            if result:

                results.append(result)


            time.sleep(0.05)


        except Exception as e:

            print(
                "SCAN ERROR:",
                symbol,
                e
            )


    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )


    if not results:

        bot.send_message(
            message.chat.id,
            "⚠️ No market data"
        )

        return



    for s in results[:5]:

        bot.send_message(
            message.chat.id,
f"""
🚀 AHAD AI LONG HUNTER 🐋

🪙 Coin:
{s['coin']}

🔥 Score:
{s['score']}/150

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


✅ Confirmations:
{chr(10).join(s['reasons'])}
"""
        )



# =====================================
# 🛡 TELEGRAM AUTO RECOVERY
# =====================================

def telegram_engine():

    while True:

        try:

            print(
                "🤖 TELEGRAM ACTIVE"
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
                "🔄 Restart Telegram..."
            )


            time.sleep(5)



# =====================================
# 🚀 START SYSTEM
# =====================================

threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=telegram_engine,
    daemon=True
).start()


print(
    "🔥 AHAD AI v8.4 FULL ONLINE"
)


while True:

    time.sleep(60)
