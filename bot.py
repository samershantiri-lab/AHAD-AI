# ================================================
# 🚀 AHAD AI v21.3 – PRODUCTION STABLE
# ================================================

# ================================================
# ⚙️ CONFIGURATION
# ================================================

# ---------- FLOW SCANNER ----------
MIN_FLOW_COINS = 50
MAX_FLOW_COINS = 150
FLOW_RATIO = 0.40
MAX_SCAN_LIMIT = 200

# ---------- CACHING ----------
CACHE_TTL = 60

# ---------- SCORING ----------
MIN_SCORE = 68
MIN_RR = 1.8

# ---------- TRADE TRACKER ----------
TRACKER_BACKOFF_INITIAL = 60
TRACKER_BACKOFF_MAX = 600

# ---------- DEBUG ----------
DEBUG_MODE = True

# ================================================
# 📋 BUILD INFORMATION
# ================================================

VERSION = "v21.3"
BUILD_DATE = "2026-07-26"

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
from contextlib import contextmanager
from datetime import datetime
from collections import defaultdict
import random
from functools import wraps

from flask import Flask
import telebot

# ================================================
# 🔑 TELEGRAM TOKEN VALIDATION
# ================================================

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN or not TOKEN.strip():
    raise Exception("❌ BOT_TOKEN is required and cannot be empty")

TOKEN = TOKEN.strip()
bot = telebot.TeleBot(TOKEN)

# ================================================
# 👥 ALLOWED CHAT IDS
# ================================================

_allowed_chat_ids_raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
if not _allowed_chat_ids_raw.strip():
    raise Exception("❌ TELEGRAM_ALLOWED_CHAT_IDS is required")

try:
    ALLOWED_CHAT_IDS = {
        int(chat_id.strip())
        for chat_id in _allowed_chat_ids_raw.split(",")
        if chat_id.strip()
    }
except ValueError as exc:
    raise Exception(
        "❌ TELEGRAM_ALLOWED_CHAT_IDS must contain comma-separated numeric chat IDs"
    ) from exc

if not ALLOWED_CHAT_IDS:
    raise Exception("❌ TELEGRAM_ALLOWED_CHAT_IDS must contain at least one valid chat ID")

# ================================================
# 🛡️ AUTHENTICATION DECORATOR
# ================================================

def authorized_only(handler):
    """Reject Telegram commands from chats outside the production allow-list."""
    @wraps(handler)
    def wrapper(message, *args, **kwargs):
        chat_id = message.chat.id
        if chat_id not in ALLOWED_CHAT_IDS:
            bot.reply_to(message, f"⛔ Unauthorized access. Your chat ID: {chat_id}")
            return None
        return handler(message, *args, **kwargs)
    return wrapper

# ================================================
# 🗄 POSTGRESQL DATABASE CONNECTION
# ================================================

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.strip():
    raise Exception("❌ DATABASE_URL is required and cannot be empty")

DATABASE_URL = DATABASE_URL.strip()


@contextmanager
def get_db_connection():
    """
    Context manager for PostgreSQL connections.
    Ensures proper cleanup even if an exception occurs.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            connect_timeout=10,
            sslmode='require'
        )
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


@contextmanager
def get_db_cursor(commit=True):
    """
    Context manager for database cursors.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

# ================================================
# 🗄 DATABASE INITIALIZATION
# ================================================

def init_database():
    """Initialize PostgreSQL database with tables and indexes"""
    print("🔄 Initializing database...")
    
    with get_db_cursor(commit=True) as cur:
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
            close_time TIMESTAMP
        )
        """)

        # ================================================
        # 🔄 DATABASE MIGRATION (v21.2.5)
        # ================================================

        # Add new columns if they don't exist
        new_columns = [
            ("brain_confidence", "INTEGER"),
            ("market_regime", "TEXT"),
            ("compression_score", "INTEGER"),
            ("compression_status", "TEXT"),
            ("momentum_weight", "DOUBLE PRECISION"),
            ("flow_score", "INTEGER"),
            ("volume_acceleration", "DOUBLE PRECISION"),
            ("flow_rating", "TEXT"),
            ("risk_grade", "TEXT"),
            ("decision_summary", "TEXT"),
            ("ranking_score", "DOUBLE PRECISION"),
            ("quality_grade", "TEXT"),
            ("market_temperature", "TEXT")
        ]

        for col_name, col_type in new_columns:
            try:
                cur.execute(f"ALTER TABLE trades ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception as e:
                print(f"⚠️ Could not add column {col_name}: {e}")

        # ================================================
        # 📊 INDEXES FOR PERFORMANCE
        # ================================================

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)",
            "CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(result)",
            "CREATE INDEX IF NOT EXISTS idx_trades_signal_time ON trades(signal_time)",
            "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_trades_status_symbol ON trades(status, symbol)",
            "CREATE INDEX IF NOT EXISTS idx_trades_market_regime ON trades(market_regime)",
            "CREATE INDEX IF NOT EXISTS idx_trades_brain_confidence ON trades(brain_confidence)",
            "CREATE INDEX IF NOT EXISTS idx_trades_quality_grade ON trades(quality_grade)"
        ]

        for idx_sql in indexes:
            try:
                cur.execute(idx_sql)
            except Exception as e:
                print(f"⚠️ Could not create index: {e}")

    print("🟢 PostgreSQL Connected & Initialized")
    print(f"🗄 AHAD AI DATABASE READY ({VERSION})")
    print("📊 Indexes: status, result, signal_time, symbol, status_symbol, market_regime, brain_confidence, quality_grade")
    print("✅ Database migration checked")

# ================================================
# 📊 UTILITY FUNCTIONS
# ================================================

def format_price(value):
    """Format price consistently with 6 decimal places"""
    if value is None:
        return "N/A"
    return f"{value:.6f}"

def get_total_trades():
    """Get total number of trades in database"""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT COUNT(*) FROM trades")
            count = cur.fetchone()[0]
            return count
    except Exception as e:
        if DEBUG_MODE:
            print(f"❌ Error getting total trades: {e}")
        return 0

# ================================================
# 💾 TRADE RECORDER
# ================================================

def save_trade(trade_data):
    """Save trade to PostgreSQL database with duplicate check and enhanced fields"""
    with get_db_cursor(commit=True) as cur:
        # Serialize same-symbol/same-side inserts across all bot processes.
        duplicate_key = f"{trade_data['symbol']}:{trade_data['side']}"
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (duplicate_key,))
        
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

        # ====== INSERT NEW TRADE ======
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
            ranking_score,
            quality_grade,
            market_temperature
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
            trade_data.get('version', VERSION),
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
            trade_data.get('ranking_score', 0.0),
            trade_data.get('quality_grade', 'N/A'),
            trade_data.get('market_temperature', 'N/A')
        ))

        trade_id = cur.fetchone()[0]
        print(f"💾 Trade saved: {trade_data['symbol']} (ID: {trade_id})")
        return trade_id

# ================================================
# 📈 OPEN TRADES MANAGEMENT
# ================================================

def get_open_trades():
    """Get all open trades from PostgreSQL"""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
            SELECT id, symbol, side, entry, sl, tp1, tp2, tp3,
                   max_profit, max_drawdown
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
                    'max_drawdown': row[9] if row[9] is not None else 0.0
                })
            
            if DEBUG_MODE:
                print(f"📂 OPEN trades loaded: {len(trades)}")
            return trades
    except Exception as e:
        print(f"❌ Error getting open trades: {e}")
        return []


def update_trade(trade_id, status, result, max_profit, max_drawdown, close_time=None):
    """Update trade data in PostgreSQL"""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
            UPDATE trades
            SET status = %s,
                result = %s,
                max_profit = %s,
                max_drawdown = %s,
                close_time = %s
            WHERE id = %s
            """, (
                status,
                result,
                max_profit,
                max_drawdown,
                close_time or datetime.now(),
                trade_id
            ))
            print(f"✅ Trade {trade_id} updated: {status} | {result}")
            return True
    except Exception as e:
        print(f"❌ Error updating trade {trade_id}: {e}")
        return False

# ================================================
# 📊 PERFORMANCE ANALYTICS
# ================================================

def get_report_stats():
    """Get AHAD AI performance statistics with enhanced fields"""
    try:
        with get_db_cursor(commit=False) as cur:
            # ====== MAIN STATS ======
            cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN status = 'OPEN' THEN 1 END) AS open_trades,
                COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) AS closed,
                COUNT(CASE WHEN result = 'WIN_TP1' THEN 1 END) AS tp1,
                COUNT(CASE WHEN result = 'WIN_TP2' THEN 1 END) AS tp2,
                COUNT(CASE WHEN result = 'WIN_TP3' THEN 1 END) AS tp3,
                COUNT(CASE WHEN result = 'LOSS_SL' THEN 1 END) AS sl,
                AVG(CASE WHEN status = 'CLOSED' THEN rr END) AS avg_rr,
                AVG(CASE WHEN status = 'CLOSED' THEN max_profit END) AS avg_max_profit,
                AVG(CASE WHEN status = 'CLOSED' THEN max_drawdown END) AS avg_max_drawdown,
                MAX(CASE WHEN status = 'CLOSED' THEN max_profit END) AS best_trade,
                MIN(CASE WHEN status = 'CLOSED' THEN max_drawdown END) AS worst_trade
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
            avg_max_profit = round(row[8] or 0, 2)
            avg_max_drawdown = round(row[9] or 0, 2)
            best_trade = round(row[10] or 0, 2)
            worst_trade = round(row[11] or 0, 2)

            wins = tp1 + tp2 + tp3
            win_rate = round((wins / closed) * 100, 2) if closed > 0 else 0

            # ====== LONG STATS ======
            cur.execute("""
            SELECT
                COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) AS total,
                COUNT(CASE WHEN status = 'CLOSED' AND result IN ('WIN_TP1', 'WIN_TP2', 'WIN_TP3') THEN 1 END) AS wins,
                COUNT(CASE WHEN status = 'CLOSED' AND result = 'LOSS_SL' THEN 1 END) AS losses,
                AVG(rr) AS avg_rr,
                AVG(max_profit) AS avg_max_profit,
                AVG(max_drawdown) AS avg_max_drawdown
            FROM trades
            WHERE side = 'LONG'
            """)
            
            long_row = cur.fetchone()
            long_total = long_row[0] or 0
            long_wins = long_row[1] or 0
            long_losses = long_row[2] or 0
            long_avg_rr = round(long_row[3] or 0, 2)
            long_avg_profit = round(long_row[4] or 0, 2)
            long_avg_dd = round(long_row[5] or 0, 2)
            long_closed = long_wins + long_losses
            long_win_rate = round((long_wins / long_closed) * 100, 2) if long_closed > 0 else 0

            # ====== SHORT STATS ======
            cur.execute("""
            SELECT
                COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) AS total,
                COUNT(CASE WHEN status = 'CLOSED' AND result IN ('WIN_TP1', 'WIN_TP2', 'WIN_TP3') THEN 1 END) AS wins,
                COUNT(CASE WHEN status = 'CLOSED' AND result = 'LOSS_SL' THEN 1 END) AS losses,
                AVG(rr) AS avg_rr,
                AVG(max_profit) AS avg_max_profit,
                AVG(max_drawdown) AS avg_max_drawdown
            FROM trades
            WHERE side = 'SHORT'
            """)
            
            short_row = cur.fetchone()
            short_total = short_row[0] or 0
            short_wins = short_row[1] or 0
            short_losses = short_row[2] or 0
            short_avg_rr = round(short_row[3] or 0, 2)
            short_avg_profit = round(short_row[4] or 0, 2)
            short_avg_dd = round(short_row[5] or 0, 2)
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
                "avg_max_profit": avg_max_profit,
                "avg_max_drawdown": avg_max_drawdown,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
                "long_total": long_total,
                "long_wins": long_wins,
                "long_losses": long_losses,
                "long_win_rate": long_win_rate,
                "long_avg_rr": long_avg_rr,
                "long_avg_profit": long_avg_profit,
                "long_avg_dd": long_avg_dd,
                "short_total": short_total,
                "short_wins": short_wins,
                "short_losses": short_losses,
                "short_win_rate": short_win_rate,
                "short_avg_rr": short_avg_rr,
                "short_avg_profit": short_avg_profit,
                "short_avg_dd": short_avg_dd
            }

    except Exception as e:
        print(f"❌ Report Error: {e}")
        return {
            "total": 0, "open": 0, "closed": 0,
            "tp1": 0, "tp2": 0, "tp3": 0, "sl": 0,
            "wins": 0, "win_rate": 0,
            "avg_rr": 0, "avg_max_profit": 0, "avg_max_drawdown": 0,
            "best_trade": 0, "worst_trade": 0,
            "long_total": 0, "long_wins": 0, "long_losses": 0,
            "long_win_rate": 0, "long_avg_rr": 0, "long_avg_profit": 0, "long_avg_dd": 0,
            "short_total": 0, "short_wins": 0, "short_losses": 0,
            "short_win_rate": 0, "short_avg_rr": 0, "short_avg_profit": 0, "short_avg_dd": 0
        }

# ================================================
# 🌐 RENDER KEEP ALIVE SERVER
# ================================================

app = Flask(__name__)

@app.route("/")
def home():
    return f"🐋 AHAD AI {VERSION} – Production Stable ONLINE 🚀"

@app.route("/health")
def health():
    """Health check endpoint for monitoring"""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return "✅ HEALTHY", 200
    except Exception as e:
        return f"❌ UNHEALTHY: {e}", 500

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
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("code") not in (None, "0"):
            raise RuntimeError(f"OKX instruments error: {data.get('msg', data.get('code'))}")

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

        if DEBUG_MODE:
            print(f"🐋 MARKETS FOUND: {len(result)}")
        return result

    except Exception as e:
        print("SYMBOL ERROR:", e)
        return []

init_database()
print(f"🔥 AHAD AI {VERSION} – Production Stable CORE READY 🐋")

# ================================================
# 📊 SECTION 2: OKX DATA + INDICATORS
# ================================================

# ================================================
# 🕯 OKX CANDLES ENGINE
# ================================================

_candle_cache = {}
_cache_timestamps = {}


def get_candles(symbol, tf):
    """
    Fetch candles from OKX API.
    
    Args:
        symbol (str): Trading pair symbol (e.g., "BTC-USDT-SWAP")
        tf (str): Timeframe (15m, 1h, 4h, 1d)
    
    Returns:
        list: List of candle dictionaries with keys:
              open, high, low, close, volume, confirmed
    """
    try:
        frames = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": symbol, "bar": frames.get(tf, "15m"), "limit": 200}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") not in (None, "0"):
            raise RuntimeError(f"OKX candles error: {data.get('msg', data.get('code'))}")

        if not data or "data" not in data or not data["data"]:
            return []

        candles = []
        for c in data["data"][::-1]:  # Reverse to get chronological order
            candles.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "confirmed": len(c) > 8 and c[8] == "1"
            })

        return candles

    except requests.exceptions.Timeout:
        print(f"⏰ Timeout fetching candles for {symbol}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"🌐 Network error for {symbol}: {e}")
        return []
    except Exception as e:
        print(f"❌ CANDLE ERROR: {symbol} - {e}")
        return []


def get_candles_cached(symbol, tf):
    """Get candles with TTL-based cache"""
    key = f"{symbol}_{tf}"
    now = time.time()
    
    if key in _candle_cache and key in _cache_timestamps:
        if now - _cache_timestamps[key] <= CACHE_TTL:
            return _candle_cache[key]
    
    candles = get_candles(symbol, tf)
    _candle_cache[key] = candles
    _cache_timestamps[key] = now
    return candles


def clear_expired_cache():
    """Clear only expired cache entries"""
    now = time.time()
    expired_keys = [k for k, t in _cache_timestamps.items() if now - t > CACHE_TTL]
    for key in expired_keys:
        _candle_cache.pop(key, None)
        _cache_timestamps.pop(key, None)
    if expired_keys and DEBUG_MODE:
        print(f"🗑️ Cleared {len(expired_keys)} expired cache entries")


# ================================================
# 🐋 TOP FLOW SCANNER
# ================================================

def top_flow_scanner(symbols):
    """
    Scan symbols for high volume flow.
    Returns top flow coins based on volume ratio.
    """
    results = []
    processed = 0
    
    for symbol in symbols:
        if processed >= MAX_SCAN_LIMIT:
            break
        processed += 1
            
        try:
            c15 = get_candles(symbol, "15m")
            if len(c15) < 50:
                continue

            volumes = [x["volume"] for x in c15]
            closes = [x["close"] for x in c15]

            # Calculate recent volume (last 5 candles)
            vol_now = sum(volumes[-5:])
            
            # Calculate average volume (last 40 candles)
            vol_avg = sum(volumes[-40:]) / 40

            if vol_avg == 0:
                continue

            # Flow ratio: compare actual volume to expected volume
            # Expected = average * 5 (for 5 candles)
            flow = vol_now / (vol_avg * 5)
            
            # Check price movement to avoid coins that already pumped
            move = ((closes[-1] - closes[-20]) / closes[-20]) * 100

            if move > 10:  # Skip coins that already pumped > 10%
                continue

            if flow >= 1.15:  # Minimum flow threshold
                results.append({"coin": symbol, "flow": flow})

        except Exception as e:
            if DEBUG_MODE:
                print(f"⚠️ Flow scan error for {symbol}: {e}")
            continue

        # Small delay to avoid rate limiting
        time.sleep(0.01)

    if len(results) == 0:
        return [], 0

    flow_candidates = len(results)
    
    # Sort by flow (highest first)
    results.sort(key=lambda x: x["flow"], reverse=True)

    # Dynamic threshold based on best flow
    best_flow = results[0]["flow"]
    dynamic_threshold = best_flow * FLOW_RATIO

    selected = []
    for coin_data in results:
        if len(selected) >= MAX_FLOW_COINS:
            break
        if coin_data["flow"] >= dynamic_threshold:
            selected.append(coin_data["coin"])

    # Ensure minimum number of coins
    if len(selected) < MIN_FLOW_COINS:
        selected = [x["coin"] for x in results[:MIN_FLOW_COINS]]

    return selected, flow_candidates


# ================================================
# 📊 INDICATORS ENGINE
# ================================================

def ema(values, period):
    """
    Calculate Exponential Moving Average.
    
    Args:
        values (list): List of price values
        period (int): EMA period
    
    Returns:
        float: EMA value
    """
    if not values:
        return 0
    
    if len(values) < period:
        return values[-1]

    k = 2 / (period + 1)
    result = values[0]

    for v in values:
        result = v * k + result * (1 - k)

    return result


def rsi(values, period=14):
    """
    Calculate Relative Strength Index.
    
    Args:
        values (list): List of price values
        period (int): RSI period (default: 14)
    
    Returns:
        float: RSI value (0-100)
    """
    if len(values) < period + 1:
        return 50  # Neutral value when insufficient data
    
    gains = 0
    losses = 0

    for i in range(-period, 0):
        diff = values[i + 1] - values[i]
        if diff > 0:
            gains += diff
        else:
            losses -= diff

    if losses == 0:
        return 100

    rs = gains / losses
    return 100 - (100 / (1 + rs))


def atr(candles, period=14):
    """
    Calculate Average True Range.
    
    Args:
        candles (list): List of candle dictionaries
        period (int): ATR period (default: 14)
    
    Returns:
        float: ATR value
    """
    if len(candles) < period:
        return 0
    
    ranges = []
    for c in candles[-period:]:
        ranges.append(c["high"] - c["low"])
    
    return sum(ranges) / len(ranges)


def macd_simple(closes, fast=12, slow=26, signal=9):
    """
    Calculate simplified MACD (just the MACD line).
    
    Args:
        closes (list): List of closing prices
        fast (int): Fast EMA period
        slow (int): Slow EMA period
        signal (int): Signal period (not used in simplified version)
    
    Returns:
        float: MACD value
    """
    if len(closes) < slow:
        return 0
    
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    return ema_fast - ema_slow


# ================================================
# 🏦 SECTOR FLOW ENGINE
# ================================================

def sector_flow(symbols):
    """
    Calculate flow power for each sector based on volume.
    
    Args:
        symbols (list): List of trading symbols
    
    Returns:
        dict: Sector flow analysis with ranking
    """
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
                            total += recent / (average * 5)
                            matched += 1

            power = round(total / matched, 2) if matched > 0 else 0

            result[sector] = power
            ranking.append((sector, power))

        ranking = sorted(ranking, key=lambda x: x[1], reverse=True)

        return {
            "sector": ranking[0][0] if ranking else "UNKNOWN",
            "power": ranking[0][1] if ranking else 0,
            "ranking": ranking[:3]
        }

    except Exception as e:
        print(f"❌ SECTOR ERROR: {e}")
        return {
            "sector": "UNKNOWN",
            "power": 0,
            "ranking": []
        }


# ================================================
# 🐋 SMART MONEY ENGINE
# ================================================

def smart_money(candles):
    """
    Detect smart money activity based on volume and price action.
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Flow analysis with status
    """
    try:
        if len(candles) < 50:
            return {"flow": 0, "status": "INSUFFICIENT_DATA", "volume_acceleration": 0}

        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            flow = 0
        else:
            flow = volume_now / (volume_avg * 5)

        # Volume acceleration (comparing last 5 to last 20 candles)
        volume_avg_20 = sum(volumes[-20:]) / 4
        volume_acceleration = volume_now / volume_avg_20 if volume_avg_20 > 0 else 0

        # Price movement over last 24 candles (6 hours for 15m)
        move = ((closes[-1] - closes[-24]) / closes[-24]) * 100 if len(closes) >= 24 else 0

        # Determine smart money status
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
        print(f"❌ SMART MONEY ERROR: {e}")
        return {"flow": 0, "status": "ERROR", "volume_acceleration": 0}


# ================================================
# 🐋 PRE PUMP ENGINE
# ================================================

def pre_pump_engine(candles):
    """
    Detect pre-pump accumulation patterns.
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Pre-pump status and score
    """
    try:
        if len(candles) < 50:
            return {"status": "INSUFFICIENT_DATA", "score": 0}

        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        price = closes[-1]
        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            return {"status": "NORMAL", "score": 0}

        flow = volume_now / (volume_avg * 5)
        move = ((price - closes[-30]) / closes[-30]) * 100 if len(closes) >= 30 else 0
        current_rsi = rsi(closes)

        # Whale loading pattern: high flow, minimal price movement, neutral RSI
        if (
            flow >= 1.20
            and abs(move) < 4
            and 40 <= current_rsi <= 60
        ):
            return {"status": "🐋 WHALE LOADING", "score": 25}

        return {"status": "NORMAL", "score": 0}

    except Exception as e:
        print(f"❌ PRE PUMP ERROR: {e}")
        return {"status": "ERROR", "score": 0}


# ================================================
# 🔥 VOLATILITY COMPRESSION ENGINE
# ================================================

def volatility_engine(candles):
    """
    Calculate volatility compression score.
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Compression score, status, and metrics
    """
    try:
        if len(candles) < 60:
            return {
                "score": 0,
                "status": "INSUFFICIENT_DATA",
                "range": 0,
                "atr_now": 0,
                "atr_old": 0,
                "bonus": 0
            }

        # Recent 20 candles
        recent = candles[-20:]

        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        # Price range
        price_range = max(highs) - min(lows)

        # Current and historical ATR
        atr_now = atr(candles[-14:])
        atr_old = atr(candles[-60:-46])

        if atr_old == 0:
            compression = 0
        else:
            compression = (1 - (atr_now / atr_old)) * 100

        compression = max(0, min(100, compression))

        # Determine status and bonus
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
        print(f"❌ VOLATILITY ERROR: {e}")
        return {
            "score": 0,
            "status": "ERROR",
            "range": 0,
            "atr_now": 0,
            "atr_old": 0,
            "bonus": 0
        }


# ================================================
# 📊 MARKET REGIME ENGINE
# ================================================

def market_regime(candles, compression_score):
    """
    Classify market into TRENDING, RANGING, or COMPRESSION.
    
    Args:
        candles (list): List of candle dictionaries
        compression_score (int): Compression score from volatility_engine
    
    Returns:
        dict: Market regime classification
    """
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

        atr_val = atr(candles[-14:])
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema100 = ema(closes, 100)

        # Calculate expansion ratio
        price_range = max(highs) - min(lows)
        avg_price = sum(closes) / len(closes)
        expansion_ratio = price_range / avg_price if avg_price > 0 else 0

        # EMA alignment
        ema_alignment = 0
        if ema20 > ema50 > ema100:
            ema_alignment = 1  # Bullish alignment
        elif ema20 < ema50 < ema100:
            ema_alignment = -1  # Bearish alignment
        else:
            ema_alignment = 0  # Mixed

        # Calculate slope
        if len(closes) >= 10:
            slope20 = (ema20 - ema(closes[:-10], 20)) / ema20 if ema20 > 0 else 0
            slope50 = (ema50 - ema(closes[:-10], 50)) / ema50 if ema50 > 0 else 0
            avg_slope = (abs(slope20) + abs(slope50)) / 2
        else:
            avg_slope = 0

        # Classify regime
        if compression_score >= 50 and expansion_ratio < 0.06:
            regime = "COMPRESSION"
            strength = compression_score
            confidence = 70 + (compression_score / 100) * 20
            description = "Market compressing - breakout imminent"
        elif expansion_ratio > 0.08 and avg_slope > 0.015:
            regime = "TRENDING"
            strength = min(100, avg_slope * 800)
            confidence = min(90, 60 + strength * 0.3)
            direction = "BULLISH" if ema_alignment > 0 else "BEARISH"
            description = f"Strong trend detected ({direction})"
        elif expansion_ratio < 0.035 and avg_slope < 0.01:
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
    """
    Calculate RSI across multiple timeframes.
    
    Args:
        c15, c1h, c4h, c1d: Candle data for each timeframe
    
    Returns:
        dict: RSI values and score for each timeframe
    """
    try:
        data = {}
        frames = {"15m": c15, "1h": c1h, "4h": c4h, "1d": c1d}
        score = 0

        for name, candles in frames.items():
            if len(candles) < 15:
                data[name] = 50  # Neutral when insufficient data
                continue
                
            closes = [x["close"] for x in candles]
            value = rsi(closes)
            data[name] = round(value, 2)

            # Scoring logic
            if 50 <= value <= 70:
                score += 10
            elif value > 75:
                score -= 10
            elif value < 35:
                score += 5

        data["score"] = score
        return data

    except Exception as e:
        print(f"❌ MULTI RSI ERROR: {e}")
        return {"15m": 50, "1h": 50, "4h": 50, "1d": 50, "score": 0}


# ================================================
# 🧱 SUPPORT RESISTANCE ENGINE
# ================================================

def support_resistance(candles):
    """
    Calculate support and resistance levels.
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Support, resistance, and distance metrics
    """
    try:
        if len(candles) < 80:
            return {"support": 0, "resistance": 0, "near_support": 0, "near_resistance": 0}

        highs = [x["high"] for x in candles[-80:]]
        lows = [x["low"] for x in candles[-80:]]
        price = candles[-1]["close"]

        support = min(lows)
        resistance = max(highs)

        return {
            "support": support,
            "resistance": resistance,
            "near_support": ((price - support) / price) * 100 if price > 0 else 0,
            "near_resistance": ((resistance - price) / price) * 100 if price > 0 else 0
        }

    except Exception as e:
        print(f"❌ SUPPORT/RESISTANCE ERROR: {e}")
        return {"support": 0, "resistance": 0, "near_support": 0, "near_resistance": 0}


# ================================================
# 🛡 SYMMETRIC FOMO FILTER
# ================================================

def fomo_filter(candles, direction="LONG"):
    """
    Prevent FOMO entries by checking overextension.
    
    Args:
        candles (list): List of candle dictionaries
        direction (str): "LONG" or "SHORT"
    
    Returns:
        tuple: (is_safe, warning_message, reason_code)
    """
    try:
        if len(candles) < 96:
            return False, "⚠️ Insufficient data for FOMO filter", "INSUFFICIENT_DATA"

        closes = [x["close"] for x in candles]
        price = closes[-1]

        move_30 = ((price - closes[-30]) / closes[-30]) * 100
        move_96 = ((price - closes[-96]) / closes[-96]) * 100
        current_rsi = rsi(closes)

        if direction == "LONG":
            # Check for overextension
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
            # Check for overextension (opposite logic)
            if move_30 < -8 or move_96 < -15:
                return False, "🚫 OVEREXTENDED BEARISH", "FOMO_OVEREXTENDED_BEAR"
            if move_30 < -5 and current_rsi < 35:
                return False, "⏳ WAIT BOUNCE", "FOMO_BOUNCE"
            if current_rsi < 25:
                return False, "🚫 RSI OVERSOLD", "FOMO_RSI_OVERSOLD"
            if current_rsi > 65:
                return False, "📈 RSI OVERBOUGHT - NOT SHORT", "FOMO_RSI_OVERBOUGHT"
            
            return True, "🐻 EARLY SHORT AREA", None

    except Exception as e:
        print(f"❌ FOMO FILTER ERROR: {e}")
        return False, f"⚠️ FOMO filter error: {e}", "ERROR"


# ================================================
# 🪤 TRAP DETECTOR
# ================================================

def trap_detector(candles):
    """
    Detect potential bull/bear traps.
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        str: Trap status message
    """
    try:
        if len(candles) < 50:
            return "⚠️ INSUFFICIENT DATA"

        closes = [x["close"] for x in candles]
        highs = [x["high"] for x in candles]
        lows = [x["low"] for x in candles]

        price = closes[-1]
        r = rsi(closes)

        # Bull trap: price near 50-period high with overbought RSI
        if price >= max(highs[-50:]) * 0.98 and r > 70:
            return "🪤 BULL TRAP"

        # Bear trap: price near 50-period low with oversold RSI
        if price <= min(lows[-50:]) * 1.02 and r < 35:
            return "🪤 BEAR TRAP"

        return "✅ NO TRAP"

    except Exception as e:
        print(f"❌ TRAP DETECTOR ERROR: {e}")
        return "⚠️ ERROR"


# ================================================
# 🧠 AI BRAIN ENGINE
# ================================================

def ai_brain(candles):
    """
    AI Brain engine for directional bias.
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Directional scores and confidence
    """
    try:
        if len(candles) < 100:
            return {
                "direction": "WAIT",
                "confidence": 0,
                "long_score": 0,
                "short_score": 0
            }

        closes = [x["close"] for x in candles]
        price = closes[-1]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        e100 = ema(closes, 100)

        long_score = 0
        short_score = 0

        # Price vs EMA20
        if price > e20:
            long_score += 25
        else:
            short_score += 25

        # EMA20 vs EMA50
        if e20 > e50:
            long_score += 20
        else:
            short_score += 20

        # EMA50 vs EMA100
        if e50 > e100:
            long_score += 20
        else:
            short_score += 20

        # EMA20 trend (last 4 candles)
        if len(closes) >= 4:
            old20 = ema(closes[:-4], 20)
            if e20 > old20:
                long_score += 15
            elif e20 < old20:
                short_score += 15

        # Proximity to EMA20
        distance = abs(price - e20) / e20 if e20 > 0 else 0
        if distance < 0.01:
            long_score += 10
            short_score += 10

        confidence = abs(long_score - short_score)

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

    except Exception as e:
        print(f"❌ AI BRAIN ERROR: {e}")
        return {
            "direction": "WAIT",
            "confidence": 0,
            "long_score": 0,
            "short_score": 0
        }


# ================================================
# 📈 TRADE TRACKER CACHE
# ================================================

_trade_tracker_cache = {}

def get_trade_tracker_candles(symbol, tf="15m", ttl=CACHE_TTL):
    """
    Cache candles for Trade Tracker with TTL.
    Returns only confirmed (completed) candles.
    """
    now = time.time()
    key = f"{symbol}_{tf}"

    if key in _trade_tracker_cache:
        cached = _trade_tracker_cache[key]
        if now - cached["time"] <= ttl:
            return cached["candles"]

    candles = get_candles(symbol, tf)
    
    # Filter to only confirmed candles
    if candles:
        candles = [c for c in candles if c.get('confirmed', False)]
    
    _trade_tracker_cache[key] = {
        "time": now,
        "candles": candles
    }

    return candles


def update_open_trades():
    """Monitor open trades with exponential backoff"""
    backoff = TRACKER_BACKOFF_INITIAL
    
    print("📈 Trade Tracker STARTED")

    while True:
        try:
            open_trades = get_open_trades()

            if not open_trades:
                time.sleep(backoff)
                backoff = min(backoff * 1.5, TRACKER_BACKOFF_MAX)
                continue

            # Reset backoff when we have trades
            backoff = TRACKER_BACKOFF_INITIAL
            
            if DEBUG_MODE:
                print(f"📊 Checking {len(open_trades)} open trades...")

            for trade in open_trades:
                try:
                    candles = get_trade_tracker_candles(trade['symbol'], "15m")
                    if not candles:
                        continue

                    # Use the latest confirmed candle
                    latest = candles[-1]
                    current_high = latest['high']
                    current_low = latest['low']

                    # Calculate profit/drawdown
                    if trade['side'] == "LONG":
                        best_excursion = ((current_high - trade['entry']) / trade['entry']) * 100
                        worst_excursion = ((current_low - trade['entry']) / trade['entry']) * 100
                    else:  # SHORT
                        best_excursion = ((trade['entry'] - current_low) / trade['entry']) * 100
                        worst_excursion = ((trade['entry'] - current_high) / trade['entry']) * 100

                    trade["max_profit"] = max(trade["max_profit"], best_excursion)
                    trade["max_drawdown"] = min(trade["max_drawdown"], worst_excursion)

                    new_status = None
                    result = None
                    close_time = datetime.now()

                    # Check TP/SL conditions
                    if trade['side'] == "LONG":
                        # Conservative: if both SL and TP touched, assume SL hit first
                        if current_low <= trade['sl'] and current_high >= trade['tp1']:
                            new_status = "CLOSED"
                            result = "LOSS_SL"
                        elif current_high >= trade['tp3']:
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
                        if current_high >= trade['sl'] and current_low <= trade['tp1']:
                            new_status = "CLOSED"
                            result = "LOSS_SL"
                        elif current_low <= trade['tp3']:
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

                    if new_status:
                        update_trade(
                            trade['id'],
                            new_status,
                            result,
                            round(trade['max_profit'], 2),
                            round(trade['max_drawdown'], 2),
                            close_time
                        )
                        print(f"🔒 Trade {trade['id']} {trade['symbol']} closed: {result}")
                    else:
                        # Update max profit/drawdown only
                        update_trade(
                            trade['id'],
                            'OPEN',
                            'PENDING',
                            round(trade['max_profit'], 2),
                            round(trade['max_drawdown'], 2),
                            None
                        )

                except Exception as e:
                    print(f"❌ Error processing trade {trade.get('id', 'unknown')}: {e}")
                    continue

            time.sleep(backoff)

        except Exception as e:
            print(f"❌ Trade Tracker error: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, TRACKER_BACKOFF_MAX)

# Print startup message
print(f"🔥 OKX Data & Indicators Engine LOADED 🐋")

# ================================================
# 🧠 SECTION 3: AI ENGINES (PART 1)
# ================================================

# ================================================
# 🏦 SECTOR FLOW ENGINE (Enhanced)
# ================================================

def sector_flow(symbols):
    """
    Calculate flow power for each sector based on volume.
    
    Enhanced with:
    - Better error handling
    - Weighted scoring based on sector size
    - Historical comparison
    
    Args:
        symbols (list): List of trading symbols
    
    Returns:
        dict: Sector flow analysis with ranking
    """
    try:
        result = {}
        ranking = []
        sector_details = {}

        for sector, coins in SECTORS.items():
            total_flow = 0
            matched = 0
            sector_flows = []

            for symbol in symbols:
                base = symbol.split("-")[0]

                if base in coins:
                    candles = get_candles_cached(symbol, "1h")

                    if len(candles) > 50:
                        volumes = [x["volume"] for x in candles]
                        recent = sum(volumes[-5:])
                        average = sum(volumes[-50:]) / 50

                        if average > 0:
                            flow = recent / (average * 5)
                            total_flow += flow
                            matched += 1
                            sector_flows.append(flow)

            # Calculate average flow for sector
            if matched > 0:
                avg_flow = round(total_flow / matched, 2)
            else:
                avg_flow = 0

            result[sector] = avg_flow
            ranking.append((sector, avg_flow))
            
            # Store detailed info
            sector_details[sector] = {
                "coins_matched": matched,
                "avg_flow": avg_flow,
                "max_flow": round(max(sector_flows) if sector_flows else 0, 2),
                "min_flow": round(min(sector_flows) if sector_flows else 0, 2)
            }

        # Sort by flow (highest first)
        ranking = sorted(ranking, key=lambda x: x[1], reverse=True)

        # Calculate sector strength score
        if ranking and ranking[0][1] > 0:
            sector_strength = "🔥 STRONG" if ranking[0][1] > 2.0 else "✅ MODERATE"
            if ranking[0][1] > 3.0:
                sector_strength = "🚀 VERY STRONG"
        else:
            sector_strength = "📊 NEUTRAL"

        return {
            "sector": ranking[0][0] if ranking else "UNKNOWN",
            "power": ranking[0][1] if ranking else 0,
            "ranking": ranking[:3],
            "strength": sector_strength,
            "details": sector_details
        }

    except Exception as e:
        print(f"❌ SECTOR FLOW ERROR: {e}")
        return {
            "sector": "UNKNOWN",
            "power": 0,
            "ranking": [],
            "strength": "📊 NEUTRAL",
            "details": {}
        }


# ================================================
# 🐋 SMART MONEY ENGINE (Enhanced)
# ================================================

def smart_money(candles):
    """
    Detect smart money activity based on volume and price action.
    
    Enhanced with:
    - More granular status detection
    - Volume acceleration metrics
    - Trend confirmation
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Flow analysis with status and metrics
    """
    try:
        if len(candles) < 50:
            return {
                "flow": 0, 
                "status": "INSUFFICIENT_DATA", 
                "volume_acceleration": 0,
                "trend": "UNKNOWN"
            }

        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]

        # Volume calculations
        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            flow = 0
        else:
            flow = volume_now / (volume_avg * 5)

        # Volume acceleration (last 5 vs last 20)
        volume_avg_20 = sum(volumes[-20:]) / 4
        volume_acceleration = volume_now / volume_avg_20 if volume_avg_20 > 0 else 0

        # Price movement
        move_24h = ((closes[-1] - closes[-24]) / closes[-24]) * 100 if len(closes) >= 24 else 0
        move_12h = ((closes[-1] - closes[-12]) / closes[-12]) * 100 if len(closes) >= 12 else 0
        
        # RSI for confirmation
        current_rsi = rsi(closes)

        # Enhanced status detection
        status = "NORMAL"
        flow_rating = "N/A"
        
        if flow >= 3.0:
            flow_rating = "🚀 EXTREME"
            if abs(move_24h) < 5 and current_rsi < 60:
                status = "🐋 MASSIVE ACCUMULATION"
            elif move_24h > 10:
                status = "🚨 WHALE DISTRIBUTION"
            else:
                status = "🐋 WHALE ACTIVITY"
                
        elif flow >= 2.0:
            flow_rating = "🐋 HIGH"
            if abs(move_24h) < 4 and current_rsi < 55:
                status = "📈 INSTITUTIONAL BUYING"
            elif move_24h > 8:
                status = "📉 INSTITUTIONAL SELLING"
            else:
                status = "💪 STRONG FLOW"
                
        elif flow >= 1.5:
            flow_rating = "💧 GOOD"
            if abs(move_24h) < 3:
                status = "📊 STEADY ACCUMULATION"
            else:
                status = "📈 HEALTHY FLOW"
                
        elif flow >= 1.2:
            flow_rating = "📊 MODERATE"
            status = "🔄 NEUTRAL FLOW"
        else:
            flow_rating = "⚠️ LOW"
            status = "⏳ LOW ACTIVITY"

        # Trend detection
        if len(closes) >= 20:
            short_ma = sum(closes[-5:]) / 5
            long_ma = sum(closes[-20:]) / 20
            if short_ma > long_ma * 1.02:
                trend = "BULLISH"
            elif short_ma < long_ma * 0.98:
                trend = "BEARISH"
            else:
                trend = "CONSOLIDATING"
        else:
            trend = "UNKNOWN"

        return {
            "flow": round(flow, 2),
            "status": status,
            "flow_rating": flow_rating,
            "volume_acceleration": round(volume_acceleration, 2),
            "trend": trend,
            "rsi": round(current_rsi, 1) if current_rsi else 0,
            "move_24h": round(move_24h, 2)
        }

    except Exception as e:
        print(f"❌ SMART MONEY ERROR: {e}")
        return {
            "flow": 0, 
            "status": "ERROR", 
            "flow_rating": "N/A",
            "volume_acceleration": 0,
            "trend": "UNKNOWN",
            "rsi": 0,
            "move_24h": 0
        }


# ================================================
# 🐋 PRE PUMP ENGINE (Enhanced)
# ================================================

def pre_pump_engine(candles):
    """
    Detect pre-pump accumulation patterns.
    
    Enhanced with:
    - Multiple accumulation patterns
    - Volume confirmation
    - RSI and price action checks
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Pre-pump status and score
    """
    try:
        if len(candles) < 60:
            return {
                "status": "INSUFFICIENT_DATA", 
                "score": 0,
                "confidence": 0,
                "pattern": "NONE"
            }

        closes = [x["close"] for x in candles]
        volumes = [x["volume"] for x in candles]
        highs = [x["high"] for x in candles]
        lows = [x["low"] for x in candles]

        price = closes[-1]
        volume_now = sum(volumes[-5:])
        volume_avg = sum(volumes[-50:]) / 50

        if volume_avg == 0:
            return {"status": "NORMAL", "score": 0, "confidence": 0, "pattern": "NONE"}

        flow = volume_now / (volume_avg * 5)
        move_30 = ((price - closes[-30]) / closes[-30]) * 100 if len(closes) >= 30 else 0
        move_10 = ((price - closes[-10]) / closes[-10]) * 100 if len(closes) >= 10 else 0
        current_rsi = rsi(closes)
        
        # Price range contraction (volatility compression)
        range_20 = (max(highs[-20:]) - min(lows[-20:])) / price * 100 if price > 0 else 0
        range_50 = (max(highs[-50:]) - min(lows[-50:])) / price * 100 if price > 0 else 0
        range_contraction = range_50 - range_20 if range_50 > 0 else 0

        # Pattern detection with multiple conditions
        pattern = "NONE"
        confidence = 0
        score = 0
        
        # Pattern 1: Classic whale loading (high volume, stable price, neutral RSI)
        if (flow >= 1.20 and abs(move_30) < 4 and 40 <= current_rsi <= 60):
            pattern = "🐋 WHALE LOADING"
            confidence = 70
            score = 25
            
            # Bonus for volume acceleration
            if flow >= 2.0:
                confidence += 15
                score += 10
            if range_contraction > 2:
                confidence += 10
                score += 5

        # Pattern 2: Spring loading (volume spike, tight range, RSI oversold)
        elif (flow >= 1.5 and range_20 < 3 and current_rsi < 40):
            pattern = "🔥 SPRING LOADING"
            confidence = 75
            score = 30
            
            # Higher confidence if RSI is turning up
            if current_rsi > 35:
                confidence += 10
                score += 5

        # Pattern 3: Stealth accumulation (gradual volume increase, small price moves)
        elif (flow >= 1.1 and abs(move_10) < 2 and current_rsi < 55 and current_rsi > 35):
            pattern = "🤫 STEALTH ACCUMULATION"
            confidence = 60
            score = 15
            
            if flow >= 1.5:
                confidence += 10
                score += 5

        # Pattern 4: Breakout preparation (volume building, range tightening)
        elif (flow >= 1.3 and range_contraction > 1.5 and current_rsi < 65):
            pattern = "⚡ BREAKOUT PREP"
            confidence = 65
            score = 20

        # Determine status based on pattern
        if pattern != "NONE":
            status = f"{pattern} [{confidence}%]"
        else:
            status = "NORMAL"

        return {
            "status": status,
            "score": score,
            "confidence": confidence,
            "pattern": pattern,
            "flow": round(flow, 2),
            "range_contraction": round(range_contraction, 2),
            "rsi": round(current_rsi, 1) if current_rsi else 0
        }

    except Exception as e:
        print(f"❌ PRE PUMP ERROR: {e}")
        return {
            "status": "ERROR", 
            "score": 0,
            "confidence": 0,
            "pattern": "ERROR",
            "flow": 0,
            "range_contraction": 0,
            "rsi": 0
        }


# ================================================
# 🔥 VOLATILITY COMPRESSION ENGINE (Enhanced)
# ================================================

def volatility_engine(candles):
    """
    Calculate volatility compression score.
    
    Enhanced with:
    - Multiple compression indicators
    - Historical comparison
    - ATR and price range analysis
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Compression score, status, and detailed metrics
    """
    try:
        if len(candles) < 60:
            return {
                "score": 0,
                "status": "INSUFFICIENT_DATA",
                "range": 0,
                "atr_now": 0,
                "atr_old": 0,
                "atr_ratio": 0,
                "range_ratio": 0,
                "bonus": 0,
                "compression_level": "NONE"
            }

        # Recent 20 candles
        recent = candles[-20:]
        old = candles[-60:-40]

        # Price ranges
        recent_highs = [c["high"] for c in recent]
        recent_lows = [c["low"] for c in recent]
        old_highs = [c["high"] for c in old]
        old_lows = [c["low"] for c in old]

        recent_range = max(recent_highs) - min(recent_lows)
        old_range = max(old_highs) - min(old_lows)

        # ATR calculations
        atr_now = atr(candles[-14:])
        atr_old = atr(candles[-60:-46])

        # Calculate compression metrics
        if atr_old > 0:
            atr_ratio = atr_now / atr_old
            compression = (1 - atr_ratio) * 100
        else:
            atr_ratio = 1
            compression = 0

        if old_range > 0:
            range_ratio = recent_range / old_range
            compression_range = (1 - range_ratio) * 100
        else:
            range_ratio = 1
            compression_range = 0

        # Combine compression scores (weighted)
        final_compression = (compression * 0.6) + (compression_range * 0.4)
        final_compression = max(0, min(100, final_compression))

        # Determine compression level
        compression_level = "NONE"
        status = "📈 EXPANDING"
        bonus = -5

        if final_compression >= 70:
            compression_level = "EXTREME"
            status = "🔥 SPRING LOADED"
            bonus = 25
        elif final_compression >= 55:
            compression_level = "HIGH"
            status = "⚡ BUILDING PRESSURE"
            bonus = 15
        elif final_compression >= 40:
            compression_level = "MODERATE"
            status = "📊 NORMAL COMPRESSION"
            bonus = 8
        elif final_compression >= 25:
            compression_level = "LOW"
            status = "🔄 MILD COMPRESSION"
            bonus = 3
        else:
            compression_level = "NONE"
            status = "📈 EXPANDING"
            bonus = -5

        # Additional bonus for compression pattern confirmation
        if final_compression >= 40 and atr_ratio < 0.7 and range_ratio < 0.7:
            bonus += 5

        return {
            "score": round(final_compression),
            "status": status,
            "range": round(recent_range, 6),
            "atr_now": round(atr_now, 6),
            "atr_old": round(atr_old, 6),
            "atr_ratio": round(atr_ratio, 3),
            "range_ratio": round(range_ratio, 3),
            "bonus": bonus,
            "compression_level": compression_level
        }

    except Exception as e:
        print(f"❌ VOLATILITY ERROR: {e}")
        return {
            "score": 0,
            "status": "ERROR",
            "range": 0,
            "atr_now": 0,
            "atr_old": 0,
            "atr_ratio": 0,
            "range_ratio": 0,
            "bonus": 0,
            "compression_level": "ERROR"
        }


# ================================================
# 📊 MARKET REGIME ENGINE (Enhanced)
# ================================================

def market_regime(candles, compression_score):
    """
    Classify market into TRENDING, RANGING, or COMPRESSION.
    
    Enhanced with:
    - Multiple regime detection indicators
    - Confidence scoring
    - Trend strength calculation
    
    Args:
        candles (list): List of candle dictionaries
        compression_score (int): Compression score from volatility_engine
    
    Returns:
        dict: Market regime classification with metrics
    """
    try:
        if len(candles) < 150:
            return {
                "regime": "UNKNOWN",
                "strength": 0,
                "confidence": 0,
                "description": "Insufficient data (need 150 candles)",
                "ema_alignment": 0,
                "expansion_ratio": 0,
                "avg_slope": 0,
                "volatility_index": 0
            }

        closes = [x["close"] for x in candles[-150:]]
        highs = [x["high"] for x in candles[-150:]]
        lows = [x["low"] for x in candles[-150:]]

        # EMAs
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema100 = ema(closes, 100)

        # Calculate expansion ratio
        price_range = max(highs) - min(lows)
        avg_price = sum(closes) / len(closes)
        expansion_ratio = price_range / avg_price if avg_price > 0 else 0

        # EMA alignment
        ema_alignment = 0
        if ema20 > ema50 > ema100:
            ema_alignment = 1  # Bullish
        elif ema20 < ema50 < ema100:
            ema_alignment = -1  # Bearish
        else:
            ema_alignment = 0  # Mixed

        # Calculate slope
        if len(closes) >= 20:
            slope20 = (ema20 - ema(closes[:-10], 20)) / ema20 if ema20 > 0 else 0
            slope50 = (ema50 - ema(closes[:-10], 50)) / ema50 if ema50 > 0 else 0
            avg_slope = (abs(slope20) + abs(slope50)) / 2
        else:
            avg_slope = 0

        # Volatility index (ATR relative to price)
        atr_val = atr(candles[-14:])
        volatility_index = (atr_val / avg_price) * 100 if avg_price > 0 else 0

        # Regime classification with confidence
        regime = "MIXED"
        strength = 40
        confidence = 50
        description = "Mixed signals - neutral regime"

        # Check for COMPRESSION first (highest priority)
        if compression_score >= 50 and expansion_ratio < 0.06:
            regime = "COMPRESSION"
            strength = compression_score
            confidence = 70 + (compression_score / 100) * 20
            description = "Market compressing - breakout imminent"
            
            # Additional compression confirmation
            if volatility_index < 1.0:
                confidence += 10

        # Check for TRENDING
        elif expansion_ratio > 0.08 and avg_slope > 0.015:
            regime = "TRENDING"
            strength = min(100, avg_slope * 800)
            confidence = min(90, 60 + strength * 0.3)
            direction = "BULLISH" if ema_alignment > 0 else "BEARISH"
            description = f"Strong trend detected ({direction})"
            
            # Additional trend confirmation
            if abs(ema_alignment) == 1:
                confidence += 10

        # Check for RANGING
        elif expansion_ratio < 0.04 and avg_slope < 0.01:
            regime = "RANGING"
            strength = 50
            confidence = 65
            description = "Market ranging - no clear direction"
            
            # Confirmation from volatility
            if volatility_index < 0.8:
                confidence += 10

        return {
            "regime": regime,
            "strength": round(strength, 2),
            "confidence": round(confidence, 2),
            "description": description,
            "ema_alignment": ema_alignment,
            "expansion_ratio": round(expansion_ratio, 4),
            "avg_slope": round(avg_slope, 4),
            "volatility_index": round(volatility_index, 2)
        }

    except Exception as e:
        print(f"❌ Market Regime Error: {e}")
        return {
            "regime": "UNKNOWN",
            "strength": 0,
            "confidence": 0,
            "description": "Error in regime detection",
            "ema_alignment": 0,
            "expansion_ratio": 0,
            "avg_slope": 0,
            "volatility_index": 0
        }


# ================================================
# 📊 MULTI TIMEFRAME ENGINE (Enhanced)
# ================================================

def multi_rsi_engine(c15, c1h, c4h, c1d):
    """
    Calculate RSI across multiple timeframes.
    
    Enhanced with:
    - Divergence detection
    - Weighted scoring based on timeframe importance
    - Trend confirmation
    
    Args:
        c15, c1h, c4h, c1d: Candle data for each timeframe
    
    Returns:
        dict: RSI values and comprehensive score
    """
    try:
        data = {}
        frames = {
            "15m": c15,
            "1h": c1h,
            "4h": c4h,
            "1d": c1d
        }
        
        score = 0
        divergence_detected = False
        timeframe_weight = {"15m": 1.0, "1h": 1.5, "4h": 2.0, "1d": 2.5}

        # Calculate RSI for each timeframe
        for name, candles in frames.items():
            if len(candles) < 15:
                data[name] = 50
                continue
                
            closes = [x["close"] for x in candles]
            value = rsi(closes)
            data[name] = round(value, 2)

            # Weighted scoring
            weight = timeframe_weight.get(name, 1.0)
            
            # RSI scoring logic
            if 50 <= value <= 70:
                score += int(10 * weight)
            elif value > 75:
                score -= int(10 * weight)
            elif value < 35:
                score += int(5 * weight)

        # Divergence detection (15m vs 4h)
        if "15m" in data and "4h" in data:
            if data["15m"] > 70 and data["4h"] < 50:
                divergence_detected = True
                score -= 15
            elif data["15m"] < 30 and data["4h"] > 50:
                divergence_detected = True
                score += 15

        # Trend confirmation (consistency across timeframes)
        rsi_values = [data[tf] for tf in ["15m", "1h", "4h", "1d"] if tf in data]
        if len(rsi_values) >= 3:
            avg_rsi = sum(rsi_values) / len(rsi_values)
            if all(v > 50 for v in rsi_values) or all(v < 50 for v in rsi_values):
                score += 10  # Bullish or bearish consensus
            elif abs(max(rsi_values) - min(rsi_values)) < 10:
                score += 5   # Neutral consensus

        data["score"] = score
        data["divergence"] = divergence_detected
        data["consensus"] = "BULLISH" if all(v > 50 for v in rsi_values) else "BEARISH" if all(v < 50 for v in rsi_values) else "NEUTRAL"

        return data

    except Exception as e:
        print(f"❌ MULTI RSI ERROR: {e}")
        return {
            "15m": 50, "1h": 50, "4h": 50, "1d": 50,
            "score": 0,
            "divergence": False,
            "consensus": "NEUTRAL"
        }


# ================================================
# 🧱 SUPPORT RESISTANCE ENGINE (Enhanced)
# ================================================

def support_resistance(candles):
    """
    Calculate support and resistance levels.
    
    Enhanced with:
    - Multiple timeframe levels
    - Strength scoring for levels
    - Proximity detection
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Support, resistance, and distance metrics
    """
    try:
        if len(candles) < 80:
            return {
                "support": 0,
                "resistance": 0,
                "near_support": 0,
                "near_resistance": 0,
                "support_strength": 0,
                "resistance_strength": 0,
                "key_levels": []
            }

        price = candles[-1]["close"]
        
        # Different timeframe levels
        levels = {
            "20": {"highs": [], "lows": []},
            "50": {"highs": [], "lows": []},
            "80": {"highs": [], "lows": []}
        }

        for period in levels.keys():
            p = int(period)
            highs = [x["high"] for x in candles[-p:]]
            lows = [x["low"] for x in candles[-p:]]
            levels[period]["highs"] = highs
            levels[period]["lows"] = lows

        # Key support and resistance
        support_80 = min(levels["80"]["lows"])
        resistance_80 = max(levels["80"]["highs"])
        support_50 = min(levels["50"]["lows"])
        resistance_50 = max(levels["50"]["highs"])
        
        # Determine strongest levels (multi-timeframe)
        if support_80 == support_50:
            support = support_80
            support_strength = 100
        elif abs(support_80 - support_50) / price < 0.01:
            support = support_80
            support_strength = 80
        else:
            support = support_50
            support_strength = 60

        if resistance_80 == resistance_50:
            resistance = resistance_80
            resistance_strength = 100
        elif abs(resistance_80 - resistance_50) / price < 0.01:
            resistance = resistance_80
            resistance_strength = 80
        else:
            resistance = resistance_50
            resistance_strength = 60

        # Key levels list
        key_levels = [
            {"level": support, "type": "SUPPORT", "strength": support_strength},
            {"level": resistance, "type": "RESISTANCE", "strength": resistance_strength}
        ]

        # Add additional levels if significant
        if abs(support - support_80) / price > 0.01:
            key_levels.append({"level": support_80, "type": "SUPPORT_MAJOR", "strength": 40})
        if abs(resistance - resistance_80) / price > 0.01:
            key_levels.append({"level": resistance_80, "type": "RESISTANCE_MAJOR", "strength": 40})

        return {
            "support": support,
            "resistance": resistance,
            "near_support": ((price - support) / price) * 100 if price > 0 else 0,
            "near_resistance": ((resistance - price) / price) * 100 if price > 0 else 0,
            "support_strength": support_strength,
            "resistance_strength": resistance_strength,
            "key_levels": key_levels
        }

    except Exception as e:
        print(f"❌ SUPPORT/RESISTANCE ERROR: {e}")
        return {
            "support": 0,
            "resistance": 0,
            "near_support": 0,
            "near_resistance": 0,
            "support_strength": 0,
            "resistance_strength": 0,
            "key_levels": []
        }


print(f"🧠 AI Engines PART 1 LOADED 🐋")

# ================================================
# 🧠 SECTION 4: AI ENGINES (PART 2)
# ================================================

# ================================================
# 🛡 SYMMETRIC FOMO FILTER (FIXED)
# ================================================

def fomo_filter(candles, direction="LONG"):
    """
    Prevent FOMO entries by checking overextension.
    
    FIXED:
    - Corrected logic for SHORT direction
    - Added symmetric checks for both directions
    - Enhanced with RSI and momentum indicators
    
    Args:
        candles (list): List of candle dictionaries
        direction (str): "LONG" or "SHORT"
    
    Returns:
        tuple: (is_safe, warning_message, reason_code)
    """
    try:
        if len(candles) < 96:
            return False, "⚠️ Insufficient data for FOMO filter", "INSUFFICIENT_DATA"

        closes = [x["close"] for x in candles]
        price = closes[-1]

        # Calculate price movements
        move_30 = ((price - closes[-30]) / closes[-30]) * 100 if len(closes) >= 30 else 0
        move_96 = ((price - closes[-96]) / closes[-96]) * 100 if len(closes) >= 96 else 0
        move_10 = ((price - closes[-10]) / closes[-10]) * 100 if len(closes) >= 10 else 0
        current_rsi = rsi(closes)
        
        # Momentum check (acceleration)
        if len(closes) >= 5:
            move_5 = ((closes[-1] - closes[-5]) / closes[-5]) * 100
        else:
            move_5 = 0

        if direction == "LONG":
            # ====== LONG FILTERS ======
            
            # 1. Check for overextension (already pumped too much)
            if move_30 > 8:
                return False, "🚫 OVEREXTENDED BULLISH (30 candles)", "FOMO_OVEREXTENDED_BULL_30"
            if move_96 > 15:
                return False, "🚫 OVEREXTENDED BULLISH (96 candles)", "FOMO_OVEREXTENDED_BULL_96"
            
            # 2. Check for recent pump (last 10 candles)
            if move_10 > 5 and current_rsi > 65:
                return False, "⏳ WAIT PULLBACK", "FOMO_PULLBACK"
            
            # 3. RSI checks
            if current_rsi > 75:
                return False, "🚫 RSI OVERBOUGHT", "FOMO_RSI_OVERBOUGHT"
            if current_rsi < 35:
                return False, "📉 RSI OVERSOLD - NOT LONG", "FOMO_RSI_OVERSOLD"
            
            # 4. Momentum acceleration check
            if move_5 > 3 and current_rsi > 70:
                return False, "🚫 ACCELERATING BULLISH MOMENTUM", "FOMO_ACCELERATING_BULL"
            
            # 5. Distance from EMAs (too far from mean)
            ema20 = ema(closes, 20)
            distance_from_ema = ((price - ema20) / ema20) * 100 if ema20 > 0 else 0
            if distance_from_ema > 4:
                return False, "🚫 TOO FAR FROM EMA20", "FOMO_FAR_FROM_EMA"
            
            return True, "🐋 EARLY LONG AREA", None
            
        else:  # SHORT
            # ====== SHORT FILTERS (SYMMETRIC) ======
            
            # 1. Check for overextension (already dumped too much)
            if move_30 < -8:
                return False, "🚫 OVEREXTENDED BEARISH (30 candles)", "FOMO_OVEREXTENDED_BEAR_30"
            if move_96 < -15:
                return False, "🚫 OVEREXTENDED BEARISH (96 candles)", "FOMO_OVEREXTENDED_BEAR_96"
            
            # 2. Check for recent dump (last 10 candles)
            if move_10 < -5 and current_rsi < 35:
                return False, "⏳ WAIT BOUNCE", "FOMO_BOUNCE"
            
            # 3. RSI checks (symmetric to LONG)
            if current_rsi < 25:
                return False, "🚫 RSI OVERSOLD", "FOMO_RSI_OVERSOLD"
            if current_rsi > 65:
                return False, "📈 RSI OVERBOUGHT - NOT SHORT", "FOMO_RSI_OVERBOUGHT"
            
            # 4. Momentum acceleration check (symmetric)
            if move_5 < -3 and current_rsi < 30:
                return False, "🚫 ACCELERATING BEARISH MOMENTUM", "FOMO_ACCELERATING_BEAR"
            
            # 5. Distance from EMAs (too far from mean)
            ema20 = ema(closes, 20)
            distance_from_ema = ((ema20 - price) / ema20) * 100 if ema20 > 0 else 0
            if distance_from_ema > 4:
                return False, "🚫 TOO FAR FROM EMA20", "FOMO_FAR_FROM_EMA"
            
            return True, "🐻 EARLY SHORT AREA", None

    except Exception as e:
        print(f"❌ FOMO FILTER ERROR: {e}")
        return False, f"⚠️ FOMO filter error: {e}", "ERROR"


# ================================================
# 🪤 TRAP DETECTOR (Enhanced)
# ================================================

def trap_detector(candles):
    """
    Detect potential bull/bear traps.
    
    Enhanced with:
    - Multiple trap patterns
    - Volume confirmation
    - RSI and price action checks
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Trap status with details
    """
    try:
        if len(candles) < 50:
            return {
                "status": "⚠️ INSUFFICIENT DATA",
                "trap_type": "NONE",
                "confidence": 0,
                "description": "Need at least 50 candles"
            }

        closes = [x["close"] for x in candles]
        highs = [x["high"] for x in candles]
        lows = [x["low"] for x in candles]
        volumes = [x["volume"] for x in candles]

        price = closes[-1]
        current_rsi = rsi(closes)
        
        # Calculate key levels
        high_50 = max(highs[-50:])
        low_50 = min(lows[-50:])
        high_20 = max(highs[-20:])
        low_20 = min(lows[-20:])
        
        # Volume indicators
        vol_avg_20 = sum(volumes[-20:]) / 20
        vol_now = volumes[-1]
        vol_spike = vol_now / vol_avg_20 if vol_avg_20 > 0 else 0

        trap_type = "NONE"
        confidence = 0
        description = "✅ NO TRAP DETECTED"

        # ====== BULL TRAP DETECTION ======
        # Pattern 1: Price breaks above resistance but fails
        if price >= high_50 * 0.98:
            # Check for false breakout: high RSI + high volume spike
            if current_rsi > 70 and vol_spike > 1.5:
                trap_type = "BULL_TRAP"
                confidence = 75
                description = "🪤 BULL TRAP - False breakout above resistance"
            
            # Check for reversal pattern: price near high but RSI diverging
            elif current_rsi > 65 and len(candles) >= 10:
                # Check if RSI is decreasing while price is increasing
                rsi_trend = rsi(closes[-10:]) - rsi(closes[-20:-10]) if len(closes) >= 20 else 0
                if rsi_trend < 0:
                    trap_type = "BULL_TRAP"
                    confidence = 60
                    description = "🪤 BULL TRAP - RSI divergence at resistance"
        
        # ====== BEAR TRAP DETECTION ======
        # Pattern 1: Price breaks below support but reverses
        elif price <= low_50 * 1.02:
            # Check for false breakdown: low RSI + high volume spike
            if current_rsi < 30 and vol_spike > 1.5:
                trap_type = "BEAR_TRAP"
                confidence = 75
                description = "🪤 BEAR TRAP - False breakdown below support"
            
            # Check for reversal pattern: price near low but RSI diverging
            elif current_rsi < 35 and len(candles) >= 10:
                # Check if RSI is increasing while price is decreasing
                rsi_trend = rsi(closes[-10:]) - rsi(closes[-20:-10]) if len(closes) >= 20 else 0
                if rsi_trend > 0:
                    trap_type = "BEAR_TRAP"
                    confidence = 60
                    description = "🪤 BEAR TRAP - RSI divergence at support"

        # ====== ADDITIONAL TRAP PATTERNS ======
        # Pattern: Long wick rejection
        if len(candles) >= 5:
            last_candle = candles[-1]
            candle_range = last_candle["high"] - last_candle["low"]
            if candle_range > 0:
                upper_wick = (last_candle["high"] - max(last_candle["open"], last_candle["close"])) / candle_range
                lower_wick = (min(last_candle["open"], last_candle["close"]) - last_candle["low"]) / candle_range
                
                # Bull trap: long upper wick at resistance
                if upper_wick > 0.6 and price >= high_20 * 0.98:
                    trap_type = "BULL_TRAP"
                    confidence = max(confidence, 50)
                    description = "🪤 BULL TRAP - Long upper wick rejection"
                
                # Bear trap: long lower wick at support
                elif lower_wick > 0.6 and price <= low_20 * 1.02:
                    trap_type = "BEAR_TRAP"
                    confidence = max(confidence, 50)
                    description = "🪤 BEAR TRAP - Long lower wick rejection"

        # Return result
        if trap_type == "NONE":
            return {
                "status": "✅ NO TRAP",
                "trap_type": "NONE",
                "confidence": 100,
                "description": "No trap patterns detected"
            }
        else:
            return {
                "status": f"🪤 {trap_type.replace('_', ' ')} [{confidence}%]",
                "trap_type": trap_type,
                "confidence": confidence,
                "description": description
            }

    except Exception as e:
        print(f"❌ TRAP DETECTOR ERROR: {e}")
        return {
            "status": "⚠️ ERROR",
            "trap_type": "ERROR",
            "confidence": 0,
            "description": f"Error in trap detection: {e}"
        }


# ================================================
# 🧠 AI BRAIN ENGINE (Enhanced)
# ================================================

def ai_brain(candles):
    """
    AI Brain engine for directional bias.
    
    Enhanced with:
    - Multiple timeframe analysis
    - Momentum integration
    - Improved confidence scoring
    
    Args:
        candles (list): List of candle dictionaries
    
    Returns:
        dict: Directional scores and confidence
    """
    try:
        if len(candles) < 100:
            return {
                "direction": "WAIT",
                "confidence": 0,
                "long_score": 0,
                "short_score": 0,
                "momentum_boost": 0,
                "trend_strength": 0
            }

        closes = [x["close"] for x in candles]
        highs = [x["high"] for x in candles]
        lows = [x["low"] for x in candles]
        price = closes[-1]

        # ====== TECHNICAL INDICATORS ======
        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        e100 = ema(closes, 100)
        e200 = ema(closes, 200) if len(closes) >= 200 else e100
        
        # RSI and momentum
        current_rsi = rsi(closes)
        
        # Calculate price velocity (momentum)
        if len(closes) >= 10:
            price_change_5 = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if closes[-5] > 0 else 0
            price_change_10 = ((closes[-1] - closes[-10]) / closes[-10]) * 100 if closes[-10] > 0 else 0
            price_velocity = (price_change_5 * 0.6) + (price_change_10 * 0.4)
        else:
            price_velocity = 0

        # ====== CALCULATE SCORES ======
        long_score = 0
        short_score = 0
        confidence_boost = 0

        # 1. Price vs EMAs (weight: 25 each)
        if price > e20:
            long_score += 25
        else:
            short_score += 25

        if e20 > e50:
            long_score += 20
        else:
            short_score += 20

        if e50 > e100:
            long_score += 20
        else:
            short_score += 20

        if len(closes) >= 200:
            if e100 > e200:
                long_score += 15
            else:
                short_score += 15

        # 2. Trend strength and direction (weight: 20)
        if price > e20 > e50 > e100:
            long_score += 20
            confidence_boost += 10
        elif price < e20 < e50 < e100:
            short_score += 20
            confidence_boost += 10

        # 3. RSI contribution (weight: 15)
        if 45 <= current_rsi <= 65:
            long_score += 10
            short_score += 10
            confidence_boost += 5
        elif current_rsi > 65:
            long_score += 5
        elif current_rsi < 35:
            short_score += 5

        # 4. Momentum contribution (weight: 15)
        if price_velocity > 0.5:
            long_score += 15
            confidence_boost += 5
        elif price_velocity < -0.5:
            short_score += 15
            confidence_boost += 5

        # 5. EMA slope (weight: 10)
        if len(closes) >= 10:
            e20_old = ema(closes[:-5], 20)
            if e20 > e20_old:
                long_score += 10
            elif e20 < e20_old:
                short_score += 10

        # 6. Volatility normalization (bonus)
        atr_val = atr(candles[-14:])
        normalized_volatility = (atr_val / price) * 100 if price > 0 else 0
        if normalized_volatility < 1:
            long_score += 5
            short_score += 5  # Low volatility favors both directions

        # ====== CALCULATE CONFIDENCE ======
        score_difference = abs(long_score - short_score)
        total_score = long_score + short_score
        
        if total_score > 0:
            confidence = (score_difference / total_score) * 100 + confidence_boost
        else:
            confidence = 0
            
        # Cap confidence at 100
        confidence = min(100, confidence)

        # ====== TREND STRENGTH ======
        # Calculate trend strength based on EMA alignment and slope
        trend_strength = 0
        if len(closes) >= 10:
            slope20 = (e20 - ema(closes[:-5], 20)) / e20 if e20 > 0 else 0
            slope50 = (e50 - ema(closes[:-5], 50)) / e50 if e50 > 0 else 0
            avg_slope = (abs(slope20) + abs(slope50)) / 2
            trend_strength = min(100, avg_slope * 500)

        # ====== DETERMINE DIRECTION ======
        # Higher threshold for stronger signals
        if long_score >= 65 and long_score > short_score + 15:
            direction = "🟢 LONG"
        elif short_score >= 65 and short_score > long_score + 15:
            direction = "🔴 SHORT"
        elif long_score >= 55 and long_score > short_score:
            direction = "🟢 LONG"
        elif short_score >= 55 and short_score > long_score:
            direction = "🔴 SHORT"
        else:
            direction = "WAIT"
            # If waiting, check if we're close to a signal
            if abs(long_score - short_score) < 15 and max(long_score, short_score) > 50:
                direction = "⏳ NEAR SIGNAL"

        return {
            "direction": direction,
            "confidence": round(confidence, 1),
            "long_score": long_score,
            "short_score": short_score,
            "momentum_boost": round(price_velocity, 2),
            "trend_strength": round(trend_strength, 1),
            "rsi": round(current_rsi, 1),
            "ema_alignment": "BULLISH" if e20 > e50 > e100 else "BEARISH" if e20 < e50 < e100 else "MIXED"
        }

    except Exception as e:
        print(f"❌ AI BRAIN ERROR: {e}")
        return {
            "direction": "WAIT",
            "confidence": 0,
            "long_score": 0,
            "short_score": 0,
            "momentum_boost": 0,
            "trend_strength": 0,
            "rsi": 50,
            "ema_alignment": "UNKNOWN"
        }


print(f"🧠 AI Engines PART 2 LOADED 🐋")

# ================================================
# 🎯 SECTION 5: ANALYZE ENGINE
# ================================================

# ================================================
# 🔧 HELPER FUNCTIONS FOR ANALYZE
# ================================================

def _validate_candles_data(c15, c1h, c4h, c1d, symbol, debug=None):
    """Validate that all required candle data is available"""
    if len(c15) < 60 or len(c1h) < 60 or len(c4h) < 60 or len(c1d) < 60:
        if debug is not None:
            debug["candles"] = debug.get("candles", 0) + 1
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"]["Insufficient Candles"] = debug["reject_reasons"].get("Insufficient Candles", 0) + 1
        return False, "Insufficient Candles"
    return True, None


def _check_blocked_assets(symbol, debug=None):
    """Check if symbol is in blocked assets list"""
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
        if debug is not None:
            debug["blocked"] = debug.get("blocked", 0) + 1
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"]["Blocked Asset"] = debug["reject_reasons"].get("Blocked Asset", 0) + 1
        return True, "Blocked Asset"
    return False, None


def _quick_filters(symbol, c15, c1h, c4h, debug=None):
    """
    Apply quick filters before heavy analysis.
    Returns: (is_valid, reject_reason, brain, direction, c15, c1h, c4h)
    """
    # Check candles
    valid, reason = _validate_candles_data(c15, c1h, c4h, c1d=[], symbol=symbol, debug=debug)
    if not valid:
        return False, reason, None, None, None, None, None
    
    # Check blocked assets
    blocked, reason = _check_blocked_assets(symbol, debug=debug)
    if blocked:
        return False, reason, None, None, None, None, None
    
    # Get price
    price = c15[-1]["close"]
    closes15 = [x["close"] for x in c15]
    closes1h = [x["close"] for x in c1h]
    closes4h = [x["close"] for x in c4h]
    
    # Smart Money flow check
    money = smart_money(c15)
    flow = money["flow"]
    if flow < 0.8:
        if debug is not None:
            debug["flow"] = debug.get("flow", 0) + 1
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"]["Low Flow"] = debug["reject_reasons"].get("Low Flow", 0) + 1
        return False, "Low Flow", None, None, None, None, None
    
    # AI Brain check
    brain = ai_brain(c1h)
    if brain["direction"] == "WAIT":
        if debug is not None:
            debug["brain"] = debug.get("brain", 0) + 1
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"]["Brain WAIT"] = debug["reject_reasons"].get("Brain WAIT", 0) + 1
        return False, "Brain WAIT", None, None, None, None, None
    
    direction = brain["direction"].replace("🟢 ", "").replace("🔴 ", "")
    
    # FOMO Filter
    safe, warning_text, fomo_reason = fomo_filter(c15, direction)
    if not safe:
        if debug is not None:
            debug["fomo"] = debug.get("fomo", 0) + 1
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"][f"FOMO: {fomo_reason}"] = debug["reject_reasons"].get(f"FOMO: {fomo_reason}", 0) + 1
        return False, f"FOMO: {fomo_reason}", None, None, None, None, None
    
    # Higher timeframe trend check
    e200_4h = ema(closes4h, 200)
    if direction == "LONG":
        if closes4h[-1] < e200_4h:
            if debug is not None:
                debug["higher_trend"] = debug.get("higher_trend", 0) + 1
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"]["Higher Trend Down"] = debug["reject_reasons"].get("Higher Trend Down", 0) + 1
            return False, "Higher Trend Down", None, None, None, None, None
    else:  # SHORT
        if closes4h[-1] > e200_4h:
            if debug is not None:
                debug["higher_trend"] = debug.get("higher_trend", 0) + 1
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"]["Higher Trend Up"] = debug["reject_reasons"].get("Higher Trend Up", 0) + 1
            return False, "Higher Trend Up", None, None, None, None, None
    
    return True, None, brain, direction, money, closes15, closes1h, closes4h


def _calculate_late_score(direction, price, closes15, move, debug=None):
    """
    Calculate late entry score with symmetric logic for LONG and SHORT.
    """
    late_score = 0
    ema20_15 = ema(closes15, 20)
    ema50_15 = ema(closes15, 50)
    ema100_15 = ema(closes15, 100)
    
    if direction == "LONG":
        # Distance from EMA50 (penalty if too far above)
        distance = price - ema50_15
        if distance > move * 0.5:
            late_score += 20
        if distance > move * 1.0:
            late_score += 20
        
        # EMA alignment bonus
        if ema20_15 > ema50_15 > ema100_15:
            late_score -= 10
        if price > ema20_15:
            late_score -= 5
        
        # Recent pump penalty
        last3_gain = ((closes15[-1] - closes15[-4]) / closes15[-4]) if closes15[-4] > 0 else 0
        if last3_gain > 0.06:
            late_score += 15
            
    else:  # SHORT (symmetric logic)
        # Distance from EMA50 (penalty if too far below)
        distance = ema50_15 - price
        if distance > move * 0.5:
            late_score += 20
        if distance > move * 1.0:
            late_score += 20
        
        # EMA alignment bonus (symmetric)
        if ema20_15 < ema50_15 < ema100_15:
            late_score -= 10
        if price < ema20_15:
            late_score -= 5
        
        # Recent dump penalty
        last3_loss = ((closes15[-4] - closes15[-1]) / closes15[-4]) if closes15[-4] > 0 else 0
        if last3_loss > 0.06:
            late_score += 15
    
    late_score = max(0, late_score)
    
    # Check if too late
    if late_score >= 35:
        if debug is not None:
            debug["late_entry"] = debug.get("late_entry", 0) + 1
            debug["late_score"] = late_score
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"]["Late Entry"] = debug["reject_reasons"].get("Late Entry", 0) + 1
        return False, late_score, None
    else:
        if debug is not None:
            debug["late_score"] = late_score
        return True, late_score, None


def _calculate_advanced_metrics(c15, c1h, c4h, direction, flow, money):
    """Calculate all advanced metrics for scoring"""
    # Get indicators
    sr = support_resistance(c15)
    pre = pre_pump_engine(c15)
    multi = multi_rsi_engine(c15, c1h, c4h, [])
    trap = trap_detector(c15)
    vol = volatility_engine(c15)
    regime = market_regime(c15, vol["score"])
    
    closes15 = [x["close"] for x in c15]
    closes1h = [x["close"] for x in c1h]
    closes4h = [x["close"] for x in c4h]
    
    rsi_15m = rsi(closes15)
    rsi_1h = rsi(closes1h)
    rsi_4h = rsi(closes4h)
    
    # Momentum calculations
    if len(closes15) >= 10:
        price_change_5 = ((closes15[-1] - closes15[-5]) / closes15[-5]) * 100 if closes15[-5] > 0 else 0
        price_change_10 = ((closes15[-1] - closes15[-10]) / closes15[-10]) * 100 if closes15[-10] > 0 else 0
        price_velocity = (price_change_5 * 0.6) + (price_change_10 * 0.4)
    else:
        price_velocity = 0
    
    volume_acceleration = money.get("volume_acceleration", 0)
    
    # Breakout strength
    recent_high = max([x["high"] for x in c15[-20:]])
    recent_low = min([x["low"] for x in c15[-20:]])
    range_width = recent_high - recent_low
    price = closes15[-1]
    if range_width > 0:
        breakout_strength = ((price - recent_low) / range_width) * 100
    else:
        breakout_strength = 50
    
    return {
        "sr": sr,
        "pre": pre,
        "multi": multi,
        "trap": trap,
        "vol": vol,
        "regime": regime,
        "rsi_15m": rsi_15m,
        "rsi_1h": rsi_1h,
        "rsi_4h": rsi_4h,
        "price_velocity": price_velocity,
        "volume_acceleration": volume_acceleration,
        "breakout_strength": breakout_strength,
        "flow": flow
    }


def _calculate_score(metrics, direction, flow_score, brain, debug=None):
    """
    Calculate final score with all components.
    """
    sr = metrics["sr"]
    trap = metrics["trap"]
    multi = metrics["multi"]
    rsi_15m = metrics["rsi_15m"]
    vol = metrics["vol"]
    regime = metrics["regime"]
    flow = metrics["flow"]
    price_velocity = metrics["price_velocity"]
    volume_acceleration = metrics["volume_acceleration"]
    breakout_strength = metrics["breakout_strength"]
    
    score = 0
    warning_text = ""
    
    # ====== RSI Score ======
    rsi_score = 0
    if 45 <= rsi_15m <= 62:
        rsi_score = 8
    elif 62 < rsi_15m <= 70:
        rsi_score = 5
        warning_text = "⚠️ RSI WARNING"
    elif rsi_15m > 70 or rsi_15m < 35:
        rsi_score = -10
        warning_text = "⚠️ RSI EXTREME"
    
    # ====== Flow Score ======
    if flow >= 3:
        flow_score_calc = 25
    elif flow >= 1.8:
        flow_score_calc = 20
    elif flow >= 1.2:
        flow_score_calc = 10
    else:
        flow_score_calc = 5
    
    # ====== MACD Score ======
    closes15 = [x["close"] for x in metrics.get("candles_15", [])]
    if closes15:
        macd_value = macd_simple(closes15)
        macd_score = 3 if macd_value > 0 else 0
    else:
        macd_score = 0
    
    # ====== Momentum Score ======
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
    
    # ====== Momentum Weight ======
    if regime["regime"] == "TRENDING":
        momentum_weight = 1.5
    elif regime["regime"] == "COMPRESSION":
        momentum_weight = 0.8
    else:
        momentum_weight = 1.0
    
    # ====== FINAL SCORE ======
    score += brain["confidence"] * 0.3
    score += flow_score_calc * 1.5
    score += (momentum_score * 0.2) * momentum_weight
    score += vol["bonus"]
    
    # Support/Resistance bonus
    if direction == "LONG":
        if sr["near_resistance"] > 5:
            score += 10
        elif sr["near_resistance"] > 3:
            score += 5
    else:
        if sr["near_support"] > 5:
            score += 10
        elif sr["near_support"] > 3:
            score += 5
    
    # Trap bonus
    if trap["trap_type"] == "NONE":
        score += 10
    
    # Multi RSI
    score += multi["score"] * 0.1
    
    # Direction-specific adjustments
    if direction == "LONG":
        score += rsi_score * 0.5
        score += macd_score * 0.5
    else:
        if 35 <= rsi_15m <= 55:
            score += 8
        elif 25 <= rsi_15m < 35:
            score += 5
        elif rsi_15m < 25 or rsi_15m > 65:
            score -= 10
        macd_short_score = 3 if macd_value < 0 else 0
        score += macd_short_score * 0.5
    
    # Late entry penalty
    late_penalty = 0
    if direction == "LONG":
        if rsi_15m >= 68:
            late_penalty += 20
    else:
        if rsi_15m <= 32:
            late_penalty += 20
    score -= late_penalty
    
    # Pump/Dump penalty
    closes15_full = [x["close"] for x in metrics.get("candles_15_full", [])]
    if len(closes15_full) >= 6:
        if direction == "LONG":
            pump = closes15_full[-1] / closes15_full[-6]
            if pump > 1.05:
                score -= 15
        else:
            dump = closes15_full[-6] / closes15_full[-1]
            if dump > 1.05:
                score -= 15
    
    # Higher timeframe RSI penalties
    if direction == "LONG":
        if metrics["rsi_4h"] > 70:
            score -= 10
        if metrics.get("rsi_1d", 50) > 70:
            score -= 10
        if rsi_15m > 75:
            score -= 5
    else:
        if metrics["rsi_4h"] < 30:
            score -= 10
        if metrics.get("rsi_1d", 50) < 30:
            score -= 10
        if rsi_15m < 25:
            score -= 5
    
    score = round(max(0, min(100, score)))
    
    return {
        "score": score,
        "momentum_score": momentum_score,
        "momentum_status": momentum_status,
        "momentum_weight": momentum_weight,
        "flow_score": flow_score_calc,
        "rsi_score": rsi_score,
        "warning_text": warning_text,
        "macd_value": macd_value
    }


def _calculate_entry_targets(direction, price, move, flow, momentum_score, money_status, regime):
    """Calculate entry, SL, and TP levels"""
    entry_low = price * 0.995
    entry_high = price * 1.005
    
    # RR multiplier based on regime and conditions
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
    
    if direction == "LONG":
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
        
        rr = (tp1 - entry_low) / risk if risk > 0 else 0
        
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
        
        rr = (entry_high - tp1) / risk if risk > 0 else 0
    
    return {
        "entry_low": entry_low,
        "entry_high": entry_high,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr": rr,
        "rr_multiplier": rr_multiplier
    }


def _validate_trade_levels(symbol, sector, direction, entry_low, entry_high, sl, tp1, tp2, tp3, rr, debug=None):
    """Validate all trade levels before returning signal"""
    blocked_assets = [
        "TSLA", "AMZN", "AAPL", "NVDA", "META", "GOOGL", "MSFT", "NFLX",
        "AMD", "COIN", "MSTR", "BABA", "PLTR", "HOOD",
        "SPX", "NASDAQ", "DOW",
        "XAU", "XAG", "WTI", "BRENT",
        "EUR", "GBP", "JPY", "AUD", "CAD", "CHF",
        "USDT_ETF", "BTC_ETF", "ETH_ETF"
    ]
    
    base = symbol.split("-")[0]
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
    if rr < MIN_RR:
        validation_errors.append(f"RR must be >= {MIN_RR}")
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
    
    if validation_errors:
        if debug is not None:
            debug["validation"] = debug.get("validation", 0) + 1
            debug.setdefault("reject_reasons", {})
            debug["reject_reasons"][f"Validation Failed: {', '.join(validation_errors)}"] = debug["reject_reasons"].get(f"Validation Failed: {', '.join(validation_errors)}", 0) + 1
        return False, validation_errors
    
    return True, None


# ================================================
# 🎯 MAIN ANALYZE FUNCTION
# ================================================

def analyze(symbol, sector, debug=None):
    """
    Main analysis function for trading signals.
    
    Args:
        symbol (str): Trading symbol
        sector (str): Sector of the coin
        debug (dict): Debug dictionary for collecting statistics
    
    Returns:
        dict: Signal data or None if no signal
    """
    try:
        # Initialize debug if provided
        if debug is not None:
            debug["checked"] = debug.get("checked", 0) + 1
        
        # ====== STEP 1: GET CANDLES ======
        c15 = get_candles_cached(symbol, "15m")
        c1h = get_candles_cached(symbol, "1h")
        c4h = get_candles_cached(symbol, "4h")
        c1d = get_candles_cached(symbol, "1d")
        
        # ====== STEP 2: QUICK FILTERS ======
        valid, reject_reason, brain, direction, money, closes15, closes1h, closes4h = _quick_filters(
            symbol, c15, c1h, c4h, debug
        )
        if not valid:
            return None
        
        price = c15[-1]["close"]
        move = atr(c15)
        flow = money["flow"]
        
        # ====== STEP 3: LATE SCORE ======
        valid, late_score, late_reason = _calculate_late_score(
            direction, price, closes15, move, debug
        )
        if not valid:
            return None
        
        # ====== STEP 4: ADVANCED METRICS ======
        metrics = _calculate_advanced_metrics(
            c15, c1h, c4h, direction, flow, money
        )
        
        # Store candles for scoring
        metrics["candles_15"] = closes15
        metrics["candles_15_full"] = c15
        metrics["rsi_1d"] = rsi([x["close"] for x in c1d]) if len(c1d) > 0 else 50
        
        # ====== STEP 5: TRAP CHECK ======
        trap_type = metrics["trap"]["trap_type"]
        if trap_type == "BULL_TRAP" and direction == "LONG":
            if debug is not None:
                debug["trap"] = debug.get("trap", 0) + 1
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"]["Bull Trap"] = debug["reject_reasons"].get("Bull Trap", 0) + 1
            return None
        if trap_type == "BEAR_TRAP" and direction == "SHORT":
            if debug is not None:
                debug["trap"] = debug.get("trap", 0) + 1
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"]["Bear Trap"] = debug["reject_reasons"].get("Bear Trap", 0) + 1
            return None
        
        # ====== STEP 6: CALCULATE SCORE ======
        score_result = _calculate_score(metrics, direction, 0, brain, debug)
        score = score_result["score"]
        momentum_score = score_result["momentum_score"]
        momentum_status = score_result["momentum_status"]
        momentum_weight = score_result["momentum_weight"]
        flow_score = score_result["flow_score"]
        warning_text = score_result["warning_text"]
        
        # ====== STEP 7: SUPPORT/RESISTANCE DISTANCE ======
        sr = metrics["sr"]
        if direction == "LONG":
            distance_to_resistance = sr["near_resistance"] * price / 100
            if distance_to_resistance < move * 1.2:
                if debug is not None:
                    debug["resistance"] = debug.get("resistance", 0) + 1
                    debug.setdefault("reject_reasons", {})
                    debug["reject_reasons"]["Too Close Resistance"] = debug["reject_reasons"].get("Too Close Resistance", 0) + 1
                return None
        else:
            distance_to_support = sr["near_support"] * price / 100
            if distance_to_support < move * 1.2:
                if debug is not None:
                    debug["resistance"] = debug.get("resistance", 0) + 1
                    debug.setdefault("reject_reasons", {})
                    debug["reject_reasons"]["Too Close Support"] = debug["reject_reasons"].get("Too Close Support", 0) + 1
                return None
        
        # ====== STEP 8: CHECK MINIMUM SCORE ======
        if score < MIN_SCORE:
            if debug is not None:
                debug["score"] = debug.get("score", 0) + 1
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"][f"Low Score ({score})"] = debug["reject_reasons"].get(f"Low Score ({score})", 0) + 1
            return None
        
        # ====== STEP 9: CALCULATE ENTRY & TARGETS ======
        money_status = "NORMAL"
        if flow >= 3:
            money_status = "🚀 HIGH WHALE FLOW"
        elif flow >= 2:
            money_status = "🐋 INSTITUTIONAL FLOW"
        elif flow >= 1.2:
            money_status = "💧 HEALTHY FLOW"
        
        entry_targets = _calculate_entry_targets(
            direction, price, move, flow, momentum_score, money_status, metrics["regime"]
        )
        
        # ====== STEP 10: VALIDATE ======
        valid, errors = _validate_trade_levels(
            symbol, sector,
            entry_targets["entry_low"], entry_targets["entry_high"],
            entry_targets["sl"], entry_targets["tp1"],
            entry_targets["tp2"], entry_targets["tp3"],
            entry_targets["rr"], debug
        )
        if not valid:
            return None
        
        # ====== STEP 11: QUALITY & RANKING ======
        brain_conf = brain["confidence"]
        rr = entry_targets["rr"]
        
        if score >= 95 and brain_conf >= 80 and rr >= 3.0 and momentum_score >= 85 and flow >= 2.0:
            quality = "💎 ELITE SETUP"
            quality_grade = "ELITE"
        elif score >= 90 and brain_conf >= 70 and rr >= 2.5:
            quality = "🔥 PREMIUM SETUP"
            quality_grade = "PREMIUM"
        elif score >= 80 and brain_conf >= 60:
            quality = "✅ HIGH QUALITY"
            quality_grade = "HIGH"
        elif score >= 70:
            quality = "⚡ GOOD SETUP"
            quality_grade = "GOOD"
        else:
            quality = "👀 WATCHLIST"
            quality_grade = "WATCHLIST"
            if debug is not None:
                debug["watchlist"] = debug.get("watchlist", 0) + 1
                debug.setdefault("reject_reasons", {})
                debug["reject_reasons"]["Watchlist Only"] = debug["reject_reasons"].get("Watchlist Only", 0) + 1
            return None
        
        # ====== STEP 12: FLOW RATING ======
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
        
        # ====== STEP 13: RISK GRADE ======
        if rr >= 3.0 and brain_conf >= 70 and score >= 85:
            risk_grade = "🟢 LOW RISK"
            risk_icon = "🟢"
        elif rr >= 2.0 and brain_conf >= 50 and score >= 70:
            risk_grade = "🟡 MEDIUM RISK"
            risk_icon = "🟡"
        else:
            risk_grade = "🔴 HIGH RISK"
            risk_icon = "🔴"
        
        # ====== STEP 14: CONFIDENCE LEVEL ======
        if score >= 85:
            confidence_level = "🔥 HIGH"
        elif score >= 70:
            confidence_level = "⚡ MEDIUM"
        else:
            confidence_level = "⏳ LOW"
        
        # ====== STEP 15: RANKING SCORE ======
        ranking_score = (
            score * 0.40 +
            brain_conf * 0.25 +
            rr * 10 +
            max(flow, 0.5) * 8 +
            momentum_score * 0.05
        )
        
        # ====== STEP 16: DECISION SUMMARY ======
        decision_reasons = []
        
        if metrics["regime"]["regime"] in ["TRENDING", "COMPRESSION"]:
            decision_reasons.append("✅ Strong Market Structure")
        else:
            decision_reasons.append("📊 Neutral Market Structure")
        
        if momentum_score >= 70:
            decision_reasons.append("✅ Strong Momentum")
        elif momentum_score >= 50:
            decision_reasons.append("⚡ Moderate Momentum")
        else:
            decision_reasons.append("📉 Weak Momentum")
        
        if flow >= 1.5:
            decision_reasons.append("✅ Institutional Flow")
        else:
            decision_reasons.append("📊 Normal Flow")
        
        if rr >= 2.5:
            decision_reasons.append("✅ High Risk/Reward")
        else:
            decision_reasons.append("📊 Standard RR")
        
        if brain_conf >= 60:
            decision_reasons.append("✅ High Brain Confidence")
        else:
            decision_reasons.append("📊 Moderate Brain Confidence")
        
        if metrics["vol"]["status"] in ["🔥 SPRING LOADED", "⚡ BUILDING PRESSURE"]:
            decision_reasons.append("✅ Compression Setup")
        else:
            decision_reasons.append("📊 Normal Volatility")
        
        if trap_type == "NONE":
            decision_reasons.append("✅ No Trap Detected")
        
        if late_score < 20:
            decision_reasons.append("✅ Early Entry Zone")
        elif late_score < 30:
            decision_reasons.append("⚡ Moderate Entry Zone")
        else:
            decision_reasons.append("⏳ Late Entry Warning")
        
        if sector not in ["UNKNOWN", "RWA"]:
            decision_reasons.append("✅ Strong Sector")
        
        decision_summary = "\n".join(decision_reasons)
        
        # ====== STEP 17: MARKET TEMPERATURE ======
        temp_score = (flow * 20) + (brain_conf * 0.3) + (metrics["vol"]["score"] * 0.2)
        if temp_score > 80:
            market_temperature = "🔴 OVERHEATED"
        elif temp_score > 60:
            market_temperature = "🟠 HOT"
        elif temp_score > 40:
            market_temperature = "🟡 WARM"
        else:
            market_temperature = "🟢 COLD"
        
        # ====== STEP 18: TRADE DATA ======
        trade_data = {
            'symbol': symbol,
            'side': direction,
            'signal_time': datetime.now(),
            'entry': round(entry_targets["entry_low"], 6),
            'sl': round(entry_targets["sl"], 6),
            'tp1': round(entry_targets["tp1"], 6),
            'tp2': round(entry_targets["tp2"], 6),
            'tp3': round(entry_targets["tp3"], 6),
            'sector': sector,
            'score': round(score),
            'brain_long': brain['long_score'],
            'brain_short': brain['short_score'],
            'flow': round(flow, 2),
            'momentum': momentum_score,
            'rr': round(rr, 2),
            'confidence': confidence_level,
            'late_score': late_score,
            'version': VERSION,
            'brain_confidence': brain_conf,
            'market_regime': metrics["regime"]["regime"],
            'compression_score': metrics["vol"]["score"],
            'compression_status': metrics["vol"]["status"],
            'momentum_weight': round(momentum_weight, 2),
            'flow_score': flow_score,
            'volume_acceleration': round(metrics["volume_acceleration"], 2),
            'flow_rating': flow_rating,
            'risk_grade': risk_grade,
            'decision_summary': decision_summary,
            'ranking_score': round(ranking_score, 2),
            'quality_grade': quality_grade,
            'market_temperature': market_temperature
        }
        
        print(f"✅ SIGNAL ACCEPTED: {symbol} | {direction} | Score: {round(score)} | Flow: {round(flow,2)} | RR: {round(rr,2)}")
        
        # Increment passed counter
        if debug is not None:
            debug["passed"] = debug.get("passed", 0) + 1
        
        # ====== STEP 19: RETURN RESULT ======
        return {
            "coin": symbol,
            "sector": sector,
            "direction": brain["direction"],
            "score": round(score),
            "quality": quality,
            "confidence_level": confidence_level,
            "money_status": money_status,
            "early_text": "🐋 EARLY ENTRY AREA" if momentum_score >= 60 and flow >= 1.2 else "⏳ WAIT FOR ENTRY",
            "entry_low": round(entry_targets["entry_low"], 6),
            "entry_high": round(entry_targets["entry_high"], 6),
            "sl": round(entry_targets["sl"], 6),
            "tp1": round(entry_targets["tp1"], 6),
            "tp2": round(entry_targets["tp2"], 6),
            "tp3": round(entry_targets["tp3"], 6),
            "liquidity": flow,
            "pre_pump": metrics["pre"]["status"],
            "multi": metrics["multi"],
            "trap": metrics["trap"]["status"],
            "warning": warning_text,
            "volatility": metrics["vol"],
            "regime": metrics["regime"],
            "momentum_score": momentum_score,
            "momentum_status": momentum_status,
            "rr": round(rr, 2),
            "brain_long_score": brain["long_score"],
            "brain_short_score": brain["short_score"],
            "late_score": late_score,
            "brain_confidence": brain_conf,
            "flow_rating": flow_rating,
            "flow_label": flow_label,
            "risk_grade": risk_grade,
            "risk_icon": risk_icon,
            "decision_summary": decision_summary,
            "ranking_score": round(ranking_score, 2),
            "quality_grade": quality_grade,
            "market_temperature": market_temperature,
            "trade_data": trade_data
        }
        
    except Exception as e:
        print(f"❌ ANALYZE ERROR: {symbol} - {e}")
        if debug is not None:
            debug["error"] = debug.get("error", 0) + 1
        return None


print(f"🎯 Analyze Engine LOADED 🐋")

# ================================================
# 🤖 SECTION 6: TELEGRAM COMMANDS + SCANNER
# ================================================

# ================================================
# 📋 FOOTER
# ================================================

FOOTER = f"""
━━━━━━━━━━━━━━━━━━━━━━
🤖 AHAD AI {VERSION}
🗄 PostgreSQL Production
🐋 Institutional Engine
📊 Production Stable
"""


# ================================================
# 📨 LONG MESSAGE SPLITTER
# ================================================

def send_long_message(chat_id, text, max_length=4000):
    """
    Send a long message by splitting it into multiple parts if needed.
    Telegram has a 4096 character limit per message.
    """
    if len(text) <= max_length:
        bot.send_message(chat_id, text)
        return
    
    # Split by lines to avoid cutting mid-word
    lines = text.split('\n')
    parts = []
    current_part = []
    current_length = 0
    
    for line in lines:
        line_length = len(line) + 1  # +1 for newline
        if current_length + line_length > max_length:
            parts.append('\n'.join(current_part))
            current_part = [line]
            current_length = line_length
        else:
            current_part.append(line)
            current_length += line_length
    
    if current_part:
        parts.append('\n'.join(current_part))
    
    for i, part in enumerate(parts):
        if len(parts) > 1:
            part = f"📄 Part {i+1}/{len(parts)}\n\n{part}"
        bot.send_message(chat_id, part)


# ================================================
# 🔒 SCAN LOCK
# ================================================

_scan_lock = threading.Lock()


def single_scan_only(handler):
    """Prevent overlapping scans from exhausting the API or duplicating signals."""
    @wraps(handler)
    def wrapper(message, *args, **kwargs):
        if not _scan_lock.acquire(blocking=False):
            bot.reply_to(message, "⏳ A scan is already running. Please wait for it to finish.")
            return None
        try:
            return handler(message, *args, **kwargs)
        finally:
            _scan_lock.release()
    return wrapper


# ================================================
# 🤖 COMMAND: /start
# ================================================

@bot.message_handler(commands=["start"])
@authorized_only
def start(message):
    total_trades = get_total_trades()
    reply = f"""
🐋 AHAD AI {VERSION} – Production Stable 🚀
📅 Build: {BUILD_DATE}
📈 Recorded Trades : {total_trades}

🗄 PostgreSQL Database ACTIVE ({VERSION})
💾 Trade Recorder ACTIVE (Duplicate Protection)
📈 Trade Tracker ACTIVE (With Backoff)
📊 Performance Analytics ACTIVE (Enhanced)
🧠 AI Brain v2.0 ACTIVE
🐋 Smart Money ACTIVE
📊 Multi TimeFrame ACTIVE
🪤 Trap Detector ACTIVE
⚡ Pre-Pump Detection ACTIVE
🔥 Heat Control ACTIVE
🎯 Dynamic Late Entry v3 ACTIVE
📊 Enhanced Score System ACTIVE
🐞 Advanced Debug System ACTIVE
🔥 Volatility Compression ACTIVE
📊 Market Regime & Compression ACTIVE
🚀 Enhanced Momentum Engine ACTIVE
📌 Reject Reason ACTIVE
🧠 Confidence Level ACTIVE
🎯 New RR Engine ACTIVE
📈 Higher Timeframe Filter v2 ACTIVE
✅ Dynamic Flow Scanner ACTIVE (With LIMIT)
🛡️ Validation Layer ACTIVE
📊 Brain LONG/SHORT Scores ACTIVE
🔄 Dual Direction Engine ACTIVE
🗄 PostgreSQL Production Ready
🔒 SSL Connection ENABLED
📊 8 Indexes for Performance
⏰ TIMESTAMP Support
📈 Professional Analytics ACTIVE
🏦 Institutional Dashboard ACTIVE
🏆 Professional Ranking Engine ACTIVE
💎 Quality Engine v2.0 ACTIVE
🏷️ Quality Grade System ACTIVE
📦 Caching System ACTIVE (With TTL)
🐞 UI Optimization ACTIVE
🌡️ Market Temperature ACTIVE
📋 Enhanced Signal Layout ACTIVE
📊 Grouped Decision Summary ACTIVE
⏱ Scan Duration Tracking ACTIVE
🔢 Scan History Counter ACTIVE
🏷️ Market Health Score ACTIVE

🎯 Goal: Best 2 LONG + Best 1 SHORT

Commands:
/scan – Run scanner with Institutional Dashboard
/report – Performance report
/open – Open trades list
/history – Last 10 closed trades
{FOOTER}
"""
    bot.reply_to(message, reply)


# ================================================
# 🤖 COMMAND: /scan
# ================================================

@bot.message_handler(commands=["scan"])
@authorized_only
@single_scan_only
def scan(message):
    # ====== SHORT STARTUP MESSAGE ======
    bot.reply_to(message, f"""
🐋 AHAD AI {VERSION}

🚀 Smart Market Scan Started

📅 Build : {BUILD_DATE}
🧠 AI Brain ACTIVE
🐋 Smart Money ACTIVE
🌍 Market Intelligence ACTIVE

⏳ Please wait...
{FOOTER}
""")

    # Clear expired cache
    clear_expired_cache()

    debug = {}
    debug["reject_reasons"] = {}

    long_results = []
    short_results = []
    all_symbols = get_symbols()

    if DEBUG_MODE:
        print("🔍 DEBUG: After get_symbols() -", len(all_symbols), "symbols found")

    # Get top flow symbols
    symbols, flow_candidates = top_flow_scanner(all_symbols)
    if DEBUG_MODE:
        print("🔍 DEBUG: After top_flow_scanner() -", len(symbols), "symbols selected,", flow_candidates, "flow candidates")

    # Get sector flow
    flow = sector_flow(all_symbols)
    if DEBUG_MODE:
        print("🔍 DEBUG: After sector_flow()")

    ranking = flow["ranking"]

    # Initialize sector data
    sector_data = {sector: {"coins": 0, "flows": [], "scores": []} for sector in SECTORS.keys()}

    # If not enough symbols, expand
    if len(symbols) < 20:
        symbols = all_symbols
        if DEBUG_MODE:
            print("🔍 DEBUG: Symbols expanded to", len(symbols))

    # Statistics collectors
    market_regimes = {}
    market_flows = []
    market_brain_scores = []
    market_compression_status = []

    scan_start_time = time.time()
    scan_start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    api_calls = 0
    cache_hits = 0
    coin_times = []

    market_universe = len(all_symbols)
    flow_candidates_count = flow_candidates
    analyzed_count = len(symbols)
    scan_limit = MAX_SCAN_LIMIT

    if DEBUG_MODE:
        print("🔍 DEBUG: Before for symbol in symbols loop -", len(symbols), "symbols to analyze")

    # ====== MAIN ANALYSIS LOOP ======
    for symbol in symbols:
        coin_start = time.time()
        
        if DEBUG_MODE:
            print("=" * 50)
            print(f"START: {symbol}")

        base = symbol.split("-")[0]
        coin_sector = "UNKNOWN"
        for sector, coins in SECTORS.items():
            if base in coins:
                coin_sector = sector
                break

        # Track cache usage
        key = f"{symbol}_15m"
        if key in _candle_cache:
            cache_hits += 1
        else:
            api_calls += 1

        # Analyze
        result = analyze(symbol, coin_sector, debug=debug)

        coin_end = time.time()
        coin_duration = round((coin_end - coin_start) * 1000, 2)
        coin_times.append((symbol, coin_duration))

        if DEBUG_MODE:
            print(f"END: {symbol}")

        # Update sector data
        if result and coin_sector in sector_data:
            sector_data[coin_sector]["coins"] += 1
            sector_data[coin_sector]["flows"].append(result.get("liquidity", 0))
            sector_data[coin_sector]["scores"].append(result.get("score", 0))

        # Process result
        if result:
            if result["score"] > 100:
                result["score"] = 100

            regime_name = result["regime"]["regime"]
            market_regimes[regime_name] = market_regimes.get(regime_name, 0) + 1
            market_flows.append(result["liquidity"])
            market_brain_scores.append(result["brain_confidence"])
            market_compression_status.append(result["volatility"]["status"])

            debug.setdefault("regimes", {})
            debug["regimes"][regime_name] = debug["regimes"].get(regime_name, 0) + 1

            compression_name = result["volatility"]["status"]
            debug.setdefault("compressions", {})
            debug["compressions"][compression_name] = debug["compressions"].get(compression_name, 0) + 1

            # Filter and add to results
            if result["direction"] == "🟢 LONG":
                if result["score"] >= 68 and (result["liquidity"] >= 1.2 or result["pre_pump"] == "🐋 WHALE LOADING"):
                    long_results.append(result)
                    if DEBUG_MODE:
                        print(f"✅ LONG ACCEPTED: {result['coin']} | Score: {result['score']} | Flow: {result['liquidity']}")
                else:
                    debug["final_gate"] = debug.get("final_gate", 0) + 1
                    reason = "Not Long"
                    debug.setdefault("reject_reasons", {})
                    debug["reject_reasons"][reason] = debug["reject_reasons"].get(reason, 0) + 1
                    if DEBUG_MODE:
                        print(f"❌ LONG REJECTED | {result['coin']} | Score={result['score']} | Flow={result['liquidity']}")

            elif result["direction"] == "🔴 SHORT":
                if result["score"] >= 68 and (result["liquidity"] >= 1.2 or result["pre_pump"] == "🐋 WHALE LOADING"):
                    short_results.append(result)
                    if DEBUG_MODE:
                        print(f"✅ SHORT ACCEPTED: {result['coin']} | Score: {result['score']} | Flow: {result['liquidity']}")
                else:
                    debug["final_gate"] = debug.get("final_gate", 0) + 1
                    reason = "Not Short"
                    debug.setdefault("reject_reasons", {})
                    debug["reject_reasons"][reason] = debug["reject_reasons"].get(reason, 0) + 1
                    if DEBUG_MODE:
                        print(f"❌ SHORT REJECTED | {result['coin']} | Score={result['score']} | Flow={result['liquidity']}")

        time.sleep(0.03)  # Rate limiting

    if DEBUG_MODE:
        print("🔍 DEBUG: After for symbol in symbols loop - completed")

    # ====== SECTOR SUMMARY ======
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

    # ====== METRICS ======
    all_results = long_results + short_results
    
    if market_flows:
        avg_flow = round(sum(market_flows) / len(market_flows), 2)
    else:
        avg_flow = 0

    if market_brain_scores:
        avg_brain = round(sum(market_brain_scores) / len(market_brain_scores), 1)
    else:
        avg_brain = 0

    has_signals = len(all_results) > 0
    
    if has_signals:
        avg_score = round(sum(r["score"] for r in all_results) / len(all_results), 2)
        avg_rr = round(sum(r["rr"] for r in all_results) / len(all_results), 2)
        avg_momentum = round(sum(r["momentum_score"] for r in all_results) / len(all_results), 2)
        
        metrics_display = f"""
📊 METRICS
Avg Final Score : {avg_score}
Avg Flow        : {avg_flow}
Avg Momentum    : {avg_momentum}
Avg RR          : {avg_rr}
Avg Brain       : {avg_brain}
"""
        debug["avg_score"] = avg_score
        debug["avg_rr"] = avg_rr
        debug["avg_momentum"] = avg_momentum
    else:
        metrics_display = """
📊 METRICS
N/A — No signals passed the final filters.
"""
        debug["avg_score"] = "N/A"
        debug["avg_rr"] = "N/A"
        debug["avg_momentum"] = "N/A"

    debug["avg_flow"] = avg_flow
    debug["avg_brain"] = avg_brain

    total_checked = debug.get('checked', 0)

    if DEBUG_MODE:
        print("🔍 DEBUG: Before building dashboard")

    # ====== MARKET HEALTH ======
    bull_pct = 0
    bear_pct = 0
    sideways_pct = 0
    compression_high_pct = 0
    market_health_score = 0
    health_icon = "🟡"

    if total_checked > 0:
        bull_pct = round((market_regimes.get("TRENDING", 0) / total_checked) * 100, 1)
        bear_pct = round((market_regimes.get("BEARISH", 0) / total_checked) * 100, 1)
        sideways_pct = round((market_regimes.get("RANGING", 0) / total_checked) * 100, 1)
        compression_pct = round((market_regimes.get("COMPRESSION", 0) / total_checked) * 100, 1)
        
        high_compression = sum(1 for s in market_compression_status if "SPRING LOADED" in s or "BUILDING" in s)
        compression_high_pct = round((high_compression / len(market_compression_status)) * 100, 1) if market_compression_status else 0
        
        # Calculate health score
        if bull_pct >= 60:
            market_health_score += 40
        elif bull_pct >= 40:
            market_health_score += 30
        elif bull_pct >= 20:
            market_health_score += 20
        else:
            market_health_score += 10
        
        if avg_flow >= 2.0:
            market_health_score += 30
        elif avg_flow >= 1.5:
            market_health_score += 20
        elif avg_flow >= 1.0:
            market_health_score += 10
        else:
            market_health_score += 5
        
        if avg_brain >= 70:
            market_health_score += 20
        elif avg_brain >= 50:
            market_health_score += 15
        elif avg_brain >= 30:
            market_health_score += 10
        else:
            market_health_score += 5
        
        if compression_high_pct >= 30:
            market_health_score += 10
        elif compression_high_pct >= 15:
            market_health_score += 5
        
        market_health_score = min(100, market_health_score)
        
        if market_health_score >= 70:
            health_icon = "🟢"
        elif market_health_score >= 40:
            health_icon = "🟡"
        else:
            health_icon = "🔴"

    # ====== TOP SECTORS ======
    top_sectors_display = ""
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
    
    if sector_summary:
        for idx, sector_data_item in enumerate(sector_summary[:6]):
            top_sectors_display += f"{medals[idx]} {sector_data_item['sector']:<8} Flow {sector_data_item['avg_flow']:.2f} | Score {sector_data_item['avg_score']:.1f}\n"
    else:
        top_sectors_display = "No sector data available."

    strongest_sector = sector_summary[0]['sector'] if sector_summary else "N/A"
    weakest_sector = sector_summary[-1]['sector'] if len(sector_summary) > 1 else "N/A"

    # ====== DASHBOARD MESSAGE ======
    dashboard_msg = f"""
🌍 AHAD AI MARKET DASHBOARD

❤️ Health Score : {market_health_score}/100
🌡 Temperature  : {avg_flow * 20 + avg_brain * 0.3:.0f}° 

🐋 Avg Flow     : {avg_flow:.2f}
🧠 Avg Brain    : {avg_brain:.1f}

🏆 Best Sector  : {strongest_sector}
📉 Weakest      : {weakest_sector}

📊 Top Sectors

{top_sectors_display}
{FOOTER}
"""
    bot.send_message(message.chat.id, dashboard_msg)

    # ====== REJECT REASONS ======
    if debug.get("reject_reasons") and len(debug["reject_reasons"]) > 0:
        all_rejects = sorted(
            debug["reject_reasons"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        top_rejects_list = all_rejects[:10]
        emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        top_rejects = "\n".join(
            f"{emojis[i]} {k} : {v}"
            for i, (k, v) in enumerate(top_rejects_list)
        )
        
        total_rejections = sum(debug["reject_reasons"].values())
        top_rejects = f"Total Rejections: {total_rejections}\n\n{top_rejects}"
        
        main_reject = all_rejects[0]
        main_reject_display = f"{main_reject[0]} ({main_reject[1]})"
    else:
        top_rejects = "N/A — No rejection data available."
        main_reject_display = "N/A"

    # ====== PERFORMANCE ======
    scan_end_time = time.time()
    scan_duration = round(scan_end_time - scan_start_time, 2)
    scan_end_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    total_calls = api_calls + cache_hits
    cache_saved_pct = round((cache_hits / total_calls) * 100, 1) if total_calls > 0 else 0
    
    debug["scan_duration"] = scan_duration
    debug["api_calls"] = api_calls
    debug["cache_hits"] = cache_hits
    debug["cache_saved_pct"] = cache_saved_pct

    if coin_times:
        avg_time = round(sum(t[1] for t in coin_times) / len(coin_times), 2)
        slowest = max(coin_times, key=lambda x: x[1])
        fastest = min(coin_times, key=lambda x: x[1])
        performance_display = f"""
⏱ Total Scan Time   : {scan_duration}s
📊 Average Analyze   : {avg_time}ms
🚀 Fastest Coin      : {fastest[0]} ({fastest[1]}ms)
🐢 Slowest Coin      : {slowest[0]} ({slowest[1]}ms)
"""
    else:
        performance_display = "⏱ No performance data available."

    # ====== CACHE STATUS ======
    if cache_hits == 0 and api_calls > 0:
        cache_display = "🧊 Cache Status : Cold Start (First Scan)"
    else:
        cache_display = f"""
API Calls       : {api_calls}
Cache Hits      : {cache_hits}
Cache Saved     : {cache_saved_pct}%
Cache TTL       : {CACHE_TTL}s
"""

    # ====== SCAN SUMMARY ======
    total_analyzed = debug.get('checked', 0)
    total_passed = debug.get('passed', 0)
    total_rejected = total_analyzed - total_passed
    
    decision_summary_display = f"""
📊 SCAN SUMMARY
Coins Analyzed  : {total_analyzed}
✅ Passed        : {total_passed}
❌ Rejected      : {total_rejected}
🎯 Main Reject   : {main_reject_display}
"""

    checked_count = debug.get('checked', 0)
    total_trades = get_total_trades()

    # ====== DEBUG REPORT ======
    debug_msg = f"""
🐞 FULL DEBUG REPORT ({VERSION})
🆔 Scan ID: #{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999):03d}
📅 Build: {BUILD_DATE}

━━━━━━━━━━━━━━━━━━━━━━
🕐 SCAN TIMESTAMPS
━━━━━━━━━━━━━━━━━━━━━━
Started         : {scan_start_timestamp}
Finished        : {scan_end_timestamp}
Duration        : {scan_duration}s

━━━━━━━━━━━━━━━━━━━━━━
📊 SCAN STATISTICS
━━━━━━━━━━━━━━━━━━━━━━
Market Universe : {market_universe} (All OKX USDT Futures)
Flow Candidates : {flow_candidates_count} (Flow ≥ 1.15x)
Analyzed        : {analyzed_count} (Top Flow Selection)
Scan Limit      : {scan_limit} (MAX_SCAN_LIMIT)

{decision_summary_display}

━━━━━━━━━━━━━━━━━━━━━━
❌ REJECTIONS
━━━━━━━━━━━━━━━━━━━━━━
Candles         : {debug.get('candles', 0)}
FOMO            : {debug.get('fomo', 0)}
Brain           : {debug.get('brain', 0)}
Low Flow        : {debug.get('flow', 0)}
Late Entry      : {debug.get('late_entry', 0)}
Late Score      : {debug.get('late_score', 0)}
Trap            : {debug.get('trap', 0)}
Resistance      : {debug.get('resistance', 0)}
Higher Trend    : {debug.get('higher_trend', 0)}
RR              : {debug.get('rr', 0)}
Score           : {debug.get('score', 0)}
Watchlist       : {debug.get('watchlist', 0)}
Validation      : {debug.get('validation', 0)}
Final Gate      : {debug.get('final_gate', 0)}
Error           : {debug.get('error', 0)}

━━━━━━━━━━━━━━━━━━━━━━
🏆 TOP REJECT REASONS (Sorted)
━━━━━━━━━━━━━━━━━━━━━━
{top_rejects}

━━━━━━━━━━━━━━━━━━━━━━
✅ RESULTS
━━━━━━━━━━━━━━━━━━━━━━
Passed          : {total_passed}
LONG Signals    : {len(long_results)}
SHORT Signals   : {len(short_results)}

{metrics_display}

━━━━━━━━━━━━━━━━━━━━━━
📈 MARKET REGIME DISTRIBUTION
━━━━━━━━━━━━━━━━━━━━━━
{debug.get('regime_distribution', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━
🔥 COMPRESSION DISTRIBUTION
━━━━━━━━━━━━━━━━━━━━━━
{debug.get('compression_distribution', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━
⚡ SCAN EFFICIENCY
━━━━━━━━━━━━━━━━━━━━━━
{cache_display}

━━━━━━━━━━━━━━━━━━━━━━
⚡ SCAN PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━
{performance_display}

📈 Recorded Trades : {total_trades}

{FOOTER}
"""
    send_long_message(message.chat.id, debug_msg)

    # ====== RANK SIGNALS ======
    def ranking_score(signal):
        return signal.get('ranking_score', 0)

    best_longs = sorted(
        long_results,
        key=ranking_score,
        reverse=True
    )[:2]

    best_shorts = sorted(
        short_results,
        key=ranking_score,
        reverse=True
    )[:1]

    results = best_longs + best_shorts

    for rank, signal in enumerate(results, start=1):
        signal["rank"] = rank

    if not results:
        bot.send_message(message.chat.id, f"""
🎯 No high-probability trading opportunity detected.

🐋 Institutional flow is currently insufficient.

⏳ Waiting for the next liquidity wave.

🎯 Main Reject Reason: {main_reject_display}
{FOOTER}
""")
        clear_expired_cache()
        return

    # ====== SIGNAL QUALITY SUMMARY ======
    if all_results:
        signal_quality = f"""
📊 SIGNAL QUALITY SUMMARY
Average Score       : {avg_score}
Average Confidence  : {avg_brain}%
Average RR          : {avg_rr}
Average Momentum    : {avg_momentum}
"""
        bot.send_message(message.chat.id, signal_quality)

    # ====== SEND SIGNALS ======
    for s in results:
        trade_id = None
        if s.get('trade_data'):
            try:
                trade_id = save_trade(s['trade_data'])
                if trade_id:
                    print(f"Trade #{trade_id} saved for {s['coin']}")
            except Exception as e:
                print(f"Error saving trade for {s['coin']}: {e}")

        brain_conf = s["brain_confidence"]

        if brain_conf >= 80:
            confidence_rank = "🔥 VERY HIGH"
        elif brain_conf >= 60:
            confidence_rank = "✅ HIGH"
        elif brain_conf >= 40:
            confidence_rank = "⚡ MEDIUM"
        else:
            confidence_rank = "⚠ LOW"

        msg = f"""
🚨 AHAD AI {VERSION} – Production Stable 🐋
📅 Build: {BUILD_DATE}

🏆 Rank #{s['rank']}
⭐ Ranking Score: {s['ranking_score']}

{s['direction']} | 🪙 {s['coin']}
🏦 Sector: {s['sector']}

━━━━━━━━━━━━━━━━━━━━━━

🎯 ENTRY PLAN
Entry      : {format_price(s['entry_low'])} - {format_price(s['entry_high'])}
Stop Loss  : {format_price(s['sl'])}
🥇 TP1     : {format_price(s['tp1'])}
🥈 TP2     : {format_price(s['tp2'])}
🥉 TP3     : {format_price(s['tp3'])}

━━━━━━━━━━━━━━━━━━━━━━

🏦 INSTITUTIONAL DASHBOARD
├─ AI Brain    : {brain_conf}/100 ({confidence_rank})
├─ Smart Money : {s['money_status']}
├─ Market      : {s['regime']['regime']}
├─ Momentum    : {s['momentum_score']}/100 ({s['momentum_status']})
├─ RR          : {s['rr']}
├─ Quality Grade: {s.get('quality_grade', 'N/A')}
├─ Ranking Score: {s.get('ranking_score', 0)}
└─ Risk        : {s['risk_grade']}

━━━━━━━━━━━━━━━━━━━━━━

🧠 AI BRAIN
📈 LONG Score  : {s['brain_long_score']}
📉 SHORT Score : {s['brain_short_score']}
🎯 Confidence  : {brain_conf}/100
🏆 Level       : {confidence_rank}

━━━━━━━━━━━━━━━━━━━━━━

📊 INSTITUTIONAL FLOW
Flow         : {s['liquidity']}X
Rating       : {s['flow_rating']}
Temperature  : {s.get('market_temperature', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━

📈 MARKET STATUS
Final Score   : {s['score']}/100
Trap Status   : {s['trap']}
Market Regime : {s['regime']['regime']}
Compression   : {s['volatility']['status']}
Late Entry    : {s['late_score']}

{s['warning']}

━━━━━━━━━━━━━━━━━━━━━━

💡 WHY THIS SIGNAL?
{s['decision_summary']}

━━━━━━━━━━━━━━━━━━━━━━

💾 Trade ID: #{trade_id if trade_id else 'N/A'}

{FOOTER}
"""

        # Fallback save if not saved earlier
        if not trade_id and s.get('trade_data'):
            try:
                trade_id = save_trade(s['trade_data'])
                if trade_id:
                    print(f"✅ Trade #{trade_id} saved for {s['coin']}")
                    msg = msg.replace("💾 Trade ID: #N/A", f"💾 Trade ID: #{trade_id}")
            except Exception as e:
                print(f"❌ Exception saving trade: {e}")

        bot.send_message(message.chat.id, msg)

    clear_expired_cache()
    if DEBUG_MODE:
        print("🔍 DEBUG: Scan completed successfully")


# ================================================
# 🤖 COMMAND: /report
# ================================================

@bot.message_handler(commands=['report'])
@authorized_only
def report_command(message):
    try:
        stats = get_report_stats()

        # Get additional summary statistics
        highest_ranking = "N/A"
        highest_brain = "N/A"
        highest_rr = "N/A"
        highest_quality = "N/A"
        
        try:
            with get_db_cursor(commit=False) as cur:
                cur.execute("""
                SELECT 
                    MAX(ranking_score) AS highest_ranking,
                    MAX(brain_confidence) AS highest_brain,
                    MAX(rr) AS highest_rr
                FROM trades
                WHERE status = 'CLOSED'
                """)
                
                row = cur.fetchone()
                if row:
                    highest_ranking = round(row[0], 2) if row[0] else "N/A"
                    highest_brain = round(row[1], 1) if row[1] else "N/A"
                    highest_rr = round(row[2], 2) if row[2] else "N/A"

                # Get most common quality grade
                cur.execute("""
                SELECT quality_grade, COUNT(*) AS count
                FROM trades
                WHERE status = 'CLOSED' AND quality_grade IS NOT NULL
                GROUP BY quality_grade
                ORDER BY count DESC
                LIMIT 1
                """)
                
                quality_row = cur.fetchone()
                if quality_row:
                    highest_quality = quality_row[0]

        except Exception as e:
            if DEBUG_MODE:
                print(f"❌ Report stats error: {e}")

        report = f"""
📊 AHAD AI PERFORMANCE REPORT ({VERSION})
📅 Build: {BUILD_DATE}
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

━━━━━━━━━━━━━━━━━━━━━━

📊 PERFORMANCE METRICS
📈 Avg Max Profit  : {stats['avg_max_profit']}%
📉 Avg Max DD      : {stats['avg_max_drawdown']}%
🏆 Best Trade      : {stats['best_trade']}%
⚠️ Worst Trade     : {stats['worst_trade']}%

━━━━━━━━━━━━━━━━━━━━━━

🏆 TOP PERFORMERS
Highest Ranking Score : {highest_ranking}
Highest Brain Conf    : {highest_brain}
Highest RR            : {highest_rr}
Top Quality Grade     : {highest_quality}

━━━━━━━━━━━━━━━━━━━━━━

🟢 LONG PERFORMANCE
Trades        : {stats['long_total']}
Wins          : {stats['long_wins']}
Losses        : {stats['long_losses']}
Win Rate      : {stats['long_win_rate']}%
Avg RR        : {stats['long_avg_rr']}
Avg Profit    : {stats['long_avg_profit']}%
Avg DD        : {stats['long_avg_dd']}%

━━━━━━━━━━━━━━━━━━━━━━

🔴 SHORT PERFORMANCE
Trades        : {stats['short_total']}
Wins          : {stats['short_wins']}
Losses        : {stats['short_losses']}
Win Rate      : {stats['short_win_rate']}%
Avg RR        : {stats['short_avg_rr']}
Avg Profit    : {stats['short_avg_profit']}%
Avg DD        : {stats['short_avg_dd']}%

{FOOTER}
"""
        bot.reply_to(message, report)

    except Exception as e:
        bot.reply_to(message, f"❌ Error generating report: {e}")


# ================================================
# 🤖 COMMAND: /open
# ================================================

@bot.message_handler(commands=['open'])
@authorized_only
def open_trades_command(message):
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
            SELECT 
                id, symbol, side, entry, tp1, tp2, tp3, sl, signal_time,
                brain_confidence, ranking_score, quality_grade
            FROM trades
            WHERE status = 'OPEN'
            ORDER BY id DESC
            """)

            rows = cur.fetchall()

            if not rows:
                bot.reply_to(message, f"📭 No open trades.\n{FOOTER}")
                return

            msg = f"📂 OPEN TRADES ({VERSION})\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

            for row in rows[:10]:
                quality = row[11] if row[11] else "--"
                brain = row[9] if row[9] else "--"
                ranking = row[10] if row[10] else "--"
                
                msg += f"#{row[0]} {row[1]} | {row[2]}\n"
                msg += f"Entry: {format_price(row[3])} | SL: {format_price(row[7])}\n"
                msg += f"TP1: {format_price(row[4])} | TP2: {format_price(row[5])} | TP3: {format_price(row[6])}\n"
                msg += f"Brain: {brain} | Ranking: {ranking}\n"
                msg += f"Quality: {quality}\n"
                msg += f"🕐 {row[8]}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

            msg += FOOTER
            bot.reply_to(message, msg)

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


# ================================================
# 🤖 COMMAND: /history
# ================================================

@bot.message_handler(commands=['history'])
@authorized_only
def history_command(message):
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
            SELECT 
                id, symbol, side, entry, result, 
                max_profit, max_drawdown, close_time,
                quality_grade, brain_confidence, ranking_score, rr
            FROM trades
            WHERE status = 'CLOSED'
            ORDER BY id DESC
            LIMIT 10
            """)

            rows = cur.fetchall()

            if not rows:
                bot.reply_to(message, f"📭 No closed trades yet.\n{FOOTER}")
                return

            msg = f"📜 TRADE HISTORY ({VERSION})\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

            for row in rows:
                result_icon = "✅" if "WIN" in row[4] else "❌"
                
                quality = row[8] if row[8] else "--"
                brain = row[9] if row[9] else "--"
                ranking = row[10] if row[10] else "--"
                rr = row[11] if row[11] else "--"
                
                msg += f"{result_icon} #{row[0]} {row[1]} | {row[2]}\n"
                msg += f"Entry: {format_price(row[3])} | Result: {row[4]}\n"
                msg += f"Max Profit: {row[5]}% | Max DD: {row[6]}%\n"
                msg += f"Quality: {quality} | Brain: {brain}\n"
                msg += f"Ranking: {ranking} | RR: {rr}\n"
                msg += f"🕐 {row[7] if row[7] else 'N/A'}\n"
                msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

            msg += FOOTER
            bot.reply_to(message, msg)

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


print(f"🤖 Telegram Commands LOADED 🐋")

# ================================================
# 🚀 SECTION 7: SYSTEM THREADS + WEB SERVER
# ================================================

# ================================================
# 🔢 SCAN COUNTER
# ================================================

_scan_counter = 0
_startup_time = time.time()


def get_uptime():
    """Get application uptime in human-readable format"""
    elapsed = int(time.time() - _startup_time)
    days = elapsed // 86400
    hours = (elapsed % 86400) // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def increment_scan_counter():
    """Increment the scan counter"""
    global _scan_counter
    _scan_counter += 1
    return _scan_counter


def get_scan_counter():
    """Get the current scan counter value"""
    return _scan_counter


# ================================================
# 🌐 WEB SERVER (Enhanced)
# ================================================

app = Flask(__name__)


@app.route("/")
def home():
    uptime = get_uptime()
    scans = get_scan_counter()
    total_trades = get_total_trades()
    
    return f"""
🐋 AHAD AI {VERSION} – Production Stable ONLINE 🚀

📅 Build: {BUILD_DATE}
⏱ Uptime: {uptime}
📊 Scans Run: {scans}
📈 Total Trades: {total_trades}

📋 Status: ✅ OPERATIONAL
🗄 Database: ✅ CONNECTED
🤖 Telegram: ✅ ACTIVE
"""


@app.route("/health")
def health():
    """Health check endpoint for monitoring"""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        
        return {
            "status": "healthy",
            "version": VERSION,
            "build_date": BUILD_DATE,
            "uptime": get_uptime(),
            "scans": get_scan_counter(),
            "total_trades": get_total_trades()
        }, 200
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "version": VERSION
        }, 500


@app.route("/ping")
def ping():
    """Simple ping endpoint for quick checks"""
    return "pong", 200


@app.route("/metrics")
def metrics():
    """Basic metrics endpoint for monitoring"""
    try:
        with get_db_cursor(commit=False) as cur:
            # Get trade counts
            cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open,
                COUNT(CASE WHEN status = 'CLOSED' AND result LIKE 'WIN%' THEN 1 END) as wins,
                COUNT(CASE WHEN status = 'CLOSED' AND result = 'LOSS_SL' THEN 1 END) as losses
            FROM trades
            """)
            row = cur.fetchone()
            
            total = row[0] or 0
            open_trades = row[1] or 0
            wins = row[2] or 0
            losses = row[3] or 0
            
            win_rate = round((wins / (wins + losses)) * 100, 2) if (wins + losses) > 0 else 0
            
            return {
                "version": VERSION,
                "uptime": get_uptime(),
                "scans": get_scan_counter(),
                "trades": {
                    "total": total,
                    "open": open_trades,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate
                },
                "cache": {
                    "entries": len(_candle_cache),
                    "ttl": CACHE_TTL
                }
            }, 200
    except Exception as e:
        return {"error": str(e)}, 500


def run_web():
    """Run the Flask web server"""
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web server starting on port {port}")
    app.run(host="0.0.0.0", port=port)


# ================================================
# 🔄 KEEP ALIVE (Enhanced)
# ================================================

def keep_alive():
    """
    Keep the bot alive by pinging the web server.
    Uses exponential backoff for retries.
    """
    url = os.environ.get("RENDER_URL")
    if not url:
        print("⚠️ RENDER_URL not set - Keep alive disabled")
        return
    
    backoff = 60  # Start with 60 seconds
    
    while True:
        try:
            response = urllib.request.urlopen(url, timeout=30)
            if response.getcode() == 200:
                if DEBUG_MODE:
                    print("🐋 Keep alive: ✅ SUCCESS")
                backoff = 60  # Reset backoff on success
            else:
                print(f"⚠️ Keep alive: HTTP {response.getcode()}")
        except Exception as e:
            print(f"⚠️ Keep alive error: {e}")
            print(f"🔄 Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 600)  # Max 10 minutes
            continue
        
        time.sleep(300)  # 5 minutes between pings


# ================================================
# 🤖 TELEGRAM ENGINE (Enhanced)
# ================================================

def telegram_engine():
    """
    Run the Telegram bot with automatic restart on failure.
    Uses exponential backoff for retries.
    """
    backoff = 5
    
    while True:
        try:
            print("🐋 Telegram engine starting...")
            bot.infinity_polling(
                skip_pending=True,
                timeout=60,
                long_polling_timeout=60
            )
            backoff = 5  # Reset backoff on successful connection
        except Exception as e:
            print(f"🚨 Telegram engine error: {e}")
            print(traceback.format_exc())
            print(f"🔄 Restarting Telegram in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)  # Max 60 seconds


# ================================================
# 🗑️ CACHE CLEANUP THREAD
# ================================================

def cache_cleanup_thread():
    """
    Clean expired cache entries periodically.
    Runs every 5 minutes (300 seconds) to balance performance.
    """
    while True:
        try:
            clear_expired_cache()
            if DEBUG_MODE:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"🗑️ Cache cleanup at {now}")
        except Exception as e:
            print(f"⚠️ Cache cleanup error: {e}")
        time.sleep(300)  # 5 minutes


# ================================================
# 🔄 TRADE TRACKER THREAD
# ================================================

# Note: update_open_trades() is defined in Section 2
# We'll reference it here


# ================================================
# 🚀 START ALL THREADS
# ================================================

def start_all_threads():
    """Start all background threads"""
    threads = []
    
    # 1. Web server
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    threads.append(("Web Server", web_thread))
    
    # 2. Telegram engine
    telegram_thread = threading.Thread(target=telegram_engine, daemon=True)
    telegram_thread.start()
    threads.append(("Telegram Engine", telegram_thread))
    
    # 3. Keep alive
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    threads.append(("Keep Alive", keep_alive_thread))
    
    # 4. Cache cleanup
    cache_thread = threading.Thread(target=cache_cleanup_thread, daemon=True)
    cache_thread.start()
    threads.append(("Cache Cleanup", cache_thread))
    
    # 5. Trade tracker
    tracker_thread = threading.Thread(target=update_open_trades, daemon=True)
    tracker_thread.start()
    threads.append(("Trade Tracker", tracker_thread))
    
    return threads


# ================================================
# 📊 SYSTEM STATUS
# ================================================

def print_system_status():
    """Print comprehensive system status"""
    print("=" * 60)
    print(f"🔥 AHAD AI {VERSION} – Production Stable ONLINE 🐋")
    print("=" * 60)
    print(f"📅 Build Date     : {BUILD_DATE}")
    print(f"📅 Started at     : {time.ctime()}")
    print(f"🐍 Python Version : {os.sys.version}")
    print("=" * 60)
    print(f"⚙️ CONFIGURATION")
    print(f"  MIN_FLOW_COINS  : {MIN_FLOW_COINS}")
    print(f"  MAX_FLOW_COINS  : {MAX_FLOW_COINS}")
    print(f"  FLOW_RATIO      : {FLOW_RATIO}")
    print(f"  MAX_SCAN_LIMIT  : {MAX_SCAN_LIMIT}")
    print(f"  CACHE_TTL       : {CACHE_TTL}s")
    print(f"  MIN_SCORE       : {MIN_SCORE}")
    print(f"  MIN_RR          : {MIN_RR}")
    print("=" * 60)
    print(f"🧠 AI ENGINES")
    print(f"  ✅ AI Brain v2.0")
    print(f"  ✅ Smart Money Engine")
    print(f"  ✅ Pre-Pump Detection")
    print(f"  ✅ Volatility Compression")
    print(f"  ✅ Market Regime")
    print(f"  ✅ Multi TimeFrame RSI")
    print(f"  ✅ Support/Resistance")
    print(f"  ✅ FOMO Filter (Fixed)")
    print(f"  ✅ Trap Detector")
    print("=" * 60)
    print(f"🗄️ DATABASE")
    print(f"  ✅ PostgreSQL Connected")
    print(f"  ✅ SSL Connection: ENABLED")
    print(f"  ✅ 8 Indexes for Performance")
    print(f"  ✅ Duplicate Protection")
    print(f"  ✅ Trade Tracker (With Backoff)")
    print("=" * 60)
    print(f"📊 FEATURES")
    print(f"  ✅ Professional Ranking Engine")
    print(f"  ✅ Quality Engine v2.0")
    print(f"  ✅ Risk Grade System")
    print(f"  ✅ Market Temperature")
    print(f"  ✅ Decision Summary (Grouped)")
    print(f"  ✅ Market Health Score")
    print(f"  ✅ Institutional Dashboard")
    print(f"  ✅ Scan Efficiency Tracking")
    print("=" * 60)
    print(f"📋 COMMANDS")
    print(f"  /scan    - Run Smart Market Scan")
    print(f"  /report  - Performance Report")
    print(f"  /open    - List Open Trades")
    print(f"  /history - Trade History")
    print("=" * 60)
    print(f"🎯 Best 2 LONG + Best 1 SHORT")
    print(f"🚀 SYSTEM READY FOR PRODUCTION")
    print("=" * 60)


# ================================================
# 🔄 STARTUP SEQUENCE
# ================================================

# Initialize database
init_database()

# Start all background threads
start_all_threads()

# Print system status
print_system_status()

# ================================================
# 🏃 MAIN LOOP
# ================================================

# Keep the main thread alive
while True:
    try:
        time.sleep(60)
        # Optional: periodic status update
        if DEBUG_MODE:
            scans = get_scan_counter()
            trades = get_total_trades()
            cache_size = len(_candle_cache)
            print(f"💚 [HEARTBEAT] Scans: {scans} | Trades: {trades} | Cache: {cache_size} entries")
    except KeyboardInterrupt:
        print("\n🛑 Shutting down gracefully...")
        break
    except Exception as e:
        print(f"⚠️ Main loop error: {e}")
        time.sleep(60)
