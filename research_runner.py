"""
================================================================================
AHAD AI - Research Lab
Research Runner (local manual entry point)
================================================================================

research_runner.py has no logic of its own beyond importing research.py
(the Research Lab controller) and calling research.run_research_lab().
Its only purpose is to give a single, memorable command to run the
entire Research Lab by hand, from a local machine:

    python research_runner.py

WHY THIS EXISTS: Render's free tier no longer provides Shell access, so
the Research Lab cannot be triggered from inside that environment on
demand. This file is meant to be run locally instead - from any
machine with network access to the same PostgreSQL database (the same
DATABASE_URL bot.py and every Research Lab module already use) - so
running the Research Lab never depends on Render Shell being available
at all.

This file:

- Is completely independent from bot.py - it does not import bot.py,
  and bot.py does not import this file.
- Imports only research.py - nothing else project-specific.
- Contains no database logic and no SQL of its own - every database
  interaction happens inside the modules research.py orchestrates, not
  here.
- Does not start automatically - it only runs when explicitly invoked
  from the command line.
- Requires no Telegram bot token or Telegram integration of any kind.
- Has no scheduler, no cron, no background thread, and no Flask/web
  server integration - it runs once, synchronously, and exits. This is
  intentionally the simplest and safest possible entry point: nothing
  here can run unattended, unexpectedly, or in the background.
- Has no effect on production - running this does not touch bot.py,
  does not run inside /scan, and does not modify AI Brain, Ranking,
  Smart Money, the Validation Engine, or the Trade Recorder in any way.

SETUP: before running this locally, DATABASE_URL must be set in the
local environment to the same value bot.py uses on Render, so this
reaches the same database. How you set that (a local .env file, an
exported shell variable, etc.) is up to your own local setup - this
file does not manage that for you, by design, since doing so would be
its own kind of logic this file deliberately does not need.
================================================================================
"""

from datetime import datetime

import research


def main():
    print(f"🚀 AHAD AI Research Lab - local run starting - {datetime.now().isoformat()}")
    research.run_research_lab()
    print(f"🏁 AHAD AI Research Lab - local run finished - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
