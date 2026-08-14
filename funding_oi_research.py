"""
================================================================================
AHAD AI - Research Lab
Funding Rate + Open Interest Research (Reports Layer v1 / Research Lab v2)
================================================================================

Not a registered core module discovery mechanism - registered explicitly
in research.py's RESEARCH_MODULES, same pattern as every other module.
Read-only against research_market_data and trades (JOIN on trade_id) -
no writes to either, no schema changes, no new tables.

Reuses, rather than duplicates:
  - evidence_level / priority_score / MIN_SAMPLE_SIZE from
    research_statistics.py - the ONLY evidence methodology used here,
    per the explicit requirement not to invent a third system.
  - save_snapshot / update_snapshot_status from snapshot_writer.py -
    the same contract every other module uses.

SCOPE, PER THE APPROVED SPECIFICATION:
  A) Funding at SIGNAL: Winners vs Losers, LONG vs SHORT
  B) Open Interest at SIGNAL: Winners vs Losers, LONG vs SHORT
  C) Funding/OI change between SIGNAL and the latest OPEN_UPDATE (when
     one exists) - change, % change, time between measurements, and
     the relationship of that change to the final outcome
  D) Funding x Direction alignment
  E) The literal result value (WIN_TP1/WIN_TP2/WIN_TP3/LOSS_SL/TIMEOUT)
     is preserved throughout - never collapsed to WIN/LOSS except as an
     explicit, clearly-labeled additional aggregation.

NOT IN SCOPE, PER THE EXPLICIT ARCHITECTURE RULES: no Funding/OI
historical backfill, no CLOSE measurement_point (OPEN_UPDATE remains
Funding/OI only), no change to how /scan collects data, no influence
on any trading decision - this module only reads what already exists.

No AI Brain, Ranking, Scanner, or Entry/SL/TP code is read, imported,
or referenced anywhere in this file.
================================================================================
"""

import os
import sys
import time
import statistics
from collections import defaultdict
from datetime import datetime

import psycopg2

from research_statistics import evidence_level, priority_score, MIN_SAMPLE_SIZE
from snapshot_writer import save_snapshot, update_snapshot_status

MODULE_KEY = "funding_oi_research"
MODULE_NAME = "Funding Rate + Open Interest Research"
MODULE_CATEGORY = "research_lab"
MODULE_VERSION = "1.0"

DATABASE_URL = os.environ.get("DATABASE_URL")

# Outcomes treated as "decided" for Winner/Loser splitting - TIMEOUT is
# excluded from Winner/Loser comparisons (matches the project-wide
# convention used everywhere else: Compare Winners vs Losers, Missed
# Opportunity Study, Winner/Loser DNA), but the raw result string is
# never discarded - see _outcome_breakdown() below.
WIN_RESULTS = ("WIN_TP1", "WIN_TP2", "WIN_TP3")
LOSS_RESULTS = ("LOSS_SL",)


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# 📥 DATA ACCESS - read-only JOIN of research_market_data and trades
# ================================================

def _fetch_joined_records():
    """
    One row per research_market_data measurement, joined with its
    trade's side/result/close_time. trade_id can be NULL in research_
    market_data (see save_research_market_data()'s own docstring) -
    those rows are excluded here since they cannot be linked to an
    outcome, which is this module's entire purpose.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT r.trade_id, r.measurement_point, r.signal_timestamp,
                   r.funding_rate, r.open_interest_contracts,
                   r.collection_status, r.collected_at,
                   t.side, t.result, t.status, t.close_time
            FROM research_market_data r
            JOIN trades t ON t.id = r.trade_id
            WHERE r.trade_id IS NOT NULL
            ORDER BY r.trade_id, r.collected_at
        """)
        rows = cur.fetchall()
        records = []
        for (trade_id, measurement_point, signal_ts, funding_rate, oi_contracts,
             collection_status, collected_at, side, result, status, close_time) in rows:
            records.append({
                "trade_id": trade_id, "measurement_point": measurement_point,
                "signal_timestamp": signal_ts, "funding_rate": funding_rate,
                "oi_contracts": oi_contracts, "collection_status": collection_status,
                "collected_at": collected_at, "side": side, "result": result,
                "status": status, "close_time": close_time,
            })
        return records
    except Exception as e:
        print(f"⚠️ Funding/OI Research: failed to read data - {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _group_by_trade(records):
    """
    trade_id -> {'signal': record or None, 'open_updates': [records, oldest first]}

    DUPLICATE SIGNAL POLICY, made explicit per review (previously an
    implicit side effect of the query's ORDER BY collected_at, not a
    stated decision): if more than one successfully-collected SIGNAL
    row exists for the same trade_id, the EARLIEST one (by collected_
    at) is used - it is closest to the trade's actual creation moment,
    which is what "at SIGNAL" is meant to represent. Every additional
    SIGNAL row beyond the first is counted in duplicate_signal_trade_
    ids (see _coverage_summary) rather than silently discarded without
    a record - a real anomaly worth surfacing, not hiding.
    """
    by_trade = defaultdict(lambda: {"signal": None, "open_updates": [], "extra_signal_count": 0})
    for r in records:
        if r["collection_status"] != "OK":
            continue  # only successfully-collected measurements are usable for analysis
        entry = by_trade[r["trade_id"]]
        if r["measurement_point"] == "SIGNAL":
            if entry["signal"] is None:
                entry["signal"] = r  # earliest, since records are pre-sorted by collected_at ascending
            else:
                entry["extra_signal_count"] += 1  # a real duplicate - tracked, not dropped silently
        elif r["measurement_point"] == "OPEN_UPDATE":
            entry["open_updates"].append(r)
    return by_trade


def _is_win(result):
    return result in WIN_RESULTS


def _is_loss(result):
    return result in LOSS_RESULTS


def _is_decided(result):
    return _is_win(result) or _is_loss(result)


# ================================================
# 📊 A) FUNDING AT SIGNAL, B) OI AT SIGNAL - Winners vs Losers, LONG vs SHORT
# ================================================

def _signal_value_dna(by_trade, field):
    """
    field: 'funding_rate' or 'oi_contracts'. Returns the full DNA split
    (Winners vs Losers, LONG vs SHORT) for that field's SIGNAL value,
    using ONLY decided (WIN/LOSS) trades with a successfully-collected
    SIGNAL measurement.
    """
    winner_vals, loser_vals = [], []
    long_vals, short_vals = {"win": [], "loss": []}, {"win": [], "loss": []}

    for trade_id, entry in by_trade.items():
        sig = entry["signal"]
        if sig is None or sig[field] is None or not _is_decided(sig["result"]):
            continue
        val = sig[field]
        if _is_win(sig["result"]):
            winner_vals.append(val)
        else:
            loser_vals.append(val)
        side_bucket = long_vals if sig["side"] == "LONG" else (short_vals if sig["side"] == "SHORT" else None)
        if side_bucket is not None:
            side_bucket["win" if _is_win(sig["result"]) else "loss"].append(val)

    def _describe(vals):
        if len(vals) < 2:
            return {"n": len(vals), "mean": None, "median": None}
        return {"n": len(vals), "mean": round(statistics.mean(vals), 6), "median": round(statistics.median(vals), 6)}

    return {
        "winners": _describe(winner_vals), "losers": _describe(loser_vals),
        "evidence_level": evidence_level(len(winner_vals), len(loser_vals), winner_vals, loser_vals),
        "long": {"win": _describe(long_vals["win"]), "loss": _describe(long_vals["loss"]),
                  "evidence_level": evidence_level(len(long_vals["win"]), len(long_vals["loss"]),
                                                     long_vals["win"], long_vals["loss"])},
        "short": {"win": _describe(short_vals["win"]), "loss": _describe(short_vals["loss"]),
                   "evidence_level": evidence_level(len(short_vals["win"]), len(short_vals["loss"]),
                                                      short_vals["win"], short_vals["loss"])},
        "priority_score": priority_score(winner_vals, loser_vals) if winner_vals and loser_vals else 0.0,
    }


# ================================================
# 📈 C) FUNDING/OI CHANGE DURING OPEN_UPDATE
# ================================================

def _change_analysis(by_trade):
    """
    For trades with both a SIGNAL and at least one OPEN_UPDATE
    measurement, computes Funding change, OI % change, and time
    between measurements - then splits that change by outcome. Uses
    the LATEST OPEN_UPDATE (by collected_at) per trade, per the
    approved spec's "latest/current - SIGNAL" definition.

    TIME FIELD CHOICE, verified and documented per explicit review:
    uses collected_at for BOTH endpoints, never signal_timestamp -
    because signal_timestamp = datetime.now() is recomputed fresh on
    EVERY /scan iteration in bot.py's scan() loop, for every signal
    whether it's a brand-new SIGNAL or a re-discovered OPEN_UPDATE.
    For a SIGNAL row this happens to equal the trade's real signal
    time; for an OPEN_UPDATE row it does NOT represent "time since the
    original signal" - it is just "now" at that particular scan run.
    collected_at, by contrast, consistently means "when this specific
    measurement was actually collected" for both measurement_point
    values - the only field that measures the same thing in both
    cases, which is what this calculation needs.
    """
    funding_changes_win, funding_changes_loss = [], []
    oi_pct_changes_win, oi_pct_changes_loss = [], []
    time_between_seconds = []
    trades_with_change = 0

    for trade_id, entry in by_trade.items():
        sig = entry["signal"]
        if sig is None or not entry["open_updates"] or not _is_decided(sig["result"]):
            continue
        latest = entry["open_updates"][-1]  # already ordered oldest->newest by the query
        trades_with_change += 1

        if sig["funding_rate"] is not None and latest["funding_rate"] is not None:
            change = latest["funding_rate"] - sig["funding_rate"]
            (funding_changes_win if _is_win(sig["result"]) else funding_changes_loss).append(change)

        if sig["oi_contracts"] is not None and latest["oi_contracts"] is not None and sig["oi_contracts"] != 0:
            pct_change = ((latest["oi_contracts"] - sig["oi_contracts"]) / sig["oi_contracts"]) * 100
            (oi_pct_changes_win if _is_win(sig["result"]) else oi_pct_changes_loss).append(pct_change)

        if sig["collected_at"] and latest["collected_at"]:
            time_between_seconds.append((latest["collected_at"] - sig["collected_at"]).total_seconds())

    def _describe(vals):
        if len(vals) < 2:
            return {"n": len(vals), "mean": None, "median": None}
        return {"n": len(vals), "mean": round(statistics.mean(vals), 6), "median": round(statistics.median(vals), 6)}

    return {
        "trades_with_open_update": trades_with_change,
        "funding_change": {
            "winners": _describe(funding_changes_win), "losers": _describe(funding_changes_loss),
            "evidence_level": evidence_level(len(funding_changes_win), len(funding_changes_loss),
                                               funding_changes_win, funding_changes_loss),
        },
        "oi_pct_change": {
            "winners": _describe(oi_pct_changes_win), "losers": _describe(oi_pct_changes_loss),
            "evidence_level": evidence_level(len(oi_pct_changes_win), len(oi_pct_changes_loss),
                                               oi_pct_changes_win, oi_pct_changes_loss),
        },
        "median_time_between_measurements_seconds": (
            round(statistics.median(time_between_seconds), 1) if time_between_seconds else None
        ),
    }


# ================================================
# 🎯 D) FUNDING CARRY DIRECTION - who pays whom, not a directional signal
# ================================================

def _funding_carry_direction(by_trade):
    """
    CORRECTED ECONOMIC DEFINITION (verified against exchange documentation
    before this fix - the prior version had this backwards):

    Funding is a periodic payment BETWEEN position holders, not a fee
    charged by the exchange, and not a directional/sentiment signal on
    its own:
      - Positive funding_rate -> LONGS PAY, SHORTS RECEIVE.
      - Negative funding_rate -> SHORTS PAY, LONGS RECEIVE.
      - funding_rate == 0 -> NEUTRAL: no payment changes hands either
        way, for either side. Tracked and counted, but deliberately
        excluded from the RECEIVES-vs-PAYS evidence comparison below -
        it isn't a "pays" case just because it's not "receives".

    "Receives" here means the position is on the side that COLLECTS the
    funding payment - i.e. funding is a small structural tailwind for
    that side while the rate stays at that sign (a carry benefit, not a
    price prediction). "Pays" means the opposite - a small structural
    cost (a carry cost), never a price prediction either.

    IMPORTANT CAVEAT, worth stating explicitly per the source material
    reviewed for this fix: funding rate reflects the perpetual-vs-spot
    price premium, not directly the ratio of long to short positions -
    a common misconception. This feature describes carry cost/benefit
    only, not market sentiment or a signal for future price direction.
    """
    receives = {"win": 0, "loss": 0}
    pays = {"win": 0, "loss": 0}
    neutral = {"win": 0, "loss": 0}

    for trade_id, entry in by_trade.items():
        sig = entry["signal"]
        if sig is None or sig["funding_rate"] is None or not _is_decided(sig["result"]) or sig["side"] not in ("LONG", "SHORT"):
            continue
        rate = sig["funding_rate"]
        if rate == 0:
            bucket = neutral
        elif (sig["side"] == "LONG" and rate < 0) or (sig["side"] == "SHORT" and rate > 0):
            bucket = receives
        else:
            bucket = pays
        bucket["win" if _is_win(sig["result"]) else "loss"] += 1

    def _win_rate(bucket):
        n = bucket["win"] + bucket["loss"]
        return {"n": n, "win_rate": round((bucket["win"] / n) * 100, 2) if n else None}

    receives_n = receives["win"] + receives["loss"]
    pays_n = pays["win"] + pays["loss"]
    neutral_n = neutral["win"] + neutral["loss"]
    # NEUTRAL is deliberately excluded from the evidence_level comparison
    # below - it compares RECEIVES vs PAYS only, per the explicit rule
    # that neutral cases don't enter that comparison.
    return {
        "receives_funding": _win_rate(receives),
        "pays_funding": _win_rate(pays),
        "neutral_funding": _win_rate(neutral),
        "evidence_level": "INSUFFICIENT DATA" if receives_n < MIN_SAMPLE_SIZE or pays_n < MIN_SAMPLE_SIZE
                           else ("STRONG EVIDENCE" if receives_n >= 90 and pays_n >= 90 else "MODERATE EVIDENCE"),
    }


# ================================================
# 📋 E) OUTCOME BREAKDOWN - literal result values preserved
# ================================================

def _outcome_breakdown(by_trade):
    """The literal result distribution among trades with a usable SIGNAL measurement - never collapsed to WIN/LOSS."""
    counts = defaultdict(int)
    for trade_id, entry in by_trade.items():
        if entry["signal"] is not None:
            counts[entry["signal"]["result"] or "UNKNOWN"] += 1
    return dict(counts)


# ================================================
# 📊 DATA QUALITY / COVERAGE
# ================================================

def _coverage_summary(records, by_trade):
    total_measurements = len(records)
    status_counts = defaultdict(int)
    for r in records:
        status_counts[r["collection_status"] or "UNKNOWN"] += 1
    trades_with_signal = sum(1 for e in by_trade.values() if e["signal"] is not None)
    trades_with_open_update = sum(1 for e in by_trade.values() if e["open_updates"])
    trades_with_duplicate_signal = sum(1 for e in by_trade.values() if e["extra_signal_count"] > 0)
    return {
        "total_measurements": total_measurements,
        "distinct_trades_covered": len(by_trade),
        "trades_with_signal": trades_with_signal,
        "trades_with_open_update": trades_with_open_update,
        "trades_with_duplicate_signal": trades_with_duplicate_signal,
        "collection_status_counts": dict(status_counts),
    }


# ================================================
# 🖨 REPORT
# ================================================

def print_report(records):
    by_trade = _group_by_trade(records)

    funding_dna = _signal_value_dna(by_trade, "funding_rate")
    oi_dna = _signal_value_dna(by_trade, "oi_contracts")
    change_analysis = _change_analysis(by_trade)
    carry_direction = _funding_carry_direction(by_trade)
    outcomes = _outcome_breakdown(by_trade)
    coverage = _coverage_summary(records, by_trade)

    print("\n" + "=" * 70)
    print("🔬 AHAD AI RESEARCH LAB - FUNDING RATE + OPEN INTEREST RESEARCH")
    print("=" * 70)
    print(f"Coverage: {coverage['distinct_trades_covered']} trades, "
          f"{coverage['trades_with_signal']} with SIGNAL, "
          f"{coverage['trades_with_open_update']} with OPEN_UPDATE, "
          f"{coverage['trades_with_duplicate_signal']} with duplicate SIGNAL rows (earliest used)")
    print(f"Outcome breakdown (literal): {outcomes}")

    print("\n[A] Funding Rate @ SIGNAL - Winners vs Losers")
    print(f"  Winners: {funding_dna['winners']}  Losers: {funding_dna['losers']}  "
          f"Evidence: {funding_dna['evidence_level']}")
    print(f"  LONG: {funding_dna['long']}")
    print(f"  SHORT: {funding_dna['short']}")

    print("\n[B] Open Interest @ SIGNAL - Winners vs Losers")
    print(f"  Winners: {oi_dna['winners']}  Losers: {oi_dna['losers']}  Evidence: {oi_dna['evidence_level']}")
    print(f"  LONG: {oi_dna['long']}")
    print(f"  SHORT: {oi_dna['short']}")

    print("\n[C] Funding/OI Change (SIGNAL -> latest OPEN_UPDATE)")
    print(f"  Trades with an OPEN_UPDATE: {change_analysis['trades_with_open_update']}")
    print(f"  Funding change: {change_analysis['funding_change']}")
    print(f"  OI %% change: {change_analysis['oi_pct_change']}")
    print(f"  Median time between measurements: {change_analysis['median_time_between_measurements_seconds']}s")

    print("\n[D] Funding Carry Direction (who pays whom - not a directional signal)")
    print(f"  {carry_direction}")

    print("\n" + "=" * 70)
    print("Note: correlation only, never causation. Funding/OI remain")
    print("Research-only - this report has no effect on any trading decision.")
    print("=" * 70 + "\n")

    return {
        "coverage": coverage, "outcomes": outcomes,
        "funding_at_signal": funding_dna, "oi_at_signal": oi_dna,
        "change_analysis": change_analysis, "funding_carry_direction": carry_direction,
    }


def main():
    update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "RUNNING")
    start_time = time.time()
    print(f"🔬 Funding/OI Research starting - {datetime.now().isoformat()}")

    try:
        records = _fetch_joined_records()
        if not records:
            print("⚠️ No research_market_data records with a linked trade_id - nothing to analyze.")
            return  # no save_snapshot() call -> Runner correctly reports PARTIAL, not a false OK

        results = print_report(records)

        coverage = results["coverage"]
        if coverage["trades_with_signal"] >= MIN_SAMPLE_SIZE:
            headline_stat = (f"{coverage['distinct_trades_covered']} trades covered "
                              f"(Funding Evidence: {results['funding_at_signal']['evidence_level']})")
        else:
            headline_stat = f"INSUFFICIENT DATA - only {coverage['trades_with_signal']} trades with a SIGNAL measurement"

        ok = save_snapshot(
            module_key=MODULE_KEY,
            module_name=MODULE_NAME,
            category=MODULE_CATEGORY,
            headline_stat=headline_stat,
            summary_data=results,
            version_scope="ALL_VERSIONS",
            detail_table=None,
            module_version=MODULE_VERSION,
            execution_duration_seconds=round(time.time() - start_time, 2),
            records_processed=coverage["total_measurements"],
        )
        if not ok:
            raise RuntimeError("snapshot write failed")

        print(f"🔬 Funding/OI Research: recorded {coverage['total_measurements']} analyzed measurement(s)")
        print(f"🔬 Funding/OI Research finished - {datetime.now().isoformat()}")
    except Exception as e:
        update_snapshot_status(MODULE_KEY, MODULE_NAME, MODULE_CATEGORY, "FAILED")
        print(f"⚠️ Funding/OI Research: unhandled error - {e}")
        raise


if __name__ == "__main__":
    main()
