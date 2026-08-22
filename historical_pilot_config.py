"""
================================================================================
AHAD AI - Historical Market Pilot - Configuration
================================================================================

Standalone constants for the Historical Market Pilot. This file has ZERO
imports from bot.py, ZERO imports from any Research module, and is never
imported by anything in Production or the Research Lab - it exists only
for the pilot itself.

Run manually only:
    python historical_market_pilot.py

Never part of Production startup, never scheduled, never imported by
research_runner.py or research.py.
================================================================================
"""

OKX_BASE_URL = "https://www.okx.com"
CANDLES_HISTORY_ENDPOINT = "/api/v5/market/history-candles"
INSTRUMENTS_ENDPOINT = "/api/v5/public/instruments"
FUNDING_RATE_HISTORY_ENDPOINT = "/api/v5/public/funding-rate-history"
OPEN_INTEREST_HISTORY_ENDPOINT = "/api/v5/rubik/stat/contracts/open-interest-history"

# Pilot scope - deliberately small, per the approved design.
#
# FIXED (confirmed design flaw from the real OKX pilot run): 12 was too
# small - selecting Top 10 from only 12 symbols means ~83% of the
# universe is selected every single hour, which does not exercise the
# actual ranking/selection logic at all. 60 keeps the pilot small
# enough to measure rate limits meaningfully (still tiny next to the
# hundreds of symbols a full 120-day backfill would use), while making
# Top 10 a real ~17% selection - a genuine test of the sorting logic,
# not a near-pass-through.
PILOT_UNIVERSE_SIZE = 60
PILOT_DAYS = 3
TOP_N_PER_HOUR = 10

# Pre-event offsets to test, in minutes before event_timestamp.
PRE_EVENT_OFFSETS_MINUTES = [15, 30, 60, 180, 360, 720, 1440]  # -15m..-24h

# Candles per history-candles request - conservative, well under OKX's
# documented cap, matching this project's existing convention of never
# using the full allowed limit.
CANDLES_PER_REQUEST = 100

# Rate limiting / retry - conservative, matches this project's existing
# REQUEST_DELAY_SECONDS convention (0.15s) elsewhere in the codebase.
REQUEST_DELAY_SECONDS = 0.2
MAX_RETRIES_PER_REQUEST = 3
BACKOFF_BASE_SECONDS = 1.0  # doubles each retry: 1s, 2s, 4s
MAX_TOTAL_REQUESTS = 2000  # hard ceiling - pilot must never run unbounded

OUTPUT_DIR = "."
EVENTS_CSV = "pilot_events.csv"
SNAPSHOTS_CSV = "pilot_pre_event_snapshots.csv"
UNIVERSE_CSV = "pilot_universe.csv"
FUNDING_OI_CSV = "pilot_funding_oi.csv"
REPORT_TXT = "pilot_report.txt"
