"""``python -m runesmith``: the command line, with unexpected errors in plain words (journey J10).

A person at a terminal gets one line saying what went wrong and where to look next, not a Python traceback.
RUNESMITH_DEBUG=1 shows the full traceback. Expected refusals already end with their own plain message.
"""
import os
import sys

from runesmith.cli import main

try:
    main()
except KeyboardInterrupt:
    sys.exit(130)
except Exception as error:                                   # SystemExit (a plain refusal) passes through untouched
    if os.environ.get("RUNESMITH_DEBUG"):
        raise
    print(f"Runesmith stopped: {error or type(error).__name__}", file=sys.stderr)
    print("Run `runesmith doctor` to check the setup, or run the same command again with RUNESMITH_DEBUG=1 "
          "to see the full details (and include them if you ask for help).", file=sys.stderr)
    sys.exit(1)
