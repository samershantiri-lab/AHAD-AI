# =====================================
# 🚀 AHAD AI v8.5 - PART 1
# BYBIT CORE + OKX + TRADINGVIEW
# =====================================

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

from tradingview_ta import TA_Handler, Interval


# =====================================
# 🔑 TELEGRAM
# =====================================

TOKEN = "8697535359:AAGlWi6GbtR1XQLlzhC_hoApLcfYiCxQWwg"

bot = telebot.TeleBot(TOKEN)


# =====================================
# 🌐 RENDER KEEP ALIVE
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v8.5 ONLINE"


def run_web():

    app.run(
        host="0.0.0.0",
        port=10000
    )


# =====================================
# 🟧 BYBIT SYMBOL ENGINE FIXED
# =====================================

def get_symbols():

    symbols = []

    try:

        url = "https://api.bybit.com/v5/market/instruments-info"

        params = {
            "category": "linear"
        }

        data = requests.get(
            url,
            params=params,
            timeout=15
        ).json()


        markets = data["result"]["list"]


        for m in markets:

            if (
                m.get("quoteCoin") == "USDT"
                and
                m.get("status") == "Trading"
            ):

                symbols.append(
                    m["symbol"]
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

def get_candles(symbol, tf):

    try:

        frames = {

            "15m": "15",
            "1h": "60",
            "4h": "240",
            "1d": "D"

        }


        url = "https://api.bybit.com/v5/market/kline"


        params = {

            "category": "linear",
            "symbol": symbol,
            "interval": frames[tf],
            "limit": 200

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        candles = data["result"]["list"]


        if len(candles) == 0:
            return None


        df = pd.DataFrame(candles)


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

            df[c] = pd.to_numeric(df[c])


        df = df[::-1]


        return df


    except Exception as e:

        print(
            "❌ Candle ERROR:",
            symbol,
            e
        )

        return None


# =====================================
# ⬛ OKX CONFIRM
# =====================================

def okx_confirm(symbol):

    try:

        okx = symbol.replace(
            "USDT",
            "-USDT-SWAP"
        )


        url = "https://www.okx.com/api/v5/market/ticker"


        data = requests.get(
            url,
            params={
                "instId": okx
            },
            timeout=5
        ).json()


        if data.get("data"):

            return 10


        return 0


    except:

        return 0


# =====================================
# 📊 TRADINGVIEW CONFIRM
# =====================================

def tradingview_score(symbol):

    try:

        handler = TA_Handler(

            symbol=symbol,
            screener="crypto",
            exchange="BYBIT",
            interval=Interval.INTERVAL_1_HOUR

        )


        result = handler.get_analysis()


        signal = result.summary["RECOMMENDATION"]


        if signal == "STRONG_BUY":

            return 20


        if signal == "BUY":

            return 10


        return 0


    except:

        return 0


# =====================================
# 🐋 START LOG
# =====================================

print("🚀 AHAD AI v8.5 STARTING")

print("🟧 BYBIT DATA ACTIVE")

print("⬛ OKX CONFIRM ACTIVE")

print("📊 TRADINGVIEW ACTIVE")

# =====================================
# 🧠 AHAD AI v8.6 - PART 2
# HUNTER SMART BRAIN ENGINE
# =====================================


def analyze(symbol):

    try:

        score = 0
        reasons = []

        frames = {}


        # =============================
        # LOAD MULTI TIMEFRAME
        # =============================

        for tf in ["15m","1h","4h","1d"]:

            df = get_candles(symbol, tf)


            if df is not None and len(df) >= 30:

                frames[tf] = df



        if len(frames) == 0:

            return None



        weights = {

            "15m": 40,
            "1h": 30,
            "4h": 20,
            "1d": 10

        }



        # =============================
        # TECH ANALYSIS
        # =============================

        last_rsi = 0


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



            temp = 0


            if price > ema20:

                temp += 1


            if ema20 > ema50:

                temp += 1


            if 30 <= rsi <= 75:

                temp += 1


            if macd_power > 0:

                temp += 1



            score += (

                temp / 4

            ) * weights[tf]



            if temp >= 2:

                reasons.append(
                    tf.upper()
                    +
                    " Trend 🟢"
                )



        # =============================
        # ENTRY DATA
        # =============================

        if "15m" in frames:

            entry_df = frames["15m"]

        else:

            entry_df = list(frames.values())[0]



        price = entry_df["close"].iloc[-1]



        atr = AverageTrueRange(

            entry_df["high"],

            entry_df["low"],

            entry_df["close"],

            window=14

        ).average_true_range().iloc[-1]



        # =============================
        # WHALE VOLUME
        # =============================

        volume_now = entry_df["volume"].iloc[-1]


        volume_avg = (

            entry_df["volume"]

            .tail(20)

            .mean()

        )


        whale = (

            volume_now / volume_avg

            if volume_avg > 0

            else 0

        )



        if whale >= 1:

            score += 20

            reasons.append(
                "Whale Activity 🐋"
            )



        # =============================
        # EXTERNAL CONFIRM SAFE
        # =============================

        try:

            score += tradingview_score(symbol)

        except:

            pass


        try:

            score += okx_confirm(symbol)

        except:

            pass



        # =============================
        # TARGETS
        # =============================

        stop_loss = price - atr * 1.5


        risk = price - stop_loss



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
            "ANALYZE ERROR",
            symbol,
            e
        )


        return None

# =====================================
# 🤖 AHAD AI v8.5 - PART 3
# TELEGRAM + SCANNER ENGINE
# =====================================


@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v8.5 ONLINE 🐋

🟧 Bybit DATA
⬛ OKX Confirm
📊 TradingView

⏱ TIMEFRAMES:
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
🐋 AHAD AI v8.5 SCANNING...

🟧 Loading Bybit Data
⬛ Checking OKX
📊 Reading TradingView

Please wait...
"""
    )


    results = []


    symbols = get_symbols()



    for symbol in symbols:

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



    # =========================
    # 🐋 STRONG SIGNAL
    # =========================

    signals = [

        x for x in results

        if x["score"] >= 90

    ][:5]



    if signals:


        for s in signals:


            bot.send_message(

                message.chat.id,

f"""
🚨 AHAD AI v8.5 SIGNAL 🐋

🟢 LONG SETUP FOUND


🪙 COIN:
{s['coin']}


🔥 AI SCORE:
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


CONFIRM:
{chr(10).join(s['reasons'])}
"""

            )



    # =========================
    # 👀 RADAR MODE
    # =========================

    else:


        text = """
👀 AHAD AI v8.5 RADAR

No SNIPER LONG yet 🛡

Closest setups:
"""


        for r in results[:5]:


            text += f"""

🪙 {r['coin']}

🔥 SCORE:
{r['score']}

📊 RSI:
{round(r['rsi'],2)}

🐋 Whale:
{round(r['whale'],2)}X

📈 Reasons:
{chr(10).join(r['reasons'])}

━━━━━━━━━━
"""


        if len(results) == 0:


            text += """

⚠️ No setup now

Market scanned successfully 🐋
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
                "🤖 Telegram ACTIVE"
            )


            bot.infinity_polling(
                skip_pending=True,
                timeout=60
            )


        except Exception as e:


            print(
                traceback.format_exc()
            )


            print(
                "🔄 Restarting..."
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
    "🔥 AHAD AI v8.5 FULL ONLINE 🐋"
)



while True:

    time.sleep(60)
