from __future__ import annotations

from typing import Any

from .db import init_db
from .storage import db_connection

TABLE_ORDER = [
    "workstation_meta",
    "import_batches",
    "campaigns",
    "leads",
    "campaign_members",
    "lead_events",
    "duplicate_review",
    "candidate_leads",
    "lead_contact_points",
    "lead_assignments",
    "lead_lifecycle_transitions",
    "lead_suppressions",
    "outbox_events",
    "webhook_subscriptions",
]


def _table_columns(conn, table: str) -> list[str]:
    if conn.backend == "sqlite":
        rows = conn.raw.execute(f"PRAGMA table_info({table})").fetchall()
        return [row[1] for row in rows]
    rows = conn.raw.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [row["column_name"] if isinstance(row, dict) else row[0] for row in rows]


def _table_exists(conn, table: str) -> bool:
    if conn.backend == "sqlite":
        row = conn.raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return bool(row)
    row = conn.raw.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema=current_schema() AND table_name=%s
        """,
        (table,),
    ).fetchone()
    return bool(row)


def migrate_sqlite_to_postgres(
    sqlite_path,
    postgres_dsn: str,
    *,
    batch_size: int = 1000,
) -> dict[str, Any]:
    init_db(sqlite_path)
    init_db(postgres_dsn)
    results: dict[str, dict[str, int]] = {}

    with db_connection(sqlite_path) as source, db_connection(postgres_dsn) as target:
        if source.backend != "sqlite":
            raise ValueError("source must be SQLite")
        if target.backend != "postgres":
            raise ValueError("target must be PostgreSQL")

        for table in TABLE_ORDER:
            if not _table_exists(source, table) or not _table_exists(target, table):
                continue
            source_columns = _table_columns(source, table)
            target_columns = set(_table_columns(target, table))
            columns = [c for c in source_columns if c in target_columns]
            if not columns:
                continue
            placeholders = ",".join("?" for _ in columns)
            sql = (
                f"INSERT INTO {table}(" + ",".join(columns) + ") "
                f"VALUES({placeholders}) ON CONFLICT DO NOTHING"
            )
            selected = 0
            inserted = 0
            rows = source.execute(
                "SELECT " + ",".join(columns) + f" FROM {table}"
            )
            for row in rows:
                selected += 1
                values = tuple(row[c] for c in columns)
                cur = target.execute(sql, values)
                inserted += max(cur.rowcount, 0)
                if selected % max(1, int(batch_size)) == 0:
                    target.commit()
            target.commit()
            results[table] = {"selected": selected, "inserted": inserted}

        for table, column in (
            ("lead_events", "event_id"),
            ("duplicate_review", "review_id"),
        ):
            if not _table_exists(target, table):
                continue
            target.raw.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence(%s, %s),
                    GREATEST(COALESCE((SELECT MAX({column}) FROM {table}), 0), 1),
                    COALESCE((SELECT MAX({column}) FROM {table}), 0) > 0
                )
                """,
                (table, column),
            )
        target.commit()

    return {
        "source": str(sqlite_path),
        "target_backend": "postgres",
        "tables": results,
    }


def compare_database_counts(sqlite_path, postgres_dsn: str) -> dict[str, Any]:
    init_db(sqlite_path)
    init_db(postgres_dsn)
    comparison = {}
    with db_connection(sqlite_path) as source, db_connection(postgres_dsn) as target:
        for table in TABLE_ORDER:
            if not _table_exists(source, table) or not _table_exists(target, table):
                continue
            source_count = source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            target_count = target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            comparison[table] = {
                "sqlite": int(source_count),
                "postgres": int(target_count),
                "match": int(source_count) == int(target_count),
            }
    return {
        "tables": comparison,
        "all_match": all(item["match"] for item in comparison.values()),
    }
