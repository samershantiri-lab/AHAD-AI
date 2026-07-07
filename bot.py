# ==============================
# 🐋 AHAD AI v7.1
# MULTI SOURCE DATA ENGINE
# ==============================


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

        symbols = []

        for s in data.get("symbols", []):

            if (
                s.get("quoteAsset") == "USDT"
                and
                s.get("status") == "TRADING"
            ):

                symbols.append(
                    {
                        "symbol": s["symbol"],
                        "source": "BINANCE"
                    }
                )

        print("🟨 Binance:", len(symbols))

        return symbols


    except Exception as e:

        print("Binance Failed:", e)

        return []



# ==============================
# 🟧 BYBIT FUTURES
# ==============================

def bybit_symbols():

    try:

        url = "https://api.bybit.com/v5/market/instruments-info"

        params = {
            "category": "linear"
        }


        data = requests.get(
            url,
            params=params,
            timeout=10
        ).json()


        symbols = []


        for s in data["result"]["list"]:


            if s["quoteCoin"] == "USDT":

                symbols.append(
                    {
                        "symbol": s["symbol"],
                        "source": "BYBIT"
                    }
                )


        print("🟧 Bybit:", len(symbols))

        return symbols


    except Exception as e:

        print("Bybit Failed:", e)

        return []



# ==============================
# 🟦 MEXC FUTURES
# ==============================

def mexc_symbols():

    try:

        url = "https://contract.mexc.com/api/v1/contract/detail"


        data = requests.get(
            url,
            timeout=10
        ).json()


        symbols = []


        for s in data["data"]:


            if s["quoteCoin"] == "USDT":

                symbols.append(
                    {
                        "symbol": s["symbol"].replace("_",""),
                        "source": "MEXC"
                    }
                )


        print("🟦 MEXC:", len(symbols))


        return symbols


    except Exception as e:


        print("MEXC Failed:", e)


        return []



# ==============================
# 🌍 MERGE SOURCES
# ==============================

def get_futures_symbols():


    all_symbols = []


    all_symbols += binance_symbols()

    all_symbols += bybit_symbols()

    all_symbols += mexc_symbols()



    clean = {}


    for x in all_symbols:

        clean[x["symbol"]] = x



    final = list(
        clean.values()
    )


    print(
        "🐋 TOTAL MARKETS:",
        len(final)
    )


    return final



# ==============================
# 📊 UNIVERSAL CANDLES
# ==============================

def get_candles(market):


    symbol = market["symbol"]

    source = market["source"]


    try:


        if source == "BINANCE":


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


            candles = [
                [
                    x[1],
                    x[2],
                    x[3],
                    x[4],
                    x[5]
                ]

                for x in data
            ]


        elif source == "BYBIT":


            url = "https://api.bybit.com/v5/market/kline"


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


            candles = [

                [
                    x[1],
                    x[2],
                    x[3],
                    x[4],
                    x[5]
                ]

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
            "Candle Failed:",
            symbol,
            source,
            e
        )


        return None
# ==============================
# 🧠 AHAD ANALYSIS ENGINE v7.1
# MULTI SOURCE READY
# ==============================

def analyze(market):

    try:

        df = get_candles(market)


        if df is None or len(df) < 60:

            return None


        symbol = market["symbol"]

        source = market["source"]


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
        # ATR
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
                "EMA50 Bullish ✅"
            )


        if ema50 > ema100:

            score += 20
            reasons.append(
                "Trend Confirmed 🟢"
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
        # ENTRY ENGINE
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

            "source": source,

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
            e
        )


        return None
# ==============================
# 🤖 TELEGRAM COMMANDS v7.1
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v7.1 MULTI SOURCE ONLINE

🟨 Binance Engine
🟧 Bybit Engine
🟦 MEXC Engine

🐋 Whale Scanner ACTIVE
📊 Futures Scanner ACTIVE
🟢 LONG Hunter ACTIVE
⏱ 15m ACTIVE
🎯 Smart Entry ACTIVE
🛑 ATR Risk ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
"""
🐋 AHAD AI v7.1 scanning...

🟨 Binance
🟧 Bybit
🟦 MEXC

⏱ 15m
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

🟢 LONG FOUND

🪙 Coin:
{s['coin']}

📡 Source:
{s['source']}

🔥 Score:
{s['score']}/100


🎯 ENTRY:
{round(s['entry'],5)}

🛑 STOP:
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


        radar = results[:5]


        text = """
👀 AHAD AI RADAR

No sniper yet 🛡

Closest setups:
"""


        if radar:


            for r in radar:


                text += f"""

🪙 {r['coin']}

📡 {r['source']}

🔥 Score:
{r['score']}/100

📊 RSI:
{round(r['rsi'],2)}

🐋 Whale:
{round(r['whale'],2)}X

━━━━━━━━━━
"""


        else:


            text += """

⚠️ No data from sources

Checking:
🟨 Binance
🟧 Bybit
🟦 MEXC
"""


        bot.send_message(
            message.chat.id,
            text
        )



# ==============================
# 🛡 AUTO RECOVERY
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
                "🔄 Restart Telegram"
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
    "🔥 AHAD AI v7.1 FULL ONLINE"
)


while True:

    time.sleep(60)
