"""
================================================================================
AHAD AI - Research Lab
Winner/Loser DNA + Direction Analysis + Distribution/IQR (Research Layer v1, Part 4)
================================================================================

Not a registered Research Lab module - standalone, read-only. Reuses,
rather than duplicates:
  - CONTINUOUS_METRICS / CATEGORICAL_METRICS from compare_winners_losers.py
    (imported directly, not copied - verified against this exact repo's
    copy before writing a single line here, not from memory).
  - evidence_level / priority_score / MIN_SAMPLE_SIZE from research_statistics.py.
  - _quartile_boundaries / _effective_groups / _assign_bucket from
    market_conditioned_analysis.py (the corrected, low-resolution-aware
    quartile logic - confirmed present in this repo's copy before reuse).

DATA SOURCE: research_winners / research_losers (compare_winners_losers.py's
own source), not `trades` directly. Both tables' own collection queries
(in winners_analyzer.py / losers_analyzer.py) already require
status='CLOSED' AND result IN (...) / result = 'LOSS_SL' - TIMEOUT and
OPEN trades cannot reach either table by construction, confirmed by
reading those two files' schema and collection query directly in this
repo. trade_id UNIQUE + ON CONFLICT DO NOTHING on both tables' INSERT
rules out duplicate rows the same way - also structural, not a filter
added here.

No AI Brain, Ranking, Scanner, bot.py, or research.py code is read,
imported, or referenced anywhere in this file. Read-only - no writes,
no schema changes, no new tables, no modification to any existing file.
================================================================================
"""

import os
import sys
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime

import psycopg2

from research_statistics import evidence_level, priority_score, MIN_SAMPLE_SIZE
from compare_winners_losers import CONTINUOUS_METRICS, CATEGORICAL_METRICS
from market_conditioned_analysis import _quartile_boundaries, _effective_groups, _assign_bucket

LOW_VARIANCE_THRESHOLD = 0.85  # per the approved spec, applied uniformly to every continuous metric


DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - this script needs "
            "the same DATABASE_URL every other Research Lab module uses."
        )
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# 📥 DATA ACCESS - read-only against research_winners / research_losers only
# ================================================

def _fetch_group(table):
    """
    Reads every row from research_winners or research_losers, with
    all 17 canonical variables (imported, not copied) plus version/
    quality_grade/market_regime/market_health for the cross-
    analyses below. TIMEOUT and OPEN trades cannot appear here by
    construction (see module docstring) - no runtime filter needed.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        extra_cols = ["trade_id", "version", "direction", "quality_grade",
                      "market_regime", "market_health"]
        metric_cols = [c for c, _ in CONTINUOUS_METRICS] + \
                      [c for c, _ in CATEGORICAL_METRICS if c not in ("direction", "market_regime", "quality_grade")]
        all_cols = extra_cols + metric_cols
        seen = set()
        ordered_cols = [c for c in all_cols if not (c in seen or seen.add(c))]
        columns_sql = ", ".join(ordered_cols)
        cur.execute(f"SELECT {columns_sql} FROM {table}")
        rows = cur.fetchall()
        return [dict(zip(ordered_cols, row)) for row in rows]
    except Exception as e:
        print(f"⚠️ Winner/Loser DNA: failed to read {table} - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 🧬 LOW VARIANCE DETECTION - applied uniformly, not just to Brain Confidence
# ================================================

def detect_low_variance(values):
    """
    True if the single most common value accounts for >= 85% of all
    non-null values - the exact pattern discovered with Brain
    Confidence (87.7% at one value). Applied to every continuous
    metric uniformly, not hardcoded to one field.
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return False
    counts = Counter(clean)
    most_common_count = counts.most_common(1)[0][1]
    return (most_common_count / len(clean)) >= LOW_VARIANCE_THRESHOLD


# ================================================
# 📊 FULL DNA STATS - one function, reused for every continuous metric
# ================================================

def _describe(values):
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return {"n": len(clean), "mean": None, "median": None, "q1": None, "q3": None,
                "iqr": None, "min": None, "max": None, "stdev": None}
    sorted_vals = sorted(clean)
    q1, _, q3 = statistics.quantiles(sorted_vals, n=4)
    return {
        "n": len(clean),
        "mean": round(statistics.mean(clean), 4),
        "median": round(statistics.median(clean), 4),
        "q1": round(q1, 4), "q3": round(q3, 4), "iqr": round(q3 - q1, 4),
        "min": round(min(clean), 4), "max": round(max(clean), 4),
        "stdev": round(statistics.stdev(clean), 4) if len(clean) >= 2 else None,
    }


def win_rate_by_range(winner_values, loser_values):
    """
    Bins BOTH groups' combined values using the corrected, low-
    resolution-aware quartile logic imported from market_conditioned_
    analysis.py - never a separately reimplemented binning method.
    """
    combined = winner_values + loser_values
    boundaries = _quartile_boundaries(combined)
    if boundaries is None:
        return {"available": False, "reason": f"Fewer than 4 combined values (n={len(combined)})."}

    distinct = _effective_groups(boundaries)
    assigned = set()
    for v in combined:
        label = _assign_bucket(v, distinct)
        if label:
            assigned.add(label)
    ordered_labels = sorted(assigned, key=lambda l: int(l.split()[1]))

    table = {}
    for label in ordered_labels:
        w_in = [v for v in winner_values if _assign_bucket(v, distinct) == label]
        l_in = [v for v in loser_values if _assign_bucket(v, distinct) == label]
        n = len(w_in) + len(l_in)
        win_rate = round((len(w_in) / n) * 100, 2) if n else None
        table[label] = {"n": n, "wins": len(w_in), "losses": len(l_in), "win_rate": win_rate}
    return {"available": True, "boundaries": [round(b, 3) for b in boundaries],
            "effective_group_count": len(ordered_labels), "table": table}


def full_dna(winner_values, loser_values, metric_label):
    """
    The complete DNA block for one continuous metric. Low Variance is
    checked on the COMBINED population - the conservative, correct
    choice for "is the gradient itself reliable" regardless of how
    each group looks individually.
    """
    w_clean = [v for v in winner_values if v is not None]
    l_clean = [v for v in loser_values if v is not None]

    low_variance = detect_low_variance(w_clean + l_clean)

    return {
        "metric": metric_label,
        "low_variance_warning": "LOW VARIANCE — GRADIENT ANALYSIS UNRELIABLE" if low_variance else None,
        "winner_stats": _describe(w_clean),
        "loser_stats": _describe(l_clean),
        "win_rate_by_range": win_rate_by_range(w_clean, l_clean),
        "priority_score": priority_score(w_clean, l_clean) if w_clean and l_clean else 0.0,
        "evidence_level": evidence_level(len(w_clean), len(l_clean), w_clean, l_clean),
    }


def dna_for_all_metrics(winners, losers):
    """Runs full_dna() for every metric in CONTINUOUS_METRICS - the single canonical list, imported not copied."""
    results = {}
    for col, label in CONTINUOUS_METRICS:
        w_values = [r[col] for r in winners]
        l_values = [r[col] for r in losers]
        results[label] = full_dna(w_values, l_values, label)
    return results


# ================================================
# 🎯 DIRECTION-SPLIT DNA (LONG W vs L, SHORT W vs L)
# ================================================

def dna_by_direction(winners, losers, direction):
    w_sub = [r for r in winners if r["direction"] == direction]
    l_sub = [r for r in losers if r["direction"] == direction]
    return dna_for_all_metrics(w_sub, l_sub)


# ================================================
# 🏆 DIRECTION × QUALITY GRADE
# ================================================

def direction_x_quality(winners, losers):
    grades = sorted(set(r["quality_grade"] for r in winners + losers if r["quality_grade"]))
    table = {}
    for direction in ["LONG", "SHORT"]:
        table[direction] = {}
        for grade in grades:
            w = [r for r in winners if r["direction"] == direction and r["quality_grade"] == grade]
            l = [r for r in losers if r["direction"] == direction and r["quality_grade"] == grade]
            n = len(w) + len(l)
            win_rate = round((len(w) / n) * 100, 2) if n else None
            rr_w = [r["rr"] for r in w if r.get("rr") is not None]
            rr_l = [r["rr"] for r in l if r.get("rr") is not None]
            all_rr = rr_w + rr_l
            # FIX 1: each side must independently clear MIN_SAMPLE_SIZE -
            # checked first, unconditionally, so a missing-RR fallback can
            # never escape this gate via the combined n.
            if len(w) < MIN_SAMPLE_SIZE or len(l) < MIN_SAMPLE_SIZE:
                ev = "INSUFFICIENT DATA"
            elif rr_w and rr_l:
                ev = evidence_level(len(w), len(l), rr_w, rr_l)
            else:
                ev = "WEAK SIGNAL"
            table[direction][grade] = {
                "n": n, "wins": len(w), "losses": len(l), "win_rate": win_rate,
                "median_rr": round(statistics.median(all_rr), 3) if all_rr else None,
                "evidence_level": ev,
            }
    return table


# ================================================
# ⚖️ RR DISTRIBUTION - by Direction and Version
# ================================================

def rr_distribution(rows, group_label):
    rr_values = [r["rr"] for r in rows if r.get("rr") is not None]
    if len(rr_values) < MIN_SAMPLE_SIZE:
        return {"group": group_label, "n": len(rr_values), "evidence_level": "INSUFFICIENT DATA"}

    sorted_rr = sorted(rr_values)
    q1, _, q3 = statistics.quantiles(sorted_rr, n=4)
    return {
        "group": group_label, "n": len(rr_values),
        "median": round(statistics.median(rr_values), 3), "q1": round(q1, 3), "q3": round(q3, 3),
        "iqr": round(q3 - q1, 3), "min": round(min(rr_values), 3), "max": round(max(rr_values), 3),
        "pct_gt_2": round(sum(1 for v in rr_values if v > 2) / len(rr_values) * 100, 2),
        "pct_gt_3": round(sum(1 for v in rr_values if v > 3) / len(rr_values) * 100, 2),
        "pct_gt_5": round(sum(1 for v in rr_values if v > 5) / len(rr_values) * 100, 2),
        "outlier_count": sum(1 for v in rr_values if v > q3 + 1.5 * (q3 - q1)),
        "evidence_level": "MODERATE EVIDENCE" if len(rr_values) < 90 else "STRONG EVIDENCE",
    }


def rr_by_direction_and_version(winners, losers):
    all_rows = winners + losers
    results = {"by_direction": {}, "by_version": {}}
    for direction in ["LONG", "SHORT"]:
        results["by_direction"][direction] = rr_distribution(
            [r for r in all_rows if r["direction"] == direction], direction)
    for version in sorted(set(r["version"] for r in all_rows if r["version"])):
        results["by_version"][version] = rr_distribution(
            [r for r in all_rows if r["version"] == version], version)
    return results


# ================================================
# 🔢 VERSION × DIRECTION
# ================================================

def version_x_direction(winners, losers):
    all_rows = winners + losers
    versions = sorted(set(r["version"] for r in all_rows if r["version"]))
    table = {}
    for version in versions:
        table[version] = {}
        for direction in ["LONG", "SHORT"]:
            w = [r for r in winners if r["version"] == version and r["direction"] == direction]
            l = [r for r in losers if r["version"] == version and r["direction"] == direction]
            n = len(w) + len(l)
            score_vals = [r["score"] for r in (w + l) if r.get("score") is not None]
            rr_vals = [r["rr"] for r in (w + l) if r.get("rr") is not None]
            # FIX 3: each side must independently clear MIN_SAMPLE_SIZE -
            # the combined n (which could be large even with one side at
            # 10) is never used for this gate.
            if len(w) < MIN_SAMPLE_SIZE or len(l) < MIN_SAMPLE_SIZE:
                ev = "INSUFFICIENT DATA"
            elif len(w) >= 90 and len(l) >= 90:
                ev = "STRONG EVIDENCE"
            else:
                ev = "MODERATE EVIDENCE"
            table[version][direction] = {
                "n": n, "win_rate": round((len(w) / n) * 100, 2) if n else None,
                "median_rr": round(statistics.median(rr_vals), 3) if rr_vals else None,
                "avg_score": round(statistics.mean(score_vals), 2) if score_vals else None,
                "evidence_level": ev,
            }
    return table


# ================================================
# 🖨 REPORT
# ================================================

def _find_strongest(dna_dict):
    candidates = [(label, d) for label, d in dna_dict.items()
                  if d["low_variance_warning"] is None and d["evidence_level"] != "INSUFFICIENT DATA"]
    if not candidates:
        return None
    return max(candidates, key=lambda kv: kv[1]["priority_score"])


def print_report(winners, losers):
    print("\n" + "=" * 70)
    print("🔬 AHAD AI RESEARCH LAB - WINNER/LOSER DNA + DIRECTION ANALYSIS")
    print("=" * 70)
    print(f"Winners: {len(winners)}  |  Losers: {len(losers)}")

    overall_dna = dna_for_all_metrics(winners, losers)
    long_dna = dna_by_direction(winners, losers, "LONG")
    short_dna = dna_by_direction(winners, losers, "SHORT")
    quality_table = direction_x_quality(winners, losers)
    rr_results = rr_by_direction_and_version(winners, losers)
    version_table = version_x_direction(winners, losers)

    print("\n" + "-" * 70)
    print("LEVEL 1 - KEY FINDINGS")
    print("-" * 70)

    strongest_overall = _find_strongest(overall_dna)
    if strongest_overall:
        label, d = strongest_overall
        print(f"\nStrongest overall Winner/Loser differentiator: {label} "
              f"({d['evidence_level']}, N={d['winner_stats']['n']}+{d['loser_stats']['n']})")
    else:
        print("\nStrongest overall differentiator: NO RELIABLE DIFFERENTIATOR — INSUFFICIENT DATA")

    strongest_long = _find_strongest(long_dna)
    if strongest_long:
        label, d = strongest_long
        print(f"Strongest LONG differentiator: {label} ({d['evidence_level']}, "
              f"N={d['winner_stats']['n']}+{d['loser_stats']['n']})")
    else:
        print("Strongest LONG differentiator: NO RELIABLE DIFFERENTIATOR — INSUFFICIENT DATA")

    strongest_short = _find_strongest(short_dna)
    if strongest_short:
        label, d = strongest_short
        print(f"Strongest SHORT differentiator: {label} ({d['evidence_level']}, "
              f"N={d['winner_stats']['n']}+{d['loser_stats']['n']})")
    else:
        print("Strongest SHORT differentiator: NO RELIABLE DIFFERENTIATOR — INSUFFICIENT DATA")

    low_var_metrics = [label for label, d in overall_dna.items() if d["low_variance_warning"]]
    print(f"\nMetrics flagged LOW VARIANCE (gradient unreliable): {low_var_metrics if low_var_metrics else 'none'}")

    print("\n" + "-" * 70)
    print("LEVEL 2 - FULL WINNER/LOSER DNA")
    print("-" * 70)
    for label, d in overall_dna.items():
        print(f"\n[{label}]" + (f"  ⚠️ {d['low_variance_warning']}" if d["low_variance_warning"] else ""))
        print(f"  Winners: {d['winner_stats']}")
        print(f"  Losers:  {d['loser_stats']}")
        print(f"  Priority Score: {d['priority_score']}  |  Evidence Level: {d['evidence_level']}")
        wrbr = d["win_rate_by_range"]
        if wrbr["available"]:
            print(f"  Win-Rate-by-Range ({wrbr['effective_group_count']} groups): {wrbr['table']}")
        else:
            print(f"  Win-Rate-by-Range: {wrbr['reason']}")

    for section_name, dna_dict in [("LONG WINNER vs LOSER", long_dna), ("SHORT WINNER vs LOSER", short_dna)]:
        print("\n" + "-" * 70)
        print(f"LEVEL 2 - {section_name}")
        print("-" * 70)
        for label, d in dna_dict.items():
            flag = f"  ⚠️ {d['low_variance_warning']}" if d["low_variance_warning"] else ""
            print(f"  {label}: Evidence={d['evidence_level']}{flag}  "
                  f"WinnerMedian={d['winner_stats']['median']}  LoserMedian={d['loser_stats']['median']}")

    print("\n" + "-" * 70)
    print("LEVEL 2 - QUALITY × DIRECTION")
    print("-" * 70)
    for direction, grades in quality_table.items():
        print(f"\n  {direction}:")
        for grade, stats in grades.items():
            print(f"    {grade}: n={stats['n']} WR={stats['win_rate']}% MedianRR={stats['median_rr']} "
                  f"Evidence={stats['evidence_level']}")

    print("\n" + "-" * 70)
    print("LEVEL 2 - RR DISTRIBUTION")
    print("-" * 70)
    print("  By Direction:")
    for direction, stats in rr_results["by_direction"].items():
        print(f"    {direction}: {stats}")
    print("  By Version:")
    for version, stats in rr_results["by_version"].items():
        print(f"    {version}: {stats}")

    print("\n" + "-" * 70)
    print("LEVEL 2 - VERSION × DIRECTION")
    print("-" * 70)
    for version, directions in version_table.items():
        print(f"  {version}: {directions}")

    print("\n" + "=" * 70)
    print("Note: correlation only, never causation. Direction Effect vs Market")
    print("Effect separation for any SHORT/LONG pattern here should be cross-")
    print("checked against market_conditioned_analysis.py's own findings before")
    print("drawing conclusions - this report does not repeat that analysis.")
    print("=" * 70 + "\n")


def main():
    print(f"🔬 Winner/Loser DNA Analysis starting - {datetime.now().isoformat()}")
    winners = _fetch_group("research_winners")
    losers = _fetch_group("research_losers")
    if not winners and not losers:
        print("⚠️ No data retrieved - nothing to analyze.")
        return
    print_report(winners, losers)
    print(f"🔬 Winner/Loser DNA Analysis finished - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
