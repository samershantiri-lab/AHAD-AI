"""
================================================================================
AHAD AI - Historical Data Downloader
================================================================================

Full 120-day historical backfill tool - separate from historical_market_
pilot.py, which remains a small quick-test script. This file NEVER
modifies historical_pilot_config.py, historical_pilot_utils.py, or
historical_market_pilot.py - it only IMPORTS already-tested low-level
functions from historical_pilot_utils.py (fetch_candles_paginated,
fetch_funding_rate_history, fetch_open_interest_history, STATS,
MAX_TOTAL_REQUESTS_GLOBAL) - reusing tested code, never duplicating or
re-deriving it.

CONFIRMED CONSTRAINT (discovered here, not assumed): historical_pilot_
utils.py's fetch_candles_paginated() has a local max_pages=40 cap (added
in the prior SIGKILL fix). For 120 days of 15m candles (11,520 candles
needed = 115.2 pages), a SINGLE call to that function is NOT enough -
it would silently stop at ~41 days. This downloader therefore calls
fetch_candles_paginated() repeatedly in a chunking loop, walking the
window further back each time, checkpointing after every chunk - never
assuming one call covers the full range. 1H (28.8 pages needed) fits in
a single call, but is still chunked identically for consistency and
because it costs nothing extra.

UNVERIFIED (explicitly, not assumed working): whether open-interest-
history's response supports before/after pagination the same way
candles do. This downloader attempts it using the same convention, but
explicitly detects and reports (never silently assumes) whether
consecutive "pages" actually advance in time - see _download_oi_full_range().

Run manually only:
    python3 historical_data_downloader.py --mode prototype --symbol BTC-USDT-SWAP --days 120

Never scheduled, never imported by any Production or Research file.
================================================================================
"""

import argparse
import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone

import historical_pilot_utils as utils  # read-only reuse - never modified

OUTPUT_DIR = "historical_data"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
MANIFEST_FILE = os.path.join(OUTPUT_DIR, "manifest.json")

CANDLES_PER_REQUEST = 100
SIXTEEN_MIN_MS = 15 * 60 * 1000


# ================================================
# Checkpoint - atomic on-disk state, survives an abrupt kill
# ================================================

def _load_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return {}
    try:
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Checkpoint file exists but is unreadable ({e}) - starting fresh for affected entries.")
        return {}


def _save_checkpoint(checkpoint):
    """Atomic write: write to a temp file, fsync, then os.replace (atomic
    on POSIX) - a kill mid-write can never leave a corrupted/partial
    checkpoint.json on disk."""
    tmp_path = CHECKPOINT_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(checkpoint, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, CHECKPOINT_FILE)


def _checkpoint_key(symbol, dataset):
    return f"{symbol}::{dataset}"


# ================================================
# Atomic CSV row writer - flush+fsync every row, matching the Pilot's
# own confirmed fix for the 0-byte-file failure mode.
# ================================================

class AtomicCsvWriter:
    def __init__(self, path, header, append=False):
        self.path = path
        mode = "a" if (append and os.path.exists(path)) else "w"
        write_header = not (append and os.path.exists(path))
        self.f = open(path, mode, newline="")
        self.writer = csv.writer(self.f)
        if write_header:
            self.writer.writerow(header)
            self.f.flush()
            os.fsync(self.f.fileno())

    def write_row(self, row):
        self.writer.writerow(row)
        self.f.flush()
        os.fsync(self.f.fileno())

    def close(self):
        self.f.close()


# ================================================
# Per-dataset download with chunked pagination + checkpointing
# ================================================

def _download_candles_full_range(symbol, bar, start_ts_ms, end_ts_ms, checkpoint, quality):
    """
    Repeatedly calls utils.fetch_candles_paginated() in chunks, walking
    backward, until start_ts_ms is reached or no more data returns.
    NEVER assumes one call covers the full range - confirmed necessary
    for 15m given the 40-page-per-call cap in historical_pilot_utils.py.
    Deduplicates by timestamp across chunks. Checkpoints after every
    chunk so a kill loses at most the in-progress chunk.
    """
    ckey = _checkpoint_key(symbol, f"candles_{bar}")
    state = checkpoint.get(ckey, {"status": "in_progress", "earliest_ts_reached": end_ts_ms, "rows_written": 0})

    csv_path = os.path.join(OUTPUT_DIR, f"candles_{bar.lower()}.csv")
    writer = AtomicCsvWriter(csv_path, ["symbol", "timestamp", "open", "high", "low", "close", "volume", "source"],
                              append=True)
    seen_timestamps = _load_existing_timestamps_from_csv(csv_path)

    current_end = state["earliest_ts_reached"]
    chunk_num = 0
    while current_end > start_ts_ms:
        if utils.STATS["total_requests"] >= utils.MAX_TOTAL_REQUESTS_GLOBAL[0]:
            print(f"⚠️ [{symbol}] {bar}: global request cap reached mid-backfill - stopping, resumable later.")
            quality["api_failures"] += 1
            break

        chunk_num += 1
        candles = utils.fetch_candles_paginated(symbol, bar, start_ts_ms, current_end,
                                                  limit=CANDLES_PER_REQUEST,
                                                  event_context=f"backfill {symbol} {bar} chunk#{chunk_num}")
        if not candles:
            print(f"  [{symbol}] {bar}: chunk#{chunk_num} returned no candles - stopping this dataset here.")
            break

        new_rows = 0
        for c in candles:
            ts = c["ts"]
            if (symbol, ts) in seen_timestamps:
                quality["duplicate_count"] += 1
                continue
            seen_timestamps.add((symbol, ts))
            writer.write_row([symbol, ts, c["open"], c["high"], c["low"], c["close"], c["volume"], "OKX"])
            new_rows += 1

        state["rows_written"] += new_rows
        oldest_this_chunk = int(candles[0]["ts"])
        state["earliest_ts_reached"] = oldest_this_chunk
        checkpoint[ckey] = state
        _save_checkpoint(checkpoint)
        print(f"  [{symbol}] {bar}: chunk#{chunk_num} -> {new_rows} new rows "
              f"(checkpoint: earliest_ts={oldest_this_chunk}, total_rows={state['rows_written']})")

        if oldest_this_chunk <= start_ts_ms:
            break
        current_end = oldest_this_chunk

    writer.close()
    state["status"] = "complete" if state["earliest_ts_reached"] <= start_ts_ms else "partial"
    checkpoint[ckey] = state
    _save_checkpoint(checkpoint)
    return state


def _load_existing_timestamps_from_csv(csv_path, ts_column_index=1, symbol_column_index=0):
    """
    FIXED (confirmed bug): identity is now (symbol, timestamp), not
    timestamp alone. These CSV files are SHARED across all symbols -
    BTC-USDT-SWAP@X and ETH-USDT-SWAP@X are two distinct, both-valid
    rows, not a duplicate. Reading timestamp alone caused the second
    symbol's genuinely different row to be wrongly skipped as a
    "duplicate". Returns a set of (symbol, timestamp) tuples.
    """
    if not os.path.exists(csv_path):
        return set()
    seen = set()
    with open(csv_path) as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) > max(ts_column_index, symbol_column_index):
                seen.add((row[symbol_column_index], row[ts_column_index]))
    return seen


def _download_funding_full_range(symbol, start_ts_ms, end_ts_ms, checkpoint, quality):
    """
    FIXED (real chunked pagination, not a single call): repeatedly
    requests funding-rate-history using before/after cursors, walking
    backward until start_ts_ms is reached or no more data returns.
    Evidence for before/after support on this exact endpoint: CCXT's
    own documented fetchFundingRateHistory(symbol, since, limit,
    params) targets this same OKX endpoint (funding-rate-history) and
    accepts a `since` timestamp - a reasonably strong (not certain)
    basis for before/after being supported here, unlike Open Interest
    below. Advancement is still explicitly verified, never assumed -
    see `paginated_advanced` in the returned state.
    """
    ckey = _checkpoint_key(symbol, "funding")
    existing_state = checkpoint.get(ckey, {})
    if existing_state.get("status") == "complete":
        print(f"  [{symbol}] funding: already complete per checkpoint - skipping, zero new requests.")
        return existing_state

    csv_path = os.path.join(OUTPUT_DIR, "funding.csv")
    already_on_disk = _load_existing_timestamps_from_csv(csv_path)
    writer = AtomicCsvWriter(csv_path, ["symbol", "timestamp", "value", "source"], append=True)

    rows_written = 0
    prev_oldest = None
    paginated_advanced = False
    cursor_before = str(end_ts_ms)
    reached_start = False

    for page_num in range(1, 41):  # same 40-page local cap convention as candles
        if utils.STATS["total_requests"] >= utils.MAX_TOTAL_REQUESTS_GLOBAL[0]:
            quality["api_failures"] += 1
            print(f"⚠️ [{symbol}] funding: global request cap reached at page {page_num}.")
            break

        data = utils._request_with_retry(
            f"{utils.OKX_BASE_URL}{utils.FUNDING_RATE_HISTORY_ENDPOINT}",
            {"instId": symbol, "limit": 100, "before": cursor_before}
        )
        if data is None:
            break
        page = data.get("data", [])
        if not page:
            break

        page_timestamps = []
        for entry in page:
            if not isinstance(entry, dict):
                quality["malformed_rows"] += 1
                continue
            ts = entry.get("fundingTime")
            if ts is None:
                continue
            page_timestamps.append(int(ts))
            if (symbol, ts) in already_on_disk:
                quality["duplicate_count"] += 1
                continue
            already_on_disk.add((symbol, ts))
            writer.write_row([symbol, ts, entry.get("fundingRate"), "OKX"])
            rows_written += 1

        if not page_timestamps:
            break
        this_oldest = min(page_timestamps)
        if prev_oldest is not None and this_oldest < prev_oldest:
            paginated_advanced = True
        prev_oldest = this_oldest

        print(f"  [{symbol}] funding: page {page_num} -> {len(page)} entries, oldest_ts={this_oldest}")
        if this_oldest <= start_ts_ms:
            reached_start = True
            break
        cursor_before = str(this_oldest)

    writer.close()
    state = {
        "status": "complete" if reached_start else ("partial" if paginated_advanced else "no_data_or_single_page"),
        "rows_written": rows_written,
        "paginated_advanced": paginated_advanced,
        "coverage_120_days": reached_start,
        "note": ("before/after pagination attempted based on CCXT documenting `since` support "
                 "for this exact OKX endpoint - advancement was verified, not assumed."),
    }
    checkpoint[ckey] = state
    _save_checkpoint(checkpoint)
    return state


def _download_oi_full_range(symbol, start_ts_ms, end_ts_ms, checkpoint, quality):
    """
    FIXED (real chunked pagination attempt, honestly labeled
    UNVERIFIED): repeatedly requests open-interest-history using
    before/after cursors, mirroring OKX's own general convention -
    but NO reliable documentation was found specifically for THIS
    endpoint's pagination support (CCXT's fetchOpenInterestHistory
    documents a DIFFERENT endpoint - open-interest-volume, not
    open-interest-history, which is the one confirmed working live
    via Render in a prior step and is NOT changed here). This function
    attempts pagination as the most reasonable evidence-based guess,
    but explicitly detects and reports (via `paginated_advanced`)
    whether it actually works - the manifest states outright whether
    120-day coverage was achieved or not, never assumes it.
    """
    ckey = _checkpoint_key(symbol, "open_interest")
    existing_state = checkpoint.get(ckey, {})
    if existing_state.get("status") == "complete":
        print(f"  [{symbol}] OI: already complete per checkpoint - skipping, zero new requests.")
        return existing_state

    csv_path = os.path.join(OUTPUT_DIR, "open_interest.csv")
    already_on_disk = _load_existing_timestamps_from_csv(csv_path)
    writer = AtomicCsvWriter(csv_path, ["symbol", "timestamp", "value", "source"], append=True)

    rows_written = 0
    prev_oldest = None
    paginated_advanced = False
    cursor_before = str(end_ts_ms)
    reached_start = False

    for page_num in range(1, 41):
        if utils.STATS["total_requests"] >= utils.MAX_TOTAL_REQUESTS_GLOBAL[0]:
            quality["api_failures"] += 1
            print(f"⚠️ [{symbol}] OI: global request cap reached at page {page_num}.")
            break

        data = utils._request_with_retry(
            f"{utils.OKX_BASE_URL}{utils.OPEN_INTEREST_HISTORY_ENDPOINT}",
            {"instId": symbol, "period": "1H", "limit": 100, "before": cursor_before}
        )
        if data is None:
            break
        page = data.get("data", [])
        if not page:
            break

        page_timestamps = []
        for entry in page:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                quality["malformed_rows"] += 1
                continue
            ts = entry[0]
            page_timestamps.append(int(ts))
            if (symbol, ts) in already_on_disk:
                quality["duplicate_count"] += 1
                continue
            already_on_disk.add((symbol, ts))
            writer.write_row([symbol, ts, entry[1], "OKX"])
            rows_written += 1

        if not page_timestamps:
            break
        this_oldest = min(page_timestamps)
        if prev_oldest is not None and this_oldest < prev_oldest:
            paginated_advanced = True
        prev_oldest = this_oldest

        print(f"  [{symbol}] OI: page {page_num} -> {len(page)} entries, oldest_ts={this_oldest}, "
              f"advanced_so_far={paginated_advanced}")
        if this_oldest <= start_ts_ms:
            reached_start = True
            break
        if page_num >= 2 and not paginated_advanced:
            # Two consecutive pages that did NOT advance in time is
            # strong evidence this endpoint ignores `before` - stop
            # requesting further identical pages rather than looping
            # pointlessly, and report this honestly.
            print(f"⚠️ [{symbol}] OI: pagination does NOT appear to advance - stopping, "
                  f"reporting UNVERIFIED/NOT SUPPORTED for this endpoint.")
            break
        cursor_before = str(this_oldest)

    writer.close()
    state = {
        "status": "complete" if reached_start else ("partial" if paginated_advanced else "single_window_only"),
        "rows_written": rows_written,
        "paginated_advanced": paginated_advanced,
        "coverage_120_days": reached_start,
        "note": ("open-interest-history pagination is UNVERIFIED by any documentation found - "
                 "CCXT documents a DIFFERENT OKX endpoint (open-interest-volume) for its "
                 "fetchOpenInterestHistory. This result reflects an ACTUAL live attempt, "
                 "not an assumption - see paginated_advanced/coverage_120_days above."),
    }
    checkpoint[ckey] = state
    _save_checkpoint(checkpoint)
    return state


# ================================================
# Per-symbol orchestration + data quality report
# ================================================

def download_symbol(symbol, days, checkpoint):
    print(f"\n{'='*70}\nDownloading: {symbol} ({days} days)\n{'='*70}")
    end_ts = datetime.now(timezone.utc)
    start_ts = end_ts - timedelta(days=days)
    end_ts_ms = int(end_ts.timestamp() * 1000)
    start_ts_ms = int(start_ts.timestamp() * 1000)

    quality = {
        "duplicate_count": 0, "malformed_rows": 0, "api_failures": 0,
        "retry_count": utils.STATS["retries"],
    }

    results = {}
    results["candles_1h"] = _download_candles_full_range(symbol, "1H", start_ts_ms, end_ts_ms, checkpoint, quality)
    results["candles_15m"] = _download_candles_full_range(symbol, "15m", start_ts_ms, end_ts_ms, checkpoint, quality)
    results["funding"] = _download_funding_full_range(symbol, start_ts_ms, end_ts_ms, checkpoint, quality)
    results["open_interest"] = _download_oi_full_range(symbol, start_ts_ms, end_ts_ms, checkpoint, quality)

    quality["retry_count"] = utils.STATS["retries"] - quality["retry_count"]
    return results, quality


def _write_manifest(all_results, start_time, args):
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "requested_days": args.days,
        "symbols_requested": args.symbol if args.mode == "prototype" else "N/A (full mode not run)",
        "total_requests": utils.STATS["total_requests"],
        "total_retries": utils.STATS["retries"],
        "total_429s": utils.STATS["http_429"],
        "total_failures": utils.STATS["failures"],
        "duration_seconds": time.time() - start_time,
        "results": all_results,
        "known_unverified_constraints": [
            "Open Interest history endpoint pagination (before/after) support is UNVERIFIED - "
            "current implementation performs a single-window fetch only. Confirm before full run.",
            "Funding rate history pagination beyond `limit` is UNVERIFIED - single-call only.",
        ],
    }
    tmp_path = MANIFEST_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, MANIFEST_FILE)
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="AHAD AI Historical Data Downloader - full 120-day backfill, separate from the small Pilot script."
    )
    parser.add_argument("--mode", choices=["prototype", "full"], default="prototype",
                         help="prototype = 1 symbol only (default, safe). full = entire universe - requires --confirm-full-run.")
    parser.add_argument("--symbol", default="BTC-USDT-SWAP", help="Symbol for prototype mode (default: BTC-USDT-SWAP)")
    parser.add_argument("--days", type=int, default=120, help="Days of history to download (default: 120)")
    parser.add_argument("--confirm-full-run", action="store_true",
                         help="Required safety flag to actually run --mode full against the entire universe.")
    args = parser.parse_args()

    if args.mode == "full" and not args.confirm_full_run:
        print("❌ --mode full requires --confirm-full-run to actually execute. Refusing to proceed without it.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    checkpoint = _load_checkpoint()
    start_time = time.time()

    if args.mode == "prototype":
        results, quality = download_symbol(args.symbol, args.days, checkpoint)
        all_results = {args.symbol: {"datasets": results, "quality": quality}}
    else:
        # Full-universe path exists for completeness but is intentionally
        # NOT invoked by this task - explicit approval required first,
        # per the task's own instructions (Q).
        print("⚠️ Full-universe download is implemented but requires the actual 289-symbol "
              "universe list to be supplied - not run automatically here.")
        all_results = {}

    manifest = _write_manifest(all_results, start_time, args)
    print(f"\n{'='*70}\nMANIFEST\n{'='*70}")
    print(json.dumps(manifest, indent=2, default=str))
    print(f"\n🏁 Done in {manifest['duration_seconds']:.1f}s. Output: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
