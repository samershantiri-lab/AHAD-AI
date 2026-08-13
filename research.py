"""
================================================================================
AHAD AI - Research Lab
Phase 5: Research Controller
================================================================================

research.py is NOT an analyzer. It contains no research logic of its
own - no SQL, no statistics, no market data fetching. Its only job is
to run the research modules that already exist, report what happened,
and never let one module's failure stop the others. It is a Research
Manager, not a Research Engine.

INDEPENDENCE FROM bot.py, STATED EXPLICITLY:
- This file does not import bot.py, in any way.
- bot.py does not import this file, and never will - nothing in this
  codebase's production path references research.py.
- This file makes no database connection of its own and holds no
  DATABASE_URL - it never touches Postgres directly. Every database
  change happens inside the modules it runs, exactly as if you had run
  each of them yourself, one at a time, from the command line.
- This file never runs inside, or is called from, /scan - it has zero
  effect on scan speed, AI Brain, Ranking, Smart Money, the Validation
  Engine, or the Trade Recorder, because it does not touch any of that
  code and does not run in that process.
- No Telegram integration of any kind.

HOW MODULES ARE RUN, AND WHY:
Each research module is executed as a fully separate OS subprocess
(python <module>.py) rather than imported and called directly. This is
a deliberate safety choice: if a module crashes, hangs, raises an
unhandled exception, or even segfaults, that failure is contained
entirely within its own subprocess - the controller's own process is
completely unaffected, and every other registered module still gets
its chance to run. Direct imports would not offer the same guarantee;
a sufficiently broken module could bring down the controller itself
along with every module still queued to run.

HOW MODULES ARE REGISTERED:
See RESEARCH_MODULES below. Adding a future module - rejection_
analysis.py, compare_winners_losers.py, pattern_discovery.py,
ai_learning.py, or anything else - is a single new entry in that list.
Nothing else in this file needs to change. This is deliberate: the
orchestration logic below has no knowledge of what any module actually
does, only that it is a Python file that can be run and that reports
its own outcome to stdout.

HOW "RECORDS PROCESSED" IS DETERMINED:
Every existing module prints a line of the exact shape
"<label>: recorded <N> ...” at the point it finishes writing to its own
research table (e.g. "Winners Analyzer: recorded 3 new winning
trade(s)"). This controller reads that number back out of the module's
own captured stdout - it does not call into the module's internals,
re-implement its counting, or make any assumption about its schema.
If a module's output does not contain a line in that shape, "records"
is simply reported as unavailable - this is a best-effort convenience,
not a requirement any module must satisfy to run correctly.
================================================================================
"""

import os
import re
import sys
import subprocess
import time
import json
import psycopg2
from datetime import datetime


# ================================================
# 🔌 DATABASE CONNECTION (Phase 2 - research.py's first-ever DB connection)
# ================================================
# Added exclusively to persist research_runs and to cross-check module
# snapshot freshness (see run_research_lab()). This does not add any
# analytical logic to the controller - it still knows nothing about
# what any module actually studies; it only records that a run
# happened and whether each module's snapshot genuinely advanced.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - research.py "
            "needs it to persist research_runs and verify snapshot freshness."
        )
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode="require"
    )


def init_research_runs_table():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS research_runs (
            id SERIAL PRIMARY KEY,
            run_timestamp TIMESTAMP,
            modules_total INTEGER,
            modules_succeeded INTEGER,
            modules_failed INTEGER,
            modules_partial INTEGER,
            total_duration_seconds REAL,
            run_details JSONB
        )
        """)
        conn.commit()
    except Exception as e:
        print(f"⚠️ research.py: failed to initialize research_runs - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _get_snapshot_last_success(module_key):
    """
    Read-only lookup against research_snapshots, used only to verify
    that a module which exited 0 actually advanced its own snapshot.
    Returns None if the module has no snapshot row yet, or on any
    failure - callers treat that the same as "cannot confirm freshness"
    rather than raising.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT last_success_at FROM research_snapshots WHERE module_key = %s", (module_key,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"⚠️ research.py: failed to check snapshot freshness for {module_key} - {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _save_research_run(started_at, results):
    """
    Writes exactly one row summarizing this controller execution -
    modules_total/succeeded/failed/partial, total duration, and a JSONB
    per-module breakdown. This is the ONLY write research.py performs;
    it never writes to research_snapshots directly (that remains
    exclusively Snapshot Writer's responsibility).
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        succeeded = sum(1 for r in results if r["success"] and not r.get("partial"))
        partial = sum(1 for r in results if r.get("partial"))
        failed = sum(1 for r in results if not r["success"])
        total_duration = sum(r["duration_seconds"] for r in results if r["duration_seconds"] is not None)

        run_details = [
            {
                "name": r["name"],
                "success": r["success"],
                "partial": r.get("partial", False),
                "duration_seconds": r["duration_seconds"],
                "records": r["records"],
                "error": r["error"],
            }
            for r in results
        ]

        cur.execute("""
            INSERT INTO research_runs (
                run_timestamp, modules_total, modules_succeeded,
                modules_failed, modules_partial, total_duration_seconds,
                run_details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            started_at, len(results), succeeded, failed, partial,
            round(total_duration, 2), json.dumps(run_details, default=str)
        ))
        conn.commit()

        # --- TEMPORARY VERIFICATION LOG (remove once confirmed) ---
        print("✅ Research run saved successfully.")
        # --- END TEMPORARY VERIFICATION LOG ---

    except Exception as e:
        print(f"⚠️ research.py: failed to save research_runs entry - {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# 📋 MODULE REGISTRY - the only place a new module needs to be added
# ================================================
# `name` is what gets printed; `file` is the script's filename,
# resolved relative to this controller's own directory (so it works
# regardless of the working directory it's launched from).

RESEARCH_MODULES = [
    {"name": "Winners Analyzer", "file": "winners_analyzer.py", "module_key": "winners_analyzer"},
    {"name": "Losers Analyzer", "file": "losers_analyzer.py", "module_key": "losers_analyzer"},
    {"name": "Top Gainers Study", "file": "top_gainers_study.py", "module_key": "top_gainers_study"},
    {"name": "Top Losers Study", "file": "top_losers_study.py", "module_key": "top_losers_study"},
    {"name": "Compare Winners vs Losers", "file": "compare_winners_losers.py", "module_key": "compare_winners_losers"},
    {"name": "Missed Opportunity Study", "file": "missed_opportunity_study.py", "module_key": "missed_opportunity_study"},
    # Advanced Research - now fully integrated with the Snapshot Writer
    # (see winner_loser_dna_analysis.py's own MODULE_KEY constant), so
    # this gets the same freshness/PARTIAL detection as every other
    # module below, not the module_key=None fallback path.
    {"name": "Winner/Loser DNA Analysis", "file": "winner_loser_dna_analysis.py", "module_key": "winner_loser_dna"},
    # Writes TWO snapshot keys (market_conditioned, loss_clusters) from
    # one execution - see the file's own main() and the architectural
    # note delivered alongside this change. This entry's module_key is
    # the PRIMARY freshness signal the Runner checks; the module's own
    # internal fail-fast logic (raises if EITHER snapshot write fails)
    # is what makes a loss_clusters-only failure surface here too.
    {"name": "Market-Conditioned Analysis", "file": "market_conditioned_analysis.py", "module_key": "market_conditioned"},
]

# Generous on purpose: Top Gainers/Losers Study fetch OHLCV data for
# every USDT-SWAP symbol individually, with a polite delay between
# requests - a full run can legitimately take a few minutes on a large
# universe. This timeout exists only to catch a genuinely hung
# process, not to rush a slow-but-working one.
MODULE_TIMEOUT_SECONDS = 600

_RECORDS_PATTERN = re.compile(r"recorded (\d+)")


# ================================================
# ▶ MODULE EXECUTION - one isolated subprocess per module
# ================================================

def _module_path(filename):
    """Resolves a module's path relative to this controller's own
    directory, not the current working directory - so this works the
    same way regardless of where it's launched from."""
    controller_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(controller_dir, filename)


def run_module(module_info):
    """
    Runs a single research module as an isolated subprocess and
    returns a plain result dict describing what happened. Never
    raises - every failure mode (missing file, non-zero exit, timeout,
    or any other unexpected error) is caught here and turned into a
    result the caller can print and move on from.
    """
    name = module_info["name"]
    filename = module_info["file"]
    module_key = module_info.get("module_key")
    path = _module_path(filename)

    result = {
        "name": name,
        "file": filename,
        "module_key": module_key,
        "exists": False,
        "success": False,
        "partial": False,
        "duration_seconds": None,
        "records": None,
        "error": None,
    }

    if not os.path.isfile(path):
        result["error"] = f"{filename} not found"
        return result

    result["exists"] = True
    start = time.time()
    started_at = datetime.now()

    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=MODULE_TIMEOUT_SECONDS
        )
        result["duration_seconds"] = round(time.time() - start, 2)

        if proc.returncode == 0:
            result["success"] = True

            if module_key:
                last_success = _get_snapshot_last_success(module_key)
                if last_success is None or last_success < started_at:
                    result["partial"] = True
                    result["error"] = ("exited successfully, but its snapshot did not advance - "
                                        "the analysis likely ran but the snapshot write may have failed")
        else:
            last_line = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no error output"
            result["error"] = f"exited with code {proc.returncode} - {last_line}"

        # Best-effort only - see the module docstring above for exactly
        # what this does and does not assume.
        match = _RECORDS_PATTERN.search(proc.stdout)
        if match:
            result["records"] = int(match.group(1))

    except subprocess.TimeoutExpired:
        result["duration_seconds"] = round(time.time() - start, 2)
        result["error"] = f"timed out after {MODULE_TIMEOUT_SECONDS}s"
    except Exception as e:
        result["duration_seconds"] = round(time.time() - start, 2)
        result["error"] = f"unexpected controller-side error - {e}"

    return result


# ================================================
# 🖨 REPORTING - console output only, no Telegram, ever
# ================================================

def _print_module_result(result):
    if not result["exists"]:
        print(f"\n⚠️  {result['name']}")
        print(f"Status   : MISSING")
        print(f"Reason   : {result['error']}")
        return

    if result.get("partial"):
        icon = "⚠️"
        status_label = "PARTIAL"
    elif result["success"]:
        icon = "✅"
        status_label = "OK"
    else:
        icon = "❌"
        status_label = "FAILED"

    print(f"\n{icon} {result['name']}")
    print(f"Status   : {status_label}")
    duration_display = f"{result['duration_seconds']}s" if result["duration_seconds"] is not None else "N/A"
    print(f"Duration : {duration_display}")
    records_display = result["records"] if result["records"] is not None else "N/A"
    print(f"Records  : {records_display}")
    if result["error"]:
        print(f"Error    : {result['error']}")


def _print_summary(results, started_at):
    partial = sum(1 for r in results if r.get("partial"))
    succeeded = sum(1 for r in results if r["success"] and not r.get("partial"))
    failed = sum(1 for r in results if not r["success"])
    missing = sum(1 for r in results if not r["exists"])

    print("\n" + "=" * 50)
    print("Research Summary")
    print()
    print(f"Modules   : {len(results)}")
    print(f"Succeeded : {succeeded}")
    print(f"Failed    : {failed}")
    if partial:
        print(f"Partial   : {partial}")
    if missing:
        print(f"Missing   : {missing}")
    total_duration = sum(r["duration_seconds"] for r in results if r["duration_seconds"] is not None)
    print(f"Total duration : {round(total_duration, 2)}s")
    print(f"Started   : {started_at.isoformat()}")
    print(f"Finished  : {datetime.now().isoformat()}")
    print("\n" + "=" * 50)


# ================================================
# ▶ ENTRY POINT
# ================================================

def run_research_lab(modules=None):
    """
    Runs every registered module in order, printing each result as it
    completes, then a final summary. A module failing (or being
    missing) never stops the loop - every other module still gets its
    turn. Returns the list of result dicts, primarily so this can also
    be called programmatically (e.g. from a future scheduler) without
    needing to parse console output.

    Phase 2: also persists one summary row to research_runs after the
    console summary is printed, and cross-checks each successful
    module's snapshot freshness (see run_module()) - a module can now
    be marked "partial" if it exited 0 but its snapshot didn't actually
    advance.
    """
    modules = modules if modules is not None else RESEARCH_MODULES
    started_at = datetime.now()

    init_research_runs_table()

    print("=" * 50)
    print("AHAD AI RESEARCH LAB")
    print("=" * 50)

    results = []
    for module_info in modules:
        result = run_module(module_info)
        _print_module_result(result)
        results.append(result)

    _print_summary(results, started_at)
    _save_research_run(started_at, results)
    return results


def main():
    run_research_lab()


if __name__ == "__main__":
    main()
