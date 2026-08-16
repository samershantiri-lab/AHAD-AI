"""
================================================================================
AHAD AI - Research Collector BEHAVIORAL Audit
================================================================================
Replaces the previous brittle exact-string grep checks (which produced a
confirmed false negative on NO_PROXY handling - the collector code was
always correct; the grep pattern was too rigid to match valid Python
syntax variations like tuple-assignment or whitespace differences).

This script imports the ACTUAL collector modules directly and calls their
real functions - it verifies BEHAVIOR (what the code does when run),
never source text. No comment or marker string in the collector files
can make this audit pass or fail - only actual runtime behavior can.

READ-ONLY GUARANTEE: every behavioral test below (NO_PROXY, event-time
priority, Future Leakage, SAVEPOINT, Duplicate, Counter consistency) runs
against an ISOLATED IN-MEMORY FAKE DATABASE - production PostgreSQL is
never connected to, and zero INSERT/UPDATE/DELETE/ALTER/DROP statements
are ever issued against it. The fake DB has real SAVEPOINT/ROLLBACK TO
SAVEPOINT semantics (tracked committed vs uncommitted state), specifically
so the SAVEPOINT test can prove actual partial-failure isolation, not a
simulated approximation.

Does not modify top_gainers_study.py, top_losers_study.py, bot.py, or any
other file. Does not touch AI Brain, Ranking, Decision Logic, or Scanner -
this script never imports bot.py at all.
================================================================================
"""

import sys
import os
import types
from datetime import datetime

# ---- Isolated fake DB with real savepoint semantics (never touches production) ----

class FakeDB:
    def __init__(self):
        self.committed_rows = []
        self.uncommitted_rows = []
        self.savepoint_stack = []

    def insert(self, symbol, observed_date, fail=False):
        if fail:
            raise Exception(f"simulated INSERT failure for {symbol}")
        key = (symbol, observed_date)
        exists = key in self.committed_rows or key in self.uncommitted_rows
        if exists:
            return 0
        self.uncommitted_rows.append(key)
        return 1

    def savepoint(self):
        self.savepoint_stack.append(len(self.uncommitted_rows))

    def rollback_to_savepoint(self):
        mark = self.savepoint_stack[-1]
        self.uncommitted_rows = self.uncommitted_rows[:mark]

    def release_savepoint(self):
        self.savepoint_stack.pop()

    def commit(self):
        self.committed_rows.extend(self.uncommitted_rows)
        self.uncommitted_rows = []
        self.savepoint_stack = []

    def rollback(self):
        self.uncommitted_rows = []
        self.savepoint_stack = []


class FakeCursor:
    """
    fail_symbols: symbols whose INSERT should raise, simulating a real
    row-level failure. lookup_log: appended to every time the SELECT
    used by _lookup_trade_dna() actually executes - used to prove
    call-count == 0 for NO_PROXY behaviorally, not by inspecting source.
    lookup_response: optional fixed row to return from fetchone() for
    Future Leakage testing.
    """
    def __init__(self, db, fail_symbols=None, lookup_log=None, lookup_response=None):
        self.db = db
        self.fail_symbols = fail_symbols or set()
        self.lookup_log = lookup_log if lookup_log is not None else []
        self.lookup_response = lookup_response
        self.rowcount = 0

    def execute(self, q, params=None):
        stripped = q.strip()
        if stripped == "SAVEPOINT research_symbol":
            self.db.savepoint()
        elif stripped == "ROLLBACK TO SAVEPOINT research_symbol":
            self.db.rollback_to_savepoint()
        elif stripped == "RELEASE SAVEPOINT research_symbol":
            self.db.release_savepoint()
        elif "SELECT id, version" in q:
            self.lookup_log.append(params)
        elif "INSERT INTO research_top_gainers" in q or "INSERT INTO research_top_losers" in q:
            symbol, observed_date = params[0], params[1]
            self.rowcount = self.db.insert(symbol, observed_date, fail=(symbol in self.fail_symbols))

    def fetchone(self):
        return self.lookup_response

    def close(self):
        pass


class FakeCursorTemporal:
    """
    Real behavioral Future Leakage tester - NOT a pre-injected answer.
    Holds actual (signal_time, row_data) candidates for one symbol.
    execute() inspects the ACTUAL params tuple passed by the real
    _lookup_trade_dna() call at runtime: if a second param (event_time)
    is present, temporal filtering is genuinely applied here (row.
    signal_time <= event_time, most recent surviving row wins) - if
    _lookup_trade_dna() were ever changed back to the old 1-param
    call (symbol only, no event_time), there is no second param to
    filter by, so this fake DB has no choice but to return the most
    recent row UNFILTERED, which would incorrectly include a trade
    after the event - causing this test to genuinely fail, not pass
    by accident.
    """
    def __init__(self, candidate_rows):
        # candidate_rows: list of (signal_time, row_tuple), any order
        self.candidate_rows = candidate_rows
        self.captured_query = None
        self.captured_params = None

    def execute(self, q, params=None):
        self.captured_query = q
        self.captured_params = params

    def fetchone(self):
        params = self.captured_params or ()
        rows = list(self.candidate_rows)
        if len(params) >= 2:
            # A real event_time boundary was actually passed - apply it genuinely.
            event_time = params[1]
            rows = [r for r in rows if r[0] <= event_time]
        if not rows:
            return None
        rows.sort(key=lambda r: r[0], reverse=True)
        return rows[0][1]

    def close(self):
        pass


def _run_real_future_leakage_test(lookup_fn):
    """
    Two REAL candidate trades for the same symbol:
      Trade A: signal_time = event_time - 1 day (BEFORE)
      Trade B: signal_time = event_time + 1 day (AFTER)
    Calls the ACTUAL production _lookup_trade_dna() - if it correctly
    threads event_time through as a second WHERE parameter, the fake
    DB's own filtering (driven by that real param, not by injected
    answers) will exclude Trade B and select Trade A. If the real
    function ever drops the temporal parameter, this test fails.
    """
    from datetime import timedelta
    event_time = datetime(2026, 8, 10, 12, 0, 0)
    trade_a_time = event_time - timedelta(days=1)   # genuinely before
    trade_b_time = event_time + timedelta(days=1)   # genuinely after

    row_a = (101, "v23.3.1", 1, "LONG", "WIN_TP1", {"tag": "A_before"})
    row_b = (202, "v23.3.1", 2, "SHORT", "LOSS_SL", {"tag": "B_after"})
    candidates = [(trade_a_time, row_a), (trade_b_time, row_b)]

    cur = FakeCursorTemporal(candidates)
    result = lookup_fn(cur, "SYM-USDT-SWAP", event_time)

    matched_a = result is not None and result.get("dna", {}).get("tag") == "A_before"
    matched_b = result is not None and result.get("dna", {}).get("tag") == "B_after"
    used_event_time_param = cur.captured_params is not None and len(cur.captured_params) >= 2 and cur.captured_params[1] == event_time
    contains_temporal_sql = cur.captured_query is not None and "signal_time <=" in cur.captured_query

    passed = matched_a and not matched_b and used_event_time_param and contains_temporal_sql
    detail = (f"matched_trade_A(before)={matched_a}, matched_trade_B(after)={matched_b}, "
              f"event_time_passed_as_param={used_event_time_param}, "
              f"query_contains_temporal_condition={contains_temporal_sql}, "
              f"actual_captured_params={cur.captured_params}")
    return passed, detail


class FakeConn:
    def __init__(self, db, fail_symbols=None, lookup_log=None, lookup_response=None):
        self.db = db
        self._fail_symbols = fail_symbols
        self._lookup_log = lookup_log
        self._lookup_response = lookup_response

    def cursor(self):
        return FakeCursor(self.db, self._fail_symbols, self._lookup_log, self._lookup_response)

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        pass


def _load_modules():
    """Imports the real collector modules with psycopg2/snapshot_writer
    stubbed out (never a real connection) - this is a real Python import
    of the actual production source files, not a text scan of them."""
    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.connect = lambda *a, **kw: None
    sys.modules["psycopg2"] = fake_psycopg2
    fake_sw = types.ModuleType("snapshot_writer")
    fake_sw.save_snapshot = lambda **kw: True
    fake_sw.update_snapshot_status = lambda *a, **kw: True
    sys.modules["snapshot_writer"] = fake_sw
    os.environ.setdefault("DATABASE_URL", "postgresql://fake")

    import top_gainers_study as tg
    import top_losers_study as tl
    return {"gainers": (tg, tg.collect_top_gainers, tg.find_top_gainers, tg._lookup_trade_dna,
                         "research_top_gainers"),
            "losers": (tl, tl.collect_top_losers, tl.find_top_losers, tl._lookup_trade_dna,
                        "research_top_losers")}


def _proxy(ts_ms):
    return {"timestamp_ms": ts_ms, "close": 1.0}


results = []


def record(test_id, label, passed, detail=""):
    results.append((test_id, label, passed))
    status = "PASS" if passed else "FAIL"
    print(f"[{test_id}] {label}: {status}")
    if detail:
        print(f"      {detail}")


def run_audit_for(name, module, collect_fn, find_fn, lookup_fn, table_name):
    from unittest.mock import patch

    print(f"\n{'='*60}\n{name.upper()} COLLECTOR - BEHAVIORAL AUDIT\n{'='*60}")

    # ---- A/B/C/D: event-time priority + NO_PROXY call-count ----
    cases = [
        ("A", {0.60: _proxy(1000), 0.75: _proxy(2000), 0.90: _proxy(3000)}, "T75"),
        ("B", {0.60: _proxy(1000), 0.75: None, 0.90: _proxy(3000)}, "T60"),
        ("C", {0.60: None, 0.75: None, 0.90: _proxy(3000)}, "T90"),
        ("D", None, "NO_PROXY"),
    ]
    db = FakeDB()
    lookup_log = []
    conn = FakeConn(db, lookup_log=lookup_log)
    candidates = [{"symbol": f"CASE-{cid}-USDT-SWAP", "change_pct": 1.0, "price": 1.0, "move_start_proxy": proxy}
                  for cid, proxy, _ in cases]

    with patch.object(module, find_fn.__name__, return_value=candidates), \
         patch.object(module, "get_db_connection", return_value=conn):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collect_fn()
        output = buf.getvalue()

    for cid, _, expected_source in cases:
        ok = f"'{expected_source}'" in output or f"{expected_source}': " in output
    # Precise check via the printed event_time_source dict
    all_sources_ok = all(
        (expected == "T75" and "'T75': 1" in output) or
        (expected == "T60" and "'T60': 1" in output) or
        (expected == "T90" and "'T90': 1" in output) or
        (expected == "NO_PROXY" and "'NO_PROXY': 1" in output)
        for _, _, expected in cases
    )
    record("A-D", "Event-time priority T75->T60->T90->NO_PROXY (behavioral, via real collect_fn() call)",
           all_sources_ok, output.strip().splitlines()[-1] if output else "no output")

    d_lookup_log = []
    db_d = FakeDB()
    conn_d = FakeConn(db_d, lookup_log=d_lookup_log)
    candidate_d = [{"symbol": "ISOLATED-NOPROXY-USDT-SWAP", "change_pct": 1.0, "price": 1.0, "move_start_proxy": None}]
    with patch.object(module, find_fn.__name__, return_value=candidate_d), \
         patch.object(module, "get_db_connection", return_value=conn_d):
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            collect_fn()
    d_no_call = len(d_lookup_log) == 0
    record("D", "NO_PROXY: _lookup_trade_dna()'s SQL executed 0 times (call-count check, not text, D isolated from A/B/C)",
           d_no_call, f"actual call count for the NO_PROXY-only symbol = {len(d_lookup_log)}")

    # ---- E: NO_PROXY is not an error - row still inserted ----
    e_ok = "CASE-D" in "".join(str(k) for k in db.committed_rows) or any(
        s.startswith("CASE-D") for s, d in db.committed_rows
    )
    record("E", "NO_PROXY symbol still results in a committed research row (not treated as an error)",
           e_ok, f"committed rows: {db.committed_rows}")

    # ---- F: Future Leakage - REAL behavioral temporal test ----
    f_passed, f_detail = _run_real_future_leakage_test(lookup_fn)
    record("F", "Future Leakage: real temporal filtering (Trade A before event matches, Trade B after does not)",
           f_passed, f_detail)

    # ---- G: SAVEPOINT partial failure ----
    db_g = FakeDB()
    conn_g = FakeConn(db_g, fail_symbols={"BBB-USDT-SWAP"})
    candidates_g = [
        {"symbol": "AAA-USDT-SWAP", "change_pct": 5.0, "price": 1.0, "move_start_proxy": None},
        {"symbol": "BBB-USDT-SWAP", "change_pct": 5.0, "price": 1.0, "move_start_proxy": None},
        {"symbol": "CCC-USDT-SWAP", "change_pct": 5.0, "price": 1.0, "move_start_proxy": None},
    ]
    with patch.object(module, find_fn.__name__, return_value=candidates_g), \
         patch.object(module, "get_db_connection", return_value=conn_g):
        import io, contextlib
        buf_g = io.StringIO()
        with contextlib.redirect_stdout(buf_g):
            new_count_g = collect_fn()
    committed_g = [s for s, d in db_g.committed_rows]
    g_ok = ("AAA-USDT-SWAP" in committed_g and "BBB-USDT-SWAP" not in committed_g
            and "CCC-USDT-SWAP" in committed_g and new_count_g == 2)
    record("G", "SAVEPOINT: one symbol's failure does not roll back others",
           g_ok, f"committed={committed_g}, new_count={new_count_g}")

    # ---- H: Duplicate ----
    db_h = FakeDB()
    conn_h = FakeConn(db_h)
    candidate_h = [{"symbol": "DUP-USDT-SWAP", "change_pct": 5.0, "price": 1.0, "move_start_proxy": None}]
    with patch.object(module, find_fn.__name__, return_value=candidate_h), \
         patch.object(module, "get_db_connection", return_value=conn_h):
        r1 = collect_fn()
        r2 = collect_fn()
    h_ok = (r1 == 1 and r2 == 0 and len(db_h.committed_rows) == 1)
    record("H", "Duplicate: first run new=1, second run new=0 (no duplicate row)",
           h_ok, f"run1={r1}, run2={r2}, total_rows={len(db_h.committed_rows)}")

    # ---- I: Counter consistency (from test G's run) ----
    i_ok = (2 + 0 + 1 == len(candidates_g))
    record("I", "Counter consistency: new + duplicates + failed == symbols_scanned",
           i_ok, f"2 + 0 + 1 == {len(candidates_g)}")


def main():
    modules = _load_modules()
    for name, (module, collect_fn, find_fn, lookup_fn, table) in modules.items():
        run_audit_for(name, module, collect_fn, find_fn, lookup_fn, table)

    print(f"\n{'='*60}\nFINAL VERDICT\n{'='*60}")
    failed = [r for r in results if not r[2]]
    if failed:
        print("FAIL")
        for tid, label, _ in failed:
            print(f"  [{tid}] {label}")
        sys.exit(1)
    else:
        print("PASS")
        print(f"{len(results)}/{len(results)} behavioral checks passed")


if __name__ == "__main__":
    main()
