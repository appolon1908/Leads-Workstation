from __future__ import annotations

import ipaddress
import json
import os
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from .db import (
    ConcurrencyError,
    _emit_outbox,
    _upsert_contact_point,
    init_db,
    now_utc,
)
from .normalize import normalize_email, normalize_phone
from .storage import db_connection

CAMPAIGN_TYPES = {"outbound", "inbound", "blended"}
CAMPAIGN_STATES = {"draft", "active", "paused", "closed", "archived"}
MEMBER_ROLES = {"primary_supervisor", "backup_supervisor", "agent", "qa", "auditor"}
CONTACT_KINDS = {"email", "phone"}

LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "Needs Verification": {"New", "DNC", "Lost"},
    "New": {"Assigned", "DNC", "Lost"},
    "Assigned": {"Attempted", "New", "DNC", "Lost"},
    "Attempted": {"Contacted", "Assigned", "DNC", "Lost"},
    "Contacted": {"Qualified", "Attempted", "DNC", "Lost"},
    "Qualified": {"Appointment", "Contacted", "DNC", "Lost"},
    "Appointment": {"Converted", "Qualified", "DNC", "Lost"},
    "Converted": set(),
    "Lost": {"New"},
    "DNC": set(),
}
ENGAGEMENT_STATES = {"Attempted", "Contacted", "Qualified", "Appointment", "Converted"}


class LifecycleError(ValueError):
    pass


class SuppressedLeadError(ValueError):
    pass


def _uuid(prefix: str) -> str:
    return prefix + uuid.uuid4().hex


def create_campaign(
    db_path,
    payload: Mapping[str, Any],
    actor: str = "system",
) -> dict[str, Any]:
    init_db(db_path)
    code = str(payload.get("campaign_code") or "").strip()
    name = str(payload.get("name") or "").strip()
    campaign_type = str(payload.get("campaign_type") or "").strip().lower()
    state = str(payload.get("state") or "draft").strip().lower()
    if not code or not name:
        raise ValueError("campaign_code and name are required")
    if campaign_type not in CAMPAIGN_TYPES:
        raise ValueError("campaign_type must be outbound, inbound, or blended")
    if state not in CAMPAIGN_STATES:
        raise ValueError("invalid campaign state")
    campaign_id = str(payload.get("campaign_id") or _uuid("cmp_"))
    stamp = now_utc()
    with db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO campaigns(
                campaign_id,campaign_code,name,campaign_type,state,
                primary_supervisor,client_id,start_at,end_at,description,
                created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                campaign_id,
                code,
                name,
                campaign_type,
                state,
                payload.get("primary_supervisor"),
                payload.get("client_id"),
                payload.get("start_at"),
                payload.get("end_at"),
                payload.get("description"),
                stamp,
                stamp,
            ),
        )
        supervisor = payload.get("primary_supervisor")
        if supervisor:
            conn.execute(
                """
                INSERT INTO campaign_members(
                    campaign_id,user_id,member_role,active,created_at
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(campaign_id,user_id) DO UPDATE SET
                    member_role=excluded.member_role,active=excluded.active
                """,
                (campaign_id, supervisor, "primary_supervisor", 1, stamp),
            )
        _emit_outbox(
            conn,
            "campaign.created",
            campaign_id,
            {"campaign_id": campaign_id, "campaign_code": code, "actor": actor},
            aggregate_type="campaign",
        )
        return dict(
            conn.execute(
                "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
            ).fetchone()
        )


def list_campaigns(db_path, state: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    sql = "SELECT * FROM campaigns"
    params: tuple[Any, ...] = ()
    if state:
        sql += " WHERE state=?"
        params = (state,)
    sql += " ORDER BY campaign_code"
    with db_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def update_campaign(
    db_path,
    campaign_id: str,
    changes: Mapping[str, Any],
    *,
    actor: str,
) -> dict[str, Any]:
    init_db(db_path)
    allowed = {
        "name",
        "campaign_type",
        "state",
        "primary_supervisor",
        "client_id",
        "start_at",
        "end_at",
        "description",
    }
    clean = {k: v for k, v in changes.items() if k in allowed}
    if not clean:
        raise ValueError("no editable campaign fields supplied")
    if "campaign_type" in clean:
        clean["campaign_type"] = str(clean["campaign_type"]).strip().lower()
        if clean["campaign_type"] not in CAMPAIGN_TYPES:
            raise ValueError("invalid campaign type")
    if "state" in clean:
        clean["state"] = str(clean["state"]).strip().lower()
        if clean["state"] not in CAMPAIGN_STATES:
            raise ValueError("invalid campaign state")
    clean["updated_at"] = now_utc()
    with db_connection(db_path) as conn:
        before = conn.execute(
            "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if not before:
            raise KeyError("campaign not found")
        assignments = ",".join(k + "=?" for k in clean)
        conn.execute(
            "UPDATE campaigns SET " + assignments + " WHERE campaign_id=?",
            tuple(clean.values()) + (campaign_id,),
        )
        supervisor = clean.get("primary_supervisor")
        if supervisor:
            conn.execute(
                """
                INSERT INTO campaign_members(
                    campaign_id,user_id,member_role,active,created_at
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(campaign_id,user_id) DO UPDATE SET
                    member_role=excluded.member_role,active=excluded.active
                """,
                (campaign_id, supervisor, "primary_supervisor", 1, now_utc()),
            )
        _emit_outbox(
            conn,
            "campaign.updated",
            campaign_id,
            {
                "campaign_id": campaign_id,
                "actor": actor,
                "changed_fields": sorted(clean.keys()),
            },
            aggregate_type="campaign",
        )
        return dict(
            conn.execute(
                "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
            ).fetchone()
        )


def add_campaign_member(
    db_path,
    campaign_id: str,
    user_id: str,
    member_role: str,
    *,
    active: bool = True,
) -> dict[str, Any]:
    init_db(db_path)
    user_id = str(user_id or "").strip()
    member_role = member_role.strip().lower()
    if not user_id:
        raise ValueError("campaign member user_id is required")
    if member_role not in MEMBER_ROLES:
        raise ValueError("invalid campaign member role")
    with db_connection(db_path) as conn:
        campaign = conn.execute(
            "SELECT campaign_id FROM campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if not campaign:
            raise KeyError("campaign not found")
        conn.execute(
            """
            INSERT INTO campaign_members(
                campaign_id,user_id,member_role,active,created_at
            ) VALUES(?,?,?,?,?)
            ON CONFLICT(campaign_id,user_id) DO UPDATE SET
                member_role=excluded.member_role,active=excluded.active
            """,
            (campaign_id, user_id, member_role, 1 if active else 0, now_utc()),
        )
        return dict(
            conn.execute(
                "SELECT * FROM campaign_members WHERE campaign_id=? AND user_id=?",
                (campaign_id, user_id),
            ).fetchone()
        )


def list_campaign_members(db_path, campaign_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM campaign_members WHERE campaign_id=? "
                "ORDER BY member_role,user_id",
                (campaign_id,),
            )
        ]


def add_contact_point(
    db_path,
    lead_id: str,
    kind: str,
    value: str,
    *,
    label: str | None = None,
    primary: bool = False,
    verification_status: str = "unverified",
    source: str = "manual",
    actor: str = "system",
) -> dict[str, Any]:
    init_db(db_path)
    kind = kind.strip().lower()
    if kind not in CONTACT_KINDS:
        raise ValueError("contact kind must be email or phone")
    normalized = normalize_email(value) if kind == "email" else normalize_phone(value)
    if not normalized:
        raise ValueError(f"invalid {kind}")
    contact_id = "cp_" + uuid.uuid5(
        uuid.NAMESPACE_URL, f"{lead_id}:{kind}:{normalized}"
    ).hex[:24]
    stamp = now_utc()
    with db_connection(db_path) as conn:
        lead = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if not lead:
            raise KeyError("lead not found")
        if primary:
            conn.execute(
                "UPDATE lead_contact_points SET is_primary=0,updated_at=? "
                "WHERE lead_id=? AND kind=?",
                (stamp, lead_id, kind),
            )
        conn.execute(
            """
            INSERT INTO lead_contact_points(
                contact_point_id,lead_id,kind,value,normalized_value,label,
                is_primary,verification_status,source,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(lead_id,kind,normalized_value) DO UPDATE SET
                value=excluded.value,label=excluded.label,
                is_primary=excluded.is_primary,
                verification_status=excluded.verification_status,
                source=excluded.source,updated_at=excluded.updated_at
            """,
            (
                contact_id,
                lead_id,
                kind,
                value,
                normalized,
                label,
                1 if primary else 0,
                verification_status,
                source,
                stamp,
                stamp,
            ),
        )
        _emit_outbox(
            conn,
            "lead.contact.updated",
            lead_id,
            {
                "lead_id": lead_id,
                "contact_point_id": contact_id,
                "kind": kind,
                "actor": actor,
            },
        )
        return dict(
            conn.execute(
                "SELECT * FROM lead_contact_points "
                "WHERE lead_id=? AND kind=? AND normalized_value=?",
                (lead_id, kind, normalized),
            ).fetchone()
        )


def list_contact_points(db_path, lead_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lead_contact_points WHERE lead_id=? "
                "ORDER BY kind,is_primary DESC,created_at",
                (lead_id,),
            )
        ]


def backfill_contact_points(db_path, limit: int | None = None) -> dict[str, int]:
    init_db(db_path)
    sql = (
        "SELECT lead_id,email,phone,verification_status,source_file "
        "FROM leads ORDER BY lead_id"
    )
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (max(1, int(limit)),)
    scanned = email_count = phone_count = 0
    with db_connection(db_path) as conn:
        for lead in conn.execute(sql, params):
            scanned += 1
            if lead["email"]:
                before = conn.execute(
                    "SELECT COUNT(*) FROM lead_contact_points "
                    "WHERE lead_id=? AND kind='email'",
                    (lead["lead_id"],),
                ).fetchone()[0]
                _upsert_contact_point(
                    conn,
                    lead["lead_id"],
                    "email",
                    lead["email"],
                    source=lead["source_file"] or "backfill",
                    verification_status=lead["verification_status"] or "unverified",
                )
                after = conn.execute(
                    "SELECT COUNT(*) FROM lead_contact_points "
                    "WHERE lead_id=? AND kind='email'",
                    (lead["lead_id"],),
                ).fetchone()[0]
                email_count += int(after > before)
            if lead["phone"]:
                before = conn.execute(
                    "SELECT COUNT(*) FROM lead_contact_points "
                    "WHERE lead_id=? AND kind='phone'",
                    (lead["lead_id"],),
                ).fetchone()[0]
                _upsert_contact_point(
                    conn,
                    lead["lead_id"],
                    "phone",
                    lead["phone"],
                    source=lead["source_file"] or "backfill",
                    verification_status=lead["verification_status"] or "unverified",
                )
                after = conn.execute(
                    "SELECT COUNT(*) FROM lead_contact_points "
                    "WHERE lead_id=? AND kind='phone'",
                    (lead["lead_id"],),
                ).fetchone()[0]
                phone_count += int(after > before)
    return {
        "scanned": scanned,
        "email_contact_points_added": email_count,
        "phone_contact_points_added": phone_count,
    }


def assign_lead(
    db_path,
    lead_id: str,
    campaign_id: str,
    to_agent: str,
    *,
    assigned_by: str,
    reason: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        lead_row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if not lead_row:
            raise KeyError("lead not found")
        lead = dict(lead_row)
        campaign = conn.execute(
            "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if not campaign:
            raise KeyError("campaign not found")
        if campaign["state"] in {"closed", "archived"}:
            raise ValueError("cannot assign into a closed or archived campaign")
        member = conn.execute(
            "SELECT * FROM campaign_members WHERE campaign_id=? AND user_id=? AND active=1",
            (campaign_id, to_agent),
        ).fetchone()
        if not member:
            raise ValueError("target agent is not an active campaign member")
        current_version = int(lead.get("version") or 1)
        if expected_version is not None and current_version != int(expected_version):
            raise ConcurrencyError(
                f"lead version mismatch: expected {expected_version}, current {current_version}"
            )
        if lead.get("suppressed") or lead.get("do_not_contact"):
            raise SuppressedLeadError("suppressed/DNC leads cannot be assigned for outreach")

        new_status = "Assigned" if lead["status"] == "New" else lead["status"]
        stamp = now_utc()
        conn.execute(
            "UPDATE leads SET campaign_id=?,assigned_agent=?,owner=?,status=?,"
            "version=?,updated_at=? WHERE lead_id=?",
            (
                campaign_id,
                to_agent,
                to_agent,
                new_status,
                current_version + 1,
                stamp,
                lead_id,
            ),
        )
        assignment_id = _uuid("asg_")
        conn.execute(
            """
            INSERT INTO lead_assignments(
                assignment_id,lead_id,campaign_id,from_agent,to_agent,
                assigned_by,reason,assigned_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                assignment_id,
                lead_id,
                campaign_id,
                lead.get("assigned_agent"),
                to_agent,
                assigned_by,
                reason,
                stamp,
            ),
        )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
            "VALUES(?,?,?,?,?)",
            (
                lead_id,
                "assigned",
                assigned_by,
                stamp,
                json.dumps(
                    {
                        "assignment_id": assignment_id,
                        "campaign_id": campaign_id,
                        "from_agent": lead.get("assigned_agent"),
                        "to_agent": to_agent,
                        "reason": reason,
                        "version": current_version + 1,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        _emit_outbox(
            conn,
            "lead.assigned",
            lead_id,
            {
                "lead_id": lead_id,
                "campaign_id": campaign_id,
                "to_agent": to_agent,
                "version": current_version + 1,
            },
        )
        return dict(conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone())


def assign_round_robin(
    db_path,
    lead_id: str,
    campaign_id: str,
    *,
    assigned_by: str,
    reason: str = "round-robin",
) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        agents = [
            r["user_id"]
            for r in conn.execute(
                "SELECT user_id FROM campaign_members "
                "WHERE campaign_id=? AND active=1 AND member_role='agent' "
                "ORDER BY user_id",
                (campaign_id,),
            )
        ]
        if not agents:
            raise ValueError("campaign has no active agents")
        counts = {
            agent: conn.execute(
                "SELECT COUNT(*) FROM leads "
                "WHERE campaign_id=? AND assigned_agent=? AND status NOT IN ('Converted','Lost','DNC')",
                (campaign_id, agent),
            ).fetchone()[0]
            for agent in agents
        }
    chosen = min(agents, key=lambda agent: (counts[agent], agent))
    return assign_lead(
        db_path,
        lead_id,
        campaign_id,
        chosen,
        assigned_by=assigned_by,
        reason=reason,
    )


def transition_lead(
    db_path,
    lead_id: str,
    to_status: str,
    *,
    actor: str,
    reason: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if not row:
            raise KeyError("lead not found")
        lead = dict(row)
        current = lead["status"]
        to_status = str(to_status).strip()
        allowed = LIFECYCLE_TRANSITIONS.get(current)
        if allowed is None or to_status not in allowed:
            raise LifecycleError(f"transition {current!r} -> {to_status!r} is not allowed")
        if to_status in ENGAGEMENT_STATES and (
            lead.get("suppressed") or lead.get("do_not_contact")
        ):
            raise SuppressedLeadError("suppressed/DNC lead cannot enter outreach lifecycle")
        current_version = int(lead.get("version") or 1)
        if expected_version is not None and current_version != int(expected_version):
            raise ConcurrencyError(
                f"lead version mismatch: expected {expected_version}, current {current_version}"
            )
        stamp = now_utc()
        next_version = current_version + 1
        last_contact_at = stamp if to_status in {"Attempted", "Contacted"} else lead.get("last_contact_at")
        conn.execute(
            "UPDATE leads SET status=?,version=?,last_contact_at=?,updated_at=? WHERE lead_id=?",
            (to_status, next_version, last_contact_at, stamp, lead_id),
        )
        transition_id = _uuid("trn_")
        conn.execute(
            """
            INSERT INTO lead_lifecycle_transitions(
                transition_id,lead_id,from_status,to_status,actor,reason,transitioned_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (transition_id, lead_id, current, to_status, actor, reason, stamp),
        )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
            "VALUES(?,?,?,?,?)",
            (
                lead_id,
                "status.transitioned",
                actor,
                stamp,
                json.dumps(
                    {
                        "transition_id": transition_id,
                        "from_status": current,
                        "to_status": to_status,
                        "reason": reason,
                        "version": next_version,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        _emit_outbox(
            conn,
            "lead.status.changed",
            lead_id,
            {
                "lead_id": lead_id,
                "from_status": current,
                "to_status": to_status,
                "version": next_version,
            },
        )
        return dict(conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone())


def suppress_lead(
    db_path,
    lead_id: str,
    *,
    channel: str,
    reason: str,
    actor: str,
    jurisdiction: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    channel = channel.strip().lower()
    if channel not in {"all", "call", "sms", "email", "whatsapp"}:
        raise ValueError("invalid suppression channel")
    if not reason.strip():
        raise ValueError("suppression reason is required")
    with db_connection(db_path) as conn:
        lead_row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if not lead_row:
            raise KeyError("lead not found")
        lead = dict(lead_row)
        stamp = now_utc()
        suppression_id = _uuid("sup_")
        conn.execute(
            """
            INSERT INTO lead_suppressions(
                suppression_id,lead_id,channel,reason,jurisdiction,source,
                active,created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                suppression_id,
                lead_id,
                channel,
                reason,
                jurisdiction,
                source,
                1,
                actor,
                stamp,
            ),
        )
        suppressed = 1 if channel == "all" else int(lead.get("suppressed") or 0)
        dnc = 1 if channel in {"all", "call"} else int(lead.get("do_not_contact") or 0)
        status = "DNC" if dnc else lead["status"]
        next_version = int(lead.get("version") or 1) + 1
        conn.execute(
            "UPDATE leads SET suppressed=?,do_not_contact=?,status=?,jurisdiction=?,"
            "version=?,updated_at=? WHERE lead_id=?",
            (
                suppressed,
                dnc,
                status,
                jurisdiction or lead.get("jurisdiction"),
                next_version,
                stamp,
                lead_id,
            ),
        )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
            "VALUES(?,?,?,?,?)",
            (
                lead_id,
                "suppressed",
                actor,
                stamp,
                json.dumps(
                    {
                        "suppression_id": suppression_id,
                        "channel": channel,
                        "reason": reason,
                        "jurisdiction": jurisdiction,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        _emit_outbox(
            conn,
            "lead.suppressed",
            lead_id,
            {
                "lead_id": lead_id,
                "channel": channel,
                "reason": reason,
                "version": next_version,
            },
        )
        return dict(conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone())


def list_suppressions(db_path, lead_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lead_suppressions WHERE lead_id=? ORDER BY created_at DESC",
                (lead_id,),
            )
        ]


def record_consent(
    db_path,
    lead_id: str,
    *,
    status: str,
    source: str,
    actor: str,
    jurisdiction: str | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    status = status.strip().lower()
    if status not in {"unknown", "opted_in", "opted_out", "legitimate_interest"}:
        raise ValueError("invalid consent status")
    with db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if not row:
            raise KeyError("lead not found")
        lead = dict(row)
        stamp = now_utc()
        next_version = int(lead.get("version") or 1) + 1
        dnc = 1 if status == "opted_out" else int(lead.get("do_not_contact") or 0)
        conn.execute(
            "UPDATE leads SET consent_status=?,consent_source=?,consent_at=?,"
            "jurisdiction=?,do_not_contact=?,version=?,updated_at=? WHERE lead_id=?",
            (
                status,
                source,
                stamp,
                jurisdiction or lead.get("jurisdiction"),
                dnc,
                next_version,
                stamp,
                lead_id,
            ),
        )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
            "VALUES(?,?,?,?,?)",
            (
                lead_id,
                "consent.updated",
                actor,
                stamp,
                json.dumps(
                    {
                        "consent_status": status,
                        "consent_source": source,
                        "jurisdiction": jurisdiction,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        _emit_outbox(
            conn,
            "lead.consent.updated",
            lead_id,
            {
                "lead_id": lead_id,
                "consent_status": status,
                "version": next_version,
            },
        )
        return dict(conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone())


def list_assignments(db_path, lead_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lead_assignments WHERE lead_id=? ORDER BY assigned_at DESC",
                (lead_id,),
            )
        ]


def list_transitions(db_path, lead_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lead_lifecycle_transitions WHERE lead_id=? "
                "ORDER BY transitioned_at DESC",
                (lead_id,),
            )
        ]


def list_outbox(
    db_path,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    init_db(db_path)
    sql = "SELECT * FROM outbox_events"
    params: list[Any] = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY created_at LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with db_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def register_webhook_subscription(
    db_path,
    *,
    name: str,
    url: str,
    secret_ref: str,
    event_types: list[str],
) -> dict[str, Any]:
    init_db(db_path)
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("webhook URL must use HTTPS except for loopback development")
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and not ip.is_loopback and (
        ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast
    ) and os.getenv("LEADS_ALLOW_PRIVATE_WEBHOOKS", "0").strip() != "1":
        raise ValueError(
            "private/link-local webhook IPs require LEADS_ALLOW_PRIVATE_WEBHOOKS=1"
        )
    if not secret_ref:
        raise ValueError("secret_ref is required; raw webhook secrets are not stored here")
    if not str(secret_ref).startswith(("env://", "openbao://")):
        raise ValueError("secret_ref must use env:// or openbao://")
    subscription_id = "wh_" + uuid.uuid5(uuid.NAMESPACE_URL, name).hex[:24]
    stamp = now_utc()
    with db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO webhook_subscriptions(
                subscription_id,name,url,secret_ref,event_types_json,active,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                url=excluded.url,secret_ref=excluded.secret_ref,
                event_types_json=excluded.event_types_json,
                active=excluded.active,updated_at=excluded.updated_at
            """,
            (
                subscription_id,
                name,
                url,
                secret_ref,
                json.dumps(sorted(set(event_types))),
                1,
                stamp,
                stamp,
            ),
        )
        return dict(
            conn.execute(
                "SELECT * FROM webhook_subscriptions WHERE name=?", (name,)
            ).fetchone()
        )


def lift_suppression(
    db_path,
    lead_id: str,
    *,
    actor: str,
    suppression_id: str | None = None,
    channel: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        lead_row = conn.execute(
            "SELECT * FROM leads WHERE lead_id=?", (lead_id,)
        ).fetchone()
        if not lead_row:
            raise KeyError("lead not found")
        lead = dict(lead_row)
        stamp = now_utc()
        if suppression_id:
            cur = conn.execute(
                "UPDATE lead_suppressions SET active=0,lifted_at=? "
                "WHERE suppression_id=? AND lead_id=? AND active=1",
                (stamp, suppression_id, lead_id),
            )
        elif channel:
            cur = conn.execute(
                "UPDATE lead_suppressions SET active=0,lifted_at=? "
                "WHERE lead_id=? AND channel=? AND active=1",
                (stamp, lead_id, channel.strip().lower()),
            )
        else:
            raise ValueError("suppression_id or channel is required")
        if cur.rowcount == 0:
            raise KeyError("active suppression not found")

        active = [
            dict(r)
            for r in conn.execute(
                "SELECT channel FROM lead_suppressions WHERE lead_id=? AND active=1",
                (lead_id,),
            )
        ]
        channels = {row["channel"] for row in active}
        suppressed = 1 if "all" in channels else 0
        dnc = 1 if channels.intersection({"all", "call"}) else 0
        status = lead["status"]
        if status == "DNC" and not dnc:
            status = "New"
        next_version = int(lead.get("version") or 1) + 1
        conn.execute(
            "UPDATE leads SET suppressed=?,do_not_contact=?,status=?,version=?,"
            "updated_at=? WHERE lead_id=?",
            (suppressed, dnc, status, next_version, stamp, lead_id),
        )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
            "VALUES(?,?,?,?,?)",
            (
                lead_id,
                "suppression.lifted",
                actor,
                stamp,
                json.dumps(
                    {
                        "suppression_id": suppression_id,
                        "channel": channel,
                        "reason": reason,
                        "remaining_channels": sorted(channels),
                        "version": next_version,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        _emit_outbox(
            conn,
            "lead.suppression.lifted",
            lead_id,
            {
                "lead_id": lead_id,
                "suppression_id": suppression_id,
                "channel": channel,
                "version": next_version,
            },
        )
        return dict(
            conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        )


def list_webhook_subscriptions(db_path) -> list[dict[str, Any]]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        return [
            {
                **dict(row),
                "secret_ref": "***configured***",
            }
            for row in conn.execute(
                "SELECT * FROM webhook_subscriptions ORDER BY name"
            )
        ]


def backfill_identity_fingerprints(db_path, limit: int | None = None) -> dict[str, int]:
    from .normalize import identity_fingerprint

    init_db(db_path)
    sql = (
        "SELECT lead_id,business_name,contact_name,country,city,email,phone "
        "FROM leads WHERE identity_fingerprint IS NULL OR identity_fingerprint=''"
    )
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (max(1, int(limit)),)

    scanned = updated = collisions = 0
    with db_connection(db_path) as conn:
        rows = [dict(r) for r in conn.execute(sql, params)]
        for lead in rows:
            scanned += 1
            fp = identity_fingerprint(lead)
            collision = conn.execute(
                "SELECT lead_id FROM leads WHERE identity_fingerprint=? AND lead_id<>? LIMIT 1",
                (fp, lead["lead_id"]),
            ).fetchone()
            if collision:
                collisions += 1
                continue
            conn.execute(
                "UPDATE leads SET identity_fingerprint=?,updated_at=? WHERE lead_id=?",
                (fp, now_utc(), lead["lead_id"]),
            )
            updated += 1
    return {"scanned": scanned, "updated": updated, "collisions": collisions}


CONTACT_VERIFICATION_STATES = {
    "unverified",
    "valid",
    "invalid",
    "risky",
    "historical",
    "do_not_contact",
}


def verify_contact_point(
    db_path,
    contact_point_id: str,
    *,
    verification_status: str,
    actor: str,
    source: str = "manual-verification",
) -> dict[str, Any]:
    init_db(db_path)
    state = verification_status.strip().lower()
    if state not in CONTACT_VERIFICATION_STATES:
        raise ValueError("invalid contact verification status")
    stamp = now_utc()
    with db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM lead_contact_points WHERE contact_point_id=?",
            (contact_point_id,),
        ).fetchone()
        if not row:
            raise KeyError("contact point not found")
        item = dict(row)
        conn.execute(
            "UPDATE lead_contact_points SET verification_status=?,source=?,updated_at=? "
            "WHERE contact_point_id=?",
            (state, source, stamp, contact_point_id),
        )
        if item["is_primary"]:
            conn.execute(
                "UPDATE leads SET verification_status=?,updated_at=? WHERE lead_id=?",
                (state, stamp, item["lead_id"]),
            )
        conn.execute(
            "INSERT INTO lead_events(lead_id,event_type,actor,event_at,payload_json) "
            "VALUES(?,?,?,?,?)",
            (
                item["lead_id"],
                "contact.verified",
                actor,
                stamp,
                json.dumps(
                    {
                        "contact_point_id": contact_point_id,
                        "kind": item["kind"],
                        "verification_status": state,
                        "source": source,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        _emit_outbox(
            conn,
            "lead.contact.verified",
            item["lead_id"],
            {
                "lead_id": item["lead_id"],
                "contact_point_id": contact_point_id,
                "verification_status": state,
            },
        )
        return dict(
            conn.execute(
                "SELECT * FROM lead_contact_points WHERE contact_point_id=?",
                (contact_point_id,),
            ).fetchone()
        )


def get_contact_point(db_path, contact_point_id: str) -> dict[str, Any] | None:
    init_db(db_path)
    with db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM lead_contact_points WHERE contact_point_id=?",
            (contact_point_id,),
        ).fetchone()
        return dict(row) if row else None
