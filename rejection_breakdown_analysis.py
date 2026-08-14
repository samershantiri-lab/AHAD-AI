"""
================================================================================
AHAD AI - Research Lab
Rejection Breakdown + Missed Opportunity Analysis (Research Layer v1, Part 3)
================================================================================

Not a registered Research Lab module - standalone, read-only. Reuses
missed_opportunity_study.py's proven direction-classification functions
(_is_directional_reason, _extract_evaluated_side, _classify_match) by
import rather than duplicating that logic - that file's own matching
is mover-centric (for each mover, find its most recent rejection);
this file is reject-centric (for each rejection, check whether it was
later followed by a qualifying market move) - a different iteration
direction, needed because the approved Miss Rate definition requires
Total Rejections as the denominator, not Total Movers Checked.

THREE DISCOVERIES FROM THIS SESSION, STATED HERE SO THEY TRAVEL WITH
THE CODE:

1. The label commonly used in discussion, "Brain WAIT", was NEVER the
   actual stored value - the real string written to reject_reason is
   exactly "Brain". Grouping/filtering uses "Brain" throughout this
   file.

2. "Invalid RR" and "Validation Failed" are never stored as exact,
   standalone strings - the real values are "Invalid RR (Fatal)" and
   f"Validation Failed: {details}" (variable suffix per specific
   error). This file groups by PREFIX for these two, matching the
   same convention missed_opportunity_study.py's own
   DIRECTIONAL_REJECT_REASONS_PREFIXES already uses.

3. Market Context at the moment of rejection is NOT captured anywhere,
   for any of the six reject reasons - confirmed by reading every
   research_record_rejection() call site directly; none of them pass
   market_regime, market_snapshot, market_health_score, or
   acceptance_rate. Section 6 of the approved spec (Market Context at
   rejection time) is therefore NOT answerable from research_rejections
   as it stands - this file reports that gap explicitly rather than
   substituting a different measurement without saying so.

A FOURTH DISCOVERY, ALSO STATED EXPLICITLY: LATE timing classification
(80% move completion) cannot be computed - only research_move_start_
proxy_60/75/90 were ever stored; no 80% threshold timestamp exists in
the database. LATE is reported as INSUFFICIENT DATA everywhere, per
the explicit instruction to never guess in place of missing data.

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file. Read-only against research_
rejections, research_top_gainers, and research_top_losers - no writes,
no schema changes, no new tables, no modification to any source table.
================================================================================
"""

import os
import sys
import json
from collections import defaultdict
from datetime import datetime, timedelta

import time

import psycopg2

from research_statistics import evidence_level, priority_score, MIN_SAMPLE_SIZE
from snapshot_writer import save_snapshot, update_snapshot_status

MODULE_KEY = "rejection_breakdown"
MODULE_NAME = "Rejection Breakdown + Missed Opportunity"
MODULE_CATEGORY = "research_lab"
MODULE_VERSION = "1.0"
from missed_opportunity_study import (
    _is_directional_reason,
    _extract_evaluated_side,
    _classify_match,
    LOOKBACK_HOURS,
)

EARLY_BUFFER_HOURS = 2  # matches the approved MOVE_START specification


DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - this script needs "
            "the same DATABASE_URL every other Research Lab module uses."
        )
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# 🏷️ REASON NORMALIZATION - discovery #1 and #2 applied here, once
# ================================================

def normalize_reason_group(reject_reason):
    """
    Groups by prefix for the two reasons that carry a variable suffix
    in the real data (Invalid RR (Fatal), Validation Failed: ...) -
    exact-string grouping would silently produce zero matches for
    both, since neither is ever stored as a bare, standalone string.
    Every other reason is used exactly as stored (discovery #1: the
    real value is "Brain", not "Brain WAIT").
    """
    if reject_reason is None:
        return "UNKNOWN"
    if reject_reason.startswith("Validation Failed"):
        return "Validation Failed"
    if reject_reason.startswith("Invalid RR"):
        return "Invalid RR"
    return reject_reason


# ================================================
# 📥 DATA ACCESS - read-only against research_rejections, research_top_gainers/losers only
# ================================================

def _fetch_all_rejections():
    """Every row in research_rejections, oldest first. Never touches any other table."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, symbol, reject_reason, context, rejected_at
            FROM research_rejections
            ORDER BY rejected_at ASC
        """)
        rows = cur.fetchall()
        rejections = []
        for rid, symbol, reason, context, rejected_at in rows:
            if isinstance(context, str):
                try:
                    context = json.loads(context)
                except Exception:
                    context = {}
            rejections.append({
                "id": rid, "symbol": symbol, "reject_reason": reason,
                "reason_group": normalize_reason_group(reason),
                "context": context if isinstance(context, dict) else {},
                "rejected_at": rejected_at,
            })
        return rejections
    except Exception as e:
        print(f"⚠️ Rejection Breakdown: failed to read research_rejections - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _fetch_movers(table, actual_move_direction):
    """
    Every row in research_top_gainers or research_top_losers, with the
    fields this analysis needs: symbol, observed_date, market_regime
    (Asset Market Regime of the ASSET at move-observation time - NOT
    market context at rejection time, see discovery #3 above).

    COLUMN SET CORRECTED per confirmed live-database verification: this
    function previously also selected research_move_start_proxy_60/75/
    90, which do NOT exist on the live research_top_gainers/research_
    top_losers tables (confirmed directly via information_schema.columns
    - CREATE TABLE IF NOT EXISTS never added those columns to tables
    that already existed before that definition was extended). That
    caused every call to fail with UndefinedColumn, silently caught and
    turned into an empty list - Gainers/Losers checked showed 0 while
    the module still reported SUCCESS. Now uses exactly the same
    column set missed_opportunity_study.py's own _fetch_movers()
    already relies on successfully (symbol, observed_date, plus
    market_regime here since match_rejections_to_movers()/_classify_
    timing() only ever read symbol/observed_date/proxy_75 - never
    change_pct/volume_ratio/volume_acceleration, which belong to a
    different analysis).

    proxy_60/75/90 are kept as explicit None in the returned dict, not
    dropped - _classify_timing() already handles their absence safely
    via mover.get("proxy_75"), so no downstream code needed to change;
    timing will correctly and honestly report INSUFFICIENT DATA rather
    than guessing.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT symbol, observed_date, market_regime
            FROM {table}
        """)
        rows = cur.fetchall()
        movers = []
        for symbol, observed_date, regime in rows:
            movers.append({
                "symbol": symbol, "observed_date": observed_date, "market_regime": regime,
                "proxy_60": None, "proxy_75": None, "proxy_90": None,
                "actual_move_direction": actual_move_direction,
            })
        return movers
    except Exception as e:
        # A genuine failure here must surface as a real module failure,
        # not silently degrade to an empty list reported as SUCCESS -
        # exactly the bug this fix addresses. Log for diagnosis, then
        # re-raise so main()'s own except block marks the run FAILED.
        print(f"⚠️ Rejection Breakdown: failed to read {table} - {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 🔗 REJECT-CENTRIC MATCHING (per approved spec - Total Rejections is the denominator)
# ================================================

def _window_bounds(observed_date, lookback_hours):
    """[observed_date - lookback_hours, observed_date + 1 day) as datetimes - mirrors missed_opportunity_study.py's own window convention."""
    window_end = datetime.combine(observed_date, datetime.min.time()) + timedelta(days=1)
    window_start = window_end - timedelta(hours=lookback_hours)
    return window_start, window_end


def _classify_timing(rejected_at, mover):
    """
    BEFORE/EARLY/DURING per the approved MOVE_START specification.
    LATE is ALWAYS "INSUFFICIENT DATA" - no 80% threshold timestamp
    was ever computed or stored (discovery #4). Returns
    "INSUFFICIENT DATA" if proxy_75 itself is missing for this mover -
    never guesses a boundary from data that isn't there.
    """
    proxy_75 = mover.get("proxy_75")
    if proxy_75 is None:
        return "INSUFFICIENT DATA"
    early_end = proxy_75 + timedelta(hours=EARLY_BUFFER_HOURS)
    if rejected_at < proxy_75:
        return "BEFORE"
    elif rejected_at < early_end:
        return "EARLY"
    else:
        return "DURING"  # LATE cannot be distinguished from DURING - see discovery #4


def match_rejections_to_movers(rejections, gainers, losers, lookback_hours=LOOKBACK_HOURS):
    """
    For each individual rejection, finds the EARLIEST qualifying mover
    (same symbol, rejected_at within [observed_date - lookback_hours,
    observed_date + 1 day)) across both gainers and losers combined.
    Each rejection contributes to the result exactly once, regardless
    of how many movers might qualify - satisfies the "never double-
    count the same rejection" requirement by construction (iterating
    per rejection, not per mover).
    """
    movers_by_symbol = defaultdict(list)
    for m in gainers + losers:
        movers_by_symbol[m["symbol"]].append(m)
    for symbol in movers_by_symbol:
        movers_by_symbol[symbol].sort(key=lambda m: m["observed_date"])

    results = []
    for r in rejections:
        matched_mover = None
        for m in movers_by_symbol.get(r["symbol"], []):
            window_start, window_end = _window_bounds(m["observed_date"], lookback_hours)
            if window_start <= r["rejected_at"] < window_end:
                matched_mover = m
                break  # earliest qualifying match, deterministic given the sort above

        entry = {"rejection": r, "matched_mover": matched_mover,
                  "classification": None, "timing": None}
        if matched_mover is not None:
            entry["classification"] = _classify_match(
                r["reject_reason"], r["context"], matched_mover["actual_move_direction"]
            )
            entry["timing"] = _classify_timing(r["rejected_at"], matched_mover)
        results.append(entry)
    return results


# ================================================
# 📊 AGGREGATION BY REASON GROUP
# ================================================

def aggregate_by_reason(matched_results):
    """
    Groups the reject-centric match results by normalized reason group.
    Reports ALL REJECTIONS vs REJECTIONS THAT BECAME MISSED
    OPPORTUNITIES as two clearly separate counts (per the explicit
    requirement never to conflate them) - Match Rate covers "any later
    move matched" (including PROTECTED/UNCLASSIFIABLE), Miss Rate
    covers "confirmed MISSED" specifically.
    """
    groups = defaultdict(lambda: {
        "total_rejections": 0, "matched": 0, "missed": 0, "protected": 0,
        "unclassifiable_matched": 0, "evaluated_long": 0, "evaluated_short": 0,
        "timing_counts": defaultdict(int), "regime_counts_when_missed": defaultdict(int),
    })

    for entry in matched_results:
        reason_group = entry["rejection"]["reason_group"]
        g = groups[reason_group]
        g["total_rejections"] += 1

        if entry["matched_mover"] is None:
            continue

        g["matched"] += 1
        classification = entry["classification"]
        if classification == "MISSED":
            g["missed"] += 1
            regime = entry["matched_mover"].get("market_regime")
            if regime:
                g["regime_counts_when_missed"][regime] += 1
        elif classification == "PROTECTED":
            g["protected"] += 1
        else:
            g["unclassifiable_matched"] += 1

        if _is_directional_reason(entry["rejection"]["reject_reason"]):
            side = _extract_evaluated_side(entry["rejection"]["context"])
            if side == "LONG":
                g["evaluated_long"] += 1
            elif side == "SHORT":
                g["evaluated_short"] += 1

        if entry["timing"]:
            g["timing_counts"][entry["timing"]] += 1

    return dict(groups)


def _cell_evidence_for_reason(group_stats, all_totals, all_missed):
    """
    Evidence Level for one reason's Miss Rate against the pooled
    baseline of every OTHER reason combined - answers "is this
    reason's miss rate meaningfully different from the rest", gated
    on MIN_SAMPLE_SIZE per research_statistics.py, never bypassed.
    """
    n1 = group_stats["total_rejections"]
    n2 = all_totals - n1
    if n1 < MIN_SAMPLE_SIZE or n2 < MIN_SAMPLE_SIZE:
        return "INSUFFICIENT DATA"
    rate_a = [1] * group_stats["missed"] + [0] * (n1 - group_stats["missed"])
    other_missed = all_missed - group_stats["missed"]
    rate_b = [1] * other_missed + [0] * (n2 - other_missed)
    return evidence_level(n1, n2, rate_a, rate_b)


# ================================================
# 🖨 REPORT
# ================================================

def print_report(rejections, gainers, losers):
    matched_results = match_rejections_to_movers(rejections, gainers, losers)
    groups = aggregate_by_reason(matched_results)

    total_rejections_all = len(rejections)
    total_missed_all = sum(g["missed"] for g in groups.values())

    print("\n" + "=" * 70)
    print("🔬 AHAD AI RESEARCH LAB - REJECTION BREAKDOWN + MISSED OPPORTUNITY")
    print("=" * 70)
    print(f"Total rejections analyzed: {total_rejections_all}")
    print(f"Total gainers checked: {len(gainers)}  |  Total losers checked: {len(losers)}")
    print("\n⚠️ DATA AVAILABILITY NOTICE (read before interpreting anything below):")
    print("  - Market Context AT REJECTION TIME is not captured for any reason -")
    print("    confirmed by reading every research_record_rejection() call site.")
    print("    'Regime when later missed' below describes the ASSET's regime at the")
    print("    move's own observation time, NOT the market condition at rejection.")
    print("  - LATE timing is always INSUFFICIENT DATA - no 80% threshold timestamp")
    print("    was ever computed or stored; only 60/75/90 MOVE_START proxies exist.")

    print("\n" + "-" * 70)
    print("LEVEL 1 - SUMMARY")
    print("-" * 70)

    if not groups:
        print("No rejections found - nothing to summarize.")
    else:
        by_missed = sorted(groups.items(), key=lambda kv: kv[1]["missed"], reverse=True)
        top_reason, top_stats = by_missed[0]
        print(f"\nTop reason by raw Missed Opportunity count: {top_reason} "
              f"({top_stats['missed']} missed, n={top_stats['total_rejections']})")

        miss_rates = []
        for reason, g in groups.items():
            if g["total_rejections"] >= MIN_SAMPLE_SIZE:
                miss_rate = round((g["missed"] / g["total_rejections"]) * 100, 2)
                miss_rates.append((reason, miss_rate, g["total_rejections"]))
        if miss_rates:
            miss_rates.sort(key=lambda x: x[1], reverse=True)
            print(f"Top reason by Miss Rate (n>={MIN_SAMPLE_SIZE} only): "
                  f"{miss_rates[0][0]} - {miss_rates[0][1]}% (n={miss_rates[0][2]})")
        else:
            print(f"Top reason by Miss Rate: INSUFFICIENT DATA (no reason group has n>={MIN_SAMPLE_SIZE})")

        directional_long = sum(g["evaluated_long"] for g in groups.values())
        directional_short = sum(g["evaluated_short"] for g in groups.values())
        if directional_long + directional_short >= MIN_SAMPLE_SIZE:
            print(f"Direction split among classifiable matched rejections: "
                  f"LONG={directional_long}, SHORT={directional_short}")
        else:
            print(f"Direction split: INSUFFICIENT DATA (n={directional_long + directional_short})")

        all_regimes = defaultdict(int)
        for g in groups.values():
            for regime, count in g["regime_counts_when_missed"].items():
                all_regimes[regime] += count
        if all_regimes and sum(all_regimes.values()) >= MIN_SAMPLE_SIZE:
            top_regime = max(all_regimes.items(), key=lambda kv: kv[1])
            print(f"Most common Asset Regime among Missed Opportunities: "
                  f"{top_regime[0]} ({top_regime[1]} of {sum(all_regimes.values())})")
        else:
            print(f"Most common Asset Regime among Missed Opportunities: "
                  f"INSUFFICIENT DATA (n={sum(all_regimes.values())})")

    print("\n" + "-" * 70)
    print("LEVEL 2 - DETAILED TABLE BY REASON")
    print("-" * 70)
    header = f"{'Reason':<22}{'Rejections':<12}{'Matched':<10}{'Missed':<8}{'Match%':<9}{'Miss%':<8}{'Evidence'}"
    print(header)
    print("-" * len(header))
    for reason, g in sorted(groups.items(), key=lambda kv: kv[1]["total_rejections"], reverse=True):
        n = g["total_rejections"]
        match_pct = round((g["matched"] / n) * 100, 2) if n else 0.0
        miss_pct = round((g["missed"] / n) * 100, 2) if n else 0.0
        ev = _cell_evidence_for_reason(g, total_rejections_all, total_missed_all)
        print(f"{reason:<22}{n:<12}{g['matched']:<10}{g['missed']:<8}{match_pct:<9}{miss_pct:<8}{ev}")

    print("\n[Direction Discipline per reason]")
    for reason, g in groups.items():
        directional = _is_directional_reason(reason) if reason in ("Invalid RR", "Validation Failed") else False
        if directional:
            print(f"  {reason}: LONG={g['evaluated_long']}, SHORT={g['evaluated_short']}")
        else:
            print(f"  {reason}: UNCLASSIFIABLE (not a directional reason)")

    print("\n[Timing breakdown per reason, among matched rejections]")
    for reason, g in groups.items():
        if g["matched"] == 0:
            print(f"  {reason}: no matched rejections")
            continue
        timing_str = ", ".join(f"{k}={v}" for k, v in g["timing_counts"].items())
        print(f"  {reason}: {timing_str if timing_str else 'INSUFFICIENT DATA'}")

    print("\n" + "=" * 70)
    print("Note: correlation only, never causation. A human decides what, if")
    print("anything, these findings mean for a future, separately reviewed change.")
    print("=" * 70 + "\n")

    # Returned for main() to build the snapshot from - every value here
    # was already computed above for the console report itself.
    top_reason_by_missed = None
    top_reason_by_miss_rate = None
    if groups:
        by_missed = sorted(groups.items(), key=lambda kv: kv[1]["missed"], reverse=True)
        top_reason_by_missed = {"reason": by_missed[0][0], "missed": by_missed[0][1]["missed"],
                                  "n": by_missed[0][1]["total_rejections"]}
        eligible = [(r, round((g["missed"] / g["total_rejections"]) * 100, 2), g["total_rejections"])
                    for r, g in groups.items() if g["total_rejections"] >= MIN_SAMPLE_SIZE]
        if eligible:
            eligible.sort(key=lambda x: x[1], reverse=True)
            top_reason_by_miss_rate = {"reason": eligible[0][0], "miss_rate_pct": eligible[0][1], "n": eligible[0][2]}

    return {
        "total_rejections": total_rejections_all,
        "gainers_checked": len(gainers), "losers_checked": len(losers),
        "top_reason_by_missed": top_reason_by_missed,
        "top_reason_by_miss_rate": top_reason_by_miss_rate,
        "reason_table": {reason: {"total_rejections": g["total_rejections"], "matched": g["matched"],
                                    "missed": g["missed"]} for reason, g in groups.items()},
    }


def main():
    update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "RUNNING")
    start_time = time.time()
    print(f"🔬 Rejection Breakdown + Missed Opportunity Analysis starting - {datetime.now().isoformat()}")

    try:
        rejections = _fetch_all_rejections()
        gainers = _fetch_movers("research_top_gainers", "UP")
        losers = _fetch_movers("research_top_losers", "DOWN")

        if not rejections:
            print("⚠️ No rejections retrieved - nothing to analyze.")
            # No save_snapshot() call here - the Runner correctly
            # reports PARTIAL (last_success_at does not advance)
            # rather than a false SUCCESS with no real content.
            return

        summary = print_report(rejections, gainers, losers)

        if summary["top_reason_by_missed"]:
            headline_stat = (f"Top reason by Missed Opportunities: {summary['top_reason_by_missed']['reason']} "
                              f"({summary['top_reason_by_missed']['missed']} missed, n={summary['top_reason_by_missed']['n']})")
        else:
            headline_stat = "No rejections matched to a later Top Gainer/Loser move"

        ok = save_snapshot(
            module_key=MODULE_KEY,
            module_name=MODULE_NAME,
            category=MODULE_CATEGORY,
            headline_stat=headline_stat,
            summary_data=summary,
            version_scope="ALL_VERSIONS",
            detail_table=None,
            module_version=MODULE_VERSION,
            execution_duration_seconds=round(time.time() - start_time, 2),
            records_processed=summary["total_rejections"],
        )
        if not ok:
            raise RuntimeError("snapshot write failed")

        print(f"🔬 Rejection Breakdown + Missed Opportunity Analysis: recorded {summary['total_rejections']} analyzed rejection(s)")
        print(f"🔬 Rejection Breakdown + Missed Opportunity Analysis finished - {datetime.now().isoformat()}")
    except Exception as e:
        update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
        print(f"⚠️ Rejection Breakdown + Missed Opportunity Analysis: unhandled error - {e}")
        raise


if __name__ == "__main__":
    main()
