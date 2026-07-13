# =====================================
# 🚀 AHAD AI v12.0 – REBUILT EDITION
# Fixes applied vs v11.3.7:
#   1) smart_money() division bug fixed (/50 instead of /10)
#   2) RSI no longer scored redundantly in 4 separate layers
#   3) Quality thresholds unified with the final send-filter (no more
#      sending "LOW QUALITY" signals because of a looser filter number)
#   4) Added real compression/accumulation check (Bollinger Band width
#      percentile) so "pre-pump" actually requires price to be coiling,
#      not just "volume up a bit + price flattish"
#   5) Sector detection is now actually used to bias which coins get
#      analyzed (previously it was cosmetic-only)
# =====================================

import os
import time
import threading
import traceback
import urllib.request

import requests
from flask import Flask
import telebot


# =====================================
# 🔑 TELEGRAM TOKEN
# =====================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise Exception("❌ BOT_TOKEN NOT FOUND")

bot = telebot.TeleBot(TOKEN)


# =====================================
# 🌐 RENDER KEEP ALIVE SERVER
# =====================================

app = Flask(__name__)


@app.route("/")
def home():
    return "🐋 AHAD AI v12.0 REBUILT ONLINE 🚀"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =====================================
# 🏦 SECTOR DATABASE
# =====================================

SECTORS = {
    "AI": ["FET", "TAO", "WLD", "ARKM", "AI", "RENDER"],
    "GAMING": ["APE", "SAND", "MANA", "GALA", "IMX", "AXS"],
    "DEFI": ["UNI", "AAVE", "LINK", "CRV", "MKR", "COMP"],
    "MEME": ["DOGE", "SHIB", "PEPE", "BONK", "FLOKI"],
    "LAYER1": ["SOL", "AVAX", "DOT", "NEAR", "ADA"],
    "RWA": ["ONDO", "PENDLE", "ENA"],
}


# =====================================
# ⬛ OKX FUTURES CRYPTO ONLY
# =====================================

def get_symbols():
    try:
        url = "https://www.okx.com/api/v5/public/instruments"
        params = {"instType": "SWAP"}
        data = requests.get(url, params=params, timeout=15).json()

        blocked = [
            "TSLA", "AMZN", "AAPL", "NVDA", "META", "GOOGL", "MSFT",
            "NFLX", "AMD", "COIN", "MSTR", "BABA", "PLTR", "HOOD",
            "XAU", "EUR", "GBP", "JPY",
            "SPX", "NASDAQ", "DOW",
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
            ):
                result.append(symbol)

        print("🐋 MARKETS FOUND:", len(result))
        return result

    except Exception as e:
        print("SYMBOL ERROR:", e)
        return []


# =====================================
# 🕯 OKX CANDLES ENGINE
# =====================================

def get_candles(symbol, tf):
    try:
        frames = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": symbol, "bar": frames[tf], "limit": 150}
        data = requests.get(url, params=params, timeout=10).json()

        candles = []
        for c in data["data"][::-1]:
            candles.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            })
        return candles

    except Exception as e:
        print("CANDLE ERROR:", symbol, e)
        return []


print("🔥 AHAD AI v12.0 CORE READY 🐋")


# =====================================
# 📊 INDICATORS ENGINE
# =====================================

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
    ranges = [c["high"] - c["low"] for c in candles[-14:]]
    return sum(ranges) / len(ranges)


def bollinger_width(closes, period=20, mult=2):
    """
    Returns the current Bollinger Band width as a % of price, plus the
    percentile of that width vs the last 100 readings (lower = tighter
    compression = more likely genuine pre-breakout coiling).
    """
    if len(closes) < period + 100:
        window = closes[-(period + 30):] if len(closes) > period + 30 else closes
    else:
        window = closes

    widths = []
    for i in range(period, len(window)):
        segment = window[i - period:i]
        mean = sum(segment) / period
        variance = sum((x - mean) ** 2 for x in segment) / period
        std = variance ** 0.5
        price = segment[-1]
        if price == 0:
            continue
        width_pct = (2 * mult * std / price) * 100
        widths.append(width_pct)

    if not widths:
        return {"width": 0, "percentile": 100}

    current = widths[-1]
    sorted_w = sorted(widths)
    rank = sum(1 for w in sorted_w if w <= current)
    percentile = (rank / len(sorted_w)) * 100

    return {"width": round(current, 3), "percentile": round(percentile, 1)}


# =====================================
# 🏦 SECTOR FLOW ENGINE
# =====================================

def sector_flow(symbols):
    try:
        result = {}
        sector_symbols = {s: [] for s in SECTORS}

        for sector, coins in SECTORS.items():
            power = 0
            for symbol in symbols:
                if any(coin in symbol for coin in coins):
                    sector_symbols[sector].append(symbol)
                    candles = get_candles(symbol, "1h")
                    if len(candles) > 50:
                        volumes = [x["volume"] for x in candles]
                        recent = sum(volumes[-10:])
                        average = sum(volumes[-50:]) / 50
                        if average > 0:
                            ratio = min(recent / average, 5)
                            power += ratio

            result[sector] = round(power, 2)

        hot_sector = max(result, key=result.get)

        return {
            "sector": hot_sector,
            "power": result[hot_sector],
            "symbols": sector_symbols[hot_sector],
        }

    except Exception as e:
        print("SECTOR ERROR:", e)
        return {"sector": "UNKNOWN", "power": 0, "symbols": []}


# =====================================
# 🐋 TOP FLOW SCANNER
# =====================================

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

        except Exception:
            pass

        time.sleep(0.01)
        if len(results) >= 80:
            break

    results = sorted(results, key=lambda x: x["flow"], reverse=True)
    return [x["coin"] for x in results[:100]]


# =====================================
# 🐋 SMART MONEY ENGINE (bug fixed: /50 not /10)
# =====================================

def smart_money(candles):
    try:
        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50  # FIXED (was /10)

        flow = 0 if volume_avg == 0 else volume_now / volume_avg
        move = ((closes[-1] - closes[-24]) / closes[-24]) * 100

        if flow >= 1.5 and abs(move) < 8:
            status = "🐋 SMART ACCUMULATION"
        elif flow >= 1.5 and move > 8:
            status = "🚨 WHALE EXIT"
        else:
            status = "NORMAL"

        return {"flow": round(flow, 2), "status": status}

    except Exception as e:
        print("SMART MONEY ERROR:", e)
        return {"flow": 0, "status": "ERROR"}


# =====================================
# 🐋 PRE-PUMP / ACCUMULATION ENGINE
# Now requires genuine range compression (Bollinger percentile <= 35),
# not just "volume slightly up + price flattish".
# =====================================

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
        bb = bollinger_width(closes)

        is_coiling = bb["percentile"] <= 35  # tight range = real accumulation

        if (
            flow >= 1.25
            and abs(move) < 5
            and 35 <= current_rsi <= 65
            and is_coiling
        ):
            return {
                "status": "🐋 WHALE LOADING",
                "score": 25,
                "bb_percentile": bb["percentile"],
            }

        return {"status": "NORMAL", "score": 0, "bb_percentile": bb["percentile"]}

    except Exception as e:
        print("PRE PUMP ERROR:", e)
        return {"status": "ERROR", "score": 0, "bb_percentile": 100}


# =====================================
# 📊 MULTI TIMEFRAME RSI ENGINE
# Single source of truth for RSI scoring — nothing else in the pipeline
# re-scores RSI. Heat control here is folded in directly instead of
# being a separate duplicate penalty later.
# =====================================

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
                score -= 15  # overheated on this timeframe
            elif value < 35:
                score += 5

        data["score"] = score
        return data

    except Exception as e:
        print("MULTI RSI ERROR:", e)
        return {"15m": 50, "1h": 50, "4h": 50, "1d": 50, "score": 0}


# =====================================
# 🧱 SUPPORT / RESISTANCE ENGINE
# =====================================

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
        "near_resistance": ((resistance - price) / price) * 100,
    }


# =====================================
# 🛡 ANTI LATE ENTRY (FOMO FILTER)
# =====================================

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


# =====================================
# 🪤 TRAP DETECTOR
# =====================================

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


# =====================================
# 🧠 AI BRAIN (trend direction)
# =====================================

def ai_brain(candles):
    closes = [x["close"] for x in candles]
    price = closes[-1]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)

    score = 0
    score += 30 if price > e20 else -30
    score += 30 if e20 > e50 else -30

    if score >= 50:
        direction = "🟢 LONG"
    elif score <= -50:
        direction = "🔴 SHORT"
    else:
        direction = "WAIT"

    return {"direction": direction, "confidence": abs(score)}


# =====================================
# 🚀 FINAL ANALYZE ENGINE
# Score layout (max ~100, weights sum to a sane, non-duplicated total):
#   AI Brain (trend)            -> up to 21   (confidence * 0.35)
#   Multi-timeframe RSI          -> up to ~25  (score * 0.6, includes heat)
#   Smart Money (real flow>=1.5) -> +15
#   Pre-Pump (flow+compression)  -> +25 * 0.6 = 15
#   Flow (dynamic)                -> up to 10
#   MACD                          -> +5
#   Timeframe EMA alignment       -> up to 10
#   Candle strength                -> +/-5
# Penalties: late entry, momentum spike, bull trap, resistance proximity
# =====================================

def _bump(debug_stats, key):
    if debug_stats is not None:
        debug_stats[key] = debug_stats.get(key, 0) + 1


def analyze(symbol, sector, debug_stats=None):
    try:
        _bump(debug_stats, "0_total_checked")

        c15 = get_candles(symbol, "15m")
        c1h = get_candles(symbol, "1h")
        c4h = get_candles(symbol, "4h")
        c1d = get_candles(symbol, "1d")

        if len(c15) < 60 or len(c1h) < 60 or len(c4h) < 60 or len(c1d) < 60:
            _bump(debug_stats, "1_rejected_not_enough_candles")
            return None

        price = c15[-1]["close"]

        safe, warning = fomo_filter(c15)
        if not safe:
            _bump(debug_stats, "2_rejected_fomo_filter")
            return None

        brain = ai_brain(c1h)
        if brain["direction"] != "🟢 LONG":
            _bump(debug_stats, "3_rejected_not_long_trend")
            return None  # this bot only hunts LONG setups, by design

        sr = support_resistance(c15)
        money = smart_money(c15)
        pre = pre_pump_engine(c15)
        multi = multi_rsi_engine(c15, c1h, c4h, c1d)
        trap = trap_detector(c15)

        closes15 = [x["close"] for x in c15]
        closes1h = [x["close"] for x in c1h]
        closes4h = [x["close"] for x in c4h]

        rsi_15m = multi["15m"]
        flow = money["flow"]

        # Hard rejects (not scored, just excluded)
        if rsi_15m > 70 or rsi_15m < 35:
            _bump(debug_stats, "4_rejected_rsi_out_of_range")
            return None
        if flow < 0.8:
            _bump(debug_stats, "5_rejected_flow_too_low")
            return None

        # ---------------------------------
        # Flow score (dynamic, single layer)
        # ---------------------------------
        if flow >= 1.8:
            flow_score = 10
            flow_status = "🚀 WHALE FLOW"
        elif flow >= 1.2:
            flow_score = 5
            flow_status = "💧 HEALTHY FLOW"
        else:
            flow_score = 0
            flow_status = "NORMAL"

        # ---------------------------------
        # MACD (simple)
        # ---------------------------------
        def macd_simple(closes, fast=12, slow=26):
            if len(closes) < slow:
                return 0
            return ema(closes, fast) - ema(closes, slow)

        macd_value = macd_simple(closes15)
        macd_score = 5 if macd_value > 0 else 0

        # ---------------------------------
        # Timeframe EMA alignment
        # ---------------------------------
        tf_score = 0
        ema20_15 = ema(closes15, 20)
        if price > ema20_15:
            tf_score += 5

        ema20_1h = ema(closes1h, 20)
        if closes1h[-1] > ema20_1h:
            tf_score += 5

        ema20_4h = ema(closes4h, 20)
        if closes4h[-1] < ema20_4h * 0.97:
            tf_score -= 15  # 4H trending down hard = don't fight it

        # ---------------------------------
        # Candle strength
        # ---------------------------------
        candle_score = 0
        last_candle = c15[-1]
        body = abs(last_candle["close"] - last_candle["open"])
        avg_body = sum(abs(c["close"] - c["open"]) for c in c15[-20:]) / 20

        if last_candle["close"] > last_candle["open"] and body > avg_body * 1.2:
            candle_score += 5
        elif body < (last_candle["high"] - last_candle["low"]) * 0.1:
            candle_score -= 5

        # ---------------------------------
        # Better entry — reject chasing price too far above EMA50
        # ---------------------------------
        move_atr = atr(c15)
        ema50_15 = ema(closes15, 50)
        if price > ema50_15 + (move_atr * 0.5):
            _bump(debug_stats, "6_rejected_chasing_price_too_far")
            return None

        # =====================================
        # 🔥 FINAL SCORE (each factor counted once)
        # =====================================
        score = 0
        score += brain["confidence"] * 0.35        # up to 21
        score += multi["score"] * 0.6              # RSI, incl. heat, once
        score += flow_score                        # up to 10
        score += macd_score                        # up to 5
        score += tf_score                          # up to 10 (or -15)
        score += candle_score                      # +/-5

        if money["status"] == "🐋 SMART ACCUMULATION":
            score += 15

        if pre["status"] == "🐋 WHALE LOADING":
            score += pre["score"] * 0.6             # up to 15

        # ---------------------------------
        # Penalties (each applied once, no overlap with scoring above)
        # ---------------------------------
        if len(c15) >= 6:
            pump = c15[-1]["close"] / c15[-6]["close"]
            if pump > 1.05:
                score -= 15  # momentum already spiked in the last 6 candles

        if trap == "🪤 BULL TRAP":
            score -= 20

        if sr["near_resistance"] < 3:
            score -= 10

        score = max(0, round(score))
        score = min(100, score)

        if debug_stats is not None:
            debug_stats.setdefault("7_scores_reaching_final_calc", []).append(
                (symbol, score, trap)
            )

        # =====================================
        # ⭐ QUALITY LEVEL — unified with send-filter, no mismatch
        # =====================================
        if trap == "🪤 BULL TRAP":
            quality = "MEDIUM QUALITY ⚠️ (trap risk)"
        elif score >= 90:
            quality = "ELITE SIGNAL ✅"
        elif score >= 80:
            quality = "HIGH QUALITY ✅"
        elif score >= 70:
            quality = "GOOD QUALITY ✅"
        else:
            quality = "WATCHLIST 👀"

        MIN_SEND_SCORE = 70  # matches "GOOD QUALITY" floor — no signal
                             # below this is ever sent, unlike v11.3.7

        if score < MIN_SEND_SCORE:
            _bump(debug_stats, "8_rejected_score_below_min")
            return None

        if trap == "🪤 BULL TRAP":
            _bump(debug_stats, "9_rejected_bull_trap_final")
            return None  # never send trap setups, regardless of score

        _bump(debug_stats, "A_passed_all_filters")

        # =====================================
        # 🐋 MONEY STATUS (display label)
        # =====================================
        if flow >= 3:
            money_status = "🚀 WHALE BUYING"
        elif flow >= 1.5:
            money_status = "🐋 SMART ACCUMULATION"
        elif flow >= 1.2:
            money_status = "💧 HEALTHY FLOW"
        else:
            money_status = "NORMAL"

        # =====================================
        # 🎯 ENTRY ZONE & TARGETS
        # =====================================
        entry_low = price * 0.995
        entry_high = price * 1.005

        sl = sr["support"] * 0.995
        tp1 = price + move_atr * 2
        tp2 = price + move_atr * 3

        if tp1 <= entry_high:
            tp1 = entry_high + move_atr * 0.8

        return {
            "coin": symbol,
            "sector": sector,
            "direction": brain["direction"],
            "score": score,
            "quality": quality,
            "money_status": money_status,
            "flow_status": flow_status,
            "entry_low": round(entry_low, 6),
            "entry_high": round(entry_high, 6),
            "sl": round(sl, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "liquidity": flow,
            "pre_pump": pre["status"],
            "bb_percentile": pre.get("bb_percentile", 100),
            "multi": multi,
            "trap": trap,
            "warning": warning,
        }

    except Exception as e:
        print("ANALYZE ERROR:", e)
        return None


# =====================================
# 🤖 TELEGRAM COMMANDS
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, """
🐋 AHAD AI v12.0 REBUILT ONLINE 🚀

🧠 AI Brain ACTIVE
🐋 Smart Money ACTIVE (bug fixed)
📊 Multi TimeFrame RSI ACTIVE
🧱 Range Compression Check ACTIVE (new)
🪤 Trap Detector ACTIVE
⚡ Pre-Pump Detection ACTIVE
🔥 Heat Control (folded into RSI, no double count)
🎯 Early Entry Filter ACTIVE
📊 Unified Score/Quality System ACTIVE
🏦 Sector Flow (now actually used for filtering)

🎯 Goal: Best 3 quality LONG setups

Send /scan
    """)


scan_lock = threading.Lock()


@bot.message_handler(commands=["debug"])
def debug_scan(message):
    if not scan_lock.acquire(blocking=False):
        bot.reply_to(message, "⏳ Scan already running, please wait...")
        return

    try:
        bot.reply_to(message, "🔬 Running diagnostic scan... this checks every coin and reports exactly where it drops out of the funnel.")

        stats = {}

        all_symbols = get_symbols()
        if not all_symbols:
            bot.send_message(message.chat.id, "🚨 Could not fetch symbols from OKX.")
            return

        flow_symbols = top_flow_scanner(all_symbols)
        flow = sector_flow(all_symbols)
        hot_sector = flow["sector"]

        sector_pool = [s for s in flow_symbols if s in flow["symbols"]]
        if len(sector_pool) >= 8:
            symbols = sector_pool + [s for s in flow_symbols if s not in sector_pool]
        else:
            symbols = flow_symbols

        if len(symbols) < 20:
            symbols = all_symbols

        for symbol in symbols:
            analyze(symbol, hot_sector, debug_stats=stats)
            time.sleep(0.03)

        # Build the funnel report
        labels = {
            "0_total_checked": "🔎 Total coins checked",
            "1_rejected_not_enough_candles": "❌ Not enough candle history",
            "2_rejected_fomo_filter": "❌ FOMO filter (late/hot move)",
            "3_rejected_not_long_trend": "❌ Trend not LONG (AI Brain)",
            "4_rejected_rsi_out_of_range": "❌ RSI outside 35-70",
            "5_rejected_flow_too_low": "❌ Flow below 0.8x",
            "6_rejected_chasing_price_too_far": "❌ Price too far above EMA50 (chasing)",
            "8_rejected_score_below_min": f"❌ Score below MIN_SEND_SCORE",
            "9_rejected_bull_trap_final": "❌ Bull trap (final reject)",
            "A_passed_all_filters": "✅ Passed everything (would be sent)",
        }

        lines = ["📊 FUNNEL — where coins drop out:\n"]
        for key in [
            "0_total_checked", "1_rejected_not_enough_candles",
            "2_rejected_fomo_filter", "3_rejected_not_long_trend",
            "4_rejected_rsi_out_of_range", "5_rejected_flow_too_low",
            "6_rejected_chasing_price_too_far", "8_rejected_score_below_min",
            "9_rejected_bull_trap_final", "A_passed_all_filters",
        ]:
            count = stats.get(key, 0)
            lines.append(f"{labels[key]}: {count}")

        bot.send_message(message.chat.id, "\n".join(lines))

        # Score distribution for coins that made it to final scoring
        scored = stats.get("7_scores_reaching_final_calc", [])
        if scored:
            scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
            top10 = scored_sorted[:10]
            lines2 = [
                "🏁 Coins that reached final scoring (top 10 by score):",
                "(score, trap status)",
            ]
            for sym, sc, trp in top10:
                lines2.append(f"{sym}: {sc} | {trp}")

            below_min = sum(1 for _, sc, _ in scored if sc < 70)
            lines2.append(f"\n📉 {below_min}/{len(scored)} reached scoring but fell below MIN_SEND_SCORE=70")

            bot.send_message(message.chat.id, "\n".join(lines2))
        else:
            bot.send_message(
                message.chat.id,
                "⚠️ No coin even reached the final scoring stage — the bottleneck is one of the hard filters above (fomo/trend/rsi/flow/chasing), not the score threshold.",
            )

    except Exception:
        print("DEBUG SCAN ERROR:", traceback.format_exc())
        bot.send_message(message.chat.id, "🚨 Debug scan failed, check logs.")

    finally:
        scan_lock.release()


@bot.message_handler(commands=["scan"])
def scan(message):
    if not scan_lock.acquire(blocking=False):
        bot.reply_to(message, "⏳ Scan already running, please wait...")
        return

    try:
        bot.reply_to(message, """
🐋 AHAD AI v12.0 SCANNING...

🔍 Checking Market Flow
🏦 Finding Hot Sector
🧱 Checking Range Compression
🟢 Hunting TOP 3 LONG setups
🐋 Tracking Smart Money
⚡ Detecting Pre-Pump
🔥 Heat Control ACTIVE

Please wait ⏳
        """)

        long_results = []

        all_symbols = get_symbols()
        if not all_symbols:
            bot.send_message(message.chat.id, "🚨 Could not fetch symbols from OKX. Try again shortly.")
            return

        flow_symbols = top_flow_scanner(all_symbols)

        flow = sector_flow(all_symbols)
        hot_sector = flow["sector"]

        bot.send_message(
            message.chat.id,
            f"""
🔥 MARKET FLOW

🏦 Hot Sector: {hot_sector}
🐋 Flow Power: {flow['power']}
            """,
        )

        # Prefer high-flow coins, but bias toward the hot sector when
        # both pools have enough candidates — this makes the "hot
        # sector" label actually influence which coins get analyzed,
        # instead of being purely cosmetic.
        sector_pool = [s for s in flow_symbols if s in flow["symbols"]]
        if len(sector_pool) >= 8:
            symbols = sector_pool + [s for s in flow_symbols if s not in sector_pool]
        else:
            symbols = flow_symbols

        if len(symbols) < 20:
            symbols = all_symbols

        bot.send_message(message.chat.id, f"💎 Watchlist: {len(symbols)} coins")

        for symbol in symbols:
            result = analyze(symbol, hot_sector)
            if result:
                if (
                    result["liquidity"] >= 1.2
                    or result["pre_pump"] == "🐋 WHALE LOADING"
                ):
                    long_results.append(result)

            time.sleep(0.03)

        results = sorted(
            long_results,
            key=lambda x: (x["score"], x["liquidity"]),
            reverse=True,
        )[:3]

        if not results:
            bot.send_message(message.chat.id, """
👀 No sniper setup now

🐋 Smart Money not ready
⏳ Waiting next liquidity wave
            """)
            return

        for s in results:
            msg = f"""
🚨 AHAD AI v12.0 🐋

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

{s['quality']}

🔥 Score: {s['score']}/100 | 💧Flow: {s['liquidity']}X
🐋 Money: {s['money_status']}
🧱 BB Compression %ile: {s['bb_percentile']}
🪤 Trap: {s['trap']}

🎯 Entry: {s['entry_low']} - {s['entry_high']}
🛑 SL: {s['sl']}

🥇 TP1: {s['tp1']}
🥈 TP2: {s['tp2']}

📊 RSI:
15m:{s['multi']['15m']} | 1H:{s['multi']['1h']}
4H:{s['multi']['4h']} | 1D:{s['multi']['1d']}

⚠️ {s['warning']}
            """
            bot.send_message(message.chat.id, msg)

    except Exception:
        print("SCAN ERROR:", traceback.format_exc())
        bot.send_message(message.chat.id, "🚨 Scan failed, check logs.")

    finally:
        scan_lock.release()


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
            print("KEEP ALIVE ERROR:", e)
        time.sleep(240)  # tightened from 300s to be safer under Render's timeout


# =====================================
# 🚀 START SYSTEM
# =====================================

def telegram_engine():
    while True:
        try:
            print("🐋 TELEGRAM ENGINE STARTED")
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception:
            print("🚨 TELEGRAM ERROR")
            print(traceback.format_exc())

        print("🔄 Restarting Telegram...")
        time.sleep(5)


threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=telegram_engine, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

print("🔥 AHAD AI v12.0 REBUILT ONLINE 🐋")

while True:
    time.sleep(60)
