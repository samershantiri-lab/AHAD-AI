"""
================================================================================
AHAD AI - Research Lab
Phase 6, Module 5: Compare Winners vs Losers
================================================================================

Completely independent from bot.py. This file:

- Is never imported by bot.py, and never imports anything from bot.py.
- Sends no Telegram messages of any kind.
- Never runs inside, or is called from, the live /scan path - it has
  zero effect on scan speed, AI Brain, Ranking, Smart Money, or the
  Validation Engine, because it never touches any of that code.
- Is READ-ONLY, and reads ONLY from research_winners and
  research_losers - never from `trades` directly, and never from
  `versions`. Those two tables are themselves already isolated copies
  of Trade DNA, one layer further removed from production than the raw
  collectors (Winners Analyzer / Losers Analyzer) - this module sits on
  top of Research Lab's own output, not on top of production.
- Writes exclusively to its own, dedicated table
  (`research_comparisons`), created and owned entirely by this script.
- Can be removed entirely without touching bot.py or affecting
  production in any way.

A DEPENDENCY WORTH STATING EXPLICITLY: this module's results are only
as fresh as the last time Winners Analyzer and Losers Analyzer ran. It
deliberately does not re-derive anything from `trades` itself -
duplicating that collection logic a third time would work against the
same "no duplicated code" principle the Research Lab controller
(research.py) was built around. If this module is registered in
research.py's RESEARCH_MODULES list, it should run after both
analyzers, not before or in place of them.

METHODOLOGY NOTE, STATED PLAINLY RATHER THAN LEFT IMPLICIT: this module
reports Mean / Median / Difference for continuous metrics and
percentage distributions for categorical ones - it does NOT run formal
hypothesis tests (no t-test, no p-value, no multiple-comparison
correction). The "Priority Score" used to rank metrities is a simpler,
deliberately transparent stand-in: it combines (a) a "consistency"
term - the difference between groups normalized by the data's own
pooled spread, the same underlying idea a standardized effect size
like Cohen's d captures, so metrics on very different scales (RSI's
0-100 range vs MACD's small fractions) remain comparable - with (b) a
sample-size factor, so a large difference backed by very little data
does not automatically outrank a smaller, better-supported one. This
is intentionally simpler than a full statistical test suite; treat
"Priority Score" as a sorting aid for a human to look closer, not as a
significance claim.

What this script does, each time it runs:
  1. Ensures research_comparisons exists (idempotent).
  2. Reads every row currently in research_winners and research_losers.
  3. Computes three comparison scopes: Overall (all winners vs all
     losers), LONG-only, and SHORT-only - the LONG/SHORT split exists
     specifically to help separate "is there a real quality gap
     between the two directions" from other explanations, since that
     question has been open since early strategy discussions.
  4. For continuous metrics: Winners Mean/Median, Losers Mean/Median,
     Difference, and a Priority Score - or "INSUFFICIENT DATA" if
     either group in that scope has fewer than MIN_SAMPLE_SIZE rows
     for that metric.
  5. For categorical metrics: side-by-side percentage distributions,
     plus a Priority Score derived from the largest single-category gap.
  6. Ranks every metric/scope combination by Priority Score into a
     "TOP METRICS WORTH INVESTIGATING" section.
  7. Stores the complete result as one JSONB row in research_comparisons
     and prints the same result as a plain-text console report.

No AI, no pattern discovery, no promotion logic, no recommendations -
by design. This module only presents observations; a human decides
what, if anything, they mean for a future, separately-reviewed change
to AI Brain. Nothing here can write to bot.py or apply anything
automatically - there is no code path that does either.
================================================================================
"""

import os
import sys
import json
import math
import statistics
import psycopg2
from datetime import datetime


# ================================================
# 🔌 DATABASE CONNECTION
# ================================================
# Identical connection pattern to bot.py's get_db_connection() (and to
# every other Research Lab module's own), so this script reaches the
# exact same database - but this is its own, independent connection.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - Compare Winners/"
            "Losers needs the same DATABASE_URL bot.py uses to reach the "
            "same database."
        )
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode="require"
    )


# ================================================
# ⚙️ CONFIGURATION
# ================================================

# Minimum rows required in BOTH groups for a metric/scope combination
# to be reported at all - below this, "INSUFFICIENT DATA" is shown
# instead of a number that looks confident but isn't. Matches the same
# 30-sample convention already used elsewhere in this project (e.g.
# the version scoreboard's "Collecting Data" threshold).
MIN_SAMPLE_SIZE = 30

CONTINUOUS_METRICS = [
    ("brain_confidence", "Brain Confidence"),
    ("score", "Score"),
    ("ranking_score", "Ranking Score"),
    ("flow", "Flow"),
    ("momentum_score", "Momentum"),
    ("rsi_15m", "RSI"),
    ("atr", "ATR"),
    ("macd", "MACD"),
    ("volume_ratio", "Volume Ratio"),
    ("volume_acceleration", "Volume Acceleration"),
    ("rr", "RR"),
]

CATEGORICAL_METRICS = [
    ("compression_status", "Compression Status"),
    ("market_regime", "Market Regime"),
    ("sector", "Sector"),
    ("session", "Session"),
    ("quality_grade", "Quality Grade"),
    ("direction", "Direction"),
]


# ================================================
# 🗄 SCHEMA - research_comparisons (the only table this script ever writes to)
# ================================================

def init_research_comparisons_table():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS research_comparisons (
            id SERIAL PRIMARY KEY,
            comparison_timestamp TIMESTAMP,
            version_scope TEXT,
            winners_sample_size INTEGER,
            losers_sample_size INTEGER,
            comparison_data JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_research_comparisons_timestamp ON research_comparisons(comparison_timestamp)")
        conn.commit()
        print("🔬 Compare Winners/Losers: research_comparisons table ready")
    except Exception as e:
        print(f"⚠️ Compare Winners/Losers: failed to initialize research_comparisons - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📥 DATA ACCESS - read-only against research_winners / research_losers
# ================================================

_ALL_COLUMNS = [name for name, _ in CONTINUOUS_METRICS] + [name for name, _ in CATEGORICAL_METRICS] + ["version"]


def _fetch_rows(table):
    """
    Reads every row from research_winners or research_losers - never
    from `trades`. Returns a list of plain dicts keyed by column name,
    so the rest of this module never has to know about cursor/tuple
    positions.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        columns_sql = ", ".join(_ALL_COLUMNS)
        cur.execute(f"SELECT {columns_sql} FROM {table}")
        rows = cur.fetchall()
        return [dict(zip(_ALL_COLUMNS, row)) for row in rows]
    except Exception as e:
        print(f"⚠️ Compare Winners/Losers: failed to read {table} - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _version_scope_label(winners_rows, losers_rows):
    """
    Records which version(s) are actually present in the data used,
    rather than restricting the comparison to one version - a plain
    metadata field describing what was compared, not a filter.
    """
    versions = set()
    for row in winners_rows + losers_rows:
        if row.get("version"):
            versions.add(row["version"])
    if not versions:
        return "UNKNOWN"
    if len(versions) == 1:
        return next(iter(versions))
    return "MIXED(" + ",".join(sorted(versions)) + ")"


# ================================================
# 📊 COMPARISON LOGIC - pure computation, no database access
# ================================================

def _pooled_std(values_a, values_b):
    """
    Pooled standard deviation across two independent samples - the
    same denominator a standardized effect size (e.g. Cohen's d) uses.
    Returns None if it cannot be computed (fewer than 2 points in
    either group, or zero pooled variance) rather than raising or
    dividing by zero.
    """
    n1, n2 = len(values_a), len(values_b)
    if n1 < 2 or n2 < 2:
        return None
    try:
        var1 = statistics.variance(values_a)
        var2 = statistics.variance(values_b)
    except statistics.StatisticsError:
        return None
    pooled_variance = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
    if pooled_variance <= 0:
        return None
    return math.sqrt(pooled_variance)


def _sample_size_factor(n1, n2):
    """
    Scales from 0 to 1 as the smaller of the two group sizes approaches
    a comfortable sample - capped at 1.0 so an enormous sample size
    cannot alone dominate the ranking once "enough" data already
    exists. Uses the same MIN_SAMPLE_SIZE convention as the
    insufficient-data gate itself, scaled by 3x as the point past which
    more data stops adding ranking weight.
    """
    smaller = min(n1, n2)
    target = MIN_SAMPLE_SIZE * 3
    return min(1.0, smaller / target)


def compare_continuous_metric(winners_rows, losers_rows, column):
    """
    Returns a dict describing one continuous metric's comparison, or
    a dict with status "INSUFFICIENT DATA" if either group has fewer
    than MIN_SAMPLE_SIZE non-null values for this column.
    """
    w_values = [r[column] for r in winners_rows if r.get(column) is not None]
    l_values = [r[column] for r in losers_rows if r.get(column) is not None]

    if len(w_values) < MIN_SAMPLE_SIZE or len(l_values) < MIN_SAMPLE_SIZE:
        return {
            "status": "INSUFFICIENT DATA",
            "winners_n": len(w_values),
            "losers_n": len(l_values),
        }

    winners_mean = statistics.mean(w_values)
    losers_mean = statistics.mean(l_values)
    winners_median = statistics.median(w_values)
    losers_median = statistics.median(l_values)
    difference = winners_mean - losers_mean

    pooled = _pooled_std(w_values, l_values)
    if pooled:
        consistency = min(abs(difference) / pooled, 3.0)  # capped defensively
    else:
        consistency = 0.0

    size_factor = _sample_size_factor(len(w_values), len(l_values))
    priority_score = round(consistency * size_factor, 4)

    return {
        "status": "OK",
        "winners_n": len(w_values),
        "losers_n": len(l_values),
        "winners_mean": round(winners_mean, 4),
        "winners_median": round(winners_median, 4),
        "losers_mean": round(losers_mean, 4),
        "losers_median": round(losers_median, 4),
        "difference": round(difference, 4),
        "priority_score": priority_score,
    }


def compare_categorical_metric(winners_rows, losers_rows, column):
    """
    Returns side-by-side percentage distributions for one categorical
    metric, plus a Priority Score derived from the largest single-
    category percentage-point gap between the two groups - the
    categorical equivalent of "difference", scaled the same way
    continuous metrics are so both can share one ranked list.
    """
    w_values = [r[column] for r in winners_rows if r.get(column) is not None]
    l_values = [r[column] for r in losers_rows if r.get(column) is not None]

    if len(w_values) < MIN_SAMPLE_SIZE or len(l_values) < MIN_SAMPLE_SIZE:
        return {
            "status": "INSUFFICIENT DATA",
            "winners_n": len(w_values),
            "losers_n": len(l_values),
        }

    def _distribution(values):
        total = len(values)
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        return {k: round((v / total) * 100, 2) for k, v in counts.items()}

    winners_dist = _distribution(w_values)
    losers_dist = _distribution(l_values)

    all_categories = set(winners_dist) | set(losers_dist)
    max_gap = 0.0
    for category in all_categories:
        gap = abs(winners_dist.get(category, 0.0) - losers_dist.get(category, 0.0))
        max_gap = max(max_gap, gap)

    # Categorical gaps are already a 0-100 percentage-point scale - a
    # 25-point gap is treated as roughly comparable in weight to a
    # continuous metric's normalized difference; both are then scaled
    # by the same sample-size factor before ranking together.
    size_factor = _sample_size_factor(len(w_values), len(l_values))
    priority_score = round((max_gap / 100.0) * 3.0 * size_factor, 4)  # scaled to the same ~0-3 range as continuous consistency

    return {
        "status": "OK",
        "winners_n": len(w_values),
        "losers_n": len(l_values),
        "winners_distribution": winners_dist,
        "losers_distribution": losers_dist,
        "max_gap_pct": round(max_gap, 2),
        "priority_score": priority_score,
    }


def run_comparison_scope(winners_rows, losers_rows, scope_label):
    """
    Runs every continuous and categorical comparison for one scope
    (Overall / LONG-only / SHORT-only) and returns a plain dict of
    results, plus a flat list of (scope, metric_label, priority_score,
    direction_note) tuples for the final ranking step.
    """
    scope_result = {"continuous": {}, "categorical": {}}
    ranking_entries = []

    for column, label in CONTINUOUS_METRICS:
        result = compare_continuous_metric(winners_rows, losers_rows, column)
        scope_result["continuous"][label] = result
        if result["status"] == "OK":
            direction_note = "winners higher" if result["difference"] > 0 else "losers higher"
            ranking_entries.append((scope_label, label, result["priority_score"], direction_note))

    for column, label in CATEGORICAL_METRICS:
        result = compare_categorical_metric(winners_rows, losers_rows, column)
        scope_result["categorical"][label] = result
        if result["status"] == "OK":
            ranking_entries.append((scope_label, label, result["priority_score"], "distribution gap"))

    return scope_result, ranking_entries


def run_full_comparison():
    """
    Orchestrates the complete comparison: fetches both tables once,
    splits by direction, runs all three scopes, and assembles the
    final ranked "top metrics" list. Pure computation plus the two
    read-only fetches - no writes happen here (see save_comparison()).
    """
    winners_rows = _fetch_rows("research_winners")
    losers_rows = _fetch_rows("research_losers")

    version_scope = _version_scope_label(winners_rows, losers_rows)

    winners_long = [r for r in winners_rows if r.get("direction") == "LONG"]
    losers_long = [r for r in losers_rows if r.get("direction") == "LONG"]
    winners_short = [r for r in winners_rows if r.get("direction") == "SHORT"]
    losers_short = [r for r in losers_rows if r.get("direction") == "SHORT"]

    overall_result, overall_ranking = run_comparison_scope(winners_rows, losers_rows, "Overall")
    long_result, long_ranking = run_comparison_scope(winners_long, losers_long, "LONG only")
    short_result, short_ranking = run_comparison_scope(winners_short, losers_short, "SHORT only")

    all_ranking = overall_ranking + long_ranking + short_ranking
    all_ranking.sort(key=lambda entry: entry[2], reverse=True)

    top_metrics = [
        {
            "scope": scope,
            "metric": metric,
            "priority_score": score,
            "note": note,
        }
        for scope, metric, score, note in all_ranking[:10]
    ]

    return {
        "comparison_timestamp": datetime.now().isoformat(),
        "version_scope": version_scope,
        "winners_sample_size": len(winners_rows),
        "losers_sample_size": len(losers_rows),
        "scopes": {
            "overall": overall_result,
            "long_only": long_result,
            "short_only": short_result,
        },
        "top_metrics_worth_investigating": top_metrics,
    }


# ================================================
# 💾 PERSISTENCE - the only write this script ever performs
# ================================================

def save_comparison(result):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO research_comparisons (
                comparison_timestamp, version_scope,
                winners_sample_size, losers_sample_size, comparison_data
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            result["comparison_timestamp"],
            result["version_scope"],
            result["winners_sample_size"],
            result["losers_sample_size"],
            json.dumps(result, default=str)
        ))
        conn.commit()
        print("🔬 Compare Winners/Losers: comparison saved to research_comparisons")
    except Exception as e:
        print(f"⚠️ Compare Winners/Losers: failed to save comparison - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 🖨 REPORT - prints a plain-text summary to stdout (no Telegram, ever)
# ================================================

def _print_continuous_section(scope_data):
    for label, r in scope_data["continuous"].items():
        print(f"\n{label}")
        if r["status"] == "INSUFFICIENT DATA":
            print(f"  INSUFFICIENT DATA (winners n={r['winners_n']}, losers n={r['losers_n']})")
            continue
        print(f"  Winners Mean   : {r['winners_mean']}")
        print(f"  Winners Median : {r['winners_median']}")
        print(f"  Losers Mean    : {r['losers_mean']}")
        print(f"  Losers Median  : {r['losers_median']}")
        print(f"  Difference     : {r['difference']}")


def _print_categorical_section(scope_data):
    for label, r in scope_data["categorical"].items():
        print(f"\n{label}")
        if r["status"] == "INSUFFICIENT DATA":
            print(f"  INSUFFICIENT DATA (winners n={r['winners_n']}, losers n={r['losers_n']})")
            continue
        print(f"  Winners Distribution : {r['winners_distribution']}")
        print(f"  Losers Distribution  : {r['losers_distribution']}")
        print(f"  Largest Gap          : {r['max_gap_pct']}%")


def print_report(result):
    print("\n" + "=" * 60)
    print("🔬 AHAD AI RESEARCH LAB - COMPARE WINNERS VS LOSERS")
    print("=" * 60)

    print(f"\nComparison Timestamp : {result['comparison_timestamp']}")
    print(f"Version Scope        : {result['version_scope']}")
    print(f"Winners Sample Size  : {result['winners_sample_size']}")
    print(f"Losers Sample Size   : {result['losers_sample_size']}")

    for scope_key, scope_title in [
        ("overall", "OVERALL (all directions combined)"),
        ("long_only", "LONG ONLY"),
        ("short_only", "SHORT ONLY"),
    ]:
        print("\n" + "-" * 60)
        print(scope_title)
        print("-" * 60)
        scope_data = result["scopes"][scope_key]
        print("\n[Continuous Metrics]")
        _print_continuous_section(scope_data)
        print("\n[Categorical Metrics]")
        _print_categorical_section(scope_data)

    print("\n" + "=" * 60)
    print("TOP METRICS WORTH INVESTIGATING")
    print("=" * 60)
    if not result["top_metrics_worth_investigating"]:
        print("\nNo metric had sufficient data in any scope this run.")
    else:
        for i, entry in enumerate(result["top_metrics_worth_investigating"], 1):
            print(f"{i}. [{entry['scope']}] {entry['metric']} "
                  f"- Priority Score: {entry['priority_score']} ({entry['note']})")

    print("\n" + "=" * 60)
    print("Note: this is an observation report only. Priority Score is a")
    print("simple, transparent ranking aid (difference normalized by the")
    print("data's own spread and sample size) - not a formal significance")
    print("test, and not a recommendation. No pattern discovery, no")
    print("promotion, no automatic changes to AHAD AI. A human decides")
    print("what, if anything, these numbers mean for future versions.")
    print("=" * 60 + "\n")


# ================================================
# ▶ ENTRY POINT
# ================================================

def main():
    print(f"🔬 Compare Winners/Losers starting - {datetime.now().isoformat()}")
    init_research_comparisons_table()
    result = run_full_comparison()
    save_comparison(result)
    print_report(result)
    print(f"🔬 Compare Winners/Losers finished - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
