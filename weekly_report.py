"""
================================================================================
AHAD AI - Reports Layer v1
Weekly Research Update
================================================================================

Standalone script, run via Render Cron - does not import bot.py, does
not run any Research Lab module, does not recompute any analysis.
Reads ONLY from research_snapshots, via the exact same _fetch_all_
snapshots()/formatter functions already used by /research_report -
imported from report_formatters.py, not reimplemented.

IMPORTANT - WHAT THIS REPORT ACTUALLY IS: research_snapshots carries
no period_start/period_end field, and market_conditioned_analysis.py /
winner_loser_dna_analysis.py both read ALL historical closed trades
(version_scope="ALL_VERSIONS", confirmed directly from their own
save_snapshot() calls) - never date-filtered. This is therefore NOT a
"last week's performance" report - it is a CUMULATIVE research state,
current as of the most recent Research Run. Every heading and every
line of this file says so explicitly, per the approved design - never
implying week-scoped numbers that don't exist.

SNAPSHOT FRESHNESS: a snapshot counts as belonging to "this week's"
Research Run if last_success_at falls within the CURRENT Sunday-to-
Sunday cycle (computed via zoneinfo, same mechanism as daily_report.py
- not a fixed day-count threshold). If no snapshot clears that bar,
the report still sends - with "⚠️ RESEARCH INCOMPLETE" for the
affected section(s), per the explicit requirement that a stale
snapshot must never be shown as current.

DESIGN NOTE ON WINNER DNA / LOSER DNA: the winner_loser_dna snapshot
computes DIFFERENTIATORS between winners and losers (strongest_overall/
long/short), not two independently-profiled "Winner DNA" and "Loser
DNA" datasets. This report presents that single comparison under both
headings, stated explicitly here rather than silently implying two
separate analyses exist when only one does.

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file. Read-only against research_
snapshots - no writes, no schema changes, no Research Lab module
execution.
================================================================================
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    print("⚠️ Weekly Report: zoneinfo unavailable (Python < 3.9) - aborting.")
    sys.exit(1)

from report_formatters import (
    _fetch_all_snapshots,
    _format_market_conditioned,
    _format_loss_clusters,
    _format_winner_loser_dna,
    format_elapsed,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID")

CYCLE_START_HOUR = 3  # 03:00 Asia/Amman, per the approved AHAD AI weekly cycle
WEEKLY_CYCLE_WEEKDAY = 6  # Python's date.weekday(): Sunday = 6

try:
    AMMAN_TZ = ZoneInfo("Asia/Amman")
except Exception as e:
    print(f"⚠️ Weekly Report: Asia/Amman timezone data unavailable - {e}")
    sys.exit(1)


def _current_sunday_cycle_start():
    """
    Returns (cycle_start_naive, cycle_start_amman) - the most recent
    Sunday 03:00 Asia/Amman, expressed both as a naive datetime (for
    comparison against research_snapshots.last_success_at, itself a
    naive TIMESTAMP written via datetime.now() - see the same
    assumption documented in daily_report.py) and as the real,
    zoneinfo-aware Amman instant (for display).
    """
    now_amman = datetime.now(timezone.utc).astimezone(AMMAN_TZ)
    days_since_sunday = (now_amman.weekday() - WEEKLY_CYCLE_WEEKDAY) % 7
    candidate = now_amman.replace(hour=CYCLE_START_HOUR, minute=0, second=0, microsecond=0) - timedelta(days=days_since_sunday)
    if candidate > now_amman:
        candidate -= timedelta(days=7)
    # naive comparison value: same "naive = server local time" assumption
    # daily_report.py documents - datetime.now() throughout bot.py/
    # snapshot_writer.py is not explicitly UTC, so the naive comparison
    # here uses Amman wall-clock time directly, matching how last_
    # success_at was actually written (datetime.now() on the server).
    cycle_start_naive = candidate.replace(tzinfo=None)
    return cycle_start_naive, candidate


def _is_current_cycle(snapshot, cycle_start_naive):
    if snapshot is None or snapshot.get("last_success_at") is None:
        return False
    return snapshot["last_success_at"] >= cycle_start_naive


def _section(title, module_key, snapshots, formatter, cycle_start_naive):
    snapshot = snapshots.get(module_key)
    lines = [title, "-" * 40]
    if not _is_current_cycle(snapshot, cycle_start_naive):
        lines.append("⚠️ RESEARCH INCOMPLETE")
        if snapshot and snapshot.get("last_success_at"):
            lines.append(f"(NO RECENT RESEARCH SNAPSHOT - last successful run: "
                          f"{format_elapsed(snapshot['last_success_at'])}, "
                          f"before this cycle's Research Run)")
        else:
            lines.append("(NO RECENT RESEARCH SNAPSHOT - this module has never completed successfully)")
        return "\n".join(lines)

    summary_data = snapshot["summary_data"]
    if isinstance(summary_data, str):
        import json
        try:
            summary_data = json.loads(summary_data)
        except Exception:
            summary_data = {}
    summary_data = summary_data or {}

    try:
        formatted = formatter(summary_data)
    except Exception as e:
        formatted = f"(Unable to format details - {snapshot.get('headline_stat', 'N/A')})"

    lines.append(f"Last Research Run: {format_elapsed(snapshot['last_success_at'])}")
    lines.append("")
    lines.append(formatted)
    return "\n".join(lines)


def _build_edge_findings(snapshots, cycle_start_naive):
    """
    Pulled directly from already-computed fields in the market_
    conditioned and winner_loser_dna snapshots - no new analysis, just
    selecting and re-presenting text that already exists.
    """
    lines = ["🏆 Quality / Edge Findings", "-" * 40]

    mc_snapshot = snapshots.get("market_conditioned")
    if _is_current_cycle(mc_snapshot, cycle_start_naive):
        summary_data = mc_snapshot["summary_data"]
        if isinstance(summary_data, str):
            import json
            try:
                summary_data = json.loads(summary_data)
            except Exception:
                summary_data = {}
        findings = (summary_data or {}).get("effect_findings") or []
        if findings:
            for f in findings:
                lines.append(f"• [{f['axis']}] {f['conclusion']}")
        else:
            lines.append("• N/A — DATA NOT AVAILABLE")
    else:
        lines.append("• ⚠️ RESEARCH INCOMPLETE (Market-Conditioned)")

    wld_snapshot = snapshots.get("winner_loser_dna")
    if _is_current_cycle(wld_snapshot, cycle_start_naive):
        summary_data = wld_snapshot["summary_data"]
        if isinstance(summary_data, str):
            import json
            try:
                summary_data = json.loads(summary_data)
            except Exception:
                summary_data = {}
        summary_data = summary_data or {}
        strongest = summary_data.get("strongest_overall")
        if strongest:
            lines.append(f"• Strongest overall differentiator: {strongest['metric']} "
                          f"({strongest['evidence_level']}, N={strongest['n_winners']}+{strongest['n_losers']})")
        else:
            lines.append("• NO RELIABLE DIFFERENTIATOR — INSUFFICIENT DATA")
        low_var = summary_data.get("low_variance_metrics") or []
        if low_var:
            lines.append(f"• Low Variance (unreliable gradient): {', '.join(low_var)}")
    else:
        lines.append("• ⚠️ RESEARCH INCOMPLETE (Winner/Loser DNA)")

    return "\n".join(lines)


def build_report_text():
    snapshots = _fetch_all_snapshots()
    cycle_start_naive, cycle_start_amman = _current_sunday_cycle_start()
    as_of = datetime.now(timezone.utc).astimezone(AMMAN_TZ)

    sections = [
        "🔬 AHAD AI — WEEKLY RESEARCH UPDATE",
        "",
        f"Research State:",
        f"through {as_of.strftime('%Y-%m-%d %H:%M')} Asia/Amman",
        "",
        "Scope:",
        "ALL CLOSED TRADES (cumulative research, not a week-scoped performance report)",
        "=" * 40,
        "",
        _section("🌡 Market-Conditioned Performance", "market_conditioned", snapshots,
                  _format_market_conditioned, cycle_start_naive),
        "",
        _section("🔴 Loss Clusters", "loss_clusters", snapshots,
                  _format_loss_clusters, cycle_start_naive),
        "",
        "🧬 Winner DNA / Loser DNA",
        "(differentiators between winners and losers - see design note)",
        _section("", "winner_loser_dna", snapshots, _format_winner_loser_dna, cycle_start_naive),
        "",
        _build_edge_findings(snapshots, cycle_start_naive),
        "",
        "Note: correlation only, never causation. A human decides what,",
        "if anything, these findings mean for a future, separately",
        "reviewed change.",
    ]
    return "\n".join(sections)


def send_to_telegram(text):
    if not BOT_TOKEN or not ADMIN_USER_ID:
        print("⚠️ Weekly Report: BOT_TOKEN or ADMIN_USER_ID not set - cannot send.")
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        # Telegram's 4096-char limit - split on section boundaries if needed.
        if len(text) <= 3900:
            chunks = [text]
        else:
            # Truncate any individual block that's still too large on its
            # own even after splitting on \n\n - mirrors bot.py's own
            # _pack_into_messages safety net, which a naive split-only
            # approach lacks (a single block with no double-newlines
            # could otherwise exceed Telegram's limit undetected).
            raw_blocks = text.split("\n\n")
            safe_blocks = []
            for block in raw_blocks:
                if len(block) > 3900:
                    cutoff = 3900 - 60
                    safe_blocks.append(block[:cutoff] + f"\n[TRUNCATED - {len(block) - cutoff} chars omitted]")
                else:
                    safe_blocks.append(block)

            chunks = []
            current = []
            current_len = 0
            for block in safe_blocks:
                block_len = len(block) + 2
                if current and current_len + block_len > 3900:
                    chunks.append("\n\n".join(current))
                    current, current_len = [], 0
                current.append(block)
                current_len += block_len
            if current:
                chunks.append("\n\n".join(current))

        all_sent = True
        for i, chunk in enumerate(chunks, 1):
            prefix = f"Part {i} of {len(chunks)}\n{'='*20}\n\n" if len(chunks) > 1 else ""
            response = requests.post(url, json={"chat_id": ADMIN_USER_ID, "text": prefix + chunk}, timeout=10)
            all_sent = all_sent and (response.status_code == 200)
        return all_sent
    except Exception as e:
        print(f"⚠️ Weekly Report: failed to send to Telegram - {e}")
        return False


def main():
    print(f"📆 Weekly Report starting - {datetime.now().isoformat()}")
    text = build_report_text()
    print(text)
    sent = send_to_telegram(text)
    print(f"📆 Weekly Report {'sent' if sent else 'FAILED to send'} - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
