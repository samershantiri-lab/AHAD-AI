"""
================================================================================
AHAD AI - Research Lab
Missed Opportunity Study
================================================================================

Determines whether AHAD AI rejected coins that later became Top
Gainers or Top Losers, and identifies which rejection reasons are
associated with those missed opportunities versus which are correctly
protecting AHAD AI from bad setups.

Completely independent from bot.py. This file:

- Is never imported by bot.py, and never imports anything from bot.py.
- Sends no Telegram messages of any kind.
- Never runs inside, or is called from, the live /scan path.
- Is READ-ONLY. It reads from research_rejections, research_top_
  gainers, and research_top_losers - never from `trades` or
  `versions`, and never writes to anything, anywhere. This module
  needs none of AHAD AI's own trade outcomes - only what it rejected
  and what the market subsequently did.

VERSION 1 DESIGN DECISIONS (approved):

1. Configurable lookback window (LOOKBACK_HOURS below) - not hardcoded,
   so the same module can be re-run with 24h/48h/72h/96h windows for
   comparison without any code change. The core analysis function also
   accepts an explicit override for one-off experimentation.

2. No database table in this version. This module reads existing
   research tables, computes, and prints a report - nothing is
   persisted. If historical storage of these reports is later found to
   have research value (e.g. once Research Lab moves to a scheduled,
   background-service architecture where Telegram commands only read
   the latest completed results rather than triggering analysis), a
   dedicated table can be added then - deliberately not built now to
   avoid unnecessary data duplication ahead of a confirmed need.

   WORTH FLAGGING NOW, NOT LATER: because there is no table, there is
   currently nothing for a future "read the latest report" Telegram
   command to retrieve for this specific study. That's an expected
   consequence of this version's own design, not an oversight - but it
   means this module will need a table (or another persistence
   mechanism) added before it can participate in a scheduled/background
   Research Lab architecture. Revisit at that time.

3. Extensible market-attribute registry (MARKET_ATTRIBUTES below)
   rather than a hardcoded "gainer vs loser" binary. Only change_pct,
   volume_ratio, and volume_acceleration are populated in the source
   tables today (volume figures only when a symbol also matched an
   AHAD AI trade - most rows will not have them, same "whenever
   available" caveat as Top Gainers/Losers Study itself). Duration of
   Move and Persistence of Trend are NOT included because nothing in
   the current schema captures them - research_top_gainers/losers store
   one point-in-time ~24h change, not a time series. Adding either
   later is a one-line addition to MARKET_ATTRIBUTES; the aggregation
   logic below iterates over whatever is registered rather than naming
   specific attributes, so no other code needs to change when that
   happens.

CLASSIFICATION METHODOLOGY - stated precisely, since getting this wrong
would produce a misleading conclusion rather than just an incomplete
one:

Of the six rejection reasons the Rejection Ledger tracks, only two
carry enough information to say which direction AHAD AI was evaluating
at the moment of rejection - Invalid RR (Fatal) and Validation Failed,
both of which fire after a specific direction's entry/SL/TP/RR have
already been computed. These two are classified as PROTECTED (the
rejected direction was the wrong side of the actual move - the
rejection helped) or MISSED (the rejected direction matched the actual
move - a real opportunity was likely lost).

The other four - Blocked Asset, Candles, High Price Asset, and Brain
WAIT - are NOT classified as protected or missed, and this is
deliberate, not an oversight. The first three fire before AI Brain ever
runs, so no direction was ever evaluated. Brain WAIT specifically means
AI Brain explicitly declined to commit to either direction - there is
no directional bet to judge against the actual move, even though
brain_long/brain_short scores are stored in context (those describe a
lean, not a decision, and are not used here to force a classification
the data doesn't cleanly support). These four are reported in their own
"Unclassifiable" bucket - visible and counted, never silently dropped,
never guessed at.
================================================================================
"""

import os
import sys
import json
import time
import psycopg2
from datetime import datetime, timedelta
from snapshot_writer import save_snapshot, update_snapshot_status

MODULE_KEY = "missed_opportunity_study"
MODULE_NAME = "Missed Opportunity Study"
MODULE_CATEGORY = "research_lab"
MODULE_VERSION = "1.0"


# ================================================
# 🔌 DATABASE CONNECTION
# ================================================
# Identical connection pattern to every other Research Lab module.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - Missed Opportunity "
            "Study needs the same DATABASE_URL bot.py uses to reach the same "
            "database."
        )
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode="require"
    )


# ================================================
# ⚙️ CONFIGURATION
# ================================================

# Default lookback window - how far back before a Top Gainer/Loser's
# observed_date to look for a matching rejection. Configurable rather
# than hardcoded, per the approved design, so future runs can compare
# 24h/48h/72h/96h windows without any code change. run_study() also
# accepts an explicit override for one-off experimentation without
# touching this default.
LOOKBACK_HOURS = 72

# Same sample-size convention used throughout Research Lab (Compare
# Winners/Losers, the version scoreboard) for confidence labeling -
# not a formal significance test, a transparent, consistent threshold.
MIN_SAMPLE_SIZE = 30

# Rejection reasons that carry a specific, already-computed direction
# (entry/SL/TP/RR) at the moment of rejection - see the module
# docstring for exactly why only these two qualify. Everything else
# lands in the "Unclassifiable" bucket, on purpose.
DIRECTIONAL_REJECT_REASONS_PREFIXES = ("Invalid RR", "Validation Failed")

# Extensible market-attribute registry (approved design point 2). Add a
# (column, label) pair here once a new attribute exists in
# research_top_gainers/research_top_losers - the aggregation below
# picks up any registered attribute automatically, nothing else needs
# to change. Duration of Move / Persistence of Trend are intentionally
# NOT listed - nothing in the current schema captures either yet.
MARKET_ATTRIBUTES = [
    ("change_pct", "Percentage Move"),
    ("volume_ratio", "Volume Ratio"),
    ("volume_acceleration", "Volume Acceleration"),
]


# ================================================
# 📥 DATA ACCESS - read-only against research_top_gainers/losers/rejections
# ================================================

def _fetch_movers(table):
    """Reads every row from research_top_gainers or research_top_losers."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        columns = ["symbol", "observed_date"] + [col for col, _ in MARKET_ATTRIBUTES]
        columns_sql = ", ".join(columns)
        cur.execute(f"SELECT {columns_sql} FROM {table}")
        rows = cur.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"⚠️ Missed Opportunity Study: failed to read {table} - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _fetch_rejections_in_window(cur, symbol, before_date, lookback_hours):
    """
    Reads every research_rejections row for this symbol whose
    rejected_at falls within [before_date - lookback_hours, before_date)
    - i.e. rejected before the move, within a bounded window, not at any
    point in history. Returns the full list (for counting persistent
    rejection) - the caller decides which one is "most recent".
    """
    window_start = before_date - timedelta(hours=lookback_hours)
    cur.execute("""
        SELECT reject_reason, context, rejected_at
        FROM research_rejections
        WHERE symbol = %s AND rejected_at >= %s AND rejected_at < %s
        ORDER BY rejected_at DESC
    """, (symbol, window_start, before_date))
    return cur.fetchall()


# ================================================
# 🧮 CLASSIFICATION - pure computation, no database access
# ================================================

def _is_directional_reason(reject_reason):
    return any(reject_reason.startswith(prefix) for prefix in DIRECTIONAL_REJECT_REASONS_PREFIXES)


def _extract_evaluated_side(context):
    """
    Determines which direction was being evaluated at rejection time,
    from the stored context - only meaningful for Invalid RR/Validation
    Failed, which store entry_low/sl/tp1 (side is inferred from
    tp1 vs entry_low, matching the same convention used everywhere else
    in this codebase: TP above entry = LONG, below = SHORT).
    """
    entry_low = context.get("entry_low")
    tp1 = context.get("tp1")
    if entry_low is None or tp1 is None:
        return None
    return "LONG" if tp1 > entry_low else "SHORT"


def _classify_match(reject_reason, context, actual_move_direction):
    """
    Returns "PROTECTED", "MISSED", or "UNCLASSIFIABLE" for one matched
    rejection. actual_move_direction is "UP" for a Top Gainer, "DOWN"
    for a Top Loser.
    """
    if not _is_directional_reason(reject_reason):
        return "UNCLASSIFIABLE"

    evaluated_side = _extract_evaluated_side(context)
    if evaluated_side is None:
        return "UNCLASSIFIABLE"

    move_side = "LONG" if actual_move_direction == "UP" else "SHORT"
    return "MISSED" if evaluated_side == move_side else "PROTECTED"


# ================================================
# 📊 STUDY LOGIC
# ================================================

def _analyze_movers(cur, movers, actual_move_direction, lookback_hours):
    """
    For one set of movers (gainers or losers), finds matching prior
    rejections and classifies each. Returns the aggregated result for
    this side of the study.
    """
    matched = 0
    reason_counts = {}
    classification_counts = {"PROTECTED": 0, "MISSED": 0, "UNCLASSIFIABLE": 0}
    classification_by_reason = {}
    market_attribute_values = {col: [] for col, _ in MARKET_ATTRIBUTES}

    for mover in movers:
        rejections = _fetch_rejections_in_window(
            cur, mover["symbol"], mover["observed_date"], lookback_hours
        )
        if not rejections:
            continue

        matched += 1
        # Most recent rejection in-window is treated as the reason most
        # directly associated with this opportunity - see module
        # docstring. Full count is still tallied for "persistent
        # rejection" context.
        most_recent_reason, most_recent_context_raw, _ = rejections[0]
        context = most_recent_context_raw if isinstance(most_recent_context_raw, dict) else (most_recent_context_raw or {})

        reason_counts[most_recent_reason] = reason_counts.get(most_recent_reason, 0) + 1

        classification = _classify_match(most_recent_reason, context, actual_move_direction)
        classification_counts[classification] += 1
        classification_by_reason.setdefault(most_recent_reason, {"PROTECTED": 0, "MISSED": 0, "UNCLASSIFIABLE": 0})
        classification_by_reason[most_recent_reason][classification] += 1

        for col, _ in MARKET_ATTRIBUTES:
            value = mover.get(col)
            if value is not None:
                market_attribute_values[col].append(value)

    market_attribute_summary = {}
    for col, label in MARKET_ATTRIBUTES:
        values = market_attribute_values[col]
        if values:
            market_attribute_summary[label] = {
                "avg": round(sum(values) / len(values), 4),
                "n": len(values),
            }
        else:
            market_attribute_summary[label] = {"avg": None, "n": 0}

    return {
        "total_checked": len(movers),
        "matched": matched,
        "match_rate_pct": round((matched / len(movers)) * 100, 2) if movers else 0.0,
        "reason_counts": reason_counts,
        "classification_counts": classification_counts,
        "classification_by_reason": classification_by_reason,
        "market_attributes": market_attribute_summary,
    }


def run_study(lookback_hours=None):
    """
    Runs the complete Missed Opportunity Study. Pure computation plus
    read-only fetches - no writes happen anywhere in this module.
    lookback_hours overrides LOOKBACK_HOURS for one-off experimentation
    without editing the module.
    """
    window = lookback_hours if lookback_hours is not None else LOOKBACK_HOURS

    gainers = _fetch_movers("research_top_gainers")
    losers = _fetch_movers("research_top_losers")

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        gainer_result = _analyze_movers(cur, gainers, "UP", window)
        loser_result = _analyze_movers(cur, losers, "DOWN", window)
    except Exception as e:
        print(f"⚠️ Missed Opportunity Study: failed during analysis - {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return {
        "run_timestamp": datetime.now().isoformat(),
        "lookback_hours": window,
        "gainers": gainer_result,
        "losers": loser_result,
    }


# ================================================
# 🖨 REPORT - prints a plain-text summary to stdout (no Telegram, ever)
# ================================================

def _confidence_label(n):
    if n >= MIN_SAMPLE_SIZE:
        return "Higher"
    if n >= MIN_SAMPLE_SIZE // 3:
        return "Moderate"
    return "Low"


def _print_side_section(title, result):
    print(f"\n{title}")
    print(f"  Checked: {result['total_checked']}  |  Matched to a prior rejection: "
          f"{result['matched']} ({result['match_rate_pct']}%)")

    if result["matched"] == 0:
        print("  No matches this run - nothing further to report for this side.")
        return

    print("\n  Rejection reasons among matches (most frequent first):")
    for reason, count in sorted(result["reason_counts"].items(), key=lambda x: x[1], reverse=True):
        print(f"    {reason}: {count}")

    print("\n  Classification (directional reasons only):")
    c = result["classification_counts"]
    print(f"    Protected: {c['PROTECTED']}  |  Missed: {c['MISSED']}  |  Unclassifiable: {c['UNCLASSIFIABLE']}")

    directional_reasons = {k: v for k, v in result["classification_by_reason"].items()
                            if v["PROTECTED"] + v["MISSED"] > 0}
    if directional_reasons:
        print("\n  By reason (directional only):")
        for reason, counts in directional_reasons.items():
            print(f"    {reason}: Protected {counts['PROTECTED']} / Missed {counts['MISSED']}")

    print("\n  Market attributes of matched opportunities:")
    for label, stats in result["market_attributes"].items():
        if stats["n"] > 0:
            print(f"    {label}: avg {stats['avg']} (n={stats['n']})")
        else:
            print(f"    {label}: no data available")


def print_report(result):
    if result is None:
        print("⚠️ Missed Opportunity Study: no result to report (analysis failed).")
        return

    print("\n" + "=" * 60)
    print("🔍 AHAD AI RESEARCH LAB - MISSED OPPORTUNITY STUDY")
    print("=" * 60)

    print("\nEXECUTIVE SUMMARY")
    print(f"Lookback window: {result['lookback_hours']} hours")
    g, l = result["gainers"], result["losers"]
    print(f"Top Gainers checked: {g['total_checked']}  |  Matched: {g['matched']} ({g['match_rate_pct']}%)")
    print(f"Top Losers checked:  {l['total_checked']}  |  Matched: {l['matched']} ({l['match_rate_pct']}%)")

    print("\n" + "-" * 60)
    print("KEY FINDINGS")
    print("-" * 60)
    findings = []
    for side_name, side_result, move_word in [("Gainer", g, "pumped"), ("Loser", l, "dropped")]:
        for reason, counts in side_result["classification_by_reason"].items():
            total = counts["PROTECTED"] + counts["MISSED"]
            if total >= MIN_SAMPLE_SIZE // 3 and counts["MISSED"] > counts["PROTECTED"]:
                pct = round((counts["MISSED"] / total) * 100, 1)
                findings.append(
                    f"- {reason} preceded a Top {side_name} that later {move_word} in "
                    f"{counts['MISSED']} of {total} classifiable cases ({pct}%) - "
                    f"more often a miss than a protection at current sample size."
                )
    if findings:
        for f in findings:
            print(f)
    else:
        print("No finding cleared the minimum sample threshold this run - see")
        print("Confidence Level below. This is an expected, honest outcome while")
        print("data is still accumulating, not a null result to act on.")

    print("\n" + "-" * 60)
    print("SUPPORTING STATISTICS")
    print("-" * 60)
    _print_side_section("TOP GAINERS", g)
    _print_side_section("TOP LOSERS", l)

    print("\n" + "-" * 60)
    print("CONFIDENCE LEVEL")
    print("-" * 60)
    for side_name, side_result in [("Top Gainers", g), ("Top Losers", l)]:
        print(f"  {side_name} match sample: {_confidence_label(side_result['matched'])} "
              f"(n={side_result['matched']})")
    print(f"  Threshold convention: Higher >= {MIN_SAMPLE_SIZE}, "
          f"Moderate >= {MIN_SAMPLE_SIZE // 3}, else Low - same convention used "
          f"throughout Research Lab, not a formal significance test.")

    print("\n" + "-" * 60)
    print("SUGGESTED FUTURE RESEARCH")
    print("-" * 60)
    print("  - Re-run with alternate LOOKBACK_HOURS (24/48/96) once more data")
    print("    exists, to check whether findings are sensitive to window choice.")
    print("  - Revisit any reason flagged above once its classifiable sample")
    print("    passes the Higher confidence threshold before treating it as a")
    print("    basis for any filter change.")
    print("  - Consider whether Duration of Move / Persistence of Trend would")
    print("    change these findings once those attributes are collected.")

    print("\n" + "=" * 60)
    print("Note: this is an observation report only - no automatic changes to")
    print("AHAD AI, no recommendations beyond what's stated above. A human")
    print("decides what, if anything, these findings mean for a future,")
    print("separately-reviewed change.")
    print("=" * 60 + "\n")


# ================================================
# ▶ ENTRY POINT
# ================================================

def main():
    update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "RUNNING")
    start_time = time.time()
    print(f"🔬 Missed Opportunity Study starting - {datetime.now().isoformat()}")

    try:
        result = run_study()
        print_report(result)

        if result is None:
            # run_study() already signals total failure this way by
            # design (e.g. an unreachable database) - treat it as a
            # real failure for the snapshot, not a successful save
            # with empty data.
            update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
            print(f"⚠️ Missed Opportunity Study: no result produced - marking snapshot as FAILED")
        else:
            g, l = result["gainers"], result["losers"]
            records_processed = g["total_checked"] + l["total_checked"]

            summary_data = {
                "lookback_hours": result["lookback_hours"],
                "gainers_checked": g["total_checked"],
                "gainers_matched": g["matched"],
                "gainers_match_rate_pct": g["match_rate_pct"],
                "losers_checked": l["total_checked"],
                "losers_matched": l["matched"],
                "losers_match_rate_pct": l["match_rate_pct"],
            }

            save_snapshot(
                module_key=MODULE_KEY,
                module_name=MODULE_NAME,
                category=MODULE_CATEGORY,
                headline_stat=f"Gainers: {g['matched']}/{g['total_checked']} matched a prior rejection "
                              f"({g['match_rate_pct']}%)  |  Losers: {l['matched']}/{l['total_checked']} "
                              f"({l['match_rate_pct']}%)",
                summary_data=summary_data,
                version_scope="ALL",
                detail_table=None,
                module_version=MODULE_VERSION,
                execution_duration_seconds=round(time.time() - start_time, 2),
                records_processed=records_processed,
            )

        print(f"🔬 Missed Opportunity Study finished - {datetime.now().isoformat()}")
    except Exception as e:
        update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
        print(f"⚠️ Missed Opportunity Study: unhandled error - {e}")
        raise


if __name__ == "__main__":
    main()
