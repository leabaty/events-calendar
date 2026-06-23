#!/usr/bin/env bash
# ------------------------------------------------------------------
# run.sh — load secrets & launch the event pipeline locally
#
# Usage:
#   chmod +x run.sh
#   ./run.sh
# ------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Load .env (Google Calendar ID) ────────────────────────────
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# ── 2. Load credentials from JSON files into env vars ────────────
if [ ! -f token.json ]; then
    echo "❌ token.json not found — run: python get_token.py"
    exit 1
fi
export GMAIL_TOKEN="$(cat token.json)"

# Find the service-account key
SA_KEY="$(ls events-gap-*.json 2>/dev/null | head -1)"
if [ -z "$SA_KEY" ]; then
    echo "❌ events-gap-*.json not found — place the service-account key in this directory."
    exit 1
fi
export GOOGLE_CALENDAR_CREDENTIALS="$(cat "$SA_KEY")"

# ── 3. Validate required vars ────────────────────────────────────
if [ -z "${GOOGLE_CALENDAR_ID:-}" ]; then
    echo "❌ GOOGLE_CALENDAR_ID is not set — add it to .env"
    exit 1
fi

# ── 4. Activate virtual env & run ────────────────────────────────
if [ ! -d .venv ]; then
    echo "📦 Creating virtual environment…"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

echo "🚀 Launching events-gap…"
python src/main.py
