# Leads Workstation

Local-first lead operations platform for Codestra.

## Implemented runtime

This repository now contains a working lead workstation, not only architecture documents:

- streaming import of the laptop lead master
- SQLite canonical runtime with indexed search fields
- deterministic dedupe fingerprints using email, then phone, then entity identity
- SHA-256 source evidence and import-batch ledger
- duplicate review ledger
- per-lead audit events
- searchable local JSON API and local landing page
- loopback-only network safety by default
- Git LFS declarations for future approved private lead-data publication
- automated unit tests and CI

Install on the laptop:

1. cd C:\Users\Usuario\Documents\GitHub\Leads-Workstation
2. .\scripts\install.ps1
3. .\scripts\stage-private-data.ps1
4. .\scripts\import-master.ps1
5. .\scripts\start.ps1

Then open http://127.0.0.1:8765

## Mission

Provide one searchable, editable, auditable lead workspace while keeping Country and Business Category as separate first-class fields.

## Repository workflow

1. 00 Authority & Architecture - data authority, schema, contracts, country/business taxonomies.
2. 10 Build & Test - Leads API, UI, validation, audit history, local service.
3. 20 Integration & Dependencies - Meltano importer, Database-migrations, n8n, future CRM/contact-center adapters.
4. 30 Staging & Release - local certification, backup/restore, desktop launcher, operational handoff.

## System boundaries

- Leads-Workstation owns canonical lead business rules, CRUD/query API, dashboard UI and audit surface.
- Meltano-Leads-Importer owns extraction/loading into raw import staging.
- Database-migrations- owns PostgreSQL schemas, roles, grants, migrations and backup/restore contracts.
- N8N owns downstream automation after a lead is accepted and must not become the canonical lead database.

Write rule: n8n direct writes to canonical PostgreSQL lead tables are forbidden.

Allowed writes:
- Meltano to lead_import_raw
- Leads API to canonical leads and audit
- n8n to Leads API or governed command

## Sensitive lead data

The GitHub repository was public when this implementation started. The actual lead payload is staged locally under data/private and is git-ignored until repository privacy is verified as PRIVATE. No lead PII should be committed to a public branch.
