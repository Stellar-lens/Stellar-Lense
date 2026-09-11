# Stellar Lense

Wash-trading detection for the Stellar DEX — Benford's Law statistical
analysis + an ML ensemble + graph-based ring detection, publishing risk
scores via a Soroban smart contract, a public REST API, and a product
website. Consolidated monorepo, rebuilt from the five source repos under
the old LedgerLens org (Ledger-Lenz). Full context and roadmap:
`docs/stellar-lens-project-plan.md`.

## Layout

```
apps/
├── web/          Product website (Next.js). Replaces the old LedgerLens dashboard repo.
├── api/          Public REST API (FastAPI). From the old LedgerLens API repo (Ledegerlens-api).
└── bot/          Trading bot service (phased: backtest → signal → execution). New.

packages/
├── core/         Detection engine (ingestion, Benford, ML, SHAP). From the old LedgerLens core repo.
├── sdk-ts/       TypeScript SDK. From core/sdk.
├── sdk-py/       Python SDK. From core/packages/stellar-lense-sdk.
└── ui/           Shared design system / component library for apps/web. New.

contracts/
└── soroban/      On-chain risk registry contract(s). From the old LedgerLens contract repo.

data/
└── pipelines/    Raw + processed trade data, labelled training sets, ingestion. From the old LedgerLens data repo.

infra/
├── helm/         Deployment charts. New.
├── monitoring/   Dashboards, alerting, observability config. New.
└── ci/           GitHub Actions workflows, consolidated from the .github org repo.

docs/             Project plan, design tokens, build guide.
```

This is currently a skeleton: directories, workspace configs, and
placeholder manifests only. No repo content has been migrated in yet — see
`docs/stellar-lens-project-plan.md` §6 for the migration plan (`git
subtree`/`git filter-repo` per source repo, to preserve history).

## Workspaces

The stack is intentionally mixed (Python core/api, Rust contracts, TS
web/bot/sdk/ui), so each language keeps its own native workspace tool
rather than forcing one build system to unify everything:

- **JS/TS** — [pnpm](https://pnpm.io) workspace. Members: `apps/web`,
  `apps/bot`, `packages/sdk-ts`, `packages/ui`. Config: `pnpm-workspace.yaml`.
- **Python** — [uv](https://docs.astral.sh/uv/) workspace. Members:
  `packages/core`, `apps/api`. Config: root `pyproject.toml`.
  `packages/sdk-py` is Python but deliberately stands outside this
  workspace (its own `pyproject.toml`, built/published independently).
- **Rust** — Cargo workspace scoped to `contracts/soroban/Cargo.toml`,
  independent of the two workspaces above.

A root `Makefile` orchestrates across all three: `make lint-all` / `make
test-all` fan out to each toolchain's own lint/test command (see the
Makefile for the per-language sub-targets).

## Status

Skeleton only, no application code yet. Next steps per the project plan:
migrate each source repo in with history preserved, get existing CI green
in the new structure, then start the rebrand pass and website rebuild.
