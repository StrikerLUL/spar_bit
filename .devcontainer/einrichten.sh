#!/usr/bin/env bash
# Wird einmal beim Bau des Dev-Containers ausgefuehrt.
set -euo pipefail

echo "== Backend =="
python -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r backend/requirements-dev.txt --quiet
.venv/bin/pip install ruff pytest-cov pre-commit --quiet

echo "== Oberflaeche =="
npm --prefix frontend ci

echo "== Commit-Haken =="
.venv/bin/pre-commit install || echo "  (uebersprungen - kein Git-Repository?)"

cat <<'HINWEIS'

Fertig. Weiter geht es mit:

  .venv/bin/python run.py --dev     # Backend + Vite, beide mit Neuladen
  .venv/bin/python -m pytest -q     # Tests
  npm --prefix frontend test        # Tests der Oberflaeche

HINWEIS
