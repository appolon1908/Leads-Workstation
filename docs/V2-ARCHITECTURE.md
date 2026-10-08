# Leads Workstation V2 Architecture

## Purpose

Leads Workstation V2 is the standalone Codestra lead-management service. It owns canonical lead ingestion, identity/deduplication, source provenance, contact verification, campaign assignment, compliance state, lifecycle transitions, audit history, and lead-domain integration events.

## Authority boundaries

- **Leads Workstation** owns canonical lead identity, ingestion, dedupe, provenance, verification, assignment history, suppression/consent, and lead lifecycle events.
- **Odoo CRM** owns downstream CRM opportunity workflow, customer/account conversion, commercial activities, and ERP-facing business processes.
- **Middleware** is the integration/command boundary between Leads Workstation, Odoo, VICIdial/contact-center services, n8n, WhatsApp and other providers.
- **n8n** consumes governed APIs/events. It must not write canonical lead tables directly.
- **Keycloak** is the production identity authority.
- **OpenBao** is the production secret authority for webhook and service secrets.
- **PostgreSQL** is the multi-user production database. SQLite remains supported for local/offline development and migration compatibility.
- **Redis** is optional for worker/event notification and can be used by surrounding orchestration without becoming canonical storage.

## V2 database model

The V2 schema adds:

- campaigns and campaign membership
- multi-value email/phone contact points
- assignment history
- lifecycle transition history
- consent and suppression/DNC records
- optimistic record versions
- identity fingerprints independent of caller-supplied lead IDs
- transactional outbox events
- webhook subscriptions containing secret references, never raw webhook secrets

Existing V1 SQLite databases are upgraded in place. New columns are added before V2 indexes are created, and existing lead identities are backfilled.

## Lead lifecycle

Governed transitions:

Needs Verification → New / DNC / Lost

New → Assigned / DNC / Lost

Assigned → Attempted / New / DNC / Lost

Attempted → Contacted / Assigned / DNC / Lost

Contacted → Qualified / Attempted / DNC / Lost

Qualified → Appointment / Contacted / DNC / Lost

Appointment → Converted / Qualified / DNC / Lost

Converted is terminal. DNC is terminal unless an authorized suppression-lift workflow explicitly restores the lead.

Suppressed or DNC leads cannot enter an outreach assignment/engagement path.

## Campaign hierarchy

Campaigns have:

- unique campaign code
- inbound/outbound/blended type
- draft/active/paused/closed/archived state
- primary supervisor
- backup supervisors
- agents
- QA/auditor members
- client, start/end and description metadata

Round-robin assignment chooses the active campaign agent with the fewest currently open assigned leads, then records an immutable assignment event.

## Identity and RBAC

V2 is fail-closed by default.

Production mode uses Keycloak JWT/JWKS validation with issuer and audience checks. Supported application roles include:

- admin
- super_user
- supervisor
- agent
- importer
- auditor
- readonly

Agent visibility is limited to assigned leads inside authorized campaigns. Supervisor visibility is campaign-scoped. Sensitive administrative operations remain restricted to elevated roles.

A loopback-only development authentication mode is available for local certification.

## Duplicate protection

V2 prevents an API caller from bypassing duplicate detection by supplying a fresh lead ID.

Identity scoring considers:

- exact email
- exact phone
- business/email domain
- normalized/fuzzy name similarity
- country
- city

High-confidence matches classify as duplicate; medium-confidence matches go to candidate review; low-confidence records remain new.

## Import pipeline

Import profiles support generic CSV, Odoo exports and VICIdial exports. Historical XLSX appraiser ingestion remains supported.

The governed path is:

preview → normalize → score/dedupe → candidate review → promote

Imports never allow automation tools to become the canonical database writer.

## Contact verification

Email and phone values live as first-class contact points with:

- type
- normalized value
- label
- primary flag
- verification status
- source
- timestamps

Verification states include unverified, valid, invalid, risky, historical and do_not_contact.

## Compliance

V2 records:

- consent status/source/time
- jurisdiction
- channel-specific suppressions
- DNC state
- suppression reasons and source
- lift history

Outbound integrations must check these fields before effects are allowed.

## Concurrency and audit

Each lead carries a monotonically increasing version.

V2 PATCH requests require If-Match. Stale writers receive a conflict instead of silently overwriting newer work.

Every material operation records audit events and emits a transactional outbox event where appropriate.

## Events and webhooks

Outbox events are created inside the same database transaction as the lead-domain change.

The worker:

- discovers active webhook subscriptions
- resolves secrets from env:// or openbao:// references
- signs webhook payloads with HMAC-SHA256
- supplies event and idempotency headers
- retries failures with exponential backoff
- marks exhausted deliveries failed
- optionally publishes completion notifications to Redis

## API surfaces

Primary V2 surfaces include:

- /api/v2/me
- /api/v2/stats
- /api/v2/campaigns
- /api/v2/leads
- /api/v2/leads/{id}/contacts
- /api/v2/leads/{id}/assign
- /api/v2/leads/{id}/transition
- /api/v2/leads/{id}/suppress
- /api/v2/leads/{id}/unsuppress
- /api/v2/leads/{id}/consent
- /api/v2/contact-points/{id}/verify
- /api/v2/candidates
- /api/v2/dedupe/preview
- /api/v2/outbox
- /api/v2/webhooks

Operational endpoints:

- /health
- /ready
- /metrics

The legacy V1 API is disabled by default and, when explicitly enabled, remains loopback-only.

## Dashboard

The root application serves an authenticated V2 dashboard with:

- overview metrics
- lead search/filtering
- lifecycle Kanban
- campaign view
- candidate review
- outbox view
- lead focus with contact points, assignment history and transitions

Bearer credentials are kept in browser memory only. Development headers are intended only for loopback development mode.

## Deployment

docker-compose.v2.yml provides:

- PostgreSQL 18
- Redis 7
- V2 API
- V2 worker

The exposed API port is bound to loopback by default.

## Backup security

V2 includes AES-GCM encrypted backup primitives. Backup encryption keys are resolved through environment/OpenBao references and are never committed to the repository.

## Promotion requirements

A governed V2 promotion requires:

1. unit/regression tests
2. Python compilation
3. PostgreSQL 18 integration tests
4. Redis connectivity tests
5. SQLite→PostgreSQL migration parity
6. Docker Compose validation
7. private-data git-ignore enforcement
8. required Codestra control-plane checks

## Internal Middleware service identity

For isolated staging where the live Keycloak service runtime is not yet available, V2 supports an explicit `LEADS_AUTH_MODE=service` mode for Middleware-to-Leads traffic.

This mode is not enabled by default. It requires all of the following:

- a bearer token supplied from a secret store or root-owned runtime environment
- an explicit source CIDR allowlist
- the fixed least-privilege `middleware_service` role
- explicit campaign scope configuration

The service role can perform governed lead-domain operations and read campaign metadata, but cannot create or mutate campaign authority, campaign membership, or webhook administration. Production user and agent authentication remains Keycloak.
