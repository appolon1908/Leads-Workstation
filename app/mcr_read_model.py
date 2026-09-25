
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

LifecycleState = Literal[
    "NEW", "VALIDATED", "ELIGIBLE", "ACTIVE_CYCLE", "ENGAGED",
    "COOLING", "REACTIVATION", "CONVERTED", "SUPPRESSED",
]
ChannelState = Literal[
    "unknown", "valid", "possible", "soft_bounce", "hard_bounce",
    "complained", "unsubscribed", "suppressed", "invalid",
]
QUEUE_STATES = {
    "eligible": ("ELIGIBLE",),
    "engaged": ("ENGAGED",),
    "cooling": ("COOLING",),
    "suppressed": ("SUPPRESSED",),
    "converted": ("CONVERTED",),
}
PROJECTION_TABLES = (
    "leads.mcr_lead_projection",
    "leads.mcr_channel_health_projection",
    "leads.mcr_suppression_projection",
    "leads.mcr_exposure_projection",
    "leads.mcr_delivery_projection",
)


class McrProjectionUnavailable(RuntimeError):
    pass


class McrContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    actor: str
    effects: Literal["none"] = "none"
    authority: Literal["Leads-Workstation read model"] = "Leads-Workstation read model"


class McrChannelHealth(BaseModel):
    channel: str
    state: ChannelState
    occurred_at: datetime | None = None
    address_ref: str | None = None


class McrSuppression(BaseModel):
    suppression_id: str
    scope: str
    channel: str | None = None
    campaign_id: str | None = None
    reason: str
    occurred_at: datetime | None = None


class McrExposure(BaseModel):
    campaign_id: str
    campaign_version: int
    channel: str
    touch_index: int
    status: str
    reserved_at: datetime | None = None
    engagement_outcome: str | None = None
    negative_outcome: str | None = None


class McrDelivery(BaseModel):
    event_id: str
    event_type: str
    channel: str
    campaign_id: str | None = None
    occurred_at: datetime | None = None
    projection_state: str | None = None


class McrLeadSummary(BaseModel):
    tenant_id: str
    lead_id: UUID
    lifecycle_state: LifecycleState
    lifecycle_version: int = Field(ge=1)
    engagement_score: float | None = None
    next_eligible_at: datetime | None = None
    next_action_reason: str | None = None
    middleware_decision_id: str | None = None
    updated_at: datetime | None = None
    channel_health: list[McrChannelHealth] = Field(default_factory=list)
    suppressions: list[McrSuppression] = Field(default_factory=list)
    source_authority: Literal["Middleware MCR-C + Leads projection"] = "Middleware MCR-C + Leads projection"
    provider_effects: Literal["none"] = "none"


class McrJourneyPage(BaseModel):
    tenant_id: str
    lead_id: UUID
    lifecycle_state: LifecycleState
    exposures: list[McrExposure]
    deliveries: list[McrDelivery]
    limit: int
    offset: int
    has_more: bool
    provider_effects: Literal["none"] = "none"


class McrQueueItem(BaseModel):
    lead_id: UUID
    business_name: str
    lifecycle_state: LifecycleState
    engagement_score: float | None = None
    next_eligible_at: datetime | None = None
    next_action_reason: str | None = None
    updated_at: datetime | None = None


class McrQueuePage(BaseModel):
    queue: str
    tenant_id: str
    items: list[McrQueueItem]
    limit: int
    offset: int
    has_more: bool
    provider_effects: Literal["none"] = "none"


def _safe_actor(value: str | None) -> str:
    actor = (value or "local-workstation").strip()
    return actor[:200] or "local-workstation"


def _tenant_context(
    x_codestra_tenant_id: str | None,
    x_codestra_actor: str | None,
) -> McrContext:
    configured = (os.getenv("LEADS_MCR_TENANT_ID") or "").strip()
    if not configured:
        raise HTTPException(
            503,
            {
                "code": "mcr_tenant_context_unavailable",
                "message": "MCR tenant context is not configured on this workstation.",
                "effects": "none",
            },
        )
    supplied = (x_codestra_tenant_id or "").strip()
    if not supplied:
        raise HTTPException(
            401,
            {
                "code": "mcr_tenant_required",
                "message": "X-Codestra-Tenant-Id is required.",
                "effects": "none",
            },
        )
    if supplied != configured:
        raise HTTPException(
            403,
            {
                "code": "mcr_tenant_forbidden",
                "message": "The requested tenant does not match the workstation tenant binding.",
                "effects": "none",
            },
        )
    return McrContext(tenant_id=configured, actor=_safe_actor(x_codestra_actor))


def _projection_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        503,
        {
            "code": "projection_unavailable",
            "message": "MCR Leads projection storage is not provisioned or not readable.",
            "dependency": "Database-migrations- MCR-B projection schema",
            "effects": "none",
            "detail": exc.__class__.__name__,
        },
    )


def build_mcr_router(db_factory: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/mcr", tags=["MCR Leads read model"])

    @router.get("/status")
    def mcr_status(
        x_codestra_tenant_id: str | None = Header(default=None),
        x_codestra_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        ctx = _tenant_context(x_codestra_tenant_id, x_codestra_actor)
        try:
            with db_factory() as (_, cur):
                cur.execute(
                    """
                    select to_regclass('leads.mcr_lead_projection') lead_projection,
                           to_regclass('leads.mcr_exposure_projection') exposure_projection,
                           to_regclass('leads.mcr_delivery_projection') delivery_projection
                    """
                )
                row = cur.fetchone() or {}
        except Exception as exc:
            raise _projection_unavailable(exc) from exc
        ready = all(row.get(key) for key in ("lead_projection", "exposure_projection", "delivery_projection"))
        return {
            "ok": ready,
            "tenant_id": ctx.tenant_id,
            "projection_ready": ready,
            "provider_effects": "none",
            "authority": {
                "decisioning": "Middleware MCR-C",
                "read_model": "Leads-Workstation",
                "schema": "Database-migrations-",
            },
        }

    @router.get("/leads/{lead_id}/summary", response_model=McrLeadSummary)
    def mcr_summary(
        lead_id: UUID,
        x_codestra_tenant_id: str | None = Header(default=None),
        x_codestra_actor: str | None = Header(default=None),
    ) -> McrLeadSummary:
        ctx = _tenant_context(x_codestra_tenant_id, x_codestra_actor)
        try:
            with db_factory() as (_, cur):
                cur.execute(
                    """
                    select tenant_id,lead_id,lifecycle_state,lifecycle_version,
                           engagement_score,next_eligible_at,next_action_reason,
                           middleware_decision_id,updated_at
                    from leads.mcr_lead_projection
                    where tenant_id=%s and lead_id=%s
                    """,
                    (ctx.tenant_id, lead_id),
                )
                base = cur.fetchone()
                if base is None:
                    raise HTTPException(
                        404,
                        {"code": "mcr_projection_not_found", "lead_id": str(lead_id), "effects": "none"},
                    )
                cur.execute(
                    """
                    select channel,state,occurred_at,address_ref
                    from leads.mcr_channel_health_projection
                    where tenant_id=%s and lead_id=%s
                    order by channel
                    """,
                    (ctx.tenant_id, lead_id),
                )
                channels = cur.fetchall()
                cur.execute(
                    """
                    select suppression_id,scope,channel,campaign_id,reason,occurred_at
                    from leads.mcr_suppression_projection
                    where tenant_id=%s and lead_id=%s
                    order by occurred_at desc nulls last,suppression_id
                    limit 100
                    """,
                    (ctx.tenant_id, lead_id),
                )
                suppressions = cur.fetchall()
        except HTTPException:
            raise
        except Exception as exc:
            raise _projection_unavailable(exc) from exc
        return McrLeadSummary(
            **base,
            channel_health=channels,
            suppressions=suppressions,
        )

    @router.get("/leads/{lead_id}/journey", response_model=McrJourneyPage)
    def mcr_journey(
        lead_id: UUID,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0, le=10000),
        x_codestra_tenant_id: str | None = Header(default=None),
        x_codestra_actor: str | None = Header(default=None),
    ) -> McrJourneyPage:
        ctx = _tenant_context(x_codestra_tenant_id, x_codestra_actor)
        try:
            with db_factory() as (_, cur):
                cur.execute(
                    """
                    select lifecycle_state
                    from leads.mcr_lead_projection
                    where tenant_id=%s and lead_id=%s
                    """,
                    (ctx.tenant_id, lead_id),
                )
                state = cur.fetchone()
                if state is None:
                    raise HTTPException(
                        404,
                        {"code": "mcr_projection_not_found", "lead_id": str(lead_id), "effects": "none"},
                    )
                cur.execute(
                    """
                    select campaign_id,campaign_version,channel,touch_index,status,reserved_at,
                           engagement_outcome,negative_outcome
                    from leads.mcr_exposure_projection
                    where tenant_id=%s and lead_id=%s
                    order by reserved_at desc nulls last,campaign_id,campaign_version,touch_index
                    limit %s offset %s
                    """,
                    (ctx.tenant_id, lead_id, limit + 1, offset),
                )
                exposures = cur.fetchall()
                cur.execute(
                    """
                    select event_id,event_type,channel,campaign_id,occurred_at,projection_state
                    from leads.mcr_delivery_projection
                    where tenant_id=%s and lead_id=%s
                    order by occurred_at desc nulls last,event_id
                    limit %s offset %s
                    """,
                    (ctx.tenant_id, lead_id, limit + 1, offset),
                )
                deliveries = cur.fetchall()
        except HTTPException:
            raise
        except Exception as exc:
            raise _projection_unavailable(exc) from exc
        return McrJourneyPage(
            tenant_id=ctx.tenant_id,
            lead_id=lead_id,
            lifecycle_state=state["lifecycle_state"],
            exposures=exposures[:limit],
            deliveries=deliveries[:limit],
            limit=limit,
            offset=offset,
            has_more=len(exposures) > limit or len(deliveries) > limit,
        )

    @router.get("/queues/{queue}", response_model=McrQueuePage)
    def mcr_queue(
        queue: str,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0, le=10000),
        country: str | None = Query(default=None, max_length=120),
        business_category: str | None = Query(default=None, max_length=200),
        owner: str | None = Query(default=None, max_length=200),
        x_codestra_tenant_id: str | None = Header(default=None),
        x_codestra_actor: str | None = Header(default=None),
    ) -> McrQueuePage:
        ctx = _tenant_context(x_codestra_tenant_id, x_codestra_actor)
        states = QUEUE_STATES.get(queue)
        if states is None:
            raise HTTPException(
                404,
                {
                    "code": "mcr_queue_not_found",
                    "allowed": sorted(QUEUE_STATES),
                    "effects": "none",
                },
            )
        where = ["p.tenant_id=%s", "p.lifecycle_state=ANY(%s)"]
        params: list[Any] = [ctx.tenant_id, list(states)]
        for column, value in (
            ("l.country", country),
            ("l.business_category", business_category),
            ("l.owner_name", owner),
        ):
            if value:
                where.append(f"{column}=%s")
                params.append(value)
        params.extend([limit + 1, offset])
        try:
            with db_factory() as (_, cur):
                cur.execute(
                    f"""
                    select l.lead_id,l.business_name,p.lifecycle_state,p.engagement_score,
                           p.next_eligible_at,p.next_action_reason,p.updated_at
                    from leads.mcr_lead_projection p
                    join leads.leads l on l.lead_id=p.lead_id
                    where {' and '.join(where)}
                    order by p.next_eligible_at nulls last,p.updated_at desc,l.lead_id
                    limit %s offset %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        except Exception as exc:
            raise _projection_unavailable(exc) from exc
        return McrQueuePage(
            queue=queue,
            tenant_id=ctx.tenant_id,
            items=rows[:limit],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    return router
