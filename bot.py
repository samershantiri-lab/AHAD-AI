# =====================================
# 🚀 AHAD AI v9.0 - OKX EDITION
# مبني بالكامل على منظومة المؤشرات المتفق عليها:
# EMA9/21/50/200 + RSI + MACD + Bollinger+Volume + OBV
# + Market Structure (HH/HL) + VWAP + ADX Gate + Distance Gate
# + Funding Rate + Open Interest + Conflict Logic + Cooldown
# فريمات: 4H(40%) / 1H(30%) / 15m(20%) + 5m طبقة تنفيذ
# =====================================

import requests
import time
import traceback
import threading
import numpy as np
import pandas as pd

from flask import Flask
import telebot

from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator


# =====================================
# 🔑 الإعدادات
# =====================================

TOKEN = "8697535359:AAGlWi6GbtR1XQLlzhC_hoApLcfYiCxQWwg"
bot = telebot.TeleBot(TOKEN)

OKX_BASE = "https://www.okx.com"

# أوزان الفريمات بالسكور (5m طبقة تنفيذ فقط، بدون وزن)
TF_WEIGHTS = {"4H": 0.40, "1H": 0.30, "15m": 0.20}
TF_BAR_MAP = {"15m": "15m", "1H": "1H", "4H": "4H", "5m": "5m"}

# حدود الإشارة
STRONG_LONG = 45
LONG_MIN = 15
STRONG_SHORT = -45
SHORT_MAX = -15

# فلاتر البوابة
MIN_ADX = 20
MAX_ATR_MULTIPLE = 3.0
MIN_24H_VOLUME_USD = 3_000_000

# منطق التعارض بين 4H و1H
CONFLICT_THRESHOLD = 60

# الكولداون (ما تتكرر نفس الإشارة لنفس العملة قبل ما تمر هالمدة)
ALERT_COOLDOWN_HOURS = 4

# ذاكرة داخلية بالبوت (تُحفظ طول ما البوت شغال)
PREV_OI = {}          # آخر قيمة Open Interest لكل عملة
LAST_ALERT = {}       # آخر تنبيه أُرسل لكل عملة {symbol: (timestamp, direction)}
SUBSCRIBERS = set()   # chat_id لكل مستخدم بعت /start


# =====================================
# 🌐 RENDER KEEP ALIVE
# =====================================

app = Flask(__name__)


@app.route("/")
def home():
    return "🐋 AHAD AI v9.0 (OKX) ONLINE"


def run_web():
    app.run(host="0.0.0.0", port=10000)


# =====================================
# ⬛ OKX DATA ENGINE
# =====================================

def okx_get(path, params=None, timeout=10):
    """نداء عام لـ OKX مع معالجة الأخطاء"""
    url = OKX_BASE + path
    res = requests.get(url, params=params, timeout=timeout)
    data = res.json()
    if data.get("code") not in (None, "0"):
        raise Exception(f"OKX error: {data.get('msg')}")
    return data.get("data", [])


def get_symbols(limit=25):
    """أهم العملات حسب حجم التداول، مع فلتر السيولة الدنيا"""
    try:
        data = okx_get("/api/v5/market/tickers", {"instType": "SWAP"})
        usdt_pairs = [t for t in data if t["instId"].endswith("-USDT-SWAP")]

        # فلتر بوابة: سيولة 24 ساعة ضعيفة تُستبعد
        usdt_pairs = [
            t for t in usdt_pairs
            if float(t.get("volCcy24h", 0)) >= MIN_24H_VOLUME_USD
        ]

        usdt_pairs.sort(key=lambda t: float(t["volCcy24h"]), reverse=True)
        symbols = [t["instId"] for t in usdt_pairs[:limit]]

        print("⬛ OKX MARKETS (بعد فلتر السيولة):", len(symbols))
        return symbols

    except Exception as e:
        print("❌ OKX SYMBOLS ERROR:", e)
        return []


def get_candles(inst_id, tf, limit=200):
    """جلب الشموع وتحويلها لـ DataFrame مرتب من القديم للجديد"""
    try:
        bar = TF_BAR_MAP[tf]
        data = okx_get("/api/v5/market/candles", {
            "instId": inst_id, "bar": bar, "limit": limit
        })

        if not data or len(data) < 30:
            return None

        df = pd.DataFrame(data)
        df = df.iloc[:, 0:6]
        df.columns = ["time", "open", "high", "low", "close", "volume"]

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])

        df = df[::-1].reset_index(drop=True)  # OKX يرجع الأحدث أول، نعكسها
        return df

    except Exception as e:
        print("❌ CANDLE ERROR:", inst_id, tf, e)
        return None


def get_funding_rate(inst_id):
    try:
        data = okx_get("/api/v5/public/funding-rate", {"instId": inst_id})
        return float(data[0]["fundingRate"]) * 100
    except Exception:
        return None


def get_open_interest(inst_id):
    try:
        data = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
        return float(data[0]["oi"])
    except Exception:
        return None


# =====================================
# 🧠 محرك التحليل الفني (لكل فريم)
# =====================================

def find_market_structure(df, lookback=2, window=40):
    """يفحص آخر Higher-High/Higher-Low أو Lower-High/Lower-Low"""
    d = df.tail(window).reset_index(drop=True)
    highs, lows = d["high"].values, d["low"].values
    n = len(highs)

    swing_highs, swing_lows = [], []

    for i in range(lookback, n - lookback):
        is_high = all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, lookback + 1))
        is_low = all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, lookback + 1))
        if is_high:
            swing_highs.append(highs[i])
        if is_low:
            swing_lows.append(lows[i])

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return 0, "غير كافٍ"

    h1, h2 = swing_highs[-2], swing_highs[-1]
    l1, l2 = swing_lows[-2], swing_lows[-1]

    if h2 > h1 and l2 > l1:
        return 1, "HH/HL صاعد"
    if h2 < h1 and l2 < l1:
        return -1, "LH/LL هابط"
    return 0, "غير واضح"


def score_timeframe(df):
    """يحسب سكور فريم واحد بكل المؤشرات المتفق عليها، ويرجع تفاصيل الفلاتر"""

    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    price = close.iloc[-1]

    ema9 = EMAIndicator(close, window=9).ema_indicator()
    ema21 = EMAIndicator(close, window=21).ema_indicator()
    ema50 = EMAIndicator(close, window=50).ema_indicator()
    ema200_window = 200 if len(close) > 200 else max(20, int(len(close) * 0.8))
    ema200 = EMAIndicator(close, window=ema200_window).ema_indicator()

    rsi_series = RSIIndicator(close, window=14).rsi()
    macd_ind = MACD(close)
    macd_line, signal_line, hist = macd_ind.macd(), macd_ind.macd_signal(), macd_ind.macd_diff()

    bb = BollingerBands(close, window=20, window_dev=2)
    bb_upper, bb_lower = bb.bollinger_hband(), bb.bollinger_lband()

    atr_series = AverageTrueRange(high, low, close, window=14).average_true_range()
    obv_series = OnBalanceVolumeIndicator(close, vol).on_balance_volume()
    adx_series = ADXIndicator(high, low, close, window=14).adx()

    structure_bias, structure_label = find_market_structure(df)

    n = len(close) - 1
    score = 0
    notes = []

    # EMA50/200 (20)
    if ema50.iloc[n] > ema200.iloc[n]:
        score += 20; notes.append("EMA50>200")
    else:
        score -= 20; notes.append("EMA50<200")

    # EMA9/21 (15)
    cross_up = ema9.iloc[n] > ema21.iloc[n] and ema9.iloc[n-1] <= ema21.iloc[n-1]
    cross_down = ema9.iloc[n] < ema21.iloc[n] and ema9.iloc[n-1] >= ema21.iloc[n-1]
    if cross_up:
        score += 15; notes.append("تقاطع EMA9/21↑")
    elif ema9.iloc[n] > ema21.iloc[n]:
        score += 8
    elif cross_down:
        score -= 15; notes.append("تقاطع EMA9/21↓")
    else:
        score -= 8

    # RSI (15)
    r, r_prev = rsi_series.iloc[n], rsi_series.iloc[n-1]
    if r < 35 and r > r_prev:
        score += 15; notes.append("ارتداد RSI")
    elif r > 70:
        score -= 10; notes.append("RSI تشبع شرائي")
    elif r > 50:
        score += 6
    else:
        score -= 6

    # MACD (15)
    macd_cross_up = macd_line.iloc[n] > signal_line.iloc[n] and macd_line.iloc[n-1] <= signal_line.iloc[n-1]
    macd_cross_down = macd_line.iloc[n] < signal_line.iloc[n] and macd_line.iloc[n-1] >= signal_line.iloc[n-1]
    if macd_cross_up and macd_line.iloc[n] > 0:
        score += 15; notes.append("MACD↑ فوق الصفر")
    elif macd_cross_up:
        score += 9; notes.append("MACD↑")
    elif hist.iloc[n] > hist.iloc[n-1] and hist.iloc[n] > 0:
        score += 5
    elif macd_cross_down:
        score -= 15; notes.append("MACD↓")
    elif hist.iloc[n] < hist.iloc[n-1] and hist.iloc[n] < 0:
        score -= 5

    # Bollinger + Volume (10)
    avg_vol = vol.tail(20).mean()
    last_vol = vol.iloc[n]
    if price <= bb_lower.iloc[n] * 1.01 and last_vol > avg_vol:
        score += 10; notes.append("ارتداد Bollinger↓+حجم")
    elif price >= bb_upper.iloc[n] * 0.99:
        score -= 8; notes.append("رفض Bollinger↑")

    # OBV (5)
    obv_tail = obv_series.tail(10)
    if obv_tail.iloc[-1] > obv_tail.iloc[0]:
        score += 5
    else:
        score -= 5

    # Market Structure (15)
    score += structure_bias * 15
    if structure_bias != 0:
        notes.append(structure_label)

    # VWAP تقريبي (نافذة الفريم الحالي) (10)
    typical = (high + low + close) / 3
    vwap_val = (typical * vol).cumsum().iloc[n] / vol.cumsum().iloc[n]
    if price > vwap_val:
        score += 10
    else:
        score -= 10

    # فلاتر البوابة
    adx_val = adx_series.iloc[n]
    dist_from_ema21 = abs(price - ema21.iloc[n])
    atr_val = atr_series.iloc[n]

    adx_gate_fail = adx_val < MIN_ADX
    dist_gate_fail = dist_from_ema21 > atr_val * MAX_ATR_MULTIPLE

    return {
        "score": max(-100, min(100, score)),
        "price": price,
        "rsi": r,
        "adx": adx_val,
        "atr": atr_val,
        "notes": notes,
        "adx_gate_fail": adx_gate_fail,
        "dist_gate_fail": dist_gate_fail,
        "structure_label": structure_label,
    }


def score_exec_5m(df):
    """طبقة تنفيذ 5 دقائق - بدون وزن بالسكور، بس تنبيه توقيت"""
    close = df["close"]
    ema9 = EMAIndicator(close, window=9).ema_indicator()
    ema21 = EMAIndicator(close, window=21).ema_indicator()
    n = len(close) - 1

    cross_up = ema9.iloc[n] > ema21.iloc[n] and ema9.iloc[n-1] <= ema21.iloc[n-1]
    cross_down = ema9.iloc[n] < ema21.iloc[n] and ema9.iloc[n-1] >= ema21.iloc[n-1]

    if cross_up:
        return "تقاطع دخول لونج 5د 🟢"
    if cross_down:
        return "تقاطع دخول شورت 5د 🔴"
    if ema9.iloc[n] > ema21.iloc[n]:
        return "زخم لونج 5د"
    if ema9.iloc[n] < ema21.iloc[n]:
        return "زخم شورت 5د"
    return "محايد 5د"


# =====================================
# 🔬 التحليل الكامل لعملة واحدة
# =====================================

def analyze_symbol(inst_id):
    try:
        tf_results = {}
        for tf in ["15m", "1H", "4H"]:
            df = get_candles(inst_id, tf, 200)
            if df is None:
                return None
            tf_results[tf] = score_timeframe(df)

        df_5m = get_candles(inst_id, "5m", 60)
        exec_note = score_exec_5m(df_5m) if df_5m is not None else "غير متاح"

        funding = get_funding_rate(inst_id)
        oi_now = get_open_interest(inst_id)

        weighted = sum(tf_results[tf]["score"] * TF_WEIGHTS[tf] for tf in TF_WEIGHTS)

        modifier = 0
        extra_notes = []

        # Funding Rate modifier
        if funding is not None:
            if funding < -0.05:
                modifier += 8; extra_notes.append("Funding سالب متطرف 🔥")
            elif funding > 0.08:
                modifier -= 8; extra_notes.append("Funding موجب مرتفع ⚠️")

        # Open Interest modifier (يقارن بآخر فحص محفوظ بالذاكرة)
        oi_prev = PREV_OI.get(inst_id)
        if oi_now is not None and oi_prev is not None:
            price_up = tf_results["15m"]["price"] >= tf_results["15m"].get("_prev_price", tf_results["15m"]["price"])
            if oi_now > oi_prev:
                modifier += 5; extra_notes.append("OI صاعد (زخم حقيقي)")
            elif oi_now < oi_prev:
                modifier -= 5; extra_notes.append("OI هابط (زخم ضعيف)")
        if oi_now is not None:
            PREV_OI[inst_id] = oi_now

        final_score = max(-100, min(100, weighted + modifier))

        # منطق التعارض 4H/1H
        conflict = abs(tf_results["4H"]["score"] - tf_results["1H"]["score"]) > CONFLICT_THRESHOLD
        if conflict:
            final_score *= 0.15
            extra_notes.append("تعارض حاد 4س/1س → محايد")

        # فلاتر البوابة
        gate_fail = (
            tf_results["1H"]["adx_gate_fail"]
            or tf_results["4H"]["adx_gate_fail"]
            or tf_results["1H"]["dist_gate_fail"]
        )
        gate_reasons = []
        if tf_results["1H"]["adx_gate_fail"] or tf_results["4H"]["adx_gate_fail"]:
            gate_reasons.append("ADX<20 (سوق عرضي)")
        if tf_results["1H"]["dist_gate_fail"]:
            gate_reasons.append("بعيد عن EMA21 (>3×ATR)")

        return {
            "symbol": inst_id,
            "tf_results": tf_results,
            "exec_note": exec_note,
            "funding": funding,
            "oi": oi_now,
            "final_score": final_score,
            "extra_notes": extra_notes,
            "gate_fail": gate_fail,
            "gate_reasons": gate_reasons,
            "price": tf_results["15m"]["price"],
        }

    except Exception as e:
        print("❌ ANALYZE ERROR:", inst_id, e)
        return None


def signal_label(score, gate_fail):
    if gate_fail:
        return "🚫 محجوبة"
    if score >= STRONG_LONG:
        return "🟢 لونج قوي"
    if score >= LONG_MIN:
        return "🟢 لونج"
    if score <= STRONG_SHORT:
        return "🔴 شورت قوي"
    if score <= SHORT_MAX:
        return "🔴 شورت"
    return "⚪ محايد"


# =====================================
# 🕒 منطق الكولداون
# =====================================

def should_alert(symbol, direction):
    """يمنع تكرار نفس الإشارة لنفس العملة قبل انتهاء مدة الكولداون"""
    prev = LAST_ALERT.get(symbol)
    now = time.time()

    if prev is None:
        return True

    prev_time, prev_direction = prev
    hours_passed = (now - prev_time) / 3600

    if direction != prev_direction:
        return True
    if hours_passed >= ALERT_COOLDOWN_HOURS:
        return True
    return False


def register_alert(symbol, direction):
    LAST_ALERT[symbol] = (time.time(), direction)


# =====================================
# 📨 تنسيق رسالة تليجرام
# =====================================

def format_signal_message(r):
    sig = signal_label(r["final_score"], r["gate_fail"])
    tf4, tf1, tf15 = r["tf_results"]["4H"], r["tf_results"]["1H"], r["tf_results"]["15m"]

    notes_combined = (tf4["notes"][:2] + r["extra_notes"])[:4]
    notes_text = "\n".join(f"• {n}" for n in notes_combined) if notes_combined else "• —"

    funding_text = f"{r['funding']:.4f}%" if r["funding"] is not None else "—"
    gate_text = f"\n🚫 السبب: {' + '.join(r['gate_reasons'])}" if r["gate_fail"] else ""

    return f"""
{sig}

🪙 العملة: {r['symbol']}
💰 السعر: {r['price']:.6f}
🔥 السكور النهائي: {r['final_score']:.0f}/100

📊 الفريمات:
4س: {tf4['score']:.0f} | 1س: {tf1['score']:.0f} | 15د: {tf15['score']:.0f}

⏱ تنفيذ 5د: {r['exec_note']}

💸 Funding: {funding_text}

📝 الأسباب:
{notes_text}{gate_text}
"""


# =====================================
# 🤖 أوامر تليجرام
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.reply_to(message, """
🚀 AHAD AI v9.0 (OKX Edition) ONLINE 🐋

⬛ مصدر البيانات: OKX Public API

⏱ الفريمات:
🎯 15m دخول — وزن 20%
📈 1H زخم — وزن 30%
🐋 4H اتجاه — وزن 40%
⚡ 5m تنفيذ (بدون وزن)

🧠 EMA + RSI + MACD + Bollinger + OBV
🏗 Market Structure + VWAP
🛡 فلاتر: ADX + المسافة + السيولة

سجّلت اشتراكك — رح توصلك تنبيهات تلقائية.
Send /scan للفحص الفوري
""")


@bot.message_handler(commands=["scan"])
def scan(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.reply_to(message, "⬛ جارِ الفحص عبر OKX...\n15m + 1H + 4H + Funding + OI\nانتظر شوي 🐋")

    symbols = get_symbols(25)
    if not symbols:
        bot.send_message(message.chat.id, "❌ تعذّر جلب قائمة العملات من OKX. جرّب لاحقاً.")
        return

    results = []
    for symbol in symbols:
        r = analyze_symbol(symbol)
        if r:
            results.append(r)
        time.sleep(0.1)

    results.sort(key=lambda x: x["final_score"], reverse=True)

    valid_signals = [r for r in results if not r["gate_fail"]]
    strong = [r for r in valid_signals if abs(r["final_score"]) >= LONG_MIN]

    if strong:
        for r in strong[:5]:
            bot.send_message(message.chat.id, format_signal_message(r))
    else:
        text = "👀 لا يوجد إشارة لونج/شورت واضحة حالياً\n\nأقرب الفرص:\n"
        for r in results[:5]:
            text += f"\n🪙 {r['symbol']} — سكور: {r['final_score']:.0f}"
            if r["gate_fail"]:
                text += f" (محجوبة: {', '.join(r['gate_reasons'])})"
        bot.send_message(message.chat.id, text)


# =====================================
# 🔁 الفحص التلقائي (تنبيهات بدون طلب المستخدم)
# =====================================

AUTO_SCAN_INTERVAL_SECONDS = 900  # كل 15 دقيقة


def auto_scan_loop():
    while True:
        try:
            time.sleep(AUTO_SCAN_INTERVAL_SECONDS)

            if not SUBSCRIBERS:
                continue

            symbols = get_symbols(25)
            for symbol in symbols:
                r = analyze_symbol(symbol)
                if not r or r["gate_fail"]:
                    continue

                score = r["final_score"]
                if abs(score) < STRONG_LONG:  # نبعت تلقائياً بس على الإشارات القوية
                    continue

                direction = "long" if score > 0 else "short"
                if not should_alert(symbol, direction):
                    continue

                register_alert(symbol, direction)
                msg = "🚨 تنبيه تلقائي جديد 🚨\n" + format_signal_message(r)
                for chat_id in list(SUBSCRIBERS):
                    try:
                        bot.send_message(chat_id, msg)
                    except Exception as e:
                        print("❌ SEND ERROR:", chat_id, e)

                time.sleep(0.2)

        except Exception:
            print(traceback.format_exc())
            time.sleep(10)


# =====================================
# 🛡 التشغيل والاستمرارية
# =====================================

def telegram_engine():
    while True:
        try:
            print("🤖 Telegram ACTIVE")
            bot.infinity_polling(skip_pending=True, timeout=60)
        except Exception:
            print(traceback.format_exc())
            print("🔄 إعادة تشغيل...")
            time.sleep(5)


threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=telegram_engine, daemon=True).start()
threading.Thread(target=auto_scan_loop, daemon=True).start()

print("🔥 AHAD AI v9.0 (OKX Edition) FULL ONLINE 🐋")

while True:
    time.sleep(60)
