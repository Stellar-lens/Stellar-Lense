# infra/ci

GitHub Actions only reads workflows from `.github/workflows/` at the repo
root, so the workflows live there; this file documents them.

| Workflow | Trigger | What it runs |
|---|---|---|
| [`ci.yml`](../../.github/workflows/ci.yml) | every pull request into `main` | `make lint-all` and `make test-all` (JS, Python, Rust); the required check for branch protection |

`make lint-all` / `make test-all` are the same commands a contributor runs
locally, so "CI is green" and "it works on my machine" mean the same thing.
See the comments on each target in [`/Makefile`](../../Makefile) for the
non-obvious details (pinned ruff version, per-package pytest scoping, Typer
terminal-detection workaround).

## History

This repository was assembled from several source repos with `git subtree`.
Each brought its own `.github/workflows/`, which GitHub never ran from a
subdirectory. Those inert copies were removed in the consolidation pass;
they remain on the `archive/pre-consolidation` branch.
