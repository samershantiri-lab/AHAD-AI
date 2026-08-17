"""
================================================================================
AHAD AI - Research Lab
Top Movers Analysis (Gainers vs Losers)
================================================================================

Compares research_top_gainers vs research_top_losers - the MARKET Top
Gainers/Losers dataset, NOT research_winners/research_losers (which are
AHAD AI trade outcomes, a completely different research domain handled
by compare_winners_losers.py, untouched by this module).

REUSED WITHOUT MODIFICATION, per the audited architecture:
  - research_statistics.py: evidence_level(), priority_score() - the
    same effect-size/evidence machinery every other Research Lab
    module uses. Confirmed statistically domain-agnostic (a pooled-std
    normalized difference works on any two continuous samples,
    including market-movement features, not just trade outcomes).
  - snapshot_writer.py: save_snapshot()/update_snapshot_status() -
    identical lifecycle contract as every other module.

RESTRICTED EVIDENCE CLASSIFICATION (first implementation, deliberate):
  Only three states are possible here: INSUFFICIENT DATA / OBSERVATION
  / CANDIDATE. VALIDATED and REJECTED are NEVER returned - no time-
  aware, out-of-sample validation path exists yet. research_statistics.
  py's own STRONG/MODERATE/WEAK labels are used only as an internal
  strength signal, then remapped here - they are never surfaced as-is,
  to avoid implying a validation status that does not exist.

MOVE STRENGTH - MAGNITUDE, NOT SIGNED CHANGE:
  change_pct is positive for every Gainer and negative for every Loser
  by definition. Computing percentiles on the SIGNED values pooled
  together would produce a bimodal distribution (Gainers cluster at
  the top, Losers at the bottom) and a meaningless combined threshold.
  This module uses abs(change_pct) - movement MAGNITUDE, direction
  removed - pooled across both Gainers and Losers, to derive normal/
  strong/extreme thresholds that apply symmetrically to both. Direction
  (GAINER/LOSER) is tracked completely separately from magnitude.
  Recorded explicitly as "magnitude_percentile_derived" and
  "classification_only": true - these thresholds classify observed
  historical moves for research purposes only; they are never used as
  predictive/entry criteria anywhere in this module.

INTERACTIONS: a small, explicitly limited set only (per the approved
spec) - no combinatorial sweep across all feature pairs.

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file. Read-only against research_top_
gainers/research_top_losers - no writes to either table, no schema
changes, no new tables.
================================================================================
"""

import os
import time
import statistics
from datetime import datetime

import psycopg2

from research_statistics import evidence_level, priority_score, MIN_SAMPLE_SIZE
from snapshot_writer import save_snapshot, update_snapshot_status

MODULE_KEY = "top_movers_analysis"
MODULE_NAME = "Top Movers Analysis (Gainers vs Losers)"
MODULE_CATEGORY = "research_lab"
MODULE_VERSION = "1.0"

DATABASE_URL = os.environ.get("DATABASE_URL")

# Restricted evidence gates for THIS module only - deliberately looser
# language than research_statistics.py's own STRONG/MODERATE/WEAK,
# since those imply a validation maturity this module does not have.
OBSERVATION_MIN_N = 20
CANDIDATE_MIN_N = 50

# Continuous features analyzed - grouped per the approved spec.
# Only columns confirmed present in both research_top_gainers and
# research_top_losers (verified against both tables' own INSERT
# column lists).
FEATURE_GROUPS = {
    "MOMENTUM": [("momentum_score", "Momentum Score"), ("rsi_15m", "RSI (15m)"), ("macd", "MACD")],
    "FLOW_VOLUME": [("flow", "Flow"), ("volume_ratio", "Volume Ratio"), ("volume_acceleration", "Volume Acceleration")],
    "STRUCTURE": [("ema20", "EMA20"), ("ema50", "EMA50"), ("ema200", "EMA200"), ("atr", "ATR")],
}
# Compression (compression_status) and Market Context (market_regime,
# market_health, session, sector, direction) are categorical/
# conditioning variables, not continuous features - handled separately
# as conditioning dimensions for top findings, not primary comparisons.

# Explicitly limited interaction set - per the approved spec, never an
# exhaustive sweep. Each pair: (feature_a, feature_b).
# Approved interaction set - exactly 4 areas, per the approved design.
# CONTINUOUS_INTERACTIONS: both variables continuous - analyzed via the
# existing product-based proxy (feat_a * feat_b), complete-case.
CONTINUOUS_INTERACTIONS = [
    ("flow", "volume_acceleration"),
]
# CONDITIONED_INTERACTIONS: one continuous feature x one categorical
# dimension (compression_status or market_regime) - these are NOT
# multiplied together (a continuous value times a category string is
# meaningless). Instead the continuous feature's Gainers-vs-Losers
# difference is stratified by each category value actually present,
# reusing the exact same _condition_finding() logic already used for
# market_regime conditioning on top findings - no new metric invented.
CONDITIONED_INTERACTIONS = [
    ("flow", "compression_status"),
    ("momentum_score", "compression_status"),
    ("volume_acceleration", "market_regime"),
]

# market_regime is the only real conditioning dimension used on top
# findings. GAINER vs LOSER (direction) is the comparison axis itself
# throughout this entire module - it is never applied a second time as
# a conditioning breakdown, since that would just repeat the same
# comparison already being made.


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# 📥 DATA ACCESS - read-only, complete-case per feature
# ================================================

def _fetch_all(table):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT symbol, observed_date, change_pct, market_regime, direction,
                   momentum_score, rsi_15m, macd, flow, volume_ratio, volume_acceleration,
                   ema20, ema50, ema200, atr, compression_status
            FROM {table}
        """)
        cols = ["symbol", "observed_date", "change_pct", "market_regime", "direction",
                "momentum_score", "rsi_15m", "macd", "flow", "volume_ratio", "volume_acceleration",
                "ema20", "ema50", "ema200", "atr", "compression_status"]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows
    except Exception as e:
        print(f"⚠️ Top Movers Analysis: failed to read {table} - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📏 MOVE STRENGTH - magnitude-derived, direction kept separate
# ================================================

def _derive_move_strength(gainers, losers):
    """
    Pools abs(change_pct) from BOTH gainers and losers - magnitude
    only, direction discarded for this calculation - and derives
    normal/strong/extreme thresholds from the ACTUAL observed
    distribution (70th and 90th percentiles), never a fixed/invented
    number. Returns the thresholds plus full metadata for auditability
    and the classify() closure to label any single record.
    """
    magnitudes = [abs(r["change_pct"]) for r in (gainers + losers) if r.get("change_pct") is not None]
    n = len(magnitudes)
    dates = [r["observed_date"] for r in (gainers + losers) if r.get("observed_date") is not None]

    definition = {
        "method": "magnitude_percentile_derived",
        "classification_only": True,
        "n_used": n,
        "date_range": {
            "from": min(dates).isoformat() if dates else None,
            "to": max(dates).isoformat() if dates else None,
        },
        "is_fixed_threshold": False,
    }

    if n < MIN_SAMPLE_SIZE:
        definition["strong_threshold_pct"] = None
        definition["extreme_threshold_pct"] = None
        definition["status"] = "INSUFFICIENT DATA"
        return definition, lambda pct: "INSUFFICIENT DATA"

    sorted_mags = sorted(magnitudes)
    # 70th/90th percentile split -> normal / strong / extreme.
    # Using statistics.quantiles (n=10, deciles) to read off exact cut points.
    deciles = statistics.quantiles(sorted_mags, n=10)
    strong_cut = deciles[6]   # 70th percentile (7th of 9 decile cut points)
    extreme_cut = deciles[8]  # 90th percentile (9th of 9 decile cut points)
    definition["strong_threshold_pct"] = round(strong_cut, 4)
    definition["extreme_threshold_pct"] = round(extreme_cut, 4)
    definition["status"] = "OK"

    def classify(change_pct):
        if change_pct is None:
            return "UNKNOWN"
        mag = abs(change_pct)
        if mag >= extreme_cut:
            return "EXTREME"
        if mag >= strong_cut:
            return "STRONG"
        return "NORMAL"

    return definition, classify


# ================================================
# 🔬 RESTRICTED EVIDENCE CLASSIFICATION
# ================================================

def _classify_evidence(n1, n2, values_a=None, values_b=None):
    """
    Only three outcomes possible: INSUFFICIENT DATA / OBSERVATION /
    CANDIDATE. VALIDATED and REJECTED are structurally impossible to
    return here - no time-aware out-of-sample validation path exists
    yet in this first implementation. Uses research_statistics.py's
    evidence_level() internally purely as a strength signal, then
    remaps - never passes STRONG/MODERATE EVIDENCE through as-is.
    """
    if n1 < OBSERVATION_MIN_N or n2 < OBSERVATION_MIN_N:
        return "INSUFFICIENT DATA"
    if n1 < CANDIDATE_MIN_N or n2 < CANDIDATE_MIN_N:
        return "OBSERVATION"
    raw = evidence_level(n1, n2, values_a, values_b)
    return "CANDIDATE" if raw in ("MODERATE EVIDENCE", "STRONG EVIDENCE") else "OBSERVATION"


# ================================================
# 📊 PER-FEATURE ANALYSIS - complete-case, real N retained
# ================================================

def _analyze_feature(feature_key, feature_label, gainers, losers):
    g_vals = [r[feature_key] for r in gainers if r.get(feature_key) is not None]
    l_vals = [r[feature_key] for r in losers if r.get(feature_key) is not None]
    n1, n2 = len(g_vals), len(l_vals)

    result = {
        "feature": feature_label, "feature_key": feature_key,
        "gainers_n": n1, "losers_n": n2,
    }
    if n1 < OBSERVATION_MIN_N or n2 < OBSERVATION_MIN_N:
        result["evidence_level"] = "INSUFFICIENT DATA"
        return result

    result["gainers_median"] = round(statistics.median(g_vals), 4)
    result["losers_median"] = round(statistics.median(l_vals), 4)
    result["gainers_mean"] = round(statistics.mean(g_vals), 4)
    result["losers_mean"] = round(statistics.mean(l_vals), 4)
    result["difference"] = round(result["gainers_mean"] - result["losers_mean"], 4)
    result["effect_size"] = priority_score(g_vals, l_vals)
    result["evidence_level"] = _classify_evidence(n1, n2, g_vals, l_vals)
    return result


def _condition_finding(feature_key, gainers, losers, dimension):
    """market_regime conditioning applied to a single feature - only
    for findings that already cleared CANDIDATE overall, to avoid
    combinatorial explosion. This is the ONLY real conditioning
    dimension used in this module - direction (GAINER/LOSER) is the
    comparison axis itself throughout, never a second conditioning
    breakdown on top of that same comparison."""
    breakdown = {}
    values_present = set(r.get(dimension) for r in (gainers + losers) if r.get(dimension) is not None)
    for val in values_present:
        g_sub = [r[feature_key] for r in gainers if r.get(dimension) == val and r.get(feature_key) is not None]
        l_sub = [r[feature_key] for r in losers if r.get(dimension) == val and r.get(feature_key) is not None]
        if len(g_sub) < OBSERVATION_MIN_N or len(l_sub) < OBSERVATION_MIN_N:
            breakdown[str(val)] = {"n_gainers": len(g_sub), "n_losers": len(l_sub), "evidence_level": "INSUFFICIENT DATA"}
            continue
        breakdown[str(val)] = {
            "n_gainers": len(g_sub), "n_losers": len(l_sub),
            "difference": round(statistics.mean(g_sub) - statistics.mean(l_sub), 4),
            "evidence_level": _classify_evidence(len(g_sub), len(l_sub), g_sub, l_sub),
        }
    return breakdown


# ================================================
# 🔗 APPROVED INTERACTIONS - 4 areas exactly, per the approved design
# ================================================

def _analyze_continuous_interaction(feat_a, feat_b, gainers, losers):
    """Both variables continuous - product-based interaction proxy
    (feat_a * feat_b), complete-case on both features."""
    def _paired(rows):
        return [r[feat_a] * r[feat_b] for r in rows if r.get(feat_a) is not None and r.get(feat_b) is not None]
    g_vals, l_vals = _paired(gainers), _paired(losers)
    n1, n2 = len(g_vals), len(l_vals)
    result = {"interaction": f"{feat_a} x {feat_b}", "type": "continuous_product", "gainers_n": n1, "losers_n": n2}
    if n1 < OBSERVATION_MIN_N or n2 < OBSERVATION_MIN_N:
        result["evidence_level"] = "INSUFFICIENT DATA"
        return result
    result["difference"] = round(statistics.mean(g_vals) - statistics.mean(l_vals), 4)
    result["evidence_level"] = _classify_evidence(n1, n2, g_vals, l_vals)
    return result


def _analyze_conditioned_interaction(feature_key, categorical_dim, gainers, losers):
    """One continuous feature x one categorical dimension (compression_
    status or market_regime) - a continuous value times a category
    string is meaningless, so this is NOT a product. Instead reuses
    _condition_finding() directly (the exact same stratification logic
    already used for market_regime conditioning on top findings) - no
    new metric invented, just applied to compression_status/market_
    regime here as an interaction area rather than a top-finding
    breakdown."""
    breakdown = _condition_finding(feature_key, gainers, losers, categorical_dim)
    return {
        "interaction": f"{feature_key} x {categorical_dim}",
        "type": "conditioned_stratification",
        "breakdown": breakdown,
    }


# ================================================
# 🖨 REPORT
# ================================================

def print_report(gainers, losers, move_definition, move_strength_summary, feature_results, interaction_results, top_findings):
    print("\n" + "=" * 70)
    print("🔬 AHAD AI RESEARCH LAB - TOP MOVERS ANALYSIS (Gainers vs Losers)")
    print("=" * 70)
    print(f"Gainers analyzed: {len(gainers)} | Losers analyzed: {len(losers)}")
    print(f"Move strength definition: {move_definition}")
    print(f"Move strength counts: {move_strength_summary}")

    print("\n[Feature Analysis]")
    for r in feature_results:
        if r["evidence_level"] == "INSUFFICIENT DATA":
            print(f"  {r['feature']}: N={r['gainers_n']}/{r['losers_n']} - INSUFFICIENT DATA")
        else:
            print(f"  {r['feature']}: N={r['gainers_n']}/{r['losers_n']}, diff={r['difference']}, "
                  f"effect={r['effect_size']}, {r['evidence_level']}")

    print("\n[Approved Interactions - 4 areas]")
    for r in interaction_results:
        if r["type"] == "continuous_product":
            print(f"  {r['interaction']}: N={r['gainers_n']}/{r['losers_n']}, "
                  f"evidence={r['evidence_level']}")
        else:
            print(f"  {r['interaction']}: {r['breakdown']}")

    print("\n[Top Findings]")
    for f in top_findings:
        print(f"  {f['feature']} - {f['evidence_level']} (N={f['gainers_n']}/{f['losers_n']})")

    print("\n" + "=" * 70)
    print("Note: correlation only, never causation. Move-strength thresholds are")
    print("classification-only, never predictive. VALIDATED is impossible in this")
    print("first implementation - no time-aware out-of-sample path exists yet.")
    print("=" * 70 + "\n")


def main():
    update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "RUNNING")
    start_time = time.time()
    print(f"🔬 Top Movers Analysis starting - {datetime.now().isoformat()}")

    try:
        gainers = _fetch_all("research_top_gainers")
        losers = _fetch_all("research_top_losers")

        if not gainers and not losers:
            print("⚠️ Top Movers Analysis: no data available - nothing to analyze.")
            # No save_snapshot() call - Runner correctly reports
            # PARTIAL (last_success_at does not advance) rather than a
            # false SUCCESS with no real content.
            return

        move_def, classify_fn = _derive_move_strength(gainers, losers)
        for r in gainers:
            r["move_strength"] = classify_fn(r.get("change_pct"))
        for r in losers:
            r["move_strength"] = classify_fn(r.get("change_pct"))

        # Fix 2: actually USE move_strength - counts per level, with
        # Gainer/Loser breakdown, stored in the snapshot. Research/
        # classification only - never referenced by any filter,
        # scoring, or ranking logic anywhere in this module.
        move_strength_summary = {}
        for level in ("NORMAL", "STRONG", "EXTREME"):
            move_strength_summary[level] = {
                "gainers": sum(1 for r in gainers if r.get("move_strength") == level),
                "losers": sum(1 for r in losers if r.get("move_strength") == level),
            }

        feature_results = []
        for group_name, features in FEATURE_GROUPS.items():
            for feature_key, feature_label in features:
                feature_results.append(_analyze_feature(feature_key, feature_label, gainers, losers))

        # Approved interaction set - exactly 4 areas.
        interaction_results = [
            _analyze_continuous_interaction(a, b, gainers, losers) for a, b in CONTINUOUS_INTERACTIONS
        ] + [
            _analyze_conditioned_interaction(feat, dim, gainers, losers) for feat, dim in CONDITIONED_INTERACTIONS
        ]

        # Top findings: CANDIDATE-level features only, ranked by effect_size,
        # top 5 - never the full feature dump, per the approved spec.
        candidates = [r for r in feature_results if r.get("evidence_level") == "CANDIDATE"]
        candidates.sort(key=lambda r: r.get("effect_size", 0), reverse=True)
        top_findings = candidates[:5]

        # market_regime conditioning applied only to top findings, not
        # every feature, to avoid combinatorial explosion. direction
        # (GAINER/LOSER) is the comparison axis this entire module
        # already runs on - never added again here as a second
        # conditioning breakdown of the same comparison.
        for finding in top_findings:
            finding["market_regime_breakdown"] = _condition_finding(
                finding["feature_key"], gainers, losers, "market_regime")

        print_report(gainers, losers, move_def, move_strength_summary, feature_results, interaction_results, top_findings)

        insufficient_count = sum(1 for r in feature_results if r["evidence_level"] == "INSUFFICIENT DATA")
        observation_count = sum(1 for r in feature_results if r["evidence_level"] == "OBSERVATION")
        candidate_count = len(candidates)

        summary_data = {
            "gainers_analyzed": len(gainers),
            "losers_analyzed": len(losers),
            "move_definition": move_def,
            "move_strength_summary": move_strength_summary,
            "feature_results": feature_results,
            "interaction_results": interaction_results,
            "interactions_tested": len(CONTINUOUS_INTERACTIONS) + len(CONDITIONED_INTERACTIONS),
            "top_findings": top_findings,
            "candidate_count": candidate_count,
            "validated_count": 0,  # structurally always 0 in this implementation
            "observation_count": observation_count,
            "insufficient_data_count": insufficient_count,
        }

        headline_stat = (
            f"Gainers={len(gainers)}, Losers={len(losers)} | "
            f"{candidate_count} candidate finding(s), 0 validated (no OOS path yet)"
        )

        ok = save_snapshot(
            module_key=MODULE_KEY,
            module_name=MODULE_NAME,
            category=MODULE_CATEGORY,
            headline_stat=headline_stat,
            summary_data=summary_data,
            version_scope="ALL_VERSIONS",
            detail_table=None,
            module_version=MODULE_VERSION,
            execution_duration_seconds=round(time.time() - start_time, 2),
            records_processed=len(gainers) + len(losers),
        )
        if not ok:
            raise RuntimeError("snapshot write failed")

        print(f"🔬 Top Movers Analysis: recorded {len(gainers) + len(losers)} analyzed record(s)")
        print(f"🔬 Top Movers Analysis finished - {datetime.now().isoformat()}")

    except Exception as e:
        update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
        print(f"⚠️ Top Movers Analysis: unhandled error - {e}")
        raise


if __name__ == "__main__":
    main()
