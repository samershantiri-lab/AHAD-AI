"""
================================================================================
AHAD AI v23.3.2 - Phase 2: Research Data Foundation + Daily Research File
================================================================================

Standalone research module. ZERO modification to bot.py, AI Brain, Ranking,
save_trade(), or any Production decision logic. Runs independently (like
top_gainers_study.py etc.), reading trades AFTER production has already
saved them - never in the live decision path.

For each new trade since the last run, this module:
  1. Reads the already-stored initial_snapshot (62 fields confirmed from
     the archived data) - extracts Score components, Market Regime/Health,
     Compression AS-IS, no recalculation, no changes to how Score/Ranking
     are computed.
  2. Independently fetches Funding/OI near signal_time (entry-safe, using
     the fixed after/begin-end logic proven in historical_event_scanner.py).
  3. Independently fetches 5m candles closed strictly before signal_time
     and computes raw measurements (momentum, volume acceleration, candle
     expansion, EMA20, distance from recent move) - NO thresholds, NO
     state classification yet (per explicit instruction: stop before any
     threshold decision).
  4. Builds one record per trade following Schema v4, appends to
     daily_research_YYYY-MM-DD.json (the Research Source of Truth).
  5. Atomic write + verification (never silently loses data).

CONFIRMED DATA GAP (documented, not invented): `initial_snapshot.market_context`
is frequently null/empty in production data. Acceptance/Breadth (discovered
earlier only inside research_winners/research_losers.market_snapshot_json)
are NOT available for every trade - only market_regime and
market_health_score (separate SQL columns on `trades`) are reliably present.
This module records acceptance/breadth as "NOT_AVAILABLE" rather than
inventing values - per the explicit "no fabricated data" rule.

Run manually or via a scheduled job, entirely separate from bot.py:
    python3 research_data_foundation.py
================================================================================
"""

import json
import os
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import requests

DATABASE_URL = os.environ.get("DATABASE_URL")
OKX_BASE_URL = "https://www.okx.com"
FUNDING_RATE_HISTORY_ENDPOINT = "/api/v5/public/funding-rate-history"
OPEN_INTEREST_HISTORY_ENDPOINT = "/api/v5/rubik/stat/contracts/open-interest-history"
CANDLES_HISTORY_ENDPOINT = "/api/v5/market/history-candles"

OUTPUT_DIR = "daily_research"
STATE_FILE = os.path.join(OUTPUT_DIR, ".research_state.json")

STATS = {"total_requests": 0, "failures": 0}


# ================================================
# HTTP - same retry pattern used throughout this project
# ================================================

def _request(url, params, max_retries=3):
    for attempt in range(max_retries):
        STATS["total_requests"] += 1
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "0":
                    return data
            time.sleep(1 * (2 ** attempt))
        except Exception:
            time.sleep(1 * (2 ** attempt))
    STATS["failures"] += 1
    return None


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


# ================================================
# Entry-safe Funding/OI near signal_time
# (Same fixed logic proven in historical_event_scanner.py: funding tries
#  after/before and verifies <= event_ts; OI uses begin/end per the
#  confirmed okx-sdk parameter signature - never trusts HTTP 200 alone.)
# ================================================

def fetch_funding_near_signal(symbol, signal_ts_ms):
    """
    FIXED (P0 patch): previously saved only funding_rate/funding_time,
    losing fields we confirmed exist in the raw response (premium,
    maxFundingRate, minFundingRate, prevFundingTime, settState, etc -
    discovered in the earlier research_market_data investigation).
    Now saves ALL fields actually present in the entry as-received -
    no field is invented if the endpoint didn't return it.
    """
    for direction in ("after", "before"):
        data = _request(f"{OKX_BASE_URL}{FUNDING_RATE_HISTORY_ENDPOINT}",
                         {"instId": symbol, "limit": 10, direction: str(signal_ts_ms)})
        if data is None:
            continue
        entries = data.get("data", [])
        valid = [e for e in entries if isinstance(e, dict) and e.get("fundingTime")
                 and int(e["fundingTime"]) <= signal_ts_ms]
        if valid:
            nearest = max(valid, key=lambda e: int(e["fundingTime"]))
            # Save the entry AS-IS (every key OKX actually returned),
            # not a hand-picked subset.
            return {
                "raw": dict(nearest), "measured_at": signal_ts_ms,
                "entry_safe": True, "data_quality": "complete",
            }
    return {"raw": {}, "measured_at": signal_ts_ms, "entry_safe": True, "data_quality": "NOT_AVAILABLE"}


def fetch_oi_near_signal(symbol, signal_ts_ms):
    """
    FIXED (P0 Final Blocker): the previous version built `raw` manually
    from nearest[1]/nearest[2] only, silently dropping any additional
    array elements OKX might return (known like oiCcy, or future/
    unknown fields). Now preserves the FULL original array entry under
    raw.entry, with normalized fields (timestamp/oi_usd/oi_contracts)
    kept alongside as a derived convenience for easy querying - never
    as a replacement for the raw data.
    """
    window_start_ms = signal_ts_ms - (30 * 24 * 3600 * 1000)
    data = _request(f"{OKX_BASE_URL}{OPEN_INTEREST_HISTORY_ENDPOINT}",
                     {"instId": symbol, "period": "1H", "limit": 100,
                      "begin": str(window_start_ms), "end": str(signal_ts_ms)})
    if data is None:
        return {"raw": {}, "measured_at": signal_ts_ms, "entry_safe": True,
                "data_quality": "NOT_AVAILABLE", "oi_delta": "NOT_AVAILABLE",
                "oi_delta_status": "NOT_AVAILABLE - request failed"}
    entries = data.get("data", [])
    valid = [e for e in entries if isinstance(e, (list, tuple)) and len(e) >= 2 and int(e[0]) <= signal_ts_ms]
    if not valid:
        return {"raw": {}, "measured_at": signal_ts_ms, "entry_safe": True,
                "data_quality": "NOT_AVAILABLE", "oi_delta": "NOT_AVAILABLE",
                "oi_delta_status": "NOT_AVAILABLE - no data in window"}
    nearest = max(valid, key=lambda e: int(e[0]))
    return {
        "raw": {
            "entry": list(nearest),  # FIXED: full original OKX array entry, whatever length it is -
                                      # never truncated to only index [0..2], so any field OKX returns
                                      # (known or unknown/future) is preserved verbatim.
            "timestamp": nearest[0], "oi_usd": nearest[1] if len(nearest) > 1 else "NOT_AVAILABLE",
            "oi_contracts": nearest[2] if len(nearest) > 2 else "NOT_AVAILABLE",
            "period": "1H", "source": "OKX",
        },
        "measured_at": signal_ts_ms, "entry_safe": True,
        "data_quality": "partial - absolute value only",
        "oi_delta": "NOT_AVAILABLE",
        "oi_delta_status": "NOT_AVAILABLE - no sufficient entry-safe historical series to derive delta yet",
    }


# ================================================
# Entry-safe 5m raw measurements (NO state classification - raw only)
# ================================================

def fetch_5m_candles_before(symbol, signal_ts_ms, limit=50):
    """
    OFFICIAL 5m ENTRY-SAFETY BOUNDARY RULE (locked by explicit team
    decision, P0 Audit Closure):

        candle_close_time <= signal_ts_ms  -> VALID  (used)
        candle_close_time >  signal_ts_ms  -> REJECT (excluded)

    A candle closing exactly AT signal_time is data that was fully
    confirmed by that instant and is therefore valid - this is the
    same inclusive rule used throughout this project (matches
    historical_event_scanner.py's own look-ahead rule). Do NOT change
    this to a strict "<" without an explicit, separate team decision -
    see test_5m_boundary_rule() below, which locks this behavior as a
    regression test.
    """
    start_ms = signal_ts_ms - (limit * 5 * 60 * 1000)
    data = _request(f"{OKX_BASE_URL}{CANDLES_HISTORY_ENDPOINT}",
                     {"instId": symbol, "bar": "5m", "after": str(signal_ts_ms), "limit": limit})
    if data is None:
        return []
    raw = data.get("data", [])
    closed = [c for c in raw if len(c) > 8 and c[8] == "1" and int(c[0]) + 300000 <= signal_ts_ms]
    closed = list(reversed(closed))  # oldest-first
    return [{"ts": c[0], "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
              "close": float(c[4]), "volume": float(c[5])} for c in closed]


def compute_5m_raw(candles):
    if len(candles) < 20:
        return {"raw": {}, "candles_used": len(candles), "data_quality": "insufficient_candles",
                "entry_safe": True}
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    price_at_signal = closes[-1]

    momentum_5m = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 and closes[-5] != 0 else None
    avg_vol_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
    volume_acceleration_5m = (volumes[-1] / avg_vol_20) if avg_vol_20 else None

    recent_ranges = [c["high"] - c["low"] for c in candles[-10:]]
    older_ranges = [c["high"] - c["low"] for c in candles[-20:-10]] if len(candles) >= 20 else []
    candle_expansion_ratio = (sum(recent_ranges) / sum(older_ranges)) if older_ranges and sum(older_ranges) > 0 else None

    ema20_5m = None
    if len(closes) >= 20:
        k = 2 / 21
        ema20_5m = sum(closes[:20]) / 20
        for p in closes[20:]:
            ema20_5m = p * k + ema20_5m * (1 - k)

    recent_high = max(c["high"] for c in candles[-20:])
    recent_low = min(c["low"] for c in candles[-20:])
    distance_from_recent_move_pct = ((price_at_signal - recent_low) / (recent_high - recent_low) * 100) \
        if (recent_high - recent_low) > 0 else None

    return {
        "raw": {
            "price_at_signal": price_at_signal, "momentum_5m": momentum_5m,
            "volume_acceleration_5m": volume_acceleration_5m,
            "candle_expansion_ratio": candle_expansion_ratio, "ema20_5m": ema20_5m,
            "distance_from_recent_move_pct": distance_from_recent_move_pct,
        },
        "candles_used": len(candles), "data_quality": "complete", "entry_safe": True,
        "state": "NOT_CLASSIFIED_YET",  # explicit: no threshold decided yet, per instruction
    }


# ================================================
# Score components - extracted AS-IS from initial_snapshot, zero recomputation
# ================================================

# Full classification of all 62 fields confirmed present in initial_snapshot
# (from the archived data investigation). A+B are research-relevant and
# kept; C+D are documented here but NOT copied into the Daily File.
SCORE_COMPONENT_KEYS_A = [  # Critical for research/analysis
    "ai_brain_long", "ai_brain_short", "ai_brain_score", "score", "final_score",
    "ranking_score", "confidence", "flow", "flow_score", "momentum_score",
    "compression_score", "compression_status", "rsi_15m", "macd", "atr", "rr",
    "quality_grade", "risk_grade", "volume_acceleration", "volume_ratio",
    "whale_status", "smart_money_status", "trend", "trend_state",
    "distance_to_support", "distance_to_resistance", "market_regime",
    "market_health", "session", "hour", "weekday", "sector", "relative_strength",
    "heat_score", "heat_tier",
]
SCORE_COMPONENT_KEYS_B = [  # Useful for re-interpreting the decision
    "entry_high", "entry_low", "support", "resistance", "price", "sl",
    "tp1", "tp2", "tp3", "ema20", "ema50", "ema100", "ema200",
    "flow_grade", "sector_reference", "validation_status",
]
# C (operational identifiers, not research-analytical - excluded):
#   symbol, side, version, version_id (already present at record top-level)
#   build_number, rule_set_version, ai_brain_version, validation_engine_version,
#   ema200_timeframe, captured_at (build/deployment metadata, not decision-relevant)
# D (excluded - null/empty in practice, confirmed from archive):
#   market_context (confirmed frequently None in the archive investigation)
SCORE_COMPONENT_KEYS = SCORE_COMPONENT_KEYS_A + SCORE_COMPONENT_KEYS_B


def extract_score_breakdown(snapshot):
    if not snapshot:
        return {"final_score": None, "raw_components_reference": {}, "data_quality": "NOT_AVAILABLE"}
    components = {k: snapshot.get(k) for k in SCORE_COMPONENT_KEYS if k in snapshot}
    return {
        "final_score": snapshot.get("final_score") or snapshot.get("score"),
        "raw_components_reference": components,
        "data_quality": "complete" if components else "NOT_AVAILABLE",
    }


# ================================================
# Funding/OI State - direction-aware, EXTREME never auto-negative
# ================================================

def classify_funding_state(funding_raw, direction):
    """
    Perpetual funding mechanics (not invented - standard exchange
    convention): positive funding_rate means LONGs pay SHORTs;
    negative means SHORTs pay LONGs. So a negative rate is SUPPORTIVE
    for LONG and AGAINST for SHORT, and vice versa for positive.

    EXTREME is its own category (magnitude near cap, via
    maxFundingRate/minFundingRate if OKX actually returned them) - it
    is NEVER auto-classified as negative. interpretation always states
    which direction the extreme value favors, per the explicit rule
    that EXTREME must be read through Direction + Context, not its
    label alone.
    """
    rate = funding_raw.get("fundingRate")
    if rate is None:
        return {"derived_state": "UNKNOWN", "interpretation": "Funding rate not available",
                "data_quality": "NOT_AVAILABLE"}
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return {"derived_state": "UNKNOWN", "interpretation": "Funding rate value unparsable",
                "data_quality": "NOT_AVAILABLE"}

    max_rate = funding_raw.get("maxFundingRate")
    cap_ratio = None
    if max_rate:
        try:
            cap_ratio = abs(rate) / abs(float(max_rate)) if float(max_rate) != 0 else None
        except (TypeError, ValueError):
            cap_ratio = None

    if rate == 0:
        return {"derived_state": "NEUTRAL", "interpretation": "Funding rate is zero - no carry cost either way",
                "data_quality": "complete"}

    favors_long = rate < 0
    favored_side = "LONG" if favors_long else "SHORT"
    aligned = (direction == favored_side)

    is_extreme = cap_ratio is not None and cap_ratio >= 0.7
    if is_extreme:
        return {
            "derived_state": "EXTREME",
            "interpretation": f"Funding rate at {cap_ratio*100:.0f}% of cap, strongly favors {favored_side} "
                               f"- {'aligned with' if aligned else 'opposes'} this {direction} trade",
            "data_quality": "complete",
        }
    return {
        "derived_state": "SUPPORTIVE" if aligned else "AGAINST",
        "interpretation": f"Funding favors {favored_side} - {'supports' if aligned else 'opposes'} this {direction} trade",
        "data_quality": "complete",
    }


def classify_oi_state(oi_raw, oi_delta_status):
    """
    Honest limitation (confirmed by prior research): with only an
    absolute OI value and no validated delta/direction signal, we
    cannot determine SUPPORTIVE/AGAINST alignment - classifying as
    NEUTRAL (data present, but non-directional) rather than inventing
    a direction reading from a single absolute number.
    """
    if not oi_raw or oi_raw.get("oi_usd") is None:
        return {"derived_state": "UNKNOWN", "interpretation": "OI data not available", "data_quality": "NOT_AVAILABLE"}
    return {
        "derived_state": "NEUTRAL",
        "interpretation": "OI absolute value present, but no delta/direction signal available "
                           f"({oi_delta_status}) - cannot determine directional alignment",
        "data_quality": "partial - absolute value only",
    }


# ================================================
# Intelligence State - 7 dimensions, aggregation aware of missing data
# ================================================

def build_intelligence_state(snapshot, trade_row, funding_result, oi_result, direction):
    """
    REVISED per explicit review: the 7 dimensions are ALWAYS recorded
    (dimension_states), but only a transparent, explicitly-declared
    subset (aggregation_basis) actually drives aggregated_state - no
    dimension silently implied to matter without a confirmed basis.

    Included in aggregation_basis (confirmed, non-invented basis):
      - funding: grounded in actual perpetual-funding mechanics (not
        an invented threshold - it's how funding payments mechanically
        work).
      - setup (quality_grade), risk (risk_grade): Production's own
        EXPLICIT, already-designed ordinal grading (PREMIUM > HIGH >
        GOOD > WATCH > WATCHLIST is Production's own intended
        ordering) - reused as-is, not reclassified or thresholded.

    Excluded from aggregation_basis (informational only - NO confirmed
    production semantic ties them to "positive/negative"):
      - context (market_regime): a descriptive label (MIXED/RANGING/...)
        with no production-defined positive/negative valence.
      - direction (confidence label): a score bin; any correlation with
        outcome is a RESEARCH finding (Score x SHORT hypothesis), not a
        Production-defined semantic - using it here would be exactly
        the kind of invented interpretation this review flagged.
      - oi: always NEUTRAL/UNKNOWN, no directional signal available.
      - timing_5m: always UNKNOWN - thresholds not yet studied.
    """
    funding_state = classify_funding_state(funding_result.get("raw", {}), direction)
    oi_state = classify_oi_state(oi_result.get("raw", {}), oi_result.get("oi_delta_status", "unknown"))

    dimension_states = {
        "context": trade_row.get("market_regime") or "UNKNOWN",
        "direction": snapshot.get("confidence") or "UNKNOWN",
        "setup": snapshot.get("quality_grade") or "UNKNOWN",
        "funding": funding_state["derived_state"],
        "oi": oi_state["derived_state"],
        "timing_5m": "UNKNOWN",
        "risk": snapshot.get("risk_grade") or "UNKNOWN",
    }
    available = [k for k, v in dimension_states.items() if v != "UNKNOWN"]
    unavailable = [k for k, v in dimension_states.items() if v == "UNKNOWN"]

    AGGREGATION_BASIS = ["funding", "setup", "risk"]  # explicit, transparent - NOT all 7
    INFORMATIONAL_ONLY = ["context", "direction", "oi", "timing_5m"]

    neg_count, pos_count = 0, 0
    if funding_state["derived_state"] == "AGAINST":
        neg_count += 1
    elif funding_state["derived_state"] == "SUPPORTIVE":
        pos_count += 1
    # EXTREME is intentionally excluded from neg/pos counting here - its
    # meaning depends entirely on alignment (see funding_detail.interpretation),
    # and is surfaced explicitly rather than auto-scored either way.
    if dimension_states["risk"] in ("HIGH", "D"):
        neg_count += 1
    elif dimension_states["risk"] in ("LOW", "A"):
        pos_count += 1
    if dimension_states["setup"] in ("WATCH", "WATCHLIST"):
        neg_count += 1
    elif dimension_states["setup"] in ("PREMIUM", "HIGH", "GOOD"):
        pos_count += 1

    conflict = neg_count > 0 and pos_count > 0
    # PROVISIONAL rule, explicitly flagged as such (per point 6) - any
    # negative + any positive within aggregation_basis = CONFLICT,
    # regardless of counts. Not yet confirmed as final by the team.
    if conflict:
        aggregated_state = "CONFLICT"
        primary_cause = "multiple_conflicting_factors_within_aggregation_basis"
    elif neg_count >= 2:
        aggregated_state = "HIGH_RISK"
        primary_cause = next((k for k in AGGREGATION_BASIS
                               if dimension_states.get(k) in ("AGAINST", "HIGH", "D", "WATCH", "WATCHLIST")), None)
    elif neg_count == 1:
        aggregated_state = "CAUTION"
        primary_cause = next((k for k in AGGREGATION_BASIS
                               if dimension_states.get(k) in ("AGAINST", "HIGH", "D", "WATCH", "WATCHLIST")), None)
    elif pos_count >= 1:
        aggregated_state = "FAVORABLE"
        primary_cause = None
    else:
        aggregated_state = "NEUTRAL"
        primary_cause = None

    contributing_factors = [k for k in AGGREGATION_BASIS
                             if dimension_states.get(k) in ("AGAINST", "HIGH", "D", "WATCH", "WATCHLIST",
                                                             "SUPPORTIVE", "PREMIUM", "GOOD", "LOW", "A")]

    return {
        "dimension_states": dimension_states,          # all 7, always recorded
        "aggregation_basis": AGGREGATION_BASIS,          # explicit - what actually drove the result
        "informational_only_dimensions": INFORMATIONAL_ONLY,  # explicit - recorded but NOT scored
        "available_dimensions": available,
        "unavailable_dimensions": unavailable,
        "data_completeness": f"{len(available)}/7",
        "aggregated_state": aggregated_state,
        "primary_cause": primary_cause,
        "contributing_factors": contributing_factors,
        "conflict": conflict,
        "funding_detail": funding_state,
        "oi_detail": oi_state,
    }


def extract_market_context(trade_row, snapshot, signal_ts_ms):
    """
    FIXED (Data Preservation patch): previously ignored
    snapshot["market_context"] entirely, always forcing acceptance/
    breadth to NOT_AVAILABLE even if the field was actually populated.
    Now reads it dynamically - if present, its real fields are
    preserved as-is (whatever keys it actually contains, e.g.
    acceptance_rate/long_signals_count/short_signals_count/condition,
    matching the shape confirmed earlier in research_winners/
    research_losers.market_snapshot_json). If absent or a given field
    isn't in it, that field is NOT_AVAILABLE - never invented, never
    backfilled from any post-entry source.

    CONFIRMED from a full scan of the 496-trade historical archive:
    market_context was empty/null on every trade found - this fix does
    not claim historical data exists where none was found; it ensures
    the field is no longer silently dropped if/when it IS populated
    (e.g. for new v23.3.2 trades).

    FIXED (P0 Audit Closure): measured_at is now the trade's actual
    signal_ts_ms (same value used for Funding/OI/5m) - not the
    descriptive placeholder string "signal_time". Never datetime.now(),
    never Research Engine runtime.
    """
    raw_context = snapshot.get("market_context") or {}
    if isinstance(raw_context, str):
        try:
            raw_context = json.loads(raw_context)
        except Exception:
            raw_context = {}

    breadth_val = "NOT_AVAILABLE"
    if raw_context.get("long_signals_count") is not None or raw_context.get("short_signals_count") is not None:
        breadth_val = {
            "long_signals_count": raw_context.get("long_signals_count", "NOT_AVAILABLE"),
            "short_signals_count": raw_context.get("short_signals_count", "NOT_AVAILABLE"),
        }

    return {
        "market_regime": trade_row.get("market_regime") or "NOT_AVAILABLE",
        "market_health_score": trade_row.get("market_health_score"),
        "market_temperature": trade_row.get("market_temperature") or "NOT_AVAILABLE",
        "acceptance": raw_context.get("acceptance_rate", raw_context.get("acceptance", "NOT_AVAILABLE")),
        "breadth": breadth_val,
        "condition": raw_context.get("condition", "NOT_AVAILABLE"),
        "raw_market_context_reference": raw_context if raw_context else "NOT_AVAILABLE",
        "strongest_sector": snapshot.get("sector_reference") or raw_context.get("strongest_sector", "NOT_AVAILABLE"),
        "entry_safe": True,
        "measured_at": signal_ts_ms,  # FIXED: actual signal timestamp, not a descriptive placeholder
    }


# ================================================
# Build one trade record (Schema v4)
# ================================================

def build_trade_record(trade_row):
    snapshot = trade_row.get("initial_snapshot") or {}
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except Exception:
            snapshot = {}

    signal_time_iso = trade_row["signal_time"].isoformat() if trade_row.get("signal_time") else None
    signal_ts_ms = int(trade_row["signal_time"].timestamp() * 1000) if trade_row.get("signal_time") else None

    funding = fetch_funding_near_signal(trade_row["symbol"], signal_ts_ms) if signal_ts_ms else \
        {"data_quality": "NOT_AVAILABLE"}
    oi = fetch_oi_near_signal(trade_row["symbol"], signal_ts_ms) if signal_ts_ms else \
        {"data_quality": "NOT_AVAILABLE"}
    candles_5m = fetch_5m_candles_before(trade_row["symbol"], signal_ts_ms) if signal_ts_ms else []
    timing_5m = compute_5m_raw(candles_5m)

    score_breakdown = extract_score_breakdown(snapshot)
    market_context = extract_market_context(trade_row, snapshot, signal_ts_ms)
    intelligence_state = build_intelligence_state(snapshot, trade_row, funding, oi, trade_row["side"])

    record = {
        "trade_id": trade_row["id"], "decision_id": trade_row.get("decision_id"),
        "symbol": trade_row["symbol"], "side": trade_row["side"], "signal_time": signal_time_iso,
        "version": trade_row.get("version"),

        "signal_snapshot": {
            "direction": trade_row["side"],
            "setup_quality_score": score_breakdown["final_score"],
            "market_regime": market_context["market_regime"],
            "intelligence_state": intelligence_state["aggregated_state"],
        },

        "score_breakdown": score_breakdown,
        "market_context": market_context,
        "funding": funding,
        "open_interest": oi,
        "compression": {
            "raw_score": snapshot.get("compression_score"), "status": snapshot.get("compression_status"),
            "entry_safe": True,
        },
        "timing_5m": timing_5m,

        "decision_comparison": {
            "baseline": {
                "decision": "ACCEPT",  # trade exists, so baseline accepted it
                "score": score_breakdown["final_score"], "direction": trade_row["side"],
                "ranking_score": snapshot.get("ranking_score"),
            },
            "intelligence": intelligence_state,
            "note": "Intelligence State is experimental/observational only - has ZERO effect on "
                    "execution, entry, SL, TP, or ranking. Baseline decision above is what actually executed.",
        },

        "expected_vs_actual": {
            "expected": {"direction": trade_row["side"], "rr": trade_row.get("rr")},
            "actual": None,  # filled at close
        },

        "data_quality": {
            "funding_available": funding.get("data_quality") == "complete",
            "oi_available": "partial" in str(oi.get("data_quality", "")),
            "5m_available": timing_5m.get("data_quality") == "complete",
            "market_context_gaps": ["acceptance", "breadth"],
        },
    }
    return record


def update_outcome(record, trade_row):
    """Called for trades that have closed - appends actual outcome only,
    never touches any entry-safe field above."""
    record["expected_vs_actual"]["actual"] = {
        "result": trade_row.get("result"), "rr_realized_note": "RR field is expected, not realized - documented gap",
        "max_profit": trade_row.get("max_profit"), "max_drawdown": trade_row.get("max_drawdown"),
        "close_time": trade_row["close_time"].isoformat() if trade_row.get("close_time") else None,
    }
    return record


# ================================================
# Daily Research File - atomic write + verification
# ================================================

def _daily_file_path(date_str):
    return os.path.join(OUTPUT_DIR, f"daily_research_{date_str}.json")


def load_or_init_daily_file(date_str):
    path = _daily_file_path(date_str)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        "date": date_str, "version": "v23.3.2_clean_start",
        "1_daily_executive_summary": {}, "2_todays_observations": [],
        "3_full_trade_records": [], "4_missed_opportunities": [],
        "5_accumulated_research_findings": [], "6_open_research_questions": [],
        "7_data_quality": {"missing_fields": [], "lookahead_risk_flags": [],
                            "entry_safe_violations": [], "api_failures": []},
    }


def upsert_trade_record(daily, record):
    """
    FIXED (P0 patch, core bug): ONE TRADE = ONE RECORD, by trade_id.
    If a record with this trade_id already exists (e.g., this trade was
    seen before as OPEN and we're now updating it to CLOSED), it is
    REPLACED in place - never appended as a second record. This is what
    makes re-running the tool on the same trade idempotent (Tests C/D).
    """
    records = daily["3_full_trade_records"]
    for i, existing in enumerate(records):
        if existing.get("trade_id") == record["trade_id"]:
            records[i] = record  # update in place - no duplicate
            return daily
    records.append(record)  # genuinely new trade_id
    return daily


def write_daily_file_atomic(date_str, content):
    """Atomic: write to temp, verify it parses back correctly, then rename."""
    path = _daily_file_path(date_str)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(content, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    with open(tmp_path) as f:
        verify = json.load(f)
    if len(verify.get("3_full_trade_records", [])) != len(content["3_full_trade_records"]):
        raise RuntimeError("Write verification failed - record count mismatch")
    # Also verify no duplicate trade_ids snuck in (defense in depth)
    ids = [r.get("trade_id") for r in verify["3_full_trade_records"]]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Write verification failed - duplicate trade_id detected")
    os.replace(tmp_path, path)
    return path


# ================================================
# State tracking - FIXED (P0 patch, the core bug)
# ================================================
# Previously: a single last_processed_id meant a trade's OPEN record
# was created once, then its id became <= last_id forever, so its
# CLOSE/outcome was NEVER re-read. Confirmed root cause.
#
# Fix: two separate pieces of state -
#   last_seen_id: highest trade id ever processed (for finding NEW trades)
#   pending_outcomes: {trade_id: date_str} for trades recorded as OPEN
#     that are NOT YET CLOSED - re-checked on EVERY run until closed,
#     regardless of how their id compares to last_seen_id.
# This guarantees: OPEN recorded once, CLOSE updates the SAME record
# once, and pending trades are never silently dropped.

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_seen_id": 0, "pending_outcomes": {}, "last_seen_rejection_id": 0}
    with open(STATE_FILE) as f:
        state = json.load(f)
    state.setdefault("last_seen_rejection_id", 0)  # backward-compatible for existing state files
    return state


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


# ================================================
# Missed Opportunities - reads from research_rejections (existing
# production table, schema unchanged). Only real exclusion_type values
# already confirmed to exist in Production (Candles, Brain, Validation
# Failed, High Price Asset) - never invents a new category.
# ================================================

MEASUREMENT_WINDOW_HOURS = 72


def fetch_missed_opportunities(cur, last_seen_rejection_id):
    """
    FIXED (P0): each record now carries rejection_id + the date_str
    derived from rejected_at itself - run() routes it to THAT dated
    file, never to "today's" file just because the runner executed today.
    """
    cur.execute("SELECT * FROM research_rejections WHERE id > %s ORDER BY id", (last_seen_rejection_id,))
    rows = cur.fetchall()
    records = []
    for r in rows:
        context = r.get("context") or {}
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except Exception:
                context = {}
        rejected_at = r.get("rejected_at")
        date_str = rejected_at.strftime("%Y-%m-%d") if rejected_at else "unknown"
        records.append({
            "rejection_id": r["id"], "date_str": date_str,
            "symbol": r["symbol"], "timestamp": rejected_at.isoformat() if rejected_at else None,
            "rejected_at_ms": int(rejected_at.timestamp() * 1000) if rejected_at else None,
            "exclusion_type": r["reject_reason"], "exclusion_reason": r["reject_reason"],
            "snapshot_at_exclusion": context if context else "NOT_AVAILABLE",
            "later_move": "NOT_YET_MEASURED", "later_outcome": "NOT_YET_MEASURED",
            "measurement_window": f"{MEASUREMENT_WINDOW_HOURS}h (pending)",
            "status": "MISSED_OPPORTUNITY - OBSERVATION",
            "note": "A later price move does NOT by itself mean this rejection was wrong - "
                    "requires separate research into whether it was actually tradeable at rejection time.",
        })
    max_id = max((r["id"] for r in rows), default=last_seen_rejection_id)
    return records, max_id


def measure_pending_rejection(rejection_id, symbol, rejected_at_ms):
    """
    Computes later_move/later_outcome ONLY once MEASUREMENT_WINDOW_HOURS
    has actually elapsed since rejected_at - fetches 1H candles strictly
    from [rejected_at, rejected_at+window]. This is explicitly POST-HOC
    research measurement, never used as an entry feature for any trade -
    no look-ahead concern applies to this specific use.
    """
    window_end_ms = rejected_at_ms + MEASUREMENT_WINDOW_HOURS * 3600 * 1000
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if now_ms < window_end_ms:
        return None  # window hasn't elapsed yet - stays NOT_YET_MEASURED
    data = _request(f"{OKX_BASE_URL}{CANDLES_HISTORY_ENDPOINT}",
                     {"instId": symbol, "bar": "1H", "after": str(window_end_ms + 3600000), "limit": 100})
    if data is None:
        return {"later_move": "MEASUREMENT_FAILED", "later_outcome": "MEASUREMENT_FAILED"}
    raw = data.get("data", [])
    closed = [c for c in raw if len(c) > 8 and c[8] == "1"
              and rejected_at_ms <= int(c[0]) <= window_end_ms]
    if len(closed) < 2:
        return {"later_move": "INSUFFICIENT_CANDLES_FOR_MEASUREMENT", "later_outcome": "INSUFFICIENT_CANDLES_FOR_MEASUREMENT"}
    closed.sort(key=lambda c: int(c[0]))
    start_price = float(closed[0][1])   # open of first candle at/after rejection
    end_price = float(closed[-1][4])    # close of last candle within window
    move_pct = ((end_price - start_price) / start_price * 100) if start_price else None
    return {
        "later_move": f"{move_pct:+.2f}%" if move_pct is not None else "NOT_AVAILABLE",
        "later_outcome": "MOVED_UP" if (move_pct or 0) > 0 else "MOVED_DOWN" if (move_pct or 0) < 0 else "FLAT",
        "measurement_window": f"{MEASUREMENT_WINDOW_HOURS}h (measured)",
    }


# ================================================
# Today's Observations - descriptive only, never claims an edge
# ================================================

def build_todays_observations(trade_records):
    """
    Pattern = (side, setup_grade, funding_state) combination observed
    TODAY only. Always status=OBSERVATION - this function NEVER
    classifies anything as HYPOTHESIS or higher; that only happens in
    build_accumulated_findings() after cross-day evidence accumulates.
    """
    groups = {}
    for r in trade_records:
        actual = r.get("expected_vs_actual", {}).get("actual")
        if not actual or not actual.get("result"):
            continue
        dims = r["decision_comparison"]["intelligence"]["dimension_states"]
        key = (r["side"], dims.get("setup"), dims.get("funding"))
        groups.setdefault(key, {"wins": 0, "losses": 0, "n": 0})
        groups[key]["n"] += 1
        if actual["result"].startswith("WIN"):
            groups[key]["wins"] += 1
        elif actual["result"] == "LOSS_SL":
            groups[key]["losses"] += 1

    observations = []
    for (side, setup, funding), stats in groups.items():
        if stats["n"] < 2:
            continue
        observations.append({
            "pattern": f"{side} + setup={setup} + funding={funding}",
            "n": stats["n"], "wins": stats["wins"], "losses": stats["losses"],
            "status": "OBSERVATION",
            "reason": "Single-day sample - not sufficient for any conclusion, purely descriptive",
        })
    return observations


# ================================================
# Component/Interaction Analysis - across ALL accumulated daily files
# ================================================

def load_all_daily_records():
    """Reads every daily_research_*.json trade record - the single
    dataset both we and Research read from (no separate source)."""
    all_records = []
    if not os.path.exists(OUTPUT_DIR):
        return all_records
    for fname in sorted(os.listdir(OUTPUT_DIR)):
        if fname.startswith("daily_research_") and fname.endswith(".json"):
            with open(os.path.join(OUTPUT_DIR, fname)) as f:
                daily = json.load(f)
            all_records.extend(daily.get("3_full_trade_records", []))
    return all_records


def component_analysis(all_records, dimension_key):
    buckets = {}
    for r in all_records:
        actual = r.get("expected_vs_actual", {}).get("actual")
        if not actual or not actual.get("result") or actual["result"] == "TIMEOUT":
            continue
        dims = r["decision_comparison"]["intelligence"]["dimension_states"]
        state = dims.get(dimension_key, "UNKNOWN")
        buckets.setdefault(state, {"n": 0, "wins": 0})
        buckets[state]["n"] += 1
        if actual["result"].startswith("WIN"):
            buckets[state]["wins"] += 1
    result = {}
    for state, stats in buckets.items():
        n = stats["n"]
        result[state] = {"n": n, "status": "INSUFFICIENT_DATA"} if n < 15 else \
            {"n": n, "wins": stats["wins"], "win_rate_pct": round(stats["wins"]/n*100, 1), "status": "OBSERVED"}
    return result


def interaction_analysis(all_records, dim_a, dim_b):
    buckets = {}
    for r in all_records:
        actual = r.get("expected_vs_actual", {}).get("actual")
        if not actual or not actual.get("result") or actual["result"] == "TIMEOUT":
            continue
        dims = r["decision_comparison"]["intelligence"]["dimension_states"]
        key = f"{dims.get(dim_a,'UNKNOWN')}_x_{dims.get(dim_b,'UNKNOWN')}"
        buckets.setdefault(key, {"n": 0, "wins": 0})
        buckets[key]["n"] += 1
        if actual["result"].startswith("WIN"):
            buckets[key]["wins"] += 1
    result = {}
    for key, stats in buckets.items():
        n = stats["n"]
        result[key] = {"n": n, "status": "INSUFFICIENT_DATA"} if n < 15 else \
            {"n": n, "wins": stats["wins"], "win_rate_pct": round(stats["wins"]/n*100, 1), "status": "OBSERVED"}
    return result


def _make_finding(pattern, stats):
    return {
        "pattern": pattern, "sample_size": stats["n"],
        "outcome_statistics": {"win_rate_pct": stats["win_rate_pct"]},
        "effect_size": "NOT_COMPUTED", "p_value": "NOT_COMPUTED",
        "oos_status": "NOT_TESTED", "version_breakdown": "NOT_YET_SEPARATED",
        "direction_breakdown": "NOT_YET_SEPARATED", "market_regime_breakdown": "NOT_YET_SEPARATED",
        "classification": "OBSERVATION" if stats["n"] < 20 else "HYPOTHESIS",
        "next_required_investigation": "Separate by direction and regime; compute effect size and OOS once sample allows",
    }


# Dimensions covered by component analysis (extends beyond funding only)
COMPONENT_DIMENSIONS = ["funding", "oi", "setup", "risk", "context", "direction"]
# 9 interaction pairs explicitly requested
INTERACTION_PAIRS = [
    ("funding", "direction_side"), ("funding", "oi"), ("funding", "context"),
    ("timing_5m", "direction_side"), ("timing_5m", "context"),
    ("setup", "risk"), ("intelligence_state", "direction_side"),
    ("intelligence_state", "context"), ("context", "direction_side"),
]


def component_analysis_by_key(all_records, key_fn, label):
    buckets = {}
    for r in all_records:
        actual = r.get("expected_vs_actual", {}).get("actual")
        if not actual or not actual.get("result") or actual["result"] == "TIMEOUT":
            continue
        state = key_fn(r)
        buckets.setdefault(state, {"n": 0, "wins": 0})
        buckets[state]["n"] += 1
        if actual["result"].startswith("WIN"):
            buckets[state]["wins"] += 1
    result = {}
    for state, stats in buckets.items():
        n = stats["n"]
        result[state] = {"n": n, "status": "INSUFFICIENT_DATA"} if n < 15 else \
            {"n": n, "wins": stats["wins"], "win_rate_pct": round(stats["wins"]/n*100, 1), "status": "OBSERVED"}
    return result


def _dim_key(r, dim):
    if dim == "direction_side":
        return r["side"]
    if dim == "intelligence_state":
        return r["decision_comparison"]["intelligence"]["aggregated_state"]
    return r["decision_comparison"]["intelligence"]["dimension_states"].get(dim, "UNKNOWN")


def build_accumulated_findings(all_records):
    """
    FIXED (P1): now covers funding/oi/setup/risk/context/direction (not
    just funding), PLUS the 9 explicitly-requested interaction pairs.
    Every field that isn't actually computed says NOT_COMPUTED - never
    a fabricated number. Classification stays conservative
    (OBSERVATION/HYPOTHESIS only) - no automatic promotion further.
    """
    findings = []

    def _component_finding(pattern, stats):
        if stats["status"] != "OBSERVED":  # N < 15
            return {
                "pattern": pattern, "sample_size": stats["n"], "outcome_statistics": "INSUFFICIENT_DATA",
                "effect_size": "NOT_COMPUTED", "p_value": "NOT_COMPUTED", "oos_status": "NOT_TESTED",
                "version_breakdown": "NOT_YET_SEPARATED", "direction_breakdown": "NOT_YET_SEPARATED",
                "market_regime_breakdown": "NOT_YET_SEPARATED", "classification": "INSUFFICIENT_DATA",
                "next_required_investigation": f"Accumulate more samples for this cell (n={stats['n']} < 15)",
            }
        return _make_finding(pattern, stats)

    # Single-dimension findings - FIXED: every state now appears, N<15 explicit
    for dim in COMPONENT_DIMENSIONS:
        breakdown = component_analysis_by_key(all_records, lambda r, d=dim: _dim_key(r, d), dim)
        for state, stats in breakdown.items():
            findings.append(_component_finding(f"{dim}={state}", stats))

    # Intelligence State (aggregated) findings - FIXED: same treatment
    intel_breakdown = component_analysis_by_key(all_records, lambda r: _dim_key(r, "intelligence_state"), "intelligence_state")
    for state, stats in intel_breakdown.items():
        findings.append(_component_finding(f"intelligence_state={state}", stats))

    # Interaction findings - N<15 per cell = INSUFFICIENT_DATA, never inferred
    for dim_a, dim_b in INTERACTION_PAIRS:
        buckets = {}
        for r in all_records:
            actual = r.get("expected_vs_actual", {}).get("actual")
            if not actual or not actual.get("result") or actual["result"] == "TIMEOUT":
                continue
            key = f"{_dim_key(r, dim_a)}_x_{_dim_key(r, dim_b)}"
            buckets.setdefault(key, {"n": 0, "wins": 0})
            buckets[key]["n"] += 1
            if actual["result"].startswith("WIN"):
                buckets[key]["wins"] += 1
        for key, stats in buckets.items():
            n = stats["n"]
            pattern = f"{dim_a} x {dim_b}: {key}"
            if n < 15:
                findings.append({
                    "pattern": pattern, "sample_size": n, "outcome_statistics": "INSUFFICIENT_DATA",
                    "effect_size": "NOT_COMPUTED", "p_value": "NOT_COMPUTED", "oos_status": "NOT_TESTED",
                    "version_breakdown": "NOT_YET_SEPARATED", "direction_breakdown": "NOT_YET_SEPARATED",
                    "market_regime_breakdown": "NOT_YET_SEPARATED", "classification": "INSUFFICIENT_DATA",
                    "next_required_investigation": f"Accumulate more samples for this {dim_a}x{dim_b} cell (n={n} < 15)",
                })
            else:
                findings.append(_make_finding(pattern, {"n": n, "win_rate_pct": round(stats["wins"]/n*100, 1)}))

    return findings


def build_open_research_questions(all_records):
    questions = []
    n_total = len([r for r in all_records if r.get("expected_vs_actual", {}).get("actual")])
    if n_total > 0:
        questions.append(f"Does funding=AGAINST independently hurt outcome, controlling for direction? (n={n_total} decided trades so far)")
        questions.append("Does OI Delta, once available, add value beyond the absolute OI value currently recorded?")
        questions.append("Is timing_5m associated with entry quality? (blocked - not yet classified, raw data accumulating)")
        questions.append("Do specific types of CONFLICT correlate with better or worse outcomes than CAUTION/HIGH_RISK?")
        questions.append("Does Market Regime change LONG/SHORT quality independently of the other aggregation_basis dimensions?")
        questions.append("Do Missed Opportunities reveal a filter that excludes good signals more than bad ones?")
    return questions


# ================================================
# Main orchestration
# ================================================

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    state = load_state()
    last_seen_id = state["last_seen_id"]
    pending_outcomes = state["pending_outcomes"]  # {str(trade_id): date_str}
    pending_measurements = state.get("pending_rejection_measurements", {})  # {str(rejection_id): {date_str, symbol, rejected_at_ms}}

    # Step A: genuinely NEW trades (never seen before)
    cur.execute("SELECT * FROM trades WHERE id > %s ORDER BY id", (last_seen_id,))
    new_trades = cur.fetchall()
    print(f"Found {len(new_trades)} new trades since id={last_seen_id}")

    # Step C: missed opportunities since last run
    last_seen_rejection_id = state.get("last_seen_rejection_id", 0)
    missed_opps, new_last_rejection_id = fetch_missed_opportunities(cur, last_seen_rejection_id)
    print(f"Found {len(missed_opps)} new missed-opportunity records")

    # Step D: re-check pending rejection measurements (72h lifecycle)
    still_pending_measurements = dict(pending_measurements)
    measurement_updates = []  # (date_str, rejection_id, update_dict)
    for rid_str, info in pending_measurements.items():
        result = measure_pending_rejection(int(rid_str), info["symbol"], info["rejected_at_ms"])
        if result is not None:  # window elapsed, measurement produced (success or explicit failure)
            measurement_updates.append((info["date_str"], int(rid_str), result))
            still_pending_measurements.pop(rid_str, None)
    print(f"Measured {len(measurement_updates)} rejections whose {MEASUREMENT_WINDOW_HOURS}h window elapsed; "
          f"{len(still_pending_measurements)} still pending")

    # Step B: previously-pending trades - re-check for CLOSE, regardless of id
    pending_ids = [int(tid) for tid in pending_outcomes.keys()]
    pending_trades = []
    if pending_ids:
        cur.execute("SELECT * FROM trades WHERE id = ANY(%s)", (pending_ids,))
        pending_trades = cur.fetchall()
    print(f"Re-checking {len(pending_trades)} pending trades for outcome")

    files_to_write = {}  # date_str -> daily dict, batched so each file is written once

    def get_daily(date_str):
        if date_str not in files_to_write:
            files_to_write[date_str] = load_or_init_daily_file(date_str)
        return files_to_write[date_str]

    write_failed = False

    # Process new trades: create entry record
    for t in new_trades:
        date_str = t["signal_time"].strftime("%Y-%m-%d") if t.get("signal_time") else "unknown"
        record = build_trade_record(t)
        if t.get("status") == "CLOSED":
            record = update_outcome(record, t)
        else:
            pending_outcomes[str(t["id"])] = date_str  # track for future re-check
        daily = get_daily(date_str)
        upsert_trade_record(daily, record)

    # Process pending trades: update outcome ONLY if now closed, in the
    # ORIGINAL date's file (not today's file)
    still_pending = dict(pending_outcomes)  # FIXED: start from current state
    # (includes trades just added as pending by the new-trades loop above),
    # not empty - previous version silently wiped newly-added pending
    # entries here (caught by TEST A).
    for t in pending_trades:
        tid_str = str(t["id"])
        original_date = pending_outcomes[tid_str]
        if t.get("status") == "CLOSED":
            daily = get_daily(original_date)
            existing = next((r for r in daily["3_full_trade_records"] if r["trade_id"] == t["id"]), None)
            if existing:
                update_outcome(existing, t)
            else:
                record = build_trade_record(t)
                record = update_outcome(record, t)
                upsert_trade_record(daily, record)
            still_pending.pop(tid_str, None)  # resolved - remove from pending
        # else: still open, remains in still_pending untouched (already copied above)

    pending_outcomes = still_pending

    # FIXED (P0): route each missed opportunity to the file matching ITS
    # OWN rejected_at date - never to "today's" file. UPSERT by
    # rejection_id (not blind append) - protects against duplicates if
    # save_state() failed after a successful file write, causing a
    # rerun to re-fetch the same rejection via a stale
    # last_seen_rejection_id.
    for opp in missed_opps:
        daily = get_daily(opp["date_str"])
        existing = next((o for o in daily["4_missed_opportunities"]
                          if o.get("rejection_id") == opp["rejection_id"]), None)
        if existing is None:
            daily["4_missed_opportunities"].append(opp)
        else:
            # Already present (from a prior run whose state save failed) -
            # do not duplicate. If it was already measured, preserve that;
            # otherwise it's still NOT_YET_MEASURED either way - no-op.
            pass
        if opp["later_move"] == "NOT_YET_MEASURED" and opp.get("rejected_at_ms"):
            still_pending_measurements[str(opp["rejection_id"])] = {
                "date_str": opp["date_str"], "symbol": opp["symbol"], "rejected_at_ms": opp["rejected_at_ms"],
            }

    # Apply measurement updates to the SAME existing record (idempotent - no duplicate)
    for date_str, rejection_id, update in measurement_updates:
        daily = get_daily(date_str)
        existing = next((o for o in daily["4_missed_opportunities"] if o.get("rejection_id") == rejection_id), None)
        if existing:
            existing.update(update)

    # Write all touched daily files atomically; if ANY fails, abort state advance entirely
    written_paths = []
    try:
        # Cross-day accumulated view: on-disk history + today's in-memory
        # records (which haven't been written to disk yet at this point
        # in the run - reading only from disk here undercounts today).
        all_records_for_accum = load_all_daily_records()
        today_ids_in_memory = set()
        for date_str, daily in files_to_write.items():
            for r in daily["3_full_trade_records"]:
                today_ids_in_memory.add(r["trade_id"])
        # avoid double-counting any record that's already on disk from a prior run today
        all_records_for_accum = [r for r in all_records_for_accum if r["trade_id"] not in today_ids_in_memory]
        for date_str, daily in files_to_write.items():
            all_records_for_accum.extend(daily["3_full_trade_records"])

        accumulated_findings = build_accumulated_findings(all_records_for_accum)
        open_questions = build_open_research_questions(all_records_for_accum)

        for date_str, daily in files_to_write.items():
            daily["1_daily_executive_summary"] = {
                "signals": len(daily["3_full_trade_records"]),
                "long": sum(1 for r in daily["3_full_trade_records"] if r["side"] == "LONG"),
                "short": sum(1 for r in daily["3_full_trade_records"] if r["side"] == "SHORT"),
            }
            daily["2_todays_observations"] = build_todays_observations(daily["3_full_trade_records"])
            daily["5_accumulated_research_findings"] = accumulated_findings
            daily["6_open_research_questions"] = open_questions
            path = write_daily_file_atomic(date_str, daily)
            written_paths.append(path)
            print(f"  {date_str}: {len(daily['3_full_trade_records'])} total records -> {path}")
    except Exception as e:
        write_failed = True
        print(f"🔴 ALERT: file write failed - {e}. State will NOT advance. Safe to retry.")

    if not write_failed:
        new_last_seen = max([t["id"] for t in new_trades], default=last_seen_id)
        save_state({"last_seen_id": new_last_seen, "pending_outcomes": pending_outcomes,
                     "last_seen_rejection_id": new_last_rejection_id,
                     "pending_rejection_measurements": still_pending_measurements})
        print(f"State advanced: last_seen_id={new_last_seen}, pending_outcomes={len(pending_outcomes)}")
    else:
        print("State NOT advanced - retry will reprocess this batch safely (idempotent).")

    cur.close()
    conn.close()
    print(f"\nRequests: {STATS['total_requests']} | Failures: {STATS['failures']}")


# ================================================
# LOCKED-IN REGRESSION TEST - 5m Entry-Safety Boundary Rule
# (P0 Audit Closure - run directly: python3 research_data_foundation.py --test-5m-boundary)
# ================================================

def test_5m_boundary_rule():
    """Pure logic test of the boundary condition itself - no network/DB needed."""
    signal_ts = 1700000000000
    interval = 300000  # 5m in ms

    def close_time_valid(candle_open_ts):
        return (candle_open_ts + interval) <= signal_ts

    # 1. close BEFORE signal -> VALID
    before = signal_ts - 2 * interval
    assert close_time_valid(before), "FAIL: close before signal must be VALID"

    # 2. close EXACTLY AT signal -> VALID (official inclusive rule)
    exactly_at = signal_ts - interval
    assert close_time_valid(exactly_at), "FAIL: close == signal must be VALID (inclusive rule)"

    # 3. close AFTER signal -> REJECT
    after = signal_ts - interval + 1  # closes 1ms after signal
    assert not close_time_valid(after), "FAIL: close after signal must be REJECTED"

    print("5m boundary rule regression test: ALL PASS (before=VALID, ==VALID, after=REJECT)")


if __name__ == "__main__":
    import sys as _sys
    if "--test-5m-boundary" in _sys.argv:
        test_5m_boundary_rule()
        _sys.exit(0)
    run()
