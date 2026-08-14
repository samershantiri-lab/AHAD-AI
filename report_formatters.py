"""
================================================================================
AHAD AI - Research Lab
Shared Report Formatters (Reports Layer v1)
================================================================================

Every function below is moved VERBATIM from bot.py's own /research_report
implementation - not rewritten, not reimplemented. Extracted here so
daily_report.py and weekly_report.py (standalone scripts, run via
Render Cron, never importing bot.py itself - that would trigger the
live Telegram bot's own polling side effects) can reuse the exact same
Level 2 formatting logic, and so bot.py's /research_report can import
from here instead of duplicating it.

get_db_connection() and format_elapsed() are copied here too (also
verbatim from bot.py) - genuinely shared utility code, not analysis
logic, needed because this file must be importable standalone without
pulling in bot.py's own module-level side effects (Telegram bot
initialization, polling setup, etc).

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file.
================================================================================
"""

import os
import json
import psycopg2
from datetime import datetime


DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Create a PostgreSQL connection with proper settings - verbatim from bot.py."""
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode='require'
    )


def format_elapsed(dt):
    """
    v23.0.2 (UI/UX Reports revision) - relative time display for
    /history and /open, per the exact spec given: "10m ago / 2h ago /
    Yesterday / etc." Pure display formatting - no data or logic change.
    """
    if dt is None:
        return "N/A"
    try:
        seconds = (datetime.now() - dt).total_seconds()
    except Exception:
        return "N/A"
    if seconds < 0:
        seconds = 0
    minutes = int(seconds // 60)
    hours = minutes // 60
    days = hours // 24
    if days >= 2:
        return f"{days}d ago"
    if days == 1:
        return "Yesterday"
    if hours > 0:
        return f"{hours}h ago"
    return f"{minutes}m ago"


def _na_or_value(value, label=""):
    """N/A for a genuinely missing/None value - never silently 0."""
    return "N/A" if value is None else f"{value}{label}"


def _format_core_winners_losers(summary_data, kind):
    prefix = "winners" if kind == "winners" else "losers"
    return (
        f"New this run: {_na_or_value(summary_data.get(f'new_{prefix}_this_run'))}\n"
        f"Total recorded: {_na_or_value(summary_data.get(f'total_{prefix}'))}\n"
        f"Avg Flow: {_na_or_value(summary_data.get('avg_flow'))}\n"
        f"Avg RSI: {_na_or_value(summary_data.get('avg_rsi'))}\n"
        f"Avg Momentum: {_na_or_value(summary_data.get('avg_momentum_score'))}\n"
        f"By Quality Grade: {summary_data.get('by_quality_grade') or 'N/A'}"
    )


def _format_core_winners(summary_data):
    return _format_core_winners_losers(summary_data, "winners")


def _format_core_losers(summary_data):
    return _format_core_winners_losers(summary_data, "losers")


def _format_core_gainers_losers_study(summary_data, kind):
    prefix = "gainers" if kind == "gainers" else "losers"
    return (
        f"New this run: {_na_or_value(summary_data.get(f'new_{prefix}_this_run'))}\n"
        f"Total recorded: {_na_or_value(summary_data.get(f'total_{prefix}_recorded'))}\n"
        f"With AHAD AI trade: {_na_or_value(summary_data.get(f'{prefix}_with_ahad_ai_trade'))}\n"
        f"Avg Change: {_na_or_value(summary_data.get('avg_change_pct'), '%')}\n"
        f"Avg Flow: {_na_or_value(summary_data.get('avg_flow'))}\n"
        f"Avg RSI: {_na_or_value(summary_data.get('avg_rsi'))}"
    )


def _format_core_top_gainers(summary_data):
    return _format_core_gainers_losers_study(summary_data, "gainers")


def _format_core_top_losers(summary_data):
    return _format_core_gainers_losers_study(summary_data, "losers")


def _format_core_compare(summary_data):
    top_metrics = summary_data.get("top_metrics_worth_investigating") or []
    lines = [
        f"Winners sample: {_na_or_value(summary_data.get('winners_sample_size'))}",
        f"Losers sample: {_na_or_value(summary_data.get('losers_sample_size'))}",
        "Top metrics worth investigating:",
    ]
    if top_metrics:
        for m in top_metrics[:3]:
            lines.append(f"  - [{m.get('scope', '?')}] {m.get('metric', '?')} "
                          f"(Priority Score {m.get('priority_score', '?')})")
    else:
        lines.append("  None cleared the minimum sample threshold this run")
    return "\n".join(lines)


def _format_core_missed_opportunity(summary_data):
    return (
        f"Lookback window: {_na_or_value(summary_data.get('lookback_hours'), 'h')}\n"
        f"Gainers checked: {_na_or_value(summary_data.get('gainers_checked'))} | "
        f"matched: {_na_or_value(summary_data.get('gainers_matched'))} "
        f"({_na_or_value(summary_data.get('gainers_match_rate_pct'), '%')})\n"
        f"Losers checked: {_na_or_value(summary_data.get('losers_checked'))} | "
        f"matched: {_na_or_value(summary_data.get('losers_matched'))} "
        f"({_na_or_value(summary_data.get('losers_match_rate_pct'), '%')})"
    )


def _format_winner_loser_dna(summary_data):
    def _fmt_finding(f):
        if not f:
            return "NO RELIABLE DIFFERENTIATOR — INSUFFICIENT DATA"
        return f"{f['metric']} ({f['evidence_level']}, N={f['n_winners']}+{f['n_losers']})"

    low_var = summary_data.get("low_variance_metrics") or []
    return (
        f"Sample: {_na_or_value(summary_data.get('winners_sample_size'))} winners, "
        f"{_na_or_value(summary_data.get('losers_sample_size'))} losers\n\n"
        f"Strongest Overall: {_fmt_finding(summary_data.get('strongest_overall'))}\n"
        f"Strongest LONG: {_fmt_finding(summary_data.get('strongest_long'))}\n"
        f"Strongest SHORT: {_fmt_finding(summary_data.get('strongest_short'))}\n\n"
        f"Low Variance metrics (gradient unreliable): "
        f"{', '.join(low_var) if low_var else 'none'}"
    )


def _format_market_conditioned(summary_data):
    def _fmt_axis_table(table):
        """Direction x Regime/Condition table -> readable per-bucket lines."""
        if not table:
            return "  N/A — DATA NOT AVAILABLE"
        lines = []
        for bucket, data in table.items():
            l, s = data["LONG"], data["SHORT"]
            lines.append(f"  {bucket}: LONG WR={_na_or_value(l['win_rate'], '%')} (n={l['n']}) | "
                          f"SHORT WR={_na_or_value(s['win_rate'], '%')} (n={s['n']}) | {data['evidence_level']}")
        return "\n".join(lines)

    def _fmt_quartile_result(result):
        if not result.get("available"):
            return f"  N/A — DATA NOT AVAILABLE ({result.get('reason', 'insufficient data')})"
        lines = []
        if result.get("low_resolution_warning"):
            lines.append(f"  ⚠️ {result['low_resolution_warning']}")
        for bucket, data in result["table"].items():
            l, s = data["LONG"], data["SHORT"]
            ev = data["evidence_level"]
            ev_display = "⚠️ INSUFFICIENT DATA" if ev == "INSUFFICIENT DATA" else ev
            lines.append(f"  {bucket}: LONG WR={_na_or_value(l['win_rate'], '%')} | "
                          f"SHORT WR={_na_or_value(s['win_rate'], '%')} | {ev_display}")
        return "\n".join(lines)

    findings = summary_data.get("effect_findings") or []
    findings_text = "\n".join(f"  [{f['axis']}] {f['conclusion']}" for f in findings) or "  N/A — DATA NOT AVAILABLE"

    return (
        f"Total sample: {_na_or_value(summary_data.get('total_sample'))}\n\n"
        f"Direction Effect vs Market Effect:\n{findings_text}\n\n"
        f"Direction x Asset Market Regime:\n{_fmt_axis_table(summary_data.get('regime_table'))}\n\n"
        f"Direction x Global Market Condition:\n{_fmt_axis_table(summary_data.get('condition_table'))}\n\n"
        f"Market Health x Direction:\n{_fmt_quartile_result(summary_data.get('market_health') or {})}\n\n"
        f"Acceptance x Direction:\n{_fmt_quartile_result(summary_data.get('acceptance') or {})}"
    )


def _format_loss_clusters(summary_data):
    cs = summary_data.get("cluster_summary") or {}
    if not cs.get("available"):
        return f"N/A — DATA NOT AVAILABLE ({cs.get('reason', 'no clusters found')})"

    regime_dist = cs.get("regime_distribution") or {}
    condition_dist = cs.get("condition_distribution") or {}
    evidence_note = cs.get("evidence_note", "N/A")

    # Correlation-only phrasing, calibrated to the evidence note already
    # computed by the module itself - never a causal claim.
    if "INSUFFICIENT" in evidence_note:
        context_label = "Potential common context (sample too small to describe reliably)"
    else:
        context_label = "Observed concentration (descriptive/correlational only, not a cause)"

    return (
        f"Number of clusters: {_na_or_value(summary_data.get('cluster_count'))}\n"
        f"Trades inside clusters: {_na_or_value(cs.get('total_trades_in_clusters'))}\n"
        f"Longest cluster: {_na_or_value(summary_data.get('longest_cluster'))}\n\n"
        f"{context_label}:\n"
        f"  Regime distribution: {regime_dist if regime_dist else 'N/A — DATA NOT AVAILABLE'}\n"
        f"  Condition distribution: {condition_dist if condition_dist else 'N/A — DATA NOT AVAILABLE'}\n"
        f"  Avg Market Health: {_na_or_value(cs.get('avg_health_in_clusters'))}\n"
        f"  Avg Acceptance: {_na_or_value(cs.get('avg_acceptance_in_clusters'), '%')}\n\n"
        f"Evidence: {evidence_note}"
    )



def _format_rejection_breakdown(summary_data):
    top_missed = summary_data.get("top_reason_by_missed")
    top_rate = summary_data.get("top_reason_by_miss_rate")
    reason_table = summary_data.get("reason_table") or {}

    lines = [
        f"Total rejections analyzed: {_na_or_value(summary_data.get('total_rejections'))}\n"
        f"Gainers checked: {_na_or_value(summary_data.get('gainers_checked'))} | "
        f"Losers checked: {_na_or_value(summary_data.get('losers_checked'))}\n"
    ]
    if top_missed:
        lines.append(f"Top reason by Missed Opportunities: {top_missed['reason']} "
                      f"({top_missed['missed']} missed, n={top_missed['n']})")
    else:
        lines.append("Top reason by Missed Opportunities: N/A — DATA NOT AVAILABLE")
    if top_rate:
        lines.append(f"Top reason by Miss Rate: {top_rate['reason']} - {top_rate['miss_rate_pct']}% (n={top_rate['n']})")
    else:
        lines.append("Top reason by Miss Rate: ⚠️ INSUFFICIENT DATA")

    if reason_table:
        lines.append("\nBy reason:")
        for reason, r in reason_table.items():
            lines.append(f"  {reason}: n={r['total_rejections']}, matched={r['matched']}, missed={r['missed']}")

    return "\n".join(lines)


def _format_funding_oi_research(summary_data):
    def _fmt_dna(dna, label):
        w, l = dna["winners"], dna["losers"]
        ev = dna["evidence_level"]
        ev_display = "⚠️ INSUFFICIENT DATA" if ev == "INSUFFICIENT DATA" else ev
        return (f"{label}: Winners mean={_na_or_value(w['mean'])} (n={w['n']}) | "
                f"Losers mean={_na_or_value(l['mean'])} (n={l['n']}) | {ev_display}")

    coverage = summary_data.get("coverage") or {}
    outcomes = summary_data.get("outcomes") or {}
    change = summary_data.get("change_analysis") or {}
    carry = summary_data.get("funding_carry_direction") or {}

    lines = [
        f"Coverage: {_na_or_value(coverage.get('distinct_trades_covered'))} trades linked | "
        f"{_na_or_value(coverage.get('trades_with_signal'))} with SIGNAL | "
        f"{_na_or_value(coverage.get('trades_with_open_update'))} with OPEN_UPDATE | "
        f"{_na_or_value(coverage.get('trades_with_duplicate_signal'))} with duplicate SIGNAL (earliest used)",
        f"Outcome breakdown (literal): {outcomes if outcomes else 'N/A'}",
        "",
        "A) " + _fmt_dna(summary_data.get("funding_at_signal", {}), "Funding Rate @ SIGNAL") if summary_data.get("funding_at_signal") else "A) Funding Rate @ SIGNAL: N/A — DATA NOT AVAILABLE",
        "B) " + _fmt_dna(summary_data.get("oi_at_signal", {}), "Open Interest @ SIGNAL") if summary_data.get("oi_at_signal") else "B) Open Interest @ SIGNAL: N/A — DATA NOT AVAILABLE",
        "",
        f"C) Funding/OI Change (SIGNAL→latest OPEN_UPDATE, {change.get('trades_with_open_update', 0)} trades):",
    ]

    funding_change = change.get("funding_change")
    if funding_change:
        lines.append("   " + _fmt_dna(funding_change, "Funding Change"))
    else:
        lines.append("   Funding Change: N/A — DATA NOT AVAILABLE")

    oi_change = change.get("oi_pct_change")
    if oi_change:
        lines.append("   " + _fmt_dna(oi_change, "OI % Change"))
    else:
        lines.append("   OI % Change: N/A — DATA NOT AVAILABLE")

    lines.append(f"   Median time between measurements: "
                 f"{_na_or_value(change.get('median_time_between_measurements_seconds'), 's')} "
                 f"(collected_at-based, not signal_timestamp)")

    lines.append("")
    lines.append(
        f"D) Funding Carry Direction (who pays whom - NOT a directional signal):\n"
        f"   Receives funding: n={carry.get('receives_funding', {}).get('n', 'N/A')} "
        f"WR={_na_or_value(carry.get('receives_funding', {}).get('win_rate'), '%')}\n"
        f"   Pays funding: n={carry.get('pays_funding', {}).get('n', 'N/A')} "
        f"WR={_na_or_value(carry.get('pays_funding', {}).get('win_rate'), '%')}\n"
        f"   Neutral funding (rate=0): n={carry.get('neutral_funding', {}).get('n', 'N/A')} "
        f"(excluded from Evidence comparison)\n"
        f"   Evidence (Receives vs Pays only): {carry.get('evidence_level', 'N/A')}\n"
        f"   (Funding reflects the perp-vs-spot premium, not the long/short ratio - "
        f"this describes carry cost/benefit only, not market sentiment.)"
    )
    return "\n".join(lines)


def _format_deep_research_export(summary_data):
    lines = [
        f"Winners: {_na_or_value(summary_data.get('winners_count'))} | "
        f"Losers: {_na_or_value(summary_data.get('losers_count'))}",
        f"Overall Avg RR: {_na_or_value(summary_data.get('overall_avg_rr'))}",
        f"Overall Avg Score: {_na_or_value(summary_data.get('overall_avg_score'))}",
        "",
        f"Quality Grade - Winners: {summary_data.get('winners_quality_grade_distribution') or 'N/A'}",
        f"Quality Grade - Losers: {summary_data.get('losers_quality_grade_distribution') or 'N/A'}",
        f"Market Regime - Winners: {summary_data.get('winners_market_regime_distribution') or 'N/A'}",
        f"Market Regime - Losers: {summary_data.get('losers_market_regime_distribution') or 'N/A'}",
        f"Compression - Winners: {summary_data.get('winners_compression_status_distribution') or 'N/A'}",
        f"Compression - Losers: {summary_data.get('losers_compression_status_distribution') or 'N/A'}",
        "",
        "D) Top Differentiators (strongest Winner/Loser separation, all 17 vars):",
    ]
    top_diff = summary_data.get("top_differentiators") or []
    if top_diff:
        for i, (name, strength, kind) in enumerate(top_diff, 1):
            lines.append(f"  {i}. {name} ({kind}) - strength: {strength}")
    else:
        lines.append("  N/A — DATA NOT AVAILABLE")

    lines.append("")
    lines.append("K) Brain Confidence Distribution (bins with data only):")
    bc_dist = summary_data.get("brain_confidence_distribution") or []
    shown_bins = [b for b in bc_dist if b["n"] > 0]
    if shown_bins:
        for b in shown_bins:
            lines.append(f"  [{b['range']}): WR={_na_or_value(b['win_rate'], '%')} (n={b['n']})")
    else:
        lines.append("  N/A — DATA NOT AVAILABLE")

    lines.append("")
    lines.append("L) Score/Ranking Score by Quartile vs Win Rate:")
    score_q = summary_data.get("score_quartiles") or {}
    for metric, quartiles in score_q.items():
        if quartiles == "INSUFFICIENT DATA":
            lines.append(f"  {metric}: ⚠️ INSUFFICIENT DATA")
        else:
            q_str = ", ".join(f"{q['quartile']}={_na_or_value(q['win_rate'], '%')}" for q in quartiles)
            lines.append(f"  {metric}: {q_str}")

    lines.append("")
    mc = summary_data.get("market_context_availability") or {}
    lines.append(f"M) Market Context Availability: market_health "
                 f"{mc.get('market_health_present', 'N/A')}/{mc.get('total_rows', 'N/A')} | "
                 f"market_regime {mc.get('market_regime_present', 'N/A')}/{mc.get('total_rows', 'N/A')}")
    if mc.get("market_health_finding"):
        lines.append(f"  FINDING: {mc['market_health_finding']}")

    incomplete = summary_data.get("incomplete_fields") or {}
    if incomplete:
        lines.append("")
        lines.append("N) Incomplete Fields (< 100% coverage):")
        for name, c in incomplete.items():
            lines.append(f"  {name}: {c['completeness_pct']}% complete ({c['missing']} missing)")

    lines.append("")
    lines.append(summary_data.get("note", ""))
    return "\n".join(lines)


def _fetch_all_snapshots():
    """Returns a dict keyed by module_key for O(1) lookup while building each module's block."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT module_key, last_success_at, last_attempt_at,
                   last_attempt_status, headline_stat, summary_data,
                   internal_metadata
            FROM research_snapshots
        """)
        rows = cur.fetchall()
        return {
            row[0]: {
                "last_success_at": row[1],
                "last_attempt_at": row[2],
                "last_attempt_status": row[3],
                "headline_stat": row[4],
                "summary_data": row[5],
                "internal_metadata": row[6],
            }
            for row in rows
        }
    except Exception as e:
        print(f"⚠️ /research_report: failed to fetch research_snapshots - {e}")
        return {}
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


