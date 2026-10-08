from __future__ import annotations

import json
import os
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .auth import (
    AuthenticationError,
    AuthorizationError,
    authenticate,
    can_access_lead,
    require_permission,
)
from .candidates import candidate_summary, list_candidates
from .dashboard import DASHBOARD_CSS, DASHBOARD_HTML, DASHBOARD_JS
from .db import (
    ConcurrencyError,
    DuplicateLeadError,
    create_lead,
    get_lead,
    init_db,
    lead_events,
    list_leads,
    stats,
    update_lead,
)
from .dedupe import find_duplicate_candidates
from .metrics import prometheus_metrics
from .platform import (
    LifecycleError,
    SuppressedLeadError,
    add_campaign_member,
    add_contact_point,
    assign_lead,
    assign_round_robin,
    create_campaign,
    get_contact_point,
    lift_suppression,
    list_assignments,
    list_campaign_members,
    list_campaigns,
    list_contact_points,
    list_outbox,
    list_suppressions,
    list_transitions,
    list_webhook_subscriptions,
    record_consent,
    register_webhook_subscription,
    suppress_lead,
    transition_lead,
    update_campaign,
    verify_contact_point,
)

INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>Codestra Leads Workstation</title>
<style>body{font-family:system-ui;margin:2rem;max-width:1400px}code{background:#eee;padding:.15rem .3rem}</style></head>
<body><h1>Codestra Leads Workstation V2</h1>
<p>Canonical lead service with campaigns, RBAC, lifecycle, compliance, audit and outbox.</p>
<p>V1 remains available locally. V2 is fail-closed unless development or Keycloak authentication is configured.</p>
<p>Health: <code>/health</code> · Ready: <code>/ready</code> · Metrics: <code>/metrics</code></p>
</body></html>"""

MAX_BODY_BYTES = 1024 * 1024


def _if_match(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip().strip('"').removeprefix("W/").strip('"')
    if not cleaned.isdigit():
        raise ValueError("If-Match must contain the numeric lead version")
    return int(cleaned)


def make_handler(db_path):
    # Initialize/upgrade schema before the server can accept concurrent requests.
    init_db(db_path)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CodestraLeads/2.0"

        def log_message(self, fmt, *args):
            return

        @property
        def request_id(self) -> str:
            existing = getattr(self, "_request_id", None)
            if existing:
                return existing
            value = self.headers.get("X-Request-ID") or "req_" + uuid.uuid4().hex
            self._request_id = value[:128]
            return self._request_id

        def _security_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.send_header("X-Request-ID", self.request_id)

        def send_json(self, value, status=HTTPStatus.OK, extra_headers=None):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            for key, val in (extra_headers or {}).items():
                self.send_header(key, str(val))
            self.end_headers()
            self.wfile.write(body)

        def send_text(self, value: str, content_type: str, status=HTTPStatus.OK):
            body = value.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError:
                raise ValueError("invalid Content-Length")
            if length <= 0:
                raise ValueError("request body required")
            if length > MAX_BODY_BYTES:
                raise ValueError("request body too large")
            body = self.rfile.read(length)
            value = json.loads(body.decode("utf-8"))
            if not isinstance(value, dict):
                raise TypeError("JSON body must be an object")
            return value

        def auth_context(self):
            return authenticate(self.headers, self.client_address[0])

        def require(self, permission: str):
            ctx = self.auth_context()
            require_permission(ctx, permission)
            return ctx

        def require_legacy_local(self):
            if os.getenv("LEADS_ENABLE_V1", "0").strip() != "1":
                raise AuthorizationError("legacy API is disabled")
            if self.client_address[0] not in {"127.0.0.1", "::1"}:
                raise AuthorizationError("legacy API is loopback-only")

        def _scope_campaign(self, ctx, campaign_id: str | None) -> None:
            if ctx.has_role("admin", "super_user"):
                return
            if ctx.has_role("agent", "supervisor") and not campaign_id:
                raise AuthorizationError("campaign is required for this role")
            if campaign_id and campaign_id not in ctx.campaign_ids:
                raise AuthorizationError("campaign is outside the caller scope")

        def _lead_for_ctx(self, ctx, lead_id: str):
            lead = get_lead(db_path, lead_id)
            if not lead:
                raise KeyError("lead not found")
            if not can_access_lead(ctx, lead):
                raise AuthorizationError("lead is outside the caller scope")
            return lead

        def _handle_error(self, exc: Exception):
            if isinstance(exc, AuthenticationError):
                self.send_json({"error": "unauthorized", "detail": str(exc)}, 401)
            elif isinstance(exc, AuthorizationError):
                self.send_json({"error": "forbidden", "detail": str(exc)}, 403)
            elif isinstance(exc, KeyError):
                self.send_json(
                    {"error": "not_found", "detail": str(exc).strip("'")}, 404
                )
            elif isinstance(exc, (DuplicateLeadError, ConcurrencyError)):
                self.send_json({"error": "conflict", "detail": str(exc)}, 409)
            elif isinstance(exc, (LifecycleError, SuppressedLeadError)):
                self.send_json({"error": "state_conflict", "detail": str(exc)}, 409)
            elif isinstance(exc, (TypeError, ValueError, json.JSONDecodeError)):
                self.send_json({"error": "bad_request", "detail": str(exc)}, 400)
            else:
                self.send_json({"error": "internal_error"}, 500)

        def do_GET(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self.send_text(DASHBOARD_HTML, "text/html; charset=utf-8")
                    return

                if parsed.path == "/assets/dashboard.css":
                    self.send_text(DASHBOARD_CSS, "text/css; charset=utf-8")
                    return

                if parsed.path == "/assets/dashboard.js":
                    self.send_text(DASHBOARD_JS, "application/javascript; charset=utf-8")
                    return

                if parsed.path == "/health":
                    self.send_json(
                        {"ok": True, "service": "leads-workstation", "version": "2.0"}
                    )
                    return

                if parsed.path == "/ready":
                    result = stats(db_path)
                    self.send_json(
                        {
                            "ok": True,
                            "service": "leads-workstation",
                            "backend": result["backend"],
                            "schema_version": result["schema_version"],
                        }
                    )
                    return

                if parsed.path == "/metrics":
                    if self.client_address[0] not in {"127.0.0.1", "::1"}:
                        self.require("audit:read")
                    self.send_text(
                        prometheus_metrics(db_path),
                        "text/plain; version=0.0.4; charset=utf-8",
                    )
                    return

                if parsed.path.startswith("/api/v2/"):
                    self._do_get_v2(parsed)
                    return

                if parsed.path.startswith("/api/"):
                    self.require_legacy_local()

                if parsed.path == "/api/stats":
                    self.send_json(stats(db_path))
                    return

                if parsed.path == "/api/candidates/summary":
                    q = parse_qs(parsed.query)
                    self.send_json(
                        candidate_summary(db_path, q.get("batch_id", [None])[0])
                    )
                    return

                if parsed.path == "/api/candidates":
                    q = parse_qs(parsed.query)
                    items = list_candidates(
                        db_path,
                        batch_id=q.get("batch_id", [None])[0],
                        disposition=q.get("disposition", [None])[0],
                        limit=int(q.get("limit", ["100"])[0]),
                    )
                    self.send_json({"items": items, "count": len(items)})
                    return

                if parsed.path == "/api/leads":
                    q = parse_qs(parsed.query)
                    items = list_leads(
                        db_path,
                        int(q.get("limit", ["50"])[0]),
                        int(q.get("offset", ["0"])[0]),
                        q.get("country", [None])[0],
                        q.get("category", [None])[0],
                        q.get("status", [None])[0],
                        q.get("q", [None])[0],
                    )
                    self.send_json({"items": items, "count": len(items)})
                    return

                if parsed.path.startswith("/api/leads/") and parsed.path.endswith(
                    "/events"
                ):
                    parts = parsed.path.strip("/").split("/")
                    if len(parts) == 4:
                        self.send_json({"items": lead_events(db_path, parts[2])})
                        return

                if parsed.path.startswith("/api/leads/"):
                    lead_id = parsed.path.split("/", 3)[-1]
                    lead = get_lead(db_path, lead_id)
                    self.send_json(
                        lead if lead else {"error": "not_found"},
                        200 if lead else 404,
                        {"ETag": f'"{lead["version"]}"'} if lead else None,
                    )
                    return

                self.send_json({"error": "not_found"}, 404)
            except Exception as exc:  # noqa: BLE001 - HTTP boundary maps unexpected failures safely
                self._handle_error(exc)

        def _do_get_v2(self, parsed):
            q = parse_qs(parsed.query)
            path = parsed.path
            parts = path.strip("/").split("/")

            if path == "/api/v2/me":
                ctx = self.auth_context()
                self.send_json(
                    {
                        "subject": ctx.subject,
                        "roles": sorted(ctx.roles),
                        "campaign_ids": sorted(ctx.campaign_ids),
                        "issuer": ctx.issuer,
                    }
                )
                return

            if path == "/api/v2/stats":
                self.require("audit:read")
                self.send_json(stats(db_path))
                return

            if path == "/api/v2/campaigns":
                ctx = self.require("campaign:read")
                campaigns = list_campaigns(db_path, q.get("state", [None])[0])
                if not ctx.has_role("admin", "super_user", "auditor", "readonly"):
                    campaigns = [
                        c for c in campaigns if c["campaign_id"] in ctx.campaign_ids
                    ]
                self.send_json({"items": campaigns, "count": len(campaigns)})
                return

            if len(parts) == 5 and parts[:3] == ["api", "v2", "campaigns"] and parts[4] == "members":
                ctx = self.require("campaign:read")
                campaign_id = parts[3]
                self._scope_campaign(ctx, campaign_id)
                items = list_campaign_members(db_path, campaign_id)
                self.send_json({"items": items, "count": len(items)})
                return

            if path == "/api/v2/leads":
                ctx = self.require("lead:read")
                items = list_leads(
                    db_path,
                    limit=int(q.get("limit", ["100"])[0]),
                    offset=int(q.get("offset", ["0"])[0]),
                    country=q.get("country", [None])[0],
                    category=q.get("category", [None])[0],
                    status=q.get("status", [None])[0],
                    q=q.get("q", [None])[0],
                    campaign_id=q.get("campaign_id", [None])[0],
                    assigned_agent=q.get("assigned_agent", [None])[0],
                )
                items = [lead for lead in items if can_access_lead(ctx, lead)]
                self.send_json({"items": items, "count": len(items)})
                return

            if len(parts) >= 4 and parts[:3] == ["api", "v2", "leads"]:
                ctx = self.require("lead:read")
                lead_id = parts[3]
                lead = self._lead_for_ctx(ctx, lead_id)
                if len(parts) == 4:
                    self.send_json(lead, extra_headers={"ETag": f'"{lead["version"]}"'})
                    return
                suffix = parts[4]
                if suffix == "contacts":
                    self.send_json({"items": list_contact_points(db_path, lead_id)})
                    return
                if suffix == "assignments":
                    self.require("audit:read")
                    self.send_json({"items": list_assignments(db_path, lead_id)})
                    return
                if suffix == "transitions":
                    self.require("audit:read")
                    self.send_json({"items": list_transitions(db_path, lead_id)})
                    return
                if suffix == "suppressions":
                    self.require("audit:read")
                    self.send_json({"items": list_suppressions(db_path, lead_id)})
                    return
                if suffix == "events":
                    self.require("audit:read")
                    self.send_json({"items": lead_events(db_path, lead_id)})
                    return

            if path == "/api/v2/outbox":
                self.require("outbox:read")
                items = list_outbox(
                    db_path,
                    status=q.get("status", [None])[0],
                    limit=int(q.get("limit", ["100"])[0]),
                )
                self.send_json({"items": items, "count": len(items)})
                return

            if path == "/api/v2/webhooks":
                self.require("webhook:manage")
                items = list_webhook_subscriptions(db_path)
                self.send_json({"items": items, "count": len(items)})
                return

            if path == "/api/v2/candidates":
                self.require("candidate:read")
                items = list_candidates(
                    db_path,
                    batch_id=q.get("batch_id", [None])[0],
                    disposition=q.get("disposition", [None])[0],
                    limit=int(q.get("limit", ["100"])[0]),
                )
                self.send_json({"items": items, "count": len(items)})
                return

            self.send_json({"error": "not_found"}, 404)

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/v2/"):
                    self._do_post_v2(parsed)
                    return

                if parsed.path.startswith("/api/"):
                    self.require_legacy_local()

                if parsed.path != "/api/leads":
                    self.send_json({"error": "not_found"}, 404)
                    return
                payload = self.read_json()
                lead = create_lead(
                    db_path,
                    payload,
                    actor="local-api",
                    request_id=self.request_id,
                )
                self.send_json(lead, 201, {"ETag": f'"{lead["version"]}"'})
            except Exception as exc:  # noqa: BLE001 - HTTP boundary maps unexpected failures safely
                self._handle_error(exc)

        def _do_post_v2(self, parsed):
            path = parsed.path
            parts = path.strip("/").split("/")
            payload = self.read_json()

            if path == "/api/v2/leads":
                ctx = self.require("lead:create")
                campaign_id = payload.get("campaign_id")
                self._scope_campaign(ctx, campaign_id)
                if ctx.has_role("agent"):
                    payload["assigned_agent"] = ctx.subject
                    payload["owner"] = ctx.subject
                    payload.setdefault("status", "Assigned")
                lead = create_lead(
                    db_path,
                    payload,
                    actor=ctx.subject,
                    request_id=self.request_id,
                )
                self.send_json(lead, 201, {"ETag": f'"{lead["version"]}"'})
                return

            if path == "/api/v2/campaigns":
                ctx = self.require("campaign:create")
                campaign = create_campaign(db_path, payload, actor=ctx.subject)
                self.send_json(campaign, 201)
                return

            if len(parts) == 5 and parts[:3] == ["api", "v2", "campaigns"] and parts[4] == "members":
                ctx = self.require("campaign:member")
                campaign_id = parts[3]
                self._scope_campaign(ctx, campaign_id)
                member = add_campaign_member(
                    db_path,
                    campaign_id,
                    str(payload.get("user_id") or ""),
                    str(payload.get("member_role") or ""),
                    active=bool(payload.get("active", True)),
                )
                self.send_json(member, 201)
                return

            if len(parts) == 5 and parts[:3] == ["api", "v2", "leads"]:
                lead_id = parts[3]
                action = parts[4]

                if action == "assign":
                    ctx = self.require("lead:assign")
                    self._lead_for_ctx(ctx, lead_id)
                    campaign_id = str(payload.get("campaign_id") or "")
                    self._scope_campaign(ctx, campaign_id)
                    if payload.get("strategy") == "round_robin":
                        lead = assign_round_robin(
                            db_path,
                            lead_id,
                            campaign_id,
                            assigned_by=ctx.subject,
                            reason=payload.get("reason") or "round-robin",
                        )
                    else:
                        lead = assign_lead(
                            db_path,
                            lead_id,
                            campaign_id,
                            str(payload.get("to_agent") or ""),
                            assigned_by=ctx.subject,
                            reason=payload.get("reason"),
                            expected_version=payload.get("expected_version"),
                        )
                    self.send_json(lead, extra_headers={"ETag": f'"{lead["version"]}"'})
                    return

                if action == "transition":
                    ctx = self.require("lead:transition")
                    self._lead_for_ctx(ctx, lead_id)
                    lead = transition_lead(
                        db_path,
                        lead_id,
                        str(payload.get("to_status") or ""),
                        actor=ctx.subject,
                        reason=payload.get("reason"),
                        expected_version=payload.get("expected_version"),
                    )
                    self.send_json(lead, extra_headers={"ETag": f'"{lead["version"]}"'})
                    return

                if action == "contacts":
                    ctx = self.require("lead:contact")
                    self._lead_for_ctx(ctx, lead_id)
                    contact = add_contact_point(
                        db_path,
                        lead_id,
                        str(payload.get("kind") or ""),
                        str(payload.get("value") or ""),
                        label=payload.get("label"),
                        primary=bool(payload.get("primary", False)),
                        verification_status=str(
                            payload.get("verification_status") or "unverified"
                        ),
                        source=str(payload.get("source") or "api"),
                        actor=ctx.subject,
                    )
                    self.send_json(contact, 201)
                    return

                if action == "suppress":
                    ctx = self.require("lead:suppress")
                    self._lead_for_ctx(ctx, lead_id)
                    lead = suppress_lead(
                        db_path,
                        lead_id,
                        channel=str(payload.get("channel") or ""),
                        reason=str(payload.get("reason") or ""),
                        actor=ctx.subject,
                        jurisdiction=payload.get("jurisdiction"),
                        source=payload.get("source"),
                    )
                    self.send_json(lead, extra_headers={"ETag": f'"{lead["version"]}"'})
                    return

                if action == "consent":
                    ctx = self.require("lead:consent")
                    self._lead_for_ctx(ctx, lead_id)
                    lead = record_consent(
                        db_path,
                        lead_id,
                        status=str(payload.get("status") or ""),
                        source=str(payload.get("source") or "api"),
                        actor=ctx.subject,
                        jurisdiction=payload.get("jurisdiction"),
                    )
                    self.send_json(lead, extra_headers={"ETag": f'"{lead["version"]}"'})
                    return

                if action == "unsuppress":
                    ctx = self.require("lead:suppress")
                    self._lead_for_ctx(ctx, lead_id)
                    lead = lift_suppression(
                        db_path,
                        lead_id,
                        actor=ctx.subject,
                        suppression_id=payload.get("suppression_id"),
                        channel=payload.get("channel"),
                        reason=payload.get("reason"),
                    )
                    self.send_json(lead, extra_headers={"ETag": f'"{lead["version"]}"'})
                    return

            if (
                len(parts) == 5
                and parts[:3] == ["api", "v2", "contact-points"]
                and parts[4] == "verify"
            ):
                ctx = self.require("lead:contact")
                contact_id = parts[3]
                contact = get_contact_point(db_path, contact_id)
                if not contact:
                    raise KeyError("contact point not found")
                self._lead_for_ctx(ctx, contact["lead_id"])
                item = verify_contact_point(
                    db_path,
                    contact_id,
                    verification_status=str(
                        payload.get("verification_status") or ""
                    ),
                    actor=ctx.subject,
                    source=str(payload.get("source") or "api-verification"),
                )
                self.send_json(item)
                return

            if path == "/api/v2/dedupe/preview":
                self.require("candidate:read")
                matches = find_duplicate_candidates(db_path, payload, limit=10)
                self.send_json({"items": matches, "count": len(matches)})
                return

            if path == "/api/v2/webhooks":
                self.require("webhook:manage")
                item = register_webhook_subscription(
                    db_path,
                    name=str(payload.get("name") or ""),
                    url=str(payload.get("url") or ""),
                    secret_ref=str(payload.get("secret_ref") or ""),
                    event_types=list(payload.get("event_types") or []),
                )
                self.send_json(item, 201)
                return

            self.send_json({"error": "not_found"}, 404)

        def do_PATCH(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/v2/campaigns/"):
                    parts = parsed.path.strip("/").split("/")
                    if len(parts) != 4:
                        self.send_json({"error": "not_found"}, 404)
                        return
                    ctx = self.require("campaign:update")
                    campaign_id = parts[3]
                    self._scope_campaign(ctx, campaign_id)
                    payload = self.read_json()
                    campaign = update_campaign(
                        db_path,
                        campaign_id,
                        payload,
                        actor=ctx.subject,
                    )
                    self.send_json(campaign)
                    return

                if parsed.path.startswith("/api/v2/leads/"):
                    parts = parsed.path.strip("/").split("/")
                    if len(parts) != 4:
                        self.send_json({"error": "not_found"}, 404)
                        return
                    ctx = self.require("lead:update")
                    lead_id = parts[3]
                    self._lead_for_ctx(ctx, lead_id)
                    payload = self.read_json()
                    if ctx.has_role("agent") and any(
                        key in payload
                        for key in ("campaign_id", "assigned_agent", "owner")
                    ):
                        raise AuthorizationError(
                            "agents cannot reassign campaign or ownership"
                        )
                    expected_version = _if_match(self.headers.get("If-Match"))
                    if expected_version is None:
                        raise ValueError("V2 PATCH requires If-Match with lead version")
                    lead = update_lead(
                        db_path,
                        lead_id,
                        payload,
                        actor=ctx.subject,
                        expected_version=expected_version,
                        request_id=self.request_id,
                    )
                    if lead is None:
                        self.send_json({"error": "not_found"}, 404)
                    else:
                        self.send_json(
                            lead, extra_headers={"ETag": f'"{lead["version"]}"'}
                        )
                    return

                if not parsed.path.startswith("/api/leads/"):
                    self.send_json({"error": "not_found"}, 404)
                    return
                self.require_legacy_local()
                lead_id = parsed.path.split("/", 3)[-1]
                payload = self.read_json()
                lead = update_lead(
                    db_path,
                    lead_id,
                    payload,
                    actor="local-api",
                    expected_version=_if_match(self.headers.get("If-Match")),
                    request_id=self.request_id,
                )
                if lead is None:
                    self.send_json({"error": "not_found"}, 404)
                else:
                    self.send_json(
                        lead, extra_headers={"ETag": f'"{lead["version"]}"'}
                    )
            except Exception as exc:  # noqa: BLE001 - HTTP boundary maps unexpected failures safely
                self._handle_error(exc)

    return Handler


def serve(db_path, host="127.0.0.1", port=8765, allow_network=False):
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if not loopback and not allow_network:
        raise SystemExit("Refusing non-loopback bind without --allow-network")
    if not loopback and os.getenv("LEADS_AUTH_MODE", "closed").strip().lower() != "keycloak":
        raise SystemExit("Network binding requires LEADS_AUTH_MODE=keycloak")
    print("Leads Workstation V2: http://" + host + ":" + str(port))
    ThreadingHTTPServer((host, port), make_handler(db_path)).serve_forever()
