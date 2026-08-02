"""
================================================================================
AHAD AI - Research Lab
Phase 3, Module 2: Losers Analyzer
================================================================================

Direct structural mirror of Winners Analyzer, applied to losing trades.
Completely independent from bot.py. This file:

- Is never imported by bot.py, and never imports anything from bot.py.
- Sends no Telegram messages of any kind - no Telegram commands, no
  changes to any existing Telegram message.
- Never runs inside, or is called from, the live /scan path - it has
  zero effect on scan speed, AI Brain, Ranking, Smart Money, or the
  Validation Engine, because it never touches any of that code.
- Is READ-ONLY with respect to every production table (`trades`,
  `versions`). It only ever issues SELECT statements against them -
  never INSERT/UPDATE/DELETE.
- Writes exclusively to its own, dedicated table (`research_losers`),
  created and owned entirely by this script.
- Can be removed entirely (the file deleted, the research_losers table
  dropped) without touching bot.py or affecting production in any way -
  there is no coupling in either direction.

Deployment: this connects to the SAME PostgreSQL database bot.py uses
(same DATABASE_URL environment variable, same connection settings), but
runs as its own separate process - invoke it manually, on a schedule
(cron / a separate scheduled job), or however fits your infrastructure.
None of that affects bot.py's own deployment, process, or runtime.

Scope note: "losing trades" here means result = 'LOSS_SL' specifically -
the same precise scoping Winners Analyzer uses for WIN_TP1/TP2/TP3.
TIMEOUT is deliberately excluded: it is neither a clean win nor a clean
loss (the position could have been slightly ahead or slightly behind
at the moment it timed out), so folding it into "losses" would blur a
distinct outcome category rather than describing it accurately. If a
future phase wants TIMEOUT studied specifically, that is a deliberate,
separate decision - not something to fold silently into this module.

What this script does, each time it runs:
  1. Ensures research_losers exists (idempotent - safe to run before
     the table has ever been created, and a no-op every time after).
  2. Finds every CLOSED, losing trade (result = 'LOSS_SL') that is not
     yet present in research_losers, and copies its Trade DNA (the
     trades.initial_snapshot column, already captured by bot.py at
     decision time - nothing here re-derives or recalculates any of
     it) into a new research_losers row. Idempotent by construction:
     re-running this script never duplicates a trade already recorded,
     because "already recorded" is checked against research_losers
     itself - trades is never written to in order to mark anything as
     processed.
  3. Runs a fixed set of simple statistical summaries against the
     accumulated losers and prints them. No AI, no pattern discovery,
     no promotion logic, no automatic changes to anything - by design,
     for this phase. These are descriptive statistics only, meant to
     help a human ask questions like "what Flow value shows up most in
     losing trades" - not to draw any conclusion automatically.
================================================================================
"""

import os
import sys
import json
import psycopg2
from datetime import datetime


# ================================================
# 🔌 DATABASE CONNECTION
# ================================================
# Identical connection pattern to bot.py's get_db_connection() (and to
# Winners Analyzer's own), so this script reaches the exact same
# database - but this is its own, independent connection; nothing here
# is shared with, or coordinated with, bot.py's or Winners Analyzer's
# own connections.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - Losers Analyzer "
            "needs the same DATABASE_URL bot.py uses to reach the same database."
        )
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode="require"
    )


# ================================================
# 🗄 SCHEMA - research_losers (the only table this script ever writes to)
# ================================================
# Same hybrid principle as research_winners: the most frequently-
# queried Trade DNA fields are promoted to real columns (for fast,
# simple aggregate queries below); the complete, unmodified Trade DNA
# snapshot is also kept in trade_dna (JSONB), so nothing is ever lost
# even if a future question needs a field that wasn't promoted to its
# own column.

def init_research_losers_table():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS research_losers (
            id SERIAL PRIMARY KEY,
            trade_id INTEGER UNIQUE,
            version TEXT,
            version_id INTEGER,
            symbol TEXT,
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
            recorded_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_losers_trade_id ON research_losers(trade_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_losers_symbol ON research_losers(symbol)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_losers_sector ON research_losers(sector)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_losers_result ON research_losers(result)")
        conn.commit()
        print("🔬 Losers Analyzer: research_losers table ready")
    except Exception as e:
        print(f"⚠️ Losers Analyzer: failed to initialize research_losers - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📥 COLLECTION - read-only against `trades`, write-only against `research_losers`
# ================================================

def collect_new_losers():
    """
    SELECT-only against `trades` - never UPDATE/INSERT/DELETE on it.
    "Already processed" is determined by checking research_losers
    itself (a trade_id already present there is skipped), never by
    writing any marker back into trades.
    """
    conn = None
    cur = None
    new_count = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT t.id, t.version, t.version_id, t.symbol, t.side, t.result, t.initial_snapshot
        FROM trades t
        WHERE t.status = 'CLOSED'
          AND t.result = 'LOSS_SL'
          AND NOT EXISTS (
              SELECT 1 FROM research_losers l WHERE l.trade_id = t.id
          )
        """)
        rows = cur.fetchall()

        for trade_id, version, version_id, symbol, side, result, dna in rows:
            dna = dna or {}
            try:
                cur.execute("""
                INSERT INTO research_losers (
                    trade_id, version, version_id, symbol, direction, result,
                    brain_confidence, score, ranking_score, quality_grade, rr,
                    risk_grade, flow, flow_grade, momentum_score,
                    compression_status, market_regime, sector, market_health,
                    session, ema20, ema50, ema200, rsi_15m, atr, macd,
                    volume_acceleration, volume_ratio, trade_dna
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (trade_id) DO NOTHING
                """, (
                    trade_id, version, version_id, symbol, side, result,
                    dna.get("ai_brain_score"), dna.get("score"), dna.get("ranking_score"),
                    dna.get("quality_grade"), dna.get("rr"),
                    dna.get("risk_grade"), dna.get("flow"), dna.get("flow_grade"), dna.get("momentum_score"),
                    dna.get("compression_status"), dna.get("market_regime"), dna.get("sector"), dna.get("market_health"),
                    dna.get("session"), dna.get("ema20"), dna.get("ema50"), dna.get("ema200"),
                    dna.get("rsi_15m"), dna.get("atr"), dna.get("macd"),
                    dna.get("volume_acceleration"), dna.get("volume_ratio"),
                    json.dumps(dna, default=str)
                ))
                # ON CONFLICT DO NOTHING never raises on a duplicate -
                # cur.rowcount is the only way to tell whether a row was
                # actually inserted (1) or silently skipped (0).
                if cur.rowcount == 1:
                    new_count += 1
            except Exception as row_error:
                print(f"⚠️ Losers Analyzer: failed to record trade {trade_id} - {row_error}")
                conn.rollback()
                continue

        conn.commit()
        print(f"🔬 Losers Analyzer: recorded {new_count} new losing trade(s)")

    except Exception as e:
        print(f"⚠️ Losers Analyzer: failed to collect losers - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return new_count


# ================================================
# 📊 SIMPLE STATISTICS - descriptive only, no AI, no pattern discovery
# ================================================
# Every function below is read-only against research_losers (this
# script's own table) and returns a plain dict/list - nothing here
# writes anywhere, draws a conclusion, or feeds back into anything.

def _run_query(query, params=None):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchall()
    except Exception as e:
        print(f"⚠️ Losers Analyzer: query failed - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def average_losing_flow():
    rows = _run_query("SELECT AVG(flow), MIN(flow), MAX(flow) FROM research_losers WHERE flow IS NOT NULL")
    if not rows or rows[0][0] is None:
        return {"avg_flow": None, "min_flow": None, "max_flow": None}
    avg_f, min_f, max_f = rows[0]
    return {"avg_flow": round(avg_f, 2), "min_flow": round(min_f, 2), "max_flow": round(max_f, 2)}


def average_losing_momentum():
    rows = _run_query("SELECT AVG(momentum_score), MIN(momentum_score), MAX(momentum_score) FROM research_losers WHERE momentum_score IS NOT NULL")
    if not rows or rows[0][0] is None:
        return {"avg_momentum": None, "min_momentum": None, "max_momentum": None}
    avg_m, min_m, max_m = rows[0]
    return {"avg_momentum": round(avg_m, 2), "min_momentum": round(min_m, 2), "max_momentum": round(max_m, 2)}


def average_losing_rsi():
    rows = _run_query("SELECT AVG(rsi_15m), MIN(rsi_15m), MAX(rsi_15m) FROM research_losers WHERE rsi_15m IS NOT NULL")
    if not rows or rows[0][0] is None:
        return {"avg_rsi": None, "min_rsi": None, "max_rsi": None}
    avg_r, min_r, max_r = rows[0]
    return {"avg_rsi": round(avg_r, 2), "min_rsi": round(min_r, 2), "max_rsi": round(max_r, 2)}


def average_losing_rr():
    rows = _run_query("SELECT AVG(rr), MIN(rr), MAX(rr) FROM research_losers WHERE rr IS NOT NULL")
    if not rows or rows[0][0] is None:
        return {"avg_rr": None, "min_rr": None, "max_rr": None}
    avg_r, min_r, max_r = rows[0]
    return {"avg_rr": round(avg_r, 2), "min_rr": round(min_r, 2), "max_rr": round(max_r, 2)}


def compression_distribution():
    rows = _run_query("""
        SELECT compression_status, COUNT(*) AS cnt
        FROM research_losers
        WHERE compression_status IS NOT NULL
        GROUP BY compression_status
        ORDER BY cnt DESC
    """)
    return [{"compression_status": r[0], "count": r[1]} for r in rows]


def sector_distribution():
    rows = _run_query("""
        SELECT sector, COUNT(*) AS cnt
        FROM research_losers
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY cnt DESC
    """)
    return [{"sector": r[0], "count": r[1]} for r in rows]


def session_distribution():
    rows = _run_query("""
        SELECT session, COUNT(*) AS cnt
        FROM research_losers
        WHERE session IS NOT NULL
        GROUP BY session
        ORDER BY cnt DESC
    """)
    return [{"session": r[0], "count": r[1]} for r in rows]


def market_regime_distribution():
    rows = _run_query("""
        SELECT market_regime, COUNT(*) AS cnt
        FROM research_losers
        WHERE market_regime IS NOT NULL
        GROUP BY market_regime
        ORDER BY cnt DESC
    """)
    return [{"market_regime": r[0], "count": r[1]} for r in rows]


def average_losers():
    """General average across every numeric Trade DNA field tracked as its own column."""
    rows = _run_query("""
        SELECT
            AVG(brain_confidence), AVG(score), AVG(ranking_score), AVG(rr),
            AVG(flow), AVG(momentum_score), AVG(rsi_15m), AVG(atr),
            AVG(volume_acceleration), AVG(volume_ratio), COUNT(*)
        FROM research_losers
    """)
    keys = [
        "avg_brain_confidence", "avg_score", "avg_ranking_score", "avg_rr",
        "avg_flow", "avg_momentum_score", "avg_rsi", "avg_atr",
        "avg_volume_acceleration", "avg_volume_ratio", "total_losers"
    ]
    if not rows:
        return {k: None for k in keys}
    result = {}
    for k, v in zip(keys, rows[0]):
        if isinstance(v, (int, float)):
            result[k] = round(v, 2)
        else:
            result[k] = v
    return result


def loss_distribution():
    """
    Breakdown of losers by quality grade, direction, and market regime -
    simple counts, no inference. (By-result is trivially all LOSS_SL by
    this module's own scope, so it is not repeated here as a separate
    "distribution" - it would just say 100% LOSS_SL.)
    """
    by_quality = {r[0]: r[1] for r in _run_query(
        "SELECT quality_grade, COUNT(*) FROM research_losers WHERE quality_grade IS NOT NULL "
        "GROUP BY quality_grade ORDER BY COUNT(*) DESC"
    )}
    by_direction = {r[0]: r[1] for r in _run_query(
        "SELECT direction, COUNT(*) FROM research_losers GROUP BY direction"
    )}
    by_regime = {r[0]: r[1] for r in _run_query(
        "SELECT market_regime, COUNT(*) FROM research_losers WHERE market_regime IS NOT NULL "
        "GROUP BY market_regime ORDER BY COUNT(*) DESC"
    )}
    return {
        "by_quality_grade": by_quality,
        "by_direction": by_direction,
        "by_market_regime": by_regime,
    }


# ================================================
# 🖨 REPORT - prints a plain-text summary to stdout (no Telegram, ever)
# ================================================

def print_report():
    print("\n" + "=" * 60)
    print("📉 AHAD AI RESEARCH LAB - LOSERS ANALYSIS")
    print("=" * 60)

    dist = loss_distribution()
    total = sum(dist["by_direction"].values()) if dist["by_direction"] else 0
    print(f"\nTotal losers recorded  : {total}")
    print(f"By direction           : {dist['by_direction']}")
    print(f"By quality grade       : {dist['by_quality_grade']}")
    print(f"By market regime       : {dist['by_market_regime']}")

    print("\n--- Average Losing Flow ---")
    print(average_losing_flow())

    print("\n--- Average Losing Momentum ---")
    print(average_losing_momentum())

    print("\n--- Average Losing RSI ---")
    print(average_losing_rsi())

    print("\n--- Average Losing RR ---")
    print(average_losing_rr())

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

    print("\n--- Average Losers (overall) ---")
    print(average_losers())

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
    print(f"🔬 Losers Analyzer starting - {datetime.now().isoformat()}")
    init_research_losers_table()
    collect_new_losers()
    print_report()
    print(f"🔬 Losers Analyzer finished - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
