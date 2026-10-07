# Certification — 2026-10-07

## Current certified result

The Leads Workstation runtime was implemented and exercised on the connected Codestra laptop.

Certified evidence:

- baseline master rows: 88,379
- promoted governed candidate records: 107
- current canonical lead total: 88,486
- rows with normalized email: 87,958
- rows with normalized phone: 86,869
- candidate batch appraisers-2019-20190605: 107 promoted, 0 failed
- candidate source contacts: 107 named appraisers
- candidate source distinct phones: 229
- strict reconciliation against the baseline master: 0 name overlaps, 0 phone overlaps
- private staged lead/source files: 118
- private staged bytes: 214,910,524
- source master SHA-256: 643462c77284ae2b36fbdddb0847f33c5cacee23014cf64cdb4af3d44ad44b2e
- Python unit tests: 8 passed
- Python compile check: passed
- live local API health check: passed
- live API lead total: 88,486
- candidate summary API: passed

## Implemented behavior

- canonical lead import into SQLite
- canonical lead ID preservation
- deterministic fallback duplicate detection for incoming records without canonical IDs
- normalized email and phone indexes
- Country and Business Category remain separate
- geographic fallback normalization for explicit Spain, Dominican Republic, Mexico and U.S. B2B categories
- import-batch ledger with source SHA-256
- per-lead audit events
- duplicate review ledger
- candidate lead staging/review ledger
- XLSX first-sheet parser for the historical appraiser package
- candidate matching by normalized names and phones
- promotion of only records classified as new
- historical candidates promoted with status Needs Verification
- candidate summary and listing API endpoints
- local create/update/search API
- loopback-only service by default
- private-data staging and manifest generation
- repeatable install, import, start, backup and certification scripts
- CI runs contract validation, unit tests, compilation and required Codestra control-plane jobs

## Data publication status

The repository is still public. Lead/contact payloads are therefore protected under the git-ignored data/private directory. No lead PII is committed or pushed to the public repository.

The code may continue through the governed branch flow. Raw lead data may only be published after repository visibility is verified PRIVATE.
