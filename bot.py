# ==============================
# 🚀 AHAD AI v8.1 - PART 1
# DATA CORE + TRADINGVIEW
# ==============================

import requests
import time
import traceback
import threading
import pandas as pd
import numpy as np

from flask import Flask
import telebot

from tradingview_ta import TA_Handler, Interval


# ==============================
# 🔑 TELEGRAM
# ==============================

TOKEN = "8697535359:AAGlWi6GbtR1XQLlzhC_hoApLcfYiCxQWwg"

bot = telebot.TeleBot(TOKEN)


# ==============================
# 🌐 KEEP ALIVE SERVER
# ==============================

app = Flask(__name__)


@app.route("/")
def home():

    return "🐋 AHAD AI v8.1 ONLINE"


def run_web():

    app.run(
        host="0.0.0.0",
        port=10000
    )


# ==============================
# 📊 GET MARKETS
# ==============================

def get_futures_symbols():

    all_symbols = []


    # 🟨 BINANCE

    try:

        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        data = requests.get(
            url,
            timeout=10
        ).json()


        binance = [
            x["symbol"]
            for x in data["symbols"]
            if x["quoteAsset"] == "USDT"
        ]


        print(
            "🟨 Binance:",
            len(binance)
        )


        all_symbols += binance


    except Exception as e:

        print(
            "❌ Binance Error:",
            e
        )


    # 🟧 BYBIT

    try:

        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"

        data = requests.get(
            url,
            timeout=10
        ).json()


        bybit = [
            x["symbol"]
            for x in data["result"]["list"]
            if "USDT" in x["symbol"]
        ]


        print(
            "🟧 Bybit:",
            len(bybit)
        )


        all_symbols += bybit


    except Exception as e:

        print(
            "❌ Bybit Error:",
            e
        )


    # 🟦 MEXC

    try:

        url = "https://contract.mexc.com/api/v1/contract/detail"

        data = requests.get(
            url,
            timeout=10
        ).json()


        mexc = [
            x["symbol"].replace("_", "")
            for x in data["data"]
        ]


        print(
            "🟦 MEXC:",
            len(mexc)
        )


        all_symbols += mexc


    except Exception as e:

        print(
            "❌ MEXC Error:",
            e
        )


    # REMOVE DUPLICATES

    final = list(
        set(all_symbols)
    )


    print(
        "🐋 TOTAL MARKETS:",
        len(final)
    )


    return final



# ==============================
# 🧠 TRADINGVIEW ENGINE
# ==============================

def tradingview_analysis(symbol):

    try:

        results = {}


        frames = {

            "15m":
            Interval.INTERVAL_15_MINUTES,

            "1H":
            Interval.INTERVAL_1_HOUR,

            "4H":
            Interval.INTERVAL_4_HOURS,

            "1D":
            Interval.INTERVAL_1_DAY

        }


        for name, frame in frames.items():


            handler = TA_Handler(

                symbol=symbol,

                screener="crypto",

                exchange="BINANCE",

                interval=frame

            )


            tv = handler.get_analysis()


            results[name] = {

                "signal":
                tv.summary["RECOMMENDATION"],

                "buy":
                tv.summary["BUY"],

                "sell":
                tv.summary["SELL"]

            }


        return results


    except Exception as e:

        print(
            "❌ TradingView:",
            symbol,
            e
        )


        return None



# ==============================
# 🐋 PRICE DATA
# ==============================

def get_price(symbol):

    try:

        url = (
            "https://api.binance.com/api/v3/ticker/price?symbol="
            + symbol
        )


        data = requests.get(
            url,
            timeout=5
        ).json()


        return float(
            data["price"]
        )


    except:


        return None



# ==============================
# 🧠 START LOG
# ==============================

print(
    "🚀 Starting AHAD AI v8.1"
)

print(
    "🐋 DATA CORE ACTIVE"
)

print(
    "📊 TradingView ACTIVE"
)
# ==============================
# 🧠 AHAD AI v8.0 BRAIN ENGINE
# ==============================

def analyze(symbol):

    try:

        frames = {}

        # ==================
        # LOAD TIMEFRAMES
        # ==================

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



        score = 0

        reasons = []



        # ==================
        # TIMEFRAME ANALYSIS
        # ==================

        weights = {

            "15m": 40,

            "1h": 30,

            "4h": 20,

            "1d": 10

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



            tf_score = 0



            if price > ema50:

                tf_score += 1


            if ema50 > ema100:

                tf_score += 1


            if 35 <= rsi <= 70:

                tf_score += 1


            if macd_power > 0:

                tf_score += 1



            gained = (

                tf_score

                /

                4

                *

                weights[tf]

            )


            score += gained



            if tf_score >= 3:


                reasons.append(

                    f"{tf} Bullish 🟢"

                )



        # ==================
        # ENTRY DATA 15M
        # ==================

        entry_df = frames["15m"]

        close = entry_df["close"]

        price = close.iloc[-1]


        atr = AverageTrueRange(

            entry_df["high"],

            entry_df["low"],

            close,

            window=14

        ).average_true_range().iloc[-1]



        volume_now = (

            entry_df["volume"]

            .iloc[-1]

        )


        volume_avg = (

            entry_df["volume"]

            .tail(30)

            .mean()

        )


        if volume_avg == 0:

            whale = 0


        else:

            whale = (

                volume_now

                /

                volume_avg

            )



        if whale >= 1.3:


            score += 20


            reasons.append(

                "Whale Volume 🐋"

            )



        # ==================
        # EXTERNAL ENGINES
        # ==================

        tv = tradingview_score(symbol)

        cg = coinglass_score(symbol)


        score += tv

        score += cg



        # ==================
        # TARGETS
        # ==================

        stop_loss = (

            price

            -

            atr * 1.5

        )


        risk = (

            price

            -

            stop_loss

        )



        return {


            "coin": symbol,


            "entry": price,


            "sl": stop_loss,


            "tp1": price + risk * 2,


            "tp2": price + risk * 3,


            "score": round(score),


            "rsi": rsi,


            "whale": whale,


            "reasons": reasons


        }



    except Exception as e:


        print(

            "Analyze Error:",

            symbol,

            e

        )


        return None
# ==============================
# 🤖 AHAD AI v8.0 TELEGRAM ENGINE
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v8.0 ONLINE 🐋

🟨 Binance Engine
🟧 Bybit Engine
🟦 MEXC Engine

📊 TradingView Bridge READY
🐋 Coinglass Bridge READY

⏱ Multi Timeframe ACTIVE:
🎯 15m Entry
📈 1H Trend
🐋 4H Power
👑 1D Macro

🧠 AI Brain ACTIVE
🛑 ATR Risk ACTIVE

Send /scan
"""
    )


# ==============================
# 🔍 MANUAL SCANNER
# ==============================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v8.0 SCANNING...

Collecting:
🟨 Binance
🟧 Bybit
🟦 MEXC

Checking:
⏱ 15m
⏱ 1H
⏱ 4H
⏱ 1D
"""
    )


    results = []


    symbols = get_futures_symbols()


    for symbol in symbols[:300]:

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



    # ==================
    # 🚀 SNIPER SIGNAL
    # ==================

    signals = [

        x for x in results

        if x["score"] >= 100

    ][:3]



    if signals:


        for s in signals:


            bot.send_message(
                message.chat.id,
f"""
🚨 AHAD AI v8.0 SIGNAL 🐋

🟢 LONG SETUP FOUND

🪙 Coin:
{s['coin']}

🔥 Power Score:
{s['score']}/120+

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

🐋 Whale Power:
{round(s['whale'],2)}X


⏱ Confirmation:
{chr(10).join(s['reasons'])}
"""
            )



    # ==================
    # 👀 RADAR MODE
    # ==================

    else:


        radar = results[:5]


        text = """
👀 AHAD AI v8.0 RADAR

No SNIPER LONG yet 🛡

Closest setups:
"""


        if radar:


            for r in radar:


                text += f"""

🪙 {r['coin']}

🔥 Score:
{r['score']}

📊 RSI:
{round(r['rsi'],2)}

🐋 Whale:
{round(r['whale'],2)}X

⏱ Trend:
{chr(10).join(r['reasons'])}

━━━━━━━━━━
"""


        else:


            text += """

⚠️ No market data

Checking sources...
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
                "🤖 Telegram Engine ACTIVE"
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
    "🔥 AHAD AI v8.0 FULL ONLINE"
)


while True:

    time.sleep(60)
