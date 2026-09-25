#!/bin/sh
# Runesmith Studio launcher. Run it (or double-click it on macOS); pass a folder to work in that folder.
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "Runesmith needs Python 3.11 or newer: https://www.python.org/downloads/"
  (command -v open >/dev/null && open "https://www.python.org/downloads/") 2>/dev/null
  printf "Press Enter to close. "; read -r _; exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Runesmith needs Python 3.11 or newer; this one is $("$PY" --version 2>&1)."
  printf "Press Enter to close. "; read -r _; exit 1
fi
echo ""
echo "  Runesmith Studio is starting. Your browser opens in a moment."
echo "  Keep this window open while you work; press Ctrl+C to stop."
echo ""
if [ -n "$1" ]; then exec "$PY" -m runesmith up "$1"; else exec "$PY" -m runesmith up --last; fi
