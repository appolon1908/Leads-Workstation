#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a
. /home/codestra/.config/codestra-leads/db.env
set +a
exec "$ROOT/.venv/bin/uvicorn" app.main:app --app-dir "$ROOT" --host 127.0.0.1 --port 8780
