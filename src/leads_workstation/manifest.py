from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path

EXTENSIONS = {".csv",".xlsx",".xls",".json",".jsonl",".sql",".vcf",".pdf",".docx",".eml",".mp3",".zip"}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def csv_rows(path: Path):
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)
            return sum(1 for _ in reader)
    except Exception:
        return None

def build_manifest(root):
    base = Path(root).resolve()
    rows = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix.lower() in EXTENSIONS:
            rows.append({
                "relative_path": str(p.relative_to(base)).replace("\\", "/"),
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
                "csv_rows": csv_rows(p),
            })
    return {"root": str(base), "file_count": len(rows), "total_bytes": sum(x["size_bytes"] for x in rows), "files": rows}

def write_manifest(root, output):
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_manifest(root), indent=2, ensure_ascii=False), encoding="utf-8")
