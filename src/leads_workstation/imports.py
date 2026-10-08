from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db import init_db, now_utc
from .dedupe import find_duplicate_candidates
from .normalize import normalize_phone
from .storage import db_connection


@dataclass(frozen=True)
class ImportProfile:
    name: str
    field_map: dict[str, str]
    defaults: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ("business_name", "country", "business_category")


BUILTIN_PROFILES = {
    "generic": ImportProfile(
        name="generic",
        field_map={
            "business_name": "business_name",
            "company": "business_name",
            "contact_name": "contact_name",
            "full_name": "contact_name",
            "email": "email",
            "email_primary": "email",
            "phone": "phone",
            "mobile": "phone",
            "country": "country",
            "city": "city",
            "business_category": "business_category",
            "lead_category": "business_category",
            "notes": "notes",
        },
        defaults={"business_category": "Uncategorized"},
    ),
    "vicidial": ImportProfile(
        name="vicidial",
        field_map={
            "vendor_lead_code": "external_id",
            "first_name": "first_name",
            "last_name": "last_name",
            "phone_number": "phone",
            "email": "email",
            "city": "city",
            "state": "state_province",
            "country_code": "country",
            "comments": "notes",
        },
        defaults={"business_name": "(VICIdial lead)", "business_category": "Call Center Lead"},
    ),
    "odoo": ImportProfile(
        name="odoo",
        field_map={
            "id": "external_id",
            "name": "business_name",
            "contact_name": "contact_name",
            "email_from": "email",
            "phone": "phone",
            "mobile": "mobile",
            "city": "city",
            "state_id": "state_province",
            "country_id": "country",
            "team_id": "campaign_source",
            "description": "notes",
        },
        defaults={"business_category": "CRM Lead"},
    ),
}


def get_profile(name: str) -> ImportProfile:
    try:
        return BUILTIN_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown import profile: {name}") from exc


def map_row(row: dict[str, Any], profile: ImportProfile) -> dict[str, Any]:
    mapped = dict(profile.defaults)
    for source, value in row.items():
        target = profile.field_map.get(source)
        if target and value not in (None, ""):
            if target in mapped and mapped[target] not in (None, "") and target in {"phone", "email"}:
                mapped.setdefault(target + "_alternate", value)
            else:
                mapped[target] = value
    if not mapped.get("contact_name"):
        first = str(mapped.get("first_name") or "").strip()
        last = str(mapped.get("last_name") or "").strip()
        if first or last:
            mapped["contact_name"] = (first + " " + last).strip()
    if not mapped.get("business_name"):
        mapped["business_name"] = mapped.get("contact_name") or "(unknown)"
    return mapped


def preview_csv(
    path: str | Path,
    *,
    profile_name: str = "generic",
    limit: int = 20,
) -> dict[str, Any]:
    src = Path(path)
    profile = get_profile(profile_name)
    with src.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for i, row in enumerate(reader):
            if i >= max(1, min(int(limit), 100)):
                break
            rows.append(map_row(dict(row), profile))
        headers = reader.fieldnames or []
    missing_mapping = [
        required
        for required in profile.required
        if required not in profile.defaults
        and required not in profile.field_map.values()
    ]
    return {
        "profile": profile.name,
        "source": str(src.resolve()),
        "headers": headers,
        "mapped_preview": rows,
        "profile_missing_required_mapping": missing_mapping,
    }


def stage_csv_candidates(
    db_path,
    path: str | Path,
    *,
    profile_name: str = "generic",
    batch_id: str | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    src = Path(path).resolve()
    profile = get_profile(profile_name)
    source_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    batch_id = batch_id or f"{src.stem}-{profile.name}-{source_hash[:12]}"

    seen = inserted = possible_matches = duplicates = new_count = invalid = 0
    with src.open("r", encoding="utf-8-sig", newline="") as fh, db_connection(db_path) as conn:
        reader = csv.DictReader(fh)
        for row_number, row in enumerate(reader, start=2):
            if max_rows is not None and seen >= max_rows:
                break
            seen += 1
            mapped = map_row(dict(row), profile)
            missing = [k for k in profile.required if not str(mapped.get(k) or "").strip()]
            if missing:
                invalid += 1
                continue

            matches = find_duplicate_candidates(db_path, mapped, limit=1)
            top = matches[0] if matches else None
            classification = top["classification"] if top else "new"
            disposition = (
                "duplicate"
                if classification == "duplicate"
                else "possible_match"
                if classification == "possible_match"
                else "new"
            )
            if disposition == "duplicate":
                duplicates += 1
            elif disposition == "possible_match":
                possible_matches += 1
            else:
                new_count += 1

            phones = []
            for key in ("phone", "phone_alternate", "mobile"):
                p = normalize_phone(mapped.get(key))
                if p and p not in phones:
                    phones.append(p)

            fp_payload = {
                "batch_id": batch_id,
                "row": row_number,
                "business_name": mapped["business_name"],
                "contact_name": mapped.get("contact_name"),
                "email": mapped.get("email"),
                "phones": phones,
            }
            source_fp = hashlib.sha256(
                json.dumps(fp_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            candidate_id = "cand_" + source_fp[:24]

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO candidate_leads(
                    candidate_id,batch_id,contact_name,business_name,country,
                    business_category,phones_json,email,notes,source_file,source_row,
                    source_fingerprint,match_lead_id,match_reason,disposition,
                    source_payload,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate_id,
                    batch_id,
                    mapped.get("contact_name") or mapped["business_name"],
                    mapped["business_name"],
                    mapped["country"],
                    mapped["business_category"],
                    json.dumps(phones),
                    mapped.get("email"),
                    mapped.get("notes"),
                    str(src),
                    row_number,
                    source_fp,
                    top["lead_id"] if top else None,
                    json.dumps(top, ensure_ascii=False) if top else None,
                    disposition,
                    json.dumps({"source": row, "mapped": mapped}, ensure_ascii=False),
                    now_utc(),
                ),
            )
            inserted += max(cur.rowcount, 0)

    return {
        "batch_id": batch_id,
        "profile": profile.name,
        "source": str(src),
        "source_sha256": source_hash,
        "rows_seen": seen,
        "rows_inserted": inserted,
        "new": new_count,
        "possible_matches": possible_matches,
        "duplicates": duplicates,
        "invalid": invalid,
    }
