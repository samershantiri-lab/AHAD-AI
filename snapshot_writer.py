"""
================================================================================
AHAD AI - Research Lab
Snapshot Writer
================================================================================

The Snapshot Writer is the sole persistence layer for the Snapshot
Layer. It has exactly two public responsibilities, per the approved
architecture:

    - save_snapshot()          - persist a successful module's summary
    - update_snapshot_status() - mark an attempt (running/failed)
                                  without touching the last good summary

Nothing else. No business logic, no analytical logic, no research
logic - this file never computes a statistic, never queries a
production table, and never knows anything about what any calling
module actually studies.

DOMAIN-AGNOSTIC BY CONSTRUCTION, NOT JUST BY INTENT: every value this
file touches arrives as a parameter from the caller - module_key,
headline_stat, summary_data, etc. There is no branch anywhere in this
file that inspects what module_key IS, and no module name, metric
name, or table name belonging to any specific Research Lab module
appears anywhere in this code. This was checked directly (grepped for
every existing module/table name) before delivery, not just assumed
from the design.

Completely independent from bot.py - never imported by it, never
imports it. Read/write scope is limited to exactly one table,
`research_snapshots`, which this file owns exclusively - no other
Research Lab module writes to it directly.

LIFECYCLE CONTRACT this file exists to support (the official lifecycle
every Research Module follows):

    Start
      → update_snapshot_status(..., "RUNNING")
    Analysis
      → the module's own, entirely separate analysis logic
    Store detailed research data (if applicable)
      → the module's own detail table, if it has one
    Generate Snapshot
      → the module computes its own headline_stat/summary_data
    Snapshot Writer
      → save_snapshot(...)              [on success]
      → update_snapshot_status(..., "FAILED")   [on failure]
    Finish

WRITE-ONCE VS REFRESHABLE, STATED PRECISELY: update_snapshot_status()
NEVER touches last_success_at/headline_stat/summary_data/
internal_metadata - a failed or in-progress attempt must never
overwrite the last good snapshot. Only save_snapshot(), called after a
module's analysis has already fully succeeded, refreshes those fields
- and it does so as a single atomic upsert, not a check-then-write
sequence, avoiding the exact "two things touching the same row
inconsistently" bug class that has appeared more than once elsewhere
in this project.
================================================================================
"""

import os
import json
import psycopg2
from datetime import datetime


# ================================================
# 🔌 DATABASE CONNECTION
# ================================================
# Identical connection pattern to every other Research Lab module.

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set in the environment - Snapshot Writer "
            "needs the same DATABASE_URL bot.py and every Research Lab "
            "module use to reach the same database."
        )
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        sslmode="require"
    )


# ================================================
# 🗄 SCHEMA - research_snapshots (owned exclusively by this file)
# ================================================

def _ensure_snapshot_table(cur):
    """
    Idempotent - CREATE TABLE IF NOT EXISTS, same convention as every
    other Research Lab module's own table ownership. Called internally
    by both public functions; not exposed as a separate responsibility.
    """
    cur.execute("""
    CREATE TABLE IF NOT EXISTS research_snapshots (
        module_key TEXT UNIQUE NOT NULL,
        module_name TEXT,
        category TEXT,
        last_success_at TIMESTAMP,
        last_attempt_at TIMESTAMP,
        last_attempt_status TEXT,
        headline_stat TEXT,
        summary_data JSONB,
        internal_metadata JSONB,
        version_scope TEXT,
        detail_table TEXT,
        schema_version INTEGER DEFAULT 1
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_snapshots_category ON research_snapshots(category)")


# ================================================
# ✍️ PUBLIC API - exactly two functions, per the approved architecture
# ================================================

def update_snapshot_status(module_key, module_name, category, status):
    """
    Marks an attempt - call with status="RUNNING" at the very start of
    a module's main() (so a mid-run crash still leaves a record that
    something was attempted), or status="FAILED" if the module's own
    analysis raises.

    Touches ONLY last_attempt_at/last_attempt_status (plus module_name/
    category, harmless display metadata refreshed for convenience) -
    NEVER last_success_at/headline_stat/summary_data/internal_metadata.
    A failed or in-progress attempt must never overwrite the last good
    snapshot.

    Never raises - any failure here is caught, logged, and returns
    False. A Snapshot Writer failure must never affect the calling
    module's own exit code or analysis.
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        _ensure_snapshot_table(cur)

        cur.execute("""
            INSERT INTO research_snapshots (
                module_key, module_name, category,
                last_attempt_at, last_attempt_status
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (module_key) DO UPDATE SET
                module_name = EXCLUDED.module_name,
                category = EXCLUDED.category,
                last_attempt_at = EXCLUDED.last_attempt_at,
                last_attempt_status = EXCLUDED.last_attempt_status
        """, (
            module_key, module_name, category,
            datetime.now(), status
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ Snapshot Writer: failed to update status for {module_key} - {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def save_snapshot(module_key, module_name, category, headline_stat,
                   summary_data, version_scope, detail_table=None,
                   schema_version=1, module_version=None,
                   execution_duration_seconds=None, records_processed=None):
    """
    Persists a successful module run as one atomic upsert - call ONLY
    after a module's own analysis has fully succeeded. Refreshes every
    field together: last_success_at, last_attempt_at,
    last_attempt_status='SUCCESS', headline_stat, summary_data,
    internal_metadata, version_scope, detail_table, schema_version.

    internal_metadata is assembled here from explicit keyword arguments
    (execution_duration_seconds, records_processed, module_version) -
    the Version 1 approved set. Deliberately extensible: adding a
    future field (e.g. execution_id, research_version) is one new
    optional parameter with a default of None - existing callers keep
    working unchanged, and old snapshot rows simply lack that key
    rather than needing a migration.

    Never raises - any failure here is caught, logged, and returns
    False, same guarantee as update_snapshot_status().
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        _ensure_snapshot_table(cur)

        internal_metadata = {
            "execution_duration_seconds": execution_duration_seconds,
            "records_processed": records_processed,
            "module_version": module_version,
        }

        now = datetime.now()

        cur.execute("""
            INSERT INTO research_snapshots (
                module_key, module_name, category,
                last_success_at, last_attempt_at, last_attempt_status,
                headline_stat, summary_data, internal_metadata,
                version_scope, detail_table, schema_version
            ) VALUES (
                %s, %s, %s,
                %s, %s, 'SUCCESS',
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (module_key) DO UPDATE SET
                module_name = EXCLUDED.module_name,
                category = EXCLUDED.category,
                last_success_at = EXCLUDED.last_success_at,
                last_attempt_at = EXCLUDED.last_attempt_at,
                last_attempt_status = EXCLUDED.last_attempt_status,
                headline_stat = EXCLUDED.headline_stat,
                summary_data = EXCLUDED.summary_data,
                internal_metadata = EXCLUDED.internal_metadata,
                version_scope = EXCLUDED.version_scope,
                detail_table = EXCLUDED.detail_table,
                schema_version = EXCLUDED.schema_version
        """, (
            module_key, module_name, category,
            now, now,
            headline_stat, json.dumps(summary_data, default=str), json.dumps(internal_metadata, default=str),
            version_scope, detail_table, schema_version
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ Snapshot Writer: failed to save snapshot for {module_key} - {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
