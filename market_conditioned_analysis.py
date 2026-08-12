"""
================================================================================
AHAD AI - Research Lab
Market-Conditioned Analysis (Research Layer v1, Part 2)
================================================================================

Not a registered Research Lab module - standalone, read-only, run
manually or via research_runner.py's pattern. Reads directly from
`trades` (not research_winners/research_losers) because market_regime,
market_snapshot, and market_health_score live there - research_winners/
losers only carry these for the small, still-growing subset of records
collected since the recent extension.

TWO DISTINCT MARKET AXES, NEVER CONFLATED (per explicit requirement):
- Asset Market Regime (trades.market_regime): TRENDING/RANGING/MIXED -
  a property of the individual symbol at analysis time.
- Global Market Condition (trades.market_snapshot->'condition'):
  BULL/BEAR/SIDEWAYS - a property of the whole market at scan time,
  shared identically across every signal from the same scan.

CORE QUESTION THIS MODULE EXISTS TO ANSWER: is SHORT's apparent
advantage a genuine Direction Effect, or explainable by the Market
Condition Effect (i.e. SHORT simply traded more often, or more
successfully, under conditions that favor it anyway)? Answered by
comparing LONG vs SHORT win rate WITHIN each regime/condition bucket
separately, not from the raw pooled win rate - and only where each
cell clears the approved sample-size threshold.

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file. Read-only against `trades` - no
writes, no schema changes, no new tables.
================================================================================
"""

import os
import sys
import json
import statistics
from collections import defaultdict
from datetime import datetime

import psycopg2

from research_statistics import evidence_level, priority_score, MIN_SAMPLE_SIZE


DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - this script needs "
            "the same DATABASE_URL every other Research Lab module uses."
        )
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# 📥 DATA ACCESS - read-only against `trades` only
# ================================================

def _fetch_trades():
    """
    Reads every CLOSED, decided (non-TIMEOUT) trade with the fields
    this analysis needs. Returns a list of dicts. Never touches any
    other table.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, side, result, close_time, market_regime,
                   market_snapshot, market_health_score, rr, score
            FROM trades
            WHERE status = 'CLOSED' AND result != 'TIMEOUT'
            ORDER BY close_time ASC
        """)
        rows = cur.fetchall()
        columns = ["id", "side", "result", "close_time", "market_regime",
                   "market_snapshot", "market_health_score", "rr", "score"]
        trades = []
        for row in rows:
            d = dict(zip(columns, row))
            snapshot = d.get("market_snapshot")
            if isinstance(snapshot, str):
                try:
                    snapshot = json.loads(snapshot)
                except Exception:
                    snapshot = None
            d["global_condition"] = snapshot.get("condition") if isinstance(snapshot, dict) else None
            d["acceptance_rate"] = snapshot.get("acceptance_rate") if isinstance(snapshot, dict) else None
            d["is_win"] = d["result"] in ("WIN_TP1", "WIN_TP2", "WIN_TP3")
            trades.append(d)
        return trades
    except Exception as e:
        print(f"⚠️ Market-Conditioned Analysis: failed to read trades - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📊 CELL STATISTICS - one function, reused for every table
# ================================================

def _cell_stats(rows):
    """Given a list of trade dicts, returns the standard cell: N/Wins/Losses/WR/AvgRR/AvgScore."""
    n = len(rows)
    wins = sum(1 for r in rows if r["is_win"])
    losses = n - wins
    win_rate = round((wins / n) * 100, 2) if n else None
    rr_values = [r["rr"] for r in rows if r.get("rr") is not None]
    score_values = [r["score"] for r in rows if r.get("score") is not None]
    return {
        "n": n, "wins": wins, "losses": losses, "win_rate": win_rate,
        "avg_rr": round(statistics.mean(rr_values), 3) if rr_values else None,
        "avg_score": round(statistics.mean(score_values), 2) if score_values else None,
    }


def _cell_evidence(rows_a, rows_b, metric="rr"):
    """Evidence level comparing two cells on a chosen numeric metric (default RR)."""
    a = [r[metric] for r in rows_a if r.get(metric) is not None]
    b = [r[metric] for r in rows_b if r.get(metric) is not None]
    return evidence_level(len(rows_a), len(rows_b), a, b)


# ================================================
# SECTION 1 - Direction × Asset Market Regime
# ================================================

def direction_x_asset_regime(trades):
    regimes = sorted(set(t["market_regime"] for t in trades if t["market_regime"]))
    table = {}
    for regime in regimes:
        long_rows = [t for t in trades if t["side"] == "LONG" and t["market_regime"] == regime]
        short_rows = [t for t in trades if t["side"] == "SHORT" and t["market_regime"] == regime]
        table[regime] = {
            "LONG": _cell_stats(long_rows),
            "SHORT": _cell_stats(short_rows),
            "evidence_level": _cell_evidence(long_rows, short_rows),
        }
    return table


# ================================================
# SECTION 2 - Direction × Global Market Condition
# ================================================

def direction_x_global_condition(trades):
    conditions = sorted(set(t["global_condition"] for t in trades if t["global_condition"]))
    table = {}
    for condition in conditions:
        long_rows = [t for t in trades if t["side"] == "LONG" and t["global_condition"] == condition]
        short_rows = [t for t in trades if t["side"] == "SHORT" and t["global_condition"] == condition]
        table[condition] = {
            "LONG": _cell_stats(long_rows),
            "SHORT": _cell_stats(short_rows),
            "evidence_level": _cell_evidence(long_rows, short_rows),
        }
    return table


# ================================================
# SECTION 3 / 4 - Quartile-based analysis (Market Health, Acceptance)
# ================================================

def _quartile_boundaries(values):
    """UNCHANGED from before this fix - returns the 3 raw cut points from the actual data, never assumed fixed ranges."""
    if len(values) < 4:
        return None
    sorted_vals = sorted(values)
    return statistics.quantiles(sorted_vals, n=4)


def _effective_groups(boundaries):
    """
    Determines the actual number of distinguishable value-based groups
    from the 3 raw boundaries - fewer than 4 when adjacent boundaries
    collide exactly (heavy value clustering). Exact equality is the
    detection criterion (not an arbitrary "closeness" threshold) - it's
    the precise, deterministic condition under which the old chained
    <= comparison logic produced a structurally empty bucket, and it
    requires no new undocumented parameter to justify.
    """
    return sorted(set(boundaries))


def _assign_bucket(value, distinct_boundaries):
    """
    Assigns using ONLY the distinct boundary set - a pure value-based
    partition. Never rank-based, so identical values always land in
    the same bucket together, and no row is ever moved between buckets
    to force equal group sizes (per the explicit requirement).
    """
    if value is None or not distinct_boundaries:
        return None
    for i, b in enumerate(distinct_boundaries):
        if value <= b:
            return f"Group {i + 1}"
    return f"Group {len(distinct_boundaries) + 1}"


def quartile_x_direction(trades, field_name):
    """
    Generic quartile analysis for a numeric field (market_health_score
    or acceptance_rate). Boundaries computed from the trades that
    actually have this field populated - not assumed. Reports the
    REAL number of distinguishable groups - determined by which
    buckets actually contain at least one value, not by boundary
    arithmetic alone (a fully-degenerate case where every value is
    identical would otherwise still imply a trailing empty group,
    caught during testing before this was delivered).
    """
    values = [t[field_name] for t in trades if t.get(field_name) is not None]
    boundaries = _quartile_boundaries(values)
    if boundaries is None:
        return {"available": False, "reason": f"Fewer than 4 non-null values for {field_name} - "
                                                 f"cannot compute quartiles (n={len(values)})."}

    distinct_boundaries = _effective_groups(boundaries)

    # Determine which groups actually contain at least one value -
    # not just how many the boundary arithmetic nominally allows.
    assigned_labels = set()
    for v in values:
        label = _assign_bucket(v, distinct_boundaries)
        if label:
            assigned_labels.add(label)
    ordered_labels = sorted(assigned_labels, key=lambda l: int(l.split()[1]))
    effective_group_count = len(ordered_labels)

    low_resolution_warning = None
    if effective_group_count < 4:
        collided = 4 - effective_group_count
        low_resolution_warning = (
            f"LOW DISTRIBUTION RESOLUTION — {field_name} too clustered for reliable quartile analysis "
            f"(only {effective_group_count} distinguishable group(s) instead of 4; "
            f"{collided} quartile boundary/boundaries collided exactly or produced no members)."
        )

    table = {}
    for label in ordered_labels:
        long_rows = [t for t in trades if t["side"] == "LONG" and _assign_bucket(t.get(field_name), distinct_boundaries) == label]
        short_rows = [t for t in trades if t["side"] == "SHORT" and _assign_bucket(t.get(field_name), distinct_boundaries) == label]
        table[label] = {
            "LONG": _cell_stats(long_rows),
            "SHORT": _cell_stats(short_rows),
            "evidence_level": _cell_evidence(long_rows, short_rows),
        }

    return {
        "available": True,
        "boundaries": [round(b, 2) for b in boundaries],
        "effective_group_count": effective_group_count,
        "low_resolution_warning": low_resolution_warning,
        "table": table,
    }


# ================================================
# SECTION 5 - Direction Effect vs Market Condition Effect
# ================================================

def direction_vs_condition_effect(regime_table, condition_table):
    """
    The core strategic question. For each axis, checks whether SHORT's
    win rate exceeds LONG's WITHIN every sufficiently-sampled bucket -
    if so, that's evidence for a genuine Direction Effect independent
    of condition. If SHORT's advantage only appears in some buckets
    and reverses or disappears in others, that points to a Market
    Condition Effect instead. Never claims causation - reports the
    pattern observed, with each bucket's own evidence level attached.
    """
    findings = []
    for axis_name, table in [("Asset Market Regime", regime_table), ("Global Market Condition", condition_table)]:
        bucket_results = []
        for bucket, data in table.items():
            long_stats, short_stats = data["LONG"], data["SHORT"]
            if long_stats["n"] < MIN_SAMPLE_SIZE or short_stats["n"] < MIN_SAMPLE_SIZE:
                bucket_results.append((bucket, "INSUFFICIENT DATA", None))
                continue
            diff = short_stats["win_rate"] - long_stats["win_rate"]
            bucket_results.append((bucket, data["evidence_level"], diff))

        sufficient = [(b, lvl, diff) for b, lvl, diff in bucket_results if diff is not None]
        if not sufficient:
            findings.append({
                "axis": axis_name,
                "conclusion": "INSUFFICIENT DATA across all buckets on this axis - "
                               "cannot separate Direction Effect from Market Condition Effect yet.",
                "buckets": bucket_results,
            })
            continue

        short_favored_everywhere = all(diff > 0 for _, _, diff in sufficient)
        short_favored_nowhere = all(diff <= 0 for _, _, diff in sufficient)
        if short_favored_everywhere and len(sufficient) > 1:
            conclusion = ("SHORT outperforms LONG in every sufficiently-sampled bucket on this axis - "
                          "consistent with a genuine Direction Effect, not explained by this axis alone.")
        elif short_favored_nowhere:
            conclusion = ("SHORT does NOT outperform LONG in any sufficiently-sampled bucket on this axis - "
                          "the pooled SHORT advantage is NOT confirmed here; it may be driven by a different factor.")
        else:
            conclusion = ("SHORT's advantage appears in some buckets but not others on this axis - "
                          "consistent with a Market Condition Effect contributing to the pooled result, "
                          "not a uniform Direction Effect.")
        findings.append({"axis": axis_name, "conclusion": conclusion, "buckets": bucket_results})
    return findings


# ================================================
# SECTION 6 - Cross Analysis (Direction × Axis × Outcome) - reuses tables above directly
# ================================================
# direction_x_asset_regime() and direction_x_global_condition() already
# ARE this cross analysis - no separate function needed, avoiding
# duplicated logic.


# ================================================
# SECTION 7 - Loss Clusters × available Market Context
# ================================================

def detect_loss_clusters(trades, min_cluster_length=2):
    """
    Groups trades by side, orders by close_time (already the fetch
    order), finds consecutive LOSS_SL runs >= min_cluster_length.
    Returns a list of clusters, each with its member trades' market
    context attached - informational only, no AI Brain implication.
    """
    clusters = []
    for side in ["LONG", "SHORT"]:
        side_trades = [t for t in trades if t["side"] == side]
        current_run = []
        for t in side_trades:
            if t["result"] == "LOSS_SL":
                current_run.append(t)
            else:
                if len(current_run) >= min_cluster_length:
                    clusters.append({"side": side, "length": len(current_run), "trades": current_run})
                current_run = []
        if len(current_run) >= min_cluster_length:
            clusters.append({"side": side, "length": len(current_run), "trades": current_run})
    return clusters


def summarize_loss_clusters(clusters):
    if not clusters:
        return {"available": False, "reason": "No loss clusters (length >= 2) found in this sample."}

    regime_counts = defaultdict(int)
    condition_counts = defaultdict(int)
    health_values = []
    acceptance_values = []
    total_trades_in_clusters = 0

    for cluster in clusters:
        for t in cluster["trades"]:
            total_trades_in_clusters += 1
            if t["market_regime"]:
                regime_counts[t["market_regime"]] += 1
            if t["global_condition"]:
                condition_counts[t["global_condition"]] += 1
            if t["market_health_score"] is not None:
                health_values.append(t["market_health_score"])
            if t["acceptance_rate"] is not None:
                acceptance_values.append(t["acceptance_rate"])

    sufficient = total_trades_in_clusters >= MIN_SAMPLE_SIZE
    return {
        "available": True,
        "cluster_count": len(clusters),
        "total_trades_in_clusters": total_trades_in_clusters,
        "evidence_note": "INSUFFICIENT DATA for a reliable pattern" if not sufficient else
                          "Sample large enough to describe, still Research Observation only",
        "regime_distribution": dict(regime_counts),
        "condition_distribution": dict(condition_counts),
        "avg_health_in_clusters": round(statistics.mean(health_values), 2) if health_values else None,
        "avg_acceptance_in_clusters": round(statistics.mean(acceptance_values), 2) if acceptance_values else None,
    }


# ================================================
# 🖨 REPORT
# ================================================

def _print_direction_table(table, axis_label):
    print(f"\n[{axis_label}]")
    for bucket, data in table.items():
        l, s = data["LONG"], data["SHORT"]
        print(f"  {bucket}:")
        print(f"    LONG:  n={l['n']}  WR={l['win_rate']}%  AvgRR={l['avg_rr']}  AvgScore={l['avg_score']}")
        print(f"    SHORT: n={s['n']}  WR={s['win_rate']}%  AvgRR={s['avg_rr']}  AvgScore={s['avg_score']}")
        print(f"    Evidence Level: {data['evidence_level']}")


def print_report(trades):
    print("\n" + "=" * 70)
    print("🔬 AHAD AI RESEARCH LAB - MARKET-CONDITIONED ANALYSIS")
    print("=" * 70)
    print(f"Total decided trades analyzed: {len(trades)}")

    regime_table = direction_x_asset_regime(trades)
    condition_table = direction_x_global_condition(trades)
    health_result = quartile_x_direction(trades, "market_health_score")
    acceptance_result = quartile_x_direction(trades, "acceptance_rate")
    effect_findings = direction_vs_condition_effect(regime_table, condition_table)
    clusters = detect_loss_clusters(trades)
    cluster_summary = summarize_loss_clusters(clusters)

    print("\n" + "-" * 70)
    print("LEVEL 1 - EXECUTIVE FINDINGS")
    print("-" * 70)
    for finding in effect_findings:
        print(f"\n[{finding['axis']}] {finding['conclusion']}")

    if cluster_summary["available"]:
        print(f"\n[Loss Clusters] {cluster_summary['cluster_count']} cluster(s) found, "
              f"{cluster_summary['total_trades_in_clusters']} trades total - {cluster_summary['evidence_note']}")
    else:
        print(f"\n[Loss Clusters] {cluster_summary['reason']}")

    print("\n" + "-" * 70)
    print("LEVEL 2 - DETAILED TABLES")
    print("-" * 70)
    _print_direction_table(regime_table, "1) Direction x Asset Market Regime")
    _print_direction_table(condition_table, "2) Direction x Global Market Condition")

    print("\n[3) Market Health Quartiles]")
    if health_result["available"]:
        print(f"  Boundaries (actual data): {health_result['boundaries']}")
        print(f"  Effective distinguishable groups: {health_result['effective_group_count']} of 4")
        if health_result["low_resolution_warning"]:
            print(f"  ⚠️ {health_result['low_resolution_warning']}")
        _print_direction_table(health_result["table"], "Market Health x Direction")
    else:
        print(f"  {health_result['reason']}")

    print("\n[4) Acceptance Rate Quartiles]")
    if acceptance_result["available"]:
        print(f"  Boundaries (actual data): {acceptance_result['boundaries']}")
        print(f"  Effective distinguishable groups: {acceptance_result['effective_group_count']} of 4")
        if acceptance_result["low_resolution_warning"]:
            print(f"  ⚠️ {acceptance_result['low_resolution_warning']}")
        _print_direction_table(acceptance_result["table"], "Acceptance Rate x Direction")
    else:
        print(f"  {acceptance_result['reason']}")

    print("\n[7) Loss Cluster Detail]")
    if cluster_summary["available"]:
        print(f"  Regime distribution within clusters: {cluster_summary['regime_distribution']}")
        print(f"  Condition distribution within clusters: {cluster_summary['condition_distribution']}")
        print(f"  Avg Market Health within clusters: {cluster_summary['avg_health_in_clusters']}")
        print(f"  Avg Acceptance within clusters: {cluster_summary['avg_acceptance_in_clusters']}")
    else:
        print(f"  {cluster_summary['reason']}")

    print("\n" + "=" * 70)
    print("RESEARCH FINDINGS")
    print("=" * 70)
    for finding in effect_findings:
        for bucket, level, diff in finding["buckets"]:
            diff_display = f"(SHORT-LONG WR diff: {round(diff,2)}pp)" if diff is not None else ""
            print(f"  [{finding['axis']} = {bucket}] {level} {diff_display}")

    print("\nNote: correlation only, never causation. A human decides what, if")
    print("anything, these findings mean for a future, separately reviewed change.")
    print("=" * 70 + "\n")


def main():
    print(f"🔬 Market-Conditioned Analysis starting - {datetime.now().isoformat()}")
    trades = _fetch_trades()
    if not trades:
        print("⚠️ No trades retrieved - nothing to analyze.")
        return
    print_report(trades)
    print(f"🔬 Market-Conditioned Analysis finished - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
