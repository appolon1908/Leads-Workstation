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

class DuplicateReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    import_batch_id: UUID | None = None
    source_row: int | None = Field(default=None, ge=1)
    fingerprint: str = Field(min_length=1, max_length=128)
    candidate_lead_id: UUID | None = None
    match_score: float | None = Field(default=None, ge=0, le=1)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="dashboard", min_length=1, max_length=200)

class DuplicateReviewResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    candidate_lead_id: UUID | None = None
    actor: str = Field(default="dashboard", min_length=1, max_length=200)

    @field_validator("status")
    @classmethod
    def status_ok(cls, v: str) -> str:
        if v not in {"accepted", "rejected", "merged"}:
            raise ValueError("status must be accepted, rejected or merged")
        return v


class LeadCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    source_file: str | None = None

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

class PromotionCandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    import_batch_id: UUID
    source_row: int = Field(ge=1)
    source_fingerprint: str = Field(min_length=1, max_length=128)
    lead: LeadCandidate = Field(default_factory=LeadCandidate)
    actor: str = Field(default="dashboard", min_length=1, max_length=200)

class PromotionCandidateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead: LeadCandidate | None = None
    decision: str | None = None
    review_reason: str | None = Field(default=None, max_length=2000)
    actor: str = Field(default="dashboard", min_length=1, max_length=200)

    @field_validator("decision")
    @classmethod
    def decision_ok(cls, v: str | None) -> str | None:
        if v is not None and v not in {"pending", "review", "approve", "reject"}:
            raise ValueError("decision must be pending, review, approve or reject")
        return v

class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(default="dashboard", min_length=1, max_length=200)

REQUIRED_CANONICAL_FIELDS = ("business_name", "country", "business_category")

def normalize_candidate(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for key, value in list(out.items()):
        if isinstance(value, str):
            out[key] = clean_text(value)
    if out.get("status") is None:
        out["status"] = "new"
    return out

def candidate_missing(data: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_CANONICAL_FIELDS if not clean_text(data.get(field))]

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

@app.get("/api/data-quality/duplicate-reviews")
def duplicate_reviews(
    status: str | None = Query("pending"),
    limit: int = Query(100, ge=1, le=1000),
):
    if status is not None and status not in {"pending", "accepted", "rejected", "merged"}:
        raise HTTPException(422, "invalid duplicate review status")
    with db() as (_, cur):
        if status is None:
            cur.execute("select * from lead_ops.duplicate_review order by created_at desc limit %s", (limit,))
        else:
            cur.execute("select * from lead_ops.duplicate_review where status=%s order by created_at desc limit %s", (status, limit))
        return cur.fetchall()

@app.post("/api/data-quality/duplicate-reviews", status_code=201)
def queue_duplicate_review(payload: DuplicateReviewCreate):
    data = payload.model_dump()
    data["fingerprint"] = clean_text(data["fingerprint"])
    data["actor"] = clean_text(data["actor"]) or "dashboard"
    if not data["fingerprint"]:
        raise HTTPException(422, "fingerprint is required")
    with db() as (_, cur):
        if data["import_batch_id"] is not None:
            cur.execute("select 1 from lead_ops.import_batches where import_batch_id=%s", (data["import_batch_id"],))
            if not cur.fetchone():
                raise HTTPException(404, "import batch not found")
        if data["candidate_lead_id"] is not None:
            cur.execute("select 1 from leads.leads where lead_id=%s", (data["candidate_lead_id"],))
            if not cur.fetchone():
                raise HTTPException(404, "candidate lead not found")
        cur.execute("""
          select * from lead_ops.duplicate_review
          where status='pending'
            and fingerprint=%s
            and import_batch_id is not distinct from %s
            and source_row is not distinct from %s
            and candidate_lead_id is not distinct from %s
          order by created_at desc limit 1
        """, (data["fingerprint"], data["import_batch_id"], data["source_row"], data["candidate_lead_id"]))
        existing = cur.fetchone()
        if existing:
            return {"created": False, "review": existing, "canonical_writes_performed": 0}
        cur.execute("""
          insert into lead_ops.duplicate_review(
            import_batch_id,source_row,fingerprint,candidate_lead_id,match_score,raw_payload,status
          ) values(%s,%s,%s,%s,%s,%s,'pending') returning *
        """, (
            data["import_batch_id"], data["source_row"], data["fingerprint"], data["candidate_lead_id"],
            data["match_score"], Jsonb(data["raw_payload"]),
        ))
        review = cur.fetchone()
        cur.execute(
            "insert into lead_audit.lead_changes(lead_id,action,new_data,actor) values(%s,'duplicate_review.queued',%s,%s)",
            (data["candidate_lead_id"], Jsonb(jsonable_encoder(review)), data["actor"]),
        )
        return {"created": True, "review": review, "canonical_writes_performed": 0}

@app.patch("/api/data-quality/duplicate-reviews/{review_id}")
def resolve_duplicate_review(review_id: int, payload: DuplicateReviewResolve):
    with db() as (_, cur):
        cur.execute("select * from lead_ops.duplicate_review where review_id=%s for update", (review_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(404, "duplicate review not found")
        candidate = payload.candidate_lead_id or old["candidate_lead_id"]
        if candidate is not None:
            cur.execute("select 1 from leads.leads where lead_id=%s", (candidate,))
            if not cur.fetchone():
                raise HTTPException(404, "candidate lead not found")
        if payload.status == "merged" and candidate is None:
            raise HTTPException(422, "merged review requires candidate_lead_id")
        if old["status"] != "pending":
            if old["status"] == payload.status and old["candidate_lead_id"] == candidate:
                return {"changed": False, "review": old, "canonical_writes_performed": 0}
            raise HTTPException(409, {"message": "review already resolved", "status": old["status"]})
        cur.execute("""
          update lead_ops.duplicate_review
          set status=%s,candidate_lead_id=%s,resolved_at=now()
          where review_id=%s returning *
        """, (payload.status, candidate, review_id))
        new = cur.fetchone()
        cur.execute(
            "insert into lead_audit.lead_changes(lead_id,action,old_data,new_data,actor) values(%s,%s,%s,%s,%s)",
            (candidate, f"duplicate_review.{payload.status}", Jsonb(jsonable_encoder(old)), Jsonb(jsonable_encoder(new)), payload.actor),
        )
        return {"changed": True, "review": new, "canonical_writes_performed": 0}

@app.get("/api/promotion-candidates")
def promotion_candidates(
    status: str | None = None,
    import_batch_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    if status is not None and status not in {"pending", "review", "approved", "promoted", "rejected"}:
        raise HTTPException(422, "invalid promotion candidate status")
    where, params = [], []
    if status is not None:
        where.append("status=%s")
        params.append(status)
    if import_batch_id is not None:
        where.append("import_batch_id=%s")
        params.append(import_batch_id)
    sql = "select * from lead_ops.promotion_candidates"
    if where:
        sql += " where " + " and ".join(where)
    sql += " order by created_at desc limit %s"
    params.append(limit)
    with db() as (_, cur):
        cur.execute(sql, params)
        return cur.fetchall()

@app.post("/api/promotion-candidates", status_code=201)
def queue_promotion_candidate(payload: PromotionCandidateCreate):
    actor = clean_text(payload.actor) or "dashboard"
    source_fingerprint = clean_text(payload.source_fingerprint)
    if not source_fingerprint:
        raise HTTPException(422, "source_fingerprint is required")
    lead = normalize_candidate(payload.lead.model_dump(exclude_unset=True))
    missing = candidate_missing(lead)
    initial_status = "review" if missing else "pending"
    review_reason = "missing required canonical fields: " + ", ".join(missing) if missing else None
    with db() as (_, cur):
        cur.execute("select * from lead_ops.import_batches where import_batch_id=%s", (payload.import_batch_id,))
        batch = cur.fetchone()
        if not batch:
            raise HTTPException(404, "import batch not found")
        if batch["status"] not in {"previewed", "running", "completed"}:
            raise HTTPException(409, {"message": "import batch is not eligible for candidate queueing", "status": batch["status"]})
        cur.execute("""
          select 1 from lead_ops.import_row_manifest
          where import_batch_id=%s and source_row=%s and source_fingerprint=%s
        """, (payload.import_batch_id, payload.source_row, source_fingerprint))
        if not cur.fetchone():
            raise HTTPException(409, "candidate provenance does not match the staged-row manifest")
        cur.execute("""
          select * from lead_ops.promotion_candidates
          where import_batch_id=%s and source_row=%s and source_fingerprint=%s
          limit 1
        """, (payload.import_batch_id, payload.source_row, source_fingerprint))
        existing = cur.fetchone()
        if existing:
            if existing["normalized_payload"] == lead:
                return {"created": False, "candidate": existing, "canonical_writes_performed": 0}
            raise HTTPException(409, {"message": "candidate provenance already exists with different normalized payload", "candidate_id": str(existing["candidate_id"])})
        cur.execute("""
          insert into lead_ops.promotion_candidates(
            import_batch_id,source_row,source_fingerprint,normalized_payload,status,review_reason
          ) values(%s,%s,%s,%s,%s,%s) returning *
        """, (payload.import_batch_id, payload.source_row, source_fingerprint, Jsonb(jsonable_encoder(lead)), initial_status, review_reason))
        candidate = cur.fetchone()
        cur.execute(
            "insert into lead_audit.lead_changes(lead_id,action,new_data,actor) values(NULL,'promotion_candidate.queued',%s,%s)",
            (Jsonb(jsonable_encoder(candidate)), actor),
        )
        return {"created": True, "candidate": candidate, "missing_required_fields": missing, "canonical_writes_performed": 0}

@app.patch("/api/promotion-candidates/{candidate_id}")
def review_promotion_candidate(candidate_id: UUID, payload: PromotionCandidateReview):
    actor = clean_text(payload.actor) or "dashboard"
    with db() as (_, cur):
        cur.execute("select * from lead_ops.promotion_candidates where candidate_id=%s for update", (candidate_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(404, "promotion candidate not found")
        if old["status"] == "promoted":
            raise HTTPException(409, "promoted candidate is immutable")
        updated_payload = dict(old["normalized_payload"] or {})
        if payload.lead is not None:
            patch = payload.lead.model_dump(exclude_unset=True)
            for key, value in patch.items():
                updated_payload[key] = clean_text(value) if isinstance(value, str) else value
        updated_payload = normalize_candidate(updated_payload)
        missing = candidate_missing(updated_payload)
        decision = payload.decision
        if decision == "approve":
            if missing:
                raise HTTPException(422, {"message": "candidate is missing required canonical fields", "missing": missing})
            try:
                canonical = LeadCreate.model_validate(updated_payload)
            except Exception as exc:
                raise HTTPException(422, f"candidate failed canonical validation: {exc}") from exc
            fp = fingerprint(canonical.model_dump())
            cur.execute("select lead_id,business_name from leads.leads where duplicate_fingerprint=%s and status<>'archived' limit 1", (fp,))
            duplicate = cur.fetchone()
            if duplicate:
                raise HTTPException(409, {"message": "canonical exact duplicate exists", "existing": jsonable_encoder(duplicate)})
            new_status = "approved"
        elif decision == "reject":
            new_status = "rejected"
        elif decision == "review":
            new_status = "review"
        elif decision == "pending":
            new_status = "review" if missing else "pending"
        else:
            new_status = "review" if missing else "pending"
        reason = clean_text(payload.review_reason)
        if new_status == "review" and not reason and missing:
            reason = "missing required canonical fields: " + ", ".join(missing)
        cur.execute("""
          update lead_ops.promotion_candidates
          set normalized_payload=%s,status=%s,review_reason=%s,updated_at=now()
          where candidate_id=%s returning *
        """, (Jsonb(jsonable_encoder(updated_payload)), new_status, reason, candidate_id))
        new = cur.fetchone()
        if old["normalized_payload"] == new["normalized_payload"] and old["status"] == new["status"] and old["review_reason"] == new["review_reason"]:
            return {"changed": False, "candidate": new, "missing_required_fields": missing, "canonical_writes_performed": 0}
        cur.execute(
            "insert into lead_audit.lead_changes(lead_id,action,old_data,new_data,actor) values(NULL,%s,%s,%s,%s)",
            (f"promotion_candidate.{new_status}", Jsonb(jsonable_encoder(old)), Jsonb(jsonable_encoder(new)), actor),
        )
        return {"changed": True, "candidate": new, "missing_required_fields": missing, "canonical_writes_performed": 0}

@app.post("/api/promotion-candidates/{candidate_id}/promote", status_code=201)
def promote_candidate(candidate_id: UUID, payload: PromotionRequest):
    actor = clean_text(payload.actor) or "dashboard"
    with db() as (_, cur):
        cur.execute("select * from lead_ops.promotion_candidates where candidate_id=%s for update", (candidate_id,))
        candidate = cur.fetchone()
        if not candidate:
            raise HTTPException(404, "promotion candidate not found")
        if candidate["status"] == "promoted":
            cur.execute("select * from leads.leads where lead_id=%s", (candidate["promoted_lead_id"],))
            lead = cur.fetchone()
            return {"promoted": False, "candidate": candidate, "lead": lead, "canonical_writes_performed": 0}
        if candidate["status"] != "approved":
            raise HTTPException(409, {"message": "candidate must be explicitly approved before promotion", "status": candidate["status"]})
        cur.execute("select * from lead_ops.import_batches where import_batch_id=%s for update", (candidate["import_batch_id"],))
        batch = cur.fetchone()
        if not batch:
            raise HTTPException(404, "import batch not found")
        metadata = batch.get("metadata") or {}
        if metadata.get("provenance_manifest_verified") is not True:
            raise HTTPException(403, "import batch provenance_manifest_verified is not true")
        if metadata.get("promotion_authorized") is not True:
            raise HTTPException(403, "import batch promotion_authorized is not true")
        if batch["status"] != "completed":
            raise HTTPException(409, {"message": "import batch must be completed before promotion", "status": batch["status"]})
        try:
            canonical = LeadCreate.model_validate(candidate["normalized_payload"])
        except Exception as exc:
            raise HTTPException(422, f"candidate failed canonical validation: {exc}") from exc
        data = canonical.model_dump()
        for key, value in list(data.items()):
            if isinstance(value, str):
                data[key] = clean_text(value)
        if not data.get("source_file"):
            data["source_file"] = clean_text(batch.get("source_location"))
        fp = fingerprint(data)
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (fp,))
        cur.execute("select lead_id,business_name from leads.leads where duplicate_fingerprint=%s and status<>'archived' limit 1", (fp,))
        duplicate = cur.fetchone()
        if duplicate:
            raise HTTPException(409, {"message": "canonical exact duplicate exists", "existing": jsonable_encoder(duplicate)})
        cols = list(data.keys()) + ["import_batch_id", "duplicate_fingerprint"]
        vals = [data[k] for k in data] + [candidate["import_batch_id"], fp]
        placeholders = ",".join(["%s"] * len(vals))
        cur.execute(f"insert into leads.leads ({','.join(cols)}) values ({placeholders}) returning *", vals)
        lead = cur.fetchone()
        cur.execute(
            "insert into lead_audit.lead_changes(lead_id,action,new_data,actor) values(%s,'promotion.create',%s,%s)",
            (lead["lead_id"], Jsonb({"candidate_id": str(candidate_id), "lead": jsonable_encoder(lead)}), actor),
        )
        cur.execute(
            "insert into lead_ops.outbox(event_type,aggregate_id,payload) values('lead.created',%s,%s)",
            (lead["lead_id"], Jsonb({"lead_id": str(lead["lead_id"]), "candidate_id": str(candidate_id), "import_batch_id": str(candidate["import_batch_id"])})),
        )
        cur.execute("""
          update lead_ops.promotion_candidates
          set status='promoted',promoted_lead_id=%s,promoted_at=now(),updated_at=now()
          where candidate_id=%s returning *
        """, (lead["lead_id"], candidate_id))
        promoted = cur.fetchone()
        cur.execute("update lead_ops.import_batches set rows_accepted=rows_accepted+1 where import_batch_id=%s", (candidate["import_batch_id"],))
        return {"promoted": True, "candidate": promoted, "lead": lead, "canonical_writes_performed": 1}

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
