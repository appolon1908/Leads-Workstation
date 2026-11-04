from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .api import serve
from .backup import create_encrypted_backup, decrypt_file
from .candidates import (
    candidate_summary,
    list_candidates,
    promote_new_candidates,
    stage_appraiser_batch,
)
from .db import import_csv, init_db, sha256_file, stats
from .imports import preview_csv, stage_csv_candidates
from .manifest import write_manifest
from .migrate import compare_database_counts, migrate_sqlite_to_postgres
from .platform import backfill_contact_points, backfill_identity_fingerprints
from .worker import process_outbox_once, run_worker


def parser():
    p = argparse.ArgumentParser(prog="leads-workstation")
    p.add_argument(
        "--db",
        default=os.getenv("LEADS_DATABASE_URL", "runtime/leads.db"),
        help="SQLite path or PostgreSQL DSN. Defaults to LEADS_DATABASE_URL or runtime/leads.db.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    imp = sub.add_parser("import-csv")
    imp.add_argument("csv_path")
    imp.add_argument("--batch-id")

    preview = sub.add_parser("preview-import")
    preview.add_argument("csv_path")
    preview.add_argument("--profile", default="generic")
    preview.add_argument("--limit", type=int, default=20)

    stage_generic = sub.add_parser("stage-import")
    stage_generic.add_argument("csv_path")
    stage_generic.add_argument("--profile", default="generic")
    stage_generic.add_argument("--batch-id")
    stage_generic.add_argument("--max-rows", type=int)

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

    backfill = sub.add_parser("backfill-contacts")
    backfill.add_argument("--limit", type=int)

    identities = sub.add_parser("backfill-identities")
    identities.add_argument("--limit", type=int)

    backup = sub.add_parser("backup-encrypted")
    backup.add_argument("destination")
    backup.add_argument(
        "--secret-ref",
        default=os.getenv("LEADS_BACKUP_SECRET_REF"),
    )

    decrypt = sub.add_parser("decrypt-backup")
    decrypt.add_argument("source")
    decrypt.add_argument("destination")
    decrypt.add_argument(
        "--secret-ref",
        default=os.getenv("LEADS_BACKUP_SECRET_REF"),
    )

    migrate = sub.add_parser("migrate-to-postgres")
    migrate.add_argument(
        "--postgres-dsn",
        default=os.getenv("LEADS_POSTGRES_DSN"),
    )
    migrate.add_argument("--batch-size", type=int, default=1000)

    compare = sub.add_parser("compare-databases")
    compare.add_argument(
        "--postgres-dsn",
        default=os.getenv("LEADS_POSTGRES_DSN"),
    )

    outbox = sub.add_parser("process-outbox")
    outbox.add_argument("--limit", type=int, default=50)

    worker = sub.add_parser("worker")
    worker.add_argument("--poll-seconds", type=float, default=2.0)

    return p


def _require_postgres_dsn(value: str | None) -> str:
    if not value:
        raise SystemExit(
            "PostgreSQL DSN is required. Pass --postgres-dsn or set LEADS_POSTGRES_DSN."
        )
    if not value.startswith(("postgresql://", "postgres://")):
        raise SystemExit("PostgreSQL DSN must begin with postgresql:// or postgres://")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    db = args.db

    if args.command == "init-db":
        init_db(db)
        print(json.dumps({"ok": True, "db": db}, indent=2))
        return 0

    if args.command == "import-csv":
        print(
            json.dumps(
                import_csv(db, args.csv_path, args.batch_id),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "preview-import":
        print(
            json.dumps(
                preview_csv(
                    args.csv_path,
                    profile_name=args.profile,
                    limit=args.limit,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "stage-import":
        print(
            json.dumps(
                stage_csv_candidates(
                    db,
                    args.csv_path,
                    profile_name=args.profile,
                    batch_id=args.batch_id,
                    max_rows=args.max_rows,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "stats":
        print(json.dumps(stats(db), indent=2, ensure_ascii=False))
        return 0

    if args.command == "verify-file":
        p = Path(args.path)
        print(
            json.dumps(
                {
                    "path": str(p.resolve()),
                    "sha256": sha256_file(p),
                    "bytes": p.stat().st_size,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "manifest":
        write_manifest(args.root, args.output)
        print(
            json.dumps(
                {"ok": True, "output": str(Path(args.output).resolve())},
                indent=2,
            )
        )
        return 0

    if args.command == "serve":
        serve(db, args.host, args.port, args.allow_network)
        return 0

    if args.command == "stage-appraisers":
        print(
            json.dumps(
                stage_appraiser_batch(db, args.xlsx_path, args.batch_id),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "candidate-summary":
        print(
            json.dumps(
                candidate_summary(db, args.batch_id),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "candidates":
        print(
            json.dumps(
                list_candidates(
                    db,
                    args.batch_id,
                    args.disposition,
                    args.limit,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "promote-candidates":
        print(
            json.dumps(
                promote_new_candidates(db, args.batch_id),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "backfill-contacts":
        print(
            json.dumps(
                backfill_contact_points(db, args.limit),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "backfill-identities":
        print(
            json.dumps(
                backfill_identity_fingerprints(db, args.limit),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "backup-encrypted":
        if not args.secret_ref:
            raise SystemExit("--secret-ref or LEADS_BACKUP_SECRET_REF is required")
        print(
            json.dumps(
                create_encrypted_backup(db, args.destination, args.secret_ref),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "decrypt-backup":
        if not args.secret_ref:
            raise SystemExit("--secret-ref or LEADS_BACKUP_SECRET_REF is required")
        print(
            json.dumps(
                decrypt_file(args.source, args.destination, args.secret_ref),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "migrate-to-postgres":
        dsn = _require_postgres_dsn(args.postgres_dsn)
        print(
            json.dumps(
                migrate_sqlite_to_postgres(
                    db,
                    dsn,
                    batch_size=args.batch_size,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "compare-databases":
        dsn = _require_postgres_dsn(args.postgres_dsn)
        print(
            json.dumps(
                compare_database_counts(db, dsn),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "process-outbox":
        print(
            json.dumps(
                process_outbox_once(db, limit=args.limit),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "worker":
        run_worker(db, poll_seconds=args.poll_seconds)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
