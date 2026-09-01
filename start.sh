#!/usr/bin/env bash
# SparBit starten (Linux/macOS) - Doppelklick oder ./start.sh
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.11 oder neuer wird benoetigt."
  echo "Holen unter: https://www.python.org/downloads/"
  read -rp "Enter zum Schliessen "
  exit 1
fi

"$PY" run.py "$@"
