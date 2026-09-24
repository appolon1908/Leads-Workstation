# Leads Workstation

Local-first lead operations platform for Codestra on the Ubuntu desktop.

## Mission

Provide one searchable, editable, auditable lead workspace with Monday-style views while keeping **Country** and **Business Category** as separate first-class fields.

## Repository workflow

1. **00 Authority & Architecture** — data authority, schema, contracts, country/business taxonomies.
2. **10 Build & Test** — Leads API, UI, validation, audit history, local service.
3. **20 Integration & Dependencies** — Meltano importer, Database-migrations, n8n, future CRM/contact-center adapters.
4. **30 Staging & Release** — local certification, backup/restore, desktop launcher, operational handoff.

## System boundaries

- **Leads-Workstation owns:** canonical lead business rules, CRUD API, dashboard UI, lead activity/audit surface.
- **Meltano-Leads-Importer owns:** extraction/loading into raw import staging and import batch evidence.
- **Database-migrations- owns:** PostgreSQL schemas, roles, grants, migrations, backup/restore database contracts.
- **N8N owns:** downstream automation/orchestration after a lead is accepted; it must not become the canonical lead database.

### Write rule

`n8n -> PostgreSQL direct write` is forbidden for canonical lead records.

Allowed write paths:

`Meltano -> lead_import_raw + append-only row provenance manifest`

`raw provenance -> Leads API promotion candidate -> explicit review/approval -> canonical leads + audit/outbox`

`Leads API -> canonical leads + audit`

`n8n -> Leads API / governed command`

## Required views

Executive · All Leads · Kanban · By Country · By Business · My Work · Data Quality · Import History · Lead Focus.

## Control plane

Linear project: Leads Workstation — Ubuntu Desktop  
Notion workstation: Codestra — Leads Workstation


### Promotion safety gate

The backup workstation does not promote raw rows directly. `lead_ops.import_row_manifest` binds a candidate to an exact staged batch/row/fingerprint tuple. Candidate queue/review operations perform zero canonical writes. Canonical promotion is allowed only for an explicitly approved candidate whose batch is completed and has both `provenance_manifest_verified=true` and `promotion_authorized=true`. The currently frozen real batch remains `promotion_authorized=false` until the release authority changes it through a governed checkpoint.
