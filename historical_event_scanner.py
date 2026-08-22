"""
================================================================================
AHAD AI - Historical Event Scanner
================================================================================

Reconstructs Daily Top 10 Gainers/Losers historically (matching production's
EXACT rolling-24h definition, verified against top_gainers_study.py's own
fetch_daily_change()), then collects pre-event indicator features and raw
candles for each event - to study what preceded the move, not just list it.

PRODUCTION ISOLATION: imports ONLY already-tested low-level HTTP/pagination
functions from historical_pilot_utils.py (read-only reuse - that file is
never modified). Never imports bot.py. Never modifies historical_data_
downloader.py or historical_market_pilot.py. Writes only its own 5 output
files. No database of any kind.

EFFICIENCY DESIGN (matches the explicit no-waste requirement): for each
symbol, ONE 1H candle series covering (N days + 200-candle indicator
warm-up) is fetched ONCE - this single series is sliced locally to compute
ALL N days' rankings (no per-day re-fetch) AND to compute 1H indicators for
any symbol that becomes a Top10 event (no re-fetch for features either).
Only 15m candles and Funding/OI near-event lookups are fetched per unique
(symbol, event_timestamp) pair that actually became an event - never for
the full universe.

LOOK-AHEAD PROTECTION: every candle used for ranking or features has an
explicit, code-enforced check that its close timestamp is strictly before
event_timestamp - see _assert_no_lookahead(). A violation is logged and the
row is dropped, never silently included.

Run manually only:
    python3 historical_event_scanner.py --mode pilot
    python3 historical_event_scanner.py --mode full --days 30
================================================================================
"""

import argparse
import csv
import json
import os
import time
import zipfile
import requests
from datetime import datetime, timedelta, timezone

import historical_pilot_utils as utils  # read-only reuse - never modified

TELEGRAM_ZIP_NAME = "historical_event_scanner_30d.zip"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID")

OUTPUT_DIR = "historical_events"
EVENTS_CSV = os.path.join(OUTPUT_DIR, "events.csv")
FEATURES_CSV = os.path.join(OUTPUT_DIR, "pre_event_features.csv")
RAW_CANDLES_CSV = os.path.join(OUTPUT_DIR, "pre_event_raw_candles.csv")
MANIFEST_FILE = os.path.join(OUTPUT_DIR, "manifest.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.txt")

TOP_N = 10
CANDLES_PER_REQUEST = 100

# Indicator warm-up: matches independent_market_indicators.py's own
# established candle-count convention for this project (200 for 15m
# there; reused as the max requirement across ALL indicators here -
# ema200/market_regime need up to 200, the largest requirement, so 200
# covers every indicator's minimum with margin). This is NOT invented
# here - it's the same number already used throughout the project.
WARMUP_CANDLES = 200

report_stats = {
    "days_requested": 0, "days_completed": 0,
    "events_total": 0, "gainers": 0, "losers": 0, "unique_symbols_in_events": 0,
    "duplicate_events": 0, "duplicate_candles": 0, "missing_candles": 0,
    "incomplete_windows": 0, "lookahead_violations": 0,
    "api_failures": 0, "retries_start": 0, "http_429_start": 0,
    "funding_available": 0, "funding_unavailable": 0,
    "oi_available": 0, "oi_unavailable": 0,
    "survivorship_note": "Universe is LIVE USDT-SWAP as of scan time - "
                          "symbols delisted during the historical window "
                          "are NOT represented. This is a known limitation, "
                          "not a bug.",
}


def _interval_ms(bar):
    return 3600000 if bar == "1H" else 900000  # 1H or 15m


def _assert_no_lookahead(candle_ts_ms, event_ts_ms, context, bar="1H"):
    """
    FIXED (confirmed close-time bug): OKX's candle `ts` is the OPEN
    timestamp, not close. A candle's actual close (when its data
    becomes confirmed/available) is ts + interval. The single explicit
    rule applied everywhere: a candle is usable if its CLOSE time is
    AT OR BEFORE event_timestamp (<=, inclusive) - the candle closing
    exactly at the daily boundary is the natural last data point
    defining "the 24h leading up to the new day" and is allowed. A
    candle whose close is strictly AFTER event_timestamp is rejected.
    """
    candle_close_ms = candle_ts_ms + _interval_ms(bar)
    if candle_close_ms > event_ts_ms:
        report_stats["lookahead_violations"] += 1
        print(f"🔴 LOOK-AHEAD VIOLATION [{context}]: candle_close={candle_close_ms} > event_ts={event_ts_ms}")
        return False
    return True


def get_daily_utc_boundaries(num_days):
    """
    FIXED (confirmed alignment bug): boundaries are now fixed UTC
    midnights, independent of script run time. boundary[0] = most
    recent UTC midnight at or before now(); boundary[1] = 24h before
    that; etc. Returns a list of `num_days` boundaries in ms, most
    recent first.
    """
    now = datetime.now(timezone.utc)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return [int((today_midnight - timedelta(days=i)).timestamp() * 1000) for i in range(num_days)]


def fetch_usdt_swap_symbols():
    """Reused verbatim (logic, not import) from top_gainers_study.py's
    own fetch_usdt_swap_symbols() - same endpoint, same filter."""
    data = utils._request_with_retry(f"{utils.OKX_BASE_URL}{utils.INSTRUMENTS_ENDPOINT}", {"instType": "SWAP"})
    if data is None:
        return []
    result = []
    for x in data.get("data", []):
        inst_id = x.get("instId", "")
        if inst_id.endswith("-USDT-SWAP") and x.get("state") == "live":
            result.append(inst_id)
    return result


# ================================================
# Phase 1: ONE 1H series per symbol -> all daily rankings + 1H indicator warm-up
# ================================================

def fetch_full_1h_series(symbol, num_days, boundary_0_ms):
    """
    Fetches (num_days*24 + WARMUP_CANDLES) 1H candles ending at the
    most recent UTC daily boundary (boundary_0_ms) - FIXED: previously
    ended at datetime.now(), causing ranking windows to be misaligned
    with actual UTC midnights.
    """
    total_needed = num_days * 24 + WARMUP_CANDLES
    start_ts_ms = boundary_0_ms - total_needed * 3600 * 1000
    candles = utils.fetch_candles_paginated(symbol, "1H", start_ts_ms, boundary_0_ms,
                                             limit=CANDLES_PER_REQUEST,
                                             event_context=f"1H series {symbol}")
    return candles


def compute_daily_rankings(universe_series, num_days, boundaries):
    """
    FIXED: uses explicit UTC daily boundaries (not index-based slicing
    from series end). For each boundary B, the ranking window is the
    24 CLOSED 1H candles whose close time is <= B (per the stated
    look-ahead rule) - the most recent 24 such candles. event_timestamp
    = B itself (the actual UTC midnight), not a candle's open time.
    """
    all_events = []
    for boundary_ms in boundaries:
        day_moves = []
        for symbol, series in universe_series.items():
            eligible = [c for c in series if int(c["ts"]) + _interval_ms("1H") <= boundary_ms]
            eligible.sort(key=lambda c: int(c["ts"]))
            window = eligible[-24:]
            if len(window) < 24:
                report_stats["incomplete_windows"] += 1
                continue
            oldest_close = window[0]["close"]
            latest_close = window[-1]["close"]
            if oldest_close == 0:
                continue
            change_pct = (latest_close - oldest_close) / oldest_close * 100
            day_moves.append({"symbol": symbol, "change_pct": change_pct,
                               "price": latest_close, "event_timestamp": boundary_ms})

        if not day_moves:
            continue
        day_moves.sort(key=lambda x: x["change_pct"], reverse=True)
        gainers = day_moves[:TOP_N]
        losers = sorted(day_moves, key=lambda x: x["change_pct"])[:TOP_N]
        event_date = datetime.fromtimestamp(boundary_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        for rank, g in enumerate(gainers, 1):
            all_events.append({**g, "direction": "GAINER", "rank": rank, "event_date": event_date})
        for rank, l in enumerate(losers, 1):
            all_events.append({**l, "direction": "LOSER", "rank": rank, "event_date": event_date})
        report_stats["days_completed"] += 1

    return all_events


def slice_1h_window_ending_at(series, event_ts_ms):
    """
    Returns the trailing WARMUP_CANDLES-sized window from `series`
    ending at-or-before event_ts_ms (per the stated close-time rule).
    """
    before_event = [c for c in series if int(c["ts"]) + _interval_ms("1H") <= event_ts_ms]
    trimmed = before_event[-WARMUP_CANDLES:] if len(before_event) >= WARMUP_CANDLES else before_event
    valid = [c for c in trimmed if _assert_no_lookahead(int(c["ts"]), event_ts_ms, "1h_slice", bar="1H")]
    return valid


# ================================================
# Phase 2: 15m candles + Funding/OI - ONLY for unique (symbol, event_timestamp) pairs
# ================================================

def fetch_15m_window_for_event(symbol, event_ts_ms):
    """One chunked fetch of (96 + WARMUP_CANDLES) 15m candles, filtered
    to close time <= event_ts_ms per the stated rule."""
    start_ts_ms = event_ts_ms - (96 + WARMUP_CANDLES) * 15 * 60 * 1000
    candles = utils.fetch_candles_paginated(symbol, "15m", start_ts_ms, event_ts_ms,
                                             limit=CANDLES_PER_REQUEST,
                                             event_context=f"15m {symbol}@{event_ts_ms}")
    valid = [c for c in candles if _assert_no_lookahead(int(c["ts"]), event_ts_ms, "15m_fetch", bar="15m")]
    return valid


def fetch_funding_near_event(symbol, event_ts_ms):
    """
    Nearest funding rate AT OR BEFORE event_ts_ms.

    FIXED (confirmed root cause from live diagnose-funding-oi test):
    `before=event_ts_ms` returned data with before_respected=false -
    the parameter was not producing historical (pre-event) data. Per
    an official OKX R package (okxr) documenting general v5 pagination
    convention, `after`="cursor for newer records" and `before`=
    "cursor for earlier records" - the OPPOSITE of the convention this
    project's own candles code uses (verified working live). Rather
    than trust either convention blindly for THIS endpoint, this
    function tries BOTH `before` and `after`, and explicitly verifies
    the returned timestamp against `<= event_ts_ms` before accepting -
    HTTP 200 alone is never treated as success. Returns
    (rate, timestamp, status, direction_used) - status/direction are
    logged so the working direction is known with certainty, not
    assumed, once tested live.
    """
    for direction in ("after", "before"):
        data = utils._request_with_retry(
            f"{utils.OKX_BASE_URL}{utils.FUNDING_RATE_HISTORY_ENDPOINT}",
            {"instId": symbol, "limit": 10, direction: str(event_ts_ms)}
        )
        if data is None:
            continue
        entries = data.get("data", [])
        valid_entries = [e for e in entries if isinstance(e, dict) and e.get("fundingTime")
                          and int(e["fundingTime"]) <= event_ts_ms]
        if valid_entries:
            nearest = max(valid_entries, key=lambda e: int(e["fundingTime"]))
            return nearest.get("fundingRate"), nearest.get("fundingTime"), f"ok_via_{direction}", direction
    return None, None, "no_valid_historical_data_either_direction", None


def fetch_oi_near_event(symbol, event_ts_ms):
    """
    Nearest OI AT OR BEFORE event_ts_ms.

    FIXED (confirmed root cause): the official okx-sdk PyPI package
    documents this exact call as get_open_interest_history(instId,
    period, begin, end, limit) - NO before/after parameters at all.
    Sending `before` was silently ignored by the endpoint (explaining
    before_respected=false), returning the latest window regardless.
    Now uses `begin`/`end` as an explicit time range ending at
    event_ts_ms, and still explicitly verifies the returned timestamp
    against `<= event_ts_ms` - never trusts HTTP 200 alone. Returns
    (oi_value, timestamp, status).
    """
    window_start_ms = event_ts_ms - (30 * 24 * 3600 * 1000)  # 30 days back, generous lookback
    data = utils._request_with_retry(
        f"{utils.OKX_BASE_URL}{utils.OPEN_INTEREST_HISTORY_ENDPOINT}",
        {"instId": symbol, "period": "1H", "limit": 100,
         "begin": str(window_start_ms), "end": str(event_ts_ms)}
    )
    if data is None:
        return None, None, "request_failed"
    entries = data.get("data", [])
    valid_entries = [e for e in entries if isinstance(e, (list, tuple)) and len(e) >= 2
                      and int(e[0]) <= event_ts_ms]
    if not valid_entries:
        return None, None, "no_valid_historical_data_with_begin_end"
    nearest = max(valid_entries, key=lambda e: int(e[0]))
    return nearest[1], nearest[0], "ok_via_begin_end"


def compute_features_for_event(event, series_1h, symbol_15m_cache):
    """Computes all indicators for one event using its 1H warm-up slice
    (from the already-fetched full series - zero extra requests) and a
    freshly-fetched 15m window (cached per unique symbol+event pair)."""
    symbol = event["symbol"]
    event_ts_ms = event["event_timestamp"]

    window_1h = slice_1h_window_ending_at(series_1h, event_ts_ms)
    cache_key = (symbol, event_ts_ms)
    if cache_key not in symbol_15m_cache:
        symbol_15m_cache[cache_key] = fetch_15m_window_for_event(symbol, event_ts_ms)
    window_15m = symbol_15m_cache[cache_key]

    ind_1h = utils.compute_indicators(window_1h) if window_1h else {}
    ind_15m = utils.compute_indicators(window_15m) if window_15m else {}

    funding_val, funding_ts, funding_status, funding_direction = fetch_funding_near_event(symbol, event_ts_ms)
    if funding_val is not None and funding_ts is not None and int(funding_ts) > event_ts_ms:
        report_stats["lookahead_violations"] += 1
        print(f"🔴 LOOK-AHEAD VIOLATION [funding]: ts={funding_ts} > event_ts={event_ts_ms}")
        funding_val, funding_ts = None, None
    if funding_val is not None:
        report_stats["funding_available"] += 1
    else:
        report_stats["funding_unavailable"] += 1

    oi_val, oi_ts, oi_status = fetch_oi_near_event(symbol, event_ts_ms)
    if oi_val is not None and oi_ts is not None and int(oi_ts) > event_ts_ms:
        report_stats["lookahead_violations"] += 1
        print(f"🔴 LOOK-AHEAD VIOLATION [oi]: ts={oi_ts} > event_ts={event_ts_ms}")
        oi_val, oi_ts = None, None
    if oi_val is not None:
        report_stats["oi_available"] += 1
    else:
        report_stats["oi_unavailable"] += 1

    return {
        "event_date": event["event_date"], "symbol": symbol, "direction": event["direction"],
        "rank": event["rank"], "event_timestamp": event_ts_ms,
        "rsi_15m": ind_15m.get("rsi_15m"), "rsi_1h": ind_1h.get("rsi_15m"),  # compute_indicators names it rsi_15m generically
        "ema20_15m": ind_15m.get("ema20"), "ema50_15m": ind_15m.get("ema50"), "ema200_15m": ind_15m.get("ema200"),
        "ema20_1h": ind_1h.get("ema20"), "ema50_1h": ind_1h.get("ema50"), "ema200_1h": ind_1h.get("ema200"),
        "macd_15m": ind_15m.get("macd"), "macd_1h": ind_1h.get("macd"),
        "atr_15m": ind_15m.get("atr"), "atr_1h": ind_1h.get("atr"),
        "flow": ind_15m.get("flow"), "volume_ratio": ind_15m.get("volume_ratio"),
        "momentum_score": ind_15m.get("momentum_score"),
        "compression_status": ind_15m.get("compression_status"), "market_regime": ind_15m.get("market_regime"),
        "funding_rate_near_event": funding_val, "funding_timestamp": funding_ts, "funding_status": funding_status,
        "open_interest_near_event": oi_val, "open_interest_timestamp": oi_ts, "oi_status": oi_status,
    }, window_15m


# ================================================
# Main orchestration
# ================================================

def _ceil_div(a, b):
    return -(-a // b)


def compute_phase1_budget(universe_size, num_days):
    """Exact expected request count for Phase 1: universe_size symbols,
    each needing ceil((num_days*24 + WARMUP_CANDLES) / 100) pages."""
    candles_per_symbol = num_days * 24 + WARMUP_CANDLES
    pages_per_symbol = _ceil_div(candles_per_symbol, CANDLES_PER_REQUEST)
    return universe_size * pages_per_symbol


def compute_phase2_budget(unique_event_count):
    """
    Exact expected request count for Phase 2: per unique event,
    ceil((96+WARMUP_CANDLES)/100) pages for 15m + up to 2 funding
    attempts (after, then before fallback - matches
    fetch_funding_near_event's actual dual-direction logic exactly,
    not a single-attempt assumption) + 1 OI lookup (begin/end, single
    attempt).
    """
    candles_15m_needed = 96 + WARMUP_CANDLES
    pages_15m = _ceil_div(candles_15m_needed, CANDLES_PER_REQUEST)
    return unique_event_count * (pages_15m + 2 + 1)


def diagnose_funding_oi_pagination(symbol, event_ts_ms):
    """
    Isolated diagnostic reflecting the FIXED logic: funding tries both
    `after` and `before` and reports which (if any) actually returns
    data with timestamp <= event_ts_ms; OI uses `begin`/`end` (the
    officially documented parameters per okx-sdk PyPI). Never accepts
    HTTP 200 as proof of success - explicitly checks the returned
    timestamp against the event boundary.
    """
    results = {}

    funding_attempts = {}
    for direction in ("after", "before"):
        url = f"{utils.OKX_BASE_URL}{utils.FUNDING_RATE_HISTORY_ENDPOINT}"
        params = {"instId": symbol, "limit": 10, direction: str(event_ts_ms)}
        try:
            resp = utils.requests.get(url, params=params, timeout=15)
            body = resp.json()
            data = body.get("data", [])
            timestamps = [int(e.get("fundingTime")) for e in data if isinstance(e, dict) and e.get("fundingTime")]
            respected = all(ts <= event_ts_ms for ts in timestamps) if timestamps else None
            funding_attempts[direction] = {
                "http_status": resp.status_code, "okx_code": body.get("code"), "row_count": len(data),
                "timestamps": timestamps, "before_value_sent": event_ts_ms, "respected": respected,
            }
        except Exception as e:
            funding_attempts[direction] = {"error": f"{type(e).__name__}: {e}"}
    results["funding"] = funding_attempts

    window_start_ms = event_ts_ms - (30 * 24 * 3600 * 1000)
    url = f"{utils.OKX_BASE_URL}{utils.OPEN_INTEREST_HISTORY_ENDPOINT}"
    params = {"instId": symbol, "period": "1H", "limit": 100, "begin": str(window_start_ms), "end": str(event_ts_ms)}
    try:
        resp = utils.requests.get(url, params=params, timeout=15)
        body = resp.json()
        data = body.get("data", [])
        timestamps = [int(e[0]) for e in data if isinstance(e, (list, tuple)) and len(e) >= 1]
        respected = all(ts <= event_ts_ms for ts in timestamps) if timestamps else None
        results["open_interest"] = {
            "http_status": resp.status_code, "okx_code": body.get("code"), "row_count": len(data),
            "timestamps": timestamps, "begin_sent": window_start_ms, "end_sent": event_ts_ms, "respected": respected,
        }
    except Exception as e:
        results["open_interest"] = {"error": f"{type(e).__name__}: {e}"}

    return results


def run_scan(num_days, universe_override=None, max_total_budget=None):
    report_stats["days_requested"] = num_days
    report_stats["retries_start"] = utils.STATS["retries"]
    report_stats["http_429_start"] = utils.STATS["http_429"]
    start_time = time.time()

    universe = universe_override if universe_override else fetch_usdt_swap_symbols()
    print(f"Universe size: {len(universe)}")

    boundaries = get_daily_utc_boundaries(num_days)
    boundary_0_ms = boundaries[0]

    # ---- PRE-FLIGHT BUDGET (Phase 1 known exactly; Phase 2 is an
    # upper-bound estimate here since exact unique-event count isn't
    # known until Phase 1 runs - TOP_N*2 directions*num_days is the
    # worst case with zero symbol reuse across days) ----
    phase1_budget = compute_phase1_budget(len(universe), num_days)
    phase2_worst_case = compute_phase2_budget(TOP_N * 2 * num_days)
    estimated_total = phase1_budget + phase2_worst_case

    print("\n" + "="*70)
    print("PRE-FLIGHT REQUEST BUDGET")
    print("="*70)
    print(f"Phase 1 (1H ranking series, {len(universe)} symbols x {num_days}d+{WARMUP_CANDLES} warmup): "
          f"{phase1_budget} requests (EXACT)")
    print(f"Phase 2 (15m + funding + OI, worst case up to {TOP_N*2*num_days} unique events): "
          f"{phase2_worst_case} requests (UPPER BOUND ESTIMATE)")
    print(f"ESTIMATED TOTAL: {estimated_total} requests")

    if max_total_budget is not None and estimated_total > max_total_budget:
        print(f"\n❌ ABORTING BEFORE ANY REQUEST: estimated total ({estimated_total}) exceeds "
              f"--max-total-budget ({max_total_budget}). Increase the budget explicitly and "
              f"re-run, or reduce universe/days. No partial run, no silent truncation.")
        return None

    # ---- PHASE 1: hard-capped at ITS OWN budget + 5% margin, so it
    # can NEVER consume Phase 2's allocation. If Phase 1 itself hits
    # this cap, that means the universe needed more than computed -
    # abort cleanly rather than continue with a silently incomplete
    # Phase 1 into Phase 2. ----
    phase1_cap = int(phase1_budget * 1.05) + 10
    utils.MAX_TOTAL_REQUESTS_GLOBAL[0] = phase1_cap
    utils.STATS["total_requests"] = 0
    print(f"\n=== PHASE 1: fetching one 1H series per symbol (budget cap: {phase1_cap} requests) ===")
    print(f"UTC daily boundaries (most recent first): {[datetime.fromtimestamp(b/1000, tz=timezone.utc).isoformat() for b in boundaries]}")
    universe_series = {}
    for symbol in universe:
        series = fetch_full_1h_series(symbol, num_days, boundary_0_ms)
        universe_series[symbol] = series
        print(f"  {symbol}: {len(series)} closed 1H candles fetched")

    phase1_actual = utils.STATS["total_requests"]
    if phase1_actual >= phase1_cap:
        print(f"\n❌ ABORTING: Phase 1 hit its own budget cap ({phase1_cap} requests) before "
              f"completing the full universe - some symbols' 1H series are incomplete. "
              f"This means the universe is larger than the pre-flight estimate accounted for. "
              f"NOT proceeding to Phase 2 with incomplete Phase 1 data.")
        return None
    print(f"Phase 1 actual usage: {phase1_actual}/{phase1_cap} requests - within budget, proceeding.")

    print("\n=== PHASE 1b: computing daily rankings locally (zero extra requests) ===")
    events = compute_daily_rankings(universe_series, num_days, boundaries)
    report_stats["events_total"] = len(events)
    report_stats["gainers"] = sum(1 for e in events if e["direction"] == "GAINER")
    report_stats["losers"] = sum(1 for e in events if e["direction"] == "LOSER")
    report_stats["unique_symbols_in_events"] = len({e["symbol"] for e in events})

    unique_pairs = len({(e["symbol"], e["event_timestamp"]) for e in events})
    phase2_exact_budget = compute_phase2_budget(unique_pairs)
    phase2_cap = phase1_actual + int(phase2_exact_budget * 1.05) + 10
    utils.MAX_TOTAL_REQUESTS_GLOBAL[0] = phase2_cap
    print(f"\n=== PHASE 2: fetching 15m + funding/OI for each event (deduplicated) ===")
    print(f"Unique (symbol, event_timestamp) pairs needing 15m/funding/OI: {unique_pairs}")
    print(f"Phase 2 EXACT budget: {phase2_exact_budget} requests | "
          f"new global cap: {phase2_cap} (= Phase 1 usage {phase1_actual} + Phase 2 budget + 5% margin)")
    symbol_15m_cache = {}
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(EVENTS_CSV, "w", newline="") as f_events, \
         open(FEATURES_CSV, "w", newline="") as f_features, \
         open(RAW_CANDLES_CSV, "w", newline="") as f_raw:

        events_writer = csv.writer(f_events)
        events_writer.writerow(["event_date", "symbol", "direction", "rank",
                                 "change_pct_24h", "price", "event_timestamp"])
        features_writer = csv.writer(f_features)
        features_writer.writerow(["event_date", "symbol", "direction", "rank", "event_timestamp",
                                   "rsi_15m", "rsi_1h", "ema20_15m", "ema50_15m", "ema200_15m",
                                   "ema20_1h", "ema50_1h", "ema200_1h", "macd_15m", "macd_1h",
                                   "atr_15m", "atr_1h", "flow", "volume_ratio", "momentum_score",
                                   "compression_status", "market_regime",
                                   "funding_rate_near_event", "funding_timestamp",
                                   "open_interest_near_event", "open_interest_timestamp"])
        raw_writer = csv.writer(f_raw)
        raw_writer.writerow(["event_date", "symbol", "direction", "rank", "event_timestamp",
                              "timeframe", "candle_timestamp", "open", "high", "low", "close", "volume"])

        seen_event_keys = set()
        for event in events:
            key = (event["symbol"], event["event_timestamp"], event["direction"], event["rank"])
            if key in seen_event_keys:
                report_stats["duplicate_events"] += 1
                continue
            seen_event_keys.add(key)

            events_writer.writerow([event["event_date"], event["symbol"], event["direction"],
                                     event["rank"], round(event["change_pct"], 4), event["price"],
                                     event["event_timestamp"]])
            f_events.flush(); os.fsync(f_events.fileno())

            features, window_15m = compute_features_for_event(event, universe_series[event["symbol"]], symbol_15m_cache)
            features_writer.writerow([features[k] for k in [
                "event_date", "symbol", "direction", "rank", "event_timestamp",
                "rsi_15m", "rsi_1h", "ema20_15m", "ema50_15m", "ema200_15m",
                "ema20_1h", "ema50_1h", "ema200_1h", "macd_15m", "macd_1h",
                "atr_15m", "atr_1h", "flow", "volume_ratio", "momentum_score",
                "compression_status", "market_regime",
                "funding_rate_near_event", "funding_timestamp",
                "open_interest_near_event", "open_interest_timestamp"]])
            f_features.flush(); os.fsync(f_features.fileno())

            window_1h_saved = slice_1h_window_ending_at(universe_series[event["symbol"]], event["event_timestamp"])[-24:]
            for c in window_1h_saved:
                raw_writer.writerow([event["event_date"], event["symbol"], event["direction"], event["rank"],
                                      event["event_timestamp"], "1H", c["ts"], c["open"], c["high"],
                                      c["low"], c["close"], c["volume"]])
            for c in window_15m[-96:]:
                raw_writer.writerow([event["event_date"], event["symbol"], event["direction"], event["rank"],
                                      event["event_timestamp"], "15m", c["ts"], c["open"], c["high"],
                                      c["low"], c["close"], c["volume"]])
            f_raw.flush(); os.fsync(f_raw.fileno())

            print(f"  Event {event['event_date']} {event['symbol']} {event['direction']}#{event['rank']} - features + raw saved")

    if utils.STATS["total_requests"] >= phase2_cap:
        print(f"\nℹ️ Phase 2 request count reached its budget estimate ({phase2_cap}) - "
              f"this is informational only. Actual data completeness (funding_available/"
              f"oi_available/incomplete_windows below) is the real signal, not this count.")

    # FIXED (confirmed root cause: budget-estimate overshoot was being
    # misreported as a failure even when all data was actually
    # complete - 20/20 funding, 20/20 OI, 0 incomplete_windows in the
    # reported run). api_failures is now derived from ACTUAL data
    # completeness, never from request-count-vs-estimate alone.
    if report_stats["funding_unavailable"] > 0 or report_stats["oi_unavailable"] > 0 or \
       report_stats["incomplete_windows"] > 0 or report_stats["missing_candles"] > 0:
        report_stats["api_failures"] += 1
        print(f"⚠️ Real data gaps detected: funding_unavailable={report_stats['funding_unavailable']}, "
              f"oi_unavailable={report_stats['oi_unavailable']}, "
              f"incomplete_windows={report_stats['incomplete_windows']}, "
              f"missing_candles={report_stats['missing_candles']} - recorded in api_failures.")

    duration = time.time() - start_time
    _write_manifest_and_report(duration)
    return events


def _write_manifest_and_report(duration):
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration,
        "total_api_requests": utils.STATS["total_requests"],
        "total_retries": utils.STATS["retries"] - report_stats["retries_start"],
        "total_429s": utils.STATS["http_429"] - report_stats["http_429_start"],
        "total_failures": utils.STATS["failures"],
        "warmup_candles_used": WARMUP_CANDLES,
        "warmup_explanation": (
            f"{WARMUP_CANDLES} candles fetched BEFORE the 24h pre-event window on both "
            "1H and 15m, purely for indicator warm-up (EMA200/market_regime need up to "
            "200 candles to compute correctly) - these warm-up candles are used ONLY "
            "for indicator math, never written to pre_event_raw_candles.csv, which "
            "contains only the actual 24h pre-event window (24x1H + 96x15m)."
        ),
        **report_stats,
    }
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    lines = ["="*70, "HISTORICAL EVENT SCANNER - REPORT", "="*70]
    for k, v in manifest.items():
        lines.append(f"{k}: {v}")
    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(lines))
    print("\n" + "\n".join(lines))


def create_results_zip():
    """Zips the 5 output files into one archive at OUTPUT_DIR level.
    Returns the zip path, or None if any required file is missing."""
    zip_path = os.path.join(OUTPUT_DIR, TELEGRAM_ZIP_NAME)
    required_files = [EVENTS_CSV, FEATURES_CSV, RAW_CANDLES_CSV, MANIFEST_FILE, REPORT_FILE]
    missing = [f for f in required_files if not os.path.exists(f)]
    if missing:
        print(f"❌ Cannot create ZIP - missing files: {missing}")
        return None
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in required_files:
            zf.write(f, arcname=os.path.basename(f))
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"📦 ZIP created: {zip_path} ({size_mb:.2f} MB)")
    return zip_path


def send_zip_to_telegram(zip_path):
    """
    Sends the ZIP via Telegram's sendDocument, using the EXACT same
    env vars and chat_id pattern already proven working in daily_
    report.py's own send_to_telegram() (ADMIN_USER_ID used directly
    as chat_id) - no telebot import, no bot.py dependency. Returns
    (success: bool, detail: str) - never silently swallows a failure.
    """
    if not BOT_TOKEN or not ADMIN_USER_ID:
        detail = "BOT_TOKEN or ADMIN_USER_ID not set in environment - cannot send."
        print(f"❌ Telegram send failed: {detail}")
        return False, detail

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(zip_path, "rb") as f:
            response = requests.post(
                url,
                data={"chat_id": ADMIN_USER_ID,
                      "caption": f"📦 Historical Event Scanner results\n{os.path.basename(zip_path)}"},
                files={"document": (os.path.basename(zip_path), f)},
                timeout=60,
            )
        if response.status_code == 200 and response.json().get("ok"):
            print(f"✅ Telegram upload SUCCESS: {zip_path} sent to chat {ADMIN_USER_ID}")
            return True, "ok"
        else:
            detail = f"HTTP {response.status_code} - {response.text[:500]}"
            print(f"❌ Telegram upload FAILED: {detail}")
            return False, detail
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        print(f"❌ Telegram upload EXCEPTION: {detail}")
        return False, detail


def main():
    parser = argparse.ArgumentParser(description="AHAD AI Historical Event Scanner")
    parser.add_argument("--mode", choices=["pilot", "full", "test-telegram", "diagnose-funding-oi"], default="pilot")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--pilot-symbols", type=int, default=5)
    parser.add_argument("--pilot-days", type=int, default=3)
    parser.add_argument("--max-total-budget", type=int, default=50000,
                         help="Explicit hard ceiling on total requests for the whole run (not "
                              "'unlimited' - default 50000). If the pre-flight estimate exceeds "
                              "this, the run aborts before making any request.")
    parser.add_argument("--diagnose-symbol", default="BTC-USDT-SWAP")
    parser.add_argument("--diagnose-days-ago", type=int, default=15,
                         help="How many days back the test event_timestamp should be (default 15 - "
                              "a genuinely historical point, not 'now').")
    args = parser.parse_args()

    if args.mode == "diagnose-funding-oi":
        boundaries = get_daily_utc_boundaries(args.diagnose_days_ago + 1)
        event_ts_ms = boundaries[-1]
        print(f"Diagnosing {args.diagnose_symbol} @ event_timestamp={event_ts_ms} "
              f"({datetime.fromtimestamp(event_ts_ms/1000, tz=timezone.utc).isoformat()})")
        results = diagnose_funding_oi_pagination(args.diagnose_symbol, event_ts_ms)
        print(json.dumps(results, indent=2, default=str))
        return

    if args.mode == "test-telegram":
        universe = fetch_usdt_swap_symbols()[:1]
        print(f"TEST-TELEGRAM MODE: {len(universe)} symbol, 1 day - proving ZIP + Telegram delivery only")
        result = run_scan(1, universe_override=universe, max_total_budget=args.max_total_budget)
    elif args.mode == "pilot":
        universe = fetch_usdt_swap_symbols()[:args.pilot_symbols]
        print(f"PILOT MODE: {len(universe)} symbols, {args.pilot_days} days")
        result = run_scan(args.pilot_days, universe_override=universe, max_total_budget=args.max_total_budget)
    else:
        result = run_scan(args.days, max_total_budget=args.max_total_budget)

    if result is None:
        print("\n⚠️ Run aborted before completion (see message above) - no ZIP created, nothing sent.")
        return

    zip_path = create_results_zip()
    if zip_path:
        success, detail = send_zip_to_telegram(zip_path)
        if not success:
            print(f"\n⚠️ ZIP was created successfully at {zip_path} but Telegram delivery FAILED: {detail}")
            print("The ZIP file still exists locally - you can retrieve it another way if needed.")
    else:
        print("⚠️ ZIP creation failed - nothing sent to Telegram.")


if __name__ == "__main__":
    main()
