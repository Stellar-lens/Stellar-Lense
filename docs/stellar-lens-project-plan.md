# Stellar Lense — Project Plan & Roadmap

> Working brief for the LedgerLens → Stellar Lense rebuild. Written to be handed to Claude Code as an execution spec.

---

## 1. Context

The existing project ("LedgerLens") is a wash-trading detection system for the Stellar DEX: Benford's Law statistical analysis + an ML ensemble (Random Forest/XGBoost/LightGBM) + graph-based ring detection, publishing risk scores via a Soroban smart contract, a public REST API, and a web dashboard. It currently lives across 6 repos in the `Ledger-Lenz` GitHub org:

| Repo | Role | Stack |
|---|---|---|
| `.github` | Org-wide CI/CD, templates | YAML |
| `Ledgerlens-data` | Raw + processed trade data, labelled training sets | Python/SQL |
| `Ledgerlens-core` | Detection engine (ingestion, Benford, ML, SHAP) | Python |
| `Ledegerlens-api` | Public REST API | Python (FastAPI) |
| `Ledgerlens-dashboard` | Web dashboard | TS/React |
| `Ledgerlens-contract` | On-chain risk registry | Rust (Soroban) |

The public-facing version (via Drip Wave / GiveTH / Grantfox) exists mainly to source grant funding — not the real product experience.

**Goal:** go solo, rename to Stellar Lense, consolidate into one monorepo, and replace the "basic dashboard" with a real product website (UI/UX-designed), plus new features: a phased trading bot and a market news/DD feed.

---

## 2. Target Monorepo Structure

Consolidate the 5 functional repos (skip `.github`'s content, fold its CI patterns in) into one monorepo. Suggested layout:

```
stellar-lense/
├── apps/
│   ├── web/                 ← NEW full website (replaces Ledgerlens-dashboard)
│   ├── api/                 ← from Ledegerlens-api
│   └── bot/                 ← NEW trading bot service (Phase 1-3, see §4)
├── packages/
│   ├── core/                 ← detection engine, from Ledgerlens-core (ingestion/, detection/, config/)
│   ├── sdk-ts/                ← TypeScript SDK (from core/sdk)
│   ├── sdk-py/                ← Python SDK (from core/packages/ledgerlens-sdk)
│   └── ui/                    ← shared design system / component library for apps/web
├── contracts/
│   └── soroban/                ← from Ledgerlens-contract
├── data/
│   └── pipelines/               ← from Ledgerlens-data
├── infra/
│   ├── helm/
│   ├── monitoring/
│   └── ci/                       ← consolidated GitHub Actions (from .github)
├── docs/
└── README.md
```

**Tooling recommendation:** given the mixed stack (Python core/api, Rust contracts, TS web/bot), use a lightweight workspace approach rather than a single build tool trying to unify everything:
- `pnpm` workspaces for the JS/TS packages (`apps/web`, `apps/bot`, `packages/sdk-ts`, `packages/ui`)
- Python packages (`packages/core`, `apps/api`) managed via `uv`/`pyproject.toml` workspace members (core already uses `uv.lock`)
- Rust contracts stay a Cargo workspace under `contracts/soroban`
- Root-level `Makefile` or `justfile` to orchestrate cross-language tasks (lint all, test all, etc.)

**Migration approach:** use `git subtree` or `git filter-repo` per source repo to preserve commit history when pulling each into the monorepo, rather than a fresh copy-paste (worth it given `core` alone has 1,000+ commits).

---

## 3. Rebrand Checklist

Systematic pass once naming is confirmed:
- [ ] Package names: `@ledgerlens/sdk` → new scope, `ledgerlens-sdk` (Python/Rust) → new name
- [ ] Env vars: `LEDGERLENS_*` prefix across `.env.example`, `config/settings.py`, docs
- [ ] Soroban contract: `ledgerlens-score` contract name/symbol
- [ ] API routes/response headers referencing `X-LedgerLens-*`
- [ ] Repo names, GitHub org
- [ ] README, docs/, CHANGELOG, ADRs
- [ ] Docker image names, Helm chart names
- [ ] Domain/branding assets, favicon, OG images
- [ ] Webhook payload field names (`X-LedgerLens-Signature`, etc.) — **breaking change for any existing subscribers**, needs a migration note since this was previously open-source with outside contributors/dependents

---

## 4. Feature Roadmap

### 4.1 Website Rebuild (replaces `Ledgerlens-dashboard`)
- Full UI/UX design pass (pending your references) — not a "basic dashboard," a real product site
- Core surfaces to carry over from the API: risk scores, alerts, asset risk rankings, SHAP explanations, analyst review queue
- New surfaces: landing/marketing page, docs, the news feed (§4.3), trading bot interface (§4.2)
- **Stack: Next.js.** Reasoning: SSR/SEO for the public marketing/landing pages (a client-only SPA is invisible to search engines and slow on first load); lets marketing pages and the authenticated app (risk dashboards, bot controls) share one codebase with different rendering strategies per route; API routes give a place for thin server-side glue (e.g. proxying the news API key) without a separate service. Trade-off acknowledged: more build complexity and a server runtime vs. a plain SPA — worth it here because the site needs real public/SEO surface, not just an authenticated dashboard.

### 4.2 Trading Bot — phased, shared engine
Not three separate bots — one strategy engine with a pluggable execution mode:

**Phase 1 — Backtesting engine**
- Historical Stellar DEX data (leverage existing `ledgerlens-data`/`core` ingestion)
- Strategy definition + simulation, no real funds involved
- Fastest to ship, validates strategies before anything riskier

**Phase 2 — Signal/alert bot**
- Same engine against live market data
- Pushes buy/sell signals via dashboard/webhook/Telegram — no execution
- Differentiator: wire in existing LedgerLens risk scores so signals account for wash-trading risk on the asset, not just price action

**Phase 3 — Auto-execution**
- Same engine, now placing real orders
- Requires: slippage & failure handling, security hardening (highest-risk phase — build last, only after Phase 1/2 validate the strategy logic)
- **Execution model decision: non-custodial, scoped session permissions.** The bot never holds user private keys. Execution happens through the user's own wallet (Freighter/Albedo) or, better, a Soroban smart-wallet/session-key contract that authorizes the bot to execute within defined limits (max amount, asset allowlist, time window) — revocable anytime. Rejected the custodial alternative (bot holds keys directly) because it makes the project a custodian of user funds, which is a much larger security and regulatory liability. This should inform Phase 1's engine design (keep execution as a pluggable interface) even though Phase 3 itself is last.

### 4.3 News / DD Feed
- **Primary source: CryptoPanic API** — sentiment-tagged (bullish/bearish/important), filterable per-currency, purpose-built for DD-style feeds rather than a generic firehose; cheap, well-documented, existing client libraries.
- **Secondary source: CoinDesk** (RSS/API) — for deeper editorial/regulatory pieces CryptoPanic's aggregator headlines don't cover.
- Plus Stellar/SDEX-specific data from existing Horizon ingestion.
- Surface as a feed in the web app; consider correlating news events with risk-score movements as a unique angle (e.g., "asset X risk score spiked after this listing news")

---

## 5. Decisions Locked In
1. **Name:** Stellar Lense.
2. **News API:** CryptoPanic (primary) + CoinDesk (secondary).
3. **`apps/web` stack:** Next.js.
4. **Phase 3 execution model:** non-custodial, scoped Soroban session permissions (see §4.2).

## 5a. Still Open
- Need a CryptoPanic + CoinDesk API key/account set up before `apps/web` news integration work starts.
- Exact session-key/smart-wallet contract design for Phase 3 — not urgent, but Phase 1's engine interface should be built with a pluggable execution mode from day one so this slots in later without a rewrite.

---

## 6. Suggested First Session in Claude Code
1. Clone all 5 repos locally in the codespace.
2. Set up the monorepo skeleton (§2) with workspace tooling.
3. Migrate each repo in with history preserved (`git subtree`/`filter-repo`).
4. Get the existing CI green in the new structure before touching any feature work.
5. Only then start on the rebrand pass and the website rebuild.
