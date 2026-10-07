from __future__ import annotations
import argparse
import json
from pathlib import Path

from .api import serve
from .candidates import candidate_summary, list_candidates, promote_new_candidates, stage_appraiser_batch
from .db import import_csv, init_db, sha256_file, stats
from .manifest import write_manifest


def parser():
    p = argparse.ArgumentParser(prog="leads-workstation")
    p.add_argument("--db", default="runtime/leads.db")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    imp = sub.add_parser("import-csv")
    imp.add_argument("csv_path")
    imp.add_argument("--batch-id")

    sub.add_parser("stats")

    v = sub.add_parser("verify-file")
    v.add_argument("path")

    m = sub.add_parser("manifest")
    m.add_argument("root")
    m.add_argument("output")

    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--allow-network", action="store_true")

    stage = sub.add_parser("stage-appraisers")
    stage.add_argument("xlsx_path")
    stage.add_argument("--batch-id", default="appraisers-2019")

    cs = sub.add_parser("candidate-summary")
    cs.add_argument("--batch-id")

    cl = sub.add_parser("candidates")
    cl.add_argument("--batch-id")
    cl.add_argument("--disposition")
    cl.add_argument("--limit", type=int, default=100)

    promote = sub.add_parser("promote-candidates")
    promote.add_argument("batch_id")

    return p


def main(argv=None):
    args = parser().parse_args(argv)
    db = Path(args.db)

    if args.command == "init-db":
        init_db(db)
        print(json.dumps({"ok": True, "db": str(db.resolve())}, indent=2))
        return 0

    if args.command == "import-csv":
        print(json.dumps(import_csv(db, args.csv_path, args.batch_id), indent=2, ensure_ascii=False))
        return 0

    if args.command == "stats":
        print(json.dumps(stats(db), indent=2, ensure_ascii=False))
        return 0

    if args.command == "verify-file":
        p = Path(args.path)
        print(json.dumps({"path": str(p.resolve()), "sha256": sha256_file(p), "bytes": p.stat().st_size}, indent=2))
        return 0

    if args.command == "manifest":
        write_manifest(args.root, args.output)
        print(json.dumps({"ok": True, "output": str(Path(args.output).resolve())}, indent=2))
        return 0

    if args.command == "serve":
        serve(str(db), args.host, args.port, args.allow_network)
        return 0

    if args.command == "stage-appraisers":
        print(json.dumps(stage_appraiser_batch(db, args.xlsx_path, args.batch_id), indent=2, ensure_ascii=False))
        return 0

    if args.command == "candidate-summary":
        print(json.dumps(candidate_summary(db, args.batch_id), indent=2, ensure_ascii=False))
        return 0

    if args.command == "candidates":
        print(json.dumps(list_candidates(db, args.batch_id, args.disposition, args.limit), indent=2, ensure_ascii=False))
        return 0

    if args.command == "promote-candidates":
        print(json.dumps(promote_new_candidates(db, args.batch_id), indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
