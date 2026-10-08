from __future__ import annotations

import csv
import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .normalize import (
    fingerprint,
    first_present,
    identity_fingerprint,
    normalize_email,
    normalize_phone,
)
from .storage import database_backend, db_connection

SCHEMA_VERSION = 2

SQLITE_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS workstation_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_batches (
    batch_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    rows_seen INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    rows_duplicates INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    contact_name TEXT,
    country TEXT NOT NULL,
    state_province TEXT,
    city TEXT,
    business_category TEXT NOT NULL,
    campaign_source TEXT,
    email TEXT,
    normalized_email TEXT,
    phone TEXT,
    normalized_phone TEXT,
    website TEXT,
    status TEXT NOT NULL,
    owner TEXT,
    priority TEXT,
    notes TEXT,
    source_file TEXT,
    import_batch_id TEXT,
    duplicate_fingerprint TEXT NOT NULL UNIQUE,
    identity_fingerprint TEXT,
    verification_status TEXT,
    verification_score REAL,
    data_quality_status TEXT,
    campaign_id TEXT,
    assigned_agent TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    suppressed INTEGER NOT NULL DEFAULT 0,
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    consent_status TEXT,
    consent_source TEXT,
    consent_at TEXT,
    jurisdiction TEXT,
    last_contact_at TEXT,
    next_action_at TEXT,
    source_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(batch_id)
);
CREATE INDEX IF NOT EXISTS idx_leads_country ON leads(country);
CREATE INDEX IF NOT EXISTS idx_leads_category ON leads(business_category);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(normalized_email);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(normalized_phone);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(business_name);
CREATE TABLE IF NOT EXISTS lead_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_at TEXT NOT NULL,
    request_id TEXT,
    payload_json TEXT,
    FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_lead_events_lead ON lead_events(lead_id, event_at);
CREATE TABLE IF NOT EXISTS duplicate_review (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    matched_lead_id TEXT,
    reason TEXT NOT NULL,
    source_payload TEXT,
    source_file TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS candidate_leads (
    candidate_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    business_name TEXT NOT NULL,
    country TEXT NOT NULL,
    business_category TEXT NOT NULL,
    phones_json TEXT,
    email TEXT,
    notes TEXT,
    source_file TEXT NOT NULL,
    source_row INTEGER,
    source_fingerprint TEXT NOT NULL UNIQUE,
    match_lead_id TEXT,
    match_reason TEXT,
    disposition TEXT NOT NULL DEFAULT 'new',
    source_payload TEXT,
    created_at TEXT NOT NULL,
    promoted_at TEXT,
    FOREIGN KEY(match_lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_batch ON candidate_leads(batch_id, disposition);
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    campaign_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    campaign_type TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft',
    primary_supervisor TEXT,
    client_id TEXT,
    start_at TEXT,
    end_at TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaign_state ON campaigns(state);
CREATE TABLE IF NOT EXISTS campaign_members (
    campaign_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    member_role TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY(campaign_id, user_id),
    FOREIGN KEY(campaign_id) REFERENCES campaigns(campaign_id)
);
CREATE TABLE IF NOT EXISTS lead_contact_points (
    contact_point_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    label TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(lead_id, kind, normalized_value),
    FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_contact_normalized ON lead_contact_points(kind, normalized_value);
CREATE TABLE IF NOT EXISTS lead_assignments (
    assignment_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    campaign_id TEXT,
    from_agent TEXT,
    to_agent TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    reason TEXT,
    assigned_at TEXT NOT NULL,
    FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_assignments_lead ON lead_assignments(lead_id, assigned_at);
CREATE TABLE IF NOT EXISTS lead_lifecycle_transitions (
    transition_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    transitioned_at TEXT NOT NULL,
    FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_lead ON lead_lifecycle_transitions(lead_id, transitioned_at);
CREATE TABLE IF NOT EXISTS lead_suppressions (
    suppression_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    reason TEXT NOT NULL,
    jurisdiction TEXT,
    source TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lifted_at TEXT,
    FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_suppression_lead ON lead_suppressions(lead_id, active);
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(status, available_at);
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    secret_ref TEXT NOT NULL,
    event_types_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS workstation_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_batches (
    batch_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    rows_seen BIGINT NOT NULL DEFAULT 0,
    rows_inserted BIGINT NOT NULL DEFAULT 0,
    rows_duplicates BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    contact_name TEXT,
    country TEXT NOT NULL,
    state_province TEXT,
    city TEXT,
    business_category TEXT NOT NULL,
    campaign_source TEXT,
    email TEXT,
    normalized_email TEXT,
    phone TEXT,
    normalized_phone TEXT,
    website TEXT,
    status TEXT NOT NULL,
    owner TEXT,
    priority TEXT,
    notes TEXT,
    source_file TEXT,
    import_batch_id TEXT REFERENCES import_batches(batch_id),
    duplicate_fingerprint TEXT NOT NULL UNIQUE,
    identity_fingerprint TEXT,
    verification_status TEXT,
    verification_score DOUBLE PRECISION,
    data_quality_status TEXT,
    campaign_id TEXT,
    assigned_agent TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    suppressed INTEGER NOT NULL DEFAULT 0,
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    consent_status TEXT,
    consent_source TEXT,
    consent_at TEXT,
    jurisdiction TEXT,
    last_contact_at TEXT,
    next_action_at TEXT,
    source_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_country ON leads(country);
CREATE INDEX IF NOT EXISTS idx_leads_category ON leads(business_category);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(normalized_email);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(normalized_phone);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(business_name);
CREATE TABLE IF NOT EXISTS lead_events (
    event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_at TEXT NOT NULL,
    request_id TEXT,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_lead_events_lead ON lead_events(lead_id, event_at);
CREATE TABLE IF NOT EXISTS duplicate_review (
    review_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    matched_lead_id TEXT,
    reason TEXT NOT NULL,
    source_payload TEXT,
    source_file TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS candidate_leads (
    candidate_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    business_name TEXT NOT NULL,
    country TEXT NOT NULL,
    business_category TEXT NOT NULL,
    phones_json TEXT,
    email TEXT,
    notes TEXT,
    source_file TEXT NOT NULL,
    source_row INTEGER,
    source_fingerprint TEXT NOT NULL UNIQUE,
    match_lead_id TEXT REFERENCES leads(lead_id),
    match_reason TEXT,
    disposition TEXT NOT NULL DEFAULT 'new',
    source_payload TEXT,
    created_at TEXT NOT NULL,
    promoted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_candidate_batch ON candidate_leads(batch_id, disposition);
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    campaign_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    campaign_type TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft',
    primary_supervisor TEXT,
    client_id TEXT,
    start_at TEXT,
    end_at TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaign_state ON campaigns(state);
CREATE TABLE IF NOT EXISTS campaign_members (
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    user_id TEXT NOT NULL,
    member_role TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY(campaign_id, user_id)
);
CREATE TABLE IF NOT EXISTS lead_contact_points (
    contact_point_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    label TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(lead_id, kind, normalized_value)
);
CREATE INDEX IF NOT EXISTS idx_contact_normalized ON lead_contact_points(kind, normalized_value);
CREATE TABLE IF NOT EXISTS lead_assignments (
    assignment_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    campaign_id TEXT,
    from_agent TEXT,
    to_agent TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    reason TEXT,
    assigned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assignments_lead ON lead_assignments(lead_id, assigned_at);
CREATE TABLE IF NOT EXISTS lead_lifecycle_transitions (
    transition_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    transitioned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_lead ON lead_lifecycle_transitions(lead_id, transitioned_at);
CREATE TABLE IF NOT EXISTS lead_suppressions (
    suppression_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    channel TEXT NOT NULL,
    reason TEXT NOT NULL,
    jurisdiction TEXT,
    source TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lifted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_suppression_lead ON lead_suppressions(lead_id, active);
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(status, available_at);
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    secret_ref TEXT NOT NULL,
    event_types_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

LEAD_COLUMNS_V2 = {
    "identity_fingerprint": "TEXT",
    "campaign_id": "TEXT",
    "assigned_agent": "TEXT",
    "version": "INTEGER NOT NULL DEFAULT 1",
    "suppressed": "INTEGER NOT NULL DEFAULT 0",
    "do_not_contact": "INTEGER NOT NULL DEFAULT 0",
    "consent_status": "TEXT",
    "consent_source": "TEXT",
    "consent_at": "TEXT",
    "jurisdiction": "TEXT",
    "last_contact_at": "TEXT",
    "next_action_at": "TEXT",
}

LEAD_EVENT_COLUMNS_V2 = {
    "request_id": "TEXT",
}


class DuplicateLeadError(ValueError):
    pass


class ConcurrencyError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_columns(conn, table: str, desired: Mapping[str, str]) -> None:
    existing = conn.column_names(table)
    for name, ddl_type in desired.items():
        if name in existing:
            continue
        if conn.backend == "postgres":
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl_type}")
        else:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")


def _backfill_identity_fingerprints(conn) -> int:
    updated = 0
    rows = conn.execute(
        "SELECT lead_id,business_name,contact_name,country,city,email,phone "
        "FROM leads WHERE identity_fingerprint IS NULL OR identity_fingerprint=''"
    ).fetchall()
    for row in rows:
        item = dict(row)
        fp = identity_fingerprint(item)
        conn.execute(
            "UPDATE leads SET identity_fingerprint=? WHERE lead_id=?",
            (fp, item["lead_id"]),
        )
        updated += 1
        if updated % 5000 == 0:
            conn.commit()
    return updated


def init_db(db_path: str | Path) -> None:
    with db_connection(db_path) as conn:
        conn.executescript(POSTGRES_DDL if conn.backend == "postgres" else SQLITE_DDL)
        _ensure_columns(conn, "leads", LEAD_COLUMNS_V2)
        _ensure_columns(conn, "lead_events", LEAD_EVENT_COLUMNS_V2)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_assigned_agent ON leads(assigned_agent)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_identity ON leads(identity_fingerprint)"
        )
        current = conn.execute(
            "SELECT value FROM workstation_meta WHERE key='schema_version'"
        ).fetchone()
        current_version = int(current["value"]) if current else 0
        if current_version < 2:
            _backfill_identity_fingerprints(conn)
        conn.execute(
            "INSERT INTO workstation_meta(key,value) VALUES('schema_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )


def _canonical(row: Mapping[str, Any], source_file: str, batch_id: str) -> dict[str, Any]:
    contact = first_present(row, "full_name", "contact_name")
    if not contact:
        contact = " ".join(
            v
            for v in (
                first_present(row, "first_name"),
                first_present(row, "middle_name"),
                first_present(row, "last_name"),
            )
            if v
        )
    business = first_present(row, "company", "business_name") or contact or "(unknown)"
    category = first_present(row, "lead_category", "business_category") or "Uncategorized"
    country = first_present(row, "country")
    if not country or country.strip().lower() in {"country", "unknown", "n/a", "na"}:
        c = category.lower()
        if "spain" in c:
            country = "Spain"
        elif "dominican republic" in c:
            country = "Dominican Republic"
        elif "mexico" in c:
            country = "Mexico"
        elif "b2b marketing" in c:
            country = "United States"
        else:
            country = "Unknown"
    email = first_present(row, "email_primary", "email")
    phone = first_present(row, "mobile", "direct_phone", "company_phone", "phone")
    verification = first_present(row, "verification_status")
    try:
        score = float(first_present(row, "verification_score") or 0)
    except ValueError:
        score = 0.0
    stamp = now_utc()
    identity_source = dict(row)
    identity_source.pop("lead_id", None)
    return {
        "lead_id": first_present(row, "lead_id") or "lead_" + uuid.uuid4().hex,
        "business_name": business,
        "contact_name": contact or None,
        "country": country,
        "state_province": first_present(row, "state", "state_province") or None,
        "city": first_present(row, "city") or None,
        "business_category": category,
        "campaign_source": first_present(row, "source", "campaign_source") or None,
        "email": email or None,
        "normalized_email": normalize_email(
            first_present(row, "normalized_email_primary", "email_primary", "email")
        )
        or None,
        "phone": phone or None,
        "normalized_phone": normalize_phone(
            first_present(
                row,
                "normalized_phone_primary",
                "mobile",
                "direct_phone",
                "company_phone",
                "phone",
            )
        )
        or None,
        "website": first_present(row, "website") or None,
        "status": first_present(row, "status") or "New",
        "owner": first_present(row, "owner") or None,
        "priority": first_present(row, "priority") or None,
        "notes": first_present(row, "notes") or None,
        "source_file": source_file,
        "import_batch_id": batch_id,
        "duplicate_fingerprint": fingerprint(row),
        "identity_fingerprint": identity_fingerprint(identity_source),
        "verification_status": verification or None,
        "verification_score": score,
        "data_quality_status": first_present(row, "data_quality_status") or None,
        "campaign_id": first_present(row, "campaign_id") or None,
        "assigned_agent": first_present(row, "assigned_agent", "owner") or None,
        "version": 1,
        "suppressed": 0,
        "do_not_contact": 0,
        "consent_status": first_present(row, "consent_status") or None,
        "consent_source": first_present(row, "consent_source") or None,
        "consent_at": first_present(row, "consent_at") or None,
        "jurisdiction": first_present(row, "jurisdiction") or None,
        "last_contact_at": first_present(row, "last_contact_at") or None,
        "next_action_at": first_present(row, "next_action_at") or None,
        "source_payload": json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")),
        "created_at": stamp,
        "updated_at": stamp,
    }


COLUMNS = [
    "lead_id",
    "business_name",
    "contact_name",
    "country",
    "state_province",
    "city",
    "business_category",
    "campaign_source",
    "email",
    "normalized_email",
    "phone",
    "normalized_phone",
    "website",
    "status",
    "owner",
    "priority",
    "notes",
    "source_file",
    "import_batch_id",
    "duplicate_fingerprint",
    "identity_fingerprint",
    "verification_status",
    "verification_score",
    "data_quality_status",
    "campaign_id",
    "assigned_agent",
    "version",
    "suppressed",
    "do_not_contact",
    "consent_status",
    "consent_source",
    "consent_at",
    "jurisdiction",
    "last_contact_at",
    "next_action_at",
    "source_payload",
    "created_at",
    "updated_at",
]


def _emit_outbox(
    conn,
    event_type: str,
    aggregate_id: str,
    payload: Mapping[str, Any],
    idempotency_key: str | None = None,
    aggregate_type: str = "lead",
) -> str:
    event_id = "evt_" + uuid.uuid4().hex
    stamp = now_utc()
    key = idempotency_key or f"{event_type}:{aggregate_id}:{event_id}"
    conn.execute(
        """
        INSERT INTO outbox_events(
            event_id,event_type,aggregate_type,aggregate_id,payload_json,
            idempotency_key,status,attempt_count,available_at,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            event_id,
            event_type,
            aggregate_type,
            aggregate_id,
            json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")),
            key,
            "pending",
            0,
            stamp,
            stamp,
        ),
    )
    return event_id


def _upsert_contact_point(
    conn,
    lead_id: str,
    kind: str,
    value: str | None,
    *,
    source: str,
    verification_status: str = "unverified",
    primary: bool = True,
) -> None:
    if not value:
        return
    normalized = normalize_email(value) if kind == "email" else normalize_phone(value)
    if not normalized:
        return
    stamp = now_utc()
    if primary:
        conn.execute(
            "UPDATE lead_contact_points SET is_primary=0,updated_at=? WHERE lead_id=? AND kind=?",
            (stamp, lead_id, kind),
        )
    contact_id = "cp_" + hashlib.sha256(
        f"{lead_id}:{kind}:{normalized}".encode()
    ).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO lead_contact_points(
            contact_point_id,lead_id,kind,value,normalized_value,label,is_primary,
            verification_status,source,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(lead_id,kind,normalized_value) DO UPDATE SET
            value=excluded.value,
            is_primary=excluded.is_primary,
            verification_status=excluded.verification_status,
            source=excluded.source,
            updated_at=excluded.updated_at
        """,
        (
            contact_id,
            lead_id,
            kind,
            value,
            normalized,
            "primary" if primary else None,
            1 if primary else 0,
            verification_status,
            source,
            stamp,
            stamp,
        ),
    )


def import_csv(
    db_path: str | Path,
    csv_path: str | Path,
    batch_id: str | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    src = Path(csv_path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    source_hash = sha256_file(src)
    batch_id = batch_id or src.stem + "-" + source_hash[:12]
    with db_connection(db_path) as conn:
        prior = conn.execute(
            "SELECT * FROM import_batches WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if prior and prior["status"] == "completed":
            return dict(prior)
        conn.execute(
            "INSERT INTO import_batches(batch_id,source_path,source_sha256,started_at,status) "
            "VALUES(?,?,?,?,?) ON CONFLICT(batch_id) DO UPDATE SET "
            "source_path=excluded.source_path,source_sha256=excluded.source_sha256,"
            "started_at=excluded.started_at,status='running',error=NULL",
            (batch_id, str(src), source_hash, now_utc(), "running"),
        )
        seen = inserted = duplicates = 0
        marks = ",".join("?" for _ in COLUMNS)
        sql = "INSERT OR IGNORE INTO leads(" + ",".join(COLUMNS) + ") VALUES(" + marks + ")"
        try:
            with src.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames:
                    raise ValueError("CSV has no header")
                for row in reader:
                    seen += 1
                    item = _canonical(row, str(src), batch_id)
                    cur = conn.execute(sql, tuple(item[c] for c in COLUMNS))
                    if cur.rowcount == 1:
                        inserted += 1
                        conn.execute(
                            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
                            "VALUES(?,?,?,?,?)",
                            (
                                item["lead_id"],
                                "imported",
                                "lead-importer",
                                now_utc(),
                                json.dumps(
                                    {"batch_id": batch_id, "source_file": str(src)},
                                    separators=(",", ":"),
                                ),
                            ),
                        )
                        _upsert_contact_point(
                            conn,
                            item["lead_id"],
                            "email",
                            item["email"],
                            source="import",
                            verification_status=item["verification_status"] or "unverified",
                        )
                        _upsert_contact_point(
                            conn,
                            item["lead_id"],
                            "phone",
                            item["phone"],
                            source="import",
                            verification_status=item["verification_status"] or "unverified",
                        )
                    else:
                        duplicates += 1
                        match = conn.execute(
                            "SELECT lead_id FROM leads WHERE duplicate_fingerprint=?",
                            (item["duplicate_fingerprint"],),
                        ).fetchone()
                        conn.execute(
                            "INSERT INTO duplicate_review("
                            "fingerprint,matched_lead_id,reason,source_payload,source_file,created_at,status"
                            ") VALUES(?,?,?,?,?,?,?)",
                            (
                                item["duplicate_fingerprint"],
                                match["lead_id"] if match else None,
                                "deterministic identity fingerprint already exists",
                                item["source_payload"],
                                str(src),
                                now_utc(),
                                "auto-collapsed",
                            ),
                        )
                    if seen % 5000 == 0:
                        conn.commit()
            conn.execute(
                "UPDATE import_batches SET completed_at=?,rows_seen=?,rows_inserted=?,"
                "rows_duplicates=?,status='completed' WHERE batch_id=?",
                (now_utc(), seen, inserted, duplicates, batch_id),
            )
            conn.commit()
        except Exception as exc:
            conn.execute(
                "UPDATE import_batches SET completed_at=?,rows_seen=?,rows_inserted=?,"
                "rows_duplicates=?,status='failed',error=? WHERE batch_id=?",
                (now_utc(), seen, inserted, duplicates, repr(exc), batch_id),
            )
            conn.commit()
            raise
        return dict(
            conn.execute(
                "SELECT * FROM import_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
        )


def stats(db_path: str | Path) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return {
            "backend": conn.backend,
            "schema_version": SCHEMA_VERSION,
            "total_leads": conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
            "with_email": conn.execute(
                "SELECT COUNT(*) FROM leads WHERE normalized_email IS NOT NULL"
            ).fetchone()[0],
            "with_phone": conn.execute(
                "SELECT COUNT(*) FROM leads WHERE normalized_phone IS NOT NULL"
            ).fetchone()[0],
            "suppressed": conn.execute(
                "SELECT COUNT(*) FROM leads WHERE suppressed=1"
            ).fetchone()[0],
            "do_not_contact": conn.execute(
                "SELECT COUNT(*) FROM leads WHERE do_not_contact=1"
            ).fetchone()[0],
            "campaign_count": conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],
            "pending_outbox": conn.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE status='pending'"
            ).fetchone()[0],
            "countries": [
                dict(r)
                for r in conn.execute(
                    "SELECT country,COUNT(*) count FROM leads GROUP BY country "
                    "ORDER BY count DESC LIMIT 25"
                )
            ],
            "categories": [
                dict(r)
                for r in conn.execute(
                    "SELECT business_category,COUNT(*) count FROM leads "
                    "GROUP BY business_category ORDER BY count DESC LIMIT 50"
                )
            ],
            "statuses": [
                dict(r)
                for r in conn.execute(
                    "SELECT status,COUNT(*) count FROM leads GROUP BY status "
                    "ORDER BY count DESC LIMIT 50"
                )
            ],
            "import_batches": [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM import_batches ORDER BY started_at DESC LIMIT 20"
                )
            ],
        }


def list_leads(
    db_path: str | Path,
    limit: int = 50,
    offset: int = 0,
    country: str | None = None,
    category: str | None = None,
    status: str | None = None,
    q: str | None = None,
    campaign_id: str | None = None,
    assigned_agent: str | None = None,
    suppressed: bool | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    where = []
    params: list[Any] = []
    if country:
        where.append("country=?")
        params.append(country)
    if category:
        where.append("business_category=?")
        params.append(category)
    if status:
        where.append("status=?")
        params.append(status)
    if campaign_id:
        where.append("campaign_id=?")
        params.append(campaign_id)
    if assigned_agent:
        where.append("assigned_agent=?")
        params.append(assigned_agent)
    if suppressed is not None:
        where.append("suppressed=?")
        params.append(1 if suppressed else 0)
    if q:
        like = "%" + q.strip() + "%"
        where.append(
            "(business_name LIKE ? OR contact_name LIKE ? OR email LIKE ? OR phone LIKE ?)"
        )
        params.extend([like, like, like, like])
    sql = (
        "SELECT lead_id,business_name,contact_name,country,state_province,city,"
        "business_category,email,phone,website,status,owner,priority,"
        "verification_status,verification_score,data_quality_status,campaign_id,"
        "assigned_agent,version,suppressed,do_not_contact,consent_status,"
        "jurisdiction,last_contact_at,next_action_at,created_at,updated_at FROM leads"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    if database_backend(db_path) == "postgres":
        sql += " ORDER BY LOWER(business_name) LIMIT ? OFFSET ?"
    else:
        sql += " ORDER BY business_name COLLATE NOCASE LIMIT ? OFFSET ?"
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
    with db_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_lead(db_path: str | Path, lead_id: str) -> dict[str, Any] | None:
    init_db(db_path)
    with db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return dict(row) if row else None


def create_lead(
    db_path: str | Path,
    payload: Mapping[str, Any],
    actor: str = "local-user",
    request_id: str | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    required = ("business_name", "country", "business_category")
    missing = [k for k in required if not first_present(payload, k)]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

    source_identity = dict(payload)
    source_identity.pop("lead_id", None)
    candidate_identity_fp = identity_fingerprint(source_identity)
    lead_id = first_present(payload, "lead_id") or "lead_" + uuid.uuid4().hex
    stamp = now_utc()
    email = first_present(payload, "email")
    phone = first_present(payload, "phone")
    item = {
        "lead_id": lead_id,
        "business_name": first_present(payload, "business_name"),
        "contact_name": first_present(payload, "contact_name") or None,
        "country": first_present(payload, "country"),
        "state_province": first_present(payload, "state_province") or None,
        "city": first_present(payload, "city") or None,
        "business_category": first_present(payload, "business_category"),
        "campaign_source": first_present(payload, "campaign_source") or None,
        "email": email or None,
        "normalized_email": normalize_email(email) or None,
        "phone": phone or None,
        "normalized_phone": normalize_phone(phone) or None,
        "website": first_present(payload, "website") or None,
        "status": first_present(payload, "status") or "New",
        "owner": first_present(payload, "owner") or None,
        "priority": first_present(payload, "priority") or None,
        "notes": first_present(payload, "notes") or None,
        "source_file": None,
        "import_batch_id": None,
        "duplicate_fingerprint": candidate_identity_fp,
        "identity_fingerprint": candidate_identity_fp,
        "verification_status": first_present(payload, "verification_status") or None,
        "verification_score": float(payload.get("verification_score") or 0),
        "data_quality_status": first_present(payload, "data_quality_status") or None,
        "campaign_id": first_present(payload, "campaign_id") or None,
        "assigned_agent": first_present(payload, "assigned_agent", "owner") or None,
        "version": 1,
        "suppressed": 1 if payload.get("suppressed") else 0,
        "do_not_contact": 1 if payload.get("do_not_contact") else 0,
        "consent_status": first_present(payload, "consent_status") or None,
        "consent_source": first_present(payload, "consent_source") or None,
        "consent_at": first_present(payload, "consent_at") or None,
        "jurisdiction": first_present(payload, "jurisdiction") or None,
        "last_contact_at": first_present(payload, "last_contact_at") or None,
        "next_action_at": first_present(payload, "next_action_at") or None,
        "source_payload": json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":")
        ),
        "created_at": stamp,
        "updated_at": stamp,
    }
    marks = ",".join("?" for _ in COLUMNS)
    sql = "INSERT INTO leads(" + ",".join(COLUMNS) + ") VALUES(" + marks + ")"
    with db_connection(db_path) as conn:
        duplicate_clauses = ["identity_fingerprint=?"]
        duplicate_params: list[Any] = [candidate_identity_fp]
        if item["normalized_email"]:
            duplicate_clauses.append("normalized_email=?")
            duplicate_params.append(item["normalized_email"])
        if item["normalized_phone"]:
            duplicate_clauses.append("normalized_phone=?")
            duplicate_params.append(item["normalized_phone"])
        existing = conn.execute(
            "SELECT lead_id FROM leads WHERE "
            + " OR ".join(duplicate_clauses)
            + " LIMIT 1",
            duplicate_params,
        ).fetchone()
        if existing:
            raise DuplicateLeadError("possible duplicate of " + existing["lead_id"])
        conn.execute(sql, tuple(item[c] for c in COLUMNS))
        conn.execute(
            "INSERT INTO lead_events("
            "lead_id,event_type,actor,event_at,request_id,payload_json"
            ") VALUES(?,?,?,?,?,?)",
            (
                lead_id,
                "created",
                actor,
                stamp,
                request_id,
                json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")),
            ),
        )
        _upsert_contact_point(
            conn,
            lead_id,
            "email",
            item["email"],
            source="api",
            verification_status=item["verification_status"] or "unverified",
        )
        _upsert_contact_point(
            conn,
            lead_id,
            "phone",
            item["phone"],
            source="api",
            verification_status=item["verification_status"] or "unverified",
        )
        _emit_outbox(
            conn,
            "lead.created",
            lead_id,
            {"lead_id": lead_id, "version": 1, "campaign_id": item["campaign_id"]},
        )
        row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return dict(row)


_EDITABLE_FIELDS = {
    "business_name",
    "contact_name",
    "country",
    "state_province",
    "city",
    "business_category",
    "campaign_source",
    "email",
    "phone",
    "website",
    "status",
    "owner",
    "priority",
    "notes",
    "verification_status",
    "verification_score",
    "data_quality_status",
    "campaign_id",
    "assigned_agent",
    "consent_status",
    "consent_source",
    "consent_at",
    "jurisdiction",
    "last_contact_at",
    "next_action_at",
}


def update_lead(
    db_path: str | Path,
    lead_id: str,
    changes: Mapping[str, Any],
    actor: str = "local-user",
    expected_version: int | None = None,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    clean = {k: v for k, v in changes.items() if k in _EDITABLE_FIELDS}
    if not clean:
        raise ValueError("no editable fields supplied")
    if "email" in clean:
        clean["normalized_email"] = normalize_email(clean.get("email")) or None
    if "phone" in clean:
        clean["normalized_phone"] = normalize_phone(clean.get("phone")) or None

    with db_connection(db_path) as conn:
        before_row = conn.execute(
            "SELECT * FROM leads WHERE lead_id=?", (lead_id,)
        ).fetchone()
        if not before_row:
            return None
        before = dict(before_row)
        current_version = int(before.get("version") or 1)
        if expected_version is not None and current_version != int(expected_version):
            raise ConcurrencyError(
                f"lead version mismatch: expected {expected_version}, current {current_version}"
            )

        identity_fields = {
            "business_name",
            "contact_name",
            "country",
            "city",
            "email",
            "phone",
        }
        if identity_fields.intersection(clean):
            merged = dict(before)
            merged.update(clean)
            new_identity_fp = identity_fingerprint(merged)
            duplicate_clauses = ["identity_fingerprint=?"]
            duplicate_params: list[Any] = [new_identity_fp]
            merged_email = normalize_email(merged.get("email")) or None
            merged_phone = normalize_phone(merged.get("phone")) or None
            if merged_email:
                duplicate_clauses.append("normalized_email=?")
                duplicate_params.append(merged_email)
            if merged_phone:
                duplicate_clauses.append("normalized_phone=?")
                duplicate_params.append(merged_phone)
            duplicate_params.append(lead_id)
            duplicate = conn.execute(
                "SELECT lead_id FROM leads WHERE ("
                + " OR ".join(duplicate_clauses)
                + ") AND lead_id<>? LIMIT 1",
                duplicate_params,
            ).fetchone()
            if duplicate:
                raise DuplicateLeadError("possible duplicate of " + duplicate["lead_id"])
            clean["identity_fingerprint"] = new_identity_fp

        clean["version"] = current_version + 1
        clean["updated_at"] = now_utc()
        assignments = ",".join(k + "=?" for k in clean)
        conn.execute(
            "UPDATE leads SET " + assignments + " WHERE lead_id=?",
            tuple(clean.values()) + (lead_id,),
        )
        conn.execute(
            "INSERT INTO lead_events("
            "lead_id,event_type,actor,event_at,request_id,payload_json"
            ") VALUES(?,?,?,?,?,?)",
            (
                lead_id,
                "updated",
                actor,
                now_utc(),
                request_id,
                json.dumps(
                    {"version": current_version + 1, "changes": clean},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )
        if "email" in clean:
            _upsert_contact_point(
                conn,
                lead_id,
                "email",
                clean.get("email"),
                source="api-update",
                verification_status=clean.get("verification_status")
                or before.get("verification_status")
                or "unverified",
            )
        if "phone" in clean:
            _upsert_contact_point(
                conn,
                lead_id,
                "phone",
                clean.get("phone"),
                source="api-update",
                verification_status=clean.get("verification_status")
                or before.get("verification_status")
                or "unverified",
            )
        _emit_outbox(
            conn,
            "lead.updated",
            lead_id,
            {
                "lead_id": lead_id,
                "version": current_version + 1,
                "changed_fields": sorted(clean.keys()),
            },
        )
        after = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return dict(after)


def lead_events(
    db_path: str | Path, lead_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lead_events WHERE lead_id=? "
                "ORDER BY event_id DESC LIMIT ?",
                (lead_id, max(1, min(int(limit), 500))),
            )
        ]
