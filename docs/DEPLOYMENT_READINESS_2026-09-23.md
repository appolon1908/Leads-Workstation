# Leads Workstation — Backup/Local Deployment Readiness

Date: 2026-09-23
Host: desktop-ubuntu-codestra
Authority: backup/local execution and recovery only; not production authority.

## Verified

- PostgreSQL 18.6 local instance is reachable on 127.0.0.1:5432.
- Database leads_workstation has schemas lead_import_raw, leads, lead_audit, and lead_ops.
- Eight contract tables are present across `leads`, `lead_audit`, and `lead_ops`; governed raw staging remains separate.
- Roles leads_owner, leads_importer, leads_app, and leads_readonly exist; no n8n database role exists.
- Importer can create/write only in raw staging and cannot create/write canonical leads.
- Application role has CRUD on canonical leads; readonly role has SELECT without write.
- Meltano 4.3.0 synthetic tap-csv -> target-postgres run loaded two fixture rows into raw staging only.
- Canonical lead count remained 0 before and after the synthetic import and API import preview.
- Synthetic raw table was removed after verification.
- Leads service is enabled and active on 127.0.0.1:8780.
- /api/health, /api/summary, dashboard /, and CSV preview returned successful local responses.
- CSV preview reported writes_performed=0.
- N8N port 127.0.0.1:5678 remains closed; workflow activation remains unauthorized.
- N8N focused integration/policy/community runtime suite passed 50 tests locally.
- Latest local backup/restore verification passed: 4 schemas, 8 contract tables, 104,677 provenance-manifest rows, 104,677 governed raw authority rows, canonical count 0.
- Ubuntu desktop launcher is installed and points only to the local 127.0.0.1:8780 service.

## Backup evidence

Protected dump:
/home/codestra/Backups/Leads/leads_workstation_20260923T200421Z.dump

SHA-256:
75c7fa8d8ccd564d7c21952ce16e0881f12d53e23b7897f97d227dede9ffd20b

## Gates that remain closed

- PAS-269 authority is frozen to the verified D: batch; governed raw staging is complete. Canonical promotion remains separately gated.
- The real batch remains `promotion_authorized=false`; no canonical real lead promotion is authorized.
- GitHub draft PR heads currently have no completed CI check runs; this local certificate does not replace required protected CI.
- N8N and Database-migrations integration PRs remain draft and must not be merged until their verification gates are green.
- No production/live calling, email, SMS, provider side effects, remote database mutation, or promotion of this backup node to source-of-truth is authorized.

## Readiness state

LOCAL BACKUP DEPLOYMENT READY / PRODUCTION NO-GO

The workstation is ready to operate as the authorized local backup/recovery Leads Platform with the frozen real batch in governed raw/provenance staging and local-only services. Canonical real-data promotion and production effects remain unauthorized.

## PAS-275 uncertain-match control

- Duplicate review records are queued in `lead_ops.duplicate_review` and exposed through governed API endpoints.
- Queue creation is idempotent for the same pending batch/source-row/fingerprint/candidate tuple.
- Resolution supports `accepted`, `rejected`, and `merged`; `merged` requires an existing candidate lead.
- Review resolution mutates review state and audit evidence only; it performs **zero automatic canonical lead writes**.
- The dashboard presents pending uncertain matches with explicit human review actions.
- This closes the behavior gap only after local API/readback tests pass; hosted CI remains a separate required gate.
## PAS-273/PAS-274/PAS-275 local verification refresh

Verified on the backup Ubuntu workstation on 2026-09-23:

- Duplicate-review API queue creation returned `201`, repeated queueing of the same pending tuple was idempotent, and review resolution returned `canonical_writes_performed=0`.
- `merged` without a candidate lead was rejected with `422`; repeated identical resolution was idempotent.
- The synthetic candidate lead remained at version `1` throughout review actions, proving the review path did not mutate the canonical lead row.
- Audit evidence was emitted for queue and resolution actions. Synthetic lead, review, and audit records were removed after verification; canonical lead count returned to `0`.
- Headless Chrome/Playwright verified navigation to Data Quality, rendering the pending uncertain-match card, confirmation + Accept distinct interaction, All Leads navigation, and return to Executive. No browser console errors or HTTP error responses remained after adding an inline empty favicon.
- Browser-driven review resolution preserved the canonical lead version and changed only review state to `accepted`; synthetic rows were removed and canonical count returned to `0`.

Hosted GitHub Actions remains a separate required release gate and is not represented as green by these local checks.



## Governed raw-to-canonical promotion verification — 2026-09-24

Implemented locally on the backup node:

- `lead_ops.import_row_manifest` binds every candidate to an exact staged batch/source-row/source-fingerprint tuple without granting the Leads API raw-schema access.
- The frozen authority batch has 104,677 manifest rows matching 104,677 raw rows and 104,677 distinct source fingerprints.
- `lead_ops.promotion_candidates` stores normalized review candidates; queue and review operations report `canonical_writes_performed=0`.
- Candidate creation rejects provenance tuples not present in the manifest.
- Incomplete candidates enter review; approval with missing required canonical fields is rejected.
- Approved candidate promotion requires both `provenance_manifest_verified=true` and `promotion_authorized=true` on a completed import batch.
- Synthetic authorized-batch test promoted exactly one synthetic lead through the Leads API, emitted audit/outbox evidence, rejected a canonical exact duplicate, and proved repeated promotion is idempotent with zero additional writes.
- Synthetic blocked-batch test returned `403` when `promotion_authorized=false`.
- All synthetic candidate/lead/audit/outbox/batch evidence was removed deterministically after verification; final canonical count returned to `0`.
- Frozen real batch remains `promotion_authorized=false`, `rows_accepted=0`; no real candidate was promoted.
- N8N port 5678 remains closed.

Latest protected backup after this extension:
`/home/codestra/Backups/Leads/leads_workstation_20260924T020521-0400.dump`
SHA-256: `599d744eb48281a59f5449d0abda9c609f5a235b221d58c3cc3e94e4ef2a637d`

Disposable restore verified 4 schemas, 8 contract tables, 104,677 manifest rows, 104,677 raw authority rows, canonical count `0`, and the real-batch promotion gate still closed.
## PAS-273/PAS-274 browser interaction verification — 2026-09-24

Implemented and verified on the localhost-only backup workstation:

- Added composable Owner and Priority controls alongside Search, Country, Business Category, and Status.
- Added local-browser saved views; saved-view state is browser-local preference data and never becomes canonical lead authority.
- Added a Lead Focus drill-down with explicit edit action, record details, activity history, and comment/note creation.
- Added `GET /api/leads/{lead_id}/activity` to provide deterministic activity readback.
- Synthetic API verification proved owner-only, priority-only, and Country + Business Category + Owner + Priority composed filters each returned exactly the intended lead.
- Headless Chrome verified all workstation views activate, the synthetic lead drills into Lead Focus, activity readback renders, a browser-created note is readable, and a saved view restores DR / Automation QA / QA Backup / high filters.
- Browser verification recorded no JavaScript exceptions, browser error-log entries, or failed network requests.
- All synthetic lead/activity/audit/outbox records created for this verification were removed; canonical lead count returned to `0`; the pre-existing four pending outbox evidence records remain preserved.

Hosted GitHub Actions remains a separate release gate and is still not represented as green.

