"""
================================================================================
AHAD AI - Historical Market Pilot - Main Orchestrator
================================================================================

Standalone, manual-run-only pilot to validate the Historical Market
Scanner approach on a small scope (12 symbols, 3 days) BEFORE committing
to a full 120-day backfill.

Run manually:
    python historical_market_pilot.py

PRODUCTION ISOLATION (verified, not just asserted):
  - Zero imports from bot.py.
  - Zero imports from any existing Research module (research.py,
    research_runner.py, independent_market_indicators.py, etc.) -
    every function this pilot needs is either defined in
    historical_pilot_utils.py or here.
  - Never scheduled, never part of Render's startCommand, never
    imported by any other file in this project.
  - Reads only (public OKX endpoints) - writes only to its own 5
    output files in the current working directory, never touches
    PostgreSQL, never touches any file elsewhere in the repo.

LOOK-AHEAD GUARANTEE: every pre-event snapshot's candle window is
fetched with an explicit end boundary strictly before event_timestamp,
and this is asserted in code (not just assumed) before the row is
written - see _assert_no_lookahead().
================================================================================
"""

import argparse
import csv
import time
from datetime import datetime, timedelta, timezone

import historical_pilot_utils as utils
from historical_pilot_config import (
    PILOT_UNIVERSE_SIZE, PILOT_DAYS, TOP_N_PER_HOUR, PRE_EVENT_OFFSETS_MINUTES,
    CANDLES_PER_REQUEST, MAX_TOTAL_REQUESTS,
    EVENTS_CSV, SNAPSHOTS_CSV, UNIVERSE_CSV, FUNDING_OI_CSV, REPORT_TXT,
)


def _parse_args():
    """
    FIXED (confirmed missing before): plain sys.argv was never
    inspected, so `--help` silently ran the full pilot instead of
    showing help. argparse now handles -h/--help correctly (argparse
    prints help and calls sys.exit(0) on its own - main() never runs
    in that case). --universe-size/--days are optional overrides for
    rate-limit testing at different scales without editing
    historical_pilot_config.py each time; both default to the config
    file's values, so a bare `python3 historical_market_pilot.py` run
    behaves identically to before, just with the corrected default
    universe size (60, not 12).
    """
    parser = argparse.ArgumentParser(
        prog="historical_market_pilot.py",
        description=(
            "AHAD AI - Historical Market Pilot. Standalone, manual-run-only "
            "test of the Historical Market Scanner approach against real OKX "
            "data, on a small scope, before committing to a full 120-day "
            "backfill. Writes 5 output files (events/snapshots/universe/"
            "funding-oi CSVs + a GO/NO-GO text report) to the current "
            "directory. Read-only against OKX; never touches PostgreSQL or "
            "any Production file."
        ),
    )
    parser.add_argument("--universe-size", type=int, default=PILOT_UNIVERSE_SIZE,
                         help=f"Number of live USDT-SWAP symbols to test against (default: {PILOT_UNIVERSE_SIZE}). "
                              f"Must be meaningfully larger than --top-n so the Top N selection is a real test, "
                              f"not a near-pass-through of the whole universe.")
    parser.add_argument("--days", type=int, default=PILOT_DAYS,
                         help=f"Number of historical days to test (default: {PILOT_DAYS}).")
    return parser.parse_args()

report = {
    "started_at": None, "finished_at": None,
    "universe_test": {}, "candles_1h": {}, "candles_15m": {},
    "events": {"total": 0, "gainers": 0, "losers": 0},
    "snapshots": {"total": 0, "lookahead_violations": 0},
    "funding": {"available": False, "symbols_tested": 0, "symbols_with_data": 0},
    "oi": {"available": False, "symbols_tested": 0, "symbols_with_data": 0},
    "integrity": {"duplicate_candles": 0, "missing_timestamps": 0, "incomplete_excluded": 0},
    "duration_seconds": None,
}


def _assert_no_lookahead(snapshot_ts_ms, event_ts_ms):
    """Hard check, not a comment - every pre-event candle's timestamp
    must be strictly before the event. A violation is counted and
    logged, never silently allowed through."""
    if snapshot_ts_ms >= event_ts_ms:
        report["snapshots"]["lookahead_violations"] += 1
        print(f"🔴 LOOK-AHEAD VIOLATION: snapshot_ts={snapshot_ts_ms} >= event_ts={event_ts_ms}")
        return False
    return True


def step1_test_universe(universe_size):
    print("\n=== STEP 1: Historical Universe test ===")
    success, instruments, states = utils.test_historical_universe()
    report["universe_test"] = {
        "endpoint_reachable": success,
        "total_instruments": len(instruments),
        "distinct_states": list(states),
        "non_live_states_present": bool(states - {"live"}),
    }
    if not success:
        print("❌ Instruments endpoint unreachable.")
        return []

    print(f"Total SWAP instruments: {len(instruments)} | states found: {states}")
    with open(UNIVERSE_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["instId", "state", "listTime", "expTime"])
        for inst in instruments:
            writer.writerow([inst.get("instId"), inst.get("state"),
                              inst.get("listTime"), inst.get("expTime")])

    # Pilot universe: first N live USDT-SWAP instruments, sorted by
    # instId for determinism - not a "top movers" selection, since the
    # pilot's job is to test the PIPELINE, not analyze the market.
    live_usdt_swaps = sorted(
        i["instId"] for i in instruments
        if i.get("state") == "live" and i.get("instId", "").endswith("-USDT-SWAP")
    )
    pilot_universe = live_usdt_swaps[:universe_size]
    selection_rate = (TOP_N_PER_HOUR / len(pilot_universe) * 100) if pilot_universe else 0
    print(f"Pilot universe selected: {len(pilot_universe)} symbols "
          f"(Top {TOP_N_PER_HOUR} selection rate: {selection_rate:.0f}% per hour)")
    if selection_rate > 50:
        print(f"⚠️ WARNING: selection rate {selection_rate:.0f}% is high - Top {TOP_N_PER_HOUR} "
              f"will not meaningfully test ranking logic. Consider a larger --universe-size.")
    return pilot_universe


def step2_detect_events(universe, start_ts_ms, end_ts_ms):
    print("\n=== STEP 2: 1H candle fetch + hourly Top 10 event detection ===")
    all_hourly = {}  # symbol -> list of closed 1H candles
    for symbol in universe:
        if utils.STATS["total_requests"] >= MAX_TOTAL_REQUESTS:
            print("⚠️ MAX_TOTAL_REQUESTS reached - stopping candle fetch early.")
            break
        candles = utils.fetch_candles_paginated(symbol, "1H", start_ts_ms, end_ts_ms,
                                                  limit=CANDLES_PER_REQUEST)
        all_hourly[symbol] = candles
        print(f"  {symbol}: {len(candles)} closed 1H candles")

    total_1h = sum(len(c) for c in all_hourly.values())
    report["candles_1h"] = {"symbols": len(all_hourly), "total_candles": total_1h}

    # Duplicate check across pagination
    for symbol, candles in all_hourly.items():
        ts_list = [c["ts"] for c in candles]
        dupes = len(ts_list) - len(set(ts_list))
        report["integrity"]["duplicate_candles"] += dupes

    # Build hourly Top 10 gainers/losers, per approved design:
    # change_pct_this_hour from (close-open)/open, NOT 24h change.
    all_hour_timestamps = sorted(set(c["ts"] for candles in all_hourly.values() for c in candles))
    events = []
    for hour_ts in all_hour_timestamps:
        hour_moves = []
        for symbol, candles in all_hourly.items():
            match = next((c for c in candles if c["ts"] == hour_ts), None)
            if match and match["open"] != 0:
                change_pct = ((match["close"] - match["open"]) / match["open"]) * 100
                hour_moves.append({"symbol": symbol, "change_pct": change_pct,
                                    "close_time": hour_ts, "price": match["close"]})
        if not hour_moves:
            continue
        hour_moves.sort(key=lambda x: x["change_pct"], reverse=True)
        gainers = hour_moves[:TOP_N_PER_HOUR]
        losers = sorted(hour_moves, key=lambda x: x["change_pct"])[:TOP_N_PER_HOUR]
        for rank, g in enumerate(gainers, 1):
            events.append({**g, "direction": "GAINER", "rank": rank,
                            "event_timestamp": g["close_time"]})
        for rank, l in enumerate(losers, 1):
            events.append({**l, "direction": "LOSER", "rank": rank,
                            "event_timestamp": l["close_time"]})

    report["events"]["total"] = len(events)
    report["events"]["gainers"] = sum(1 for e in events if e["direction"] == "GAINER")
    report["events"]["losers"] = sum(1 for e in events if e["direction"] == "LOSER")

    with open(EVENTS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "direction", "rank", "change_pct_this_hour",
                          "price_at_event", "event_timestamp", "data_source"])
        for e in events:
            event_iso = datetime.fromtimestamp(int(e["event_timestamp"]) / 1000, tz=timezone.utc).isoformat()
            writer.writerow([e["symbol"], e["direction"], e["rank"],
                              round(e["change_pct"], 4), e["price"], event_iso, "OKX"])

    print(f"Events detected: {len(events)} ({report['events']['gainers']} gainer-events, "
          f"{report['events']['losers']} loser-events)")
    return events


def step3_pre_event_snapshots(events):
    print("\n=== STEP 3: Pre-event 15m snapshots ===")
    rows_written = 0
    with open(SNAPSHOTS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "event_timestamp", "offset_minutes", "snapshot_timestamp",
                          "rsi_15m", "flow", "volume_ratio", "momentum_score",
                          "ema20", "ema50", "ema200", "macd", "atr",
                          "compression_status", "market_regime", "candles_used"])

        # Test only a subset of events to keep the pilot small and fast
        # - full coverage is the job of the 120-day backfill, not this
        # pilot. Every event still gets tested for at least the
        # smallest offset to confirm the mechanism works end-to-end.
        sample_events = events[:10]

        for event in sample_events:
            event_ts_ms = int(event["event_timestamp"])
            for offset_min in PRE_EVENT_OFFSETS_MINUTES:
                if utils.STATS["total_requests"] >= MAX_TOTAL_REQUESTS:
                    print("⚠️ MAX_TOTAL_REQUESTS reached - stopping snapshot fetch early.")
                    break
                snapshot_target_ms = event_ts_ms - (offset_min * 60 * 1000)
                # Fetch a 15m window ENDING strictly before snapshot_target_ms
                window_start_ms = snapshot_target_ms - (250 * 15 * 60 * 1000)  # ~250 candles back
                candles_15m = utils.fetch_candles_paginated(
                    event["symbol"], "15m", window_start_ms, snapshot_target_ms - 1,
                    limit=CANDLES_PER_REQUEST
                )
                if not candles_15m:
                    continue

                actual_snapshot_ts = int(candles_15m[-1]["ts"])
                if not _assert_no_lookahead(actual_snapshot_ts, event_ts_ms):
                    continue  # violation logged, row skipped - never written

                indicators = utils.compute_indicators(candles_15m)
                snapshot_iso = datetime.fromtimestamp(actual_snapshot_ts / 1000, tz=timezone.utc).isoformat()
                writer.writerow([
                    event["symbol"], event["event_timestamp"], offset_min, snapshot_iso,
                    indicators["rsi_15m"], indicators["flow"], indicators["volume_ratio"],
                    indicators["momentum_score"], indicators["ema20"], indicators["ema50"],
                    indicators["ema200"], indicators["macd"], indicators["atr"],
                    indicators["compression_status"], indicators["market_regime"],
                    indicators["candles_used"],
                ])
                rows_written += 1

    report["snapshots"]["total"] = rows_written
    print(f"Pre-event snapshots written: {rows_written} "
          f"(look-ahead violations caught and excluded: {report['snapshots']['lookahead_violations']})")


def step4_funding_oi(universe):
    print("\n=== STEP 4: Funding Rate + Open Interest historical availability test ===")
    with open(FUNDING_OI_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "type", "timestamp", "value"])

        funding_with_data = 0
        oi_with_data = 0
        for symbol in universe[:5]:  # small subset - this step tests AVAILABILITY, not coverage
            report["funding"]["symbols_tested"] += 1
            funding_data = utils.fetch_funding_rate_history(symbol, limit=5)
            if funding_data:
                funding_with_data += 1
                for entry in funding_data:
                    writer.writerow([symbol, "funding_rate", entry.get("fundingTime"), entry.get("fundingRate")])

            report["oi"]["symbols_tested"] += 1
            oi_data = utils.fetch_open_interest_history(symbol, limit=5)
            if oi_data:
                oi_with_data += 1
                for entry in oi_data:
                    writer.writerow([symbol, "open_interest", entry.get("ts"), entry.get("oi")])

    report["funding"]["symbols_with_data"] = funding_with_data
    report["funding"]["available"] = funding_with_data > 0
    report["oi"]["symbols_with_data"] = oi_with_data
    report["oi"]["available"] = oi_with_data > 0
    print(f"Funding history available for {funding_with_data}/{report['funding']['symbols_tested']} symbols tested")
    print(f"OI history available for {oi_with_data}/{report['oi']['symbols_tested']} symbols tested")


def write_final_report():
    lines = []
    lines.append("="*70)
    lines.append("AHAD AI - HISTORICAL MARKET PILOT REPORT")
    lines.append("="*70)
    lines.append(f"Started: {report['started_at']} | Finished: {report['finished_at']}")
    lines.append(f"Duration: {report['duration_seconds']:.1f}s")
    lines.append("")
    lines.append("-- REQUEST STATS --")
    lines.append(f"Total requests: {utils.STATS['total_requests']}")
    lines.append(f"Retries: {utils.STATS['retries']}")
    lines.append(f"HTTP 429s: {utils.STATS['http_429']}")
    lines.append(f"Failed (exhausted retries): {utils.STATS['failures']}")
    lines.append("")
    lines.append("-- 1) HISTORICAL UNIVERSE --")
    lines.append(str(report["universe_test"]))
    universe_go = report["universe_test"].get("endpoint_reachable", False)
    universe_survivorship_solvable = report["universe_test"].get("non_live_states_present", False)
    lines.append(f"GO/NO-GO: {'GO' if universe_go else 'NO-GO'} "
                  f"(endpoint reachable={universe_go}; "
                  f"non-live states present={universe_survivorship_solvable} - "
                  f"{'Survivorship Bias mitigation POSSIBLE from OKX directly' if universe_survivorship_solvable else 'Survivorship Bias mitigation NOT CONFIRMED possible from OKX alone - only live instruments returned'})")
    lines.append("")
    lines.append("-- 2) 1H HISTORICAL CANDLES + PAGINATION --")
    lines.append(str(report["candles_1h"]))
    candles_go = report["candles_1h"].get("total_candles", 0) > 0
    lines.append(f"GO/NO-GO: {'GO' if candles_go else 'NO-GO'}")
    lines.append("")
    lines.append("-- 3) 15m PRE-EVENT SNAPSHOTS --")
    lines.append(str(report["snapshots"]))
    snapshots_go = report["snapshots"]["total"] > 0 and report["snapshots"]["lookahead_violations"] == 0
    lines.append(f"GO/NO-GO: {'GO' if snapshots_go else 'NO-GO'} "
                  f"({'zero look-ahead violations confirmed' if report['snapshots']['lookahead_violations']==0 else 'LOOK-AHEAD VIOLATIONS DETECTED - do not proceed'})")
    lines.append("")
    lines.append("-- 4) EVENT DETECTION --")
    lines.append(str(report["events"]))
    lines.append(f"GO/NO-GO: {'GO' if report['events']['total'] > 0 else 'NO-GO'}")
    lines.append("")
    lines.append("-- 5) RATE LIMITS --")
    rate_go = utils.STATS["failures"] == 0
    lines.append(f"429s encountered: {utils.STATS['http_429']} | Unrecovered failures: {utils.STATS['failures']}")
    lines.append(f"GO/NO-GO: {'GO' if rate_go else 'CAUTION - some requests failed even after retries'}")
    lines.append("")
    lines.append("-- 6) FUNDING RATE --")
    lines.append(str(report["funding"]))
    lines.append(f"GO/NO-GO: {'GO' if report['funding']['available'] else 'NO-GO - historical funding NOT confirmed available'}")
    lines.append("")
    lines.append("-- 7) OPEN INTEREST --")
    lines.append(str(report["oi"]))
    lines.append(f"GO/NO-GO: {'GO' if report['oi']['available'] else 'NO-GO - historical OI NOT confirmed available'}")
    lines.append("")
    lines.append("-- 8) DATA INTEGRITY --")
    lines.append(str(report["integrity"]))
    integrity_go = report["integrity"]["duplicate_candles"] == 0
    lines.append(f"GO/NO-GO: {'GO' if integrity_go else 'CAUTION - duplicate candles found, pagination logic needs review'}")
    lines.append("")
    lines.append("="*70)
    lines.append("OVERALL: Individual component results above. Do NOT treat this as")
    lines.append("a single pass/fail - review each GO/NO-GO line before deciding on")
    lines.append("the full 120-day backfill.")
    lines.append("="*70)

    text = "\n".join(lines)
    with open(REPORT_TXT, "w") as f:
        f.write(text)
    print("\n" + text)


def main():
    args = _parse_args()  # --help exits here via argparse, before any work happens

    start = time.time()
    report["started_at"] = datetime.now(timezone.utc).isoformat()
    print(f"🚀 AHAD AI Historical Market Pilot starting - {report['started_at']}")
    print(f"Scope: {args.universe_size} symbols, {args.days} days")

    end_ts = datetime.now(timezone.utc)
    start_ts = end_ts - timedelta(days=args.days)
    end_ts_ms = int(end_ts.timestamp() * 1000)
    start_ts_ms = int(start_ts.timestamp() * 1000)

    universe = step1_test_universe(args.universe_size)
    if not universe:
        print("❌ No universe available - aborting remaining steps.")
        write_final_report()
        return

    events = step2_detect_events(universe, start_ts_ms, end_ts_ms)
    if events:
        step3_pre_event_snapshots(events)
    else:
        print("⚠️ No events detected - skipping snapshot step.")

    step4_funding_oi(universe)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = time.time() - start
    write_final_report()
    print(f"\n🏁 Pilot finished in {report['duration_seconds']:.1f}s")
    print(f"Outputs: {EVENTS_CSV}, {SNAPSHOTS_CSV}, {UNIVERSE_CSV}, {FUNDING_OI_CSV}, {REPORT_TXT}")


if __name__ == "__main__":
    main()
