# MCR-B Leads projection requirements

MCR-B adds **read-model and UI authority only** to Leads-Workstation. Middleware MCR-C at
`7d713735e46a0d0efc437808ad34f42ecdc41c6c` remains authoritative for eligibility,
next-action decisioning, suppression policy, execution/idempotency, and reconciliation.

## Required projection schema

`Database-migrations-` owns creation and lifecycle of these tenant-bound tables:

- `leads.mcr_lead_projection`
- `leads.mcr_channel_health_projection`
- `leads.mcr_suppression_projection`
- `leads.mcr_exposure_projection`
- `leads.mcr_delivery_projection`

Leads-Workstation intentionally does not create or migrate these tables. If they are absent,
the MCR APIs return `503 projection_unavailable`; they never return a false empty journey.

## API contract

All MCR endpoints are GET-only and require `X-Codestra-Tenant-Id`. The header must equal the
workstation binding in `LEADS_MCR_TENANT_ID`; missing context returns 401 and cross-tenant
requests return 403.

- `GET /api/mcr/status`
- `GET /api/mcr/leads/{lead_id}/summary`
- `GET /api/mcr/leads/{lead_id}/journey?limit=&offset=`
- `GET /api/mcr/queues/{eligible|engaged|cooling|suppressed|converted}?limit=&offset=`

Journey and queue pagination is bounded to 200 records per request and 10,000 offset.
Every response declares `provider_effects=none`.

## UI contract

The Lifecycle & Journey workspace provides:

- eligible, engaged, cooling, suppressed and converted queues;
- lifecycle state/version and engagement score;
- next-eligible timestamp and decision reason readback;
- channel-health and suppression visibility;
- campaign exposure timeline;
- delivery/engagement projection timeline;
- explicit loading, empty, forbidden, error and unavailable states.

No UI action can execute a campaign, change suppression policy, dispatch a provider message,
or mutate Middleware MCR authority.

## Release gate

MCR-B is not complete until Database-migrations provisions the projection schema and restart/readback
is certified against the exact candidate SHA. Production/provider effects remain fail-closed.
