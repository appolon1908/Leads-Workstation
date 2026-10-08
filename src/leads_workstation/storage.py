from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_POSTGRES_PREFIXES = ("postgresql://", "postgres://")
_QMARK = re.compile(r"\?")


class HybridRow(dict):
    """Mapping row that also supports SQLite-style positional indexing."""

    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _hybrid_row_factory(cursor):
    description = cursor.description
    if description is None:
        return lambda values: HybridRow((), values)
    columns = [column.name for column in description]

    def make_row(values):
        return HybridRow(columns, values)

    return make_row


class ConnectionAdapter:
    def __init__(self, raw: Any, backend: str):
        self.raw = raw
        self.backend = backend

    def _sql(self, sql: str) -> str:
        if self.backend == "sqlite":
            return sql
        normalized = sql
        if normalized.lstrip().upper().startswith("PRAGMA "):
            return ""
        normalized = normalized.replace(" COLLATE NOCASE", "")
        if normalized.lstrip().upper().startswith("INSERT OR IGNORE INTO"):
            normalized = re.sub(
                r"(?i)^\s*INSERT\s+OR\s+IGNORE\s+INTO",
                "INSERT INTO",
                normalized,
                count=1,
            )
            normalized = normalized.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return _QMARK.sub("%s", normalized)

    def execute(self, sql: str, params: Iterable[Any] = ()):
        sql = self._sql(sql)
        if not sql:
            return _NoopCursor()
        return self.raw.execute(sql, tuple(params))

    def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]):
        sql = self._sql(sql)
        if not sql:
            return _NoopCursor()
        return self.raw.executemany(sql, list(params_seq))

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.raw.executescript(script)
            return
        for statement in _split_sql(script):
            sql = self._sql(statement)
            if sql:
                self.raw.execute(sql)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    def column_names(self, table: str) -> set[str]:
        if self.backend == "sqlite":
            return {
                row[1]
                for row in self.raw.execute(f"PRAGMA table_info({table})").fetchall()
            }
        rows = self.raw.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name=%s
            """,
            (table,),
        ).fetchall()
        return {row["column_name"] for row in rows}


class _NoopCursor:
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


def _split_sql(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


def is_postgres_target(target: str | Path) -> bool:
    return isinstance(target, str) and target.startswith(_POSTGRES_PREFIXES)


def connect(target: str | Path) -> ConnectionAdapter:
    if is_postgres_target(target):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires the 'postgres' extra: "
                "pip install -e '.[postgres]'"
            ) from exc
        raw = psycopg.connect(str(target), row_factory=_hybrid_row_factory)
        return ConnectionAdapter(raw, "postgres")

    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("PRAGMA busy_timeout=5000")
    return ConnectionAdapter(raw, "sqlite")


@contextmanager
def db_connection(target: str | Path):
    conn = connect(target)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def database_backend(target: str | Path) -> str:
    return "postgres" if is_postgres_target(target) else "sqlite"
