from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TRACKED_PREFIXES = (
    "data/private/",
    "runtime/",
)

SECRET_PATTERNS = {
    "github_token": re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b"),
    "openai_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".ps1", ".sh",
    ".ini", ".cfg", ".conf", ".sql", ".html", ".css", ".js", ".ts",
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    problems: list[str] = []
    tracked = tracked_files()

    for rel in tracked:
        normalized = rel.replace("\\", "/")
        if normalized == ".env" or normalized.startswith(".env."):
            if normalized != ".env.example":
                problems.append(f"tracked environment file: {normalized}")
        if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES):
            problems.append(f"private/runtime path is tracked: {normalized}")

        path = ROOT / rel
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            ".gitignore",
            ".gitattributes",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                problems.append(f"possible {name} in {normalized}")

    if problems:
        for problem in problems:
            print("SECURITY_FAIL:", problem)
        return 1

    print(f"Security scan passed for {len(tracked)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
