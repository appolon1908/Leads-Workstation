#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

export PYTHONPATH="$ROOT/src"

echo "== Leads Workstation V2 certification =="
"$PYTHON" -m compileall -q src
"$PYTHON" -m unittest discover -s tests -v

if [[ -f scripts/security_scan.py ]]; then
  "$PYTHON" scripts/security_scan.py
fi

"$PYTHON" - <<'PY'
from pathlib import Path
required = [
    "src/leads_workstation/auth.py",
    "src/leads_workstation/platform.py",
    "src/leads_workstation/storage.py",
    "src/leads_workstation/worker.py",
    "src/leads_workstation/migrate.py",
    "src/leads_workstation/dedupe.py",
    "src/leads_workstation/imports.py",
    "src/leads_workstation/dashboard.py",
    "src/leads_workstation/backup.py",
    "docker-compose.v2.yml",
    "docs/V2-ARCHITECTURE.md",
    "docs/V2-CERTIFICATION-2026-10-07.md",
]
missing=[p for p in required if not Path(p).is_file()]
if missing:
    raise SystemExit("missing V2 artifacts: " + ", ".join(missing))
print("v2_artifacts=passed")
PY

printf '%s\n' 'data/private/sample.csv' | git check-ignore --stdin >/dev/null
echo "private_data_ignore=passed"

CERT_DB="${LEADS_CERT_DB:-runtime/v2-cert.db}"
"$PYTHON" -m leads_workstation --db "$CERT_DB" init-db >/dev/null
"$PYTHON" -m leads_workstation --db "$CERT_DB" stats >/dev/null
echo "sqlite_v2_schema=passed"

if [[ -n "${LEADS_POSTGRES_TEST_DSN:-}" && "${LEADS_ALLOW_TEST_RESET:-0}" != "1" ]]; then
  echo "LEADS_POSTGRES_TEST_DSN is set but LEADS_ALLOW_TEST_RESET is not 1" >&2
  exit 2
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  LEADS_POSTGRES_PASSWORD="${LEADS_POSTGRES_PASSWORD:-certification-config-only}" \
    docker compose -f docker-compose.v2.yml config --quiet
  echo "docker_compose_config=passed"
else
  echo "docker_compose_config=skipped_no_socket_access"
fi

mkdir -p runtime
"$PYTHON" - <<'PY'
import json, os, platform
from pathlib import Path
result={
    "certified": True,
    "python": platform.python_version(),
    "platform": platform.platform(),
    "schema_version": 2,
    "postgres_integration": bool(os.getenv("LEADS_POSTGRES_TEST_DSN")),
    "redis_integration": bool(os.getenv("REDIS_TEST_URL")),
    "private_data_ignored": True,
    "compile": "passed",
    "tests": "passed",
}
Path("runtime/v2-certification.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
PY

echo "V2_CERTIFICATION=PASS"
