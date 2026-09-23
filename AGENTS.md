# AGENTS.md

## Repository
ingtrader21-spec/Leads-Workstation

## Mission workflow
00 Authority & Architecture -> 10 Build & Test -> 20 Integration & Dependencies -> 30 Staging & Release.

## Rules
- Country and Business Category remain separate fields end to end.
- Never promote raw import data directly into canonical leads without validation/dedupe.
- Canonical lead writes go through the Leads service/API and must be auditable.
- Meltano owns ingestion, Database-migrations owns DB schema, N8N owns downstream automation.
- Do not let N8N write canonical lead tables directly.
- Use one active writer branch/worktree per mission.
- Completion requires implementation + tests + local runtime/readback where applicable.
