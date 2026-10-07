from __future__ import annotations
import csv
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from .normalize import fingerprint, first_present, normalize_email, normalize_phone

SCHEMA_VERSION = 1

DDL = """
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
    verification_status TEXT,
    verification_score REAL,
    data_quality_status TEXT,
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
"""

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def connect(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

@contextmanager
def db_connection(db_path: str | Path):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(db_path: str | Path) -> None:
    with db_connection(db_path) as conn:
        conn.executescript(DDL)
        conn.execute(
            "INSERT INTO workstation_meta(key,value) VALUES('schema_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )

def _canonical(row: Mapping[str, Any], source_file: str, batch_id: str) -> dict[str, Any]:
    contact = first_present(row, "full_name", "contact_name")
    if not contact:
        contact = " ".join(v for v in (
            first_present(row, "first_name"),
            first_present(row, "middle_name"),
            first_present(row, "last_name"),
        ) if v)
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
        "normalized_email": normalize_email(first_present(row, "normalized_email_primary", "email_primary", "email")) or None,
        "phone": phone or None,
        "normalized_phone": normalize_phone(first_present(row, "normalized_phone_primary", "mobile", "direct_phone", "company_phone", "phone")) or None,
        "website": first_present(row, "website") or None,
        "status": verification or first_present(row, "status") or "New",
        "owner": first_present(row, "owner") or None,
        "priority": first_present(row, "priority") or None,
        "notes": first_present(row, "notes") or None,
        "source_file": source_file,
        "import_batch_id": batch_id,
        "duplicate_fingerprint": fingerprint(row),
        "verification_status": verification or None,
        "verification_score": score,
        "data_quality_status": first_present(row, "data_quality_status") or None,
        "source_payload": json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")),
        "created_at": stamp,
        "updated_at": stamp,
    }

COLUMNS = [
    "lead_id","business_name","contact_name","country","state_province","city",
    "business_category","campaign_source","email","normalized_email","phone",
    "normalized_phone","website","status","owner","priority","notes","source_file",
    "import_batch_id","duplicate_fingerprint","verification_status","verification_score",
    "data_quality_status","source_payload","created_at","updated_at",
]

def import_csv(db_path: str | Path, csv_path: str | Path, batch_id: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    src = Path(csv_path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    source_hash = sha256_file(src)
    batch_id = batch_id or src.stem + "-" + source_hash[:12]
    with db_connection(db_path) as conn:
        prior = conn.execute("SELECT * FROM import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if prior and prior["status"] == "completed":
            return dict(prior)
        conn.execute(
            "INSERT INTO import_batches(batch_id,source_path,source_sha256,started_at,status) VALUES(?,?,?,?,?) "
            "ON CONFLICT(batch_id) DO UPDATE SET source_path=excluded.source_path,source_sha256=excluded.source_sha256,started_at=excluded.started_at,status='running',error=NULL",
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
                            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) VALUES(?,?,?,?,?)",
                            (item["lead_id"], "imported", "lead-importer", now_utc(),
                             json.dumps({"batch_id": batch_id, "source_file": str(src)}, separators=(",", ":"))),
                        )
                    else:
                        duplicates += 1
                        match = conn.execute(
                            "SELECT lead_id FROM leads WHERE duplicate_fingerprint=?",
                            (item["duplicate_fingerprint"],),
                        ).fetchone()
                        conn.execute(
                            "INSERT INTO duplicate_review(fingerprint,matched_lead_id,reason,source_payload,source_file,created_at,status) VALUES(?,?,?,?,?,?,?)",
                            (item["duplicate_fingerprint"], match["lead_id"] if match else None,
                             "deterministic identity fingerprint already exists", item["source_payload"],
                             str(src), now_utc(), "auto-collapsed"),
                        )
                    if seen % 5000 == 0:
                        conn.commit()
            conn.execute(
                "UPDATE import_batches SET completed_at=?,rows_seen=?,rows_inserted=?,rows_duplicates=?,status='completed' WHERE batch_id=?",
                (now_utc(), seen, inserted, duplicates, batch_id),
            )
            conn.commit()
        except Exception as exc:
            conn.execute(
                "UPDATE import_batches SET completed_at=?,rows_seen=?,rows_inserted=?,rows_duplicates=?,status='failed',error=? WHERE batch_id=?",
                (now_utc(), seen, inserted, duplicates, repr(exc), batch_id),
            )
            conn.commit()
            raise
        return dict(conn.execute("SELECT * FROM import_batches WHERE batch_id=?", (batch_id,)).fetchone())

def stats(db_path: str | Path) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return {
            "total_leads": conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
            "with_email": conn.execute("SELECT COUNT(*) FROM leads WHERE normalized_email IS NOT NULL").fetchone()[0],
            "with_phone": conn.execute("SELECT COUNT(*) FROM leads WHERE normalized_phone IS NOT NULL").fetchone()[0],
            "countries": [dict(r) for r in conn.execute("SELECT country,COUNT(*) count FROM leads GROUP BY country ORDER BY count DESC LIMIT 25")],
            "categories": [dict(r) for r in conn.execute("SELECT business_category,COUNT(*) count FROM leads GROUP BY business_category ORDER BY count DESC LIMIT 25")],
            "import_batches": [dict(r) for r in conn.execute("SELECT * FROM import_batches ORDER BY started_at DESC LIMIT 20")],
        }

def list_leads(db_path: str | Path, limit: int = 50, offset: int = 0, country: str | None = None, category: str | None = None, status: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    where = []
    params: list[Any] = []
    if country:
        where.append("country=?"); params.append(country)
    if category:
        where.append("business_category=?"); params.append(category)
    if status:
        where.append("status=?"); params.append(status)
    if q:
        like = "%" + q.strip() + "%"
        where.append("(business_name LIKE ? OR contact_name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        params.extend([like, like, like, like])
    sql = "SELECT lead_id,business_name,contact_name,country,state_province,city,business_category,email,phone,website,status,verification_status,verification_score,data_quality_status,created_at,updated_at FROM leads"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY business_name COLLATE NOCASE LIMIT ? OFFSET ?"
    params.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
    with db_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params)]

def get_lead(db_path: str | Path, lead_id: str) -> dict[str, Any] | None:
    init_db(db_path)
    with db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return dict(row) if row else None


class DuplicateLeadError(ValueError):
    pass

def create_lead(db_path: str | Path, payload: Mapping[str, Any], actor: str = "local-user") -> dict[str, Any]:
    init_db(db_path)
    required = ("business_name", "country", "business_category")
    missing = [k for k in required if not first_present(payload, k)]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

    source_identity = dict(payload)
    candidate_fp = fingerprint(source_identity)
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
        "duplicate_fingerprint": candidate_fp,
        "verification_status": first_present(payload, "verification_status") or None,
        "verification_score": float(payload.get("verification_score") or 0),
        "data_quality_status": first_present(payload, "data_quality_status") or None,
        "source_payload": json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")),
        "created_at": stamp,
        "updated_at": stamp,
    }
    marks = ",".join("?" for _ in COLUMNS)
    sql = "INSERT INTO leads(" + ",".join(COLUMNS) + ") VALUES(" + marks + ")"
    with db_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT lead_id FROM leads WHERE duplicate_fingerprint=?", (candidate_fp,)
        ).fetchone()
        if existing:
            raise DuplicateLeadError("possible duplicate of " + existing["lead_id"])
        conn.execute(sql, tuple(item[c] for c in COLUMNS))
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) VALUES(?,?,?,?,?)",
            (lead_id, "created", actor, stamp, json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))),
        )
        row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return dict(row)

_EDITABLE_FIELDS = {
    "business_name", "contact_name", "country", "state_province", "city",
    "business_category", "campaign_source", "email", "phone", "website",
    "status", "owner", "priority", "notes", "verification_status",
    "verification_score", "data_quality_status",
}

def update_lead(db_path: str | Path, lead_id: str, changes: Mapping[str, Any], actor: str = "local-user") -> dict[str, Any] | None:
    init_db(db_path)
    clean = {k: v for k, v in changes.items() if k in _EDITABLE_FIELDS}
    if not clean:
        raise ValueError("no editable fields supplied")
    if "email" in clean:
        clean["normalized_email"] = normalize_email(clean.get("email")) or None
    if "phone" in clean:
        clean["normalized_phone"] = normalize_phone(clean.get("phone")) or None
    clean["updated_at"] = now_utc()

    with db_connection(db_path) as conn:
        before = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if not before:
            return None
        assignments = ",".join(k + "=?" for k in clean)
        conn.execute(
            "UPDATE leads SET " + assignments + " WHERE lead_id=?",
            tuple(clean.values()) + (lead_id,),
        )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) VALUES(?,?,?,?,?)",
            (
                lead_id,
                "updated",
                actor,
                now_utc(),
                json.dumps({"changes": clean}, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        after = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return dict(after)

def lead_events(db_path: str | Path, lead_id: str, limit: int = 100) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lead_events WHERE lead_id=? ORDER BY event_id DESC LIMIT ?",
                (lead_id, max(1, min(int(limit), 500))),
            )
        ]
