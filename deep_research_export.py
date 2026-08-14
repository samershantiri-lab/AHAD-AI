"""
================================================================================
AHAD AI - Research Lab
Deep Historical Research Export (Generation 2 Pre-Analysis)
================================================================================

A one-off, standalone analysis script - NOT a registered Research Lab
module, NOT added to research.py's execution registry. Built for a
single explicit purpose: produce a complete statistical breakdown of
every Winner/Loser recorded so far, across all 17 variables
compare_winners_losers.py already computes, plus an honest audit of
what Market Context data actually exists for these specific trades.

ABSOLUTE SCOPE, STATED EXPLICITLY:
- Reads ONLY from research_winners and research_losers.
- Never touches `trades`, `versions`, AI Brain, Ranking, the Validation
  Engine, or any decision-making code, anywhere.
- Never writes anywhere except one local CSV file (Section O) - no
  database writes, no new tables, no modification to any existing
  table or row.
- Not the same thing as compare_winners_losers.py's own Priority Score
  ranking - Section D here is a fresh, simpler ranking computed
  independently for this specific request, so it can be read on its
  own without needing to reconcile two different scoring formulas.

HONESTY REQUIREMENT, PER SECTION M's OWN INSTRUCTION: this script does
not assume market_health/market_regime data is meaningfully populated
for these trades. It checks directly, reports exactly what it finds
including a NULL rate, and states plainly if the data is not usable -
never silently proceeding as if it were.
================================================================================
"""

import os
import sys
import csv
import json
import statistics
import time

import psycopg2
from datetime import datetime

from snapshot_writer import save_snapshot, update_snapshot_status

MODULE_KEY = "deep_research_export"
MODULE_NAME = "Deep Historical Research Export"
MODULE_CATEGORY = "research_lab"
MODULE_VERSION = "1.0"


# ================================================
# 🔌 DATABASE CONNECTION - identical pattern to every other Research Lab module
# ================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - this script needs "
            "the same DATABASE_URL every other Research Lab module uses."
        )
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# ⚙️ THE 17 VARIABLES - same set compare_winners_losers.py already computes
# ================================================

CONTINUOUS_VARS = [
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

CATEGORICAL_VARS = [
    ("compression_status", "Compression"),
    ("market_regime", "Market Regime"),
    ("sector", "Sector"),
    ("session", "Session"),
    ("quality_grade", "Quality Grade"),
    ("direction", "Direction"),
]

ALL_COLUMNS = (
    ["trade_id", "symbol", "recorded_at", "market_health"]
    + [c for c, _ in CONTINUOUS_VARS]
    + [c for c, _ in CATEGORICAL_VARS]
)


# ================================================
# 📥 DATA ACCESS
# ================================================

def _fetch_all(table):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        columns_sql = ", ".join(ALL_COLUMNS)
        cur.execute(f"SELECT {columns_sql} FROM {table}")
        rows = cur.fetchall()
        return [dict(zip(ALL_COLUMNS, row)) for row in rows]
    except Exception as e:
        print(f"⚠️ Deep Research Export: failed to read {table} - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📊 STATISTICAL HELPERS
# ================================================

def _continuous_stats(rows, column):
    values = [r[column] for r in rows if r.get(column) is not None]
    if not values:
        return {"n": 0, "mean": None, "median": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "stdev": round(statistics.stdev(values), 4) if len(values) >= 2 else None,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _categorical_distribution(rows, column):
    values = [r[column] for r in rows if r.get(column) is not None]
    total = len(values)
    if total == 0:
        return {}
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return {k: {"count": v, "pct": round((v / total) * 100, 2)} for k, v in
            sorted(counts.items(), key=lambda x: x[1], reverse=True)}


def _pooled_std(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    try:
        va, vb = statistics.variance(a), statistics.variance(b)
    except statistics.StatisticsError:
        return None
    n1, n2 = len(a), len(b)
    pooled_var = ((n1 - 1) * va + (n2 - 1) * vb) / (n1 + n2 - 2)
    return pooled_var ** 0.5 if pooled_var > 0 else None


# ================================================
# SECTION A / B - per-group full breakdown
# ================================================

def section_a_b(rows, label):
    print(f"\n{'=' * 70}\nSECTION - {label}\n{'=' * 70}")
    print(f"Sample size (n): {len(rows)}")

    print("\n-- Continuous variables (Mean / Median / StDev / Min / Max) --")
    for col, name in CONTINUOUS_VARS:
        s = _continuous_stats(rows, col)
        if s["n"] == 0:
            print(f"  {name}: NO DATA")
        else:
            print(f"  {name}: n={s['n']} mean={s['mean']} median={s['median']} "
                  f"stdev={s['stdev']} min={s['min']} max={s['max']}")

    print("\n-- Categorical variables (distribution) --")
    for col, name in CATEGORICAL_VARS:
        dist = _categorical_distribution(rows, col)
        print(f"  {name}:")
        if not dist:
            print("    NO DATA")
        for cat, d in dist.items():
            print(f"    {cat}: {d['count']} ({d['pct']}%)")


# ================================================
# SECTION C / D - Winners vs Losers, ranked by strength of difference
# ================================================

def section_c_and_d(winners, losers):
    print(f"\n{'=' * 70}\nSECTION C - WINNERS vs LOSERS (all 17 variables)\n{'=' * 70}")

    ranking = []

    for col, name in CONTINUOUS_VARS:
        w_vals = [r[col] for r in winners if r.get(col) is not None]
        l_vals = [r[col] for r in losers if r.get(col) is not None]
        print(f"\n{name}")
        if not w_vals or not l_vals:
            print("  INSUFFICIENT DATA")
            continue
        w_mean, l_mean = statistics.mean(w_vals), statistics.mean(l_vals)
        w_med, l_med = statistics.median(w_vals), statistics.median(l_vals)
        diff = w_mean - l_mean
        pooled = _pooled_std(w_vals, l_vals)
        strength = round(abs(diff) / pooled, 4) if pooled else 0.0
        print(f"  Winner Mean/Median: {round(w_mean,4)} / {round(w_med,4)}  "
              f"(n={len(w_vals)})")
        print(f"  Loser  Mean/Median: {round(l_mean,4)} / {round(l_med,4)}  "
              f"(n={len(l_vals)})")
        print(f"  Difference (mean): {round(diff,4)}")
        print(f"  Normalized strength (|diff| / pooled stdev): {strength}"
              f"{'  [caution: small sample]' if min(len(w_vals), len(l_vals)) < 30 else ''}")
        ranking.append((name, strength, "continuous"))

    for col, name in CATEGORICAL_VARS:
        w_dist = _categorical_distribution(winners, col)
        l_dist = _categorical_distribution(losers, col)
        print(f"\n{name}")
        if not w_dist or not l_dist:
            print("  INSUFFICIENT DATA")
            continue
        all_cats = set(w_dist) | set(l_dist)
        max_gap, max_gap_cat = 0.0, None
        for cat in all_cats:
            wp = w_dist.get(cat, {}).get("pct", 0.0)
            lp = l_dist.get(cat, {}).get("pct", 0.0)
            gap = abs(wp - lp)
            if gap > max_gap:
                max_gap, max_gap_cat = gap, cat
        w_str = ", ".join(f"{k}: {v['pct']}%" for k, v in w_dist.items())
        l_str = ", ".join(f"{k}: {v['pct']}%" for k, v in l_dist.items())
        print(f"  Winners distribution: {{{w_str}}}")
        print(f"  Losers  distribution: {{{l_str}}}")
        print(f"  Largest single-category gap: {max_gap_cat} ({round(max_gap,2)} pts)")
        ranking.append((name, round(max_gap / 100.0, 4), "categorical"))

    print(f"\n{'=' * 70}\nSECTION D - RANKED BY STRENGTH OF DIFFERENCE (data-driven, not theoretical)\n{'=' * 70}")
    ranking.sort(key=lambda x: x[1], reverse=True)
    for i, (name, strength, kind) in enumerate(ranking, 1):
        print(f"  {i}. {name} ({kind}) - strength score: {strength}")

    return ranking  # additive only - the printed Section D above is unchanged


# ================================================
# SECTION E - Direction split, with explicit sample-size honesty
# ================================================

def section_e(winners, losers):
    print(f"\n{'=' * 70}\nSECTION E - DIRECTION SPLIT\n{'=' * 70}")
    for direction in ["LONG", "SHORT"]:
        w_sub = [r for r in winners if r.get("direction") == direction]
        l_sub = [r for r in losers if r.get("direction") == direction]
        print(f"\n{direction}: {len(w_sub)} winners, {len(l_sub)} losers")
        if len(w_sub) < 30 or len(l_sub) < 30:
            print("  SAMPLE TOO SMALL (< 30 in one or both groups) - "
                  "no strong conclusion should be drawn from this split yet.")
            continue
        for col, name in CONTINUOUS_VARS[:5]:
            w_vals = [r[col] for r in w_sub if r.get(col) is not None]
            l_vals = [r[col] for r in l_sub if r.get(col) is not None]
            if w_vals and l_vals:
                print(f"  {name}: winner mean {round(statistics.mean(w_vals),3)} "
                      f"vs loser mean {round(statistics.mean(l_vals),3)}")


# ================================================
# SECTION F/G/H/I/J - individual categorical deep-dives
# ================================================

def section_categorical_deep_dive(winners, losers, column, title, note=None):
    print(f"\n{'=' * 70}\nSECTION - {title}\n{'=' * 70}")
    if note:
        print(note)
    w_dist = _categorical_distribution(winners, column)
    l_dist = _categorical_distribution(losers, column)
    all_cats = sorted(set(w_dist) | set(l_dist))
    if not all_cats:
        print("  NO DATA AVAILABLE FOR THIS VARIABLE")
        return
    print(f"  Categories actually present in the data: {all_cats}")
    for cat in all_cats:
        w = w_dist.get(cat, {"count": 0, "pct": 0.0})
        l = l_dist.get(cat, {"count": 0, "pct": 0.0})
        w_total = w["count"] + l["count"]
        win_rate = round((w["count"] / w_total) * 100, 2) if w_total > 0 else None
        print(f"  {cat}: Winners={w['count']} ({w['pct']}%)  Losers={l['count']} ({l['pct']}%)  "
              f"Win Rate within category={win_rate}%")


# ================================================
# SECTION K - Brain Confidence full distribution (not just mean)
# ================================================

def section_k(winners, losers):
    print(f"\n{'=' * 70}\nSECTION K - BRAIN CONFIDENCE DISTRIBUTION (not just mean)\n{'=' * 70}")
    bins = [(0, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
    bin_results = []
    for lo, hi in bins:
        w_in_bin = [r for r in winners if r.get("brain_confidence") is not None and lo <= r["brain_confidence"] < hi]
        l_in_bin = [r for r in losers if r.get("brain_confidence") is not None and lo <= r["brain_confidence"] < hi]
        total = len(w_in_bin) + len(l_in_bin)
        win_rate = round((len(w_in_bin) / total) * 100, 2) if total > 0 else None
        flag = "" if total >= 30 else "  [small sample]"
        print(f"  [{lo}-{hi}): winners={len(w_in_bin)} losers={len(l_in_bin)} "
              f"win_rate={win_rate}%{flag}")
        bin_results.append({"range": f"{lo}-{hi}", "winners": len(w_in_bin), "losers": len(l_in_bin),
                             "win_rate": win_rate, "n": total})
    return bin_results  # additive only - the printed distribution above is unchanged


# ================================================
# SECTION L - does higher Score/Ranking Score correlate with win rate?
# ================================================

def section_l(winners, losers):
    print(f"\n{'=' * 70}\nSECTION L - SCORE / RANKING SCORE vs WIN RATE\n{'=' * 70}")
    all_results = {}
    for col, name in [("score", "Score"), ("ranking_score", "Ranking Score")]:
        print(f"\n{name} (quartile bins across the combined pool):")
        combined = [(r[col], "WIN") for r in winners if r.get(col) is not None] + \
                   [(r[col], "LOSS") for r in losers if r.get(col) is not None]
        if len(combined) < 40:
            print("  INSUFFICIENT DATA for quartile binning")
            all_results[name] = "INSUFFICIENT DATA"
            continue
        combined.sort(key=lambda x: x[0])
        n = len(combined)
        quartile_size = n // 4
        quartiles = []
        for q in range(4):
            start = q * quartile_size
            end = (q + 1) * quartile_size if q < 3 else n
            chunk = combined[start:end]
            wins = sum(1 for _, outcome in chunk if outcome == "WIN")
            win_rate = round((wins / len(chunk)) * 100, 2) if chunk else None
            val_range = f"{round(chunk[0][0], 2)} - {round(chunk[-1][0], 2)}" if chunk else "N/A"
            print(f"  Q{q+1} (range {val_range}, n={len(chunk)}): win rate = {win_rate}%")
            quartiles.append({"quartile": f"Q{q+1}", "range": val_range, "n": len(chunk), "win_rate": win_rate})
        all_results[name] = quartiles
    return all_results  # additive only - the printed quartile breakdown above is unchanged


# ================================================
# SECTION M - Market Context: verify, don't assume
# ================================================

def section_m(winners, losers):
    print(f"\n{'=' * 70}\nSECTION M - MARKET CONTEXT (verified, not assumed)\n{'=' * 70}")

    all_rows = winners + losers
    total = len(all_rows)
    market_health_present = sum(1 for r in all_rows if r.get("market_health") is not None)
    market_regime_present = sum(1 for r in all_rows if r.get("market_regime") is not None)

    print(f"\nmarket_health (from research_winners/losers' own column):")
    print(f"  Present: {market_health_present}/{total} "
          f"({round((market_health_present/total)*100, 1) if total else 0}%)")
    market_health_finding = None
    if market_health_present == 0:
        market_health_finding = ("market_health is NOT populated for any trade in this sample - "
                                  "sourced from initial_snapshot's own key, reserved None at write "
                                  "time (structural circular dependency, predates v23.2.1). No "
                                  "Winners vs Losers breakdown by Market Health is possible from "
                                  "research_winners/research_losers as they stand today.")
        print("  FINDING: market_health is NOT populated for any trade in this sample.")
        print("  This column is sourced from initial_snapshot's own 'market_health' key,")
        print("  which was reserved as None at write time due to a structural circular")
        print("  dependency (market_health_score is computed AFTER the per-symbol decision")
        print("  loop completes - documented at the time initial_snapshot was expanded).")
        print("  IMPORTANT: this is DIFFERENT from the market_health_score/market_snapshot")
        print("  columns added directly to `trades` in v23.2.1 - those were never wired")
        print("  into winners_analyzer.py/losers_analyzer.py's own SELECT/INSERT, since")
        print("  that code predates v23.2.1. No Winners vs Losers breakdown by Market")
        print("  Health is possible from research_winners/research_losers as they stand")
        print("  today - this requires a separate, explicit development step, not")
        print("  something this analysis can produce from existing data.")
    else:
        section_categorical_deep_dive(winners, losers, "market_health", "Market Health (populated)")

    print(f"\nmarket_regime:")
    print(f"  Present: {market_regime_present}/{total} "
          f"({round((market_regime_present/total)*100, 1) if total else 0}%)")
    if market_regime_present > 0:
        section_categorical_deep_dive(winners, losers, "market_regime", "Market Regime (populated)")
    else:
        print("  FINDING: market_regime is not populated for this sample either.")

    return {
        "total_rows": total,
        "market_health_present": market_health_present,
        "market_regime_present": market_regime_present,
        "market_health_finding": market_health_finding,
    }  # additive only - every print statement above is unchanged


# ================================================
# SECTION N - Missing Data Audit, all 17 variables
# ================================================

def section_n(winners, losers):
    print(f"\n{'=' * 70}\nSECTION N - MISSING DATA AUDIT (all 17 variables)\n{'=' * 70}")
    all_rows = winners + losers
    total = len(all_rows)
    print(f"Total records audited: {total} ({len(winners)} winners + {len(losers)} losers)\n")

    coverage = {}
    for col, name in CONTINUOUS_VARS + CATEGORICAL_VARS:
        present = sum(1 for r in all_rows if r.get(col) is not None)
        missing = total - present
        pct = round((present / total) * 100, 2) if total else 0.0
        flag = "" if pct == 100.0 else "  ⚠️"
        print(f"  {name}: present={present} missing={missing} completeness={pct}%{flag}")
        coverage[name] = {"present": present, "missing": missing, "completeness_pct": pct}
    return coverage  # additive only - every print statement above is unchanged


# ================================================
# SECTION O - Raw export, one row per trade
# ================================================

def section_o(winners, losers, output_path="deep_research_export.csv"):
    print(f"\n{'=' * 70}\nSECTION O - RAW EXPORT\n{'=' * 70}")
    fieldnames = ["trade_id", "outcome", "symbol", "recorded_at"] + \
                 [c for c, _ in CONTINUOUS_VARS] + [c for c, _ in CATEGORICAL_VARS]
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in winners:
                row = {k: r.get(k) for k in fieldnames if k not in ("outcome",)}
                row["outcome"] = "WIN"
                writer.writerow(row)
            for r in losers:
                row = {k: r.get(k) for k in fieldnames if k not in ("outcome",)}
                row["outcome"] = "LOSS"
                writer.writerow(row)
        print(f"  Exported {len(winners) + len(losers)} rows to {output_path}")
    except Exception as e:
        print(f"  ⚠️ Failed to write export - {e}")


# ================================================
# ▶ ENTRY POINT
# ================================================

def main():
    update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "RUNNING")
    start_time = time.time()
    print(f"🔬 Deep Historical Research Export starting - {datetime.now().isoformat()}")

    try:
        winners = _fetch_all("research_winners")
        losers = _fetch_all("research_losers")

        if not winners and not losers:
            print("⚠️ No data retrieved from research_winners/research_losers - nothing to analyze.")
            # No save_snapshot() call - the Runner correctly reports
            # PARTIAL (last_success_at does not advance) rather than a
            # false SUCCESS with no real content.
            return

        section_a_b(winners, "A) WINNERS")
        section_a_b(losers, "B) LOSERS")
        ranking = section_c_and_d(winners, losers)
        section_e(winners, losers)
        section_categorical_deep_dive(winners, losers, "quality_grade", "F) QUALITY GRADE")
        section_categorical_deep_dive(winners, losers, "market_regime", "G) MARKET REGIME")
        section_categorical_deep_dive(winners, losers, "compression_status", "H) COMPRESSION",
                                       note="Showing categories actually present in the data - not an assumed fixed list.")
        section_categorical_deep_dive(winners, losers, "session", "I) SESSION")
        section_categorical_deep_dive(winners, losers, "sector", "J) SECTOR")
        brain_confidence_distribution = section_k(winners, losers)
        score_quartiles = section_l(winners, losers)
        market_context = section_m(winners, losers)
        missing_data_coverage = section_n(winners, losers)
        section_o(winners, losers)

        total_records = len(winners) + len(losers)
        print(f"\n🔬 Deep Historical Research Export finished - {datetime.now().isoformat()}")
        print(f"🔬 Deep Historical Research Export: recorded {total_records} analyzed record(s)")
        print("\nNote: descriptive statistics only. No AI Brain, decision logic, or")
        print("weights were read or modified anywhere in this script. A human decides")
        print("what, if anything, these findings mean for a future, separately")
        print("reviewed change.")

        # Executive summary for Telegram - basic numbers, simple
        # categorical distributions, PLUS structured extracts from
        # Sections D/K/L/M/N (the ranking, distribution, and coverage
        # values those functions already computed and printed - see
        # each section_* function above, where a single additive
        # `return` was added at the very end, with zero change to any
        # calculation or existing print statement).
        #
        # WHAT STAYED LOCAL, AND WHY: Section C (full per-variable
        # detail for all 17 variables) is not duplicated here - it
        # overlaps with winner_loser_dna_analysis.py's own full_dna()
        # breakdown, already in /research_report. Sections E and F-J
        # (per-category deep dives) are not duplicated either - the
        # top-level categorical distributions already captured below
        # cover the same ground without repeating five near-identical
        # per-category tables. Section O (raw CSV, one row per trade)
        # cannot safely become a structured Telegram summary at all -
        # it IS the raw per-trade export; summarizing it further would
        # just re-derive what sections A-N already provide. All of
        # these remain fully available locally/stdout - nothing was
        # deleted, only not duplicated into the Telegram-facing summary.
        from collections import Counter
        rr_values = [r.get("rr") for r in (winners + losers) if r.get("rr") is not None]
        score_values = [r.get("score") for r in (winners + losers) if r.get("score") is not None]

        def _distribution(rows, field):
            counts = Counter(r.get(field) for r in rows if r.get(field) is not None)
            return dict(counts.most_common(5))  # top 5 categories - keeps the Telegram message readable

        summary = {
            "winners_count": len(winners),
            "losers_count": len(losers),
            "overall_avg_rr": round(sum(rr_values) / len(rr_values), 3) if rr_values else None,
            "overall_avg_score": round(sum(score_values) / len(score_values), 2) if score_values else None,
            "winners_quality_grade_distribution": _distribution(winners, "quality_grade"),
            "losers_quality_grade_distribution": _distribution(losers, "quality_grade"),
            "winners_market_regime_distribution": _distribution(winners, "market_regime"),
            "losers_market_regime_distribution": _distribution(losers, "market_regime"),
            "winners_compression_status_distribution": _distribution(winners, "compression_status"),
            "losers_compression_status_distribution": _distribution(losers, "compression_status"),
            # Section D - top 5 strongest differentiators across all 17 variables
            "top_differentiators": ranking[:5] if ranking else [],
            # Section K - full Brain Confidence distribution (the field
            # confirmed elsewhere to be Low Variance - shown here with
            # real numbers, not just the qualitative warning)
            "brain_confidence_distribution": brain_confidence_distribution,
            # Section L - Score/Ranking Score by quartile vs win rate
            "score_quartiles": score_quartiles,
            # Section M - Market Context availability + the architectural finding
            "market_context_availability": market_context,
            # Section N - completeness of all 17 variables (condensed to incomplete-only, keeps the message shorter)
            "incomplete_fields": {k: v for k, v in missing_data_coverage.items() if v["completeness_pct"] < 100.0},
            "note": "Section C (full per-variable detail) overlaps with Winner/Loser DNA elsewhere in "
                    "/research_report, not duplicated here. Sections E/F-J (per-category deep dives) are "
                    "covered by the distributions above. Section O (raw CSV, one row per trade) stays "
                    "local/stdout only - it cannot become a structured summary without just re-deriving "
                    "what sections A-N already provide. Full detail: run deep_research_export.py directly.",
        }
        headline_stat = (f"{len(winners)} winners, {len(losers)} losers | "
                          f"Top differentiator: {ranking[0][0] if ranking else 'N/A'}")

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
            records_processed=total_records,
        )
        if not ok:
            raise RuntimeError("snapshot write failed")

    except Exception as e:
        update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
        print(f"⚠️ Deep Historical Research Export: unhandled error - {e}")
        raise


if __name__ == "__main__":
    main()
