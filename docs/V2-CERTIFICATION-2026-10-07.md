# Leads Workstation V2 Certification — Final Evidence

Final certification completed on **2026-10-08** for branch:

`feature/leads-v2-platform-20261007`

## Certification result

**PASS**

### Full production suite

- 25 tests passed
- Python compilation passed
- security scan passed
- V2 artifact checks passed
- private-data git-ignore enforcement passed
- SQLite schema V2 initialization passed
- PostgreSQL integration enabled and passed
- Redis integration enabled and passed
- Docker Compose V2 configuration validated separately with Docker socket access
- no raw lead/contact payload committed

### PostgreSQL 18 evidence

Validated against the healthy Ubuntu development PostgreSQL 18 runtime using an isolated certification database.

Passed:

- schema V2 initialization
- campaign creation and membership
- lead creation
- multi-contact persistence
- assignment
- lifecycle transition
- SQLite → PostgreSQL migration
- table-count parity
- PostgreSQL identity/sequence behavior

### Redis evidence

Validated against the healthy Ubuntu development Redis runtime.

Passed:

- PING
- SET
- GET
- worker notification client compatibility

The integration test uses bounded retry behavior for short startup/network jitter but fails if Redis remains unavailable.

### Regression and V2 coverage

Passed coverage includes:

- original V1 API foundation
- original import idempotency
- candidate promotion
- canonical lead-ID import behavior
- email/phone normalization
- API-supplied lead ID cannot bypass duplicate detection
- identity fingerprint refresh after mutable identity updates
- optimistic record locking/version conflict
- campaign hierarchy
- campaign updates
- active campaign membership
- round-robin assignment
- assignment history
- governed lifecycle transitions
- suppression and DNC enforcement
- suppression lift
- consent state
- multiple email/phone contact points
- contact verification
- candidate review/dedupe scoring
- webhook registration safety
- private-IP webhook rejection without explicit development opt-in
- transactional outbox
- outbox worker
- Prometheus metrics
- HTTP RBAC/campaign scoping
- V2 fail-closed authentication behavior
- legacy V1 API disabled by default
- encrypted SQLite backup round trip
- in-place V1 SQLite → schema V2 upgrade
- PostgreSQL migration parity
- Redis connectivity

## Implemented V2 platform

- schema version 2
- SQLite local/offline compatibility
- PostgreSQL production backend
- Keycloak JWT/JWKS authentication
- application RBAC
- campaign hierarchy and membership
- assignment routing/history
- lifecycle engine
- multiple contact points
- contact verification
- stronger duplicate scoring
- generic/Odoo/VICIdial import profiles
- consent/suppression/DNC controls
- optimistic locking with `If-Match`
- audit events with request IDs
- transactional outbox
- signed HMAC webhook worker
- retry/failure handling
- Redis event notification support
- OpenBao/environment secret references
- health/readiness/Prometheus metrics
- authenticated V2 operations dashboard
- OpenAPI 3.1 contract
- AES-GCM encrypted backup primitives
- Docker application/worker/PostgreSQL/Redis deployment definition
- repository privacy/credential scan
- PostgreSQL/Redis required CI gate
- production/testing/staging/development/main workflow coverage

## Security posture

- V2 authentication is fail-closed by default.
- Development-header authentication is loopback-only.
- Legacy V1 API is disabled by default and loopback-only if explicitly enabled.
- API containers bind to loopback by default in the supplied Compose definition.
- webhook secrets are stored as references, not raw secret values.
- OpenBao and environment secret references are supported.
- webhook payloads are signed with HMAC-SHA256.
- webhook registration rejects unsafe private-address destinations unless explicitly allowed for development.
- private lead payload, runtime databases, key material and non-template environment files are blocked by repository scanning.
- encrypted backups use AES-GCM.
- no lead/contact PII was added to this branch.

## Current canonical data

The V2 code is compatible with the existing certified workstation dataset. Raw lead/contact payload remains outside Git.

Previous certified canonical runtime evidence remains:

- baseline master: 88,379
- governed appraiser candidates promoted: 107
- certified canonical runtime total: 88,486

## Promotion decision

The V2 feature branch is **certified for pull-request review into `development`**.

Production activation remains a separate promotion decision. No provider effects, outbound messaging, calling, WhatsApp delivery, or production deployment are enabled by this certification.
