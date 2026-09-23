# Leads Workstation — Backup/Local Deployment Readiness

Date: 2026-09-23
Host: desktop-ubuntu-codestra
Authority: backup/local execution and recovery only; not production authority.

## Verified

- PostgreSQL 18.6 local instance is reachable on 127.0.0.1:5432.
- Database leads_workstation has schemas lead_import_raw, leads, lead_audit, and lead_ops.
- Six canonical/operations tables are present.
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
- Local backup/restore verification passed: 4 schemas, 6 tables, canonical count 0.
- Ubuntu desktop launcher is installed and points only to the local 127.0.0.1:8780 service.

## Backup evidence

Protected dump:
/home/codestra/Backups/Leads/leads_workstation_20260923T200421Z.dump

SHA-256:
75c7fa8d8ccd564d7c21952ce16e0881f12d53e23b7897f97d227dede9ffd20b

## Gates that remain closed

- No canonical real lead source has been identified. PAS-269 remains open.
- No real lead import is authorized until PAS-269 is satisfied.
- GitHub draft PR heads currently have no completed CI check runs; this local certificate does not replace required protected CI.
- N8N and Database-migrations integration PRs remain draft and must not be merged until their verification gates are green.
- No production/live calling, email, SMS, provider side effects, remote database mutation, or promotion of this backup node to source-of-truth is authorized.

## Readiness state

LOCAL BACKUP DEPLOYMENT READY / PRODUCTION NO-GO

The workstation is ready to operate as the authorized local backup/recovery Leads Platform with synthetic/test data and local-only services. It is not authorized for real-data ingestion or production effects.
