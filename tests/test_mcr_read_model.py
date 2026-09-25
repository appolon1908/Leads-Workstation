
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.mcr_read_model import build_mcr_router

TENANT = "TENANT_MCR_B"
LEAD = UUID("00000000-0000-4000-8000-000000000042")


class FakeCursor:
    def __init__(self, *, fetchones=None, fetchalls=None, execute_error: Exception | None = None):
        self.fetchones = list(fetchones or [])
        self.fetchalls = list(fetchalls or [])
        self.execute_error = execute_error
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        if self.execute_error:
            raise self.execute_error

    def fetchone(self):
        return self.fetchones.pop(0) if self.fetchones else None

    def fetchall(self):
        return self.fetchalls.pop(0) if self.fetchalls else []


def client_for(cursor: FakeCursor) -> TestClient:
    @contextmanager
    def fake_db():
        yield object(), cursor

    app = FastAPI()
    app.include_router(build_mcr_router(fake_db))
    return TestClient(app)


def headers(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Codestra-Tenant-Id": tenant, "X-Codestra-Actor": "tester"}


def setup_function():
    os.environ["LEADS_MCR_TENANT_ID"] = TENANT


def test_tenant_context_fails_closed_and_rejects_cross_tenant():
    c = client_for(FakeCursor())
    assert c.get("/api/mcr/status").status_code == 401
    denied = c.get("/api/mcr/status", headers=headers("OTHER"))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "mcr_tenant_forbidden"

    del os.environ["LEADS_MCR_TENANT_ID"]
    unavailable = c.get("/api/mcr/status", headers=headers())
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "mcr_tenant_context_unavailable"


def test_status_is_read_only_and_reports_projection_readiness():
    cursor = FakeCursor(fetchones=[{
        "lead_projection": "leads.mcr_lead_projection",
        "exposure_projection": "leads.mcr_exposure_projection",
        "delivery_projection": "leads.mcr_delivery_projection",
    }])
    response = client_for(cursor).get("/api/mcr/status", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["provider_effects"] == "none"
    assert body["authority"]["decisioning"] == "Middleware MCR-C"
    assert len(cursor.executed) == 1
    assert cursor.executed[0][1] is None


def test_summary_is_tenant_bound_and_contains_projection_state():
    cursor = FakeCursor(
        fetchones=[
            {
                "tenant_id": TENANT,
                "lead_id": LEAD,
                "lifecycle_state": "ELIGIBLE",
                "lifecycle_version": 3,
                "engagement_score": 72.5,
                "next_eligible_at": datetime(2026, 9, 26, tzinfo=UTC),
                "next_action_reason": "COOLDOWN_COMPLETE",
                "middleware_decision_id": "decision-1",
                "updated_at": datetime(2026, 9, 25, tzinfo=UTC),
            },
        ],
        fetchalls=[
            [{"channel": "email", "state": "valid", "occurred_at": datetime(2026, 9, 25, tzinfo=UTC), "address_ref": "email:1"}],
            [{"suppression_id": "sup-1", "scope": "channel", "channel": "sms", "campaign_id": None, "reason": "unsubscribe", "occurred_at": datetime(2026, 9, 25, tzinfo=UTC)}],
        ],
    )
    response = client_for(cursor).get(f"/api/mcr/leads/{LEAD}/summary", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == TENANT
    assert body["lifecycle_state"] == "ELIGIBLE"
    assert body["provider_effects"] == "none"
    assert body["source_authority"] == "Middleware MCR-C + Leads projection"
    projection_query = cursor.executed[0]
    assert "where tenant_id=%s and lead_id=%s" in projection_query[0].lower()
    assert projection_query[1] == (TENANT, LEAD)


def test_journey_is_bounded_paginated_and_empty_is_explicit():
    cursor = FakeCursor(
        fetchones=[
            {"lifecycle_state": "COOLING"},
        ],
        fetchalls=[[], []],
    )
    response = client_for(cursor).get(
        f"/api/mcr/leads/{LEAD}/journey?limit=25&offset=50", headers=headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lifecycle_state"] == "COOLING"
    assert body["exposures"] == []
    assert body["deliveries"] == []
    assert body["has_more"] is False
    assert cursor.executed[1][1][-2:] == (26, 50)
    assert cursor.executed[2][1][-2:] == (26, 50)

    too_large = client_for(FakeCursor()).get(
        f"/api/mcr/leads/{LEAD}/journey?limit=201", headers=headers()
    )
    assert too_large.status_code == 422


def test_queue_filters_are_tenant_bound_and_bounded():
    row = {
        "lead_id": LEAD,
        "business_name": "Acme",
        "lifecycle_state": "ENGAGED",
        "engagement_score": 91.0,
        "next_eligible_at": None,
        "next_action_reason": "HUMAN_HANDOFF",
        "updated_at": datetime(2026, 9, 25, tzinfo=UTC),
    }
    cursor = FakeCursor(fetchalls=[[row, row]])
    response = client_for(cursor).get(
        "/api/mcr/queues/engaged?limit=1&offset=5&country=DO&owner=Ralph",
        headers=headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["has_more"] is True
    sql, params = cursor.executed[0]
    assert "p.tenant_id=%s" in sql
    assert params[0] == TENANT
    assert params[-2:] == (2, 5)
    assert "l.country=%s" in sql and "l.owner_name=%s" in sql


def test_projection_storage_errors_are_explicit_503_not_false_empty():
    response = client_for(FakeCursor(execute_error=RuntimeError("missing relation"))).get(
        f"/api/mcr/leads/{LEAD}/summary", headers=headers()
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "projection_unavailable"
    assert detail["effects"] == "none"


def test_mcr_router_has_get_only_read_surfaces():
    @contextmanager
    def fake_db():
        yield object(), FakeCursor()

    router = build_mcr_router(fake_db)
    methods = {(route.path, method) for route in router.routes for method in route.methods}
    assert methods
    assert {method for _, method in methods} == {"GET"}
    assert not any("/execute" in path or "/suppressions" in path for path, _ in methods)


def test_ui_declares_mcr_lifecycle_states_and_unavailable_state():
    html = (Path(__file__).resolve().parents[1] / "app/static/index.html").read_text()
    for marker in (
        "Lifecycle & Journey",
        "mcrLifecycle",
        "projection_unavailable",
        "MCR tenant context is not configured",
        "eligible",
        "engaged",
        "cooling",
        "suppressed",
        "converted",
    ):
        assert marker in html


def test_main_app_registers_only_read_only_mcr_openapi_operations():
    from app.main import app

    schema = app.openapi()
    mcr_paths = {path: item for path, item in schema["paths"].items() if path.startswith("/api/mcr/")}
    assert {
        "/api/mcr/status",
        "/api/mcr/leads/{lead_id}/summary",
        "/api/mcr/leads/{lead_id}/journey",
        "/api/mcr/queues/{queue}",
    } <= set(mcr_paths)
    for item in mcr_paths.values():
        assert set(item).issubset({"get", "parameters"})
