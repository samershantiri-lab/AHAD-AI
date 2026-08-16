"""
================================================================================
AHAD AI - Research Lab
Phase 4, Module 3: Top Gainers Study
================================================================================

Completely independent from bot.py. This file:

- Is never imported by bot.py, and never imports anything from bot.py.
- Sends no Telegram messages of any kind.
- Never runs inside, or is called from, the live /scan path - it has
  zero effect on scan speed, AI Brain, Ranking, Smart Money, or the
  Validation Engine, because it never touches any of that code.
- Is READ-ONLY with respect to every production table (`trades`,
  `versions`). It only ever issues SELECT statements against them -
  never INSERT/UPDATE/DELETE.
- Writes exclusively to its own, dedicated table
  (`research_top_gainers`), created and owned entirely by this script.
- Can be removed entirely without touching bot.py or affecting
  production in any way.

A DESIGN DECISION WORTH STATING EXPLICITLY: "Top Gainer" is a market-
wide observation (which coins moved up the most), not a concept that
exists anywhere in `trades` - most top gainers will have NO matching
AHAD AI trade at all, since the bot does not signal on every mover.
That is expected, not a gap - it is exactly why the request asks for
Trade DNA fields "whenever available" rather than always.

Because of that, this script does NOT depend on anything bot.py writes
(e.g. market_universe.json) - that would silently assume this script
runs on the same filesystem/deployment as bot.py, which is not a safe
assumption to make quietly. Instead, this script fetches OHLCV data
directly and independently from OKX's public REST API - the exact same
public endpoints bot.py happens to use, but called here with entirely
separate, self-contained code. This script needs only network access
and the shared DATABASE_URL; it has zero dependency on bot.py's
process, filesystem, or deployment.

MARKET HEALTH - stated plainly rather than left as a silent None:
market_health_score, as it exists in bot.py today, is never persisted
to any database table - it is computed fresh inside a live scan() call
and only ever appears in an ephemeral Telegram message. No Research
Lab module (this one included) can report a real historical value for
it without bot.py itself being changed to persist it somewhere, which
is out of scope here. Every research_top_gainers row will show
market_health as unavailable for this reason - not because it wasn't
looked for.

What this script does, each time it runs:
  1. Ensures research_top_gainers exists (idempotent).
  2. Fetches the current USDT-SWAP symbol list from OKX, computes each
     symbol's ~24h price change independently (own candle fetch, not
     shared with bot.py), and takes the top N gainers by that change.
  3. For each, looks up the most recent CLOSED trade for that symbol in
     `trades` (read-only) - if AHAD AI has traded it before, its Trade
     DNA is copied in; if not, those fields are correctly left null.
  4. Records one row per (symbol, observed_date) - idempotent by
     construction: re-running this on the same day never duplicates a
     symbol already recorded that day (a UNIQUE constraint enforces
     this at the database level, not just in application logic).
  5. Runs a fixed set of simple statistical summaries and prints them.
     No AI, no pattern discovery, no promotion logic - descriptive
     statistics only, meant to help a human ask questions like "what
     Flow value shows up most among today's biggest movers" - not to
     draw any conclusion automatically.
================================================================================
"""

import os
import sys
import json
import time
import requests
import psycopg2
from datetime import datetime, date
from snapshot_writer import save_snapshot, update_snapshot_status

MODULE_KEY = "top_gainers_study"
MODULE_NAME = "Top Gainers Study"
MODULE_CATEGORY = "research_lab"
MODULE_VERSION = "1.0"


# ================================================
# 🔌 DATABASE CONNECTION
# ================================================
# Identical connection pattern to bot.py's get_db_connection() (and to
# Winners/Losers Analyzer's own), so this script reaches the exact same
# database - but this is its own, independent connection.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - Top Gainers Study "
            "needs the same DATABASE_URL bot.py uses to reach the same database."
        )
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode="require"
    )


# ================================================
# 🌐 INDEPENDENT MARKET DATA (OKX public API - no import from bot.py)
# ================================================
# These deliberately do not reuse bot.py's own get_symbols()/
# get_candles() - not because those are wrong, but because importing
# them would create exactly the coupling this module must not have.
# This is a simplified, self-contained equivalent - broad market-wide
# parity with bot.py's own universe is not required for a descriptive
# study of overall market movers.

TOP_N_GAINERS = 20
REQUEST_DELAY_SECONDS = 0.15  # polite pacing against OKX's public API


def fetch_usdt_swap_symbols():
    try:
        url = "https://www.okx.com/api/v5/public/instruments"
        params = {"instType": "SWAP"}
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ Top Gainers Study: instrument list HTTP {response.status_code}")
            return []
        data = response.json()
        if data.get("code") != "0":
            print(f"⚠️ Top Gainers Study: instrument list API error {data.get('code')}")
            return []

        result = []
        for x in data.get("data", []):
            inst_id = x.get("instId", "")
            if inst_id.endswith("-USDT-SWAP") and x.get("state") == "live":
                result.append(inst_id)
        return result
    except Exception as e:
        print(f"⚠️ Top Gainers Study: failed to fetch symbol list - {e}")
        return []


def fetch_daily_change(symbol):
    """
    Percent change over the most recent ~24h, using 24 hourly candles.
    Returns {"change_pct": float, "price": float, "candles": [...]} or
    None on any failure - a single symbol's fetch failing never stops
    the rest of the study. `candles` (raw OKX response, most-recent-
    first) is now included so compute_move_start_proxy() can use the
    exact same fetch - no second API call needed.
    """
    try:
        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": symbol, "bar": "1H", "limit": 24}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if data.get("code") != "0":
            return None
        candles = data.get("data", [])
        if len(candles) < 2:
            return None

        # OKX returns most-recent-first.
        latest_close = float(candles[0][4])
        oldest_close = float(candles[-1][4])
        if oldest_close == 0:
            return None

        change_pct = ((latest_close - oldest_close) / oldest_close) * 100
        return {"change_pct": change_pct, "price": latest_close, "candles": candles}
    except Exception as e:
        print(f"⚠️ Top Gainers Study: failed to fetch candles for {symbol} - {e}")
        return None


# ================================================
# 🎯 RESEARCH MOVE START PROXY (Research Layer v1)
# ================================================
# NOT the actual move start - an estimate based on a cumulative-return
# threshold over the same 24 hourly candles already fetched above.
# Named "proxy" everywhere deliberately, per the approved specification,
# so this is never mistaken for a ground-truth timestamp the historical
# data cannot actually provide.
#
# Approved parameters:
MOVE_START_PRIMARY_THRESHOLD = 0.75
MOVE_START_SENSITIVITY_THRESHOLDS = [0.60, 0.75, 0.90]
EARLY_BUFFER_HOURS = 2
EARLY_BUFFER_SENSITIVITY_HOURS = [1, 2, 3]
LATE_THRESHOLD = 0.80  # independent of the MOVE_START thresholds above


def compute_move_start_proxy(candles, total_change_pct):
    """
    For each sensitivity threshold, finds the LATEST (most recent)
    candle in the window at which the remaining return from that
    candle's close to the final close is still >= threshold * total_
    change_pct (matching sign). This is deliberately NOT "the first
    candle scanning oldest-to-newest that satisfies the condition" -
    every candle during a quiet pre-move period trivially satisfies
    "100% of the move is still ahead", so taking the first match would
    always return the oldest candle in the window, never the actual
    transition point. Verified against a hand-derived worked example
    (flat-then-jump price path) before this was written.

    Returns {threshold: {"timestamp_ms": int, "close": float} or None, ...}
    or None entirely if the input doesn't support the calculation.
    """
    if not candles or len(candles) < 2 or total_change_pct == 0:
        return None

    final_close = float(candles[0][4])
    ordered = list(reversed(candles))  # oldest-first

    results = {}
    for threshold in MOVE_START_SENSITIVITY_THRESHOLDS:
        last_match = None
        target = threshold * total_change_pct
        for candle in ordered[:-1]:  # exclude the final candle (remaining=0 trivially)
            try:
                candle_close = float(candle[4])
            except (ValueError, TypeError):
                continue
            if candle_close == 0:
                continue
            remaining_pct = ((final_close - candle_close) / candle_close) * 100
            satisfies = remaining_pct >= target if total_change_pct > 0 else remaining_pct <= target
            if satisfies:
                last_match = candle
        results[threshold] = (
            {"timestamp_ms": int(last_match[0]), "close": float(last_match[4])}
            if last_match else None
        )
    return results


def find_top_gainers(limit=TOP_N_GAINERS):
    symbols = fetch_usdt_swap_symbols()
    if not symbols:
        print("⚠️ Top Gainers Study: no symbols available - skipping this run")
        return []

    candidates = []
    for symbol in symbols:
        change = fetch_daily_change(symbol)
        if change is not None:
            proxy = compute_move_start_proxy(change["candles"], change["change_pct"])
            candidates.append({"symbol": symbol, **change, "move_start_proxy": proxy})
        time.sleep(REQUEST_DELAY_SECONDS)

    candidates.sort(key=lambda c: c["change_pct"], reverse=True)
    return candidates[:limit]


# ================================================
# 🗄 SCHEMA - research_top_gainers (the only table this script ever writes to)
# ================================================
# Same hybrid principle as research_winners/research_losers: the most
# frequently-queried fields are promoted to real columns; the complete
# raw record is also kept in trade_dna (JSONB) for anything not
# promoted. Trade DNA columns are nullable throughout, since most top
# gainers will have no matching AHAD AI trade at all.

def init_research_top_gainers_table():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS research_top_gainers (
            id SERIAL PRIMARY KEY,
            symbol TEXT,
            observed_date DATE,
            change_pct REAL,
            price REAL,
            trade_id INTEGER,
            version TEXT,
            version_id INTEGER,
            direction TEXT,
            result TEXT,
            brain_confidence REAL,
            score REAL,
            ranking_score REAL,
            quality_grade TEXT,
            rr REAL,
            risk_grade TEXT,
            flow REAL,
            flow_grade TEXT,
            momentum_score REAL,
            compression_status TEXT,
            market_regime TEXT,
            sector TEXT,
            market_health REAL,
            session TEXT,
            ema20 REAL,
            ema50 REAL,
            ema200 REAL,
            rsi_15m REAL,
            atr REAL,
            macd REAL,
            volume_acceleration REAL,
            volume_ratio REAL,
            trade_dna JSONB,
            recorded_at TIMESTAMP DEFAULT NOW(),
            research_move_start_proxy_60 TIMESTAMP,
            research_move_start_proxy_75 TIMESTAMP,
            research_move_start_proxy_90 TIMESTAMP,
            UNIQUE(symbol, observed_date)
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_top_gainers_symbol ON research_top_gainers(symbol)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_top_gainers_date ON research_top_gainers(observed_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_top_gainers_sector ON research_top_gainers(sector)")
        # Idempotent migration - CREATE TABLE IF NOT EXISTS above never
        # adds columns to a table that already existed before this
        # definition was extended. Confirmed as the exact root cause of
        # zero new records since 2026-08-11: every column below is
        # already in the CREATE TABLE definition, but the LIVE table
        # predates several of them. Every ADD COLUMN is a no-op when
        # already present - safe on every startup regardless of the
        # table's actual current state.
        for col_name, col_type in [
            ("trade_id", "INTEGER"), ("version", "TEXT"), ("version_id", "INTEGER"),
            ("direction", "TEXT"), ("result", "TEXT"), ("brain_confidence", "REAL"),
            ("score", "REAL"), ("ranking_score", "REAL"), ("quality_grade", "TEXT"),
            ("rr", "REAL"), ("risk_grade", "TEXT"), ("flow", "REAL"), ("flow_grade", "TEXT"),
            ("momentum_score", "REAL"), ("compression_status", "TEXT"), ("market_regime", "TEXT"),
            ("sector", "TEXT"), ("market_health", "REAL"), ("session", "TEXT"),
            ("ema20", "REAL"), ("ema50", "REAL"), ("ema200", "REAL"), ("rsi_15m", "REAL"),
            ("atr", "REAL"), ("macd", "REAL"), ("volume_acceleration", "REAL"),
            ("volume_ratio", "REAL"), ("trade_dna", "JSONB"), ("recorded_at", "TIMESTAMP DEFAULT NOW()"),
            ("research_move_start_proxy_60", "TIMESTAMP"),
            ("research_move_start_proxy_75", "TIMESTAMP"),
            ("research_move_start_proxy_90", "TIMESTAMP"),
        ]:
            cur.execute(f"ALTER TABLE research_top_gainers ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        conn.commit()
        print("🔬 Top Gainers Study: research_top_gainers table ready")
    except Exception as e:
        print(f"⚠️ Top Gainers Study: failed to initialize research_top_gainers - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📥 COLLECTION - read-only against `trades`, write-only against `research_top_gainers`
# ================================================

def _lookup_trade_dna(cur, symbol, event_time):
    """
    Point-in-time lookup of the most recent CLOSED trade for this
    symbol AT OR BEFORE event_time - used only to enrich a top-gainer
    record when AHAD AI happens to have traded it before the move
    being studied. Returns None (not an empty dict) when no match
    exists, so the caller can tell "never traded before this event"
    apart from "traded, but with an empty snapshot".

    FIXED (previously a confirmed Future Leakage bug): this used to be
    `ORDER BY signal_time DESC LIMIT 1` with no time bound at all - the
    most recent CLOSED trade for the symbol REGARDLESS of whether it
    happened before or after the move being studied. A trade that
    happened AFTER the move, under completely different conditions,
    could get attributed to that move's research row. event_time is
    now required - the caller must supply the actual event timestamp
    (see collect_top_gainers()'s own docstring for how it's chosen),
    never a substitute like observed_date.
    """
    cur.execute("""
        SELECT id, version, version_id, side, result, initial_snapshot
        FROM trades
        WHERE symbol = %s AND status = 'CLOSED' AND signal_time <= %s
        ORDER BY signal_time DESC
        LIMIT 1
    """, (symbol, event_time))
    row = cur.fetchone()
    if not row:
        return None
    trade_id, version, version_id, side, result, dna = row
    return {
        "trade_id": trade_id, "version": version, "version_id": version_id,
        "side": side, "result": result, "dna": dna or {}
    }


def collect_top_gainers():
    conn = None
    cur = None
    new_count = 0
    try:
        gainers = find_top_gainers()
        if not gainers:
            print("🔬 Top Gainers Study: no gainers found this run")
            return 0

        conn = get_db_connection()
        cur = conn.cursor()
        today = date.today()

        duplicate_count = 0
        failed_count = 0
        trade_dna_matched = 0
        trade_dna_missing = 0
        event_source_counts = {"T75": 0, "T60": 0, "T90": 0, "NO_PROXY": 0}

        for g in gainers:
            symbol = g["symbol"]

            proxy = g.get("move_start_proxy") or {}
            proxy_datetimes = {}
            for threshold in (0.60, 0.75, 0.90):
                entry = proxy.get(threshold)
                proxy_datetimes[threshold] = (
                    datetime.fromtimestamp(entry["timestamp_ms"] / 1000)
                    if entry else None
                )

            # event_time selection, per the approved Point-in-Time
            # research rule: T75 (this codebase's own existing primary
            # threshold, MOVE_START_PRIMARY_THRESHOLD) -> T60 -> T90 ->
            # NO_PROXY. These are RESEARCH MOVE-START PROXIES, not
            # ground truth - never described as "actual move start".
            #
            # NO_PROXY, fixed here: previously fell back to midnight of
            # observed_date as a synthetic event_time, which is not a
            # real Point-in-Time timestamp and could produce a
            # misleading Trade DNA match. Now: when no proxy exists at
            # all, event_time stays None, _lookup_trade_dna() is never
            # called, trade_dna_missing is still counted, and the
            # market-observation row is still inserted - trade_dna and
            # all three proxy columns simply stay NULL. The observation
            # itself (symbol, change_pct, price, market/indicator
            # fields) is never discarded for lacking a proxy.
            if proxy_datetimes[0.75] is not None:
                event_time, event_time_source = proxy_datetimes[0.75], "T75"
            elif proxy_datetimes[0.60] is not None:
                event_time, event_time_source = proxy_datetimes[0.60], "T60"
            elif proxy_datetimes[0.90] is not None:
                event_time, event_time_source = proxy_datetimes[0.90], "T90"
            else:
                event_time, event_time_source = None, "NO_PROXY"
            event_source_counts[event_time_source] += 1

            trade_info = _lookup_trade_dna(cur, symbol, event_time) if event_time is not None else None
            dna = trade_info["dna"] if trade_info else {}
            if trade_info:
                trade_dna_matched += 1
            else:
                trade_dna_missing += 1

            # SAVEPOINT per symbol - fixed here: previously used
            # conn.rollback() on a row-level failure, which rolls back
            # the ENTIRE transaction, silently discarding every
            # already-successful INSERT earlier in this same loop
            # while new_count still counted them. Now: only this
            # symbol's own work is undone on failure; every prior
            # symbol's committed-later INSERT is preserved.
            cur.execute("SAVEPOINT research_symbol")
            try:
                cur.execute("""
                INSERT INTO research_top_gainers (
                    symbol, observed_date, change_pct, price,
                    trade_id, version, version_id, direction, result,
                    brain_confidence, score, ranking_score, quality_grade, rr,
                    risk_grade, flow, flow_grade, momentum_score,
                    compression_status, market_regime, sector, market_health,
                    session, ema20, ema50, ema200, rsi_15m, atr, macd,
                    volume_acceleration, volume_ratio, trade_dna,
                    research_move_start_proxy_60, research_move_start_proxy_75,
                    research_move_start_proxy_90
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (symbol, observed_date) DO NOTHING
                """, (
                    symbol, today, round(g["change_pct"], 2), g["price"],
                    trade_info["trade_id"] if trade_info else None,
                    trade_info["version"] if trade_info else None,
                    trade_info["version_id"] if trade_info else None,
                    trade_info["side"] if trade_info else None,
                    trade_info["result"] if trade_info else None,
                    dna.get("ai_brain_score"), dna.get("score"), dna.get("ranking_score"),
                    dna.get("quality_grade"), dna.get("rr"),
                    dna.get("risk_grade"), dna.get("flow"), dna.get("flow_grade"), dna.get("momentum_score"),
                    dna.get("compression_status"), dna.get("market_regime"), dna.get("sector"), dna.get("market_health"),
                    dna.get("session"), dna.get("ema20"), dna.get("ema50"), dna.get("ema200"),
                    dna.get("rsi_15m"), dna.get("atr"), dna.get("macd"),
                    dna.get("volume_acceleration"), dna.get("volume_ratio"),
                    json.dumps(dna, default=str),
                    proxy_datetimes[0.60], proxy_datetimes[0.75], proxy_datetimes[0.90]
                ))
                # ON CONFLICT DO NOTHING never raises on a duplicate -
                # cur.rowcount is the only way to tell whether a row was
                # actually inserted (1) or silently skipped (0). `new`
                # only ever increments after this INSERT has actually
                # succeeded - never before.
                if cur.rowcount == 1:
                    new_count += 1
                else:
                    duplicate_count += 1
                cur.execute("RELEASE SAVEPOINT research_symbol")
            except Exception as row_error:
                print(f"⚠️ Top Gainers Study: failed to record {symbol} - {row_error}")
                cur.execute("ROLLBACK TO SAVEPOINT research_symbol")
                cur.execute("RELEASE SAVEPOINT research_symbol")
                failed_count += 1
                continue

        conn.commit()
        print(f"🔬 Top Gainers Study: recorded {new_count} gainer(s) for {today}")
        print(
            f"🔬 Top Gainers Study Summary — symbols_scanned={len(gainers)}, "
            f"new={new_count}, duplicates={duplicate_count}, failed={failed_count}, "
            f"trade_dna_matched={trade_dna_matched}, trade_dna_missing={trade_dna_missing}, "
            f"event_time_source={event_source_counts}"
        )

    except Exception as e:
        # Catastrophic failure OUTSIDE the per-symbol loop (e.g. the
        # connection itself, or find_top_gainers() failing) - the only
        # place a full-transaction rollback still applies.
        print(f"⚠️ Top Gainers Study: failed to collect gainers - {e}")
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return new_count


# ================================================
# 📊 SIMPLE STATISTICS - descriptive only, no AI, no pattern discovery
# ================================================

def _run_query(query, params=None):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Top Gainers Study: query failed - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _avg_min_max(column):
    rows = _run_query(f"SELECT AVG({column}), MIN({column}), MAX({column}) FROM research_top_gainers WHERE {column} IS NOT NULL")
    if not rows or rows[0][0] is None:
        return {"avg": None, "min": None, "max": None}
    avg_v, min_v, max_v = rows[0]
    return {"avg": round(avg_v, 2), "min": round(min_v, 2), "max": round(max_v, 2)}


def average_flow():
    return _avg_min_max("flow")


def average_rsi():
    return _avg_min_max("rsi_15m")


def average_momentum():
    return _avg_min_max("momentum_score")


def average_rr():
    """
    "If applicable" per the request: most top gainers will have no RR
    at all (never AI-signaled), so this naturally averages over only
    the subset that does - AVG() already ignores NULLs, and the
    surrounding report states the sample size explicitly so this
    isn't mistaken for "average RR across all gainers".
    """
    count_with_rr = _run_query("SELECT COUNT(*) FROM research_top_gainers WHERE rr IS NOT NULL")
    n = count_with_rr[0][0] if count_with_rr else 0
    stats = _avg_min_max("rr")
    stats["sample_size"] = n
    return stats


def average_atr():
    return _avg_min_max("atr")


def average_volume_ratio():
    return _avg_min_max("volume_ratio")


def average_volume_acceleration():
    return _avg_min_max("volume_acceleration")


def compression_distribution():
    rows = _run_query("""
        SELECT compression_status, COUNT(*) AS cnt
        FROM research_top_gainers
        WHERE compression_status IS NOT NULL
        GROUP BY compression_status
        ORDER BY cnt DESC
    """)
    return [{"compression_status": r[0], "count": r[1]} for r in rows]


def sector_distribution():
    rows = _run_query("""
        SELECT sector, COUNT(*) AS cnt
        FROM research_top_gainers
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY cnt DESC
    """)
    return [{"sector": r[0], "count": r[1]} for r in rows]


def session_distribution():
    rows = _run_query("""
        SELECT session, COUNT(*) AS cnt
        FROM research_top_gainers
        WHERE session IS NOT NULL
        GROUP BY session
        ORDER BY cnt DESC
    """)
    return [{"session": r[0], "count": r[1]} for r in rows]


def market_regime_distribution():
    rows = _run_query("""
        SELECT market_regime, COUNT(*) AS cnt
        FROM research_top_gainers
        WHERE market_regime IS NOT NULL
        GROUP BY market_regime
        ORDER BY cnt DESC
    """)
    return [{"market_regime": r[0], "count": r[1]} for r in rows]


def market_health_summary():
    """
    Always unavailable today, by construction - see the module
    docstring for why. Returned as an explicit, explained status rather
    than a bare None, so this isn't mistaken for "checked and empty".
    """
    return {
        "available": False,
        "reason": "market_health_score is never persisted to the database by bot.py - "
                   "it exists only transiently during a live scan and in its Telegram "
                   "message. Reporting a real value here would require a change to "
                   "bot.py, which is out of scope for this module."
    }


def overall_averages():
    rows = _run_query("""
        SELECT
            AVG(change_pct), AVG(brain_confidence), AVG(score), AVG(ranking_score),
            AVG(flow), AVG(momentum_score), AVG(rsi_15m), AVG(atr),
            AVG(volume_acceleration), AVG(volume_ratio), COUNT(*),
            COUNT(trade_id)
        FROM research_top_gainers
    """)
    keys = [
        "avg_change_pct", "avg_brain_confidence", "avg_score", "avg_ranking_score",
        "avg_flow", "avg_momentum_score", "avg_rsi", "avg_atr",
        "avg_volume_acceleration", "avg_volume_ratio", "total_gainers_recorded",
        "gainers_with_ahad_ai_trade"
    ]
    if not rows:
        return {k: None for k in keys}
    result = {}
    for k, v in zip(keys, rows[0]):
        result[k] = round(v, 2) if isinstance(v, (int, float)) else v
    return result


# ================================================
# 🖨 REPORT - prints a plain-text summary to stdout (no Telegram, ever)
# ================================================

def print_report():
    print("\n" + "=" * 60)
    print("📈 AHAD AI RESEARCH LAB - TOP GAINERS STUDY")
    print("=" * 60)

    overall = overall_averages()
    print(f"\nTotal gainers recorded       : {overall['total_gainers_recorded']}")
    print(f"...with a matching AHAD AI trade : {overall['gainers_with_ahad_ai_trade']}")

    print("\n--- Average Flow ---")
    print(average_flow())

    print("\n--- Average RSI ---")
    print(average_rsi())

    print("\n--- Average Momentum ---")
    print(average_momentum())

    print("\n--- Average RR (if applicable) ---")
    print(average_rr())

    print("\n--- Average ATR ---")
    print(average_atr())

    print("\n--- Average Volume Ratio ---")
    print(average_volume_ratio())

    print("\n--- Average Volume Acceleration ---")
    print(average_volume_acceleration())

    print("\n--- Compression Distribution ---")
    for row in compression_distribution():
        print(f"  {row['compression_status']}: {row['count']}")

    print("\n--- Sector Distribution ---")
    for row in sector_distribution():
        print(f"  {row['sector']}: {row['count']}")

    print("\n--- Session Distribution ---")
    for row in session_distribution():
        print(f"  {row['session']}: {row['count']}")

    print("\n--- Market Regime Distribution ---")
    for row in market_regime_distribution():
        print(f"  {row['market_regime']}: {row['count']}")

    print("\n--- Market Health ---")
    health = market_health_summary()
    print(f"  Available: {health['available']}")
    print(f"  Reason: {health['reason']}")

    print("\n--- Overall Averages ---")
    print(overall)

    print("\n" + "=" * 60)
    print("Note: descriptive statistics only. No pattern discovery, no")
    print("recommendations, no promotion, no automatic changes to AHAD")
    print("AI. A human decides what, if anything, these numbers mean")
    print("for future versions.")
    print("=" * 60 + "\n")


# ================================================
# ▶ ENTRY POINT
# ================================================

def main():
    update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "RUNNING")
    start_time = time.time()
    print(f"🔬 Top Gainers Study starting - {datetime.now().isoformat()}")

    try:
        init_research_top_gainers_table()
        new_count = collect_top_gainers()
        print_report()

        overall = overall_averages()

        summary_data = {
            "new_gainers_this_run": new_count,
            "total_gainers_recorded": overall.get("total_gainers_recorded"),
            "gainers_with_ahad_ai_trade": overall.get("gainers_with_ahad_ai_trade"),
            "avg_change_pct": overall.get("avg_change_pct"),
            "avg_flow": overall.get("avg_flow"),
            "avg_rsi": overall.get("avg_rsi"),
        }

        save_snapshot(
            module_key=MODULE_KEY,
            module_name=MODULE_NAME,
            category=MODULE_CATEGORY,
            headline_stat=f"{new_count} gainer(s) recorded this run "
                           f"({overall.get('total_gainers_recorded', 0)} total)",
            summary_data=summary_data,
            version_scope="ALL",
            detail_table="research_top_gainers",
            module_version=MODULE_VERSION,
            execution_duration_seconds=round(time.time() - start_time, 2),
            records_processed=new_count,
        )

        print(f"🔬 Top Gainers Study finished - {datetime.now().isoformat()}")
    except Exception as e:
        update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
        print(f"⚠️ Top Gainers Study: unhandled error - {e}")
        raise


if __name__ == "__main__":
    main()
