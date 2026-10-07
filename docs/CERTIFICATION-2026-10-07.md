# Certification — 2026-10-07

## Result

The Leads Workstation runtime was implemented and exercised on the connected Codestra laptop.

Certified evidence:

- source master rows seen: 88,379
- canonical runtime rows inserted: 88,379
- unintended duplicate collapses: 0
- rows with normalized email: 87,958
- rows with normalized phone: 86,762
- private staged lead/source files: 118
- private staged bytes: 214,910,524
- source master SHA-256: 643462c77284ae2b36fbdddb0847f33c5cacee23014cf64cdb4af3d44ad44b2e
- Python unit tests: passed
- Python compile check: passed
- live local API health check: passed
- live API lead total: 88,379
- filtered API query: passed

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
- local create/update/search API
- loopback-only service by default
- private-data staging and manifest generation
- repeatable install, import, start, backup and certification scripts
- CI runs contract validation, unit tests and compilation

## Data publication status

The repository was public when implementation began. Lead/contact payloads are therefore protected under the git-ignored data/private directory. No lead PII was committed or pushed to the public repository.

The code can be promoted through the governed branch flow. Raw lead data may only be published after the GitHub repository is verified PRIVATE.
