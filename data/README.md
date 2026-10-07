# Lead data storage

The data/private folder is the local staging area for lead/contact payloads. It is intentionally ignored by Git while the repository is not confirmed private.

Expected layout:

- data/private/workspace - organized lead workspace copied from C:\Users\Usuario\03_LEADS_AND_DATA
- data/private/incoming - newer candidate batches awaiting reconciliation
- runtime/leads.db - generated canonical runtime database; never committed

Large source formats are declared for Git LFS in .gitattributes.

Safety gate: do not remove the data/private ignore rule and do not push lead payloads until repository visibility is verified as PRIVATE.

Canonical workflow:
1. Stage sources locally.
2. Build a file manifest and hashes.
3. Import canonical master or approved batches.
4. Deterministically deduplicate by normalized email, phone, then entity identity.
5. Record import evidence and duplicate dispositions.
6. Query through the local API.
7. Publish raw lead payload only to an approved private data remote.
