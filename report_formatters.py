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


