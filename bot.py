# ================================================
# 🚀 AHAD AI v21.1.7 – Production Analytics
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
import psycopg2
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
# 🗄 POSTGRESQL DATABASE
# ================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ DATABASE_URL NOT FOUND")


def get_db_connection():
    """Create a PostgreSQL connection with proper settings"""
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode='require'
    )


def init_database():
    """Initialize PostgreSQL database with tables and indexes"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Create main table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (

            id SERIAL PRIMARY KEY,

            symbol TEXT,
            side TEXT,

            signal_time TIMESTAMP,

            entry DOUBLE PRECISION,
            sl DOUBLE PRECISION,

            tp1 DOUBLE PRECISION,
            tp2 DOUBLE PRECISION,
            tp3 DOUBLE PRECISION,

            sector TEXT,

            score INTEGER,

            brain_long INTEGER,
            brain_short INTEGER,

            flow DOUBLE PRECISION,
            momentum INTEGER,
            rr DOUBLE PRECISION,

            confidence TEXT,

            late_score INTEGER,

            version TEXT,

            status TEXT,

            result TEXT,

            max_profit DOUBLE PRECISION,
            max_drawdown DOUBLE PRECISION,

            close_time TIMESTAMP,

            -- NEW FIELDS v21.1.7
            brain_confidence INTEGER,
            market_regime TEXT,
            compression_score INTEGER,
            compression_status TEXT,
            momentum_weight DOUBLE PRECISION,
            flow_score INTEGER,
            volume_acceleration DOUBLE PRECISION,
            flow_rating TEXT,
            risk_grade TEXT,
            decision_summary TEXT,
            result_pct DOUBLE PRECISION,
            trade_duration INTEGER,
            max_profit_pct DOUBLE PRECISION

        )
        """)

        # Add new columns if they don't exist (v21.1.0+)
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS brain_confidence INTEGER
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS market_regime TEXT
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS compression_score INTEGER
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS compression_status TEXT
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS momentum_weight DOUBLE PRECISION
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS flow_score INTEGER
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS volume_acceleration DOUBLE PRECISION
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS flow_rating TEXT
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS risk_grade TEXT
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS decision_summary TEXT
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS result_pct DOUBLE PRECISION
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS trade_duration INTEGER
        """)
        
        cur.execute("""
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS max_profit_pct DOUBLE PRECISION
        """)

        # Indexes for performance
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(result)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_signal_time ON trades(signal_time)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_status_symbol ON trades(status, symbol)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_market_regime ON trades(market_regime)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_brain_confidence ON trades(brain_confidence)
        """)

        conn.commit()
        print("🟢 PostgreSQL Connected")
        print("🗄 AHAD AI DATABASE READY (v21.1.7)")
        print("📊 Indexes: status, result, signal_time, symbol, status_symbol, market_regime, brain_confidence")
        print("📊 New columns: brain_confidence, market_regime, compression_score, compression_status, momentum_weight, flow_score, volume_acceleration, flow_rating, risk_grade, decision_summary, result_pct, trade_duration, max_profit_pct")

    except Exception as e:
        print(f"❌ Database Error: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 💾 TRADE RECORDER (v21.1.7)
# ================================================

def save_trade(trade_data):
    """Save trade to PostgreSQL database with duplicate check"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ====== CHECK FOR DUPLICATE ======
        cur.execute("""
        SELECT id FROM trades
        WHERE symbol = %s
        AND side = %s
        AND status = 'OPEN'
        """, (trade_data['symbol'], trade_data['side']))
        
        existing = cur.fetchone()
        
        if existing:
            print(f"⚠️ Duplicate trade skipped: {trade_data['symbol']} ({trade_data['side']})")
            return existing[0]
        # =================================

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
            close_time,
            brain_confidence,
            market_regime,
            compression_score,
            compression_status,
            momentum_weight,
            flow_score,
            volume_acceleration,
            flow_rating,
            risk_grade,
            decision_summary,
            result_pct,
            trade_duration,
            max_profit_pct
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s,
            %s, %s,
            %s, %s,
            %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        )
        RETURNING id
        """, (
            trade_data['symbol'],
            trade_data['side'],
            datetime.now(),
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
            trade_data.get('version', 'v21.1.7'),
            'OPEN',
            'PENDING',
            0.0,
            0.0,
            None,
            trade_data.get('brain_confidence', 0),
            trade_data.get('market_regime', 'UNKNOWN'),
            trade_data.get('compression_score', 0),
            trade_data.get('compression_status', 'UNKNOWN'),
            trade_data.get('momentum_weight', 1.0),
            trade_data.get('flow_score', 0),
            trade_data.get('volume_acceleration', 0.0),
            trade_data.get('flow_rating', 'N/A'),
            trade_data.get('risk_grade', 'N/A'),
            trade_data.get('decision_summary', ''),
            0.0,
            0,
            0.0
        ))

        trade_id = cur.fetchone()[0]

        conn.commit()

        print(f"💾 Trade saved: {trade_data['symbol']} (ID: {trade_id})")
        return trade_id

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error saving trade: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📈 TRADE TRACKING SYSTEM
# ================================================

def get_open_trades():
    """Get all open trades from PostgreSQL"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT id, symbol, side, entry, sl, tp1, tp2, tp3,
               max_profit, max_drawdown, signal_time
        FROM trades
        WHERE status = 'OPEN'
        """)

        rows = cur.fetchall()

        trades = []

        for row in rows:
            trades.append({
                'id': row[0],
                'symbol': row[1],
                'side': row[2],
                'entry': row[3],
                'sl': row[4],
                'tp1': row[5],
                'tp2': row[6],
                'tp3': row[7],
                'max_profit': row[8] if row[8] is not None else 0.0,
                'max_drawdown': row[9] if row[9] is not None else 0.0,
                'signal_time': row[10]
            })

        print(f"📂 OPEN trades loaded: {len(trades)}")
        return trades

    except Exception as e:
        print(f"❌ Error getting open trades: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def update_trade(trade_id, status, result, max_profit, max_drawdown, close_time=None, result_pct=None, trade_duration=None, max_profit_pct=None):
    """Update trade data in PostgreSQL"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
        UPDATE trades
        SET status = %s,
            result = %s,
            max_profit = %s,
            max_drawdown = %s,
            close_time = %s,
            result_pct = %s,
            trade_duration = %s,
            max_profit_pct = %s
        WHERE id = %s
        """, (
            status,
            result,
            max_profit,
            max_drawdown,
            close_time,
            result_pct,
            trade_duration,
            max_profit_pct,
            trade_id
        ))

        conn.commit()

        print(f"✅ Trade {trade_id} updated: {status} | {result}")
        return True

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error updating trade {trade_id}: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📦 TRADE TRACKER CACHE
# ================================================

_trade_tracker_cache = {}

def get_trade_tracker_candles(symbol, tf="15m", ttl=60):
    """
    Cache candles for Trade Tracker.
    Reuses candle data for 60 seconds to reduce API requests.
    """
    now = time.time()
    key = f"{symbol}_{tf}"

    if key in _trade_tracker_cache:
        cached = _trade_tracker_cache[key]

        if now - cached["time"] <= ttl:
            return cached["candles"]

    candles = get_candles(symbol, tf)

    _trade_tracker_cache[key] = {
        "time": now,
        "candles": candles
    }

    return candles


# ================================================
# 🧹 CACHE CLEANUP (v21.1.7)
# ================================================

def cache_cleanup(ttl=600):
    """Clean up old cache entries to prevent memory growth"""
    now = time.time()
    
    # Clean _candle_cache
    keys_to_remove = []
    for key, value in _candle_cache.items():
        # _candle_cache stores tuples (candles, timestamp)
        if isinstance(value, tuple) and len(value) == 2:
            if now - value[1] > ttl:
                keys_to_remove.append(key)
        elif isinstance(value, list):
            # Old format without timestamp, keep it
            continue
    
    for key in keys_to_remove:
        del _candle_cache[key]
    
    if keys_to_remove:
        print(f"🧹 Cache cleanup: removed {len(keys_to_remove)} old entries")


def update_open_trades():
    """Monitor open trades every 5 minutes using HIGH/LOW for accuracy"""
    print("📈 Trade Tracker STARTED")

    while True:
        try:
            open_trades = get_open_trades()

            if not open_trades:
                time.sleep(300)
                continue

            print(f"📊 Checking {len(open_trades)} open trades...")

            for trade in open_trades:
                try:
                    # ==========================================
                    # CURRENT CANDLE PRICES (CACHED)
                    # ==========================================
                    candles = get_trade_tracker_candles(trade['symbol'], "15m")
                    if not candles:
                        continue

                    current_price = candles[-1]['close']
                    current_high = candles[-1]['high']
                    current_low = candles[-1]['low']
                    # ==========================================

                    # Calculate current profit/loss using CLOSE
                    if trade['side'] == 'LONG':
                        profit_percent = ((current_price - trade['entry']) / trade['entry']) * 100
                    else:  # SHORT
                        profit_percent = ((trade['entry'] - current_price) / trade['entry']) * 100

                    # ==========================================
                    # PROFESSIONAL PROFIT / DRAWDOWN TRACKER
                    # ==========================================

                    if trade['side'] == "LONG":

                        # Highest profit reached
                        if profit_percent > trade["max_profit"]:
                            trade["max_profit"] = profit_percent

                        # Lowest excursion reached
                        if profit_percent < trade["max_drawdown"]:
                            trade["max_drawdown"] = profit_percent

                    else:   # SHORT

                        # Highest profit while short
                        if profit_percent > trade["max_profit"]:
                            trade["max_profit"] = profit_percent

                        # Worst adverse movement
                        if profit_percent < trade["max_drawdown"]:
                            trade["max_drawdown"] = profit_percent

                    # ==========================================
                    # HIGH / LOW ACCURACY TP/SL CHECK
                    # ==========================================

                    new_status = None
                    result = None
                    close_time = datetime.now()

                    if trade['side'] == "LONG":

                        if current_high >= trade['tp3']:
                            new_status = "CLOSED"
                            result = "WIN_TP3"

                        elif current_high >= trade['tp2']:
                            new_status = "CLOSED"
                            result = "WIN_TP2"

                        elif current_high >= trade['tp1']:
                            new_status = "CLOSED"
                            result = "WIN_TP1"

                        elif current_low <= trade['sl']:
                            new_status = "CLOSED"
                            result = "LOSS_SL"

                    else:  # SHORT

                        if current_low <= trade['tp3']:
                            new_status = "CLOSED"
                            result = "WIN_TP3"

                        elif current_low <= trade['tp2']:
                            new_status = "CLOSED"
                            result = "WIN_TP2"

                        elif current_low <= trade['tp1']:
                            new_status = "CLOSED"
                            result = "WIN_TP1"

                        elif current_high >= trade['sl']:
                            new_status = "CLOSED"
                            result = "LOSS_SL"

                    # Update database if closed
                    if new_status:
                        # Calculate result_pct and trade_duration
                        result_pct = round(profit_percent, 2)
                        trade_duration = int((close_time - trade['signal_time']).total_seconds())
                        max_profit_pct = round(trade['max_profit'], 2)

                        update_trade(
                            trade['id'],
                            new_status,
                            result,
                            round(trade['max_profit'], 2),
                            round(trade['max_drawdown'], 2),
                            close_time,
                            result_pct,
                            trade_duration,
                            max_profit_pct
                        )
                        print(f"🔒 Trade {trade['id']} {trade['symbol']} closed: {result} | Profit: {result_pct}% | Duration: {trade_duration}s")
                    else:
                        # Update max_profit and max_drawdown only
                        update_trade(
                            trade['id'],
                            'OPEN',
                            'PENDING',
                            round(trade['max_profit'], 2),
                            round(trade['max_drawdown'], 2),
                            None,
                            None,
                            None,
                            None
                        )

                except Exception as e:
                    print(f"❌ Error processing trade {trade.get('id', 'unknown')}: {e}")
                    continue

            time.sleep(300)  # 5 minutes

        except Exception as e:
            print(f"❌ Trade Tracker error: {e}")
            time.sleep(60)
            # ================================================
# 📊 PERFORMANCE ANALYTICS
# ================================================

def get_report_stats():
    """Get AHAD AI performance statistics including LONG/SHORT breakdown"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Main statistics
        cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'OPEN' THEN 1 END) AS open_trades,
            COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) AS closed,
            COUNT(CASE WHEN result = 'WIN_TP1' THEN 1 END) AS tp1,
            COUNT(CASE WHEN result = 'WIN_TP2' THEN 1 END) AS tp2,
            COUNT(CASE WHEN result = 'WIN_TP3' THEN 1 END) AS tp3,
            COUNT(CASE WHEN result = 'LOSS_SL' THEN 1 END) AS sl,
            AVG(rr) AS avg_rr,
            AVG(result_pct) AS avg_result_pct,
            AVG(trade_duration) AS avg_duration
        FROM trades
        """)

        row = cur.fetchone()

        total = row[0] or 0
        open_trades = row[1] or 0
        closed = row[2] or 0
        tp1 = row[3] or 0
        tp2 = row[4] or 0
        tp3 = row[5] or 0
        sl = row[6] or 0
        avg_rr = round(row[7] or 0, 2)
        avg_result_pct = round(row[8] or 0, 2)
        avg_duration = round(row[9] or 0, 0)

        wins = tp1 + tp2 + tp3

        if closed > 0:
            win_rate = round((wins / closed) * 100, 2)
        else:
            win_rate = 0

        # LONG statistics
        cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'CLOSED' AND result IN ('WIN_TP1', 'WIN_TP2', 'WIN_TP3') THEN 1 END) AS wins,
            COUNT(CASE WHEN status = 'CLOSED' AND result = 'LOSS_SL' THEN 1 END) AS losses,
            AVG(rr) AS avg_rr,
            AVG(result_pct) AS avg_result_pct,
            AVG(trade_duration) AS avg_duration
        FROM trades
        WHERE side = 'LONG'
        """)

        long_row = cur.fetchone()
        long_total = long_row[0] or 0
        long_wins = long_row[1] or 0
        long_losses = long_row[2] or 0
        long_avg_rr = round(long_row[3] or 0, 2)
        long_avg_result_pct = round(long_row[4] or 0, 2)
        long_avg_duration = round(long_row[5] or 0, 0)
        long_closed = long_wins + long_losses
        long_win_rate = round((long_wins / long_closed) * 100, 2) if long_closed > 0 else 0

        # SHORT statistics
        cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'CLOSED' AND result IN ('WIN_TP1', 'WIN_TP2', 'WIN_TP3') THEN 1 END) AS wins,
            COUNT(CASE WHEN status = 'CLOSED' AND result = 'LOSS_SL' THEN 1 END) AS losses,
            AVG(rr) AS avg_rr,
            AVG(result_pct) AS avg_result_pct,
            AVG(trade_duration) AS avg_duration
        FROM trades
        WHERE side = 'SHORT'
        """)

        short_row = cur.fetchone()
        short_total = short_row[0] or 0
        short_wins = short_row[1] or 0
        short_losses = short_row[2] or 0
        short_avg_rr = round(short_row[3] or 0, 2)
        short_avg_result_pct = round(short_row[4] or 0, 2)
        short_avg_duration = round(short_row[5] or 0, 0)
        short_closed = short_wins + short_losses
        short_win_rate = round((short_wins / short_closed) * 100, 2) if short_closed > 0 else 0

        return {
            "total": total,
            "open": open_trades,
            "closed": closed,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "sl": sl,
            "wins": wins,
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "avg_result_pct": avg_result_pct,
            "avg_duration": avg_duration,
            "long_total": long_total,
            "long_wins": long_wins,
            "long_losses": long_losses,
            "long_win_rate": long_win_rate,
            "long_avg_rr": long_avg_rr,
            "long_avg_result_pct": long_avg_result_pct,
            "long_avg_duration": long_avg_duration,
            "short_total": short_total,
            "short_wins": short_wins,
            "short_losses": short_losses,
            "short_win_rate": short_win_rate,
            "short_avg_rr": short_avg_rr,
            "short_avg_result_pct": short_avg_result_pct,
            "short_avg_duration": short_avg_duration
        }

    except Exception as e:
        print(f"❌ Report Error: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 🌐 RENDER KEEP ALIVE SERVER
# ================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "🐋 AHAD AI v21.1.7 – Production Analytics ONLINE 🚀"

@app.route("/health")
def health():
    """Health check endpoint for monitoring"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        return "✅ HEALTHY", 200
    except Exception as e:
        return f"❌ UNHEALTHY: {e}", 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

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
        params = {"instId": symbol, "bar": frames[tf], "limit": 200}

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
print("🔥 AHAD AI v21.1.7 – Production Analytics CORE READY 🐋")


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
    """Get cached candles with timestamp for TTL cleanup"""
    key = f"{symbol}_{tf}"
    now = time.time()
    
    if key in _candle_cache:
        cached = _candle_cache[key]
        # Check if cached data is a tuple (candles, timestamp)
        if isinstance(cached, tuple) and len(cached) == 2:
            candles, timestamp = cached
            # If less than 10 minutes old, return cached data
            if now - timestamp < 600:
                return candles
            # Otherwise, remove old cache and fetch fresh data
            del _candle_cache[key]
    
    candles = get_candles(symbol, tf)
    _candle_cache[key] = (candles, now)
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
    """Calculate volatility compression score with improved detection"""
    try:
        if len(candles) < 60:
            return {
                "score": 0,
                "status": "UNKNOWN",
                "range": 0,
                "atr_now": 0,
                "atr_old": 0,
                "bonus": 0
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
            bonus = 20
        elif compression >= 50:
            status = "⚡ BUILDING PRESSURE"
            bonus = 10
        elif compression >= 30:
            status = "📊 NORMAL COMPRESSION"
            bonus = 5
        else:
            status = "📈 EXPANDING"
            bonus = -5

        return {
            "score": round(compression),
            "status": status,
            "range": round(price_range, 6),
            "atr_now": round(atr_now, 6),
            "atr_old": round(atr_old, 6),
            "bonus": bonus
        }

    except Exception as e:
        print("VOLATILITY ERROR:", e)
        return {
            "score": 0,
            "status": "ERROR",
            "range": 0,
            "atr_now": 0,
            "atr_old": 0,
            "bonus": 0
}
        # ================================================
# 📊 MARKET REGIME ENGINE (FIXED)
# ================================================

def market_regime(candles, compression_score):
    """Classify market into TRENDING, RANGING, or COMPRESSION"""
    try:
        if len(candles) < 150:
            return {
                "regime": "UNKNOWN",
                "strength": 0,
                "confidence": 0,
                "description": "Insufficient data (need 150 candles)"
            }

        closes = [x["close"] for x in candles[-150:]]
        highs = [x["high"] for x in candles[-150:]]
        lows = [x["low"] for x in candles[-150:]]

        # Calculate ATR for normalization
        atr_val = atr(candles[-14:])

        # Calculate trend strength using EMA slopes
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema100 = ema(closes, 100)

        # Calculate price expansion
        price_range = max(highs) - min(lows)
        avg_price = sum(closes) / len(closes)
        expansion_ratio = price_range / avg_price if avg_price > 0 else 0

        # Calculate EMA alignment
        ema_alignment = 0
        if ema20 > ema50 > ema100:
            ema_alignment = 1  # Bullish alignment
        elif ema20 < ema50 < ema100:
            ema_alignment = -1  # Bearish alignment
        else:
            ema_alignment = 0  # Mixed

        # Trend strength based on EMA slopes
        if len(closes) >= 10:
            slope20 = (ema20 - ema(closes[:-10], 20)) / ema20 if ema20 > 0 else 0
            slope50 = (ema50 - ema(closes[:-10], 50)) / ema50 if ema50 > 0 else 0
            avg_slope = (abs(slope20) + abs(slope50)) / 2
        else:
            avg_slope = 0

        # Classification logic
        if compression_score >= 50:
            regime = "COMPRESSION"
            strength = compression_score
            confidence = 70 + (compression_score / 100) * 20
            description = "Market compressing - breakout imminent"
        elif expansion_ratio > 0.08 and avg_slope > 0.02:
            regime = "TRENDING"
            strength = min(100, avg_slope * 1000)
            confidence = min(90, 60 + strength * 0.3)
            direction = "BULLISH" if ema_alignment > 0 else "BEARISH"
            description = f"Strong trend detected ({direction})"
        elif expansion_ratio < 0.03 and avg_slope < 0.01:
            regime = "RANGING"
            strength = 50
            confidence = 70
            description = "Market ranging - no clear direction"
        else:
            regime = "MIXED"
            strength = 40
            confidence = 50
            description = "Mixed signals - neutral regime"

        return {
            "regime": regime,
            "strength": round(strength, 2),
            "confidence": round(confidence, 2),
            "description": description,
            "ema_alignment": ema_alignment,
            "expansion_ratio": round(expansion_ratio, 4),
            "avg_slope": round(avg_slope, 4)
        }

    except Exception as e:
        print(f"❌ Market Regime Error: {e}")
        return {
            "regime": "UNKNOWN",
            "strength": 0,
            "confidence": 0,
            "description": "Error in regime detection"
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
# 🛡 SYMMETRIC FOMO FILTER
# ================================================

def fomo_filter(candles, direction="LONG"):
    """
    Symmetric FOMO Filter - detects overextended moves for both directions.
    Returns (safe, warning, reject_reason)
    """
    closes = [x["close"] for x in candles]
    price = closes[-1]

    # Calculate move percentages
    move_30 = ((price - closes[-30]) / closes[-30]) * 100
    move_96 = ((price - closes[-96]) / closes[-96]) * 100
    current_rsi = rsi(closes)

    # Direction-specific detection
    if direction == "LONG":
        # Detect overextended bullish move
        if move_30 > 8 or move_96 > 15:
            return False, "🚫 OVEREXTENDED BULLISH", "FOMO_OVEREXTENDED_BULL"
        
        if move_30 > 5 and current_rsi > 65:
            return False, "⏳ WAIT PULLBACK", "FOMO_PULLBACK"
        
        if current_rsi > 75:
            return False, "🚫 RSI OVERBOUGHT", "FOMO_RSI_OVERBOUGHT"
        
        if current_rsi < 35:
            return False, "📉 RSI OVERSOLD - NOT LONG", "FOMO_RSI_OVERSOLD"
        
        return True, "🐋 EARLY LONG AREA", None

    else:  # SHORT
        # Detect overextended bearish move
        if move_30 < -8 or move_96 < -15:
            return False, "🚫 OVEREXTENDED BEARISH", "FOMO_OVEREXTENDED_BEAR"
        
        if move_30 < -5 and current_rsi < 35:
            return False, "⏳ WAIT BOUNCE", "FOMO_BOUNCE"
        
        if current_rsi < 25:
            return False, "🚫 RSI OVERSOLD", "FOMO_RSI_OVERSOLD"
        
        if current_rsi > 65:
            return False, "📈 RSI OVERBOUGHT - NOT SHORT", "FOMO_RSI_OVERBOUGHT"
        
        return True, "🐻 EARLY SHORT AREA", None


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
# 🧠 AI BRAIN ENGINE
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
# 🎯 SECTION 3: ANALYZE ENGINE (v21.1.7)
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

        # ====== CACHED CANDLES ======
        c15 = get_candles_cached(symbol, "15m")
        c1h = get_candles_cached(symbol, "1h")
        c4h = get_candles_cached(symbol, "4h")
        c1d = get_candles_cached(symbol, "1d")

        if len(c15) < 60 or len(c1h) < 60 or len(c4h) < 60 or len(c1d) < 60:
            reject_reason = "Candles"
            if debug is not None:
                debug["candles"] = debug.get("candles", 0) + 1
            return None

        price = c15[-1]["close"]

        # ================================================
        # 🧠 AI BRAIN DETECTION
        # ================================================

        brain = ai_brain(c1h)
        debug_reason = []

        if brain["direction"] == "WAIT":
            brain_penalty = 10
            reject_reason = "Brain"
            if debug is not None:
                debug["brain"] = debug.get("brain", 0) + 1
            return None
        else:
            brain_penalty = 0

        direction = brain["direction"]
        direction_clean = direction.replace("🟢 ", "").replace("🔴 ", "")

        # ================================================
        # 🛡️ SYMMETRIC FOMO FILTER
        # ================================================

        safe, warning_text, fomo_reason = fomo_filter(c15, direction_clean)
        if not safe:
            reject_reason = f"FOMO: {fomo_reason}"
            if debug is not None:
                debug["fomo"] = debug.get("fomo", 0) + 1
            return None

        # ================================================
        # 📊 ENGINE CALCULATIONS
        # ================================================

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
        # 📊 MARKET REGIME
        # ================================================

        regime = market_regime(c15, vol["score"])

        # ================================================
        # 🔥 SMART RSI
        # ================================================

        rsi_score = 0
        if 45 <= rsi_15m <= 62:
            rsi_score = 8
        elif 62 < rsi_15m <= 70:
            rsi_score = 5
            warning_text = "⚠️ RSI WARNING"
        elif rsi_15m > 70 or rsi_15m < 35:
            rsi_score = -10
            warning_text = "⚠️ RSI EXTREME"

        # ================================================
        # 💧 DYNAMIC FLOW (SINGLE SOURCE - FIXED)
        # ================================================

        flow_score = 0
        if flow < 0.8:
            reject_reason = "Low Flow"
            if debug is not None:
                debug["flow"] = debug.get("flow", 0) + 1
            return None
        elif flow >= 3:
            flow_score = 25
            money_status = "🚀 HIGH WHALE FLOW"
        elif flow >= 1.8:
            flow_score = 20
            money_status = "🐋 INSTITUTIONAL FLOW"
        elif flow >= 1.2:
            flow_score = 10
            money_status = "💧 HEALTHY FLOW"
        else:
            flow_score = 5
            money_status = "NORMAL"

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
if direction_clean == "LONG":
    if price > ema20_15:
        tf_score += 5
    else:
        tf_alignment = False
else:  # SHORT
    if price < ema20_15:
        tf_score += 5
    else:
        tf_alignment = False

ema20_1h = ema(closes1h, 20)
if direction_clean == "LONG":
    if closes1h[-1] > ema20_1h:
        tf_score += 5
    else:
        tf_alignment = False
else:  # SHORT
    if closes1h[-1] < ema20_1h:
        tf_score += 5
    else:
        tf_alignment = False

ema20_4h = ema(closes4h, 20)
if direction_clean == "LONG":
    if closes4h[-1] < ema20_4h * 0.97:
        tf_score -= 10
else:  # SHORT
    if closes4h[-1] > ema20_4h * 1.03:
        tf_score -= 10

# ================================================
# 🔥 STRONG CANDLE CHECK
# ================================================

candle_score = 0
last_candle = c15[-1]
body = abs(last_candle["close"] - last_candle["open"])
avg_body = sum([abs(c["close"] - c["open"]) for c in c15[-20:]]) / 20

if direction_clean == "LONG":
    if last_candle["close"] > last_candle["open"] and body > avg_body * 1.2:
        candle_score += 5
    elif body < (last_candle["high"] - last_candle["low"]) * 0.1:
        candle_score -= 5
else:  # SHORT
    if last_candle["close"] < last_candle["open"] and body > avg_body * 1.2:
        candle_score += 5
    elif body < (last_candle["high"] - last_candle["low"]) * 0.1:
        candle_score -= 5

# ================================================
# 📊 DYNAMIC LATE ENTRY v3
# ================================================

move = atr(c15)

ema20_15 = ema(closes15, 20)
ema50_15 = ema(closes15, 50)
ema100_15 = ema(closes15, 100)

late_score = 0

# Symmetric distance calculation
if direction_clean == "LONG":
    # Measure distance ABOVE EMA50 for LONG
    distance = price - ema50_15
else:  # SHORT
    # Measure distance BELOW EMA50 for SHORT
    distance = ema50_15 - price

if distance > move * 0.5:
    late_score += 20

if distance > move * 1.0:
    late_score += 20

# Symmetric trend bonus
if direction_clean == "LONG":
    if ema20_15 > ema50_15 > ema100_15:
        late_score -= 10
    if price > ema20_15:
        late_score -= 5
else:  # SHORT
    if ema20_15 < ema50_15 < ema100_15:
        late_score -= 10
    if price < ema20_15:
        late_score -= 5

# Symmetric momentum penalty
if direction_clean == "LONG":
    last3_gain = ((closes15[-1] - closes15[-4]) / closes15[-4])
    if last3_gain > 0.06:
        late_score += 15
else:  # SHORT
    last3_loss = ((closes15[-4] - closes15[-1]) / closes15[-4])
    if last3_loss > 0.06:
        late_score += 15

# Decision
if late_score >= 35:
    reject_reason = "Late Entry"
    if debug is not None:
        debug["late_entry"] = debug.get("late_entry", 0) + 1
        debug["late_score"] = late_score
    return None
else:
    if debug is not None:
        debug["late_score"] = late_score

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

if abs(price_velocity) > 3:
    momentum_score += 40
elif abs(price_velocity) > 1:
    momentum_score += 25
elif abs(price_velocity) > 0:
    momentum_score += 10

if volume_acceleration > 2:
    momentum_score += 30
elif volume_acceleration > 1.5:
    momentum_score += 20
elif volume_acceleration > 1.2:
    momentum_score += 10

if breakout_strength > 80 or breakout_strength < 20:
    momentum_score += 30
elif breakout_strength > 60 or breakout_strength < 40:
    momentum_score += 20
elif breakout_strength > 50 or breakout_strength < 50:
    momentum_score += 10

momentum_score = min(100, momentum_score)

if momentum_score >= 70:
    momentum_status = "🔥 Strong"
elif momentum_score >= 50:
    momentum_status = "⚡ Moderate"
else:
    momentum_status = "⚠️ Weak"

# ================================================
# 📊 DYNAMIC MOMENTUM WEIGHT
# ================================================

if regime["regime"] == "TRENDING":
    momentum_weight = 1.5
elif regime["regime"] == "COMPRESSION":
    momentum_weight = 0.8
else:  # RANGING or MIXED
    momentum_weight = 1.0

# ================================================
# 🧠 REBALANCED SCORE ENGINE
# ================================================

score = 0

# Brain confidence
score += brain["confidence"] * 0.3

# Flow score
score += flow_score * 1.5

# Momentum with dynamic weight
score += (momentum_score * 0.2) * momentum_weight

# Compression bonus
score += vol["bonus"]

# Support/Resistance
if direction_clean == "LONG":
    if sr["near_resistance"] > 5:
        score += 10
    elif sr["near_resistance"] > 3:
        score += 5
else:  # SHORT
    if sr["near_support"] > 5:
        score += 10
    elif sr["near_support"] > 3:
        score += 5

# Trap detection
if trap == "✅ NO TRAP":
    score += 10

# Multi timeframe
score += multi["score"] * 0.1

# RSI
if direction_clean == "LONG":
    score += rsi_score * 0.5
else:  # SHORT
    # RSI scoring symmetric for SHORT
    if 35 <= rsi_15m <= 55:
        score += 8
    elif 25 <= rsi_15m < 35:
        score += 5
    elif rsi_15m < 25 or rsi_15m > 65:
        score -= 10

# MACD
if direction_clean == "LONG":
    score += macd_score * 0.5
else:  # SHORT
    macd_short_score = 3 if macd_value < 0 else 0
    score += macd_short_score * 0.5

# Brain penalty
score -= brain_penalty

score = round(max(0, min(100, score)))

# ================================================
# 🔥 PENALTIES
# ================================================

late_penalty = 0
if direction_clean == "LONG":
    if rsi_15m >= 68:
        late_penalty += 20
else:  # SHORT
    if rsi_15m <= 32:
        late_penalty += 20
score -= late_penalty
score = max(0, score)

if len(c15) >= 6:
    if direction_clean == "LONG":
        pump = c15[-1]["close"] / c15[-6]["close"]
        if pump > 1.05:
            score -= 15
    else:  # SHORT
        dump = c15[-6]["close"] / c15[-1]["close"]
        if dump > 1.05:
            score -= 15

# ================================================
# 🔥 TRAP CHECK
# ================================================

if trap == "🪤 BULL TRAP" and direction_clean == "LONG":
    reject_reason = "Trap"
    if debug is not None:
        debug["trap"] = debug.get("trap", 0) + 1
    return None

if trap == "🪤 BEAR TRAP" and direction_clean == "SHORT":
    reject_reason = "Trap"
    if debug is not None:
        debug["trap"] = debug.get("trap", 0) + 1
    return None

# ================================================
# 🔥 HEAT CONTROL
# ================================================

if direction_clean == "LONG":
    if multi["4h"] > 70:
        score -= 10
    if multi["1d"] > 70:
        score -= 10
    if multi["15m"] > 75:
        score -= 5
else:  # SHORT
    if multi["4h"] < 30:
        score -= 10
    if multi["1d"] < 30:
        score -= 10
    if multi["15m"] < 25:
        score -= 5

# ================================================
# 🔥 RESISTANCE/SUPPORT FILTER
# ================================================

if direction_clean == "LONG":
    distance_to_resistance = sr["near_resistance"] * price / 100
    if distance_to_resistance < move * 1.2:
        reject_reason = "Too Close Resistance"
        if debug is not None:
            debug["resistance"] = debug.get("resistance", 0) + 1
        return None
else:  # SHORT
    distance_to_support = sr["near_support"] * price / 100
    if distance_to_support < move * 1.2:
        reject_reason = "Too Close Support"
        if debug is not None:
            debug["resistance"] = debug.get("resistance", 0) + 1
        return None

# ================================================
# 🔥 HIGHER TIMEFRAME TREND FILTER v2
# ================================================

e200_4h = ema(closes4h, 200)
if direction_clean == "LONG":
    if closes4h[-1] < e200_4h:
        reject_reason = "Higher Trend Down"
        if debug is not None:
            debug["higher_trend"] = debug.get("higher_trend", 0) + 1
        return None
else:  # SHORT
    if closes4h[-1] > e200_4h:
        reject_reason = "Higher Trend Up"
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
# 🎯 ENTRY ZONE & TARGETS
# ================================================

entry_low = price * 0.995
entry_high = price * 1.005

# Dynamic RR based on market conditions
if regime["regime"] == "TRENDING":
    rr_multiplier = 1.8
elif regime["regime"] == "COMPRESSION":
    rr_multiplier = 2.2
else:
    rr_multiplier = 1.5

if flow >= 2:
    rr_multiplier += 0.3
if momentum_score >= 70:
    rr_multiplier += 0.2

if direction_clean == "LONG":
    base_multiplier = 1.5
    if flow >= 2:
        base_multiplier += 0.3
    if money_status in ["🚀 HIGH WHALE FLOW", "🐋 INSTITUTIONAL FLOW"]:
        base_multiplier += 0.3
    if momentum_score >= 70:
        base_multiplier += 0.2

    sl = entry_low - move * base_multiplier
    risk = entry_low - sl

    tp1 = entry_low + risk * rr_multiplier
    tp2 = entry_low + risk * (rr_multiplier * 2)
    tp3 = entry_low + risk * (rr_multiplier * 3.3)

    if tp1 <= entry_high:
        tp1 = entry_high + move * 0.8

    if tp2 <= tp1:
        tp2 = tp1 + move * 0.5
    if tp3 <= tp2:
        tp3 = tp2 + move * 0.5

    rr = (tp1 - entry_low) / risk

else:  # SHORT
    base_multiplier = 1.5
    if flow >= 2:
        base_multiplier += 0.3
    if money_status in ["🚀 HIGH WHALE FLOW", "🐋 INSTITUTIONAL FLOW"]:
        base_multiplier += 0.3
    if momentum_score >= 70:
        base_multiplier += 0.2

    sl = entry_high + move * base_multiplier
    risk = sl - entry_high

    tp1 = entry_high - risk * rr_multiplier
    tp2 = entry_high - risk * (rr_multiplier * 2)
    tp3 = entry_high - risk * (rr_multiplier * 3.3)

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

        if direction_clean == "LONG":
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
        # 💎 PROFESSIONAL QUALITY ENGINE v2.0
        # ================================================

        brain_conf = brain["confidence"]

        if (
            score >= 95
            and brain_conf >= 80
            and rr >= 3.0
            and momentum_score >= 85
            and flow >= 2.0
        ):
            quality = "💎 ELITE SETUP"

        elif (
            score >= 90
            and brain_conf >= 70
            and rr >= 2.5
        ):
            quality = "🔥 PREMIUM SETUP"

        elif (
            score >= 80
            and brain_conf >= 60
        ):
            quality = "✅ HIGH QUALITY"

        elif (
            score >= 70
        ):
            quality = "⚡ GOOD SETUP"

        else:
            quality = "👀 WATCHLIST"
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
        # 🐋 MONEY STATUS (SINGLE SOURCE - FIXED)
        # ================================================

        # Already calculated above in DYNAMIC FLOW section

        # ================================================
        # 🎯 EARLY ENTRY CHECK
        # ================================================

        if direction_clean == "LONG":
            if momentum_score >= 60 and flow >= 1.2 and sr["near_resistance"] > 3:
                early_text = "🐋 EARLY ENTRY AREA"
            else:
                early_text = "⏳ WAIT FOR ENTRY"
        else:  # SHORT
            if momentum_score >= 60 and flow >= 1.2 and sr["near_support"] > 3:
                early_text = "🐻 EARLY ENTRY AREA"
            else:
                early_text = "⏳ WAIT FOR ENTRY"

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
            debug["regime"] = regime["regime"]
            debug["compression_score"] = vol["score"]
            debug["momentum_weight"] = round(momentum_weight, 2)
            debug["late_score"] = late_score

        # ================================================
        # 📊 INSTITUTIONAL FLOW RATING
        # ================================================

        if flow >= 3.0:
            flow_rating = "AAA"
            flow_label = "🚀 EXTREME"
        elif flow >= 2.0:
            flow_rating = "AA"
            flow_label = "🐋 HIGH"
        elif flow >= 1.5:
            flow_rating = "A"
            flow_label = "💧 GOOD"
        elif flow >= 1.2:
            flow_rating = "BBB"
            flow_label = "📊 MODERATE"
        else:
            flow_rating = "BB"
            flow_label = "⚠️ LOW"

        # ================================================
        # 🛡️ RISK GRADE
        # ================================================

        if rr >= 3.0 and brain["confidence"] >= 70 and score >= 85:
            risk_grade = "🟢 LOW RISK"
            risk_icon = "🟢"
        elif rr >= 2.0 and brain["confidence"] >= 50 and score >= 70:
            risk_grade = "🟡 MEDIUM RISK"
            risk_icon = "🟡"
        else:
            risk_grade = "🔴 HIGH RISK"
            risk_icon = "🔴"

        # ================================================
        # 🧠 AI DECISION SUMMARY (COMPLETE)
        # ================================================

        decision_reasons = []

        # Market Structure
        if regime["regime"] in ["TRENDING", "COMPRESSION"]:
            decision_reasons.append("✅ Strong Market Structure")
        else:
            decision_reasons.append("📊 Neutral Market Structure")

        # Momentum
        if momentum_score >= 70:
            decision_reasons.append("✅ Strong Momentum")
        elif momentum_score >= 50:
            decision_reasons.append("⚡ Moderate Momentum")
        else:
            decision_reasons.append("📉 Weak Momentum")

        # Institutional Flow
        if flow >= 1.5:
            decision_reasons.append("✅ Institutional Flow")
        else:
            decision_reasons.append("📊 Normal Flow")

        # Risk/Reward
        if rr >= 2.5:
            decision_reasons.append("✅ High Risk/Reward")
        else:
            decision_reasons.append("📊 Standard RR")

        # Brain Confidence
        if brain["confidence"] >= 60:
            decision_reasons.append("✅ High Brain Confidence")
        else:
            decision_reasons.append("📊 Moderate Brain Confidence")

        # Compression Setup
        if vol["status"] in ["🔥 SPRING LOADED", "⚡ BUILDING PRESSURE"]:
            decision_reasons.append("✅ Compression Setup")
        else:
            decision_reasons.append("📊 Normal Volatility")

        # Trap Detection
        if trap == "✅ NO TRAP":
            decision_reasons.append("✅ No Trap Detected")

        # Sector Strength
        if sector not in ["UNKNOWN", "RWA"]:
            decision_reasons.append("✅ Strong Sector")
        else:
            decision_reasons.append("📊 Neutral Sector")

        # Late Entry Score
        if late_score < 20:
            decision_reasons.append("✅ Early Entry Zone")
        elif late_score < 30:
            decision_reasons.append("⚡ Moderate Entry Zone")
        else:
            decision_reasons.append("⏳ Late Entry Warning")

        # Validation Passed
        if not validation_errors:
            decision_reasons.append("✅ Validation Passed")

        if len(decision_reasons) == 0:
            decision_reasons.append("⏳ Standard Setup")

        decision_summary = "\n".join(decision_reasons[:12])

        # ================================================
        # 📦 TRADE DATA (v21.1.7 - COMPLETE)
        # ================================================

        trade_data = {
            'symbol': symbol,
            'side': direction_clean,
            'signal_time': datetime.now(),
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
            'version': 'v21.1.7',
            'brain_confidence': brain['confidence'],
            'market_regime': regime['regime'],
            'compression_score': vol['score'],
            'compression_status': vol['status'],
            'momentum_weight': round(momentum_weight, 2),
            'flow_score': flow_score,
            'volume_acceleration': round(volume_acceleration, 2),
            'flow_rating': flow_rating,
            'risk_grade': risk_grade,
            'decision_summary': decision_summary
        }

        # ================================================
        # 📊 LOGGING
        # ================================================

        print(f"✅ SIGNAL ACCEPTED: {symbol} | {direction_clean} | Score: {round(score)} | Flow: {round(flow,2)} | RR: {round(rr,2)} | Regime: {regime['regime']}")

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
            "warning": warning_text,
            "volatility": vol,
            "regime": regime,
            "reject_reason": reject_reason,
            "debug_reason": debug_reason,
            "momentum_score": momentum_score,
            "momentum_status": momentum_status,
            "rr": round(rr, 2),
            "brain_long_score": brain["long_score"],
            "brain_short_score": brain["short_score"],
            "late_score": late_score,
            "brain_confidence": brain["confidence"],
            "flow_rating": flow_rating,
            "flow_label": flow_label,
            "risk_grade": risk_grade,
            "risk_icon": risk_icon,
            "decision_summary": decision_summary,
            "trade_data": trade_data
        }

    except Exception as e:
        print("ANALYZE ERROR:", e)
        return None


# ================================================
# 🤖 SECTION 4: TELEGRAM SCANNER (v21.1.7)
# ================================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, """
🐋 AHAD AI v21.1.7 – Production Analytics 🚀

🗄 PostgreSQL Database ACTIVE (v21.1.7)
💾 Trade Recorder ACTIVE (Duplicate Protection)
📈 Trade Tracker ACTIVE (HIGH/LOW Accuracy)
📊 Performance Analytics ACTIVE (LONG/SHORT Breakdown)
🧠 AI Brain v2.0 ACTIVE
🐋 Smart Money ACTIVE
📊 Multi TimeFrame ACTIVE
🪤 Trap Detector ACTIVE
⚡ Pre-Pump Detection ACTIVE
🔥 Heat Control ACTIVE
🎯 Dynamic Late Entry v3 ACTIVE (Symmetric)
📊 Enhanced Score System ACTIVE (Symmetric)
🐞 Full Debug Funnel ACTIVE
🔥 Volatility Compression ACTIVE (Integrated)
📊 Market Regime ACTIVE (Fixed EMA100)
🚀 Enhanced Momentum Engine ACTIVE (Dynamic Weight)
📌 Reject Reason ACTIVE
🧠 Confidence Level ACTIVE
🎯 New RR Engine ACTIVE (Dynamic)
📈 Higher Timeframe Filter v2 ACTIVE (Symmetric)
✅ Dynamic Flow Scanner ACTIVE
🛡️ Validation Layer ACTIVE
📊 Brain LONG/SHORT Scores ACTIVE
🐞 Debug Reason ACTIVE
🔄 Dual Direction Engine ACTIVE (Fully Symmetric)
🗄 PostgreSQL Production Ready
🔒 SSL Connection ENABLED
📊 7 Indexes for Performance
⏰ TIMESTAMP Support
📈 Professional Analytics ACTIVE
📊 Market Regime & Compression Tracking
🏦 Institutional Dashboard ACTIVE
💎 Professional Quality Engine v2.0 ACTIVE
🏆 Professional Ranking Engine ACTIVE
📦 Caching System ACTIVE (TTL=600s)
📊 Extended Data Collection ACTIVE
📈 Result % & Duration Tracking ACTIVE

🎯 Goal: Best 2 LONG + Best 1 SHORT

Commands:
/scan – Run scanner with Institutional Dashboard
/report – Performance report
/open – Open trades list
/history – Last 10 closed trades
""")


# ================================================
# 🔎 SMART SCANNER (v21.1.7)
# ================================================

@bot.message_handler(commands=["scan"])
def scan(message):
    bot.reply_to(message, """
🐋 AHAD AI v21.1.7 – Production Analytics SCANNING...

🔍 Checking Market Flow
🏦 Finding Hot Sector (Ranked)
🟢 Hunting TOP 2 LONG setups
🔴 Hunting TOP 1 SHORT setup
🐋 Tracking Smart Money
⚡ Detecting Pre-Pump
📊 Market Regime Detection ACTIVE
🔥 Volatility Compression ACTIVE
🚀 Dynamic Momentum ACTIVE
📊 Enhanced Score System ACTIVE
🐞 Full Debug Funnel ACTIVE
📌 Reject Reason ACTIVE
🎯 New RR Engine ACTIVE
✅ Dynamic Flow Scanner ACTIVE
🛡️ Validation Layer ACTIVE
🧠 Brain v2.0 ACTIVE
🎯 Dynamic Late Entry v3 ACTIVE
🐞 Debug Reason ACTIVE
💾 Trade Recorder ACTIVE (Duplicate Protection)
📈 Trade Tracker ACTIVE (HIGH/LOW Accuracy)
📊 Performance Analytics ACTIVE
🔄 Dual Direction Engine ACTIVE (Fully Symmetric)
🗄 PostgreSQL Production Ready (v21.1.7)
🏦 Institutional Dashboard ACTIVE
📦 Caching System ACTIVE (TTL=600s)
📊 Extended Data Collection ACTIVE
🧹 Cache Cleanup ACTIVE

Please wait ⏳
""")
    # ====== CLEAR CACHE BEFORE SCAN ======
    global _candle_cache
    _candle_cache.clear()
    # ====================================

    debug = {}
    debug["reject_reasons"] = {}

    long_results = []
    short_results = []
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

    # ====== SECTOR SUMMARY DATA COLLECTION ======
    sector_data = {sector: {"coins": 0, "flows": [], "scores": []} for sector in SECTORS.keys()}

    if len(symbols) < 20:
        symbols = all_symbols

    bot.send_message(message.chat.id, f"💎 Smart Money Watchlist: {len(symbols)} coins")

    # ====== COLLECT MARKET HEALTH DATA ======
    market_regimes = {}
    market_flows = []
    market_brain_scores = []
    market_compression_status = []

    # ====== SCAN EFFICIENCY TRACKING ======
    scan_start_time = time.time()
    api_calls = 0
    cache_hits = 0

    for symbol in symbols:

        print("=" * 50)
        print("START:", symbol)

        # ====== SECTOR DETECTION ======
        base = symbol.split("-")[0]
        coin_sector = "UNKNOWN"
        for sector, coins in SECTORS.items():
            if base in coins:
                coin_sector = sector
                break
        # ==============================

        # Track cache usage
        key = f"{symbol}_15m"
        if key in _candle_cache:
            cache_hits += 1
        else:
            api_calls += 1

        result = analyze(symbol, coin_sector, debug=debug)

        print("END:", symbol)

        # ====== SECTOR DATA COLLECTION ======
        if result and coin_sector in sector_data:
            sector_data[coin_sector]["coins"] += 1
            sector_data[coin_sector]["flows"].append(result.get("liquidity", 0))
            sector_data[coin_sector]["scores"].append(result.get("score", 0))

        # ====== COLLECT DATA FOR EVERY ANALYZED COIN ======
        if result:
            # Collect regime, flow, brain, compression for EVERY coin
            regime_name = result["regime"]["regime"]
            market_regimes[regime_name] = market_regimes.get(regime_name, 0) + 1
            market_flows.append(result["liquidity"])
            market_brain_scores.append(result["brain_confidence"])
            market_compression_status.append(result["volatility"]["status"])

            # ====== REGIME COUNTER ======
            debug.setdefault("regimes", {})
            debug["regimes"][regime_name] = debug["regimes"].get(regime_name, 0) + 1

            # ====== COMPRESSION COUNTER ======
            compression_name = result["volatility"]["status"]
            debug.setdefault("compressions", {})
            debug["compressions"][compression_name] = debug["compressions"].get(compression_name, 0) + 1

            # ====== CHECK IF ACCEPTED ======
            if result["direction"] == "🟢 LONG":
                if (
                    result["score"] >= 68
                    and (
                        result["liquidity"] >= 1.2
                        or result["pre_pump"] == "🐋 WHALE LOADING"
                    )
                ):
                    long_results.append(result)
                    print(f"✅ LONG ACCEPTED: {result['coin']} | Score: {result['score']} | Flow: {result['liquidity']} | Regime: {result['regime']['regime']}")
                else:
                    debug["final_gate"] = debug.get("final_gate", 0) + 1
                    reason = (
                        "Not Long"
                        if not result.get("debug_reason")
                        else " | ".join(result["debug_reason"])
                    )
                    debug.setdefault("reject_reasons", {})
                    debug["reject_reasons"][reason] = (
                        debug["reject_reasons"].get(reason, 0) + 1
                    )
                    debug["reject_reason"] = reason
                    print(
                        f"❌ LONG REJECTED | "
                        f"{result['coin']} | "
                        f"Score={result['score']} | "
                        f"Flow={result['liquidity']} | "
                        f"PrePump={result['pre_pump']} | "
                        f"Reason={debug['reject_reason']} | "
                        f"Brain={result['direction']} | "
                        f"LateScore={result.get('late_score', 0)}"
                    )

            elif result["direction"] == "🔴 SHORT":
                if (
                    result["score"] >= 68
                    and (
                        result["liquidity"] >= 1.2
                        or result["pre_pump"] == "🐋 WHALE LOADING"
                    )
                ):
                    short_results.append(result)
                    print(f"✅ SHORT ACCEPTED: {result['coin']} | Score: {result['score']} | Flow: {result['liquidity']} | Regime: {result['regime']['regime']}")
                else:
                    debug["final_gate"] = debug.get("final_gate", 0) + 1
                    reason = (
                        "Not Short"
                        if not result.get("debug_reason")
                        else " | ".join(result["debug_reason"])
                    )
                    debug.setdefault("reject_reasons", {})
                    debug["reject_reasons"][reason] = (
                        debug["reject_reasons"].get(reason, 0) + 1
                    )
                    debug["reject_reason"] = reason
                    print(
                        f"❌ SHORT REJECTED | "
                        f"{result['coin']} | "
                        f"Score={result['score']} | "
                        f"Flow={result['liquidity']} | "
                        f"PrePump={result['pre_pump']} | "
                        f"Reason={debug['reject_reason']} | "
                        f"Brain={result['direction']} | "
                        f"LateScore={result.get('late_score', 0)}"
                    )

            else:
                debug["not_long"] = debug.get("not_long", 0) + 1
                reason = (
                    "Not Long/Short"
                    if not result.get("debug_reason")
                    else " | ".join(result["debug_reason"])
                )
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"][reason] = (
                    debug["reject_reasons"].get(reason, 0) + 1
                )
                debug["reject_reason"] = reason

                print(
                    f"⏳ WAIT SIGNAL | "
                    f"{result['coin']} | "
                    f"Score={result['score']} | "
                    f"Reason={debug['reject_reason']}"
                )

        time.sleep(0.03)

    # ====== CALCULATE SECTOR SUMMARY ======
    sector_summary = []
    for sector, data in sector_data.items():
        if data["coins"] > 0:
            avg_flow = round(sum(data["flows"]) / len(data["flows"]), 2) if data["flows"] else 0
            avg_score = round(sum(data["scores"]) / len(data["scores"]), 1) if data["scores"] else 0
            sector_summary.append({
                "sector": sector,
                "coins": data["coins"],
                "avg_flow": avg_flow,
                "avg_score": avg_score
            })
    sector_summary.sort(key=lambda x: x["avg_flow"], reverse=True)

    # ====== CALCULATE AVERAGE METRICS ======
    all_results = long_results + short_results
    
    # ====== FIX: Average Flow & Brain from ALL analyzed coins ======
    if market_flows:
        avg_flow = round(sum(market_flows) / len(market_flows), 2)
    else:
        avg_flow = 0

    if market_brain_scores:
        avg_brain = round(sum(market_brain_scores) / len(market_brain_scores), 1)
    else:
        avg_brain = 0

    # Keep these for backward compatibility
    if all_results:
        avg_score = round(sum(r["score"] for r in all_results) / len(all_results), 2)
        avg_rr = round(sum(r["rr"] for r in all_results) / len(all_results), 2)
        avg_momentum = round(sum(r["momentum_score"] for r in all_results) / len(all_results), 2)
    else:
        avg_score = "N/A"
        avg_rr = "N/A"
        avg_momentum = "N/A"

    debug["avg_flow"] = avg_flow
    debug["avg_brain"] = avg_brain
    debug["avg_score"] = avg_score
    debug["avg_rr"] = avg_rr
    debug["avg_momentum"] = avg_momentum

    # ====== MARKET HEALTH REPORT ======
    total_checked = debug.get('checked', 0)
    
    if total_checked > 0 and market_regimes:
        # Market Regime Distribution - from ALL checked coins
        bull_pct = round((market_regimes.get("TRENDING", 0) / total_checked) * 100, 1)
        bear_pct = round((market_regimes.get("BEARISH", 0) / total_checked) * 100, 1)
        sideways_pct = round((market_regimes.get("RANGING", 0) / total_checked) * 100, 1)
        mixed_pct = round((market_regimes.get("MIXED", 0) / total_checked) * 100, 1)
        compression_pct = round((market_regimes.get("COMPRESSION", 0) / total_checked) * 100, 1)
        
        # Compression Status - from ALL checked coins
        high_compression = sum(1 for s in market_compression_status if "SPRING LOADED" in s or "BUILDING" in s)
        compression_high_pct = round((high_compression / len(market_compression_status)) * 100, 1) if market_compression_status else 0
        
        # Market Quality
        if bull_pct > 50 and avg_brain > 70:
            market_quality = "🔥 EXCELLENT"
        elif bull_pct > 30 and avg_brain > 60:
            market_quality = "✅ GOOD"
        elif bear_pct > 50:
            market_quality = "⚠️ CAUTION"
        else:
            market_quality = "📊 NEUTRAL"
        
        # ====== MARKET TEMPERATURE ======
        temp_score = (avg_flow * 20) + (avg_brain * 0.3) + (compression_high_pct * 0.2)
        
        if temp_score > 80:
            market_temp = "🔴 OVERHEATED"
        elif temp_score > 60:
            market_temp = "🟠 HOT"
        elif temp_score > 40:
            market_temp = "🟡 WARM"
        else:
            market_temp = "🟢 COLD"
        
        health_report = f"""
🐘 MARKET HEALTH REPORT

📈 Bull        : {bull_pct}%
📉 Bear        : {bear_pct}%
📊 Sideways    : {sideways_pct}%
🔄 Mixed       : {mixed_pct}%
🔥 Compression : {compression_high_pct}%

📊 Average Flow    : {avg_flow}X
🧠 Average Brain   : {avg_brain}
🏆 Market Quality  : {market_quality}
🌡️ Market Temp     : {market_temp}
"""
        bot.send_message(message.chat.id, health_report)
    else:
        bot.send_message(message.chat.id, """
🐘 MARKET HEALTH REPORT

No classified coins.
Run /scan to analyze market.
""")

    # ====== SECTOR SUMMARY ======
    if sector_summary:
        sector_msg = "🏦 SECTOR SUMMARY\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
        
        for idx, sector_data in enumerate(sector_summary[:6]):
            sector_msg += f"{medals[idx]} {sector_data['sector']}\n"
            sector_msg += f"   Coins        : {sector_data['coins']}\n"
            sector_msg += f"   Avg Flow     : {sector_data['avg_flow']}X\n"
            sector_msg += f"   Avg Score    : {sector_data['avg_score']}\n\n"
        
        bot.send_message(message.chat.id, sector_msg)

    # ====== REGIME DISTRIBUTION (FIXED - ALWAYS SHOW IF DATA EXISTS) ======
    if debug.get("regimes"):
        debug["regime_distribution"] = "\n".join(
            f"{k}: {v}"
            for k, v in sorted(
                debug["regimes"].items(),
                key=lambda x: x[1],
                reverse=True
            )
        )
    else:
        debug["regime_distribution"] = "N/A"

    # ====== COMPRESSION DISTRIBUTION (FIXED - ALWAYS SHOW IF DATA EXISTS) ======
    if debug.get("compressions"):
        debug["compression_distribution"] = "\n".join(
            f"{k}: {v}"
            for k, v in sorted(
                debug["compressions"].items(),
                key=lambda x: x[1],
                reverse=True
            )
        )
    else:
        debug["compression_distribution"] = "N/A"

    # ====== TOP REJECT REASONS (FIXED - ALWAYS SHOW IF DATA EXISTS) ======
    if debug.get("reject_reasons"):
        top_rejects_list = sorted(
            debug["reject_reasons"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        top_rejects = "\n".join(
            f"{emojis[i]} {k} ({v})"
            for i, (k, v) in enumerate(top_rejects_list)
        )
    else:
        top_rejects = "N/A"

    # ====== SCAN EFFICIENCY ======
    scan_end_time = time.time()
    scan_duration = round(scan_end_time - scan_start_time, 2)
    
    total_calls = api_calls + cache_hits
    cache_saved_pct = round((cache_hits / total_calls) * 100, 1) if total_calls > 0 else 0
    
    debug["scan_duration"] = scan_duration
    debug["api_calls"] = api_calls
    debug["cache_hits"] = cache_hits
    debug["cache_saved_pct"] = cache_saved_pct

    checked_count = debug.get('checked', 0)

    debug_msg = f"""
🐞 FULL DEBUG REPORT

━━━━━━━━━━━━━━━━━━━━━━

📊 SCAN STATISTICS
Checked: {checked_count}
Flow Candidates: {flow_candidates}
Selected: {len(symbols)}

━━━━━━━━━━━━━━━━━━━━━━

❌ REJECTIONS
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
Final Gate: {debug.get('final_gate', 0)}
Not Long/Short: {debug.get('not_long', 0)}

━━━━━━━━━━━━━━━━━━━━━━

✅ RESULTS
Passed: {debug.get('passed', 0)}
LONG Signals: {len(long_results)}
SHORT Signals: {len(short_results)}

━━━━━━━━━━━━━━━━━━━━━━

📊 METRICS
Avg Final Score: {debug.get('avg_score', 'N/A')}
Avg Flow: {debug.get('avg_flow', 0)}
Avg Momentum: {debug.get('avg_momentum', 'N/A')}
Avg RR: {debug.get('avg_rr', 'N/A')}
Avg Brain: {debug.get('avg_brain', 0)}

━━━━━━━━━━━━━━━━━━━━━━

📈 MARKET REGIME DISTRIBUTION
{debug.get('regime_distribution', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━

🔥 COMPRESSION DISTRIBUTION
{debug.get('compression_distribution', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━

Top Reject Reasons:
{top_rejects}

━━━━━━━━━━━━━━━━━━━━━━

⚡ SCAN EFFICIENCY
Scan Time      : {scan_duration}s
API Calls      : {api_calls}
Cache Hits     : {cache_hits}
Cache Saved    : {cache_saved_pct}%
"""
    bot.send_message(message.chat.id, debug_msg)
        # ==========================================================
    # 🏆 PROFESSIONAL SIGNAL RANKING
    # ==========================================================

    def ranking_score(signal):
        """
        Professional Ranking Engine

        لا يغير قبول أو رفض الإشارة.
        يستخدم فقط لترتيب الإشارات المقبولة.
        """

        score = signal["score"]
        brain = signal.get("brain_confidence", 0)
        rr = signal.get("rr", 0)
        flow = signal.get("liquidity", 0)
        momentum = signal.get("momentum_score", 0)

        total = (
            score * 0.40 +
            brain * 0.25 +
            rr * 10 +
            flow * 8 +
            momentum * 0.05
        )

        return round(total, 2)

    # ترتيب جميع إشارات LONG
    best_longs = sorted(
        long_results,
        key=ranking_score,
        reverse=True
    )[:2]

    # ترتيب جميع إشارات SHORT
    best_shorts = sorted(
        short_results,
        key=ranking_score,
        reverse=True
    )[:1]

    # دمج النتائج
    results = best_longs + best_shorts

    # إضافة ترتيب لكل إشارة
    for rank, signal in enumerate(results, start=1):
        signal["rank"] = rank
        signal["ranking_score"] = ranking_score(signal)

    # ==========================================================

    if not results:
        bot.send_message(message.chat.id, """
👀 No sniper setup now

🐋 Smart Money not ready
⏳ Waiting next liquidity wave
""")
        # ====== CLEAR CACHE AFTER SCAN ======
        _candle_cache.clear()
        # ====================================
        return

    # ====== FORMAT PRICE FUNCTION ======
    def format_price(value):
        """Format price without scientific notation"""
        if value is None:
            return "N/A"
        if value < 0.00001:
            return f"{value:.8f}"
        elif value < 0.0001:
            return f"{value:.7f}"
        elif value < 0.001:
            return f"{value:.6f}"
        elif value < 0.01:
            return f"{value:.5f}"
        elif value < 0.1:
            return f"{value:.4f}"
        elif value < 1:
            return f"{value:.4f}"
        elif value < 10:
            return f"{value:.3f}"
        else:
            return f"{value:.2f}"

    for s in results:
        # ====== AI BRAIN CONFIDENCE RANK ======
        brain_conf = s["brain_confidence"]

        if brain_conf >= 80:
            confidence_rank = "🔥 VERY HIGH"
        elif brain_conf >= 60:
            confidence_rank = "✅ HIGH"
        elif brain_conf >= 40:
            confidence_rank = "⚡ MEDIUM"
        else:
            confidence_rank = "⚠ LOW"

        # ====== DIRECTION ICON ======
        direction_icon = "📈" if s['direction'] == "🟢 LONG" else "📉"

        # ====== FORMAT PRICES ======
        entry_low_f = format_price(s['entry_low'])
        entry_high_f = format_price(s['entry_high'])
        sl_f = format_price(s['sl'])
        tp1_f = format_price(s['tp1'])
        tp2_f = format_price(s['tp2'])
        tp3_f = format_price(s['tp3'])

        # ====== BUILD TELEGRAM MESSAGE ======
        msg = f"""
🚨 AHAD AI v21.1.7 – Production Analytics 🐋

🏆 Rank #{s['rank']}
⭐ Ranking Score: {s['ranking_score']}

{direction_icon} {s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

━━━━━━━━━━━━━━━━━━━━━━

💰 Entry      : {entry_low_f} - {entry_high_f}
🛑 SL         : {sl_f}

🎯 TP1        : {tp1_f}
🥈 TP2        : {tp2_f}
🥉 TP3        : {tp3_f}

━━━━━━━━━━━━━━━━━━━━━━

🏦 INSTITUTIONAL DASHBOARD

├─ AI Brain    : {brain_conf}/100 ({confidence_rank})
├─ Smart Money : {s['money_status']}
├─ Flow Rating : {s['flow_rating']}
├─ Final Score : {s['score']}/100
├─ Risk Grade  : {s['risk_grade']}
├─ Quality     : {s['quality']}
├─ Market      : {s['regime']['regime']}
├─ Compression : {s['volatility']['status']}
└─ RR          : {s['rr']}

━━━━━━━━━━━━━━━━━━━━━━

📊 RSI

15m : {s['multi']['15m']}
1H  : {s['multi']['1h']}
4H  : {s['multi']['4h']}
1D  : {s['multi']['1d']}

━━━━━━━━━━━━━━━━━━━━━━

⚠️ {s['warning']}
{s['early_text']}

━━━━━━━━━━━━━━━━━━━━━━

✅ WHY THIS SIGNAL?

{s['decision_summary']}

━━━━━━━━━━━━━━━━━━━━━━

💾 Trade ID: #{trade_id if 'trade_id' in locals() else 'PENDING'}
"""

        # ====== SAVE TRADE TO DATABASE ======
        trade_id = None
        if s.get('trade_data'):
            try:
                trade_id = save_trade(s['trade_data'])
                if trade_id:
                    # Update message with actual Trade ID
                    msg = msg.replace('#PENDING', f'#{trade_id}')
                    print(f"✅ Trade #{trade_id} saved for {s['coin']}")
                else:
                    msg = msg.replace('#PENDING', '❌ FAILED')
                    msg += "\n\n❌ Failed to save trade"
            except Exception as e:
                print(f"❌ Exception saving trade: {e}")
                msg = msg.replace('#PENDING', '❌ ERROR')
                msg += "\n\n❌ Database error saving trade"
        # ==================================

        bot.send_message(message.chat.id, msg)

    # ====== CLEAR CACHE AFTER SCAN ======
    _candle_cache.clear()
    # ====================================


# ================================================
# 📊 PERFORMANCE COMMANDS
# ================================================

@bot.message_handler(commands=['report'])
def report_command(message):
    """Performance statistics with LONG/SHORT breakdown"""
    try:
        stats = get_report_stats()

        report = f"""
📊 AHAD AI PERFORMANCE REPORT
━━━━━━━━━━━━━━━━━━━━━━

📂 Total Trades   : {stats['total']}
🟢 Open Trades   : {stats['open']}
🔒 Closed Trades : {stats['closed']}

━━━━━━━━━━━━━━━━━━━━━━

📈 WIN / LOSS BREAKDOWN
🏆 TP1 : {stats['tp1']}
🥈 TP2 : {stats['tp2']}
🥉 TP3 : {stats['tp3']}
❌ SL  : {stats['sl']}

🎯 Overall Win Rate : {stats['win_rate']}%
📊 Avg RR           : {stats['avg_rr']}
📊 Avg Result %     : {stats['avg_result_pct']}%
⏱️ Avg Duration     : {int(stats['avg_duration']//60)}m {int(stats['avg_duration']%60)}s

━━━━━━━━━━━━━━━━━━━━━━

🟢 LONG PERFORMANCE
Trades        : {stats['long_total']}
Wins          : {stats['long_wins']}
Losses        : {stats['long_losses']}
Win Rate      : {stats['long_win_rate']}%
Avg RR        : {stats['long_avg_rr']}
Avg Result %  : {stats['long_avg_result_pct']}%
⏱️ Avg Duration : {int(stats['long_avg_duration']//60)}m {int(stats['long_avg_duration']%60)}s

━━━━━━━━━━━━━━━━━━━━━━

🔴 SHORT PERFORMANCE
Trades        : {stats['short_total']}
Wins          : {stats['short_wins']}
Losses        : {stats['short_losses']}
Win Rate      : {stats['short_win_rate']}%
Avg RR        : {stats['short_avg_rr']}
Avg Result %  : {stats['short_avg_result_pct']}%
⏱️ Avg Duration : {int(stats['short_avg_duration']//60)}m {int(stats['short_avg_duration']%60)}s

━━━━━━━━━━━━━━━━━━━━━━
🤖 AHAD AI v21.1.7
🗄 PostgreSQL | 🔒 SSL
📊 Production Analytics
"""
        bot.reply_to(message, report)

    except Exception as e:
        bot.reply_to(message, f"❌ Error generating report: {e}")


@bot.message_handler(commands=['open'])
def open_trades_command(message):
    """Show open trades"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT id, symbol, side, entry, tp1, tp2, tp3, sl, signal_time
        FROM trades
        WHERE status = 'OPEN'
        ORDER BY id DESC
        """)

        rows = cur.fetchall()

        if not rows:
            bot.reply_to(message, "📭 No open trades.")
            return

        msg = "📂 OPEN TRADES\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for row in rows[:10]:
            # Format time without microseconds
            signal_time = row[8].strftime("%Y-%m-%d %H:%M") if row[8] else "N/A"
            msg += f"#{row[0]} {row[1]} | {row[2]}\n"
            msg += f"Entry: {row[3]} | SL: {row[7]}\n"
            msg += f"TP1: {row[4]} | TP2: {row[5]} | TP3: {row[6]}\n"
            msg += f"🕐 {signal_time}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        bot.reply_to(message, msg)

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@bot.message_handler(commands=['history'])
def history_command(message):
    """Show last 10 closed trades with improved UI"""
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT id, symbol, side, entry, result, max_profit, max_drawdown, close_time, result_pct, trade_duration
        FROM trades
        WHERE status = 'CLOSED'
        ORDER BY id DESC
        LIMIT 10
        """)

        rows = cur.fetchall()

        if not rows:
            bot.reply_to(message, "📭 No closed trades yet.")
            return

        msg = "📜 TRADE HISTORY (Last 10)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        # Result mapping
        result_map = {
            "WIN_TP1": "🥇 TP1 Hit",
            "WIN_TP2": "🥈 TP2 Hit",
            "WIN_TP3": "🥉 TP3 Hit",
            "LOSS_SL": "❌ SL Hit"
        }

        for row in rows:
            result_display = result_map.get(row[4], row[4])
            close_time = row[7].strftime("%Y-%m-%d %H:%M") if row[7] else "N/A"
            result_pct = f"{row[8]:.2f}%" if row[8] is not None else "N/A"
            duration = f"{row[9]//60}m {row[9]%60}s" if row[9] else "N/A"
            
            msg += f"#{row[0]} {row[1]} | {row[2]}\n"
            msg += f"Entry: {row[3]} | Result: {result_display}\n"
            msg += f"Profit: {result_pct} | Duration: {duration}\n"
            msg += f"Max Profit: {row[5]:.2f}% | Max DD: {row[6]:.2f}%\n"
            msg += f"🕐 {close_time}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        bot.reply_to(message, msg)

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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
threading.Thread(target=update_open_trades, daemon=True).start()

print("🔥 AHAD AI v21.1.7 – Production Analytics ONLINE 🐋")
print(f"📅 Started at: {time.ctime()}")
print(f"🐍 Python Version: {os.sys.version}")
print(f"⚙️ MIN_FLOW_COINS: {MIN_FLOW_COINS}")
print(f"⚙️ MAX_FLOW_COINS: {MAX_FLOW_COINS}")
print(f"⚙️ FLOW_RATIO: {FLOW_RATIO}")
print("🛡️ Validation Layer ACTIVE")
print("🗑️ Cache cleared on each scan")
print("🧹 Cache TTL Cleanup ACTIVE (600s)")
print("🧠 Brain v2.0 ACTIVE")
print("🎯 Dynamic Late Entry v3 ACTIVE (Symmetric)")
print("🐞 Debug Reason ACTIVE")
print("🗄️ PostgreSQL Database ACTIVE (v21.1.7)")
print("📊 Indexes: status, result, signal_time, symbol, status_symbol, market_regime, brain_confidence")
print("🔒 SSL Connection: ENABLED")
print("⏰ TIMESTAMP Support ACTIVE")
print("🔄 Duplicate Trade Protection ACTIVE")
print("📈 Trade Tracker ACTIVE (HIGH/LOW Accuracy)")
print("📊 Performance Analytics ACTIVE (LONG/SHORT Breakdown)")
print("📊 Market Regime Engine ACTIVE (Fixed EMA100)")
print("🔥 Volatility Compression Integration ACTIVE")
print("🚀 Dynamic Momentum Weight ACTIVE")
print("🎯 Dynamic RR Engine ACTIVE")
print("🔄 Dual Direction Engine ACTIVE (Fully Symmetric)")
print("📊 Trade Data Expansion ACTIVE (Extended)")
print("🏆 Professional Ranking Engine ACTIVE")
print("💎 Professional Quality Engine v2.0 ACTIVE")
print("📊 Institutional Flow Rating ACTIVE")
print("🛡️ Risk Grade System ACTIVE")
print("🧠 AI Decision Summary ACTIVE (Complete)")
print("🐘 Market Health Report ACTIVE")
print("🏦 Institutional Dashboard ACTIVE")
print("🐞 Enhanced Debug Report with Top Reject Reasons")
print("📦 Caching System ACTIVE (TTL=600s)")
print("⚡ Scan Efficiency Tracking ACTIVE")
print("🌡️ Market Temperature ACTIVE")
print("🏦 Sector Summary ACTIVE")
print("📊 Extended Data Collection ACTIVE")
print("📈 Result % & Duration Tracking ACTIVE")
print("📋 Commands: /scan | /report | /open | /history")
print("🎯 Best 2 LONG + Best 1 SHORT")
print("✅ SYSTEM READY FOR PRODUCTION")
print("🚀 Production Analytics v21.1.7")

while True:
    time.sleep(60)
    
