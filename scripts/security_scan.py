from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATH_PREFIXES = (
    "data/private/",
    "runtime/",
)
FORBIDDEN_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
)
SECRET_PATTERNS = [
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:sk-proj|ghp|github_pat)_[A-Za-z0-9_\-]{20,}\b"),
]
TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".sh",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".html",
    ".css",
    ".js",
}


def candidate_files() -> list[str]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def main() -> int:
    errors: list[str] = []
    files = candidate_files()

    for rel in files:
        normalized = rel.replace("\\", "/")
        if normalized.startswith(FORBIDDEN_PATH_PREFIXES):
            errors.append(f"forbidden private/runtime path: {normalized}")
        if normalized.lower().endswith(FORBIDDEN_SUFFIXES):
            errors.append(f"forbidden database/key artifact: {normalized}")
        if normalized == ".env" or (
            normalized.startswith(".env.")
            and not normalized.endswith(".example")
        ):
            errors.append(f"forbidden environment secret file: {normalized}")

        path = ROOT / rel
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > 2_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"credential-like content detected: {normalized}")

    auth = ROOT / "src/leads_workstation/auth.py"
    if auth.exists():
        text = auth.read_text(encoding="utf-8", errors="replace")
        if "V2 API is fail-closed" not in text:
            errors.append("auth.py does not contain fail-closed production guard")

    compose = ROOT / "docker-compose.v2.yml"
    if compose.exists():
        text = compose.read_text(encoding="utf-8", errors="replace")
        if "127.0.0.1:" not in text:
            errors.append("V2 compose does not bind the API to loopback by default")

    if errors:
        print("SECURITY_SCAN=FAIL")
        for error in errors:
            print(" -", error)
        return 1

    print(f"SECURITY_SCAN=PASS files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
