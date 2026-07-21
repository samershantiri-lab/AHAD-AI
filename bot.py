# ================================================
# 🚀 AHAD AI v20.5.0 STAGE 2
# TRADE RECORDER SYSTEM
# ================================================

# ================================================
# ⚙️ CONFIGURATION
# ================================================

MIN_FLOW_COINS = 50
MAX_FLOW_COINS = 150
FLOW_RATIO = 0.40

# ================================================
# 📦 SECTION 1: CORE + DATA
# ================================================

import os
import time
import threading
import traceback
import requests
import urllib.request
import sqlite3
from datetime import datetime

from flask import Flask
import telebot


# ================================================
# 🔑 TELEGRAM TOKEN
# ================================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise Exception("❌ BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)


# ================================================
# 🗄 AHAD AI DATABASE
# ================================================

DB_NAME = "ahad_ai.db"


def init_database():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        symbol TEXT,
        side TEXT,

        signal_time TEXT,

        entry REAL,
        sl REAL,

        tp1 REAL,
        tp2 REAL,
        tp3 REAL,

        sector TEXT,

        score INTEGER,

        brain_long INTEGER,
        brain_short INTEGER,

        flow REAL,
        momentum INTEGER,
        rr REAL,

        confidence TEXT,

        late_score INTEGER,

        version TEXT,

        status TEXT,

        result TEXT,

        max_profit REAL,
        max_drawdown REAL,

        close_time TEXT

    )
    """)

    conn.commit()
    conn.close()

    print("🗄 AHAD AI DATABASE READY")


# ================================================
# 💾 TRADE RECORDER (STAGE 2)
# ================================================

def save_trade(trade_data):
    """حفظ الصفقة في قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        
        cur.execute("""
        INSERT INTO trades (
            symbol, side, signal_time,
            entry, sl, tp1, tp2, tp3,
            sector, score,
            brain_long, brain_short,
            flow, momentum, rr,
            confidence, late_score,
            version,
            status, result,
            max_profit, max_drawdown,
            close_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['symbol'],
            trade_data['side'],
            trade_data['signal_time'],
            trade_data['entry'],
            trade_data['sl'],
            trade_data['tp1'],
            trade_data['tp2'],
            trade_data['tp3'],
            trade_data['sector'],
            trade_data['score'],
            trade_data['brain_long'],
            trade_data['brain_short'],
            trade_data['flow'],
            trade_data['momentum'],
            trade_data['rr'],
            trade_data['confidence'],
            trade_data['late_score'],
            trade_data.get('version', 'v20.5.0'),
            'OPEN',
            'PENDING',
            0.0,
            0.0,
            None
        ))
        
        conn.commit()
        trade_id = cur.lastrowid
        conn.close()
        
        print(f"💾 Trade saved: {trade_data['symbol']} (ID: {trade_id})")
        return trade_id
        
    except Exception as e:
        print(f"❌ Error saving trade: {e}")
        return None


# ================================================
# 🌐 RENDER KEEP ALIVE SERVER
# ================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v20.5.0 STAGE 2 ONLINE 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ================================================
# 🏦 SECTOR DATABASE
# ================================================

SECTORS = {
    "AI": ["FET", "TAO", "WLD", "ARKM", "AI", "RENDER"],
    "GAMING": ["APE", "SAND", "MANA", "GALA", "IMX", "AXS"],
    "DEFI": ["UNI", "AAVE", "LINK", "CRV", "MKR", "COMP"],
    "MEME": ["DOGE", "SHIB", "PEPE", "BONK", "FLOKI"],
    "LAYER1": ["SOL", "AVAX", "DOT", "NEAR", "ADA"],
    "RWA": ["ONDO", "PENDLE", "ENA"]
}


# ================================================
# ⬛ OKX FUTURES CRYPTO ONLY
# ================================================

def get_symbols():
    try:
        url = "https://www.okx.com/api/v5/public/instruments"
        params = {"instType": "SWAP"}
        data = requests.get(url, params=params, timeout=15).json()

        blocked = [
            "TSLA", "AMZN", "AAPL", "NVDA", "META", "GOOGL", "MSFT", "NFLX",
            "AMD", "COIN", "MSTR", "BABA", "PLTR", "HOOD",
            "SPX", "NASDAQ", "DOW",
            "XAU", "XAG", "WTI", "BRENT",
            "EUR", "GBP", "JPY", "AUD", "CAD", "CHF",
            "USDT_ETF", "BTC_ETF", "ETH_ETF"
        ]

        result = []
        for x in data["data"]:
            symbol = x["instId"]
            if (
                x["settleCcy"] == "USDT"
                and x["state"] == "live"
                and x.get("ctType") == "linear"
                and "USD" not in x["instId"].replace("USDT", "")
                and not any(b in symbol for b in blocked)
                and not any(b in symbol.split("-")[0] for b in blocked)
            ):
                result.append(symbol)

        print("🐋 MARKETS FOUND:", len(result))
        return result

    except Exception as e:
        print("SYMBOL ERROR:", e)
        return []


# ================================================
# 🐋 TOP FLOW SCANNER (DYNAMIC)
# ================================================

def top_flow_scanner(symbols):
    results = []
    for symbol in symbols:
        try:
            c15 = get_candles(symbol, "15m")
            if len(c15) < 50:
                continue

            volumes = [x["volume"] for x in c15]
            closes = [x["close"] for x in c15]

            vol_now = sum(volumes[-5:])
            vol_avg = sum(volumes[-40:]) / 40

            if vol_avg == 0:
                continue

            flow = vol_now / vol_avg
            move = ((closes[-1] - closes[-20]) / closes[-20]) * 100

            if move > 10:
                continue

            if flow >= 1.15:
                results.append({"coin": symbol, "flow": flow})

        except Exception as e:
            print(symbol, e)

        time.sleep(0.01)

    if len(results) == 0:
        return [], 0

    flow_candidates = len(results)

    results.sort(key=lambda x: x["flow"], reverse=True)

    best_flow = results[0]["flow"]
    dynamic_threshold = best_flow * FLOW_RATIO

    selected = []

    for coin_data in results:
        if len(selected) >= MAX_FLOW_COINS:
            break
        if coin_data["flow"] >= dynamic_threshold:
            selected.append(coin_data["coin"])

    if len(selected) < MIN_FLOW_COINS:
        selected = [x["coin"] for x in results[:MIN_FLOW_COINS]]

    return selected, flow_candidates


# ================================================
# 🕯 OKX CANDLES ENGINE
# ================================================

def get_candles(symbol, tf):
    try:
        frames = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": symbol, "bar": frames[tf], "limit": 150}

        data = requests.get(url, params=params, timeout=10).json()

        if not data or "data" not in data or not data["data"]:
            return []

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
        print("CANDLE ERROR:", symbol, e)
        return []


init_database()
print("🔥 AHAD AI v20.5.0 STAGE 2 CORE READY 🐋")


# ================================================
# 📊 INDICATORS ENGINE
# ================================================

def ema(values, period):
    if len(values) < period:
        return values[-1]

    k = 2 / (period + 1)
    result = values[0]

    for v in values:
        result = v * k + result * (1 - k)

    return result


def rsi(values, period=14):
    gains = 0
    losses = 0

    for i in range(-period, -1):
        diff = values[i + 1] - values[i]
        if diff > 0:
            gains += diff
        else:
            losses -= diff

    if losses == 0:
        return 100

    rs = gains / losses
    return 100 - 100 / (1 + rs)


def atr(candles):
    ranges = []
    for c in candles[-14:]:
        ranges.append(c["high"] - c["low"])
    return sum(ranges) / len(ranges)


def macd_simple(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow:
        return 0
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    return ema_fast - ema_slow


# ================================================
# 🧠 SECTION 2: AI ENGINES
# ================================================

_candle_cache = {}

def get_candles_cached(symbol, tf):
    key = f"{symbol}_{tf}"
    if key in _candle_cache:
        return _candle_cache[key]
    candles = get_candles(symbol, tf)
    _candle_cache[key] = candles
    return candles


# ================================================
# 🏦 SECTOR FLOW ENGINE
# ================================================

def sector_flow(symbols):
    try:
        result = {}
        ranking = []

        for sector, coins in SECTORS.items():
            total = 0
            matched = 0

            for symbol in symbols:
                base = symbol.split("-")[0]

                if base in coins:
                    candles = get_candles_cached(symbol, "1h")

                    if len(candles) > 50:
                        volumes = [x["volume"] for x in candles]
                        recent = sum(volumes[-5:])
                        average = sum(volumes[-50:]) / 50

                        if average > 0:
                            total += recent / average
                            matched += 1

            power = round(total / matched, 2) if matched > 0 else 0

            result[sector] = power
            ranking.append((sector, power))

        ranking = sorted(ranking, key=lambda x: x[1], reverse=True)

        return {
            "sector": ranking[0][0],
            "power": ranking[0][1],
            "ranking": ranking[:3]
        }

    except Exception as e:
        print("SECTOR ERROR:", e)
        return {
            "sector": "UNKNOWN",
            "power": 0,
            "ranking": []
        }


# ================================================
# 🐋 SMART MONEY ENGINE
# ================================================

def smart_money(candles):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            flow = 0
        else:
            flow = volume_now / volume_avg

        volume_avg_20 = sum(volumes[-20:]) / 4
        volume_acceleration = volume_now / volume_avg_20 if volume_avg_20 > 0 else 0

        move = ((closes[-1] - closes[-24]) / closes[-24]) * 100

        if flow >= 1.5 and abs(move) < 8:
            status = "🐋 SMART ACCUMULATION"
        elif flow >= 1.5 and move > 8:
            status = "🚨 WHALE EXIT"
        else:
            status = "NORMAL"

        return {
            "flow": round(flow, 2),
            "status": status,
            "volume_acceleration": round(volume_acceleration, 2)
        }

    except Exception as e:
        print("SMART MONEY ERROR:", e)
        return {"flow": 0, "status": "ERROR", "volume_acceleration": 0}


# ================================================
# 🐋 PRE PUMP ENGINE
# ================================================

def pre_pump_engine(candles):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        price = closes[-1]
        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            return {"status": "NORMAL", "score": 0}

        flow = volume_now / volume_avg
        move = ((price - closes[-30]) / closes[-30]) * 100
        current_rsi = rsi(closes)

        if (
            flow >= 1.20
            and abs(move) < 4
            and 40 <= current_rsi <= 60
        ):
            return {"status": "🐋 WHALE LOADING", "score": 25}

        return {"status": "NORMAL", "score": 0}

    except Exception as e:
        print("PRE PUMP ERROR:", e)
        return {"status": "ERROR", "score": 0}


# ================================================
# 🔥 VOLATILITY COMPRESSION ENGINE
# ================================================

def volatility_engine(candles):
    try:
        if len(candles) < 60:
            return {
                "score": 0,
                "status": "UNKNOWN"
            }

        recent = candles[-20:]

        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        price_range = max(highs) - min(lows)

        atr_now = atr(candles[-14:])
        atr_old = atr(candles[-60:-46])

        if atr_old == 0:
            compression = 0
        else:
            compression = (1 - (atr_now / atr_old)) * 100

        compression = max(0, min(100, compression))

        if compression >= 70:
            status = "🔥 SPRING LOADED"
        elif compression >= 50:
            status = "⚡ BUILDING PRESSURE"
        else:
            status = "NORMAL"

        return {
            "score": round(compression),
            "status": status,
            "range": round(price_range, 6)
        }

    except Exception as e:
        print("VOLATILITY ERROR:", e)
        return {
            "score": 0,
            "status": "ERROR",
            "range": 0
        }


# ================================================
# 📊 MULTI TIMEFRAME ENGINE
# ================================================

def multi_rsi_engine(c15, c1h, c4h, c1d):
    try:
        data = {}
        frames = {"15m": c15, "1h": c1h, "4h": c4h, "1d": c1d}
        score = 0

        for name, candles in frames.items():
            closes = [x["close"] for x in candles]
            value = rsi(closes)
            data[name] = round(value, 2)

            if 50 <= value <= 70:
                score += 10
            elif value > 75:
                score -= 10
            elif value < 35:
                score += 5

        data["score"] = score
        return data

    except Exception as e:
        print("MULTI RSI ERROR:", e)
        return {"15m": 50, "1h": 50, "4h": 50, "1d": 50, "score": 0}


# ================================================
# 🧱 SUPPORT RESISTANCE ENGINE
# ================================================

def support_resistance(candles):
    highs = [x["high"] for x in candles[-80:]]
    lows = [x["low"] for x in candles[-80:]]
    price = candles[-1]["close"]

    support = min(lows)
    resistance = max(highs)

    return {
        "support": support,
        "resistance": resistance,
        "near_support": ((price - support) / price) * 100,
        "near_resistance": ((resistance - price) / price) * 100
    }


# ================================================
# 🛡 ANTI LATE ENTRY (FOMO FILTER)
# ================================================

def fomo_filter(candles):
    closes = [x["close"] for x in candles]
    price = closes[-1]

    move = ((price - closes[-96]) / closes[-96]) * 100
    current_rsi = rsi(closes)

    if move > 5 and current_rsi > 65:
        return False, "⏳ WAIT PULLBACK"

    if move > 8:
        return False, "🚫 MOVE DONE - WAIT RETEST"

    if current_rsi > 75:
        return False, "🚫 RSI HOT"

    return True, "🐋 EARLY ENTRY AREA"


# ================================================
# 🪤 TRAP DETECTOR
# ================================================

def trap_detector(candles):
    closes = [x["close"] for x in candles]
    highs = [x["high"] for x in candles]
    lows = [x["low"] for x in candles]

    price = closes[-1]
    r = rsi(closes)

    if price >= max(highs[-50:]) * 0.98 and r > 70:
        return "🪤 BULL TRAP"

    if price <= min(lows[-50:]) * 1.02 and r < 35:
        return "🪤 BEAR TRAP"

    return "✅ NO TRAP"


# ================================================
# 🧠 AI BRAIN ENGINE (v20.5.0)
# ================================================

def ai_brain(candles):
    closes = [x["close"] for x in candles]
    price = closes[-1]

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e100 = ema(closes, 100)

    long_score = 0
    short_score = 0

    # ==========================================
    # Price Position
    # ==========================================

    if price > e20:
        long_score += 25
    else:
        short_score += 25

    # ==========================================
    # EMA Alignment
    # ==========================================

    if e20 > e50:
        long_score += 20
    else:
        short_score += 20

    if e50 > e100:
        long_score += 20
    else:
        short_score += 20

    # ==========================================
    # EMA Slope
    # ==========================================

    if len(closes) >= 5:

        old20 = ema(closes[:-4], 20)

        if e20 > old20:
            long_score += 15
        elif e20 < old20:
            short_score += 15

    # ==========================================
    # Distance From EMA20
    # ==========================================

    distance = abs(price - e20) / e20

    if distance < 0.01:
        long_score += 10
        short_score += 10

    # ==========================================
    # Confidence
    # ==========================================

    confidence = abs(long_score - short_score)

    # ==========================================
    # Direction
    # ==========================================

    if long_score >= 60 and long_score > short_score:
        direction = "🟢 LONG"

    elif short_score >= 60 and short_score > long_score:
        direction = "🔴 SHORT"

    else:
        direction = "WAIT"

    return {
        "direction": direction,
        "confidence": confidence,
        "long_score": long_score,
        "short_score": short_score
    }
    # ================================================
# 🎯 SECTION 3: ANALYZE ENGINE (v20.5.0)
# ================================================

def analyze(symbol, sector, debug=None):
    try:

        reject_reason = ""

        if debug is not None:
            debug["checked"] = debug.get("checked", 0) + 1

        # ================================================
        # 🛡️ ASSET VALIDATION
        # ================================================

        blocked_assets = [
            "TSLA", "AMZN", "AAPL", "NVDA", "META", "GOOGL", "MSFT", "NFLX",
            "AMD", "COIN", "MSTR", "BABA", "PLTR", "HOOD",
            "SPX", "NASDAQ", "DOW",
            "XAU", "XAG", "WTI", "BRENT",
            "EUR", "GBP", "JPY", "AUD", "CAD", "CHF",
            "USDT_ETF", "BTC_ETF", "ETH_ETF"
        ]

        base = symbol.split("-")[0]
        if base in blocked_assets:
            reject_reason = "Blocked Asset"
            return None

        c15 = get_candles(symbol, "15m")
        c1h = get_candles(symbol, "1h")
        c4h = get_candles(symbol, "4h")
        c1d = get_candles(symbol, "1d")

        if len(c15) < 60 or len(c1h) < 60 or len(c4h) < 60 or len(c1d) < 60:
            reject_reason = "Candles"
            if debug is not None:
                debug["candles"] = debug.get("candles", 0) + 1
            return None

        price = c15[-1]["close"]

        safe, warning = fomo_filter(c15)
        if not safe:
            reject_reason = "FOMO"
            if debug is not None:
                debug["fomo"] = debug.get("fomo", 0) + 1
            return None

        brain = ai_brain(c1h)
        debug_reason = []

        if brain["direction"] == "WAIT":
            brain_penalty = 10
            reject_reason = "Brain"
            if debug is not None:
                debug["brain"] = debug.get("brain", 0) + 1
        else:
            brain_penalty = 0

        sr = support_resistance(c15)
        money = smart_money(c15)
        pre = pre_pump_engine(c15)
        multi = multi_rsi_engine(c15, c1h, c4h, c1d)
        trap = trap_detector(c15)

        vol = volatility_engine(c15)

        closes15 = [x["close"] for x in c15]
        closes1h = [x["close"] for x in c1h]
        closes4h = [x["close"] for x in c4h]
        closes1d = [x["close"] for x in c1d]

        rsi_15m = rsi(closes15)
        rsi_1h = rsi(closes1h)
        rsi_4h = rsi(closes4h)
        rsi_1d = rsi(closes1d)

        flow = money["flow"]

        # ================================================
        # 🔥 SMART RSI
        # ================================================

        rsi_score = 0
        if 45 <= rsi_15m <= 62:
            rsi_score = 8
        elif 62 < rsi_15m <= 70:
            rsi_score = 5
            warning = "⚠️ RSI WARNING"
        elif rsi_15m > 70 or rsi_15m < 35:
            rsi_score = -10
            warning = "⚠️ RSI EXTREME"

        # ================================================
        # 💧 DYNAMIC FLOW
        # ================================================

        flow_score = 0
        if flow < 0.8:
            reject_reason = "Low Flow"
            if debug is not None:
                debug["flow"] = debug.get("flow", 0) + 1
            return None
        elif flow >= 1.8:
            flow_score = 20
            flow_status = "🚀 WHALE FLOW"
        elif flow >= 1.2:
            flow_score = 10
            flow_status = "💧 HEALTHY FLOW"
        else:
            flow_score = 5
            flow_status = "NORMAL"

        # ================================================
        # 📈 MACD MOMENTUM
        # ================================================

        macd_value = macd_simple(closes15)
        macd_score = 3 if macd_value > 0 else 0

        # ================================================
        # 🔥 MULTI TIMEFRAME VALIDATOR
        # ================================================

        tf_score = 0
        tf_alignment = True

        ema20_15 = ema(closes15, 20)
        if price > ema20_15:
            tf_score += 5
        else:
            tf_alignment = False

        ema20_1h = ema(closes1h, 20)
        if closes1h[-1] > ema20_1h:
            tf_score += 5
        else:
            tf_alignment = False

        ema20_4h = ema(closes4h, 20)
        if closes4h[-1] < ema20_4h * 0.97:
            tf_score -= 10

        # ================================================
        # 🔥 STRONG CANDLE CHECK
        # ================================================

        candle_score = 0
        last_candle = c15[-1]
        body = abs(last_candle["close"] - last_candle["open"])
        avg_body = sum([abs(c["close"] - c["open"]) for c in c15[-20:]]) / 20

        if last_candle["close"] > last_candle["open"] and body > avg_body * 1.2:
            candle_score += 5
        elif body < (last_candle["high"] - last_candle["low"]) * 0.1:
            candle_score -= 5

        # ================================================
        # 📊 DYNAMIC LATE ENTRY v20.5.0
        # ================================================

        move = atr(c15)

        ema20_15 = ema(closes15, 20)
        ema50_15 = ema(closes15, 50)
        ema100_15 = ema(closes15, 100)

        late_score = 0

        # --------------------------------
        # Distance from EMA50
        # --------------------------------
        distance = price - ema50_15

        if distance > move * 0.5:
            late_score += 20

        if distance > move * 1.0:
            late_score += 20

        # --------------------------------
        # Healthy Trend Bonus
        # --------------------------------
        if ema20_15 > ema50_15 > ema100_15:
            late_score -= 10

        if price > ema20_15:
            late_score -= 5

        # --------------------------------
        # Strong Momentum Penalty
        # --------------------------------
        last3_gain = (
            (closes15[-1] - closes15[-4]) / closes15[-4]
        )

        if last3_gain > 0.06:
            late_score += 15

        # --------------------------------
        # Decision
        # --------------------------------
        if late_score >= 35:

            reject_reason = "Late Entry"

            if debug is not None:
                debug["late_entry"] = debug.get("late_entry", 0) + 1
                debug["late_score"] = late_score

            early_text = "⏳ WAIT RETEST"

            return None

        else:

            if debug is not None:
                debug["late_score"] = late_score

            early_text = "🐋 EARLY ENTRY AREA"

        # ================================================
        # 🚀 ENHANCED MOMENTUM ENGINE
        # ================================================

        if len(closes15) >= 10:
            price_change_5 = ((closes15[-1] - closes15[-5]) / closes15[-5]) * 100
            price_change_10 = ((closes15[-1] - closes15[-10]) / closes15[-10]) * 100
            price_velocity = (price_change_5 * 0.6) + (price_change_10 * 0.4)
        else:
            price_velocity = 0

        volume_acceleration = money.get("volume_acceleration", 0)

        recent_high = max([x["high"] for x in c15[-20:]])
        recent_low = min([x["low"] for x in c15[-20:]])
        range_width = recent_high - recent_low
        if range_width > 0:
            breakout_strength = ((price - recent_low) / range_width) * 100
        else:
            breakout_strength = 50

        momentum_score = 0

        if price_velocity > 3:
            momentum_score += 40
        elif price_velocity > 1:
            momentum_score += 25
        elif price_velocity > 0:
            momentum_score += 10

        if volume_acceleration > 2:
            momentum_score += 30
        elif volume_acceleration > 1.5:
            momentum_score += 20
        elif volume_acceleration > 1.2:
            momentum_score += 10

        if breakout_strength > 80:
            momentum_score += 30
        elif breakout_strength > 60:
            momentum_score += 20
        elif breakout_strength > 50:
            momentum_score += 10

        momentum_score = min(100, momentum_score)

        if momentum_score >= 70:
            momentum_status = "🔥 Strong"
        elif momentum_score >= 50:
            momentum_status = "⚡ Moderate"
        else:
            momentum_status = "⚠️ Weak"

        # ================================================
        # 🧠 REBALANCED SCORE ENGINE
        # ================================================

        score = 0

        score += brain["confidence"] * 0.3
        score += flow_score * 1.5
        score += momentum_score * 0.2 * 1.5

        if sr["near_resistance"] > 5:
            score += 10
        elif sr["near_resistance"] > 3:
            score += 5

        if trap == "✅ NO TRAP":
            score += 10

        score += multi["score"] * 0.1
        score += rsi_score * 0.5
        score += macd_score * 0.5

        score -= brain_penalty

        score = round(max(0, min(100, score)))

        # ================================================
        # 🔥 PENALTIES
        # ================================================

        late_penalty = 0
        if rsi_15m >= 68:
            late_penalty += 20
        score -= late_penalty
        score = max(0, score)

        if len(c15) >= 6:
            pump = c15[-1]["close"] / c15[-6]["close"]
            if pump > 1.05:
                score -= 15

        # ================================================
        # 🔥 BULL TRAP CHECK
        # ================================================

        if trap == "🪤 BULL TRAP":
            reject_reason = "Trap"
            if debug is not None:
                debug["trap"] = debug.get("trap", 0) + 1
            return None

        # ================================================
        # 🔥 HEAT CONTROL
        # ================================================

        if multi["4h"] > 70:
            score -= 10
        if multi["1d"] > 70:
            score -= 10
        if multi["15m"] > 75:
            score -= 5

        # ================================================
        # 🔥 RESISTANCE FILTER
        # ================================================

        distance_to_resistance = sr["near_resistance"] * price / 100
        if distance_to_resistance < move * 1.2:
            reject_reason = "Too Close Resistance"
            if debug is not None:
                debug["resistance"] = debug.get("resistance", 0) + 1
            return None

        # ================================================
        # 🔥 HIGHER TIMEFRAME TREND FILTER
        # ================================================

        e200_4h = ema(closes4h, 200)
        if brain["direction"] == "🟢 LONG" and closes4h[-1] < e200_4h:
            reject_reason = "Higher Trend Down"
            if debug is not None:
                debug["higher_trend"] = debug.get("higher_trend", 0) + 1
            return None

        # ================================================
        # 🔥 MINIMUM SCORE FILTER
        # ================================================

        MIN_SCORE = 68
        if score < MIN_SCORE:
            reject_reason = f"Low Score ({score})"
            if debug is not None:
                debug["score"] = debug.get("score", 0) + 1
            return None

        # ================================================
        # ⭐ QUALITY LEVEL
        # ================================================

        if score >= 85:
            quality = "ELITE ✅"
        elif score >= 70:
            quality = "HIGH QUALITY ✅"
        else:
            reject_reason = "Watchlist Only"
            if debug is not None:
                debug["watchlist"] = debug.get("watchlist", 0) + 1
            return None

        # ================================================
        # 🧠 CONFIDENCE LEVEL
        # ================================================

        if score >= 85:
            confidence_level = "🔥 HIGH"
        elif score >= 70:
            confidence_level = "⚡ MEDIUM"
        else:
            confidence_level = "⏳ LOW"

        # ================================================
        # 🐋 MONEY STATUS
        # ================================================

        if flow >= 3:
            money_status = "🚀 WHALE BUYING"
        elif flow >= 2:
            money_status = "🐋 SMART ACCUMULATION"
        elif flow >= 1.2:
            money_status = "💧 HEALTHY FLOW"
        else:
            money_status = "NORMAL"

        # ================================================
        # 🎯 EARLY ENTRY CHECK
        # ================================================

        if (
            momentum_score >= 60
            and flow >= 1.2
            and sr["near_resistance"] > 3
        ):
            early_text = "🐋 EARLY ENTRY AREA"
        else:
            early_text = "⏳ WAIT FOR ENTRY"

        # ================================================
        # 🎯 ENTRY ZONE & TARGETS
        # ================================================

        entry_low = price * 0.995
        entry_high = price * 1.005

        if brain["direction"] == "🟢 LONG":
            direction = "LONG"

            base_multiplier = 1.5
            if flow >= 2:
                base_multiplier += 0.3
            if money_status in ["🚀 WHALE BUYING", "🐋 SMART ACCUMULATION"]:
                base_multiplier += 0.3
            if momentum_score >= 70:
                base_multiplier += 0.2

            sl = entry_low - move * base_multiplier
            risk = entry_low - sl

            tp1 = entry_low + risk * 1.5
            tp2 = entry_low + risk * 3.0
            tp3 = entry_low + risk * 5.0

            if tp1 <= entry_high:
                tp1 = entry_high + move * 0.8

            if tp2 <= tp1:
                tp2 = tp1 + move * 0.5
            if tp3 <= tp2:
                tp3 = tp2 + move * 0.5

            rr = (tp1 - entry_low) / risk

        else:
            direction = "SHORT"
            base_multiplier = 1.5
            if flow >= 2:
                base_multiplier += 0.3
            if money_status in ["🚀 WHALE BUYING", "🐋 SMART ACCUMULATION"]:
                base_multiplier += 0.3
            if momentum_score >= 70:
                base_multiplier += 0.2

            sl = entry_high + move * base_multiplier
            risk = sl - entry_high

            tp1 = entry_high - risk * 1.5
            tp2 = entry_high - risk * 3.0
            tp3 = entry_high - risk * 5.0

            if tp1 >= entry_low:
                tp1 = entry_low - move * 0.8

            if tp2 >= tp1:
                tp2 = tp1 - move * 0.5
            if tp3 >= tp2:
                tp3 = tp2 - move * 0.5

            rr = (entry_high - tp1) / risk

        # ================================================
        # 🛡️ VALIDATION LAYER
        # ================================================

        validation_errors = []

        if direction == "LONG":
            if sl >= entry_low:
                validation_errors.append("SL must be below Entry")
            if tp1 <= entry_low:
                validation_errors.append("TP1 must be above Entry")
            if tp2 <= tp1:
                validation_errors.append("TP2 must be above TP1")
            if tp3 <= tp2:
                validation_errors.append("TP3 must be above TP2")
        else:
            if sl <= entry_high:
                validation_errors.append("SL must be above Entry")
            if tp1 >= entry_high:
                validation_errors.append("TP1 must be below Entry")
            if tp2 >= tp1:
                validation_errors.append("TP2 must be below TP1")
            if tp3 >= tp2:
                validation_errors.append("TP3 must be below TP2")

        if rr <= 0:
            validation_errors.append("RR must be positive")

        if base in blocked_assets:
            validation_errors.append("Blocked Asset")

        if sector == "UNKNOWN":
            validation_errors.append("Invalid Sector")

        if entry_low <= 0 or entry_high <= 0:
            validation_errors.append("Invalid Entry")

        if sl <= 0:
            validation_errors.append("Invalid SL")

        if tp1 <= 0 or tp2 <= 0 or tp3 <= 0:
            validation_errors.append("Invalid TP")

        if rr < 1.8:
            reject_reason = "Bad RR (Validation)"
            if debug is not None:
                debug["rr"] = debug.get("rr", 0) + 1
            return None

        if validation_errors:
            reject_reason = f"Validation Failed: {', '.join(validation_errors)}"
            if debug is not None:
                debug["validation"] = debug.get("validation", 0) + 1
            return None

        # ================================================
        # 🐞 DEBUG REASON
        # ================================================

        if brain["direction"] != "🟢 LONG":
            debug_reason.append(f"Brain={brain['direction']}")

        if brain["long_score"] < brain["short_score"]:
            debug_reason.append("LongScore<ShortScore")

        if momentum_status != "🔥 Strong" and momentum_status != "⚡ Moderate":
            debug_reason.append(f"Momentum={momentum_status}")

        if score < MIN_SCORE:
            debug_reason.append(f"Score={round(score)}")

        if debug is not None:
            debug["passed"] = debug.get("passed", 0) + 1
            debug["reject_reason"] = reject_reason
            debug["debug_reason"] = debug_reason

        # ====== TRADE DATA FOR RECORDER (STAGE 2) ======
        trade_data = {
            'symbol': symbol,
            'side': brain['direction'].replace('🟢 ', '').replace('🔴 ', ''),
            'signal_time': datetime.now().isoformat(),
            'entry': round(entry_low, 6),
            'sl': round(sl, 6),
            'tp1': round(tp1, 6),
            'tp2': round(tp2, 6),
            'tp3': round(tp3, 6),
            'sector': sector,
            'score': round(score),
            'brain_long': brain['long_score'],
            'brain_short': brain['short_score'],
            'flow': round(flow, 2),
            'momentum': momentum_score,
            'rr': round(rr, 2),
            'confidence': confidence_level,
            'late_score': late_score,
            'version': 'v20.5.0'
        }
        # =================================================

        return {
            "coin": symbol,
            "sector": sector,
            "direction": brain["direction"],
            "score": round(score),
            "quality": quality,
            "confidence_level": confidence_level,
            "money_status": money_status,
            "early_text": early_text,
            "entry_low": round(entry_low, 6),
            "entry_high": round(entry_high, 6),
            "sl": round(sl, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "tp3": round(tp3, 6),
            "liquidity": money["flow"],
            "pre_pump": pre["status"],
            "multi": multi,
            "trap": trap,
            "warning": warning,
            "volatility": vol,
            "reject_reason": reject_reason,
            "debug_reason": debug_reason,
            "momentum_score": momentum_score,
            "momentum_status": momentum_status,
            "rr": round(rr, 2),
            "brain_long_score": brain["long_score"],
            "brain_short_score": brain["short_score"],
            "trade_data": trade_data  # <-- Added for STAGE 2
        }

    except Exception as e:
        print("ANALYZE ERROR:", e)
        return None
        # ================================================
# 🤖 SECTION 4: TELEGRAM SCANNER (v20.5.0)
# ================================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, """
🐋 AHAD AI v20.5.0 STAGE 2 ONLINE 🚀

🗄 Database Foundation ACTIVE
💾 Trade Recorder ACTIVE
🧠 AI Brain v2.0 ACTIVE
🐋 Smart Money ACTIVE
📊 Multi TimeFrame ACTIVE
🪤 Trap Detector ACTIVE
⚡ Pre-Pump Detection ACTIVE
🔥 Heat Control ACTIVE
🎯 Dynamic Late Entry v2 ACTIVE
📊 Enhanced Score System ACTIVE
🐞 Full Debug Funnel ACTIVE
🔥 Volatility Compression ACTIVE
🚀 Enhanced Momentum Engine ACTIVE
📌 Reject Reason ACTIVE
🧠 Confidence Level ACTIVE
🎯 New RR Engine ACTIVE
📈 Higher Timeframe Filter ACTIVE
✅ Dynamic Flow Scanner ACTIVE
🛡️ Validation Layer ACTIVE
📊 Brain LONG/SHORT Scores ACTIVE
🐞 Debug Reason ACTIVE

🎯 Goal: Best 3 quality LONG setups

Send /scan
""")


# ================================================
# 🔎 SMART SCANNER (v20.5.0)
# ================================================

@bot.message_handler(commands=["scan"])
def scan(message):
    bot.reply_to(message, """
🐋 AHAD AI v20.5.0 STAGE 2 SCANNING...

🔍 Checking Market Flow
🏦 Finding Hot Sector (Ranked)
🟢 Hunting TOP 3 LONG setups
🐋 Tracking Smart Money
⚡ Detecting Pre-Pump
🚀 Enhanced Momentum Engine ACTIVE
🔥 Heat Control ACTIVE
📊 Enhanced Score System ACTIVE
🐞 Full Debug Funnel ACTIVE
📌 Reject Reason ACTIVE
🎯 New RR Engine ACTIVE
✅ Dynamic Flow Scanner ACTIVE
🛡️ Validation Layer ACTIVE
🧠 Brain v2.0 ACTIVE
🎯 Dynamic Late Entry v2 ACTIVE
🐞 Debug Reason ACTIVE
💾 Trade Recorder ACTIVE

Please wait ⏳
""")

    # ====== FIX v20.5.0 ======
    global _candle_cache
    _candle_cache.clear()
    # =========================

    debug = {}

    long_results = []
    all_symbols = get_symbols()

    symbols, flow_candidates = top_flow_scanner(all_symbols)

    flow = sector_flow(all_symbols)
    hot_sector = flow["sector"]

    ranking = flow["ranking"]
    text = "🔥 MARKET FLOW\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, item in enumerate(ranking):
        text += f"{medals[i]} {item[0]}  |  Flow: {item[1]}\n"

    bot.send_message(message.chat.id, text)

    if len(symbols) < 20:
        symbols = all_symbols

    bot.send_message(message.chat.id, f"💎 Smart Money Watchlist: {len(symbols)} coins")

    for symbol in symbols:

        print("=" * 50)
        print("START:", symbol)

        result = analyze(symbol, hot_sector, debug=debug)

        print("END:", symbol)

        if result:

            if result["score"] > 100:
                result["score"] = 100

            if result["direction"] == "🟢 LONG":

                if (
                    result["score"] >= 68
                    and (
                        result["liquidity"] >= 1.2
                        or result["pre_pump"] == "🐋 WHALE LOADING"
                    )
                ):

                    long_results.append(result)
                    print("ADDED:", result["coin"])

                else:

                    debug["final_gate"] = debug.get("final_gate", 0) + 1
                    debug["reject_reason"] = (
                        "Not Long"
                        if not result.get("debug_reason")
                        else " | ".join(result["debug_reason"])
                    )

                    print(
                        f"GATE REJECT | "
                        f"{result['coin']} | "
                        f"Score={result['score']} | "
                        f"Flow={result['liquidity']} | "
                        f"PrePump={result['pre_pump']} | "
                        f"Reason={debug['reject_reason']}"
                    )

            else:

                debug["not_long"] = debug.get("not_long", 0) + 1
                debug["reject_reason"] = (
                    "Not Long"
                    if not result.get("debug_reason")
                    else " | ".join(result["debug_reason"])
                )

                print(
                    f"SHORT SIGNAL | "
                    f"{result['coin']} | "
                    f"Score={result['score']} | "
                    f"Reason={debug['reject_reason']}"
                )

        time.sleep(0.03)

    checked_count = debug.get('checked', 0)

    debug_msg = f"""
🐞 FULL DEBUG REPORT

Checked: {checked_count}
Flow Candidates: {flow_candidates}
Selected: {len(symbols)}
Candles: {debug.get('candles', 0)}
FOMO: {debug.get('fomo', 0)}
Brain: {debug.get('brain', 0)}
RSI: {debug.get('rsi', 0)}
Low Flow: {debug.get('flow', 0)}
Late Entry: {debug.get('late_entry', 0)}
Late Score: {debug.get('late_score', 0)}
Trap: {debug.get('trap', 0)}
Heat: {debug.get('heat', 0)}
Resistance: {debug.get('resistance', 0)}
Higher Trend: {debug.get('higher_trend', 0)}
RR: {debug.get('rr', 0)}
Score: {debug.get('score', 0)}
Watchlist: {debug.get('watchlist', 0)}
Validation: {debug.get('validation', 0)}
Passed: {debug.get('passed', 0)}
Final Gate: {debug.get('final_gate', 0)}
Not Long: {debug.get('not_long', 0)}
Reject Reason: {debug.get('reject_reason', 'NONE')}
"""
    bot.send_message(message.chat.id, debug_msg)

    results = sorted(long_results, key=lambda x: (x["score"], x["liquidity"]), reverse=True)[:3]

    if not results:
        bot.send_message(message.chat.id, """
👀 No sniper setup now

🐋 Smart Money not ready
⏳ Waiting next liquidity wave
""")
        return

    for s in results:
        msg = f"""
🚨 AHAD AI v20.5.0 STAGE 2 🐋

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

{s['quality']}
🧠 Confidence: {s['confidence_level']}
📊 Brain Scores | LONG: {s['brain_long_score']} | SHORT: {s['brain_short_score']}

🔥 Score: {s['score']}/100 | 💧Flow: {s['liquidity']}X
🐋 Money: {s['money_status']}
⚡ Momentum: {s['momentum_score']}/100 {s['momentum_status']}
📊 RR: {s['rr']}
🪤 Trap: {s['trap']}

🎯 Entry: {round(s['entry_low'],6)} - {round(s['entry_high'],6)}
🛑 SL: {round(s['sl'],6)}

🥇 TP1: {round(s['tp1'],6)}
🥈 TP2: {round(s['tp2'],6)}
🥉 TP3: {round(s['tp3'],6)}

📊 RSI:
15m:{s['multi']['15m']} | 1H:{s['multi']['1h']}
4H:{s['multi']['4h']} | 1D:{s['multi']['1d']}

⚠️ {s['warning']}
{s['early_text']}
"""

        # ====== SAVE TRADE TO DATABASE (STAGE 2) ======
        if s.get('trade_data'):
            trade_id = save_trade(s['trade_data'])
            if trade_id:
                msg += f"\n\n💾 Trade ID: #{trade_id}"
                print(f"✅ Trade #{trade_id} saved for {s['coin']}")
            else:
                msg += "\n\n❌ Failed to save trade"
        # =============================================

        bot.send_message(message.chat.id, msg)


# ================================================
# 🚀 SECTION 5: SYSTEM
# ================================================

# ================================================
# 🐋 KEEP ALIVE ENGINE
# ================================================

def keep_alive():
    while True:
        try:
            url = os.environ.get("RENDER_URL")
            if url:
                urllib.request.urlopen(url, timeout=10)
                print("🐋 KEEP ALIVE ACTIVE")
        except Exception as e:
            print("KEEP ALIVE ERROR:", e)
        time.sleep(300)


# ================================================
# 🚀 START SYSTEM
# ================================================

def telegram_engine():
    backoff = 5
    while True:
        try:
            print("🐋 TELEGRAM ENGINE STARTED")
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
            backoff = 5
        except Exception:
            print("🚨 TELEGRAM ERROR")
            print(traceback.format_exc())
            print(f"🔄 Restarting Telegram in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=telegram_engine, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

print("🔥 AHAD AI v20.5.0 STAGE 2 ONLINE 🐋")
print(f"📅 Started at: {time.ctime()}")
print(f"🐍 Python Version: {os.sys.version}")
print(f"⚙️ MIN_FLOW_COINS: {MIN_FLOW_COINS}")
print(f"⚙️ MAX_FLOW_COINS: {MAX_FLOW_COINS}")
print(f"⚙️ FLOW_RATIO: {FLOW_RATIO}")
print("🛡️ Validation Layer ACTIVE")
print("🗑️ Cache cleared on each scan")
print("🧠 Brain v2.0 ACTIVE")
print("🎯 Dynamic Late Entry v2 ACTIVE")
print("🐞 Debug Reason ACTIVE")
print("🗄️ Database Foundation ACTIVE")
print("💾 Trade Recorder ACTIVE (STAGE 2)")
print("⏳ STAGE 3 NOT STARTED")

while True:
    time.sleep(60)
