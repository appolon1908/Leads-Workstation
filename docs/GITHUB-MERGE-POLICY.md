# GitHub source-merge policy

GitHub checks and applicable repository rulesets enforce source-merge readiness.
The obsolete `codestra-control-plane` and `codestra/control-plane` jobs are
retired. Historical certification text and file-presence assertions are not
evidence that the current pull-request revision passes validation.

## Checks

The development workflow retains three substantive GitHub Actions jobs:

- `validate`: contracts, static quality, unit tests and the security scan.
- `postgres-redis-integration`: the production test suite with PostgreSQL and Redis.
- `privacy-security`: private-data exclusion and the repository security scan.

As verified on 2026-11-03, the required status-check rules bind `validate` to
GitHub Actions (integration ID `15368`) and require the branch to be up to date.
The additional two jobs remain part of development CI. The main branch's
source-only workflow emits only `validate`; do not require absent job contexts
across all branches. GitHub's live rulesets are authoritative if this snapshot
becomes stale.

## Protections

The existing rule IDs retain their branch scopes and enforcement:

- [24625228](https://github.com/appolon1908/Leads-Workstation/rules/24625228):
  required Actions validation and strict branch freshness.
- [24624080](https://github.com/appolon1908/Leads-Workstation/rules/24624080):
  required Actions validation, reviews, resolved discussions, and protection
  against branch deletion and force pushes on its configured branches.
- [26405664](https://github.com/appolon1908/Leads-Workstation/rules/26405664):
  signed commits, fresh approvals, code-owner reviews where applicable,
  last-push approval, resolved discussions, and deletion/force-push protections.

No bypass actors are configured. A green check does not substitute for any
other applicable rule. Inspect the current PR head and GitHub's mergeability
result; cancelled, pending or missing required checks do not establish readiness.
Resolve conflicts and review findings, update stale branches, and obtain the
required independent review before merging. Do not fabricate controller statuses
or disable protections to make a PR mergeable.

## Delivery boundary

This policy governs source merges only. Publication continues to follow the
assigned worktree's publishing policy. A source merge or publication does not
authorize deployment, production activation, provider effects or canonical-data
writes. Existing Leads API write and private-data boundaries still apply.
