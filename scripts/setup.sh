#!/usr/bin/env bash
# VLM Annotate - one-command setup for macOS / Linux.
#
# Usage (from the repository root):
#   bash scripts/setup.sh
#   SKIP_FRONTEND=1 bash scripts/setup.sh
#
# Installs backend dependencies into .venv, applies Alembic migrations, and
# (unless SKIP_FRONTEND=1) installs and builds the React UI.
# It never deletes data and never touches .env.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "VLM Annotate setup - $ROOT"

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found. Install Python 3.12+ and retry." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "Python 3.12+ required (found $("$PYTHON_BIN" --version))." >&2
  exit 1
fi
echo "Python $("$PYTHON_BIN" --version) OK"

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating .venv ..."
  "$PYTHON_BIN" -m venv .venv
fi
VENV_PY="$ROOT/.venv/bin/python"

if [ "${SKIP_INSTALL:-0}" != "1" ]; then
  echo "Installing backend dependencies ..."
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r backend/requirements.lock.txt
fi

echo "Applying database migrations ..."
if ! (cd backend && "$VENV_PY" -m alembic upgrade head); then
  echo ""
  echo "Migration failed." >&2
  echo "Most common cause: the API was started before migrations, so data/vlm_annotate.db" >&2
  echo "exists without Alembic's version row. Stop the API/worker, delete" >&2
  echo "data/vlm_annotate.db (development only) and rerun this script." >&2
  exit 1
fi

if [ "${SKIP_FRONTEND:-0}" != "1" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found. Install Node.js 20.19+ (22 LTS recommended)." >&2
    exit 1
  fi
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
  if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "Node 20.19+ required (found $(node --version))." >&2
    exit 1
  fi
  echo "Installing and building the frontend ..."
  (cd frontend && npm ci && npm run build)
fi

echo ""
echo "Setup complete. Start two terminals:"
echo "  1) cd backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000"
echo "  2) cd backend && ../.venv/bin/python -m app.worker --loop"
echo "Then open http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/api/docs)"
echo "The real GPU engine is optional: see video_grounding/README.md."
