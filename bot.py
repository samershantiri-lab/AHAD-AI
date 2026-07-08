# =====================================
# 🚀 AHAD AI v9.0 - PART 1
# OKX PURE DATA CORE
# =====================================

import os
import requests
import time
import traceback
import threading

import pandas as pd

from flask import Flask
import telebot

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange


# =====================================
# 🔑 TELEGRAM TOKEN (RENDER)
# =====================================

TOKEN = os.environ.get("BOT_TOKEN")

if TOKEN is None:

    raise Exception(
        "❌ BOT_TOKEN NOT FOUND"
    )


bot = telebot.TeleBot(TOKEN)



# =====================================
# 🌐 RENDER KEEP ALIVE
# =====================================

app = Flask(__name__)


@app.route("/")
def home():

    return "🐋 AHAD AI v9.0 OKX ONLINE"



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



# =====================================
# ⬛ OKX FUTURES SYMBOLS
# =====================================

def get_symbols():

    try:

        url = (
            "https://www.okx.com"
            "/api/v5/public/instruments"
        )


        params = {

            "instType": "SWAP"

        }


        data = requests.get(

            url,

            params=params,

            timeout=15

        ).json()



        symbols = []



        for coin in data["data"]:



            if (

                coin.get("settleCcy") == "USDT"

                and

                coin.get("state") == "live"

            ):



                symbols.append(

                    coin["instId"]

                )



        print(

            "⬛ OKX MARKETS:",

            len(symbols)

        )



        return symbols



    except Exception as e:


        print(

            "❌ OKX SYMBOL ERROR:",

            e

        )


        return []




# =====================================
# ⬛ OKX CANDLE ENGINE
# =====================================

def get_candles(symbol, tf):


    try:


        frames = {

            "15m": "15m",

            "1h": "1H",

            "4h": "4H",

            "1d": "1D"

        }



        url = (

            "https://www.okx.com"

            "/api/v5/market/candles"

        )



        params = {


            "instId": symbol,


            "bar": frames[tf],


            "limit": 200


        }



        data = requests.get(

            url,

            params=params,

            timeout=10

        ).json()



        candles = data["data"]



        if len(candles) == 0:


            return None



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



        for col in [

            "open",

            "high",

            "low",

            "close",

            "volume"

        ]:


            df[col] = pd.to_numeric(

                df[col]

            )



        # ترتيب الشموع

        df = df[::-1]



        return df



    except Exception as e:


        print(

            "❌ OKX CANDLE ERROR:",

            symbol,

            e

        )


        return None


# =====================================
# 🐋 START LOG
# =====================================

print(
    "🚀 AHAD AI v9.0 STARTING"
)

print(
    "⬛ OKX DATA CORE ACTIVE"
)

# =====================================
# 🧠 AHAD AI v9.0 - PART 2
# SMART BRAIN ENGINE
# =====================================


def analyze(symbol):

    try:

        score = 0
        reasons = []

        frames = {}


        # =============================
        # LOAD OKX MULTI TIMEFRAME
        # =============================

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


            # دعم العملات الجديدة

            if df is not None and len(df) >= 50:


                frames[tf] = df



        if len(frames) == 0:


            return None



        # =============================
        # TIMEFRAME WEIGHTS
        # =============================


        weights = {

            "15m": 40,

            "1h": 30,

            "4h": 20,

            "1d": 10

        }



        last_rsi = 0



        # =============================
        # INDICATOR ENGINE
        # =============================


        for tf, df in frames.items():



            close = df["close"]


            price = close.iloc[-1]



            ema20 = EMAIndicator(

                close,

                window=20

            ).ema_indicator().iloc[-1]



            ema50 = EMAIndicator(

                close,

                window=50

            ).ema_indicator().iloc[-1]



            rsi = RSIIndicator(

                close,

                window=14

            ).rsi().iloc[-1]



            last_rsi = rsi



            macd = MACD(close)



            macd_power = (

                macd.macd().iloc[-1]

                -

                macd.macd_signal().iloc[-1]

            )



            power = 0



            if price > ema20:


                power += 1



            if ema20 > ema50:


                power += 1



            if 30 <= rsi <= 75:


                power += 1



            if macd_power > 0:


                power += 1




            score += (

                power / 4

            ) * weights[tf]




            if power >= 3:


                reasons.append(

                    tf.upper()

                    +

                    " Trend 🟢"

                )




        # =============================
        # ENTRY FRAME
        # =============================


        if "15m" in frames:


            entry_df = frames["15m"]


        else:


            entry_df = list(

                frames.values()

            )[0]



        price = (

            entry_df["close"]

            .iloc[-1]

        )




        # =============================
        # ATR RISK
        # =============================


        atr = AverageTrueRange(


            entry_df["high"],

            entry_df["low"],

            entry_df["close"],

            window=14


        ).average_true_range().iloc[-1]




        # =============================
        # 🐋 WHALE VOLUME
        # =============================


        volume_now = (

            entry_df["volume"]

            .iloc[-1]

        )



        volume_avg = (

            entry_df["volume"]

            .tail(30)

            .mean()

        )



        if volume_avg > 0:


            whale = (

                volume_now

                /

                volume_avg

            )


        else:


            whale = 0




        if whale >= 1.2:


            score += 20



            reasons.append(

                "OKX Whale Volume 🐋"

            )




        # =============================
        # TARGETS
        # =============================


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


            "rsi": last_rsi,


            "whale": whale,


            "reasons": reasons


        }




    except Exception as e:


        print(

            "ANALYZE ERROR:",

            symbol,

            e

        )



        return None

# =====================================
# 🤖 AHAD AI v9.0 - PART 3
# TELEGRAM ENGINE
# =====================================


@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v9.0 ONLINE 🐋

⬛ OKX PURE DATA CORE

⏱ TIMEFRAMES:
🎯 15m Entry
📈 1H Trend
🐋 4H Smart Money
👑 1D Macro

🧠 AI Brain ACTIVE
🐋 Whale Engine ACTIVE

Send /scan
"""
    )



# =====================================
# 🔍 MARKET SCANNER
# =====================================


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v9.0 SCANNING...

⬛ Loading OKX Futures
🧠 Running AI Brain...

Please wait...
"""
    )


    results = []


    symbols = get_symbols()


    bot.send_message(
        message.chat.id,
        f"⬛ OKX Markets Loaded: {len(symbols)}"
    )


    print(
        "⬛ SCANNING:",
        len(symbols)
    )



    for symbol in symbols[:250]:

        try:


            result = analyze(
                symbol
            )


            if result:


                results.append(
                    result
                )



            time.sleep(
                0.03
            )



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



    # =============================
    # 🚀 BEST SIGNALS
    # =============================


    signals = [

        x for x in results

        if x["score"] >= 80

    ][:5]



    if signals:



        for s in signals:



            bot.send_message(

                message.chat.id,

f"""
🚀 AHAD AI v9.0 SIGNAL 🐋

🟢 LONG SETUP

🪙 COIN:
{s['coin']}

🔥 SCORE:
{s['score']}/120


🎯 ENTRY:
{round(s['entry'],6)}

🛑 STOP LOSS:
{round(s['sl'],6)}

🎯 TP1:
{round(s['tp1'],6)}

🎯 TP2:
{round(s['tp2'],6)}


📊 RSI:
{round(s['rsi'],2)}

🐋 WHALE:
{round(s['whale'],2)}X


✅ CONFIRM:
{chr(10).join(s['reasons'])}
"""

            )



    # =============================
    # 👀 RADAR MODE
    # =============================


    else:


        text = """
👀 AHAD AI v9.0 RADAR

No perfect LONG yet 🛡

Closest OKX setups:
"""



        for r in results[:5]:



            text += f"""

🪙 {r['coin']}

🔥 SCORE:
{r['score']}

📊 RSI:
{round(r['rsi'],2)}

🐋 WHALE:
{round(r['whale'],2)}X

📈:
{chr(10).join(r['reasons'])}

━━━━━━━━━━
"""



        if len(results) == 0:


            text += """

⚠️ No market data

Check OKX connection
"""



        bot.send_message(

            message.chat.id,

            text

        )




# =====================================
# 🛡 AUTO RECOVERY
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

                "🔄 Restart Telegram"

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
    "🔥 AHAD AI v9.0 OKX FULL ONLINE 🐋"
)



while True:

    time.sleep(60)
