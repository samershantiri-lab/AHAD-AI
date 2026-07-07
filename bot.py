# ==============================
# 🚀 AHAD AI v7.0 MULTI SOURCE ENGINE
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
# CONFIG
# ==============================

TOKEN = os.environ.get("BOT_TOKEN")

if TOKEN is None:
    raise Exception("BOT_TOKEN NOT FOUND")


bot = telebot.TeleBot(TOKEN)


print("🚀 Starting AHAD AI v7.0")
print("🐋 Multi Source Engine ACTIVE")


# ==============================
# KEEP RENDER ONLINE
# ==============================

app = Flask(__name__)


@app.route("/")
def home():

    return "🚀 AHAD AI v7.0 ONLINE 🐋"


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
# 🟨 BINANCE SYMBOLS
# ==============================

def binance_symbols():

    try:

        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

        data = requests.get(
            url,
            timeout=10
        ).json()


        coins = []


        if "symbols" in data:

            for s in data["symbols"]:

                if (
                    s["quoteAsset"] == "USDT"
                    and
                    s["status"] == "TRADING"
                ):

                    coins.append(
                        s["symbol"]
                    )


        print(
            "🟨 Binance:",
            len(coins)
        )


        return coins


    except Exception as e:

        print(
            "Binance Error:",
            e
        )

        return []



# ==============================
# 🟧 BYBIT SYMBOLS BACKUP
# ==============================

def bybit_symbols():

    try:

        url = (
            "https://api.bybit.com"
            "/v5/market/instruments-info"
        )


        params = {
            "category": "linear"
        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        coins = []


        for s in data["result"]["list"]:

            if (
                s["quoteCoin"] == "USDT"
                and
                s["status"] == "Trading"
            ):

                coins.append(
                    s["symbol"]
                )


        print(
            "🟧 Bybit:",
            len(coins)
        )


        return coins


    except Exception as e:

        print(
            "Bybit Error:",
            e
        )

        return []



# ==============================
# AUTO SOURCE SELECTOR
# ==============================

def get_futures_symbols():

    coins = binance_symbols()


    if len(coins) > 0:

        print(
            "✅ Using Binance Data"
        )

        return coins


    coins = bybit_symbols()


    if len(coins) > 0:

        print(
            "✅ Using Bybit Data"
        )


    return coins



# ==============================
# GET CANDLES MULTI SOURCE
# ==============================

def get_candles(symbol):


    # TRY BINANCE FIRST

    try:

        url = "https://fapi.binance.com/fapi/v1/klines"


        params = {

            "symbol": symbol,

            "interval": "15m",

            "limit": 150

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        if isinstance(data, list):

            return make_dataframe(data)


    except Exception:

        pass



    # BYBIT BACKUP

    try:

        url = (
            "https://api.bybit.com"
            "/v5/market/kline"
        )


        params = {

            "category": "linear",

            "symbol": symbol,

            "interval": "15",

            "limit": 150

        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        candles = data["result"]["list"]


        candles.reverse()


        return pd.DataFrame({

            "open": [
                float(x[1]) for x in candles
            ],

            "high": [
                float(x[2]) for x in candles
            ],

            "low": [
                float(x[3]) for x in candles
            ],

            "close": [
                float(x[4]) for x in candles
            ],

            "volume": [
                float(x[5]) for x in candles
            ]

        })


    except Exception as e:

        print(
            "Candle Error:",
            symbol,
            e
        )


        return None



# ==============================
# DATAFRAME BUILDER
# ==============================

def make_dataframe(data):


    df = pd.DataFrame(

        data,

        columns=[

            "time",

            "open",

            "high",

            "low",

            "close",

            "volume",

            "x1",

            "x2",

            "x3",

            "x4",

            "x5",

            "x6"

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
# ==============================
# 🧠 AHAD ANALYSIS ENGINE v6.5
# ==============================

def analyze(symbol):

    try:

        df = get_candles(symbol)

        # allow new futures coins
        if df is None or len(df) < 60:
            return None


        close = df["close"]

        price = close.iloc[-1]


        # ==================
        # EMA TREND
        # ==================

        ema50 = EMAIndicator(
            close,
            window=50
        ).ema_indicator().iloc[-1]


        ema100 = EMAIndicator(
            close,
            window=100
        ).ema_indicator().iloc[-1]


        # ==================
        # RSI
        # ==================

        rsi = RSIIndicator(
            close,
            window=14
        ).rsi().iloc[-1]


        # ==================
        # MACD
        # ==================

        macd = MACD(close)

        macd_value = (
            macd.macd().iloc[-1]
            -
            macd.macd_signal().iloc[-1]
        )


        # ==================
        # ATR RISK ENGINE
        # ==================

        atr = AverageTrueRange(
            df["high"],
            df["low"],
            close,
            window=14
        ).average_true_range().iloc[-1]


        # ==================
        # 🐋 WHALE ENGINE
        # ==================

        volume_now = df["volume"].iloc[-1]

        volume_avg = (
            df["volume"]
            .tail(30)
            .mean()
        )


        if volume_avg == 0:

            whale_power = 0

        else:

            whale_power = (
                volume_now /
                volume_avg
            )


        # ==================
        # SCORE ENGINE
        # ==================

        score = 0

        reasons = []


        if price > ema50:

            score += 20
            reasons.append(
                "Price above EMA50 ✅"
            )


        if ema50 > ema100:

            score += 20
            reasons.append(
                "Trend Bullish 🟢"
            )


        if 35 <= rsi <= 70:

            score += 20
            reasons.append(
                "RSI Healthy 🎯"
            )


        if macd_value > 0:

            score += 20
            reasons.append(
                "MACD Momentum 📈"
            )


        if whale_power >= 1:

            score += 20
            reasons.append(
                "Whale Volume 🐋"
            )


        # ==================
        # SMART ENTRY
        # ==================

        entry = price


        stop_loss = (
            price -
            atr * 1.5
        )


        risk = (
            entry -
            stop_loss
        )


        tp1 = (
            entry +
            risk * 2
        )


        tp2 = (
            entry +
            risk * 3
        )


        return {

            "coin": symbol,

            "entry": entry,

            "sl": stop_loss,

            "tp1": tp1,

            "tp2": tp2,

            "score": score,

            "rsi": rsi,

            "whale": whale_power,

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
# 🤖 TELEGRAM COMMANDS v6.5
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v6.5 RADAR ONLINE

🐋 Whale Engine ACTIVE
📊 Futures Scanner ACTIVE
🟢 LONG Hunter ACTIVE
⏱ 15m Timeframe ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Risk ACTIVE
👀 TRUE Radar ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v6.5 scanning market...
⏱ Timeframe: 15m
"""
    )


    results = []


    symbols = get_futures_symbols()


    # ==================
    # SCAN ENGINE
    # ==================

    for symbol in symbols[:200]:

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
    # 🟢 SNIPER LONG
    # ==================

    signals = [
        x for x in results
        if x["score"] >= 80
    ][:3]


    if signals:


        for s in signals:


            bot.send_message(
                message.chat.id,
f"""
🚀 AHAD AI SNIPER SIGNAL 🐋

🟢 LONG SETUP FOUND

🪙 Coin:
{s['coin']}

🔥 Score:
{s['score']}/100

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

✅ Reasons:
{chr(10).join(s['reasons'])}
"""
            )


    # ==================
    # 👀 TRUE RADAR
    # ==================

    else:


        radar = results[:5]


        text = """
👀 AHAD AI TRUE RADAR

No sniper LONG yet 🛡

🐋 Closest Market Setups:
"""


        if radar:


            for r in radar:


                text += f"""

🪙 {r['coin']}

🔥 Score:
{r['score']}/100

📊 RSI:
{round(r['rsi'],2)}

🐋 Whale:
{round(r['whale'],2)}X

👀 Monitoring...

━━━━━━━━━━
"""


        else:


            text += """

⚠️ No market data detected

Check:
- Binance API
- Futures connection
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
    "🔥 AHAD AI v6.5 FULL ONLINE"
)


while True:

    time.sleep(60)
