# infra/ci

GitHub Actions only reads workflows from `.github/workflows/` at the repo
root — it can't be pointed at `infra/ci/`, so the actual workflow lives at
[`/.github/workflows/ci.yml`](../../.github/workflows/ci.yml), not here.
This file just documents the CI setup and its history.

Runs `make lint-all` and `make test-all` (see `/Makefile`) on every pull
request into `main` — the single required check for branch protection.

## What replaced

Each of the 5 source repos this monorepo was assembled from still has its
own `.github/workflows/` from before the migration (`data/pipelines/`,
`packages/core/`, `contracts/soroban/`, one org-wide `.github` repo whose
content was intentionally skipped per
`docs/stellar-lens-project-plan.md` §2 — "skip `.github`'s content, fold
its CI patterns in"). None of those nested `.github/workflows/` directories
do anything now — GitHub Actions doesn't look inside subdirectories for
workflows — they're inert leftovers from the `git subtree` migration, not
active CI. `.github/workflows/ci.yml` is what replaced them for the
lint/test check; those nested files haven't been individually reviewed for
other patterns worth porting (lock-file freshness checks, deploy smoke
tests, etc.) - that's a separate follow-up, not done here.

## Known issues as of the last CI audit

See the CI-readiness report for the full breakdown (pass/fail per
ecosystem, and what's blocking branch protection). Two Makefile bugs were
fixed as part of getting this workflow to actually run at all:
`lint-py`/`test-py` previously used bare `uv run ruff`/`uv run pytest` at
the workspace root, which either failed outright or silently collected the
wrong tests - see the comments on those targets in `/Makefile`.
