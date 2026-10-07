from __future__ import annotations
import hashlib
import re
from typing import Mapping

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_NON_DIGIT = re.compile(r"\D+")

def clean_text(value: object | None) -> str:
    return " ".join(str(value or "").strip().split())

def normalize_text(value: object | None) -> str:
    return _NON_ALNUM.sub(" ", clean_text(value).lower()).strip()

def normalize_email(value: object | None) -> str:
    email = clean_text(value).lower()
    if not email or "@" not in email:
        return ""
    local, domain = email.rsplit("@", 1)
    if not local or "." not in domain:
        return ""
    return f"{local}@{domain}"

def normalize_phone(value: object | None) -> str:
    digits = _NON_DIGIT.sub("", clean_text(value))
    if len(digits) < 7:
        return ""
    return digits[-10:] if len(digits) > 10 else digits

def first_present(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = clean_text(row.get(key))
        if value:
            return value
    return ""

def identity_key(row: Mapping[str, object]) -> tuple[str, str]:
    canonical_id = first_present(row, "lead_id")
    if canonical_id:
        return "lead_id", canonical_id.strip().lower()
    email = normalize_email(first_present(row, "normalized_email_primary", "email_primary", "email"))
    if email:
        return "email", email
    phone = normalize_phone(first_present(row, "normalized_phone_primary", "mobile", "direct_phone", "company_phone", "phone"))
    if phone:
        return "phone", phone
    entity = normalize_text(first_present(row, "company", "business_name", "full_name", "contact_name"))
    country = normalize_text(first_present(row, "country"))
    city = normalize_text(first_present(row, "city"))
    return "entity", entity + "|" + country + "|" + city

def fingerprint(row: Mapping[str, object]) -> str:
    kind, key = identity_key(row)
    return hashlib.sha256((kind + ":" + key).encode("utf-8")).hexdigest()
