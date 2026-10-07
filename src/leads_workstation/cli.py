from __future__ import annotations
import argparse
import json
from pathlib import Path
from .api import serve
from .db import import_csv, init_db, sha256_file, stats
from .manifest import write_manifest

def parser():
    p = argparse.ArgumentParser(prog="leads-workstation")
    p.add_argument("--db", default="runtime/leads.db")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    imp = sub.add_parser("import-csv"); imp.add_argument("csv_path"); imp.add_argument("--batch-id")
    sub.add_parser("stats")
    v = sub.add_parser("verify-file"); v.add_argument("path")
    m = sub.add_parser("manifest"); m.add_argument("root"); m.add_argument("output")
    s = sub.add_parser("serve"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765); s.add_argument("--allow-network", action="store_true")
    return p

def main(argv=None):
    args = parser().parse_args(argv)
    db = Path(args.db)
    if args.command == "init-db":
        init_db(db); print(json.dumps({"ok": True, "db": str(db.resolve())}, indent=2)); return 0
    if args.command == "import-csv":
        print(json.dumps(import_csv(db, args.csv_path, args.batch_id), indent=2, ensure_ascii=False)); return 0
    if args.command == "stats":
        print(json.dumps(stats(db), indent=2, ensure_ascii=False)); return 0
    if args.command == "verify-file":
        p = Path(args.path); print(json.dumps({"path": str(p.resolve()), "sha256": sha256_file(p), "bytes": p.stat().st_size}, indent=2)); return 0
    if args.command == "manifest":
        write_manifest(args.root, args.output); print(json.dumps({"ok": True, "output": str(Path(args.output).resolve())}, indent=2)); return 0
    if args.command == "serve":
        serve(str(db), args.host, args.port, args.allow_network); return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
