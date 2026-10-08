from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from .db import init_db
from .normalize import normalize_email, normalize_phone, normalize_text
from .storage import db_connection


def _domain(email: str | None, website: str | None = None) -> str:
    email = normalize_email(email)
    if email:
        return email.split("@", 1)[1]
    if website:
        raw = str(website).strip()
        if "://" not in raw:
            raw = "https://" + raw
        try:
            host = urlparse(raw).hostname or ""
        except ValueError:
            host = ""
        return host.lower().removeprefix("www.")
    return ""


def score_match(candidate: Mapping[str, Any], existing: Mapping[str, Any]) -> dict[str, Any]:
    score = 0.0
    reasons: list[str] = []

    c_email = normalize_email(candidate.get("email") or candidate.get("email_primary"))
    e_email = normalize_email(existing.get("email"))
    if c_email and e_email and c_email == e_email:
        score += 90
        reasons.append("exact_email")

    candidate_phones = {
        normalize_phone(v)
        for key, v in candidate.items()
        if "phone" in str(key).lower() or str(key).lower() == "mobile"
    }
    candidate_phones.discard("")
    existing_phones = {
        normalize_phone(existing.get("phone")),
        normalize_phone(existing.get("normalized_phone")),
    }
    existing_phones.discard("")
    if candidate_phones.intersection(existing_phones):
        score += 65
        reasons.append("exact_phone")

    c_domain = _domain(c_email, candidate.get("website"))
    e_domain = _domain(e_email, existing.get("website"))
    if c_domain and e_domain and c_domain == e_domain:
        score += 15
        reasons.append("same_domain")

    c_name = normalize_text(
        candidate.get("contact_name")
        or candidate.get("full_name")
        or candidate.get("business_name")
        or candidate.get("company")
    )
    e_name = normalize_text(
        existing.get("contact_name") or existing.get("business_name")
    )
    similarity = SequenceMatcher(None, c_name, e_name).ratio() if c_name and e_name else 0.0
    if similarity >= 0.92:
        score += 25
        reasons.append("very_close_name")
    elif similarity >= 0.82:
        score += 15
        reasons.append("close_name")
    elif similarity >= 0.72:
        score += 8
        reasons.append("similar_name")

    c_country = normalize_text(candidate.get("country"))
    e_country = normalize_text(existing.get("country"))
    if c_country and e_country and c_country == e_country:
        score += 3
        reasons.append("same_country")

    c_city = normalize_text(candidate.get("city"))
    e_city = normalize_text(existing.get("city"))
    if c_city and e_city and c_city == e_city:
        score += 3
        reasons.append("same_city")

    score = min(score, 100.0)
    classification = (
        "duplicate" if score >= 85 else "possible_match" if score >= 60 else "new"
    )
    return {
        "score": round(score, 2),
        "classification": classification,
        "reasons": reasons,
        "name_similarity": round(similarity, 4),
    }


def find_duplicate_candidates(
    db_path,
    candidate: Mapping[str, Any],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    init_db(db_path)
    email = normalize_email(candidate.get("email") or candidate.get("email_primary"))
    phones = {
        normalize_phone(v)
        for key, v in candidate.items()
        if "phone" in str(key).lower() or str(key).lower() == "mobile"
    }
    phones.discard("")
    country = str(candidate.get("country") or "").strip()

    with db_connection(db_path) as conn:
        rows_by_id: dict[str, dict[str, Any]] = {}
        contact_evidence: dict[str, set[str]] = {}

        if email:
            for row in conn.execute(
                "SELECT * FROM leads WHERE normalized_email=? LIMIT 250",
                (email,),
            ):
                item = dict(row)
                rows_by_id[item["lead_id"]] = item
            for row in conn.execute(
                "SELECT lead_id FROM lead_contact_points "
                "WHERE kind='email' AND normalized_value=? LIMIT 250",
                (email,),
            ):
                lead_id = row["lead_id"]
                contact_evidence.setdefault(lead_id, set()).add("exact_email_contact")
                if lead_id not in rows_by_id:
                    lead = conn.execute(
                        "SELECT * FROM leads WHERE lead_id=?", (lead_id,)
                    ).fetchone()
                    if lead:
                        rows_by_id[lead_id] = dict(lead)

        for phone in sorted(phones):
            for row in conn.execute(
                "SELECT * FROM leads WHERE normalized_phone=? LIMIT 250",
                (phone,),
            ):
                item = dict(row)
                rows_by_id[item["lead_id"]] = item
            for row in conn.execute(
                "SELECT lead_id FROM lead_contact_points "
                "WHERE kind='phone' AND normalized_value=? LIMIT 250",
                (phone,),
            ):
                lead_id = row["lead_id"]
                contact_evidence.setdefault(lead_id, set()).add("exact_phone_contact")
                if lead_id not in rows_by_id:
                    lead = conn.execute(
                        "SELECT * FROM leads WHERE lead_id=?", (lead_id,)
                    ).fetchone()
                    if lead:
                        rows_by_id[lead_id] = dict(lead)

        if rows_by_id:
            rows = list(rows_by_id.values())
        elif country:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM leads WHERE country=? "
                    "ORDER BY updated_at DESC LIMIT 750",
                    (country,),
                )
            ]
        else:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM leads ORDER BY updated_at DESC LIMIT 500"
                )
            ]

    matches = []
    for row in rows:
        scored = score_match(candidate, row)
        evidence = contact_evidence.get(row["lead_id"], set())
        if "exact_email_contact" in evidence:
            scored["score"] = max(float(scored["score"]), 90.0)
            scored["classification"] = "duplicate"
            if "exact_email_contact" not in scored["reasons"]:
                scored["reasons"].append("exact_email_contact")
        if "exact_phone_contact" in evidence:
            scored["score"] = max(float(scored["score"]), 65.0)
            if scored["score"] >= 85:
                scored["classification"] = "duplicate"
            else:
                scored["classification"] = "possible_match"
            if "exact_phone_contact" not in scored["reasons"]:
                scored["reasons"].append("exact_phone_contact")
        if scored["score"] <= 0:
            continue
        matches.append(
            {
                "lead_id": row["lead_id"],
                "business_name": row.get("business_name"),
                "contact_name": row.get("contact_name"),
                **scored,
            }
        )
    matches.sort(key=lambda item: (-item["score"], item["lead_id"]))
    return matches[: max(1, min(int(limit), 50))]
