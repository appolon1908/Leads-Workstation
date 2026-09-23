from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
ALLOWED_STATUS = {"new","qualified","contacted","follow_up","converted","not_interested","invalid","archived"}
ALLOWED_PRIORITY = {None,"","low","medium","high","urgent"}

def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None

def normalize_phone(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")

def fingerprint(data: dict[str, Any]) -> str:
    parts = [
        (clean_text(data.get("business_name")) or "").casefold(),
        (clean_text(data.get("email")) or "").casefold(),
        normalize_phone(clean_text(data.get("phone"))),
        (clean_text(data.get("country")) or "").casefold(),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def vcf_escape(value: Any) -> str:
    text = clean_text(value) or ""
    return (
        text.replace("\\", "\\\\")
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )

def db_kwargs() -> dict[str, Any]:
    required = ["LEADS_DB_HOST","LEADS_DB_PORT","LEADS_DB_NAME","LEADS_APP_USER","LEADS_APP_PASSWORD"]
    missing = [x for x in required if not os.getenv(x)]
    if missing:
        raise RuntimeError("Missing database settings: " + ", ".join(missing))
    return {
        "host": os.environ["LEADS_DB_HOST"],
        "port": int(os.environ["LEADS_DB_PORT"]),
        "dbname": os.environ["LEADS_DB_NAME"],
        "user": os.environ["LEADS_APP_USER"],
        "password": os.environ["LEADS_APP_PASSWORD"],
        "row_factory": dict_row,
    }

@contextmanager
def db():
    with psycopg.connect(**db_kwargs()) as conn:
        with conn.cursor() as cur:
            yield conn, cur

class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_name: str = Field(min_length=1)
    contact_name: str | None = None
    country: str = Field(min_length=1)
    state_province: str | None = None
    city: str | None = None
    business_category: str = Field(min_length=1)
    campaign_source: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    status: str = "new"
    owner_name: str | None = None
    priority: str | None = None
    last_contact_at: datetime | None = None
    next_action: str | None = None
    notes: str | None = None
    source_file: str | None = None

    @field_validator("status")
    @classmethod
    def status_ok(cls, v: str) -> str:
        if v not in ALLOWED_STATUS:
            raise ValueError("invalid status")
        return v

    @field_validator("priority")
    @classmethod
    def priority_ok(cls, v: str | None) -> str | None:
        if v not in ALLOWED_PRIORITY:
            raise ValueError("invalid priority")
        return v or None

class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    business_name: str | None = None
    contact_name: str | None = None
    country: str | None = None
    state_province: str | None = None
    city: str | None = None
    business_category: str | None = None
    campaign_source: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    status: str | None = None
    owner_name: str | None = None
    priority: str | None = None
    last_contact_at: datetime | None = None
    next_action: str | None = None
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def status_ok(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_STATUS:
            raise ValueError("invalid status")
        return v

    @field_validator("priority")
    @classmethod
    def priority_ok(cls, v: str | None) -> str | None:
        if v not in ALLOWED_PRIORITY:
            raise ValueError("invalid priority")
        return v or None

class ActivityCreate(BaseModel):
    activity_type: str = "comment"
    body: str = Field(min_length=1, max_length=10000)
    actor: str = "dashboard"

app = FastAPI(title="Codestra Leads Workstation", version="0.1.0")

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

@app.get("/api/health")
def health():
    try:
        with db() as (_, cur):
            cur.execute("select current_database() db, current_user usr, now() ts")
            row = cur.fetchone()
        return {"ok": True, "database": row["db"], "user": row["usr"], "time": row["ts"]}
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc

@app.get("/api/summary")
def summary():
    with db() as (_, cur):
        cur.execute("""
          select
            count(*)::int total,
            count(*) filter (where created_at::date=current_date)::int new_today,
            count(*) filter (where status='follow_up')::int follow_up,
            count(*) filter (where status='converted')::int converted,
            count(*) filter (where email is null and phone is null)::int no_contact,
            count(distinct country)::int countries,
            count(distinct business_category)::int categories
          from leads.leads where status <> 'archived'
        """)
        base = cur.fetchone()
        cur.execute("select status, count(*)::int count from leads.leads group by status order by status")
        statuses = cur.fetchall()
        cur.execute("select country, count(*)::int count from leads.leads where status <> 'archived' group by country order by count(*) desc, country limit 12")
        countries = cur.fetchall()
        cur.execute("select business_category, count(*)::int count from leads.leads where status <> 'archived' group by business_category order by count(*) desc, business_category limit 12")
        categories = cur.fetchall()
    return {**base, "statuses": statuses, "top_countries": countries, "top_categories": categories}

@app.get("/api/options")
def options():
    with db() as (_, cur):
        def vals(col: str):
            cur.execute(f"select distinct {col} value from leads.leads where {col} is not null and btrim({col})<>'' order by 1")
            return [r["value"] for r in cur.fetchall()]
        return {
            "countries": vals("country"),
            "business_categories": vals("business_category"),
            "owners": vals("owner_name"),
            "statuses": sorted(ALLOWED_STATUS),
            "priorities": ["low","medium","high","urgent"],
        }

@app.get("/api/leads")
def list_leads(
    q: str | None = None,
    country: str | None = None,
    business_category: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
):
    where, params = [], []
    if q:
        where.append("""(business_name ilike %s or coalesce(contact_name,'') ilike %s or coalesce(email,'') ilike %s
          or coalesce(phone,'') ilike %s or coalesce(website,'') ilike %s or coalesce(notes,'') ilike %s)""")
        params.extend([f"%{q}%"]*6)
    for col, val in [("country",country),("business_category",business_category),("status",status),("owner_name",owner),("priority",priority)]:
        if val:
            where.append(f"{col}=%s"); params.append(val)
    sql = "select * from leads.leads"
    if where:
        sql += " where " + " and ".join(where)
    sql += " order by updated_at desc limit %s"
    params.append(limit)
    with db() as (_, cur):
        cur.execute(sql, params)
        return cur.fetchall()

@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: UUID):
    with db() as (_, cur):
        cur.execute("select * from leads.leads where lead_id=%s", (lead_id,))
        lead = cur.fetchone()
        if not lead:
            raise HTTPException(404, "lead not found")
        cur.execute("select * from leads.lead_activity where lead_id=%s order by created_at desc limit 100", (lead_id,))
        lead["activity"] = cur.fetchall()
        return lead

@app.post("/api/leads", status_code=201)
def create_lead(payload: LeadCreate):
    data = payload.model_dump()
    data["business_name"] = clean_text(data["business_name"])
    data["country"] = clean_text(data["country"])
    data["business_category"] = clean_text(data["business_category"])
    if not data["business_name"] or not data["country"] or not data["business_category"]:
        raise HTTPException(422, "business_name, country and business_category are required")
    for k in list(data):
        if isinstance(data[k], str):
            data[k] = clean_text(data[k])
    fp = fingerprint(data)
    with db() as (_, cur):
        cur.execute("select lead_id,business_name from leads.leads where duplicate_fingerprint=%s and status<>'archived' limit 1", (fp,))
        dup = cur.fetchone()
        if dup:
            raise HTTPException(409, {"message":"possible exact duplicate","existing":jsonable_encoder(dup)})
        cols = list(data.keys()) + ["duplicate_fingerprint"]
        vals = [data[k] for k in data] + [fp]
        placeholders = ",".join(["%s"]*len(vals))
        cur.execute(f"insert into leads.leads ({','.join(cols)}) values ({placeholders}) returning *", vals)
        lead = cur.fetchone()
        cur.execute("insert into lead_audit.lead_changes(lead_id,action,new_data,actor) values(%s,'create',%s,'dashboard')",
                    (lead["lead_id"], Jsonb(jsonable_encoder(lead))))
        cur.execute("insert into lead_ops.outbox(event_type,aggregate_id,payload) values('lead.created',%s,%s)",
                    (lead["lead_id"], Jsonb({"lead_id":str(lead["lead_id"])})))
        return lead

@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: UUID, payload: LeadUpdate):
    changes = payload.model_dump(exclude_unset=True)
    expected = changes.pop("version")
    if not changes:
        return get_lead(lead_id)
    for k, v in list(changes.items()):
        if isinstance(v, str):
            changes[k] = clean_text(v)
    with db() as (_, cur):
        cur.execute("select * from leads.leads where lead_id=%s for update", (lead_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(404, "lead not found")
        if old["version"] != expected:
            raise HTTPException(409, {"message":"record changed","current_version":old["version"]})
        merged = dict(old); merged.update(changes)
        if not clean_text(merged["business_name"]) or not clean_text(merged["country"]) or not clean_text(merged["business_category"]):
            raise HTTPException(422, "business_name, country and business_category are required")
        changes["duplicate_fingerprint"] = fingerprint(merged)
        cur.execute("""select lead_id,business_name from leads.leads
                       where duplicate_fingerprint=%s and lead_id<>%s and status<>'archived' limit 1""",
                    (changes["duplicate_fingerprint"], lead_id))
        dup = cur.fetchone()
        if dup:
            raise HTTPException(409, {"message":"possible exact duplicate","existing":jsonable_encoder(dup)})
        sets = ", ".join(f"{k}=%s" for k in changes)
        vals = list(changes.values()) + [lead_id]
        cur.execute(f"update leads.leads set {sets} where lead_id=%s returning *", vals)
        new = cur.fetchone()
        cur.execute("insert into lead_audit.lead_changes(lead_id,action,old_data,new_data,actor) values(%s,'update',%s,%s,'dashboard')",
                    (lead_id, Jsonb(jsonable_encoder(old)), Jsonb(jsonable_encoder(new))))
        cur.execute("insert into lead_ops.outbox(event_type,aggregate_id,payload) values('lead.updated',%s,%s)",
                    (lead_id, Jsonb({"lead_id":str(lead_id),"fields":list(changes.keys())})))
        return new

@app.post("/api/leads/{lead_id}/activity", status_code=201)
def add_activity(lead_id: UUID, payload: ActivityCreate):
    with db() as (_, cur):
        cur.execute("select 1 from leads.leads where lead_id=%s", (lead_id,))
        if not cur.fetchone():
            raise HTTPException(404, "lead not found")
        cur.execute("""insert into leads.lead_activity(lead_id,activity_type,body,actor)
                       values(%s,%s,%s,%s) returning *""",
                    (lead_id,payload.activity_type,payload.body,payload.actor))
        return cur.fetchone()

@app.get("/api/data-quality")
def data_quality():
    with db() as (_, cur):
        cur.execute("""
          select
            count(*) filter (where email is null and phone is null)::int missing_contact,
            count(*) filter (where owner_name is null)::int unassigned,
            count(*) filter (where next_action is null and status in ('new','qualified','contacted','follow_up'))::int missing_next_action
          from leads.leads where status<>'archived'
        """)
        metrics = cur.fetchone()
        cur.execute("""
          select duplicate_fingerprint, count(*)::int count, array_agg(lead_id::text) lead_ids
          from leads.leads where duplicate_fingerprint is not null and status<>'archived'
          group by duplicate_fingerprint having count(*)>1 order by count(*) desc limit 100
        """)
        duplicates = cur.fetchall()
        cur.execute("select * from lead_ops.duplicate_review where status='pending' order by created_at desc limit 100")
        review = cur.fetchall()
    return {**metrics, "duplicate_groups":duplicates, "review_queue":review}

@app.get("/api/export/thunderbird.vcf")
def export_thunderbird_vcf(
    q: str | None = None,
    country: str | None = None,
    business_category: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    limit: int = Query(5000, ge=1, le=20000),
):
    """Read-only Thunderbird address-book export of canonical local leads."""
    where, params = ["status <> 'archived'"], []
    if q:
        where.append("""(business_name ilike %s or coalesce(contact_name,'') ilike %s or coalesce(email,'') ilike %s
          or coalesce(phone,'') ilike %s or coalesce(website,'') ilike %s or coalesce(notes,'') ilike %s)""")
        params.extend([f"%{q}%"] * 6)
    for col, val in [
        ("country", country),
        ("business_category", business_category),
        ("status", status),
        ("owner_name", owner),
        ("priority", priority),
    ]:
        if val:
            where.append(f"{col}=%s")
            params.append(val)
    sql = """select lead_id,business_name,contact_name,country,business_category,email,phone
             from leads.leads where """ + " and ".join(where) + " order by updated_at desc limit %s"
    params.append(limit)
    with db() as (_, cur):
        cur.execute(sql, params)
        rows = cur.fetchall()

    cards: list[str] = []
    for lead in rows:
        if not lead.get("email") and not lead.get("phone"):
            continue
        display = lead.get("contact_name") or lead.get("business_name") or lead.get("email") or lead.get("phone") or "Lead"
        lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{vcf_escape(display)}"]
        if lead.get("business_name"):
            lines.append(f"ORG:{vcf_escape(lead['business_name'])}")
        if lead.get("email"):
            lines.append(f"EMAIL;TYPE=INTERNET:{vcf_escape(lead['email'])}")
        if lead.get("phone"):
            lines.append(f"TEL;TYPE=CELL:{vcf_escape(lead['phone'])}")
        if lead.get("country"):
            lines.append(f"ADR;TYPE=WORK:;;;;;;{vcf_escape(lead['country'])}")
        if lead.get("business_category"):
            lines.append(f"CATEGORIES:{vcf_escape(lead['business_category'])}")
        lines.extend([f"UID:codestra-lead-{lead['lead_id']}", "END:VCARD"])
        cards.extend(lines)
    content = "\r\n".join(cards) + ("\r\n" if cards else "")
    return Response(
        content=content,
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="codestra-leads-thunderbird.vcf"'},
    )

@app.get("/api/import-batches")
def import_batches():
    with db() as (_, cur):
        cur.execute("select * from lead_ops.import_batches order by created_at desc limit 200")
        return cur.fetchall()

@app.post("/api/import/preview")
async def import_preview(file: UploadFile = File(...)):
    name = file.filename or "upload.csv"
    if not name.lower().endswith(".csv"):
        raise HTTPException(415, "preview currently supports CSV; other sources go through Meltano connectors")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "file exceeds 50 MB preview limit")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        fields = reader.fieldnames or []
        required = {"business_name","country","business_category"}
        missing = sorted(required - set(fields))
        rows, fps = [], {}
        total = invalid = 0
        for i, row in enumerate(reader, start=2):
            total += 1
            if any(not clean_text(row.get(k)) for k in required):
                invalid += 1
            fp = fingerprint(row)
            fps[fp] = fps.get(fp, 0) + 1
            if len(rows) < 20:
                rows.append({"row":i, **row})
        duplicates = sum(v-1 for v in fps.values() if v>1)
        return {
            "filename":name, "bytes":len(raw), "columns":fields, "rows":total,
            "missing_required_columns":missing, "invalid_required_rows":invalid,
            "duplicate_rows_within_file":duplicates, "sample":rows,
            "writes_performed":0,
            "message":"Preview only. No database writes or imports were performed."
        }
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "CSV must be UTF-8 for dashboard preview") from exc
