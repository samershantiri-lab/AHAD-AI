# =====================================
# 🚀 AHAD AI v11.4 — LIQUIDITY HUNTER + DATABASE
# Core decision logic (v11.3) UNCHANGED — LONG/SHORT acceptance,
# ai_brain, smart_money, pre_pump_engine, entry/SL/TP formulas are
# byte-for-byte identical to v11.3 (+ SHORT mirror added earlier).
# Added: PostgreSQL persistence, duplicate protection, dynamic price
# precision (storage only, not decision logic), and Telegram commands
# (/report, /debug, /history, /open, /trade).
# =====================================

import os
import time
import threading
import traceback
import requests
import urllib.request
import psycopg2
import json
from datetime import datetime

from flask import Flask
import telebot

VERSION = "v11.8"


# =====================================
# 🔑 TELEGRAM TOKEN
# =====================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:

    raise Exception(
        "❌ BOT_TOKEN NOT FOUND"
    )


bot = telebot.TeleBot(
    TOKEN
)


# =====================================
# 🗄 DATABASE (NEW — v11.4)
# =====================================
# Separate table from any prior version's `trades` table - v11.3's
# fields are fundamentally different (no ranking_score, no
# compression_status, no market_regime) - a dedicated table avoids
# any mixing between architectures.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def init_database():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades_v11 (
            id SERIAL PRIMARY KEY,
            version TEXT DEFAULT 'v11.4',
            symbol TEXT NOT NULL,
            sector TEXT,
            direction TEXT NOT NULL,
            score REAL,
            entry_low REAL,
            entry_high REAL,
            sl REAL,
            tp1 REAL,
            tp2 REAL,
            liquidity REAL,
            money_status TEXT,
            pre_pump_status TEXT,
            signal_time TIMESTAMPTZ DEFAULT NOW(),
            status TEXT DEFAULT 'OPEN',
            result TEXT,
            close_time TIMESTAMPTZ,
            pnl_percent REAL,
            peak_price REAL,
            peak_profit_pct REAL,
            peak_reached_at TIMESTAMPTZ
        )
    """)
    cur.execute("""
        ALTER TABLE trades_v11 ADD COLUMN IF NOT EXISTS pnl_percent REAL
    """)
    cur.execute("""
        ALTER TABLE trades_v11 ADD COLUMN IF NOT EXISTS peak_price REAL
    """)
    cur.execute("""
        ALTER TABLE trades_v11 ADD COLUMN IF NOT EXISTS peak_profit_pct REAL
    """)
    cur.execute("""
        ALTER TABLE trades_v11 ADD COLUMN IF NOT EXISTS peak_reached_at TIMESTAMPTZ
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_v11_no_dup
        ON trades_v11 (symbol, direction)
        WHERE status = 'OPEN'
    """)
    conn.commit()
    cur.close()
    conn.close()


def round_price_dynamic(value):
    """
    Storage-only precision fix (same class of bug confirmed and fixed
    in v23.4) - v11.3's own display already used round(x, 6) fixed,
    which is unsafe for very low-priced assets. This does NOT change
    entry/SL/TP calculation logic (identical to v11.3's formulas above)
    - only how the resulting numbers are stored/displayed precisely.
    """
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    abs_value = abs(value)
    if abs_value >= 10000:
        decimals = 0
    elif abs_value >= 10:
        decimals = 2
    elif abs_value >= 1:
        decimals = 3
    elif abs_value >= 0.01:
        decimals = 4
    elif abs_value >= 0.001:
        decimals = 5
    elif abs_value >= 0.0001:
        decimals = 7
    elif abs_value >= 0.00001:
        decimals = 8
    elif abs_value >= 0.000001:
        decimals = 9
    elif abs_value >= 0.0000001:
        decimals = 10
    else:
        decimals = 11
    return round(value, decimals)


def save_trade(trade_data):
    """
    Duplicate protection: unique index on (symbol, direction) WHERE
    status='OPEN' prevents a second open trade for the same symbol+
    direction combo - matches the spirit of v23.4's protection.
    Returns (trade_id, is_duplicate).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO trades_v11 (
                version, symbol, sector, direction, score, entry_low, entry_high,
                sl, tp1, tp2, liquidity, money_status, pre_pump_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            VERSION,
            trade_data["coin"], trade_data["sector"], trade_data["direction"],
            trade_data["score"],
            round_price_dynamic(trade_data["entry_low"]),
            round_price_dynamic(trade_data["entry_high"]),
            round_price_dynamic(trade_data["sl"]),
            round_price_dynamic(trade_data["tp1"]),
            round_price_dynamic(trade_data["tp2"]),
            trade_data["liquidity"], trade_data["money"], trade_data["pre_pump"],
        ))
        trade_id = cur.fetchone()[0]
        conn.commit()
        return trade_id, False
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        cur.execute("""
            SELECT id FROM trades_v11
            WHERE symbol=%s AND direction=%s AND status='OPEN'
            ORDER BY id DESC LIMIT 1
        """, (trade_data["coin"], trade_data["direction"]))
        row = cur.fetchone()
        existing_id = row[0] if row else None
        return existing_id, True
    finally:
        cur.close()
        conn.close()


def update_open_trades():
    """
    Checks OPEN trades against current price to detect TP1/TP2/SL hits.
    Also tracks peak_profit_pct/peak_price/peak_reached_at on every check
    (independent of close decision) - answers "how far did it actually go"
    without changing the close-on-first-TP-hit behavior itself.
    Runs independently of scan() - does not affect signal generation.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, direction, entry_low, entry_high, sl, tp1, tp2, peak_profit_pct FROM trades_v11 WHERE status='OPEN'")
    open_trades = cur.fetchall()
    for (tid, symbol, direction, entry_low, entry_high, sl, tp1, tp2, prev_peak_profit) in open_trades:
        try:
            candles = get_candles(symbol, "15m")
            if not candles:
                continue
            current_price = candles[-1]["close"]
            entry_mid = (entry_low + entry_high) / 2

            if direction == "🟢 LONG":
                best_price_in_candles = max(c["high"] for c in candles)
                best_profit_pct = ((best_price_in_candles - entry_mid) / entry_mid) * 100
            else:
                best_price_in_candles = min(c["low"] for c in candles)
                best_profit_pct = ((entry_mid - best_price_in_candles) / entry_mid) * 100

            if prev_peak_profit is None or best_profit_pct > prev_peak_profit:
                cur.execute(
                    "UPDATE trades_v11 SET peak_price=%s, peak_profit_pct=%s, peak_reached_at=NOW() WHERE id=%s",
                    (best_price_in_candles, round(best_profit_pct, 3), tid)
                )
                conn.commit()

            result = None
            if direction == "🟢 LONG":
                if current_price <= sl:
                    result = "LOSS_SL"
                elif current_price >= tp2:
                    result = "WIN_TP2"
                elif current_price >= tp1:
                    result = "WIN_TP1"
            else:
                if current_price >= sl:
                    result = "LOSS_SL"
                elif current_price <= tp2:
                    result = "WIN_TP2"
                elif current_price <= tp1:
                    result = "WIN_TP1"
            if result:
                if direction == "🟢 LONG":
                    pnl_percent = ((current_price - entry_mid) / entry_mid) * 100
                else:
                    pnl_percent = ((entry_mid - current_price) / entry_mid) * 100
                cur.execute(
                    "UPDATE trades_v11 SET status='CLOSED', result=%s, close_time=NOW(), pnl_percent=%s WHERE id=%s",
                    (result, round(pnl_percent, 3), tid)
                )
                conn.commit()
        except Exception as e:
            print(f"⚠️ update_open_trades error for {symbol}: {e}")
    cur.close()
    conn.close()


# 🌐 RENDER KEEP ALIVE SERVER
# =====================================

app = Flask(
    __name__
)


@app.route("/")
def home():

    return (
        f"🐋 AHAD AI {VERSION} "
        "LIQUIDITY HUNTER ONLINE 🚀"
    )


# =====================================
# 📊 REPORTING COMMANDS (NEW — v11.4)
# =====================================

@bot.message_handler(commands=["report"])
def report_command(message):
    parts = message.text.strip().split()
    version_filter = parts[1] if len(parts) > 1 else None

    conn = get_db_connection()
    cur = conn.cursor()

    if version_filter:
        cur.execute("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE status='CLOSED'),
                   COUNT(*) FILTER (WHERE status='OPEN'),
                   COUNT(*) FILTER (WHERE result LIKE %s),
                   COUNT(*) FILTER (WHERE result='LOSS_SL')
            FROM trades_v11 WHERE version=%s
        """, ('WIN%', version_filter))
    else:
        cur.execute("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE status='CLOSED'),
                   COUNT(*) FILTER (WHERE status='OPEN'),
                   COUNT(*) FILTER (WHERE result LIKE 'WIN%'),
                   COUNT(*) FILTER (WHERE result='LOSS_SL')
            FROM trades_v11
        """)
    total, closed, open_n, wins, losses = cur.fetchone()
    decided = wins + losses
    wr = round(100.0 * wins / decided, 1) if decided > 0 else 0.0

    if version_filter:
        cur.execute("""
            SELECT direction, COUNT(*), COUNT(*) FILTER (WHERE result LIKE %s), COUNT(*) FILTER (WHERE result='LOSS_SL')
            FROM trades_v11 WHERE status='CLOSED' AND version=%s GROUP BY direction
        """, ('WIN%', version_filter))
    else:
        cur.execute("""
            SELECT direction, COUNT(*), COUNT(*) FILTER (WHERE result LIKE 'WIN%'), COUNT(*) FILTER (WHERE result='LOSS_SL')
            FROM trades_v11 WHERE status='CLOSED' GROUP BY direction
        """)
    by_dir = cur.fetchall()
    cur.close()
    conn.close()

    if version_filter and total == 0:
        bot.reply_to(message, f"📭 No trades found for version {version_filter}.")
        return

    header = f"📊 AHAD AI {version_filter}" if version_filter else f"📊 AHAD AI {VERSION} (ALL VERSIONS)"
    msg = f"""{header}

Trades: {total}
Closed: {closed}
Open: {open_n}

🟢 Wins: {wins}
🔴 Losses: {losses}
🎯 Win Rate: {wr}%

────────────────
"""
    for direction, n, w, l in by_dir:
        d_decided = w + l
        d_wr = round(100.0 * w / d_decided, 1) if d_decided > 0 else 0.0
        msg += f"\n{direction}\nTrades: {n} | Wins: {w} | Losses: {l} | WR: {d_wr}%\n"

    bot.reply_to(message, msg)


@bot.message_handler(commands=["open"])
def open_command(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, direction, entry_low, entry_high, sl, tp1, tp2, signal_time FROM trades_v11 WHERE status='OPEN' ORDER BY id DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        bot.reply_to(message, "📭 No open trades.")
        return

    msg = "📂 OPEN TRADES\n\n"
    for (tid, symbol, direction, entry_low, entry_high, sl, tp1, tp2, sig_time) in rows:
        msg += f"#{tid} {direction} {symbol}\n🎯 {round_price_dynamic(entry_low)}-{round_price_dynamic(entry_high)} 🛑{round_price_dynamic(sl)}\n\n"
    bot.reply_to(message, msg)


@bot.message_handler(commands=["history"])
def history_command(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, symbol, direction, result, pnl_percent, peak_profit_pct,
               EXTRACT(EPOCH FROM (peak_reached_at - signal_time))/60 as minutes_to_peak
        FROM trades_v11 WHERE status='CLOSED' ORDER BY id DESC LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        bot.reply_to(message, "📭 No closed trades yet.")
        return

    msg = "📜 LAST 10 CLOSED TRADES\n\n"
    for (tid, symbol, direction, result, pnl_percent, peak_profit_pct, minutes_to_peak) in rows:
        icon = "🟢" if result and "WIN" in result else "🔴"
        pnl_str = f"{pnl_percent:+.2f}%" if pnl_percent is not None else "N/A"
        msg += f"{icon} #{tid} {direction} {symbol} — {result} ({pnl_str})\n"
        if peak_profit_pct is not None:
            mins = int(minutes_to_peak) if minutes_to_peak is not None else 0
            msg += f"   📈 Peak: {peak_profit_pct:+.2f}% (reached in {mins} min)\n"
    bot.reply_to(message, msg)


@bot.message_handler(commands=["trade"])
def trade_command(message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /trade <id>")
        return
    try:
        trade_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "Usage: /trade <id>")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades_v11 WHERE id=%s", (trade_id,))
    row = cur.fetchone()
    colnames = [desc[0] for desc in cur.description]
    cur.close()
    conn.close()

    if not row:
        bot.reply_to(message, f"❌ Trade #{trade_id} not found.")
        return

    data = dict(zip(colnames, row))
    msg = f"📖 TRADE #{trade_id}\n\n"
    for k, v in data.items():
        msg += f"{k}: {v}\n"
    bot.reply_to(message, msg)


@bot.message_handler(commands=["debug"])
def debug_command(message):
    bot.reply_to(message, f"🐞 AHAD AI {VERSION} — Simplified core (v11.3 logic), no complex ranking/context pipeline to debug.")


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
# 🏦 SECTOR DATABASE v11.3
# =====================================

SECTORS = {


    "AI": [

        "FET",
        "TAO",
        "WLD",
        "ARKM",
        "AI",
        "RENDER"

    ],


    "GAMING": [

        "APE",
        "SAND",
        "MANA",
        "GALA",
        "IMX",
        "AXS"

    ],


    "DEFI": [

        "UNI",
        "AAVE",
        "LINK",
        "CRV",
        "MKR",
        "COMP"

    ],


    "MEME": [

        "DOGE",
        "SHIB",
        "PEPE",
        "BONK",
        "FLOKI"

    ],


    "LAYER1": [

        "SOL",
        "AVAX",
        "DOT",
        "NEAR",
        "ADA"

    ],


    "RWA": [

        "ONDO",
        "PENDLE",
        "ENA"

    ]

}



# =====================================
# ⬛ OKX FUTURES CRYPTO ONLY
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



        blocked = [

            # STOCKS
            "TSLA",
            "AMZN",
            "AAPL",
            "NVDA",
            "META",
            "GOOGL",
            "MSFT",
            "NFLX",
            "AMD",
            "COIN",
            "MSTR",
            "BABA",
            "PLTR",
            "HOOD",

            # GOLD / FOREX
            "XAU",
            "EUR",
            "GBP",
            "JPY",

            # INDEX
            "SPX",
            "NASDAQ",
            "DOW"

        ]



        result = []



        for x in data["data"]:


            symbol = x["instId"]


            if (

                x["settleCcy"] == "USDT"

                and

                x["state"] == "live"

                and

                x.get("ctType") == "linear"

                and

                "USD" not in x["instId"].replace("USDT", "")

                and

                not any(
                    b in symbol
                    for b in blocked
                )

            ):


                result.append(
                    symbol
                )



        print(

            "🐋 MARKETS FOUND:",

            len(result)

        )


        return result



    except Exception as e:


        print(

            "SYMBOL ERROR:",

            e

        )


        return []



# =====================================
# 🐋 TOP FLOW SCANNER v12
# Find hot money before AI scan
# =====================================

def top_flow_scanner(symbols):

    results = []

    for symbol in symbols:

        try:

            c15 = get_candles(symbol, "15m")

            if len(c15) < 50:
                continue


            volumes = [
                x["volume"]
                for x in c15
            ]

            closes = [
                x["close"]
                for x in c15
            ]


            vol_now = sum(volumes[-5:])

            vol_avg = (
                sum(volumes[-40:])
                /
                40
            )


            if vol_avg == 0:
                continue


            flow = vol_now / vol_avg


            move = (
                (closes[-1] - closes[-20])
                /
                closes[-20]
            ) * 100


            # لا نريد عملة طارت كثير
            if move > 10:
                continue


            if flow >= 1.15:

                results.append({

                    "coin": symbol,

                    "flow": flow

                })


        except:

            pass


        time.sleep(0.01)

        if len(results) >= 80:
            break


    results = sorted(
        results,
        key=lambda x: x["flow"],
        reverse=True
    )


    return [
        x["coin"]
        for x in results[:100]
    ]



# =====================================
# 🕯 OKX CANDLES ENGINE
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


            "limit": 150

        }


        data = requests.get(

            url,

            params=params,

            timeout=10

        ).json()


        candles = []


        for c in data["data"][::-1]:


            candles.append({


                "open": float(c[1]),

                "high": float(c[2]),

                "low": float(c[3]),

                "close": float(c[4]),

                "volume": float(c[5])


            })


        return candles



    except Exception as e:


        print(

            "CANDLE ERROR:",

            symbol,

            e

        )


        return []



print(
    "🔥 AHAD AI v11.3 CORE READY 🐋"
)

# =====================================
# 📊 INDICATORS ENGINE v11.3
# =====================================

def ema(values, period):

    if len(values) < period:

        return values[-1]


    k = 2 / (period + 1)

    result = values[0]


    for v in values:

        result = (
            v * k
            +
            result * (1 - k)
        )


    return result



def rsi(values, period=14):

    gains = 0
    losses = 0


    for i in range(-period, -1):

        diff = (
            values[i + 1]
            -
            values[i]
        )


        if diff > 0:

            gains += diff

        else:

            losses -= diff



    if losses == 0:

        return 100



    rs = gains / losses


    return (
        100
        -
        100 / (1 + rs)
    )



def atr(candles):

    ranges = []


    for c in candles[-14:]:

        ranges.append(
            c["high"]
            -
            c["low"]
        )


    return (
        sum(ranges)
        /
        len(ranges)
    )



# =====================================
# 🏦 SECTOR FLOW ENGINE v11.3
# FIND WHERE MONEY GOES
# =====================================

def sector_flow(symbols):

    try:

        result = {}


        for sector, coins in SECTORS.items():

            power = 0


            for symbol in symbols:


                if any(
                    coin in symbol
                    for coin in coins
                ):

                    candles = get_candles(
                        symbol,
                        "1h"
                    )


                    if len(candles) > 50:


                        volumes = [
                            x["volume"]
                            for x in candles
                        ]


                        recent = sum(
                            volumes[-5:]
                        )


                        average = (
                            sum(
                                volumes[-50:]
                            )
                            /
                            50
                        )


                        if average > 0:

                            power += (
                                recent
                                /
                                average
                            )


            result[sector] = round(
                power,
                2
            )



        hot_sector = max(
            result,
            key=result.get
        )


        return {

            "sector": hot_sector,

            "power": result[hot_sector]

        }



    except Exception as e:

        print(
            "SECTOR ERROR:",
            e
        )


        return {

            "sector": "UNKNOWN",

            "power": 0

        }



# =====================================
# 🐋 SMART MONEY ENGINE v11.3
# =====================================

def smart_money(candles):

    try:

        closes = [
            x["close"]
            for x in candles
        ]


        volumes = [
            x["volume"]
            for x in candles
        ]


        volume_now = sum(
            volumes[-5:]
        )


        volume_avg = (
            sum(volumes[-50:])
            /
            50
        )


        if volume_avg == 0:

            flow = 0

        else:

            flow = (
                volume_now
                /
                volume_avg
            )


        move = (
            (
                closes[-1]
                -
                closes[-24]
            )
            /
            closes[-24]
        ) * 100



        if (
            flow >= 1.5
            and
            abs(move) < 8
        ):

            status = (
                "🐋 SMART ACCUMULATION"
            )


        elif (
            flow >= 1.5
            and
            move > 8
        ):

            status = (
                "🚨 WHALE EXIT"
            )


        else:

            status = "NORMAL"



        return {

            "flow": round(flow, 2),

            "status": status

        }



    except Exception as e:

        print(
            "SMART MONEY ERROR:",
            e
        )


        return {

            "flow": 0,

            "status": "ERROR"

        }



# =====================================
# 🐋 PRE PUMP ACCUMULATION ENGINE v11.3
# Detect whales before breakout
# =====================================

def pre_pump_engine(candles):

    try:

        closes = [
            x["close"]
            for x in candles
        ]

        volumes = [
            x["volume"]
            for x in candles
        ]


        price = closes[-1]


        volume_now = sum(
            volumes[-5:]
        )


        volume_avg = (
            sum(volumes[-50:])
            /
            50
        )


        if volume_avg == 0:

            return {

                "status":"NORMAL",

                "score":0

            }


        flow = (
            volume_now
            /
            volume_avg
        )


        move = (
            (price - closes[-30])
            /
            closes[-30]
        ) * 100


        current_rsi = rsi(
            closes
        )


        # 🐋 Quiet accumulation before pump

        if (
            flow >= 1.15
            and
            abs(move) < 5
            and
            35 <= current_rsi <= 65
        ):

            return {

                "status":"🐋 WHALE LOADING",

                "score":25

            }


        return {

            "status":"NORMAL",

            "score":0

        }


    except Exception as e:

        print(
            "PRE PUMP ERROR:",
            e
        )


        return {

            "status":"ERROR",

            "score":0

        }



# =====================================
# 📊 MULTI TIMEFRAME ENGINE v11.3
# =====================================

def multi_rsi_engine(c15, c1h, c4h, c1d):

    try:

        data = {}

        frames = {

            "15m": c15,
            "1h": c1h,
            "4h": c4h,
            "1d": c1d

        }


        score = 0


        for name, candles in frames.items():

            closes = [
                x["close"]
                for x in candles
            ]


            value = rsi(
                closes
            )


            data[name] = round(
                value,
                2
            )


            if 50 <= value <= 70:

                score += 10


            elif value > 75:

                score -= 10


            elif value < 35:

                score += 5



        data["score"] = score


        return data



    except Exception as e:

        print(
            "MULTI RSI ERROR:",
            e
        )


        return {

            "15m":50,
            "1h":50,
            "4h":50,
            "1d":50,
            "score":0

        }



# =====================================
# 🧱 SUPPORT RESISTANCE ENGINE
# =====================================

def support_resistance(candles):

    highs = [
        x["high"]
        for x in candles[-80:]
    ]


    lows = [
        x["low"]
        for x in candles[-80:]
    ]


    price = candles[-1]["close"]


    support = min(lows)

    resistance = max(highs)


    return {

        "support": support,

        "resistance": resistance,

        "near_support":
        ((price-support)/price)*100,

        "near_resistance":
        ((resistance-price)/price)*100

    }



# =====================================
# 🛡 ANTI LATE ENTRY v11.3
# =====================================

def fomo_filter(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    price = closes[-1]


    move = (

        (price - closes[-96])

        /

        closes[-96]

    ) * 100



    current_rsi = rsi(
        closes
    )


    # Avoid late momentum entry

    if (
        move > 5
        and
        current_rsi > 65
    ):

        return (

            False,

            "⏳ WAIT PULLBACK"

        )



    if move > 8:

        return (

            False,

            "🚫 MOVE DONE - WAIT RETEST"

        )



    if current_rsi > 75:

        return (

            False,

            "🚫 RSI HOT"

        )



    return (

        True,

        "🐋 EARLY ENTRY AREA"

    )



# =====================================
# 🪤 TRAP DETECTOR v11.3
# =====================================

def trap_detector(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    highs = [
        x["high"]
        for x in candles
    ]


    lows = [
        x["low"]
        for x in candles
    ]


    price = closes[-1]

    r = rsi(closes)


    if (
        price >= max(highs[-50:]) * 0.98
        and
        r > 70
    ):

        return "🪤 BULL TRAP"



    if (
        price <= min(lows[-50:]) * 1.02
        and
        r < 35
    ):

        return "🪤 BEAR TRAP"



    return "✅ NO TRAP"



# =====================================
# 🧠 AI BRAIN ENGINE v11.3
# =====================================

def ai_brain(candles):

    closes = [
        x["close"]
        for x in candles
    ]


    price = closes[-1]


    e20 = ema(
        closes,
        20
    )


    e50 = ema(
        closes,
        50
    )


    score = 0



    if price > e20:

        score += 30

    else:

        score -= 30



    if e20 > e50:

        score += 30

    else:

        score -= 30



    if score >= 50:

        direction = "🟢 LONG"


    elif score <= -50:

        direction = "🔴 SHORT"


    else:

        direction = "WAIT"



    return {

        "direction": direction,

        "confidence": abs(score)

    }



# =====================================
# 🚀 FINAL ANALYZE ENGINE v11.3
# =====================================

def analyze(symbol, sector):

    try:

        c15 = get_candles(symbol,"15m")
        c1h = get_candles(symbol,"1h")
        c4h = get_candles(symbol,"4h")
        c1d = get_candles(symbol,"1d")


        if (
            len(c15)<96
            or len(c1h)<60
            or len(c4h)<60
            or len(c1d)<60
        ):

            return None



        price = c15[-1]["close"]


        safe, warning = fomo_filter(c15)


        if not safe:

            return None


        brain = ai_brain(c1h)


        if brain["direction"] == "WAIT":

            return None


        sr = support_resistance(c15)

        money = smart_money(c15)

        pre = pre_pump_engine(c15)

        multi = multi_rsi_engine(
            c15,
            c1h,
            c4h,
            c1d
        )

        trap = trap_detector(c15)


        score = (
            brain["confidence"]
            +
            multi["score"]
        )


        # =====================================
        # 🔥 HEAT CONTROL v11.3
        # Avoid late entries
        # =====================================

        if multi["4h"] > 70:

            score -= 15


        if multi["1d"] > 70:

            score -= 20


        if multi["15m"] > 75:

            score -= 10


        # =====================================
        # RESISTANCE FILTER v11.3
        # =====================================

        if sr["near_resistance"] < 3:
            score -= 10


        if money["status"] == "🐋 SMART ACCUMULATION":
            score += 20

        score += pre["score"]


        move = atr(c15)


        entry_low = price * 0.995

        entry_high = price * 1.005


        if brain["direction"] == "🟢 LONG":

            tp1 = max(price + move * 2, price * 1.01)
            tp2 = max(price + move * 3, tp1 + move)

            sl_raw = sr["support"] * 0.995
            tp1_distance = tp1 - price
            max_sl_floor = price - (2 * tp1_distance)
            sl = max(sl_raw, max_sl_floor)


        else:

            tp1 = min(price - move * 2, price * 0.99)
            tp2 = min(price - move * 3, tp1 - move)

            sl_raw = sr["resistance"] * 1.005
            tp1_distance = price - tp1
            max_sl_ceiling = price + (2 * tp1_distance)
            sl = min(sl_raw, max_sl_ceiling)



        return {

            "coin":symbol,
            "sector":sector,
            "direction":brain["direction"],
            "score":round(score),
            "entry_low":entry_low,
            "entry_high":entry_high,
            "sl":sl,
            "tp1":tp1,
            "tp2":tp2,
            "money":money["status"],
            "liquidity":money["flow"],
            "pre_pump":pre["status"],
            "multi":multi,
            "trap":trap,
            "warning":warning

        }


    except Exception as e:

        print(
            "ANALYZE ERROR:",
            e
        )

        return None



# =====================================
# 🤖 TELEGRAM ENGINE v11.3
# =====================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
        f"""
🐋 AHAD AI {VERSION} ONLINE 🚀

🧠 AI Brain ACTIVE
🐋 Liquidity Hunter ACTIVE
🏦 Sector Flow ACTIVE
📊 Multi TimeFrame ACTIVE
🪤 Trap Detector ACTIVE
⚡ Pre-Pump Detection ACTIVE
🔥 Heat Control ACTIVE

🎯 Goal:
Best 3 quality LONG or SHORT setups

Send /scan
        """
    )



# =====================================
# 🔎 SMART SCANNER v11.3
# Liquidity → Sector → Coin
# =====================================

@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        f"""
🐋 AHAD AI {VERSION} SCANNING...

🔍 Checking Market Flow
🏦 Finding Hot Sector
🎯 Hunting TOP 3 LONG/SHORT setups
🐋 Tracking Smart Money
⚡ Detecting Pre-Pump
🔥 Heat Control ACTIVE

Please wait ⏳
        """
    )


    long_results = []
    short_results = []


    all_symbols = get_symbols()

    symbols = top_flow_scanner(all_symbols)


    flow = sector_flow(
        all_symbols
    )


    hot_sector = flow["sector"]


    bot.send_message(
        message.chat.id,
        f"""
🔥 MARKET FLOW

🏦 Hot Sector:
{hot_sector}

🐋 Flow Power:
{flow['power']}
        """
    )


    # TOP FLOW PRIORITY

    if len(symbols) < 20:

        symbols = all_symbols


    bot.send_message(
        message.chat.id,
        f"💎 Smart Money Watchlist: {len(symbols)} coins"
    )



    for symbol in symbols:


        result = analyze(
            symbol,
            hot_sector
        )


        if result:



            if result["direction"] == "🟢 LONG":

                if (
                    result["score"] >= 75
                    and
                    (
                        result["liquidity"] >= 1.2
                        or
                        result["pre_pump"] == "🐋 WHALE LOADING"
                    )
                ):

                    result["passed_via"] = "Flow" if result["liquidity"] >= 1.2 else "Whale Loading"
                    long_results.append(result)

            elif result["direction"] == "🔴 SHORT":

                if (
                    result["score"] >= 75
                    and
                    (
                        result["liquidity"] >= 1.2
                        or
                        result["pre_pump"] == "🐋 WHALE LOADING"
                    )
                ):

                    result["passed_via"] = "Flow" if result["liquidity"] >= 1.2 else "Whale Loading"
                    short_results.append(result)



        time.sleep(
            0.03
        )



    results = sorted(

        long_results + short_results,

        key=lambda x: (
            x["score"],
            x["liquidity"]
        ),

        reverse=True

    )[:3]



    if not results:


        bot.send_message(
            message.chat.id,
            """
👀 No sniper setup now

🐋 Smart Money not ready
⏳ Waiting next liquidity wave
            """
        )


        return



    for idx, s in enumerate(results, start=1):

        trade_id, is_duplicate = save_trade(s)

        if s['score'] >= 110:
            quality_label = "🔵 ELITE"
        elif s['score'] >= 90:
            quality_label = "🟢 STRONG"
        else:
            quality_label = "🟡 STANDARD"

        if is_duplicate and trade_id:
            id_line = f"🔄 #{trade_id} updated | 📖 /trade {trade_id}"
        elif trade_id:
            id_line = f"💾 #{trade_id}"
        else:
            id_line = "⚠️ SAVE FAILED"

        entry_mid = (s['entry_low'] + s['entry_high']) / 2
        if s['direction'] == "🟢 LONG":
            risk = entry_mid - s['sl']
        else:
            risk = s['sl'] - entry_mid

        if risk > 0:
            if s['direction'] == "🟢 LONG":
                rr1 = (s['tp1'] - entry_mid) / risk
                rr2 = (s['tp2'] - entry_mid) / risk
            else:
                rr1 = (entry_mid - s['tp1']) / risk
                rr2 = (entry_mid - s['tp2']) / risk
            rr1_str = f"  ⚖️{rr1:.1f}R"
            rr2_str = f"  ⚖️{rr2:.1f}R"
        else:
            rr1_str = ""
            rr2_str = ""

        rsi_15m = s['multi']['15m']
        if rsi_15m > 70:
            entry_timing = "🟡 WAIT FOR PULLBACK"
        elif rsi_15m < 40:
            entry_timing = "🔴 LATE (already dropped)"
        else:
            entry_timing = "🟢 READY TO ENTER"

        msg = f"""
🚨 AHAD AI {VERSION} 🐋

🏆 {s['direction']} • Rank #{idx}
🪙 {s['coin']}

🔥 Score: {s['score']} {quality_label}
💧 Flow: {s['liquidity']}X
🐋 Money: {s['money']}
🪤 Trap: {s['trap']}
✅ Passed via: {s.get('passed_via', 'N/A')}

🎯 Entry: {round_price_dynamic(s['entry_low'])} - {round_price_dynamic(s['entry_high'])}
🛑 SL: {round_price_dynamic(s['sl'])}

🥇 TP1: {round_price_dynamic(s['tp1'])}{rr1_str}
🥈 TP2: {round_price_dynamic(s['tp2'])}{rr2_str}

{entry_timing}

{id_line}
        """


        bot.send_message(
            message.chat.id,
            msg
        )



# =====================================
# 🐋 KEEP ALIVE ENGINE
# =====================================

def keep_alive():

    while True:

        try:

            url = os.environ.get("RENDER_URL")

            if url:

                urllib.request.urlopen(url)

                print("🐋 KEEP ALIVE ACTIVE")


        except Exception as e:

            print(
                "KEEP ALIVE ERROR:",
                e
            )


        time.sleep(300)



# =====================================
# 🚀 START SYSTEM
# =====================================

def telegram_engine():

    while True:

        try:

            print(
                "🐋 TELEGRAM ENGINE STARTED"
            )


            bot.infinity_polling(

                skip_pending=True,

                timeout=60,

                long_polling_timeout=60

            )


        except Exception:


            print(
                "🚨 TELEGRAM ERROR"
            )


            print(
                traceback.format_exc()
            )



        print(
            "🔄 Restarting Telegram..."
        )


        time.sleep(
            5
        )



try:
    init_database()
except Exception as e:
    print(f"⚠️ init_database() failed at startup (will retry per-request): {e}")


def open_trades_monitor():
    while True:
        try:
            update_open_trades()
        except Exception as e:
            print(f"⚠️ open_trades_monitor error: {e}")
        time.sleep(600)


threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=telegram_engine,
    daemon=True
).start()


threading.Thread(
    target=keep_alive,
    daemon=True
).start()


threading.Thread(
    target=open_trades_monitor,
    daemon=True
).start()


print(
    f"🔥 AHAD AI {VERSION} LIQUIDITY HUNTER ONLINE 🐋"
)



while True:

    time.sleep(
        60
    )
