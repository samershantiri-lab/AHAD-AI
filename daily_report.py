"""
================================================================================
AHAD AI - Reports Layer v1
Daily Telegram Report
================================================================================

Standalone script, run via Render Cron - NOT imported by bot.py, does
not import bot.py (would trigger the live Telegram bot's own polling
side effects). Reads directly from `trades` - no research_* tables,
no Research Lab module execution, no analysis recomputation.

TIMEZONE - explicit Asia/Amman via zoneinfo, per the approved design:
"today" is computed by asking Python's own timezone database for the
real UTC offset of Asia/Amman right now (currently +3, no DST since
Oct 2022 - but this is looked up, never hardcoded as a manual offset).

ONE REMAINING ASSUMPTION, ISOLATED TO A SINGLE POINT: trades.signal_
time/close_time are PostgreSQL `TIMESTAMP` (naive, no timezone) columns
- confirmed from bot.py's own schema. This script assumes those naive
values represent UTC (consistent with datetime.now() being called
throughout bot.py, presumed to run on a UTC-configured server). That
assumption is applied in exactly one place - _cycle_boundaries_naive()
- by converting the Amman-time cycle boundary to a real, zoneinfo-
computed UTC instant, then stripping the tzinfo to match the naive
column type. If the live server's actual timezone differs, this is
the single function to correct - nothing else in this file depends on
that assumption being right.

"Generated" = signal_time falls within the cycle. "Closed" = close_
time falls within the cycle, status='CLOSED'. "Open" = ALL currently
OPEN trades, regardless of when generated - never date-filtered.

Win Rate is computed excluding TIMEOUT from both numerator and
denominator - the same project-wide convention used everywhere else.

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file. Read-only against `trades` - no
writes, no schema changes.
================================================================================
"""

import os
import sys
import statistics
import requests
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    print("⚠️ Daily Report: zoneinfo unavailable (Python < 3.9) - aborting.")
    sys.exit(1)

import psycopg2

from research_statistics import MIN_SAMPLE_SIZE

DATABASE_URL = os.environ.get("DATABASE_URL")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID")

RESEARCH_TARGET_CLOSED_TRADES = 100
CYCLE_START_HOUR = 3  # 03:00 Asia/Amman, per the approved AHAD AI daily cycle

try:
    AMMAN_TZ = ZoneInfo("Asia/Amman")
except Exception as e:
    # tzdata not installed on this system - fail loudly and immediately,
    # not with a silently wrong offset somewhere downstream.
    print(f"⚠️ Daily Report: Asia/Amman timezone data unavailable - {e}")
    sys.exit(1)


def _cycle_boundaries_naive():
    """
    Returns (start_naive, end_naive) - the current daily cycle's
    03:00->03:00 Asia/Amman boundaries, converted to naive datetimes
    for comparison against trades.signal_time/close_time (TIMESTAMP,
    no timezone). See the module docstring for the one assumption this
    conversion relies on.
    """
    now_amman = datetime.now(timezone.utc).astimezone(AMMAN_TZ)
    cycle_start_amman = now_amman.replace(hour=CYCLE_START_HOUR, minute=0, second=0, microsecond=0)
    if now_amman.hour < CYCLE_START_HOUR:
        cycle_start_amman -= timedelta(days=1)
    cycle_end_amman = cycle_start_amman + timedelta(days=1)

    # Real, zoneinfo-computed UTC instants - then stripped to naive to
    # match the column type. This is the one point where the "naive
    # column = UTC" assumption is applied.
    start_naive = cycle_start_amman.astimezone(timezone.utc).replace(tzinfo=None)
    end_naive = cycle_end_amman.astimezone(timezone.utc).replace(tzinfo=None)
    return start_naive, end_naive, cycle_start_amman


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


def _fetch_daily_data():
    """
    Single connection, several queries - all read-only against `trades`.
    Returns a dict with generated/closed/open row lists, or None on
    total failure.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        start_utc, end_utc, cycle_start_amman = _cycle_boundaries_naive()

        cur.execute("SELECT COUNT(*) FROM trades WHERE signal_time >= %s AND signal_time < %s",
                     (start_utc, end_utc))
        generated_count = cur.fetchone()[0]

        cur.execute("""
            SELECT side, result, rr, brain_confidence
            FROM trades
            WHERE status = 'CLOSED' AND close_time >= %s AND close_time < %s
        """, (start_utc, end_utc))
        closed_today = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM trades WHERE status = 'OPEN'")
        open_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM trades WHERE status = 'CLOSED'")
        total_closed_alltime = cur.fetchone()[0]

        return {
            "generated_count": generated_count,
            "closed_today": closed_today,
            "open_count": open_count,
            "total_closed_alltime": total_closed_alltime,
            "start_utc": start_utc,
            "cycle_start_amman": cycle_start_amman,
        }
    except Exception as e:
        print(f"⚠️ Daily Report: failed to fetch data - {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _summarize(rows):
    """
    rows: list of (side, result, rr, brain_confidence) tuples.
    Win Rate excludes TIMEOUT from both numerator and denominator -
    Avg RR / Avg Brain Score are computed across all closed-today rows
    (TIMEOUT included), since those aren't Win Rate figures themselves.
    """
    n = len(rows)
    decided = [r for r in rows if r[1] != "TIMEOUT"]
    wins = sum(1 for r in decided if r[1] in ("WIN_TP1", "WIN_TP2", "WIN_TP3"))
    losses = len(decided) - wins
    win_rate = round((wins / len(decided)) * 100, 1) if decided else None

    rr_values = [r[2] for r in rows if r[2] is not None]
    bc_values = [r[3] for r in rows if r[3] is not None]

    return {
        "n": n, "wins": wins, "losses": losses, "win_rate": win_rate,
        "avg_rr": round(statistics.mean(rr_values), 2) if rr_values else None,
        "avg_brain": round(statistics.mean(bc_values), 1) if bc_values else None,
    }


def _direction_line(rows, side):
    side_rows = [r for r in rows if r[0] == side]
    s = _summarize(side_rows)
    if s["n"] < MIN_SAMPLE_SIZE:
        return f"{side}: {s['n']} trade(s) — Insufficient sample"
    return f"{side}: {s['n']} trades — {s['win_rate']}% WR, Avg RR {s['avg_rr']}"


def build_report_text(data):
    today_str = data["cycle_start_amman"].strftime("%Y-%m-%d")
    overall = _summarize(data["closed_today"])
    remaining = max(0, RESEARCH_TARGET_CLOSED_TRADES - data["total_closed_alltime"])

    lines = [
        f"📅 AHAD AI — Daily Report ({today_str})",
        "",
        f"📊 Generated: {data['generated_count']}  |  Closed: {overall['n']}  |  Open: {data['open_count']}",
    ]

    if overall["n"] == 0:
        lines.append("No trades closed today.")
    elif overall["n"] < MIN_SAMPLE_SIZE:
        lines.append(f"🟢 {overall['wins']}W  🔴 {overall['losses']}L  — Insufficient sample for Win Rate")
        if overall["avg_rr"] is not None:
            lines.append(f"⚖️ Avg RR: {overall['avg_rr']}  🧠 Avg Brain: {overall['avg_brain']}")
    else:
        lines.append(f"🟢 {overall['wins']}W  🔴 {overall['losses']}L  🎯 {overall['win_rate']}% WR")
        lines.append(f"⚖️ Avg RR: {overall['avg_rr']}  🧠 Avg Brain: {overall['avg_brain']}")

    lines.append("")
    lines.append(_direction_line(data["closed_today"], "LONG"))
    lines.append(_direction_line(data["closed_today"], "SHORT"))

    lines.append("")
    lines.append("📋 Research Progress")
    lines.append(f"Closed: {data['total_closed_alltime']} / {RESEARCH_TARGET_CLOSED_TRADES}")
    lines.append(f"Remaining: {remaining}")

    return "\n".join(lines)


def send_to_telegram(text):
    if not BOT_TOKEN or not ADMIN_USER_ID:
        print("⚠️ Daily Report: BOT_TOKEN or ADMIN_USER_ID not set - cannot send.")
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={"chat_id": ADMIN_USER_ID, "text": text}, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️ Daily Report: failed to send to Telegram - {e}")
        return False


def main():
    print(f"📅 Daily Report starting - {datetime.now().isoformat()}")
    data = _fetch_daily_data()
    if data is None:
        print("⚠️ Daily Report: no data - aborting without sending.")
        return
    text = build_report_text(data)
    print(text)
    sent = send_to_telegram(text)
    print(f"📅 Daily Report {'sent' if sent else 'FAILED to send'} - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
