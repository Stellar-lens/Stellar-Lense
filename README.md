# Stellar Lense

**Wash-trading detection for the Stellar DEX.**

Stellar Lense scores every asset on the Stellar decentralized exchange for wash-trading risk, combining statistical analysis, machine learning, and graph-based ring detection — then publishes those scores on-chain via a Soroban smart contract so anyone can verify them independently.

Formerly developed under the open-source LedgerLens project. Stellar Lense is a consolidated, solo-maintained rebuild: same detection engine, full commit history preserved, new product surface.

---

## What it does

- **Statistical fingerprinting** — Benford's Law analysis flags trade volume patterns that deviate from the digit distribution real markets naturally follow.
- **ML ensemble scoring** — Random Forest, XGBoost, and LightGBM models trained on labelled wash-trading patterns, with SHAP explanations so every score is interpretable, not a black box.
- **Graph-based ring detection** — surfaces coordinated trading rings across multiple accounts that single-trade analysis misses entirely.
- **On-chain risk registry** — scores are published via a Soroban contract, so they're independently verifiable rather than trusted on our word.
- **A real product surface** — a full risk-ranking dashboard, per-asset detail views, a wash-trading alert feed, market news/DD aggregation, and a phased trading-assist bot (see [Roadmap](#roadmap)).

## Status

Active solo development. Detection engine, API, and contract are functional and migrated from the original LedgerLens repos with full history intact. The web product (landing page, dashboard, alerts, asset detail views, news/DD feed) and the bot's Phase 1 backtesting engine are built; see [`docs/stellar-lens-project-plan.md`](docs/stellar-lens-project-plan.md) for the full roadmap and current phase.

CI (`make lint-all` + `make test-all`, see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)) is green for JS, Rust, and `apps/api`. `packages/core`'s pytest suite currently has known failures — mainly a `TestClient`/stacked-middleware incompatibility and tests that depend on optional extras (`mlflow`, `web3`, etc.) not installed by CI — blocking branch protection on that check until fixed.

## Architecture

```
apps/
├── web/          Product website (Next.js + TypeScript + Tailwind)
├── api/          Public REST API (FastAPI)
└── bot/          Trading-assist bot — phased: backtest → signal → non-custodial execution

packages/
├── core/         Detection engine — ingestion, Benford's Law, ML ensemble, SHAP
├── sdk-ts/       TypeScript SDK
├── sdk-py/       Python SDK
└── ui/           Shared design system / component library for apps/web

contracts/
└── soroban/      On-chain risk registry contract

data/
└── pipelines/    Raw + processed trade data, labelled training sets, ingestion

infra/
├── helm/         Deployment charts
├── monitoring/   Observability, alerting config
└── ci/           GitHub Actions workflows (the actual workflow lives at /.github/workflows, which is the only place GitHub Actions reads from — see infra/ci/README.md)

docs/             Project plan, design system, build/launch guides
```

Three independent toolchains, by design — the stack is intentionally mixed and each language keeps its native workspace tool rather than forcing one build system across all of it:

| Layer | Tool | Members |
|---|---|---|
| JS/TS | [pnpm](https://pnpm.io) workspaces | `apps/web`, `apps/bot`, `packages/sdk-ts`, `packages/ui` |
| Python | [uv](https://docs.astral.sh/uv/) workspace | `packages/core`, `apps/api` (`packages/sdk-py` is standalone, published independently) |
| Rust | Cargo workspace | `contracts/soroban` |

## Tech stack

- **Web**: Next.js, TypeScript, Tailwind CSS
- **API**: FastAPI (Python)
- **Detection engine**: Python — pandas/numpy for ingestion, scikit-learn/XGBoost/LightGBM for the ML ensemble, SHAP for explainability
- **Smart contract**: Soroban (Rust), deployed on Stellar
- **Data**: Historical + live Stellar DEX trade data via Horizon

## Getting started

> This is a solo, closed-development project — not currently accepting outside contributions. Setup notes below are for local development reference.

```bash
git clone https://github.com/Stellar-lens/Stellar-Lense.git
cd Stellar-Lense

# JS/TS workspaces
pnpm install

# Python workspace
uv sync

# Rust contract workspace
cd contracts/soroban && cargo build
```

Run the full lint/test suite across all three toolchains (the same commands CI runs on every PR into `main`):

```bash
make lint-all
make test-all
```

See each app's own README for service-specific run instructions (`apps/web`, `apps/api`, `apps/bot`).

## Design system

The visual and typographic system — color tokens, type scale, layout principles — is documented in [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) and mirrored in the [Figma file](https://www.figma.com/design/hRiGmu5WcbVgmB0TuNZfCy/Steller-Lens). Dark, dense, data-forward — closer to a trading terminal than a generic SaaS dashboard, with a single Poppins type family carrying the full hierarchy.

## Roadmap

Full detail in [`docs/stellar-lens-project-plan.md`](docs/stellar-lens-project-plan.md). Summary:

- [x] Monorepo consolidation from the original 5 LedgerLens repos, history preserved
- [x] Rebrand pass (LedgerLens → Stellar Lense)
- [x] Website rebuild — landing page + risk-ranking dashboard
- [x] Alerts feed, asset detail views, news/DD aggregation (CryptoPanic + CoinDesk)
- [x] Trading-assist bot, Phase 1: backtesting engine (no live funds)
- [ ] Get `packages/core`'s pytest suite green in CI, then turn on branch protection
- [ ] Trading-assist bot, Phase 2: live signal/alert bot
- [ ] Trading-assist bot, Phase 3: non-custodial execution via scoped Soroban session permissions — **gated on independent security review**
- [ ] Public launch

## Security

The Soroban contract publishes on-chain risk data and will eventually gate bot execution permissions. Mainnet deployment is gated on an independent security review — see `contracts/soroban/README.md` for the current audit-prep status. Found a vulnerability? Please don't open a public issue — [contact details to be added before public launch].

## License

[License to be finalized before public launch — carried over from the original LedgerLens open-source licensing where applicable; confirm terms before removing public access to any previously open-sourced component.]

## Acknowledgments

Built on the detection engine and research originally developed under the open-source LedgerLens project.
