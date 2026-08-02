"""
================================================================================
AHAD AI - Research Lab
Phase 7: Manual Runner
================================================================================

run_research.py is not a module in its own right - it has no logic of
its own beyond importing research.py (the Research Lab controller) and
calling research.run_research_lab(). Its only purpose is to give a
single, memorable command to run the entire Research Lab by hand:

    python run_research.py

This file:

- Is completely independent from bot.py - it does not import bot.py,
  and bot.py does not import this file.
- Contains no database logic and no SQL of its own - every database
  interaction happens inside the modules research.py orchestrates, not
  here.
- Sends no Telegram messages and includes no scheduler - it runs once,
  when invoked, and exits.
- Duplicates nothing from research.py - it calls the controller's
  existing entry point rather than reimplementing any part of what it
  does.
================================================================================
"""

from datetime import datetime

import research


def main():
    print(f"🚀 AHAD AI Research Lab - manual run starting - {datetime.now().isoformat()}")
    research.run_research_lab()
    print(f"🏁 AHAD AI Research Lab - manual run finished - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
