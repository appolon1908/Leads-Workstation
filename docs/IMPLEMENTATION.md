# Leads Workstation implementation

## Runtime

The workstation is a Python 3.11+ local application with:

- SQLite canonical runtime at runtime/leads.db
- streaming CSV ingestion
- deterministic duplicate fingerprints
- import-batch evidence with SHA-256 source hashes
- lead audit events
- duplicate review ledger
- indexed country, business category, status, email and phone fields
- local HTTP dashboard and JSON API
- default loopback-only binding at 127.0.0.1

## API

- GET /health
- GET /api/stats
- GET /api/leads?limit=100&q=...&country=...&category=...&status=...
- GET /api/leads/{lead_id}

The service refuses non-loopback binding unless --allow-network is supplied.

## Laptop source of truth

Current master:
C:\Users\Usuario\03_LEADS_AND_DATA\01_CORE\Master\MASTER_SALES_LEADS_20260921.csv

The importer preserves source payload, source path, verification fields and batch evidence while mapping the master into the repository country/category contract.

## Private-data gate

The GitHub repository was public when implementation started. Lead/contact payloads are therefore staged locally under ignored data/private and are not eligible for push until repository privacy is verified as PRIVATE.
