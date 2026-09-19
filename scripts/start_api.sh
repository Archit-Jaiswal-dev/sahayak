#!/usr/bin/env bash
# Start the Sahayak FastAPI backend (conversation, STT, TTS bridge, filing, watchdog).
#
#   bash scripts/start_api.sh
#
# Requires .env to be configured (LLM key, etc.). Listens on 0.0.0.0 so your
# phone (same Wi-Fi) can reach it at http://<PC-LAN-IP>:8000.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill in keys." >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  "$@"
