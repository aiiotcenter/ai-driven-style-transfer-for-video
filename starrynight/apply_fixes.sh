#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Fixing startup blockers"
echo

if command -v python3.9 >/dev/null 2>&1; then
  PYTHON_BIN="python3.9"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "python3.9 or python3 is required for this setup script."
  echo "Install Python, then rerun this script."
  exit 1
fi

echo "1. Creating Python venv"
# Uses python3.9 when available, otherwise falls back to python3.
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "2. Running Django setup"
cd backend
python manage.py migrate
python manage.py check

echo
echo "3. Preparing frontend"
cd ../frontend
if command -v nvm >/dev/null 2>&1; then
  nvm use 18 >/dev/null
else
  echo "nvm not found; make sure Node 18 is active before continuing."
fi
npm install
npm run build

echo
echo "All repo-side fixes are applied."
echo
echo "Start development with:"
echo "  Terminal 1: cd starrynight/backend && source ../.venv/bin/activate && export CACHE_BACKEND=file && python manage.py runserver"
echo "  Terminal 2: cd starrynight/frontend && npm start"
